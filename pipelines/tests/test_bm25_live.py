from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("pyarrow")

from scitech_pipelines.bm25_live import rebuild_bm25, switch_dir  # noqa: E402

quiet = {"log": lambda _: None}


class Source:
    """Payloads as a Qdrant scroll returns them: any order, only the asked fields."""

    collection = "live"

    def __init__(self, payloads: list[dict], fail: bool = False):
        self.payloads, self.fail = payloads, fail

    def scroll_payloads(self, fields):
        if self.fail:
            raise RuntimeError("Qdrant went away")
        return [{k: v for k, v in p.items() if k in fields} for p in self.payloads]


def chunk(doc_id: str, index: int, text: str) -> dict:
    return {
        "chunk_id": f"{doc_id}#{index}",
        "doc_id": doc_id,
        "source": "arxiv",
        "title": f"Paper {doc_id}",
        "text": text,
        "chunk_index": index,
        "published_at": "2026-10-16",
        "categories": ["cs.CL"],
        "embedding_model": "not indexed",
    }


def test_rebuild_indexes_the_collection_and_switches_it_in(tmp_path: Path):
    from scitech_agent.retrieval.keyword import BM25Index

    live = tmp_path / "bm25-live"
    rebuild_bm25(Source([chunk("b", 0, "old retrieval text")]), live, **quiet)
    source = Source(
        [
            chunk("b", 1, "dense passage retrieval with hard negatives"),
            chunk("a", 0, "speculative decoding for language models"),
            chunk("b", 0, "a second abstract window"),
        ]
    )
    manifest = rebuild_bm25(source, live, **quiet)

    index = BM25Index.load(live)
    assert [index.chunk(i, 0).chunk_id for i in range(len(index))] == ["a#0", "b#0", "b#1"]
    assert index.search("retrieval negatives", 1)[0].chunk_id == "b#1"
    assert index.search("old", 5) == []  # the replaced text is gone
    assert manifest["chunks"] == "qdrant:live" and manifest["counts"]["chunks"] == 3
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bm25-live"]  # no .next or .old left


def test_a_failed_build_leaves_the_live_index_in_use(tmp_path: Path):
    from scitech_agent.retrieval.keyword import BM25Index

    live = tmp_path / "bm25-live"
    rebuild_bm25(Source([chunk("a", 0, "speculative decoding")]), live, **quiet)
    with pytest.raises(RuntimeError, match="went away"):
        rebuild_bm25(Source([], fail=True), live, **quiet)
    with pytest.raises(ValueError, match="no chunks"):
        rebuild_bm25(Source([]), live, **quiet)
    assert BM25Index.load(live).search("decoding", 1)[0].chunk_id == "a#0"


def test_switch_dir_replaces_the_directory(tmp_path: Path):
    live, new = tmp_path / "live", tmp_path / "live.next"
    live.mkdir()
    (live / "x").write_text("old")
    new.mkdir()
    (new / "x").write_text("new")
    switch_dir(new, live)
    assert (live / "x").read_text() == "new"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["live"]
    switch_dir_first = tmp_path / "first.next"
    switch_dir_first.mkdir()
    switch_dir(switch_dir_first, tmp_path / "first")  # no live index yet
    assert (tmp_path / "first").is_dir()
