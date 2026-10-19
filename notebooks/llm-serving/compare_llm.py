"""Compare the candidate LLMs for ADR 0006 (W2-D4-DAT-1) on golden items with pasted context.

The method is fixed in `docs/decisions/0006-llm-model.md` (section "Method"); this script does
the mechanical parts, so the run on Kaggle is a few commands:

1. `contexts`  golden items + cleaned documents -> `contexts.jsonl`: for each item, the title and
               abstract of every document in its `relevant_doc_ids` (no retrieval involved).
2. `run`       one streamed call per model and item, with the agent's own system prompt
               (`agent/prompts/answer.md`) and source format (`answer_user_message`), the agent's
               defaults (temperature 0, max_tokens 512), and the model order rotated per item.
               Writes `answers.jsonl` with the answer, TTFT, total time and completion tokens.
3. `blind`     shuffles the answers, replaces the model names by codes and writes one rating
               sheet per rater (`ratings-LDN.csv` with relevance and grounded, `ratings-DAT.csv`
               with relevance only, PLAN.md section 9) and `key.json` (code -> model). Keep the
               key closed until both sheets are filled in.
4. `summarise` reads the answers, the key and the filled sheets and prints the ADR results table,
               the rater agreement and what the decision rule of the ADR picks.

Citation adherence is counted automatically: sentences with at least one `[n]`, and markers whose
number is outside 1..number of sources.

Configuration follows `docs/contracts/llm-client.md`: LLM_BASE_URL and LLM_API_KEY. The URL and
the key are never printed or written to an output file (the tunnel URL must not be committed).

Example (repository root as working directory; output in `data/adr0006/`, git-ignored):
    PYTHONPATH=agent/src python notebooks/llm-serving/compare_llm.py contexts \
        --documents data/processed/documents
    LLM_BASE_URL=https://<random>.trycloudflare.com/v1 PYTHONPATH=agent/src \
        python notebooks/llm-serving/compare_llm.py run \
        --models qwen2.5:3b,llama3.2:3b,qwen2.5:7b
    python notebooks/llm-serving/compare_llm.py blind
    python notebooks/llm-serving/compare_llm.py summarise
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import statistics
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_ITEMS = [f"gs-{i:03d}" for i in range(1, 11)]
TEMPERATURE = 0.0  # AgentConfig defaults, so the comparison tests the product's settings
MAX_TOKENS = 512
TIE_MARGIN = 0.2  # ADR 0006 decision rule: a gap of 0.2 or less in mean relevance is a tie
SHUFFLE_SEED = 6  # fixed, so the blind order can be reproduced from the answers file

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")
_MARKER = re.compile(r"\[(\d+)\]")


# --- Inputs --------------------------------------------------------------------------------------


def sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def read_golden(path: Path, ids: list[str]) -> list[dict[str, Any]]:
    """The golden items with the given ids, in that order."""
    items = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            items[item["id"]] = item
    missing = [i for i in ids if i not in items]
    if missing:
        raise ValueError(f"not in {path}: {', '.join(missing)}")
    return [items[i] for i in ids]


def read_documents(path: Path, doc_ids: set[str], id_field: str = "doc_id") -> dict[str, dict]:
    """`doc_id` -> {title, abstract} for the wanted ids, from the cleaned Parquet documents
    (a folder or file) or from a JSONL file such as FAO's sample."""
    path = Path(path)
    found: dict[str, dict] = {}
    if path.suffix == ".jsonl":
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                doc_id = str(record.get(id_field, "")).strip()
                if doc_id in doc_ids:
                    found[doc_id] = {"title": record["title"], "abstract": record["abstract"]}
        return found
    import pyarrow.dataset as ds

    dataset = ds.dataset(path, format="parquet", partitioning="hive")
    table = dataset.to_table(
        columns=["doc_id", "title", "abstract"], filter=ds.field("doc_id").isin(sorted(doc_ids))
    )
    for row in table.to_pylist():
        found[row["doc_id"]] = {"title": row["title"], "abstract": row["abstract"]}
    return found


def build_contexts(items: list[dict], documents: dict[str, dict]) -> list[dict]:
    """One record per item: question, reference answer and its sources (title + abstract)."""
    missing = sorted({d for it in items for d in it["relevant_doc_ids"]} - set(documents))
    if missing:
        raise ValueError(f"documents not found: {', '.join(missing)}")
    return [
        {
            "id": it["id"],
            "type": it["type"],
            "question": it["question"],
            "reference_answer": it.get("reference_answer", ""),
            "sources": [
                {"doc_id": d, "title": documents[d]["title"], "text": documents[d]["abstract"]}
                for d in it["relevant_doc_ids"]
            ],
        }
        for it in items
    ]


def answer_messages(context: dict) -> list[dict[str, str]]:
    """The answer call exactly as the agent builds it (system prompt and numbered sources)."""
    from scitech_agent.agent import answer_user_message, load_prompt
    from scitech_agent.retrieval import ScoredChunk

    evidence = [
        ScoredChunk(
            chunk_id=f"{s['doc_id']}#0",
            doc_id=s["doc_id"],
            score=1.0,
            title=s["title"],
            text=s["text"],
            source="arxiv",
            chunk_index=0,
        )
        for s in context["sources"]
    ]
    return [
        {"role": "system", "content": load_prompt("answer")},
        {"role": "user", "content": answer_user_message(context["question"], evidence)},
    ]


# --- Calls ---------------------------------------------------------------------------------------


@dataclass
class Answer:
    item: str
    model: str
    position: int  # 0-based place of this model in the item's rotated order
    answer: str
    ttft_s: float | None
    total_s: float
    completion_tokens: int
    token_source: str  # "usage" (reported by the server) or "chunks" (count of stream chunks)
    decode_tps: float | None
    started_at: str
    error: str | None = None


# A streaming call yields ("text", fragment) items and at most one ("usage", tokens) item.
StreamFn = Callable[[str, list[dict[str, str]]], Iterable[tuple[str, Any]]]


def openai_stream(base_url: str, api_key: str, timeout: float) -> StreamFn:
    from openai import OpenAI

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=0)

    def stream(model: str, messages: list[dict[str, str]]) -> Iterator[tuple[str, Any]]:
        events = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            stream=True,
            stream_options={"include_usage": True},
        )
        for event in events:
            if event.usage is not None:
                yield "usage", event.usage.completion_tokens
            if event.choices and event.choices[0].delta.content:
                yield "text", event.choices[0].delta.content

    return stream


def call_once(
    stream: StreamFn, model: str, context: dict, position: int, clock=time.perf_counter
) -> Answer:
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = clock()
    t_first = None
    parts: list[str] = []
    usage = None
    error = None
    try:
        for kind, value in stream(model, answer_messages(context)):
            if kind == "usage":
                usage = value
            elif value:
                if t_first is None:
                    t_first = clock()
                parts.append(value)
    except Exception as exc:  # noqa: BLE001 - a failed call is recorded, the run goes on
        error = f"{type(exc).__name__}: {exc}"
    t_end = clock()
    tokens = usage if usage is not None else len(parts)
    decode = None
    if t_first is not None and tokens > 1 and t_end > t_first:
        decode = (tokens - 1) / (t_end - t_first)
    return Answer(
        item=context["id"],
        model=model,
        position=position,
        answer="".join(parts),
        ttft_s=None if t_first is None else t_first - t0,
        total_s=t_end - t0,
        completion_tokens=tokens,
        token_source="usage" if usage is not None else "chunks",
        decode_tps=decode,
        started_at=started_at,
        error=error,
    )


def rotated(models: list[str], index: int) -> list[str]:
    """Model order for the item at `index`: shifted by one per item (decode rate drifts within a
    session, runbook section 4.1, so no model is always first or last)."""
    shift = index % len(models)
    return models[shift:] + models[:shift]


def run_all(
    stream: StreamFn, models: list[str], contexts: list[dict], log=print
) -> tuple[list[Answer], list[Answer]]:
    """Warm-up call per model (not scored), then every item with the rotated model order."""
    warmups = []
    for model in models:
        warmups.append(call_once(stream, model, contexts[0], position=-1))
        log(f"warm-up {model}: total {warmups[-1].total_s:.1f}s {warmups[-1].error or ''}")
    answers = []
    for index, context in enumerate(contexts):
        for position, model in enumerate(rotated(models, index)):
            a = call_once(stream, model, context, position)
            answers.append(a)
            ttft = "n/a" if a.ttft_s is None else f"{a.ttft_s:.2f}s"
            log(
                f"{a.item} {model}: ttft {ttft} total {a.total_s:.1f}s "
                f"tokens {a.completion_tokens}" + (f" ERROR {a.error}" if a.error else "")
            )
    return warmups, answers


# --- Automatic measures --------------------------------------------------------------------------


def sentences(text: str) -> list[str]:
    """Rough sentence split: on . ! ? followed by space and a capital, digit, quote or bracket.
    Markers such as `[1].` stay with their sentence."""
    out = []
    for block in text.splitlines():
        block = block.strip().lstrip("-*• ").strip()
        if block:
            out.extend(s.strip() for s in _SENTENCE_END.split(block) if s.strip())
    return [s for s in out if re.search(r"[A-Za-z]", s)]


def citation_counts(text: str, n_sources: int) -> dict[str, int]:
    """Sentences, sentences with at least one `[n]`, and markers outside 1..n_sources."""
    parts = sentences(text)
    markers = [int(m) for m in _MARKER.findall(text)]
    return {
        "sentences": len(parts),
        "cited_sentences": sum(1 for s in parts if _MARKER.search(s)),
        "markers": len(markers),
        "invalid_markers": sum(1 for m in markers if not 1 <= m <= n_sources),
    }


def looks_english(text: str) -> bool:
    """Heuristic for the language measure (all 10 items are English): at least 90% of the
    letters are ASCII. Vietnamese or Chinese output fails it. Recorded as a heuristic."""
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(c.isascii() for c in letters) / len(letters) >= 0.9


# --- Blind rating --------------------------------------------------------------------------------

LDN_COLUMNS = ["relevance_1_3", "grounded_yes_no", "note"]
DAT_COLUMNS = ["relevance_1_3", "note"]
RATING_HELP = (
    "relevance: 1 = does not address the question, 2 = partly (for example answers only one part "
    "of a two-part question), 3 = fully; judged against the question and the reference answer. "
    "grounded: yes = every factual claim is in the pasted abstracts, no = at least one is not."
)


def blind(answers: list[dict], contexts: dict[str, dict], seed: int = SHUFFLE_SEED):
    """Shuffled rows with codes A01.. and the key code -> (item, model)."""
    order = list(range(len(answers)))
    random.Random(seed).shuffle(order)
    rows, key = [], {}
    for n, i in enumerate(order, start=1):
        a = answers[i]
        code = f"A{n:02d}"
        ctx = contexts[a["item"]]
        key[code] = {"item": a["item"], "model": a["model"]}
        sources = "\n\n".join(
            f"[{k}] {s['title']}\n{s['text']}" for k, s in enumerate(ctx["sources"], start=1)
        )
        rows.append(
            {
                "code": code,
                "item": a["item"],
                "question": ctx["question"],
                "reference_answer": ctx["reference_answer"],
                "sources": sources,
                "answer": a["answer"] if not a.get("error") else f"(call failed: {a['error']})",
            }
        )
    return rows, key


def write_sheet(path: Path, rows: list[dict], rating_columns: list[str]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:  # BOM: Excel opens it as UTF-8
        writer = csv.DictWriter(fh, fieldnames=[*rows[0].keys(), *rating_columns])
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, **{c: "" for c in rating_columns}})


def read_sheet(path: Path) -> dict[str, dict]:
    """code -> {relevance, grounded}; raises on a missing or out-of-range rating."""
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            code = row["code"]
            try:
                relevance = int(row["relevance_1_3"].strip())
            except ValueError:
                raise ValueError(f"{path}: {code} has no relevance rating") from None
            if relevance not in (1, 2, 3):
                raise ValueError(f"{path}: {code} relevance must be 1, 2 or 3")
            grounded = None
            if "grounded_yes_no" in row:
                value = row["grounded_yes_no"].strip().lower()
                if value not in ("yes", "no"):
                    raise ValueError(f"{path}: {code} grounded must be yes or no")
                grounded = value == "yes"
            out[code] = {"relevance": relevance, "grounded": grounded}
    return out


# --- Summary -------------------------------------------------------------------------------------


def _median(xs: list[float]) -> float | None:
    return statistics.median(xs) if xs else None


def summarise(
    answers: list[dict],
    contexts: dict[str, dict],
    key: dict[str, dict],
    ldn: dict[str, dict],
    dat: dict[str, dict],
    slow: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    code_of = {(v["item"], v["model"]): c for c, v in key.items()}
    models = list(dict.fromkeys(a["model"] for a in answers))
    table = {}
    for model in models:
        mine = [a for a in answers if a["model"] == model]
        codes = [code_of[(a["item"], model)] for a in mine]
        counts = [citation_counts(a["answer"], len(contexts[a["item"]]["sources"])) for a in mine]
        ok = [a for a in mine if not a.get("error")]
        rel_ldn = [ldn[c]["relevance"] for c in codes]
        rel_dat = [dat[c]["relevance"] for c in codes]
        table[model] = {
            "n": len(mine),
            "errors": len(mine) - len(ok),
            "relevance_mean_ldn": statistics.mean(rel_ldn),
            "relevance_mean_dat": statistics.mean(rel_dat),
            "relevance_ldn_1_2_3": [rel_ldn.count(k) for k in (1, 2, 3)],
            "ungrounded_ldn": sum(1 for c in codes if ldn[c]["grounded"] is False),
            "sentences": sum(c["sentences"] for c in counts),
            "cited_sentences": sum(c["cited_sentences"] for c in counts),
            "invalid_markers": sum(c["invalid_markers"] for c in counts),
            "not_english": sum(1 for a in ok if not looks_english(a["answer"])),
            "ttft_median_s": _median([a["ttft_s"] for a in ok if a["ttft_s"] is not None]),
            "total_median_s": _median([a["total_s"] for a in ok]),
            "decode_tps_median": _median([a["decode_tps"] for a in ok if a["decode_tps"]]),
        }
    agree = [c for c in key if ldn[c]["relevance"] == dat[c]["relevance"]]
    differ = sorted(
        (c, key[c]["item"], key[c]["model"], ldn[c]["relevance"], dat[c]["relevance"])
        for c in key
        if c not in agree
    )
    return {
        "models": table,
        "agreement": {"equal": len(agree), "of": len(key), "differ": differ},
        "decision": decide(table, slow),
    }


def decide(
    table: dict[str, dict], slow: frozenset[str] = frozenset(), margin: float = TIE_MARGIN
) -> dict[str, Any]:
    """The ADR 0006 decision rule. Per rater, rank by mean relevance; the leader wins only by
    more than `margin`, for both raters. Otherwise the tied models are ordered by fewer
    ungrounded answers, then fewer invalid citations, then the faster median total time. A
    `slow` model (the 7B) wins only outright, never a tie (rule 4)."""

    def leaders(column: str) -> list[str]:
        best = max(row[column] for row in table.values())
        return [m for m, row in table.items() if best - row[column] <= margin + 1e-9]

    tied = sorted(set(leaders("relevance_mean_ldn")) | set(leaders("relevance_mean_dat")))
    if len(tied) == 1:
        return {"pick": tied[0], "tied": tied, "by": "mean relevance (both raters)"}
    candidates = [m for m in tied if m not in slow] or tied

    def tiebreak(m: str):
        row = table[m]
        total = row["total_median_s"] if row["total_median_s"] is not None else float("inf")
        return (row["ungrounded_ldn"], row["invalid_markers"], total)

    ranked = sorted(candidates, key=tiebreak)
    return {"pick": ranked[0], "tied": tied, "by": "tie: ungrounded, invalid [n], then speed"}


def _fmt(x: float | None, digits: int) -> str:
    return "n/a" if x is None else f"{x:.{digits}f}"


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "| Model | Mean relevance LDN / DAT (1-3) | Relevance 1 / 2 / 3 (LDN) "
        "| Ungrounded answers (LDN) | Sentences cited | Invalid `[n]` | Not English "
        "| TTFT median s | Total median s | tok/s median | Errors |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for model, r in summary["models"].items():
        lines.append(
            f"| `{model}` | {r['relevance_mean_ldn']:.2f} / {r['relevance_mean_dat']:.2f} "
            f"| {' / '.join(map(str, r['relevance_ldn_1_2_3']))} "
            f"| {r['ungrounded_ldn']} of {r['n']} | {r['cited_sentences']} of {r['sentences']} "
            f"| {r['invalid_markers']} | {r['not_english']} | {_fmt(r['ttft_median_s'], 2)} "
            f"| {_fmt(r['total_median_s'], 1)} | {_fmt(r['decode_tps_median'], 1)} "
            f"| {r['errors']} |"
        )
    agreement = summary["agreement"]
    lines += ["", f"Relevance agreement (DAT vs LDN): {agreement['equal']} of {agreement['of']}."]
    for code, item, model, l_rating, d_rating in agreement["differ"]:
        lines.append(f"- {code} ({item}, `{model}`): LDN {l_rating}, DAT {d_rating}")
    decision = summary["decision"]
    lines += [
        "",
        f"Decision rule picks `{decision['pick']}` ({decision['by']}; "
        f"within {TIE_MARGIN}: {', '.join(decision['tied'])}).",
    ]
    return "\n".join(lines) + "\n"


# --- Command line --------------------------------------------------------------------------------


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


def _write_jsonl(path: Path, records: Iterable[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("contexts", help="golden items + documents -> contexts.jsonl")
    p.add_argument("--golden", type=Path, default=Path("evaluation/golden_set/golden.jsonl"))
    p.add_argument("--documents", type=Path, default=Path("data/processed/documents"))
    p.add_argument("--id-field", default="doc_id", help="doc id field of a JSONL --documents")
    p.add_argument("--items", default=",".join(DEFAULT_ITEMS))
    p = sub.add_parser("run", help="one streamed call per model and item -> answers.jsonl")
    p.add_argument("--models", required=True, help="comma-separated model tags")
    p.add_argument("--timeout", type=float, default=300.0)
    sub.add_parser("blind", help="answers -> rating sheets and key.json")
    p = sub.add_parser("summarise", help="answers, key and filled sheets -> results table")
    p.add_argument(
        "--slow", default="qwen2.5:7b", help="models that win only outright, never a tie (rule 4)"
    )
    for p in sub.choices.values():
        p.add_argument("--out", type=Path, default=Path("data/adr0006"), help="working folder")
    args = parser.parse_args(argv)
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    if args.command == "contexts":
        items = read_golden(args.golden, [i.strip() for i in args.items.split(",") if i.strip()])
        wanted = {d for it in items for d in it["relevant_doc_ids"]}
        contexts = build_contexts(items, read_documents(args.documents, wanted, args.id_field))
        _write_jsonl(out / "contexts.jsonl", contexts)
        meta = {
            "golden": str(args.golden),
            "golden_sha256": sha256_of(args.golden),
            "commit": git_commit(),
            "items": [c["id"] for c in contexts],
            "documents": len(wanted),
        }
        (out / "contexts_meta.json").write_text(json.dumps(meta, indent=2) + "\n", "utf-8")
        print(f"{len(contexts)} items, {len(wanted)} documents -> {out / 'contexts.jsonl'}")
        print(f"golden sha256 {meta['golden_sha256']}, commit {meta['commit']}")
        return 0

    if args.command == "run":
        base_url = os.environ.get("LLM_BASE_URL", "").strip()
        if not base_url:
            print("Set LLM_BASE_URL (see docs/runbooks/llm-serving.md).", file=sys.stderr)
            return 2
        models = [m.strip() for m in args.models.split(",") if m.strip()]
        contexts = _jsonl(out / "contexts.jsonl")
        stream = openai_stream(
            base_url, os.environ.get("LLM_API_KEY") or "not-needed", args.timeout
        )
        warmups, answers = run_all(stream, models, contexts)
        _write_jsonl(out / "answers.jsonl", (asdict(a) for a in answers))
        _write_jsonl(out / "warmups.jsonl", (asdict(a) for a in warmups))
        meta = {
            "models": models,
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
            "commit": git_commit(),
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        (out / "run_meta.json").write_text(json.dumps(meta, indent=2) + "\n", "utf-8")
        failed = sum(1 for a in answers if a.error)
        print(f"{len(answers)} answers ({failed} failed) -> {out / 'answers.jsonl'}")
        return 1 if failed else 0

    contexts = {c["id"]: c for c in _jsonl(out / "contexts.jsonl")}
    answers = _jsonl(out / "answers.jsonl")
    if args.command == "blind":
        rows, key = blind(answers, contexts)
        write_sheet(out / "ratings-LDN.csv", rows, LDN_COLUMNS)
        write_sheet(out / "ratings-DAT.csv", rows, DAT_COLUMNS)
        (out / "key.json").write_text(json.dumps(key, indent=2) + "\n", "utf-8")
        (out / "RATING.md").write_text(RATING_HELP + "\n", "utf-8")
        print(f"{len(rows)} rows -> ratings-LDN.csv, ratings-DAT.csv; key.json stays closed")
        return 0

    key = json.loads((out / "key.json").read_text(encoding="utf-8"))
    summary = summarise(
        answers,
        contexts,
        key,
        read_sheet(out / "ratings-LDN.csv"),
        read_sheet(out / "ratings-DAT.csv"),
        slow=frozenset(m.strip() for m in args.slow.split(",") if m.strip()),
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", "utf-8")
    text = markdown(summary)
    (out / "summary.md").write_text(text, "utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
