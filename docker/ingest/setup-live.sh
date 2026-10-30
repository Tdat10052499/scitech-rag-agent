#!/bin/sh
# One-time setup of the live index (W7-D6-FAO-1, ADR 0011): load the frozen bulk chunks and
# vectors into a new collection INGEST_COLLECTION, copy the frozen BM25 index to BM25_LIVE_DIR,
# and write the first watermark with the first scheduled run (--start = snapshot day).
# The frozen collection and data/index/bm25 are only read.
#   docker compose run --rm ingest setup-live.sh
set -eu

COLLECTION="${INGEST_COLLECTION:-scitech_chunks_live}"
BM25_LIVE="${BM25_LIVE_DIR:-data/index/bm25-live}"
BM25_FROZEN="${BM25_INDEX_DIR:-data/index/bm25}"
START="${INGEST_START:-2026-10-10}"  # Kaggle snapshot 307 (evaluation/SNAPSHOT.md)
FROZEN="${FROZEN_COLLECTION:-scitech_chunks}"

if [ "$COLLECTION" = "$FROZEN" ]; then
    echo "setup-live: INGEST_COLLECTION must not be the frozen collection $FROZEN" >&2
    exit 1
fi
if [ -e "$BM25_LIVE" ]; then
    echo "setup-live: $BM25_LIVE exists already; remove it first to set up again" >&2
    exit 1
fi

python -m scitech_pipelines --data-dir "$DATA_DIR" load --collection "$COLLECTION" \
    --out "$DATA_DIR/processed/index-live"
cp -r "$BM25_FROZEN" "$BM25_LIVE.next"
mv "$BM25_LIVE.next" "$BM25_LIVE"
echo "setup-live: $COLLECTION loaded and $BM25_LIVE copied from $BM25_FROZEN"
echo "setup-live: first run (catches up from $START to today, about 10 minutes on a CPU):"
python -m scitech_pipelines --data-dir "$DATA_DIR" incremental-run \
    --collection "$COLLECTION" --until today --rebuild-bm25 "$BM25_LIVE" \
    --model "$EMBEDDING_MODEL" --device cpu --start "$START"
