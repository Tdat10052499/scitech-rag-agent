import json
from datetime import date
from pathlib import Path

import pytest

from scitech_pipelines.chunk import chunk_documents
from scitech_pipelines.embed import embed_chunks
from scitech_pipelines.incremental_run import (
    STATE_FILE,
    Steps,
    default_steps,
    read_watermark,
    replace_documents,
    run_incremental,
)
from scitech_pipelines.load import load_index, point_id

duckdb = pytest.importorskip("duckdb")
pytest.importorskip("numpy")
pytest.importorskip("pyarrow")

from test_chunk import doc, fixture_documents, write_documents  # noqa: E402
from test_embed import FakeEncoder  # noqa: E402
from test_load import FakeStore  # noqa: E402

TODAY = date(2026, 10, 20)  # so "yesterday" is 2026-10-19
SNAPSHOT_DAY = date(2026, 10, 10)
MAX_WORDS, OVERLAP = 60, 10  # small windows, so fixture abstracts have several chunks
quiet = {"log": lambda _: None}


class ReplaceStore(FakeStore):
    """FakeStore plus deleting by doc_id, like a Qdrant delete with a `doc_id` filter."""

    def __init__(self, *args, fail_on_delete: int = -1, **kwargs):
        super().__init__(*args, **kwargs)
        self.deletes = 0
        self.fail_on_delete = fail_on_delete

    def delete_doc_ids(self, doc_ids) -> None:
        if self.deletes == self.fail_on_delete:
            raise ConnectionError("Qdrant went away")
        self.deletes += 1
        wanted = set(doc_ids)
        for pid in [p for p, (_, payload) in self.points.items() if payload["doc_id"] in wanted]:
            del self.points[pid]


def chunk_ids_of(store: FakeStore, doc_id: str) -> list[str]:
    return sorted(pl["chunk_id"] for _, pl in store.points.values() if pl["doc_id"] == doc_id)


def build(tmp_path: Path, name: str, docs: list[dict]) -> tuple[Path, Path]:
    """Documents -> chunks -> vectors with the real steps and the fake encoder."""
    documents = write_documents(tmp_path / name / "documents", docs)
    chunks, vectors = tmp_path / name / "chunks", tmp_path / name / "embeddings"
    chunk_documents(documents, chunks, max_words=MAX_WORDS, overlap_words=OVERLAP, **quiet)
    embed_chunks(chunks, vectors, FakeEncoder(), part_size=4, **quiet)
    return chunks, vectors


@pytest.fixture
def bulk(tmp_path: Path) -> ReplaceStore:
    """A store holding the bulk index of the 20 fixture papers."""
    chunks, vectors = build(tmp_path, "bulk", fixture_documents())
    store = ReplaceStore()
    load_index(chunks, vectors, store, tmp_path / "bulk" / "index", **quiet)
    return store


# --- replace_documents: papers already in the index --------------------------------------------


def test_already_present_paper_replaces_all_its_old_chunks(bulk: ReplaceStore, tmp_path: Path):
    docs = fixture_documents()
    old = docs[0]
    old_chunks = chunk_ids_of(bulk, old["doc_id"])
    assert len(old_chunks) > 1  # the new version must drop chunks, not only rewrite them
    before = bulk.count()
    new_version = {
        **old,
        "abstract": "A much shorter abstract of the new version.",
        "updated_at": "2026-10-16",
    }
    new_paper = {
        **doc("2610.00001", words=30),
        "published_at": "2026-10-16",
        "updated_at": None,
        "year": 2026,
    }
    chunks, vectors = build(tmp_path, "day", [new_version, new_paper])

    manifest = replace_documents(chunks, vectors, bulk, tmp_path / "day" / "index", **quiet)

    assert chunk_ids_of(bulk, old["doc_id"]) == [f"{old['doc_id']}#0"]
    _, payload = bulk.points[point_id(f"{old['doc_id']}#0")]
    assert payload["text"].endswith("A much shorter abstract of the new version.")
    assert chunk_ids_of(bulk, "2610.00001") == ["2610.00001#0"]
    assert bulk.count() == before - len(old_chunks) + 2
    assert manifest["mode"] == "replace"
    assert manifest["counts"] == {
        "documents": 2,
        "points_before": before,
        "points_deleted": len(old_chunks),
        "points_loaded": 2,
        "points": before - len(old_chunks) + 2,
    }
    for other in docs[1:]:  # papers that were not harvested again are untouched
        assert chunk_ids_of(bulk, other["doc_id"])


def test_replacing_the_same_day_twice_changes_nothing(bulk: ReplaceStore, tmp_path: Path):
    chunks, vectors = build(tmp_path, "day", fixture_documents()[:3])
    replace_documents(chunks, vectors, bulk, tmp_path / "day" / "index", **quiet)
    points = dict(bulk.points)
    replace_documents(chunks, vectors, bulk, tmp_path / "day" / "index", **quiet)
    assert bulk.points == points


def test_count_check_catches_a_store_that_does_not_delete(tmp_path: Path):
    class NoDelete(ReplaceStore):
        def delete_doc_ids(self, doc_ids) -> None:
            pass

    chunks, vectors = build(tmp_path, "day", fixture_documents()[:2])
    store = NoDelete()
    replace_documents(chunks, vectors, store, tmp_path / "a", **quiet)
    store.points["stale"] = (
        store.points[next(iter(store.points))][0],
        {"doc_id": fixture_documents()[0]["doc_id"], "chunk_id": "stale"},
    )
    with pytest.raises(RuntimeError, match="load check failed"):
        replace_documents(chunks, vectors, store, tmp_path / "b", **quiet)


# --- run_incremental: watermark rules ---------------------------------------------------------


class FakeSteps:
    """Records the calls; `fail` names a step that raises; `records` is what fetch keeps."""

    def __init__(self, records: int = 5, fail: str | None = None, points: int = 100):
        self.calls: list[tuple] = []
        self.records, self.fail, self.points = records, fail, points

    def _step(self, name: str, *args):
        self.calls.append((name, *args))
        if name == self.fail:
            raise RuntimeError(f"{name} failed")

    def steps(self) -> Steps:
        def fetch(f, u, out):
            self._step("fetch", f, u, out)
            return {"counts": {"kept": self.records}}

        def load(chunks, vectors, out):
            self._step("load", chunks, vectors, out)
            return {"counts": {"points": self.points}, "index_snapshot": "test/model/day"}

        return Steps(
            fetch=fetch,
            clean=lambda raw, out: self._step("clean", raw, out),
            chunk=lambda docs, out: self._step("chunk", docs, out),
            embed=lambda chunks, out: self._step("embed", chunks, out),
            load=load,
        )

    def names(self) -> list[str]:
        return [c[0] for c in self.calls]


def test_first_run_needs_a_start_day(tmp_path: Path):
    with pytest.raises(ValueError, match="--start"):
        run_incremental(tmp_path, FakeSteps().steps(), today=TODAY, **quiet)


def test_new_records_run_every_step_and_move_the_watermark(tmp_path: Path):
    fake = FakeSteps()
    state = run_incremental(tmp_path, fake.steps(), start=SNAPSHOT_DAY, today=TODAY, **quiet)

    assert fake.names() == ["fetch", "clean", "chunk", "embed", "load"]
    work = tmp_path / "processed" / "incremental" / "2026-10-10_2026-10-19"
    raw = tmp_path / "raw" / "arxiv-oai" / "2026-10-10_2026-10-19.jsonl"
    assert fake.calls[0] == ("fetch", SNAPSHOT_DAY, date(2026, 10, 19), raw)
    assert fake.calls[1] == ("clean", raw, work / "documents")
    assert fake.calls[4] == ("load", work / "chunks", work / "embeddings", work / "index")
    assert state["until"] == "2026-10-19" and state["from"] == "2026-10-10"
    assert state["records"] == 5 and state["points"] == 100
    assert state["index_snapshot"] == "test/model/day"
    assert read_watermark(tmp_path) == state


def test_next_run_starts_at_the_watermark_day(tmp_path: Path):
    run_incremental(tmp_path, FakeSteps().steps(), start=SNAPSHOT_DAY, today=TODAY, **quiet)
    fake = FakeSteps()
    run_incremental(tmp_path, fake.steps(), today=date(2026, 10, 22), **quiet)
    assert fake.calls[0][1:3] == (date(2026, 10, 19), date(2026, 10, 21))
    assert read_watermark(tmp_path)["until"] == "2026-10-21"


@pytest.mark.parametrize("step", ["fetch", "clean", "chunk", "embed", "load"])
def test_failed_step_leaves_the_watermark_and_the_next_run_repeats_the_range(
    tmp_path: Path, step: str
):
    run_incremental(tmp_path, FakeSteps().steps(), start=SNAPSHOT_DAY, today=TODAY, **quiet)
    before = (tmp_path / STATE_FILE).read_text(encoding="utf-8")

    failing = FakeSteps(fail=step)
    with pytest.raises(RuntimeError, match=f"{step} failed"):
        run_incremental(tmp_path, failing.steps(), today=date(2026, 10, 22), **quiet)
    assert (tmp_path / STATE_FILE).read_text(encoding="utf-8") == before
    assert failing.names()[-1] == step

    retry = FakeSteps()
    run_incremental(tmp_path, retry.steps(), today=date(2026, 10, 22), **quiet)
    assert retry.calls[0][1:3] == (date(2026, 10, 19), date(2026, 10, 21))
    assert read_watermark(tmp_path)["until"] == "2026-10-21"


def test_no_new_records_moves_the_watermark_without_loading(tmp_path: Path):
    run_incremental(tmp_path, FakeSteps().steps(), start=SNAPSHOT_DAY, today=TODAY, **quiet)
    fake = FakeSteps(records=0)
    state = run_incremental(tmp_path, fake.steps(), today=date(2026, 10, 21), **quiet)
    assert fake.names() == ["fetch"]
    assert state["until"] == "2026-10-20" and state["records"] == 0
    assert state["points"] == 100 and state["load_manifest"] is None  # from the last load


def test_nothing_to_do_before_the_watermark_day_has_passed(tmp_path: Path):
    run_incremental(tmp_path, FakeSteps().steps(), start=SNAPSHOT_DAY, today=TODAY, **quiet)
    fake = FakeSteps()
    state = run_incremental(tmp_path, fake.steps(), today=date(2026, 10, 19), **quiet)
    assert fake.calls == [] and state["until"] == "2026-10-19"


def test_leftovers_of_a_failed_run_are_cleared(tmp_path: Path):
    work = tmp_path / "processed" / "incremental" / "2026-10-10_2026-10-19"
    (work / "chunks").mkdir(parents=True)
    (work / "chunks" / "leftover.txt").write_text("x")
    run_incremental(tmp_path, FakeSteps().steps(), start=SNAPSHOT_DAY, today=TODAY, **quiet)
    assert not (work / "chunks" / "leftover.txt").exists()


# --- end to end with the real chunk, embed and load steps -------------------------------------


def real_steps(tmp_path: Path, store: ReplaceStore, days: dict[date, list[dict]]) -> Steps:
    """Real chunk, embed (fake encoder) and replace; fetch and clean write the day's documents
    (clean needs Java, and is tested in test_clean)."""
    wanted: dict[str, list[dict]] = {}

    def fetch(f, u, out):
        docs = [d for day, ds in days.items() if f <= day <= u for d in ds]
        wanted[str(out)] = docs
        return {"counts": {"kept": len(docs)}}

    def clean(raw, documents):
        write_documents(documents, wanted[str(raw)])

    return Steps(
        fetch=fetch,
        clean=clean,
        chunk=lambda docs, out: chunk_documents(
            docs, out, max_words=MAX_WORDS, overlap_words=OVERLAP, **quiet
        ),
        embed=lambda chunks, out: embed_chunks(chunks, out, FakeEncoder(), part_size=4, **quiet),
        load=lambda chunks, vectors, out: replace_documents(chunks, vectors, store, out, **quiet),
    )


def test_end_to_end_failed_load_then_retry(bulk: ReplaceStore, tmp_path: Path):
    docs = fixture_documents()
    new_version = {**docs[0], "abstract": "Shorter abstract.", "updated_at": "2026-10-16"}
    new_paper = {
        **doc("2610.00001", words=30),
        "published_at": "2026-10-16",
        "updated_at": None,
        "year": 2026,
    }
    days = {date(2026, 10, 16): [new_version, new_paper]}
    data = tmp_path / "data"
    expected = bulk.count() - len(chunk_ids_of(bulk, docs[0]["doc_id"])) + 2

    # The store fails after the old points are deleted and before the new ones are in.
    bulk.fail_on_upsert = bulk.upserts
    with pytest.raises(ConnectionError):
        run_incremental(
            data, real_steps(tmp_path, bulk, days), start=SNAPSHOT_DAY, today=TODAY, **quiet
        )
    assert read_watermark(data) is None
    assert chunk_ids_of(bulk, docs[0]["doc_id"]) == []  # the index is short of a paper

    bulk.fail_on_upsert = -1
    state = run_incremental(
        data, real_steps(tmp_path, bulk, days), start=SNAPSHOT_DAY, today=TODAY, **quiet
    )
    assert state["until"] == "2026-10-19" and state["records"] == 2
    assert bulk.count() == state["points"] == expected
    assert chunk_ids_of(bulk, docs[0]["doc_id"]) == [f"{docs[0]['doc_id']}#0"]
    manifest = json.loads(Path(state["load_manifest"]).read_text(encoding="utf-8"))
    assert manifest["counts"]["points"] == expected


def test_default_steps_chunk_embed_and_replace(tmp_path: Path):
    store = ReplaceStore()
    steps = default_steps(store, FakeEncoder(), log=lambda _: None)
    documents = write_documents(tmp_path / "documents", fixture_documents()[:3])
    steps.chunk(documents, tmp_path / "chunks")
    steps.embed(tmp_path / "chunks", tmp_path / "embeddings")
    manifest = steps.load(tmp_path / "chunks", tmp_path / "embeddings", tmp_path / "index")
    assert store.count() == manifest["counts"]["points"] == manifest["counts"]["points_loaded"]
    assert manifest["counts"]["documents"] == 3
