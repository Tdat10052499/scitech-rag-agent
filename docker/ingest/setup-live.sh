#!/bin/sh
# One-time setup of the live index (W7-D6-FAO-1, ADR 0011): load the frozen bulk chunks and
# vectors into a new collection INGEST_COLLECTION, copy the frozen BM25 index to BM25_LIVE_DIR,
# and write the first watermark with the first run (catch-up.sh, --start = snapshot day).
# The frozen collection and data/index/bm25 are only read.
#   docker compose run --rm ingest setup-live.sh
set -eu

: "${EMBEDDING_MODEL:?set EMBEDDING_MODEL in .env (ADR 0007)}"
COLLECTION="${INGEST_COLLECTION:-scitech_chunks_live}"
BM25_LIVE="${BM25_LIVE_DIR:-data/index/bm25-live}"
BM25_FROZEN="${BM25_INDEX_DIR:-data/index/bm25}"
FROZEN="${FROZEN_COLLECTION:-scitech_chunks}"

if [ "$COLLECTION" = "$FROZEN" ]; then
    echo "setup-live: INGEST_COLLECTION must not be the frozen collection $FROZEN" >&2
    exit 1
fi
if [ -e "$BM25_LIVE" ]; then
    echo "setup-live: $BM25_LIVE exists already, so the setup was done before." >&2
    echo "If only its first run failed, do not delete anything: run the catch-up alone with" >&2
    echo "  docker compose run --rm ingest catch-up.sh" >&2
    echo "To set up again from the start, follow 'Stop it' in runbook section 6 first." >&2
    exit 1
fi

python -m scitech_pipelines --data-dir "$DATA_DIR" load --collection "$COLLECTION" \
    --out "$DATA_DIR/processed/index-live"
cp -r "$BM25_FROZEN" "$BM25_LIVE.next"
mv "$BM25_LIVE.next" "$BM25_LIVE"
echo "setup-live: $COLLECTION loaded and $BM25_LIVE copied from $BM25_FROZEN"
exec catch-up.sh
