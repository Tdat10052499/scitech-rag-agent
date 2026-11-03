# One-container image for a Hugging Face Docker Space (hosting, 2026-11-02): Qdrant, the backend
# and the built UI behind nginx on port 7860. Build context: the folder assembled by
# `python deploy/hf-space/push_space.py code` (agent/, backend/, frontend/ and this folder's files
# at the root), not the repository root. The LLM stays outside (LLM_BASE_URL, ADR 0001) and the
# index is downloaded from a Hugging Face dataset repo at startup (start.sh, fetch_index.py).

FROM node:22-alpine AS ui
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Same Qdrant version as docker-compose.yml and the evaluation index.
FROM qdrant/qdrant:v1.19.2 AS qdrant

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/agent/src \
    HF_HOME=/app/.cache/huggingface \
    DATA_DIR=/app/data

# nginx serves the UI; libunwind8 is a runtime library of the Qdrant binary (ldd).
RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx libunwind8 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
COPY agent/requirements.txt agent/requirements-embed.txt agent/
COPY requirements-space.txt ./
RUN pip install -r backend/requirements.txt -r agent/requirements.txt -r requirements-space.txt \
    && pip install --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install -r agent/requirements-embed.txt

# The query embedding model goes into the image, so a restart does not download it again.
ARG EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"

COPY --from=qdrant /qdrant/qdrant /usr/local/bin/qdrant
COPY --from=ui /src/dist /app/ui
COPY agent/src agent/src
COPY agent/prompts agent/prompts
COPY backend/src backend/src
COPY nginx.conf /app/nginx.conf
COPY start.sh fetch_index.py ./

# Spaces run the container as uid 1000; everything that is written at runtime lives under /app.
# A Windows checkout can give start.sh CRLF line ends, which sh cannot run; they are removed.
RUN useradd -m -u 1000 user \
    && mkdir -p /app/data /app/run \
    && sed -i "s/\r$//" /app/start.sh /app/nginx.conf \
    && chmod +x /app/start.sh \
    && chown -R user:user /app
USER user

EXPOSE 7860
CMD ["/app/start.sh"]
