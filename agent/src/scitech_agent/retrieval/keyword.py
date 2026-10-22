"""Keyword (BM25) retriever (W3-D3-DAT-1).

`build_index` reads `chunks.parquet` (the output of `chunk`, fields of
`docs/contracts/chunk.schema.json`) and builds an Okapi BM25 index over each chunk's `text`;
`save`/`BM25Index.load` keep it in `data/index/bm25/`. `KeywordRetriever` implements `Retriever`
on a loaded index. The scoring is written here with numpy (about 100 lines) rather than taken from
a BM25 package: the index is a term -> postings table with the BM25 weight of every (term, chunk)
pair precomputed, so a query adds a few postings lists and sorts the non-zero scores.

- Tokens: lowercase runs of letters and digits (`[a-z0-9]+`, the same rule as the in-memory fake),
  minus an optional English stop-word list (on by default).
- Score: sum over query tokens of idf(t) * tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avgdl)),
  with the non-negative idf ln(1 + (N - df + 0.5) / (df + 0.5)) (Lucene's). `k1` 1.2, `b` 0.75.
  Scores are not on the cosine scale of the dense retriever, so `RETRIEVAL_MIN_SCORE` does not
  carry over; hybrid retrieval (W3-D4-DAT-1) fuses ranks, not scores.
- Filters: the `Retriever` rules (`retrieval.matches`), applied to the scored chunks in rank order.
- Files in the index directory: `postings.npz` (CSR arrays), `vocabulary.json`, `chunks.parquet`
  (the chunk fields a `ScoredChunk` needs, in index order) and `_bm25_manifest.json` (parameters,
  counts, source chunks, build seconds and peak memory).
- Memory: the whole index lives in RAM once loaded (postings, vocabulary and the chunk texts).

Build and check from the repository root (needs the chunks of `chunk`):
    PYTHONPATH=agent/src python -m scitech_agent.retrieval.keyword build \
        --chunks data/processed/chunks --out data/index/bm25
    PYTHONPATH=agent/src python -m scitech_agent.retrieval.keyword search \
        --index data/index/bm25 "dense passage retrieval" -k 5
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import tracemalloc
from array import array
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from scitech_agent.retrieval import Filters, ScoredChunk, matches

CHUNK_FILE = "chunks.parquet"  # input name, as written by `chunk` (pipelines)
CHUNK_MANIFEST = "_chunk_manifest.json"
POSTINGS = "postings.npz"
VOCABULARY = "vocabulary.json"
META = "chunks.parquet"
MANIFEST = "_bm25_manifest.json"
# Chunk fields kept next to the index to build `ScoredChunk`s (no `authors`, no vectors).
META_FIELDS = (
    "chunk_id",
    "doc_id",
    "source",
    "title",
    "text",
    "chunk_index",
    "categories",
    "published_at",
    "url",
    "license",
)

_TOKEN = re.compile(r"[a-z0-9]+")
# A short English list (articles, pronouns, auxiliaries, prepositions, conjunctions). Domain words
# such as "model", "language" or "learning" are kept: in cs.CL abstracts they carry meaning.
STOP_WORDS = frozenset(
    """a about above after again against all also am an and any are as at be been before being
    below between both but by can could did do does doing down during each few for from further
    had has have having he her here hers herself him himself his how i if in into is it its itself
    just me more most my myself no nor not of off on once only or other our ours ourselves out over
    own same she should so some such than that the their theirs them themselves then there these
    they this those through to too under until up very was we were what when where which while who
    whom why will with would you your yours yourself yourselves""".split()
)


def tokenize(text: str, stop_words: frozenset[str] | None = STOP_WORDS) -> list[str]:
    tokens = _TOKEN.findall(text.lower())
    return [t for t in tokens if t not in stop_words] if stop_words else tokens


@dataclass(frozen=True)
class BM25Params:
    k1: float = 1.2
    b: float = 0.75
    stop_words: bool = True


class BM25Index:
    """Postings in CSR form: the chunks containing term `t` are `doc_ids[indptr[t]:indptr[t+1]]`,
    with their BM25 weights in `weights` at the same positions."""

    def __init__(
        self,
        vocabulary: Mapping[str, int],
        indptr: np.ndarray,
        doc_ids: np.ndarray,
        weights: np.ndarray,
        chunks: Any,
        params: BM25Params,
        manifest: Mapping[str, Any] | None = None,
    ) -> None:
        if len(indptr) != len(vocabulary) + 1 or len(doc_ids) != len(weights):
            raise ValueError("inconsistent BM25 index arrays")
        self.vocabulary = dict(vocabulary)
        self.indptr = indptr
        self.doc_ids = doc_ids
        self.weights = weights
        import pyarrow as pa

        # Chunk fields stay in Arrow columns: Python objects for 122k texts would take several
        # times the memory. A row is converted only when it is a candidate hit.
        table = chunks if isinstance(chunks, pa.Table) else pa.Table.from_pylist(list(chunks))
        self.chunks = table
        self._columns = {name: table.column(name).combine_chunks() for name in table.column_names}
        self._lists: dict[str, list[Any]] = {}
        self.params = params
        self.manifest = dict(manifest or {})

    def __len__(self) -> int:
        return self.chunks.num_rows

    def scores(self, query: str) -> np.ndarray:
        """BM25 score of every chunk for `query` (float32, zero for chunks sharing no token)."""
        scores = np.zeros(len(self), dtype=np.float32)
        stop_words = STOP_WORDS if self.params.stop_words else None
        for term, count in Counter(tokenize(query, stop_words)).items():
            t = self.vocabulary.get(term)
            if t is None:
                continue
            start, end = self.indptr[t], self.indptr[t + 1]
            scores[self.doc_ids[start:end]] += count * self.weights[start:end]
        return scores

    def chunk(self, i: int, score: float) -> ScoredChunk:
        row = {name: column[i].as_py() for name, column in self._columns.items()}
        return ScoredChunk(
            chunk_id=row["chunk_id"],
            doc_id=row["doc_id"],
            score=round(float(score), 4),
            title=row["title"],
            text=row["text"],
            source=row["source"],
            chunk_index=int(row["chunk_index"]),
            url=row.get("url"),
            published_at=row.get("published_at"),
            categories=tuple(row.get("categories") or ()),
            license=row.get("license"),
        )

    def search(self, query: str, k: int, filters: Filters | None = None) -> list[ScoredChunk]:
        if k <= 0:
            raise ValueError(f"k must be positive, got {k}")
        scores = self.scores(query)
        hits = np.flatnonzero(scores > 0)
        # Best first; ties in index order (chunks are sorted by doc_id, chunk_index).
        hits = hits[np.lexsort((hits, -scores[hits]))]
        if filters:
            hits = list(islice((i for i in hits if self._matches(int(i), filters)), k))
        return [self.chunk(int(i), scores[i]) for i in hits[:k]]

    def _matches(self, i: int, filters: Filters) -> bool:
        """`retrieval.matches` on the filtered fields of row `i` only (no full row conversion)."""
        row = SimpleNamespace(**{name: self._values(name)[i] for name in filters})
        return matches(row, filters)  # type: ignore[arg-type]

    def _values(self, name: str) -> list[Any]:
        """A filterable column as a Python list, converted on first use and kept."""
        if name not in self._lists:
            column = self._columns.get(name)
            if column is None:
                self._lists[name] = [None] * len(self)
            else:
                values = column.to_pylist()
                self._lists[name] = [tuple(v) if isinstance(v, list) else v for v in values]
        return self._lists[name]

    # --- Files ----------------------------------------------------------------------------------

    def save(self, out: Path) -> None:
        import pyarrow.parquet as pq

        out.mkdir(parents=True, exist_ok=True)
        np.savez(out / POSTINGS, indptr=self.indptr, doc_ids=self.doc_ids, weights=self.weights)
        terms = sorted(self.vocabulary, key=self.vocabulary.__getitem__)
        (out / VOCABULARY).write_text(json.dumps(terms), encoding="utf-8")
        pq.write_table(self.chunks, out / META)
        manifest = dict(self.manifest, params=vars(self.params))
        (out / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> BM25Index:
        import pyarrow.parquet as pq

        for name in (POSTINGS, VOCABULARY, META, MANIFEST):
            if not (path / name).is_file():
                raise FileNotFoundError(f"{path / name} not found (build the index first)")
        manifest = json.loads((path / MANIFEST).read_text(encoding="utf-8"))
        terms = json.loads((path / VOCABULARY).read_text(encoding="utf-8"))
        arrays = np.load(path / POSTINGS)
        return cls(
            {term: i for i, term in enumerate(terms)},
            arrays["indptr"],
            arrays["doc_ids"],
            arrays["weights"],
            pq.read_table(path / META),
            BM25Params(**manifest["params"]),
            manifest,
        )


def index_chunks(
    chunks: Iterable[Mapping[str, Any]], params: BM25Params | None = None
) -> BM25Index:
    """Build the index in memory from chunk records (fields of chunk.schema.json)."""
    params = params or BM25Params()
    stop_words = STOP_WORDS if params.stop_words else None
    vocabulary: dict[str, int] = {}
    terms, docs, tfs = array("i"), array("i"), array("f")
    lengths = array("i")
    meta: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks):
        tokens = tokenize(chunk["text"], stop_words)
        lengths.append(len(tokens))
        for term, tf in Counter(tokens).items():
            terms.append(vocabulary.setdefault(term, len(vocabulary)))
            docs.append(i)
            tfs.append(tf)
        meta.append({name: chunk.get(name) for name in META_FIELDS})
    if not meta:
        raise ValueError("no chunks to index")

    n = len(meta)
    term_ids = np.frombuffer(terms, dtype=np.int32)
    doc_ids = np.frombuffer(docs, dtype=np.int32)
    tf = np.frombuffer(tfs, dtype=np.float32)
    dl = np.frombuffer(lengths, dtype=np.int32).astype(np.float32)
    avgdl = float(dl.mean()) or 1.0
    df = np.bincount(term_ids, minlength=len(vocabulary)).astype(np.float64)
    idf = np.log1p((n - df + 0.5) / (df + 0.5)).astype(np.float32)
    norm = params.k1 * (1.0 - params.b + params.b * dl[doc_ids] / avgdl)
    weights = idf[term_ids] * tf * (params.k1 + 1.0) / (tf + norm)

    order = np.argsort(term_ids, kind="stable")  # postings of a term stay in chunk order
    indptr = np.zeros(len(vocabulary) + 1, dtype=np.int64)
    np.cumsum(np.bincount(term_ids, minlength=len(vocabulary)), out=indptr[1:])
    manifest = {
        "step": "bm25",
        "counts": {
            "chunks": n,
            "terms": len(vocabulary),
            "postings": int(len(term_ids)),
            "avg_tokens": round(avgdl, 1),
        },
    }
    return BM25Index(
        vocabulary,
        indptr,
        doc_ids[order].copy(),
        weights[order].astype(np.float32),
        meta,
        params,
        manifest,
    )


def read_chunks(chunks_dir: Path) -> Iterator[dict[str, Any]]:
    """Chunk records of `<chunks_dir>/chunks.parquet`, in file order, a batch at a time."""
    import pyarrow.parquet as pq

    path = chunks_dir / CHUNK_FILE
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found (run `chunk` first)")
    for batch in pq.ParquetFile(path).iter_batches(batch_size=10_000, columns=list(META_FIELDS)):
        yield from batch.to_pylist()


def _peak_rss_mb() -> float | None:
    """Peak resident memory of this process so far (Linux, macOS, WSL2); None on Windows."""
    try:
        import resource
    except ImportError:
        return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (2**20 if sys.platform == "darwin" else 2**10), 1)  # bytes vs KiB


def build_index(
    chunks_dir: Path,
    out: Path,
    params: BM25Params | None = None,
    *,
    trace_memory: bool = False,
) -> dict[str, Any]:
    """Build the index from `chunks.parquet`, save it to `out` and return its manifest, with
    build seconds and peak memory: the process's peak RSS where the OS reports it, and with
    `trace_memory` also the peak of Python and numpy allocations (tracemalloc, which works on
    Windows too but makes the build several times slower, so its seconds are not comparable)."""
    if trace_memory:
        tracemalloc.start()
    started = time.monotonic()
    try:
        index = index_chunks(read_chunks(chunks_dir), params)
        build_seconds = time.monotonic() - started
        traced = tracemalloc.get_traced_memory()[1] if trace_memory else None
    finally:
        if trace_memory:
            tracemalloc.stop()
    source = chunks_dir / CHUNK_MANIFEST
    chunk_manifest = json.loads(source.read_text(encoding="utf-8")) if source.is_file() else {}
    index.manifest.update(
        {
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "chunks": str(chunks_dir),
            "chunked_at": chunk_manifest.get("chunked_at"),
            "build_seconds": round(build_seconds, 1),
            "peak_rss_mb": _peak_rss_mb(),
            "peak_traced_mb": round(traced / 2**20, 1) if traced is not None else None,
            "traced": trace_memory,
        }
    )
    index.save(out)
    files = (POSTINGS, VOCABULARY, META, MANIFEST)
    index.manifest["index_mb"] = round(sum((out / f).stat().st_size for f in files) / 2**20, 1)
    (out / MANIFEST).write_text(
        json.dumps(dict(index.manifest, params=vars(index.params)), indent=2) + "\n",
        encoding="utf-8",
    )
    return index.manifest


class KeywordRetriever:
    """`Retriever` over a BM25 index (loaded once; searches are in memory)."""

    def __init__(self, index: BM25Index) -> None:
        self.index = index

    @classmethod
    def load(cls, path: Path) -> KeywordRetriever:
        return cls(BM25Index.load(path))

    def search(self, query: str, k: int, filters: Filters | None = None) -> list[ScoredChunk]:
        return self.index.search(query, k, filters)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scitech_agent.retrieval.keyword")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="Build the BM25 index from chunks.parquet.")
    build.add_argument("--chunks", type=Path, default=Path("data/processed/chunks"))
    build.add_argument("--out", type=Path, default=Path("data/index/bm25"))
    build.add_argument("--k1", type=float, default=BM25Params.k1)
    build.add_argument("--b", type=float, default=BM25Params.b)
    build.add_argument("--keep-stop-words", action="store_true")
    build.add_argument(
        "--trace-memory",
        action="store_true",
        help="Also trace Python/numpy allocations (works on Windows; the build is slower).",
    )
    search = sub.add_parser("search", help="Search a built index (manual check).")
    search.add_argument("query")
    search.add_argument("--index", type=Path, default=Path("data/index/bm25"))
    search.add_argument("-k", type=int, default=5)
    search.add_argument("--filters", type=json.loads, default=None, help="JSON object")
    args = parser.parse_args(argv)

    if args.command == "build":
        params = BM25Params(k1=args.k1, b=args.b, stop_words=not args.keep_stop_words)
        m = build_index(args.chunks, args.out, params, trace_memory=args.trace_memory)
        c = m["counts"]
        memory = f"peak RSS {m['peak_rss_mb']} MB" if m["peak_rss_mb"] else "peak RSS not reported"
        if m["traced"]:
            memory += f", peak traced {m['peak_traced_mb']} MB"
        print(
            f"bm25: {c['chunks']:,} chunks, {c['terms']:,} terms, {c['postings']:,} postings; "
            f"built in {m['build_seconds']} s, {memory}, {m['index_mb']} MB on disk -> {args.out}"
        )
        return 0
    started = time.monotonic()
    retriever = KeywordRetriever.load(args.index)
    loaded = time.monotonic() - started
    started = time.monotonic()
    hits = retriever.search(args.query, args.k, args.filters)
    took = (time.monotonic() - started) * 1000
    print(f"loaded {len(retriever.index):,} chunks in {loaded:.1f} s; search {took:.1f} ms")
    for rank, hit in enumerate(hits, 1):
        print(f"{rank:>2}. {hit.score:7.3f}  {hit.chunk_id}  {hit.title[:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
