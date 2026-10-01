# pipelines/ — data ingestion

Scope: download open datasets, clean them, split into chunks, create embeddings, load them into the vector store.
Source of truth for output: `docs/contracts/chunk.schema.json`. Sources and licences: `docs/03-data-sources.md`.

- Code in `src/scitech_pipelines/`, tests in `tests/`. Runtime dependencies in `requirements.txt` (create it with your first dependency).
- Every step must be re-runnable (idempotent) and take paths/URLs from arguments or env vars, not constants.
- Raw and processed data go to the git-ignored `data/` directory, never into git.
- Respect source terms and rate limits (e.g. pause between API requests). Record licence per record in the `license` field.
- Large-scale processing (Spark or similar) is justified only if the data volume requires it; record that decision in `docs/decisions/`.
- Validate outputs against the chunk schema in tests.
