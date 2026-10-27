"""Data quality checks on the cleaned documents (W2-D4-FAO-1). Engine: DuckDB (ADR 0005).

`validate` reads the Parquet output of `clean` (`<dir>/year=<year>/*.parquet`) and runs every check
on the whole dataset: schema, required fields, unique `doc_id`, dates, sub-domain, fixed values
(source, licence, URL), record count against `_clean_manifest.json`, and optionally that every
`relevant_doc_ids` of golden-set files exists (W2-D3-LDN-1). DuckDB runs natively on Windows, so
this step needs no Java.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from scitech_pipelines.clean import ABS_URL, CLEAN_MANIFEST, DEFAULT_CATEGORY, METADATA_LICENSE

# Column -> accepted DuckDB types. `year` comes from the partition directory name.
SCHEMA: dict[str, tuple[str, ...]] = {
    "doc_id": ("VARCHAR",),
    "source": ("VARCHAR",),
    "title": ("VARCHAR",),
    "abstract": ("VARCHAR",),
    "authors": ("VARCHAR[]",),
    "categories": ("VARCHAR[]",),
    "published_at": ("DATE",),
    "updated_at": ("DATE",),
    "url": ("VARCHAR",),
    "license": ("VARCHAR",),
    "year": ("BIGINT", "INTEGER"),
}
FIRST_DATE = date(1990, 1, 1)  # before arXiv (1991), so any earlier date is a parsing error
VERSION_SUFFIX = r"v[0-9]+$"
SAMPLE_IDS = 5

Log = Callable[[str], None]


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str
    skipped: bool = False  # shown as SKIP; counts as passed


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def documents_glob(path: Path) -> str:
    return (path / "**" / "*.parquet").as_posix()


def _violations(con, where: str) -> tuple[int, list[str]]:
    """Number of documents matching `where`, and a few of their ids for the report."""
    total = con.execute(f"SELECT count(*) FROM docs WHERE {where}").fetchone()[0]
    ids = [
        str(row[0])
        for row in con.execute(
            f"SELECT doc_id FROM docs WHERE {where} ORDER BY doc_id LIMIT {SAMPLE_IDS}"
        ).fetchall()
    ]
    return int(total), ids


def _row_check(con, name: str, where: str) -> Check:
    count, ids = _violations(con, where)
    if count == 0:
        return Check(name, True, "no violations")
    return Check(name, False, f"{count:,} records, e.g. {', '.join(ids)}")


def read_golden_doc_ids(paths: Iterable[Path]) -> dict[str, list[str]]:
    """`relevant_doc_ids` of every golden item, keyed by `<file>:<item id>`."""
    wanted: dict[str, list[str]] = {}
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                key = f"{Path(path).name}:{item.get('id')}"
                wanted[key] = list(item.get("relevant_doc_ids", []))
    return wanted


def validate_documents(
    path: Path,
    *,
    category: str = DEFAULT_CATEGORY,
    golden: Sequence[Path] = (),
    today: date | None = None,
) -> tuple[int, list[Check]]:
    """Run every check on the cleaned documents in `path`. Returns (records, checks)."""
    import duckdb

    if not any(path.glob("year=*/*.parquet")):
        raise FileNotFoundError(f"no cleaned documents in {path} (run `clean` first)")
    today = today or date.today()
    con = duckdb.connect()
    con.execute(
        "CREATE VIEW docs AS SELECT * FROM read_parquet("
        f"{_quote(documents_glob(path))}, hive_partitioning = true)"
    )
    records = int(con.execute("SELECT count(*) FROM docs").fetchone()[0])
    checks: list[Check] = []

    types = {name: kind for name, kind, *_ in con.execute("DESCRIBE docs").fetchall()}
    wrong = [
        f"{col}: {types.get(col, 'missing')}"
        for col, accepted in SCHEMA.items()
        if types.get(col) not in accepted
    ]
    extra = sorted(set(types) - set(SCHEMA))
    problems = wrong + [f"unexpected column {c}" for c in extra]
    detail = "; ".join(problems) or f"{len(SCHEMA)} columns"
    checks.append(Check("schema", not wrong and not extra, detail))
    if wrong:  # the row checks below assume the schema
        return records, checks

    checks.append(Check("records", records > 0, f"{records:,} records"))
    for field in ("doc_id", "title", "abstract"):
        checks.append(_row_check(con, f"{field} present", f"{field} IS NULL OR trim({field}) = ''"))
    checks.append(
        _row_check(
            con, "doc_id without version suffix", f"regexp_matches(doc_id, '{VERSION_SUFFIX}')"
        )
    )
    duplicates = con.execute(
        "SELECT count(*), coalesce(sum(n), 0) FROM "
        "(SELECT doc_id, count(*) AS n FROM docs GROUP BY doc_id HAVING count(*) > 1)"
    ).fetchone()
    checks.append(
        Check(
            "doc_id unique",
            duplicates[0] == 0,
            f"{int(duplicates[0]):,} duplicated ids ({int(duplicates[1]):,} records)",
        )
    )
    checks.append(
        _row_check(
            con,
            "published_at valid",
            f"published_at IS NULL OR published_at < DATE '{FIRST_DATE}' "
            f"OR published_at > DATE '{today}'",
        )
    )
    checks.append(_row_check(con, "year matches published_at", "year <> year(published_at)"))
    checks.append(
        _row_check(
            con,
            "updated_at valid",
            f"updated_at IS NOT NULL AND (updated_at < DATE '{FIRST_DATE}' "
            f"OR updated_at > DATE '{today}')",
        )
    )
    checks.append(
        _row_check(
            con, f"in sub-domain {category}", f"NOT list_contains(categories, {_quote(category)})"
        )
    )
    checks.append(
        _row_check(
            con,
            "fixed values (source, license, url)",
            f"source <> 'arxiv' OR license <> {_quote(METADATA_LICENSE)} "
            f"OR url <> {_quote(ABS_URL)} || doc_id",
        )
    )

    manifest = path / CLEAN_MANIFEST
    if manifest.is_file():
        expected = json.loads(manifest.read_text(encoding="utf-8"))["counts"]["records_out"]
        checks.append(
            Check(
                "count matches clean manifest",
                expected == records,
                f"manifest {expected:,}, Parquet {records:,}",
            )
        )
    else:
        checks.append(
            Check("count matches clean manifest", True, f"no {CLEAN_MANIFEST}", skipped=True)
        )

    if golden:
        wanted = read_golden_doc_ids(golden)
        ids = sorted({doc for docs in wanted.values() for doc in docs})
        con.execute("CREATE TEMP TABLE wanted (doc_id VARCHAR)")
        con.executemany("INSERT INTO wanted VALUES (?)", [(i,) for i in ids])
        missing = {
            row[0]
            for row in con.execute(
                "SELECT doc_id FROM wanted w "
                "WHERE NOT EXISTS (SELECT 1 FROM docs d WHERE d.doc_id = w.doc_id)"
            ).fetchall()
        }
        items = [
            f"{item} ({doc})" for item, docs in wanted.items() for doc in docs if doc in missing
        ]
        checks.append(
            Check(
                "golden doc ids exist",
                not missing,
                f"{len(ids)} ids in {len(wanted)} items, all found"
                if not missing
                else f"{len(missing)} of {len(ids)} ids missing: {', '.join(items[:10])}"
                + (" ..." if len(items) > 10 else ""),
            )
        )
    con.close()
    return records, checks


def run_validate(
    path: Path,
    *,
    category: str = DEFAULT_CATEGORY,
    golden: Sequence[Path] = (),
    log: Log = print,
) -> bool:
    """Validate and print one line per check. Returns True if every check passed."""
    records, checks = validate_documents(path, category=category, golden=golden)
    width = max(len(c.name) for c in checks)
    log(f"validate: {path} ({records:,} records)")
    for check in checks:
        status = "SKIP" if check.skipped else "PASS" if check.passed else "FAIL"
        log(f"  {status}  {check.name:<{width}}  {check.detail}")
    failed = [c.name for c in checks if not c.passed]
    log(
        "validate: all checks passed"
        if not failed
        else f"validate: {len(failed)} check(s) failed: {', '.join(failed)}"
    )
    return not failed
