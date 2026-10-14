"""Measure time to first token and generation speed of an OpenAI-compatible endpoint.

Task W1-D3-DAT-1 (LLM serving spike). Used on Kaggle against the local Ollama server and
from a laptop through the tunnel, with the same settings, so the numbers are comparable.

Configuration follows docs/contracts/llm-client.md: LLM_BASE_URL, LLM_API_KEY, LLM_MODEL.
The API key is never printed or written to the results file.

Example:
    LLM_BASE_URL=http://localhost:11434/v1 python bench_llm.py \
        --models qwen2.5:3b,llama3.2:3b --runs 5 --label kaggle-t4-local
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from openai import OpenAI

PROMPTS = {
    "en": (
        "Explain in about 150 words what retrieval-augmented generation is and why it "
        "can reduce hallucinations in question answering."
    ),
    "vi": (
        "Hãy giải thích bằng tiếng Việt, khoảng 150 từ, retrieval-augmented generation "
        "là gì và vì sao nó có thể giảm hallucination khi trả lời câu hỏi."
    ),
}


@dataclass
class RunResult:
    label: str
    model: str
    prompt_id: str
    run: int
    warmup: bool
    ttft_s: float | None
    total_s: float
    completion_tokens: int
    token_source: str  # "usage" (reported by the server) or "chunks" (count of stream chunks)
    decode_tps: float | None  # tokens after the first one / time after the first token
    e2e_tps: float  # tokens / total time
    temperature: float
    max_tokens: int
    started_at: str
    error: str | None = None


def run_once(
    client: OpenAI,
    model: str,
    prompt_id: str,
    run: int,
    warmup: bool,
    args: argparse.Namespace,
) -> RunResult:
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = time.perf_counter()
    t_first: float | None = None
    chunks = 0
    usage_tokens: int | None = None
    error: str | None = None
    try:
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": PROMPTS[prompt_id]}],
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            stream=True,
            stream_options={"include_usage": True},
        )
        for event in stream:
            if event.usage is not None:
                usage_tokens = event.usage.completion_tokens
            if event.choices and event.choices[0].delta.content:
                if t_first is None:
                    t_first = time.perf_counter()
                chunks += 1
    except Exception as exc:  # noqa: BLE001 - a spike records every failure and continues
        error = f"{type(exc).__name__}: {exc}"
    t_end = time.perf_counter()

    tokens = usage_tokens if usage_tokens is not None else chunks
    total = t_end - t0
    ttft = None if t_first is None else t_first - t0
    decode_tps = None
    if t_first is not None and tokens > 1 and t_end > t_first:
        decode_tps = (tokens - 1) / (t_end - t_first)
    return RunResult(
        label=args.label,
        model=model,
        prompt_id=prompt_id,
        run=run,
        warmup=warmup,
        ttft_s=ttft,
        total_s=total,
        completion_tokens=tokens,
        token_source="usage" if usage_tokens is not None else "chunks",
        decode_tps=decode_tps,
        e2e_tps=tokens / total if total > 0 else 0.0,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        started_at=started_at,
        error=error,
    )


def summarise(results: list[RunResult]) -> str:
    lines = [
        "| label | model | prompt | n | TTFT median (min-max) s | decode tok/s median (min-max)"
        " | tokens median | errors |",
        "|---|---|---|---|---|---|---|---|",
    ]
    keys = sorted({(r.label, r.model, r.prompt_id) for r in results if not r.warmup})
    for label, model, prompt_id in keys:
        group = [
            r
            for r in results
            if not r.warmup and (r.label, r.model, r.prompt_id) == (label, model, prompt_id)
        ]
        ok = [r for r in group if r.error is None]
        ttft = [r.ttft_s for r in ok if r.ttft_s is not None]
        tps = [r.decode_tps for r in ok if r.decode_tps is not None]
        toks = [r.completion_tokens for r in ok]

        def fmt(xs: list[float], digits: int) -> str:
            if not xs:
                return "n/a"
            return f"{statistics.median(xs):.{digits}f} ({min(xs):.{digits}f}-{max(xs):.{digits}f})"

        lines.append(
            f"| {label} | {model} | {prompt_id} | {len(ok)} | {fmt(ttft, 2)} | {fmt(tps, 1)}"
            f" | {statistics.median(toks) if toks else 'n/a'} | {len(group) - len(ok)} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", default=os.environ.get("LLM_MODEL", ""))
    parser.add_argument("--runs", type=int, default=5, help="measured runs per model and prompt")
    parser.add_argument("--prompts", default="en,vi", help=f"subset of {sorted(PROMPTS)}")
    parser.add_argument("--max-tokens", type=int, default=200)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--label", default=platform.node() or "unknown")
    parser.add_argument("--out", default="bench_results.jsonl", help="JSONL file (appended)")
    args = parser.parse_args(argv)

    base_url = os.environ.get("LLM_BASE_URL")
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    prompt_ids = [p.strip() for p in args.prompts.split(",") if p.strip()]
    if not base_url or not models:
        print("Set LLM_BASE_URL and --models (or LLM_MODEL).", file=sys.stderr)
        return 2
    unknown = set(prompt_ids) - set(PROMPTS)
    if unknown:
        print(f"Unknown prompt ids: {sorted(unknown)}", file=sys.stderr)
        return 2

    client = OpenAI(
        base_url=base_url,
        api_key=os.environ.get("LLM_API_KEY", "not-needed"),
        timeout=args.timeout,
        max_retries=0,  # measure the endpoint as it is; retries would hide failures
    )
    print(f"label={args.label} models={models} runs={args.runs} max_tokens={args.max_tokens}")

    results: list[RunResult] = []
    with open(args.out, "a", encoding="utf-8") as fh:
        for model in models:
            # One warm-up call loads the model into memory; it is recorded but not summarised.
            plan = [(prompt_ids[0], 0, True)]
            plan += [(p, i, False) for i in range(1, args.runs + 1) for p in prompt_ids]
            for prompt_id, run, warmup in plan:
                r = run_once(client, model, prompt_id, run, warmup, args)
                results.append(r)
                fh.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
                fh.flush()
                tag = "warmup" if warmup else f"run {run}"
                ttft = "n/a" if r.ttft_s is None else f"{r.ttft_s:.2f}s"
                tps = "n/a" if r.decode_tps is None else f"{r.decode_tps:.1f} tok/s"
                print(
                    f"{model} {prompt_id} {tag}: ttft={ttft} decode={tps} "
                    f"tokens={r.completion_tokens} total={r.total_s:.2f}s"
                    + (f" ERROR {r.error}" if r.error else "")
                )

    print()
    print(summarise(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
