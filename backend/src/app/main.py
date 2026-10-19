"""FastAPI entry point. Endpoints follow docs/contracts/api.openapi.yaml (frozen 2026-10-15)."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from scitech_agent.demo import demo_agent

from .agent_adapter import AgentAdapter
from .agent_port import ChatAgent
from .schemas import ChatRequest
from .sse import chat_events


@lru_cache(maxsize=1)
def get_agent() -> ChatAgent:
    """Agent used by `/chat`: the real pipeline with the offline demo retriever and LLM, until
    the index and the LLM server are wired in (W3). One instance, so session history persists.
    Tests override it."""
    return AgentAdapter(demo_agent())


def cors_origins_from_env() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def create_app(cors_origins: list[str] | None = None) -> FastAPI:
    app = FastAPI(title="SciTech RAG Agent", version="0.2.1")

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
