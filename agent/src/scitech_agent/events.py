"""Events yielded by `Agent.run`, one per API event type (docs/contracts/api.openapi.yaml).

The agent does not import the backend: the backend maps these events to its SSE payloads.
Order: `SourcesEvent` first, then `TokenEvent`s, an optional `FollowupsEvent` and one `DoneEvent`.
A failure raises `AgentError`; it may come before `SourcesEvent` (retrieval failed, issue #36).
"""

from __future__ import annotations

from dataclasses import dataclass

from scitech_agent.retrieval import ScoredChunk

ERROR_CODES = ("llm_unavailable", "retrieval_failed", "timeout", "internal")


@dataclass(frozen=True)
class SourcesEvent:
    chunks: list[ScoredChunk]


@dataclass(frozen=True)
class TokenEvent:
    text: str


@dataclass(frozen=True)
class FollowupsEvent:
    questions: list[str]


@dataclass(frozen=True)
class DoneEvent:
    insufficient_evidence: bool = False
    message_id: str | None = None


AgentEvent = SourcesEvent | TokenEvent | FollowupsEvent | DoneEvent


class AgentError(Exception):
    """A failure the user sees as an `error` event. `code` is a contract `Error.code`; `message`
    is safe to show (no internals)."""

    def __init__(self, code: str, message: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"unknown error code {code!r}")
        super().__init__(message)
        self.code = code
        self.message = message
