"""Profile the Kaggle arXiv metadata snapshot for one category (W1-D2-FAO-1).

Streams the snapshot line by line (it does not fit comfortably in memory) and writes:
- profile.json: record counts, per-year counts of the category (primary only and including
  cross-lists), bytes per record and field completeness;
- sample.jsonl: a reproducible random sample of the category (reservoir sampling);
- fixture.jsonl: a smaller random subset of the sample, for pipelines/tests/fixtures/.

Year = year of the first version (`versions[0].created`). Primary category = first entry of
`categories` (the snapshot has no separate primary field).

Usage:
    python pipelines/scripts/profile_arxiv_snapshot.py \
        --snapshot data/raw/arxiv-metadata-oai-snapshot.json --out-dir data/raw/sample
"""

from __future__ import annotations

import argparse
import json
import random
import time
from collections import Counter
from email.utils import parsedate_to_datetime
from pathlib import Path

FIXTURE_DROP_FIELDS = ("submitter", "authors_parsed")


def first_version_year(record: dict) -> int | None:
    """Return the year of the first version, or None if it is missing or unparsable."""
    versions = record.get("versions") or []
    if not versions:
        return None
    try:
        return parsedate_to_datetime(versions[0]["created"]).year
    except (KeyError, TypeError, ValueError):
        return None


def is_filled(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def profile(args: argparse.Namespace) -> dict:
    category = args.category
    rng = random.Random(args.seed)
    started = time.perf_counter()

    total_records = 0
    total_bytes = 0
    bad_lines = 0
    primary_by_year: Counter[int] = Counter()
    any_by_year: Counter[int] = Counter()
    cross_from: Counter[str] = Counter()
    field_filled: Counter[str] = Counter()
    field_seen: set[str] = set()
    cat_records = 0
    cat_bytes = 0
    cat_chars = 0
    sample: list[dict] = []
    eligible = 0

    with open(args.snapshot, encoding="utf-8") as f:
        for line in f:
            total_records += 1
            line_bytes = len(line.encode("utf-8"))
            total_bytes += line_bytes
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                bad_lines += 1
                continue
            cats = (record.get("categories") or "").split()
            if category not in cats:
                continue
            year = first_version_year(record)
            year_key = year if year is not None else 0
            any_by_year[year_key] += 1
            if cats[0] == category:
                primary_by_year[year_key] += 1
            else:
                cross_from[cats[0]] += 1

            cat_records += 1
            cat_bytes += line_bytes
            cat_chars += len(record.get("abstract") or "")
            field_seen.update(record)
            for key, value in record.items():
                if is_filled(value):
                    field_filled[key] += 1

            if year is not None and year >= args.sample_from_year:
                eligible += 1
                if len(sample) < args.sample_size:
                    sample.append(record)
                else:
                    j = rng.randrange(eligible)
                    if j < args.sample_size:
                        sample[j] = record

            if args.progress and total_records % 500_000 == 0:
                print(f"... {total_records:,} records read", flush=True)

    sample.sort(key=lambda r: r["id"])
    picked = rng.sample(sample, min(args.fixture_size, len(sample)))
    fixture = [
        {k: v for k, v in r.items() if k not in FIXTURE_DROP_FIELDS}
        for r in sorted(picked, key=lambda r: r["id"])
    ]
    out_dir = Path(args.out_dir)
    write_jsonl(out_dir / "sample.jsonl", sample)
    write_jsonl(out_dir / "fixture.jsonl", fixture)

    years = sorted(y for y in any_by_year if y)
    since = {str(y): sum(n for yy, n in any_by_year.items() if yy >= y) for y in years}
    result = {
        "snapshot": str(args.snapshot),
        "category": category,
        "seconds": round(time.perf_counter() - started, 1),
        "total_records": total_records,
        "total_bytes": total_bytes,
        "bad_lines": bad_lines,
        "category_records": cat_records,
        "category_bytes": cat_bytes,
        "category_avg_bytes_per_record": round(cat_bytes / cat_records) if cat_records else 0,
        "category_avg_abstract_chars": round(cat_chars / cat_records) if cat_records else 0,
        "per_year_primary": {str(y): primary_by_year[y] for y in years},
        "per_year_incl_crosslists": {str(y): any_by_year[y] for y in years},
        "records_since_year_incl_crosslists": since,
        "records_without_year": any_by_year.get(0, 0),
        "crosslisted_from_top10": dict(cross_from.most_common(10)),
        "field_completeness_pct": {
            k: round(100 * field_filled[k] / cat_records, 1) for k in sorted(field_seen)
        },
        "sample_size": len(sample),
        "sample_from_year": args.sample_from_year,
        "fixture_size": len(fixture),
        "seed": args.seed,
    }
    (out_dir / "profile.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result


def print_summary(result: dict) -> None:
    print(
        f"\nRead {result['total_records']:,} records "
        f"({result['total_bytes'] / 1e9:.2f} GB) in {result['seconds']} s"
    )
    print(
        f"{result['category']}: {result['category_records']:,} records, "
        f"{result['category_bytes'] / 1e6:.0f} MB, "
        f"{result['category_avg_bytes_per_record']} bytes/record, "
        f"{result['category_avg_abstract_chars']} abstract chars/record\n"
    )
    print("| Year | Primary only | Incl. cross-lists | Since this year (incl.) |")
    print("|---|---:|---:|---:|")
    for year, n_any in result["per_year_incl_crosslists"].items():
        n_primary = result["per_year_primary"][year]
        n_since = result["records_since_year_incl_crosslists"][year]
        print(f"| {year} | {n_primary:,} | {n_any:,} | {n_since:,} |")
    print("\nField completeness (%):", result["field_completeness_pct"])
    print("Cross-listed from (top 10):", result["crosslisted_from_top10"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--snapshot", required=True, help="arxiv-metadata-oai-snapshot.json")
    parser.add_argument("--out-dir", default="data/raw/sample", help="Output directory")
    parser.add_argument("--category", default="cs.CL")
    parser.add_argument("--sample-size", type=int, default=1000)
    parser.add_argument("--sample-from-year", type=int, default=2022)
    parser.add_argument("--fixture-size", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--progress", action="store_true", help="Print progress every 500k lines")
    print_summary(profile(parser.parse_args()))


if __name__ == "__main__":
    main()
