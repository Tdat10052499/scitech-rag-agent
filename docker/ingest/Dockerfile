# Scheduled ingestion (W7-D6-FAO-1, ADR 0011): `incremental-run` every INGEST_EVERY_HOURS hours
# against the live collection, with a BM25 rebuild after each load. Build context: the repository
# root (`docker compose build ingest`); `Dockerfile.dockerignore` next to this file replaces the
# root .dockerignore for this image, which needs pipelines/.
# Debian bookworm pinned: it ships Java 17, which PySpark 4 (`clean`) needs (ADR 0005).
FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/pipelines/src:/app/agent/src \
    DATA_DIR=/app/data

WORKDIR /app

# CPU-only PyTorch first, so sentence-transformers does not pull the CUDA build. Retries: a cut
# download of the 200 MB wheel fails pip's hash check (seen on FAO's laptop, #146).
COPY pipelines/requirements.txt pipelines/requirements-embed.txt pipelines/
COPY agent/requirements.txt agent/
RUN pip install --retries 10 --timeout 120 --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install --retries 10 --timeout 120 \
        -r pipelines/requirements-embed.txt -r agent/requirements.txt

COPY pipelines/src pipelines/src
COPY agent/src agent/src
COPY docker/ingest/ingest.sh docker/ingest/setup-live.sh docker/ingest/catch-up.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/ingest.sh /usr/local/bin/setup-live.sh /usr/local/bin/catch-up.sh

CMD ["ingest.sh"]
