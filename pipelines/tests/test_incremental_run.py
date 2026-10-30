import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from scitech_pipelines.chunk import chunk_documents
from scitech_pipelines.embed import embed_chunks
from scitech_pipelines.incremental_run import (
    LOCK_FILE,
    SEEN_FILE,
    STATE_FILE,
    QdrantReplaceStore,
    RunLocked,
    Steps,
    check_index_model,
    check_not_frozen,
    default_steps,
    read_seen,
    read_watermark,
    replace_documents,
    run_incremental,
    run_lock,
)
from scitech_pipelines.load import load_index, point_id

duckdb = pytest.importorskip("duckdb")
pytest.importorskip("numpy")
pytest.importorskip("pyarrow")

from test_chunk import doc, fixture_documents, write_documents  # noqa: E402
from test_embed import FakeEncoder  # noqa: E402
from test_load import FakeQdrant, FakeStore  # noqa: E402

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


# --- QdrantReplaceStore and the incremental-run command ----------------------------------------


class DeletingQdrant(FakeQdrant):
    """FakeQdrant plus `POST /collections/<name>/points/delete` with a `doc_id` filter."""

    def __init__(self):
        super().__init__()
        self.deletes: list[dict] = []

    def __call__(self, request):
        import httpx

        parts = request.url.path.strip("/").split("/")
        if request.method == "POST" and parts[2:] == ["points", "delete"]:
            assert request.url.params["wait"] == "true"
            body = json.loads(request.content)
            self.deletes.append(body)
            (condition,) = body["filter"]["must"]
            assert condition["key"] == "doc_id"
            wanted = set(condition["match"]["any"])
            points = self.collections[parts[1]]["points"]
            for pid in [p for p, point in points.items() if point["payload"]["doc_id"] in wanted]:
                del points[pid]
            return httpx.Response(200, json={"result": {"status": "completed"}})
        return super().__call__(request)


def test_qdrant_replace_store_replaces_papers_through_the_rest_api(tmp_path: Path):
    httpx = pytest.importorskip("httpx")
    from scitech_agent.store import QdrantStore, StoreConfig

    qdrant = DeletingQdrant()
    transport = httpx.MockTransport(qdrant)
    docs = fixture_documents()
    chunks, vectors = build(tmp_path, "bulk", docs)
    with QdrantStore(StoreConfig(collection="live"), transport=transport) as store:
        load_index(chunks, vectors, store, tmp_path / "bulk" / "index", **quiet)
        points = qdrant.collections["live"]["points"]
        old = [
            p["payload"]["chunk_id"]
            for p in points.values()
            if p["payload"]["doc_id"] == docs[0]["doc_id"]
        ]
        assert len(old) > 1
        before = len(points)
        new_version = {
            **docs[0],
            "abstract": "A much shorter abstract.",
            "updated_at": "2026-10-16",
        }
        day_chunks, day_vectors = build(tmp_path, "day", [new_version])

        with QdrantReplaceStore(store, transport=transport) as replace_store:
            assert replace_store.collection == "live"
            manifest = replace_documents(
                day_chunks, day_vectors, replace_store, tmp_path / "day" / "index", **quiet
            )
            replace_store.delete_doc_ids([])  # nothing to delete: no request

    assert len(qdrant.deletes) == 1
    assert qdrant.deletes[0]["filter"]["must"][0]["match"]["any"] == [docs[0]["doc_id"]]
    left = sorted(
        p["payload"]["chunk_id"]
        for p in points.values()
        if p["payload"]["doc_id"] == docs[0]["doc_id"]
    )
    assert left == [f"{docs[0]['doc_id']}#0"]
    assert len(points) == manifest["counts"]["points"] == before - len(old) + 1
    assert manifest["index_snapshot"].startswith("live/")


def test_qdrant_replace_store_raises_when_the_delete_fails():
    httpx = pytest.importorskip("httpx")
    from scitech_agent.store import QdrantStore, StoreConfig

    def refuse(request):
        return httpx.Response(500, text="disk full")

    transport = httpx.MockTransport(refuse)
    with QdrantStore(StoreConfig(collection="live"), transport=transport) as store:
        with QdrantReplaceStore(store, transport=transport) as replace_store:
            with pytest.raises(RuntimeError, match="HTTP 500: disk full"):
                replace_store.delete_doc_ids(["2404.00001"])


def write_bulk_manifest(data_dir: Path, collection: str, model: str) -> None:
    index = data_dir / "processed" / "index"
    index.mkdir(parents=True)
    manifest = {"step": "load", "collection": collection, "model": model}
    (index / "_load_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_index_model_must_match_the_bulk_load_of_the_same_collection(tmp_path: Path):
    check_index_model(tmp_path, "scitech_chunks", "any/model")  # no bulk manifest: no check
    write_bulk_manifest(tmp_path, "scitech_chunks", "BAAI/bge-small-en-v1.5")
    check_index_model(tmp_path, "scitech_chunks", "BAAI/bge-small-en-v1.5")
    check_index_model(tmp_path, "other_collection", "other/model")  # not the bulk collection
    with pytest.raises(ValueError, match="loaded with BAAI/bge-small-en-v1.5"):
        check_index_model(tmp_path, "scitech_chunks", "BAAI/bge-base-en-v1.5")


def test_incremental_run_command_refuses_another_model_than_the_bulk_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import scitech_pipelines.embed
    from scitech_pipelines.cli import main

    write_bulk_manifest(tmp_path, "scitech_chunks", "BAAI/bge-small-en-v1.5")
    monkeypatch.setenv("QDRANT_COLLECTION", "scitech_chunks")
    monkeypatch.setattr(  # the check runs before the model is loaded
        scitech_pipelines.embed, "SentenceTransformerEncoder", lambda *a, **k: pytest.fail()
    )
    args = ["--data-dir", str(tmp_path), "incremental-run", "--model", "BAAI/bge-base-en-v1.5"]
    with pytest.raises(ValueError, match="vectors of two models"):
        main(args)


def test_incremental_run_command_wires_store_model_and_watermark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    pytest.importorskip("httpx")
    import scitech_agent.store
    import scitech_pipelines.embed
    import scitech_pipelines.incremental_run
    from scitech_pipelines.cli import main

    seen: dict = {}

    class Store(FakeStore):
        def __init__(self, config):
            super().__init__(config.collection)
            self.config = config

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            seen["closed"] = True

    def fake_run(data_dir, steps, **kwargs):
        seen.update(data_dir=data_dir, steps=steps, **kwargs)
        return {}

    monkeypatch.setattr(scitech_agent.store, "QdrantStore", Store)
    monkeypatch.setattr(
        scitech_pipelines.embed,
        "SentenceTransformerEncoder",
        lambda name, device=None: seen.update(model=name, device=device) or FakeEncoder(),
    )
    monkeypatch.setattr(scitech_pipelines.incremental_run, "run_incremental", fake_run)
    monkeypatch.setenv("QDRANT_COLLECTION", "from_env")
    args = ["--data-dir", str(tmp_path), "incremental-run", "--model", "some/model"]
    assert main([*args, "--start", "2026-10-10", "--collection", "live", "--device", "cpu"]) == 0
    assert seen["data_dir"] == tmp_path and seen["start"] == SNAPSHOT_DAY
    assert (seen["model"], seen["device"]) == ("some/model", "cpu")
    assert (seen["set_spec"], seen["category"]) == ("cs:cs:CL", "cs.CL")
    assert isinstance(seen["steps"], Steps) and seen["closed"]

    assert main(args) == 0  # later runs: the watermark gives the first day
    assert seen["start"] is None
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    with pytest.raises(ValueError, match="no embedding model"):
        main(["--data-dir", str(tmp_path), "incremental-run"])
    with pytest.raises(SystemExit):
        main([*args, "--start", "10/10/2026"])


# --- scheduled runs (W7-D6-FAO-1, ADR 0011) -----------------------------------------------------


def record(doc_id: str, abstract: str = "An abstract.") -> dict:
    return {"id": doc_id, "title": f"Paper {doc_id}", "abstract": abstract}


class FetchingSteps(FakeSteps):
    """FakeSteps whose fetch writes `records` as JSON lines, like `incremental-fetch`."""

    def __init__(self, records: list[dict], **kwargs):
        super().__init__(records=len(records), **kwargs)
        self.lines = records

    def steps(self) -> Steps:
        base = super().steps()

        def fetch(f, u, out):
            self._step("fetch", f, u, out)
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("w", encoding="utf-8") as fh:
                for r in self.lines:
                    fh.write(json.dumps(r) + "\n")
            return {"counts": {"kept": len(self.lines)}}

        return Steps(fetch, base.clean, base.chunk, base.embed, base.load)


NOW = datetime(2026, 11, 4, 8, 0, 5, tzinfo=timezone.utc)


def test_until_today_fetches_today_and_the_next_run_starts_there(tmp_path: Path):
    fake = FakeSteps()
    run = {"until_today": True, **quiet}
    state = run_incremental(tmp_path, fake.steps(), start=SNAPSHOT_DAY, now=NOW, **run)
    assert fake.calls[0][1:3] == (SNAPSHOT_DAY, date(2026, 11, 4))
    assert state["until"] == "2026-11-04"
    work = tmp_path / "processed" / "incremental" / "2026-10-10_2026-11-04_080005"
    assert fake.calls[-1][3] == work / "index"  # one folder per run, so none is removed

    later = FakeSteps()
    run_incremental(tmp_path, later.steps(), now=NOW.replace(hour=10), **run)
    assert later.calls[0][1:3] == (date(2026, 11, 4), date(2026, 11, 4))
    assert later.calls[-1][3] == work.with_name("2026-11-04_2026-11-04_100005") / "index"


def test_only_new_or_changed_papers_go_to_clean(tmp_path: Path):
    run = {"until_today": True, "skip_unchanged": True, **quiet}
    first = FetchingSteps([record("a"), record("b")])
    run_incremental(tmp_path, first.steps(), start=SNAPSHOT_DAY, now=NOW, **run)
    assert set(read_seen(tmp_path)) == {"a", "b"}

    second = FetchingSteps([record("a"), record("b", "A new abstract."), record("c")])
    state = run_incremental(tmp_path, second.steps(), now=NOW.replace(hour=10), **run)
    cleaned = second.calls[1][1]
    assert cleaned.name == "changed.jsonl"
    assert [json.loads(line)["id"] for line in cleaned.read_text().splitlines()] == ["b", "c"]
    assert state["records"] == 2
    assert set(read_seen(tmp_path)) == {"a", "b", "c"}


def test_a_run_with_nothing_changed_skips_every_step_and_keeps_the_watermark(tmp_path: Path):
    run = {"until_today": True, "skip_unchanged": True, **quiet}
    lines = [record("a"), record("b")]
    run_incremental(tmp_path, FetchingSteps(lines).steps(), start=SNAPSHOT_DAY, now=NOW, **run)
    before = (tmp_path / STATE_FILE).read_text(encoding="utf-8")
    seen = (tmp_path / SEEN_FILE).read_text(encoding="utf-8")

    again = FetchingSteps(lines)
    logged: list[str] = []
    run_incremental(
        tmp_path, again.steps(), now=NOW.replace(hour=10), **{**run, "log": logged.append}
    )
    assert again.names() == ["fetch"]
    assert "incremental: nothing changed" in logged
    assert (tmp_path / STATE_FILE).read_text(encoding="utf-8") == before
    assert (tmp_path / SEEN_FILE).read_text(encoding="utf-8") == seen
    assert not (tmp_path / "processed" / "incremental" / "2026-11-04_2026-11-04_100005").exists()


def test_after_load_runs_before_the_watermark_moves_and_a_failure_repeats_the_run(
    tmp_path: Path,
):
    run = {"until_today": True, "skip_unchanged": True, **quiet}
    calls: list[str] = []

    def failing_rebuild():
        calls.append("rebuild")
        raise RuntimeError("bm25 build failed")

    fake = FetchingSteps([record("a")])
    with pytest.raises(RuntimeError, match="bm25 build failed"):
        run_incremental(
            tmp_path, fake.steps(), start=SNAPSHOT_DAY, now=NOW, after_load=failing_rebuild, **run
        )
    assert fake.names()[-1] == "load" and calls == ["rebuild"]
    assert read_watermark(tmp_path) is None and read_seen(tmp_path) == {}

    retry = FetchingSteps([record("a")])
    state = run_incremental(
        tmp_path,
        retry.steps(),
        start=SNAPSHOT_DAY,
        now=NOW,
        after_load=lambda: calls.append("rebuild"),
        **run,
    )
    assert retry.names() == ["fetch", "clean", "chunk", "embed", "load"]
    assert calls == ["rebuild", "rebuild"] and state["until"] == "2026-11-04"


def test_after_load_is_not_called_without_a_load(tmp_path: Path):
    called = []
    run_incremental(
        tmp_path,
        FakeSteps(records=0).steps(),
        start=SNAPSHOT_DAY,
        today=TODAY,
        after_load=lambda: called.append(1),
        **quiet,
    )
    assert called == []


def test_the_frozen_collection_is_refused():
    check_not_frozen("scitech_chunks_live")
    check_not_frozen("scitech_chunks", "")  # no frozen collection named: no check
    with pytest.raises(ValueError, match="frozen evaluation collection"):
        check_not_frozen("scitech_chunks")
    with pytest.raises(ValueError, match="frozen"):
        check_not_frozen("other", "other")


def test_a_second_run_stops_while_the_lock_is_held(tmp_path: Path):
    with run_lock(tmp_path, **quiet) as path:
        assert path == tmp_path / LOCK_FILE and path.exists()
        with pytest.raises(RunLocked, match="another incremental run"):
            with run_lock(tmp_path, **quiet):
                pass
    assert not (tmp_path / LOCK_FILE).exists()


def write_lock(data_dir: Path, **held) -> None:
    (data_dir / LOCK_FILE).parent.mkdir(parents=True, exist_ok=True)
    (data_dir / LOCK_FILE).write_text(json.dumps(held), encoding="utf-8")


def test_a_lock_of_a_process_that_is_gone_is_taken_over(tmp_path: Path):
    import socket

    write_lock(tmp_path, host=socket.gethostname(), pid=2**22 + 12345, started=time.time())
    with run_lock(tmp_path, **quiet):
        held = json.loads((tmp_path / LOCK_FILE).read_text(encoding="utf-8"))
        assert held["pid"] == os.getpid()


def test_a_lock_of_another_host_is_taken_over_only_when_old(tmp_path: Path):
    write_lock(tmp_path, host="old-container", pid=1, started=time.time() - 60)
    with pytest.raises(RunLocked):
        with run_lock(tmp_path, **quiet):
            pass
    write_lock(tmp_path, host="old-container", pid=1, started=time.time() - 4 * 3600)
    with run_lock(tmp_path, **quiet):
        pass


def test_the_lock_is_released_when_the_run_fails(tmp_path: Path):
    with pytest.raises(RuntimeError):
        with run_lock(tmp_path, **quiet):
            raise RuntimeError("run failed")
    assert not (tmp_path / LOCK_FILE).exists()


class ScrollingQdrant(DeletingQdrant):
    """DeletingQdrant plus `POST /collections/<name>/points/scroll`, two points per page."""

    def __call__(self, request):
        import httpx

        parts = request.url.path.strip("/").split("/")
        if request.method == "POST" and parts[2:] == ["points", "scroll"]:
            body = json.loads(request.content)
            assert body["with_vector"] is False
            ids = sorted(self.collections[parts[1]]["points"])
            start = ids.index(body["offset"]) if body.get("offset") is not None else 0
            page = ids[start : start + body["limit"]]
            nxt = ids[start + body["limit"]] if start + body["limit"] < len(ids) else None
            fields = body["with_payload"]
            points = [
                {
                    "id": i,
                    "payload": {
                        k: v
                        for k, v in self.collections[parts[1]]["points"][i]["payload"].items()
                        if k in fields
                    },
                }
                for i in page
            ]
            return httpx.Response(
                200, json={"result": {"points": points, "next_page_offset": nxt}}
            )
        return super().__call__(request)


def test_qdrant_replace_store_scrolls_every_payload(tmp_path: Path):
    httpx = pytest.importorskip("httpx")
    from scitech_agent.store import QdrantStore, StoreConfig

    qdrant = ScrollingQdrant()
    transport = httpx.MockTransport(qdrant)
    chunks, vectors = build(tmp_path, "bulk", fixture_documents())
    with QdrantStore(StoreConfig(collection="live"), transport=transport) as store:
        load_index(chunks, vectors, store, tmp_path / "bulk" / "index", **quiet)
        with QdrantReplaceStore(store, transport=transport) as replace_store:
            payloads = list(replace_store.scroll_payloads(["chunk_id", "text"], page_size=7))
    stored = qdrant.collections["live"]["points"]
    assert len(payloads) == len(stored) > 7
    assert {p["chunk_id"] for p in payloads} == {p["payload"]["chunk_id"] for p in stored.values()}
    assert all(set(p) == {"chunk_id", "text"} for p in payloads)


def test_incremental_run_command_refuses_the_frozen_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import scitech_pipelines.embed
    from scitech_pipelines.cli import main

    monkeypatch.setattr(  # refused before the model is loaded
        scitech_pipelines.embed, "SentenceTransformerEncoder", lambda *a, **k: pytest.fail()
    )
    monkeypatch.setenv("FROZEN_COLLECTION", "")  # empty in .env: still scitech_chunks
    args = ["--data-dir", str(tmp_path), "incremental-run", "--model", "some/model"]
    with pytest.raises(ValueError, match="frozen evaluation collection"):
        main([*args, "--collection", "scitech_chunks"])
    monkeypatch.setenv("FROZEN_COLLECTION", "my_frozen")
    with pytest.raises(ValueError, match="frozen evaluation collection"):
        main([*args, "--collection", "my_frozen"])
    assert not (tmp_path / LOCK_FILE).exists()


def test_incremental_run_command_passes_the_scheduled_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    pytest.importorskip("httpx")
    import scitech_agent.store
    import scitech_pipelines.bm25_live
    import scitech_pipelines.embed
    import scitech_pipelines.incremental_run
    from scitech_pipelines.cli import main

    seen: dict = {}

    class Store(FakeStore):
        def __init__(self, config):
            super().__init__(config.collection)
            self.config = config

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

    def fake_run(data_dir, steps, **kwargs):
        seen.update(kwargs, locked=(data_dir / LOCK_FILE).exists())
        kwargs["after_load"]()
        return {}

    monkeypatch.setattr(scitech_agent.store, "QdrantStore", Store)
    monkeypatch.setattr(
        scitech_pipelines.embed, "SentenceTransformerEncoder", lambda *a, **k: FakeEncoder()
    )
    monkeypatch.setattr(scitech_pipelines.incremental_run, "run_incremental", fake_run)
    monkeypatch.setattr(
        scitech_pipelines.bm25_live,
        "rebuild_bm25",
        lambda store, out: seen.update(rebuilt=(store.collection, out)),
    )
    args = ["--data-dir", str(tmp_path), "incremental-run", "--model", "some/model"]
    live = tmp_path / "bm25-live"
    main([*args, "--collection", "live", "--until", "today", "--rebuild-bm25", str(live)])
    assert seen["until_today"] is True and seen["skip_unchanged"] is True
    assert seen["rebuilt"] == ("live", live) and seen["locked"]
    assert not (tmp_path / LOCK_FILE).exists()
