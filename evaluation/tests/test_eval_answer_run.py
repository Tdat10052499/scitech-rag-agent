"""Tests of `python -m scitech_eval answers` with a fake agent and a scripted judge.

Nothing here talks to a model. The fake agent returns records in the format of
`BatchResult.to_dict()` (agent/src/scitech_agent/agent.py); `test_real_agent_records` checks that
format against the real `Agent` with `InMemoryRetriever` and `FakeLLM`.
"""

import json
from pathlib import Path

import pytest
import yaml

from scitech_eval.__main__ import main
from scitech_eval.answer_run import (
    REFUSAL_SENTENCE,
    build_judge_prompt,
    format_passages,
    invalid_citations,
    load_answer_config,
    parse_judgement,
    run_answers,
    select_items,
    sentences_for_judge,
    traces_target,
)
from scitech_eval.golden import load_golden

REPO = Path(__file__).resolve().parents[2]
DATA = Path(__file__).parent / "data"
TEMPLATE = (
    "Q: {question}\nS: {sentence}\nP:\n{cited_passages}\n"
    'Reply with JSON only: {"label": "supported" | "not supported" | "not checkable"}'
)
PROMPT_INFO = {"path": "p.md", "sha256": "abc", "commit": "def"}


def source(n, doc, text="passage"):
    return {
        "n": n,
        "chunk_id": f"{doc}#0",
        "doc_id": doc,
        "title": f"T{n}",
        "text": text,
        "score": 0.5,
    }


def record(item_id, answer, sources, *, raw=None, citations=(), error=None, refused=False):
    return {
        "answer_id": item_id,
        "question": f"question of {item_id}",
        "error": error,
        "answer": answer,
        "answer_raw": answer if raw is None else raw,
        "sources": sources,
        "citations": list(citations),
        "followups": [],
        "insufficient_evidence": refused,
        "trace": {
            "latency_ms": 5,
            "retrieved": [{"chunk_id": s["chunk_id"], "doc_id": s["doc_id"]} for s in sources],
            "model": {
                "model": "gen-model",
                "timeout": 60,
                "max_retries": 2,
            },  # LLMClient.describe()
            "config": {"temperature": 0.0},
        },
    }


class FakeResult:
    def __init__(self, data):
        self.data = data

    def to_dict(self):
        return self.data


class FakeAgent:
    def __init__(self, records):
        self.records = records
        self.batch = None
        self.events = []

    def warm_up(self):
        self.events.append("warm_up")

    def run_batch(self, questions):
        self.events.append("run_batch")
        self.batch = list(questions)
        return [FakeResult(self.records[q["id"]]) for q in self.batch]


class FakeJudge:
    """Answers by the sentence found in the prompt; unknown sentences get `default`."""

    model = "judge-model"

    def __init__(self, replies, default='{"label": "not checkable"}'):
        self.replies, self.default, self.calls = replies, default, []

    def chat(self, messages, temperature, max_tokens):
        prompt = messages[0]["content"]
        self.calls.append((prompt, temperature, max_tokens))
        sentence = prompt.split("\nS: ")[1].split("\nP:")[0]
        reply = self.replies.get(sentence, self.default)
        if isinstance(reply, Exception):
            raise reply
        return reply


def config(tmp_path, **overrides):
    golden = tmp_path / "golden.jsonl"
    golden.write_text((DATA / "toy_golden.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    base = {
        "name": "t",
        "golden_path": str(golden),
        "split": "dev",
        "language": "en",
        "dataset_snapshot": "d",
        "index_snapshot": "i",
        "notes": "",
        "generator": {"digest": "gd", "max_tokens": 512},
        "agent": {"factory": "x:y"},
        "judge": {"prompt_path": "p.md", "digest": "jd", "temperature": 0, "max_tokens": 150},
        "bootstrap": {"resamples": 50, "seed": 0},
    }
    base.update(overrides)
    return base


def run(tmp_path, records, replies, ids, **overrides):
    cfg = config(tmp_path, **overrides)
    cfg["ids"] = ids
    items = select_items(cfg, load_golden(Path(cfg["golden_path"])))
    judge = FakeJudge(replies)
    agent = FakeAgent(records)
    result, answers = run_answers(cfg, items, agent, judge, TEMPLATE, PROMPT_INFO)
    return result, answers, judge, agent


SUPPORTED = '{"label": "supported", "reason": ""}'
UNSUPPORTED = '{"label": "not supported", "reason": "missing"}'


def test_scores_counts_and_separates_refusals_errors_and_judge_errors(tmp_path):
    records = {
        # gs-001: 2 supported, 1 not supported, 1 not checkable; cites doc 1 only -> cited recall 1
        "gs-001": record(
            "gs-001",
            "Alpha is one [1]. Beta is two [2]. Gamma is three. Hello there.",
            [source(1, "2001.00001"), source(2, "2001.00099")],
            citations=["2001.00001#0", "2001.00099#0"],
        ),
        "gs-002": record("gs-002", "The sources do not contain enough evidence.", [], refused=True),
        "gs-003": record("gs-003", "", [], error="llm_unavailable"),
        # gs-004: [9] is invalid; one sentence gets an unreadable reply, one a failed call
        "gs-004": record(
            "gs-004",
            "Delta is four [1]. Epsilon is five [1].",
            [source(1, "2001.00002")],
            raw="Delta is four [1]. Epsilon is five [1][9].",
            citations=["2001.00002#0"],
        ),
        "gs-u01": record("gs-u01", "No evidence.", [], refused=True),
    }
    replies = {
        "Alpha is one [1].": SUPPORTED,
        "Beta is two [2].": SUPPORTED,
        "Gamma is three.": UNSUPPORTED,
        "Delta is four [1].": "I think it is supported",
        "Epsilon is five [1].": RuntimeError("boom"),
    }
    result, answers, judge, agent = run(
        tmp_path, records, replies, ["gs-001", "gs-002", "gs-003", "gs-004", "gs-u01"]
    )
    c = result["counts"]
    assert (c["answers"], c["errors"], c["refused_answerable"], c["judged_answers"]) == (5, 1, 1, 2)
    assert (c["supported"], c["not_supported"], c["not_checkable"], c["judge_error"]) == (
        2,
        1,
        1,
        2,
    )
    assert c["unanswerable_refused"] == 1 and c["unanswerable_answered_anyway"] == 0
    # refusals, errors and the unanswerable item never reach the judge
    assert len(judge.calls) == 6
    by_id = {r["id"]: r for r in result["per_answer"]}
    assert by_id["gs-001"]["faithfulness"] == pytest.approx(2 / 3)
    assert by_id["gs-001"]["cited_doc_recall"] == 1.0
    assert by_id["gs-004"]["faithfulness"] is None  # no checkable sentence: left out of the mean
    assert by_id["gs-004"]["cited_doc_recall"] == 0.5  # needs 2001.00002 and 2001.00004
    assert (by_id["gs-004"]["invalid_citations"], by_id["gs-004"]["citation_numbers"]) == (1, 3)
    assert result["metrics"]["faithfulness_macro"]["n"] == 1
    assert result["metrics"]["faithfulness_micro"] == pytest.approx(2 / 3)
    assert result["metrics"]["over_refusal_rate"] == pytest.approx(1 / 4)
    assert result["metrics"]["invalid_citation_rate"] == pytest.approx(1 / 5)
    assert result["judge"]["errors"] == {"unreadable": 1, "call:RuntimeError": 1}
    unreadable = [s for s in by_id["gs-004"]["sentences"] if s["judge_error"] == "unreadable reply"]
    assert unreadable[0]["reply"] == "I think it is supported" and unreadable[0]["label"] is None
    assert len(answers) == 5 and answers[0]["answer_id"] == "gs-001"


def test_run_file_records_judge_and_generator_settings(tmp_path):
    records = {
        "gs-001": record(
            "gs-001", "Alpha is one [1].", [source(1, "2001.00001")], citations=["2001.00001#0"]
        )
    }
    result, _, judge, _ = run(
        tmp_path,
        records,
        {"Alpha is one [1].": SUPPORTED},
        ["gs-001"],
        judge={
            "prompt_path": "p.md",
            "digest": "jd",
            "temperature": 0,
            "max_tokens": 150,
            "context_tokens": 10,
        },
    )
    j = result["judge"]
    assert (j["model"], j["digest"], j["temperature"], j["max_tokens"]) == (
        "judge-model",
        "jd",
        0,
        150,
    )
    assert j["prompt"] == PROMPT_INFO
    assert judge.calls[0][1:] == (0, 150)
    assert j["max_prompt_chars"] == len(judge.calls[0][0])
    assert j["prompt_fits_context"] is False  # context of 10 tokens is smaller than the prompt
    assert result["generator"]["model"] == "gen-model" and result["generator"]["digest"] == "gd"
    assert result["golden"]["sha256"] and result["golden"]["n_items"] == 1


def test_unanswerable_answered_anyway_is_listed_not_judged(tmp_path):
    records = {"gs-u01": record("gs-u01", "It is so [1].", [source(1, "2001.00001")])}
    result, _, judge, _ = run(tmp_path, records, {}, ["gs-u01"])
    assert result["answered_anyway"] == ["gs-u01"] and not judge.calls
    assert result["metrics"]["faithfulness_macro"] is None


def test_agent_gets_ids_questions_and_history(tmp_path):
    records = {"gs-001": record("gs-001", "", [], refused=True)}
    _, _, _, agent = run(tmp_path, records, {}, ["gs-001"])
    assert agent.batch == [{"id": "gs-001", "question": "Toy question one?", "history": []}]


def test_invalid_numbers_get_no_passage_and_no_citation_is_marked():
    sources = [source(1, "d1", "text one")]
    assert format_passages(sources, [1, 7]) == "[1] Title: T1\nText: text one"
    assert format_passages(sources, []) == "(no cited passage)"
    prompt = build_judge_prompt(TEMPLATE, "Q?", "S.", "P")
    assert "Q: Q?" in prompt and '{"label": "supported"' in prompt  # braces survive
    assert invalid_citations("A [1]. B [2][3].", 2) == (1, 3)


@pytest.mark.parametrize(
    "reply, expected",
    [
        ('{"label": "supported", "reason": "x"}', ("supported", "x")),
        ('```json\n{"label": "not supported", "reason": "y"}\n```', ("not supported", "y")),
        ('Sure: {"label": "not checkable"} done', ("not checkable", "")),
        ('{"label": "Supported"}', None),
        ('{"label": "maybe"}', None),
        ("supported", None),
        ("", None),
        ("[1, 2]", None),
    ],
)
def test_parse_judgement(reply, expected):
    assert parse_judgement(reply) == expected


def test_config_checks(tmp_path):
    def write(**overrides):
        cfg = config(tmp_path, **overrides)
        path = tmp_path / "c.yaml"
        path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
        return path

    assert load_answer_config(write())["agent"]["factory"] == "x:y"
    with pytest.raises(ValueError, match="max_tokens"):
        load_answer_config(write(judge={"prompt_path": "p", "digest": "d"}))
    with pytest.raises(ValueError, match="digest"):
        load_answer_config(write(judge={"prompt_path": "p", "max_tokens": 5}))
    with pytest.raises(ValueError, match="'limit'"):
        load_answer_config(write(limit=0))
    cfg = config(tmp_path, ids=["gs-999"])
    with pytest.raises(ValueError, match="gs-999"):
        select_items(cfg, load_golden(Path(cfg["golden_path"])))
    cfg = config(tmp_path, limit=2)
    assert [i.id for i in select_items(cfg, load_golden(Path(cfg["golden_path"])))] == [
        "gs-001",
        "gs-002",
    ]


def test_cli_writes_run_and_answers_files(tmp_path, monkeypatch):
    records = {
        "gs-001": record(
            "gs-001", "Alpha is one [1].", [source(1, "2001.00001")], citations=["2001.00001#0"]
        )
    }
    prompt = tmp_path / "judge.md"
    prompt.write_text(TEMPLATE, encoding="utf-8")
    cfg = config(tmp_path, ids=["gs-001"], agent={"factory": "test_eval_answer_run:build_fake"})
    cfg["judge"]["prompt_path"] = str(prompt)
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    monkeypatch.syspath_prepend(str(Path(__file__).parent))
    monkeypatch.setattr(
        "scitech_eval.answer_run.judge_from_env",
        lambda: FakeJudge({"Alpha is one [1].": SUPPORTED}),
    )
    monkeypatch.setattr(
        __import__(__name__), "build_fake", lambda: FakeAgent(records), raising=False
    )
    out = tmp_path / "runs"
    assert main(["answers", "--config", str(path), "--out-dir", str(out)]) == 0
    run_file = next(out.glob("*-t.json"))
    data = json.loads(run_file.read_text(encoding="utf-8"))
    assert data["kind"] == "answers" and data["counts"]["supported"] == 1
    assert data["traces_path"].endswith(".traces.jsonl")
    # the run, answers and traces files share one prefix (evaluation/AGENTS.md)
    prefix = run_file.name.removesuffix("-t.json")
    assert Path(data["traces_path"]).name == f"{prefix}-t.traces.jsonl"
    assert next(out.glob("*.answers.jsonl")).name == f"{prefix}-t.answers.jsonl"
    assert data["judge"]["prompt"]["sha256"]
    # the answers file is what `make-sheet` reads
    answers_file = next(out.glob("*.answers.jsonl"))
    assert main(["make-sheet", str(answers_file), "--out-dir", str(tmp_path / "sheet")]) == 0


def test_real_agent_records(tmp_path):
    """`BatchResult.to_dict()` of the real agent has what the runner reads."""
    from scitech_agent.agent import Agent
    from scitech_agent.llm import FakeLLM
    from scitech_agent.retrieval import InMemoryRetriever, ScoredChunk

    chunk = ScoredChunk(
        "2001.00001#0", "2001.00001", 0.0, "T", "T. Alpha is one.", source="arxiv", chunk_index=0
    )
    agent = Agent(InMemoryRetriever([chunk]), FakeLLM(["Alpha is one [1].", '["More?"]']))
    cfg = config(tmp_path, ids=["gs-001"])
    items = select_items(cfg, load_golden(Path(cfg["golden_path"])))
    judge = FakeJudge({"Alpha is one [1]. ": SUPPORTED}, default=SUPPORTED)
    result, answers = run_answers(cfg, items, agent, judge, TEMPLATE, PROMPT_INFO)
    assert result["counts"]["supported"] == 1 and result["counts"]["errors"] == 0
    assert result["per_answer"][0]["cited_doc_recall"] == 1.0
    assert answers[0]["sources"][0]["doc_id"] == "2001.00001"


def test_agent_is_warmed_up_before_the_batch(tmp_path):
    records = {"gs-001": record("gs-001", "", [], refused=True)}
    result, _, _, agent = run(tmp_path, records, {}, ["gs-001"])
    assert agent.events == ["warm_up", "run_batch"]
    assert "warm_up_seconds" in result["timings"]


def test_half_refusal_is_judged_like_an_answer(tmp_path):
    """Fixed refusal sentence, then an answer, `insufficient_evidence` false (gs-002, #139)."""
    refusal = "The sources do not contain enough evidence to answer this question."
    records = {
        "gs-001": record(
            "gs-001",
            f"{refusal} Alpha is one [1].",
            [source(1, "2001.00001")],
            citations=["2001.00001#0"],
        )
    }
    replies = {refusal: UNSUPPORTED, "Alpha is one [1].": SUPPORTED}  # the judge is not asked
    result, _, judge, _ = run(tmp_path, records, replies, ["gs-001"])
    assert result["counts"]["refused_answerable"] == 0 and len(judge.calls) == 1
    assert result["per_answer"][0]["faithfulness"] == 1.0
    first = result["per_answer"][0]["sentences"][0]
    assert first["label"] == "not checkable" and "rule 4" in first["reason"]
    assert (
        result["counts"]["not_checkable"] == 1 and result["judge"]["fixed_refusal_sentences"] == 1
    )


def test_fixed_refusal_sentence_is_the_one_in_the_agent_prompt():
    prompt = (REPO / "agent" / "prompts" / "answer.md").read_text(encoding="utf-8")
    assert f'"{REFUSAL_SENTENCE}"' in prompt


def test_marker_only_piece_is_attached_to_the_sentence_before(tmp_path):
    assert sentences_for_judge("Delta is four. [4]") == ["Delta is four. [4]"]
    assert sentences_for_judge("Delta is four [1].\n[4]\nEpsilon is five.") == [
        "Delta is four [1]. [4]",
        "Epsilon is five.",
    ]
    assert sentences_for_judge("[2]") == ["[2]"]  # nothing before it: left as it is
    assert sentences_for_judge("A [1]. B.") == ["A [1].", "B."]
    records = {
        "gs-001": record(
            "gs-001",
            "Delta is four [1].\n[4]",
            [source(1, "2001.00001")],
            citations=["2001.00001#0"],
        )
    }
    result, _, judge, _ = run(tmp_path, records, {"Delta is four [1]. [4]": SUPPORTED}, ["gs-001"])
    assert len(judge.calls) == 1 and result["counts"]["sentences"] == 1
    assert result["counts"]["supported"] == 1


def test_traces_path_off_written_unquoted_in_yaml_switches_traces_off(tmp_path):
    # YAML reads `off` as the boolean False; it must not fall back to the default trace file.
    unquoted = yaml.safe_load("name: t\ntraces_path: off\n")
    quoted = yaml.safe_load('name: t\ntraces_path: "off"\n')
    assert unquoted["traces_path"] is False
    assert traces_target(unquoted, tmp_path, "S") == "off"
    assert traces_target(quoted, tmp_path, "S") == "off"


def test_traces_path_default_and_explicit(tmp_path):
    default = str(tmp_path / "S-t.traces.jsonl")
    assert traces_target({"name": "t"}, tmp_path, "S") == default
    assert traces_target({"name": "t", "traces_path": None}, tmp_path, "S") == default
    assert traces_target({"name": "t", "traces_path": ""}, tmp_path, "S") == default
    assert traces_target({"name": "t", "traces_path": "x/y.jsonl"}, tmp_path, "S") == "x/y.jsonl"
