"""Faithfulness pilot: split an answer into sentences and write the labelling sheet.

The manual protocol is section 5 of `evaluation/PLAN.md`; the sheet has one row per sentence of an
answer. Nothing here calls a model.

Sentence rules (kept simple on purpose, see `evaluation/pilot/faithfulness/README.md`):

- A line break always ends a sentence, and a list marker (`- `, `* `, `1. `) is dropped.
- `.`, `!` or `?` end a sentence when whitespace follows and the next word starts with an upper-case
  letter, a digit, a quote or a bracket (or the line ends).
- Citation markers `[n]` that follow the end mark directly (`... works. [1] Next`) stay with the
  sentence before it; markers before the end mark (`... works [1].`) are already inside it.
- No split after an abbreviation (`e.g.`, `i.e.`, `et al.`, `vs.`, ...), after a single capital
  letter (an initial), or inside a number or a name such as `bge-small-en-v1.5` (no space follows).
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

LABELS = ("supported", "not supported", "not checkable")
SHEET_COLUMNS = [
    "answer_id",
    "sentence_no",
    "sentence",
    "cited_n",
    "cited_chunk_ids",
    "label",
    "reason",
    "partial_note",
    "annotator",
]
CHUNK_COLUMNS = ["answer_id", "n", "chunk_id", "doc_id", "text"]

# The same marker forms the agent parses (`agent/src/scitech_agent/answer.py`): `[1]`, `[1, 2]`,
# `[1; 2]`, `[1-3]`. A range longer than 20 is not read as a citation, nor is a marker with a 0.
_ITEM = r"\d+(?:\s*[-–]\s*\d+)?"
CITATION = re.compile(rf"\[\s*({_ITEM}(?:\s*[,;]\s*{_ITEM})*)\s*\]")
_MAX_RANGE = 20
ABBREVIATIONS = {"e.g", "i.e", "et al", "vs", "etc", "fig", "no", "approx", "cf", "eq", "al"}
_LIST_MARKER = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_END = re.compile(rf"[.!?]+[)\"'”]*(?:\s*\[\s*{_ITEM}(?:\s*[,;]\s*{_ITEM})*\s*\])*(?=\s|$)")


def _is_boundary(line: str, start: int, end: int) -> bool:
    """Whether the end mark found at line[start:end] really ends a sentence."""
    rest = line[end:].lstrip()
    if rest and not (rest[0].isupper() or rest[0].isdigit() or rest[0] in "\"'“(["):
        return False
    before = line[:start].rstrip()
    word = re.split(r"\s+", before)[-1] if before else ""
    if line[start] == "." and (word.lower().strip("([\"'") in ABBREVIATIONS):
        return False
    if line[start] == "." and re.fullmatch(r"[A-Z]", word.strip("([\"'")):
        return False  # an initial such as "J. Smith"
    if line[start] == "." and re.search(r"\be\.g$|\bi\.e$|\bet al$", before, re.IGNORECASE):
        return False
    return True


def split_sentences(text: str) -> list[str]:
    """Split an answer into sentences (rules in the module docstring); empty pieces are dropped."""
    sentences: list[str] = []
    for raw in text.splitlines():
        line = _LIST_MARKER.sub("", raw).strip()
        if not line:
            continue
        begin = 0
        for match in _END.finditer(line):
            if _is_boundary(line, match.start(), match.end()):
                piece = line[begin : match.end()].strip()
                if piece:
                    sentences.append(piece)
                begin = match.end()
        tail = line[begin:].strip()
        if tail:
            sentences.append(tail)
    return sentences


def cited_numbers(sentence: str) -> list[int]:
    """The source numbers cited in a sentence, in order, without repeats (`[1, 2]` and `[1-3]`
    included, as the agent reads them)."""
    seen: list[int] = []
    for match in CITATION.finditer(sentence):
        if match.start() > 0 and re.match(r"\w", sentence[match.start() - 1]):
            continue  # `x[1]` is an index, not a citation
        numbers: list[int] = []
        for item in re.split(r"\s*[,;]\s*", match.group(1).strip()):
            bounds = [int(b) for b in re.split(r"\s*[-–]\s*", item)]
            if len(bounds) == 2 and 0 <= bounds[1] - bounds[0] < _MAX_RANGE:
                numbers.extend(range(bounds[0], bounds[1] + 1))
            elif len(bounds) == 1:
                numbers.append(bounds[0])
        if 0 in numbers:
            continue
        for n in numbers:
            if n not in seen:
                seen.append(n)
    return seen


def read_answers(path: Path) -> list[dict]:
    """Read `answers.jsonl`: one object per answer, with `answer_id`, `answer` and `sources`."""
    answers = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        for key in ("answer_id", "answer", "sources"):
            if key not in item:
                raise ValueError(f"{path}:{number}: missing '{key}'")
        answers.append(item)
    ids = [a["answer_id"] for a in answers]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{path}: answer_id values are not unique")
    return answers


def build_sheet(answers: list[dict]) -> tuple[list[dict], list[dict]]:
    """Rows of the labelling sheet and of the chunk file that goes with it.

    The label columns stay empty. A marker `[n]` with no source `n` is written as `n(INVALID)`, so
    the annotator sees it and knows there is no passage to check the sentence against.
    """
    sheet: list[dict] = []
    chunks: list[dict] = []
    for answer in answers:
        by_n = {s["n"]: s for s in answer["sources"]}
        for source in answer["sources"]:
            chunks.append(
                {
                    "answer_id": answer["answer_id"],
                    "n": source["n"],
                    "chunk_id": source.get("chunk_id", ""),
                    "doc_id": source.get("doc_id", ""),
                    "text": source.get("text", ""),
                }
            )
        for number, sentence in enumerate(split_sentences(answer["answer"]), start=1):
            numbers = cited_numbers(sentence)
            sheet.append(
                {
                    "answer_id": answer["answer_id"],
                    "sentence_no": number,
                    "sentence": sentence,
                    "cited_n": ";".join(str(n) if n in by_n else f"{n}(INVALID)" for n in numbers),
                    "cited_chunk_ids": ";".join(
                        by_n[n].get("chunk_id", "") for n in numbers if n in by_n
                    ),
                    "label": "",
                    "reason": "",
                    "partial_note": "",
                    "annotator": "",
                }
            )
    return sheet, chunks


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    """UTF-8 with a BOM, so that Excel opens the file with the right encoding."""
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def make_sheet(answers_path: Path, out_dir: Path) -> tuple[Path, Path]:
    """Write `labels-template.csv` and `chunks.csv` for an `answers.jsonl`."""
    sheet, chunks = build_sheet(read_answers(answers_path))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sheet_path, chunks_path = out_dir / "labels-template.csv", out_dir / "chunks.csv"
    write_csv(sheet_path, SHEET_COLUMNS, sheet)
    write_csv(chunks_path, CHUNK_COLUMNS, chunks)
    return sheet_path, chunks_path


def check_labels(path: Path) -> list[str]:
    """Problems in a filled sheet: unknown or empty label, `not supported` without a reason."""
    problems = []
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in SHEET_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            return [f"{path}: missing columns {', '.join(missing)}"]
        for row in reader:
            where = f"{row['answer_id']} sentence {row['sentence_no']}"
            label = row["label"].strip()
            if label not in LABELS:
                problems.append(f"{where}: label {label!r} is not one of {', '.join(LABELS)}")
            elif label == "not supported" and not row["reason"].strip():
                problems.append(f"{where}: 'not supported' needs a one-line reason")
            if not row["annotator"].strip():
                problems.append(f"{where}: annotator is empty")
    return problems
