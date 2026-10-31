"""Faithfulness pilot: split an answer into sentences and write the labelling sheet.

The manual protocol is section 5 of `evaluation/PLAN.md`; the sheet has one row per sentence of an
answer. Nothing here calls a model.

For the manual check of the judge (W7-D2-LDN-1) the sheet can be made for a seeded sample of the
answers that enter the metrics (`sample_answers`): no error, not refused, an answerable item.

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
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

from scitech_eval.golden import load_golden

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
# One row per sampled answer, for the manual relevance rating (1 to 3, anchor in PLAN.md 4.2).
RELEVANCE_COLUMNS = [
    "answer_id",
    "question",
    "history",
    "reference_answer",
    "answer",
    "rating",
    "reason",
    "annotator",
]

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


def _sample_key(seed: int, answer_id: str) -> str:
    return hashlib.sha256(f"{seed}|{answer_id}".encode()).hexdigest()


def parse_part(text: str) -> tuple[int, int]:
    """`K/N` -> (K, N) with 1 <= K <= N."""
    try:
        k, n = (int(x) for x in text.split("/"))
    except ValueError:
        raise ValueError(f"part must look like 1/2, not {text!r}") from None
    if not 1 <= k <= n:
        raise ValueError(f"part {text!r}: need 1 <= K <= N")
    return k, n


def sample_answers(
    answers: list[dict],
    golden: dict,
    fraction: float,
    seed: int,
    part: tuple[int, int] | None = None,
) -> tuple[list[dict], dict]:
    """A seeded sample of the answers that enter the metrics, and a record of how it was drawn.

    Eligible: no `error`, not `insufficient_evidence`, and an answerable item of `golden`
    (`{id: GoldenItem}`). Refused answers and answers to unanswerable items are not scored
    (PLAN.md 4.2), so they are not labelled here. The sample is the first `ceil(fraction * n)`
    eligible ids ordered by sha256 of `seed|id`: the same seed and the same eligible ids give the
    same sample on any Python version, and the order of the file does not matter. `part=(k, n)`
    keeps every n-th id of that order starting at k-1, so the parts are disjoint and together are
    the sample (one part per annotator). The answers come back in file order.
    """
    if not 0 < fraction <= 1:
        raise ValueError(f"sample fraction must be in (0, 1], not {fraction}")
    unknown = sorted({a["answer_id"] for a in answers} - set(golden))
    if unknown:
        raise ValueError(f"answer ids not in the golden file: {', '.join(unknown[:5])}")
    errors = [a for a in answers if a.get("error")]
    refused = [a for a in answers if not a.get("error") and a.get("insufficient_evidence")]
    scored = [a for a in answers if not a.get("error") and not a.get("insufficient_evidence")]
    unanswerable = [a for a in scored if golden[a["answer_id"]].type == "unanswerable"]
    eligible = [a for a in scored if golden[a["answer_id"]].type != "unanswerable"]
    size = min(len(eligible), math.ceil(fraction * len(eligible) - 1e-9))
    order = sorted((a["answer_id"] for a in eligible), key=lambda i: _sample_key(seed, i))[:size]
    mine = order if part is None else order[part[0] - 1 :: part[1]]
    picked = set(mine)
    record = {
        "fraction": fraction,
        "seed": seed,
        "part": None if part is None else f"{part[0]}/{part[1]}",
        "answers_in_file": len(answers),
        "excluded": {
            "error": len(errors),
            "refused": len(refused),
            "unanswerable_item": len(unanswerable),
        },
        "eligible": len(eligible),
        "sampled_all_parts": sorted(order),
        "sampled_this_part": sorted(picked),
        "types_this_part": dict(Counter(golden[i].type for i in picked)),
    }
    return [a for a in answers if a["answer_id"] in picked], record


def _history_text(item) -> str:
    return "\n".join(f"{t['role']}: {t['content']}" for t in (item.history or ()))


def relevance_rows(answers: list[dict], golden: dict) -> list[dict]:
    """The manual relevance sheet: one row per answer, the rating columns empty."""
    return [
        {
            "answer_id": a["answer_id"],
            "question": golden[a["answer_id"]].question,
            "history": _history_text(golden[a["answer_id"]]),
            "reference_answer": golden[a["answer_id"]].reference_answer,
            "answer": a["answer"],
            "rating": "",
            "reason": "",
            "annotator": "",
        }
        for a in answers
    ]


def make_sheet(
    answers_path: Path,
    out_dir: Path,
    *,
    sample: float | None = None,
    seed: int = 0,
    part: tuple[int, int] | None = None,
    golden_path: Path | None = None,
) -> list[Path]:
    """Write `labels-template.csv` and `chunks.csv` for an `answers.jsonl`.

    With `sample` (a fraction) only a seeded sample of the scored answers is written, plus
    `relevance-template.csv` and `sample.json` (how the sample was drawn, for the report). With
    `part` the file names get a `-partKofN` suffix. `golden_path` (default
    `evaluation/golden_set/golden.jsonl`) is needed with `sample`.
    """
    answers = read_answers(answers_path)
    out_dir = Path(out_dir)
    if sample is None:
        if part is not None:
            raise ValueError("--part needs --sample")
        sheet, chunks = build_sheet(answers)
        out_dir.mkdir(parents=True, exist_ok=True)
        sheet_path, chunks_path = out_dir / "labels-template.csv", out_dir / "chunks.csv"
        write_csv(sheet_path, SHEET_COLUMNS, sheet)
        write_csv(chunks_path, CHUNK_COLUMNS, chunks)
        return [sheet_path, chunks_path]

    golden_path = golden_path or Path("evaluation/golden_set/golden.jsonl")
    golden = {i.id: i for i in load_golden(golden_path)}
    picked, record = sample_answers(answers, golden, sample, seed, part)
    record["answers_file"] = Path(answers_path).name
    suffix = "" if part is None else f"-part{part[0]}of{part[1]}"
    sheet, chunks = build_sheet(picked)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [
        out_dir / f"labels-template{suffix}.csv",
        out_dir / f"chunks{suffix}.csv",
        out_dir / f"relevance-template{suffix}.csv",
        out_dir / f"sample{suffix}.json",
    ]
    write_csv(paths[0], SHEET_COLUMNS, sheet)
    write_csv(paths[1], CHUNK_COLUMNS, chunks)
    write_csv(paths[2], RELEVANCE_COLUMNS, relevance_rows(picked, golden))
    paths[3].write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return paths


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
