"""`AGENT_MODE` chooses the agent behind `/chat`; a real agent that cannot be built gives an
`error` event instead of a crash (W4-D2-DAT-1)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.agent_adapter import AgentAdapter
from scitech_agent.agent import Agent
from scitech_agent.demo import DemoRetriever
from scitech_agent.llm import FakeLLM
from scitech_agent.retrieval import InMemoryRetriever, ScoredChunk

CHUNK = ScoredChunk(
    chunk_id="2410.18050#0",
    doc_id="2410.18050",
    score=1.0,
    title="LongRAG",
    text="LongRAG outperforms long-context LLMs on multi-hop question answering.",
    source="arxiv",
    chunk_index=0,
)


def events(client: TestClient, message: str, session_id: str = "s1") -> list[tuple[str, object]]:
    response = client.post("/chat", json={"session_id": session_id, "message": message})
    assert response.status_code == 200
    frames = [f.split("\n") for f in response.text.split("\n\n") if f.strip()]
    return [(f[0].removeprefix("event: "), json.loads(f[1].removeprefix("data: "))) for f in frames]


@pytest.mark.parametrize(
    ("value", "expected"), [("", "real"), ("real", "real"), (" Demo ", "demo")]
)
def test_agent_mode_values(value: str, expected: str) -> None:
    assert main.agent_mode({"AGENT_MODE": value}) == expected


def test_agent_mode_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="AGENT_MODE"):
        main.agent_mode({"AGENT_MODE": "fake"})


def test_demo_mode_uses_the_offline_agent() -> None:
    agent = main.get_agent()
    assert isinstance(agent, AgentAdapter)
    assert isinstance(agent.agent.retriever, DemoRetriever)


def test_real_mode_streams_from_the_configured_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = FakeLLM(["LongRAG beats long-context LLMs [1].", '["What is RAG?"]'], default="[]")
    built: list[Agent] = []

    def build() -> Agent:
        built.append(Agent(InMemoryRetriever([CHUNK]), llm))
        return built[-1]

    monkeypatch.setenv("AGENT_MODE", "real")
    monkeypatch.setattr(main, "agent_from_env", build)
    with TestClient(main.create_app()) as client:
        first = events(client, "How much better is LongRAG?")
        events(client, "And on single-hop questions?")
    names = [name for name, _ in first]
    assert names[0] == "sources" and names[-2:] == ["followups", "done"]
    assert set(names[1:-2]) == {"token"}
    assert first[0][1][0]["chunk_id"] == "2410.18050#0"  # type: ignore[index]
    assert len(built) == 1  # built once at startup, then reused
    assert [t.question for t in built[0].history("s1")] == [
        "How much better is LongRAG?",
        "And on single-hop questions?",
    ]


def test_real_mode_without_llm_settings_gives_an_error_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_MODE", "real")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    with TestClient(main.create_app()) as client:
        result = events(client, "What is a Transformer?")
    assert [name for name, _ in result] == ["error"]
    assert result[0][1]["code"] == "llm_unavailable"  # type: ignore[index]
    assert "LLM_" not in result[0][1]["message"]  # type: ignore[index]  # no internals


def test_real_mode_retries_after_a_failed_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MODE", "real")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("LLM_MODEL", "llama3.2:3b")
    monkeypatch.setenv("RETRIEVER", "bm25")
    monkeypatch.setenv("BM25_INDEX_DIR", "/nonexistent/bm25")
    failed = main.get_agent()
    assert isinstance(failed, main.UnavailableAgent) and failed.code == "retrieval_failed"

    monkeypatch.setattr(main, "agent_from_env", lambda: Agent(InMemoryRetriever([]), FakeLLM()))
    assert isinstance(main.get_agent(), AgentAdapter)  # the failure was not cached


def test_startup_fails_on_unknown_agent_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MODE", "fake")
    with pytest.raises(ValueError, match="AGENT_MODE"), TestClient(main.create_app()):
        pass
