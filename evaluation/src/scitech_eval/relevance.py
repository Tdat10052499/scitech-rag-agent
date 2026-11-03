"""Answer relevance judge: a separate pass over a stored `.answers.jsonl` (PLAN.md 4.2, #94).

`python -m scitech_eval relevance --config <yaml> --answers <answers.jsonl>`:

1. Reads the answers of one run (written by `answers`) and the golden file (reference answer,
   earlier turns, item type). The agent is not called.
2. An answer is rated when it enters the metrics: no `error`, not `insufficient_evidence`, and an
   answerable item (PLAN.md 4.2). Refusals, errors and answers to unanswerable items are counted
   and left out.
3. An LLM judge rates each answer 1 to 3 with the anchor of PLAN.md 4.2
   (`evaluation/prompts/relevance-judge.md`), one answer per call. It sees the question, the earlier
   turns, the reference answer and the answer, and not the sources: citations and correctness are
   faithfulness, not relevance.
4. An answer that is empty or only citation markers gets rating 1 without a judge call, because
   the anchor defines it ("no answer"), so that rating does not depend on a 7B model.
5. The run file holds mean and distribution, and the judge settings, so two runs can be compared.

A reply that cannot be read, or a failed call, is stored as `judge_error` on that answer; it gets no
rating and is not retried. Faithfulness and relevance of one condition are separate files that share
the `<timestamp>-<name>` prefix of the answers file.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

import yaml

from scitech_eval.answer_run import Judge, _summary, judge_from_env, load_prompt
from scitech_eval.answers import CITATION, read_answers
from scitech_eval.golden import GoldenItem, load_golden
from scitech_eval.runner import git_commit

SCHEMA_VERSION = 1
RATINGS = (1, 2, 3)
NOTE = (
    "The judge is a 7B model whose relevance ratings have not been checked against human ratings "
    "when this file was written; the manual rating of the same sample (PLAN.md 4.2) decides where "
    "they differ. Relevance means addressing what the question asks, not being correct or "
    "supported. One run per condition; never compare runs with different judges or prompts."
)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def load_relevance_config(path: Path) -> dict:
    config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"{path}: config must be a YAML mapping")
    for key in ("name", "golden_path"):
        if not config.get(key):
            raise ValueError(f"{path}: missing '{key}'")
    judge = config.get("judge")
    if not isinstance(judge, dict):
        raise ValueError(f"{path}: missing 'judge' mapping")
    for key in ("prompt_path", "digest"):
        if not judge.get(key):
            raise ValueError(f"{path}: missing 'judge.{key}'")
    if not (isinstance(judge.get("max_tokens"), int) and judge["max_tokens"] > 0):
        raise ValueError(f"{path}: 'judge.max_tokens' must be a positive integer")
    judge.setdefault("temperature", 0.0)
    ctx = judge.get("context_tokens")
    if ctx is not None and not (isinstance(ctx, int) and ctx > 0):
        raise ValueError(f"{path}: 'judge.context_tokens' must be a positive integer")
    if config.get("bootstrap") is None:
        config["bootstrap"] = {}
    return config


def history_text(item: GoldenItem) -> str:
    """The earlier turns of a follow-up item, one line per turn; `(none)` for the others."""
    turns = [f"{t['role']}: {t['content']}" for t in (item.history or ())]
    return "\n".join(turns) if turns else "(none)"


def build_relevance_prompt(template: str, item: GoldenItem, answer: str) -> str:
    # str.replace, not str.format: the prompt contains literal braces (the JSON reply format).
    return (
        template.replace("{question}", item.question)
        .replace("{history}", history_text(item))
        .replace("{reference_answer}", item.reference_answer)
        .replace("{answer}", answer)
    )


def parse_rating(reply: str) -> tuple[int, str] | None:
    """(rating, reason) from the judge reply, or `None` if it cannot be read.

    The reply is a JSON object, optionally in a code fence or with text around it; `rating` must be
    the integer 1, 2 or 3. Nothing else is guessed (a string "3" or 2.5 is unreadable).
    """
    text = _FENCE.sub("", reply.strip())
    for candidate in (text, text[text.find("{") : text.rfind("}") + 1] if "{" in text else ""):
        try:
            obj = json.loads(candidate)
        except ValueError:
            continue
        rating = obj.get("rating") if isinstance(obj, dict) else None
        if isinstance(rating, int) and not isinstance(rating, bool) and rating in RATINGS:
            reason = obj.get("reason")
            return rating, reason if isinstance(reason, str) else ""
    return None


def is_empty_answer(text: str) -> bool:
    """True if nothing is left of the answer after the citation markers and punctuation go."""
    return not CITATION.sub("", text).strip(" \t\r\n.;,:-")


def rateable(answers: list[dict], golden: Mapping[str, GoldenItem]) -> tuple[list[dict], dict]:
    """The answers that enter the metrics, and counts of what was left out (PLAN.md 4.2)."""
    unknown = sorted({a["answer_id"] for a in answers} - set(golden))
    if unknown:
        raise ValueError(f"answer ids not in the golden file: {', '.join(unknown[:5])}")
    kept: list[dict] = []
    left_out = {"error": 0, "refused": 0, "unanswerable_item": 0}
    for a in answers:
        if a.get("error"):
            left_out["error"] += 1
        elif a.get("insufficient_evidence"):
            left_out["refused"] += 1
        elif golden[a["answer_id"]].type == "unanswerable":
            left_out["unanswerable_item"] += 1
        else:
            kept.append(a)
    return kept, left_out


def rate_answers(
    judge: Judge,
    template: str,
    answers: list[dict],
    golden: Mapping[str, GoldenItem],
    settings: dict,
) -> tuple[list[dict], dict]:
    """One row per rateable answer (`rating` and `reason`, or `judge_error`) and the run stats."""
    stats = {"max_prompt_chars": 0, "errors": Counter(), "fixed_no_answer": 0}
    rows: list[dict] = []
    for a in answers:
        item = golden[a["answer_id"]]
        row = {"id": item.id, "type": item.type}
        if is_empty_answer(a["answer"]):
            stats["fixed_no_answer"] += 1
            rows.append(
                {
                    **row,
                    "rating": 1,
                    "reason": "no answer text (empty or only markers); not sent to the judge",
                }
            )
            continue
        prompt = build_relevance_prompt(template, item, a["answer"])
        stats["max_prompt_chars"] = max(stats["max_prompt_chars"], len(prompt))
        try:
            reply = judge.chat(
                [{"role": "user", "content": prompt}],
                temperature=settings["temperature"],
                max_tokens=settings["max_tokens"],
            )
        except Exception as exc:  # LLMError (server down, timeout ...): keep the run going
            code = getattr(exc, "code", type(exc).__name__)
            stats["errors"][f"call:{code}"] += 1
            rows.append({**row, "rating": None, "judge_error": f"call failed: {code}"})
            continue
        parsed = parse_rating(reply)
        if parsed is None:
            stats["errors"]["unreadable"] += 1
            rows.append({**row, "rating": None, "judge_error": "unreadable reply", "reply": reply})
            continue
        rows.append({**row, "rating": parsed[0], "reason": parsed[1]})
    return rows, stats


def run_relevance(
    config: dict,
    answers_path: Path,
    golden: Mapping[str, GoldenItem],
    judge: Judge,
    template: str,
    prompt_info: dict,
    stamp: str | None = None,
) -> dict:
    answers = read_answers(answers_path)
    kept, left_out = rateable(answers, golden)
    rows, stats = rate_answers(judge, template, kept, golden, config["judge"])
    rated = [r["rating"] for r in rows if r["rating"] is not None]
    distribution = {str(n): rated.count(n) for n in RATINGS}
    resamples = config["bootstrap"].get("resamples", 1000)
    seed = config["bootstrap"].get("seed", 0)
    prompt_tokens = stats["max_prompt_chars"] / 4  # rough: 4 characters per token
    context = config["judge"].get("context_tokens")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "relevance",
        "name": config["name"],
        "timestamp": stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "git_commit": git_commit(),
        "answers_file": {
            "name": Path(answers_path).name,
            "sha256": hashlib.sha256(Path(answers_path).read_bytes()).hexdigest(),
        },
        "golden": {
            "path": str(config["golden_path"]),
            "sha256": hashlib.sha256(Path(config["golden_path"]).read_bytes()).hexdigest(),
        },
        "judge": {
            "model": judge.model,
            "digest": config["judge"]["digest"],
            "temperature": config["judge"]["temperature"],
            "max_tokens": config["judge"]["max_tokens"],
            "prompt": prompt_info,
            "context_tokens": context,
            "max_prompt_chars": stats["max_prompt_chars"],
            "approx_max_prompt_tokens": round(prompt_tokens),
            "prompt_fits_context": None if context is None else prompt_tokens < context,
            "errors": dict(stats["errors"]),
            "fixed_no_answer": stats["fixed_no_answer"],
        },
        "counts": {
            "answers_in_file": len(answers),
            "left_out": left_out,
            "rateable": len(kept),
            "rated": len(rated),
            "judge_error": len(rows) - len(rated),
        },
        "metrics": {
            "relevance": _summary([float(r) for r in rated], resamples, seed),
            "distribution": distribution,
        },
        "per_answer": rows,
        "config": config,
        "note": NOTE,
    }


def output_path(record: dict, answers_path: Path, out_dir: Path) -> Path:
    """`<stem of the answers file>.relevance.json`, so the file sits next to its answers."""
    stem = Path(answers_path).name
    stem = stem[: -len(".answers.jsonl")] if stem.endswith(".answers.jsonl") else Path(stem).stem
    return Path(out_dir) / f"{stem}.relevance.json"


def run_from_relevance_config(config_path: Path, answers_path: Path, out_dir: Path) -> Path:
    config = load_relevance_config(config_path)
    golden = {i.id: i for i in load_golden(Path(config["golden_path"]))}
    template, prompt_info = load_prompt(Path(config["judge"]["prompt_path"]))
    judge = judge_from_env()
    record = run_relevance(config, answers_path, golden, judge, template, prompt_info)
    path = output_path(record, answers_path, out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
