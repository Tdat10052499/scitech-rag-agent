# Live index: backend on the scheduled ingestion (ADR 0011)

W7-D7-DAT-1. The scheduled ingestion keeps a separate live collection and BM25 index up to date
every 2 hours, and the demo backend reads them without a restart. The frozen evaluation index
(`scitech_chunks`, `data/index/bm25`) is never written. Every evaluation run uses the frozen
settings: `BM25_RELOAD_SECONDS` empty and the frozen collection.

The setup of the live index and the `ingest` container itself are in
`docs/runbooks/data-pipeline.md`, section 6, "Scheduled runs" (W7-D6-FAO-1).

## 1. Settings (`.env`)

| Setting | Frozen (default) | Live demo |
|---|---|---|
| `QDRANT_COLLECTION` | `scitech_chunks` | `scitech_chunks_live` |
| `BM25_INDEX_DIR` | empty (`data/index/bm25`) | `data/index/bm25-live` |
| `BM25_RELOAD_SECONDS` | empty or `0`: load once | `60` |
| `INGEST_ENABLED` (shell, read by make) | empty or `0` | `1` |

## 2. Start and stop

```bash
INGEST_ENABLED=1 make up     # Qdrant, backend, frontend and ingest
make down                    # stops all four, ingest included; data/ and the volumes are kept
```

Without make (Windows PowerShell): `docker compose --profile ingest up -d --build`, and
`docker compose --profile ingest down`. `make up` with `INGEST_ENABLED` empty starts the frozen
stack only. The `ingest` service restarts by itself (`restart: unless-stopped`) after a crash or
a Docker restart. Its log goes to `data/logs/incremental.log`.

## 3. How the reload works

- The ingestion writes the new BM25 index to `bm25-live.next` and switches it in with two renames
  (`scitech_pipelines.bm25_live.switch_dir`).
- With `BM25_RELOAD_SECONDS=N`, at most every N seconds the first search reads
  `_bm25_manifest.json`. When the file's content has changed, that search loads the new index and
  swaps the whole retriever object under a lock.
- A search that already started finishes on the old index. Other searches keep using the old
  index while the new one loads.
- If the manifest is missing (the moment between the two renames) or the new index fails to
  load, the backend logs a warning or error and keeps the old index. The next check tries again.
- A new paper is cited at the latest N seconds plus the load time after the BM25 switch. The
  BM25 build ran 15.8-20.3 s on DAT's laptop; the load is a few seconds. The dense half finds new
  papers as soon as they are loaded into Qdrant.
- While it loads, the backend holds two indexes in memory, about 2 x 177 MiB for the bulk index.

Log lines (`docker compose logs backend`). The backend sets no log level, so only the warning
and error lines show by default; the `switched` line is at INFO level:

- `bm25 reload: switched to the index at data/index/bm25-live (N chunks)`
- `bm25 reload: cannot read ... ; keeping the old index`
- `bm25 reload: new index at ... failed to load (...); keeping the old index`

## 4. Check it

1. Start as in section 2 with the live settings, and wait for a run that loaded papers
   (`incremental: N of M papers new or changed` in `data/logs/incremental.log`).
2. Within `BM25_RELOAD_SECONDS`, the backend log shows `bm25 reload: switched`.
3. Ask about a paper announced that day: it is cited.
