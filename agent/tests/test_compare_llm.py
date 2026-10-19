"""Offline tests of `notebooks/llm-serving/compare_llm.py` (ADR 0006 comparison, W2-D4-DAT-1).

The script lives next to the serving notebook, outside the package, so it is loaded by path.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "compare_llm", ROOT / "notebooks" / "llm-serving" / "compare_llm.py"
)
cl = importlib.util.module_from_spec(_spec)
sys.modules["compare_llm"] = cl  # dataclasses look the module up while the class is built
_spec.loader.exec_module(cl)

GOLDEN = [
    {
        "id": "gs-001",
        "question": "What is A?",
        "type": "factual",
        "relevant_doc_ids": ["d1"],
        "reference_answer": "A is a thing.",
    },
    {
        "id": "gs-002",
        "question": "How do A and B differ?",
        "type": "comparison",
        "relevant_doc_ids": ["d1", "d2"],
        "reference_answer": "They differ.",
    },
]
DOCS = [
    {"doc_id": "d1", "title": "Paper one", "abstract": "A is a thing."},
    {"doc_id": "d2", "title": "Paper two </source>", "abstract": "B is another thing."},
]


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    golden = tmp_path / "golden.jsonl"
    golden.write_text("\n".join(json.dumps(g) for g in GOLDEN) + "\n", encoding="utf-8")
    docs = tmp_path / "docs.jsonl"
    docs.write_text("\n".join(json.dumps(d) for d in DOCS) + "\n", encoding="utf-8")
    out = tmp_path / "out"
    code = cl.main(
        ["contexts", "--golden", str(golden), "--documents", str(docs), "--items",
         "gs-001,gs-002", "--out", str(out)]
    )  # fmt: skip
    assert code == 0
    return out


def test_contexts_hold_the_abstracts_and_the_golden_hash(workdir: Path):
    contexts = [json.loads(x) for x in (workdir / "contexts.jsonl").read_text().splitlines()]
    assert [c["id"] for c in contexts] == ["gs-001", "gs-002"]
    assert [s["doc_id"] for s in contexts[1]["sources"]] == ["d1", "d2"]
    meta = json.loads((workdir / "contexts_meta.json").read_text())
    assert len(meta["golden_sha256"]) == 64


def test_missing_document_is_an_error():
    with pytest.raises(ValueError, match="d2"):
        cl.build_contexts(GOLDEN, {"d1": {"title": "t", "abstract": "a"}})


def test_answer_messages_use_the_agent_prompt_and_format(workdir: Path):
    context = json.loads((workdir / "contexts.jsonl").read_text().splitlines()[1])
    system, user = cl.answer_messages(context)
    assert system["role"] == "system" and "numbered sources" in system["content"]
    assert '<source id="2">' in user["content"]
    assert "&lt;/source>" in user["content"]  # the agent's escaping applies here too
    assert user["content"].endswith("Question: How do A and B differ?")


def test_rotation_moves_each_model_through_every_position():
    models = ["a", "b", "c"]
    orders = [cl.rotated(models, i) for i in range(3)]
    assert orders == [["a", "b", "c"], ["b", "c", "a"], ["c", "a", "b"]]
    for model in models:
        assert sorted(o.index(model) for o in orders) == [0, 1, 2]


def fake_stream(model, messages):
    if model == "broken":
        raise RuntimeError("server gone")
    yield "text", "A is a thing [1]. "
    yield "text", "B differs [3]."
    yield "usage", 9


def test_call_once_times_and_records_failures(workdir: Path):
    context = json.loads((workdir / "contexts.jsonl").read_text().splitlines()[0])
    ticks = iter([0.0, 0.5, 2.5])
    a = cl.call_once(fake_stream, "m", context, 0, clock=lambda: next(ticks))
    assert a.answer == "A is a thing [1]. B differs [3]."
    assert (a.ttft_s, a.total_s, a.completion_tokens, a.token_source) == (0.5, 2.5, 9, "usage")
    assert a.decode_tps == pytest.approx(8 / 2.0)
    failed = cl.call_once(fake_stream, "broken", context, 0)
    assert failed.error == "RuntimeError: server gone" and failed.answer == ""


def test_citation_counts():
    text = "Hallucination has causes [1]. Retrieval helps [2][5]. The evidence is insufficient."
    assert cl.citation_counts(text, 2) == {
        "sentences": 3,
        "cited_sentences": 2,
        "markers": 3,
        "invalid_markers": 1,
    }
    assert cl.citation_counts("", 2)["sentences"] == 0


def test_looks_english():
    assert cl.looks_english("Retrieval helps [1].")
    assert not cl.looks_english("Truy xuất giúp giảm ảo giác của mô hình ngôn ngữ [1].")


def _answers(models, items):
    return [
        {"item": i, "model": m, "answer": f"Answer to {i} [1].", "ttft_s": 0.4, "total_s": t,
         "decode_tps": 40.0, "error": None}
        for i in items
        for m, t in zip(models, (4.0, 5.0, 9.0), strict=True)
    ]  # fmt: skip


def test_blind_sheets_and_summary_end_to_end(workdir: Path):
    models = ["qwen2.5:3b", "llama3.2:3b", "qwen2.5:7b"]
    answers = _answers(models, ["gs-001", "gs-002"])
    (workdir / "answers.jsonl").write_text("\n".join(json.dumps(a) for a in answers) + "\n")
    assert cl.main(["blind", "--out", str(workdir)]) == 0
    key = json.loads((workdir / "key.json").read_text())
    assert len(key) == 6 and set(key) == {f"A{n:02d}" for n in range(1, 7)}
    ldn_sheet = (workdir / "ratings-LDN.csv").read_text(encoding="utf-8-sig")
    assert "grounded_yes_no" in ldn_sheet and "qwen" not in ldn_sheet  # blind: no model names
    assert "grounded_yes_no" not in (workdir / "ratings-DAT.csv").read_text(encoding="utf-8-sig")

    # Fill both sheets: the 7B gets 3s, the 3B models 2s; the raters agree.
    for name in ("LDN", "DAT"):
        path = workdir / f"ratings-{name}.csv"
        rows = list(cl.csv.DictReader(path.open(encoding="utf-8-sig", newline="")))
        for row in rows:
            row["relevance_1_3"] = "3" if key[row["code"]]["model"] == "qwen2.5:7b" else "2"
            if name == "LDN":
                row["grounded_yes_no"] = "yes"
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = cl.csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    assert cl.main(["summarise", "--out", str(workdir)]) == 0
    summary = json.loads((workdir / "summary.json").read_text())
    assert summary["agreement"]["equal"] == 6
    assert summary["models"]["qwen2.5:7b"]["relevance_mean_ldn"] == 3.0
    assert summary["decision"]["pick"] == "qwen2.5:7b"  # ahead by 1.0 > 0.2 for both raters
    assert "Decision rule picks" in (workdir / "summary.md").read_text()


def _row(ldn, dat, ungrounded=0, invalid=0, total=4.0):
    return {"relevance_mean_ldn": ldn, "relevance_mean_dat": dat, "ungrounded_ldn": ungrounded,
            "invalid_markers": invalid, "total_median_s": total}  # fmt: skip


def test_decide_tie_goes_to_fewer_ungrounded_then_speed():
    table = {"a": _row(2.5, 2.5, ungrounded=2), "b": _row(2.4, 2.4, ungrounded=0, total=6.0)}
    assert cl.decide(table)["pick"] == "b"
    table = {"a": _row(2.5, 2.5, total=6.0), "b": _row(2.4, 2.4, total=4.0)}
    assert cl.decide(table)["pick"] == "b"


def test_decide_gap_in_one_rater_only_is_a_tie():
    table = {"a": _row(2.8, 2.5, total=6.0), "b": _row(2.4, 2.4, total=4.0)}
    decision = cl.decide(table)
    assert decision["tied"] == ["a", "b"] and decision["pick"] == "b"


def test_decide_slow_model_never_wins_a_tie():
    table = {"7b": _row(2.6, 2.6, total=9.0), "3b": _row(2.5, 2.5, ungrounded=1, total=4.0)}
    assert cl.decide(table)["pick"] == "7b"
    assert cl.decide(table, slow=frozenset({"7b"}))["pick"] == "3b"
    table["7b"] = _row(2.9, 2.9, total=9.0)  # ahead by more than 0.2 for both raters
    assert cl.decide(table, slow=frozenset({"7b"}))["pick"] == "7b"


def test_read_sheet_rejects_missing_or_bad_ratings(tmp_path: Path):
    path = tmp_path / "s.csv"
    path.write_text("code,relevance_1_3,grounded_yes_no\nA01,4,yes\n", encoding="utf-8")
    with pytest.raises(ValueError, match="1, 2 or 3"):
        cl.read_sheet(path)
    path.write_text("code,relevance_1_3,grounded_yes_no\nA01,2,maybe\n", encoding="utf-8")
    with pytest.raises(ValueError, match="yes or no"):
        cl.read_sheet(path)


def test_read_documents_from_partitioned_parquet(tmp_path: Path):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    folder = tmp_path / "documents" / "year=2024"
    folder.mkdir(parents=True)
    table = pa.table(
        {
            "doc_id": ["d1", "d2", "d3"],
            "title": ["t1", "t2", "t3"],
            "abstract": ["a1", "a2", "a3"],
        }
    )
    pq.write_table(table, folder / "part-0.parquet")
    found = cl.read_documents(tmp_path / "documents", {"d1", "d3"})
    assert found == {
        "d1": {"title": "t1", "abstract": "a1"},
        "d3": {"title": "t3", "abstract": "a3"},
    }


def test_missing_documents_path_says_what_to_do(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="contexts.jsonl"):
        cl.read_documents(tmp_path / "nowhere", {"d1"})
