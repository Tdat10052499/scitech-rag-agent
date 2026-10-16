"""Request and event payload models of the frozen API contract (docs/contracts/api.openapi.yaml)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

ErrorCode = Literal["llm_unavailable", "retrieval_failed", "timeout", "internal"]


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1)


class Source(BaseModel):
    chunk_id: str
    doc_id: str
    title: str
    score: float
    url: str | None = None
    snippet: str | None = None
    source: Literal["arxiv", "openalex", "wikipedia"] | None = None
    published_at: date | None = None
    categories: list[str] | None = None


class Done(BaseModel):
    insufficient_evidence: bool = False
    message_id: str | None = None


class Error(BaseModel):
    code: ErrorCode
    message: str
