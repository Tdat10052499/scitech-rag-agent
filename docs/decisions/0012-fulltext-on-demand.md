# 0012. Read a paper's full text on demand, without indexing it

- Status: accepted (2026-11-03; FAO approved #187, which merged the same day; LDN has not reviewed it yet. The hosted Space passed the full-text questions of the trap test set on 2026-11-03)
- Date: 2026-11-03
- Deciders: DAT (author), FAO (pipelines, data scope), LDN (evaluation impact)

## Context
The index holds titles and abstracts of arXiv `cs.CL` only (ADR 0003). Full-text PDFs were out of scope. Testing the Space on 2026-11-03 showed the cost of this limit. After finding a paper, users ask about its method, data or results, and the abstract does not hold the answer, so the agent refuses or stays vague. PR #186 added questions that name a paper by arXiv id (`scitech_agent.intent`, reason `arxiv_id`). Today such a question sees only that paper's abstract.

Facts and estimates:
- Index: 121,926 chunks, embedded in 863 s on a T4 (ADR 0007). Suppose a full text gives about 50 chunks per paper (an assumption, not measured). The corpus would then be about 6 million chunks, about 9 GB of float32 vectors at 384 dimensions, and about 12 hours of embedding on a T4, extrapolated from ADR 0007.
- Most arXiv papers are under arXiv's default licence, not CC. Storing and serving their full text from our index is not covered the way the CC0 metadata is (ADR 0003).
- arXiv serves an HTML rendering (LaTeXML) of most recent papers at `arxiv.org/html/<id>`, and ar5iv (`ar5iv.labs.arxiv.org/html/<id>`) covers older ones. Coverage is an assumption to check on a sample. arXiv asks clients to send at most one request every 3 s.
- The evaluation index is frozen until v1.0 (2026-11-06), and the golden set has no question with an arXiv id (`agent/tests/test_intent.py`).

## Options considered
1. Keep abstracts only; describe full text as future work.
2. Index the full text of all 121,860 papers: see the estimates above (size, time, licence). Not possible before the defense.
3. Index the full text of a CC-licensed subset: needs a new PDF pipeline and a rebuild of the frozen index.
4. Read the full text of one paper on demand, when a question names it, and keep the passages in memory only.

## Decision
**Option 4**, behind the flag `AGENT_FULLTEXT` (empty: on; `off` restores #186):
- `scitech_agent.fulltext.ArxivHtmlFetcher` downloads the paper's HTML from `FULLTEXT_URLS` (default: arxiv.org/html, then ar5iv). Requests are at least 3 s apart, with a timeout of `FULLTEXT_TIMEOUT` (10 s) and a User-Agent that names the project.
- The page is parsed with the standard library. The parser keeps section headings, paragraphs and captions, keeps math as TeX, and drops the bibliography, navigation and footnotes. The text is cut into passages of at most 180 words.
- Passages are ranked against the question with the dense retriever's model (`embed_passages`, bge-small), or by word overlap when there is no dense retriever. A question without English topic words ("explain 2302.00083", or most Vietnamese questions) gets the first passage of each section.
- The answer sees the paper's abstract (when it is in the index) plus `FULLTEXT_TOP_K` passages (6). Their titles end with `(full text, section: ...)`, and `prompts/answer_papers.md` asks the model to name the section it uses.
- Nothing is written to disk. The latest `FULLTEXT_CACHE` papers (32) stay in memory. Each request reads the paper for the user's question, so the full text is not stored or redistributed.
- Any failure (network, HTTP status, no HTML version, empty page) keeps the abstract only. The answer then says the full text could not be read. The trace records the outcome in `search.fulltext` (`read`, `cached` or `unavailable`).

## Consequences
- Deep questions about one paper can be answered from its body, and the answer stays grounded: it cites passages that were actually retrieved. It also works for papers outside the `cs.CL` index when the user gives their id.
- The evaluation numbers do not change: the frozen index is untouched, and no golden item names an arXiv id. The new mode has no measured quality yet. It needs a small set of 5–10 deep questions whose answers are in the body, reported apart from the W7 numbers.
- The laptop check (2026-11-03, llama3.2:3b) showed the small model citing a passage for perplexity numbers that are in no source (the paper shows them in figures). A full-text answer therefore gets a visible warning when it cites nothing or has numbers its cited sources do not contain (`check_numbers`). The warning flags the problem; it does not correct the answer.
- Risks:
  - The Space must reach arxiv.org. The cloud container used for development could not, so the fetch was tested with a fake client only.
  - The first question about a paper is slower: one fetch, plus embedding about 50 to 400 passages on CPU. This has not been measured.
  - Tables and equations extract poorly, and papers without an HTML rendering fall back to the abstract.
- Revisit after the defense: a PDF fallback (a new dependency), and a disk cache if the same papers are asked about often.
