"""Adapter from `scitech_agent.Agent` to the backend's `ChatAgent` port (W2-D3-DAT-1).

The agent package does not import the backend, so its events carry `ScoredChunk`s; this module
turns them into the contract `Source` payloads and agent errors into backend `AgentError`s.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

from scitech_agent import events as agent_events
from scitech_agent.agent import Agent
from scitech_agent.retrieval import ScoredChunk

from .agent_port import (
    AgentError,
    AgentEvent,
    DoneEvent,
    FollowupsEvent,
    SourcesEvent,
    TokenEvent,
)
from .schemas import Done, ErrorCode, Source

SNIPPET_CHARS = 300


def to_source(chunk: ScoredChunk) -> Source:
    snippet = chunk.text
    if len(snippet) > SNIPPET_CHARS:
        snippet = snippet[:SNIPPET_CHARS].rsplit(" ", 1)[0] + " ..."
    return Source(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        title=chunk.title,
        score=chunk.score,
        url=chunk.url,
        snippet=snippet,
        source=chunk.source,  # type: ignore[arg-type]  # validated by the Source model
        published_at=chunk.published_at,  # type: ignore[arg-type]  # ISO string parsed to date
        categories=list(chunk.categories) or None,
    )


class AgentAdapter:
    """`ChatAgent` backed by the real agent pipeline."""

    def __init__(self, agent: Agent) -> None:
        self.agent = agent

    def warm_up(self) -> None:
        self.agent.warm_up()

    def run(self, session_id: str, message: str) -> Iterator[AgentEvent]:
        try:
            for event in self.agent.run(session_id, message):
                match event:
                    case agent_events.SourcesEvent(chunks=chunks):
                        yield SourcesEvent([to_source(c) for c in chunks])
                    case agent_events.TokenEvent(text=text):
                        yield TokenEvent(text)
                    case agent_events.FollowupsEvent(questions=questions):
                        yield FollowupsEvent(list(questions))
                    case agent_events.DoneEvent():
                        done = Done(
                            insufficient_evidence=event.insufficient_evidence,
                            message_id=event.message_id,
                        )
                        yield DoneEvent(done)
        except agent_events.AgentError as exc:
            raise AgentError(cast(ErrorCode, exc.code), exc.message) from exc
