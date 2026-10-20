# pipelines/: from an empty `data/` to a loaded index

How to rebuild the corpus, step by step. The options of every command are in `AGENTS.md` (this folder) and in `python -m scitech_pipelines <step> --help`; the reasons behind the choices are in ADR 0003 (corpus), ADR 0005 (engine) and ADR 0007 (embedding model).

The `load` into Qdrant came with W3-D3-FAO-1 (#67); its time below is from a full-scale rehearsal of it on Kaggle. The one-command `run-all` (W4-D2-FAO-1) does not exist yet; this file gets its command, time and disk use when it is merged.

## What runs where

| Step | Command | Output | Where it runs | Time (measured) | Disk |
|---|---|---|---|---|---|
| 1. download | `download --source arxiv` | `data/raw/arxiv/arxiv-metadata-oai-snapshot.json` + `manifest.json` | anywhere, needs a Kaggle login | 150 s on FAO's laptop (1.86 GB zip at 19.8 MB/s, extraction, checksum) | 5.61 GB; 7.5 GB at the peak while the zip is still there |
| 2. clean | `clean` | `data/processed/documents/year=*/` (Parquet) + `_clean_manifest.json` | **Java 17+ only**: Kaggle CPU notebook, WSL2 or Linux; not native Windows | 82-111 s for the whole process on a Kaggle CPU notebook (4 CPUs), peak memory 2.7-2.9 GB | 95 MB |
| 3. validate | `validate --golden evaluation/golden_set/golden.jsonl` | PASS/FAIL per check (exit code 1 on a failure) | anywhere (DuckDB) | seconds (not timed on the full data) | none |
| 4. profile (optional) | `profile --clean-peak-mb <MB>` | `pipelines/reports/data_profile.md` and `.json` | where the raw snapshot is (DuckDB) | 22.4 s on FAO's laptop | none |
| 5. chunk | `chunk` | `data/processed/chunks/chunks.parquet` + `_chunk_manifest.json` | anywhere (DuckDB) | 14.1 s on Kaggle, 18.4 s on FAO's laptop | 101 MB |
| 6. embed | `embed --model <EMBEDDING_MODEL>` | `data/processed/embeddings/part-*.parquet` + `_embed_manifest.json` | GPU notebook (Kaggle T4); CPU only for small runs | T4: 14.4 min (`bge-small-en-v1.5`), 43.8 min (`bge-base-en-v1.5`) | 198 MB (small), 385 MB (base) |
| 7. load | `load` | Qdrant collection `QDRANT_COLLECTION` + `data/processed/index/_load_manifest.json` | where Qdrant runs (`make up`, or the release binary on Kaggle) | 106.3 s for 121,926 bge-small vectors on a Kaggle CPU notebook, Qdrant 1.19.2 (4-17 s per part) | Qdrant storage: not measured yet (index profile, W3-D5-FAO-1) |

Full corpus: arXiv `cs.CL`, Kaggle snapshot version 307: 3,205,432 records in, 121,860 documents, 121,926 chunks (2026-10-16/17 runs; journal `docs/journal/FAO/W2.md`). On a CPU, embedding the full corpus would take about 12 h with bge-small and 38 h with bge-base (estimate from 2.8 and 0.9 records/s on a Colab CPU, `docs/03-data-sources.md`), so use a GPU.

## Setup
From the repository root, in the project's virtual environment:

```bash
python -m pip install -r pipelines/requirements.txt     # every step except embed
python -m pip install -r pipelines/requirements-embed.txt  # embed only (PyTorch, several GB)
export PYTHONPATH=pipelines/src                          # PowerShell: $env:PYTHONPATH = "pipelines\src"
python -m scitech_pipelines --help
```

- `download` needs a Kaggle account: `kaggle auth login` once (the token stays in your user profile, never in the repository).
- `clean` needs Java 17 or newer (`java -version`). Java 8 counts as none: `clean` then stops with an error and its tests skip.
- Every step writes under `--data-dir` (env `DATA_DIR`, default `data`). `data/` is git-ignored; on a small `C:` drive, point it at another disk (for example a junction from `data\raw` to `D:\scitech-data\raw`).

## Full rebuild
```bash
python -m scitech_pipelines download --source arxiv
python -m scitech_pipelines clean            # Java 17+: see "clean on Kaggle" below
python -m scitech_pipelines validate --golden evaluation/golden_set/golden.jsonl
python -m scitech_pipelines chunk
python -m scitech_pipelines embed --model "$EMBEDDING_MODEL"   # GPU notebook: see below
make up                                      # Qdrant (docker compose), then:
PYTHONPATH=pipelines/src:agent/src python -m scitech_pipelines load
```

Every step can be re-run: `download` skips a complete source, `clean` and `chunk` replace their own output, `embed` resumes at the first missing part (or skips a complete output), and `load` resumes at the first part not loaded (it upserts by `uuid5(chunk_id)`, so a re-run never duplicates points). `--force` starts `download`, `embed` or `load` again.

**clean on Kaggle (no Java on the laptop).** New notebook, Accelerator *None* (no GPU quota used), Internet *on*, **Add Input** > the `Cornell-University/arxiv` dataset. In a cell:

```python
from pathlib import Path
!git clone -q --depth 1 https://github.com/Tdat10052499/scitech-rag-agent
!pip -q install "pyspark>=4" "duckdb>=1.1"
SNAPSHOT = next(Path("/kaggle/input").rglob("arxiv-metadata-oai-snapshot.json"))
!cd scitech-rag-agent && PYTHONPATH=pipelines/src python -m scitech_pipelines --data-dir /kaggle/working/data clean --input {SNAPSHOT}
```

Then zip `/kaggle/working/data/processed/documents` and download it into `data/processed/documents` on your machine, or run `chunk` in the same notebook.

**embed on Kaggle.** Accelerator *GPU T4*, Internet *on* (the model comes from Hugging Face), and the chunks as input (the private dataset below, or the output of the notebook above). Run `embed --input <chunks folder> --out /kaggle/working/embeddings/<model> --model <model>` with **Save & Run All (Commit)**, so it runs in the background and its output stays attached to the notebook version.

**load on Kaggle (no Docker).** CPU notebook, Internet *on*, the chunks and the embeddings as inputs, the repository cloned and `pipelines/requirements.txt` installed as for `clean` above. Start the Qdrant release binary that `docker-compose.yml` pins, then load:

```python
!wget -q https://github.com/qdrant/qdrant/releases/download/v1.19.2/qdrant-x86_64-unknown-linux-musl.tar.gz -O /kaggle/working/qdrant.tgz
!tar xzf /kaggle/working/qdrant.tgz -C /kaggle/working
import os, subprocess, time, urllib.request
os.makedirs("/kaggle/working/qdrant-storage", exist_ok=True)
qdrant = subprocess.Popen(["/kaggle/working/qdrant"], cwd="/kaggle/working",
    env={**os.environ, "QDRANT__STORAGE__STORAGE_PATH": "/kaggle/working/qdrant-storage",
         "QDRANT__TELEMETRY_DISABLED": "true"},
    stdout=open("/kaggle/working/qdrant.log", "w"), stderr=subprocess.STDOUT)
for _ in range(30):  # wait until Qdrant answers
    try:
        urllib.request.urlopen("http://localhost:6333/healthz"); break
    except OSError:
        time.sleep(1)
os.environ.update(QDRANT_URL="http://localhost:6333", QDRANT_COLLECTION="scitech_chunks")
!cd scitech-rag-agent && PYTHONPATH=pipelines/src:agent/src python -m scitech_pipelines --data-dir /kaggle/working/data load --chunks <chunks folder> --vectors <embeddings/bge-small-en-v1.5 folder>
```

The collection lives only as long as the notebook session. Don't use *Save Version* with Qdrant's storage under `/kaggle/working`: it would be kept as notebook output.

## Small run (weak machine, or to try the steps)
The 20 records of `pipelines/tests/fixtures/sample.jsonl` (in git) go through every step in seconds. Measured on a Linux VM (4 CPUs): `clean` 22 s including Spark start-up, `validate` 0.3 s, `chunk` 0.2 s; 20 documents, 20 chunks, under 200 KB.

```bash
python -m scitech_pipelines --data-dir data/small clean --input pipelines/tests/fixtures/sample.jsonl --sample-size 0
python -m scitech_pipelines --data-dir data/small validate
python -m scitech_pipelines --data-dir data/small chunk
python -m scitech_pipelines --data-dir data/small embed --model "$EMBEDDING_MODEL" --device cpu
PYTHONPATH=pipelines/src:agent/src python -m scitech_pipelines --data-dir data/small load --collection scitech_small
```

The small `load` goes into its own collection (`--collection`), so it never mixes with the full index.

`clean` still needs Java 17+. Without it, skip the rebuild and take the processed data:
- **Documents and chunks:** the private Kaggle dataset `minhchinhnguyen/scitech-cscl-v307` (71 files: `documents/` and `chunks/` of the full corpus). Ask FAO to add your Kaggle account, then add it as a notebook input or download it into `data/processed/`.
- **Vectors:** the output of FAO's Kaggle notebook "Embedding job W3-D2-FAO-1 [blocking]", Version 1 (`embeddings/bge-small-en-v1.5`, `embeddings/bge-base-en-v1.5`), shared the same way.
- `embed --limit N` embeds only the first N chunks, for a quick CPU run on the full chunks.

## Check a result
- `_clean_manifest.json`, `_chunk_manifest.json`, `_embed_manifest.json` and `_load_manifest.json` hold the counts of each run; `documents -> chunks -> vectors -> points` must be 121,860 -> 121,926 -> 121,926 -> 121,926 for snapshot 307. `load` fails if the points do not equal the chunks.
- `validate` re-checks the documents against the clean manifest; `embed` checks its own output (count, distinct ids, dimension) and fails if it is wrong.
- Data files never go into git (`data/` is ignored); share them through Kaggle.
