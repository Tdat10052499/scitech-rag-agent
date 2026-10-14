# Data sources

Status: **candidate, surveyed on 2026-10-13 (W1-D1-FAO-1).** Access, format, terms and rate limits below come from each source's own documentation (linked) or from a check run on 2026-10-13. Sizes for the chosen subset are measured in W1-D2-FAO-1 and the recommendation is recorded in ADR 0003; the status becomes "verified" then.

Sub-domain (from the brief, W1-D2-DAT-1): LLM/NLP, i.e. arXiv `cs.CL` including papers cross-listed to `cs.CL` from `cs.LG`/`cs.AI`, plus Wikipedia background articles.

## Survey

| | arXiv (main source) | OpenAlex | Wikipedia (English) |
|---|---|---|---|
| Role | Core corpus: titles and abstracts of `cs.CL` papers; daily new papers feed incremental ingestion (W5) | Optional enrichment (citations, topics) of arXiv records; not a text source | Background explanations of NLP/LLM concepts |
| How to download | Three official routes ([bulk data](https://info.arxiv.org/help/bulk_data.html)): (1) **Kaggle metadata snapshot**, one file `arxiv-metadata-oai-snapshot.json` for all of arXiv, filter on `categories` containing `cs.CL` ([Kaggle](https://www.kaggle.com/datasets/Cornell-University/arxiv)); needs a free Kaggle account and API token. (2) **OAI-PMH**, "the preferred way to bulk-download or keep an up-to-date copy", selective harvest by set and date; the category set syntax is `group:archive:CATEGORY` (example `cs:cs:AI` in the docs, so `cs:cs:CL` for us) ([OAI-PMH](https://info.arxiv.org/help/oa/index.html)). (3) **Search API**, `export.arxiv.org/api/query` with `cat:` and `submittedDate:[YYYYMMDDTTTT+TO+YYYYMMDDTTTT]` ([API manual](https://info.arxiv.org/help/api/user-manual.html)); good for small samples only. | REST API `api.openalex.org` (`per_page` max 100) ([auth and limits](https://help.openalex.org/api/authentication/)), or the full snapshot in the public S3 bucket `s3://openalex` with `aws s3 sync --no-sign-request`, no AWS account needed ([snapshot](https://help.openalex.org/access/snapshot/)) | Select pages from `Category:Natural language processing` and its subcategories, then fetch plain text, through the MediaWiki Action API ([API etiquette](https://www.mediawiki.org/wiki/API:Etiquette)); or the monthly XML dumps for all of Wikipedia ([data dumps](https://meta.wikimedia.org/wiki/Data_dumps)) |
| Format | Kaggle: JSON Lines (one JSON object per paper). OAI-PMH: XML in `oai_dc`, `arXiv` (latest version, parsed authors, categories and licence) or `arXivRaw` (with version history) ([OAI-PMH](https://info.arxiv.org/help/oa/index.html)). API: Atom 1.0 XML ([API manual](https://info.arxiv.org/help/api/user-manual.html)) | API: JSON. Snapshot: gzip JSON Lines or snappy Parquet ([snapshot](https://help.openalex.org/access/snapshot/)) | API: JSON. Dumps: XML compressed with bz2 or 7z, multistream recommended ([data dumps](https://meta.wikimedia.org/wiki/Data_dumps)) |
| Fields available | API entries: `id`, `title`, `summary` (abstract), `author/name`, `published`, `updated`, `category`, `primary_category`, `comment`, `affiliation`, `journal_ref`, `doi`, `link` ([API manual](https://info.arxiv.org/help/api/user-manual.html)). Kaggle snapshot fields (read from the file on 2026-10-14, W1-D2-FAO-1): `id`, `submitter`, `authors`, `title`, `comments`, `journal-ref`, `doi`, `report-no`, `categories` (space-separated, primary first), `license`, `abstract`, `versions` (list of `version`, `created`), `update_date`, `authors_parsed`; there is no separate primary-category field. Filled in `cs.CL` records: `title`, `abstract`, `authors`, `categories`, `versions`, `update_date` 100%, `license` 98.8%, `comments` 63.8%, `doi` 7.9%, `journal-ref` 7.6% (see Measured subset below). Maps to every field of `chunk.schema.json` (`doc_id`, `title`, `text`, `authors`, `categories`, `published_at`, `url`, `license`). | Abstract only as `abstract_inverted_index`: "OpenAlex does not ship plaintext abstracts for legal reasons"; no arXiv id or arXiv category field, only `indexed_in` can contain `arxiv`; ids are `openalex`, `doi`, `mag`, `pmid`, `pmcid` ([work attributes](https://help.openalex.org/data/works/attributes/)). Joining to arXiv must go through the DOI. | Title, page id, revision id, categories, URL ([API:Categorymembers](https://www.mediawiki.org/wiki/API:Categorymembers): `list=categorymembers`, `cmtype=page\|subcat`, up to 500 members per request); plain-text extract ([TextExtracts](https://www.mediawiki.org/wiki/Extension:TextExtracts): `prop=extracts&explaintext`, full text for 1 page per request, intros for up to 20) |
| Licence / terms | Descriptive metadata (title, abstract, authors, identifiers, classification) is **CC0 1.0**. Full-text e-prints are under the author's chosen licence and need the copyright holder's permission to redistribute; link to the abstract page; do not imply arXiv endorses the project ([API terms of use](https://info.arxiv.org/help/api/tou.html)). Kaggle lists the dataset as "CC0: Public Domain" ([Kaggle API metadata](https://www.kaggle.com/api/v1/datasets/view/Cornell-University/arxiv)). So titles/abstracts may be stored, embedded and committed as a fixture. | **CC0 1.0**: the `LICENSE.txt` at the root of the snapshot bucket is the CC0 1.0 Universal text ([LICENSE.txt](https://openalex.s3.amazonaws.com/LICENSE.txt), checked 2026-10-14); the help pages do not state it ([snapshot](https://help.openalex.org/access/snapshot/)). | Text is under the **Creative Commons Attribution-ShareAlike 4.0 License**; "additional terms may apply" (page footer of [Natural language processing](https://en.wikipedia.org/wiki/Natural_language_processing), checked 2026-10-13; [Terms of Use](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use)). Reuse needs attribution (link to the article) and share-alike: the `license` field is `CC BY-SA 4.0` and the UI links the article. |
| Rate limits | One request every 3 seconds, one connection at a time, for the API, OAI-PMH and RSS together, across all machines you control ([API terms of use](https://info.arxiv.org/help/api/tou.html)). API: at most 2,000 results per call and 30,000 per query ([API manual](https://info.arxiv.org/help/api/user-manual.html)). Kaggle download: none stated. | 10 requests/s without key, 30 requests/s with a free key. Daily budget: $0.10/day without key, $1/day with a free key = 10,000 list calls = up to 1,000,000 records/day; single-entity gets are free ([auth](https://help.openalex.org/api/authentication/), [costs](https://help.openalex.org/access/example-costs/)). Snapshot: free, no limit. | No hard numeric limit for reads; send requests one at a time, use `maxlag`, send a descriptive `User-Agent` with contact ([API etiquette](https://www.mediawiki.org/wiki/API:Etiquette)) |
| Update frequency | Metadata updated nightly; new papers announced around 22:30 ET, Sunday to Thursday ([OAI-PMH](https://info.arxiv.org/help/oa/index.html)). Kaggle snapshot: about weekly (inferred: version 307, last updated 2026-10-10 ([Kaggle API metadata](https://www.kaggle.com/api/v1/datasets/view/Cornell-University/arxiv))). | Public snapshot quarterly (second Wednesday of Jan, Apr, Jul, Oct); daily snapshot needs a paid plan ([snapshot](https://help.openalex.org/access/snapshot/)) | Live via API; dumps monthly ([data dumps](https://meta.wikimedia.org/wiki/Data_dumps)) |
| Size | All of arXiv on Kaggle: **3,205,432 records, 5,610,256,780 bytes (5.61 GB)**, measured on the file downloaded on 2026-10-14 (same byte count as version 307 in the [Kaggle API metadata](https://www.kaggle.com/api/v1/datasets/view/Cornell-University/arxiv)); the "1.7M+" in the Kaggle description is outdated. `cs.CL` including cross-lists: **121,860 records, 233 MB** (see Measured subset below). `cs.CL` listing totals on 2026-10-13: 2022: 8,959; 2023: 13,565; 2024: 20,654; 2025: 23,696; 2026 to date: 18,702 ([cs.CL 2025 listing](https://arxiv.org/list/cs.CL/2025)). Past week: 765 entries ([past week](https://arxiv.org/list/cs.CL/pastweek)). These listing totals **include cross-lists**: they match the snapshot counts including cross-lists (2024: 20,654 vs 20,689; 2025: 23,696 vs 23,762), not the primary-only counts (14,999; 17,086). | Whole snapshot (Sept 2026 release): about 745 GB JSON Lines (615 GB works), about 626M records ([snapshot](https://help.openalex.org/access/snapshot/)). Too big to download for an enrichment role; use the API by DOI. | Subset size unknown until the category crawl (W1-D2). Full English dumps are 100+ GiB compressed with history ([data dumps](https://meta.wikimedia.org/wiki/Data_dumps)). |

## Measured subset: arXiv `cs.CL` (W1-D2-FAO-1, 2026-10-14)

Method: one streaming pass over `arxiv-metadata-oai-snapshot.json` (3,205,432 records, 5.61 GB, 77 s on a laptop) with `pipelines/scripts/profile_arxiv_snapshot.py`. A record is in `cs.CL` if `categories` contains `cs.CL`; it is primary if `cs.CL` is the first entry. Year = year of the first version (`versions[0].created`).

| Year | `cs.CL` primary | `cs.CL` incl. cross-lists | Records since this year (incl.) |
|---|---:|---:|---:|
| 1994-1997 | 0 | 814 | 121,860 |
| 1998-2011 | 795 | 1,062 | 121,046 |
| 2012 | 147 | 225 | 119,984 |
| 2013 | 219 | 334 | 119,759 |
| 2014 | 396 | 557 | 119,425 |
| 2015 | 587 | 832 | 118,868 |
| 2016 | 1,306 | 1,692 | 118,036 |
| 2017 | 1,922 | 2,400 | 116,344 |
| 2018 | 2,974 | 3,729 | 113,944 |
| 2019 | 4,170 | 5,393 | 110,215 |
| 2020 | 5,582 | 7,125 | 104,822 |
| 2021 | 6,578 | 8,083 | 97,697 |
| 2022 | 7,133 | 8,971 | 89,614 |
| 2023 | 10,482 | 13,603 | 80,643 |
| 2024 | 14,999 | 20,689 | 67,040 |
| 2025 | 17,086 | 23,762 | 46,351 |
| 2026 (to 2026-10-10) | 15,185 | 22,589 | 22,589 |

- `cs.CL` incl. cross-lists: 121,860 records, 233 MB of metadata, 1,914 bytes and 1,197 abstract characters per record.
- Cross-lists come mostly from `cs.LG` (7,879), `cs.AI` (5,759), `cs.CV` (4,647), `cs.IR` (2,545), `eess.AS` (1,734), `cs.SD` (1,383). 1994-1997 have no primary `cs.CL`: those papers have primary `cmp-lg`, the pre-1998 name of the category (894 `cmp-lg` records in total).
- Since 2018, primary-only is 72-80% of the count including cross-lists.

Embedding throughput (`pipelines/scripts/bench_embeddings.py`): 1,000 random `cs.CL` records from 2022 on (seed 42), text `title. abstract`, batch 64, Google Colab. Estimated time for a full run = records since the start year / measured throughput, assuming one chunk per abstract and no other overhead (an estimate, not a measurement).

| Model (dim) | Device | Records/s | Since 2015 | Since 2018 | Since 2020 | Since 2022 | Since 2024 |
|---|---|---:|---:|---:|---:|---:|---:|
| `BAAI/bge-small-en-v1.5` (384) | Tesla T4 | 145.8 | 14 min | 13 min | 12 min | 10 min | 8 min |
| `BAAI/bge-base-en-v1.5` (768) | Tesla T4 | 49.3 | 40 min | 39 min | 35 min | 30 min | 23 min |
| `BAAI/bge-small-en-v1.5` (384) | Colab CPU | 2.8 | 12.0 h | 11.4 h | 10.5 h | 9.0 h | 6.7 h |
| `BAAI/bge-base-en-v1.5` (768) | Colab CPU | 0.9 | 37.7 h | 36.2 h | 33.3 h | 28.4 h | 21.3 h |

On a T4, every candidate start year (even all 121,860 records) embeds in under an hour with either model, so the start year is not limited by embedding time; on CPU none fits a night with bge-base. The sample is in `data/raw/sample/` (git-ignored); a 20-record fixture (CC0 metadata, without `submitter` and `authors_parsed`) is in `pipelines/tests/fixtures/sample.jsonl`.

## First reading (input for ADR 0003, not a decision)

- **arXiv:** bulk load from the Kaggle snapshot (one download, filter `cs.CL` locally, no rate limit), keep OAI-PMH (`cs:cs:CL`, `from=` date) for incremental ingestion in W5, use the search API only for quick samples. `cs.CL` including cross-lists from 2022 is 89,614 papers (measured; about 1.2 KB of abstract per paper, 1.9 KB of metadata).
- **OpenAlex:** keep optional. It adds citations and topics but no plain-text abstracts and no arXiv category, and the API now has a daily budget. Cut first if time is short.
- **Wikipedia:** small (estimate, not measured: hundreds to a few thousand pages); fetch through the API by category. Share-alike licence means the `license` field must say `CC BY-SA 4.0` and the UI must link the article.

## Guidelines
- Start with titles and abstracts; add full text for a subset only if time allows and the licence permits.
- Store raw and processed data in `data/` (git-ignored). Commit only download scripts and this document.
- Record the licence/terms per record in the `license` field of the chunk schema.
