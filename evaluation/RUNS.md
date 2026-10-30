# Week 7 run plan

Status: draft by LDN for DAT's and FAO's confirmation (task W6-D5-LDN-1). Items marked **[TBC]** need a decision before the first run. Drafted with AI assistance (Claude); LDN is responsible for the final text.

This file lists every experiment of Week 7 with its config file, who runs it, where the result is stored and what it needs first. It follows `evaluation/PLAN.md` (sections 4 to 6) and `docs/plan/week-07.md`. Results are not in this file; each run writes a file to `evaluation/runs/`, and the log in section 7 points to it.

## 1. Rules for every run

- **Frozen system.** Tag `v0.6-rc` (`b61001d`) plus `evaluation/SNAPSHOT.md`: index `scitech_chunks/bge-small-en-v1.5/chunked-2026-10-17T05:19:12/embedded-2026-10-17T06:40:37` (121,926 points), `llama3.2:3b` digest `a80c4f17acd5`, judge `qwen2.5:7b` digest `845dbda0ea48`, prompts at the commit named in SNAPSHOT section 2. W7-D1-DAT-1 checks this before the first run. A run with a different index id, digest or prompt commit is a different condition and is not compared.
- **One host.** All W7 runs use DAT's laptop: local Ollama 0.40.13 with the same model digests, the frozen index, `AGENT_TIMEOUT_S=600` (decision on #156, 2026-10-30). Kaggle is not used. The same `.env` is used for every condition; only the flag a condition changes differs (section 3). Hardware and Ollama version go into the report next to every number.
- **Same checkout.** One commit for all runs (the run file records it). The golden file hash in a run file differs between Windows (CRLF) and Linux checkouts with the same content, so runs are compared only when made on the same machine.
- **Golden set.** The runs start when the golden set is frozen at 60 items or more (W5-D1-LDN-1) and W7-D1-FAO-1 has confirmed coverage. Each run file stores the sha256 of the golden file; all runs of this table must show the same one. Today `main` has 47 items (45 answerable: 30 dev, 15 test; 2 unanswerable).
- **One run per condition.** LLM output is not fully deterministic, so differences smaller than the run-to-run variation are not interpreted (PLAN section 6). A P0 fix after a run means the affected runs are repeated and the new commit is recorded.
- **Files.** `python -m scitech_eval` writes `evaluation/runs/<timestamp>-<name>.json` (and for `answers` also `.answers.jsonl` and `.traces.jsonl`). Commit each run file as it finishes. No tunnel URL, no key, no participant data in any of them.
- **Dev and test items.** Runs use `split: all`. The report gives numbers on all items and on the test items alone (PLAN section 3.4); the second set is taken from the per-question results by `split`.

Setup of the shell, repository root, PowerShell (values of the variables stay in the local `.env`):

```powershell
$env:PYTHONPATH = "evaluation/src;agent/src"
# agent settings come from .env; judge settings are separate:
#   JUDGE_BASE_URL (local Ollama /v1), JUDGE_API_KEY, JUDGE_MODEL=qwen2.5:7b
```

## 2. Retrieval (RQ1), W7-D1-LDN-1

Answerable English items only (unanswerable items are excluded by the runner); `k` in 1, 5, 10; questions used as asked. Needs Qdrant with the frozen collection and the BM25 index. No LLM is called.

| Run | Retriever | Config | Output |
|---|---|---|---|
| R1 | hybrid (baseline) | `evaluation/configs/retrieval-final-hybrid.yaml` | `evaluation/runs/<ts>-retrieval-final-hybrid.json` |
| R2 | dense | `evaluation/configs/retrieval-final-dense.yaml` | `evaluation/runs/<ts>-retrieval-final-dense.json` |
| R3 | BM25 | `evaluation/configs/retrieval-final-bm25.yaml` | `evaluation/runs/<ts>-retrieval-final-bm25.json` |

```powershell
foreach ($t in "hybrid", "dense", "bm25") {
  python -m scitech_eval retrieval --config "evaluation/configs/retrieval-final-$t.yaml" --out-dir evaluation/runs
}
python -m scitech_eval compare evaluation/runs/<hybrid>.json evaluation/runs/<dense>.json evaluation/runs/<bm25>.json
```

Send back the full text of `compare`. A WARNING about snapshot, golden file or `unspecified` makes the run invalid for the report. The per-type table (factual, explanatory, comparison, multi-hop, follow-up) comes from the per-question results; report `n` per cell and do not compare cells with fewer than 10 items. FAO's retrieval error analysis (W7-D3-FAO-1) works on R1 to R3.

## 3. Agent ablations and faithfulness (RQ2), W7-D2-DAT-1 and W7-D2-LDN-1

Each condition answers all English items of the golden set (answerable and unanswerable) with the real agent and labels every sentence with the LLM judge, in one command (`python -m scitech_eval answers`, PR #148). The condition is set by two environment variables, not by the config; the four configs differ only in name and notes.

| Run | Condition | `AGENT_REWRITE` | `AGENT_SELF_CHECK` | Config |
|---|---|---|---|---|
| A1 | MVP (all flags off) | `off` | `off` | `evaluation/configs/answers-w7-a1-mvp.yaml` |
| A2 | +rewrite | `on` | `off` | `evaluation/configs/answers-w7-a2-rewrite.yaml` |
| A3 | +evidence check | `off` | `on` | `evaluation/configs/answers-w7-a3-check.yaml` |
| A4 | full agent | `on` | `on` | `evaluation/configs/answers-w7-a4-full.yaml` |

```powershell
$env:AGENT_REWRITE = "on"; $env:AGENT_SELF_CHECK = "off"     # example: A2
python -m scitech_eval answers --config evaluation/configs/answers-w7-a2-rewrite.yaml --out-dir evaluation/runs
```

Run one condition at a time and commit each run file when it finishes (GPU is not used now, but a laptop can sleep or crash). A2 is also the product configuration of `v0.6-rc` (SNAPSHOT section 2: rewrite on, evidence check off). A4 turns the evidence check on; with `llama3.2:3b` it refused 6 of 6 test questions in #127, so A3 and A4 are expected to show a high refusal rate, and the report states it next to faithfulness. **[TBC with DAT: A4 is "full agent" as PLAN section 6 defines it (both steps on), not the frozen product setting.]**

What each run file holds: faithfulness (macro, micro, share of answers with faithfulness 1), cited-document recall, invalid-citation rate, over-refusal rate (answerable questions refused), refusals on the unanswerable items and the ids answered anyway, errors, judge errors, latency per question, and the generator and judge settings. LLM calls per answer are in the `.traces.jsonl` of the run. The 18 of 22 "not supported" sentences in DAT's pilot had no `[n]`; the report says that faithfulness here includes missing citations (#115).

Time, from DAT's pilot of 10 questions on the laptop (warm-up 8 s, answers 52 s, judge 27 s, #148): roughly 8 to 10 minutes per condition for about 60 items if the cost per question stays the same. This is an extrapolation from one pilot, not a measurement; A3 and A4 add one LLM call per question.

### Manual check of the judge (W7-D2-LDN-1)

- A random 20% of the answers are labelled by hand with the written procedure (`PLAN.md` section 5): LDN and FAO each label half, DAT does not (he built the agent). No double annotation; this stays a limitation.
- Sheets come from `python -m scitech_eval make-sheet <answers.jsonl>`; the labelled sheets are checked with `check-labels`. Agreement is Cohen's kappa plus raw agreement between judge and human. Where they disagree, the human label is used for the headline numbers, and the report says so.
- **[TBC]** `make-sheet` has no sampling option yet. LDN adds a seeded sample (same seed written in the report) before the first sheet is made; which answers are sampled (per condition, or pooled over the four) is decided there. The pilot cases from #148 (gs-003: the judge's reason is about answering the question, not support) go into the pilot kappa sheet.

## 4. Efficiency

| Run | What | Owner | Where the result goes |
|---|---|---|---|
| L1 | Latency p50 and p95 (time to first token, total) over 30 golden questions on the frozen system | DAT (W6-D2-DAT-1, moved to D18) | `docs/runbooks/performance.md` |
| S1 | Ingestion throughput, index build time, query latency, scaling charts | FAO (W7-D2-FAO-1; done in W6, repeated only if the snapshot changed, and it did not) | `pipelines/reports/scaling.md` |

L1 runs outside the user-study times so the two do not disturb each other, and states hardware, endpoint and network. **[TBC with DAT: the exact method and the 30 questions; L1 and the A runs must not run at the same time on the laptop.]**

## 5. User study (RQ3), W7-D3-LDN-1 and W7-D4-LDN-1

| Run | What | Owner | Where the result goes |
|---|---|---|---|
| U1 | Moderated sessions, n >= 5, following `evaluation/user_study/PROTOCOL.md` | LDN observer, FAO operator and host | questionnaire and observer sheets (anonymised) in `evaluation/user_study/responses/`; study trace and `feedback-<date>.jsonl` in LDN's private folder |

Sessions are held on one day, Tue 2026-11-03, in five slots from 21:00 to 00:00 (FAO confirmed on #134); Mon 2026-11-02 is not used. The study uses the same `v0.6-rc` stack on FAO's laptop (host decided on #134), not DAT's laptop, and its own trace and feedback files, so no evaluation run is mixed into the study data. Analysis (PROTOCOL section 10): counts, medians, distributions, follow-up click rate from `feedback.jsonl`, themes of the open comments. Descriptive only.

## 6. Optional

| Run | What | Condition |
|---|---|---|
| X1 | Closed-book check: the same LLM answers 20 golden questions without retrieval; compare with the reference answers (PLAN section 6, prior-knowledge threat) | Only if A1 to A4 and the manual check are done; no config yet |

Not planned: a Vietnamese run (the golden set has no `vi` items), reranking and question decomposition (cut, ADR 0010).

## 7. Order and run log

Order: W7-D1-DAT-1 and W7-D1-FAO-1 confirm the stack and coverage (D17, by 09:30) and the golden set is at 60 items; then R1 to R3 (LDN's task, run on the laptop), then A1 to A4 one after another; L1 on D18 outside the study; U1 on D19 night. The Sunday buffer takes any run that did not finish.

After every run: check that `counts` and `golden.n_items` match the other runs, that `git_commit`, `index_snapshot` and the golden sha256 are the same, and for A1 to A4 that `generator.agent_config` shows the flags of the condition. Then fill the row.

| Run | Run file | Date | Commit | Host | Golden sha256 | Status |
|---|---|---|---|---|---|---|
| R1 | | | | | | not run |
| R2 | | | | | | not run |
| R3 | | | | | | not run |
| A1 | | | | | | not run |
| A2 | | | | | | not run |
| A3 | | | | | | not run |
| A4 | | | | | | not run |
| L1 | | | | | | not run |
| S1 | `pipelines/reports/scaling.md` | | | | | done in W6 |
| U1 | | | | | | not run |

## 8. Confirmation needed

- **DAT:** the definition of A4 (section 3); who runs R1 to R3 on the laptop (they need Qdrant and the BM25 index, no LLM); the L1 method; `judge.context_tokens` (`ollama ps`, column CONTEXT, with `qwen2.5:7b` loaded) to be written into the four A configs before the first run; the Ollama version and digests re-read on the laptop (W7-D1-DAT-1). SNAPSHOT section 2 gives `AGENT_TIMEOUT_S=120` while #156 says 600 for the W7 runs; one of them needs to change.
- **FAO:** coverage of the final golden set (W7-D1-FAO-1); half of the manual labels (W7-D3-FAO-1); S1 stays as it is; operator of U1.
