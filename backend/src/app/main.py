"""FastAPI entry point. Endpoints follow docs/contracts/api.openapi.yaml."""

from fastapi import FastAPI

app = FastAPI(title="SciTech RAG Agent", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by CI, Docker Compose and the frontend."""
    return {"status": "ok"}
