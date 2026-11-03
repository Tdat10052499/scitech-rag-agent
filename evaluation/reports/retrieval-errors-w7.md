# Retrieval error analysis, Week 7 (W7-D3-FAO-1)

Status: draft by FAO, 2026-11-02, from the W7 retrieval runs R1 to R3 in `evaluation/RUNS.md` section 7 (#179). It is written for the error-analysis section of `final.md` (W7-D5-LDN-1), next to DAT's answer error analysis (`evaluation/reports/answer-errors-w7.md`, W7-D4-DAT-1). Drafted with AI assistance (Claude); FAO is responsible for the final text.

## 1. Scope and method

- **Runs.** R1 hybrid (`evaluation/runs/20261102T111427Z-retrieval-final-hybrid.json`), R2 dense (`20261102T111434Z-retrieval-final-dense.json`) and R3 BM25 (`20261102T111435Z-retrieval-final-bm25.json`). They have the same code (`3a2b92d`), index snapshot and golden file (sha256 `1d05086d…`), and the 60 answerable items (`split: all`). Each run searched with the raw `question` field (`query: question`), as in `RUNS.md` section 2.
- **What "missed" means.** A question is missed by a run when **at least one** of its relevant documents is not in that run's top 5. This is stricter than recall@5: an item with two relevant documents and one of them found has recall@5 0.5 but counts as missed (DAT's review of #175). Hybrid has recall@5 0.508, but only 28 of 60 items have every relevant document in its top 5.
- **List of misses.** `pipelines/scripts/retrieval_misses.py` (#175) on the three run files with `--k 5`.
- **Reading.** For each missed question, FAO read three things: the question, the reference answer, and the title and abstract of each relevant document. FAO also read the titles and abstracts of the top 5 of each run. The texts come from `data/index/bm25/chunks.parquet` of the frozen index on FAO's laptop (479 documents, a one-off export, not committed). Each question got one primary cause, from the categories in section 3.
- **Two causes from the plan that do not occur.**
  - **Missing document: 0.** All 78 relevant documents of the golden set are in the chunks and in Qdrant (coverage check W7-D1-FAO-1, #156 and #168).
  - **Chunking split: 0.** All 78 relevant documents are a single chunk (title plus abstract) in the frozen index, so no relevant text is split across chunks.

## 2. Overall picture

| Run | Questions missed (of 60) |
|---|---:|
| R1 hybrid | 32 |
| R2 dense | 36 |
| R3 BM25 | 33 |
| at least one run | 40 |
| every run | 27 |

| Cause | All 40 missed questions | Missed by hybrid (32) | Missed by every run (27) |
|---|---:|---:|---:|
| Follow-up searched without its history | 10 | 10 | 9 |
| Vocabulary mismatch | 7 | 7 | 7 |
| Crowded topic: other papers rank higher | 7 | 7 | 7 |
| Answer is a side detail of the relevant paper | 2 | 2 | 2 |
| Retriever-dependent: each relevant paper is found by some run | 14 | 6 | 2 |

Hybrid is the product retriever (ADR 0009), so the middle column is the one that matters for the system.

- **No single fix.** The two largest groups among hybrid's misses are follow-up turns and vocabulary mismatch (17 of 32). Neither is solved by a better ranker: both need a better query.
- **Near misses.** 6 of hybrid's 32 misses have a relevant document at hybrid ranks 6 to 10: `gs-005`, `gs-030`, `gs-037`, `gs-040`, `gs-043` and `gs-057`. The agent shows the top 5 sources (`RETRIEVAL_TOP_K` 5, SNAPSHOT), so these documents never reach the answer.
- **Question types.** Hybrid misses, by type:
  - follow-up: 10 of 11;
  - multi-hop: 9 of 11;
  - comparison: 5 of 8;
  - explanatory: 6 of 17;
  - factual: 2 of 13.

  Multi-hop and comparison items need two papers, so they count as missed when either paper is missing. The type sizes are small (8 to 17), so do not compare these shares closely.

## 3. Causes, with two examples each

### 3.1 Follow-up searched without its history (10)

`gs-018`, `gs-019`, `gs-022`, `gs-023`, `gs-024`, `gs-043`, `gs-044`, `gs-058`, `gs-059`, `gs-060`.

- **What happens.** R1 to R3 search with the last turn only ("Can you tell it not to?"). The topic is in the earlier turns, so the search matches the wording of the follow-up instead.
- **`gs-059`** "What if a person edits the text afterwards?" The topic, watermark detection, is in the history. Hybrid and dense return papers on text editing ("QuickEdit: Editing Text & Translations by Crossing Words Out"). The relevant paper (2411.13868, watermark detection under human edits) is at BM25 rank 8 and absent from the other two top-10 lists.
- **`gs-043`** "What happens if the questions use brand names instead?" The medical-benchmark topic is in the history. All three runs put "Generating Appealing Brand Names" first. BM25 still finds the relevant paper (2406.12066, drug names in biomedical benchmarks) at rank 2, because "brand names" occurs in its abstract.
- **This is a property of the evaluation, not only of the system.** The product rewrites a follow-up into a standalone query first (`AGENT_REWRITE=on`). On answered follow-up items, `retrieved_doc_recall` is 0.13 without the rewrite (A1, n = 8) and 0.44 with it (A2, n = 9). R1 on the raw question gives 0.09 (n = 11) (`answer-errors-w7.md` section 4.2). The answered sets differ and n is small, so this is an indication only. Retrieval on the golden `standalone_query` was not run.

### 3.2 Vocabulary mismatch (7)

`gs-001`, `gs-002`, `gs-003`, `gs-004`, `gs-028`, `gs-029`, `gs-041`.

- **What happens.** The question names the concept in everyday words, and the relevant abstract uses the technical term. BM25 cannot match the words. Dense retrieval with `bge-small-en-v1.5` does not bridge the gap either: it finds papers that share the everyday words.
- **Question style.** 6 of the 7 have the `plain` style in the golden notes. The exception is `gs-041`, whose second half ("judge how reliable its answers are when you only see its outputs") is a plain paraphrase of "uncertainty quantification for black-box LLMs".
- **`gs-001`** "Why do AI chatbots sometimes make things up, and what are two ways to reduce it?" Both relevant papers say "hallucination" and "large language models". Neither says "chatbot" or "make things up". All three runs return chatbot papers instead, for example "Chatting with Bots: AI, Speech Acts, and the Edge of Assertion" and "A Literature Survey of Recent Advances in Chatbots". Neither relevant paper is in any top 10.
- **`gs-029`** "Do language models get better at knowing when they are wrong as they are trained or as they get larger?" The relevant paper (2211.00151) is about calibration. The question never says "calibration" or "confidence". The runs return papers on training and scale, for example "Training Trajectories of Language Models Across Scales".

### 3.3 Crowded topic: other papers rank higher (7)

`gs-007`, `gs-014`, `gs-015`, `gs-025`, `gs-026`, `gs-040`, `gs-057`.

- **What happens.** The question uses the right terms, and the top 5 are on the right topic, but the corpus holds several papers on it and the relevant one is not among the first five. In some cases the papers that rank higher also answer the question. The golden set then lists one paper where several fit, and the miss overstates the failure (section 5).
- **`gs-014`** "Does the order of the answer choices change how well an AI model does on a multiple-choice test?"
  - The relevant paper (2309.12481) has a title that does not name the topic: "HANS, are you clever? Clever Hans Effect Analysis of Neural Systems".
  - All three runs rank other papers higher: "Large Language Models Sensitivity to The Order of Options in Multiple-Choice Questions" (2308.11483) and "Changing Answer Order Can Decrease MMLU Accuracy" (2406.19470).
  - Both abstracts report that reordering the options lowers accuracy, so they answer the question as asked.
- **`gs-057`** (two parts: ROME collapse, and reasoning after editing).
  - Hybrid ranks "Rebuilding ROME: Resolving Model Collapse during Sequential Model Editing" (2403.07175) above the relevant "Understanding the Collapse of LLMs in Model Editing" (2406.11263). Dense finds the relevant paper at rank 2.
  - The second relevant paper (2406.02882) is at hybrid rank 6.

### 3.4 Answer is a side detail of the relevant paper (2)

`gs-016`, `gs-021`.

- **What happens.** The fact the question asks for is in the abstract, but the paper's main topic is something else. Search ranks papers by their main topic.
- **`gs-021`** "How many parameters does GPT-4 have, according to papers that report a figure?"
  - One relevant paper (2404.14883) is a grammaticality-judgement study. Its abstract lists "ChatGPT-4, 1.5 trillion" only to describe the models tested.
  - The other (2305.03195) is a general GPT-4 review that mentions "more than one trillion" once.
  - Hybrid ranks the "GPT-4 Technical Report" first, which gives no size.
- **`gs-016`** (SetFit compared with LoRA fine-tuning). SetFit (2209.11055) is at rank 1 in all three runs. The second relevant paper (2510.16985) is a study of Bengali hate-speech detection that compares LoRA-tuned LLMs. The question names neither its task nor its language, and it is in no top 10.

### 3.5 Retriever-dependent (14; 6 of them are hybrid misses)

`gs-005`, `gs-008`, `gs-012`, `gs-020`, `gs-030`, `gs-034`, `gs-035`, `gs-037`, `gs-042`, `gs-052`, `gs-053`, `gs-054`, `gs-055`, `gs-056`.

- **What happens.** Every relevant paper of these items is in the top 5 of at least one run, so the corpus and the question are not the problem. Here, the question was missed because of which retriever, or which combination, was used.
- **Hybrid among the missers.** Hybrid misses 6 of them: `gs-005`, `gs-012`, `gs-030`, `gs-037`, `gs-042` and `gs-054`. The other 8 are dense-only or BM25-only misses that hybrid gets right.
- **Why fusion can lose a paper.** Hybrid fuses the top 50 of each retriever with reciprocal rank fusion (`RRF_K` 60). A paper that only one retriever ranks high gets a score from one list only:
  - rank 1 in one list scores 1/61 ≈ 0.016;
  - rank 30 in both lists scores 2/90 ≈ 0.022.

  So papers that both retrievers rank moderately can push it out of the top 5.
- **`gs-012`** asks for ShotKV's figures. "ShotKV" occurs in the abstract of the relevant paper (2502.01941) but not in its title. BM25 ranks the paper first, dense does not have it in its top 10, and hybrid does not have it in its top 10 either.
- **`gs-054`** (two parts: distillation from a cross-encoder, and adaptation from a domain description).
  - Hybrid finds ADAM (2212.10192) at rank 3. Dense finds the domain-description paper (2307.02740) at rank 1.
  - No single run has both papers in its top 5.

## 4. What this means for the system

These are proposals for future work. No code changes are planned before v1.0 (ADR 0010).

1. **Measure follow-up retrieval on the rewritten query.** Run R1 with `query: standalone_query` on the follow-up items, or log the rewritten query in A2 and score it. The raw-question number (0.09) does not describe the product (also DAT's future-work item 5).
2. **Rewrite or expand every question, not only follow-ups.** The rewrite step today only runs when there are earlier turns. A second query in technical terms ("hallucination", "calibration", "lexical and semantic metrics"), searched next to the original, targets the vocabulary-mismatch group. This should be measured with the same R1 setup.
3. **Retrieve deeper for multi-paper questions.** Four of the six hybrid near misses are multi-hop, comparison or follow-up items. The two parts of `gs-054` are found by different retrievers. Two options:
   - a larger number of sources for questions that name two things;
   - retrieval per part of the question. Question decomposition was cut in ADR 0010; DAT's future-work item 3 makes the same proposal.
4. **Fusion settings.** Weighted RRF, or a smaller `RRF_K`, would let a paper ranked first by one retriever stay in the top 5. That would help `gs-012`. Any change needs the same three runs again, because it can also lose items that hybrid gets right today.

## 5. Limits of this analysis

- **One reader, one cause.** FAO assigned each cause alone, with one primary cause per question. Some questions fit two: `gs-040` and `gs-057` are both crowded and near misses, and `gs-015` asks a broader question than its two papers answer. No second annotator checked the causes.
- **Abstracts only.** Causes were judged from titles and abstracts, the same text the retrievers see. Nothing was checked in the full papers.
- **Golden labels may be incomplete.** `relevant_doc_ids` lists the papers needed for the reference answer, not every paper on the topic (`evaluation/golden_set/FORMAT.md` rule 9). So recall and the miss counts are lower bounds.
  - Rule 9 also asks the item's author to read the top 10 of every retriever after a run and add papers that really contain the answer (pooling). That has not been done for the W7 runs, and the golden file is frozen in their run files (sha256 `1d05086d…`).
  - This analysis found one clear pooling candidate: `gs-014`, with 2308.11483 and 2406.19470 (section 3.3). Other crowded items may hold more.
  - Whether to pool after Gate W7 is LDN's decision as the golden set's owner. After pooling, R1 to R3 would be rerun on the new file; they take seconds.
- **Small n.** 60 answerable items, 40 missed by some run. The counts per cause (2 to 14) describe this golden set; they are not rates for the system.
- **Single run.** Each retriever ran once. The searches are deterministic on the frozen index, so a rerun gives the same lists.

## Appendix: the 40 missed questions

Ranks are hybrid / dense / BM25 in each run's top 10 ("-" = not in the top 10). "Missed by" uses the definition in section 1: some relevant paper not in that run's top 5.

| Item | Type | Style | Missed by | Relevant paper: ranks | Cause |
|---|---|---|---|---|---|
| `gs-001` | multi_hop | plain | hybrid, dense, bm25 | 2406.11267: -/-/-; 2409.10011: -/-/- | vocabulary mismatch |
| `gs-002` | explanatory | plain | hybrid, dense, bm25 | 2410.05983: -/-/- | vocabulary mismatch |
| `gs-003` | factual | plain | hybrid, dense, bm25 | 2605.15000: -/-/- | vocabulary mismatch |
| `gs-004` | comparison | plain | hybrid, dense, bm25 | 2511.17432: -/-/-; 2206.12664: -/-/- | vocabulary mismatch |
| `gs-005` | comparison | plain | hybrid, dense, bm25 | 2407.19794: 3/10/6; 2501.16952: 6/-/1 | retriever-dependent |
| `gs-007` | multi_hop | expert | hybrid, dense, bm25 | 2312.02798: -/-/1; 2606.31033: -/-/- | crowded topic |
| `gs-008` | factual | expert | dense | 2512.24058: 3/-/2 | retriever-dependent |
| `gs-012` | factual | specific | hybrid, dense | 2502.01941: -/-/1 | retriever-dependent |
| `gs-014` | explanatory | plain | hybrid, dense, bm25 | 2309.12481: -/-/- | crowded topic |
| `gs-015` | multi_hop | expert | hybrid, dense, bm25 | 2510.15313: -/-/-; 2609.00494: -/-/- | crowded topic |
| `gs-016` | comparison | specific | hybrid, dense, bm25 | 2510.16985: -/-/-; 2209.11055: 1/1/1 | side detail |
| `gs-018` | follow_up | plain | hybrid, dense, bm25 | 2305.15008: -/-/- | follow-up without history |
| `gs-019` | follow_up | plain | hybrid, dense, bm25 | 2505.17829: -/-/- | follow-up without history |
| `gs-020` | explanatory | plain | dense, bm25 | 2606.06178: 4/-/10 | retriever-dependent |
| `gs-021` | multi_hop | plain | hybrid, dense, bm25 | 2305.03195: -/-/-; 2404.14883: -/-/- | side detail |
| `gs-022` | follow_up | plain | hybrid, dense, bm25 | 2604.14682: -/-/- | follow-up without history |
| `gs-023` | follow_up | plain | hybrid, dense, bm25 | 2609.26185: -/-/- | follow-up without history |
| `gs-024` | follow_up | plain | hybrid, dense, bm25 | 2506.07295: -/-/- | follow-up without history |
| `gs-025` | multi_hop | plain | hybrid, dense, bm25 | 2509.07889: -/7/-; 2506.00748: -/-/- | crowded topic |
| `gs-026` | comparison | plain | hybrid, dense, bm25 | 2506.19399: -/-/-; 2303.14770: -/-/- | crowded topic |
| `gs-028` | explanatory | plain | hybrid, dense, bm25 | 2503.19693: -/-/- | vocabulary mismatch |
| `gs-029` | explanatory | plain | hybrid, dense, bm25 | 2211.00151: -/-/- | vocabulary mismatch |
| `gs-030` | explanatory | plain | hybrid, bm25 | 2102.04708: 8/3/- | retriever-dependent |
| `gs-034` | factual | expert | dense | 2112.07198: 2/-/1 | retriever-dependent |
| `gs-035` | explanatory | plain | bm25 | 2409.01357: 2/1/- | retriever-dependent |
| `gs-037` | explanatory | plain | hybrid, bm25 | 2406.02378: 10/5/- | retriever-dependent |
| `gs-040` | comparison | specific | hybrid, dense, bm25 | 2305.13245: 6/10/-; 2404.02258: -/-/2 | crowded topic |
| `gs-041` | multi_hop | expert | hybrid, dense, bm25 | 2212.03827: 1/1/2; 2305.19187: -/-/- | vocabulary mismatch |
| `gs-042` | multi_hop | expert | hybrid, dense | 2412.15246: -/-/2; 2304.11943: 1/3/1 | retriever-dependent |
| `gs-043` | follow_up | plain | hybrid, dense | 2406.12066: 8/-/2 | follow-up without history |
| `gs-044` | follow_up | plain | hybrid, dense, bm25 | 2307.02599: -/-/- | follow-up without history |
| `gs-052` | comparison | expert | bm25 | 2305.13648: 2/2/3; 2406.06073: 4/1/9 | retriever-dependent |
| `gs-053` | comparison | specific | dense | 2404.04102: 4/-/1; 2405.20830: 2/9/2 | retriever-dependent |
| `gs-054` | multi_hop | expert | hybrid, dense, bm25 | 2212.10192: 3/-/-; 2307.02740: -/1/- | retriever-dependent |
| `gs-055` | multi_hop | plain | dense, bm25 | 2402.11279: 3/1/-; 2405.16856: 2/-/5 | retriever-dependent |
| `gs-056` | multi_hop | specific | dense | 2403.20014: 3/-/2; 2401.10506: 1/5/1 | retriever-dependent |
| `gs-057` | multi_hop | expert | hybrid, dense, bm25 | 2406.11263: -/2/-; 2406.02882: 6/-/8 | crowded topic |
| `gs-058` | follow_up | plain | hybrid, dense, bm25 | 2410.07809: -/-/- | follow-up without history |
| `gs-059` | follow_up | plain | hybrid, dense, bm25 | 2411.13868: -/-/8 | follow-up without history |
| `gs-060` | follow_up | plain | hybrid, dense, bm25 | 2406.05606: -/-/- | follow-up without history |
