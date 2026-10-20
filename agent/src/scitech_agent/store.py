"""Qdrant vector store (W3-D1-DAT-1): create the collection, upsert points, count, search.

`QdrantStore` talks to Qdrant's REST API with `httpx` (already an agent dependency), so there is no
client SDK to install and tests can use `httpx.MockTransport`. The image version is pinned in
`docker-compose.yml`. Configuration: `QDRANT_URL` and `QDRANT_COLLECTION` (`.env.example`).

- `ensure_collection(dimension)`: creates the collection (cosine distance) if it is missing, fails
  if it exists with another dimension or distance, then makes sure the payload indexes exist:
  keyword on `source`, `categories`, `doc_id`, datetime on `published_at`. The dimension comes from
  the embedding run (`embed`'s state, ADR 0007), so the store cannot drift from the vectors.
- `upsert(points)`: inserts or replaces points in batches (`batch_size`, default 256); a point is
  anything with `id`, `vector` and `payload` (`Point` here, or the loader's own type). Payload
  fields follow `docs/contracts/chunk.schema.json`.
- `count()`: exact number of points. `search(vector, k, filters)`: the `k` nearest points as
  `ScoredChunk`s, best first; the score is Qdrant's cosine similarity.

This is the `VectorStore` that the loader (W3-D3-FAO-1) needs, and the backend of the dense
retriever (W3-D2-DAT-1). Every failure raises `StoreError`, a `RetrievalError`, so the agent
reports it as `retrieval_failed`.

Filters are the same as for every `Retriever`: `{"field": value}` keeps points whose field equals
the value or, for a list field such as `categories`, contains it; `{"field": {"gte": a, "lte": b}}`
is an inclusive range (`gt`/`lt` for exclusive), e.g. on `published_at` with ISO dates.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from scitech_agent.retrieval import Filters, RetrievalError, ScoredChunk

DISTANCE = "Cosine"
DEFAULT_BATCH_SIZE = 256
# Payload indexes made by `ensure_collection`. `doc_id` is not needed for search; it makes the
# delete of a reloaded paper's old points by `doc_id` (ADR 0008, W5-D2-FAO-1) cheap.
PAYLOAD_INDEXES = {
    "source": "keyword",
    "categories": "keyword",
    "doc_id": "keyword",
    "published_at": "datetime",
}
RANGE_KEYS = frozenset({"gte", "lte", "gt", "lt"})
# Payload fields that `ScoredChunk` needs (required in chunk.schema.json).
REQUIRED_FIELDS = ("chunk_id", "doc_id", "title", "text", "source", "chunk_index")


class StoreError(RetrievalError):
    """Qdrant failed or answered something unexpected (down, HTTP error, bad payload)."""


@dataclass(frozen=True)
class StoreConfig:
    url: str = "http://localhost:6333"
    collection: str = "scitech_chunks"
    timeout: float = 30.0  # seconds per request

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> StoreConfig:
        """Read `QDRANT_URL` and `QDRANT_COLLECTION` (empty: the defaults above)."""
        env = os.environ if env is None else env
        return cls(
            url=(env.get("QDRANT_URL") or cls.url).rstrip("/"),
            collection=env.get("QDRANT_COLLECTION") or cls.collection,
        )


class PointLike(Protocol):
    id: str | int  # unsigned integer or UUID, as Qdrant requires
    vector: Sequence[float]
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class Point:
    id: str | int
    vector: Sequence[float]
    payload: Mapping[str, Any] = field(default_factory=dict)


def to_qdrant_filter(filters: Filters | None) -> dict[str, Any] | None:
    """Translate retriever filters into a Qdrant filter (all conditions must hold)."""
    if not filters:
        return None
    must = []
    for name, wanted in filters.items():
        if isinstance(wanted, Mapping):
            unknown = set(wanted) - RANGE_KEYS
            if unknown or not wanted:
                raise ValueError(
                    f"filter {name!r}: a range takes gte, lte, gt or lt, got {sorted(wanted)}"
                )
            must.append({"key": name, "range": dict(wanted)})
        elif isinstance(wanted, (str, int, bool)):
            must.append({"key": name, "match": {"value": wanted}})
        else:
            raise ValueError(f"filter {name!r}: unsupported value {wanted!r}")
    return {"must": must}


def to_scored_chunk(payload: Mapping[str, Any], score: float) -> ScoredChunk:
    """Map a point's payload (chunk.schema.json fields) to a `ScoredChunk`."""
    missing = [name for name in REQUIRED_FIELDS if payload.get(name) is None]
    if missing:
        raise StoreError(f"point {payload.get('chunk_id')!r} has no {', '.join(missing)}")
    return ScoredChunk(
        chunk_id=payload["chunk_id"],
        doc_id=payload["doc_id"],
        score=float(score),
        title=payload["title"],
        text=payload["text"],
        source=payload["source"],
        chunk_index=int(payload["chunk_index"]),
        url=payload.get("url"),
        published_at=payload.get("published_at"),
        categories=tuple(payload.get("categories") or ()),
        license=payload.get("license"),
    )


def _batches(points: Iterable[PointLike], size: int) -> Iterator[list[PointLike]]:
    batch: list[PointLike] = []
    for point in points:
        batch.append(point)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


class QdrantStore:
    """One Qdrant collection, through the REST API."""

    def __init__(
        self,
        config: StoreConfig | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config or StoreConfig()
        self._http = httpx.Client(
            base_url=self.config.url, timeout=self.config.timeout, transport=transport
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> QdrantStore:
        return cls(StoreConfig.from_env(env))

    @property
    def collection(self) -> str:
        return self.config.collection

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> QdrantStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- HTTP -----------------------------------------------------------------------------------

    def _request(
        self, method: str, path: str, *, json: Any = None, allow_404: bool = False
    ) -> dict[str, Any] | None:
        try:
            response = self._http.request(method, path, json=json)
        except httpx.HTTPError as exc:
            raise StoreError(f"Qdrant at {self.config.url} is not reachable: {exc}") from exc
        if allow_404 and response.status_code == 404:
            return None
        if response.is_error:
            raise StoreError(
                f"Qdrant {method} {path} failed with HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise StoreError(f"Qdrant {method} {path} returned no JSON") from exc

    def _path(self, suffix: str = "") -> str:
        return f"/collections/{self.collection}{suffix}"

    # --- Collection -----------------------------------------------------------------------------

    def ensure_collection(self, dimension: int) -> bool:
        """Create the collection if it is missing and make sure its payload indexes exist.
        Return True if it was created. Fail if it exists with another dimension or distance."""
        if dimension < 1:
            raise ValueError(f"dimension must be >= 1, got {dimension}")
        info = self._request("GET", self._path(), allow_404=True)
        created = info is None
        if created:
            self._request(
                "PUT",
                self._path(),
                json={"vectors": {"size": dimension, "distance": DISTANCE}},
            )
        else:
            vectors = info["result"]["config"]["params"]["vectors"]
            size, distance = vectors.get("size"), vectors.get("distance")
            if size != dimension or distance != DISTANCE:
                raise StoreError(
                    f"collection {self.collection} has {size} dimensions ({distance}), "
                    f"expected {dimension} ({DISTANCE}); use another QDRANT_COLLECTION or "
                    "delete the collection first"
                )
        for name, schema in PAYLOAD_INDEXES.items():  # creating an existing index is a no-op
            self._request(
                "PUT",
                self._path("/index?wait=true"),
                json={"field_name": name, "field_schema": schema},
            )
        return created

    def delete_collection(self) -> None:
        """Delete the collection and all its points (no error if it does not exist)."""
        self._request("DELETE", self._path(), allow_404=True)

    # --- Points ---------------------------------------------------------------------------------

    def upsert(self, points: Iterable[PointLike], *, batch_size: int = DEFAULT_BATCH_SIZE) -> int:
        """Insert or replace `points` (same id: replaced) in batches; return how many."""
        if batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {batch_size}")
        total = 0
        for batch in _batches(points, batch_size):
            body = {
                "points": [
                    {
                        "id": p.id,
                        "vector": [float(x) for x in p.vector],
                        "payload": dict(p.payload),
                    }
                    for p in batch
                ]
            }
            self._request("PUT", self._path("/points?wait=true"), json=body)
            total += len(batch)
        return total

    def count(self, filters: Filters | None = None) -> int:
        """Exact number of points (matching `filters`, if given)."""
        body: dict[str, Any] = {"exact": True}
        qdrant_filter = to_qdrant_filter(filters)
        if qdrant_filter:
            body["filter"] = qdrant_filter
        data = self._request("POST", self._path("/points/count"), json=body)
        return int(data["result"]["count"])

    def search(
        self, vector: Sequence[float], k: int, filters: Filters | None = None
    ) -> list[ScoredChunk]:
        """The `k` points nearest to `vector` that match `filters`, best first."""
        if k <= 0:
            raise ValueError(f"k must be positive, got {k}")
        body: dict[str, Any] = {
            "query": [float(x) for x in vector],
            "limit": k,
            "with_payload": True,
        }
        qdrant_filter = to_qdrant_filter(filters)
        if qdrant_filter:
            body["filter"] = qdrant_filter
        data = self._request("POST", self._path("/points/query"), json=body)
        try:
            hits = data["result"]["points"]
        except (KeyError, TypeError) as exc:
            raise StoreError("Qdrant query returned no points list") from exc
        return [to_scored_chunk(hit.get("payload") or {}, hit["score"]) for hit in hits]
