"""Query embedding (W3-D2-DAT-1): the one place that turns a question into a vector.

The query must be embedded with the model that embedded the corpus (`EMBEDDING_MODEL`, ADR 0007)
and with that model's query rule: bge-*-en-v1.5 expects an instruction before each query and none
before passages, so the instruction is read from `EMBEDDING_QUERY_PREFIX` (empty: none). The
prefix and the query are joined with one space, so a prefix whose trailing space was trimmed by an
`.env` parser still gives the text the model expects. Vectors are L2-normalised, as the corpus
vectors are (`embed` in pipelines), so the store's cosine score is their dot product.

- `SentenceTransformerEmbedder`: the real model, loaded on first use. Needs
  `pip install -r agent/requirements-embed.txt` (sentence-transformers and PyTorch, not installed
  by CI); the first load downloads the model from Hugging Face.
- `FakeEmbedder`: deterministic word-hash vectors for tests; never loads a model.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from scitech_agent.retrieval import RetrievalError


class EmbeddingError(RetrievalError):
    """The query could not be embedded (model missing, failed to load). `retrieval_failed`."""


@dataclass(frozen=True)
class EmbeddingConfig:
    model: str
    query_prefix: str = ""
    device: str | None = None  # None: sentence-transformers picks (GPU if there is one)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> EmbeddingConfig:
        """Read `EMBEDDING_MODEL` (required) and `EMBEDDING_QUERY_PREFIX` (empty: none)."""
        env = os.environ if env is None else env
        model = (env.get("EMBEDDING_MODEL") or "").strip()
        if not model or model == "replace-me":
            raise ValueError("EMBEDDING_MODEL is not set (ADR 0007 names the model)")
        return cls(model=model, query_prefix=env.get("EMBEDDING_QUERY_PREFIX") or "")


def query_text(query: str, prefix: str) -> str:
    """The text the model embeds for `query`: `<prefix> <query>`, or the query alone."""
    prefix = prefix.strip()
    return f"{prefix} {query}" if prefix else query


class QueryEmbedder(Protocol):
    def embed_query(self, query: str) -> list[float]:
        """One L2-normalised vector for the query. Raise `EmbeddingError` on failure."""
        ...


class SentenceTransformerEmbedder:
    """A sentence-transformers model, loaded on the first `embed_query`."""

    def __init__(self, config: EmbeddingConfig) -> None:
        self.config = config
        self._model: Any = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> SentenceTransformerEmbedder:
        return cls(EmbeddingConfig.from_env(env))

    def _load(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise EmbeddingError(
                    "sentence-transformers is not installed: "
                    "pip install -r agent/requirements-embed.txt"
                ) from exc
            try:
                self._model = SentenceTransformer(self.config.model, device=self.config.device)
            except Exception as exc:  # download or load failure: any library error
                raise EmbeddingError(f"could not load {self.config.model}: {exc}") from exc
        return self._model

    @property
    def dimension(self) -> int:
        return int(self._load().get_sentence_embedding_dimension())

    def embed_query(self, query: str) -> list[float]:
        vector = self._load().encode(
            query_text(query, self.config.query_prefix),
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [float(x) for x in vector]


_WORD = re.compile(r"[a-z0-9]+")


class FakeEmbedder:
    """Bag of hashed words, L2-normalised: texts sharing words get a positive cosine. Records the
    texts it embedded (after the prefix rule) in `calls`."""

    def __init__(self, dimension: int = 16, query_prefix: str = "") -> None:
        self.dimension = dimension
        self.query_prefix = query_prefix
        self.calls: list[str] = []

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for word in _WORD.findall(text.lower()):
            digest = hashlib.sha1(word.encode()).digest()
            vector[int.from_bytes(digest[:4], "big") % self.dimension] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_query(self, query: str) -> list[float]:
        text = query_text(query, self.query_prefix)
        self.calls.append(text)
        return self.embed(text)
