"""Tests of the BM25 reload (W7-D7-DAT-1, ADR 0011): fake clock, two tiny indexes."""

from __future__ import annotations

import logging
import shutil
import threading
from pathlib import Path

import pytest

from scitech_agent.retrieval.hybrid import HybridRetriever, retriever_from_env
from scitech_agent.retrieval.keyword import (
    MANIFEST,
    BM25Index,
    KeywordRetriever,
    ReloadingKeywordRetriever,
    bm25_reload_seconds,
    index_chunks,
    keyword_retriever,
)


def chunk(doc: str, text: str) -> dict:
    return {
        "chunk_id": f"{doc}#0",
        "doc_id": doc,
        "source": "arxiv",
        "title": text.split(".")[0],
        "text": text,
        "chunk_index": 0,
        "authors": ["A. Author"],
        "categories": ["cs.CL"],
        "published_at": "2026-11-02",
        "url": f"https://arxiv.org/abs/{doc}",
        "license": "CC0-1.0",
    }


OLD = [chunk("old-1", "Dense retrieval. Dual encoders for passages."), chunk("old-2", "Parsing.")]
NEW = OLD + [chunk("new-1", "Speculative decoding. Draft tokens verified by a target model.")]


def save(chunks: list[dict], path: Path, built_at: str) -> None:
    index = index_chunks(chunks)
    index.manifest["built_at"] = built_at
    index.save(path)


def switch(chunks: list[dict], live: Path, built_at: str) -> None:
    """The two renames of `scitech_pipelines.bm25_live.switch_dir`."""
    new = live.with_name(live.name + ".next")
    save(chunks, new, built_at)
    old = live.with_name(live.name + ".old")
    live.rename(old)
    new.rename(live)
    shutil.rmtree(old)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def live(tmp_path: Path) -> Path:
    path = tmp_path / "bm25-live"
    save(OLD, path, "2026-11-02T08:00:00+00:00")
    return path


def docs(retriever, query: str = "speculative decoding draft tokens") -> list[str]:
    return [hit.doc_id for hit in retriever.search(query, 5)]


def test_zero_or_empty_means_off_and_loads_once(live: Path) -> None:
    assert bm25_reload_seconds({}) == 0
    assert bm25_reload_seconds({"BM25_RELOAD_SECONDS": ""}) == 0
    assert bm25_reload_seconds({"BM25_RELOAD_SECONDS": "0"}) == 0
    retriever = keyword_retriever(live, {"BM25_RELOAD_SECONDS": "0"})
    assert type(retriever) is KeywordRetriever  # the frozen behaviour, nothing watched


def test_negative_value_is_refused() -> None:
    with pytest.raises(ValueError, match="BM25_RELOAD_SECONDS"):
        bm25_reload_seconds({"BM25_RELOAD_SECONDS": "-5"})


def test_positive_value_gives_the_reloading_retriever(live: Path) -> None:
    retriever = keyword_retriever(live, {"BM25_RELOAD_SECONDS": "60"})
    assert isinstance(retriever, ReloadingKeywordRetriever)
    assert retriever.reload_seconds == 60


def test_new_index_is_used_after_the_interval_not_before(live: Path) -> None:
    clock = Clock()
    retriever = ReloadingKeywordRetriever(live, 60, clock=clock)
    assert "new-1" not in docs(retriever)

    switch(NEW, live, "2026-11-02T10:00:00+00:00")
    clock.now += 59
    assert "new-1" not in docs(retriever)  # still inside the interval
    clock.now += 1
    assert docs(retriever)[0] == "new-1"
    assert len(retriever.index) == 3


def test_unchanged_manifest_does_not_reload(live: Path) -> None:
    clock = Clock()
    loads: list[Path] = []

    def loader(path: Path) -> BM25Index:
        loads.append(path)
        return BM25Index.load(path)

    retriever = ReloadingKeywordRetriever(live, 60, clock=clock, loader=loader)
    for _ in range(3):
        clock.now += 61
        assert retriever.maybe_reload() is False
    assert len(loads) == 1  # only the first load


def test_search_in_flight_finishes_on_the_old_index(live: Path) -> None:
    clock = Clock()
    retriever = ReloadingKeywordRetriever(live, 60, clock=clock)
    started, release = threading.Event(), threading.Event()
    old = retriever._current
    seen: list[list[str]] = []

    class Slow:
        index = old.index

        def search(self, query, k, filters=None):
            started.set()
            release.wait(5)
            return old.search(query, k, filters)

    retriever._current = Slow()  # type: ignore[assignment]
    worker = threading.Thread(target=lambda: seen.append(docs(retriever)))
    worker.start()
    assert started.wait(5)

    switch(NEW, live, "2026-11-02T10:00:00+00:00")
    clock.now += 60
    assert docs(retriever)[0] == "new-1"  # a new request already gets the new index
    release.set()
    worker.join(5)
    assert len(seen) == 1 and "new-1" not in seen[0]  # the old index, to the end


def test_broken_new_index_is_logged_and_the_old_one_kept(
    live: Path, caplog: pytest.LogCaptureFixture
) -> None:
    clock = Clock()
    retriever = ReloadingKeywordRetriever(live, 60, clock=clock)
    (live / MANIFEST).write_text('{"built_at": "broken", "params": {}}', encoding="utf-8")
    (live / "postings.npz").write_bytes(b"not an index")
    clock.now += 60
    with caplog.at_level(logging.ERROR):
        assert retriever.maybe_reload() is False
        assert len(retriever.index) == 2
    assert "failed to load" in caplog.text
    assert "old-1" in docs(retriever, "dense retrieval")

    switch(NEW, live, "2026-11-02T12:00:00+00:00")  # the next good build is picked up
    clock.now += 60
    assert retriever.maybe_reload() is True
    assert len(retriever.index) == 3


def test_missing_directory_between_the_renames_keeps_the_old_index(
    live: Path, caplog: pytest.LogCaptureFixture
) -> None:
    clock = Clock()
    retriever = ReloadingKeywordRetriever(live, 60, clock=clock)
    live.rename(live.with_name("moved"))
    clock.now += 60
    with caplog.at_level(logging.WARNING):
        assert docs(retriever, "dense retrieval")[0] == "old-1"
    assert "keeping the old index" in caplog.text


def test_broken_index_at_start_fails_the_build(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ReloadingKeywordRetriever(tmp_path / "missing", 60)


def test_hybrid_from_env_wraps_the_keyword_half(live: Path, monkeypatch) -> None:
    from scitech_agent.retrieval import dense

    monkeypatch.setattr(dense.DenseRetriever, "from_env", classmethod(lambda cls, env: object()))
    env = {"BM25_INDEX_DIR": str(live), "BM25_RELOAD_SECONDS": "30"}
    retriever = retriever_from_env(env)
    assert isinstance(retriever, HybridRetriever)
    assert isinstance(retriever.keyword, ReloadingKeywordRetriever)
    env["BM25_RELOAD_SECONDS"] = ""
    assert type(retriever_from_env(env).keyword) is KeywordRetriever
