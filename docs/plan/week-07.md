# Week 7 (phase 7 of 8): Experimental evaluation (2026-10-31 to 2026-11-03)

> Replanned on 2026-10-13, see [ADR 0010](../decisions/0010-compressed-schedule.md). This phase has 3 working days (D17, D18, D19); Sunday 2026-11-01 is a buffer day (long LLM runs may continue unattended).
> Task IDs are unchanged. Lines starting with **Replan:** say what changed.

Goal: all experiments are run on the frozen system (`v0.6-rc` + `evaluation/SNAPSHOT.md`) and written up with sample sizes and limitations.

Gate (D19, Tue 2026-11-03; checked at the latest D20 10:00): every experiment in `evaluation/RUNS.md` has a stored run file; user study completed (n >= 5); `evaluation/reports/final.md` draft merged with all tables, error analysis and threats to validity.

Rule this phase: no feature work. Only P0 bug fixes, and every fix after a run means the affected runs are repeated and the commit hash is recorded.
**Replan (2026-10-30, ADR 0011):** one controlled exception: scheduled ingestion every 2 hours (W7-D6-DAT-1, W7-D6-FAO-1, W7-D7-DAT-1). It is built on branches only, against a separate serving collection, and merged after Gate W7 (W8-D6-FAO-1), so no Week 7 run sees it. Evaluation tasks keep priority: if they slip, these tasks wait.

## D17
Saturday 2026-10-31

### DAT (@Tdat10052499)

#### W7-D1-DAT-1 Confirm frozen configuration and run support
- Do (by 09:30): verify that the stack matches `evaluation/SNAPSHOT.md` (model id, prompts commit, flags); make sure the remote LLM session is stable for long runs (or switch runs to the fallback and record it).
- Done when: confirmation comment in the Week 7 tracking issue.
- Depends on: W6-D5-DAT-1

#### W7-D2-DAT-1 Agent ablations
- Module: `evaluation/runs/`
- Do: with LDN's runner, run: MVP (all flags off), +rewrite, +evidence check, full agent; collect faithfulness, cited-document recall, refusal rate, LLM calls and latency.
- **Replan:** the "+decompose" condition is removed (decomposition cut). Start the runs right after W7-D1-DAT-1; GPU sessions can end, so run one condition at a time and commit each run file as it finishes.
- Done when: run files committed and listed in `RUNS.md` (the last condition may finish during the Sunday buffer).
- Depends on: W7-D1-DAT-1

#### W7-D6-DAT-1 ADR 0011 accepted and issue for scheduled ingestion
- Module: `docs/decisions/`, GitHub issue
- Do: get FAO's review of ADR 0011 (scheduled ingestion every 2 hours on `scitech_chunks_live`); set it to accepted; open one issue for the shared-file changes (`docker-compose.yml`, `Makefile`, `.env.example`) linking the two briefs `docs/tasks/W7-D6-FAO-1-scheduled-ingestion.md` and `docs/tasks/W7-D7-DAT-1-bm25-reload-and-ingest-service.md`.
- Done when: ADR 0011 accepted on `main`; issue open and linked from the Week 7 tracking issue.
- Depends on: none

### FAO (@F4ol4n)

#### W7-D1-FAO-1 Golden-set and snapshot integrity check
- Do (by 09:30): run the coverage script against the frozen index; confirm the golden set has >= 60 items and none point to missing documents.
- Done when: result posted in the tracking issue.
- Depends on: W6-D4-FAO-1, W5-D1-LDN-1

#### W7-D2-FAO-1 Efficiency results
- Do: final ingestion throughput, index build time, query latency (from the W6 scaling work, repeated on the frozen snapshot if it changed); produce charts for the report.
- Done when: numbers and charts in `pipelines/reports/scaling.md` and referenced in `final.md`.
- Depends on: W6-D2-FAO-1

### LDN (@Yui-Mika)

#### W7-D1-LDN-1 Final retrieval experiments
- Module: `evaluation/runs/`
- Do: run dense, BM25 and hybrid with k = 1, 5, 10 on the full golden set; per-type breakdown (factual, multi-hop, ...).
- **Replan:** "hybrid+rerank" removed (reranker cut). Per-type cells can have fewer than 10 items; report n per cell and avoid comparing cells that small.
- Done when: run files committed; table drafted in `final.md`.
- Depends on: W7-D1-FAO-1

## D18
Monday 2026-11-02

### DAT (@Tdat10052499)

#### W7-D3-DAT-1 Support user study sessions
- Do: keep the system running for the sessions; observe one session; log any failure with time and trace id.
- Done when: incident notes in the journal.
- Depends on: W6-D4-LDN-1

#### W6-D2-DAT-1 Latency measurement on the frozen system
- Module: `docs/runbooks/performance.md`
- **Replan:** moved from Week 6 and reduced: measurement only, no caching (cut) and no code changes (freeze). Run outside the user-study session times so the two do not interfere.
- Do: measure p50/p95 latency for 30 golden questions (time to first token and total) with the frozen configuration; state hardware, LLM endpoint and network conditions.
- Done when: numbers in `docs/runbooks/performance.md` and referenced in `final.md`.
- Depends on: W5-D4-DAT-1

### FAO (@F4ol4n)

#### W7-D3-FAO-1 Retrieval error analysis
- Do: categorise retrieval misses from W7-D1 (vocabulary mismatch, chunking split, missing document, ambiguous question, ...) with counts and 2 examples each.
- **Replan:** FAO also labels half of the manual faithfulness sample for W7-D2-LDN-1 today, using LDN's written procedure.
- Done when: section added to `final.md`; manual labels handed to LDN.
- Depends on: W7-D1-LDN-1

#### W7-D6-FAO-1 Scheduled ingestion in the pipeline (branch only)
- Module: `pipelines/`, `docker/ingest/`
- Brief: `docs/tasks/W7-D6-FAO-1-scheduled-ingestion.md`
- Do (D18-D19, after W7-D3-FAO-1): `incremental-run --until today`, "nothing changed" short-cut, run lock, refuse the frozen collection, `--rebuild-bm25` with an atomic switch; setup of `scitech_chunks_live` and `data/index/bm25-live`; `ingest` image with Java 17.
- Done when: PR open with the brief's acceptance criteria checked and one real run recorded; **not merged before Gate W7**.
- Depends on: W7-D6-DAT-1

### LDN (@Yui-Mika)

#### W7-D2-LDN-1 Faithfulness evaluation with manual check
- Do: LLM-judge faithfulness on all ablation outputs (start on D17 as run files arrive); manually judge a random 20% sample; report agreement between judge and human, and use human labels where they disagree for the headline numbers (state this choice).
- **Replan:** the manual sample is split between LDN and FAO (two annotators, same written procedure from W4-D4-LDN-1); DAT does not annotate because he built the agent. State the split and the absence of double annotation as a limitation.
- Done when: results and agreement in `final.md`.
- Depends on: W7-D2-DAT-1

#### W7-D3-LDN-1 User study sessions part 1
- Do: run sessions with the first half of participants following `PROTOCOL.md`; store questionnaire answers anonymised in `evaluation/user_study/responses/`.
- Done when: sessions done; responses stored.
- Depends on: W6-D4-LDN-1

## D19
Tuesday 2026-11-03 · Gate day

### DAT (@Tdat10052499)

#### W7-D4-DAT-1 Answer error analysis
- Do: take 20 low-faithfulness or refused answers; categorise causes (bad retrieval, model ignored evidence, citation errors, over-refusal) with examples; propose fixes as "future work" (no code changes now).
- Done when: section added to `final.md`.
- Depends on: W7-D2-LDN-1

#### W7-D5-DAT-1 Evaluation gate and report outline
- Do: check every run in `RUNS.md` has results; review `final.md`; create `docs/report/00-outline.md` with chapters, owners and page budget (Markdown chapters exported to PDF, see the brief).
- Done when: gate status recorded; outline merged.
- Depends on: W7-D4-LDN-1, W7-D4-DAT-1

#### W7-D7-DAT-1 BM25 reload and `ingest` compose service (branch only)
- Module: `agent/src/scitech_agent/retrieval/`, `backend/`, `docker-compose.yml`, `Makefile`
- Brief: `docs/tasks/W7-D7-DAT-1-bm25-reload-and-ingest-service.md`
- Do (after W7-D4-DAT-1): reload the BM25 index when `BM25_RELOAD_SECONDS` > 0 (default 0, frozen behaviour); `ingest` service started by `make up` only with `INGEST_ENABLED=1`.
- Done when: PR open with the brief's acceptance criteria checked; **not merged before Gate W7**.
- Depends on: W7-D6-DAT-1; W7-D6-FAO-1 for the image

### FAO (@F4ol4n)

#### W7-D4-FAO-1 Report data chapter with final numbers
- Module: `docs/report/02-data.md`
- **Replan:** includes the merged W6-D5-FAO-1: write the chapter in one pass: sources and licences, volume, pipeline design, engine choice (ADR 0005), incremental ingestion (or the cut decision), scaling results, pipeline diagram.
- Done when: LDN reviewed.
- Depends on: W7-D2-FAO-1

#### W7-D5-FAO-1 Review evaluation report
- Do (as soon as LDN opens the PR; at the latest D20 10:00): review `final.md` for correctness of numbers against run files (spot-check 5 numbers).
- Done when: review approved or issues listed.
- Depends on: W7-D4-LDN-1

### LDN (@Yui-Mika)

#### W7-D4-LDN-1 User study sessions part 2 and analysis
- Do (sessions in the morning): remaining sessions; analyse ratings (mean, median, distribution, n), follow-up click rate from `feedback.jsonl`, and recurring comments; state limitations (small, non-random sample).
- Done when: user study section in `final.md`.
- Depends on: W7-D3-LDN-1

#### W7-D5-LDN-1 `final.md` draft complete
- Module: `evaluation/reports/final.md`
- Do: assemble all sections: setup (snapshot, models, sample sizes), retrieval, answers and ablations, efficiency, user study, error analysis, threats to validity, summary of answers to the research questions; mark measured results vs interpretations.
- **Replan:** start assembling on D18 evening with the retrieval and ablation sections; merge at the latest D20 10:00.
- Done when: merged.
- Depends on: W7-D3-FAO-1, W7-D4-DAT-1, W7-D4-LDN-1

## Cut or merged in the replan
None in Week 7 (W6-D2-DAT-1 moved here; W6-D5-FAO-1 merged into W7-D4-FAO-1).
Added on 2026-10-30 (ADR 0011): W7-D6-DAT-1, W7-D6-FAO-1, W7-D7-DAT-1.
