# evaluation/ — experimental evaluation

Scope: golden question set, retrieval metrics (e.g. recall@k, MRR), answer quality (faithfulness to retrieved evidence, relevance), follow-up suggestion ratings, experiment reports.

- `golden_set/` holds questions with the documents that should be retrieved; document how each item was created and by whom.
- Every reported result must state: dataset snapshot, model and parameters, code revision (commit hash), sample size, and known limitations. Distinguish measured results from hypotheses.
- If an LLM is used as an automatic judge, state which model and note its possible bias; check a sample by hand.
- Results go to `reports/` as files, so experiments can be reproduced and compared.

## Running the harness

Run from the repository root. The package is not installed, so put `evaluation/src` on the Python path and install its dependency first (`pip install -r evaluation/requirements.txt`).

```powershell
# Windows PowerShell
$env:PYTHONPATH = "evaluation/src"
python -m scitech_eval check-golden evaluation/golden_set/golden.jsonl
python -m scitech_eval retrieval --config evaluation/configs/toy.yaml --out-dir evaluation/runs
python -m scitech_eval compare evaluation/runs/<run-a>.json evaluation/runs/<run-b>.json
```

```bash
# macOS / Linux
PYTHONPATH=evaluation/src python -m scitech_eval check-golden evaluation/golden_set/golden.jsonl
PYTHONPATH=evaluation/src python -m scitech_eval retrieval --config evaluation/configs/toy.yaml --out-dir evaluation/runs
PYTHONPATH=evaluation/src python -m scitech_eval compare evaluation/runs/<run-a>.json evaluation/runs/<run-b>.json
```

- `check-golden [path] [--corpus file.jsonl --id-field doc_id]` checks the file against `golden_set/FORMAT.md`; with `--corpus` it also checks that every relevant doc id exists in that file. It exits 0 when the file is valid, 1 when it has problems, 2 when a file cannot be read.
- `retrieval --config <yaml>` writes one run file (JSON) to `--out-dir`. The config sets `split`, `language`, `ks`, the `retriever` factory and what the run is about: `dataset_snapshot`, `retriever_type` (a label such as `dense`, `bm25`, `hybrid`), `embedding_model` (empty for BM25), `index_snapshot` (the id of the loaded index, from FAO's manifest) and free-text `notes`; see `configs/toy.yaml`. The run file repeats all of these, adds the git commit and the timings (`run_seconds`, and `search_seconds` as total, median and maximum, plus `search_seconds` per question). The timings are the wall-clock time of `retriever.search` on the machine that ran it, not a latency benchmark.
- `compare <run> <run> ...` (two or more run files; the first is the baseline) prints each run's setup, a table of the metrics with their 95% intervals, and for every other run a paired comparison with the baseline: mean difference per question, a bootstrap interval of it, and wins, losses and ties. The paired table has a `questions` column (mean difference times the number of questions, recall rows only; ADR 0009 states its rule in questions). It warns when the runs used a different golden file, split, language, query mode, `index_snapshot` or `dataset_snapshot`, or left a snapshot as `unspecified`, and pairs only the questions that both runs scored. It exits 0, or 2 when a file cannot be read or is not a run file.
- `query: question` (default) sends each question as asked. `query: standalone_query` sends the rewritten query of follow-up items instead (other items keep their question). The choice is stored in the run file under `config` and, per item, as `query`, so a run says which text was searched.
- `scitech_eval.retrievers:agent_retriever` builds the agent's dense, BM25 or hybrid retriever for a config (`params.retriever: dense|bm25|hybrid`; other params are environment variables such as `RRF_K`, and the process environment supplies the rest). It imports `scitech_agent.retrieval.hybrid` (on `main` since #82), so `agent/src` must be on `PYTHONPATH`. Put every setting that changes the ranking (`QDRANT_SEARCH_EXACT`, `RRF_K`, `HYBRID_DENSE_TOP_K`, `HYBRID_KEYWORD_TOP_K`) in `params`, because only `params` reach the run file; the process environment is not recorded.
- A retriever is any object with `search(query, k, filters=None)` returning chunks that have `chunk_id` and `doc_id` (the agent's `Retriever` and `ScoredChunk` fit). Point `retriever.factory` at a `module:callable` that builds it.
- `pytest` runs the harness tests (`pythonpath` is set in `pyproject.toml`).

## Retrieval comparison v1 (W3-D4-LDN-1, ADR 0009 table B)

Three configs, `configs/retrieval-v1-{dense,bm25,hybrid}.yaml`, run the 30 answerable dev items on the same index. They differ only in the retriever; do not change `golden_path`, `split`, `ks` or the two snapshot labels in one of them without changing all three. Run on the machine that has the full index (Qdrant with the vectors loaded, and the BM25 index), from the repository root, with the agent's environment set as in `.env.example` (`QDRANT_URL`, `QDRANT_COLLECTION`, `DATA_DIR` or `BM25_INDEX_DIR`). Keep the working tree at one commit for all three runs. `index_snapshot` in the three configs must be the id in `_load_manifest.json` of the loaded collection (format `collection/model/chunked-.../embedded-...`); replace it in all three if it differs. Build the BM25 index from the same `chunks.parquet` as the vectors (`python -m scitech_agent.retrieval.keyword build --chunks data/processed/chunks --out data/index/bm25`) and check that `chunked_at` in its `_bm25_manifest.json` equals the `chunked-` part of the snapshot id.

```powershell
# Windows PowerShell
$env:PYTHONPATH = "evaluation/src;agent/src"
python -m scitech_eval check-golden evaluation/golden_set/golden.jsonl
foreach ($t in "hybrid", "dense", "bm25") {
  python -m scitech_eval retrieval --config "evaluation/configs/retrieval-v1-$t.yaml" --out-dir evaluation/runs
}
# <hybrid> <dense> <bm25> = the three files just written; hybrid first, it is the baseline (A)
python -m scitech_eval compare evaluation/runs/<hybrid>.json evaluation/runs/<dense>.json evaluation/runs/<bm25>.json
```

```bash
# macOS / Linux
export PYTHONPATH=evaluation/src:agent/src
python -m scitech_eval check-golden evaluation/golden_set/golden.jsonl
for t in hybrid dense bm25; do
  python -m scitech_eval retrieval --config evaluation/configs/retrieval-v1-$t.yaml --out-dir evaluation/runs
done
python -m scitech_eval compare evaluation/runs/<hybrid>.json evaluation/runs/<dense>.json evaluation/runs/<bm25>.json
```

What to send back: the whole text printed by `compare` (it has the setup of each run, the warnings and the tables) and the three run files. A run with a WARNING about `index_snapshot`, golden file or `unspecified` is not a valid run for the report. In the output, B is dense and C is bm25, each against A = hybrid: the `wins` and `losses` columns are the other retriever's, and the `questions` column is the difference of recall in questions, which is what the ADR 0009 rule reads (a single retriever beats hybrid on recall@5 if `questions` is at least +2 with an `mrr` mean diff that is not negative). The p95 latency guard is not in `compare` (it prints the median search time only); the per-question times are in the run files under `search_seconds`.

## Answers run (W5-D4-LDN-1)

`python -m scitech_eval answers --config <yaml>` answers golden questions with the agent (`Agent.run_batch`) and labels every sentence of each answer with an LLM judge (procedure: `PLAN.md` section 5, prompt: `evaluation/prompts/faithfulness-judge.md`). It needs the agent's environment as in `.env.example` (full index, Kaggle LLM up) and the judge variables `JUDGE_BASE_URL`, `JUDGE_API_KEY`, `JUDGE_MODEL` (decided on #142: `qwen2.5:7b`, temperature 0, one sentence per call; the values stay in the local `.env`, never in the repository). The config `configs/answers-pilot10.yaml` runs the first 10 dev items; fill the `TODO` fields first (`generator.digest` and `generator.max_tokens` from `SNAPSHOT.md`, `judge.max_tokens`, `judge.context_tokens` measured on the Kaggle session with `ollama ps` (column CONTEXT, while the judge model is loaded), `notes`). `traces_path: off` can be written with or without quotes (YAML reads the unquoted word as `false`, which also switches traces off). Run from the repository root:

```powershell
# Windows PowerShell
$env:PYTHONPATH = "evaluation/src;agent/src"
python -m scitech_eval answers --config evaluation/configs/answers-pilot10.yaml --out-dir evaluation/runs
```

```bash
# macOS / Linux
export PYTHONPATH=evaluation/src:agent/src
python -m scitech_eval answers --config evaluation/configs/answers-pilot10.yaml --out-dir evaluation/runs
```

It writes three files in `--out-dir`: `<timestamp>-<name>.json` (the run file: counts, metrics, per-sentence labels, judge and generator settings), `<timestamp>-<name>.answers.jsonl` (one record per question with the answer, sources and trace; `make-sheet` reads it) and `<timestamp>-<name>.traces.jsonl` (the agent's own trace file for this run, set through `AGENT_TRACES`; `traces_path: off` in the config switches it off). The three files share one `<timestamp>-<name>` prefix. The run file holds no tunnel URL.

How to read it: refusals and failed questions are counted separately and are never sent to the judge; an answer that opens with the refusal sentence but still answers (`insufficient_evidence` false) is judged like any other. The fixed refusal sentence ("The sources do not contain enough evidence to answer this question.") is labelled `not checkable` without a judge call (`judge.fixed_refusal_sentences` counts them), and a piece of the answer that is only citation markers (such as `[4]` on its own line) is attached to the sentence before it. A judge reply the parser cannot read, or a failed judge call, is stored as `judge_error` on that sentence, not retried and not counted as a label (`judge.errors` and `counts.judge_error` give the numbers). `over_refusal_rate` is refused answerable questions divided by **all** answerable questions in the run, including those that failed with an error (an error is neither answered nor refused, so it lowers the rate); `counts.errors` says how many there were. Check `judge.prompt_fits_context`: if it is false, sentences were cut by the server; null means `judge.context_tokens` was not measured, so nothing is known. Never compare runs made with different judges or different prompt hashes.
