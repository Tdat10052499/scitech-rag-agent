"""Search plans for paper-finding questions (follow-up of the Space test of 2026-11-03).

The agent was built for questions answered by the content of abstracts. Questions such as "list
the newest 2026 papers on LLMs" or "explain 2302.00083 simply" need the metadata of the chunks
(publication date, arXiv id), which retrieval did not use and the answer prompt did not show, so
the LLM refused. `plan_search` reads the message (and the rewritten query) with fixed patterns, no
LLM call, and returns a `SearchPlan`:

- `arxiv_id`: an arXiv id such as `2302.00083` (also `arXiv:2302.00083v2`) restricts retrieval to
  that paper, one search per id (at most `MAX_IDS`), so "explain this paper" sees only it;
- `year`: a year with a temporal word ("in 2026", "năm 2026", "since 2023", "2020-2024", or any
  year in a paper-finding question) filters `published_at` with `retrieval.year_range`;
- `recent`: "latest", "newest", "most recent", "mới nhất", "gần đây" keep the last `RECENT_DAYS`
  days before today;
- `list`: a request to find, list or recommend papers ("find 5 to 10 papers", "liệt kê các bài
  báo") retrieves `list_top_k` chunks (or the number asked, at most `list_top_k`) and asks the
  answer prompt for a list (`prompts/answer_papers.md`).

A question without any of these gets the empty plan, and the agent then behaves exactly as before
(same search, same prompts), so evaluation runs on the golden set are unchanged: no golden
question matches (`tests/test_intent.py` checks it). When a filtered search finds nothing, the
agent searches again without filters (`SearchPlan.fallback`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from scitech_agent.retrieval import Filters, year_range

RECENT_DAYS = 365
MAX_IDS = 5
FIRST_YEAR = 1990  # arXiv starts in 1991; earlier four-digit numbers are not years here

_ARXIV_ID = re.compile(r"(?<![\w.])(?:arxiv:\s*)?(\d{4}\.\d{4,5})(?:v\d+)?(?![\w.])", re.I)

_YEAR = r"((?:19|20)\d{2})"
_RANGE = re.compile(rf"\b{_YEAR}\s*(?:-|–|to|and|until|đến|tới|và)\s*{_YEAR}\b", re.I)
_SINCE = re.compile(rf"\b(?:since|from|từ|kể\s+từ)\s+(?:năm\s+)?{_YEAR}\b", re.I)
_AFTER = re.compile(rf"\b(?:after|sau)\s+(?:năm\s+)?{_YEAR}\b", re.I)
_BEFORE = re.compile(rf"\b(?:before|trước)\s+(?:năm\s+)?{_YEAR}\b", re.I)
_IN = re.compile(
    rf"\b(?:in|during|of|published\s+in|năm|vào\s+năm|trong\s+năm|vào|trong)\s+(?:năm\s+)?{_YEAR}\b",
    re.I,
)
_BARE_YEAR = re.compile(rf"\b{_YEAR}\b")

_RECENT = re.compile(
    r"\b(?:latest|newest|most\s+recent|recently\s+published|mới\s+nhất|gần\s+đây(?:\s+nhất)?"
    r"|mới\s+đây)\b",
    re.I,
)

_PAPERS = (
    r"(?:papers?|articles?|publications?|preprints?|studies|references|sources|"
    r"bài\s+(?:báo|viết|nghiên\s+cứu)|bài|công\s+trình|tài\s+liệu|nguồn|nghiên\s+cứu)"
)
_LIST_VERB = (
    r"(?:list|find|show|give|recommend|suggest|search\s+for|look\s+for|collect|gather|name|"
    r"liệt\s+kê|tìm(?!\s+hiểu)|đưa\s+ra|gợi\s+ý|giới\s+thiệu|kể\s+tên|cho\s+(?:tôi|mình|em))"
)
_LIST = re.compile(
    "|".join(
        [
            rf"\b{_LIST_VERB}\b[^.?!\n]{{0,60}}?\b{_PAPERS}\b",
            r"\b(?:which|what)\s+(?:\w+\s+){0,2}(?:papers|articles|publications|studies)\b",
            rf"\bnhững\s+{_PAPERS}\b",
        ]
    ),
    re.I,
)
_COUNT = re.compile(
    rf"\b(\d{{1,2}})\s*(?:(?:-|–|to|or|đến|tới|hoặc)\s*(\d{{1,2}})\s*)?(?:\w+\s+){{0,2}}{_PAPERS}\b",
    re.I,
)


@dataclass(frozen=True)
class SearchPlan:
    """How to search for one message. The empty plan (no `reasons`) is the default search."""

    reasons: tuple[str, ...] = ()  # "arxiv_id", "year", "recent", "list"
    filters: dict[str, Any] | None = None
    arxiv_ids: tuple[str, ...] = ()
    k: int | None = None  # None: AgentConfig.top_k
    list_papers: bool = False
    fallback: bool = field(default=False, compare=False)  # filtered search was empty

    @property
    def active(self) -> bool:
        return bool(self.reasons)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reasons": list(self.reasons),
            "filters": self.filters,
            "arxiv_ids": list(self.arxiv_ids),
            "k": self.k,
            "list_papers": self.list_papers,
            "fallback": self.fallback,
        }


def arxiv_ids(text: str) -> tuple[str, ...]:
    """arXiv ids (new style, `YYMM.NNNNN`) in order of first mention, version dropped."""
    seen: dict[str, None] = {}
    for match in _ARXIV_ID.finditer(text):
        seen.setdefault(match.group(1), None)
    return tuple(seen)[:MAX_IDS]


def wants_papers(text: str) -> bool:
    """True when the text asks to find, list or recommend papers."""
    return _LIST.search(text) is not None


def paper_count(text: str) -> int | None:
    """The number of papers asked for ("5 to 10 papers": 10), else None."""
    match = _COUNT.search(text)
    if match is None:
        return None
    numbers = [int(n) for n in match.groups() if n]
    return max(numbers) if numbers and max(numbers) > 0 else None


def years(text: str, today: date, papers: bool) -> tuple[int | None, int | None] | None:
    """(start, end) years of the period the text asks about, either may be None; None if none.
    A bare year counts only in a paper-finding question; "BERT (2018)" alone is no filter."""

    def ok(year: str) -> bool:
        return FIRST_YEAR <= int(year) <= today.year + 1

    if (m := _RANGE.search(text)) and ok(m.group(1)) and ok(m.group(2)):
        start, end = sorted((int(m.group(1)), int(m.group(2))))
        return start, end
    if (m := _SINCE.search(text)) and ok(m.group(1)):
        return int(m.group(1)), None
    if (m := _AFTER.search(text)) and ok(m.group(1)):
        return int(m.group(1)) + 1, None
    if (m := _BEFORE.search(text)) and ok(m.group(1)):
        return None, int(m.group(1)) - 1
    if (m := _IN.search(text)) and ok(m.group(1)):
        return int(m.group(1)), int(m.group(1))
    if papers:
        found = [int(y) for y in _BARE_YEAR.findall(text) if ok(y)]
        if found:
            return min(found), max(found)
    return None


def plan_search(
    message: str, query: str, today: date, *, top_k: int, list_top_k: int
) -> SearchPlan:
    """The `SearchPlan` for `message` and its search `query` (the rewrite, or the message)."""
    text = message if query == message else f"{message}\n{query}"
    reasons: list[str] = []
    ids = arxiv_ids(text)
    if ids:
        # One paper (or a few) named by id: its own chunks only, whatever else the text says.
        return SearchPlan(reasons=("arxiv_id",), arxiv_ids=ids, k=top_k)

    papers = wants_papers(text)
    filters: Filters = {}
    period = years(text, today, papers)
    if period is not None:
        filters = year_range(*period)
        reasons.append("year")
    elif _RECENT.search(text):
        filters = {"published_at": {"gte": (today - timedelta(days=RECENT_DAYS)).isoformat()}}
        reasons.append("recent")
    k = None
    if papers:
        reasons.append("list")
        asked = paper_count(text)
        k = min(asked, list_top_k) if asked else list_top_k
        k = max(k, top_k)
    if not reasons:
        return SearchPlan()
    return SearchPlan(
        reasons=tuple(reasons), filters=dict(filters) or None, k=k, list_papers=papers
    )
