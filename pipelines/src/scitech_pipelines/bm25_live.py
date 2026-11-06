"""BM25 index of the live collection, rebuilt after each scheduled load (W7-D6-FAO-1, ADR 0011).

`incremental-run` replaces papers in the live Qdrant collection; the BM25 index (DAT's
`scitech_agent.retrieval.keyword`) is built from chunk files and does not follow (#119). This
module rebuilds it from the collection itself: it scrolls every point's chunk fields, so the text
of a replaced paper is the new one and nothing depends on keeping the chunk files of every run.

The new index is written next to the live one (`<dir>.next`) and then switched in with two
renames (`<dir>` -> `<dir>.old`, `<dir>.next` -> `<dir>`), so a reader sees the old index or the
new one, never half of one; between the two renames, a few microseconds, the directory is
missing and a reader that loads at that moment fails and keeps its old index (W7-D7-DAT-1). A
failed build leaves `<dir>` untouched.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

Log = Callable[[str], None]


class PayloadSource(Protocol):
    """A store whose points' payloads can be read back (`QdrantReplaceStore`)."""

    @property
    def collection(self) -> str: ...

    def scroll_payloads(self, fields: Sequence[str]) -> Iterable[Mapping[str, Any]]: ...


def _order(payload: Mapping[str, Any]) -> tuple[str, int]:
    return (str(payload.get("doc_id")), int(payload.get("chunk_index") or 0))


def switch_dir(new: Path, live: Path) -> None:
    """Put `new` in place of `live` (two renames), then remove the old one."""
    old = live.with_name(live.name + ".old")
    if old.exists():
        shutil.rmtree(old)
    if live.exists():
        live.rename(old)
    new.rename(live)
    if old.exists():
        shutil.rmtree(old)


def rebuild_bm25(source: PayloadSource, live: Path, *, log: Log = print) -> dict[str, Any]:
    """Build the BM25 index of every chunk in `source`, in (doc_id, chunk_index) order, and
    switch it in at `live`. Return the index manifest."""
    from scitech_agent.retrieval.keyword import META_FIELDS, index_chunks

    started = time.monotonic()
    chunks = sorted(source.scroll_payloads(META_FIELDS), key=_order)
    read_seconds = time.monotonic() - started
    index = index_chunks(chunks)
    new = live.with_name(live.name + ".next")
    if new.exists():  # leftovers of a failed build
        shutil.rmtree(new)
    index.manifest.update(
        {
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "chunks": f"qdrant:{source.collection}",
            "chunked_at": None,
            "read_seconds": round(read_seconds, 1),
            "build_seconds": round(time.monotonic() - started - read_seconds, 1),
        }
    )
    index.save(new)
    switch_dir(new, live)
    log(
        f"bm25: {len(index):,} chunks of {source.collection} indexed in "
        f"{time.monotonic() - started:.1f} s -> {live}"
    )
    return index.manifest
