# 6. Conclusion

<!-- Draft (W8-D2-FAO-1, written early on D13, updated on D16 with the Week 7 latency and
ablation runs and ADR 0011). The limitations and the data side are written from
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
Preliminary, from the 32 dev items on the Week 7 host (`evaluation/reports/ablations-v1.md`,
#163):
- **Rewriting** changed only the 5 follow-up turns. Macro faithfulness was 0.576 [0.44, 0.70]
  with rewriting and 0.556 [0.42, 0.67] without, so the difference is inside both intervals. It
  found the relevant paper in 1 of the 5 follow-ups, against 0 without.
- **The evidence check** refused all 32 items, including questions that the other conditions
  answered with faithfulness 1.0. With `llama3.2:3b` it is a constant NO, so the "+evidence" and
  "full" conditions could not be scored, and the frozen configuration keeps it off.

<!-- TODO(W7-D2-LDN-1, W7-D5-LDN-1): faithfulness and refusal rate for MVP, +rewrite, +evidence
check and full agent, per type; the follow-up items for rewriting; the manual check of the judge. -->

**RQ3 (follow-up suggestions): do users find them useful and click them?**
<!-- TODO(W7-D4-LDN-1): n, mean, median and distribution of the usefulness rating, click rate, and
recurring comments; descriptive only (5-6 participants). -->

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
  (Kaggle snapshot version 307, 2026-10-10). Full texts are not used: their licences differ per
  paper (chapter 2.1), so the agent can answer only what an abstract states.
- **One field:** NLP and computational linguistics, including cross-lists. Questions from other
  fields fall outside the corpus.
- **English only:** the embedding model `bge-small-en-v1.5` is English-only. The Vietnamese question
  group was dropped (ADR 0007), so the system was not tested on Vietnamese.
- **Freshness:** the serving index takes new papers every 2 hours (ADR 0011), but arXiv announces
  them once a day, so the delay is up to a day, not 2 hours. The schedule runs only while the
  serving laptop is awake. The evaluated index is the frozen copy, which stops at 2026-10-10; the
  live index is never evaluated.
  <!-- TODO(W8-D6-FAO-1): soak result; if the soak failed, the schedule is off and this says
  "by hand" again. -->

**Small samples.**
- **Golden set:** 60 items planned (47 on D13), of which 30 were used for decisions.
  <!-- TODO(W5-D1-LDN-1): final count. --> One question is 3.3 points of
  recall on the dev split, and the intervals of most comparisons overlap.
- **User study:** 5 to 6 participants, chosen by the team, not at random. It supports
  description, not a claim about users in general.
- **Efficiency:** measured on one laptop, one run per size, with sequential queries. Load under
  several users at once was not measured.

**Model size.**
- **Generator:** `llama3.2:3b` (ADR 0006). It was chosen on speed, because at n = 10 its answers
  could not be told apart from those of `qwen2.5:3b` and `qwen2.5:7b`. The 7B model had no
  ungrounded answer in that run, so a larger model may follow the evidence better. The
  faithfulness numbers belong to this model.

**Judge bias.**
- **Judge:** faithfulness is judged by an LLM that is not the generator (`evaluation/PLAN.md` §5).
  It is checked by hand on a sample only, so its errors can remain in the rest.
  <!-- TODO(W7-D2-LDN-1): the agreement between judge and manual labels. -->

**Features cut by ADR 0010.** The plan was written for 40 working days and the project had 22,
so the cut list was applied at the start instead of at the first delay (ADR 0010):
- **Kafka streaming:** arXiv announces new papers in one daily batch, so a stream would add
  infrastructure without fresher data. New papers come in by a scheduled batch with a watermark
  instead (ADR 0008, ADR 0011).
- **Reranker and query decomposition:** cut for time, to keep the evaluation and the report on the
  critical path. RQ1 and RQ2 therefore say nothing about reranking or decomposition, and the
  results describe a simpler agent than the original brief.
- **UI extras** (data page, `GET /stats`, step display, debug view): cut for time; the chat,
  citations, sources panel, follow-ups and feedback buttons were kept.
- **Also cut** outside the original list: follow-up suggestions v2 (v1 is the evaluated version)
  and response caching (the latency measurement was kept).
- **Kept at the minimum size:** the user study, with 5 to 6 participants.
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

- **Full texts** where the licence allows it, so answers can draw on methods and results, not
  only abstracts.
- **A multilingual embedding model**, measured on a Vietnamese question group with the same
  golden-set rules (ADR 0007).
- **HNSW search** with its recall checked against exact search (#87) once the corpus grows, and
  an always-on server for the schedule instead of a laptop.
- **An evidence check that works with a small model,** for example a reply parsed as a score
  rather than YES/NO, measured again as the "+evidence" ablation.
- **A larger golden set**, so differences of a few questions can be told apart from noise.
- **The cut features:** a reranker and query decomposition, each tested as an ablation like RQ2.

<!-- TODO(W7-D3-FAO-1 and the answer error analysis): one or two items from the most common
retrieval misses and answer errors. -->
