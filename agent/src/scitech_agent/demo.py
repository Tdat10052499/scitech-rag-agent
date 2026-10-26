"""Offline demo agent: the real `Agent` with a fixed retriever and a scripted LLM.

The backend uses it until the index (W3) and the LLM server are wired in, so `/chat`, the UI and
the tests run with no index, no LLM and no network. It keeps the behaviour of the earlier backend
stub (W2-D2-DAT-1):
- the answer cites its two sources with `[1]` and `[2]`;
- a message containing "insufficient" gets no hits (insufficient-evidence branch);
- "fail:<code>" fails the matching step: `fail:retrieval_failed` in retrieval, before `sources`;
  `fail:llm_unavailable`, `fail:timeout` and `fail:internal` in the answer, after `sources`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import Any

from scitech_agent.agent import Agent, AgentConfig
from scitech_agent.llm import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    LLMError,
    LLMTimeoutError,
    LLMUnavailableError,
    Message,
    split_fragments,
)
from scitech_agent.retrieval import Filters, RetrievalError, ScoredChunk, matches

DEMO_CHUNKS = [
    ScoredChunk(
        chunk_id="1706.03762#0",
        doc_id="1706.03762",
        score=0.82,
        title="Attention Is All You Need",
        text="Attention Is All You Need. The dominant sequence transduction models are based on "
        "complex recurrent or convolutional neural networks ...",
        source="arxiv",
        chunk_index=0,
        url="https://arxiv.org/abs/1706.03762",
        published_at="2017-06-12",
        categories=("cs.CL", "cs.LG"),
        license="CC0-1.0",
    ),
    ScoredChunk(
        chunk_id="1810.04805#0",
        doc_id="1810.04805",
        score=0.74,
        title="BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
        text="BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding. "
        "We introduce a new language representation model called BERT ...",
        source="arxiv",
        chunk_index=0,
        url="https://arxiv.org/abs/1810.04805",
        license="CC0-1.0",
    ),
]

DEMO_ANSWER = (
    "This is a demo answer from the offline agent. "
    "The Transformer relies only on attention, without recurrence [1].\n"
    "BERT pre-trains a bidirectional Transformer encoder on unlabelled text [2]."
)

DEMO_FOLLOWUPS = [
    "What is multi-head attention?",
    "How does a Transformer differ from an RNN?",
    "Which models are based on the Transformer?",
]

LLM_FAILURES: dict[str, type[LLMError]] = {
    "llm_unavailable": LLMUnavailableError,
    "timeout": LLMTimeoutError,
    "internal": LLMError,
}


class DemoRetriever:
    """Returns `DEMO_CHUNKS` for any query, except the "insufficient" and "fail:" triggers."""

    def search(self, query: str, k: int, filters: Filters | None = None) -> list[ScoredChunk]:
        lowered = query.lower()
        if "fail:retrieval_failed" in lowered:
            raise RetrievalError("Simulated failure (retrieval_failed) from the demo retriever.")
        if "insufficient" in lowered:
            return []
        return [c for c in DEMO_CHUNKS if matches(c, filters)][:k]


class DemoLLM:
    """Scripted LLM: `stream_chat` streams `DEMO_ANSWER`, `chat` returns `DEMO_FOLLOWUPS` (JSON)."""

    model = "demo-llm"

    def chat(
        self,
        messages: Sequence[Message],
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        return json.dumps(DEMO_FOLLOWUPS)

    def stream_chat(
        self,
        messages: Sequence[Message],
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> Iterator[str]:
        question = messages[-1]["content"].lower()
        for code, error in LLM_FAILURES.items():
            if f"fail:{code}" in question:
                raise error(f"Simulated failure ({code}) from the demo LLM.")
        return iter(split_fragments(DEMO_ANSWER))

    def describe(self) -> dict[str, Any]:
        return {"model": self.model}


def demo_agent(config: AgentConfig | None = None) -> Agent:
    # Not from the environment: RETRIEVAL_* are for a real index and mean nothing for the fixed
    # demo scores, so exported settings cannot change `/chat` in the demo or in the tests.
    return Agent(DemoRetriever(), DemoLLM(), config or AgentConfig())
