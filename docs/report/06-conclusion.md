# 6. Conclusion

<!-- Draft (W8-D2-FAO-1, written early on D13, updated on D16 with the Week 7 latency and
ablation runs and ADR 0011, on D18 with the W7 runs R1-R3 and A1-A4 of #179 and the two error
analyses, #179 and #180, and on D19 with the judge check of `final.md` §5, #196). The RQ1 and RQ2 numbers below come from the run files of #179; when
`final.md` (W7-D5-LDN-1) is merged, the citations move to it. RQ3 is not evaluated: the user study was cancelled on 2026-11-03,
ADR 0013. -->

## 6.1 Results by research question

**RQ1 (retrieval): does hybrid retrieval beat dense-only and BM25-only?**
Partly: hybrid beats dense-only at recall@10, but not BM25-only, and at recall@5 no retriever is
measurably better. The final runs R1 to R3 used all 60 answerable items with the raw question
(`evaluation/RUNS.md` §7, `retrieval-final-compare.txt`, #179):

| Retriever | recall@5 | recall@10 | MRR |
|---|---:|---:|---:|
| Hybrid (product default) | 0.508 [0.38, 0.63] | 0.583 [0.46, 0.70] | 0.474 |
| Dense only | 0.458 [0.35, 0.58] | 0.492 [0.38, 0.60] | 0.420 |
| BM25 only | 0.508 [0.39, 0.63] | 0.567 [0.45, 0.69] | 0.486 |

- **Hybrid against dense.** At recall@10, hybrid is +0.092 ahead, with a 95% interval of
  [+0.025, +0.167]. That is the only paired difference whose interval excludes 0.
- **Hybrid against BM25.** No difference: the interval of every metric includes 0. Hybrid stays
  the default by the rule set in ADR 0009 before the numbers.
- **By question type (hybrid recall@5, n per type):**
  - factual 0.85 (13);
  - explanatory 0.65 (17);
  - comparison 0.50 (8);
  - multi-hop 0.32 (11);
  - follow-up 0.09 (11).

  Follow-up turns were searched without their history. The product rewrites them first, and on
  answered follow-ups that rewrite raised the share of relevant papers retrieved from 0.13 to
  0.44 (A1 against A2, `answer-errors-w7.md` §4.2, #179).
- **Why questions are missed** (retrieval error analysis, #180). Of hybrid's 32 missed questions:
  - 10 are follow-ups without their history;
  - 7 use everyday words for a technical term (vocabulary mismatch);
  - 7 are on topics where other papers rank higher;
  - 2 ask for a side detail of a paper;
  - 6 are found by one of the single retrievers but lost in the fusion.

  No relevant paper was missing from the index.

**RQ2 (agent steps): do query rewriting and the evidence check improve faithfulness?**
Not measurably. The final runs A1 to A4 used all 65 items on the Week 7 host (`evaluation/RUNS.md`
§7, #179; `evaluation/reports/answer-errors-w7.md`):
- **Rewriting.** Macro faithfulness was 0.491 [0.39, 0.59] for the MVP (A1) and 0.527 [0.43, 0.62]
  with rewriting (A2). The intervals overlap almost completely. Rewriting changes only the 11
  follow-up turns, and on those it found the relevant paper more often (above).
- **Refusals.** Answerable items refused: 6/60 (A1) and 5/60 (A2). Unanswerable items refused:
  4/5 in both; `gs-u05` was answered.
- **The evidence check** (A3, A4) refused every item, 60/60 answerable and 5/5 unanswerable, as in
  the earlier dev run (#163). With `llama3.2:3b` it is a constant NO, so these two conditions
  cannot be scored, and the frozen configuration keeps it off.
- **Where faithfulness is lost.** 75% of the unsupported sentences in A2 have no citation at all.
  Sentences that do cite a passage are supported 76% of the time (DAT's error analysis, #179).
  So the low score is partly a citation-format failure of the 3B generator, not only unfaithfulness.

- **The judge against people.** On a 20% sample (11 answers per run, labelled by LDN and FAO
  without seeing the judge), the judge gave the human label on 47 of 55 sentences (0.855, Cohen's
  kappa 0.734). On those answers it scored faithfulness higher than the people did (A1 0.50
  against 0.39, A2 0.58 against 0.52), so the numbers above may be a little optimistic
  (`final.md` §5, #196).
- **Answer relevance** (judge, 1 to 3): 2.31 [2.11, 2.52] for A1 (n = 54) and 2.44 [2.24, 2.62]
  for A2 (n = 55) (`evaluation/RUNS.md` §7, V1 and V2). On the 22 sampled ratings the judge
  agreed with people 15 times (kappa 0.389), too few to trust these means much.

**RQ3 (follow-up suggestions): do users find them useful and click them?**
Not answered. The user study that was its only evidence was cancelled on 2026-11-03 (ADR 0013),
so this report makes no claim about the usefulness of the follow-up suggestions. The product
still shows them (chapter 5); measuring them is future work (6.3).

**Efficiency (not a research question).** The data side is measured in chapter 2.6 and
`pipelines/reports/scaling.md`:
- **Vector search:** inside Qdrant, exact search took 2.0, 8.0 and 14.4 ms p50 at 10%, 50% and
  100% of the corpus. HNSW stayed at 1.6 to 2.6 ms.
- **Whole retrieval:** under 135 ms at p95 at every size.
- **Whole answer** on the frozen system, on the Week 7 host (DAT's laptop, RTX 5060 8 GB, the
  first 30 golden questions with `split: all` and `limit: 30`, 5 of them follow-up turns;
  `docs/runbooks/performance.md` run B, #161): the first token arrived at p50 0.42 s and p95
  2.6 s, the answer was complete at p50 1.3 s and p95 3.2 s, and the full turn including the
  follow-up suggestions took p50 4.3 s and p95 6.0 s, with 0 errors.

At this corpus size retrieval is not the bottleneck of a chat turn: the LLM is.

## 6.2 Limitations

**Data scope.**
- **Abstracts only:** the corpus is the titles and abstracts of 121,860 arXiv `cs.CL` papers
  (Kaggle snapshot version 307, 2026-10-10). Full texts are not indexed, because their licences
  differ per paper (chapter 2.1), so the evaluated system answers only what an abstract states.
  After the freeze, ADR 0012 added one exception: when a question names a paper by its arXiv id,
  the agent reads that paper's HTML full text on demand, keeps it in memory only, and cites its
  sections. This mode has no measured quality yet, and no golden item uses it.
- **One field:** NLP and computational linguistics, including cross-lists. Questions from other
  fields fall outside the corpus.
- **English only:** the embedding model `bge-small-en-v1.5` is English-only. The Vietnamese question
  group was dropped (ADR 0007), so the system was not tested on Vietnamese.
- **Freshness:** new papers enter by hand in v1.0, with the incremental command of ADR 0008. The
  2-hour schedule (ADR 0011) is built but not deployed: its soak test was postponed until after
  the presentation (chapter 3.7). Even scheduled, the delay would be up to a day, because arXiv
  announces once a day. The evaluated index is the frozen copy, which stops at 2026-10-10.

**Small samples.**
- **Golden set:** 65 items (60 answerable: 30 dev and 30 test; 5 unanswerable; #168). One
  question is 1.7 points of recall over the 60 answerable items, and the intervals of most
  comparisons overlap. The relevant papers of an item are the ones it was written from, not
  every paper that answers it, so recall is a lower bound: in at least one item (`gs-014`) two
  papers ranked above the relevant one also answer the question (#180).
- **No user study:** it was cancelled (ADR 0013), so nothing in this report comes from users
  of the system, and RQ3 is unanswered.
- **Efficiency:** measured on one laptop, one run per size, with sequential queries. Load under
  several users at once was not measured.

**Model size.**
- **Generator:** `llama3.2:3b` (ADR 0006). It was chosen on speed, because at n = 10 its answers
  could not be told apart from those of `qwen2.5:3b` and `qwen2.5:7b`. The 7B model had no
  ungrounded answer in that run, so a larger model may follow the evidence better. The
  faithfulness numbers belong to this model.

**Judge bias.**
- **Judge:** faithfulness is judged by an LLM that is not the generator (`evaluation/PLAN.md` §5).
  It is checked by hand on a sample only, so its errors can remain in the rest. On that sample
  it matched people on 85% of sentences (kappa 0.73) but scored faithfulness higher than they
  did, and it agreed on only 15 of 22 relevance ratings (`final.md` §5, #196).

**Features cut by ADR 0010.** The plan was written for 40 working days and the project had 22,
so the cut list was applied at the start instead of at the first delay (ADR 0010):
- **Kafka streaming:** arXiv announces new papers in one daily batch, so a stream would add
  infrastructure without fresher data. New papers come in by a scheduled batch with a watermark
  instead (ADR 0008; the 2-hour schedule of ADR 0011 is built but not deployed in v1.0).
- **Reranker and query decomposition:** cut for time, to keep the evaluation and the report on the
  critical path. RQ1 and RQ2 therefore say nothing about reranking or decomposition, and the
  results describe a simpler agent than the original brief.
- **UI extras** (data page, `GET /stats`, step display, debug view): cut for time; the chat,
  citations, sources panel, follow-ups and feedback buttons were kept.
- **Also cut** outside the original list: follow-up suggestions v2 (v1 is the evaluated version)
  and response caching (the latency measurement was kept).
- **Cut on 2026-11-03:** the user study, first reduced to 5 to 6 participants by ADR 0010, then
  cancelled before its first session (ADR 0013). RQ3 is therefore not evaluated.
- **Fixed, not tuned:** the RRF settings (ADR 0009), because 30 questions are too few to tune
  them on.

**Engineering limits found on the way.**
- **Self-check with a 3B model:** the LLM evidence check answered NO to every question (#163), so
  the agent relies on retrieval and the answer prompt alone to refuse. Whether the model, the
  prompt or the 8-token reply limit causes it was not established.
- **`localhost` on Windows:** with a native Qdrant reached as `localhost`, 6 of 30 retrievals took
  about 2 s, likely because Windows tries IPv6 first; `127.0.0.1` brought every retrieval to
  15-47 ms (#161).
- **Exact search cost:** exact vector search grows by about 1.1 ms per 10,000 points
  (`scaling.md` §2.1). It is right for this corpus, but at about a million chunks it would cost
  about 110 ms per search (an extrapolation), and HNSW would be needed.
- **HTTP overhead:** each search through `QdrantStore` carried about 46 ms of HTTP round trip on
  the Windows laptop, and 44 ms of waiting on a gzip reply on Linux (#128). Both are larger than
  the search itself.

## 6.3 Future work

- **Full texts:** measure the on-demand mode of ADR 0012 on a small set of 5 to 10 deep questions
  whose answers are in a paper's body, reported apart from the W7 numbers, and add the PDF fallback
  it leaves for later. Indexing full texts stays limited to papers whose licence allows it.
- **A multilingual embedding model**, measured on a Vietnamese question group with the same
  golden-set rules (ADR 0007).
- **The scheduled ingestion soak test** (ADR 0011): run #152 and #178 on an always-on host for at
  least a day (12 or more runs, none failed or overlapping, no backend error during a BM25 switch),
  then deploy the schedule.
- **HNSW search** with its recall checked against exact search (#87) once the corpus grows.
- **An evidence check that works with a small model,** for example a reply parsed as a score
  rather than YES/NO, measured again as the "+evidence" ablation.
- **A larger golden set**, so differences of a few questions can be told apart from noise.
- **The cut features:** a reranker and query decomposition, each tested as an ablation like RQ2.
- **A user study for RQ3:** the protocol is ready (`evaluation/user_study/PROTOCOL.md`), and the
  rating buttons and the feedback log are already in the product.

- **Citation enforcement:** find answer sentences without a `[n]` marker after generation and
  either have them cited from the sources or drop them. This targets the largest cause of low
  faithfulness (DAT's error analysis, #179).
- **Better queries, not only better ranking:** the two largest groups of retrieval misses are
  follow-ups searched without history and everyday wording of technical terms (#180). Next steps:
  - measure follow-up retrieval on the rewritten query;
  - try a second, technical rewrite of every question, searched next to the original.
