# 0003. Corpus: all of arXiv `cs.CL` from the Kaggle snapshot, Wikipedia as background

- Status: proposed
- Date: 2026-10-14
- Deciders: FAO (author), DAT (reviewer)

## Context
The sub-domain is LLM/NLP (brief, W1-D2-DAT-1). This ADR fixes which sources, which subset and how big it is, so the downloader (W2-D1-FAO-1) and the index have a fixed target.
Constraints:
- The full embedding run must fit in one night on the available GPU (ADR 0010; run planned for D08, 2026-10-21).
- The GPU is a free Kaggle/Colab session. Kaggle's weekly quota is 30 h of session time, with 27 h 57 min left on 2026-10-14, shared with the LLM runs (`docs/runbooks/llm-serving.md`).
- This is a Big Data course, so the scale must be stated with numbers.

All numbers below were measured on 2026-10-14 (W1-D2-FAO-1) unless marked as an estimate; the method and full tables are in `docs/03-data-sources.md` (Measured subset).

| Measured | Value |
|---|---|
| Kaggle arXiv snapshot (all of arXiv) | 3,205,432 records, 5,610,256,780 bytes, one streaming pass in 77 s on a laptop |
| `cs.CL` including cross-lists, all years | 121,860 records, 233 MB of metadata, 1,197 abstract characters per record |
| `cs.CL` incl. cross-lists since 2018 / 2020 / 2022 / 2024 | 113,944 / 104,822 / 89,614 / 67,040 |
| New `cs.CL` papers per year (2025, incl. cross-lists) | 23,762, about 460 per week (yearly total / 52) |
| Embedding throughput, Colab Tesla T4, `title. abstract`, batch 64 | `bge-small-en-v1.5` 145.8 records/s, `bge-base-en-v1.5` 49.3 records/s |
| OpenAlex join by DataCite DOI `10.48550/arXiv.<id>` | 20 of 20 sample records found |

## Options considered
Subset (start year):
1. Since 2022 (89,614) or 2024 (67,040): the most LLM-heavy years only.
2. Since 2018 (113,944): the BERT/Transformer era.
3. All years (121,860): the whole category, no year filter.

Processing scope:
- A. "Index only": harvest `cs.CL` through OAI-PMH and never touch the rest of arXiv.
- B. "Two tiers": a processing tier reads the whole 5.61 GB snapshot (all 3.2M records) and filters it; an index tier holds only `cs.CL`.

Extra sources:
- Wikipedia NLP/LLM articles as background explanations.
- OpenAlex for citations and topics.
- Full-text PDFs.

## Decision
**Corpus: every arXiv record whose `categories` contains `cs.CL` (primary or cross-list), all years: 121,860 records on the 2026-10-10 snapshot, titles and abstracts only.**
- Embedding time does not limit the start year. On a T4 all 121,860 records take an estimated 14 min with `bge-small-en-v1.5` and 41 min with `bge-base-en-v1.5` (records / measured throughput), far inside one night even with a 3x margin (about 2 h).
- A start year removes few records (2018 would save 7,916, 6.5%) but loses foundational papers users are likely to ask about, for example "Attention Is All You Need" (arXiv 1706.03762, 2017, categories `cs.CL cs.LG`, checked in the snapshot).
- No year filter is also the simplest definition, and it matches incremental ingestion (W5), which harvests by date only (OAI-PMH set `cs:cs:CL`, `from=`). Whether that set also returns cross-lists is checked in ADR 0008.
- Cross-lists are kept because they are 20-28% of the category each year since 2018, mostly papers with primary `cs.LG` (7,879) or `cs.AI` (5,759). arXiv's own `cs.CL` listing counts them too.

**Processing: two tiers (option B).** The pipeline downloads and reads the whole Kaggle snapshot (3,205,432 records, 5.61 GB) on every rebuild, filters, cleans and profiles it, and indexes only `cs.CL`. Engine: ADR 0005.
- Why not A: "index only" processes 233 MB, which needs no big-data tooling, and it ties every rebuild to arXiv's rate-limited OAI-PMH service (one request per 3 s) instead of one Kaggle file.
- B is affordable: one streaming pass over the snapshot took 77 s in plain Python, and the D02 engine dry run extrapolates to about 17 s with DuckDB (estimate, measured in ADR 0005).

**Sources:**

| Source | Role | Access | Volume | Licence (stored in `license`) |
|---|---|---|---|---|
| arXiv, Kaggle snapshot `Cornell-University/arxiv` | Core corpus, bulk load | `kaggle datasets download` (log in with `kaggle auth login`) | 5.61 GB in, 121,860 records out | `CC0-1.0` for title and abstract. The snapshot `license` field is the e-print licence, not the metadata licence |
| arXiv OAI-PMH, set `cs:cs:CL` | Incremental ingestion (W5, ADR 0008) | `from=` date, 1 request per 3 s | about 460 records per week | `CC0-1.0` |
| Wikipedia (English) | Background explanations of NLP/LLM concepts | MediaWiki API, pages under `Category:Natural language processing` and subcategories | Estimate, not measured: hundreds to a few thousand pages. Measured by the category crawl in W2-D1-FAO-1 | `CC BY-SA 4.0`; the UI links the article |
| OpenAlex | Optional enrichment (citations, topics), not a text source | REST API by DOI `10.48550/arXiv.<id>` with `select=` | One request per paper if used | CC0 1.0 |

**Big-data scale, in numbers:**
- Every rebuild processes 3,205,432 records and 5.61 GB of JSON.
- The index holds 121,860 documents. With one chunk per abstract, the vectors take 187 MB at 384 dimensions or 374 MB at 768 (4-byte floats).
- The corpus grows by about 460 records per week.

**Out of scope:**
- Full-text PDFs (author licences, and the size would multiply).
- arXiv categories other than `cs.CL`.
- The OpenAlex snapshot (about 745 GB).
- Wikipedia dumps.
- Wikipedia pages outside the NLP category tree.

## Consequences
- The downloader (W2-D1-FAO-1) fetches one file from Kaggle. It needs a Kaggle login on the machine that runs it, so its tests must use a mocked response and never call Kaggle.
- The Kaggle snapshot is updated about weekly (version 307 on 2026-10-10). The manifest records the version or date used, and the frozen evaluation index (W6) names it.
- The embedding estimate assumes one chunk per abstract and was measured on 1,000 records from 2022 on only. Older abstracts may differ in length. W2-D3-FAO-1 measures the abstract length distribution over all years, and the D08 run records the real time. If chunking splits long abstracts, multiply the estimate by the measured chunks per record.
- The D08 overnight run shares the Kaggle/Colab GPU quota with the LLM. FAO and DAT book it in the Week 1 tracking issue.
- Pre-2018 papers (7,916 records, 6.5%) may rank for queries where newer work is more relevant. If the evaluation shows this, add a date-aware ranking feature or a filter instead of dropping them from the index.
- If time is short, cut OpenAlex first (it adds no text), then Wikipedia. arXiv `cs.CL` alone meets the success criteria.
- Revisit this ADR if the GPU becomes unavailable for a night. Then the start year becomes the lever (since 2022: 30 min with `bge-base`, 10 min with `bge-small`, estimate).
