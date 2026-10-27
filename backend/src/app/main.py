"""FastAPI entry point. Endpoints follow docs/contracts/api.openapi.yaml (frozen 2026-10-15)."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Annotated, cast

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from scitech_agent import events as agent_events
from scitech_agent.demo import demo_agent
from scitech_agent.factory import agent_from_env

from .agent_adapter import AgentAdapter
from .agent_port import AgentError, AgentEvent, ChatAgent
from .schemas import ChatRequest, ErrorCode
from .sse import chat_events

logger = logging.getLogger(__name__)

AGENT_MODES = ("real", "demo")


def agent_mode(env: Mapping[str, str] | None = None) -> str:
    """`AGENT_MODE`: `real` (configured retriever and LLM; the default) or `demo` (offline)."""
    env = os.environ if env is None else env
    mode = (env.get("AGENT_MODE") or "real").strip().lower()
    if mode not in AGENT_MODES:
        raise ValueError(f"AGENT_MODE must be one of {', '.join(AGENT_MODES)}, got {mode!r}")
    return mode


class UnavailableAgent:
    """Stands in for an agent that could not be built: each request gets one `error` event."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code: ErrorCode = code
        self.message = message

    def run(self, session_id: str, message: str) -> Iterator[AgentEvent]:
        raise AgentError(self.code, self.message)
        yield  # a generator, like every ChatAgent


@lru_cache(maxsize=1)
def _demo_agent() -> ChatAgent:
    return AgentAdapter(demo_agent())


@lru_cache(maxsize=1)
def _real_agent() -> ChatAgent:
    return AgentAdapter(agent_from_env())


def get_agent() -> ChatAgent:
    """Agent used by `/chat`, chosen by `AGENT_MODE`. One instance per mode, so session history
    persists. If the real agent cannot be built, the request gets an `error` event and the next
    request tries again (a failure is not cached). Tests override it."""
    if agent_mode() == "demo":
        return _demo_agent()
    try:
        return _real_agent()
    except agent_events.AgentError as exc:
        return UnavailableAgent(cast(ErrorCode, exc.code), exc.message)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Check `AGENT_MODE`, build the agent and, in real mode, warm up its retriever at startup,
    so a wrong setting shows in the log and the embedding model is loaded before the first
    question (the server still starts if the build fails, and `/chat` reports the error)."""
    mode = agent_mode()
    agent = get_agent()
    if isinstance(agent, UnavailableAgent):
        logger.error("AGENT_MODE=%s: agent not available (%s), see the log above", mode, agent.code)
    else:
        if mode == "real" and isinstance(agent, AgentAdapter):
            # Load the embedding model now (14-15 s on a laptop), not in the first question.
            await asyncio.to_thread(agent.warm_up)
        logger.info("AGENT_MODE=%s: agent ready", mode)
    yield


def cors_origins_from_env() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def create_app(cors_origins: list[str] | None = None) -> FastAPI:
    app = FastAPI(title="SciTech RAG Agent", version="0.2.1", lifespan=lifespan)

    origins = cors_origins_from_env() if cors_origins is None else cors_origins
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe used by CI, Docker Compose and the frontend."""
        return {"status": "ok"}

    @app.post("/chat")
    def chat(
        request: ChatRequest, agent: Annotated[ChatAgent, Depends(get_agent)]
    ) -> StreamingResponse:
        """Stream the answer as server-sent events; an invalid body is rejected with 422 first."""
        return StreamingResponse(
            chat_events(agent, request.session_id, request.message),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()
