# evaluation/ — experimental evaluation

Scope: golden question set, retrieval metrics (e.g. recall@k, MRR), answer quality (faithfulness to retrieved evidence, relevance), follow-up suggestion ratings, experiment reports.

- `golden_set/` holds questions with the documents that should be retrieved; document how each item was created and by whom.
- Every reported result must state: dataset snapshot, model and parameters, code revision (commit hash), sample size, and known limitations. Distinguish measured results from hypotheses.
- If an LLM is used as an automatic judge, state which model and note its possible bias; check a sample by hand.
- Results go to `reports/` as files, so experiments can be reproduced and compared.
