"""Clean the raw arXiv snapshot into Parquet (W2-D2-FAO-1). Engine: PySpark, local mode (ADR 0005).

Steps, in order:
1. Read the Kaggle snapshot (JSON Lines) with an explicit schema in FAILFAST mode, so a changed
   field type stops the run instead of turning into nulls.
2. Keep records whose `categories` contain the sub-domain category (`cs.CL` by default; ADR 0003).
   Filtering first means the later shuffle covers about 120k records instead of 3.2M.
3. Normalise: whitespace in title and abstract, authors as a list of names, categories as a list,
   `published_at` from the first version, `updated_at`, the abstract page URL, and the licence of
   title and abstract (`CC0-1.0`; the snapshot's own `license` field is the e-print licence).
4. Drop records without abstract, title or a parsable first-version date (counted separately).
5. De-duplicate by `doc_id`, keeping the latest record (latest `update_date`, then most versions).
   The snapshot holds one record per arXiv id with every version listed, so this only acts if
   Kaggle repeats an id.
6. Write Parquet to `<out>/year=<year>/`, a small sample for golden-set writing, and
   `<out>/_clean_manifest.json` with the record counts (Spark and DuckDB skip `_` files).

DuckDB counts the in-category records of the same file independently; a mismatch fails the run
(ADR 0005, reproducibility check).
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyspark.sql import Column, DataFrame, SparkSession
    from pyspark.sql.types import StructType

ARXIV_FILE = "arxiv-metadata-oai-snapshot.json"
DEFAULT_CATEGORY = "cs.CL"
METADATA_LICENSE = "CC0-1.0"
ABS_URL = "https://arxiv.org/abs/"
CLEAN_MANIFEST = "_clean_manifest.json"
DEFAULT_SAMPLE_SIZE = 200
# "Wed, 11 May 2022 12:16:56 GMT" -> "11 May 2022". Spark parses day names only when formatting.
FIRST_VERSION_DATE = r"(\d{1,2} [A-Za-z]{3} \d{4})"
COLUMNS = (
    "doc_id",
    "source",
    "title",
    "abstract",
    "authors",
    "categories",
    "published_at",
    "updated_at",
    "url",
    "license",
    "year",
)

Log = Callable[[str], None]


def java_available() -> bool:
    """True if a `java` executable is on JAVA_HOME or PATH (PySpark needs Java 17+)."""
    home = os.environ.get("JAVA_HOME")
    if home and any((Path(home) / "bin" / name).is_file() for name in ("java", "java.exe")):
        return True
    return shutil.which("java") is not None


def snapshot_schema() -> StructType:
    """Explicit schema of the Kaggle arXiv snapshot. `submitter` is not read (personal data)."""
    from pyspark.sql.types import ArrayType, StringType, StructField, StructType

    def text(name: str) -> StructField:
        return StructField(name, StringType())

    version = StructType([text("version"), text("created")])
    return StructType(
        [
            text("id"),
            text("authors"),
            text("title"),
            text("comments"),
            text("journal-ref"),
            text("doi"),
            text("report-no"),
            text("categories"),
            text("license"),
            text("abstract"),
            StructField("versions", ArrayType(version)),
            text("update_date"),
            StructField("authors_parsed", ArrayType(ArrayType(StringType()))),
        ]
    )


def create_spark(master: str = "local[*]", driver_memory: str = "4g") -> SparkSession:
    """Start a local Spark session. Fails early with a clear message when Java is missing."""
    if not java_available():
        raise RuntimeError(
            "PySpark needs Java 17 or newer and none was found (JAVA_HOME or PATH). "
            "`clean` does not run natively on Windows: use WSL2, Colab or a Kaggle notebook "
            "(pipelines/AGENTS.md, ADR 0005)."
        )
    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.master(master)
        .appName("scitech-clean")
        .config("spark.driver.memory", driver_memory)
        .config("spark.ui.enabled", "false")
        .config("spark.ui.showConsoleProgress", "false")
        .config("spark.sql.shuffle.partitions", "16")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


def read_snapshot(spark: SparkSession, path: str) -> DataFrame:
    return spark.read.schema(snapshot_schema()).option("mode", "FAILFAST").json(path)


def _text(column: str) -> Column:
    """Collapse whitespace (the snapshot wraps lines) and turn empty strings into null."""
    from pyspark.sql import functions as F

    value = F.trim(F.regexp_replace(F.col(column), r"\s+", " "))
    return F.when(value != "", value)


def _authors() -> Column:
    """Author names as "First Last Suffix" from `authors_parsed`, else split the `authors` text.

    LaTeX accents (e.g. `Pol\\'ak`) are kept as in the snapshot.
    """
    from pyspark.sql import functions as F

    def part(name: Column, index: int) -> Column:
        return F.try_element_at(name, F.lit(index))

    parsed = F.transform(
        "authors_parsed",
        lambda n: F.trim(F.concat_ws(" ", part(n, 2), part(n, 1), part(n, 3))),
    )
    text = F.split(F.regexp_replace("authors", r"\s+", " "), r",\s*(?:and\s+)?|\s+and\s+")
    names = F.coalesce(parsed, text)
    return F.filter(F.transform(names, lambda n: F.trim(n)), lambda n: n != "")


def in_category(category: str) -> Column:
    from pyspark.sql import functions as F

    return F.array_contains(F.split(F.trim(F.col("categories")), r"\s+"), category)


def normalise(raw: DataFrame) -> DataFrame:
    """Map snapshot records to the cleaned document columns (plus `n_versions` for de-dup)."""
    from pyspark.sql import functions as F

    first_created = F.try_element_at("versions", F.lit(1))["created"]
    published = F.try_to_date(F.regexp_extract(first_created, FIRST_VERSION_DATE, 1), "d MMM yyyy")
    return raw.select(
        F.trim("id").alias("doc_id"),
        F.lit("arxiv").alias("source"),
        _text("title").alias("title"),
        _text("abstract").alias("abstract"),
        _authors().alias("authors"),
        F.split(F.trim(F.col("categories")), r"\s+").alias("categories"),
        published.alias("published_at"),
        F.try_to_date(F.col("update_date"), "yyyy-MM-dd").alias("updated_at"),
        F.concat(F.lit(ABS_URL), F.trim("id")).alias("url"),
        F.lit(METADATA_LICENSE).alias("license"),
        F.year(published).alias("year"),
        F.coalesce(F.size("versions"), F.lit(0)).alias("n_versions"),
    )


def deduplicate(docs: DataFrame) -> DataFrame:
    """Keep one record per `doc_id`: latest `updated_at`, then most versions."""
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    latest = Window.partitionBy("doc_id").orderBy(
        F.col("updated_at").desc_nulls_last(), F.col("n_versions").desc()
    )
    return (
        docs.withColumn("_rank", F.row_number().over(latest))
        .where(F.col("_rank") == 1)
        .drop("_rank")
    )


def duckdb_category_count(path: str, category: str) -> int:
    """Count in-category records with DuckDB, independently of Spark (ADR 0005)."""
    import duckdb

    def quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    query = f"""
        SELECT count(*)
        FROM read_json({quote(path)}, format = 'newline_delimited',
                       columns = {{'id': 'VARCHAR', 'categories': 'VARCHAR'}},
                       maximum_object_size = 10000000)
        WHERE list_contains(string_split(trim(categories), ' '), {quote(category)})
    """
    with duckdb.connect() as con:
        return int(con.execute(query).fetchone()[0])


def _snapshot_version(src: Path) -> Any:
    """Kaggle dataset version from the downloader's manifest next to the snapshot, if any."""
    manifest = src.parent / "manifest.json"
    if not manifest.is_file():
        return None
    return json.loads(manifest.read_text(encoding="utf-8")).get("version")


def clean_arxiv(
    spark: SparkSession,
    src: Path,
    out: Path,
    *,
    category: str = DEFAULT_CATEGORY,
    sample_out: Path | None = None,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    duckdb_check: bool = True,
    snapshot_version: Any = None,
    log: Log = print,
) -> dict[str, Any]:
    """Clean the snapshot at `src` into `<out>/year=<year>/` and return the manifest."""
    from pyspark.sql import functions as F

    if not src.is_file():
        raise FileNotFoundError(f"arXiv snapshot not found: {src} (run `download` first)")
    started = time.monotonic()
    raw = read_snapshot(spark, str(src))

    # Pass 1 reads only `id` and `categories` (Spark prunes JSON columns).
    totals = raw.select(
        F.count(F.lit(1)).alias("records_in"),
        F.count("id").alias("with_id"),
        F.sum(in_category(category).cast("int")).alias("in_category"),
    ).first()
    records_in, with_id = totals["records_in"], totals["with_id"]
    category_count = totals["in_category"] or 0
    log(f"clean: {records_in:,} records in, {category_count:,} with {category}")
    if with_id != records_in:
        raise ValueError(
            f"{records_in - with_id:,} records have no `id`: has the snapshot format changed?"
        )
    duckdb_count = None
    if duckdb_check:
        duckdb_count = duckdb_category_count(str(src), category)
        if duckdb_count != category_count:
            raise RuntimeError(
                f"Spark and DuckDB disagree on the {category} count: "
                f"{category_count:,} vs {duckdb_count:,}"
            )
        log(f"clean: DuckDB agrees ({duckdb_count:,} records with {category})")

    # Pass 2: the in-category records, cached for the counts, de-dup, write and sample.
    docs = normalise(raw.where(in_category(category))).cache()
    no_abstract = F.col("abstract").isNull()
    no_title = ~no_abstract & F.col("title").isNull()
    no_date = ~no_abstract & ~no_title & F.col("published_at").isNull()
    drops = docs.select(
        F.sum(no_abstract.cast("int")).alias("no_abstract"),
        F.sum(no_title.cast("int")).alias("no_title"),
        F.sum(no_date.cast("int")).alias("no_date"),
    ).first()
    valid = docs.where(
        F.col("abstract").isNotNull()
        & F.col("title").isNotNull()
        & F.col("published_at").isNotNull()
    )
    valid_count = valid.count()
    final = deduplicate(valid).select(*COLUMNS).cache()
    by_year = {
        str(row["year"]): row["count"]
        for row in final.groupBy("year").count().orderBy("year").collect()
    }
    records_out = sum(by_year.values())

    # One file per year (at most about 25k records each) instead of one per shuffle partition.
    final.repartition("year").write.mode("overwrite").partitionBy("year").parquet(str(out))
    sample_count = 0
    if sample_out is not None and sample_size > 0:
        # A fixed hash order spreads the sample over all years and gives the same records on
        # every run of the same snapshot.
        sample = final.orderBy(F.xxhash64("doc_id"), "doc_id").limit(sample_size)
        sample.coalesce(1).write.mode("overwrite").parquet(str(sample_out))
        sample_count = min(sample_size, records_out)
    docs.unpersist()
    final.unpersist()

    manifest = {
        "step": "clean",
        "source": "arxiv",
        "input": str(src),
        "input_bytes": src.stat().st_size,
        "snapshot_version": snapshot_version or _snapshot_version(src),
        "category": category,
        "cleaned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seconds": round(time.monotonic() - started, 1),
        "engine": f"pyspark {spark.version} ({spark.sparkContext.master})",
        "platform": platform.platform(),
        "counts": {
            "records_in": records_in,
            "in_category": category_count,
            "in_category_duckdb": duckdb_count,
            "dropped_no_abstract": drops["no_abstract"] or 0,
            "dropped_no_title": drops["no_title"] or 0,
            "dropped_no_date": drops["no_date"] or 0,
            "duplicates_removed": valid_count - records_out,
            "records_out": records_out,
        },
        "records_by_year": by_year,
        "sample": {"path": str(sample_out), "records": sample_count} if sample_count else None,
    }
    (out / CLEAN_MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    counts = manifest["counts"]
    log(
        f"clean: dropped {counts['dropped_no_abstract']:,} without abstract, "
        f"{counts['dropped_no_title']:,} without title, {counts['dropped_no_date']:,} without "
        f"date, {counts['duplicates_removed']:,} duplicates"
    )
    log(f"clean: {records_out:,} records out in {manifest['seconds']} s -> {out}")
    if sample_count:
        log(f"clean: sample of {sample_count} records -> {sample_out}")
    return manifest
