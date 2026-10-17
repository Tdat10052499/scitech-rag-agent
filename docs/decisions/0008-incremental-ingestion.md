# 0008. Incremental ingestion: daily OAI-PMH harvest with a date watermark

- Status: proposed (draft). The OAI-PMH set is settled by the live check of 2026-10-17 (below)
- Date: 2026-10-17 (drafted early; task W3-D4-FAO-1 is scheduled for D13, 2026-10-27)
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

## Decision (proposed)
**Harvest arXiv OAI-PMH by datestamp with `incremental-fetch`, run the existing clean -> chunk -> embed -> load on that file only, and keep a date watermark that moves only after a successful load.**

1. **Fetch** (prototype in this PR): `python -m scitech_pipelines incremental-fetch --from <watermark> --until <yesterday, UTC> --set cs:cs:CL --category cs.CL --out <file>.jsonl`. It follows `resumptionToken`, waits at least 3 s between requests, retries 429/5xx with `Retry-After`, treats `noRecordsMatch` as zero records, and writes the records as JSON Lines in the Kaggle snapshot shape, plus `<file>.manifest.json` with the settings and counts. `--from` is the watermark day itself, not the day after: datestamps are days, and a day's records may still be arriving when it is first harvested. The overlap costs one day of records, and re-loading them is harmless (point 5).
2. **Set `cs:cs:CL`.** The rule written before the live check was: use `cs:cs:CL` if it contains cross-lists and has every `cs.CL` id that `cs` has. It does (table below): the same 304 ids as `cs` filtered on `cs.CL`, 99 of them cross-lists, in one request instead of two. ADR 0003's known risk (a set of primary `cs.CL` only) does not hold. `--category cs.CL` stays on as a guard.
3. **Process** the new file with the existing commands, each with its own output directory (`clean` replaces its `--out`, and `chunk` refuses an `--out` with other files):
   - `clean --input <file>.jsonl --out data/processed/incremental/<until>/documents`: the same Spark code as the bulk load, so normalisation exists once. It needs Java 17+: WSL2 on FAO's laptop or a Kaggle CPU notebook, not Windows. The simplest setup runs every step in WSL2.
   - `chunk`, then `embed` with the model of the index (`EMBEDDING_MODEL`, ADR 0007) on CPU. The live check harvested 304 records for one day (above the 90 estimated from the 2025 total; see the table). At the 0.9 records/s measured for `bge-base-en-v1.5` (the model of ADR 0007) on a Colab CPU, 304 chunks take about 6 min (estimate: about one chunk per record, as in the bulk run). No GPU is needed.
   - `load` (W3-D3-FAO-1) into the same collection.
4. **Watermark**: `data/state/incremental.json` (git-ignored) with the last loaded `until` day, the set and category, the fetch manifest path and the point count after the load. It is written only after `load` succeeds and its count check passes (W5-D2-FAO-1); a failure at any step leaves it, so the next run repeats the same range. The first value is the date of the Kaggle snapshot of the bulk index (2026-10-10 for version 307). A run after missed days harvests all of them in one range.
5. **Idempotency**: `load` upserts by `chunk_id` (`<doc_id>#<chunk_index>`, stable), so re-running a range replaces points instead of adding them. A record's datestamp also changes when an old paper gets a new version (or its metadata is edited), so it is harvested again with its latest title and abstract and replaces the old chunks. `published_at` stays the v1 date (`created`) and `updated_at` becomes the new version's date. If the new abstract has fewer chunks, the old higher-numbered chunks would remain, so `load` must first delete the points of every `doc_id` it reloads (W5-D2-FAO-1).
6. **Scheduling**: the manual command until the D14 live test passes; then one daily run after the announcement, through cron in WSL2 or Task Scheduler calling `wsl`, chosen and recorded here by W5-D4-FAO-1. GitHub Actions is not used.

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

## Consequences
- One code path: fetched records go through the bulk `clean`. The tests check that hand-written OAI-PMH pages fetched by the prototype pass `clean` (Spark and DuckDB) with the expected rows.
- Each day costs one or two requests and a few hundred records and chunks (304 on the checked day), and one Spark start-up (about 15 s, ADR 0005) that is large next to the data. Accepted, to keep one code path.
- The daily run needs a machine with Java 17+ (WSL2 or Kaggle), so the schedule lives there, not in Windows alone.
- The pipeline now depends on arXiv's OAI-PMH service and its XML. Parsing matches local element names, so a namespace change does not break it; a missing title, abstract or date shows up in `clean`'s drop counts.
- Deleted records (`<header status="deleted">`) are counted in the fetch manifest but stay in the index until the next full rebuild. A paper whose `cs.CL` category is removed also stays until then. Both are rare and accepted for v1.0.
- After W6 freezes the evaluation index, incremental loads must not change it: they go to the serving collection, or each evaluation run records the watermark.
- A full rebuild from a newer Kaggle snapshot resets the watermark to that snapshot's date.
- Revisit if: a later check finds `cs.CL` ids that `cs:cs:CL` misses; OAI-PMH is unavailable for more than two days (fall back to (a), the weekly Kaggle diff); the measured daily volume is far above the estimate; or cut-list item 6 is applied at D14 (status: rejected, and the report describes this design).
