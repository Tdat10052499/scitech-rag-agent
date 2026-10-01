# Week 1: Foundations (2026-10-05 to 2026-10-09)

Goal: everyone can build and test; scope, data sources and contracts are fixed so the three modules can be built in parallel from Week 2.

Gate (Friday): ADR 0003 merged (sub-domain and sources with measured numbers); contracts frozen and validated in CI; all three members ran the quick start; `evaluation/PLAN.md` merged; ADR 0004 (frontend) and ADR 0005 (engine) merged.

Related briefs: `docs/tasks/W01-01` ... `W01-04`.

## W1-D1
Monday 2026-10-05 · D01

### DAT (@Tdat10052499)

#### W1-D1-DAT-1 [blocking] Finish GitHub setup
- Module: repo settings, `.github/`
- Do: run `setup-github.ps1` (DryRun first), merge the CODEOWNERS PR, assign the four W01 issues (W01-01 FAO, W01-02 DAT, W01-03 LDN, W01-04 LDN), create one tracking issue "Week 1 tracking" for blockers.
- Outputs: ruleset "Protect main" active, 15+ labels, 8 milestones, W01 issues assigned.
- Done when: the script's verification summary shows the expected values and a test PR cannot be merged without CI.
- Depends on: none

#### W1-D1-DAT-2 Send open questions to the instructor
- Module: `docs/00-project-brief.md`
- Do: email/message the instructor the open questions listed in the brief (mandatory tools, local-only LLM, report format, presentation length, licence, repo visibility, deadline).
- Outputs: questions sent; a "Pending answers" note in the brief.
- Done when: message sent and noted in your journal with the date.
- Depends on: none

#### W1-D1-DAT-3 Kickoff meeting (30 min)
- Do: walk through `docs/plan/`, AGENTS.md, the PR workflow; agree on the journal habit; create `docs/journal/DAT/`, `docs/journal/FAO/`, `docs/journal/LDN/` with an empty `W1.md` each.
- Done when: journal folders merged; every member confirmed in the tracking issue that they read the plan.
- Depends on: none

### FAO (@F4ol4n)

#### W1-D1-FAO-1 [blocking] Data source survey: access and terms
- Module: `docs/03-data-sources.md` (brief `docs/tasks/W01-01-scope-and-data-survey.md`)
- Do: for arXiv (metadata snapshot and API/OAI-PMH), OpenAlex and Wikipedia, record: how to download, format, fields available, terms of use/licence, rate limits, update frequency. Link the official documentation for every claim.
- Outputs: updated table in `docs/03-data-sources.md` (draft PR).
- Done when: every cell of the table is filled with a value and a source link, or marked "unknown" with the reason.
- Depends on: none

### LDN (@Yui-Mika)

#### W1-D1-LDN-1 [blocking] Quick start on Windows
- Module: `README.md`, `CONTRIBUTING.md` (brief `docs/tasks/W01-03-dev-environment.md`)
- Do: clone, create `.env` from `.env.example`, install Python 3.10+, run the commands of `make setup`, `make lint`, `make test`, `make run`; call `GET http://localhost:8000/health`. Decide how Windows members run `make` (WSL, installed make, or the raw commands) and document it.
- Outputs: a "Windows" subsection in README quick start; PR.
- Done when: `/health` returns `{"status": "ok"}` on your machine and the steps are written so a teammate can repeat them.
- Depends on: none

## W1-D2
Tuesday 2026-10-06 · D02

### DAT (@Tdat10052499)

#### W1-D2-DAT-1 Sub-domain shortlist with FAO
- Module: `docs/00-project-brief.md`
- Do: with FAO, shortlist 2-3 candidate sub-domains (for example a group of arXiv categories such as AI/ML/NLP) by: data volume available, relevance to users, team knowledge. Decide in a 20-minute call.
- Outputs: decision and reasons written in the brief (In scope section).
- Done when: brief updated in a PR approved by FAO.
- Depends on: W1-D1-FAO-1

#### W1-D2-DAT-2 Contract review pass
- Module: `docs/contracts/` (brief `docs/tasks/W01-02-freeze-contracts.md`)
- Do: compare `chunk.schema.json` fields with the fields FAO found in the sources; check the `/chat` event list covers UI needs (ask LDN). Open one issue per needed change.
- Outputs: list of contract change issues (may be empty).
- Done when: FAO and LDN commented on the review issue.
- Depends on: W1-D1-FAO-1

### FAO (@F4ol4n)

#### W1-D2-FAO-1 [blocking] Sample download and size measurement
- Module: `pipelines/`, `docs/03-data-sources.md`
- Do: download a small sample (about 1,000 records) of the main source for the chosen sub-domain into `data/raw/sample/` (git-ignored). Measure record size, field completeness, and estimate full size for the sub-domain (records, GB).
- Outputs: numbers in `docs/03-data-sources.md`; a small anonymised fixture (20 records) in `pipelines/tests/fixtures/sample.jsonl` (commit only if the licence allows redistribution; otherwise generate synthetic records with the same fields).
- Done when: estimate written with the method used; fixture or synthetic fixture committed.
- Depends on: W1-D1-FAO-1

### LDN (@Yui-Mika)

#### W1-D2-LDN-1 ADR 0004: frontend framework
- Module: `docs/decisions/0004-frontend-framework.md`
- Do: compare Streamlit and one JavaScript option (e.g. React + Vite) on: SSE streaming support, time to build, team skills, deployment with Docker. Build a 20-line spike in the default choice that calls `/health`.
- Outputs: ADR 0004 (status accepted after DAT review); spike code in `frontend/`.
- Done when: ADR merged; `frontend/AGENTS.md` updated with run commands for the chosen framework.
- Depends on: W1-D1-LDN-1

## W1-D3
Wednesday 2026-10-07 · D03

### DAT (@Tdat10052499)

#### W1-D3-DAT-1 LLM serving spike
- Module: `docs/runbooks/llm-serving.md` (new)
- Do: run an OpenAI-compatible server (Ollama or vLLM) with one small open-source instruct model on Colab or Kaggle GPU; expose it to your laptop through a tunnel; call it with the `openai` Python client using `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`. Measure time to first token and tokens/second for a 200-token answer. Also try a small model locally via Ollama on CPU for comparison.
- Outputs: runbook with exact steps and the measured numbers; note session time limits observed.
- Done when: a teammate could reproduce the call by following the runbook.
- Depends on: none

### FAO (@F4ol4n)

#### W1-D3-FAO-1 [blocking] ADR 0003: sub-domain and data sources
- Module: `docs/decisions/0003-data-sources.md`, `docs/03-data-sources.md`
- Do: write the recommendation: which sources, which subset (categories, years), expected volume (records, GB), licence constraints, how "big data" scale is met (numbers), what is out of scope (e.g. full-text PDFs).
- Outputs: ADR 0003; `docs/03-data-sources.md` status changed from "candidate" to "verified".
- Done when: DAT approved the PR.
- Depends on: W1-D2-FAO-1, W1-D2-DAT-1

### LDN (@Yui-Mika)

#### W1-D3-LDN-1 Evaluation plan draft
- Module: `evaluation/PLAN.md` (brief `docs/tasks/W01-04-evaluation-plan.md`)
- Do: write research questions (e.g. RQ1 does hybrid retrieval beat dense-only; RQ2 do agent steps improve faithfulness; RQ3 are follow-up suggestions useful), metric definitions with formulas (recall@k, MRR, faithfulness rate, answer relevance, suggestion usefulness rating), baselines, threats to validity.
- Outputs: draft PR.
- Done when: every metric has a formula or procedure and an owner.
- Depends on: none

## W1-D4
Thursday 2026-10-08 · D04

### DAT (@Tdat10052499)

#### W1-D4-DAT-1 [blocking] Freeze contracts with CI checks
- Module: `docs/contracts/`, `backend/tests/`, `backend/requirements.txt` or `requirements-dev.txt`
- Do: apply the agreed contract changes; add a test that validates `pipelines/tests/fixtures/sample.jsonl` (converted to chunks or a hand-written example chunk) against `chunk.schema.json` using `jsonschema`; add a test that loads `api.openapi.yaml` and checks it parses and contains `/health` and `/chat`. Add "Frozen on 2026-10-08" to each contract file.
- Outputs: contract files frozen; tests in CI.
- Done when: CI green on the PR; FAO and LDN approved.
- Depends on: W1-D2-DAT-2, W1-D2-FAO-1

### FAO (@F4ol4n)

#### W1-D4-FAO-1 Pipelines module skeleton
- Module: `pipelines/`
- Do: create `pipelines/requirements.txt`; a CLI entry `python -m scitech_pipelines --help` with sub-commands `download`, `clean`, `chunk`, `embed`, `load` (stubs that print "not implemented"); config from environment/arguments; a smoke test. Ask DAT to add `pipelines/requirements.txt` to CI install (shared file).
- Outputs: skeleton merged.
- Done when: `make test` passes including the new smoke test; CI installs the module requirements.
- Depends on: none

### LDN (@Yui-Mika)

#### W1-D4-LDN-1 Golden set format and first 10 items
- Module: `evaluation/golden_set/`
- Do: define the item format (JSONL: `id`, `question`, `type` in {factual, explanatory, comparison, multi_hop, follow_up}, `relevant_doc_ids`, `reference_answer`, `notes`, `author`). Write 10 items in the chosen sub-domain using the sample data from FAO (questions must be answerable from the corpus).
- Outputs: `evaluation/golden_set/FORMAT.md`, `evaluation/golden_set/golden.jsonl` (10 items).
- Done when: each item's `relevant_doc_ids` exist in the sample; FAO checked 3 random items.
- Depends on: W1-D2-FAO-1

## W1-D5
Friday 2026-10-09 · D05 · Gate day

### DAT (@Tdat10052499)

#### W1-D5-DAT-1 Week 1 gate and brief update
- Do: run the gate checklist at the top of this file; merge or close every W1 PR; update `docs/00-project-brief.md` with instructor answers received so far; close milestone Week 1 if the gate is met, otherwise list what moves to Monday.
- Done when: gate status written in the "Week 1 tracking" issue and closed.
- Depends on: all W1 tasks

#### W1-D5-DAT-2 Add CI install for module requirements
- Module: `.github/workflows/ci.yml`, `Makefile`
- Do: install `pipelines/requirements.txt` (and frontend requirements if Python) in CI and in `make setup`.
- Done when: CI green on `main`.
- Depends on: W1-D4-FAO-1

### FAO (@F4ol4n)

#### W1-D5-FAO-1 ADR 0005: big-data processing engine
- Module: `docs/decisions/0005-processing-engine.md`
- Do: run the same small job (load sample, filter by category, count by year, write Parquet) with PySpark and with DuckDB or Polars on your machine; record runtime, memory, setup effort; extrapolate to the full sub-domain size; check instructor requirement on Spark.
- Outputs: ADR 0005 with a measured comparison table.
- Done when: DAT approved.
- Depends on: W1-D3-FAO-1

### LDN (@Yui-Mika)

#### W1-D5-LDN-1 Evaluation plan final + frontend skeleton
- Module: `evaluation/PLAN.md`, `frontend/`
- Do: finalise PLAN.md after DAT/FAO comments; create the frontend app skeleton in the chosen framework with a page that shows backend health status; add lint/run commands to `frontend/AGENTS.md`.
- Done when: both PRs merged and CI green.
- Depends on: W1-D3-LDN-1, W1-D2-LDN-1
