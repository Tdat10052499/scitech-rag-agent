# Week 5 (phase 5 of 8): Agent v2 (reduced) and incremental ingestion (2026-10-27 to 2026-10-28)

> Replanned on 2026-10-13, see [ADR 0010](../decisions/0010-compressed-schedule.md). This phase has 2 working days (D13, D14) and carries most of the scope cuts.
> Task IDs are unchanged. Lines starting with **Replan:** say what changed.

Goal: the agent rewrites queries and checks evidence within limits, every request is traceable, and the evaluation runner works end to end. Incremental ingestion is either working or formally cut.

Gate (D14, Wed 2026-10-28, end of day): query rewriting and evidence check merged behind config flags; step and time limits enforced; per-request traces written; `Agent.run_batch` available; golden set >= 60 (**Replan:** >= 45 if items 31-45 were late, see W5-D1-LDN-1); answer runner works on 10 questions with the real stack; incremental ingestion either adds new items without duplicates or cut-list item 6 is applied and recorded in the tracking issue.

Contract change planned this week: none (the optional `status` event is cut together with the step display, cut-list item 3).

## D13
Tuesday 2026-10-27

### DAT (@Tdat10052499)

#### W5-D1-DAT-1 Conversation-aware query rewriting
- Module: `agent/prompts/rewrite.md`, `agent/src/scitech_agent/rewrite.py`
- Do: rewrite the user message into a standalone search query using the last turns (resolve "it", "that method"); keep the original if rewriting fails; config flag `AGENT_REWRITE=on|off`.
- Done when: unit tests with FakeLLM; manual check on the 5 follow-up golden items.
- Depends on: W4-D2-DAT-1

#### W5-D3-DAT-1 Evidence check and limits
- Module: `agent/src/scitech_agent/`
- Do: evidence sufficiency = score threshold plus optional LLM self-check ("is the question answerable from these chunks?"); refuse path with a helpful message and suggestions; hard limits on LLM calls per request and total time.
- **Replan:** no `status` events (cut); the dependencies on decomposition (W5-D2-DAT-1) and the status contract (W5-D2-DAT-2) are removed.
- Done when: tests for refuse path and limits; flags `AGENT_SELF_CHECK`, `AGENT_MAX_LLM_CALLS`, `AGENT_TIMEOUT_S` documented in `.env.example`.
- Depends on: W4-D2-DAT-1

### FAO (@F4ol4n)

#### W3-D4-FAO-1 ADR 0008: incremental ingestion design
- Module: `docs/decisions/0008-incremental-ingestion.md`, `pipelines/src/scitech_pipelines/incremental.py`
- **Replan:** moved from Week 3. Scope is scheduled batch with a watermark only; Kafka is cut (cut-list item 1; there is no instructor requirement, see the brief).
- Do (morning): design ingestion of new items since a stored watermark (date or token) through the same clean -> chunk -> embed -> load steps; decide scheduling (manual command, cron/Task Scheduler, or GitHub Actions without data). Prototype fetching the latest day of new items.
- Done when: ADR merged; prototype fetches and cleans one day of new items.
- Depends on: W2-D2-FAO-1

#### W5-D2-FAO-1 Incremental ingestion implementation
- Module: `pipelines/src/scitech_pipelines/incremental.py`
- Do (afternoon, finish D14 morning): implement ADR 0008: read watermark, fetch new items, run clean -> chunk -> embed -> load for them only, update watermark only after a successful load; idempotent if re-run.
- Done when: tests with fixture data for "new", "already present" and "failed load" cases.
- Depends on: W3-D4-FAO-1

### LDN (@Yui-Mika)

#### W5-D1-LDN-1 Golden set to 60 with multi-turn items
- Module: `evaluation/golden_set/`
- Do: add 15 items (total 60): multi-turn sequences (2-3 turns with the expected standalone query) and multi-hop questions needing 2 documents.
- **Replan:** if items 31-45 were not ready by D07 (W3-D4-LDN-1), the D14 gate accepts >= 45 items and this task finishes the set to 60 by D16.
- Done when: FAO's coverage script reports zero missing documents.
- Depends on: W4-D3-FAO-1

## D14
Wednesday 2026-10-28 · Gate day

### DAT (@Tdat10052499)

#### W5-D4-DAT-1 [blocking] Per-request traces
- Module: `agent/src/scitech_agent/trace.py`
- Do (merge by 12:00): write one JSON line per request to `data/logs/traces.jsonl` (git-ignored): timestamp, session, original and rewritten queries, retrieved chunk ids with scores, evidence decision, LLM calls count, latency per step, model and config. Provide `Agent.run_batch(questions)` for evaluation without the API.
- **Replan:** the "sub-questions" field is dropped (decomposition is cut).
- Done when: tests; LDN confirmed the format fits the harness.
- Depends on: W5-D3-DAT-1

#### W5-D5-DAT-1 Week 5 gate and feature list for W6
- Do (end of day): gate checklist; confirm the Week 6 scope from ADR 0010; decide keep/cut for incremental ingestion from FAO's live test; merge; close milestone.
- Done when: decisions recorded in the tracking issue and in `docs/plan/00-overview.md` if scope changed.
- Depends on: all W5 tasks

### FAO (@F4ol4n)

#### W5-D4-FAO-1 Incremental ingestion live test
- Do: run incremental ingestion on the latest real new items (one or more days if available); verify counts increase by exactly the new items and no duplicates exist; record numbers.
- **Replan:** includes the non-Kafka branch of the merged W5-D3-FAO-1: schedule the incremental command (Task Scheduler/cron) and document it in ADR 0008. If the test does not pass by 17:00, stop and apply cut-list item 6 (keep the batch pipeline; describe the design in the report).
- Done when: results in `pipelines/reports/incremental_test.md`, or the cut recorded with the reason.
- Depends on: W5-D2-FAO-1

### LDN (@Yui-Mika)

#### W5-D4-LDN-1 End-to-end answer evaluation runner
- Module: `evaluation/src/scitech_eval/`
- Do (afternoon, after traces are merged): `python -m scitech_eval answers --config <yaml>` runs `Agent.run_batch` over the golden set, stores answers, citations and traces, then applies the faithfulness procedure (LLM judge) and recall metrics on the cited documents.
- Done when: works on 10 questions with the real stack.
- Depends on: W5-D4-DAT-1, W4-D4-LDN-1

## Cut or merged in the replan

| Task | Decision | Where it went / reason |
|---|---|---|
| W5-D1-FAO-1 Reranker spike | Cut | Cut-list item 2. |
| W5-D2-DAT-1 Question decomposition | Cut | Cut-list item 4. RQ2 ablations run without the "+decompose" condition. |
| W5-D2-DAT-2 Approve the `status` event contract change | Cut | Only needed for the step display (cut-list item 3). |
| W5-D2-LDN-1 Propose the `status` event | Cut | Same reason. |
| W5-D3-LDN-1 Show agent steps in the UI | Cut | Cut-list item 3 (UI extras: step/status display). |
| W5-D3-FAO-1 Kafka decision follow-up | Merged | Kafka branch cut (item 1); the scheduling branch is part of W5-D4-FAO-1. |
| W5-D5-FAO-1 Review agent retrieval changes / rerank re-run | Cut | No reranker to re-run; PR reviews continue through CODEOWNERS as usual. |
| W5-D5-LDN-1 Pilot comparison: MVP vs agent v2 | Cut | The full comparison is part of the Week 7 ablations (W7-D2-DAT-1) on all 60 items; the runner is validated by W5-D4-LDN-1 on 10 questions. |
