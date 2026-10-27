"""`agent_from_env` builds the configured agent or fails with a contract error code."""

from __future__ import annotations

import logging

import pytest

from scitech_agent import factory
from scitech_agent.agent import Agent
from scitech_agent.events import AgentError
from scitech_agent.llm import OpenAICompatibleLLM
from scitech_agent.retrieval import InMemoryRetriever
from scitech_agent.retrieval.hybrid import HybridConfig, HybridRetriever

LLM_ENV = {"LLM_BASE_URL": "http://localhost:11434/v1", "LLM_MODEL": "llama3.2:3b"}


def test_builds_the_agent_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    retriever = InMemoryRetriever([])
    seen: list[dict[str, str]] = []
    monkeypatch.setattr(factory, "retriever_from_env", lambda env: seen.append(env) or retriever)
    env = {**LLM_ENV, "RETRIEVER": "hybrid", "RETRIEVAL_TOP_K": "7", "RETRIEVAL_MIN_SCORE": "0.01"}
    agent = factory.agent_from_env(env)
    assert isinstance(agent, Agent)
    assert agent.retriever is retriever and seen == [env]
    assert isinstance(agent.llm, OpenAICompatibleLLM) and agent.llm.model == "llama3.2:3b"
    assert (agent.config.top_k, agent.config.min_score) == (7, 0.01)


@pytest.mark.parametrize(
    ("env", "code"),
    [
        ({**LLM_ENV, "RETRIEVAL_TOP_K": "five"}, "internal"),
        ({"LLM_MODEL": "llama3.2:3b"}, "llm_unavailable"),
        ({**LLM_ENV, "LLM_BASE_URL": "localhost:11434"}, "llm_unavailable"),
        ({**LLM_ENV, "RETRIEVER": "sparse"}, "retrieval_failed"),
        (
            {**LLM_ENV, "RETRIEVER": "bm25", "BM25_INDEX_DIR": "/nonexistent/bm25"},
            "retrieval_failed",
        ),
    ],
)
def test_settings_that_stop_the_build_map_to_contract_codes(
    env: dict[str, str], code: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(AgentError) as info:
        factory.agent_from_env(env)
    assert info.value.code == code
    assert "cannot build the agent" in caplog.text  # the cause is logged, not shown to the user
    assert "nonexistent" not in info.value.message and "LLM_" not in info.value.message


def test_llm_is_not_needed_to_check_the_llm_settings_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def must_not_load(env: object) -> None:
        raise AssertionError("retriever built before the LLM settings were checked")

    monkeypatch.setattr(factory, "retriever_from_env", must_not_load)
    with pytest.raises(AgentError) as info:
        factory.agent_from_env({"LLM_MODEL": "x"})
    assert info.value.code == "llm_unavailable"


@pytest.mark.parametrize(
    ("min_score", "builds"), [("0.03", True), ("0.033", False), ("0.5", False)]
)
def test_threshold_must_be_reachable_by_the_hybrid_retriever(
    monkeypatch: pytest.MonkeyPatch, min_score: str, builds: bool
) -> None:
    # RRF with rrf_k 60: the best hit (rank 1 in both lists) scores 2 / 61, about 0.0328.
    hybrid = HybridRetriever(InMemoryRetriever([]), InMemoryRetriever([]))
    monkeypatch.setattr(factory, "retriever_from_env", lambda env: hybrid)
    env = {**LLM_ENV, "RETRIEVAL_MIN_SCORE": min_score}
    if builds:
        assert factory.agent_from_env(env).config.min_score == float(min_score)
    else:
        with pytest.raises(AgentError) as info:
            factory.agent_from_env(env)
        assert info.value.code == "internal"


def test_score_ceiling_per_retriever() -> None:
    assert factory.score_ceiling(InMemoryRetriever([])) is None
    hybrid = HybridRetriever(InMemoryRetriever([]), InMemoryRetriever([]), HybridConfig(rrf_k=0))
    assert factory.score_ceiling(hybrid) == 2.0


@pytest.mark.parametrize(
    "env",
    [
        {"AGENT_SELF_CHECK": "maybe"},
        {"AGENT_MAX_LLM_CALLS": "0"},
        {"AGENT_MAX_LLM_CALLS": "four"},
        {"AGENT_TIMEOUT_S": "0"},
    ],
)
def test_invalid_agent_limits_stop_the_build(env: dict[str, str]) -> None:
    with pytest.raises(AgentError) as info:
        factory.agent_from_env({**LLM_ENV, **env})
    assert info.value.code == "internal"
