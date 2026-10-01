# Week 7: Experimental evaluation (2026-11-16 to 2026-11-20)

Goal: all experiments are run on the frozen system (`v0.6-rc` + `evaluation/SNAPSHOT.md`) and written up with sample sizes and limitations.

Gate (Friday): every experiment in `evaluation/RUNS.md` has a stored run file; user study completed; `evaluation/reports/final.md` draft merged with all tables, error analysis and threats to validity.

Rule this week: no feature work. Only P0 bug fixes, and every fix after a run means the affected runs are repeated and the commit hash is recorded.

## W7-D1
Monday 2026-11-16 · D31

### DAT (@Tdat10052499)

#### W7-D1-DAT-1 Confirm frozen configuration and run support
- Do: verify that the stack matches `evaluation/SNAPSHOT.md` (model id, prompts commit, flags); make sure the remote LLM session is stable for long runs (or switch runs to the fallback and record it).
- Done when: confirmation comment in the Week 7 tracking issue.
- Depends on: W6-D5-DAT-1

### FAO (@F4ol4n)

#### W7-D1-FAO-1 Golden-set and snapshot integrity check
- Do: run the coverage script against the frozen index; confirm the golden set has >= 60 items and none point to missing documents.
- Done when: result posted in the tracking issue.
- Depends on: W6-D4-FAO-1, W5-D1-LDN-1

### LDN (@Yui-Mika)

#### W7-D1-LDN-1 Final retrieval experiments
- Module: `evaluation/runs/`
- Do: run dense, BM25, hybrid, hybrid+rerank (if kept) with k = 1, 5, 10 on the full golden set; per-type breakdown (factual, multi-hop, ...).
- Done when: run files committed; table drafted in `final.md`.
- Depends on: W7-D1-FAO-1

## W7-D2
Tuesday 2026-11-17 · D32

### DAT (@Tdat10052499)

#### W7-D2-DAT-1 Agent ablations
- Module: `evaluation/runs/`
- Do: with LDN's runner, run: MVP (all flags off), +rewrite, +decompose, +evidence check, full agent; collect faithfulness, cited-document recall, refusal rate, LLM calls and latency.
- Done when: run files committed and listed in `RUNS.md`.
- Depends on: W7-D1-DAT-1

### FAO (@F4ol4n)

#### W7-D2-FAO-1 Efficiency results
- Do: final ingestion throughput, index build time, query latency (from W6 scaling work, repeated on the frozen snapshot if it changed); produce charts for the report.
- Done when: numbers and charts in `pipelines/reports/scaling.md` and referenced in `final.md`.
- Depends on: W6-D2-FAO-1

### LDN (@Yui-Mika)

#### W7-D2-LDN-1 Faithfulness evaluation with manual check
- Do: LLM-judge faithfulness on all ablation outputs; manually judge a random 20% sample; report agreement between judge and human, and use human labels where they disagree for the headline numbers (state this choice).
- Done when: results and agreement in `final.md`.
- Depends on: W7-D2-DAT-1

## W7-D3
Wednesday 2026-11-18 · D33

### DAT (@Tdat10052499)

#### W7-D3-DAT-1 Support user study sessions
- Do: keep the system running for the sessions; observe one session; log any failure with time and trace id.
- Done when: incident notes in the journal.
- Depends on: W6-D4-LDN-1

### FAO (@F4ol4n)

#### W7-D3-FAO-1 Retrieval error analysis
- Do: categorise retrieval misses from W7-D1 (vocabulary mismatch, chunking split, missing document, ambiguous question, ...) with counts and 2 examples each.
- Done when: section added to `final.md`.
- Depends on: W7-D1-LDN-1

### LDN (@Yui-Mika)

#### W7-D3-LDN-1 User study sessions part 1
- Do: run sessions with the first half of participants following `PROTOCOL.md`; store questionnaire answers anonymised in `evaluation/user_study/responses/`.
- Done when: sessions done; responses stored.
- Depends on: W6-D4-LDN-1

## W7-D4
Thursday 2026-11-19 · D34

### DAT (@Tdat10052499)

#### W7-D4-DAT-1 Answer error analysis
- Do: take 20 low-faithfulness or refused answers; categorise causes (bad retrieval, model ignored evidence, citation errors, over-refusal) with examples; propose fixes as "future work" (no code changes now).
- Done when: section added to `final.md`.
- Depends on: W7-D2-LDN-1

### FAO (@F4ol4n)

#### W7-D4-FAO-1 Report data chapter with final numbers
- Module: `docs/report/02-data.md`
- Do: update the chapter with final efficiency and dataset numbers; add the pipeline diagram.
- Done when: LDN reviewed.
- Depends on: W7-D2-FAO-1, W6-D5-FAO-1

### LDN (@Yui-Mika)

#### W7-D4-LDN-1 User study sessions part 2 and analysis
- Do: remaining sessions; analyse ratings (mean, median, distribution, n), follow-up click rate from `feedback.jsonl`, and recurring comments; state limitations (small, non-random sample).
- Done when: user study section in `final.md`.
- Depends on: W7-D3-LDN-1

## W7-D5
Friday 2026-11-20 · D35 · Gate day

### DAT (@Tdat10052499)

#### W7-D5-DAT-1 Evaluation gate and report outline
- Do: check every run in `RUNS.md` has results; review `final.md`; create `docs/report/00-outline.md` with chapters, owners and page budget according to the instructor's format.
- Done when: gate status recorded; outline merged.
- Depends on: W7-D4-LDN-1, W7-D4-DAT-1

### FAO (@F4ol4n)

#### W7-D5-FAO-1 Review evaluation report
- Do: review `final.md` for correctness of numbers against run files (spot-check 5 numbers).
- Done when: review approved or issues listed.
- Depends on: W7-D4-LDN-1

### LDN (@Yui-Mika)

#### W7-D5-LDN-1 `final.md` draft complete
- Module: `evaluation/reports/final.md`
- Do: assemble all sections: setup (snapshot, models, sample sizes), retrieval, answers and ablations, efficiency, user study, error analysis, threats to validity, summary of answers to the research questions; mark measured results vs interpretations.
- Done when: merged.
- Depends on: W7-D3-FAO-1, W7-D4-DAT-1, W7-D4-LDN-1
