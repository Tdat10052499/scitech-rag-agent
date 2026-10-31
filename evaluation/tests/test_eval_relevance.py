"""Tests of `python -m scitech_eval relevance` with a scripted judge (nothing talks to a model)."""

import json
from pathlib import Path

import pytest
import yaml

from scitech_eval.__main__ import main
from scitech_eval.golden import GoldenItem
from scitech_eval.relevance import (
    build_relevance_prompt,
    history_text,
    is_empty_answer,
    load_relevance_config,
    output_path,
    parse_rating,
    rateable,
    run_relevance,
)

REPO = Path(__file__).resolve().parents[2]
PROMPT = REPO / "evaluation" / "prompts" / "relevance-judge.md"
DATA = Path(__file__).parent / "data"
PROMPT_INFO = {"path": "p.md", "sha256": "abc", "commit": "def"}


def item(item_id, type_="factual", history=None, question=None):
    return GoldenItem(
        id=item_id,
        question=question or f"Question of {item_id}?",
        type=type_,
        relevant_doc_ids=() if type_ == "unanswerable" else ("2001.00001",),
        reference_answer=f"Reference of {item_id}.",
        notes="plain.",
        author="LDN",
        split="dev",
        history=history,
    )


def golden():
    turns = (
        {"role": "user", "content": "What is RAG?"},
        {"role": "assistant", "content": "Retrieval-augmented generation."},
    )
    items = [
        item("gs-001"),
        item("gs-002", "follow_up", history=turns, question="And why does it help?"),
        item("gs-003"),
        item("gs-004"),
        item("gs-005"),
        item("gs-u01", "unanswerable"),
    ]
    return {i.id: i for i in items}


def answer(item_id, text, *, error=None, refused=False):
    return {
        "answer_id": item_id,
        "question": f"Question of {item_id}?",
        "answer": text,
        "sources": [{"n": 1, "chunk_id": "c#0", "doc_id": "d", "title": "T", "text": "t"}],
        "error": error,
        "insufficient_evidence": refused,
    }


def write_answers(tmp_path, records, name="x.answers.jsonl"):
    path = tmp_path / name
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


class FakeJudge:
    """Replies by the answer text found in the prompt; unknown answers get `default`."""

    model = "judge-model"

    def __init__(self, replies=None, default='{"rating": 3, "reason": "ok"}'):
        self.replies, self.default, self.calls = replies or {}, default, []

    def chat(self, messages, temperature, max_tokens):
        prompt = messages[0]["content"]
        self.calls.append((prompt, temperature, max_tokens))
        text = prompt.split("Answer to rate:\n")[1].split("\n\nRules:")[0]
        reply = self.replies.get(text, self.default)
        if isinstance(reply, Exception):
            raise reply
        return reply


def config(tmp_path):
    gold = tmp_path / "golden.jsonl"
    gold.write_text("{}\n", encoding="utf-8")
    return {
        "name": "rel",
        "golden_path": str(gold),
        "judge": {"prompt_path": str(PROMPT), "digest": "jd", "temperature": 0, "max_tokens": 200},
        "bootstrap": {"resamples": 50, "seed": 0},
    }


TEMPLATE = PROMPT.read_text(encoding="utf-8")


def test_prompt_template_has_each_placeholder_once_and_the_reply_format():
    for name in ("{question}", "{history}", "{reference_answer}", "{answer}"):
        assert TEMPLATE.count(name) == 1, name
    assert '"rating": 1 | 2 | 3' in TEMPLATE
    # nothing else in braces that build_relevance_prompt would not fill
    filled = build_relevance_prompt(TEMPLATE, item("gs-001"), "An answer.")
    assert "{question}" not in filled and "{answer}" not in filled
    assert "Question of gs-001?" in filled and "Reference of gs-001." in filled
    assert filled.count("An answer.") == 1
    assert "Earlier turns of the conversation" in filled and "(none)" in filled


def test_prompt_states_the_three_levels_of_plan_4_2():
    assert "Rating 3, fully" in TEMPLATE
    assert "Rating 2, partly" in TEMPLATE and "infer the answer" in TEMPLATE
    assert "Rating 1, not at all" in TEMPLATE and "only citation markers" in TEMPLATE
    assert "Do not judge whether it is correct" in TEMPLATE


def test_history_of_a_follow_up_is_in_the_prompt():
    g = golden()
    assert history_text(g["gs-001"]) == "(none)"
    assert history_text(g["gs-002"]) == (
        "user: What is RAG?\nassistant: Retrieval-augmented generation."
    )
    prompt = build_relevance_prompt(TEMPLATE, g["gs-002"], "Because it adds evidence.")
    assert "user: What is RAG?" in prompt and "And why does it help?" in prompt


def test_prompt_keeps_braces_and_dollar_signs_in_the_answer():
    prompt = build_relevance_prompt(TEMPLATE, item("gs-001"), 'Use {"a": 1} and {question} $1')
    assert 'Use {"a": 1} and {question} $1' in prompt


def test_parse_rating_reads_json_in_fence_or_text_and_nothing_else():
    assert parse_rating('{"rating": 2, "reason": "one part missing"}') == (2, "one part missing")
    assert parse_rating('```json\n{"rating": 3, "reason": "full"}\n```') == (3, "full")
    assert parse_rating('Sure: {"rating": 1}') == (1, "")
    assert parse_rating('{"rating": 1, "reason": 5}') == (1, "")
    for bad in (
        '{"rating": 4}',
        '{"rating": 0}',
        '{"rating": "3"}',
        '{"rating": 2.5}',
        '{"rating": true}',
        '{"label": "supported"}',
        "3",
        "[3]",
        "",
        "not json",
    ):
        assert parse_rating(bad) is None, bad


def test_empty_answer_means_nothing_left_after_markers_and_punctuation():
    for empty in ("", "  \n", "[1][2]", "[1] [2]", "[1, 2].", " [3]\n[4] "):
        assert is_empty_answer(empty), empty
    for text in ("Yes [1].", "x[1]", "[1] A word"):
        assert not is_empty_answer(text), text


def test_rateable_leaves_out_errors_refusals_and_unanswerable_items():
    g = golden()
    answers = [
        answer("gs-001", "a"),
        answer("gs-002", "b", error="timeout"),
        answer("gs-003", "c", refused=True),
        answer("gs-u01", "d"),
        answer("gs-004", "e"),
    ]
    kept, left_out = rateable(answers, g)
    assert [a["answer_id"] for a in kept] == ["gs-001", "gs-004"]
    assert left_out == {"error": 1, "refused": 1, "unanswerable_item": 1}
    with pytest.raises(ValueError, match="gs-999"):
        rateable([answer("gs-999", "x")], g)


def test_run_rates_each_answer_once_and_counts_everything(tmp_path):
    g = golden()
    path = write_answers(
        tmp_path,
        [
            answer("gs-001", "Full answer [1]."),
            answer("gs-002", "Half answer [1]."),
            answer("gs-003", "[1][2]"),
            answer("gs-004", "Something else [1]."),
            answer("gs-005", "Broken reply [1]."),
            answer("gs-u01", "Answered anyway."),
        ],
    )
    judge = FakeJudge(
        {
            "Half answer [1].": '{"rating": 2, "reason": "second part missing"}',
            "Something else [1].": '{"rating": 1, "reason": "other question"}',
            "Broken reply [1].": "I think it is fine",
        }
    )
    record = run_relevance(config(tmp_path), path, g, judge, TEMPLATE, PROMPT_INFO, stamp="S")
    rows = {r["id"]: r for r in record["per_answer"]}
    assert rows["gs-001"]["rating"] == 3 and rows["gs-002"]["rating"] == 2
    assert rows["gs-004"]["rating"] == 1 and rows["gs-002"]["reason"] == "second part missing"
    assert rows["gs-003"]["rating"] == 1 and "not sent to the judge" in rows["gs-003"]["reason"]
    assert rows["gs-005"]["rating"] is None and rows["gs-005"]["judge_error"] == "unreadable reply"
    assert rows["gs-005"]["reply"] == "I think it is fine"
    assert len(judge.calls) == 4  # gs-003 (only markers) and gs-u01 (unanswerable) are not sent
    assert record["counts"] == {
        "answers_in_file": 6,
        "left_out": {"error": 0, "refused": 0, "unanswerable_item": 1},
        "rateable": 5,
        "rated": 4,
        "judge_error": 1,
    }
    assert record["metrics"]["distribution"] == {"1": 2, "2": 1, "3": 1}
    assert record["metrics"]["relevance"]["n"] == 4
    assert record["metrics"]["relevance"]["mean"] == pytest.approx(7 / 4)
    assert record["judge"]["fixed_no_answer"] == 1
    assert record["judge"]["errors"] == {"unreadable": 1}
    assert record["judge"]["model"] == "judge-model" and record["judge"]["digest"] == "jd"
    assert record["judge"]["prompt"] == PROMPT_INFO and record["timestamp"] == "S"
    assert record["answers_file"]["name"] == "x.answers.jsonl"
    assert len(record["answers_file"]["sha256"]) == 64


def test_judge_gets_the_settings_and_never_sees_sources_or_ids(tmp_path):
    g = golden()
    records = [answer("gs-001", "Plain answer [1].")]
    records[0]["sources"][0]["text"] = "SECRET SOURCE TEXT"
    path = write_answers(tmp_path, records)
    judge = FakeJudge()
    run_relevance(config(tmp_path), path, g, judge, TEMPLATE, PROMPT_INFO)
    prompt, temperature, max_tokens = judge.calls[0]
    assert (temperature, max_tokens) == (0, 200)
    assert "SECRET SOURCE TEXT" not in prompt and "c#0" not in prompt
    assert "Reference of gs-001." in prompt


def test_call_failure_is_stored_and_the_run_goes_on(tmp_path):
    class Down(Exception):
        code = "timeout"

    g = golden()
    path = write_answers(tmp_path, [answer("gs-001", "A [1]."), answer("gs-003", "B [1].")])
    judge = FakeJudge({"A [1].": Down()})
    record = run_relevance(config(tmp_path), path, g, judge, TEMPLATE, PROMPT_INFO)
    rows = {r["id"]: r for r in record["per_answer"]}
    assert (
        rows["gs-001"]["rating"] is None and rows["gs-001"]["judge_error"] == "call failed: timeout"
    )
    assert rows["gs-003"]["rating"] == 3
    assert record["counts"]["judge_error"] == 1 and record["judge"]["errors"] == {"call:timeout": 1}


def test_no_rated_answers_gives_no_mean(tmp_path):
    g = golden()
    path = write_answers(tmp_path, [answer("gs-001", "x", refused=True)])
    record = run_relevance(config(tmp_path), path, g, FakeJudge(), TEMPLATE, PROMPT_INFO)
    assert record["metrics"]["relevance"] is None
    assert record["metrics"]["distribution"] == {"1": 0, "2": 0, "3": 0}


def test_prompt_fits_context_is_checked_only_when_context_is_known(tmp_path):
    g = golden()
    path = write_answers(tmp_path, [answer("gs-001", "x" * 400)])
    cfg = config(tmp_path)
    assert (
        run_relevance(cfg, path, g, FakeJudge(), TEMPLATE, PROMPT_INFO)["judge"][
            "prompt_fits_context"
        ]
        is None
    )
    cfg["judge"]["context_tokens"] = 4096
    assert (
        run_relevance(cfg, path, g, FakeJudge(), TEMPLATE, PROMPT_INFO)["judge"][
            "prompt_fits_context"
        ]
        is True
    )
    cfg["judge"]["context_tokens"] = 50
    assert (
        run_relevance(cfg, path, g, FakeJudge(), TEMPLATE, PROMPT_INFO)["judge"][
            "prompt_fits_context"
        ]
        is False
    )


def test_output_path_sits_next_to_the_answers_name(tmp_path):
    out = tmp_path / "out"
    name = "20261101T010203Z-answers-w7-a2-rewrite.answers.jsonl"
    assert (
        output_path({}, Path(name), out)
        == out / "20261101T010203Z-answers-w7-a2-rewrite.relevance.json"
    )
    assert output_path({}, Path("other.jsonl"), out) == out / "other.relevance.json"


def write_config(tmp_path, **judge_overrides):
    gold = tmp_path / "golden.jsonl"
    gold.write_text((DATA / "toy_golden.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    judge = {"prompt_path": str(PROMPT), "digest": "jd", "max_tokens": 200}
    judge.update(judge_overrides)
    path = tmp_path / "rel.yaml"
    path.write_text(
        yaml.safe_dump({"name": "rel", "golden_path": str(gold), "judge": judge}), encoding="utf-8"
    )
    return path


def test_config_needs_a_judge_with_prompt_digest_and_max_tokens(tmp_path):
    cfg = load_relevance_config(write_config(tmp_path))
    assert cfg["judge"]["temperature"] == 0.0 and cfg["bootstrap"] == {}
    for key in ("prompt_path", "digest", "max_tokens"):
        path = write_config(tmp_path, **{key: None})
        with pytest.raises(ValueError, match=key):
            load_relevance_config(path)
    with pytest.raises(ValueError, match="context_tokens"):
        load_relevance_config(write_config(tmp_path, context_tokens=0))
    bare = tmp_path / "bare.yaml"
    bare.write_text("name: x\ngolden_path: g\n", encoding="utf-8")
    with pytest.raises(ValueError, match="judge"):
        load_relevance_config(bare)


def test_the_shipped_config_loads_and_points_at_the_shipped_prompt():
    cfg = load_relevance_config(REPO / "evaluation" / "configs" / "relevance-w7.yaml")
    assert cfg["judge"]["prompt_path"] == "evaluation/prompts/relevance-judge.md"
    assert (REPO / cfg["judge"]["prompt_path"]).is_file()
    assert (REPO / cfg["golden_path"]).is_file()
    assert cfg["judge"]["digest"] == "845dbda0ea48"


def test_cli_writes_the_relevance_file_next_to_the_answers_name(tmp_path, monkeypatch, capsys):
    path = write_answers(
        tmp_path,
        [answer("gs-001", "Full [1]."), answer("gs-002", "Half [1]."), answer("gs-u01", "More.")],
        name="20261101T010203Z-answers-x.answers.jsonl",
    )
    judge = FakeJudge({"Half [1].": '{"rating": 2, "reason": "r"}'})
    monkeypatch.setattr("scitech_eval.relevance.judge_from_env", lambda: judge)
    cfg = write_config(tmp_path)
    out = tmp_path / "out"
    code = main(["relevance", "--config", str(cfg), "--answers", str(path), "--out-dir", str(out)])
    assert code == 0
    target = out / "20261101T010203Z-answers-x.relevance.json"
    record = json.loads(target.read_text(encoding="utf-8"))
    assert record["kind"] == "relevance" and record["counts"]["rated"] == 2
    assert record["counts"]["left_out"]["unanswerable_item"] == 1
    assert record["metrics"]["distribution"] == {"1": 0, "2": 1, "3": 1}
    printed = capsys.readouterr().out
    assert "relevance.json" in printed and "rated 1/2/3: 0/1/1" in printed
    assert "relevance (n=2) 2.500" in printed
    assert "http" not in target.read_text(encoding="utf-8")


def test_cli_reports_errors_and_returns_1(tmp_path, monkeypatch, capsys):
    path = write_answers(tmp_path, [answer("gs-001", "x")])
    cfg = write_config(tmp_path)
    out = str(tmp_path / "out")
    for var in ("JUDGE_BASE_URL", "JUDGE_API_KEY", "JUDGE_MODEL"):
        monkeypatch.delenv(var, raising=False)
    assert main(["relevance", "--config", str(cfg), "--answers", str(path), "--out-dir", out]) == 1
    assert "missing environment variable" in capsys.readouterr().err
    missing = str(tmp_path / "none.jsonl")
    monkeypatch.setattr("scitech_eval.relevance.judge_from_env", lambda: FakeJudge())
    assert main(["relevance", "--config", str(cfg), "--answers", missing, "--out-dir", out]) == 1
    unknown = write_answers(tmp_path, [answer("gs-999", "x")], name="u.answers.jsonl")
    assert (
        main(["relevance", "--config", str(cfg), "--answers", str(unknown), "--out-dir", out]) == 1
    )
    assert "gs-999" in capsys.readouterr().err
