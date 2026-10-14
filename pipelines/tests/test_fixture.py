import json
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "sample.jsonl"
REQUIRED = ("id", "title", "abstract", "authors", "categories", "versions")


def test_fixture_has_20_cs_cl_records() -> None:
    records = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 20
    assert len({r["id"] for r in records}) == 20
    for record in records:
        for field in REQUIRED:
            assert record.get(field), f"{record.get('id')}: missing {field}"
        assert "cs.CL" in record["categories"].split()
        assert "submitter" not in record
