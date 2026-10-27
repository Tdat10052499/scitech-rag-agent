# Incremental ingestion: live test

W5-D4-FAO-1, run on 2026-10-27 (D13, one day early). The raw results are in
`incremental_test.json` next to this report; the two command logs were checked against it.

**Result: PASS.** Two real runs of `incremental-run` (#76) against arXiv OAI-PMH added every
fetched paper to a copy of the full index with no duplicate and no stale chunk, and a second run
of the same day left the index unchanged.

## Setup

| Item | Value |
|---|---|
| Machine | Kaggle CPU notebook (no accelerator), Java 21, internet on |
| Code | branch `feat/w5-d2-fao-1-incremental-run` at `de6819d` (#76) |
| Qdrant | 1.19.2 (the version in `docker-compose.yml`), a binary started inside the notebook |
| Starting index | the full bulk index, snapshot 307 of 2026-10-10: 121,926 points, loaded with `load` from the Kaggle dataset `scitech-cscl-v307` and the vectors of the embedding job (W3-D2-FAO-1) |
| Model | `BAAI/bge-small-en-v1.5`, on CPU (ADR 0007) |
| OAI-PMH | set `cs:cs:CL`, category guard `cs.CL` (ADR 0008) |

The test used a copy of the index inside the notebook, so the serving index on FAO's laptop was
not changed.

Commands, with `--data-dir /kaggle/working/data`:

```
incremental-run --start 2026-10-10 --model BAAI/bge-small-en-v1.5 --device cpu   # run 1
incremental-run --model BAAI/bge-small-en-v1.5 --device cpu                      # run 2, at once
```

Run 1 starts from the snapshot date. Run 2 has no `--start`, so it reads the watermark that run 1
wrote and repeats only that day (ADR 0008, point 1).

## How each run was checked

Before and after each run, the notebook scrolled the whole collection and kept the
`(chunk_id, doc_id)` of every point. It then compared the two lists with the run's own chunks
(`chunks.parquet` of the range):

- `duplicate_chunk_ids`: points after the run minus distinct `chunk_id`s; must be 0.
- `documents_already_in_index`: papers of the run that had points before it (new versions of
  older papers, or papers fetched again).
- `expected_points_after`: points before - old points of those papers + chunks of the run. The
  count after the run must equal it.
- `stale_chunks_of_reloaded_docs`: points of the run's papers that are not among the run's chunks
  (an old chunk left behind by a shorter abstract); must be 0.
- `missing_new_chunks`: chunks of the run that are not in the index; must be 0.

A run passes when all four conditions hold. This check is independent of the load step's own
count check (`points == kept + loaded`), which also passed in both runs.

## Results

| | Run 1 | Run 2 (same day again) |
|---|---:|---:|
| Range (datestamp days) | 2026-10-10 to 2026-10-26 | 2026-10-26 |
| Records harvested / deleted / kept with `cs.CL` | 2,744 / 0 / 2,744 | 177 / 0 / 177 |
| OAI-PMH pages | 3 | 1 |
| Records after `clean` (dropped, duplicates) | 2,744 (0, 0) | 177 (0, 0) |
| Chunks | 2,758 (1.005 per paper) | 178 |
| Papers already in the index | 962 (35%) | 177 (100%) |
| their old points, deleted | 966 | 178 |
| New papers | 1,782 | 0 |
| Points before | 121,926 | 123,718 |
| Points loaded | 2,758 | 178 |
| Points after | **123,718** | **123,718** |
| Expected points after | 123,718 | 123,718 |
| Duplicate `chunk_id`s | 0 | 0 |
| Stale chunks of reloaded papers | 0 | 0 |
| Missing new chunks | 0 | 0 |
| Watermark after the run | `until` 2026-10-26 | `until` 2026-10-26 (unchanged) |

Run 1: 121,926 - 966 + 2,758 = 123,718. The index grew by exactly the 1,782 new papers' chunks,
and the 962 papers it already had kept one set of chunks each (the new version).

Run 2: the 177 papers of 2026-10-26 were all in the index from run 1, so their 178 points were
deleted and the same 178 loaded again. The count did not move, which is the idempotence the
watermark relies on: a failed or repeated run can always be run again.

Time per step (from the logs; Kaggle CPU, 4 cores):

| Step | Run 1 | Run 2 |
|---|---:|---:|
| `clean` (Spark) | 15.3 s | 11.5 s |
| `chunk` | 0.4 s | 0.1 s |
| `embed` (CPU) | 549.2 s (5.0 chunks/s) | 39.1 s (4.6 chunks/s) |
| `load` (delete + upsert + count) | 2.4 s | 0.3 s |
| Whole command (wall time) | 10 min 45 s | 1 min 13 s |

The rest of the wall time (about 78 s in run 1 and 22 s in run 2) is the harvest with its 3 s
pauses, the Spark and model start-up and Python imports; the logs do not time them separately.
Embedding on CPU is 85% of run 1. A normal day (one day of records, about 180-300) takes about a
minute of embedding, so no GPU is needed.

## Observations

- **Volume.** 2,744 records over 17 datestamp days, about 160 per day, weekends included. The one
  weekday checked alone gave 177 (2026-10-26, a Monday). Earlier single days gave 304
  (2026-10-15) and 276 (2026-10-16) (ADR 0008).
- **Replacing is the normal case.** 35% of run 1's papers were already in the index (32% on the
  live day of 2026-10-16). Without the delete by `doc_id` before the upsert, papers whose new
  abstract has fewer chunks would keep old chunks. The check found none left behind.
- **The overlap day.** The watermark day is harvested again on the next run (ADR 0008, point 1).
  Run 2 shows what that costs: 177 papers embedded again, about 40 s.
- **Not covered by this test.** Deleted records (none in this range) stay in the index until the
  next rebuild (ADR 0008). The BM25 index is not rebuilt, so keyword and hybrid retrieval do not
  see the new chunks yet (#119). Retrieval quality on the new papers was not measured.

## Reproduce

Kaggle CPU notebook (Accelerator None, Internet on) with two inputs: the dataset
`scitech-cscl-v307` (documents and chunks) and the output of the embedding job (W3-D2-FAO-1).
Run the cells below in order, interactively. `incremental_test.json` is written by cell 8.

### Cell 1: code and packages (about 2 min)
```python
!git clone -q -b feat/w5-d2-fao-1-incremental-run https://github.com/Tdat10052499/scitech-rag-agent.git /kaggle/working/repo
!pip install -q -r /kaggle/working/repo/pipelines/requirements-embed.txt
!java -version 2>&1 | head -1
!cd /kaggle/working/repo && git log --oneline -1
```

### Cell 2: start Qdrant 1.19.2 (the version in docker-compose.yml)
```python
import os, subprocess, time, httpx
!wget -q https://github.com/qdrant/qdrant/releases/download/v1.19.2/qdrant-x86_64-unknown-linux-musl.tar.gz -O /kaggle/working/qdrant.tgz
!tar xzf /kaggle/working/qdrant.tgz -C /kaggle/working
os.makedirs("/kaggle/working/qdrant-storage", exist_ok=True)
qdrant = subprocess.Popen(["/kaggle/working/qdrant"], cwd="/kaggle/working",
    env={**os.environ, "QDRANT__STORAGE__STORAGE_PATH": "/kaggle/working/qdrant-storage",
         "QDRANT__TELEMETRY_DISABLED": "true"},
    stdout=open("/kaggle/working/qdrant.log", "w"), stderr=subprocess.STDOUT)
for _ in range(30):
    try:
        if httpx.get("http://localhost:6333/healthz", timeout=2).is_success:
            print("Qdrant is up"); break
    except httpx.HTTPError:
        time.sleep(1)
os.environ.update(QDRANT_URL="http://localhost:6333", QDRANT_COLLECTION="scitech_chunks",
                  PYTHONPATH="/kaggle/working/repo/pipelines/src:/kaggle/working/repo/agent/src")
```

### Cell 3: load the bulk index, snapshot 307 (about 2 min)
```python
from pathlib import Path
import json
CHUNKS = next(p.parent for p in Path("/kaggle/input").rglob("chunks.parquet"))
VECTORS = next(p.parent for p in Path("/kaggle/input").rglob("_embed_manifest.json") if "bge-small" in str(p))
MODEL = json.loads((VECTORS / "_embed_manifest.json").read_text())["model"]
print("chunks: ", CHUNKS); print("vectors:", VECTORS); print("model:  ", MODEL)
!cd /kaggle/working/repo && python -m scitech_pipelines --data-dir /kaggle/working/data load --chunks "{CHUNKS}" --vectors "{VECTORS}"
```
Check: it ends with 121,926 points.

### Cell 4: helpers, and the index before the run
```python
import json, duckdb, httpx, os
from pathlib import Path

D = Path("/kaggle/working/data")
URL, COL = os.environ["QDRANT_URL"], os.environ["QDRANT_COLLECTION"]


def all_points():
    """(chunk_id, doc_id) of every point in the collection."""
    out, offset = [], None
    while True:
        body = {"limit": 10000, "with_payload": ["chunk_id", "doc_id"], "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        r = httpx.post(f"{URL}/collections/{COL}/points/scroll", json=body, timeout=300).json()[
            "result"
        ]
        out += [(p["payload"]["chunk_id"], p["payload"]["doc_id"]) for p in r["points"]]
        offset = r.get("next_page_offset")
        if offset is None:
            return out


def check(run_name, before):
    """Compare the index after a run with the index before it and the run's chunks."""
    state = json.loads((D / "state/incremental.json").read_text())
    fetch = json.loads(Path(state["fetch_manifest"]).read_text())
    after = all_points()
    chunk_ids = [c for c, _ in after]
    result = {
        "run": run_name,
        "range": [state["from"], state["until"]],
        "fetch_counts": fetch["counts"],
        "points_before": len(before),
        "points_after": len(after),
        "duplicate_chunk_ids": len(chunk_ids) - len(set(chunk_ids)),
    }
    if not state["load_manifest"]:  # a range without records: nothing may change
        result["PASS"] = len(after) == len(before) and result["duplicate_chunk_ids"] == 0
        return result, after, state
    load = json.loads(Path(state["load_manifest"]).read_text())
    new = Path(load["chunks"]) / "chunks.parquet"
    con = duckdb.connect()
    new_ids = {r[0] for r in con.execute(f"SELECT chunk_id FROM read_parquet('{new}')").fetchall()}
    new_docs = {
        r[0] for r in con.execute(f"SELECT DISTINCT doc_id FROM read_parquet('{new}')").fetchall()
    }
    old = [(c, d) for c, d in before if d in new_docs]  # points of reloaded papers before the run
    after_new_docs = {c for c, d in after if d in new_docs}
    result.update(
        {
            "load_counts": load["counts"],
            "load_seconds": load["seconds"],
            "run_documents": len(new_docs),
            "run_chunks": len(new_ids),
            "documents_already_in_index": len({d for _, d in old}),
            "their_old_points": len(old),
            "new_documents": len(new_docs) - len({d for _, d in old}),
            "expected_points_after": len(before) - len(old) + len(new_ids),
            "stale_chunks_of_reloaded_docs": len(after_new_docs - new_ids),
            "missing_new_chunks": len(new_ids - after_new_docs),
        }
    )
    result["PASS"] = (
        len(after) == result["expected_points_after"]
        and result["duplicate_chunk_ids"] == 0
        and result["stale_chunks_of_reloaded_docs"] == 0
        and result["missing_new_chunks"] == 0
    )
    return result, after, state


before1 = all_points()
print(len(before1), "points before the first run")
```
Check: it prints 121926.

### Cell 5: the incremental run, from the snapshot date to yesterday (11 min in this test)
```python
%%time
!cd /kaggle/working/repo && python -m scitech_pipelines --data-dir /kaggle/working/data incremental-run --start 2026-10-10 --model "{MODEL}" --device cpu 2>&1 | tee /kaggle/working/run1.log
```
Check: the last lines say `watermark ... -> .../state/incremental.json`.

### Cell 6: verify the first run
```python
r1, before2, state1 = check("first run", before1)
print(json.dumps(r1, indent=2))
```
Check: `"PASS": true` at the end.

### Cell 7: run it again at once (it repeats only the watermark day)
```python
%%time
!cd /kaggle/working/repo && python -m scitech_pipelines --data-dir /kaggle/working/data incremental-run --model "{MODEL}" --device cpu 2>&1 | tee /kaggle/working/run2.log
```

### Cell 8: verify again and save everything for the report
```python
r2, _, state2 = check("second run, same day", before2)
print(json.dumps(r2, indent=2))
out = {"run1": r1, "run2": r2, "watermark_after_run1": state1, "watermark_after_run2": state2}
Path("/kaggle/working/incremental_test.json").write_text(json.dumps(out, indent=2))
print("saved /kaggle/working/incremental_test.json")
```
