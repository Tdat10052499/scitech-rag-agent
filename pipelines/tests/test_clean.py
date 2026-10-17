import json
from datetime import date
from pathlib import Path

import pytest

from scitech_pipelines import clean
from scitech_pipelines.cli import build_parser

FIXTURE = Path(__file__).parent / "fixtures" / "sample.jsonl"


def fixture_records() -> list[dict]:
    return [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]


def record(doc_id: str, **fields) -> dict:
    base = {
        "id": doc_id,
        "authors": "Ada Lovelace and Alan Turing",
        "title": "A title",
        "categories": "cs.CL",
        "license": None,
        "abstract": "An abstract.",
        "versions": [{"version": "v1", "created": "Mon, 2 Apr 2007 19:18:42 GMT"}],
        "update_date": "2007-04-03",
    }
    return {**base, **fields}


def write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


# --- without Spark --------------------------------------------------------------------------


def test_java_executable_prefers_java_home(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "java").write_text("")
    monkeypatch.setenv("JAVA_HOME", str(tmp_path))
    monkeypatch.setattr(clean.shutil, "which", lambda name: "/usr/bin/java")
    assert clean.java_executable() == str(tmp_path / "bin" / "java")
    monkeypatch.delenv("JAVA_HOME")
    assert clean.java_executable() == "/usr/bin/java"


@pytest.mark.parametrize(
    ("output", "major"),
    [
        ('java version "1.8.0_402"\nJava(TM) SE Runtime Environment', 8),
        ('openjdk version "17.0.20.1" 2026-07-21\nOpenJDK Runtime Environment', 17),
        ('openjdk version "21" 2023-09-19', 21),
        ("not java", None),
    ],
)
def test_java_major_version(monkeypatch, output: str, major: int | None) -> None:
    def run(cmd, **kwargs):
        assert cmd == ["java", "-version"]
        return clean.subprocess.CompletedProcess(cmd, 0, stdout="", stderr=output)

    monkeypatch.setattr(clean.subprocess, "run", run)
    assert clean.java_major_version("java") == major


def test_java_major_version_when_java_cannot_start(monkeypatch) -> None:
    def run(cmd, **kwargs):
        raise OSError("broken")

    monkeypatch.setattr(clean.subprocess, "run", run)
    assert clean.java_major_version("java") is None


@pytest.mark.parametrize(("major", "ok"), [(8, False), (11, False), (17, True), (21, True)])
def test_java_available_needs_java_17(monkeypatch, major: int, ok: bool) -> None:
    monkeypatch.setattr(clean, "java_executable", lambda: "java")
    monkeypatch.setattr(clean, "java_major_version", lambda java: major)
    assert clean.java_available() is ok


def test_create_spark_without_java_says_where_to_run(monkeypatch) -> None:
    monkeypatch.setattr(clean, "java_executable", lambda: None)
    with pytest.raises(RuntimeError, match="none was found.*WSL2, Colab or a Kaggle notebook"):
        clean.create_spark()


def test_create_spark_with_old_java_names_the_version(monkeypatch) -> None:
    monkeypatch.setattr(clean, "java_executable", lambda: "C:/java8/bin/java.exe")
    monkeypatch.setattr(clean, "java_major_version", lambda java: 8)
    with pytest.raises(RuntimeError, match="found Java 8 at C:/java8/bin/java.exe"):
        clean.create_spark()


def test_cli_clean_defaults_follow_data_dir() -> None:
    args = build_parser().parse_args(["--data-dir", "d", "clean", "--sample-size", "5"])
    assert args.command == "clean"
    assert args.input is None and args.out is None
    assert args.category == "cs.CL"
    assert args.sample_size == 5
    assert not args.skip_duckdb_check


def test_duckdb_counts_category_records(tmp_path: Path) -> None:
    pytest.importorskip("duckdb")
    src = write_jsonl(
        tmp_path / "in.jsonl",
        [record("1"), record("2", categories="cs.LG  cs.CL"), record("3", categories="cs.CLX")],
    )
    assert clean.duckdb_category_count(str(src), "cs.CL") == 2


# --- with Spark (skipped without PySpark or Java, ADR 0005) --------------------------------


@pytest.fixture(scope="module")
def spark():
    pytest.importorskip("pyspark")
    if not clean.java_available():
        pytest.skip("Java not found: Spark tests run in CI (ADR 0005)")
    session = clean.create_spark("local[1]", "1g")
    yield session
    session.stop()


def read_parquet(spark, path: Path) -> dict[str, dict]:
    return {row["doc_id"]: row.asDict() for row in spark.read.parquet(str(path)).collect()}


def test_clean_fixture_end_to_end(spark, tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    src = write_jsonl(raw_dir / clean.ARXIV_FILE, fixture_records())
    (raw_dir / "manifest.json").write_text(json.dumps({"version": 307}), encoding="utf-8")
    out = tmp_path / "documents"

    manifest = clean.clean_arxiv(spark, src, out, sample_out=tmp_path / "sample", log=lambda _: 0)

    counts = manifest["counts"]
    assert counts["records_in"] == counts["in_category"] == counts["records_out"] == 20
    assert counts["in_category_duckdb"] in (20, None)
    assert manifest["snapshot_version"] == 307
    assert sum(manifest["records_by_year"].values()) == 20
    assert sorted(p.name for p in out.glob("year=*")) == [
        f"year={y}" for y in sorted(manifest["records_by_year"])
    ]
    assert all(len(list(d.glob("*.parquet"))) == 1 for d in out.glob("year=*"))
    assert json.loads((out / clean.CLEAN_MANIFEST).read_text(encoding="utf-8")) == manifest

    docs = read_parquet(spark, out)
    assert set(spark.read.parquet(str(out)).columns) == set(clean.COLUMNS)
    doc = docs["2205.05433"]
    assert doc["title"] == (
        "ALIGNMEET: A Comprehensive Tool for Meeting Annotation, Alignment, and Evaluation"
    )
    assert doc["abstract"].startswith("Summarization is a challenging problem, and even")
    assert "\n" not in doc["abstract"] and "  " not in doc["abstract"]
    assert doc["authors"][0] == "Peter Pol\\'ak" and len(doc["authors"]) == 4
    assert doc["categories"] == ["cs.CL"]
    assert doc["published_at"] == date(2022, 5, 11) and doc["year"] == 2022
    assert doc["updated_at"] == date(2022, 5, 12)
    assert doc["url"] == "https://arxiv.org/abs/2205.05433"
    assert doc["license"] == "CC0-1.0" and doc["source"] == "arxiv"
    assert docs["2404.03653"]["published_at"] == date(2024, 4, 4)  # one-digit day

    sample = spark.read.parquet(str(tmp_path / "sample"))
    assert sample.count() == 20 and manifest["sample"]["records"] == 20


def test_clean_filters_drops_and_deduplicates(spark, tmp_path: Path) -> None:
    newer = record(
        "dup",
        title="Second  version\n title",
        versions=[
            {"version": "v1", "created": "Mon, 2 Apr 2007 19:18:42 GMT"},
            {"version": "v2", "created": "Tue, 1 May 2007 10:00:00 GMT"},
        ],
        update_date="2007-05-02",
        authors_parsed=[["Lovelace", "Ada", ""], ["Turing", "Alan", "Jr"]],
    )
    src = write_jsonl(
        tmp_path / "in.jsonl",
        [
            record("keep", authors="A. One, B. Two, and C. Three"),
            record("other", categories="cs.LG stat.ML"),
            record("blank", abstract="  \n "),
            record("notitle", title=None),
            record("nodate", versions=[{"version": "v1", "created": "unknown"}]),
            record("noversions", versions=[]),
            record("dup", title="First version"),
            newer,
        ],
    )
    out = tmp_path / "documents"

    manifest = clean.clean_arxiv(spark, src, out, sample_size=0, log=lambda _: 0)

    assert manifest["counts"] == {
        "records_in": 8,
        "in_category": 7,
        "in_category_duckdb": manifest["counts"]["in_category_duckdb"],
        "dropped_no_abstract": 1,
        "dropped_no_title": 1,
        "dropped_no_date": 2,
        "duplicates_removed": 1,
        "records_out": 2,
    }
    assert manifest["sample"] is None
    docs = read_parquet(spark, out)
    assert set(docs) == {"keep", "dup"}
    assert docs["keep"]["authors"] == ["A. One", "B. Two", "C. Three"]
    assert docs["dup"]["title"] == "Second version title"
    assert docs["dup"]["authors"] == ["Ada Lovelace", "Alan Turing Jr"]
    assert docs["dup"]["published_at"] == date(2007, 4, 2)

    # Re-running replaces the output instead of appending to it.
    clean.clean_arxiv(spark, src, out, sample_size=0, duckdb_check=False, log=lambda _: 0)
    assert len(read_parquet(spark, out)) == 2


def test_clean_fails_loudly_when_a_field_changes_type(spark, tmp_path: Path) -> None:
    src = write_jsonl(tmp_path / "in.jsonl", [record("1", versions="v1")])
    with pytest.raises(Exception, match="(?i)malformed|FAILFAST"):
        clean.clean_arxiv(
            spark, src, tmp_path / "out", duckdb_check=False, sample_size=0, log=lambda _: 0
        )


def test_clean_missing_input_names_the_download_step(spark, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="download"):
        clean.clean_arxiv(spark, tmp_path / "missing.json", tmp_path / "out", log=lambda _: 0)
