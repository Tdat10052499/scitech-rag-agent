#!/bin/sh
# Entry point of the Space container (deploy/hf-space): Qdrant, then the index, then the backend,
# then nginx in the foreground on 7860. If a step fails the container stops and the Space shows
# the log (Settings > Logs).
set -eu

export QDRANT_URL="${QDRANT_URL:-http://127.0.0.1:6333}"
export BM25_INDEX_DIR="${BM25_INDEX_DIR:-$DATA_DIR/index-src/bm25}"
# A public deployment keeps no per-question traces unless asked (they hold visitors' questions).
export AGENT_TRACES="${AGENT_TRACES:-off}"

QDRANT__SERVICE__HOST=127.0.0.1 \
QDRANT__STORAGE__STORAGE_PATH="$DATA_DIR/qdrant/storage" \
QDRANT__STORAGE__SNAPSHOTS_PATH="$DATA_DIR/qdrant/snapshots" \
QDRANT__TELEMETRY_DISABLED=true \
    qdrant --disable-telemetry > /app/run/qdrant.log 2>&1 &

python /app/fetch_index.py

python -m uvicorn app.main:app --app-dir /app/backend/src --host 127.0.0.1 --port 8000 &

sed -e "s/__CHAT_PER_MINUTE__/${CHAT_PER_MINUTE:-3}/" \
    -e "s/__CHAT_TOTAL_PER_MINUTE__/${CHAT_TOTAL_PER_MINUTE:-4}/" \
    /app/nginx.conf > /app/run/nginx.conf
exec nginx -c /app/run/nginx.conf -g "daemon off;"
