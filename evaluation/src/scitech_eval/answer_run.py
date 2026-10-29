"""Run the agent on golden questions and score the answers (evaluation/PLAN.md sections 4.2 and 5).

`python -m scitech_eval answers --config <yaml>`:

1. `Agent.run_batch` answers the selected golden items, one new session each (needs the agent
   package on `PYTHONPATH` and the agent's environment, see `.env.example`).
2. Every answer of an answerable item that was neither refused nor failed is split into sentences;
   an LLM judge labels each sentence from the passages it cites
   (`evaluation/prompts/faithfulness-judge.md`),
   one sentence per call, as in the manual protocol.
3. The run file reports faithfulness, cited-document recall, invalid citations, refusals and errors,
   and records the generator and judge settings so two runs can be compared.

Counted separately, never mixed into the faithfulness rate:

- `error`: the agent failed on the item; no judge call.
- refusal (`insufficient_evidence`): no sentence is sent to the judge (rule 4 of the judge prompt).
  On answerable items this is over-refusal; on unanswerable items it is the correct behaviour.
- `judge_error`: the judge reply could not be read, or the call failed. The sentence gets no label
  and is not retried; the numbers are in `judge.errors`.

A "half refusal" (the answer opens with the fixed refusal sentence and then answers, so
`insufficient_evidence` is false; seen on gs-002, #139) is not a refusal here: its sentences go to
the judge, and the refusal sentence itself is labelled not checkable (judge prompt rule 4).

Unanswerable items that were answered anyway are listed in `answered_anyway` for a manual check;
they are not judged here. Answer relevance (PLAN.md section 4.2) is not computed by this command.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import yaml

from scitech_eval.answers import LABELS, cited_numbers, split_sentences
from scitech_eval.golden import GoldenItem, load_golden
from scitech_eval.metrics import bootstrap_ci, mean
from scitech_eval.runner import git_commit

SCHEMA_VERSION = 1
DEFAULT_FACTORY = "scitech_agent.factory:agent_from_env"
JUDGE_ENV = {
    "JUDGE_BASE_URL": "LLM_BASE_URL",
    "JUDGE_API_KEY": "LLM_API_KEY",
    "JUDGE_MODEL": "LLM_MODEL",
}
NOTE = (
    "The judge is a 7B model that has not been validated against human labels; the pilot kappa "
    "(evaluation/pilot/faithfulness) is the first evidence. Faithfulness means supported by the "
    "cited passages, not true. One run per condition; never compare runs with different judges."
)


class Judge(Protocol):
    model: str

    def chat(self, messages: list[dict[str, str]], temperature: float, max_tokens: int) -> str: ...


# --- Config -------------------------------------------------------------------------------------


def load_answer_config(path: Path) -> dict:
    config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"{path}: config must be a YAML mapping")
    for key in ("name", "golden_path"):
        if not config.get(key):
            raise ValueError(f"{path}: missing '{key}'")
    config.setdefault("split", "dev")
    config.setdefault("language", "en")
    if config["split"] not in ("dev", "test", "all"):
        raise ValueError(f"{path}: 'split' must be dev, test or all")
    ids, limit = config.get("ids"), config.get("limit")
    if ids is not None and not (isinstance(ids, list) and all(isinstance(i, str) for i in ids)):
        raise ValueError(f"{path}: 'ids' must be a list of golden ids")
    if limit is not None and not (isinstance(limit, int) and limit > 0):
        raise ValueError(f"{path}: 'limit' must be a positive integer")
    for key in ("notes", "dataset_snapshot", "index_snapshot"):
        if config.get(key) is None:
            config[key] = "" if key == "notes" else "unspecified"
    agent = config.get("agent") or {}
    agent.setdefault("factory", DEFAULT_FACTORY)
    config["agent"] = agent
    # Generator settings the trace does not hold (SNAPSHOT.md): model digest and max_tokens.
    config["generator"] = config.get("generator") or {}
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


def select_items(config: dict, items: list[GoldenItem]) -> list[GoldenItem]:
    chosen = [
        i for i in items if config["split"] in ("all", i.split) and i.language == config["language"]
    ]
    if config.get("ids"):
        by_id = {i.id: i for i in chosen}
        missing = [i for i in config["ids"] if i not in by_id]
        if missing:
            raise ValueError(f"ids not in the selected split/language: {', '.join(missing)}")
        chosen = [by_id[i] for i in config["ids"]]
    if config.get("limit"):
        chosen = chosen[: config["limit"]]
    if not chosen:
        raise ValueError("no golden items match the split, language and ids in the config")
    return chosen


# --- Judge --------------------------------------------------------------------------------------


def judge_from_env(env: Mapping[str, str] | None = None) -> Judge:
    """The judge LLM of `JUDGE_BASE_URL`, `JUDGE_API_KEY`, `JUDGE_MODEL` (same client as the
    generator; `LLM_TIMEOUT` and `LLM_MAX_RETRIES` are shared)."""
    from scitech_agent.llm import LLMConfig, OpenAICompatibleLLM

    env = os.environ if env is None else env
    mapped = {target: env.get(source, "") for source, target in JUDGE_ENV.items()}
    for key in ("LLM_TIMEOUT", "LLM_MAX_RETRIES"):
        mapped[key] = env.get(key, "")
    missing = [name for name in JUDGE_ENV if not env.get(name, "").strip()]
    if missing:
        raise ValueError(f"missing environment variable(s): {', '.join(missing)}")
    return OpenAICompatibleLLM(LLMConfig.from_env(mapped))


def load_prompt(path: Path) -> tuple[str, dict]:
    """The judge prompt and where it came from (sha256 of the text, last commit that touched it)."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"judge prompt not found: {path} (it comes with PR #135)")
    text = path.read_text(encoding="utf-8")
    try:
        commit = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", str(path)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = ""
    info = {
        "path": str(path),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "commit": commit or "not committed",
    }
    return text, info


def format_passages(sources: list[dict], numbers: list[int]) -> str:
    """The cited passages as the model sees them: `[n]`, title and text. A number with no source
    adds nothing (judge prompt rule 6)."""
    by_n = {s["n"]: s for s in sources}
    parts = [
        f"[{n}] Title: {by_n[n].get('title', '')}\nText: {by_n[n].get('text', '')}"
        for n in numbers
        if n in by_n
    ]
    return "\n\n".join(parts) if parts else "(no cited passage)"


def build_judge_prompt(template: str, question: str, sentence: str, passages: str) -> str:
    # str.replace, not str.format: the prompt contains literal braces (the JSON reply format).
    return (
        template.replace("{question}", question)
        .replace("{sentence}", sentence)
        .replace("{cited_passages}", passages)
    )


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_judgement(reply: str) -> tuple[str, str] | None:
    """(label, reason) from the judge reply, or `None` if it cannot be read.

    The reply is a JSON object, optionally in a code fence or with text around it; the label must
    be one of `LABELS`. Nothing else is guessed.
    """
    text = _FENCE.sub("", reply.strip())
    for candidate in (text, text[text.find("{") : text.rfind("}") + 1] if "{" in text else ""):
        try:
            obj = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("label") in LABELS:
            reason = obj.get("reason")
            return obj["label"], reason if isinstance(reason, str) else ""
    return None


def judge_answer(
    judge: Judge, template: str, answer: dict, settings: dict, stats: dict
) -> list[dict]:
    """Label every sentence of one answer. `stats` collects the longest prompt and error counts."""
    rows = []
    for number, sentence in enumerate(split_sentences(answer["answer"]), start=1):
        cited = cited_numbers(sentence)
        prompt = build_judge_prompt(
            template,
            answer["question"],
            sentence,
            format_passages(answer["sources"], cited),
        )
        stats["max_prompt_chars"] = max(stats["max_prompt_chars"], len(prompt))
        row = {"sentence_no": number, "sentence": sentence, "cited_n": cited}
        try:
            reply = judge.chat(
                [{"role": "user", "content": prompt}],
                temperature=settings["temperature"],
                max_tokens=settings["max_tokens"],
            )
        except Exception as exc:  # LLMError (tunnel down, timeout ...): keep the run going
            code = getattr(exc, "code", type(exc).__name__)
            stats["errors"][f"call:{code}"] += 1
            rows.append({**row, "label": None, "judge_error": f"call failed: {code}"})
            continue
        parsed = parse_judgement(reply)
        if parsed is None:
            stats["errors"]["unreadable"] += 1
            rows.append({**row, "label": None, "judge_error": "unreadable reply", "reply": reply})
            continue
        rows.append({**row, "label": parsed[0], "reason": parsed[1]})
    return rows


# --- Metrics ------------------------------------------------------------------------------------


def invalid_citations(answer_raw: str, n_sources: int) -> tuple[int, int]:
    """(marker numbers pointing to no source, all marker numbers) in the raw LLM text. Counted per
    sentence, so a number repeated inside one sentence counts once."""
    bad = total = 0
    for sentence in split_sentences(answer_raw):
        for n in cited_numbers(sentence):
            total += 1
            bad += not 1 <= n <= n_sources
    return bad, total


def cited_doc_ids(answer: dict) -> set[str]:
    by_chunk = {s["chunk_id"]: s["doc_id"] for s in answer["sources"]}
    return {by_chunk[c] for c in answer.get("citations", []) if c in by_chunk}


def faithfulness(rows: list[dict]) -> dict:
    counts = Counter(r["label"] for r in rows if r["label"])
    supported, unsupported = counts["supported"], counts["not supported"]
    checkable = supported + unsupported
    return {
        "supported": supported,
        "not_supported": unsupported,
        "not_checkable": counts["not checkable"],
        "judge_error": sum(1 for r in rows if not r["label"]),
        "checkable": checkable,
        "faithfulness": supported / checkable if checkable else None,
    }


def _summary(values: list[float], resamples: int, seed: int) -> dict | None:
    if not values:
        return None
    low, high = bootstrap_ci(values, resamples=resamples, seed=seed)
    return {"n": len(values), "mean": mean(values), "ci95": [low, high]}


# --- Run ----------------------------------------------------------------------------------------


def run_answers(
    config: dict,
    items: list[GoldenItem],
    agent: Any,
    judge: Judge,
    template: str,
    prompt_info: dict,
    clock: Callable[[], float] = time.perf_counter,
) -> tuple[dict, list[dict]]:
    """Answer and judge `items`. Returns the run record and the raw answer records (one per item,
    `BatchResult.to_dict()`, for `make-sheet` and the traces)."""
    resamples = config["bootstrap"].get("resamples", 1000)
    seed = config["bootstrap"].get("seed", 0)
    by_id = {i.id: i for i in items}
    batch = [{"id": i.id, "question": i.question, "history": list(i.history or ())} for i in items]
    # The first search loads the embedding model (11 s measured on the real stack, #139), so it is
    # done before the batch and is not counted in the per-question latency. A failure is only
    # logged by the agent; the questions then report their own errors.
    warm_up = getattr(agent, "warm_up", None)
    warm_started = clock()
    if callable(warm_up):
        warm_up()
    warm_up_seconds = clock() - warm_started
    started = clock()
    answers = [r.to_dict() for r in agent.run_batch(batch)]
    answer_seconds = clock() - started

    stats = {"max_prompt_chars": 0, "errors": Counter()}
    per_answer, answered_anyway = [], []
    n_error = n_refused = n_unans = n_unans_refused = 0
    judge_started = clock()
    for a in answers:
        item = by_id[a["answer_id"]]
        unanswerable = item.type == "unanswerable"
        row: dict[str, Any] = {
            "id": item.id,
            "type": item.type,
            "error": a["error"],
            "insufficient_evidence": a["insufficient_evidence"],
            "latency_ms": (a.get("trace") or {}).get("latency_ms"),
            "n_sources": len(a["sources"]),
        }
        if unanswerable:
            n_unans += 1
            if a["error"]:
                n_error += 1
            elif a["insufficient_evidence"]:
                n_unans_refused += 1
            else:
                answered_anyway.append(item.id)
            per_answer.append(row)
            continue
        if a["error"]:
            n_error += 1
            per_answer.append(row)
            continue
        if a["insufficient_evidence"]:
            n_refused += 1
            per_answer.append(row)
            continue
        relevant = set(item.relevant_doc_ids)
        retrieved_docs = {r["doc_id"] for r in (a.get("trace") or {}).get("retrieved", [])}
        cited_docs = cited_doc_ids(a)
        bad, total = invalid_citations(a.get("answer_raw") or a["answer"], len(a["sources"]))
        sentences = judge_answer(judge, template, a, config["judge"], stats)
        row.update(
            {
                "cited_doc_recall": len(relevant & cited_docs) / len(relevant),
                "retrieved_doc_recall": len(relevant & retrieved_docs) / len(relevant),
                "cited_doc_ids": sorted(cited_docs),
                "relevant_doc_ids": list(item.relevant_doc_ids),
                "invalid_citations": bad,
                "citation_numbers": total,
                "sentences": sentences,
                **faithfulness(sentences),
            }
        )
        per_answer.append(row)
    judge_seconds = clock() - judge_started

    judged = [r for r in per_answer if "sentences" in r]
    scored = [r for r in judged if r["faithfulness"] is not None]
    all_sentences = [s for r in judged for s in r["sentences"]]
    pooled = faithfulness(all_sentences)
    n_answerable = sum(1 for i in items if i.type != "unanswerable")
    n_markers = sum(r["citation_numbers"] for r in judged)
    metrics = {
        "faithfulness_macro": _summary([r["faithfulness"] for r in scored], resamples, seed),
        "faithfulness_micro": pooled["faithfulness"],
        "share_faithfulness_1": (
            sum(1 for r in scored if r["faithfulness"] == 1) / len(scored) if scored else None
        ),
        "cited_doc_recall": _summary([r["cited_doc_recall"] for r in judged], resamples, seed),
        "retrieved_doc_recall": _summary(
            [r["retrieved_doc_recall"] for r in judged], resamples, seed
        ),
        "invalid_citation_rate": (
            sum(r["invalid_citations"] for r in judged) / n_markers if n_markers else None
        ),
        "over_refusal_rate": n_refused / n_answerable if n_answerable else None,
    }
    prompt_tokens = stats["max_prompt_chars"] / 4  # rough: 4 characters per token
    context = config["judge"].get("context_tokens")
    trace = (answers[0].get("trace") or {}) if answers else {}
    record = {
        "schema_version": SCHEMA_VERSION,
        "kind": "answers",
        "name": config["name"],
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "git_commit": git_commit(),
        "dataset_snapshot": config["dataset_snapshot"],
        "index_snapshot": config["index_snapshot"],
        "notes": config["notes"],
        "golden": {
            "path": str(config["golden_path"]),
            "sha256": hashlib.sha256(Path(config["golden_path"]).read_bytes()).hexdigest(),
            "split": config["split"],
            "language": config["language"],
            "n_items": len(items),
            "n_answerable": n_answerable,
            "n_unanswerable": n_unans,
        },
        "generator": {
            "model": (trace.get("model") or {}).get("LLM_MODEL"),
            "trace_model": trace.get("model"),
            "agent_config": trace.get("config"),
            **config["generator"],  # digest, max_tokens (from SNAPSHOT.md)
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
            "n_judge_error": pooled["judge_error"],
        },
        "counts": {
            "answers": len(answers),
            "errors": n_error,
            "refused_answerable": n_refused,
            "judged_answers": len(judged),
            "sentences": len(all_sentences),
            "supported": pooled["supported"],
            "not_supported": pooled["not_supported"],
            "not_checkable": pooled["not_checkable"],
            "judge_error": pooled["judge_error"],
            "unanswerable_refused": n_unans_refused,
            "unanswerable_answered_anyway": len(answered_anyway),
        },
        "answered_anyway": answered_anyway,
        "timings": {
            "warm_up_seconds": round(warm_up_seconds, 3),
            "answer_seconds": round(answer_seconds, 3),
            "judge_seconds": round(judge_seconds, 3),
        },
        "metrics": metrics,
        "per_answer": per_answer,
        "config": config,
        "note": NOTE,
    }
    return record, answers


def write_answer_run(record: dict, answers: list[dict], out_dir: Path) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{record['timestamp']}-{record['name']}"
    run_path, answers_path = out_dir / f"{stem}.json", out_dir / f"{stem}.answers.jsonl"
    run_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    answers_path.write_text(
        "".join(json.dumps(a, ensure_ascii=False) + "\n" for a in answers), encoding="utf-8"
    )
    return run_path, answers_path


@contextmanager
def _environ(overrides: Mapping[str, str]) -> Iterator[None]:
    saved = {k: os.environ.get(k) for k in overrides}
    os.environ.update(overrides)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def build_agent(spec: dict) -> Any:
    import importlib

    module_name, _, attr = spec["factory"].partition(":")
    return getattr(importlib.import_module(module_name), attr)()


def run_from_answer_config(config_path: Path, out_dir: Path) -> tuple[Path, Path]:
    config = load_answer_config(config_path)
    items = select_items(config, load_golden(Path(config["golden_path"])))
    template, prompt_info = load_prompt(Path(config["judge"]["prompt_path"]))
    judge = judge_from_env()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # One trace file per run (docs/runbooks/traces.md); `traces_path: off` switches traces off.
    traces = config.get("traces_path") or str(
        Path(out_dir) / f"{stamp}-{config['name']}.traces.jsonl"
    )
    with _environ({"AGENT_TRACES": traces}):
        agent = build_agent(config["agent"])
        record, answers = run_answers(config, items, agent, judge, template, prompt_info)
    record["traces_path"] = traces
    return write_answer_run(record, answers, out_dir)
