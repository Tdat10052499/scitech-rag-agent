# Week 5: Agent v2 and incremental ingestion (2026-11-02 to 2026-11-06)

Goal: the agent reasons in steps (rewrite, decompose, check evidence) within limits, every request is traceable, and new data flows in incrementally.

Gate (Friday): query rewriting, decomposition and evidence check merged behind config flags; per-request traces written; incremental ingestion adds new items without duplicates; golden set >= 60; pilot comparison agent v2 vs MVP in `evaluation/reports/agent-v2-pilot.md`.

Contract change planned this week: optional `status` event (agent step messages) in `/chat`. Requires an issue approved by DAT before implementation.

## W5-D1
Monday 2026-11-02 · D21

### DAT (@Tdat10052499)

#### W5-D1-DAT-1 Conversation-aware query rewriting
- Module: `agent/prompts/rewrite.md`, `agent/src/scitech_agent/rewrite.py`
- Do: rewrite the user message into a standalone search query using the last turns (resolve "it", "that method"); keep the original if rewriting fails; config flag `AGENT_REWRITE=on|off`.
- Done when: unit tests with FakeLLM; manual check on the 5 follow-up golden items.
- Depends on: W4-D2-DAT-1

### FAO (@F4ol4n)

#### W5-D1-FAO-1 Reranker spike (cut-list item 2)
- Module: `agent/src/scitech_agent/retrieval/rerank.py` (DAT reviews)
- Do: optional cross-encoder reranking of the top 20 hybrid results; measure recall@5/MRR change with LDN's harness and added latency; flag `RERANK=on|off`.
- Done when: numbers in the PR; keep it only if gain is clear and latency acceptable (state the threshold you used).
- Depends on: W3-D4-DAT-1

### LDN (@Yui-Mika)

#### W5-D1-LDN-1 Golden set to 60 with multi-turn items
- Module: `evaluation/golden_set/`
- Do: add 15 items (total 60): multi-turn sequences (2-3 turns with the expected standalone query) and multi-hop questions needing 2 documents.
- Done when: FAO's coverage script reports zero missing documents.
- Depends on: W4-D3-FAO-1

## W5-D2
Tuesday 2026-11-03 · D22

### DAT (@Tdat10052499)

#### W5-D2-DAT-1 Question decomposition
- Module: `agent/prompts/decompose.md`, `agent/src/scitech_agent/decompose.py`
- Do: detect multi-part questions; split into at most `AGENT_MAX_SUBQUESTIONS` (default 3); retrieve per sub-question; merge and deduplicate evidence before answering; flag `AGENT_DECOMPOSE=on|off`.
- Done when: tests; manual check on the multi-hop golden items.
- Depends on: W5-D1-DAT-1

#### W5-D2-DAT-2 Approve the `status` event contract change
- Module: `docs/contracts/api.openapi.yaml`
- Do: review LDN's issue; if accepted, update the contract (event `status` with JSON `{step, message}`, optional for clients) and the backend test.
- Done when: contract PR merged.
- Depends on: W5-D2-LDN-1

### FAO (@F4ol4n)

#### W5-D2-FAO-1 Incremental ingestion implementation
- Module: `pipelines/src/scitech_pipelines/incremental.py`
- Do: implement ADR 0008: read watermark, fetch new items, run clean -> chunk -> embed -> load for them only, update watermark only after a successful load; idempotent if re-run.
- Done when: tests with fixture data for "new", "already present" and "failed load" cases.
- Depends on: W3-D4-FAO-1

### LDN (@Yui-Mika)

#### W5-D2-LDN-1 Propose the `status` event
- Module: GitHub issue (contract change)
- Do: write an issue describing the optional `status` event the UI needs to show agent steps ("Rewriting question", "Searching 3 sub-questions", "Checking evidence"), with JSON example and how old clients ignore it.
- Done when: issue opened and linked to W5-D2-DAT-2.
- Depends on: none

## W5-D3
Wednesday 2026-11-04 · D23

### DAT (@Tdat10052499)

#### W5-D3-DAT-1 Evidence check and limits
- Module: `agent/src/scitech_agent/`
- Do: evidence sufficiency = score threshold plus optional LLM self-check ("is the question answerable from these chunks?"); refuse path with a helpful message and suggestions; hard limits on LLM calls per request and total time; emit `status` events for each step.
- Done when: tests for refuse path and limits; flags `AGENT_SELF_CHECK`, `AGENT_MAX_LLM_CALLS`, `AGENT_TIMEOUT_S` documented in `.env.example`.
- Depends on: W5-D2-DAT-1, W5-D2-DAT-2

### FAO (@F4ol4n)

#### W5-D3-FAO-1 Kafka decision follow-up (cut-list item 1)
- Do: if the instructor requires streaming with Kafka, add a minimal producer (new items) and consumer (runs the incremental steps) with Kafka in `docker-compose.yml` via a PR reviewed by DAT; otherwise schedule the incremental command (Task Scheduler/cron) and document it.
- Done when: the chosen mechanism runs once end to end; ADR 0008 updated with what was built.
- Depends on: W5-D2-FAO-1

### LDN (@Yui-Mika)

#### W5-D3-LDN-1 Show agent steps in the UI
- Module: `frontend/`
- Do: display `status` events as a small progress line above the streaming answer; hide it when `done` arrives.
- Done when: works with the backend once W5-D3-DAT-1 is merged (use a stub before that).
- Depends on: W5-D2-DAT-2

## W5-D4
Thursday 2026-11-05 · D24

### DAT (@Tdat10052499)

#### W5-D4-DAT-1 [blocking] Per-request traces
- Module: `agent/src/scitech_agent/trace.py`
- Do: write one JSON line per request to `data/logs/traces.jsonl` (git-ignored): timestamp, session, original and rewritten queries, sub-questions, retrieved chunk ids with scores, evidence decision, LLM calls count, latency per step, model and config. Provide `Agent.run_batch(questions)` for evaluation without the API.
- Done when: tests; LDN confirmed the format fits the harness.
- Depends on: W5-D3-DAT-1

### FAO (@F4ol4n)

#### W5-D4-FAO-1 Incremental ingestion live test
- Do: run incremental ingestion on the latest real new items (several days if available); verify counts increase by exactly the new items and no duplicates exist; record numbers.
- Done when: results in `pipelines/reports/incremental_test.md`.
- Depends on: W5-D3-FAO-1

### LDN (@Yui-Mika)

#### W5-D4-LDN-1 End-to-end answer evaluation runner
- Module: `evaluation/src/scitech_eval/`
- Do: `python -m scitech_eval answers --config <yaml>` runs `Agent.run_batch` over the golden set, stores answers, citations and traces, then applies the faithfulness procedure (LLM judge) and recall metrics on the cited documents.
- Done when: works on 10 questions with the real stack.
- Depends on: W5-D4-DAT-1, W4-D4-LDN-1

## W5-D5
Friday 2026-11-06 · D25 · Gate day

### DAT (@Tdat10052499)

#### W5-D5-DAT-1 Week 5 gate and feature list for W6
- Do: gate checklist; decide which W6 features stay (apply the cut list); merge; close milestone.
- Done when: decisions recorded in the tracking issue and in `docs/plan/00-overview.md` if scope changed.
- Depends on: all W5 tasks

### FAO (@F4ol4n)

#### W5-D5-FAO-1 Review agent retrieval changes
- Do: review open agent PRs touching retrieval; run hybrid vs hybrid+rerank once more on 60 items if the reranker is kept.
- Done when: reviews done; numbers in the journal.
- Depends on: W5-D1-FAO-1, W5-D1-LDN-1

### LDN (@Yui-Mika)

#### W5-D5-LDN-1 Pilot comparison: MVP vs agent v2
- Module: `evaluation/reports/agent-v2-pilot.md`
- Do: run the answers runner on 20 golden items with all agent flags off (MVP behaviour) and on; compare faithfulness, cited-document recall, refusal rate, latency; state that this is a pilot.
- Done when: report merged.
- Depends on: W5-D4-LDN-1
