import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("duckdb")
pq = pytest.importorskip("pyarrow.parquet")

from test_chunk import doc, write_documents  # noqa: E402

from scitech_pipelines.chunk import CHUNK_FILE, CHUNK_MANIFEST, chunk_documents  # noqa: E402
from scitech_pipelines.load import LOAD_MANIFEST, in_subset  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scaling.py"
spec = importlib.util.spec_from_file_location("scaling", SCRIPT)
scaling = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scaling)

quiet = {"log": lambda _: None}


@pytest.fixture
def chunks(tmp_path: Path) -> Path:
    """Chunks of 200 short papers, several chunks for every fifth one."""
    docs = [
        {
            **doc(f"2401.{i:05d}", words=400 if i % 5 == 0 else 20),
            "published_at": "2024-01-15",
            "updated_at": None,
            "year": 2024,
        }
        for i in range(200)
    ]
    documents = write_documents(tmp_path / "documents", docs)
    out = tmp_path / "processed" / "chunks"
    chunk_documents(documents, out, max_words=120, overlap_words=20, **quiet)
    return out


def test_pct_names():
    assert [scaling.pct(f) for f in (0.1, 0.5, 0.05, 1.0)] == ["10pct", "50pct", "5pct", "100pct"]


def test_memory_from_docker_stats():
    assert scaling.memory_mib("280.7MiB / 7.662GiB") == 280.7
    assert scaling.memory_mib("1.5GiB / 7.662GiB") == 1536.0
    assert scaling.memory_mib("512KiB / 1GiB") == 0.5
    assert scaling.memory_mib(None) is None and scaling.memory_mib("n/a") is None


def test_subset_chunks_keeps_whole_documents_of_the_nested_subset(chunks: Path, tmp_path: Path):
    full = pq.read_table(chunks / CHUNK_FILE).to_pylist()
    small = scaling.subset_chunks(chunks, tmp_path / "c10", 0.1)
    large = scaling.subset_chunks(chunks, tmp_path / "c50", 0.5)

    rows10 = pq.read_table(tmp_path / "c10" / CHUNK_FILE).to_pylist()
    rows50 = pq.read_table(tmp_path / "c50" / CHUNK_FILE).to_pylist()
    expected10 = [r for r in full if in_subset(r["doc_id"], 0.1)]
    assert sorted(r["chunk_id"] for r in rows10) == sorted(r["chunk_id"] for r in expected10)
    assert {r["chunk_id"] for r in rows10} < {r["chunk_id"] for r in rows50}
    assert small == {"documents": len({r["doc_id"] for r in rows10}), "chunks": len(rows10)}
    assert 0 < small["chunks"] < large["chunks"] < len(full)
    assert rows10[0].keys() == full[0].keys()  # the same columns, so BM25 builds from it
    from scitech_agent.retrieval.keyword import build_index

    bm25 = build_index(tmp_path / "c10", tmp_path / "bm25-10pct")
    assert bm25["counts"]["chunks"] == len(rows10)

    manifest = json.loads((tmp_path / "c10" / CHUNK_MANIFEST).read_text(encoding="utf-8"))
    source = json.loads((chunks / CHUNK_MANIFEST).read_text(encoding="utf-8"))
    assert manifest["chunked_at"] == source["chunked_at"]
    assert manifest["fraction"] == 0.1 and manifest["counts"] == small


def profile(collection_bytes: int, memory: str, base: float) -> dict:
    latency = {
        r: {"p50_ms": base + i, "p95_ms": base + i + 0.5} for i, r in enumerate(scaling.RETRIEVERS)
    }
    return {
        "docker": {"collection_bytes": collection_bytes, "memory_usage": memory},
        "latency": latency,
    }


def test_row_and_table():
    load = {"counts": {"points": 12193}, "seconds": 41.2}
    bm25 = {"build_seconds": 3.9, "index_mb": 17.6}
    r = scaling.row(0.1, load, bm25, profile(64 * 2**20, "300MiB / 8GiB", 80.0), 12180)
    assert r["chunks"] == 12193 and r["documents"] == 12180
    assert (r["load_seconds"], r["bm25_build_seconds"], r["bm25_index_mib"]) == (41.2, 3.9, 17.6)
    assert (r["qdrant_collection_mib"], r["qdrant_memory_mib"]) == (64.0, 300.0)
    assert (r["dense_p50_ms"], r["bm25_p95_ms"], r["hybrid_p50_ms"]) == (80.0, 81.5, 82.0)
    assert list(r) == list(scaling.CSV_FIELDS)

    table = scaling.markdown([r, scaling.row(1.0, load, {}, {}, None)])
    assert "| 10% | 12,180 | 12,193 | 41.2 | 3.9 | 64 | 17.6 | 300 | 80 / 80.5 |" in table
    assert "| 100% | - | 12,193 | 41.2 | - | - | - | - | - / - | - / - | - / - |" in table


def test_main_loads_builds_and_profiles_every_size(chunks: Path, tmp_path: Path, monkeypatch):
    data = chunks.parents[1]
    full_index, full_bm25 = data / "processed" / "index", data / "index" / "bm25"
    full_index.mkdir(parents=True)
    vectors = tmp_path / "elsewhere" / "embeddings"  # not under data/: taken from the manifest
    vectors.mkdir(parents=True)
    full_load = {"counts": {"points": 999}, "seconds": 135.2}
    full_load.update(chunks=str(chunks), vectors=str(vectors))
    (full_index / LOAD_MANIFEST).write_text(json.dumps(full_load))
    full_bm25.mkdir(parents=True)
    (full_bm25 / "_bm25_manifest.json").write_text(
        json.dumps({"build_seconds": 36.7, "index_mb": 177.2})
    )
    calls = []

    def fake_run(cmd, check, env):
        calls.append((cmd, env))
        if cmd[:3] == [sys.executable, "-m", "scitech_pipelines"]:
            out = Path(cmd[cmd.index("--out") + 1])
            f = float(cmd[cmd.index("--fraction") + 1])
            out.mkdir(parents=True)
            manifest = {"counts": {"points": int(f * 1000)}, "seconds": f * 100}
            (out / LOAD_MANIFEST).write_text(json.dumps(manifest))
        elif cmd[1:3] == ["-m", "scitech_agent.retrieval.keyword"]:
            assert (Path(cmd[cmd.index("--chunks") + 1]) / CHUNK_FILE).is_file()
            out = Path(cmd[cmd.index("--out") + 1])
            out.mkdir(parents=True)
            (out / "_bm25_manifest.json").write_text(
                json.dumps({"build_seconds": 1.0, "index_mb": 2.0})
            )
        elif cmd[1].endswith("index_profile.py"):
            out = Path(cmd[cmd.index("--out") + 1])
            out.write_text(json.dumps(profile(2**20, "100MiB / 8GiB", 10.0)))
        return None

    waits = []
    monkeypatch.setattr(scaling, "wait_for_qdrant", lambda url: waits.append(url))
    out_dir = tmp_path / "reports"
    argv = ["--data-dir", str(data), "--collection", "chunks", "--out-dir", str(out_dir)]
    assert scaling.main(argv, run=fake_run) == 0

    commands = [c for c, _ in calls]
    loads = [c for c in commands if "load" in c]
    assert [c[c.index("--collection") + 1] for c in loads] == ["chunks_10pct", "chunks_50pct"]
    assert all(c[c.index("--vectors") + 1] == str(vectors) for c in loads)
    assert all(c[c.index("--chunks") + 1] == str(chunks) for c in loads)
    restarts = [c for c in commands if c[:2] == ["docker", "compose"]]
    assert len(restarts) == len(waits) == 3
    profiles = [(c, env) for c, env in calls if c[1].endswith("index_profile.py")]
    assert [env["QDRANT_COLLECTION"] for _, env in profiles] == [
        "chunks_10pct",
        "chunks_50pct",
        "chunks",
    ]
    assert profiles[2][1]["BM25_INDEX_DIR"] == str(full_bm25)
    assert all(c[c.index("--chunks") + 1] == str(chunks) for c, _ in profiles)  # same queries

    result = json.loads((out_dir / "scaling.json").read_text(encoding="utf-8"))
    assert [r["fraction"] for r in result["rows"]] == [0.1, 0.5, 1.0]
    assert [r["chunks"] for r in result["rows"]] == [100, 500, 999]
    assert result["rows"][2]["load_seconds"] == 135.2
    assert (out_dir / "scaling.csv").read_text(encoding="utf-8").startswith("fraction,documents,")

    calls.clear()  # a re-run reuses the finished loads and BM25 indexes
    assert scaling.main([*argv, "--no-restart"], run=fake_run) == 0
    assert all(c[1].endswith("index_profile.py") for c, _ in calls) and len(calls) == 3


def test_main_needs_the_full_load_first(chunks: Path, tmp_path: Path):
    with pytest.raises(SystemExit):
        scaling.main(["--data-dir", str(chunks.parents[1])], run=lambda *a, **k: 1 / 0)


def test_main_refuses_a_fraction_of_one(tmp_path: Path):
    with pytest.raises(SystemExit):
        scaling.main(["--fraction", "1", "--out-dir", str(tmp_path)], run=lambda *a, **k: None)


def test_main_needs_the_vectors_of_the_full_load(chunks: Path, tmp_path: Path, capsys):
    data = chunks.parents[1]
    (data / "processed" / "index").mkdir(parents=True)
    manifest = {"chunks": str(chunks), "vectors": str(tmp_path / "gone")}
    (data / "processed" / "index" / LOAD_MANIFEST).write_text(json.dumps(manifest))
    (data / "index" / "bm25").mkdir(parents=True)
    (data / "index" / "bm25" / "_bm25_manifest.json").write_text("{}")
    with pytest.raises(SystemExit):
        scaling.main(["--data-dir", str(data)], run=lambda *a, **k: 1 / 0)
    assert "use --vectors" in capsys.readouterr().err
