"""Contract checks (W1-D4-DAT-1): the frozen files in docs/contracts/ stay valid and consistent.

- chunk.schema.json validates real records (the arXiv fixture of pipelines/, mapped to chunks as
  issue #7, C7, specifies) and rejects malformed chunks.
- api.openapi.yaml is a valid OpenAPI 3.0 document and keeps the paths, schemas and fields the
  frontend and backend rely on.
"""

from __future__ import annotations

import json
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "docs" / "contracts"
FIXTURE = ROOT / "pipelines" / "tests" / "fixtures" / "sample.jsonl"


@pytest.fixture(scope="module")
def chunk_validator() -> Draft202012Validator:
    schema = json.loads((CONTRACTS / "chunk.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


@pytest.fixture(scope="module")
def openapi() -> dict[str, Any]:
    return yaml.safe_load((CONTRACTS / "api.openapi.yaml").read_text(encoding="utf-8"))


def arxiv_record_to_chunk(record: dict[str, Any]) -> dict[str, Any]:
    """Map one arXiv snapshot record to a chunk as agreed in issue #7 (one chunk per abstract).

    This is a reference mapping for the contract test, not the pipeline implementation.
    """
    title = " ".join(record["title"].split())
    abstract = " ".join(record["abstract"].split())
    first_version = parsedate_to_datetime(record["versions"][0]["created"])
    authors = record["authors"].replace(" and ", ", ").split(",")
    return {
        "chunk_id": f"{record['id']}#0",
        "doc_id": record["id"],
        "source": "arxiv",
        "title": title,
        "text": f"{title}. {abstract}",
        "chunk_index": 0,
        "authors": [a.strip() for a in authors if a.strip()],
        "categories": record["categories"].split(),
        "published_at": first_version.date().isoformat(),
        "url": f"https://arxiv.org/abs/{record['id']}",
        "license": "CC0-1.0",
    }


def fixture_records() -> list[dict[str, Any]]:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_fixture_is_present() -> None:
    assert len(fixture_records()) == 20


@pytest.mark.parametrize("record", fixture_records(), ids=lambda r: r["id"])
def test_fixture_records_map_to_valid_chunks(
    chunk_validator: Draft202012Validator, record: dict[str, Any]
) -> None:
    errors = [e.message for e in chunk_validator.iter_errors(arxiv_record_to_chunk(record))]
    assert errors == []


def test_wikipedia_chunk_is_valid(chunk_validator: Draft202012Validator) -> None:
    chunk = {
        "chunk_id": "wiki-21173#2",
        "doc_id": "wiki-21173",
        "source": "wikipedia",
        "title": "Natural language processing",
        "text": "Natural language processing is a subfield of computer science.",
        "chunk_index": 2,
        "url": "https://en.wikipedia.org/wiki/Natural_language_processing",
        "license": "CC BY-SA 4.0",
    }
    assert list(chunk_validator.iter_errors(chunk)) == []


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"extra_field": 1}, "additionalProperties is false"),
        ({"source": "pubmed"}, "source outside the enum"),
        ({"text": ""}, "empty text"),
        ({"chunk_index": -1}, "negative chunk_index"),
        ({"published_at": "11 May 2022"}, "date not in ISO format"),
    ],
)
def test_invalid_chunks_are_rejected(
    chunk_validator: Draft202012Validator, change: dict[str, Any], reason: str
) -> None:
    chunk = arxiv_record_to_chunk(fixture_records()[0]) | change
    assert list(chunk_validator.iter_errors(chunk)), reason


def test_missing_required_field_is_rejected(chunk_validator: Draft202012Validator) -> None:
    chunk = arxiv_record_to_chunk(fixture_records()[0])
    del chunk["doc_id"]
    assert list(chunk_validator.iter_errors(chunk))


def test_openapi_document_is_valid(openapi: dict[str, Any]) -> None:
    validate(openapi)  # raises on an invalid OpenAPI 3.0 document


def test_openapi_paths(openapi: dict[str, Any]) -> None:
    assert set(openapi["paths"]) >= {"/health", "/chat"}
    chat = openapi["paths"]["/chat"]["post"]
    assert "text/event-stream" in chat["responses"]["200"]["content"]
    assert "422" in chat["responses"]


def test_openapi_frozen_schemas(openapi: dict[str, Any]) -> None:
    schemas = openapi["components"]["schemas"]
    source = schemas["Source"]["properties"]
    assert set(schemas["Source"]["required"]) == {"chunk_id", "doc_id", "title", "score"}
    assert {"source", "published_at", "categories"} <= set(source)
    assert source["source"]["enum"] == ["arxiv", "openalex", "wikipedia"]
    done = schemas["Done"]["properties"]
    assert done["insufficient_evidence"]["default"] is False
    assert "message_id" in done
    assert schemas["Error"]["properties"]["code"]["enum"] == [
        "llm_unavailable",
        "retrieval_failed",
        "timeout",
        "internal",
    ]


def test_source_enum_matches_chunk_schema(openapi: dict[str, Any]) -> None:
    chunk_schema = json.loads((CONTRACTS / "chunk.schema.json").read_text(encoding="utf-8"))
    chunk_sources = chunk_schema["properties"]["source"]["enum"]
    api_sources = openapi["components"]["schemas"]["Source"]["properties"]["source"]["enum"]
    assert api_sources == chunk_sources


@pytest.mark.parametrize("name", ["chunk.schema.json", "api.openapi.yaml", "llm-client.md"])
def test_contract_files_are_marked_frozen(name: str) -> None:
    assert "Frozen on 2026-10-15" in (CONTRACTS / name).read_text(encoding="utf-8")
