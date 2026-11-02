# Week 7 run plan

Status: W6-D5-LDN-1 by LDN. FAO confirmed his parts on #160, and DAT approved it on #160 on 2026-10-31 with answers to the open items, which are written into this file. Two conditions are still open and marked **[open]**: #169 is merged before the first sheet, and #171 is tried on the real judge (section 3). Drafted with AI assistance (Claude); LDN is responsible for the final text.

This file lists every experiment of Week 7 with its config file, who runs it, where the result is stored and what it needs first. It follows `evaluation/PLAN.md` (sections 4 to 6) and `docs/plan/week-07.md`. Results are not in this file; each run writes a file to `evaluation/runs/`, and the log in section 7 points to it.

## 1. Rules for every run

- **Frozen system.** Tag `v0.6-rc` (`b61001d`) plus `evaluation/SNAPSHOT.md`: index `scitech_chunks/bge-small-en-v1.5/chunked-2026-10-17T05:19:12/embedded-2026-10-17T06:40:37` (121,926 points), `llama3.2:3b` digest `a80c4f17acd5`, judge `qwen2.5:7b` digest `845dbda0ea48`, prompts at the commit named in SNAPSHOT section 2. W7-D1-DAT-1 checks this before the first run. A run with a different index id, digest or prompt commit is a different condition and is not compared.
- **Refusal detector (#167).** The P0 fix of `is_refusal()` is commit `e8cad3c` in #166 (two more phrasings). Runs made after it is on the checkout use the new detector, and the commit in each run file says which one a run used. DAT re-read every stored answer file made before the fix (pilot10 x2, latency30 x2, ablations x5) and found 0 missed refusals (table on #167), so `ablations-v1.md` and `performance.md` stay and no earlier run is repeated. All R and A runs of this table use one commit: `main` after #166 is merged (decided by DAT on #160). DAT posts the commit hash on #156 before the first run.
- **One host.** All W7 runs use DAT's laptop: local Ollama 0.40.13 with the same model digests, the frozen index, `AGENT_TIMEOUT_S=600` (decision on #156, 2026-10-30; `SNAPSHOT.md` says the same). Both models run on the laptop's GPU (RTX 5060 Laptop 8 GB, `ollama ps`: 100% GPU, context 4096). On Windows the Qdrant URL is `QDRANT_URL=http://127.0.0.1:6333`, not `localhost` (with `localhost` some retrievals took about 2 s; DAT, #156). Kaggle is not used for the W7 runs. The same `.env` is used for every condition; only the flag a condition changes differs (section 3). Hardware and Ollama version go into the report next to every number.
- **Same checkout.** One commit for all runs (the run file records it). The golden file hash in a run file differs between Windows (CRLF) and Linux checkouts with the same content, so runs are compared only when made on the same machine.
- **Golden set.** The runs start when the golden set is frozen at 60 items or more (W5-D1-LDN-1) and W7-D1-FAO-1 has confirmed coverage. Each run file stores the sha256 of the golden file; all runs of this table must show the same one. `main` has 47 items (45 answerable: 30 dev, 15 test; 2 unanswerable). #168 takes the file to 65 lines (60 answerable: 30 dev, 30 test; 5 unanswerable). DAT approved it; FAO's coverage check (W7-D1-FAO-1) passed and is posted on #156 (2026-10-31, all 78 relevant ids found). The runs start after #168 is merged.
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

Run one condition at a time and commit each run file when it finishes (a laptop can sleep or crash). A2 is also the product configuration of `v0.6-rc` (SNAPSHOT section 2: rewrite on, evidence check off). A4 turns the evidence check on; with `llama3.2:3b` it refused 6 of 6 test questions in #127, so A3 and A4 are expected to show a high refusal rate, and the report states it next to faithfulness. A4 is the "full agent" as PLAN section 6 defines it (rewrite on and evidence check on); it is not the product setting, which is A2 (DAT, #160). The four configs use `split: all`; DAT's `ablations-v1.md` (#163) used `split: dev` (32 items) and stays as the earlier, dev-only run, and the report uses A1 to A4 (DAT, #160). They need the golden set at 60 items and about 15 minutes on the laptop.

What each run file holds: faithfulness (macro, micro, share of answers with faithfulness 1), cited-document recall, invalid-citation rate, over-refusal rate (answerable questions refused), refusals on the unanswerable items and the ids answered anyway, errors, judge errors, latency per question, and the generator and judge settings. LLM calls per answer are in the `.traces.jsonl` of the run. The 18 of 22 "not supported" sentences in DAT's pilot had no `[n]`; the report says that faithfulness here includes missing citations (#115).

Time, from DAT's pilot of 10 questions on the laptop's GPU (warm-up 8 s, answers 52 s, judge 27 s, #148): roughly 8 to 10 minutes per condition for about 60 items if the cost per question stays the same. This is an extrapolation from one pilot, not a measurement; A3 and A4 add one LLM call per question.

### Manual check of the judge (W7-D2-LDN-1)

- A random 20% of the answers are labelled by hand with the written procedure (`PLAN.md` section 5): LDN and FAO each label half, DAT does not (he built the agent). No double annotation; this stays a limitation.
- Sheets come from `python -m scitech_eval make-sheet <answers.jsonl>`; the labelled sheets are checked with `check-labels`. Agreement is Cohen's kappa plus raw agreement between judge and human. Where they disagree, the human label is used for the headline numbers, and the report says so.
- `make-sheet --sample 0.2 --seed N [--part K/N]` draws the seeded sample (PR #169, Draft until merged; see `evaluation/AGENTS.md`). It samples each run file separately, from the answers that enter the metrics (no error, not refused, answerable item), and writes `sample.json` with the seed and the counts; the same seed is used for all four conditions and written in the report, together with one `sample.json` per run (DAT's review of #169). Refusals are recognised by more phrasings after #167, so eligibility can differ from runs made before it. If a run refuses every answer (likely for A3 and A4: the evidence check refused 32 of 32 in `ablations-v1.md`), `make-sheet` writes empty sheets and `sample.json` has `eligible: 0`; read `sample.json` before waiting for a sheet (FAO's review of #169). **The seed is 20261031** (the date it was set, Sat 2026-10-31, D17; chosen on D17 before the A runs of this table (the run log in section 7 shows none) and not changed after a sample has been seen). `--part 1/2` is LDN's half and `--part 2/2` FAO's, for every condition. Each run file is sampled by itself, so the four conditions get the same items only where the same answers are eligible (refusals differ per run); the report says so. **[open: #169 is merged before the first sheet; DAT and FAO approved it.]** The pilot cases from #148 (gs-003: the judge's reason is about answering the question, not support) go into the pilot kappa sheet.

### Relevance (W7-D2-LDN-1)

- Answer relevance (`PLAN.md` 4.2, anchor #94, rated 1 to 3) is not computed by `answers`. After each of A1 to A4 has finished, a separate pass rates the stored answers: `python -m scitech_eval relevance --config evaluation/configs/relevance-w7.yaml --answers evaluation/runs/<ts>-answers-w7-<cond>.answers.jsonl --out-dir evaluation/runs` (PR #171). It reads the `.answers.jsonl`, so the agent is not called and no A run is repeated. It uses the same judge (`qwen2.5:7b`) on the same laptop, so it runs after the A runs and not at the same time as one, and before L1 (one run at a time on the laptop).
- Output: `<ts>-answers-w7-<cond>.relevance.json` (mean, distribution, per-answer ratings, judge settings and prompt hash). Commit it with the A run file.
- The manual rating of the same 20% sample uses `relevance-template.csv` from `make-sheet --sample` (same seed and parts as faithfulness). Where judge and human differ the human rating is used; the report gives the raw agreement and a table of judge against human ratings.
- DAT approved #170 (the anchor) and #171 (the pass) on 2026-10-31. **[open: #171 is merged and tried once on real `qwen2.5:7b` output (pilot answers, gs-003 included) on the laptop before the A runs finish; DAT runs it when #171 is marked Ready.]** If the pass is not merged and tried by the evening of D18 (Mon 2 Nov), relevance is rated by hand only, on the pooled sample, with `n` stated and no comparison between conditions (accepted by DAT, #160).

## 4. Efficiency

| Run | What | Owner | Where the result goes |
|---|---|---|---|
| L1 | Latency p50 and p95 (time to first token, total) over 30 golden questions on the frozen system | DAT (W6-D2-DAT-1; measured 2026-10-30) | `docs/runbooks/performance.md` |
| S1 | Ingestion throughput, index build time, query latency, scaling charts | FAO (W7-D2-FAO-1; done in W6, repeated only if the snapshot changed, and it did not) | `pipelines/reports/scaling.md` |

L1 is already measured (DAT, #161, `docs/runbooks/performance.md`, run B `20261030T083604Z`): the first 30 golden questions (`split: all`, `limit: 30`), `QDRANT_URL=127.0.0.1`, version `v0.6-rc` plus the files of #148. It is not repeated after #167, because the regex change does not touch the timed steps. If the team wants L1 on the final commit, it can be rerun after the A runs (about 2 minutes, `latency30.yaml`); L1 and the A runs must not run at the same time on the laptop.

## 5. User study (RQ3), W7-D3-LDN-1 and W7-D4-LDN-1

| Run | What | Owner | Where the result goes |
|---|---|---|---|
| U1 | Moderated sessions, n >= 5, following `evaluation/user_study/PROTOCOL.md` | LDN observer, FAO operator and host | questionnaire and observer sheets (anonymised) in `evaluation/user_study/responses/`; study trace and `feedback-<date>.jsonl` in LDN's private folder |

Sessions are held on one day, Tue 2026-11-03 (Vietnam time): 4 confirmed participants (target 5-6; if fewer than 5 take part, the report states the real number), slots P01 22:30, P02 23:15, P03 00:00 and P04 00:45 (night of 3 to 4 Nov), as in `PROTOCOL.md` section 12. FAO confirmed the four slots on #159 and hosts until about 01:30; if a fifth person is confirmed, 21:00 or 21:45 also works for him. Mon 2026-11-02 is not used. The study uses the same `v0.6-rc` stack on FAO's laptop (host decided on #134), not DAT's laptop, and its own trace and feedback files, so no evaluation run is mixed into the study data. Analysis (PROTOCOL section 10): counts, medians, distributions, follow-up click rate from `feedback.jsonl`, themes of the open comments. Descriptive only.

## 6. Optional

| Run | What | Condition |
|---|---|---|
| X1 | Closed-book check: the same LLM answers 20 golden questions without retrieval; compare with the reference answers (PLAN section 6, prior-knowledge threat) | Only if A1 to A4 and the manual check are done; no config yet |

Not planned: a Vietnamese run (the golden set has no `vi` items), reranking and question decomposition (cut, ADR 0010).

## 7. Order and run log

Order: W7-D1-DAT-1 and W7-D1-FAO-1 confirm the stack and coverage (D17, by 09:30) and the golden set is at 60 items; then R1 to R3 (DAT runs them on the laptop, which has the frozen collection and the BM25 index; no LLM; after #168 is merged and FAO's coverage check, DAT, #160), then A1 to A4 one after another, then the relevance pass on each of their answer files; L1 is already done; U1 on D19 night. The Sunday buffer takes any run that did not finish.

After every run: check that `counts` and `golden.n_items` match the other runs, that `git_commit`, `index_snapshot` and the golden sha256 are the same, and for A1 to A4 that `generator.agent_config` shows the flags of the condition. Then fill the row.

| Run | Run file | Date | Commit | Host | Golden sha256 | Status |
|---|---|---|---|---|---|---|
| R1 | `evaluation/runs/20261102T111427Z-retrieval-final-hybrid.json` | 2026-11-02 | `3a2b92d` | DAT laptop | `1d05086d…` | done: n=60, R@5 0.508, R@10 0.583, MRR 0.474 |
| R2 | `evaluation/runs/20261102T111434Z-retrieval-final-dense.json` | 2026-11-02 | `3a2b92d` | DAT laptop | `1d05086d…` | done: R@5 0.458, R@10 0.492, MRR 0.420 |
| R3 | `evaluation/runs/20261102T111435Z-retrieval-final-bm25.json` | 2026-11-02 | `3a2b92d` | DAT laptop | `1d05086d…` | done: R@5 0.508, R@10 0.567, MRR 0.486; `compare`: `retrieval-final-compare.txt` |
| A1 | `evaluation/runs/20261102T111436Z-answers-w7-a1-mvp.json` | 2026-11-02 | `1638c06` (code = `3a2b92d`) | DAT laptop | `1d05086d…` | done: faithfulness 0.491 [0.39, 0.59], over-refusal 6/60, unanswerable refused 4/5 |
| A2 | `evaluation/runs/20261102T112100Z-answers-w7-a2-rewrite.json` | 2026-11-02 | `dac3848` (code = `3a2b92d`) | DAT laptop | `1d05086d…` | done: faithfulness 0.527 [0.43, 0.62], over-refusal 5/60, unanswerable refused 4/5 |
| A3 | `evaluation/runs/20261102T112723Z-answers-w7-a3-check.json` | 2026-11-02 | `32cf09d` (code = `3a2b92d`) | DAT laptop | `1d05086d…` | done: over-refusal 60/60, not scorable on faithfulness |
| A4 | `evaluation/runs/20261102T112800Z-answers-w7-a4-full.json` | 2026-11-02 | `367ccdc` (code = `3a2b92d`) | DAT laptop | `1d05086d…` | done: over-refusal 60/60, not scorable on faithfulness |
| V1 (A1) | `evaluation/runs/20261102T111436Z-answers-w7-a1-mvp.relevance.json` | 2026-11-02 | `4036333` (`main` `b729811` with this PR merged in) | DAT laptop | `1d05086d…` | done: relevance n=54, mean 2.31 [2.11, 2.52], ratings 1/2/3 = 11/15/28 |
| V2 (A2) | `evaluation/runs/20261102T112100Z-answers-w7-a2-rewrite.relevance.json` | 2026-11-02 | `61e7e42` (code = `4036333`) | DAT laptop | `1d05086d…` | done: relevance n=55, mean 2.44 [2.24, 2.62], ratings 1/2/3 = 8/15/32 |
| L1 | `docs/runbooks/performance.md` (run B `20261030T083604Z`) | 2026-10-30 | `v0.6-rc` + files of #148 | DAT laptop | | done (DAT, #161) |
| S1 | `pipelines/reports/scaling.md` | | | | | done in W6 |
| U1 | | | | | | not run |

Notes on this log (DAT, 2026-11-02):
- All seven runs used the same code. The script committed each run file as soon as it finished, so the runner recorded the commit that holds the previous run files: `1638c06`, `dac3848`, `32cf09d` and `367ccdc`. `git diff 3a2b92d 01da803 -- . ':!evaluation/runs'` is empty, so the code, prompts and configs are those of `3a2b92d` (`main` after #166, #168 and #160).
- `index_snapshot` and the golden sha256 (`1d05086d71904dcc479793c930b7586fd2afb0a0e4c1543b30c46f0ed3ec50bc`, Windows checkout) are the same in all seven files. Every A run has 0 errors and 0 judge errors.
- `+dirty` on R2 and R3 (LDN's question): the runner's `git_commit()` (`evaluation/src/scitech_eval/runner.py`) runs `git status --porcelain`, which also counts untracked files. The script ran R1, R2 and R3 back to back and committed the three files together (`1638c06`), so R2 saw R1's new run file and R3 saw R1's and R2's. R1 ran on a clean tree. No tracked file changed, so the code is `3a2b92d` for all three.
- Relevance (#171, `relevance-w7.yaml`, judge `qwen2.5:7b` `845dbda0ea48`) ran on 2026-11-02 on the stored A1 and A2 answers, after `main` (with #171) was merged into this branch (`4036333`); the agent was not called again. Rated: every answer that is not refused, not an error and not an unanswerable item; 0 judge errors. The A1-A2 difference is +0.12 and the intervals overlap. A3 and A4 have no rateable answer (all refused). The A2 numbers equal the trial run of #171 on the same file.
- Answer error analysis of A2 (W7-D4-DAT-1): `evaluation/reports/answer-errors-w7.md`.

## 8. Confirmations

- **DAT (approved #160 on 2026-10-31, answers written into this file):** A4 is the full agent (section 3); `split: all` for A1 to A4 (section 3); one commit, `main` after #166 is merged, hash posted on #156 (section 1); DAT runs R1 to R3 (sections 2 and 7); L1 is done (section 4); the relevance fallback (section 3). Settled earlier: the Ollama version and digests (W7-D1-DAT-1, #156), `judge.context_tokens: 4096` (written into the four configs) and `AGENT_TIMEOUT_S=600` (SNAPSHOT).
- **FAO:** confirmed on #160: coverage of the final golden set (W7-D1-FAO-1; passed on 2026-10-31, #156), half of the manual labels (W7-D3-FAO-1), S1 as it is, operator and host of U1. The full-index check of `gs-u03` to `gs-u05` and three random items of #168 were done on 2026-10-31 (#168); `gs-u04` was corrected afterwards.
