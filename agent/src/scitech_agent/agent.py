"""Agent pipeline (W2-D3-DAT-1): rewrite -> retrieve -> evidence check -> answer -> follow-ups.

`Agent.run(session_id, message)` yields the events of `scitech_agent.events` in API order. Each
step is a small method so later tasks can replace it. With `AGENT_REWRITE=on` a message that
follows earlier turns is rewritten into a standalone search query first (`scitech_agent.rewrite`,
W5-D1-DAT-1). The answer and the follow-ups are two LLM calls per question; if no chunk reaches
`RETRIEVAL_MIN_SCORE`, or the optional self-check (`AGENT_SELF_CHECK=on`) answers NO, the agent
refuses with a fixed message and suggestions, without an answer call (agent/AGENTS.md,
`scitech_agent.evidence`, W5-D3-DAT-1). Each request has at most `AGENT_MAX_LLM_CALLS` LLM calls
and `AGENT_TIMEOUT_S` seconds. The answer prompt and its citation checks live in
`scitech_agent.answer` (W4-D1-DAT-1).
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from scitech_agent.answer import (
    CitationFilter,
    answer_messages,
    answer_user_message,
    answer_words,
    format_sources,
    parse_citations,
)
from scitech_agent.events import (
    AgentError,
    AgentEvent,
    DoneEvent,
    FollowupsEvent,
    SourcesEvent,
    TokenEvent,
)
from scitech_agent.evidence import (
    INSUFFICIENT_ANSWER,
    REFUSAL_HINT,
    LimitExceeded,
    RequestBudget,
    is_refusal,
    parse_verdict,
    self_check_messages,
)
from scitech_agent.followups import followups_user_message, parse_followups
from scitech_agent.llm import LLMClient, LLMError, Message, split_fragments
from scitech_agent.retrieval import Retriever, ScoredChunk
from scitech_agent.rewrite import rewrite_query

logger = logging.getLogger(__name__)

__all__ = [
    "Agent",
    "AgentConfig",
    "INSUFFICIENT_ANSWER",
    "Turn",
    "answer_user_message",
    "format_sources",
    "load_prompt",
]

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
# Shown to the user; the cause goes to the log only.
ERROR_MESSAGES = {
    "llm_unavailable": "The language model is not reachable right now. Please try again later.",
    "timeout": "The language model took too long to answer. Please try again.",
    "retrieval_failed": "The search index is not reachable right now. Please try again later.",
    "internal": "Internal error while answering. Please try again.",
}
MAX_SESSIONS = 1000
_FLAGS = {"on": True, "true": True, "1": True, "off": False, "false": False, "0": False, "": False}


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


@dataclass(frozen=True)
class AgentConfig:
    top_k: int = 5
    min_score: float = 0.0
    max_followups: int = 4  # contract: followups has at most 4 questions
    history_turns: int = 10  # turns kept per session for query rewriting
    answer_history_turns: int = 3  # latest turns shown to the answer prompt
    temperature: float = 0.0
    answer_max_tokens: int = 512
    followups_max_tokens: int = 192
    rewrite: bool = False  # AGENT_REWRITE: standalone search query for follow-up messages
    rewrite_history_turns: int = 3  # latest turns shown to the rewrite prompt
    rewrite_max_tokens: int = 96
    self_check: bool = False  # AGENT_SELF_CHECK: ask the LLM whether the sources answer it
    self_check_max_tokens: int = 8
    max_llm_calls: int = 4  # AGENT_MAX_LLM_CALLS: rewrite, self-check, answer, follow-ups
    timeout_s: float = 120.0  # AGENT_TIMEOUT_S: whole request, checked between steps

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> AgentConfig:
        """Read `RETRIEVAL_TOP_K`, `RETRIEVAL_MIN_SCORE`, `AGENT_REWRITE`, `AGENT_SELF_CHECK`,
        `AGENT_MAX_LLM_CALLS` and `AGENT_TIMEOUT_S` (empty: 5, 0.0, off, off, 4 and 120)."""
        env = os.environ if env is None else env
        try:
            top_k = int(env.get("RETRIEVAL_TOP_K") or 5)
            min_score = float(env.get("RETRIEVAL_MIN_SCORE") or 0.0)
            max_llm_calls = int(env.get("AGENT_MAX_LLM_CALLS") or 4)
            timeout_s = float(env.get("AGENT_TIMEOUT_S") or 120.0)
        except ValueError as exc:
            raise ValueError(
                "RETRIEVAL_TOP_K / RETRIEVAL_MIN_SCORE / AGENT_MAX_LLM_CALLS / AGENT_TIMEOUT_S "
                f"must be numbers: {exc}"
            ) from None
        if top_k <= 0:
            raise ValueError("RETRIEVAL_TOP_K must be > 0")
        if max_llm_calls < 1:
            raise ValueError("AGENT_MAX_LLM_CALLS must be >= 1 (the answer call)")
        if not timeout_s > 0:
            raise ValueError("AGENT_TIMEOUT_S must be > 0")
        return cls(
            top_k=top_k,
            min_score=min_score,
            rewrite=_flag(env, "AGENT_REWRITE"),
            self_check=_flag(env, "AGENT_SELF_CHECK"),
            max_llm_calls=max_llm_calls,
            timeout_s=timeout_s,
        )


def _flag(env: Mapping[str, str], name: str) -> bool:
    value = (env.get(name) or "").strip().lower()
    if value not in _FLAGS:
        raise ValueError(f"{name} must be on or off, not {value!r}")
    return _FLAGS[value]


@dataclass(frozen=True)
class Turn:
    question: str
    answer: str
    citations: tuple[str, ...] = ()  # chunk_ids cited by the answer, in order of first use


class Agent:
    def __init__(
        self,
        retriever: Retriever,
        llm: LLMClient,
        config: AgentConfig | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.retriever = retriever
        self.llm = llm
        self.config = config or AgentConfig()
        self.clock = clock
        self.answer_prompt = load_prompt("answer")
        self.followups_prompt = load_prompt("followups")
        self.rewrite_prompt = load_prompt("rewrite")
        self.self_check_prompt = load_prompt("self_check")
        self._history: OrderedDict[str, list[Turn]] = OrderedDict()
        self._lock = threading.Lock()  # the backend streams requests from worker threads

    # --- Pipeline -------------------------------------------------------------------------------

    def run(self, session_id: str, message: str) -> Iterator[AgentEvent]:
        """Answer `message` in the conversation `session_id`. Raises `AgentError` on failure."""
        budget = RequestBudget(self.config.max_llm_calls, self.config.timeout_s, self.clock)
        history = self.history(session_id)
        query = self.rewrite(message, history, budget)
        evidence = self.check_evidence(self.retrieve(query))
        if evidence and not self.self_check(query, evidence, budget):
            evidence = []
        message_id = f"msg-{uuid.uuid4().hex[:12]}"

        if not evidence:
            yield SourcesEvent([])
            for fragment in split_fragments(INSUFFICIENT_ANSWER):
                yield TokenEvent(fragment)
            self._remember(session_id, Turn(message, INSUFFICIENT_ANSWER))
            yield DoneEvent(insufficient_evidence=True, message_id=message_id)
            return

        try:
            budget.take_required()
        except LimitExceeded as exc:  # before `sources`: the stream is a single `error`
            logger.warning("request stopped: %s", exc)
            raise AgentError("timeout", ERROR_MESSAGES["timeout"]) from exc
        yield SourcesEvent(evidence)
        parts: list[str] = []
        for fragment in self.answer(message, evidence, history, budget):
            parts.append(fragment)
            yield TokenEvent(fragment)
        answer = "".join(parts)
        cited = tuple(c.chunk_id for c in parse_citations(answer, evidence))
        if not answer_words(answer):
            logger.warning("answer has no words outside citation markers")
        # Only an uncited answer that says the evidence is insufficient is a refusal (contract:
        # "answered that the evidence is insufficient"); a cited partial answer is not, and an
        # uncited answer that does answer only forgot its markers (#114). RRF scores are
        # rank-based, so a score threshold cannot decide this for hybrid.
        refused = not cited and is_refusal(answer)
        if refused:
            hint = "\n\n" + REFUSAL_HINT
            for fragment in split_fragments(hint):
                yield TokenEvent(fragment)
        elif not cited:
            logger.info("answer cites no source and is not a refusal")
        # Follow-ups grounded in sources that did not answer would point to more of the same.
        questions = [] if refused else self.followups(message, answer, evidence, history, budget)
        if questions:
            yield FollowupsEvent(questions)
        self._remember(session_id, Turn(message, answer, cited))
        yield DoneEvent(insufficient_evidence=refused, message_id=message_id)

    def warm_up(self) -> None:
        """One search, so the embedding model and the index are loaded before the first
        question (ADR 0009). A failure is only logged: a request reports it to the user."""
        try:
            self.retriever.search("warm-up", k=1)
        except Exception as exc:  # noqa: BLE001 - the request path handles retrieval errors
            logger.warning("warm-up search failed: %s", exc)

    def rewrite(
        self, message: str, history: list[Turn], budget: RequestBudget | None = None
    ) -> str:
        """Standalone search query for `message` from the latest turns (`scitech_agent.rewrite`).
        `message` itself when rewriting is off, the session has no earlier turn, the request
        has no call or time to spare, or the call fails or returns nothing usable: a bad rewrite
        must not fail the question."""
        keep = self.config.rewrite_history_turns
        recent = history[-keep:] if keep > 0 else []
        if not self.config.rewrite or not recent or not message.strip():
            return message
        if budget is not None and not budget.take_optional():
            logger.info("rewrite skipped: request limits")
            return message
        try:
            query = rewrite_query(
                self.llm,
                self.rewrite_prompt,
                message,
                recent,
                temperature=self.config.temperature,
                max_tokens=self.config.rewrite_max_tokens,
            )
        except LLMError as exc:
            logger.warning("rewrite skipped: %s (%s)", exc, exc.code)
            return message
        if query is None:
            logger.info("rewrite output unusable, original message kept")
            return message
        logger.info("rewrote %r as %r", message, query)
        return query

    def retrieve(self, query: str) -> list[ScoredChunk]:
        try:
            return self.retriever.search(query, k=self.config.top_k)
        except Exception as exc:
            logger.exception("retrieval failed")
            raise AgentError("retrieval_failed", ERROR_MESSAGES["retrieval_failed"]) from exc

    def check_evidence(self, hits: list[ScoredChunk]) -> list[ScoredChunk]:
        """Chunks with `score >= min_score`, best first; empty means insufficient evidence.
        `min_score` is on the scale of the retriever in use (ADR 0009)."""
        return sorted((h for h in hits if h.score >= self.config.min_score), key=lambda h: -h.score)

    def self_check(
        self, query: str, evidence: list[ScoredChunk], budget: RequestBudget | None = None
    ) -> bool:
        """False only when `AGENT_SELF_CHECK` is on and the LLM answers NO to "can `query` be
        answered from `evidence`?". Fails open: off, no call or time to spare, an LLM error or
        an unreadable verdict all leave the decision to the answer step."""
        if not self.config.self_check:
            return True
        if budget is not None and not budget.take_optional():
            logger.info("self-check skipped: request limits")
            return True
        try:
            text = self.llm.chat(
                self_check_messages(self.self_check_prompt, query, evidence),
                temperature=0.0,
                max_tokens=self.config.self_check_max_tokens,
            )
        except LLMError as exc:
            logger.warning("self-check skipped: %s (%s)", exc, exc.code)
            return True
        verdict = parse_verdict(text)
        if verdict is None:
            logger.info("self-check verdict unreadable: %r", text[:80])
            return True
        logger.info("self-check: %s (%r)", verdict, text[:80])
        return verdict != "no"

    def answer(
        self,
        question: str,
        evidence: list[ScoredChunk],
        history: list[Turn] | None = None,
        budget: RequestBudget | None = None,
    ) -> Iterator[str]:
        """Streamed answer; markers that cite no source are dropped from it (`CitationFilter`).
        Raises `AgentError("timeout")` when the request's time runs out while it streams."""
        keep = self.config.answer_history_turns
        recent = (history or [])[-keep:] if keep > 0 else []
        messages = answer_messages(self.answer_prompt, question, evidence, recent)
        stream = None
        try:
            stream = self.llm.stream_chat(
                messages,
                temperature=self.config.temperature,
                max_tokens=self.config.answer_max_tokens,
            )
            for fragment in CitationFilter(len(evidence)).filter(stream):
                yield fragment
                if budget is not None and budget.expired():
                    raise LimitExceeded("time limit reached while the answer streamed")
        except LLMError as exc:
            logger.warning("answer failed: %s (%s)", exc, exc.code)
            raise AgentError(exc.code, ERROR_MESSAGES[exc.code]) from exc
        except LimitExceeded as exc:
            logger.warning("request stopped: %s", exc)
            raise AgentError("timeout", ERROR_MESSAGES["timeout"]) from exc
        finally:
            close = getattr(stream, "close", None)
            if close is not None:
                close()

    def followups(
        self,
        question: str,
        answer: str,
        evidence: list[ScoredChunk],
        history: list[Turn] | None = None,
        budget: RequestBudget | None = None,
    ) -> list[str]:
        """Suggested next questions (`scitech_agent.followups`), never one already asked in the
        session. A failure, or no call or time left, only drops them: the answer is out."""
        history = history or []
        if budget is not None and not budget.take_optional(reserve=0):
            logger.info("follow-ups skipped: request limits")
            return []
        keep = self.config.answer_history_turns
        recent = history[-keep:] if keep > 0 else []
        limit = self.config.max_followups
        user = followups_user_message(question, answer, evidence, recent, limit)
        messages: list[Message] = [
            {"role": "system", "content": self.followups_prompt},
            {"role": "user", "content": user},
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
        asked = [turn.question for turn in history] + [question]
        return parse_followups(text, limit, asked)

    # --- Sessions -------------------------------------------------------------------------------

    def history(self, session_id: str) -> list[Turn]:
        with self._lock:
            return list(self._history.get(session_id, []))

    def _remember(self, session_id: str, turn: Turn) -> None:
        with self._lock:
            turns = self._history.pop(session_id, [])
            turns.append(turn)
            keep = self.config.history_turns
            self._history[session_id] = turns[-keep:] if keep > 0 else []
            while len(self._history) > MAX_SESSIONS:  # in-memory only: drop the oldest sessions
                self._history.popitem(last=False)
