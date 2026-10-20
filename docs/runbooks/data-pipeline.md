# Runbook: data pipeline (arXiv snapshot to a loaded Qdrant index)

Task: W4-D5-FAO-1 (draft; final version W6-D3-FAO-1 adds incremental ingestion, scaling notes and more troubleshooting).
Commands: `pipelines/AGENTS.md` (every option) and `pipelines/README.md` (setup, what runs where, the Kaggle recipes). Decisions: ADR 0003 (corpus), ADR 0005 (engine), ADR 0007 (embedding model), ADR 0008 (incremental ingestion).

> Status: draft written on 2026-10-20 (D07). `run-all` is in review (#92) and the README's Kaggle recipes are on #60. Times are the measured ones from the FAO journal (W2, W3) unless marked otherwise.

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
| Qdrant storage | not measured yet | index profile, W3-D5-FAO-1 |

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

Measured times for the full corpus:

| Step | Time | Where |
|---|---|---|
| download | 150 s | FAO's laptop (19.8 MB/s) |
| clean | 82-111 s for the whole process, peak memory 2.7-2.9 GB | Kaggle CPU notebook (4 CPUs) |
| validate | seconds | anywhere |
| chunk | 14-18 s | Kaggle or laptop |
| embed | 14.4 min (bge-small), 43.8 min (bge-base) | Kaggle T4 |
| load | 106.3 s (121,926 bge-small points, 4-17 s per part) | Kaggle CPU notebook, Qdrant 1.19.2 |

`run-all` writes each step's output to `<data-dir>/logs/run-all-<UTC time>/<nn>-<step>.log` and a summary `run-all.json` (exit code and seconds per step). Keep the folder of the run you report on.

## 3. Small rebuild (weak machine, or to try the steps)
```bash
python -m scitech_pipelines run-all --limit 2000 --device cpu --model "$EMBEDDING_MODEL"
```
- `--limit N` keeps the first N `cs.CL` records of the snapshot. Everything after the download goes to `<data-dir>/limit-<N>/` and into the collection `<QDRANT_COLLECTION>_limit_<N>`, so the full data and the full index are never touched.
- The download is still the full 1.86 GB zip, because Kaggle only serves the whole snapshot. With a snapshot already on disk, add `--snapshot <path>` to skip it.
- Without any download: the records of `pipelines/tests/fixtures/sample.jsonl` (in git), for example `--snapshot pipelines/tests/fixtures/sample.jsonl --limit 10`. Up to `chunk` (`--to chunk`), this took 16.9 s on a Linux VM (4 CPUs), mostly Spark's start-up.
- Time for `--limit 2000` end to end: *not measured yet* (W4-D2-FAO-1 records it in the README).

## 4. Verify a build
The counts must chain, for snapshot 307:

| Manifest | Field | Expected |
|---|---|---|
| `processed/documents/_clean_manifest.json` | `counts.records_out` | 121,860 |
| `processed/chunks/_chunk_manifest.json` | `counts.chunks` | 121,926 |
| `processed/embeddings/_embed_manifest.json` | `counts.chunks` | 121,926 |
| `processed/index/_load_manifest.json` | `counts.points` | 121,926 |

- `validate --golden evaluation/golden_set/golden.jsonl` checks the documents and that every golden `relevant_doc_ids` exists. `run-all` runs it on full runs.
- `pipelines/scripts/golden_coverage.py --chunks data/processed/chunks --qdrant` checks the same ids against the chunks and the loaded collection (#69). On 2026-10-20 all 57 ids of gs-001 to gs-047 (golden set of #88) were in the chunks.
- `_load_manifest.json` holds `index_snapshot`, the id that evaluation runs cite.
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
| Dense recall lower than ADR 0007 through Qdrant | Qdrant's default approximate search (gs-016 drops out) | See #87: exact search or a larger `hnsw_ef` reproduces ADR 0007 |
| Kaggle notebook: data of a previous run gone | `/kaggle/working` lasts only for the session | Keep inputs as Kaggle datasets; don't use *Save Version* with Qdrant's storage in `/kaggle/working` |

## 6. Not covered yet
- Incremental ingestion (ADR 0008, W5): the steps for new records since the watermark.
- Qdrant storage size and RAM (W3-D5-FAO-1) and the scaling numbers (W6-D2-FAO-1).
- Restoring a frozen snapshot for the final evaluation (W6-D4-FAO-1).
