# Runbook: data pipeline (arXiv snapshot to a loaded Qdrant index)

Tasks: W4-D5-FAO-1 (draft) and W6-D3-FAO-1 (final: incremental ingestion with the live test, scaling notes, more troubleshooting).
Commands: `pipelines/AGENTS.md` (every option) and `pipelines/README.md` (setup, what runs where, the Kaggle recipes). Decisions: ADR 0003 (corpus), ADR 0005 (engine), ADR 0007 (embedding model), ADR 0008 (incremental ingestion).

> Status: final version, 2026-10-27 (D13). Draft of 2026-10-20 (D07), updated on 2026-10-22 (D09). `run-all` (#92), the index profile (#68), `incremental-run` (#76), its live test (#124) and the scaling script (#96) are merged. Still in review: the README's Kaggle recipes (#60). Times are the measured ones from the FAO journal (W2, W3, W5) unless marked otherwise.

## 1. Before you start
- **Python environment:** `make setup`, then `PYTHONPATH=pipelines/src:agent/src` from the repository root (PowerShell: `$env:PYTHONPATH = "pipelines/src;agent/src"`). `load` and `run-all` need `agent/src` for DAT's Qdrant store.
- **Java 17+** for `clean` (PySpark). Native Windows does not work: use WSL2, Linux or a Kaggle CPU notebook. Java 8 counts as none.
- **A GPU** for `embed` on the full corpus (Kaggle T4: 14.4 min with bge-small). On a CPU it would take about 12 h (estimate, `docs/03-data-sources.md`).
- **Qdrant** for `load`: `make up` (docker compose, `qdrant/qdrant:v1.19.2`), or the release binary of the same version in a notebook (README, "load on Kaggle").
- **Kaggle login** for `download`: `kaggle auth login` once. The token stays in your user profile, never in the repository.
- **Environment:** `EMBEDDING_MODEL`, `EMBEDDING_QUERY_PREFIX`, `QDRANT_URL`, `QDRANT_COLLECTION` and `DATA_DIR` from `.env.example`.

### Disk space (full corpus, snapshot version 307)
| What | Size | Note |
|---|---|---|
| raw snapshot `data/raw/arxiv/` | 5.61 GB | 7.5 GB at the peak while the 1.86 GB zip is still there |
| documents `data/processed/documents/` | 95 MB | 33 year partitions |
| chunks `data/processed/chunks/` | 101 MB | |
| vectors `data/processed/embeddings/` | 198 MB (bge-small), 385 MB (bge-base) | |
| BM25 index `data/index/bm25/` | 177.2 MB | needed by the default retriever (hybrid) |
| Qdrant storage | 609.9 MiB | the `scitech_chunks` collection (bge-small, 121,926 points); container memory 280.7 MiB (`docker stats`, includes page cache). Index profile, #68 |

Plan for **at least 8 GB free** for a full rebuild from the download. On a small `C:` drive, point `DATA_DIR` (or a junction from `data\raw`) at another disk. On D02, the C: drive filled up while the zip was still there.

## 2. Full rebuild
With `run-all` (#92):
```bash
python -m scitech_pipelines run-all --model "$EMBEDDING_MODEL"
```
On machines without everything (the usual case), split it where the hardware changes:
```bash
python -m scitech_pipelines run-all --to chunk           # Java machine or Kaggle CPU notebook
python -m scitech_pipelines run-all --from embed --to embed --model "$EMBEDDING_MODEL"   # GPU notebook
python -m scitech_pipelines run-all --from load          # where Qdrant runs
```
Step by step without `run-all`: the "Full rebuild" block of `pipelines/README.md`.

Then build the BM25 index from the same chunks. `run-all` does not do it, and the default retriever (hybrid, `RETRIEVER` empty) needs both the Qdrant collection and this index:
```bash
PYTHONPATH=agent/src python -m scitech_agent.retrieval.keyword build --chunks data/processed/chunks --out data/index/bm25
```

Measured times for the full corpus:

| Step | Time | Where |
|---|---|---|
| download | 150 s | FAO's laptop (19.8 MB/s) |
| clean | 82-111 s for the whole process, peak memory 2.7-2.9 GB | Kaggle CPU notebook (4 CPUs) |
| validate | seconds | anywhere |
| chunk | 14-18 s | Kaggle or laptop |
| embed | 14.4 min (bge-small), 43.8 min (bge-base) | Kaggle T4 |
| load | 106.3 s (121,926 bge-small points, 4-17 s per part) | Kaggle CPU notebook, Qdrant 1.19.2 |
| load | 135.2 s (121,926 bge-small points, 7.6-11.2 s per part); a dry run earlier the same evening took 201.7 s | FAO's Windows laptop, Qdrant 1.19.2 in Docker (2026-10-21) |
| BM25 build | 15.8-20.3 s, peak working set 1,184 MB | DAT's Windows laptop |
| BM25 build | 36.7 s | FAO's Windows laptop (2026-10-21) |

`run-all` writes each step's output to `<data-dir>/logs/run-all-<UTC time>/<nn>-<step>.log` and a summary `run-all.json` (exit code and seconds per step). Keep the folder of the run you report on.

## 3. Small rebuild (weak machine, or to try the steps)
```bash
python -m scitech_pipelines run-all --limit 2000 --device cpu --model "$EMBEDDING_MODEL"
```
- `--limit N` keeps the first N `cs.CL` records in snapshot order, which are mostly the oldest papers, and none of the golden documents. A small run is a smoke test of the steps only: never evaluate on it or report retrieval numbers from it.
- Everything after the download goes to `<data-dir>/limit-<N>/` and into the collection `<QDRANT_COLLECTION>_limit_<N>`, so the full data and the full index are never touched.
- The download is still the full 1.86 GB zip, because Kaggle only serves the whole snapshot. With a snapshot already on disk, add `--snapshot <path>` to skip it.
- Without any download: the records of `pipelines/tests/fixtures/sample.jsonl` (in git), for example `--snapshot pipelines/tests/fixtures/sample.jsonl --limit 10`. Up to `chunk` (`--to chunk`), this took 16.9 s on a Linux VM (4 CPUs), mostly Spark's start-up.
- Time for `--limit 2000`, from the snapshot on disk to loaded points: **400.1 s** in a Kaggle CPU notebook on 2026-10-20 (sample 38.2 s, clean 28.4 s, validate 0.4 s, chunk 0.4 s, embed on CPU 329.7 s at 7.0 chunks/s, load 3.0 s). That gave 2,000 documents, 2,002 chunks and 2,002 points. Per-step table: `pipelines/README.md`.

## 4. Verify a build
The counts must chain, for snapshot 307:

| Manifest | Field | Expected |
|---|---|---|
| `processed/documents/_clean_manifest.json` | `counts.records_out` | 121,860 |
| `processed/chunks/_chunk_manifest.json` | `counts.chunks` | 121,926 |
| `processed/embeddings/_embed_manifest.json` | `counts.chunks` | 121,926 |
| `processed/index/_load_manifest.json` | `counts.points` | 121,926 |

- `validate --golden evaluation/golden_set/golden.jsonl` checks the documents and that every golden `relevant_doc_ids` exists. `run-all` runs it on full runs.
- `pipelines/scripts/golden_coverage.py --chunks data/processed/chunks --qdrant` checks the same ids against the chunks and the loaded collection (#69). Run it with `PYTHONPATH=pipelines/src` (PowerShell: `$env:PYTHONPATH = "pipelines/src"`). On 2026-10-20 all 57 doc ids of the 47 items (gs-001 to gs-045, gs-u01, gs-u02; golden set of #88) were in the chunks.
- `_load_manifest.json` holds `index_snapshot`, the id that evaluation runs cite.
- Search speed, filters, size on disk and memory: `pipelines/scripts/index_profile.py`, with usage and the 2026-10-21 numbers in `pipelines/reports/index_profile.md` (#68). On FAO's laptop, p95 was 88 ms for dense, 14 ms for BM25 and 149 ms for hybrid.
- A quick look at the store: `PYTHONPATH=agent/src python -c "from scitech_agent.store import QdrantStore; s = QdrantStore.from_env(); print(s.count())"`.

## 5. Common failures and fixes
| Symptom | Cause | Fix |
|---|---|---|
| `clean` stops at once, or its tests are skipped | No Java 17+ (or Java 8) | Install Java 17+, or run `clean` in WSL2, Linux or a Kaggle CPU notebook |
| `clean` fails on Kaggle with an unknown Spark function | Older PySpark in the notebook | Fixed for PySpark 4.0.4 (`a64d69a`); run from current `main` |
| `download` fails with 401/403 | No Kaggle login | `kaggle auth login`; never copy the token into the repository |
| Kaggle's dataset page crashes | Kaggle side | Download through the API (the `download` command), not the web page |
| "No space left on device" during `download` | Zip and extracted file both on disk (7.5 GB peak) | Free space or move `DATA_DIR`; the zip is deleted after extraction unless `--keep-zip` |
| `embed` very slow | Running on CPU (no GPU runtime selected) | Select a GPU in the notebook; `--device cuda` fails loudly instead of falling back |
| `embed` fails with "no embedding model" | `EMBEDDING_MODEL` unset or `replace-me` | `--model BAAI/bge-small-en-v1.5` (ADR 0007) or set the variable |
| `load`: `ModuleNotFoundError: scitech_agent` | `agent/src` not on `PYTHONPATH` | Add it (section 1) |
| `load`: connection refused | Qdrant not running, or a wrong `QDRANT_URL` | `make up`, or start the binary; check `curl $QDRANT_URL/healthz` |
| `load` refuses the vectors | Vectors from other chunks (`chunked_at` differs), an `embed --limit` run, or an unfinished embed run | Re-run `embed` on the current chunks, without `--limit` |
| `load`: "other settings" | Resume state from a load with other vectors, chunks or collection | `--force`, or another `--out` |
| `load`: "load check failed ... holds N points" | Points from an older load in the same collection | Recreate the collection (another `QDRANT_COLLECTION`, or delete it), then `load --force` |
| Dense recall lower than ADR 0007 through Qdrant | `QDRANT_SEARCH_EXACT=false`: approximate HNSW search, where gs-016 drops out (#87) | Check that `QDRANT_SEARCH_EXACT` is not `false`; exact search is the default since #101 |
| `load` (or its tests) fails with an `AttributeError` about `fetch_arrow_table` | duckdb 2.0 removed `fetch_arrow_table`, and a fresh `make setup` installs 2.0 | Fixed in #107 (`to_arrow_table` first); on an older branch, merge `main` |
| `ModuleNotFoundError: scitech_agent.retrieval.hybrid` (evaluation configs, `index_profile.py`) | A branch from before the hybrid retriever (#82, #101) | Merge `main` into the branch, or run from `main` |
| `docker start qdrant`: "No such container: qdrant" | The container belongs to docker compose and is named `<folder>-qdrant-1` | `docker compose up -d` (or `make up`) from the repository root |
| A golden set or run file copied from Windows has another sha256 than on Linux | Git on Windows checks text files out with CRLF line ends | Compare files with LF line ends, or run on one OS; the run file records the sha256 of the bytes it read |
| Kaggle notebook: data of a previous run gone | `/kaggle/working` lasts only for the session | Keep inputs as Kaggle datasets; don't use *Save Version* with Qdrant's storage in `/kaggle/working` |
| `Warning: You are sending unauthenticated requests to the HF Hub` at the start of `embed` or `incremental-run` | No Hugging Face token; the model is public | Harmless. Downloads are only slower; don't put a token in the repository |
| `WARN NativeCodeLoader: Unable to load native-hadoop library` | Spark without native Hadoop libraries | Harmless; `clean` uses the Java fallback |
| Notebook cell: `UsageError: Line magic function %%time not found` | `%%time` is not the first line of the cell (a comment above it counts) | Move `%%time` to the first line |
| `incremental-run`: "no watermark ... give the first day with --start" | First run on this data directory | `--start` with the date of the snapshot the index was built from (2026-10-10 for version 307) |
| `incremental-run`: "load check failed" | Another process wrote to or deleted from the collection during the run | The watermark did not move: run the command again; it deletes and reloads the same papers |

## 6. New records since the snapshot
`incremental-run` (ADR 0008, #76) adds the arXiv records published since the watermark `<data-dir>/state/incremental.json` to a collection:
```bash
python -m scitech_pipelines incremental-run --start 2026-10-10 --model "$EMBEDDING_MODEL"   # first run only
python -m scitech_pipelines incremental-run --model "$EMBEDDING_MODEL"                      # later runs
```
- It needs Java 17+ (`clean`), sentence-transformers (`embed`, a CPU is enough) and the Qdrant it loads into, on one machine. FAO's laptop has Java 8, so it runs in WSL2, Linux or a Kaggle CPU notebook. A notebook has its own Qdrant and cannot update the one on the laptop.
- **Schedule:** by hand (ADR 0008, point 6) until ADR 0011's scheduled runs are merged after Gate W7; see "Scheduled runs" below. One run catches up all missed days in one range.
- **What it does:** fetch from OAI-PMH (set `cs:cs:CL`) from the watermark day to yesterday (UTC), then `clean`, `chunk`, `embed` and a replacing load: every fetched paper loses all its old points before its new chunks are loaded. The watermark moves only after the load's count check passes, so a failed run is simply run again. The watermark day is fetched again on the next run (its records may still have been arriving), which costs about one day of embedding.
- **Check a run:** the last lines say `load: N papers replaced in <collection>: D old points deleted, L loaded, P points now` and `incremental: watermark <day> -> ...`. In the run's `_load_manifest.json` (`<data-dir>/processed/incremental/<from>_<until>/index/`), `counts.points` must equal `points_before - points_deleted + points_loaded`.
- **Live test** (W5-D4-FAO-1, 2026-10-27, `pipelines/reports/incremental_test.md`, #124), on a Kaggle CPU notebook against a copy of the full index:

  | | `--start 2026-10-10` | same day again |
  |---|---:|---:|
  | Papers / chunks | 2,744 / 2,758 | 177 / 178 |
  | Already indexed (old points deleted) | 962 (966) | 177 (178) |
  | Points before -> after | 121,926 -> 123,718 | 123,718 -> 123,718 |
  | Duplicate, stale or missing chunks | 0 | 0 |
  | Wall time (embed on CPU) | 10 min 45 s (549.2 s) | 1 min 13 s (39.1 s) |

  The cells, with the independent check of duplicates and stale chunks, are in the report's "Reproduce" section.
- **Never** point it at the frozen evaluation collection: it refuses `FROZEN_COLLECTION` (empty or unset: `scitech_chunks`) with "is the frozen evaluation collection". No index changes from W6-D4 to D22 unless approved.
- **Only new or changed papers are processed.** Each fetched record is compared with the one fetched for the same paper by the last successful run (`<data-dir>/state/incremental-seen.json`); unchanged papers skip `clean`, `embed` and the load. When nothing is left, the run logs `incremental: nothing changed` and leaves the watermark as it is. To force a full re-run of the watermark range, delete that file.
- **One run at a time:** a run holds `<data-dir>/state/incremental.lock`. A second run stops at once with "another incremental run holds ..." and exit code 1. A lock left by a process that is gone is taken over, and any lock older than 3 hours is taken over (a run takes about 10 minutes). A restarted container keeps its host name and reuses low process ids, so a lock whose id is the new run's own or its parent's counts as gone too.
- Without `--rebuild-bm25` it does not rebuild the BM25 index, so incremental papers are found only by the dense half of hybrid retrieval, and BM25 keeps the old text of replaced papers, until the index is rebuilt (#119).

### Scheduled runs (ADR 0011, W7-D6-FAO-1; not merged before Gate W7)
The `ingest` container (`docker/ingest/`) runs `incremental-run` on the live collection every 2 hours, on the hour (UTC), and rebuilds its BM25 index after each load. The frozen `scitech_chunks` and `data/index/bm25` are only read, once, by the setup.

| Setting (`.env`) | Default | Meaning |
|---|---|---|
| `INGEST_EVERY_HOURS` | 2 | Hours between runs: 1, 2, 3, 4, 6, 8, 12 or 24; runs start at the hours divisible by it |
| `INGEST_COLLECTION` | `scitech_chunks_live` | The live collection the demo backend uses |
| `BM25_LIVE_DIR` | `data/index/bm25-live` | Its BM25 index (the backend's `BM25_INDEX_DIR` in the live setup) |
| `FROZEN_COLLECTION` | `scitech_chunks` | Refused by `incremental-run` |
| `INGEST_RUN_NOW` | 0 | 1: also run once when the container starts |

1. **Once, set up the live index.** This loads the bulk chunks and vectors (`data/processed/chunks`, `data/processed/embeddings`, or the release zip `data-2026-10-17`) into `scitech_chunks_live`, copies `data/index/bm25` to `data/index/bm25-live`, and runs the first catch-up from 2026-10-10 to today. The load took 135.2 s on FAO's laptop (#91). The catch-up embedded 2,744 papers in 549 s on a Kaggle CPU (#124).
   ```bash
   docker compose run --rm ingest setup-live.sh
   ```
   It stops if `data/index/bm25-live` exists already, and if `INGEST_COLLECTION` is the frozen collection.
   If the load and copy passed but the first run (the catch-up) failed, delete nothing: run the catch-up alone. It goes on from the watermark once there is one.
   ```bash
   docker compose run --rm ingest catch-up.sh
   ```
2. **Start the schedule** with the stack: `INGEST_ENABLED=1` (W7-D7-DAT-1) and `make up`, or `docker compose up -d ingest`. Each run's output is in `docker compose logs ingest` and is appended to `data/logs/incremental.log` between `=== run started <time>` and `=== run ended <time>, exit code <n>` lines.
3. **Check a run** in the log:
   - `incremental: N of M papers new or changed`, then the usual `load:` line;
   - `bm25: C chunks of scitech_chunks_live indexed in S s -> data/index/bm25-live`;
   - `incremental: watermark ...`.
   A run with nothing new logs `incremental: nothing changed` and ends with exit code 0. Count the soak runs (W8-D6-DAT-1) with `grep -c "=== run ended" data/logs/incremental.log`, and the failed ones with `grep "=== run ended" data/logs/incremental.log | grep -vc "exit code 0"`.
4. **Stop it:** `docker compose stop ingest`, or `INGEST_ENABLED=0` and `make up`. The live index stays as it is. To start again from the frozen copy, stop it, delete `data/index/bm25-live`, `data/state/incremental.json` and `data/state/incremental-seen.json`, drop the collection (PowerShell: `Invoke-RestMethod -Method Delete http://localhost:6333/collections/scitech_chunks_live`), and run step 1 again.

Notes:
- **BM25 rebuild:** the new index is built from the live collection's own payloads (Qdrant scroll), so a replaced paper's old text is gone and no run's chunk files are needed. It is written to `bm25-live.next` and switched in with two renames, so a reader sees the old index or the new one. A failed build leaves the old one in place, and the watermark does not move, so the next run repeats the load and the build.
- **Laptop sleep:** nothing runs while Windows sleeps (the Docker VM is paused). For the soak, set "When plugged in, put my device to sleep after" to Never. A missed hour is not run later; the next run catches up its records.
- **Disk:** each run with new papers keeps about 1-2 MB under `data/processed/incremental/`. The raw fetch file in `data/raw/arxiv-oai/` is deleted when the run has passed (or found nothing changed); its `.manifest.json` stays. A failed run keeps it for the retry. The live copy adds about 610 MiB in Qdrant (Docker's disk) and 177 MiB for BM25 in `data/` (`index_profile.md` section 4).
- **Memory:** the BM25 build peaked at 1,184 MB (DAT's laptop, bulk index); `clean` starts Spark with at most 4 GB of driver memory. Record the container's peak (`docker stats`) on the first real run.
- **Not covered:** deleted arXiv records stay until a full rebuild (ADR 0008).
- Deleted arXiv records are counted in the fetch manifest but stay in the index until the next full rebuild.

## 7. Scaling measurements
`pipelines/scripts/scaling.py` (W6-D2-FAO-1, #96) builds the index at 10% and 50% of the corpus next to the full one, from the vectors already computed (nothing is embedded again), and profiles each size with `index_profile.py`:
```bash
PYTHONPATH=agent/src:pipelines/src python pipelines/scripts/scaling.py --out-dir data/reports/scaling
```
- It needs the full load and BM25 build done first (it reads `processed/index/_load_manifest.json` and `index/bm25`), Qdrant in Docker (it runs `docker compose restart qdrant` before each size) and about 1.5 GiB of Qdrant storage for the three collections.
- The subsets go to `<QDRANT_COLLECTION>_10pct` and `_50pct`, and their BM25 indexes to `data/index/bm25-10pct` and `-50pct`. Re-running reuses them; `--force` builds them again. Delete these collections when done: they are not used by the app.
- Results of 2026-10-22 on FAO's laptop (`pipelines/reports/scaling.md`): hybrid p95 131 to 135 ms at every size; BM25 grows with the corpus (p50 1.2, 4.8, 8.1 ms); dense stays at 81 to 93 ms p50, mostly query embedding on the CPU. One run of 100 queries per size, so differences of a few ms are noise.
- Charts: `python pipelines/scripts/scaling_charts.py` writes two SVG charts next to `scaling.csv` (W7-D2-FAO-1, #121).

## 8. Not covered yet
- Restoring the frozen snapshot for the final evaluation (W6-D4-FAO-1, `evaluation/SNAPSHOT.md`).
