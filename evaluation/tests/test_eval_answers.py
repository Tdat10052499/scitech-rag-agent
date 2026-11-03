"""Sentence splitting, the labelling sheet and its check (faithfulness pilot, W4-D4-LDN-1)."""

import csv
import json

import pytest

from scitech_eval.__main__ import main
from scitech_eval.answers import (
    RELEVANCE_COLUMNS,
    SHEET_COLUMNS,
    build_sheet,
    check_labels,
    cited_numbers,
    parse_part,
    read_answers,
    sample_answers,
    split_sentences,
)
from scitech_eval.golden import GoldenItem


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


def test_cited_numbers_read_lists_and_ranges_as_the_agent_does():
    assert cited_numbers("RAG helps [1, 2].") == [1, 2]
    assert cited_numbers("It fails [1-3] and [4; 2].") == [1, 2, 3, 4]
    assert cited_numbers("See [2–3].") == [2, 3]
    # not citations: an index after a word, a 0, a range longer than 20 numbers
    assert cited_numbers("x[1] and the interval [0, 1].") == []
    assert cited_numbers("Years [1-40].") == []


def test_list_and_range_markers_after_the_end_mark_stay_with_their_sentence():
    assert split_sentences("It improves recall. [1, 2] The cost is higher. [3-4]") == [
        "It improves recall. [1, 2]",
        "The cost is higher. [3-4]",
    ]


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


# --- seeded sample for the manual check (W7-D2-LDN-1) ---------------------------------------------


def _golden(n=20, history_for=None):
    """`n` answerable items gs-001.. and the unanswerable gs-u01, as {id: GoldenItem}."""
    items = {}
    for i in range(1, n + 1):
        gid = f"gs-{i:03d}"
        items[gid] = GoldenItem(
            id=gid,
            question=f"Question {i}?",
            type="follow_up" if gid == history_for else "factual",
            relevant_doc_ids=(f"2001.{i:05d}",),
            reference_answer=f"Reference {i}.",
            notes="plain.",
            author="LDN",
            split="dev",
            history=(
                (
                    {"role": "user", "content": "Earlier question"},
                    {"role": "assistant", "content": "Earlier answer"},
                )
                if gid == history_for
                else None
            ),
        )
    items["gs-u01"] = GoldenItem(
        id="gs-u01",
        question="No answer?",
        type="unanswerable",
        relevant_doc_ids=(),
        reference_answer="Insufficient.",
        notes="plain.",
        author="LDN",
        split="dev",
    )
    return items


def _batch(golden, **flags):
    """One answer per golden item; `flags` maps an id to extra fields (error, refusal)."""
    return [
        {
            "answer_id": gid,
            "question": golden[gid].question,
            "answer": f"Answer {gid} [1].",
            "sources": [{"n": 1, "chunk_id": f"{gid}#0", "doc_id": "d", "text": "t"}],
            "error": None,
            "insufficient_evidence": False,
            **flags.get(gid, {}),
        }
        for gid in golden
    ]


def test_sample_leaves_out_errors_refusals_and_unanswerable_items():
    golden = _golden()
    answers = _batch(
        golden,
        **{
            "gs-001": {"error": "timeout"},
            "gs-002": {"insufficient_evidence": True},
            "gs-u01": {"insufficient_evidence": False},  # answered anyway: still not scored
        },
    )
    picked, record = sample_answers(answers, golden, 1.0, seed=0)
    ids = {a["answer_id"] for a in picked}
    assert not ids & {"gs-001", "gs-002", "gs-u01"} and len(ids) == 18
    assert record["eligible"] == 18
    assert record["excluded"] == {"error": 1, "refused": 1, "unanswerable_item": 1}


def test_sample_size_is_the_fraction_rounded_up_and_never_above_the_eligible():
    golden = _golden(20)
    answers = _batch(golden)
    assert len(sample_answers(answers, golden, 0.2, 0)[0]) == 4  # 20 eligible
    assert len(sample_answers(answers, golden, 0.21, 0)[0]) == 5
    assert len(sample_answers(answers, golden, 1.0, 0)[0]) == 20
    assert sample_answers([], golden, 0.2, 0)[0] == []
    for bad in (0, -0.1, 1.5):
        with pytest.raises(ValueError, match="fraction"):
            sample_answers(answers, golden, bad, 0)


def test_sample_depends_on_seed_and_ids_only_not_on_file_order():
    golden = _golden(40)
    answers = _batch(golden)
    first = sample_answers(answers, golden, 0.25, seed=7)[1]["sampled_all_parts"]
    again = sample_answers(list(reversed(answers)), golden, 0.25, seed=7)[1]["sampled_all_parts"]
    other = sample_answers(answers, golden, 0.25, seed=8)[1]["sampled_all_parts"]
    assert first == again and len(first) == 10
    assert first != other
    # pinned: the draw must not change between Python versions or releases of this code
    assert first == [
        "gs-001", "gs-002", "gs-013", "gs-022", "gs-025",
        "gs-029", "gs-036", "gs-037", "gs-038", "gs-040",
    ]  # fmt: skip
    assert sample_answers(answers, golden, 0.1, seed=0)[1]["sampled_all_parts"] == [
        "gs-007",
        "gs-009",
        "gs-020",
        "gs-029",
    ]


def test_parts_are_disjoint_and_together_are_the_sample():
    golden = _golden(40)
    answers = _batch(golden)
    whole = sample_answers(answers, golden, 0.3, seed=3)[1]["sampled_all_parts"]
    one, rec1 = sample_answers(answers, golden, 0.3, seed=3, part=(1, 2))
    two, rec2 = sample_answers(answers, golden, 0.3, seed=3, part=(2, 2))
    ids1, ids2 = {a["answer_id"] for a in one}, {a["answer_id"] for a in two}
    assert not ids1 & ids2 and sorted(ids1 | ids2) == whole
    assert abs(len(ids1) - len(ids2)) <= 1
    assert rec1["part"] == "1/2" and rec2["sampled_all_parts"] == whole


def test_sample_rejects_answers_that_are_not_in_the_golden_file():
    golden = _golden(3)
    answers = _batch(golden) + [{"answer_id": "gs-999", "answer": "x", "sources": []}]
    with pytest.raises(ValueError, match="gs-999"):
        sample_answers(answers, golden, 0.5, 0)


def test_parse_part():
    assert parse_part("2/3") == (2, 3)
    for bad in ("0/2", "3/2", "x", "1-2", "1/"):
        with pytest.raises(ValueError):
            parse_part(bad)


def _golden_file(tmp_path, golden):
    path = tmp_path / "golden.jsonl"
    rows = []
    for i in golden.values():
        row = {
            "id": i.id,
            "question": i.question,
            "type": i.type,
            "relevant_doc_ids": list(i.relevant_doc_ids),
            "reference_answer": i.reference_answer,
            "notes": i.notes,
            "author": i.author,
            "split": i.split,
        }
        if i.history:
            row["history"] = list(i.history)
            row["standalone_query"] = "Standalone?"
        rows.append(json.dumps(row))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_make_sheet_with_sample_writes_the_four_files_and_the_record(tmp_path, capsys):
    golden = _golden(20, history_for="gs-005")
    answers = _write_answers(tmp_path, _batch(golden, **{"gs-003": {"error": "x"}}))
    gold = _golden_file(tmp_path, golden)
    out = tmp_path / "out"
    args = ["make-sheet", str(answers), "--out-dir", str(out), "--golden", str(gold)]
    assert main([*args, "--sample", "0.5", "--seed", "4"]) == 0
    printed = capsys.readouterr().out
    for name in ("labels-template.csv", "chunks.csv", "relevance-template.csv", "sample.json"):
        assert name in printed and (out / name).exists()
    record = json.loads((out / "sample.json").read_text(encoding="utf-8"))
    assert record["seed"] == 4 and record["fraction"] == 0.5 and record["eligible"] == 19
    assert record["answers_file"] == "answers.jsonl" and len(record["sampled_all_parts"]) == 10
    with (out / "relevance-template.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == RELEVANCE_COLUMNS and len(rows) == 10
    assert {r["answer_id"] for r in rows} == set(record["sampled_this_part"])
    assert all(r["rating"] == "" and r["annotator"] == "" for r in rows)
    with (out / "labels-template.csv").open(encoding="utf-8-sig", newline="") as f:
        sheet_ids = {r["answer_id"] for r in csv.DictReader(f)}
    assert sheet_ids == set(record["sampled_this_part"])


def test_relevance_sheet_has_the_history_of_a_follow_up_and_the_reference(tmp_path):
    golden = _golden(6, history_for="gs-002")
    answers = _write_answers(tmp_path, _batch(golden))
    gold = _golden_file(tmp_path, golden)
    out = tmp_path / "out"
    assert (
        main(
            [
                "make-sheet",
                str(answers),
                "--out-dir",
                str(out),
                "--golden",
                str(gold),
                "--sample",
                "1",
            ]
        )
        == 0
    )
    with (out / "relevance-template.csv").open(encoding="utf-8-sig", newline="") as f:
        by_id = {r["answer_id"]: r for r in csv.DictReader(f)}
    assert by_id["gs-002"]["history"] == "user: Earlier question\nassistant: Earlier answer"
    assert (
        by_id["gs-001"]["history"] == "" and by_id["gs-001"]["reference_answer"] == "Reference 1."
    )


def test_make_sheet_parts_get_a_suffix_and_the_old_call_is_unchanged(tmp_path):
    golden = _golden(20)
    answers = _write_answers(tmp_path, _batch(golden))
    gold = _golden_file(tmp_path, golden)
    out = tmp_path / "out"
    base = ["make-sheet", str(answers), "--out-dir", str(out), "--golden", str(gold)]
    assert main([*base, "--sample", "0.5", "--part", "2/2"]) == 0
    assert (out / "labels-template-part2of2.csv").exists() and (
        out / "sample-part2of2.json"
    ).exists()
    assert not (out / "labels-template.csv").exists()
    plain = tmp_path / "plain"
    assert main(["make-sheet", str(answers), "--out-dir", str(plain)]) == 0
    assert sorted(p.name for p in plain.iterdir()) == ["chunks.csv", "labels-template.csv"]


def test_make_sheet_option_errors_return_2(tmp_path, capsys):
    golden = _golden(4)
    answers = _write_answers(tmp_path, _batch(golden))
    gold = _golden_file(tmp_path, golden)
    out = str(tmp_path / "out")
    assert main(["make-sheet", str(answers), "--out-dir", out, "--part", "1/2"]) == 2
    assert main(["make-sheet", str(answers), "--out-dir", out, "--golden", str(gold)]) == 2
    assert (
        main(["make-sheet", str(answers), "--out-dir", out, "--sample", "2", "--golden", str(gold)])
        == 2
    )
    assert (
        main(
            [
                "make-sheet",
                str(answers),
                "--out-dir",
                out,
                "--sample",
                "0.5",
                "--part",
                "3/2",
                "--golden",
                str(gold),
            ]
        )
        == 2
    )
    assert (
        main(
            [
                "make-sheet",
                str(answers),
                "--out-dir",
                out,
                "--sample",
                "0.5",
                "--golden",
                str(tmp_path / "missing.jsonl"),
            ]
        )
        == 2
    )
    assert capsys.readouterr().err.count("error:") == 5
