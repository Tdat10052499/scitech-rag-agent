"""Agent pipeline (W2-D3-DAT-1): rewrite -> retrieve -> evidence check -> answer -> follow-ups.

`Agent.run(session_id, message)` yields the events of `scitech_agent.events` in API order. Each
step is a small method so later tasks can replace it: query rewriting with the history (W4),
hybrid retrieval and reranking (W4), the evidence check. The answer and the follow-ups are two LLM
calls per question; if no chunk reaches `RETRIEVAL_MIN_SCORE` the agent answers that the evidence
is insufficient without calling the LLM (agent/AGENTS.md).
"""

from __future__ import annotations

import logging
import os
import re
import threading
import uuid
from collections import OrderedDict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from scitech_agent.events import (
    AgentError,
    AgentEvent,
    DoneEvent,
    FollowupsEvent,
    SourcesEvent,
    TokenEvent,
)
from scitech_agent.llm import LLMClient, LLMError, Message, split_fragments
from scitech_agent.retrieval import Retriever, ScoredChunk

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
INSUFFICIENT_ANSWER = (
    "I could not find enough evidence in the corpus to answer this question. "
    "Try rephrasing it or asking about a related topic."
)
# Shown to the user; the cause goes to the log only.
ERROR_MESSAGES = {
    "llm_unavailable": "The language model is not reachable right now. Please try again later.",
    "timeout": "The language model took too long to answer. Please try again.",
    "retrieval_failed": "The search index is not reachable right now. Please try again later.",
    "internal": "Internal error while answering. Please try again.",
}
MAX_SESSIONS = 1000


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


@dataclass(frozen=True)
class AgentConfig:
    top_k: int = 5
    min_score: float = 0.0
    max_followups: int = 3
    history_turns: int = 10  # turns kept per session for query rewriting
    temperature: float = 0.0
    answer_max_tokens: int = 512
    followups_max_tokens: int = 128

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> AgentConfig:
        """Read `RETRIEVAL_TOP_K` and `RETRIEVAL_MIN_SCORE` (empty: 5 and 0.0)."""
        env = os.environ if env is None else env
        try:
            top_k = int(env.get("RETRIEVAL_TOP_K") or 5)
            min_score = float(env.get("RETRIEVAL_MIN_SCORE") or 0.0)
        except ValueError as exc:
            raise ValueError(
                f"RETRIEVAL_TOP_K / RETRIEVAL_MIN_SCORE must be numbers: {exc}"
            ) from None
        if top_k <= 0:
            raise ValueError("RETRIEVAL_TOP_K must be > 0")
        return cls(top_k=top_k, min_score=min_score)


@dataclass(frozen=True)
class Turn:
    question: str
    answer: str


class Agent:
    def __init__(
        self, retriever: Retriever, llm: LLMClient, config: AgentConfig | None = None
    ) -> None:
        self.retriever = retriever
        self.llm = llm
        self.config = config or AgentConfig()
        self.answer_prompt = load_prompt("answer")
        self.followups_prompt = load_prompt("followups")
        self._history: OrderedDict[str, list[Turn]] = OrderedDict()
        self._lock = threading.Lock()  # the backend streams requests from worker threads

    # --- Pipeline -------------------------------------------------------------------------------

    def run(self, session_id: str, message: str) -> Iterator[AgentEvent]:
        """Answer `message` in the conversation `session_id`. Raises `AgentError` on failure."""
        query = self.rewrite(message, self.history(session_id))
        evidence = self.check_evidence(self.retrieve(query))
        message_id = f"msg-{uuid.uuid4().hex[:12]}"

        if not evidence:
            yield SourcesEvent([])
            for fragment in split_fragments(INSUFFICIENT_ANSWER):
                yield TokenEvent(fragment)
            self._remember(session_id, Turn(message, INSUFFICIENT_ANSWER))
            yield DoneEvent(insufficient_evidence=True, message_id=message_id)
            return

        yield SourcesEvent(evidence)
        parts: list[str] = []
        for fragment in self.answer(message, evidence):
            parts.append(fragment)
            yield TokenEvent(fragment)
        answer = "".join(parts)
        questions = self.followups(message, answer, evidence)
        if questions:
            yield FollowupsEvent(questions)
        self._remember(session_id, Turn(message, answer))
        yield DoneEvent(message_id=message_id)

    def rewrite(self, message: str, history: list[Turn]) -> str:
        """Standalone search query for `message`. Identity for now; uses `history` later."""
        return message

    def retrieve(self, query: str) -> list[ScoredChunk]:
        try:
            return self.retriever.search(query, k=self.config.top_k)
        except Exception as exc:
            logger.exception("retrieval failed")
            raise AgentError("retrieval_failed", ERROR_MESSAGES["retrieval_failed"]) from exc

    def check_evidence(self, hits: list[ScoredChunk]) -> list[ScoredChunk]:
        """Chunks with `score >= min_score`, best first; empty means insufficient evidence."""
        return sorted((h for h in hits if h.score >= self.config.min_score), key=lambda h: -h.score)

    def answer(self, question: str, evidence: list[ScoredChunk]) -> Iterator[str]:
        messages = [
            {"role": "system", "content": self.answer_prompt},
            {"role": "user", "content": answer_user_message(question, evidence)},
        ]
        try:
            yield from self.llm.stream_chat(
                messages,
                temperature=self.config.temperature,
                max_tokens=self.config.answer_max_tokens,
            )
        except LLMError as exc:
            logger.warning("answer failed: %s (%s)", exc, exc.code)
            raise AgentError(exc.code, ERROR_MESSAGES[exc.code]) from exc

    def followups(self, question: str, answer: str, evidence: list[ScoredChunk]) -> list[str]:
        """Suggested next questions. A failure here only drops them: the answer is already out."""
        messages: list[Message] = [
            {"role": "system", "content": self.followups_prompt},
            {"role": "user", "content": followups_user_message(question, answer, evidence)},
        ]
        try:
            text = self.llm.chat(
                messages,
                temperature=self.config.temperature,
                max_tokens=self.config.followups_max_tokens,
            )
        except LLMError as exc:
            logger.warning("follow-ups skipped: %s (%s)", exc, exc.code)
            return []
        return parse_followups(text, self.config.max_followups, exclude=question)

    # --- Sessions -------------------------------------------------------------------------------

    def history(self, session_id: str) -> list[Turn]:
        with self._lock:
            return list(self._history.get(session_id, []))

    def _remember(self, session_id: str, turn: Turn) -> None:
        with self._lock:
            turns = self._history.pop(session_id, [])
            turns.append(turn)
            self._history[session_id] = turns[-self.config.history_turns :]
            while len(self._history) > MAX_SESSIONS:  # in-memory only: drop the oldest sessions
                self._history.popitem(last=False)


# --- Prompt building --------------------------------------------------------------------------


def _inside_source(text: str) -> str:
    """Chunk text cannot close or open a `<source>` block itself."""
    return re.sub(r"<(/?source)", r"&lt;\1", text, flags=re.IGNORECASE)


def format_sources(evidence: list[ScoredChunk]) -> str:
    """Numbered sources; the numbers are the citation markers `[n]` of the answer."""
    blocks = [
        f'<source id="{n}">\nTitle: {_inside_source(chunk.title)}\n'
        f"Text: {_inside_source(chunk.text)}\n</source>"
        for n, chunk in enumerate(evidence, start=1)
    ]
    return "\n\n".join(blocks)


def answer_user_message(question: str, evidence: list[ScoredChunk]) -> str:
    return f"Sources:\n\n{format_sources(evidence)}\n\nQuestion: {question}"


def followups_user_message(question: str, answer: str, evidence: list[ScoredChunk]) -> str:
    titles = "\n".join(f"- {chunk.title}" for chunk in evidence)
    return f"Question: {question}\n\nAnswer: {answer}\n\nSource titles:\n{titles}"


_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")


def parse_followups(text: str, limit: int, exclude: str = "") -> list[str]:
    """One question per line: strip bullets and numbering, drop blanks, duplicates and a repeat
    of the user's question, keep at most `limit`."""
    seen = {exclude.strip().lower()} if exclude else set()
    questions = []
    for line in text.splitlines():
        question = _BULLET.sub("", line).strip().strip('"').strip()
        if question and question.lower() not in seen:
            seen.add(question.lower())
            questions.append(question)
    return questions[:limit]
