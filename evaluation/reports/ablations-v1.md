# Agent ablations v1: query rewrite and LLM self-check on the dev golden set

Task: W7-D2-DAT-1. Status: **draft, not reviewed**. This is an evaluation result, so it needs a review by LDN or FAO before merging. Drafted with AI assistance (Claude); DAT ran every condition and is responsible for the text.

## 1. What this report is

The report compares four agent configurations that differ only in two flags: `AGENT_REWRITE` (rewrite a follow-up question into a standalone search query) and `AGENT_SELF_CHECK` (one LLM call before answering that asks whether the sources answer the question, and refuses on NO). Each condition answers the same 32 dev items. The answers are judged with LDN's answers runner (#148).

| Condition | `AGENT_REWRITE` | `AGENT_SELF_CHECK` |
|---|---|---|
| mvp | off | off |
| rewrite | on | off (the frozen configuration in `evaluation/SNAPSHOT.md`) |
| evidence | off | on |
| full | on | on |

## 2. Setup and provenance

| Item | Value |
|---|---|
| Run by | DAT, 2026-10-30, 08:53–09:05 UTC, one condition after another in one PowerShell window |
| Code | `main` at `fa1c765` (#148 merged). The run files say `+dirty` because the four configs below were copied in uncommitted; nothing else differed |
| Host | DAT's laptop: RTX 5060 Laptop 8 GB, Ollama 0.40.13 at 100% GPU, context 4096; Qdrant 1.19.2 native at `http://127.0.0.1:6333` (`docs/runbooks/performance.md`) |
| Generator | `llama3.2:3b`, digest `a80c4f17acd5`, temperature 0, `answer_max_tokens` 512, hybrid retrieval top_k 5 |
| Judge | `qwen2.5:7b`, digest `845dbda0ea48`, temperature 0, max_tokens 200, context 4096; prompt sha256 `c910b2e9…` |
| Dataset / index | `kaggle-arxiv-v307-cs.CL-2026-10-10`; `scitech_chunks/bge-small-en-v1.5/chunked-2026-10-17T05:19:12/embedded-2026-10-17T06:40:37` |
| Golden set | `split: dev`, 32 items: 30 answerable (5 of them follow-up turns) and 2 unanswerable; sha256 `88c86717…` |
| Intervals | 95% bootstrap over answers, 1000 resamples, seed 0 |
| Configs | `evaluation/configs/ablation-{mvp,rewrite,evidence,full}.yaml` |
| Run files | `evaluation/runs/20261030T090452Z-ablation-mvp.json`, `…T085601Z-ablation-rewrite.json`, `…T085910Z-ablation-evidence.json`, `…T085934Z-ablation-full.json` |

The answers and traces files (`*.answers.jsonl`, `*.traces.jsonl`) stay on the laptop.

The first mvp run (`20261030T085300Z`) is not used. In that run, gs-015 failed with `retrieval_failed` because Qdrant closed the connection ("Server disconnected without sending a response"). The rerun 12 minutes later had 0 errors.

## 3. Results

| | mvp | rewrite | evidence | full |
|---|---|---|---|---|
| Errors | 0 | 0 | 0 | 0 |
| Answerable refused (over-refusal rate) | 5/30 (0.17) | 5/30 (0.17) | **30/30 (1.00)** | **30/30 (1.00)** |
| Unanswerable refused | 2/2 | 2/2 | 2/2 | 2/2 |
| Judged answers / sentences | 25 / 78 | 25 / 76 | 0 / 0 | 0 / 0 |
| Faithfulness, macro [95% CI] | 0.556 [0.42, 0.67] | 0.576 [0.44, 0.70] | n/a | n/a |
| Faithfulness, micro (supported / checkable) | 0.500 (38/76) | 0.514 (38/74) | n/a | n/a |
| Answers with faithfulness 1 | 0.20 | 0.24 | n/a | n/a |
| Cited-document recall | 0.24 | 0.28 | n/a | n/a |
| Retrieved-document recall (answered items) | 0.36 | 0.40 | n/a | n/a |
| Invalid-citation rate | 0.0 | 0.0 | n/a | n/a |
| LLM calls per item (from the phases timed) | 1.78 | 1.94 | 1.00 | 1.16 |
| First token p50 / p95 (ms) | 422 / 2413 | 422 / 2618 | 359 / 407 | 125 / 669 |
| Total p50 / p95 (ms) | 4226 / 6054 | 4243 / 6067 | 359 / 407 | 125 / 669 |

The LLM calls column counts these calls:
- the answer call, on every item not refused before answering;
- the follow-up suggestions call, on every answer that was not a refusal;
- the self-check call;
- the rewrite call, on the follow-up turns.

The judge is not included. Latency is the agent only, measured in-process, without the judge, as in the performance runbook. The rewrite and evidence latencies are listed for completeness, not as a separate benchmark.

## 4. Findings

**4.1 The self-check refuses every question with this generator.** In the evidence and full conditions, the trace records `self_check: "no"` and `decision: "refuse_self_check"` for all 32 items. DAT counted the traces on the laptop, and `parse_verdict` read every reply as NO; there were no LLM errors and no unreadable replies. The self-check is therefore not "conservative" here, it is a constant: with `llama3.2:3b` and `prompts/self_check.md` it answers NO even when the sources hold the answer. Examples are gs-010, gs-013 and gs-017, which every other condition answered with faithfulness 1.0 or 0.67 and cited-document recall 1.0.

Consequence: the "+evidence" and "full" conditions cannot be scored on faithfulness, and the result supports keeping `AGENT_SELF_CHECK=off` in the frozen configuration. Why the model always answers NO is not established by these runs. Possible causes are the 3B model, the prompt wording, or `self_check_max_tokens` 8 cutting a longer reply that starts with "No". The answers runner does not keep the raw self-check text, so these causes cannot be told apart here.

**4.2 Query rewrite changes only the follow-up turns, and the effect is not measurable at n = 5.** At temperature 0, the 25 items that are not follow-up turns gave identical answers and labels in mvp and rewrite. All differences come from the 5 follow-up turns:

| Item | mvp | rewrite |
|---|---|---|
| gs-018 | answered, faithfulness 0.33, retrieved recall 0 | refused |
| gs-019 | answered, faithfulness 0.67, retrieved recall 0 | answered, faithfulness 1.0, **retrieved recall 1.0** |
| gs-022 | refused | answered, faithfulness 0.5, retrieved recall 0 |
| gs-023 | answered, faithfulness 1.0, retrieved recall 0 | answered (different sources), faithfulness 1.0, retrieved recall 0 |
| gs-024 | refused | refused |

In this sample, rewrite found the relevant paper in 1 of 5 follow-ups, and mvp found it in 0. The overall macro difference (0.556 vs 0.576) lies well inside both intervals. This is an illustration of what rewrite does, not evidence that it improves faithfulness.

**4.3 Cost.** Rewrite adds one short LLM call on follow-up turns only: 0.2–0.3 s on three of them, and about 2.2 s on gs-019 and gs-022. The p50 latency is unchanged. The self-check costs one call per question, about 0.1–0.4 s, but in these runs it removes every answer, so its cost cannot be weighed against a benefit.

## 5. Limits

- One run per condition, on one host. Temperature is 0, but answers already differed between Kaggle sessions in W4, so small differences between runs are not reliable.
- 30 answerable items, of which only 5 are follow-up turns. The test split was not used.
- Faithfulness is judged by a 7B model that has not been validated against human labels (runner note; the manual sample is W7-D2-LDN-1). "Supported" means supported by the cited passages, not true.
- Over-refusal counts refused answerable items and says nothing about whether the refused items were in fact answerable from the retrieved sources.
- The "+decompose" condition was cut in the replan and is not run.

## 6. Next steps (not part of this task)

- Record the four run files in `evaluation/RUNS.md` when LDN creates it (W7-D2-DAT-1 done-when).
- If the self-check is to be reported as more than "always NO", keep its raw reply in the trace and try it on a few items by hand. With the feature freeze, that is a post-presentation item.
