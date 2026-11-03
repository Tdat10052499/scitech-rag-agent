"""Search plans for paper-finding questions (scitech_agent.intent) and how the agent uses them."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from scitech_agent.agent import Agent, AgentConfig
from scitech_agent.intent import SearchPlan, arxiv_ids, paper_count, plan_search, wants_papers
from scitech_agent.llm import FakeLLM
from scitech_agent.retrieval import InMemoryRetriever, ScoredChunk, year_range
from scitech_agent.trace import ListTraceWriter

TODAY = date(2026, 11, 3)
GOLDEN = Path(__file__).resolve().parents[2] / "evaluation" / "golden_set" / "golden.jsonl"


def plan(text: str, query: str | None = None) -> SearchPlan:
    return plan_search(text, query or text, TODAY, top_k=5, list_top_k=10)


# --- Detection ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "reasons", "filters", "k"),
    [
        # The two questions refused on the Space on 2026-11-03.
        (
            "Bạn có đưa ra những nghiên cứu mới nhất vào năm 2026 về Large Language-model "
            "được không",
            ("year", "list"),
            year_range(2026, 2026),
            10,
        ),
        ("Just find the 5 to 10 papers that make the research for this topic", ("list",), None, 10),
        ("Find 3 papers on speculative decoding", ("list",), None, 5),  # never below top_k
        ("Liệt kê các bài báo về RAG từ năm 2024", ("year", "list"), year_range(2024), 10),
        ("Which papers study tokenization between 2020 and 2022?", ("year", "list"), None, 10),
        ("What are the latest results on long-context models?", ("recent",), None, None),
        ("Hallucination detection methods published in 2025", ("year",), None, None),
        ("Before 2015, how was machine translation evaluated?", ("year",), None, None),
    ],
)
def test_plan_detects_paper_finding_questions(text, reasons, filters, k) -> None:
    got = plan(text)
    assert got.reasons == reasons
    if filters is not None:
        assert got.filters == filters
    assert got.k == k
    assert got.list_papers == ("list" in reasons)


def test_year_forms() -> None:
    assert plan("papers between 2020 and 2022").filters == year_range(2020, 2022)
    assert plan("work after 2023 on agents").filters == year_range(2024)
    assert plan("evaluation before 2015").filters == year_range(None, 2014)
    recent = plan("mới nhất về LLM").filters
    assert recent == {"published_at": {"gte": "2025-11-03"}}


@pytest.mark.parametrize(
    "text",
    [
        "What is retrieval-augmented generation?",
        "How does BERT (2018) differ from GPT?",  # a year without a temporal word
        "Show me how attention works",
        "Tìm hiểu về transformer",  # "tìm hiểu" is "learn about", not "find"
        "Okey, so can you give me the specific method that I can research deeper in it please!",
        "Recent work shows that larger models hallucinate less; is that true?",
    ],
)
def test_plain_questions_get_the_empty_plan(text: str) -> None:
    assert plan(text) == SearchPlan()


def test_arxiv_ids() -> None:
    assert arxiv_ids("explain arXiv:2302.00083v2 and 1810.04805, then 2302.00083") == (
        "2302.00083",
        "1810.04805",
    )
    assert arxiv_ids("version 1.2345 or 12.34567 or 2302.008") == ()
    got = plan("Giải thích dễ hiểu bài 2302.00083 năm 2023")
    assert (got.reasons, got.arxiv_ids, got.filters) == (("arxiv_id",), ("2302.00083",), None)


def test_paper_count_and_list_words() -> None:
    assert paper_count("find the 5 to 10 papers") == 10
    assert paper_count("give me 3 recent papers") == 3
    assert paper_count("papers please") is None
    assert wants_papers("Gợi ý cho tôi vài bài báo về RAG")
    assert not wants_papers("How do papers evaluate RAG?")


def test_the_rewritten_query_is_read_too() -> None:
    got = plan("Find papers on that", "papers on retrieval-augmented generation in 2025")
    assert got.reasons == ("year", "list") and got.filters == year_range(2025, 2025)


def test_no_golden_question_changes_its_search() -> None:
    """Evaluation runs answer golden items as before: none gets a plan, except gs-u02 (2027), whose
    filtered search is empty on the frozen index, so the agent falls back to the default search."""
    triggered = []
    for line in GOLDEN.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        texts = [item["question"]]
        texts += [t["content"] for t in item.get("history", []) if t["role"] == "user"]
        if any(plan(t).active for t in texts):
            triggered.append(item["id"])
    assert triggered == ["gs-u02"]


# --- Agent -------------------------------------------------------------------------------------


def chunk(doc_id: str, title: str, text: str, published_at: str) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=f"{doc_id}#0",
        doc_id=doc_id,
        score=0.0,
        title=title,
        text=text,
        source="arxiv",
        chunk_index=0,
        published_at=published_at,
    )


CHUNKS = [
    chunk("2601.00001", "Reasoning LLMs", "large language models reasoning survey", "2026-01-15"),
    chunk(
        "2302.00083", "In-Context RALM", "large language models retrieval grounding", "2023-01-31"
    ),
    chunk("2410.00002", "Agents", "large language models agents planning", "2024-10-02"),
]


def make_agent(outputs, **config):
    tracer = ListTraceWriter()
    llm = FakeLLM(outputs)
    retriever = InMemoryRetriever(CHUNKS)
    agent = Agent(
        retriever,
        llm,
        AgentConfig(search_modes=True, **config),
        tracer=tracer,
        today=lambda: TODAY,
    )
    return agent, llm, retriever, tracer


def test_year_list_question_filters_and_shows_dates() -> None:
    agent, llm, retriever, tracer = make_agent(
        ["- Reasoning LLMs (2601.00001, 2026-01-15) [1]", "[]"]
    )
    list(agent.run("s1", "Find papers on large language models in 2026"))

    query, k, filters = retriever.calls[-1]
    assert (k, filters) == (10, year_range(2026, 2026))
    system, user = llm.calls[0].messages
    assert "Extra rules for this question" in system["content"]
    assert "arXiv: 2601.00001\nPublished: 2026-01-15" in user["content"]
    assert "2302.00083" not in user["content"]  # 2023, filtered out
    assert llm.calls[0].max_tokens == AgentConfig().list_max_tokens
    search = tracer.traces[0]["search"]
    assert search["reasons"] == ["year", "list"] and search["fallback"] is False


def test_arxiv_id_question_sees_only_that_paper() -> None:
    agent, llm, retriever, _ = make_agent(["It grounds an LM in retrieved text [1].", "[]"])
    list(agent.run("s1", "Explain 2302.00083 in simple words: large language models"))
    assert retriever.calls[-1][2] == {"doc_id": "2302.00083"}
    user = llm.calls[0].messages[1]["content"]
    assert user.count("<source id=") == 1 and "arXiv: 2302.00083" in user


def test_empty_filtered_search_falls_back_to_the_default_search() -> None:
    agent, llm, retriever, tracer = make_agent(["Models reason [1].", "[]"])
    list(agent.run("s1", "large language models reasoning in 2019"))
    assert [c[2] for c in retriever.calls] == [year_range(2019, 2019), None]
    assert retriever.calls[-1][1] == 5
    messages = llm.calls[0].messages
    assert messages[0]["content"] == agent.answer_prompt  # exactly the default prompts
    assert "Published:" not in messages[1]["content"]
    assert tracer.traces[0]["search"] == SearchPlan(fallback=True).to_dict()


def test_empty_filtered_list_question_stays_a_list() -> None:
    agent, llm, retriever, tracer = make_agent(["- Agents (2410.00002, 2024-10-02) [1]", "[]"])
    list(agent.run("s1", "List papers on large language models in 2019"))
    assert retriever.calls[-1][1:] == (10, None)
    assert "Extra rules" in llm.calls[0].messages[0]["content"]
    assert tracer.traces[0]["search"]["reasons"] == ["list"]
    assert tracer.traces[0]["search"]["fallback"] is True


def test_plain_question_is_unchanged_with_search_modes_on() -> None:
    on, llm_on, retriever_on, _ = make_agent(["Models reason [1].", "[]"])
    off = Agent(InMemoryRetriever(CHUNKS), FakeLLM(["Models reason [1].", "[]"]), AgentConfig())
    list(on.run("s1", "How do large language models reason?"))
    list(off.run("s1", "How do large language models reason?"))
    assert retriever_on.calls == off.retriever.calls
    assert llm_on.calls[0].messages == off.llm.calls[0].messages


def test_search_modes_off_ignores_paper_questions() -> None:
    agent = Agent(InMemoryRetriever(CHUNKS), FakeLLM(["x [1].", "[]"]), AgentConfig())
    list(agent.run("s1", "Find papers on large language models in 2026"))
    assert agent.retriever.calls == [("Find papers on large language models in 2026", 5, None)]
