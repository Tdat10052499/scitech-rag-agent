"""Run the same small job with several engines and measure it (W1-D5-FAO-1, ADR 0005).

Job: load arXiv metadata (JSON Lines), keep records whose `categories` contain the category,
count them by year of the first version, write the kept records to Parquet.
Measured per engine: wall time (including engine start-up) and peak resident memory of this
process and its children (the Spark JVM is a child process).

Usage:
    python pipelines/scripts/bench_engines.py --input data/raw/sample/sample.jsonl \
        --engines duckdb,polars,pyspark --out-dir data/bench
Dependencies: pipelines/requirements-bench.txt. PySpark needs Java 17; on Windows use WSL2 or Colab.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path

import psutil

YEAR_REGEX = r"(\d{4})"


def run_duckdb(src: str, out: str, category: str) -> dict[str, int]:
    import duckdb

    def quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    con = duckdb.connect()
    con.execute(
        f"""
        CREATE TEMP TABLE kept AS
        SELECT *, CAST(regexp_extract(versions[1].created, '{YEAR_REGEX}', 1) AS INTEGER) AS year
        FROM read_json_auto({quote(src)}, format = 'newline_delimited',
                            maximum_object_size = 10000000)
        WHERE list_contains(string_split(categories, ' '), {quote(category)})
        """
    )
    con.execute(f"COPY kept TO {quote(out)} (FORMAT parquet)")
    rows = con.execute("SELECT year, count(*) FROM kept GROUP BY year ORDER BY year").fetchall()
    return {str(year): n for year, n in rows}


def run_polars(src: str, out: str, category: str) -> dict[str, int]:
    import polars as pl

    kept = (
        pl.read_ndjson(src, infer_schema_length=None)
        .filter(pl.col("categories").str.split(" ").list.contains(category))
        .with_columns(
            pl.col("versions")
            .list.first()
            .struct.field("created")
            .str.extract(YEAR_REGEX, 1)
            .cast(pl.Int32)
            .alias("year")
        )
    )
    kept.write_parquet(out)
    counts = kept.group_by("year").len().sort("year")
    return {str(year): n for year, n in counts.iter_rows()}


def run_pyspark(src: str, out: str, category: str) -> dict[str, int]:
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F

    spark = (
        SparkSession.builder.master("local[*]")
        .appName("bench_engines")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    try:
        kept = (
            spark.read.json(src)
            .where(F.array_contains(F.split("categories", " "), category))
            .withColumn(
                "year",
                F.regexp_extract(F.col("versions")[0]["created"], YEAR_REGEX, 1).cast("int"),
            )
            .cache()
        )
        kept.write.mode("overwrite").parquet(out)
        rows = kept.groupBy("year").count().orderBy("year").collect()
        return {str(row["year"]): row["count"] for row in rows}
    finally:
        spark.stop()


ENGINES: dict[str, Callable[[str, str, str], dict[str, int]]] = {
    "duckdb": run_duckdb,
    "polars": run_polars,
    "pyspark": run_pyspark,
}


class PeakMemory:
    """Poll the resident memory of this process and its children in a background thread."""

    def __init__(self, interval: float = 0.05) -> None:
        self.interval = interval
        self.peak = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._poll, daemon=True)

    def _poll(self) -> None:
        me = psutil.Process()
        while not self._stop.is_set():
            total = 0
            for proc in [me, *me.children(recursive=True)]:
                try:
                    total += proc.memory_info().rss
                except psutil.Error:
                    pass
            self.peak = max(self.peak, total)
            time.sleep(self.interval)

    def __enter__(self) -> PeakMemory:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", default="data/raw/sample/sample.jsonl")
    parser.add_argument("--engines", default="duckdb,polars,pyspark")
    parser.add_argument("--category", default="cs.CL")
    parser.add_argument("--out-dir", default="data/bench")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    src = str(Path(args.input).resolve())
    size_mb = Path(src).stat().st_size / 1e6
    results = []
    for name in args.engines.split(","):
        out = out_dir / f"{name}.parquet"
        if out.is_dir():
            shutil.rmtree(out)
        elif out.exists():
            out.unlink()
        started = time.perf_counter()
        with PeakMemory() as memory:
            counts = ENGINES[name](src, str(out), args.category)
        seconds = time.perf_counter() - started
        results.append(
            {
                "engine": name,
                "seconds": round(seconds, 2),
                "peak_rss_mb": round(memory.peak / 1e6),
                "kept_records": sum(counts.values()),
                "counts_by_year": counts,
            }
        )
        print(
            f"{name}: {seconds:.2f} s, peak {memory.peak / 1e6:.0f} MB, "
            f"{sum(counts.values()):,} records kept"
        )

    print(
        f"\nInput: {args.input} ({size_mb:.1f} MB), {platform.platform()}, "
        f"{psutil.cpu_count()} CPUs, {psutil.virtual_memory().total / 1e9:.0f} GB RAM\n"
    )
    print("| Engine | Wall time (s) | Peak memory (MB) | Records kept |")
    print("|---|---:|---:|---:|")
    for r in results:
        print(f"| {r['engine']} | {r['seconds']} | {r['peak_rss_mb']:,} | {r['kept_records']:,} |")
    if len({json.dumps(r["counts_by_year"], sort_keys=True) for r in results}) > 1:
        print("\nWARNING: engines disagree on the per-year counts; check before using the numbers.")
    summary = {"input": args.input, "input_mb": round(size_mb, 1), "results": results}
    (out_dir / "bench_engines.json").write_text(json.dumps(summary, indent=2) + "\n", "utf-8")


if __name__ == "__main__":
    main()
