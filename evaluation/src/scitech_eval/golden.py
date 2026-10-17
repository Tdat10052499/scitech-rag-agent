"""Golden set: load and check `golden.jsonl` (format: evaluation/golden_set/FORMAT.md)."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

TYPES = ("factual", "explanatory", "comparison", "multi_hop", "follow_up", "unanswerable")
SPLITS = ("dev", "test")
AUTHORS = ("LDN", "FAO", "DAT")
LANGUAGES = ("en", "vi")
REQUIRED = (
    "id",
    "question",
    "type",
    "relevant_doc_ids",
    "reference_answer",
    "notes",
    "author",
    "split",
)
_ID = re.compile(r"^gs-(?:(\d{3})|u\d{2})$")
_VERSION_SUFFIX = re.compile(r"v\d+$")
_NOTES_STYLE = re.compile(r"^(plain|expert|specific)\b")


class GoldenError(ValueError):
    """The golden file breaks the format rules; the message lists every problem."""


@dataclass(frozen=True)
class GoldenItem:
    id: str
    question: str
    type: str
    relevant_doc_ids: tuple[str, ...]
    reference_answer: str
    notes: str
    author: str
    split: str
    language: str = "en"
    history: tuple[dict, ...] | None = None
    standalone_query: str | None = None


def _check_item(obj: object) -> list[str]:
    """Return the format problems of one parsed line (empty list if it is fine)."""
    if not isinstance(obj, dict):
        return ["line is not a JSON object"]
    problems = [f"missing field '{f}'" for f in REQUIRED if f not in obj]
    if problems:
        return problems
    for f in ("id", "question", "reference_answer", "notes"):
        if not isinstance(obj[f], str) or not obj[f].strip():
            problems.append(f"'{f}' must be a non-empty string")
    if obj["type"] not in TYPES:
        problems.append(f"'type' must be one of {', '.join(TYPES)}")
    if obj["split"] not in SPLITS:
        problems.append(f"'split' must be one of {', '.join(SPLITS)}")
    if obj["author"] not in AUTHORS:
        problems.append(f"'author' must be one of {', '.join(AUTHORS)}")
    if obj.get("language", "en") not in LANGUAGES:
        problems.append(f"'language' must be one of {', '.join(LANGUAGES)}")
    if isinstance(obj["id"], str):
        m = _ID.match(obj["id"])
        if not m:
            problems.append("'id' must look like gs-NNN (or gs-uNN for unanswerable items)")
        elif m.group(1):
            number = int(m.group(1))
            expected = "dev" if number <= 30 else "test" if number <= 60 else None
            if expected and obj["split"] != expected:
                problems.append(f"items 001-030 are dev and 031-060 are test; got {obj['split']}")
    if isinstance(obj["notes"], str) and not _NOTES_STYLE.match(obj["notes"]):
        problems.append("'notes' must start with plain, expert or specific")

    ids = obj["relevant_doc_ids"]
    if not isinstance(ids, list) or not all(isinstance(d, str) and d for d in ids):
        problems.append("'relevant_doc_ids' must be a list of strings")
    else:
        if len(set(ids)) != len(ids):
            problems.append("'relevant_doc_ids' has duplicates")
        problems += [
            f"doc id '{d}' has a version suffix; drop it" for d in ids if _VERSION_SUFFIX.search(d)
        ]
        if obj["type"] == "unanswerable" and ids:
            problems.append("unanswerable items must have an empty 'relevant_doc_ids'")
        if obj["type"] != "unanswerable" and not ids:
            problems.append("'relevant_doc_ids' may be empty only for unanswerable items")
        if obj["type"] in ("comparison", "multi_hop") and len(ids) < 2:
            problems.append(f"{obj['type']} items need at least two relevant documents")

    if obj["type"] == "follow_up":
        history = obj.get("history")
        if not isinstance(history, list) or not history:
            problems.append("follow_up items need a non-empty 'history'")
        elif not all(
            isinstance(t, dict)
            and t.get("role") in ("user", "assistant")
            and isinstance(t.get("content"), str)
            for t in history
        ):
            problems.append("each history turn needs role (user|assistant) and content")
        if not isinstance(obj.get("standalone_query"), str) or not obj["standalone_query"].strip():
            problems.append("follow_up items need 'standalone_query'")
    return problems


def check_golden(path: Path, corpus_doc_ids: Iterable[str] | None = None) -> list[str]:
    """Check a golden file. Returns one message per problem; empty list means it is valid."""
    problems: list[str] = []
    seen: set[str] = set()
    corpus = set(corpus_doc_ids) if corpus_doc_ids is not None else None
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(f"line {number}: invalid JSON ({exc.msg})")
            continue
        has_id = isinstance(obj, dict) and "id" in obj
        where = f"line {number}" + (f" ({obj['id']})" if has_id else "")
        problems += [f"{where}: {p}" for p in _check_item(obj)]
        if isinstance(obj, dict) and isinstance(obj.get("id"), str):
            if obj["id"] in seen:
                problems.append(f"{where}: duplicate id")
            seen.add(obj["id"])
            if corpus is not None and isinstance(obj.get("relevant_doc_ids"), list):
                problems += [
                    f"{where}: doc id '{d}' is not in the corpus"
                    for d in obj["relevant_doc_ids"]
                    if d not in corpus
                ]
    return problems


def load_golden(path: Path) -> list[GoldenItem]:
    """Load a golden file, raising GoldenError with all problems if it breaks the format."""
    problems = check_golden(path)
    if problems:
        raise GoldenError(f"{path}: " + "; ".join(problems))
    items = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        history = o.get("history")
        items.append(
            GoldenItem(
                id=o["id"],
                question=o["question"],
                type=o["type"],
                relevant_doc_ids=tuple(o["relevant_doc_ids"]),
                reference_answer=o["reference_answer"],
                notes=o["notes"],
                author=o["author"],
                split=o["split"],
                language=o.get("language", "en"),
                history=tuple(history) if history else None,
                standalone_query=o.get("standalone_query"),
            )
        )
    return items


def read_corpus_doc_ids(path: Path, id_field: str = "doc_id") -> set[str]:
    """Read doc ids from a JSONL corpus file (one object per line); a version suffix is dropped."""
    ids: set[str] = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            ids.add(_VERSION_SUFFIX.sub("", str(json.loads(line)[id_field])))
    return ids
