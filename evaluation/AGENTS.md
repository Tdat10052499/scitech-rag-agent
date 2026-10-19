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
- `compare <run> <run> ...` (two or more run files; the first is the baseline) prints each run's setup, a table of the metrics with their 95% intervals, and for every other run a paired comparison with the baseline: mean difference per question, a bootstrap interval of it, and wins, losses and ties. It warns when the runs used a different golden file, split, language or query mode, and pairs only the questions that both runs scored. It exits 0, or 2 when a file cannot be read or is not a run file.
- `query: question` (default) sends each question as asked. `query: standalone_query` sends the rewritten query of follow-up items instead (other items keep their question). The choice is stored in the run file under `config` and, per item, as `query`, so a run says which text was searched.
- A retriever is any object with `search(query, k, filters=None)` returning chunks that have `chunk_id` and `doc_id` (the agent's `Retriever` and `ScoredChunk` fit). Point `retriever.factory` at a `module:callable` that builds it.
- `pytest` runs the harness tests (`pythonpath` is set in `pyproject.toml`).
