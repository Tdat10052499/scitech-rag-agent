#!/bin/sh
# First run on the live index (W7-D6-FAO-1, ADR 0011): catch up from the snapshot day to today
# and write the first watermark. setup-live.sh ends with it; run it alone when that first run
# failed (setup-live.sh then stops because the live BM25 index exists):
#   docker compose run --rm ingest catch-up.sh
# With a watermark already written, --start is ignored and the run goes on from the watermark.
set -eu

: "${EMBEDDING_MODEL:?set EMBEDDING_MODEL in .env (ADR 0007)}"
COLLECTION="${INGEST_COLLECTION:-scitech_chunks_live}"
BM25_LIVE="${BM25_LIVE_DIR:-data/index/bm25-live}"
START="${INGEST_START:-2026-10-10}"  # Kaggle snapshot 307 (evaluation/SNAPSHOT.md)

echo "catch-up: from $START (or the watermark) to today, about 10 minutes on a CPU"
exec python -m scitech_pipelines --data-dir "$DATA_DIR" incremental-run \
    --collection "$COLLECTION" --until today --rebuild-bm25 "$BM25_LIVE" \
    --model "$EMBEDDING_MODEL" --device cpu --start "$START"
