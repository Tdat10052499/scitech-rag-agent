"""Per-request traces (W5-D4-DAT-1).

`Agent.run` fills one `RequestTrace` per request and hands it to the agent's `TraceWriter`, which
appends it as one JSON line to `data/logs/traces.jsonl` (git-ignored; `AGENT_TRACES` sets the
path or turns traces off). The fields are listed in `docs/runbooks/traces.md`; `TRACE_VERSION`
changes when one is renamed or removed. A trace is written for every request, also when it
fails or the client goes away, and a write error is only logged: tracing never fails a question.

Latencies come from the agent's clock (`time.monotonic` unless a test injects one) and are in
milliseconds; `timestamp` is the wall-clock start in UTC. The answer step is timed from the call
to the end of the stream, so it includes the time the consumer (the SSE response) takes.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from scitech_agent.events import AgentEvent, DoneEvent, FollowupsEvent, SourcesEvent, TokenEvent
from scitech_agent.retrieval import ScoredChunk

logger = logging.getLogger(__name__)

TRACE_VERSION = 1
DEFAULT_TRACE_FILE = Path("logs") / "traces.jsonl"  # under DATA_DIR
_OFF = {"off", "false", "0", "none"}


class TraceWriter(Protocol):
    def write(self, trace: Mapping[str, Any]) -> None: ...


class JsonlTraceWriter:
    """Appends each trace as one UTF-8 JSON line; safe to share between request threads."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def write(self, trace: Mapping[str, Any]) -> None:
        line = json.dumps(trace, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line)


class ListTraceWriter:
    """Keeps traces in memory (tests)."""

    def __init__(self) -> None:
        self.traces: list[dict[str, Any]] = []

    def write(self, trace: Mapping[str, Any]) -> None:
        self.traces.append(dict(trace))


def trace_writer_from_env(env: Mapping[str, str] | None = None) -> JsonlTraceWriter | None:
    """`AGENT_TRACES`: a file path, `off` for no traces, empty for
    `<DATA_DIR>/logs/traces.jsonl` (`DATA_DIR` empty: `data`)."""
    env = os.environ if env is None else env
    value = (env.get("AGENT_TRACES") or "").strip()
    if value.lower() in _OFF:
        return None
    if value:
        return JsonlTraceWriter(value)
    return JsonlTraceWriter(Path(env.get("DATA_DIR") or "data") / DEFAULT_TRACE_FILE)


def _ms(seconds: float) -> float:
    return round(seconds * 1000.0, 1)


def _hit(chunk: ScoredChunk) -> dict[str, Any]:
    return {"chunk_id": chunk.chunk_id, "doc_id": chunk.doc_id, "score": chunk.score}


class RequestTrace:
    """What one request did. The agent sets the step results; `observe` reads the events it
    yields (sources, shown answer, follow-ups, refusal flag, time to first token)."""

    def __init__(
        self,
        trace_id: str,
        session_id: str,
        message: str,
        *,
        clock: Callable[[], float],
        model: Mapping[str, Any] | None = None,
        config: Mapping[str, Any] | None = None,
    ) -> None:
        self.trace_id = trace_id
        self.session_id = session_id
        self.message = message
        self.clock = clock
        self.timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        self.model = dict(model or {})
        self.config = dict(config or {})
        self.started = clock()
        self.query = message
        self.retrieved: list[dict[str, Any]] = []
        self.evidence_count: int | None = None
        self.self_check = "off"
        self.decision: str | None = None
        self.sources: list[str] = []
        self.answer_raw: str | None = None
        self.answer_parts: list[str] = []
        self.citations: list[str] = []
        self.followups: list[str] = []
        self.insufficient_evidence: bool | None = None
        self.llm_calls = 0
        self.latency: dict[str, float] = {}
        self.status = "ok"
        self.error: str | None = None
        self.total: float | None = None

    @contextmanager
    def step(self, name: str, record: bool = True) -> Iterator[None]:
        """Time a step, also when it raises; `record=False` (a step switched off) leaves it out."""
        start = self.clock()
        try:
            yield
        finally:
            if record:
                self.latency[name] = _ms(self.clock() - start)

    def set_retrieved(self, hits: Sequence[ScoredChunk]) -> None:
        self.retrieved = [_hit(h) for h in hits]

    def observe(self, event: AgentEvent) -> None:
        match event:
            case SourcesEvent(chunks=chunks):
                self.sources = [c.chunk_id for c in chunks]
            case TokenEvent(text=text):
                if not self.answer_parts:
                    self.latency["first_token"] = _ms(self.clock() - self.started)
                self.answer_parts.append(text)
            case FollowupsEvent(questions=questions):
                self.followups = list(questions)
            case DoneEvent(insufficient_evidence=flag):
                self.insufficient_evidence = flag

    def fail(self, status: str, code: str | None) -> None:
        self.status = status
        self.error = code

    def finish(self) -> None:
        if self.total is None:
            self.total = _ms(self.clock() - self.started)
            self.latency["total"] = self.total

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_version": TRACE_VERSION,
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "status": self.status,
            "error": self.error,
            "message": self.message,
            "query": self.query,
            "rewritten": self.query != self.message,
            "retrieved": self.retrieved,
            "evidence": {
                "min_score": self.config.get("min_score"),
                "above_min_score": self.evidence_count,
                "self_check": self.self_check,
                "decision": self.decision,
            },
            "sources": self.sources,
            "answer_raw": self.answer_raw,
            "answer": "".join(self.answer_parts),
            "citations": self.citations,
            "insufficient_evidence": self.insufficient_evidence,
            "followups": self.followups,
            "llm_calls": self.llm_calls,
            "latency_ms": dict(self.latency),
            "model": self.model,
            "config": self.config,
        }
