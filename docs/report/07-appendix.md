# Appendix

Status: draft by DAT, 2026-11-02, ahead of W8-D5-DAT-1. Sections A to D follow `docs/report/00-outline.md`. Drafted with AI assistance (Claude); DAT is responsible for the final text.

## A. How to run

The full steps are in `README.md`. In short:

- **With Docker:** `make setup`, copy `.env.example` to `.env`, then `make up`. This starts Qdrant, the backend on port 8000 and the frontend on port 8080. The LLM runs outside the stack: Ollama on the same machine, or any OpenAI-compatible endpoint (`docs/runbooks/llm-serving.md`).
- **Windows without Docker:** README section "Run the real app on Windows without Docker". It covers native Qdrant, Ollama, `.env` loaded into the shell, `PYTHONPATH`, uvicorn and the frontend dev server. This is how the Week 7 runs and the clean-clone check of 2026-10-30 were done.
- **Index:**
  - The index is not in the repository. Build it from the Kaggle arXiv snapshot with `docs/runbooks/data-pipeline.md`, or load the release data.
  - The evaluation index is frozen: collection `scitech_chunks`, 121,926 points, id in `evaluation/SNAPSHOT.md`.
- **Evaluation:** `evaluation/RUNS.md` lists every run, with its config, command and result file.

## B. Architecture decisions

| ADR | Decision | Status |
|---|---|---|
| 0001 | Hybrid LLM backend behind an OpenAI-compatible interface | accepted |
| 0002 | Retrieval-augmented generation instead of training on the corpus | accepted |
| 0003 | Corpus: all of arXiv `cs.CL` from the Kaggle snapshot, Wikipedia as background | accepted 2026-10-14 |
| 0004 | Frontend framework: React + Vite + TypeScript | accepted 2026-10-14 |
| 0005 | Processing engine: PySpark in local mode, DuckDB for checks | accepted 2026-10-16 |
| 0006 | LLM model and serving | accepted 2026-10-19 |
| 0007 | Embedding model: bge-small-en-v1.5 with the query instruction | accepted 2026-10-20 |
| 0008 | Incremental ingestion: daily OAI-PMH harvest with a date watermark | accepted 2026-10-27 |
| 0009 | Default retrieval configuration (hybrid, RRF) | accepted 2026-10-22 |
| 0010 | Compressed schedule: 2026-10-13 to 2026-11-06, and the features it cut | accepted 2026-10-13 |
| 0011 | Scheduled incremental ingestion every 2 hours on a separate serving index | accepted 2026-10-30 |

Each file is `docs/decisions/<number>-<slug>.md`. It has the context, the options, the decision, its consequences, and the measurements behind it.

## C. Golden set format

The golden set is `evaluation/golden_set/golden.jsonl`, one JSON object per line. The full rules are in `evaluation/golden_set/FORMAT.md`.

- **Size:** 65 items. 60 are answerable (30 dev, 30 test) and 5 are unanswerable (#168).
- **Fields:** `id`, `question`, `type`, `relevant_doc_ids`, `reference_answer`, `split`, `author` and `notes`.
- **Follow-up turns:** these also carry `history` (the earlier turns) and `standalone_query` (the question rewritten without the history).
- **Types:** factual, explanatory, comparison, multi-hop, follow-up and unanswerable.
- **How items were made:** each item was written from one or more abstracts in the corpus, by the member in its `author` field; `notes` records how it was made. Unanswerable items were checked against the full index (FORMAT rule 7; FAO's search on #168).
- **Coverage:** all 78 relevant documents are in the frozen index (W7-D1-FAO-1, #156).

## D. Team and use of AI tools

| Member | GitHub | Main areas |
|---|---|---|
| DAT | `Tdat10052499` | Agent, backend, LLM serving, evaluation runs on the W7 host, report chapters 1 and 3, release |
| FAO | `F4ol4n` | Data pipeline, processing engine, index, incremental and scheduled ingestion, scaling, report chapters 2 and 6 |
| LDN | `Yui-Mika` | Golden set, evaluation runner and judges, user study, frontend, report chapters 4 and 5 |

**Work method.** The work was planned day by day (`docs/plan/`). Each task had an ID, used in branch names, pull requests and journals (`docs/journal/`). Each member merged their own pull requests after review. Blocking tasks, contract changes and evaluation runs were reviewed by another member (`CONTRIBUTING.md`).

**AI tools.** All three members used an AI assistant (Claude, through Claude Code) to draft code, documents, reviews and comments. The rules in `CONTRIBUTING.md` and `AGENTS.md` applied to all of it:
- The member is the author.
- The member reads the whole diff, runs the tests, and can explain every change.
- Texts drafted with AI say so ("Drafted with AI assistance").

AI was not used as a source of facts about the papers. The answers of the system come from the retrieved passages, and the evaluation numbers come from run files in the repository. The faithfulness and relevance judges are LLMs (`qwen2.5:7b`). Their labels are checked against human labels on a sample (`evaluation/PLAN.md` §5), and the report states the agreement.
