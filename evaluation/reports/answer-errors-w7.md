# Answer error analysis, Week 7 (W7-D4-DAT-1)

Status: draft by DAT, 2026-11-02, from the W7 runs in `evaluation/RUNS.md` section 7. It is written for the error-analysis section of `final.md` (W7-D5-LDN-1). Drafted with AI assistance (Claude); DAT is responsible for the final text.

## 1. Scope and method

- **Runs.** The main source is A2 (`evaluation/runs/20261102T112100Z-answers-w7-a2-rewrite.json`). A2 is the product configuration (rewrite on, evidence check off; SNAPSHOT section 2). A1 is used for comparison, and R1 (`20261102T111427Z-retrieval-final-hybrid.json`) is used for the retrieval of refused items. All runs have the same code (`3a2b92d`), index, golden file (65 items: 60 answerable, 5 unanswerable) and host (DAT's laptop, `llama3.2:3b` generator, `qwen2.5:7b` judge).
- **Cases.** The plan asks for 20 low-faithfulness or refused answers. These are the 5 answerable items A2 refused, plus the 15 judged answers with the lowest faithfulness, ties broken by lower retrieved-document recall. All 15 have faithfulness of 0.25 or lower.
- **Cause.** Each case gets one cause from a fixed rule, applied in this order:
  1. **Over-refusal:** an answerable item was refused.
  2. **Retrieval miss:** no relevant document was in the 5 sources (`retrieved_doc_recall` = 0).
  3. **Missing citations:** at least as many unsupported sentences have no `[n]` as have one.
  4. **Cited claim not supported:** otherwise.
- **Evidence used.** The fields of the run file are the only input: the per-sentence judge labels and reasons, cited and retrieved document recall, and the citation numbers. The answer texts and passages are in the `.answers.jsonl` and `.traces.jsonl` files on DAT's laptop, which are not committed (`.gitignore`). No case was re-read by a person for this draft.

## 2. Overall picture (A2, 55 judged answers, 155 sentences)

| Measure | A1 (MVP) | A2 (+rewrite) |
|---|---:|---:|
| Faithfulness, macro [95% CI] | 0.491 [0.39, 0.59] | 0.527 [0.43, 0.62] |
| Faithfulness, micro (supported / checkable) | 0.408 (62/152) | 0.441 (67/152) |
| Cited sentences supported | 62/82 (0.76) | 67/88 (0.76) |
| Sentences without a citation | 70 (all "not supported") | 64 (all "not supported") |
| Share of "not supported" sentences that have no citation | 70/90 (0.78) | 64/85 (0.75) |
| Answers with no citation at all | 7 | 6 |
| Relevant document retrieved but none cited | 7 | 8 |
| Cited-document recall [95% CI] | 0.398 [0.27, 0.53] | 0.427 [0.30, 0.55] |
| Answerable items refused | 6/60 | 5/60 |
| Unanswerable items refused | 4/5 (`gs-u05` answered) | 4/5 (`gs-u05` answered) |
| Invalid citations | 0 | 0 |

Faithfulness by question type in A2, as mean with n: factual 0.58 (11), explanatory 0.54 (17), follow-up 0.70 (9), multi-hop 0.42 (10), comparison 0.36 (8). In A1 the follow-up mean was 0.48 (8); the other types are unchanged.

Faithfulness did not differ with retrieval: A2 answers with no relevant document in their sources averaged 0.53 (n = 20), the others 0.52 (n = 35). This is expected from the metric. Faithfulness asks whether a sentence is supported by the passage it cites, not whether the answer is correct. A fluent answer built on the wrong papers can still score high.

## 3. The 20 cases (A2)

"Retrieved recall" for refused items is R1's hybrid recall@5 on the raw question. A2 rewrites follow-up questions before searching, so for `gs-018` and `gs-024` it is only an indication.

| # | Item | Type | Faith. | Retrieved recall | Cited recall | Unsupported: uncited / cited | Cause (rule) | Judge reason (first unsupported sentence) |
|---|---|---|---:|---:|---:|---|---|---|
| 1 | gs-008 | factual | refused | 1.0 (R1 hybrid @5) | - | - | over-refusal | - |
| 2 | gs-012 | factual | refused | 0.0 (R1 hybrid @5) | - | - | over-refusal | - |
| 3 | gs-018 | follow_up | refused | 0.0 (R1 hybrid @5) | - | - | over-refusal | - |
| 4 | gs-021 | multi_hop | refused | 0.0 (R1 hybrid @5) | - | - | over-refusal | - |
| 5 | gs-024 | follow_up | refused | 0.0 (R1 hybrid @5) | - | - | over-refusal | - |
| 6 | gs-001 | multi_hop | 0.00 | 0.00 | 0.00 | 3 / 2 | retrieval miss | The cited passages are empty, providing no basis to support or refute the claim. |
| 7 | gs-040 | comparison | 0.00 | 0.00 | 0.00 | 1 / 3 | retrieval miss | The cited passage does not discuss grouped-query attention or mixture-of-depths, and does not compare the two methods in terms of computatio |
| 8 | gs-042 | multi_hop | 0.00 | 0.50 | 0.00 | 2 / 2 | missing citations | The cited passages are empty, providing no evidence for the claim about exact nearest neighbor search being worth its cost or about approxim |
| 9 | gs-009 | explanatory | 0.00 | 1.00 | 0.00 | 2 / 0 | missing citations | The cited passages are empty, providing no evidence for the claims made in the sentence. |
| 10 | gs-027 | factual | 0.00 | 1.00 | 0.00 | 2 / 0 | missing citations | The cited passages do not contain any information about the number of parameters used per input token or the amount of training data. |
| 11 | gs-032 | factual | 0.00 | 1.00 | 1.00 | 1 / 1 | missing citations | The cited passages do not exist. |
| 12 | gs-034 | factual | 0.00 | 1.00 | 0.00 | 2 / 0 | missing citations | The cited passages do not contain any information about BERT, contrastive pruning, QQP, MNLI, or the accuracy of BERT after pruning. |
| 13 | gs-036 | explanatory | 0.00 | 1.00 | 1.00 | 2 / 1 | missing citations | The cited passages are empty, providing no evidence for the claim. |
| 14 | gs-051 | explanatory | 0.00 | 1.00 | 0.00 | 2 / 0 | missing citations | There are no cited passages to support the sentence. |
| 15 | gs-053 | comparison | 0.00 | 1.00 | 0.00 | 2 / 0 | missing citations | The cited passages do not exist. |
| 16 | gs-055 | multi_hop | 0.00 | 1.00 | 0.00 | 3 / 0 | missing citations | The sentence claims two ways to reduce overconfidence in language models, but no cited passages are provided to verify this information. |
| 17 | gs-005 | comparison | 0.14 | 0.50 | 0.50 | 6 / 0 | missing citations | The cited passages are empty, providing no information to support or refute the claim about chunk size affecting answer quality in RAG syste |
| 18 | gs-052 | comparison | 0.14 | 1.00 | 1.00 | 5 / 1 | missing citations | The cited passages are empty, providing no information to support or refute the claim. |
| 19 | gs-004 | comparison | 0.25 | 0.00 | 0.00 | 3 / 0 | retrieval miss | The cited passages do not exist to support the claim. |
| 20 | gs-044 | follow_up | 0.25 | 1.00 | 1.00 | 2 / 1 | missing citations | The cited passages are empty, providing no evidence for the claim. |

Count by cause: missing citations 12, over-refusal 5, retrieval miss 3, cited claim not supported 0. The last category is empty because the rule takes "missing citations" first. 7 of the 15 judged cases also have at least one cited sentence that the judge did not accept (column "uncited / cited").

## 4. Causes

### 4.1 Missing citations (12 of 20; the largest cause)

- **Evidence.** In A2, 64 of the 85 "not supported" sentences (75%) carry no `[n]`. The judge labels every uncited sentence "not supported" ("the cited passages are empty"), as `PLAN.md` section 5 says. Sentences that do cite a passage are supported 76% of the time (67/88).
- **Retrieval was not the problem.** In all 12 cases at least one relevant document was among the sources: retrieved recall was 1.0 in 10 cases and 0.5 in 2. In 7 of them no relevant document was cited (cited recall 0). Example: `gs-034` retrieved the right paper but the answer cites nothing about it; the judge says the cited passages "do not contain any information about BERT, contrastive pruning, QQP, MNLI".
- **Reading.** The 3B generator often writes a correct-looking sentence from a source without the marker, or from its own prior knowledge. These runs cannot separate the two: that needs the answer text and passages (section 6). The low score is partly a citation-format failure, not only unfaithfulness. This matches #115 and DAT's pilot on #148 (18 of 22 unsupported sentences were uncited).
- **Sensitivity.** Counting cited sentences only, micro faithfulness would be 0.76 instead of 0.44. The report should give both numbers and say which one is the headline.

### 4.2 Over-refusal (5 of 20)

- **`gs-008`** is a true over-refusal: R1 found the relevant document at rank 5 or better, and the model still said the sources were insufficient.
- In **`gs-012`** and **`gs-021`**, the relevant documents were not in R1's top 5. A refusal is the correct behaviour given those sources. The cause is retrieval, not the answer step.
- **`gs-018`** and **`gs-024`** are follow-up turns. R1 searches with the raw follow-up question, so its recall of 0 does not show what A2's rewritten query found. Without the trace, the cause stays open.
- **Overall rate.** A2 over-refused 5/60 (0.08) and A1 6/60 (0.10). A3 and A4 refused 60/60. Section 5 covers why.

### 4.3 Retrieval miss (3 of 20)

- `gs-001` (multi-hop), `gs-040` (comparison) and `gs-004` (comparison) had no relevant document among their sources, and the model answered anyway.
- This matches R1 by type: recall@5 was 0.32 for multi-hop and 0.50 for comparison, against 0.85 for factual. Questions that need two papers are where retrieval fails, and question decomposition, which targeted them, was cut (ADR 0010).
- **Unanswerable `gs-u05`** (Gemini's parameter count) was answered in both A1 and A2. FAO found three abstracts that mention Gemini near "parameter" without giving its size (#168). The likely cause is that retrieval brings these near-matches and the model reports a number for another model. That is a hypothesis to check in the answer text.

## 5. The evidence check (A3, A4)

- **Result.** With `AGENT_SELF_CHECK=on`, every answerable item was refused (60/60) and every unanswerable item too (5/5). Each run took about 29 s of answer time for 65 items. This is the same result as `ablations-v1.md` (32/32 on the dev split): the self-check prompt with `llama3.2:3b` returns NO whatever the sources.
- **Consequence.** These two conditions cannot be scored on faithfulness. The result supports keeping the check off in the product.
- **Cause not established.** The runs cannot tell whether the cause is the model size, the prompt, or `self_check_max_tokens` 8, because the raw self-check reply is not stored.

## 6. Limits of this analysis

- **Judge not validated.** The judge (`qwen2.5:7b`) has not yet been checked against human labels for these runs. The 20% manual sample (W7-D2-LDN-1, `make-sheet --sample 0.2 --seed 20261031`) is still to do. Every cause above rests on its labels.
- **Rule-based causes.** The causes come from a fixed rule on the run fields, not from a person reading answers and passages. "Model ignored evidence" (the right passage was cited but misread) cannot be told apart from "missing citations" without the texts, so it is not counted.
- **Small and single.** n is small: 8 to 17 per question type, 20 cases. Each condition was run once. Differences between A1 and A2, including follow-up 0.48 against 0.70, are inside the run-to-run variation (PLAN section 6) and are not interpreted as effects.
- **Correlation, not cause.** The link between question type, retrieval and faithfulness is an association in one run, not a measured cause.

## 7. Future work (no code changes before v1.0)

1. **Citation enforcement:** after generation, find sentences without `[n]`. Either ask the model once to add the marker from the sources, or drop the sentence and say so. This targets the largest cause (4.1). Measure it with the same A2 setting and the cited-only and all-sentence faithfulness.
2. **Stronger generator:** run A2 with `qwen2.5:7b` or a hosted model as generator, with another model as judge (PLAN section 5 requires them to differ). This would show how much of 4.1 and 5 is the 3B model.
3. **Multi-hop and comparison retrieval:** question decomposition, or retrieving per entity named in the question, for the types with recall@5 of 0.32 and 0.50 (4.3).
4. **Self-check calibration:** store the raw reply, raise `self_check_max_tokens`, and try the check with a larger model before using it again (5).
5. **Follow-up retrieval evaluation:** evaluate retrieval on the rewritten query (`standalone_query` in the golden set), not only the raw question. R1 gives follow-ups recall@5 0.09, which says little about the product.
