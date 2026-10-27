"""Tests of the evidence check, the refuse path and the request limits (W5-D3-DAT-1), with
`InMemoryRetriever` and `FakeLLM` only."""

from __future__ import annotations

import pytest

from scitech_agent.agent import Agent, AgentConfig, Turn, load_prompt
from scitech_agent.events import AgentError, DoneEvent, FollowupsEvent, SourcesEvent, TokenEvent
from scitech_agent.evidence import (
    INSUFFICIENT_ANSWER,
    REFUSAL_HINT,
    LimitExceeded,
    RequestBudget,
    is_refusal,
    parse_verdict,
)
from scitech_agent.llm import FakeLLM, LLMUnavailableError, split_fragments
from scitech_agent.retrieval import InMemoryRetriever, ScoredChunk

CHUNKS = [
    ScoredChunk(
        "2409.02060#0",
        "2409.02060",
        0.0,
        "OLMoE",
        "OLMoE. A mixture-of-experts language model with 1B active and 7B total parameters, "
        "pretrained on 5 trillion tokens.",
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
CITED = "OLMoE uses 1B active parameters out of 7B [1]."
UNCITED = "OLMoE uses 1 billion parameters per token and was trained on 5 trillion tokens."
REFUSAL = "The sources do not contain enough evidence to answer this question."
FOLLOWUPS = '["How was OLMoE pretrained?"]'


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def make_agent(outputs, clock: Clock | None = None, **config):
    retriever = InMemoryRetriever(CHUNKS)
    llm = FakeLLM(outputs)
    agent = Agent(retriever, llm, AgentConfig(**config), clock=clock or Clock())
    return agent, retriever, llm


def text_of(events) -> str:
    return "".join(e.text for e in events if isinstance(e, TokenEvent))


# --- Self-check -------------------------------------------------------------------------------


def test_self_check_no_refuses_without_an_answer_call() -> None:
    agent, _, llm = make_agent(["NO"], self_check=True)
    events = list(agent.run("s1", QUESTION))

    assert events[0] == SourcesEvent([])
    assert text_of(events) == INSUFFICIENT_ANSWER and REFUSAL_HINT in INSUFFICIENT_ANSWER
    assert not any(isinstance(e, FollowupsEvent) for e in events)
    assert isinstance(events[-1], DoneEvent) and events[-1].insufficient_evidence
    (call,) = llm.calls
    assert call.stream is False and call.max_tokens == 8 and call.temperature == 0.0
    assert call.messages[0] == {"role": "system", "content": load_prompt("self_check")}
    user = call.messages[1]["content"]
    assert '<source id="1">\nTitle: OLMoE' in user
    assert user.endswith(f"<question>\n{QUESTION}\n</question>")


@pytest.mark.parametrize("verdict", ["YES", "Partly.", "yes, source 1 states it"])
def test_self_check_yes_or_partly_answers(verdict: str) -> None:
    agent, _, llm = make_agent([verdict, CITED, FOLLOWUPS], self_check=True)
    events = list(agent.run("s1", QUESTION))
    assert text_of(events) == CITED and not events[-1].insufficient_evidence
    assert [c.stream for c in llm.calls] == [False, True, False]


@pytest.mark.parametrize("failure", [LLMUnavailableError("tunnel gone"), "", "I think so"])
def test_self_check_fails_open(failure) -> None:
    agent, _, llm = make_agent([failure, CITED, FOLLOWUPS], self_check=True)
    events = list(agent.run("s1", QUESTION))
    assert isinstance(events[0], SourcesEvent) and events[0].chunks
    assert text_of(events) == CITED


def test_self_check_off_makes_no_call() -> None:
    agent, _, llm = make_agent([CITED, FOLLOWUPS])
    list(agent.run("s1", QUESTION))
    assert [c.stream for c in llm.calls] == [True, False]


def test_self_check_gets_the_rewritten_query() -> None:
    standalone = "How many parameters does OLMoE use per token?"
    agent, _, llm = make_agent([standalone, "YES", CITED, FOLLOWUPS], rewrite=True, self_check=True)
    agent._remember("s1", Turn("What is OLMoE?", "A mixture-of-experts model [1]."))
    list(agent.run("s1", "How many parameters does it use?"))
    assert llm.calls[1].messages[1]["content"].endswith(f"<question>\n{standalone}\n</question>")


# --- Refusal in the answer (#114) -------------------------------------------------------------


def test_uncited_refusal_is_insufficient_and_gets_the_hint() -> None:
    agent, _, llm = make_agent([REFUSAL])
    events = list(agent.run("s1", QUESTION))
    assert text_of(events) == REFUSAL + "\n\n" + REFUSAL_HINT
    assert events[-1].insufficient_evidence
    assert not any(isinstance(e, FollowupsEvent) for e in events) and len(llm.calls) == 1
    assert agent.history("s1")[-1].answer == REFUSAL  # the hint is not kept for later prompts


def test_uncited_answer_is_not_reported_as_insufficient() -> None:
    agent, _, llm = make_agent([UNCITED, FOLLOWUPS])
    events = list(agent.run("s1", QUESTION))
    assert text_of(events) == UNCITED
    assert not events[-1].insufficient_evidence
    assert events[-2] == FollowupsEvent(["How was OLMoE pretrained?"])


def test_cited_partial_answer_is_not_a_refusal() -> None:
    partial = CITED + " The sources do not mention the training data."
    agent, _, _ = make_agent([partial, FOLLOWUPS])
    events = list(agent.run("s1", QUESTION))
    assert text_of(events) == partial and not events[-1].insufficient_evidence


@pytest.mark.parametrize(
    "answer",
    [
        REFUSAL,
        "The evidence is insufficient to answer this question.",
        "There is not enough information in the sources to answer this.",
        "None of the sources mention the number of parameters.",
        "The provided sources don't specify which datasets were used.",
        "I cannot answer this question from the given sources.",
        "The datasets are not specified in the provided abstracts.",
        "No source covers this.",
    ],
)
def test_is_refusal(answer: str) -> None:
    assert is_refusal(answer)


@pytest.mark.parametrize(
    "answer",
    [UNCITED, "Dropout does not change the number of parameters.", "Yes, it is open source."],
)
def test_is_not_refusal(answer: str) -> None:
    assert not is_refusal(answer)


@pytest.mark.parametrize(
    ("text", "verdict"),
    [("YES", "yes"), ("no.", "no"), ("PARTLY", "partly"), ("Partially", "partly"), ("?", None)],
)
def test_parse_verdict(text: str, verdict: str | None) -> None:
    assert parse_verdict(text) == verdict


# --- Limits -----------------------------------------------------------------------------------


def follow_up_agent(outputs, **config):
    agent, retriever, llm = make_agent(outputs, rewrite=True, self_check=True, **config)
    agent._remember("s1", Turn("What is OLMoE?", "A mixture-of-experts model [1]."))
    return agent, retriever, llm


def test_one_llm_call_is_kept_for_the_answer() -> None:
    agent, retriever, llm = follow_up_agent([CITED], max_llm_calls=1)
    events = list(agent.run("s1", QUESTION))
    assert [c.stream for c in llm.calls] == [True]  # no rewrite, self-check or follow-ups
    assert retriever.calls[0][0] == QUESTION
    assert text_of(events) == CITED and not any(isinstance(e, FollowupsEvent) for e in events)


@pytest.mark.parametrize(
    ("limit", "streams"),
    [
        (2, [False, True]),  # rewrite, answer
        (3, [False, False, True]),  # rewrite, self-check, answer
        (4, [False, False, True, False]),  # and follow-ups
    ],
)
def test_llm_calls_never_exceed_the_limit(limit: int, streams: list[bool]) -> None:
    agent, _, llm = follow_up_agent([QUESTION, "YES", CITED, FOLLOWUPS], max_llm_calls=limit)
    list(agent.run("s1", QUESTION))
    assert [c.stream for c in llm.calls] == streams


def test_time_limit_before_the_answer_is_a_timeout_error() -> None:
    clock = Clock()

    def slow_rewrite(messages):
        clock.now += 30.0
        return QUESTION

    agent, _, llm = follow_up_agent([slow_rewrite], clock=clock, timeout_s=10.0)
    with pytest.raises(AgentError) as info:
        next(agent.run("s1", QUESTION))  # a single `error` event, no `sources`
    assert info.value.code == "timeout"
    assert len(llm.calls) == 1  # the self-check was skipped, the answer never called


def test_time_limit_while_streaming_stops_the_answer() -> None:
    clock = Clock()

    class SlowStream(FakeLLM):
        def stream_chat(self, messages, temperature=0.0, max_tokens=512):
            self.calls.append(None)
            for n, fragment in enumerate(split_fragments(CITED)):
                if n == 2:
                    clock.now = 99.0
                yield fragment

    llm = SlowStream()
    agent = Agent(InMemoryRetriever(CHUNKS), llm, AgentConfig(timeout_s=10.0), clock=clock)
    run = agent.run("s1", QUESTION)
    events = [next(run) for _ in range(4)]  # sources and three fragments
    assert isinstance(events[0], SourcesEvent)
    with pytest.raises(AgentError) as info:
        next(run)
    assert info.value.code == "timeout"
    assert len(llm.calls) == 1  # no follow-ups call


def test_request_budget() -> None:
    clock = Clock()
    budget = RequestBudget(3, 5.0, clock)
    assert budget.take_optional() and budget.take_optional()
    assert not budget.take_optional()  # the last call is kept for the answer
    budget.take_required()
    assert budget.calls_left == 0 and not budget.take_optional(reserve=0)

    budget = RequestBudget(4, 5.0, clock)
    clock.now = 5.0
    assert budget.expired() and not budget.take_optional(reserve=0)
    with pytest.raises(LimitExceeded):
        budget.take_required()


def test_limits_from_env() -> None:
    config = AgentConfig.from_env({})
    assert (config.self_check, config.max_llm_calls, config.timeout_s) == (False, 4, 120.0)
    env = {"AGENT_SELF_CHECK": "on", "AGENT_MAX_LLM_CALLS": "2", "AGENT_TIMEOUT_S": "45.5"}
    config = AgentConfig.from_env(env)
    assert (config.self_check, config.max_llm_calls, config.timeout_s) == (True, 2, 45.5)
    for bad in ({"AGENT_MAX_LLM_CALLS": "0"}, {"AGENT_TIMEOUT_S": "-1"}, {"AGENT_SELF_CHECK": "2"}):
        with pytest.raises(ValueError):
            AgentConfig.from_env(bad)
