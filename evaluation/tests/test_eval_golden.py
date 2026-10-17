import json
from pathlib import Path

import pytest

from scitech_eval.golden import GoldenError, check_golden, load_golden, read_corpus_doc_ids

DATA = Path(__file__).parent / "data"


def _item(**overrides):
    base = {
        "id": "gs-001",
        "question": "Q?",
        "type": "factual",
        "relevant_doc_ids": ["2401.03205"],
        "reference_answer": "A.",
        "notes": "plain. Where the answer is.",
        "author": "LDN",
        "split": "dev",
    }
    base.update(overrides)
    return base


def _write(tmp_path, *items):
    path = tmp_path / "g.jsonl"
    path.write_text("\n".join(json.dumps(i) for i in items) + "\n", encoding="utf-8")
    return path


def test_toy_file_is_valid_and_loads():
    items = load_golden(DATA / "toy_golden.jsonl")
    assert [i.id for i in items][:3] == ["gs-001", "gs-002", "gs-003"]
    assert items[0].relevant_doc_ids == ("2001.00001",)
    assert items[6].language == "vi"


def test_valid_file_has_no_problems(tmp_path):
    assert check_golden(_write(tmp_path, _item())) == []


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"type": "essay"}, "'type'"),
        ({"split": "train"}, "'split'"),
        ({"author": "XYZ"}, "'author'"),
        ({"id": "item-1"}, "'id'"),
        ({"id": "gs-031"}, "031-060 are test"),
        ({"notes": "Answer is in the abstract."}, "plain, expert or specific"),
        ({"relevant_doc_ids": []}, "empty only for unanswerable"),
        ({"relevant_doc_ids": ["2401.03205v2"]}, "version suffix"),
        ({"relevant_doc_ids": ["2401.03205", "2401.03205"]}, "duplicates"),
        ({"type": "comparison"}, "at least two"),
        ({"type": "unanswerable"}, "empty 'relevant_doc_ids'"),
        ({"type": "follow_up"}, "history"),
        ({"language": "fr"}, "'language'"),
        ({"question": " "}, "'question'"),
    ],
)
def test_format_rules(tmp_path, overrides, fragment):
    problems = check_golden(_write(tmp_path, _item(**overrides)))
    assert any(fragment in p for p in problems), problems


def test_missing_field_duplicate_id_and_bad_json(tmp_path):
    broken = _item()
    del broken["author"]
    path = _write(tmp_path, broken, _item(), _item())
    path.write_text(path.read_text() + "{not json\n", encoding="utf-8")
    problems = check_golden(path)
    assert any("missing field 'author'" in p for p in problems)
    assert any("duplicate id" in p for p in problems)
    assert any("invalid JSON" in p for p in problems)


def test_follow_up_with_history_is_valid(tmp_path):
    item = _item(
        type="follow_up",
        history=[{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}],
        standalone_query="Standalone?",
    )
    assert check_golden(_write(tmp_path, item)) == []


def test_unanswerable_item_has_empty_list(tmp_path):
    item = _item(id="gs-u01", type="unanswerable", relevant_doc_ids=[])
    assert check_golden(_write(tmp_path, item)) == []


def test_corpus_check(tmp_path):
    path = _write(tmp_path, _item())
    assert check_golden(path, {"2401.03205"}) == []
    assert any("not in the corpus" in p for p in check_golden(path, {"1111.11111"}))


def test_read_corpus_doc_ids_drops_version_suffix(tmp_path):
    corpus = tmp_path / "c.jsonl"
    corpus.write_text('{"id": "2401.03205v2"}\n{"id": "2402.00001"}\n', encoding="utf-8")
    assert read_corpus_doc_ids(corpus, "id") == {"2401.03205", "2402.00001"}


def test_load_raises_with_all_problems(tmp_path):
    with pytest.raises(GoldenError) as err:
        load_golden(_write(tmp_path, _item(type="essay", split="train")))
    assert "'type'" in str(err.value) and "'split'" in str(err.value)
