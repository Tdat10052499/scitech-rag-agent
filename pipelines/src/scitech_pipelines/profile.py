"""Data profile of the raw and cleaned corpus (W2-D3-FAO-1). Engine: DuckDB (ADR 0005).

`profile` reads the raw arXiv snapshot, the cleaned documents of `clean`, the manifests of
`download` and `clean`, and (if present) the raw Wikipedia pages, and writes the numbers as JSON
and as a Markdown report in which every table says how it was computed. DuckDB runs natively on
Windows, so the profile can run where the data is, without Java.
"""

from __future__ import annotations

import json
import os
import platform
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scitech_pipelines.clean import CLEAN_MANIFEST, DEFAULT_CATEGORY
from scitech_pipelines.validate import documents_glob

QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95, 0.99)
RAW_FIELDS = {
    "id": "VARCHAR",
    "authors": "VARCHAR",
    "title": "VARCHAR",
    "comments": "VARCHAR",
    "journal-ref": "VARCHAR",
    "doi": "VARCHAR",
    "report-no": "VARCHAR",
    "categories": "VARCHAR",
    "license": "VARCHAR",
    "abstract": "VARCHAR",
    "versions": "STRUCT(version VARCHAR, created VARCHAR)[]",
    "update_date": "VARCHAR",
    "authors_parsed": "VARCHAR[][]",
}
WORD_THRESHOLDS = (256, 384, 512)
TOP_CATEGORIES = 15

Log = Callable[[str], None]


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _read_json(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _stats(con, expr: str, table: str) -> dict[str, float]:
    """min, quantiles, max and mean of `expr` over `table`."""
    qs = ", ".join(str(q) for q in QUANTILES)
    row = con.execute(
        f"SELECT min({expr}), quantile_cont({expr}, [{qs}]), max({expr}), avg({expr}) FROM {table}"
    ).fetchone()
    stats = {"min": row[0]}
    stats.update({f"p{round(q * 100)}": value for q, value in zip(QUANTILES, row[1], strict=True)})
    stats.update({"max": row[2], "mean": round(row[3], 1)})
    return stats


def _ram_bytes() -> int | None:
    if hasattr(os, "sysconf"):
        try:
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        except (ValueError, OSError):
            return None
    try:  # Windows
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = (
                [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)]
                + [
                    (name, ctypes.c_ulonglong)
                    for name in ("total", "avail", "page", "avail_page", "virtual", "avail_virtual")
                ]
                + [("avail_extended", ctypes.c_ulonglong)]
            )

        status = MemoryStatus(length=ctypes.sizeof(MemoryStatus))
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return int(status.total)
    except (AttributeError, OSError):
        return None


def _machine() -> dict[str, Any]:
    ram = _ram_bytes()
    return {"platform": platform.platform(), "cpus": os.cpu_count(), "ram_bytes": ram}


def profile_raw(con, raw: Path, category: str) -> dict[str, Any]:
    """Whole-snapshot counts, and missing values of the in-category records before cleaning."""
    path = _quote(raw.as_posix())
    total, distinct = con.execute(
        f"SELECT count(*), count(DISTINCT id) FROM read_json({path}, "
        "format = 'newline_delimited', columns = {'id': 'VARCHAR'}, "
        "maximum_object_size = 10000000)"
    ).fetchone()
    columns = ", ".join(f"{_quote(name)}: {_quote(kind)}" for name, kind in RAW_FIELDS.items())
    con.execute(
        f"CREATE TEMP TABLE raw_cat AS SELECT * FROM read_json({path}, "
        f"format = 'newline_delimited', columns = {{{columns}}}, maximum_object_size = 10000000) "
        f"WHERE list_contains(string_split(trim(categories), ' '), {_quote(category)})"
    )
    n = con.execute("SELECT count(*) FROM raw_cat").fetchone()[0]
    missing = {}
    for name, kind in RAW_FIELDS.items():
        column = f'"{name}"'
        empty = (
            f"{column} IS NULL OR len({column}) = 0"
            if kind.endswith("[]")
            else f"{column} IS NULL OR trim({column}) = ''"
        )
        count = con.execute(f"SELECT count(*) FROM raw_cat WHERE {empty}").fetchone()[0]
        missing[name] = {"missing": count, "rate": round(count / n, 4) if n else None}
    return {
        "file": str(raw),
        "bytes": raw.stat().st_size,
        "records": total,
        "distinct_ids": distinct,
        "in_category": n,
        "missing_in_category": missing,
    }


def profile_documents(con, documents: Path, category: str) -> dict[str, Any]:
    """Counts, sizes and length distributions of the cleaned documents."""
    files = list(documents.glob("year=*/*.parquet"))
    con.execute(
        "CREATE TEMP TABLE docs AS SELECT *, "
        "len(string_split(abstract, ' ')) AS abstract_words, "
        "length(abstract) AS abstract_chars, length(title) AS title_chars, "
        "len(authors) AS n_authors "
        f"FROM read_parquet({_quote(documents_glob(documents))}, hive_partitioning = true)"
    )
    n = con.execute("SELECT count(*) FROM docs").fetchone()[0]
    by_year = [
        {"year": int(y), "records": c, "median_words": m, "p95_words": p}
        for y, c, m, p in con.execute(
            "SELECT year, count(*), quantile_cont(abstract_words, 0.5), "
            "quantile_cont(abstract_words, 0.95) FROM docs GROUP BY year ORDER BY year"
        ).fetchall()
    ]
    listed = con.execute(
        "SELECT c, count(*) AS k FROM (SELECT unnest(categories) AS c FROM docs) "
        f"GROUP BY c ORDER BY k DESC, c LIMIT {TOP_CATEGORIES}"
    ).fetchall()
    primary = con.execute(  # every category, so each listed one finds its primary count
        "SELECT categories[1] AS c, count(*) AS k FROM docs GROUP BY c ORDER BY k DESC, c"
    ).fetchall()
    cross = con.execute(
        f"SELECT count(*) FROM docs WHERE categories[1] <> {_quote(category)}"
    ).fetchone()[0]
    over = {
        str(t): con.execute(f"SELECT count(*) FROM docs WHERE abstract_words > {t}").fetchone()[0]
        for t in WORD_THRESHOLDS
    }
    no_authors = con.execute("SELECT count(*) FROM docs WHERE n_authors = 0").fetchone()[0]
    no_update = con.execute("SELECT count(*) FROM docs WHERE updated_at IS NULL").fetchone()[0]
    return {
        "path": str(documents),
        "records": n,
        "parquet_files": len(files),
        "parquet_bytes": sum(f.stat().st_size for f in files),
        "by_year": by_year,
        "categories_listed": [{"category": c, "records": k} for c, k in listed],
        "primary_category": [{"category": c, "records": k} for c, k in primary],
        "cross_listed": cross,
        "abstract_words": _stats(con, "abstract_words", "docs"),
        "abstract_chars": _stats(con, "abstract_chars", "docs"),
        "title_chars": _stats(con, "title_chars", "docs"),
        "authors_per_paper": _stats(con, "n_authors", "docs"),
        "abstracts_over_words": over,
        "missing_after_cleaning": {"authors_empty": no_authors, "updated_at_null": no_update},
    }


def profile_wikipedia(con, wiki: Path) -> dict[str, Any] | None:
    """Pages per depth and category, and text lengths, of the raw Wikipedia download."""
    pages = wiki / "pages.jsonl"
    if not pages.is_file():
        return None
    con.execute(
        "CREATE TEMP TABLE wiki AS SELECT *, len(string_split(trim(text), ' ')) AS words "
        f"FROM read_json({_quote(pages.as_posix())}, format = 'newline_delimited', "
        "columns = {'pageid': 'BIGINT', 'title': 'VARCHAR', 'text': 'VARCHAR', "
        "'depth': 'INTEGER', 'category': 'VARCHAR'}, maximum_object_size = 50000000)"
    )
    by_depth = [
        {"depth": d, "pages": c, "median_words": m}
        for d, c, m in con.execute(
            "SELECT depth, count(*), quantile_cont(words, 0.5) FROM wiki "
            "GROUP BY depth ORDER BY depth"
        ).fetchall()
    ]
    categories = [
        {"category": c, "depth": d, "pages": k}
        for c, d, k in con.execute(
            "SELECT category, depth, count(*) FROM wiki "
            "GROUP BY category, depth ORDER BY depth, count(*) DESC, category"
        ).fetchall()
    ]
    no_text = wiki / "pages_without_text.txt"
    return {
        "pages": con.execute("SELECT count(*) FROM wiki").fetchone()[0],
        "pages_without_text": (
            len(no_text.read_text(encoding="utf-8").split()) if no_text.is_file() else None
        ),
        "words": _stats(con, "words", "wiki"),
        "by_depth": by_depth,
        "categories": categories,
    }


def build_profile(
    raw: Path,
    documents: Path,
    *,
    wiki: Path | None = None,
    category: str = DEFAULT_CATEGORY,
    clean_peak_mb: float | None = None,
    log: Log = print,
) -> dict[str, Any]:
    """Compute every number of the data profile. `clean_peak_mb` is measured outside `clean`."""
    import duckdb

    started = time.monotonic()
    con = duckdb.connect()
    log("profile: cleaned documents")
    docs = profile_documents(con, documents, category)
    log("profile: raw snapshot (one pass for ids, one for the category)")
    raw_profile = profile_raw(con, raw, category)
    wiki_profile = None
    if wiki is not None:
        log("profile: Wikipedia pages")
        wiki_profile = profile_wikipedia(con, wiki)
    con.close()
    clean_manifest = _read_json(documents / CLEAN_MANIFEST)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "category": category,
        "machine": {**_machine(), "duckdb": duckdb.__version__},
        "profile_seconds": round(time.monotonic() - started, 1),
        "clean_peak_mb": clean_peak_mb,
        "download_manifest": _read_json(raw.parent / "manifest.json"),
        "wikipedia_manifest": _read_json(wiki / "manifest.json") if wiki else None,
        "clean_manifest": clean_manifest,
        "raw": raw_profile,
        "documents": docs,
        "wikipedia": wiki_profile,
    }


def _n(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:,.1f}" if value != int(value) else f"{int(value):,}"
    return f"{value:,}" if isinstance(value, int) else str(value)


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "n/a"


def _stats_row(label: str, stats: dict[str, Any]) -> str:
    keys = ["min", *[f"p{round(q * 100)}" for q in QUANTILES], "max", "mean"]
    return f"| {label} | " + " | ".join(_n(stats[k]) for k in keys) + " |"


def render_markdown(p: dict[str, Any]) -> str:
    """The data profile as Markdown. Every section says how its numbers were computed."""
    raw, docs, clean = p["raw"], p["documents"], p["clean_manifest"] or {}
    counts = clean.get("counts", {})
    download = p["download_manifest"] or {}
    machine = p["machine"]
    ram = machine["ram_bytes"]
    ratio = f"{raw['bytes'] / docs['parquet_bytes']:.0f} : 1" if docs["parquet_bytes"] else "n/a"
    lines = [
        "# Data profile",
        "",
        f"Generated by `python -m scitech_pipelines profile` (W2-D3-FAO-1) on {p['created_at']}.",
        "All numbers below come from that command unless a line says otherwise; the raw",
        "numbers are in the JSON file written next to this report.",
        "",
        "## 1. Volume",
        "",
        "| Item | Value |",
        "|---|---:|",
        f"| Snapshot version (Kaggle `Cornell-University/arxiv`) | "
        f"{_n(clean.get('snapshot_version') or download.get('version'))} |",
        f"| Raw snapshot, records | {_n(raw['records'])} |",
        f"| Raw snapshot, size | {_n(raw['bytes'])} bytes |",
        f"| Records with `{p['category']}` (raw) | {_n(raw['in_category'])} |",
        f"| Records after cleaning | {_n(docs['records'])} |",
        f"| Cleaned Parquet, size | {_n(docs['parquet_bytes'])} bytes in "
        f"{docs['parquet_files']} files |",
        f"| Raw snapshot : cleaned Parquet | {ratio} |",
        "",
        "How computed: records by counting the lines of the snapshot with DuckDB; sizes from the "
        "file system (all `*.parquet` files under the cleaned directory). The Parquet holds only "
        f"the `{p['category']}` records, so the ratio mixes filtering and compression.",
        "",
        "## 2. Cleaning: records removed",
        "",
        "| Step | Records |",
        "|---|---:|",
        f"| In category (Spark / DuckDB) | {_n(counts.get('in_category'))} / "
        f"{_n(counts.get('in_category_duckdb'))} |",
        f"| Dropped, no abstract | {_n(counts.get('dropped_no_abstract'))} |",
        f"| Dropped, no title | {_n(counts.get('dropped_no_title'))} |",
        f"| Dropped, no parsable first-version date | {_n(counts.get('dropped_no_date'))} |",
        f"| Duplicates removed (`doc_id`) | {_n(counts.get('duplicates_removed'))} "
        f"({_pct(counts.get('duplicates_removed', 0), counts.get('in_category', 0))}) |",
        f"| Duplicate ids in the whole snapshot | {_n(raw['records'] - raw['distinct_ids'])} |",
        f"| Records out | {_n(counts.get('records_out'))} |",
        "",
        "How computed: from `_clean_manifest.json` written by `clean`; duplicate ids in the whole "
        "snapshot as `count(*) - count(DISTINCT id)` over all records with DuckDB. That row covers "
        f"every category; only duplicates among the `{p['category']}` records are removed by "
        '`clean` (row "Duplicates removed"), so the rest belong to records outside the category.',
        "",
        "## 3. Runtime and hardware",
        "",
        "| Step | Seconds | Machine |",
        "|---|---:|---|",
        f"| download, arXiv (Kaggle zip + extraction + checksums) | "
        f"{_n(download.get('seconds'))} | not recorded in the download manifest |",
        f"| clean (PySpark job, from the manifest) | {_n(clean.get('seconds'))} | "
        f"{clean.get('engine', 'n/a')}, {clean.get('platform', 'n/a')} |",
        f"| profile (this report, DuckDB {machine['duckdb']}) | {_n(p['profile_seconds'])} | "
        f"{machine['platform']}, {machine['cpus']} CPUs"
        + (f", {ram / 1e9:.0f} GB RAM" if ram else "")
        + " |",
        "",
        "How computed: `seconds` fields of the download and clean manifests (wall time measured "
        "by each command, on the machine named in the row); the profile time is measured by "
        "this command. "
        + (
            f"Peak memory of the `clean` run: {_n(p['clean_peak_mb'])} MB, the largest resident "
            "memory of the process and its Spark JVM, sampled every 0.2 s outside the command "
            "(given to `profile` with `--clean-peak-mb`)."
            if p.get("clean_peak_mb")
            else "Peak memory is not measured by these commands."
        ),
        "",
        "## 4. Records per year",
        "",
        "| Year | Records | Median abstract words | p95 abstract words |",
        "|---|---:|---:|---:|",
    ]
    lines += [
        f"| {r['year']} | {_n(r['records'])} | {_n(r['median_words'])} | {_n(r['p95_words'])} |"
        for r in docs["by_year"]
    ]
    lines += [
        "",
        "How computed: cleaned documents grouped by `year` (year of the first version); words "
        "are the abstract split on single spaces (whitespace is normalised by `clean`), "
        "quantiles with DuckDB `quantile_cont`.",
        "",
        "## 5. Categories",
        "",
        f"Cross-listed (primary category is not `{p['category']}`): "
        f"{_n(docs['cross_listed'])} of {_n(docs['records'])} "
        f"({_pct(docs['cross_listed'], docs['records'])}).",
        "",
        "| Category | Records listing it | Share | Records with it as primary | Share |",
        "|---|---:|---:|---:|---:|",
    ]
    primary = {r["category"]: r["records"] for r in docs["primary_category"]}
    for r in docs["categories_listed"]:
        first = primary.get(r["category"], 0)
        lines.append(
            f"| `{r['category']}` | {_n(r['records'])} | {_pct(r['records'], docs['records'])} | "
            f"{_n(first)} | {_pct(first, docs['records'])} |"
        )
    lines += [
        "",
        f"How computed: the {TOP_CATEGORIES} categories listed most often in `categories`; "
        "primary = the first category in the list, as arXiv orders it (all primary categories "
        "are in the JSON file). A paper lists several categories, so the shares add up to more "
        "than 100%.",
        "",
        "## 6. Lengths",
        "",
        "| Measure | min | p5 | p25 | median | p75 | p95 | p99 | max | mean |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        _stats_row("Abstract, words", docs["abstract_words"]),
        _stats_row("Abstract, characters", docs["abstract_chars"]),
        _stats_row("Title, characters", docs["title_chars"]),
        _stats_row("Authors per paper", docs["authors_per_paper"]),
        "",
        "Abstracts longer than: "
        + ", ".join(
            f"{t} words {_n(c)} ({_pct(c, docs['records'])})"
            for t, c in docs["abstracts_over_words"].items()
        )
        + ".",
        "",
        "How computed: over all cleaned documents with DuckDB; words as in section 4, "
        "characters with `length`. Token counts depend on the embedding model's tokenizer and "
        "are measured by the chunker (W3-D1-FAO-1), not here.",
        "",
        "## 7. Missing values",
        "",
        f"Raw `{p['category']}` records before cleaning ({_n(raw['in_category'])} records):",
        "",
        "| Field | Missing | Rate |",
        "|---|---:|---:|",
    ]
    for name, m in raw["missing_in_category"].items():
        rate = f"{100 * m['rate']:.2f}%" if m["rate"] is not None else "n/a"
        lines.append(f"| `{name}` | {_n(m['missing'])} | {rate} |")
    after = docs["missing_after_cleaning"]
    lines += [
        "",
        f"After cleaning: `authors` empty in {_n(after['authors_empty'])} records, "
        f"`updated_at` null in {_n(after['updated_at_null'])}; `doc_id`, `title`, `abstract` and "
        "`published_at` are never missing (checked by `validate`, W2-D4-FAO-1).",
        "",
        "How computed: a field is missing when it is null, empty or only whitespace (lists: "
        "null or empty), over the raw records that list the category, read with DuckDB.",
    ]
    wiki = p["wikipedia"]
    if wiki:
        manifest = p["wikipedia_manifest"] or {}
        lines += [
            "",
            "## 8. Wikipedia (raw, not cleaned)",
            "",
            f"{_n(wiki['pages'])} pages with text, {_n(wiki['pages_without_text'])} without "
            f"text; download time {_n(manifest.get('seconds'))} s.",
            "",
            "| Depth | Pages | Median words |",
            "|---:|---:|---:|",
        ]
        lines += [
            f"| {r['depth']} | {_n(r['pages'])} | {_n(r['median_words'])} |"
            for r in wiki["by_depth"]
        ]
        lines += [
            "",
            "| Measure | min | p5 | p25 | median | p75 | p95 | p99 | max | mean |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            _stats_row("Page text, words", wiki["words"]),
            "",
            "Categories with pages (depth 0 is the root category; pages first found there):",
            "",
            "| Category | Depth | Pages |",
            "|---|---:|---:|",
        ]
        lines += [
            f"| {r['category']} | {r['depth']} | {_n(r['pages'])} |" for r in wiki["categories"]
        ]
        lines += [
            "",
            "How computed: `pages.jsonl` of the download, each page with the depth and category "
            "where the crawl first found it; words as in section 4 after trimming. Whether a "
            "category is on topic is a judgement made from this list, not computed.",
        ]
    return "\n".join(lines) + "\n"


def run_profile(
    raw: Path,
    documents: Path,
    out: Path,
    *,
    wiki: Path | None = None,
    category: str = DEFAULT_CATEGORY,
    clean_peak_mb: float | None = None,
    log: Log = print,
) -> dict[str, Any]:
    """Build the profile and write `<out>` (Markdown) and `<out>.json`."""
    for path, step in ((raw, "download"), (documents / CLEAN_MANIFEST, "clean")):
        if not path.is_file():
            raise FileNotFoundError(f"{path} not found (run `{step}` first)")
    profile = build_profile(
        raw, documents, wiki=wiki, category=category, clean_peak_mb=clean_peak_mb, log=log
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(profile), encoding="utf-8")
    json_out = out.with_suffix(".json")
    json_out.write_text(json.dumps(profile, indent=2, default=str) + "\n", encoding="utf-8")
    log(f"profile: {out} and {json_out.name} written in {profile['profile_seconds']} s")
    return profile
