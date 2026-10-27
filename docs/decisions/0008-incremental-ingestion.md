# 0008. Incremental ingestion: daily OAI-PMH harvest with a date watermark

- Status: accepted (2026-10-27, DAT's review on #124). The OAI-PMH set is settled by the live check of 2026-10-17, one real day went through fetch, clean, validate and chunk on 2026-10-19, and the end-to-end live test passed on 2026-10-27 (all three below); scheduling decided by that test (point 6)
- Date: 2026-10-17 (drafted early for W3-D4-FAO-1); live test and scheduling 2026-10-27 (W5-D4-FAO-1)
- Deciders: FAO (author), DAT (reviewer)

## Context
The index holds every arXiv record whose `categories` contain `cs.CL`, bulk-loaded from the Kaggle snapshot (ADR 0003). Incremental ingestion adds new papers between rebuilds through the same clean -> chunk -> embed -> load steps.

Facts and constraints (sources: ADR 0003, `docs/03-data-sources.md`):
- Volume: 23,762 new `cs.CL` records in 2025 including cross-lists (measured), about 460 per week (yearly total / 52), so about 90 per announcement day (estimate: 460 / 5).
- arXiv announces new papers around 22:30 ET, Sunday to Thursday; metadata is updated nightly.
- Rate limit: one request every 3 s, one connection at a time, for the API, OAI-PMH and RSS together, across all our machines.
- The Kaggle snapshot is updated about weekly (version 307 on 2026-10-10, inferred from the dataset metadata).
- Cross-lists are 20-28% of `cs.CL` per year since 2018 (measured). ADR 0003 left open whether the OAI-PMH set `cs:cs:CL` returns them.
- Scope after the replan: a scheduled batch with a watermark only. Kafka is cut (ADR 0010, cut-list item 1; brief, decisions table: arXiv publishes in daily batches). Incremental ingestion itself is cut-list item 6: it stays only if the D14 live test (W5-D4-FAO-1) passes.
- `clean` is PySpark and needs Java 17+, which the Windows laptop does not have (ADR 0005); `chunk`, `validate` and `load` run on Windows.

## Options considered
Source of new records:
- (a) Download the weekly Kaggle snapshot again and diff by `doc_id`. Same file and code as the bulk load, but 5.61 GB per week for about 460 new records, up to a week late, and changed records must be detected by `update_date`.
- (b) OAI-PMH `ListRecords`, `from=`/`until=` datestamps, set `cs:cs:CL`. The smallest harvest, and arXiv's recommended way to keep a copy up to date. Misses 20-28% of new papers if the set holds primary `cs.CL` only.
- (c) OAI-PMH set `cs`, keeping records whose `categories` contain `cs.CL`. Covers cross-lists if (b) misses them, but harvests all of `cs` (more records and pages per day, number not measured yet). It could still miss cross-lists whose primary is outside `cs` (e.g. `eess.AS`, 1,734 records) if set membership follows the primary category.
- (d) arXiv search API, `cat:cs.CL` sorted by `submittedDate`. Meant for search (at most 2,000 results per call), returns Atom, which needs a second mapping to the snapshot fields, and a submission-date query does not see new versions of old papers.

Scheduling:
1. Manual command, run by FAO.
2. cron (WSL2) or Windows Task Scheduler on FAO's laptop.
3. GitHub Actions on a schedule. CI has no data and no Qdrant (`data/` is git-ignored, the index is local), so it could only remind someone to run the command.

## Decision
**Harvest arXiv OAI-PMH by datestamp with `incremental-fetch`, run the existing clean -> chunk -> embed -> load on that file only, and keep a date watermark that moves only after a successful load.**

1. **Fetch** (prototype in this PR): `python -m scitech_pipelines incremental-fetch --from <watermark> --until <yesterday, UTC> --set cs:cs:CL --category cs.CL --out <file>.jsonl`. It follows `resumptionToken`, waits at least 3 s between requests, retries 429/5xx with `Retry-After`, treats `noRecordsMatch` as zero records, and writes the records as JSON Lines in the Kaggle snapshot shape, plus `<file>.manifest.json` with the settings and counts. `--from` is the watermark day itself, not the day after: datestamps are days, and a day's records may still be arriving when it is first harvested. The overlap costs one day of records, and re-loading them is harmless (point 5).
2. **Set `cs:cs:CL`.** The rule written before the live check was: use `cs:cs:CL` if it contains cross-lists and has every `cs.CL` id that `cs` has. It does (table below): the same 304 ids as `cs` filtered on `cs.CL`, 99 of them cross-lists, in one request instead of two. ADR 0003's known risk (a set of primary `cs.CL` only) does not hold. `--category cs.CL` stays on as a guard.
3. **Process** the new file with the existing commands, each with its own output directory (`clean` replaces its `--out`, and `chunk` refuses an `--out` with other files):
   - `clean --input <file>.jsonl --out data/processed/incremental/<until>/documents`: the same Spark code as the bulk load, so normalisation exists once. It needs Java 17+: WSL2 on FAO's laptop or a Kaggle CPU notebook, not Windows. The simplest setup runs every step in WSL2.
   - `chunk`, then `embed` with the model of the index (`EMBEDDING_MODEL`, ADR 0007) on CPU. The live check harvested 304 records for one day (above the 90 estimated from the 2025 total; see the table). `bge-small-en-v1.5` (the model of ADR 0007) embedded 2.8 records/s on a Colab CPU (`docs/03-data-sources.md`), so 304 chunks take about 2 min (estimate; the live day of 2026-10-19 gave exactly one chunk per record). No GPU is needed.
   - `load` (W3-D3-FAO-1) into the same collection.
4. **Watermark**: `data/state/incremental.json` (git-ignored) with the last loaded `until` day, the set and category, the fetch manifest path and the point count after the load. It is written only after `load` succeeds and its count check passes (W5-D2-FAO-1); a failure at any step leaves it, so the next run repeats the same range. The first value is the date of the Kaggle snapshot of the bulk index (2026-10-10 for version 307). A run after missed days harvests all of them in one range.
5. **Idempotency**: `load` upserts by `chunk_id` (`<doc_id>#<chunk_index>`, stable), so re-running a range replaces points instead of adding them. A record's datestamp also changes when an old paper gets a new version (or its metadata is edited), so it is harvested again with its latest title and abstract and replaces the old chunks. `published_at` stays the v1 date (`created`) and `updated_at` becomes the new version's date. If the new abstract has fewer chunks, the old higher-numbered chunks would remain, so `load` must first delete the points of every `doc_id` it reloads (W5-D2-FAO-1). Accepted gap of delete-then-upsert (DAT's review of #76): the papers being replaced have no points between the delete and the upsert (0.3 to 2.4 s in the live test below), and if the upsert fails they stay missing until the next run, which repeats the range. `incremental-run` also refuses a `--model` other than the one in the bulk load's manifest for the same collection, since Qdrant checks only the vector size.
6. **Scheduling** (decided by W5-D4-FAO-1 on 2026-10-27): **one manual command, run on demand; no unattended schedule for v1.0.** GitHub Actions is not used. Reasons:
   - The command needs Java 17+, the embedding model and the serving Qdrant on one machine. FAO's laptop, where the serving Qdrant runs, has Java 8 and no WSL2 with Java 17 set up, so `clean` cannot run there yet; the live test ran in a Kaggle notebook against its own copy of the index, and a Kaggle notebook cannot reach the laptop's Qdrant.
   - The evaluation index is frozen at W6-D4 (2026-10-30), with no index changes until D22 (2026-11-06) unless approved, and incremental loads must not change it (Consequences). Before the presentation on 2026-11-10 the serving index needs new papers only for the demo, and one run catches up every missed day in one range (point 4): 17 days took 10 min 45 s on a Kaggle CPU.
   - To run it, on a machine with Java 17+ that reaches the serving Qdrant (`QDRANT_URL`, `QDRANT_COLLECTION`): `PYTHONPATH=pipelines/src:agent/src python -m scitech_pipelines incremental-run --model BAAI/bge-small-en-v1.5 --device cpu`.
   - If a machine with Java 17+ and the serving Qdrant becomes available (WSL2 on the laptop, or a Linux server), the daily schedule is one cron line, run after arXiv's nightly metadata update (not tested): `30 5 * * * cd <repo> && QDRANT_URL=http://localhost:6333 PYTHONPATH=pipelines/src:agent/src .venv/bin/python -m scitech_pipelines incremental-run --model BAAI/bge-small-en-v1.5 --device cpu >> data/logs/incremental.log 2>&1` (05:30 UTC, 12:30 in UTC+7). On Windows, a Task Scheduler task runs the same command through `wsl`.

## Live check: which set (run 2026-10-17)
Run on FAO's laptop (Windows PowerShell, repo root, `.venv` active, no Java needed): two harvests of one recent weekday before today, then a comparison of the ids. Each run takes a few requests.

```powershell
$env:PYTHONPATH = "pipelines/src"
$day = "2026-10-15"  # a recent weekday before today
python -m scitech_pipelines incremental-fetch --from $day --until $day --set cs:cs:CL --category cs.CL --out data/raw/arxiv-oai/check-cscl.jsonl
Start-Sleep 3
python -m scitech_pipelines incremental-fetch --from $day --until $day --set cs --category cs.CL --out data/raw/arxiv-oai/check-cs.jsonl
python -c "import json,datetime as t,email.utils as e; D=t.date.fromisoformat('$day'); r=lambda p:{d['id']:d for d in map(json.loads,open(p,encoding='utf-8'))}; a=r('data/raw/arxiv-oai/check-cscl.jsonl'); b=r('data/raw/arxiv-oai/check-cs.jsonl'); x=lambda s:sum(d['categories'].split()[0]!='cs.CL' for d in s.values()); o=lambda s:sum(not d['versions'] or (D-e.parsedate_to_datetime(d['versions'][0]['created']).date()).days>7 for d in s.values()); [print(n, len(s), 'records, cross-lists', x(s), ', v1 over 7 days old', o(s)) for n,s in (('cs:cs:CL',a),('cs',b))]; print('only cs:cs:CL', sorted(a.keys()-b.keys())); print('only cs', sorted(b.keys()-a.keys()))"
```

If a run fails with an HTTP or OAI error about the set, `https://oaipmh.arxiv.org/oai?verb=ListSets` lists the set names. The other counts (`harvested`, `deleted`, `not_in_category`, `pages`, `requests`, `seconds`) are in `data/raw/arxiv-oai/check-*.manifest.json`.

Result, run on FAO's laptop on 2026-10-17 with `$day = "2026-10-15"` (a Thursday), base URL `https://oaipmh.arxiv.org/oai`, this branch at `a86f6c9`:

| Same day: 2026-10-15 | set `cs:cs:CL` | set `cs`, filtered on `cs.CL` |
|---|---:|---:|
| Records harvested (manifest `harvested`) | 304 | 1,564 |
| Records kept with `cs.CL` (manifest `kept`) | 304 | 304 |
| of which cross-lists (first category not `cs.CL`) | 99 | 99 |
| of which first version more than 7 days old (new versions of old papers) | 15 | 15 |
| Pages / requests / seconds | 1 / 1 / 2.1 | 2 / 2 / 7.5 |
| Ids only in this set | none | none |
| Output file | 619,504 bytes | 619,504 bytes |

No deleted records on that day. The two files have the same size and the same ids (their checksums differ, so the record order differs). Cross-lists are 33% of the day (99 of 304), above the 20-28% per year of ADR 0003 (one day only). Not checked: papers whose primary category is outside `cs` (e.g. `eess.AS`) but cross-listed to `cs.CL`; the `cs` set could not show them either.

The day's volume, 304 records, is about 3 times the 90 per day estimated from the 2025 total. A datestamp day is a metadata-change day, not an announcement day, so it also holds the 15 new versions of old papers, and 2026 volume may be higher than 2025 (not measured). It stays small for every step.

## Live day: one real day through fetch, clean, validate and chunk (run 2026-10-19)
Run in a Kaggle CPU notebook ("ADR 0008 live day", Java 21, PySpark 4.0.4), branch at `742fd8e`, for the datestamp day 2026-10-16 (a Friday after snapshot 307 of 2026-10-10). The notebook ran these commands with `--data-dir /kaggle/working/data`:

```
incremental-fetch --from 2026-10-16 --until 2026-10-16 --set cs:cs:CL --category cs.CL --out data/raw/arxiv-oai/2026-10-16.jsonl
clean    --input data/raw/arxiv-oai/2026-10-16.jsonl --out data/processed/incremental/2026-10-16/documents --sample-size 0
validate --input data/processed/incremental/2026-10-16/documents
chunk    --input data/processed/incremental/2026-10-16/documents --out data/processed/incremental/2026-10-16/chunks
```

It then compared the cleaned ids with the bulk documents of snapshot 307 (Kaggle dataset `scitech-cscl-v307`) in DuckDB.

| Step | Result | Time |
|---|---|---:|
| `incremental-fetch` | 276 records harvested in 1 page / 1 request, 0 deleted, 276 kept with `cs.CL`; 576,700 bytes | 0.4 s |
| `clean` | 276 in, 276 out; DuckDB agrees; 0 dropped (no abstract, title or date), 0 duplicates | 13.0 s (24.1 s with Spark start-up) |
| `validate` | all 13 checks PASS, including the count against the clean manifest | 0.3 s |
| `chunk` | 276 documents -> 276 chunks; words per chunk median 199, p95 276, max 318 (under 320) | 0.1 s |

| The 276 cleaned records | Count |
|---|---:|
| First version (`published_at`) in 2026 | 272 |
| First version in 2023, 2024 or 2025 | 1, 2, 1 |
| Already in the bulk index (snapshot 307) | 89 (32%) |
| New to the index | 187 |

A third of the day's records are papers the index already has. Being in snapshot 307, their first version is older than 2026-10-10, and they were harvested again because they got a new version or a metadata change on 2026-10-16; at least 85 of the 89 are 2026 papers. That is the case of point 5: their chunks must replace the old ones, so the delete-then-upsert per `doc_id` in W5-D2-FAO-1 is needed on most days, not only in rare cases. `embed` and `load` were not run: `load` is W3-D3-FAO-1 (D09), and the end-to-end run with the watermark is W5-D4-FAO-1 (D14).

## Live test: two end-to-end runs with the watermark (run 2026-10-27)
Run in a Kaggle CPU notebook (Java 21, Qdrant 1.19.2) with `incremental-run` (#76) at `de6819d`, against a copy of the full bulk index (snapshot 307, 121,926 points). Full report: `pipelines/reports/incremental_test.md`.

| | Run 1: `--start 2026-10-10` | Run 2: same day again |
|---|---:|---:|
| Range | 2026-10-10 to 2026-10-26 | 2026-10-26 |
| Records kept / chunks | 2,744 / 2,758 | 177 / 178 |
| Papers already in the index (old points deleted) | 962 (966) | 177 (178) |
| Points before -> after | 121,926 -> 123,718 | 123,718 -> 123,718 |
| Duplicate chunk ids / stale chunks / missing chunks | 0 / 0 / 0 | 0 / 0 / 0 |
| Wall time (embed on CPU) | 10 min 45 s (549.2 s) | 1 min 13 s (39.1 s) |

Both runs passed: the index grew by exactly the new papers' chunks, every reloaded paper kept only its new chunks, and repeating the watermark day changed nothing. 35% of run 1's papers were already indexed, which confirms that replacing by `doc_id` (point 5) is the normal case. Cut-list item 6 is not applied.

## Consequences
- One code path: fetched records go through the bulk `clean`. The tests check that hand-written OAI-PMH pages fetched by the prototype pass `clean` (Spark and DuckDB) with the expected rows, and the live day above did the same with 276 real records.
- Each day costs one or two requests and a few hundred records and chunks (304 and 276 on the two checked days), and one Spark start-up (about 15 s, ADR 0005) that is large next to the data. Accepted, to keep one code path.
- The daily run needs a machine with Java 17+ (WSL2 or Kaggle), so the schedule lives there, not in Windows alone.
- The pipeline now depends on arXiv's OAI-PMH service and its XML. Parsing matches local element names, so a namespace change does not break it; a missing title, abstract or date shows up in `clean`'s drop counts.
- Deleted records (`<header status="deleted">`) are counted in the fetch manifest but stay in the index until the next full rebuild. A paper whose `cs.CL` category is removed also stays until then. Both are rare and accepted for v1.0.
- After W6 freezes the evaluation index, incremental loads must not change it: they go to the serving collection, or each evaluation run records the watermark.
- A full rebuild from a newer Kaggle snapshot resets the watermark to that snapshot's date.
- Revisit if: a later check finds `cs.CL` ids that `cs:cs:CL` misses; OAI-PMH is unavailable for more than two days (fall back to (a), the weekly Kaggle diff); the measured daily volume is far above the estimate; or a machine with Java 17+ and the serving Qdrant becomes available (then schedule the daily run, point 6).
