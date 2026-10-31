#!/bin/sh
# Entry point of the `ingest` container (W7-D6-FAO-1, ADR 0011): run `incremental-run` on the
# live collection every INGEST_EVERY_HOURS hours, on the hour (UTC), and rebuild its BM25 index
# after each load. Output: `docker compose logs ingest` and data/logs/incremental.log.
set -eu

: "${EMBEDDING_MODEL:?set EMBEDDING_MODEL in .env (ADR 0007)}"
COLLECTION="${INGEST_COLLECTION:-scitech_chunks_live}"
BM25_LIVE="${BM25_LIVE_DIR:-data/index/bm25-live}"
EVERY="${INGEST_EVERY_HOURS:-2}"

if [ ! -f "$BM25_LIVE/_bm25_manifest.json" ]; then
    echo "ingest: $BM25_LIVE has no BM25 index; run setup-live.sh once (runbook section 6)" >&2
    exit 1
fi

set -- python -m scitech_pipelines.schedule --every-hours "$EVERY" \
    --log "$DATA_DIR/logs/incremental.log"
if [ "${INGEST_RUN_NOW:-0}" = "1" ]; then
    set -- "$@" --run-now
fi
exec "$@" -- python -m scitech_pipelines --data-dir "$DATA_DIR" incremental-run \
    --collection "$COLLECTION" --until today --rebuild-bm25 "$BM25_LIVE" \
    --model "$EMBEDDING_MODEL" --device cpu
