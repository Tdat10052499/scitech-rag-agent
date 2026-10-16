import json
from pathlib import Path

import pytest

from scitech_pipelines import clean
from scitech_pipelines.cli import main
from scitech_pipelines.profile import build_profile, render_markdown, run_profile

duckdb = pytest.importorskip("duckdb")

FIXTURE = Path(__file__).parent / "fixtures" / "sample.jsonl"


def doc(doc_id: str, year: int, categories: list[str], abstract: str, **fields) -> dict:
    return {
        "doc_id": doc_id,
        "source": "arxiv",
        "title": "A title",
        "abstract": abstract,
        "authors": ["Ada Lovelace", "Alan Turing"],
        "categories": categories,
        "published_at": f"{year}-04-04",
        "updated_at": None,
        "url": f"https://arxiv.org/abs/{doc_id}",
        "license": "CC0-1.0",
        "year": year,
        **fields,
    }


DOCS = [
    doc("2304.00001", 2023, ["cs.CL"], "one two three four"),
    doc("2404.00001", 2024, ["cs.CL", "cs.LG"], "one two", authors=[]),
    doc("2404.00002", 2024, ["cs.LG", "cs.CL"], " ".join(["w"] * 300), updated_at="2024-05-01"),
]


def write_data(root: Path, *, wiki: bool = True) -> Path:
    """A data directory laid out the way `download` and `clean` write it."""
    raw = root / "raw" / "arxiv"
    raw.mkdir(parents=True)
    records = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]
    other = {**records[0], "id": "other", "categories": "cs.LG"}
    no_doi = {**records[0], "doi": None, "license": "  ", "authors_parsed": []}
    lines = [json.dumps(r) for r in [*records, other, no_doi]]
    (raw / clean.ARXIV_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")
    (raw / "manifest.json").write_text(json.dumps({"version": 307, "seconds": 12.5}))

    out = root / "processed" / "documents"
    out.parent.mkdir(parents=True)
    src = root / "docs.json"
    src.write_text(json.dumps(DOCS), encoding="utf-8")
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
    manifest = {
        "snapshot_version": 307,
        "seconds": 74.0,
        "engine": "pyspark 4.0.4 (local[*])",
        "platform": "Linux",
        "counts": {
            "records_in": 22,
            "in_category": 21,
            "in_category_duckdb": 21,
            "dropped_no_abstract": 0,
            "dropped_no_title": 0,
            "dropped_no_date": 0,
            "duplicates_removed": 1,
            "records_out": 3,
        },
    }
    (out / clean.CLEAN_MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")

    if wiki:
        pages = root / "raw" / "wikipedia"
        pages.mkdir()
        rows = [
            {"pageid": 1, "title": "NLP", "text": "a b c", "depth": 0, "category": "Category:NLP"},
            {"pageid": 2, "title": "BERT", "text": "a b", "depth": 1, "category": "Category:LM"},
            {"pageid": 3, "title": "GPT", "text": "a", "depth": 1, "category": "Category:LM"},
        ]
        (pages / "pages.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
        (pages / "pages_without_text.txt").write_text("4\n5\n", encoding="utf-8")
        (pages / "manifest.json").write_text(json.dumps({"seconds": 99.0}))
    return root


def profile_of(root: Path, **kwargs) -> dict:
    return build_profile(
        root / "raw" / "arxiv" / clean.ARXIV_FILE,
        root / "processed" / "documents",
        log=lambda _: 0,
        **kwargs,
    )


def test_profile_counts_raw_and_cleaned_data(tmp_path: Path) -> None:
    root = write_data(tmp_path)
    p = profile_of(root, wiki=root / "raw" / "wikipedia")

    raw = p["raw"]
    assert raw["records"] == 22 and raw["distinct_ids"] == 21
    assert raw["in_category"] == 21
    assert raw["missing_in_category"]["id"]["missing"] == 0
    assert raw["missing_in_category"]["doi"]["missing"] >= 1
    assert raw["missing_in_category"]["license"]["missing"] >= 1  # whitespace counts as missing
    assert raw["missing_in_category"]["authors_parsed"]["missing"] >= 1  # empty list too

    docs = p["documents"]
    assert docs["records"] == 3 and docs["parquet_files"] == 2 and docs["parquet_bytes"] > 0
    assert [(r["year"], r["records"]) for r in docs["by_year"]] == [(2023, 1), (2024, 2)]
    assert docs["categories_listed"] == [
        {"category": "cs.CL", "records": 3},
        {"category": "cs.LG", "records": 2},
    ]
    assert docs["cross_listed"] == 1
    assert docs["abstract_words"]["min"] == 2 and docs["abstract_words"]["max"] == 300
    assert docs["abstract_words"]["p50"] == 4
    assert docs["abstracts_over_words"] == {"256": 1, "384": 0, "512": 0}
    assert docs["missing_after_cleaning"] == {"authors_empty": 1, "updated_at_null": 2}

    wiki = p["wikipedia"]
    assert wiki["pages"] == 3 and wiki["pages_without_text"] == 2
    assert wiki["by_depth"] == [
        {"depth": 0, "pages": 1, "median_words": 3.0},
        {"depth": 1, "pages": 2, "median_words": 1.5},
    ]
    assert wiki["categories"][1] == {"category": "Category:LM", "depth": 1, "pages": 2}
    assert p["download_manifest"]["seconds"] == 12.5
    assert p["clean_manifest"]["counts"]["duplicates_removed"] == 1


def test_report_says_how_every_section_was_computed(tmp_path: Path) -> None:
    root = write_data(tmp_path)
    report = render_markdown(profile_of(root, wiki=root / "raw" / "wikipedia"))

    sections = [line for line in report.splitlines() if line.startswith("## ")]
    assert len(sections) == 8
    assert report.count("How computed:") == len(sections)
    assert "| Raw snapshot, records | 22 |" in report
    assert "| Duplicates removed (`doc_id`) | 1 (4.8%) |" in report
    assert "| 2024 | 2 |" in report
    assert "| `cs.LG` | 2 | 66.7% | 1 | 33.3% |" in report
    assert "256 words 1 (33.3%)" in report
    cells = None  # every table row has as many cells as its table's header
    for line in report.splitlines():
        if not line.startswith("|"):
            cells = None
        elif cells is None:
            cells = line.count("|")
        else:
            assert line.count("|") == cells, line


def test_report_without_wikipedia_has_seven_sections(tmp_path: Path) -> None:
    root = write_data(tmp_path, wiki=False)
    report = render_markdown(profile_of(root))
    assert len([line for line in report.splitlines() if line.startswith("## ")]) == 7
    assert "Wikipedia" not in report


def test_cli_profile_writes_markdown_and_json(tmp_path: Path) -> None:
    root = write_data(tmp_path / "data")
    out = tmp_path / "reports" / "data_profile.md"

    args = ["--data-dir", str(root), "profile", "--out", str(out), "--clean-peak-mb", "2698"]
    assert main(args) == 0

    report = out.read_text(encoding="utf-8")
    assert report.startswith("# Data profile")
    assert "Peak memory of the `clean` run: 2,698 MB" in report
    numbers = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert numbers["documents"]["records"] == 3
    assert numbers["wikipedia"]["pages"] == 3  # found under <data-dir>/raw/wikipedia


def test_profile_needs_the_clean_output(tmp_path: Path) -> None:
    root = write_data(tmp_path, wiki=False)
    (root / "processed" / "documents" / clean.CLEAN_MANIFEST).unlink()
    with pytest.raises(FileNotFoundError, match="clean"):
        run_profile(
            root / "raw" / "arxiv" / clean.ARXIV_FILE,
            root / "processed" / "documents",
            tmp_path / "report.md",
            log=lambda _: 0,
        )
