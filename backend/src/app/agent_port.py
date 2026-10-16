"""What the backend expects from an agent, and the events it streams.

The backend only orchestrates (backend/AGENTS.md): it validates the request, asks an agent for
events and turns them into server-sent events. The real `Agent` (W2-D3-DAT-1) implements
`ChatAgent`; until then `FakeAgent` stands in, so the endpoint and the UI can be built offline.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol

from .schemas import Done, ErrorCode, Source


@dataclass(frozen=True)
class SourcesEvent:
    sources: list[Source]


@dataclass(frozen=True)
class TokenEvent:
    text: str


@dataclass(frozen=True)
class FollowupsEvent:
    questions: list[str]


@dataclass(frozen=True)
class DoneEvent:
    done: Done = field(default_factory=Done)


AgentEvent = SourcesEvent | TokenEvent | FollowupsEvent | DoneEvent


class AgentError(Exception):
    """Failure the user should see as an `error` event with a contract error code."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code: ErrorCode = code
        self.message = message


class ChatAgent(Protocol):
    def run(self, session_id: str, message: str) -> Iterator[AgentEvent]:
        """Yield `SourcesEvent` first, then tokens, optional follow-ups and one `DoneEvent`.

        Raise `AgentError` for failures that map to a contract error code.
        """
        ...
