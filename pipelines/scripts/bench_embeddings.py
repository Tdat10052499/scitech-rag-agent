"""Measure embedding throughput on the sample and estimate full-run time (W1-D2-FAO-1).

Embeds `title. abstract` of every record in the sample with a sentence-transformers model,
reports records/second, and, given profile.json from profile_arxiv_snapshot.py, estimates
the time of a full embedding run per candidate start year (one chunk per abstract assumed).

Usage:
    python pipelines/scripts/bench_embeddings.py --sample data/raw/sample/sample.jsonl \
        --profile data/raw/sample/profile.json --model BAAI/bge-small-en-v1.5
The model defaults to the EMBEDDING_MODEL environment variable.
Dependencies: pipelines/requirements-bench.txt.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import time
from pathlib import Path


def load_texts(path: Path, limit: int | None) -> list[str]:
    texts = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            text = f"{record.get('title', '')}. {record.get('abstract', '')}"
            texts.append(re.sub(r"\s+", " ", text).strip())
            if limit and len(texts) >= limit:
                break
    return texts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sample", default="data/raw/sample/sample.jsonl")
    parser.add_argument("--profile", help="profile.json, to estimate full-run time")
    parser.add_argument("--model", default=os.environ.get("EMBEDDING_MODEL"))
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--device", help="cpu, cuda or mps (default: auto)")
    parser.add_argument("--limit", type=int, help="Use only the first N records")
    parser.add_argument("--start-years", default="2015,2018,2020,2022,2024")
    args = parser.parse_args()
    if not args.model or args.model == "replace-me":
        parser.error("set --model or the EMBEDDING_MODEL environment variable")

    import torch
    from sentence_transformers import SentenceTransformer

    texts = load_texts(Path(args.sample), args.limit)
    model = SentenceTransformer(args.model, device=args.device)
    device = str(model.device)
    gpu = torch.cuda.get_device_name(0) if device.startswith("cuda") else None

    model.encode(texts[: args.batch_size], batch_size=args.batch_size)  # warm-up
    started = time.perf_counter()
    vectors = model.encode(texts, batch_size=args.batch_size, show_progress_bar=True)
    seconds = time.perf_counter() - started
    rate = len(texts) / seconds

    result: dict = {
        "model": args.model,
        "dimension": int(vectors.shape[1]),
        "device": device,
        "gpu": gpu,
        "cpu": platform.processor() or platform.machine(),
        "batch_size": args.batch_size,
        "records": len(texts),
        "avg_chars": round(sum(map(len, texts)) / len(texts)),
        "seconds": round(seconds, 2),
        "records_per_second": round(rate, 1),
    }
    print(
        f"\n{args.model} on {gpu or device}: {len(texts)} records in {seconds:.1f} s "
        f"= {rate:.1f} records/s (dim {result['dimension']})"
    )

    if args.profile:
        since = json.loads(Path(args.profile).read_text(encoding="utf-8"))[
            "records_since_year_incl_crosslists"
        ]
        estimates = {}
        print("\n| Start year | Records (incl. cross-lists) | Estimated embedding time |")
        print("|---|---:|---:|")
        for year in args.start_years.split(","):
            if year not in since:
                continue
            hours = since[year] / rate / 3600
            estimates[year] = {"records": since[year], "hours": round(hours, 2)}
            print(f"| {year} | {since[year]:,} | {hours:.2f} h ({hours * 60:.0f} min) |")
        result["estimates"] = estimates

    slug = re.sub(r"[^A-Za-z0-9]+", "-", args.model).strip("-")
    out = Path(args.sample).with_name(f"bench-{slug}-{device.split(':')[0]}.json")
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"\nWritten {out}")


if __name__ == "__main__":
    main()
