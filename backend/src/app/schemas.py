"""Request and event payload models of the frozen API contract (docs/contracts/api.openapi.yaml)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ErrorCode = Literal["llm_unavailable", "retrieval_failed", "timeout", "internal"]


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1)


class FeedbackRequest(BaseModel):
    """Body of `POST /feedback` (issue #147): a thumbs rating of an answer or a follow-up, or a
    click on a follow-up suggestion."""

    session_id: str
    message_id: str = Field(min_length=1)
    target: Literal["answer", "followup"]
    rating: Literal["up", "down", "click"]
    followup: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _check_target(self) -> FeedbackRequest:
        if self.target == "answer":
            if self.rating == "click":
                raise ValueError("rating 'click' needs target 'followup'")
            if self.followup is not None:
                raise ValueError("followup is only allowed with target 'followup'")
        elif self.followup is None:
            raise ValueError("target 'followup' needs the followup text")
        return self


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
