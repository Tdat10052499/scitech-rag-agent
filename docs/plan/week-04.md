# Week 4: RAG MVP with a real LLM (2026-10-26 to 2026-10-30)

Goal: the first end-to-end product: question -> retrieved evidence -> streamed answer with citations -> follow-up suggestions, in the real UI with the real LLM.

Gate (Friday): live demo of the full flow on 5 golden questions; "insufficient evidence" path works; tag `v0.4-mvp`; demo video v1 recorded (fallback for later); open bugs triaged into Week 5.

## W4-D1
Monday 2026-10-26 · D16

### DAT (@Tdat10052499)

#### W4-D1-DAT-1 [blocking] Answer generation with citations
- Module: `agent/prompts/answer.md`, `agent/src/scitech_agent/answer.py`
- Do: prompt that receives numbered evidence chunks and the conversation, must answer only from the evidence, cite as `[n]`, and say clearly when evidence does not support an answer. Retrieved text is placed in a delimited data section and the prompt states it must not be followed as instructions. Parse the output to map `[n]` to `chunk_id`s; drop citations that point to non-existent numbers.
- Done when: unit tests with FakeLLM for citation parsing; manual run on 5 golden questions with the real model, outputs pasted in the PR.
- Depends on: W2-D3-DAT-1, W3-D5-DAT-1

### FAO (@F4ol4n)

#### W4-D1-FAO-1 Stable search API and metadata filters
- Module: `agent/src/scitech_agent/retrieval/` (co-owned, DAT reviews)
- Do: make sure `search(query, k, filters)` supports filters by year range and category for all retrievers; add tests; document in `agent/AGENTS.md`.
- Done when: tests pass; one filtered query demonstrated in the PR.
- Depends on: W3-D4-DAT-1

### LDN (@Yui-Mika)

#### W4-D1-LDN-1 Streaming answer rendering with citations
- Module: `frontend/`
- Do: render tokens progressively including Markdown; turn `[n]` into clickable references to the sources panel; keep the UI responsive while streaming; a stop button if the framework allows.
- Done when: works against the backend with FakeLLM; screenshot/GIF.
- Depends on: W3-D2-LDN-1

## W4-D2
Tuesday 2026-10-27 · D17

### DAT (@Tdat10052499)

#### W4-D2-DAT-1 [blocking] Real pipeline behind `/chat`
- Module: `backend/src/app/`, `agent/`
- Do: connect `/chat` to `Agent` with the configured retriever and LLM; emit `sources` before tokens; short-term session memory (last N turns, in memory, keyed by `session_id`); map exceptions to `error` events with codes (`llm_unavailable`, `retrieval_failed`, `bad_request`).
- Done when: local run with Qdrant + remote LLM answers a golden question in the UI; tests with fakes still pass.
- Depends on: W4-D1-DAT-1, W3-D3-FAO-1

### FAO (@F4ol4n)

#### W4-D2-FAO-1 One-command pipeline run
- Module: `pipelines/src/scitech_pipelines/__main__.py`, `pipelines/README.md`
- Do: `run-all` sub-command chaining download -> clean -> chunk -> embed -> load with a `--limit` option for small runs; logs per step to `data/logs/`.
- Done when: `run-all --limit 2000` finishes from an empty `data/` on your machine; time recorded in the README.
- Depends on: W3-D3-FAO-1

### LDN (@Yui-Mika)

#### W4-D2-LDN-1 Automated end-to-end smoke test
- Module: `evaluation/` or `backend/tests/` (agree with DAT)
- Do: test that starts the backend with FakeLLM and a fake retriever, posts a question, and checks the event sequence and that cited numbers exist in `sources`.
- Done when: runs in CI.
- Depends on: W2-D2-DAT-1

## W4-D3
Wednesday 2026-10-28 · D18

### DAT (@Tdat10052499)

#### W4-D3-DAT-1 Follow-up suggestions v1
- Module: `agent/prompts/followups.md`, `agent/src/scitech_agent/followups.py`
- Do: after the answer, ask the LLM for up to 4 short follow-up questions grounded in the evidence and the conversation, as a JSON array; robust parsing (strip extra text, fallback to empty list); remove duplicates of questions already asked.
- Done when: unit tests for parsing edge cases; manual check on 5 questions.
- Depends on: W4-D2-DAT-1

### FAO (@F4ol4n)

#### W4-D3-FAO-1 Golden-set coverage check against the index
- Module: `evaluation/` (script) or `pipelines/`
- Do: script that verifies every `relevant_doc_ids` in `golden.jsonl` exists in the loaded index and reports missing ones.
- Done when: script merged; zero missing or a list of fixes sent to LDN.
- Depends on: W3-D3-FAO-1, W3-D4-LDN-1

### LDN (@Yui-Mika)

#### W4-D3-LDN-1 Clickable follow-ups and conversation flow
- Module: `frontend/`
- Do: follow-up chips send their text as the next question in the same session; new conversation button resets `session_id`; scroll handling for long answers.
- Done when: a 3-turn conversation works in the UI with the real backend.
- Depends on: W4-D1-LDN-1, W4-D3-DAT-1

## W4-D4
Thursday 2026-10-29 · D19 · Integration day

### DAT (@Tdat10052499)

#### W4-D4-DAT-1 Integration session and bug triage
- Do: run the full stack together (1 hour call); each member asks 10 questions; file every problem as an issue with label and priority; fix P0 issues in agent/backend today.
- Done when: all P0 issues have an owner; your P0 fixes merged.
- Depends on: W4-D2-DAT-1, W4-D3-LDN-1

### FAO (@F4ol4n)

#### W4-D4-FAO-1 Fix data and retrieval issues from integration
- Do: take issues labelled `area:data` or `area:retrieval`; fix P0s.
- Done when: your P0 issues closed.
- Depends on: W4-D4-DAT-1

### LDN (@Yui-Mika)

#### W4-D4-LDN-1 Faithfulness judging procedure and pilot
- Module: `evaluation/PLAN.md`, `evaluation/src/scitech_eval/answers.py`
- Do: define how faithfulness is judged (claim-level: each sentence supported / not supported by cited chunks), with an LLM-judge prompt and a manual protocol. Pilot on 10 golden questions: judge manually and with the LLM, compute agreement.
- Done when: procedure written; pilot numbers in the journal.
- Depends on: W4-D2-DAT-1

## W4-D5
Friday 2026-10-30 · D20 · Gate day

### DAT (@Tdat10052499)

#### W4-D5-DAT-1 MVP gate, tag and demo video v1
- Do: gate checklist; tag `v0.4-mvp`; record a 3-minute demo video of the flow (store outside git, link in the tracking issue); review the cut list against progress.
- Done when: tag pushed via PR-merged commit; video link recorded.
- Depends on: W4-D4-DAT-1

### FAO (@F4ol4n)

#### W4-D5-FAO-1 Data pipeline runbook draft
- Module: `docs/runbooks/data-pipeline.md`
- Do: operations guide: full rebuild, small rebuild, how to verify counts, common failures and fixes, disk space needed.
- Done when: DAT reviewed.
- Depends on: W4-D2-FAO-1

### LDN (@Yui-Mika)

#### W4-D5-LDN-1 UI fixes from integration
- Do: close `area:frontend` P0/P1 issues from Thursday.
- Done when: issues closed or moved to Week 5 with reason.
- Depends on: W4-D4-DAT-1
