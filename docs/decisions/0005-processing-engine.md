# 0005. Processing engine for the processing tier: TBD

- Status: proposed
- Date: 2026-10-15
- Deciders: FAO (author), DAT (reviewer)

## Context
ADR 0003 chose two tiers: the processing tier reads the whole Kaggle arXiv snapshot (3,205,432 records, 5.61 GB of JSON Lines) on every rebuild and keeps `cs.CL` (121,860 records). The index tier holds only `cs.CL`. This ADR picks the engine for the processing tier: `clean` (W2-D2-FAO-1) and any later batch job over the snapshot.

Constraints:
- The brief prefers PySpark in local mode, because this is a Big Data course, if a measurement shows it is workable. There is no instructor requirement (brief, decisions table).
- No cluster is available. The engine runs on one machine: a member's Windows laptop (8 CPUs, 17 GB RAM, little free disk on C:) or a free Colab/Kaggle VM.
- PySpark needs Java 17 or newer and does not run natively on Windows without extra setup (`winutils`), so on Windows it runs in WSL2 or on Colab.
- The rebuild is a batch job that runs a few times in the project, so a few minutes per run is acceptable. Memory must fit the machine.

## Options considered
1. **PySpark 4.x, local mode** (`local[*]`).
2. **DuckDB** (in-process SQL engine).
3. **Polars** (in-process DataFrame library).

Plain Python streaming (the 77 s profile pass in ADR 0003) is the baseline. It is not an option for `clean`, because it has no Parquet writer, joins or SQL.

## Measurement
Job, identical for every engine (`pipelines/scripts/bench_engines.py`): load JSON Lines, keep records whose `categories` contain `cs.CL`, take the year of the first version, write the kept records to Parquet, count them by year. The script measures wall time including engine start-up, and peak resident memory of the process and its children (the Spark JVM is a child). Each table row is the second of two runs, so files are in the OS cache. All engines returned the same per-year counts, unless a row says otherwise.

Inputs:
- `sample.jsonl`: the 1,000-record `cs.CL` sample from W1-D2-FAO-1 (2.0 MB).
- `slice-200k.jsonl`: the first 200,000 lines of the snapshot (302.6 MB, old ids `0704.x`, 268 `cs.CL` records).
- The full snapshot (5.61 GB), where marked.

**Colab CPU VM** (TBD CPUs, TBD GB RAM; DuckDB TBD, Polars TBD, PySpark TBD, Java TBD):

| Input | Engine | Wall time (s) | Peak memory (MB) | Records kept |
|---|---|---:|---:|---:|
| sample.jsonl (2.0 MB) | DuckDB | TBD | TBD | 1,000 |
| sample.jsonl (2.0 MB) | Polars | TBD | TBD | 1,000 |
| sample.jsonl (2.0 MB) | PySpark | TBD | TBD | 1,000 |
| slice-200k.jsonl (302.6 MB) | DuckDB | TBD | TBD | 268 |
| slice-200k.jsonl (302.6 MB) | Polars | TBD | TBD | 268 |
| slice-200k.jsonl (302.6 MB) | PySpark | TBD | TBD | 268 |
| full snapshot (5.61 GB) | DuckDB | TBD | TBD | 121,860 |
| full snapshot (5.61 GB) | PySpark | TBD | TBD | 121,860 |

**Windows 11 laptop** (8 CPUs, 17 GB RAM, Python 3.14; DuckDB 1.5.6, Polars 2.0.0; measured 2026-10-14, first run, no PySpark):

| Input | Engine | Wall time (s) | Peak memory (MB) | Records kept |
|---|---|---:|---:|---:|
| sample.jsonl (2.0 MB) | DuckDB | 3.65 | 51 | 1,000 |
| sample.jsonl (2.0 MB) | Polars | 15.45 | 78 | 1,000 |
| slice-200k.jsonl (302.6 MB) | DuckDB | 0.90 | 232 | 268 |
| slice-200k.jsonl (302.6 MB) | Polars | 4.63 | 1,866 | 268 |

The two machines differ, so compare engines within one table only. On the 2 MB sample, start-up dominates the time.

**Full snapshot, estimate, not measured** (slice time x 18.5, the size ratio; assumes time and memory grow linearly): TBD for PySpark. From the laptop: DuckDB about 17 s; Polars about 86 s and about 35 GB peak memory with eager `read_ndjson`, which does not fit 17 GB, so Polars needs `scan_ndjson` with streaming for the full file.

**Setup effort:**

| Engine | Install | Runs on Windows natively | Notes |
|---|---|---|---|
| DuckDB | `pip install duckdb` | yes | One wheel, no other dependency |
| Polars | `pip install polars` | yes | One wheel; the full file needs the streaming API |
| PySpark | `pip install pyspark` plus Java 17+ | no: WSL2 or Colab | TBD (time to set up on Colab). JVM start-up adds a fixed cost per run |

## Decision
TBD after the Colab numbers.

## Consequences
TBD after the decision. To cover in any case:
- Where `clean` (W2-D2-FAO-1) runs, given that PySpark needs WSL2 or Colab on Windows and C: has little free space.
- What CI needs: if `clean` uses PySpark, its tests need Java on the runner (GitHub's `ubuntu-latest` has it) and `pyspark` in `pipelines/requirements.txt` (W1-D5-DAT-2 installs that file in CI).
- What to revisit if the measured full-snapshot run does not fit the machine's memory.
