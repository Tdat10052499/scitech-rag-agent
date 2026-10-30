"""Retrieval interface of the agent (W2-D3-DAT-1).

`Retriever` is what the agent needs from any search backend: the vector store (W3), hybrid search
(W4) or a fake. `ScoredChunk` is one hit; its field names follow `docs/contracts/chunk.schema.json`,
and `chunk_id`, `doc_id`, `score` match `Hit` in `evaluation/` (W2-D4-LDN-1), so the evaluation
harness can wrap the same retriever. `InMemoryRetriever` is a deterministic fake for tests.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from functools import lru_cache
from typing import Any, Protocol

Filters = Mapping[str, Any]


class RetrievalError(Exception):
    """The search backend failed (index down, bad response). Contract code `retrieval_failed`."""

    code = "retrieval_failed"


@dataclass(frozen=True)
class ScoredChunk:
    """One retrieved chunk with its similarity score (higher is better)."""

    chunk_id: str
    doc_id: str
    score: float
    title: str
    text: str
    source: str  # required, as in chunk.schema.json: a store must map it, not default it
    chunk_index: int
    url: str | None = None
    published_at: str | None = None  # ISO date, as in chunk.schema.json
    categories: tuple[str, ...] = field(default_factory=tuple)
    license: str | None = None


class Retriever(Protocol):
    def search(self, query: str, k: int, filters: Filters | None = None) -> list[ScoredChunk]:
        """Return at most `k` chunks, best first. Raise on backend failure."""
        ...


def matches(chunk: ScoredChunk, filters: Filters | None) -> bool:
    """True if `chunk` has every filtered value; a list field (categories) must contain it.
    A `{"gte", "lte", "gt", "lt"}` mapping is a range checked with `check_range`'s rules, as in
    the vector store (`scitech_agent.store`). To test many chunks, use `compile_filters` once."""
    return compile_filters(filters)(chunk)


def compile_filters(filters: Filters | None) -> Callable[[Any], bool]:
    """Check `filters` and return a test for one chunk with the rules of `matches`. Bad bounds
    raise ValueError here, once, and the bounds are parsed once rather than for every chunk."""
    tests = [
        _range_test(name, wanted) if isinstance(wanted, Mapping) else _value_test(name, wanted)
        for name, wanted in (filters or {}).items()
    ]
    return lambda chunk: all(test(chunk) for test in tests)


def _value_test(name: str, wanted: Any) -> Callable[[Any], bool]:
    def test(chunk: Any) -> bool:
        value = getattr(chunk, name, None)
        if isinstance(value, (tuple, list)):
            return wanted in value
        return value == wanted

    return test


def year_range(start: int | None = None, end: int | None = None) -> dict[str, dict[str, str]]:
    """Filter on `published_at` for the years `start` to `end`, both included; either may be
    None (open end). Combine it with other filters: `{**year_range(2020, 2024), "categories":
    "cs.CL"}`. The upper bound is `lt` the next 1 January, so a datetime late on 31 December
    still matches."""
    if start is None and end is None:
        raise ValueError("year_range needs a start year, an end year or both")
    if start is not None and end is not None and start > end:
        raise ValueError(f"year_range: start {start} is after end {end}")
    bounds = {}
    if start is not None:
        bounds["gte"] = f"{start:04d}-01-01"
    if end is not None:
        bounds["lt"] = f"{end + 1:04d}-01-01"
    return {"published_at": bounds}


RANGE_OPS = ("gte", "lte", "gt", "lt")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def check_range(name: str, bounds: Mapping[str, Any]) -> None:
    """Raise ValueError unless `bounds` is a range Qdrant accepts: keys among gte, lte, gt, lt,
    and every bound a number, or every bound an ISO date or datetime string (`2024-01-01`,
    `2024-01-01T00:00:00Z`). A bare year such as `"2024"` is refused: Qdrant rejects it (HTTP
    400), and comparing it as a string would silently drop dates; use `year_range`. Numbers and
    dates in one range are refused too: no value can match both."""
    unknown = set(bounds) - set(RANGE_OPS)
    if unknown or not bounds:
        raise ValueError(f"filter {name!r}: a range takes gte, lte, gt or lt, got {sorted(bounds)}")
    kinds = set()
    for op, bound in bounds.items():
        if _number(bound) is not None:
            kinds.add("number")
        elif _datetime(bound) is not None:
            kinds.add("date")
        else:
            raise ValueError(
                f"filter {name!r}: {op} bound {bound!r} is not a number or an ISO date "
                "(YYYY-MM-DD or RFC 3339); for whole years use year_range"
            )
    if len(kinds) > 1:
        raise ValueError(
            f"filter {name!r}: a range mixes numbers and dates ({dict(bounds)}); use one kind"
        )


def _range_test(name: str, bounds: Mapping[str, Any]) -> Callable[[Any], bool]:
    """Numbers compare as numbers; dates and datetimes as UTC instants, like Qdrant's datetime
    index (a date is midnight UTC, so `gte "2024-01-01T00:00:00Z"` keeps `2024-01-01`). A value
    of another kind than its bounds, or none, never matches."""
    check_range(name, bounds)
    numeric = _number(next(iter(bounds.values()))) is not None
    convert = _number if numeric else _datetime
    limits = [(_COMPARE[op], convert(bound)) for op, bound in bounds.items()]

    def test(chunk: Any) -> bool:
        value = getattr(chunk, name, None)
        left = None if value is None else convert(value)
        return left is not None and all(compare(left, right) for compare, right in limits)

    return test


_COMPARE = {
    "gte": lambda a, b: a >= b,
    "lte": lambda a, b: a <= b,
    "gt": lambda a, b: a > b,
    "lt": lambda a, b: a < b,
}


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _datetime(value: Any) -> datetime | None:
    """A date, datetime or ISO string as an aware datetime (naive means UTC), else None."""
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, date):
        moment = datetime(value.year, value.month, value.day)
    elif isinstance(value, str):
        return _parse_iso(value)
    else:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


@lru_cache(maxsize=65536)  # chunks share dates: a corpus has a few thousand distinct values
def _parse_iso(value: str) -> datetime | None:
    if not _ISO_DATE.match(value):
        return None
    text = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


_WORD = re.compile(r"[a-z0-9]+")


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


class InMemoryRetriever:
    """Fake retriever over a fixed list of chunks. The score is the share of query words found
    in the chunk's title and text (0 to 1); chunks sharing no word with the query are not hits.
    Ties are broken by `chunk_id`, so results are deterministic."""

    def __init__(self, chunks: Iterable[ScoredChunk]) -> None:
        self.chunks: Sequence[ScoredChunk] = list(chunks)
        self.calls: list[tuple[str, int, Filters | None]] = []

    def search(self, query: str, k: int, filters: Filters | None = None) -> list[ScoredChunk]:
        if k <= 0:
            raise ValueError(f"k must be positive, got {k}")
        self.calls.append((query, k, filters))
        terms = _words(query)
        keep = compile_filters(filters)
        hits = []
        for chunk in self.chunks:
            if not keep(chunk) or not terms:
                continue
            overlap = len(terms & _words(f"{chunk.title} {chunk.text}"))
            if overlap:
                hits.append(replace(chunk, score=round(overlap / len(terms), 4)))
        hits.sort(key=lambda c: (-c.score, c.chunk_id))
        return hits[:k]
