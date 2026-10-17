"""`POST /chat` streams contract-valid server-sent events (W2-D2-DAT-1).

The endpoint runs the real `scitech_agent.Agent` with the offline demo retriever and LLM
(W2-D3-DAT-1). Payloads are validated against the schemas of the frozen contract
(docs/contracts/api.openapi.yaml), so a drift between code and contract fails here.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.agent_adapter import AgentAdapter
from app.agent_port import (
    AgentError,
    AgentEvent,
    DoneEvent,
    FollowupsEvent,
    SourcesEvent,
    TokenEvent,
)
from app.main import app, create_app, get_agent
from scitech_agent.agent import Agent
from scitech_agent.demo import DEMO_CHUNKS, DEMO_FOLLOWUPS

CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "api.openapi.yaml"
SCHEMAS = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))["components"]["schemas"]
EVENT_NAMES = {"sources", "token", "followups", "done", "error"}


def parse_sse(body: str) -> list[tuple[str, Any]]:
    """Return (event, decoded JSON data) pairs; fails if a frame is not `event:` + JSON `data:`."""
    events = []
    for frame in body.split("\n\n"):
        if not frame.strip():
            continue
        lines = frame.split("\n")
        assert lines[0].startswith("event: "), frame
        assert len(lines) == 2 and lines[1].startswith("data: "), frame
        events.append((lines[0][len("event: ") :], json.loads(lines[1][len("data: ") :])))
    return events


def check(schema_name: str, payload: Any) -> None:
    errors = [e.message for e in Draft202012Validator(SCHEMAS[schema_name]).iter_errors(payload)]
    assert errors == [], (schema_name, payload)


def post_chat(client: TestClient, message: str = "What is a Transformer?") -> list[tuple[str, Any]]:
    response = client.post("/chat", json={"session_id": "s1", "message": message})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return parse_sse(response.text)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_endpoint_uses_the_real_agent() -> None:
    agent = get_agent()
    assert isinstance(agent, AgentAdapter) and isinstance(agent.agent, Agent)
    assert get_agent() is agent  # one instance, so session history persists


def test_stream_order_and_shapes(client: TestClient) -> None:
    events = post_chat(client)
    names = [name for name, _ in events]

    assert set(names) <= EVENT_NAMES
    assert names[0] == "sources"
    assert names[-1] == "done"
    assert names.count("sources") == 1 and names.count("done") == 1
    assert "error" not in names
    middle = names[1:-1]
    assert middle[-1] == "followups" and set(middle[:-1]) == {"token"}

    sources = events[0][1]
    assert isinstance(sources, list) and len(sources) == len(DEMO_CHUNKS)
    for source in sources:
        check("Source", source)
    assert all(isinstance(data, str) for name, data in events if name == "token")
    followups = dict(events)["followups"]
    assert followups == DEMO_FOLLOWUPS and len(followups) <= 4
    done = events[-1][1]
    check("Done", done)
    assert done["insufficient_evidence"] is False
    assert done["message_id"]


def test_tokens_rebuild_answer_and_citations_point_to_sources(client: TestClient) -> None:
    events = post_chat(client)
    answer = "".join(data for name, data in events if name == "token")
    assert "\n" in answer  # a newline survives because tokens are JSON strings
    citations = {int(n) for n in re.findall(r"\[(\d+)\]", answer)}
    assert citations and all(1 <= n <= len(events[0][1]) for n in citations)


def test_insufficient_evidence(client: TestClient) -> None:
    events = post_chat(client, "insufficient evidence please")
    assert events[0] == ("sources", [])
    assert [name for name, _ in events][-1] == "done"
    done = events[-1][1]
    check("Done", done)
    assert done["insufficient_evidence"] is True
    assert "followups" not in [name for name, _ in events]


@pytest.mark.parametrize("code", ["llm_unavailable", "timeout", "internal"])
def test_llm_error_ends_stream_with_error_event(client: TestClient, code: str) -> None:
    events = post_chat(client, f"please fail:{code}")
    names = [name for name, _ in events]
    assert names == ["sources", "error"]
    check("Error", events[-1][1])
    assert events[-1][1]["code"] == code
    assert "Simulated" not in events[-1][1]["message"]  # the cause stays in the log


def test_retrieval_error_is_the_only_event(client: TestClient) -> None:
    events = post_chat(client, "please fail:retrieval_failed")
    assert [name for name, _ in events] == ["error"]
    check("Error", events[0][1])
    assert events[0][1]["code"] == "retrieval_failed"


def test_sources_carry_contract_fields(client: TestClient) -> None:
    sources = post_chat(client)[0][1]
    first = sources[0]
    assert first["chunk_id"] == DEMO_CHUNKS[0].chunk_id
    assert first["published_at"] == "2017-06-12"
    assert first["categories"] == ["cs.CL", "cs.LG"]
    assert "categories" not in sources[1]  # empty fields are left out, not sent as null


class CrashingAgent:
    def run(self, session_id: str, message: str) -> Iterator[AgentEvent]:
        yield SourcesEvent([])
        raise ValueError("secret stack detail")


class NoSourcesAgent:
    def run(self, session_id: str, message: str) -> Iterator[AgentEvent]:
        yield TokenEvent("hello")
        yield DoneEvent()


class NoDoneAgent:
    def run(self, session_id: str, message: str) -> Iterator[AgentEvent]:
        yield SourcesEvent([])
        yield TokenEvent("hello")


class EarlyErrorAgent:
    def run(self, session_id: str, message: str) -> Iterator[AgentEvent]:
        raise AgentError("retrieval_failed", "Qdrant is not reachable.")
        yield  # pragma: no cover - makes this a generator


@pytest.mark.parametrize("agent", [CrashingAgent(), NoSourcesAgent(), NoDoneAgent()])
def test_unexpected_failures_become_internal_error(client: TestClient, agent: object) -> None:
    app.dependency_overrides[get_agent] = lambda: agent
    events = post_chat(client)
    name, payload = events[-1]
    assert name == "error"
    check("Error", payload)
    assert payload["code"] == "internal"
    assert "secret" not in payload["message"]
    assert [n for n, _ in events].count("error") == 1
    assert "done" not in [n for n, _ in events]


def test_error_before_any_source(client: TestClient) -> None:
    app.dependency_overrides[get_agent] = lambda: EarlyErrorAgent()
    events = post_chat(client)
    expected = {"code": "retrieval_failed", "message": "Qdrant is not reachable."}
    assert events == [("error", expected)]


def test_followups_are_capped_at_four(client: TestClient) -> None:
    class ChattyAgent:
        def run(self, session_id: str, message: str) -> Iterator[AgentEvent]:
            yield SourcesEvent([])
            yield FollowupsEvent([f"q{i}" for i in range(6)])
            yield DoneEvent()

    app.dependency_overrides[get_agent] = lambda: ChattyAgent()
    events = post_chat(client)
    assert dict(events)["followups"] == ["q0", "q1", "q2", "q3"]
    assert events[-1] == ("done", {"insufficient_evidence": False})


@pytest.mark.parametrize(
    "body",
    [{"session_id": "s1", "message": ""}, {"session_id": "s1"}, {"message": "hi"}, {}],
)
def test_invalid_request_is_422_before_streaming(client: TestClient, body: dict[str, str]) -> None:
    response = client.post("/chat", json=body)
    assert response.status_code == 422
    assert not response.headers["content-type"].startswith("text/event-stream")


def test_cors_allows_configured_origin() -> None:
    with TestClient(create_app(cors_origins=["http://localhost:5173"])) as cors_client:
        response = cors_client.options(
            "/chat",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    with TestClient(create_app()) as plain_client:
        response = plain_client.get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in response.headers
