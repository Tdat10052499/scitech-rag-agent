import json
from datetime import date
from email.utils import parsedate_to_datetime
from pathlib import Path

import pytest

from scitech_pipelines import chunk, clean
from scitech_pipelines.chunk import chunk_document, chunk_documents, windows
from scitech_pipelines.cli import build_parser, main

duckdb = pytest.importorskip("duckdb")
jsonschema = pytest.importorskip("jsonschema")

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "docs" / "contracts" / "chunk.schema.json"
FIXTURE = Path(__file__).parent / "fixtures" / "sample.jsonl"


def doc(doc_id: str = "2404.00001", words: int = 20, title: str = "A title") -> dict:
    return {
        "doc_id": doc_id,
        "source": "arxiv",
        "title": title,
        "abstract": " ".join(f"w{i}" for i in range(words)),
        "authors": ["Ada Lovelace"],
        "categories": ["cs.CL"],
        "published_at": date(2024, 4, 4),
        "url": f"https://arxiv.org/abs/{doc_id}",
        "license": "CC0-1.0",
    }


def fixture_documents() -> list[dict]:
    """The 20 fixture records as `clean` writes them (simplified: no LaTeX, no dedup)."""
    docs = []
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        created = parsedate_to_datetime(r["versions"][0]["created"]).date()
        docs.append(
            {
                "doc_id": r["id"],
                "source": "arxiv",
                "title": " ".join(r["title"].split()),
                "abstract": " ".join(r["abstract"].split()),
                "authors": [a.strip() for a in r["authors"].replace(" and ", ",").split(",")],
                "categories": r["categories"].split(),
                "published_at": created.isoformat(),
                "updated_at": None,
                "url": f"https://arxiv.org/abs/{r['id']}",
                "license": "CC0-1.0",
                "year": created.year,
            }
        )
    return docs


def write_documents(out: Path, docs: list[dict]) -> Path:
    """Parquet partitioned by `year` plus the clean manifest, the way `clean` writes them."""
    out.parent.mkdir(parents=True, exist_ok=True)
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
    manifest = {"counts": {"records_out": len(docs)}}
    (out / clean.CLEAN_MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    return out


def read_chunks(out: Path) -> list[dict]:
    con = duckdb.connect()
    result = con.execute(f"SELECT * FROM read_parquet('{(out / chunk.CHUNK_FILE).as_posix()}')")
    names = [d[0] for d in result.description]
    rows = [dict(zip(names, row, strict=True)) for row in result.fetchall()]
    con.close()
    return rows


def assert_valid(chunks: list[dict]) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    for c in chunks:
        record = {k: v for k, v in c.items() if v is not None}
        assert [e.message for e in validator.iter_errors(record)] == [], c["chunk_id"]


# --- windows and one document ---------------------------------------------------------------


def test_short_text_is_one_window() -> None:
    assert windows(list("abc"), 3, 1) == [list("abc")]


def test_windows_overlap_and_end_at_the_last_word() -> None:
    words = [str(i) for i in range(10)]
    assert windows(words, 4, 1) == [
        ["0", "1", "2", "3"],
        ["3", "4", "5", "6"],
        ["6", "7", "8", "9"],
    ]
    assert windows(words, 4, 0) == [["0", "1", "2", "3"], ["4", "5", "6", "7"], ["8", "9"]]


def test_abstract_that_fits_gives_one_chunk_like_the_contract_example() -> None:
    chunks = chunk_document(doc(words=20))
    assert len(chunks) == 1
    c = chunks[0]
    assert c["chunk_id"] == "2404.00001#0" and c["chunk_index"] == 0
    assert c["text"] == "A title. " + doc()["abstract"]
    assert c["published_at"] == "2024-04-04"
    assert_valid(chunks)


def test_long_abstract_is_split_with_overlap_within_the_limit() -> None:
    d = doc(words=200)
    chunks = chunk_document(d, max_words=62, overlap_words=10)  # 60 abstract words per chunk

    assert [c["chunk_id"] for c in chunks] == [f"2404.00001#{i}" for i in range(4)]
    bodies = [c["text"].removeprefix("A title. ").split() for c in chunks]
    assert all(len(c["text"].split()) <= 62 for c in chunks)
    assert all(a[-10:] == b[:10] for a, b in zip(bodies, bodies[1:], strict=False))
    assert bodies[0][0] == "w0" and bodies[-1][-1] == "w199"
    rebuilt = bodies[0] + [w for b in bodies[1:] for w in b[10:]]
    assert rebuilt == d["abstract"].split()
    assert_valid(chunks)


def test_title_with_end_punctuation_gets_no_extra_full_stop() -> None:
    assert chunk_document(doc(title="Is it?"))[0]["text"].startswith("Is it? w0")


def test_very_long_title_still_leaves_half_the_limit_for_the_abstract() -> None:
    chunks = chunk_document(doc(words=100, title=" ".join(["t"] * 50)), 40, 5)
    assert all(len(c["text"].split()) == 50 + 20 for c in chunks[:-1])


@pytest.mark.parametrize(("max_words", "overlap"), [(1, 0), (10, 5), (10, -1)])
def test_bad_sizes_are_rejected(max_words: int, overlap: int) -> None:
    with pytest.raises(ValueError, match="overlap_words"):
        chunk_document(doc(), max_words, overlap)


# --- the whole step -------------------------------------------------------------------------


def test_every_fixture_chunk_is_valid_against_the_schema(tmp_path: Path) -> None:
    documents = write_documents(tmp_path / "documents", fixture_documents())
    out = tmp_path / "chunks"

    manifest = chunk_documents(documents, out, max_words=80, overlap_words=16, log=lambda _: 0)

    chunks = read_chunks(out)
    assert_valid(chunks)
    assert len(chunks) == manifest["counts"]["chunks"] > 20  # 80 words splits some abstracts
    assert manifest["counts"]["documents"] == 20
    assert sum(manifest["counts"]["chunks_per_document"].values()) == 20
    assert len({c["chunk_id"] for c in chunks}) == len(chunks)
    first = next(c for c in chunks if c["chunk_id"] == "2205.05433#0")
    assert first["text"].startswith("ALIGNMEET: A Comprehensive Tool for Meeting Annotation")
    assert first["published_at"] == "2022-05-11" and first["license"] == "CC0-1.0"
    assert manifest["words_per_chunk"]["max"] <= 80
    assert json.loads((out / chunk.CHUNK_MANIFEST).read_text(encoding="utf-8")) == manifest

    # With the default limit every fixture abstract fits in one chunk.
    manifest = chunk_documents(documents, out, log=lambda _: 0)
    assert manifest["counts"]["chunks"] == 20 and len(read_chunks(out)) == 20  # replaced


def test_chunk_needs_the_clean_output(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="clean"):
        chunk_documents(tmp_path / "documents", tmp_path / "chunks", log=lambda _: 0)


def test_cli_chunk_uses_data_dir_and_env(monkeypatch, tmp_path: Path) -> None:
    write_documents(tmp_path / "processed" / "documents", fixture_documents())
    monkeypatch.setenv("CHUNK_MAX_WORDS", "100")
    monkeypatch.setenv("CHUNK_OVERLAP_WORDS", "")
    args = build_parser().parse_args(["chunk"])
    assert args.max_words == 100 and args.overlap_words == chunk.DEFAULT_OVERLAP_WORDS

    assert main(["--data-dir", str(tmp_path), "chunk"]) == 0
    manifest = json.loads(
        (tmp_path / "processed" / "chunks" / chunk.CHUNK_MANIFEST).read_text(encoding="utf-8")
    )
    assert manifest["max_words"] == 100 and manifest["counts"]["documents"] == 20


def test_chunks_of_real_clean_output_are_valid(tmp_path: Path) -> None:
    """clean (Spark) then chunk on the fixture; skipped without PySpark or Java (ADR 0005)."""
    pytest.importorskip("pyspark")
    if not clean.java_available():
        pytest.skip("Java not found: Spark tests run in CI (ADR 0005)")
    src = tmp_path / "in.jsonl"
    src.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    spark = clean.create_spark("local[1]", "1g")
    try:
        clean.clean_arxiv(spark, src, tmp_path / "documents", sample_size=0, log=lambda _: 0)
    finally:
        spark.stop()

    chunk_documents(tmp_path / "documents", tmp_path / "chunks", log=lambda _: 0)

    chunks = read_chunks(tmp_path / "chunks")
    assert len(chunks) == 20
    assert_valid(chunks)
