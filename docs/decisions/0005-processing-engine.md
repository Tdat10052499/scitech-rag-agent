# 0005. Processing engine: PySpark in local mode, DuckDB for checks

- Status: accepted (2026-10-16, DAT review on #30)
- Date: 2026-10-15
- Deciders: FAO (author), DAT (reviewer)

## Context
ADR 0003 chose two tiers: the processing tier reads the whole Kaggle arXiv snapshot (3,205,432 records, 5.61 GB of JSON Lines) on every rebuild and keeps `cs.CL` (121,860 records); the index tier holds only `cs.CL`. This ADR picks the engine for the processing tier: `clean` (W2-D2-FAO-1) and any later batch job over the snapshot.

Constraints:
- The brief prefers PySpark in local mode, because this is a Big Data course, if a measurement shows it is workable. There is no instructor requirement (brief, decisions table).
- No cluster is available. The engine runs on one machine: a member's Windows laptop (8 CPUs, 17 GB RAM, little free disk on C:), a Linux machine or WSL2, or a free Colab/Kaggle VM.
- PySpark needs Java 17 or newer and does not run natively on Windows without extra setup (`winutils`), so on Windows it runs in WSL2 or on Colab.
- The rebuild is a batch job that runs a few times in the project, so a few minutes per run is acceptable. Memory must fit the machine.

## Options considered
1. **PySpark 4.x, local mode** (`local[*]`).
2. **DuckDB** (in-process SQL engine).
3. **Polars** (in-process DataFrame library).

Plain Python streaming (the 77 s profile pass in ADR 0003) is the baseline. It is not an option for `clean`, because it has no Parquet writer, joins or SQL.

## Measurement
Job, identical for every engine (`pipelines/scripts/bench_engines.py`): load JSON Lines, keep records whose `categories` contain `cs.CL`, take the year of the first version, write the kept records to Parquet, count them by year. The script measures wall time including engine start-up (for Spark: JVM start, schema inference and the job), and peak resident memory of the process and its children (the Spark JVM is a child). In every run all engines returned the same per-year counts.

The two machines differ, so compare engines within one table only.

**A. Windows 11 laptop, real data** (8 CPUs, 17 GB RAM, Python 3.14, DuckDB 1.5.6, Polars 2.0.0; 2026-10-14, first run). No PySpark: it does not run natively on Windows.

| Input | Engine | Wall time (s) | Peak memory (MB) | Records kept |
|---|---|---:|---:|---:|
| `sample.jsonl`, 1,000 `cs.CL` records (2.0 MB) | DuckDB | 3.65 | 51 | 1,000 |
| `sample.jsonl`, 1,000 `cs.CL` records (2.0 MB) | Polars | 15.45 | 78 | 1,000 |
| `slice-200k.jsonl`, first 200,000 snapshot lines (302.6 MB) | DuckDB | 0.90 | 232 | 268 |
| `slice-200k.jsonl`, first 200,000 snapshot lines (302.6 MB) | Polars | 4.63 | 1,866 | 268 |

On the 2 MB sample, start-up and first import dominate the time.

**B. Linux VM, synthetic data with the snapshot's schema** (4 CPUs, 17 GB RAM, Python 3.13, OpenJDK 21, DuckDB 1.5.6, Polars 2.0.0, PySpark 4.2.0; 2026-10-15). The real snapshot was not on this machine, so the inputs repeat the 20 real records of `pipelines/tests/fixtures/sample.jsonl` with unique ids; every 746th (slice) or 26th (full size) line keeps `cs.CL` and the rest get other categories. The slice table shows the second of two runs (warm OS cache).

| Input | Engine | Wall time (s) | Peak memory (MB) | Records kept |
|---|---|---:|---:|---:|
| synthetic slice, 200,000 lines (342.5 MB) | DuckDB | 0.46 | 166 | 269 |
| synthetic slice, 200,000 lines (342.5 MB) | Polars | 2.48 | 1,773 | 269 |
| synthetic slice, 200,000 lines (342.5 MB) | PySpark | 16.36 | 1,492 | 269 |
| synthetic, about the size of the snapshot: 3,205,432 lines (5.49 GB) | DuckDB | 5.30 | 626 | 123,286 |
| synthetic, about the size of the snapshot: 3,205,432 lines (5.49 GB) | PySpark | 34.61 | 1,057 | 123,286 |

Polars was not run at full size: with eager `read_ndjson` its peak memory grows with the input (1.8 GB for 0.3 GB of JSON in both tables), which extrapolates to about 30-35 GB for the full snapshot (estimate). Polars would need `scan_ndjson` with the streaming engine instead.

Limits of table B: 20 distinct records repeated make the data more uniform than the real snapshot (Spark's schema inference and the JSON parsers see only one shape), and the file was just written, so it was in the OS cache. Real-data times will be higher. The first, cold run of the slice took 5.15 s (DuckDB), 12.39 s (Polars) and 44.46 s (PySpark). A run of the same script on Colab with the real `slice-200k.jsonl` and the real snapshot is a follow-up (below), not a condition of this decision.

**Setup effort:**

| Engine | Install | Runs on Windows natively | Notes |
|---|---|---|---|
| DuckDB | `pip install duckdb` | yes | One wheel, no other dependency |
| Polars | `pip install polars` | yes | One wheel; the full file needs the streaming API |
| PySpark | `pip install pyspark` plus Java 17+ | no: WSL2, Linux or Colab | About 15 s of JVM start-up per run, independent of input size; the installed package is about 480 MB |

## Decision
**PySpark 4.x in local mode is the engine of the processing tier (`clean` and later batch jobs over the snapshot). DuckDB is used for profiling, quick checks and tests that compare counts, and is the fallback if Spark becomes a blocker.**

- PySpark is workable at our scale: on the synthetic full-size file (5.49 GB, 3.2M lines) the whole job took 35 s with about 1.1 GB peak memory on 4 CPUs. Even if real data is 10 times slower (estimate), a rebuild stays within minutes and within the memory of every machine we have. This meets the brief's condition, so the brief's preference applies.
- DuckDB is faster (5.3 s, 0.6 GB on the same file) and easier to install, and would be the choice on speed alone. We still pick Spark because the course is assessed on big-data tooling, and Spark's DataFrame API is the one that scales from `local[*]` to a cluster without rewriting `clean`. The extra 30 s per rebuild is not a cost that matters for a job that runs a few times.
- Polars is not chosen: its eager reader needs memory proportional to the input (about 30-35 GB for the snapshot, estimate), and it brings no advantage over DuckDB for checks.

## Consequences
- `clean` (W2-D2-FAO-1) runs where Java 17+ exists: WSL2 on FAO's laptop or Colab. Windows-native runs are not supported; `pipelines/AGENTS.md` and the runbook must say so.
- `pipelines/requirements.txt` gains `pyspark` (W2-D2-FAO-1). CI already installs that file (W1-D5-DAT-2); the first PR that adds `pyspark` checks that `ubuntu-latest` provides Java 17+ (if not, DAT adds `actions/setup-java` to `ci.yml`). Tests use one shared `local[1]` session on the 20-record fixture, which adds about 15 s of JVM start-up and the install of `pyspark` (about 480 MB, pip cache helps) to each CI run.
- Spark tests **skip**, not fail, when PySpark or Java is missing (`pytest.importorskip("pyspark")` plus a skip when no `java` is found), so `make test` keeps working for Windows members without Java; they run in CI. `pipelines/AGENTS.md` states this (W2-D2-FAO-1).
- The Spark job must not rely on schema inference over the whole file in production: `clean` passes an explicit schema for the snapshot fields (faster, and it fails loudly if Kaggle changes a field).
- Reproducibility checks compare Spark's output counts with a DuckDB query over the same file; a mismatch fails the run.
- Scaling numbers for the report (`pipelines/reports/scaling.md`) come from the real `clean` run on the full snapshot, not from table B.
- Follow-up (FAO, before or with W2-D2-FAO-1 on D05): run `bench_engines.py` with PySpark on the real `slice-200k.jsonl` (Colab or WSL2), and on the real snapshot if possible, and add the rows here. The revisit rule below only works if this is measured. Revisit this decision if PySpark on the real snapshot takes more than 15 minutes or more than 8 GB of memory, or if WSL2/Colab is unavailable when `clean` must run; then switch to DuckDB, which runs the same job natively on Windows.
