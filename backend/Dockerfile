# Backend API with the agent package (W6-D3-DAT-1). Build context: the repository root
# (`docker compose build backend`), because the backend imports agent/src.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/agent/src

WORKDIR /app

# Query embedding of the dense and hybrid retrievers needs sentence-transformers. PyTorch is
# installed first from the CPU-only index, so sentence-transformers does not pull the CUDA build
# (several GB). Build with `--build-arg WITH_EMBED=0` for a small image that only runs
# RETRIEVER=bm25 or AGENT_MODE=demo.
ARG WITH_EMBED=1
COPY backend/requirements.txt backend/requirements.txt
COPY agent/requirements.txt agent/requirements-embed.txt agent/
RUN pip install -r backend/requirements.txt -r agent/requirements.txt \
    && if [ "$WITH_EMBED" = "1" ]; then \
        pip install --index-url https://download.pytorch.org/whl/cpu torch \
        && pip install -r agent/requirements-embed.txt; \
    fi

COPY agent/src agent/src
COPY agent/prompts agent/prompts
COPY backend/src backend/src

# data/ (BM25 index, logs, traces) is mounted here by docker compose.
ENV DATA_DIR=/app/data
EXPOSE 8000

# The server answers /health only after startup (agent build and embedding warm-up, about
# 15 s on a laptop plus a model download on the first start).
HEALTHCHECK --interval=10s --timeout=5s --start-period=180s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "backend/src", "--host", "0.0.0.0", "--port", "8000"]
