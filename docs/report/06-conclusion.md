# 6. Conclusion

<!-- Draft (W8-D2-FAO-1, written early on D13). The limitations and the data side are written from
what is measured now. Every result of the research questions is a TODO until `final.md`
(W7-D5-LDN-1) is merged; the numbers there replace the preliminary ones below. Future work from the
error analyses is a TODO until W7-D3-FAO-1 and the answer error analysis exist. -->

## 6.1 Results by research question

**RQ1 (retrieval): does hybrid retrieval beat dense-only and BM25-only?**
Preliminary, from the 30 answerable dev items (ADR 0009, table B; 2026-10-21):
- recall@5 was 0.333 for hybrid, 0.283 for dense and 0.350 for BM25;
- MRR was 0.301, 0.253 and 0.370.

Every 95% interval of the paired differences with hybrid included 0. On this sample none of the
three is measurably better. Hybrid was kept as the default by the rule set before the numbers.

<!-- TODO(W7-D1-LDN-1, W7-D5-LDN-1): the final runs on the full golden set (k = 1, 5, 10, per
question type, with n per cell) and one sentence answering RQ1. -->

**RQ2 (agent steps): do query rewriting and the evidence check improve faithfulness?**
<!-- TODO(W7-D2-LDN-1, W7-D5-LDN-1): faithfulness and refusal rate for MVP, +rewrite, +evidence
check and full agent, per type; the follow-up items for rewriting; the manual check of the judge. -->

**RQ3 (follow-up suggestions): do users find them useful and click them?**
<!-- TODO(W7-D4-LDN-1): n, mean, median and distribution of the usefulness rating, click rate, and
recurring comments; descriptive only (5-6 participants). -->

**Efficiency (not a research question).** The data side is measured in chapter 2.6 and
`pipelines/reports/scaling.md`:
- **Vector search:** inside Qdrant, exact search took 2.0, 8.0 and 14.4 ms p50 at 10%, 50% and
  100% of the corpus. HNSW stayed at 1.6 to 2.6 ms.
- **Whole retrieval:** under 135 ms at p95 at every size, far below the LLM's time to first token
  (0.44 s, #91).

At this corpus size retrieval is not the bottleneck of a chat turn.

<!-- TODO(DAT, W7): time to first token and total answer time on the frozen system. -->

## 6.2 Limitations

**Data scope.**
- **Abstracts only:** the corpus is the titles and abstracts of 121,860 arXiv `cs.CL` papers
  (Kaggle snapshot version 307, 2026-10-10). Full texts are not used: their licences differ per
  paper (chapter 2.1), so the agent can answer only what an abstract states.
- **One field:** NLP and computational linguistics, including cross-lists. Questions from other
  fields fall outside the corpus.
- **English only:** the embedding model `bge-small-en-v1.5` is English-only. The Vietnamese question
  group was dropped (ADR 0007), so the system was not tested on Vietnamese.
- **Freshness:** new papers can be added with `incremental-run` (ADR 0008), but by hand, and only
  on a machine with Java 17+. The frozen index used for evaluation stops at 2026-10-10.

**Small samples.**
- **Golden set:** 60 items, of which 30 were used for decisions. One question is 3.3 points of
  recall on the dev split, and the intervals of most comparisons overlap.
- **User study:** 5 to 6 participants, chosen by the team, not at random. It supports
  description, not a claim about users in general.
- **Efficiency:** measured on one laptop, one run per size, with sequential queries. Load under
  several users at once was not measured.

**Model size.**
- **Generator:** `llama3.2:3b` (ADR 0006), chosen to fit a free GPU session and a laptop
  fallback. A larger model may follow the evidence better, so the faithfulness numbers belong to
  this model.

**Judge bias.**
- **Judge:** faithfulness is judged by an LLM that is not the generator (`evaluation/PLAN.md` §5).
  It is checked by hand on a sample only, so its errors can remain in the rest.
  <!-- TODO(W7-D2-LDN-1): the agreement between judge and manual labels. -->

**Features cut by ADR 0010.**
- **Cut:** the reranker, query decomposition, Kafka streaming, and the UI extras (data page,
  statistics, step display, debug view). RQ1 and RQ2 therefore say nothing about reranking or
  decomposition.
- **Fixed, not tuned:** the RRF settings (ADR 0009), because 30 questions are too few to tune
  them on.

**Engineering limits found on the way.**
- **BM25 and new papers:** the BM25 index is not updated by `incremental-run`. New papers are
  found only by the dense half of hybrid search until a rebuild (#119).
- **Exact search cost:** exact vector search grows by about 1.1 ms per 10,000 points
  (`scaling.md` §2.1). It is right for this corpus, but at about a million chunks it would cost
  about 110 ms per search (an extrapolation), and HNSW would be needed.
- **HTTP overhead:** each search through `QdrantStore` carried about 46 ms of HTTP round trip on
  the Windows laptop, and 44 ms of waiting on a gzip reply on Linux (#128). Both are larger than
  the search itself.

## 6.3 Future work

- **Full texts** where the licence allows it, so answers can draw on methods and results, not
  only abstracts.
- **A multilingual embedding model**, measured on a Vietnamese question group with the same
  golden-set rules (ADR 0007).
- **A scheduled incremental run** with an automatic BM25 rebuild (#119), and HNSW search with its
  recall checked against exact search (#87) once the corpus grows.
- **A larger golden set**, so differences of a few questions can be told apart from noise.
- **The cut features:** a reranker and query decomposition, each tested as an ablation like RQ2.

<!-- TODO(W7-D3-FAO-1 and the answer error analysis): one or two items from the most common
retrieval misses and answer errors. -->
