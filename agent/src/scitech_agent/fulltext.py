"""Full text of one arXiv paper, read on demand (ADR 0012).

The index holds titles and abstracts only (ADR 0003). When a question names a paper by its arXiv
id (`scitech_agent.intent`, reason `arxiv_id`) and `AGENT_FULLTEXT` is on, the agent asks
`FullTextReader` for passages of that paper's body that match the question:

1. `ArxivHtmlFetcher` downloads the paper's HTML rendering (LaTeXML), trying each URL template of
   `FULLTEXT_URLS` in turn (default: arxiv.org/html, then ar5iv for older papers). Nothing is
   written to disk; the parsed passages stay in a small in-memory cache (`FULLTEXT_CACHE`
   papers), so the text is read for the user's question, not stored or redistributed.
2. `parse_paper_html` keeps the title and the text of each section (paragraphs, figure and table
   captions; math as its TeX `alttext`) and drops the bibliography, navigation and scripts.
3. `split_passages` cuts each section into passages of at most `PASSAGE_WORDS` words, on
   paragraph boundaries when it can.
4. `rank_passages` orders them by cosine similarity to the question with the dense retriever's
   embedding model when there is one (`embed_passages`), else by word overlap. A question with no
   topic words ("explain 2302.00083") gets the first passage of each section instead, in order.

Every failure (network, HTTP status, no HTML version, empty text, timeout) raises
`FullTextUnavailable`; the agent then answers from the abstract as before and says so.
Manual check (needs network): `python -m scitech_agent.fulltext 2302.00083 "how is it trained?"`.
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from html.parser import HTMLParser
from typing import Any, Protocol

from scitech_agent.retrieval import ScoredChunk

logger = logging.getLogger(__name__)

DEFAULT_URLS = ("https://arxiv.org/html/{id}", "https://ar5iv.labs.arxiv.org/html/{id}")
USER_AGENT = (
    "scitech-rag-agent/1.0 (course project; https://github.com/Tdat10052499/scitech-rag-agent)"
)
PASSAGE_WORDS = 180
MAX_PASSAGES = 400  # per paper; a very long paper keeps its first sections
MIN_PARAGRAPH_WORDS = 5

_SKIP_TAGS = {"script", "style", "nav", "header", "footer", "annotation", "annotation-xml"}
_SKIP_CLASSES = (
    "ltx_bibliography",
    "ltx_page_footer",
    "ltx_page_header",
    "ltx_authors",
    "ltx_dates",
    "ltx_role_affiliation",
    "ltx_TOC",
    "ltx_note_outer",
)
_HEADINGS = {"h2", "h3", "h4"}
_BLOCKS = {"p", "figcaption", "li", "td", "th", "div"}
_VOID = {"br", "img", "hr", "meta", "link", "input", "col", "area", "base", "source", "wbr"}
_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "a an and are as at be by can could do does explain for from give how i in is it its me of on "
    "or paper please simple simply tell that the this to us was what when where which who why "
    "with words would you your arxiv about main idea summarize summary describe "
    "cho toi minh em ban la va cua bai nay ve gi trong".split()
)


class FullTextUnavailable(Exception):
    """The paper's full text could not be read; the agent falls back to the abstract."""


@dataclass(frozen=True)
class Section:
    heading: str
    paragraphs: tuple[str, ...]


@dataclass(frozen=True)
class Paper:
    arxiv_id: str
    title: str
    url: str
    sections: tuple[Section, ...]


class PassageEmbedder(Protocol):
    def embed_query(self, query: str) -> list[float]: ...

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...


# --- HTML --------------------------------------------------------------------------------------


class _PaperParser(HTMLParser):
    """Collects the document title and (heading, paragraphs) of a LaTeXML/ar5iv page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.sections: list[tuple[str, list[str]]] = [("", [])]
        self._stack: list[tuple[str, bool, str]] = []  # (tag, skipped, role)
        self._text: list[str] = []
        self._role = ""  # "heading", "doc_title" or "block" while collecting

    def _skipping(self) -> bool:
        return any(skipped for _, skipped, _ in self._stack)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _VOID:
            return
        values = dict(attrs)
        classes = values.get("class") or ""
        skipped = tag in _SKIP_TAGS or any(c in classes for c in _SKIP_CLASSES)
        role = ""
        if not self._skipping() and not skipped and not self._role:
            if tag == "h1" and "ltx_title" in classes:
                role = "doc_title"
            elif tag in _HEADINGS:
                role = "heading"
            elif tag in _BLOCKS and (tag != "div" or "ltx_para" in classes):
                role = "block"
            if role:
                self._role, self._text = role, []
        if tag == "math" and not self._skipping() and not skipped and self._role:
            tex = values.get("alttext")
            if tex:
                self._text.append(f" {tex} ")
            skipped = True  # the MathML inside repeats it
        self._stack.append((tag, skipped, role))

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID:
            return
        # Pop to the matching tag; HTMLParser does not repair unclosed elements.
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                closed = self._stack[i:]
                del self._stack[i:]
                for _, _, role in reversed(closed):
                    if role:
                        self._close(role)
                return

    def handle_data(self, data: str) -> None:
        if self._role and not self._skipping():
            self._text.append(data)

    def _close(self, role: str) -> None:
        text = " ".join("".join(self._text).split())
        self._role, self._text = "", []
        if not text:
            return
        if role == "doc_title":
            self.title = self.title or text
        elif role == "heading":
            self.sections.append((text, []))
        elif len(text.split()) >= MIN_PARAGRAPH_WORDS:
            self.sections[-1][1].append(text)


def parse_paper_html(html: str, arxiv_id: str, url: str) -> Paper:
    """The title and sections of an arXiv HTML page; raises `FullTextUnavailable` if empty."""
    parser = _PaperParser()
    parser.feed(html)
    parser.close()
    sections = tuple(
        Section(heading or "Front matter", tuple(paragraphs))
        for heading, paragraphs in parser.sections
        if paragraphs
    )
    if not sections:
        raise FullTextUnavailable(f"{arxiv_id}: no text found in {url}")
    return Paper(arxiv_id, parser.title, url, sections)


# --- Passages ----------------------------------------------------------------------------------


def split_passages(paper: Paper, max_words: int = PASSAGE_WORDS) -> list[ScoredChunk]:
    """Passages of at most `max_words` words, section by section; paragraphs are joined while
    they fit and a longer paragraph is cut into windows. Ids are `<arxiv id>#full-<n>`."""
    passages: list[tuple[str, str]] = []
    for section in paper.sections:
        current: list[str] = []
        for paragraph in section.paragraphs:
            words = paragraph.split()
            if current and len(current) + len(words) > max_words:
                passages.append((section.heading, " ".join(current)))
                current = []
            while len(words) > max_words:
                passages.append((section.heading, " ".join(words[:max_words])))
                words = words[max_words:]
            current.extend(words)
        if current:
            passages.append((section.heading, " ".join(current)))
    title = paper.title or paper.arxiv_id
    return [
        ScoredChunk(
            chunk_id=f"{paper.arxiv_id}#full-{n}",
            doc_id=paper.arxiv_id,
            score=0.0,
            title=f"{title} (full text, section: {heading})",
            text=text,
            source="arxiv",
            chunk_index=n,
            url=paper.url,
        )
        for n, (heading, text) in enumerate(passages[:MAX_PASSAGES])
    ]


def topic_words(query: str, arxiv_id: str) -> set[str]:
    """English content words of `query`. Words with Vietnamese (non-ASCII) letters are left out:
    the lexical match and the English embedding model cannot use them, so a question with no
    English topic word gets the overview (the start of each section)."""
    words = re.findall(r"\w+", query.lower().replace(arxiv_id, " "))
    return {w for w in words if w.isascii() and len(w) > 1 and w not in _STOP and not w.isdigit()}


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def rank_passages(
    query: str,
    arxiv_id: str,
    passages: Sequence[ScoredChunk],
    k: int,
    embedder: PassageEmbedder | None = None,
    vectors: Sequence[Sequence[float]] | None = None,
) -> list[ScoredChunk]:
    """The `k` passages that best match `query`, best first, with their score set. `vectors` are
    the passages' embeddings when an embedder is used (cached by the reader)."""
    if not passages or k <= 0:
        return []
    words = topic_words(query, arxiv_id)
    if not words:
        # "Explain this paper": the start of each section, in reading order.
        firsts: dict[str, ScoredChunk] = {}
        for passage in passages:
            firsts.setdefault(passage.title, passage)
        return [replace(p, score=1.0) for p in list(firsts.values())[:k]]
    if embedder is not None and vectors is not None:
        q = embedder.embed_query(query)
        scored = [(_cosine(q, v), p) for p, v in zip(passages, vectors, strict=True)]
    else:
        scored = [
            (len(words & set(_WORD.findall(f"{p.title} {p.text}".lower()))) / len(words), p)
            for p in passages
        ]
    scored.sort(key=lambda sp: (-sp[0], sp[1].chunk_index))
    return [replace(p, score=round(s, 4)) for s, p in scored[:k]]


# --- Fetching and cache ------------------------------------------------------------------------


class ArxivHtmlFetcher:
    """GET the paper's HTML from the first URL template that answers 200 with text. Requests are
    spaced at least `min_interval` seconds apart (arXiv asks for one request every 3 s)."""

    def __init__(
        self,
        urls: Sequence[str] = DEFAULT_URLS,
        timeout: float = 10.0,
        client: Any = None,
        min_interval: float = 3.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.urls = tuple(urls)
        self.timeout = timeout
        self._client = client
        self.min_interval = min_interval
        self.clock = clock
        self.sleep = sleep
        self._last: float | None = None
        self._pace = threading.Lock()

    def _wait_turn(self) -> None:
        with self._pace:
            now = self.clock()
            if self._last is not None and now - self._last < self.min_interval:
                self.sleep(self.min_interval - (now - self._last))
            self._last = self.clock()

    def _http(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            )
        return self._client

    def fetch(self, arxiv_id: str) -> Paper:
        errors = []
        for template in self.urls:
            url = template.format(id=arxiv_id)
            self._wait_turn()
            try:
                response = self._http().get(url)
            except Exception as exc:  # noqa: BLE001 - any transport error means "try the next"
                errors.append(f"{url}: {type(exc).__name__}")
                continue
            if response.status_code != 200 or "html" not in response.headers.get(
                "content-type", "html"
            ):
                errors.append(f"{url}: HTTP {response.status_code}")
                continue
            try:
                return parse_paper_html(response.text, arxiv_id, str(response.url))
            except FullTextUnavailable as exc:
                errors.append(str(exc))
        raise FullTextUnavailable(f"{arxiv_id}: " + "; ".join(errors))


class Fetcher(Protocol):
    def fetch(self, arxiv_id: str) -> Paper: ...


class FullTextReader:
    """Fetches, splits and (optionally) embeds a paper once, then ranks its passages per question.
    Thread-safe; keeps the latest `cache_size` papers in memory."""

    def __init__(
        self,
        fetcher: Fetcher,
        embedder: PassageEmbedder | None = None,
        cache_size: int = 32,
    ) -> None:
        self.fetcher = fetcher
        self.embedder = embedder
        self.cache_size = cache_size
        self._cache: OrderedDict[str, tuple[list[ScoredChunk], list[list[float]] | None]] = (
            OrderedDict()
        )
        self._lock = threading.Lock()

    def _load(self, arxiv_id: str) -> tuple[list[ScoredChunk], list[list[float]] | None, bool]:
        with self._lock:
            if arxiv_id in self._cache:
                self._cache.move_to_end(arxiv_id)
                passages, vectors = self._cache[arxiv_id]
                return passages, vectors, True
        passages = split_passages(self.fetcher.fetch(arxiv_id))
        vectors = None
        if self.embedder is not None:
            try:
                vectors = self.embedder.embed_passages([f"{p.title}. {p.text}" for p in passages])
            except Exception as exc:  # noqa: BLE001 - fall back to word overlap
                logger.warning("full text of %s not embedded: %s", arxiv_id, exc)
        with self._lock:
            self._cache[arxiv_id] = (passages, vectors)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
        return passages, vectors, False

    def passages(self, arxiv_id: str, query: str, k: int) -> tuple[list[ScoredChunk], bool]:
        """The `k` best passages for `query` and whether the paper came from the cache. Raises
        `FullTextUnavailable`."""
        passages, vectors, cached = self._load(arxiv_id)
        embedder = self.embedder if vectors is not None else None
        return rank_passages(query, arxiv_id, passages, k, embedder, vectors), cached


def embedder_of(retriever: Any) -> PassageEmbedder | None:
    """The dense retriever's embedding model, if it can embed passages (hybrid or dense)."""
    for candidate in (getattr(retriever, "dense", None), retriever):
        embedder = getattr(candidate, "embedder", None)
        if embedder is not None and callable(getattr(embedder, "embed_passages", None)):
            return embedder
    return None


def reader_from_env(retriever: Any = None, env: Mapping[str, str] | None = None) -> FullTextReader:
    """`FULLTEXT_URLS` (comma-separated templates with `{id}`), `FULLTEXT_TIMEOUT` seconds and
    `FULLTEXT_CACHE` papers (empty: arxiv.org/html then ar5iv, 10 and 32)."""
    env = os.environ if env is None else env
    urls = [u.strip() for u in (env.get("FULLTEXT_URLS") or "").split(",") if u.strip()]
    if any("{id}" not in u for u in urls):
        raise ValueError("FULLTEXT_URLS: every template needs {id}")
    timeout = float(env.get("FULLTEXT_TIMEOUT") or 10.0)
    cache = int(env.get("FULLTEXT_CACHE") or 32)
    if timeout <= 0 or cache <= 0:
        raise ValueError("FULLTEXT_TIMEOUT and FULLTEXT_CACHE must be > 0")
    return FullTextReader(
        ArxivHtmlFetcher(urls or DEFAULT_URLS, timeout), embedder_of(retriever), cache
    )


# --- Manual check ------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None, out: Callable[[str], None] = print) -> int:
    parser = argparse.ArgumentParser(description="Read one arXiv paper's full text (ADR 0012).")
    parser.add_argument("arxiv_id")
    parser.add_argument("question", nargs="?", default="")
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args(argv)
    reader = reader_from_env()
    try:
        passages, _ = reader.passages(args.arxiv_id, args.question, args.k)
    except FullTextUnavailable as exc:
        out(f"unavailable: {exc}")
        return 1
    count = len(reader._cache[args.arxiv_id][0])
    out(f"{args.arxiv_id}: {count} passages; best {len(passages)} for {args.question!r}:")
    for p in passages:
        out(f"\n[{p.score}] {p.title}\n{p.text[:400]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
