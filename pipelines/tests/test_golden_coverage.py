import importlib.util
import json
from pathlib import Path

import pytest

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "golden_coverage.py"
spec = importlib.util.spec_from_file_location("golden_coverage", SCRIPT)
golden_coverage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(golden_coverage)

INDEXED = ["2301.00001", "2301.00001", "2301.00002", "2301.00003", "2301.00009"]


def write_golden(path: Path) -> Path:
    items = [
        {"id": "gs-001", "relevant_doc_ids": ["2301.00001"]},
        {"id": "gs-002", "relevant_doc_ids": ["2301.00002", "2301.00004"]},
        {"id": "gs-u01", "relevant_doc_ids": []},
        {"id": "gs-003", "relevant_doc_ids": ["2301.00005", "2301.00003"]},
    ]
    path.write_text("\n".join(json.dumps(i) for i in items) + "\n", encoding="utf-8")
    return path


def write_chunks(folder: Path) -> Path:
    folder.mkdir()
    chunk_ids = [f"{d}#{i}" for i, d in enumerate(INDEXED)]
    pq.write_table(pa.table({"chunk_id": chunk_ids, "doc_id": INDEXED}), folder / "chunks.parquet")
    return folder


class FakeQdrant:
    """Scroll endpoint over points with a doc_id payload; pages of `limit` points."""

    def __init__(self, doc_ids: list[str]):
        self.points = [{"id": n, "payload": {"doc_id": d}} for n, d in enumerate(doc_ids)]
        self.requests: list[tuple[str, dict]] = []

    def __call__(self, url: str, body: dict) -> dict:
        self.requests.append((url, body))
        assert body["with_vector"] is False and body["with_payload"] == ["doc_id"]
        wanted = set(body["filter"]["must"][0]["match"]["any"])
        matching = [p for p in self.points if p["payload"]["doc_id"] in wanted]
        start = body.get("offset", 0)
        page = matching[start : start + body["limit"]]
        following = start + body["limit"]
        return {
            "result": {
                "points": page,
                "next_page_offset": following if following < len(matching) else None,
            }
        }


def test_missing_by_item_keeps_only_items_with_missing_ids():
    wanted = {"a:gs-001": ["x"], "a:gs-002": ["x", "y"], "a:gs-u01": []}
    assert golden_coverage.missing_by_item(wanted, {"x"}) == {"a:gs-002": ["y"]}
    assert golden_coverage.missing_by_item(wanted, {"x", "y"}) == {}


def test_chunk_doc_ids(tmp_path):
    chunks = write_chunks(tmp_path / "chunks")
    wanted = ["2301.00001", "2301.00004", "2301.00009"]
    assert golden_coverage.chunk_doc_ids(chunks, wanted) == {"2301.00001", "2301.00009"}
    assert golden_coverage.chunk_doc_ids(chunks / "chunks.parquet", wanted) == {
        "2301.00001",
        "2301.00009",
    }
    with pytest.raises(FileNotFoundError, match="run `chunk` first"):
        golden_coverage.chunk_doc_ids(tmp_path / "nothing", wanted)


def test_qdrant_doc_ids_batches_ids_and_follows_pages():
    qdrant = FakeQdrant(INDEXED)
    wanted = ["2301.00001", "2301.00002", "2301.00003", "2301.00004", "2301.00005"]
    found = golden_coverage.qdrant_doc_ids(
        "http://localhost:6333/", "chunks", wanted, post=qdrant, id_batch=2, page_size=1
    )
    assert found == {"2301.00001", "2301.00002", "2301.00003"}
    urls = {url for url, _ in qdrant.requests}
    assert urls == {"http://localhost:6333/collections/chunks/points/scroll"}
    batches = [tuple(body["filter"]["must"][0]["match"]["any"]) for _, body in qdrant.requests]
    # ids 1-2: three points, one per page; ids 3-4: one point; id 5: no point
    assert batches == [("2301.00001", "2301.00002")] * 3 + [("2301.00003", "2301.00004")] + [
        ("2301.00005",)
    ]


def test_command_line_with_chunks_lists_missing_ids_per_item(tmp_path, capsys):
    golden = write_golden(tmp_path / "golden.jsonl")
    chunks = write_chunks(tmp_path / "chunks")
    code = golden_coverage.main(["--golden", str(golden), "--chunks", str(chunks)])
    out = capsys.readouterr().out
    assert code == 1
    assert "golden-coverage: " in out and "(5 ids)" in out
    assert "FAIL  chunks" in out and "2 of 5 ids missing in 2 items" in out
    assert "golden.jsonl:gs-002: 2301.00004" in out
    assert "golden.jsonl:gs-003: 2301.00005" in out
    assert "gs-001" not in out and "gs-u01" not in out


def test_command_line_with_qdrant_passes_when_everything_is_loaded(tmp_path, capsys, monkeypatch):
    golden = tmp_path / "golden.jsonl"
    golden.write_text(json.dumps({"id": "gs-001", "relevant_doc_ids": ["2301.00002"]}) + "\n")
    qdrant = FakeQdrant(INDEXED)
    monkeypatch.setattr(golden_coverage, "http_post", qdrant)
    monkeypatch.setenv("QDRANT_COLLECTION", "chunks")
    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")
    code = golden_coverage.main(["--golden", str(golden), "--qdrant"])
    out = capsys.readouterr().out
    assert code == 0
    assert "PASS  Qdrant chunks: 1 ids in 1 items, all found" in out
    assert "golden-coverage: all ids found" in out
    assert qdrant.requests[0][0] == "http://qdrant:6333/collections/chunks/points/scroll"


def test_command_line_needs_a_source(tmp_path):
    with pytest.raises(SystemExit):
        golden_coverage.main(["--golden", str(tmp_path / "g.jsonl")])
    with pytest.raises(SystemExit):
        golden_coverage.main(
            ["--golden", str(tmp_path / "g.jsonl"), "--qdrant", "--collection", ""]
        )
