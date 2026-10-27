"""Tests for the incremental run (W5-D2-FAO-1, ADR 0008): watermark, steps, replacing documents
in the store. No network, no Spark, no model: the steps run in this process with fakes (fetch
writes fixture records, clean is replaced by the documents writer of the chunk tests, embed uses
the fake encoder), and the store is in memory."""

import json
import shutil
from datetime import date
from email.utils import parsedate_to_datetime
from pathlib import Path

import pytest

from scitech_pipelines.chunk import chunk_documents
from scitech_pipelines.cli import main
from scitech_pipelines.embed import embed_chunks
from scitech_pipelines.incremental import (
    SUMMARY,
    manifest_path,
    plan_incremental_steps,
    plan_range,
    run_incremental,
    run_paths,
)
from scitech_pipelines.load import point_id

pytest.importorskip("duckdb")
pytest.importorskip("numpy")
pytest.importorskip("pyarrow")

from test_chunk import write_documents  # noqa: E402
from test_embed import DIM, FakeEncoder  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "sample.jsonl"
RECORDS = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]
TODAY = date(2026, 10, 27)
MODEL = "fake/model-a"  # the name of FakeEncoder


def quiet(_: str) -> None:
    pass


class FakeStore:
    """One collection in memory, with the store methods the run uses."""

    def __init__(self, collection: str = "test_chunks", fail_on_upsert: bool = False):
        self.collection = collection
        self.points: dict[str, tuple[list[float], dict]] = {}
        self.dimension: int | None = None
        self.fail_on_upsert = fail_on_upsert
        self.deleted: list[list[str]] = []

    def ensure_collection(self, dimension: int) -> None:
        if self.dimension not in (None, dimension):
            raise ValueError("collection exists with another dimension")
        self.dimension = dimension

    def upsert(self, points) -> None:
        if self.fail_on_upsert:
            raise ConnectionError("Qdrant went away")
        for p in points:
            self.points[p.id] = (p.vector, p.payload)

    def count(self) -> int:
        return len(self.points)

    def delete_doc_ids(self, doc_ids) -> int:
        ids = set(doc_ids)
        self.deleted.append(sorted(ids))
        self.points = {k: v for k, v in self.points.items() if v[1]["doc_id"] not in ids}
        return len(ids)

    def add(self, chunk_id: str) -> None:
        """A point of the bulk index (any vector), as `load` would have written it."""
        doc_id = chunk_id.split("#")[0]
        self.points[point_id(chunk_id)] = ([0.0] * DIM, {"chunk_id": chunk_id, "doc_id": doc_id})

    def chunk_ids(self) -> set[str]:
        return {payload["chunk_id"] for _, payload in self.points.values()}


def to_documents(records: list[dict]) -> list[dict]:
    """What `clean` makes of snapshot records (simplified, like `test_chunk.fixture_documents`)."""
    docs = []
    for r in records:
        created = parsedate_to_datetime(r["versions"][0]["created"]).date()
        docs.append(
            {
                "doc_id": r["id"],
                "source": "arxiv",
                "title": " ".join(r["title"].split()),
                "abstract": " ".join(r["abstract"].split()),
                "authors": [a.strip() for a in r["authors"].replace(" and ", ",").split(",")],
                "categories": r["categories"].split(),
                "published_at": created.isoformat(),
                "updated_at": None,
                "url": f"https://arxiv.org/abs/{r['id']}",
                "license": "CC0-1.0",
                "year": created.year,
            }
        )
    return docs


class FakeSteps:
    """Runs the steps in this process. `records` is what the OAI-PMH fetch returns; a step
    named in `fail` exits with 1."""

    def __init__(self, records: list[dict], fail: str | None = None):
        self.records = records
        self.fail = fail
        self.calls: list[list[str]] = []

    def __call__(self, argv, log_file: Path) -> int:
        argv = list(argv)
        self.calls.append(argv)
        name = argv[2]
        log_file.write_text(" ".join(argv) + "\n", encoding="utf-8")
        if name == self.fail:
            return 1

        def arg(flag: str) -> Path:
            return Path(argv[argv.index(flag) + 1])

        if name == "incremental-fetch":
            out = arg("--out")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("".join(json.dumps(r) + "\n" for r in self.records), encoding="utf-8")
            counts = {"harvested": len(self.records), "kept": len(self.records)}
            manifest_path(out).write_text(json.dumps({"counts": counts}), encoding="utf-8")
        elif name == "clean":
            records = [json.loads(line) for line in arg("--input").read_text().splitlines()]
            shutil.rmtree(arg("--out"), ignore_errors=True)  # Spark writes with mode("overwrite")
            write_documents(arg("--out"), to_documents(records))
        elif name == "chunk":
            chunk_documents(arg("--input"), arg("--out"), log=quiet)
        elif name == "embed":
            assert "--force" in argv and argv[argv.index("--model") + 1] == MODEL
            encoder = FakeEncoder()
            embed_chunks(arg("--input"), arg("--out"), encoder, part_size=4, force=True, log=quiet)
        return 0

    def names(self) -> list[str]:
        return [c[2] for c in self.calls]


def run(tmp_path: Path, store: FakeStore, steps: FakeSteps, **kwargs) -> int:
    kwargs.setdefault("today", TODAY)
    return run_incremental(
        tmp_path / "data", store, model=MODEL, run_step=steps, log=quiet, **kwargs
    )


def state(tmp_path: Path) -> dict | None:
    path = tmp_path / "data" / "state" / "incremental.json"
    return json.loads(path.read_text()) if path.is_file() else None


def summary(tmp_path: Path) -> dict:
    [path] = sorted((tmp_path / "data" / "logs").glob(f"incremental-*/{SUMMARY}"))[-1:]
    return json.loads(path.read_text())


def test_new_documents_are_added_and_the_watermark_moves(tmp_path: Path):
    store = FakeStore()
    for doc in ("2001.00001", "2001.00002", "2001.00003"):  # the bulk index
        store.add(f"{doc}#0")
    steps = FakeSteps(RECORDS[:6])
    assert run(tmp_path, store, steps, start=date(2026, 10, 10)) == 0
    assert steps.names() == ["incremental-fetch", "clean", "validate", "chunk", "embed"]
    new = {f"{r['id']}#0" for r in RECORDS[:6]}
    assert store.chunk_ids() == new | {"2001.00001#0", "2001.00002#0", "2001.00003#0"}
    s = state(tmp_path)
    assert s["until"] == "2026-10-26"  # yesterday
    assert s["points"] == store.count() == 9
    assert (s["set"], s["category"], s["collection"], s["model"]) == (
        "cs:cs:CL",
        "cs.CL",
        "test_chunks",
        MODEL,
    )
    load = summary(tmp_path)["load"]
    assert (load["documents"], load["old_points_deleted"], load["points"]) == (6, 0, 9)
    assert summary(tmp_path)["watermark_after"] == "2026-10-26"


def test_documents_already_present_are_replaced_with_no_stale_chunks(tmp_path: Path):
    store = FakeStore()
    old = RECORDS[0]["id"]
    store.add(f"{old}#0")
    store.add(f"{old}#1")  # its old abstract had two chunks, the new version has one
    store.add("2001.00001#0")
    steps = FakeSteps(RECORDS[:2])
    assert run(tmp_path, store, steps, start=date(2026, 10, 10)) == 0
    assert store.chunk_ids() == {f"{old}#0", f"{RECORDS[1]['id']}#0", "2001.00001#0"}
    vector, payload = store.points[point_id(f"{old}#0")]
    assert payload["title"] and vector != [0.0] * DIM  # the new chunk, not the old point
    load = summary(tmp_path)["load"]
    assert (load["points_before"], load["old_points_deleted"], load["points"]) == (3, 2, 3)


def test_a_failed_load_keeps_the_watermark_and_a_re_run_repairs_it(tmp_path: Path):
    store = FakeStore(fail_on_upsert=True)
    store.add(f"{RECORDS[0]['id']}#0")
    store.add("2001.00001#0")
    first = {"until": "2026-10-20", "set": "cs:cs:CL", "category": "cs.CL"}
    first |= {"collection": "test_chunks", "model": MODEL, "points": 2}
    path = tmp_path / "data" / "state" / "incremental.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(first))
    assert run(tmp_path, store, FakeSteps(RECORDS[:3])) == 1
    assert state(tmp_path) == first
    assert summary(tmp_path)["exit_code"] == 1
    assert summary(tmp_path)["watermark_after"] == "2026-10-20"
    assert summary(tmp_path)["steps"][-1] == {
        "name": "load",
        "exit_code": 1,
        "seconds": summary(tmp_path)["steps"][-1]["seconds"],
    }
    assert store.chunk_ids() == {"2001.00001#0"}  # deleted before the upsert failed

    store.fail_on_upsert = False
    steps = FakeSteps(RECORDS[:3])
    assert run(tmp_path, store, steps) == 0
    assert "--from 2026-10-20" in " ".join(steps.calls[0])  # the same range again
    assert store.count() == 4 and state(tmp_path)["until"] == "2026-10-26"


def test_a_failed_step_stops_the_run_before_the_store(tmp_path: Path):
    store = FakeStore()
    steps = FakeSteps(RECORDS[:3], fail="clean")
    assert run(tmp_path, store, steps, start=date(2026, 10, 10)) == 1
    assert steps.names() == ["incremental-fetch", "clean"]
    assert state(tmp_path) is None and store.count() == 0 and store.deleted == []


def test_running_the_same_range_again_changes_nothing(tmp_path: Path):
    store = FakeStore()
    store.add("2001.00001#0")
    assert run(tmp_path, store, FakeSteps(RECORDS[:4]), start=date(2026, 10, 10)) == 0
    points = dict(store.points)
    steps = FakeSteps(RECORDS[:4])
    assert run(tmp_path, store, steps) == 0  # from the watermark day itself (ADR 0008, point 1)
    assert "--from 2026-10-26 --until 2026-10-26" in " ".join(steps.calls[0])
    assert store.points == points


def test_a_day_without_records_moves_the_watermark_without_loading(tmp_path: Path):
    store = FakeStore()
    store.add("2001.00001#0")
    steps = FakeSteps([])
    assert run(tmp_path, store, steps, start=date(2026, 10, 25)) == 0
    assert steps.names() == ["incremental-fetch"]
    assert state(tmp_path)["until"] == "2026-10-26" and store.deleted == []


def test_watermark_rules(tmp_path: Path):
    path = tmp_path / "incremental.json"
    with pytest.raises(ValueError, match="--start"):
        plan_range(None, start=None, until=None, today=TODAY, state_path=path)
    with pytest.raises(ValueError, match="only for the first run"):
        plan_range(
            {"until": "2026-10-20"},
            start=date(2026, 10, 1),
            until=None,
            today=TODAY,
            state_path=path,
        )
    assert plan_range(
        {"until": "2026-10-20"}, start=None, until=None, today=TODAY, state_path=path
    ) == (date(2026, 10, 20), date(2026, 10, 26))
    assert plan_range(
        None, start=date(2026, 10, 10), until=date(2026, 10, 12), today=TODAY, state_path=path
    ) == (date(2026, 10, 10), date(2026, 10, 12))


def test_a_watermark_after_until_is_nothing_to_do(tmp_path: Path):
    steps = FakeSteps(RECORDS[:2])
    assert run(tmp_path, FakeStore(), steps, start=TODAY) == 0  # until is yesterday
    assert steps.calls == [] and state(tmp_path) is None


def test_other_settings_than_the_watermark_are_refused(tmp_path: Path):
    assert run(tmp_path, FakeStore(), FakeSteps(RECORDS[:2]), start=date(2026, 10, 10)) == 0
    with pytest.raises(ValueError, match="collection"):
        run(tmp_path, FakeStore(collection="other"), FakeSteps(RECORDS[:2]))
    with pytest.raises(ValueError, match="set"):
        run(tmp_path, FakeStore(), FakeSteps(RECORDS[:2]), set_spec="cs")


def test_the_steps_use_their_own_folders_and_the_same_commands_as_by_hand(tmp_path: Path):
    data = tmp_path / "data"
    paths = run_paths(data, "cs:cs:CL", date(2026, 10, 20), date(2026, 10, 26))
    assert paths.raw == data / "raw" / "arxiv-oai" / "cs-cs-CL_2026-10-20_2026-10-26.jsonl"
    assert paths.work == data / "processed" / "incremental" / "2026-10-20_2026-10-26"
    steps = plan_incremental_steps(
        data,
        paths,
        from_date=date(2026, 10, 20),
        until=date(2026, 10, 26),
        set_spec="cs:cs:CL",
        category="cs.CL",
        base_url="https://oai.example.org/oai",
        pause=3.0,
        model=MODEL,
        device="cpu",
    )
    assert steps["incremental-fetch"][2:] == (
        "incremental-fetch", "--from", "2026-10-20", "--until", "2026-10-26",
        "--set", "cs:cs:CL", "--category", "cs.CL", "--out", str(paths.raw),
        "--base-url", "https://oai.example.org/oai", "--pause", "3",
    )  # fmt: skip
    assert steps["clean"][-4:] == ("--sample-size", "0", "--category", "cs.CL")
    assert steps["embed"][-5:] == ("--model", MODEL, "--force", "--device", "cpu")
    assert str(paths.documents) in steps["validate"]


def test_the_command_needs_a_model_before_anything_runs(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    with pytest.raises(ValueError, match="embedding model"):
        main(["--data-dir", str(tmp_path), "incremental", "--start", "2026-10-10"])
    assert not (tmp_path / "logs").exists()
