"""Turn agent events into server-sent events exactly as the frozen contract describes.

Every `data:` line is JSON (so newlines in tokens cannot break the framing), `sources` comes first
when present (a request that fails before the sources is a single `error` event, #36), and exactly
one `done` or `error` ends the stream.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

from .agent_port import (
    AgentError,
    ChatAgent,
    DoneEvent,
    FollowupsEvent,
    SourcesEvent,
    TokenEvent,
)
from .schemas import Error, ErrorCode

logger = logging.getLogger(__name__)

MAX_FOLLOWUPS = 4


def format_event(name: str, payload: Any) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _error(code: ErrorCode, message: str) -> str:
    return format_event("error", Error(code=code, message=message).model_dump())


def chat_events(agent: ChatAgent, session_id: str, message: str) -> Iterator[str]:
    """Run the agent and yield SSE frames; contract violations by the agent become `internal`."""
    sources_sent = False
    try:
        for event in agent.run(session_id, message):
            if not sources_sent and not isinstance(event, SourcesEvent):
                raise ContractViolation(f"first event was {type(event).__name__}, not sources")
            match event:
                case SourcesEvent(sources=sources):
                    if sources_sent:
                        raise ContractViolation("sources sent twice")
                    sources_sent = True
                    yield format_event(
                        "sources", [s.model_dump(mode="json", exclude_none=True) for s in sources]
                    )
                case TokenEvent(text=text):
                    yield format_event("token", text)
                case FollowupsEvent(questions=questions):
                    yield format_event("followups", questions[:MAX_FOLLOWUPS])
                case DoneEvent(done=done):
                    yield format_event("done", done.model_dump(exclude_none=True))
                    return
        raise ContractViolation("agent stopped without a done event")
    except AgentError as exc:
        yield _error(exc.code, exc.message)
    except Exception:  # noqa: BLE001 - never leak internals to the client; log them instead
        logger.exception("chat stream failed (session %s)", session_id)
        yield _error("internal", "Internal error while answering. Please try again.")


class ContractViolation(RuntimeError):
    """The agent produced events in an order the API contract does not allow."""
