"""Deterministic stand-in agent for tests, local development and the frontend (W2-D2-DAT-1).

It needs no LLM, no index and no network. The default answer cites its two sources with `[1]` and
`[2]`. A message containing "insufficient" triggers the insufficient-evidence branch; a message
containing "fail:<code>" raises `AgentError` with that code after the sources (to exercise the
`error` event in the UI).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date

from .agent_port import (
    AgentError,
    AgentEvent,
    DoneEvent,
    FollowupsEvent,
    SourcesEvent,
    TokenEvent,
)
from .schemas import Done, ErrorCode, Source

FAKE_SOURCES = [
    Source(
        chunk_id="1706.03762#0",
        doc_id="1706.03762",
        title="Attention Is All You Need",
        score=0.82,
        url="https://arxiv.org/abs/1706.03762",
        snippet="The dominant sequence transduction models are based on complex recurrent or ...",
        source="arxiv",
        published_at=date(2017, 6, 12),
        categories=["cs.CL", "cs.LG"],
    ),
    Source(
        chunk_id="wiki-Transformer_(deep_learning_architecture)#0",
        doc_id="wiki-Transformer_(deep_learning_architecture)",
        title="Transformer (deep learning architecture)",
        score=0.74,
        url="https://en.wikipedia.org/wiki/Transformer_(deep_learning_architecture)",
        snippet="A transformer is a deep learning architecture based on multi-head attention ...",
        source="wikipedia",
    ),
]

FAKE_ANSWER = (
    "This is a fake answer from the stub agent. "
    "The Transformer relies only on attention, without recurrence [1].\n"
    "It is now the standard architecture for language models [2]."
)

FAKE_FOLLOWUPS = [
    "What is multi-head attention?",
    "How does a Transformer differ from an RNN?",
    "Which models are based on the Transformer?",
]

INSUFFICIENT_ANSWER = "I could not find enough evidence in the corpus to answer this question."

ERROR_CODES: tuple[ErrorCode, ...] = ("llm_unavailable", "retrieval_failed", "timeout", "internal")


class FakeAgent:
    def run(self, session_id: str, message: str) -> Iterator[AgentEvent]:
        lowered = message.lower()
        if "insufficient" in lowered:
            yield SourcesEvent([])
            yield from _tokens(INSUFFICIENT_ANSWER)
            yield DoneEvent(Done(insufficient_evidence=True, message_id=_message_id()))
            return

        yield SourcesEvent(list(FAKE_SOURCES))
        for code in ERROR_CODES:
            if f"fail:{code}" in lowered:
                raise AgentError(code, f"Simulated failure ({code}) from the fake agent.")
        yield from _tokens(FAKE_ANSWER)
        yield FollowupsEvent(list(FAKE_FOLLOWUPS))
        yield DoneEvent(Done(message_id=_message_id()))


def _tokens(text: str) -> Iterator[TokenEvent]:
    """Split into word-sized fragments, keeping spaces and newlines, like a streaming LLM."""
    fragment = ""
    for char in text:
        fragment += char
        if char in " \n":
            yield TokenEvent(fragment)
            fragment = ""
    if fragment:
        yield TokenEvent(fragment)


def _message_id() -> str:
    return f"msg-{uuid.uuid4().hex[:12]}"
