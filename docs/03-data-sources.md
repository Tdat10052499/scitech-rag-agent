# Data sources

Status: **candidate list, not yet verified.** Week 1 task `W01-01` must confirm size, format, access method, update frequency and licence for each source before ingestion starts.

| Source | Content | Intended role | To verify |
|---|---|---|---|
| arXiv (metadata snapshot, API/OAI-PMH) | Titles, abstracts, categories, dates | Core corpus; daily new items could serve as the streaming source | Actual snapshot size, API rate limits, terms of use |
| OpenAlex | Works, authors, topics, citations | Metadata enrichment, optional citation graph | Licence, download method, volume |
| Wikipedia (science/technology articles) | Explanatory text | Background knowledge | Licence/attribution requirements, extraction method |

Guidelines
- Start with titles and abstracts; add full text for a subset only if time allows and the licence permits.
- Store raw and processed data in `data/` (git-ignored). Commit only download scripts and this document.
- Record the licence/terms per record in the `license` field of the chunk schema.
