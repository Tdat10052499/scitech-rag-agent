"""Sentence splitting, the labelling sheet and its check (faithfulness pilot, W4-D4-LDN-1)."""

import csv
import json

import pytest

from scitech_eval.__main__ import main
from scitech_eval.answers import (
    SHEET_COLUMNS,
    build_sheet,
    check_labels,
    cited_numbers,
    read_answers,
    split_sentences,
)


def test_plain_sentences_keep_their_citations():
    text = "Models make things up when data is noisy [1]. Two fixes exist [1][2]. They differ."
    assert split_sentences(text) == [
        "Models make things up when data is noisy [1].",
        "Two fixes exist [1][2].",
        "They differ.",
    ]


def test_citation_after_the_end_mark_stays_with_its_sentence():
    assert split_sentences("It improves recall. [1] The cost is higher. [2][3]") == [
        "It improves recall. [1]",
        "The cost is higher. [2][3]",
    ]


def test_no_split_at_abbreviations_initials_or_numbers():
    text = "Methods differ, e.g. BM25 vs. dense search [1]. Smith et al. report 25.7% gain [2]."
    assert len(split_sentences(text)) == 2
    assert len(split_sentences("The model bge-small-en-v1.5 has 384 dimensions [1].")) == 1
    assert len(split_sentences("It was proposed by J. Smith in 2020 [1].")) == 1


def test_line_breaks_split_and_list_markers_are_dropped():
    text = "Two ways are:\n- Faithful finetuning [1].\n- HALO [2].\n1. A third one [3]."
    assert split_sentences(text) == [
        "Two ways are:",
        "Faithful finetuning [1].",
        "HALO [2].",
        "A third one [3].",
    ]


def test_questions_and_exclamations_split_and_lowercase_continuations_do_not():
    assert len(split_sentences("Is it better? No [1]. See below!")) == 3
    assert len(split_sentences("The score is 3.5. which is high [1].")) == 1


def test_text_with_only_citations_or_nothing():
    assert split_sentences("[1][2]") == ["[1][2]"]
    assert split_sentences("  \n \n") == []


def test_cited_numbers_in_order_without_repeats():
    assert cited_numbers("A [2] B [1][2] C [10].") == [2, 1, 10]
    assert cited_numbers("no citation") == []


def _answers():
    return [
        {
            "answer_id": "p-011",
            "question_id": "gs-011",
            "answer": "It matters [1]. It also helps [2][3]. No source here.",
            "sources": [
                {"n": 1, "chunk_id": "2401.00001#0", "doc_id": "2401.00001", "text": "one"},
                {"n": 2, "chunk_id": "2401.00002#0", "doc_id": "2401.00002", "text": "two"},
            ],
        }
    ]


def test_sheet_has_one_row_per_sentence_and_flags_invalid_markers():
    sheet, chunks = build_sheet(_answers())
    assert [r["sentence_no"] for r in sheet] == [1, 2, 3]
    assert sheet[0]["cited_n"] == "1" and sheet[0]["cited_chunk_ids"] == "2401.00001#0"
    assert sheet[1]["cited_n"] == "2;3(INVALID)"
    assert sheet[1]["cited_chunk_ids"] == "2401.00002#0"
    assert sheet[2]["cited_n"] == "" and sheet[2]["cited_chunk_ids"] == ""
    assert all(r["label"] == "" and r["annotator"] == "" for r in sheet)
    assert [(c["n"], c["text"]) for c in chunks] == [(1, "one"), (2, "two")]


def _write_answers(tmp_path, answers):
    path = tmp_path / "answers.jsonl"
    path.write_text("\n".join(json.dumps(a) for a in answers) + "\n", encoding="utf-8")
    return path


def test_make_sheet_writes_both_files_and_the_command_works(tmp_path, capsys):
    path = _write_answers(tmp_path, _answers())
    assert main(["make-sheet", str(path), "--out-dir", str(tmp_path / "out")]) == 0
    assert "labels-template.csv" in capsys.readouterr().out
    with (tmp_path / "out" / "labels-template.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == SHEET_COLUMNS and len(rows) == 3
    assert (tmp_path / "out" / "chunks.csv").exists()


def test_read_answers_rejects_missing_fields_and_duplicate_ids(tmp_path):
    with pytest.raises(ValueError, match="missing 'sources'"):
        read_answers(_write_answers(tmp_path, [{"answer_id": "a", "answer": "x"}]))
    twice = [{"answer_id": "a", "answer": "x", "sources": []}] * 2
    with pytest.raises(ValueError, match="not unique"):
        read_answers(_write_answers(tmp_path, twice))
    assert main(["make-sheet", str(tmp_path / "missing.jsonl")]) == 2


def _filled(tmp_path, labels):
    sheet, _ = build_sheet(_answers())
    path = tmp_path / "labels.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SHEET_COLUMNS)
        writer.writeheader()
        for row, (label, reason, who) in zip(sheet, labels, strict=True):
            writer.writerow({**row, "label": label, "reason": reason, "annotator": who})
    return path


def test_check_labels_accepts_a_complete_sheet(tmp_path):
    path = _filled(
        tmp_path,
        [
            ("supported", "", "FAO"),
            ("not supported", "[3] has no source", "FAO"),
            ("not checkable", "", "FAO"),
        ],
    )
    assert check_labels(path) == []
    assert main(["check-labels", str(path)]) == 0


def test_check_labels_reports_each_kind_of_problem(tmp_path, capsys):
    path = _filled(
        tmp_path,
        [("yes", "", "FAO"), ("not supported", "", "FAO"), ("supported", "", "")],
    )
    problems = check_labels(path)
    assert any("'yes' is not one of" in p for p in problems)
    assert any("needs a one-line reason" in p for p in problems)
    assert any("annotator is empty" in p for p in problems)
    assert main(["check-labels", str(path)]) == 1
    assert "3 problem(s)" in capsys.readouterr().out
