import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "retrieval_misses.py"
spec = importlib.util.spec_from_file_location("retrieval_misses", SCRIPT)
retrieval_misses = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retrieval_misses)


def hits(*doc_ids: str) -> list[dict]:
    return [{"chunk_id": f"{d}#0", "doc_id": d} for d in doc_ids]


def question(qid: str, relevant: list[str], retrieved: list[str], **extra) -> dict:
    return {
        "id": qid,
        "type": extra.pop("type", "factual"),
        "query": extra.pop("query", f"query {qid}"),
        "relevant_doc_ids": relevant,
        "retrieved": hits(*retrieved),
        **extra,
    }


def write_run(path: Path, retriever: str, questions: list[dict]) -> Path:
    path.write_text(json.dumps({"retriever_type": retriever, "per_question": questions}))
    return path


def write_golden(path: Path) -> Path:
    items = [
        {"id": "gs-001", "question": "Q one?", "relevant_doc_ids": ["a"]},
        {"id": "gs-002", "question": "Q two?", "relevant_doc_ids": ["b", "c"]},
        {
            "id": "gs-003",
            "question": "Q three?",
            "relevant_doc_ids": ["d"],
            "standalone_query": "Standalone three?",
        },
        {"id": "gs-u01", "question": "Q none?", "relevant_doc_ids": []},
    ]
    path.write_text("\n".join(json.dumps(i) for i in items) + "\n", encoding="utf-8")
    return path


def runs(tmp_path: Path) -> list[Path]:
    dense = [
        question("gs-001", ["a"], ["a", "x"]),
        question("gs-002", ["b", "c"], ["b", "x", "y", "z", "w", "c"]),
        question("gs-003", ["d"], ["x", "y"]),
        question("gs-u01", [], ["x"]),
    ]
    bm25 = [
        question("gs-001", ["a"], ["a"]),
        question("gs-002", ["b", "c"], ["c", "b"]),
        question("gs-003", ["d"], ["y", "d"]),
        question("gs-u01", [], ["x"]),
    ]
    return [
        write_run(tmp_path / "dense.json", "dense", dense),
        write_run(tmp_path / "bm25.json", "bm25", bm25),
    ]


def test_ranks_count_documents_not_chunks():
    retrieved = [{"doc_id": "x"}, {"doc_id": "x"}, {"doc_id": "a"}]
    assert retrieval_misses.ranks(retrieved, ["a", "b"]) == {"a": 2, "b": None}


def test_misses_lists_questions_some_run_missed(tmp_path):
    loaded = [(p.stem, retrieval_misses.load_run(p)) for p in runs(tmp_path)]
    found = retrieval_misses.misses(loaded, k=5)
    assert [m["id"] for m in found] == ["gs-002", "gs-003"]
    by_id = {m["id"]: m for m in found}
    assert by_id["gs-002"]["missed_by"] == ["dense"]  # c at rank 6 > k
    assert by_id["gs-002"]["runs"]["dense"]["ranks"] == {"b": 1, "c": 6}
    assert by_id["gs-003"]["missed_by"] == ["dense"]
    assert by_id["gs-003"]["runs"]["bm25"]["ranks"] == {"d": 2}


def test_main_writes_markdown_and_csv(tmp_path):
    golden = write_golden(tmp_path / "golden.jsonl")
    out, sheet = tmp_path / "out" / "misses.md", tmp_path / "out" / "misses.csv"
    paths = [str(p) for p in runs(tmp_path)]
    code = retrieval_misses.main(
        [*paths, "--golden", str(golden), "--k", "1", "--out", str(out), "--csv", str(sheet)]
    )
    assert code == 0
    text = out.read_text(encoding="utf-8")
    assert "Answerable questions: 3; missed by at least one run: 2." in text
    assert "| dense | 2 |" in text and "| bm25 | 2 |" in text
    assert "- Standalone query: Standalone three?" in text
    assert "  - d (rank: dense -, bm25 2)" in text
    assert sheet.read_text(encoding="utf-8").splitlines()[0] == "id,type,missed_by,category,note"


def test_titles_come_from_the_chunks(tmp_path):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    folder = tmp_path / "chunks"
    folder.mkdir()
    pq.write_table(
        pa.table({"doc_id": ["d", "y"], "title": ["Paper D", "Paper Y"]}),
        folder / "chunks.parquet",
    )
    assert retrieval_misses.doc_titles(folder, {"d", "z"}) == {"d": "Paper D"}


def test_a_file_without_per_question_is_refused(tmp_path):
    path = tmp_path / "x.json"
    path.write_text(json.dumps({"kind": "answers"}))
    with pytest.raises(ValueError, match="per_question"):
        retrieval_misses.load_run(path)
