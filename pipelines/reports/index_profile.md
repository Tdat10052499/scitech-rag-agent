# Index profile

W3-D5-FAO-1. Measured on 2026-10-21 at 12:31 UTC with `pipelines/scripts/index_profile.py`
(#68) against the full index loaded that evening (W3-D3-FAO-1, report on #91). All numbers come from that one run
unless a line says otherwise. The JSON the script wrote (`data/reports/index_profile.json`) is
kept on the laptop, as `data/` is not in git.

## 1. Setup

| Item | Value |
|---|---|
| Machine | FAO's laptop: Windows 11 (10.0.26300), Intel64 Family 6 Model 142 Stepping 12 (as Python reports it), 8 logical CPUs, 15.8 GiB RAM, Python 3.14.3, no GPU used |
| Qdrant | 1.19.2 in Docker (`docker compose`, `qdrant/qdrant:v1.19.2`), on the same laptop |
| Collection | `scitech_chunks`, 121,926 points, 4 segments, 384-dimension vectors (`BAAI/bge-small-en-v1.5`, ADR 0007) |
| `index_snapshot` | `scitech_chunks/bge-small-en-v1.5/chunked-2026-10-17T05:19:12/embedded-2026-10-17T06:40:37` |
| Vector search | exact (`QDRANT_SEARCH_EXACT` unset, the default since #101) |
| BM25 index | `data/index/bm25`: 121,926 chunks, 133,273 terms, 11,245,023 postings (built in 36.7 s) |
| Hybrid | RRF with `RRF_K` 60, dense top 50 and BM25 top 50 (the defaults of `HybridConfig`) |
| Code | `main` at a0561bc plus #68 at 2e59d7d |

Command (repository root, `PYTHONPATH=agent/src;pipelines/src;evaluation/src`, with
`QDRANT_URL`, `QDRANT_COLLECTION=scitech_chunks`, `EMBEDDING_MODEL=BAAI/bge-small-en-v1.5`,
`EMBEDDING_QUERY_PREFIX` as in ADR 0007 and `BM25_INDEX_DIR=data/index/bm25`):

```
python pipelines/scripts/index_profile.py \
    --retriever dense --retriever bm25 --retriever hybrid \
    --filter '{"categories": "cs.LG"}' \
    --filter '{"published_at": {"gte": "2023-01-01", "lt": "2024-01-01"}}' \
    --collection scitech_chunks --size bm25=data/index/bm25 \
    --out data/reports/index_profile.json
```

## 2. Query latency

100 queries: the 37 golden query texts (32 questions and the standalone rewrites of the 5
follow-up items), then 63 chunk titles sampled with seed 0. k = 10. Each retriever ran 5
untimed warm-up searches first, then the 100 queries one after another. A time is the whole
`search(query, k)` call measured in Python: for dense and hybrid it includes embedding the
query on the CPU and the HTTP request to Qdrant.

| Retriever | p50 (ms) | p95 (ms) | mean (ms) | max (ms) | queries without hits |
|---|---:|---:|---:|---:|---:|
| dense | 82.46 | 88.46 | 82.64 | 91.27 | 0 |
| bm25 | 7.06 | 14.2 | 7.81 | 20.96 | 0 |
| hybrid | 107.15 | 149.05 | 113.77 | 153.63 | 0 |

What the numbers say:
- **Dense** time is mostly the query embedding on the CPU. The search itself is the smaller
  part: on Kaggle, exact search cost about 35 ms per query and HNSW about 24 ms (#87).
- **Hybrid** is about one dense search plus one BM25 search plus the fusion, since it runs both
  with top 50.
- **BM25** is the fastest by an order of magnitude.
- All three are far below the time the LLM takes to start answering (TTFT 0.44 s on the
  Kaggle server, #91), so retrieval is not the bottleneck of a chat turn.

## 3. Filters

For each filter, the first 5 queries were run with k = 10, and every hit was checked with
`scitech_agent.retrieval.matches`, the rule all retrievers share since #99. A filter passes when
there are hits and none of them breaks it.

Only the dense rows are a fully independent check: Qdrant applies the filter itself, and its hits
are then checked with `matches`. BM25 filters with `matches` itself, so its 0 violations hold by
construction and only show that the filters run and still return hits. Hybrid is in between: hits
from its dense half were filtered by Qdrant, hits from its BM25 half by `matches` (DAT's review).

| Retriever | Filter | Hits | Violations | Result |
|---|---|---:|---:|---|
| dense | `{"categories": "cs.LG"}` | 50 | 0 | ok |
| dense | `{"published_at": {"gte": "2023-01-01", "lt": "2024-01-01"}}` | 50 | 0 | ok |
| bm25 | `{"categories": "cs.LG"}` | 50 | 0 | ok |
| bm25 | `{"published_at": {"gte": "2023-01-01", "lt": "2024-01-01"}}` | 50 | 0 | ok |
| hybrid | `{"categories": "cs.LG"}` | 50 | 0 | ok |
| hybrid | `{"published_at": {"gte": "2023-01-01", "lt": "2024-01-01"}}` | 50 | 0 | ok |

The second filter is `retrieval.year_range(2023, 2023)`. Earlier the same evening, on a test
collection of the same data, `year_range(2024, 2024)`, the same with `cs.LG`, and
`year_range(None, 2019)` each returned 5 matching hits in 92 to 97 ms through dense search, and a
bare `"2024"` bound was refused before reaching Qdrant (#99).

## 4. Size on disk and memory

| Item | Value |
|---|---|
| Qdrant collection on disk | 609.9 MiB |
| Qdrant storage on disk (all collections) | 609.9 MiB |
| Qdrant container memory (`docker stats`) | 280.7 MiB (Docker's limit: 7.662 GiB) |
| BM25 index on disk | 177.2 MiB |

How measured:
- **Disk:** `du -sb` inside the `qdrant` container, read after the latency runs.
- **Memory:** what `docker stats` reports for the container at the same moment. It includes the
  page cache of the memory-mapped segments, so it is an upper bound of what Qdrant needs. The
  limit is the memory Docker Desktop gives its VM, not the laptop's RAM.

Related times from the same evening:
- **Load:** 121,926 points in 135.2 s (15 parts, 7.6 to 11.2 s each; #91).
- **BM25 build:** 36.7 s.

## 5. Limits

- **One machine, one run.** The p95 values rest on 100 queries; read differences of a few
  milliseconds as noise.
- **Sequential queries only.** Latency under concurrent users is not measured; the user study
  (W7) will be the first time several people search at once.
- **Process memory of the agent is not measured.** The BM25 index and the embedding model live
  in the backend process. DAT measured a peak of 1,184 MB for the BM25 build.
- **Exact search.** If the corpus grows a lot (W5, W6), exact search costs grow linearly, and the
  HNSW settings of #87 have to be measured again.
