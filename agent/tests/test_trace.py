"""Tests of the per-request traces and `Agent.run_batch` (W5-D4-DAT-1), with `InMemoryRetriever`
and `FakeLLM` only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scitech_agent.agent import Agent, AgentConfig, BatchItem, Turn
from scitech_agent.events import AgentError, TokenEvent
from scitech_agent.llm import FakeLLM, LLMUnavailableError, split_fragments
from scitech_agent.retrieval import InMemoryRetriever, RetrievalError, ScoredChunk
from scitech_agent.trace import (
    TRACE_VERSION,
    JsonlTraceWriter,
    ListTraceWriter,
    trace_writer_from_env,
)

CHUNKS = [
    ScoredChunk(
        "2409.02060#0",
        "2409.02060",
        0.0,
        "OLMoE",
        "OLMoE. A mixture-of-experts language model with 1B active and 7B total parameters.",
        source="arxiv",
        chunk_index=0,
    ),
    ScoredChunk(
        "1810.04805#0",
        "1810.04805",
        0.0,
        "BERT",
        "BERT. Pre-training of deep bidirectional Transformer encoders for language models.",
        source="arxiv",
        chunk_index=0,
    ),
]
QUESTION = "How many parameters does the OLMoE language model use?"
RAW = "OLMoE uses 1B active parameters out of 7B [1, 2] [9]."
SHOWN = "OLMoE uses 1B active parameters out of 7B [1][2]."
FOLLOWUPS = '["How was OLMoE pretrained?"]'
REFUSAL = "The sources do not contain enough evidence to answer this question."

FIELDS = {
    "trace_version",
    "trace_id",
    "timestamp",
    "session_id",
    "status",
    "error",
    "message",
    "query",
    "rewritten",
    "retrieved",
    "evidence",
    "sources",
    "answer_raw",
    "answer",
    "citations",
    "number_check",
    "insufficient_evidence",
    "followups",
    "llm_calls",
    "latency_ms",
    "model",
    "config",
}


class Clock:
    """Advances one second per reading, so every step has a known, non-zero latency."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 1.0
        return self.now


def make_agent(outputs, retriever=None, **config):
    tracer = ListTraceWriter()
    llm = FakeLLM(outputs, model="fake-model")
    agent = Agent(
        retriever or InMemoryRetriever(CHUNKS),
        llm,
        AgentConfig(**config),
        clock=Clock(),
        tracer=tracer,
    )
    return agent, llm, tracer


def test_answered_request_writes_one_complete_trace() -> None:
    agent, _, tracer = make_agent([RAW, FOLLOWUPS])
    events = list(agent.run("s1", QUESTION))

    assert len(tracer.traces) == 1
    trace = tracer.traces[0]
    assert set(trace) == FIELDS
    assert trace["trace_version"] == TRACE_VERSION
    assert trace["trace_id"] == events[-1].message_id  # links /feedback and UI to the trace
    assert trace["timestamp"].endswith("+00:00")
    assert (trace["session_id"], trace["status"], trace["error"]) == ("s1", "ok", None)
    assert trace["message"] == trace["query"] == QUESTION and trace["rewritten"] is False
    assert [h["chunk_id"] for h in trace["retrieved"]] == ["2409.02060#0", "1810.04805#0"]
    assert all(set(h) == {"chunk_id", "doc_id", "score"} for h in trace["retrieved"])
    assert trace["evidence"] == {
        "min_score": 0.0,
        "above_min_score": 2,
        "self_check": "off",
        "decision": "answer",
    }
    assert trace["sources"] == ["2409.02060#0", "1810.04805#0"]
    assert trace["answer_raw"] == RAW  # before the citation filter dropped [9]
    assert trace["answer"] == SHOWN == "".join(e.text for e in events if isinstance(e, TokenEvent))
    assert trace["citations"] == ["2409.02060#0", "1810.04805#0"]
    assert trace["number_check"] == []  # "1B" and "7B" are not checked numbers
    assert trace["insufficient_evidence"] is False
    assert trace["followups"] == ["How was OLMoE pretrained?"]
    assert trace["llm_calls"] == 2
    latency = trace["latency_ms"]
    assert set(latency) == {"retrieve", "answer", "first_token", "followups", "total"}
    assert all(v > 0 for v in latency.values()) and latency["total"] >= latency["answer"]
    assert trace["model"] == {"model": "fake-model"}
    assert trace["config"]["retriever"] == "InMemoryRetriever"
    assert trace["config"]["top_k"] == 5 and trace["config"]["self_check"] is False
    json.dumps(trace)  # JSON-ready


def test_rewritten_query_and_self_check_are_traced() -> None:
    agent, _, tracer = make_agent(
        ["OLMoE parameter count", "PARTLY", RAW, FOLLOWUPS], rewrite=True, self_check=True
    )
    agent._remember("s1", Turn("What is OLMoE?", "A mixture-of-experts model [1]."))
    list(agent.run("s1", "How many parameters does it use?"))
    trace = tracer.traces[0]
    assert trace["query"] == "OLMoE parameter count" and trace["rewritten"] is True
    assert trace["evidence"]["self_check"] == "partly"
    assert trace["llm_calls"] == 4 and "self_check" in trace["latency_ms"]


def test_self_check_refusal_is_traced() -> None:
    agent, _, tracer = make_agent(["NO"], self_check=True)
    list(agent.run("s1", QUESTION))
    trace = tracer.traces[0]
    assert trace["evidence"]["self_check"] == "no"
    assert trace["evidence"]["decision"] == "refuse_self_check"
    assert trace["sources"] == [] and len(trace["retrieved"]) == 2
    assert trace["answer_raw"] is None and trace["insufficient_evidence"] is True
    assert trace["number_check"] is None  # no answer call
    assert trace["llm_calls"] == 1 and "answer" not in trace["latency_ms"]


def test_no_evidence_refusal_is_traced() -> None:
    agent, llm, tracer = make_agent([], min_score=0.99)
    list(agent.run("s1", QUESTION))
    trace = tracer.traces[0]
    assert trace["evidence"]["above_min_score"] == 0
    assert trace["evidence"]["decision"] == "refuse_no_evidence"
    assert trace["llm_calls"] == 0 and llm.calls == []


def test_refusal_after_the_answer_is_traced() -> None:
    agent, _, tracer = make_agent([REFUSAL])
    list(agent.run("s1", QUESTION))
    trace = tracer.traces[0]
    assert trace["evidence"]["decision"] == "answer"  # evidence passed; the answer refused
    assert trace["answer_raw"] == REFUSAL and trace["answer"].startswith(REFUSAL)
    assert trace["insufficient_evidence"] is True and trace["followups"] == []


def test_failed_request_still_writes_a_trace() -> None:
    agent, _, tracer = make_agent([LLMUnavailableError("down")])
    with pytest.raises(AgentError):
        list(agent.run("s1", QUESTION))
    trace = tracer.traces[0]
    assert (trace["status"], trace["error"]) == ("error", "llm_unavailable")
    assert trace["llm_calls"] == 1 and "answer" in trace["latency_ms"]

    class Broken(InMemoryRetriever):
        def search(self, query, k, filters=None):
            raise RetrievalError("index gone")

    agent, _, tracer = make_agent([], retriever=Broken(CHUNKS))
    with pytest.raises(AgentError):
        list(agent.run("s1", QUESTION))
    assert tracer.traces[0]["error"] == "retrieval_failed"
    assert tracer.traces[0]["retrieved"] == [] and "retrieve" in tracer.traces[0]["latency_ms"]


def test_stopped_stream_is_traced_as_cancelled() -> None:
    agent, _, tracer = make_agent([RAW, FOLLOWUPS])
    run = agent.run("s1", QUESTION)
    next(run), next(run)  # sources and one fragment, then the client goes away
    run.close()
    trace = tracer.traces[0]
    assert trace["status"] == "cancelled" and trace["error"] is None
    assert trace["answer"] == split_fragments(SHOWN)[0]


def test_a_failing_tracer_never_fails_the_request() -> None:
    class Failing:
        def write(self, trace):
            raise OSError("disk full")

    agent, _, _ = make_agent([RAW, FOLLOWUPS])
    agent.tracer = Failing()
    assert list(agent.run("s1", QUESTION))


def test_jsonl_writer_appends_utf8_lines(tmp_path: Path) -> None:
    path = tmp_path / "logs" / "traces.jsonl"
    agent, _, _ = make_agent([RAW, FOLLOWUPS, RAW, FOLLOWUPS])
    agent.tracer = JsonlTraceWriter(path)
    list(agent.run("s1", QUESTION))
    list(agent.run("s1", "Mô hình OLMoE có bao nhiêu tham số?"))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["message"] == "Mô hình OLMoE có bao nhiêu tham số?"
    assert "Mô hình" in lines[1]  # not escaped


def test_trace_writer_from_env(tmp_path: Path) -> None:
    assert trace_writer_from_env({"AGENT_TRACES": "off"}) is None
    default = trace_writer_from_env({"DATA_DIR": str(tmp_path)})
    assert default is not None and default.path == tmp_path / "logs" / "traces.jsonl"
    assert trace_writer_from_env({}).path == Path("data/logs/traces.jsonl")
    assert trace_writer_from_env({"AGENT_TRACES": "x/t.jsonl"}).path == Path("x/t.jsonl")


# --- run_batch --------------------------------------------------------------------------------


def test_run_batch_answers_each_question_in_a_new_session() -> None:
    agent, _, tracer = make_agent([RAW, FOLLOWUPS, LLMUnavailableError("down"), RAW, FOLLOWUPS])
    results = agent.run_batch(
        [QUESTION, BatchItem("What is BERT?", id="gs-002"), {"question": "x"}]
    )

    assert [r.id for r in results] == ["q1", "gs-002", "q3"]
    assert [r.error for r in results] == [None, "llm_unavailable", None]
    first = results[0]
    assert first.answer == SHOWN and first.insufficient_evidence is False
    assert [c.chunk_id for c in first.sources] == ["2409.02060#0", "1810.04805#0"]
    assert len({r.trace["session_id"] for r in results}) == 3
    assert [t["trace_id"] for t in tracer.traces] == [r.trace["trace_id"] for r in results]
    assert agent._history == {}  # batch sessions are not kept

    record = first.to_dict()
    assert record["answer_id"] == "q1" and record["answer_raw"] == RAW
    assert record["sources"][0] == {
        "n": 1,
        "chunk_id": "2409.02060#0",
        "doc_id": "2409.02060",
        "title": "OLMoE",
        "text": CHUNKS[0].text,
        "score": first.sources[0].score,
    }
    assert record["citations"] == ["2409.02060#0", "1810.04805#0"]
    assert record["trace"] == first.trace
    json.dumps(record)


def test_run_batch_uses_golden_history() -> None:
    agent, llm, _ = make_agent(["OLMoE parameter count", RAW, FOLLOWUPS], rewrite=True)
    item = {
        "id": "gs-018",
        "question": "How many parameters does it use?",
        "history": [
            {"role": "user", "content": "What is OLMoE?"},
            {"role": "assistant", "content": "A mixture-of-experts model."},
        ],
    }
    (result,) = agent.run_batch([item])
    assert result.id == "gs-018" and result.trace["query"] == "OLMoE parameter count"
    assert "What is OLMoE?" in llm.calls[0].messages[-1]["content"]  # the rewrite saw the turn


def test_batch_item_turns_pair_user_and_assistant() -> None:
    item = BatchItem(
        "q",
        history=[
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "assistant", "content": "orphan"},
            {"role": "user", "content": "c"},
        ],
    )
    assert item.turns() == [Turn("a", "b")]
    with pytest.raises(ValueError):
        BatchItem.of({"id": "x"}, default_id="q1")


def test_number_cited_to_the_wrong_source_is_traced() -> None:
    chunks = [
        ScoredChunk("a#0", "a", 0.0, "LongRAG A", "LongRAG A beats RAG by 6.16%.", "arxiv", 0),
        ScoredChunk("b#0", "b", 0.0, "LongRAG B", "LongRAG B improves recall.", "arxiv", 0),
    ]
    raw = "LongRAG beats RAG by 6.16% [2]. It improves recall [2]."
    agent, _, tracer = make_agent([raw, FOLLOWUPS], retriever=InMemoryRetriever(chunks))
    list(agent.run("s1", "How much does LongRAG beat RAG?"))

    assert tracer.traces[0]["number_check"] == [
        {"sentence": 0, "number": "6.16%", "cited": [2], "found_in": [1]}
    ]
