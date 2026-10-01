# Week 2: Batch data pipeline and skeletons (2026-10-12 to 2026-10-16)

Goal: a clean, profiled dataset exists; the agent, backend and UI skeletons talk to each other through the frozen contracts using fakes.

Gate (Friday): clean Parquet dataset of the chosen sub-domain with `pipelines/reports/data_profile.md`; LLM client + fake merged; `POST /chat` streams contract-valid events from a fake agent; UI renders those events; golden set >= 30 items; eval harness computes recall@k and MRR on toy data; ADR 0006 merged.

## W2-D1
Monday 2026-10-12 · D06

### DAT (@Tdat10052499)

#### W2-D1-DAT-1 [blocking] LLM client module
- Module: `agent/src/scitech_agent/llm.py`, `agent/tests/`, `agent/requirements.txt`
- Do: implement the client described in `docs/contracts/llm-client.md`: `chat(messages, temperature, max_tokens)` and `stream_chat(...)` yielding text fragments, config from `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`, timeout and limited retries, clear error type when the endpoint is unreachable. Add `FakeLLM` returning scripted outputs.
- Outputs: module + unit tests using `FakeLLM` only (no network in tests).
- Done when: tests pass in CI; a manual call to the remote server from the W1 runbook works (paste the output in the PR).
- Depends on: W1-D3-DAT-1

### FAO (@F4ol4n)

#### W2-D1-FAO-1 [blocking] Raw downloader
- Module: `pipelines/src/scitech_pipelines/download.py`
- Do: implement `download` for the source(s) in ADR 0003 into `data/raw/<source>/` with resume, a manifest (`manifest.json`: source, URL, date, file sizes, checksums) and rate-limit pauses where an API is used.
- Outputs: command `python -m scitech_pipelines download --source <name> --out data/raw` + tests on a mocked HTTP response.
- Done when: a full download of the chosen subset completes on your machine (record size and duration in the journal); re-running skips completed files.
- Depends on: W1-D3-FAO-1, W1-D4-FAO-1

### LDN (@Yui-Mika)

#### W2-D1-LDN-1 Chat UI layout with mock data
- Module: `frontend/`
- Do: build the main screen: question input, message list (user/assistant), sources panel (title, link, score), follow-up chips (max 4), an "insufficient evidence" message style. Use a hard-coded mock conversation.
- Outputs: screenshot in the PR.
- Done when: all five elements are visible and readable at 1280 px and at phone width.
- Depends on: W1-D5-LDN-1

## W2-D2
Tuesday 2026-10-13 · D07

### DAT (@Tdat10052499)

#### W2-D2-DAT-1 [blocking] `/chat` SSE endpoint with fake agent
- Module: `backend/src/app/`, `backend/tests/`
- Do: implement `POST /chat` (body `ChatRequest`) returning `text/event-stream` with events `sources`, `token` (several), `followups`, `done`, and `error` on failure, exactly as in the contract. Use a fake agent object injected via dependency so tests are offline. Enable CORS for the frontend origin from an env variable.
- Outputs: endpoint + tests that parse the stream and check event names, order and JSON shapes.
- Done when: tests pass; `curl -N` against the local server shows the stream (paste in PR).
- Depends on: W1-D4-DAT-1

### FAO (@F4ol4n)

#### W2-D2-FAO-1 [blocking] Cleaning to Parquet
- Module: `pipelines/src/scitech_pipelines/clean.py`
- Do: using the engine from ADR 0005: parse raw records, normalise fields (title, abstract, authors, categories, dates, URL, licence), drop records without abstract, de-duplicate by `doc_id` (keep latest version), filter to the sub-domain, write Parquet to `data/processed/documents/` partitioned by year.
- Outputs: `clean` command + tests on the fixture.
- Done when: tests pass; the command runs on the full raw data; record counts in/out are logged. Share a 200-record Parquet sample with LDN (outside git) for golden-set writing.
- Depends on: W2-D1-FAO-1

### LDN (@Yui-Mika)

#### W2-D2-LDN-1 Connect UI to the SSE stub
- Module: `frontend/`
- Do: call `POST /chat`, consume the event stream incrementally, render tokens as they arrive, show sources and follow-ups when their events arrive, handle `error`. Generate a `session_id` per conversation.
- Done when: the UI works against DAT's stub running locally (record a short GIF or screenshots in the PR).
- Depends on: W2-D1-LDN-1, W2-D2-DAT-1

## W2-D3
Wednesday 2026-10-14 · D08

### DAT (@Tdat10052499)

#### W2-D3-DAT-1 Agent skeleton with interfaces
- Module: `agent/src/scitech_agent/`
- Do: define a `Retriever` protocol (`search(query, k, filters) -> list[ScoredChunk]`), an in-memory fake retriever, and an `Agent.run(session, message)` pipeline that yields the same event types as the API: rewrite (identity for now) -> retrieve -> evidence check (score >= `RETRIEVAL_MIN_SCORE`) -> answer (FakeLLM) -> follow-ups (FakeLLM). Wire the backend to use `Agent` instead of its local fake.
- Outputs: agent package + tests covering the "insufficient evidence" branch.
- Done when: backend tests still pass using the real `Agent` with fakes.
- Depends on: W2-D1-DAT-1, W2-D2-DAT-1

### FAO (@F4ol4n)

#### W2-D3-FAO-1 Full-scale run and data profile
- Module: `pipelines/reports/data_profile.md`, `pipelines/src/scitech_pipelines/profile.py`
- Do: run download + clean on the full subset; write a profile: record count, size on disk (raw vs Parquet), runtime per step, hardware used, records per year and per category, abstract length distribution, missing-value rates, duplicate rate removed.
- Outputs: profile report (numbers and small tables; charts optional).
- Done when: report merged; every number states how it was computed.
- Depends on: W2-D2-FAO-1

### LDN (@Yui-Mika)

#### W2-D3-LDN-1 Golden set to 30 items
- Module: `evaluation/golden_set/golden.jsonl`
- Do: add 20 items (total 30) from the 200-record sample, covering all `type` values, at least 5 multi-hop and 5 follow-up items. Record for each how it was written.
- Done when: FAO validated that every `relevant_doc_ids` exists in the cleaned dataset (script or manual check of all items).
- Depends on: W1-D4-LDN-1, W2-D2-FAO-1

## W2-D4
Thursday 2026-10-15 · D09

### DAT (@Tdat10052499)

#### W2-D4-DAT-1 ADR 0006: LLM model and serving
- Module: `docs/decisions/0006-llm-model.md`, `docs/runbooks/llm-serving.md`
- Do: compare 2-3 open-source instruct models that fit the available GPU on 10 golden questions with hand-pasted context: answer quality (simple 1-3 rating), adherence to citation format, speed. Choose one plus the fallback (API or small local model). Record exact model identifiers and quantisation.
- Outputs: ADR 0006 with the comparison table; runbook updated.
- Done when: LDN reviewed the ratings method; ADR merged.
- Depends on: W1-D3-DAT-1, W2-D3-LDN-1

### FAO (@F4ol4n)

#### W2-D4-FAO-1 Data quality tests
- Module: `pipelines/tests/`
- Do: tests for schema of cleaned records, no null `doc_id`/`title`/abstract, no duplicate `doc_id`, dates parse, categories within the sub-domain. Add a `validate` command that runs the same checks on the full dataset and prints a summary.
- Done when: CI runs the fixture-based tests; `validate` passes on the full dataset (output in PR).
- Depends on: W2-D2-FAO-1

### LDN (@Yui-Mika)

#### W2-D4-LDN-1 Evaluation harness skeleton
- Module: `evaluation/src/scitech_eval/`, `evaluation/tests/`
- Do: load `golden.jsonl`; given any `search(query, k)` function compute recall@k (k = 1, 5, 10) and MRR; write results to `evaluation/runs/<timestamp>-<name>.json` including git commit hash, config and per-question results. CLI: `python -m scitech_eval retrieval --config <yaml>`.
- Done when: unit tests with a toy corpus and hand-computed expected metrics pass.
- Depends on: W1-D5-LDN-1

## W2-D5
Friday 2026-10-16 · D10 · Gate day

### DAT (@Tdat10052499)

#### W2-D5-DAT-1 Week 2 gate and integration check
- Do: run backend + frontend locally with the fake agent; check the gate list; merge PRs; close milestone or carry over; update `docs/01-architecture.md` if interfaces changed.
- Done when: gate status in the Week 2 tracking issue.
- Depends on: all W2 tasks

### FAO (@F4ol4n)

#### W2-D5-FAO-1 Reproducibility note for the data pipeline
- Module: `pipelines/README.md` (new)
- Do: exact commands from empty `data/` to cleaned Parquet, expected runtime and disk usage, how to run on a small subset (`--limit`) for teammates with weak machines.
- Done when: LDN reproduced the small-subset run following only the README.
- Depends on: W2-D3-FAO-1

### LDN (@Yui-Mika)

#### W2-D5-LDN-1 UI tidy-up and frontend test
- Module: `frontend/`
- Do: handle network errors and backend down state; add at least one automated test or a scripted smoke check (for example a test of the SSE parsing function).
- Done when: CI runs the test.
- Depends on: W2-D2-LDN-1
