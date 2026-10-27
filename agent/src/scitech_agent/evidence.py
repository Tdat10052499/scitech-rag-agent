"""Evidence check and request limits (W5-D3-DAT-1).

Evidence is sufficient when at least one hit reaches `RETRIEVAL_MIN_SCORE` (on the scale of the
retriever in use: cosine, BM25 or RRF, ADR 0009) and, with `AGENT_SELF_CHECK=on`, when one
non-streamed LLM call (`prompts/self_check.md`) does not answer NO to "can the question be
answered from these sources?". The self-check fails open: an LLM error or an output that is not
YES, PARTLY or NO lets the answer step decide, so a flaky check never hides a good answer.

After the answer, `is_refusal` tells a refusal ("the sources do not contain enough evidence")
from an answer that only forgot its `[n]` markers (#114): only an uncited answer that says the
evidence is insufficient sets `done.insufficient_evidence`.

`RequestBudget` enforces the hard limits of one request: at most `AGENT_MAX_LLM_CALLS` LLM calls
and `AGENT_TIMEOUT_S` seconds. The optional calls (rewrite, self-check) keep one call for the
answer; the follow-ups use what is left. Time is checked between steps and between streamed
fragments: a single blocked call is bounded by `LLM_TIMEOUT`, not interrupted.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Sequence

from scitech_agent.answer import _escape, format_sources, strip_citations
from scitech_agent.llm import Message
from scitech_agent.retrieval import ScoredChunk

VERDICTS = ("yes", "partly", "no")

# Shown when the agent refuses; the corpus is arXiv cs.CL titles and abstracts (ADR 0003).
REFUSAL_HINT = (
    "You could try naming the method, model or dataset you mean, using the technical term, or "
    "asking about one part of the question at a time. The corpus covers arXiv papers on "
    "computation and language (titles and abstracts)."
)
INSUFFICIENT_ANSWER = (
    "I could not find enough evidence in the corpus to answer this question. " + REFUSAL_HINT
)

_VERDICT = re.compile(r"\b(yes|partly|partially|no)\b", re.IGNORECASE)
_SOURCES = r"(?:sources?|evidence|context|documents?|information|abstracts?|papers?)"
_REFUSAL = re.compile(
    "|".join(
        [
            r"\b(?:insufficient|not\s+enough|no\s+(?:sufficient|enough))\s+(?:\w+\s+){0,2}"
            r"(?:evidence|information)",
            rf"\b{_SOURCES}\s+(?:\w+\s+){{0,3}}(?:is|are)\s+(?:insufficient|not\s+(?:enough|"
            r"sufficient))",
            rf"\b{_SOURCES}\s+(?:\w+\s+){{0,3}}(?:do|does|did)(?:\s+not|n't)\s+(?:\w+\s+)?"
            r"(?:contain|provide|mention|cover|answer|say|include|discuss|specify|address|give)",
            rf"\bno(?:ne\s+of\s+the)?\s+{_SOURCES}\s+(?:\w+\s+)?(?:covers?|mentions?|contains?|"
            r"provides?|answers?|discuss(?:es)?|says?|specif(?:y|ies))",
            r"\b(?:cannot|can't|can\s+not|unable\s+to)\s+(?:be\s+)?answer",
            rf"\bnot\s+(?:specified|mentioned|stated|covered)\s+in\s+the\s+(?:\w+\s+)?{_SOURCES}",
        ]
    ),
    re.IGNORECASE,
)


def self_check_messages(
    system_prompt: str, question: str, evidence: Sequence[ScoredChunk]
) -> list[Message]:
    user = (
        f"Sources:\n\n{format_sources(evidence)}\n\n"
        f"Question:\n<question>\n{_escape(question, 'question')}\n</question>"
    )
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": user}]


def parse_verdict(text: str) -> str | None:
    """`yes`, `partly` or `no` from the first such word of the output, else `None`."""
    match = _VERDICT.search(text)
    if match is None:
        return None
    word = match.group(1).lower()
    return "partly" if word == "partially" else word


def is_refusal(answer: str) -> bool:
    """True when the answer says the evidence is insufficient (citation markers ignored)."""
    return bool(_REFUSAL.search(" ".join(strip_citations(answer).split())))


class LimitExceeded(Exception):
    """The request ran out of time before a step that cannot be skipped."""


class RequestBudget:
    """LLM calls and time left for one request."""

    def __init__(
        self,
        max_llm_calls: int,
        timeout_s: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_llm_calls = max_llm_calls
        self.calls = 0
        self.clock = clock
        self.deadline = clock() + timeout_s

    @property
    def calls_left(self) -> int:
        return self.max_llm_calls - self.calls

    def expired(self) -> bool:
        return self.clock() >= self.deadline

    def take_optional(self, reserve: int = 1) -> bool:
        """Count one optional call if `reserve` calls stay for later steps and time is left."""
        if self.calls_left - 1 < reserve or self.expired():
            return False
        self.calls += 1
        return True

    def take_required(self) -> None:
        """Count the answer call; raises `LimitExceeded` when no time is left."""
        if self.expired():
            raise LimitExceeded("time limit reached before the answer")
        self.calls += 1
