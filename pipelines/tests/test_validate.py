import json
from datetime import date
from pathlib import Path

import pytest

from scitech_pipelines import clean
from scitech_pipelines.cli import main
from scitech_pipelines.validate import run_validate, validate_documents

duckdb = pytest.importorskip("duckdb")

FIXTURE = Path(__file__).parent / "fixtures" / "sample.jsonl"
TODAY = date(2026, 10, 16)


def doc(doc_id: str, **fields) -> dict:
    base = {
        "doc_id": doc_id,
        "source": "arxiv",
        "title": "A title",
        "abstract": "An abstract.",
        "authors": ["Ada Lovelace"],
        "categories": ["cs.CL", "cs.LG"],
        "published_at": "2024-04-04",
        "updated_at": "2024-05-01",
        "url": f"https://arxiv.org/abs/{doc_id}",
        "license": "CC0-1.0",
        "year": 2024,
    }
    return {**base, **fields}


def write_documents(out: Path, docs: list[dict], records_out: int | None = None) -> Path:
    """Write documents the way `clean` does: Parquet partitioned by `year`, plus the manifest."""
    src = out.parent / "docs.json"
    src.write_text(json.dumps(docs), encoding="utf-8")
    con = duckdb.connect()
    con.execute(
        f"""
        COPY (
            SELECT doc_id, source, title, abstract, authors, categories,
                   CAST(published_at AS DATE) AS published_at,
                   CAST(updated_at AS DATE) AS updated_at, url, license, year
            FROM read_json('{src.as_posix()}', columns = {{
                doc_id: 'VARCHAR', source: 'VARCHAR', title: 'VARCHAR', abstract: 'VARCHAR',
                authors: 'VARCHAR[]', categories: 'VARCHAR[]', published_at: 'VARCHAR',
                updated_at: 'VARCHAR', url: 'VARCHAR', license: 'VARCHAR', year: 'INTEGER'}})
        ) TO '{out.as_posix()}' (FORMAT parquet, PARTITION_BY (year))
        """
    )
    con.close()
    if records_out is not None:
        manifest = {"counts": {"records_out": records_out}}
        (out / clean.CLEAN_MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    return out


def results(path: Path, **kwargs) -> dict[str, tuple[bool, str]]:
    records, checks = validate_documents(path, today=TODAY, **kwargs)
    return {c.name: (c.passed, c.detail) for c in checks}


def failed(path: Path, **kwargs) -> set[str]:
    return {name for name, (ok, _) in results(path, **kwargs).items() if not ok}


def test_valid_documents_pass_every_check(tmp_path: Path) -> None:
    out = write_documents(tmp_path / "documents", [doc("2404.00001"), doc("cs/0101001")], 2)
    checks = results(out)
    assert all(ok for ok, _ in checks.values()), checks
    assert checks["count matches clean manifest"] == (True, "manifest 2, Parquet 2")
    assert "golden doc ids exist" not in checks


@pytest.mark.parametrize(
    ("bad", "check"),
    [
        (doc("x", title=None), "title present"),
        (doc("x", title="  "), "title present"),
        (doc("x", abstract=""), "abstract present"),
        (
            doc("2404.00002v2", url="https://arxiv.org/abs/2404.00002v2"),
            "doc_id without version suffix",
        ),
        (doc("x", categories=["cs.LG"]), "in sub-domain cs.CL"),
        (doc("x", published_at=None), "published_at valid"),
        (doc("x", published_at="1970-01-01", year=1970), "published_at valid"),
        (doc("x", published_at="2027-01-01", year=2027), "published_at valid"),
        (doc("x", year=2023), "year matches published_at"),
        (doc("x", updated_at="2099-01-01"), "updated_at valid"),
        (doc("x", license="CC-BY-4.0"), "fixed values (source, license, url)"),
        (doc("x", url="https://arxiv.org/abs/y"), "fixed values (source, license, url)"),
        (doc("x", source="wikipedia"), "fixed values (source, license, url)"),
    ],
)
def test_each_rule_fails_on_a_bad_record(tmp_path: Path, bad: dict, check: str) -> None:
    out = write_documents(tmp_path / "documents", [doc("2404.00001"), bad])
    assert failed(out) == {check}


def test_duplicate_doc_id_and_manifest_mismatch(tmp_path: Path) -> None:
    out = write_documents(tmp_path / "documents", [doc("a"), doc("a"), doc("b")], records_out=2)
    checks = results(out)
    assert checks["doc_id unique"] == (False, "1 duplicated ids (2 records)")
    assert checks["count matches clean manifest"] == (False, "manifest 2, Parquet 3")


def test_schema_mismatch_stops_before_row_checks(tmp_path: Path) -> None:
    out = tmp_path / "documents" / "year=2024"
    out.mkdir(parents=True)
    duckdb.execute(f"COPY (SELECT 'a' AS doc_id, 1 AS title) TO '{(out / 'p.parquet').as_posix()}'")
    checks = results(tmp_path / "documents")
    assert list(checks) == ["schema"]
    ok, detail = checks["schema"]
    assert not ok and "title: INTEGER" in detail and "abstract: missing" in detail


def test_golden_doc_ids_must_exist(tmp_path: Path) -> None:
    out = write_documents(tmp_path / "documents", [doc("2404.00001"), doc("cs/0101001")])
    golden = tmp_path / "golden.jsonl"
    items = [
        {"id": "gs-001", "relevant_doc_ids": ["2404.00001", "cs/0101001"]},
        {"id": "gs-u01", "relevant_doc_ids": []},
        {"id": "gs-002", "relevant_doc_ids": ["2404.99999"]},
    ]
    golden.write_text("\n".join(json.dumps(i) for i in items) + "\n", encoding="utf-8")
    ok, detail = results(out, golden=[golden])["golden doc ids exist"]
    assert not ok
    assert detail == "1 of 3 ids missing: golden.jsonl:gs-002 (2404.99999)"
    items.pop()
    golden.write_text("\n".join(json.dumps(i) for i in items) + "\n", encoding="utf-8")
    assert results(out, golden=[golden])["golden doc ids exist"] == (
        True,
        "2 ids in 2 items, all found",
    )


def test_missing_input_names_the_clean_step(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="clean"):
        validate_documents(tmp_path / "nothing")


def test_missing_manifest_is_shown_as_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = write_documents(tmp_path / "documents", [doc("2404.00001")])
    assert results(out)["count matches clean manifest"] == (True, f"no {clean.CLEAN_MANIFEST}")
    assert run_validate(out)
    line = next(x for x in capsys.readouterr().out.splitlines() if "clean manifest" in x)
    assert line.split() == [
        "SKIP",
        "count",
        "matches",
        "clean",
        "manifest",
        "no",
        "_clean_manifest.json",
    ]


def test_cli_exit_code_and_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = write_documents(tmp_path / "documents", [doc("2404.00001")])
    assert main(["validate", "--input", str(out)]) == 0
    assert "validate: all checks passed" in capsys.readouterr().out
    write_documents(tmp_path / "bad", [doc("2404.00001", categories=["cs.LG"])])
    assert main(["validate", "--input", str(tmp_path / "bad")]) == 1
    assert "FAIL  in sub-domain cs.CL" in capsys.readouterr().out


@pytest.fixture(scope="module")
def spark():
    pytest.importorskip("pyspark")
    if not clean.java_available():
        pytest.skip("Java not found: Spark tests run in CI (ADR 0005)")
    session = clean.create_spark("local[1]", "1g")
    yield session
    session.stop()


def test_output_of_clean_on_the_fixture_passes(spark, tmp_path: Path) -> None:
    out = tmp_path / "documents"
    clean.clean_arxiv(spark, FIXTURE, out, sample_size=0, log=lambda _: 0)
    checks = results(out)
    assert all(ok for ok, _ in checks.values()), checks
    assert checks["count matches clean manifest"] == (True, "manifest 20, Parquet 20")
