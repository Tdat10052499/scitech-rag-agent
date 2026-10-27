# Evaluation plan

- Status: draft 3 (W1-D3-LDN-1; updated 2026-10-16 after DAT's and FAO's review on PR #25); final version in W1-D5-LDN-1 after FAO's comments.
- Owner: LDN (`evaluation/`). Reviewers: DAT, FAO. Brief: `docs/tasks/W01-04-evaluation-plan.md`, issue #9.
- Scope reference: `docs/decisions/0010-compressed-schedule.md` (reduced scope), `docs/00-project-brief.md` (LLM/NLP sub-domain).

This plan says how the system will be judged, so that evaluation is designed now and not improvised in Week 7. Everything here is a plan: numbers, thresholds and sample sizes are targets, not results. Results will go to `evaluation/runs/` and `evaluation/reports/`, each stating dataset snapshot, model, parameters, commit hash and sample size (`evaluation/AGENTS.md`).

## 1. What is evaluated

| Part | Question it answers | Main metrics | Owner |
|---|---|---|---|
| Retrieval | Does the right evidence come back? | recall@k, MRR | LDN |
| Answers | Is the answer supported by the evidence it cites, and does it address the question? | faithfulness, cited-document recall, answer relevance, refusal rate, correct refusal rate | LDN (manual labels: LDN and FAO) |
| Follow-up suggestions | Do users find them useful? | usefulness rating, follow-up click rate | LDN |
| Efficiency | How fast, and how does it scale? | latency p50/p95, ingestion throughput, index build time | DAT (latency), FAO (scaling) |

Out of scope: training or fine-tuning, answer correctness against world knowledge (see section 7, prior knowledge), full-text PDFs, other topics than LLM/NLP.

## 2. Research questions

Each question is stated with the comparison that answers it. The expectations are hypotheses and may turn out wrong.

- **RQ1 (retrieval).** Does hybrid retrieval (dense + BM25, reciprocal rank fusion) give higher recall@k and MRR than dense-only or BM25-only on the golden set? Expectation: hybrid is at least as good as the better single retriever, and BM25 is competitive on questions that use exact technical terms. Reranking is not tested (cut, ADR 0010).
- **RQ2 (agent steps).** Do the agent steps that remain after ADR 0010, query rewriting and the evidence check, improve faithfulness compared with the MVP pipeline? Conditions: MVP (all flags off), +rewrite, +evidence check, full agent. Question decomposition is cut and is not tested. Expectation: rewriting helps mostly on follow-up and multi-turn items; the evidence check raises faithfulness but may raise the refusal rate.
- **RQ3 (follow-up suggestions).** Do users rate the suggested follow-up questions as useful, and do they click them? Evidence: a user study with 5-6 participants (cut-list item 5), so descriptive statistics only. No claim about a general effect.

## 3. Golden set

### 3.1 Purpose, size, language

The golden set is a list of questions with the documents that should be retrieved and a reference answer. It is used for retrieval metrics (RQ1), answer runs (RQ2) and, early on, for model choices (ADR 0006 and 0007).

Target size: 10 items at D03 (W1-D4-LDN-1), 30 at D06 (W2-D3-LDN-1), 45 at D09 (W3-D4-LDN-1), 60 at D14 (W5-D1-LDN-1).

Language: the main set is in English, because the corpus is English arXiv titles and abstracts (`docs/03-data-sources.md`). A small separate group of 5-10 Vietnamese questions on the same documents tests cross-lingual retrieval. DAT accepted it (issue #7) on the condition that it is dropped if the multilingual embedding model does not fit the D08 run (ADR 0007); the English-only bge models would handle it poorly. If kept, it is marked with `language: "vi"`, reported separately, and never mixed into the main recall@k and MRR numbers.

### 3.2 Item format (one JSON object per line in `evaluation/golden_set/golden.jsonl`)

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Unique, stable, for example `gs-001`. |
| `question` | string | The user question. For `follow_up` items, the last user turn. |
| `type` | string | One of `factual`, `explanatory`, `comparison`, `multi_hop`, `follow_up`, `unanswerable`. |
| `relevant_doc_ids` | list of strings | `doc_id` values, exactly as in the chunks (`chunk.schema.json`): the arXiv id without a version suffix (`2401.03205`, not `2401.03205v2`); old-style ids keep their slash (`cs/0501001`). Otherwise the coverage check and recall@k silently miss matches. These are the documents that contain the information needed. A multi-hop item lists at least 2. Empty list for `unanswerable` items. |
| `reference_answer` | string | Short answer written from the relevant documents; used as guidance for the judge, not as the only valid answer. For `unanswerable` items: the expected behaviour (the agent says the evidence is insufficient). |
| `notes` | string | How the item was written, what makes it hard, uncertainty about relevance. |
| `author` | string | Member code (`LDN`, `FAO`, `DAT`). |
| `split` | string | `dev` (items 1-30) or `test` (items 31-60), see 3.4. |
| `language` | string (optional) | `en` (default) or `vi`. |
| `history` | list (optional) | Earlier turns of the conversation for `follow_up` items (W5-D1-LDN-1 adds multi-turn items). |
| `standalone_query` | string (optional) | What a correct rewrite of the last turn should look like, for `follow_up` items. |

**Unanswerable group.** On DAT's request, about 5 extra items (not counted in the 60) have a question whose answer is not in the corpus, for example a recent event outside `cs.CL` or a detail that only appears in a full text. They check that the insufficient-evidence branch refuses when it should. The writer verifies by searching the sample or index that no document answers the question; absence cannot be proved for 122,000 papers, so the notes record what was searched. These items are excluded from recall@k and MRR (section 4).

The exact format, with validation rules, goes into `evaluation/golden_set/FORMAT.md` (W1-D4-LDN-1).

Example (the document is in FAO's 1,000-record sample; the coverage check will confirm it against the full index before the item is committed):

```json
{"id": "gs-001", "question": "Which aspects of large language model hallucination does the HaluEval 2.0 study investigate?", "type": "factual", "relevant_doc_ids": ["2401.03205"], "reference_answer": "Three aspects: how to detect hallucinations, why LLMs hallucinate (the sources across training and utilization stages), and how to mitigate them.", "notes": "Written from the abstract of arXiv 2401.03205; answerable from the abstract alone.", "author": "LDN", "split": "dev"}
```

### 3.3 How items are created and checked

1. Items are written from real documents: first the 1,000-record sample from FAO (arXiv `cs.CL` papers from 2022-2026, kept outside git in `data/raw/sample/sample.jsonl`), later the full index, so every question is answerable from the corpus (except the unanswerable group, 3.2). The sample is 2022-2026 only, while 26% of the index (32,246 of 121,860 records) is older (ADR 0003), so from item 31 on some items are written from older papers, using FAO's 200-record sample across all years (W2-D2-FAO-1, end of D05). Questions are phrased in the writer's own words, not copied from the abstract, to avoid favouring keyword matching.
2. `relevant_doc_ids` are the documents the writer judged necessary to answer. Other relevant documents may exist and are not labelled (see section 7).
3. FAO checks 3 random items of the first 10 (W1-D4-LDN-1) and runs the coverage script that confirms every `relevant_doc_ids` exists in the loaded index (W4-D3-FAO-1). Items 31-60 get the same coverage check.
4. The item mix covers all answerable `type` values, with at least 5 multi-hop and 5 follow-up items by 30 items. The unanswerable group (about 5 items) is added alongside: 2 `dev` items by D09 and the rest as `test` items by D14. Two items are too few to tune a threshold, so `RETRIEVAL_MIN_SCORE` is tuned on the answerable dev items (keeping over-refusal low), and the 2 unanswerable dev items only check that they are refused.

### 3.4 Development and test items

The same items must not be used to choose settings and to report final results. Agreed with DAT (review of PR #25):
- Items 1-30 (`split: dev`) may be used for decisions: model choice (ADR 0006), embedding model (ADR 0007), default retriever (ADR 0009), prompt wording and thresholds such as `RETRIEVAL_MIN_SCORE`.
- Items 31-60 (`split: test`) are not used for any decision. The final report gives numbers on all 60 items and on the 30 test items, and says if they differ materially.
- W3-D4-LDN-1 reports on all items available (45) for information, but ADR 0009 cites the dev numbers (items 1-30) as its basis.

## 4. Metrics

Notation: for question `q`, `R_q` is the set of relevant `doc_id`s (`relevant_doc_ids`), `N` the number of questions evaluated.

### 4.1 Retrieval (RQ1)

The retriever returns a ranked list of chunks. A chunk is a hit if its `doc_id` is in `R_q`. `k` is applied to the chunk list, as the LLM would receive it.

- **Recall@k** for `k` in {1, 5, 10}: `recall@k(q) = |R_q ∩ D_k(q)| / |R_q|`, where `D_k(q)` is the set of distinct `doc_id`s among the top-k chunks. Reported as the mean over `q`. For items with one relevant document it equals hit rate. At small `k`, several chunks of the same document use up slots; this is part of the system's behaviour and is not corrected.
- **MRR** (mean reciprocal rank): `MRR = (1/N) * sum_q 1/rank_q`, where `rank_q` is the position of the first hit chunk in the top 10, and the term is 0 if there is none. Ranks are positions in the chunk list. Several chunks of one document do not change this: only the first hit chunk counts, and later chunks of the same document are not skipped when ranks are counted.
- **Scope.** `unanswerable` items have no relevant document and are excluded from recall@k and MRR (N counts answerable items only).
- **Reporting.** Always give `N` and a 95% bootstrap interval over questions (1,000 resamples). Compare two retrievers on the same questions: per-question differences, number of wins and losses, and the bootstrap interval of the mean difference. Per-type cells can be very small (fewer than 10 items); report `n` per cell and do not compare cells that small.

### 4.2 Answers (RQ2)

Only non-refused answers to answerable items enter the faithfulness and relevance metrics. A refused answer is not scored, even if it still contains factual sentences; their number is reported next to the refusal rate, so the choice is visible. Refusals are reported separately.

- **Faithfulness rate.** The answer is split into sentences. Sentences without factual content (greetings, "I cannot answer", pure structure) are not checkable. Each checkable sentence is labelled *supported* or *not supported* by the chunks it cites with `[n]`, judged on those chunks only (procedure in section 5). `faithfulness(a) = supported / checkable` per answer; headline = mean over answers (macro), with the pooled rate over all sentences (micro) as a check. Also report the share of answers with faithfulness = 1.
- **Cited-document recall.** `|R_q ∩ cited docs(a)| / |R_q|`: how many of the needed documents the answer actually cites. Combined with recall@k it shows whether the agent uses the evidence it retrieved.
- **Invalid-citation rate.** Share of `[n]` markers pointing to a non-existent source number (counted before DAT's parser drops them; the agent trace of W5 stores the raw answer text, which DAT confirmed).
- **Refusal rate (over-refusal).** Share of answers to answerable items where the agent reports insufficient evidence. Because these questions are answerable from the corpus, a high refusal rate is over-refusal, and it is reported next to faithfulness so that raising faithfulness by refusing more is visible.
- **Correct refusal rate.** On the unanswerable group: share of items where the agent reports insufficient evidence. The complement is the share answered anyway, which are checked by hand for unsupported claims. With about 5 items each item is 20 points, so this is a coarse check, reported as a count (for example 4 of 5).
- **Answer relevance.** Rating from 1 to 3 for how well the answer addresses the question: 1 = does not address it, 2 = partly, 3 = fully. Judged by an LLM judge against the question and the reference answer, and checked manually on the same sample as faithfulness. Reported as mean and distribution.

### 4.3 Follow-up suggestions (RQ3)

- **Usefulness rating.** Post-task questionnaire item on a 1-5 scale ("The suggested follow-up questions were useful"), plus open comments (`evaluation/user_study/PROTOCOL.md`, W6-D3-LDN-1). Report `n`, mean, median and the full distribution.
- **Follow-up click rate.** `clicks on suggestions / answers shown`, from `data/logs/feedback.jsonl`, and the share of clicked follow-ups that received a thumbs-up.
- **Optional offline check** (if time remains): for 20 sampled suggestion sets, whether each suggestion is answerable from the corpus (relevant document in the top 5). Report as an extra, not as a headline result.

### 4.4 Efficiency (not a research question)

Latency (time to first token, total time; p50 and p95 over 30 golden questions) is measured by DAT on the frozen system; ingestion throughput, index build time and scaling by FAO. They are described in `docs/runbooks/performance.md` and `pipelines/reports/scaling.md`. This plan only requires that hardware, endpoint and conditions are stated with every number.

## 5. Faithfulness procedure (draft; finalised and piloted in W4-D4-LDN-1)

Principle: faithfulness means "supported by the cited chunks", not "true". A sentence can be true and still unsupported if the cited chunks do not say it; the LLM may know it from training, which is the prior-knowledge threat (section 7).

Manual protocol (written so that a second annotator can apply it):
1. The annotator sees the question, the answer sentence by sentence, and the text of the chunks cited in each sentence, and nothing else (no web, no own knowledge).
2. For each sentence with factual content, label:
   - *supported*: every factual element of the sentence (entities, numbers, relations, comparisons) is stated in, or directly follows from, the cited chunks;
   - *not supported*: anything else, including a sentence with no citation, a citation to a chunk that does not contain the claim, and a sentence that is only partly covered (partial support is recorded in a note and counts as not supported);
   - *not checkable*: no factual content.
3. Numbers and names must match exactly; paraphrase is allowed.
4. Record the label, a one-line reason for every *not supported*, and the annotator.
5. Several citations in one sentence (`[1][2]`): the cited chunks count together. The sentence is *supported* if the chunks taken together state every element; otherwise write in the reason which `[n]` is missing.
6. A sentence with factual content and no `[n]` is *not supported*. A citation `[n]` with no source `n` is marked `INVALID` in the sheet: there is no chunk to check against, so a sentence that cites only invalid numbers is *not supported*.
7. A sentence with two claims, one supported and one not, is *not supported*; write the unsupported claim in `reason` and put "partial" in `partial_note`.
8. Hedging is part of the claim: a source that says a method "suggests" or "may" and a sentence that says it "proves" or "always" is *not supported*. The other direction is allowed: a source that says a method "improves" X supports a sentence that says it "may improve" X, because the weaker claim follows from the stronger one.
9. A lead-in such as "According to the sources," is not a claim; judge the rest. A lead-in that only announces a list ("Two ways are:") and a sentence made only of citation markers are *not checkable*. A lead-in that names a source is different: in "According to Smith et al. (2023)," the name and the year are factual elements and must be stated in the cited chunk text. The chunks hold the title and the abstract only, with no author list or publication year of the paper itself, so such a name or year is *supported* only if the abstract states it (for example for a cited work). The title of the paper is part of the chunk, so a quoted title is *supported* when it matches.
10. A refusal sentence ("the evidence is insufficient") is *not checkable*. If the same answer also states facts, label those sentences as usual in the sheet; whether the answer is scored is decided by section 4.2 (refused answers are not scored, and their factual sentences are counted and reported). A sentence that only says what the sources do or do not contain ("The sources do not give the parameter count", "No source mentions X") is also *not checkable* and needs no citation, because it is a statement about the sources, not about the world. A sentence that also states something about the world is labelled as usual. These sentences are counted and reported with the refusals, because the procedure cannot detect a wrong "not in the sources".
11. Sentences come from `evaluation/pilot/faithfulness/` `make-sheet` (rules in `answers.py`). If a sentence is cut in the wrong place, label each piece as it stands and write "split" in `partial_note`; do not merge or re-cut sentences by hand, because the judge sees the same pieces.

LLM judge: same input and the same three labels, one sentence per call, with a fixed prompt stored in `evaluation/`. Settings: temperature 0. The judge model must differ from the generator; DAT chooses it in ADR 0006 (D06), the candidate being the hosted API fallback of ADR 0001, and it is named in `evaluation/SNAPSHOT.md`.

Calibration: a random 20% of the answers are labelled by hand (split between LDN and FAO, same written procedure; DAT does not annotate because he built the agent). Report agreement between judge and human as Cohen's kappa on the sentence labels together with the raw agreement; where they disagree, the human label is used for the headline numbers, and this choice is stated. The pilot on 10 questions in W4-D4-LDN-1 tests whether two readings of the procedure agree before the full run.

## 6. Baselines and conditions

Retrieval (RQ1), same golden set and index snapshot for all, `k` in {1, 5, 10}:
- dense only (embedding model from ADR 0007),
- BM25 only,
- hybrid (RRF; default chosen in ADR 0009).

Agent (RQ2), same retriever, same model, same prompts, temperature fixed and stated:
- MVP: `AGENT_REWRITE=off`, `AGENT_SELF_CHECK=off`,
- +rewrite,
- +evidence check,
- full agent.

Per-type breakdown is reported for RQ2, because rewriting should matter mainly for `follow_up` items. The unanswerable group is run under the same four conditions to see whether the evidence check changes the correct refusal rate.

Diagnostic for the prior-knowledge threat (optional, if time remains): ask the same LLM the golden questions without retrieval ("closed book") and compare with the reference answers on a sample of 20. If the closed-book answers are often right, a faithful-looking answer proves little about retrieval, and the report says so.

All runs record: configuration file, git commit hash, dataset snapshot id (from FAO's manifest), model identifier and parameters, timings. Runs are listed in `evaluation/RUNS.md` (W6-D5-LDN-1) and stored in `evaluation/runs/`. After the feature freeze, a fix means the affected runs are repeated. Each condition is run once; LLM output is not fully deterministic, so differences smaller than the run-to-run variation (measured on a subset if time allows) are not interpreted.

## 7. Threats to validity and limitations

- **Small sample.** 60 items; per-type cells below 10; bootstrap intervals will be wide. Differences between systems may not be distinguishable from noise, and no significance claims are made for small differences.
- **Single-author bias.** Most items are written by one person, from abstracts, which can favour keyword matching (BM25) even with rephrased questions. FAO checks a part of the items; this reduces but does not remove the bias.
- **Incomplete relevance labels.** Only the documents the writer found are labelled. Other relevant documents in a corpus of about 122,000 papers count as misses, so recall and MRR are conservative estimates.
- **Selection on test data.** Items used for decisions would give optimistic numbers; the dev/test split in section 3.4 limits this, but only if the rule is followed.
- **Prior knowledge (LLM/NLP topic).** The LLM knows this field from training and may answer from memory instead of the retrieved evidence. Faithfulness is therefore judged against the cited chunks only, so a correct claim from memory counts as unsupported. The opposite also holds: an answer can be faithful to a wrong or irrelevant chunk. Faithfulness is not correctness, and the report must not present it as such.
- **Judge bias.** An LLM judge can prefer its own style, long answers, or fail on subtle numeric differences. The manual sample (20%) estimates this; the sample is small and the agreement figure itself has a wide interval.
- **Annotators.** Two annotators label different halves with one written procedure, so agreement between annotators is unknown (no double annotation). DAT does not annotate; this is a limitation, not a flaw in the procedure.
- **Corpus and snapshot.** Titles and abstracts of arXiv `cs.CL` papers from one snapshot (121,860 records, Kaggle snapshot version 307 of 2026-10-10, ADR 0003); questions that need full text are out of scope. Incremental ingestion after the freeze is not part of the evaluated index.
- **Year bias.** The first items come from a 2022-2026 sample, while 26% of the index is older. Until items from older papers are added (from item 31 on), results mainly describe recent papers.
- **Simplified system.** Reranking and decomposition were cut (ADR 0010); results describe the reduced system, not the original design.
- **Run variability.** The LLM runs on an external GPU session that can end and may be replaced by a fallback model; each run records the model actually used. One run per condition.
- **User study.** 5-6 classmates, a convenience sample of AI students who know the team: possible courtesy bias, not representative of general users. Descriptive statistics only.
- **Vietnamese subset (if kept).** Very small, written by one person, and affected by translation choices; not comparable with the English numbers.
- **Unanswerable group.** About 5 items written by one person who knows the corpus; absence of an answer is checked by search, not proved. The correct refusal rate has a resolution of 20 points and is descriptive only.

## 8. Who does what, and when

| Step | Task ID | Date |
|---|---|---|
| Plan draft / final | W1-D3-LDN-1 / W1-D5-LDN-1 | 14 Oct / 15 Oct |
| Golden-set format and 10 items | W1-D4-LDN-1 | 15 Oct |
| Evaluation harness (recall@k, MRR) | W2-D4-LDN-1 | 17 Oct |
| Golden set to 30 | W2-D3-LDN-1 | 19 Oct |
| First dense run; dense/BM25/hybrid comparison, set to 45 | W3-D3-LDN-1 / W3-D4-LDN-1 | 22 Oct |
| Faithfulness procedure and pilot | W4-D4-LDN-1 | 26 Oct |
| Golden set to 60 (multi-turn, multi-hop) | W5-D1-LDN-1 | 27 Oct |
| End-to-end answer runner | W5-D4-LDN-1 | 28 Oct |
| User-study protocol, run plan (`RUNS.md`) | W6-D3-LDN-1 / W6-D5-LDN-1 | 29-30 Oct |
| Final retrieval runs, faithfulness, user study, `final.md` | W7-D1..D5-LDN-1 | 31 Oct - 3 Nov |

Task dates follow `docs/plan/calendar.md`. LDN is away on 23-26 October; DAT proposed a replan on issue #10 (W4 tasks pulled forward or moved to D12-D13). The dates of the W4 tasks above will change once the replan is agreed and written into `docs/plan/week-03.md` and `week-04.md`.

## 9. Decisions after DAT's review (PR #25) and what is still open

Decided:
1. Vietnamese subset: accepted as a separate group, dropped if the multilingual model does not fit the D08 run (DAT, issue #7).
2. Unanswerable group: added (about 5 items, correct refusal rate, excluded from recall@k and MRR).
3. Judge model: different from the generator; DAT decides it in ADR 0006 on D06 and names it in `evaluation/SNAPSHOT.md`.
4. Dev/test split: agreed; ADR 0009 cites the dev numbers (items 1-30). ADR 0006 on D06 uses the first 10 dev items, so its numbers are indicative only (n = 10).
5. Sentence splitting: decided by the W4 pilot; keep whichever gives better judge-human agreement.
6. DAT does not annotate faithfulness (he built the agent); no double annotation stays listed as a limitation.

Requirements this plan puts on other modules (confirmed by DAT): the agent trace stores the raw answer text (W5); latency p50/p95 over 30 golden questions on the frozen system (W6/W7); `POST /feedback` logs to `data/logs/feedback.jsonl` (W6).

Still open:
- FAO's check of the first 10 items and of the plan (annotator split, coverage check).
- Whether the Vietnamese group survives the choice of embedding model (ADR 0007).
- Which 5 questions go into the unanswerable group, and which 2 are `dev`.
