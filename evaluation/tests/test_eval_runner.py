"""End-to-end checks on the toy data in tests/data; every number below is computed by hand.

Dev items in English that are answerable (gs-001..gs-005), with the doc ids each ranking returns:

  gs-001 factual     relevant {1}     ranking [X, 1, Y]            recall 0 / 1 / 1   rr 1/2
  gs-002 explanatory relevant {2}     ranking [2, 2, X]            recall 1 / 1 / 1   rr 1
  gs-003 comparison  relevant {1, 3}  ranking [X, X, 3, Y, Z, 1]   recall 0 / .5 / 1  rr 1/3
  gs-004 multi_hop   relevant {2, 4}  ranking [4, Y, 2]            recall .5 / 1 / 1  rr 1
  gs-005 factual     relevant {5}     ranking [X, Y, Z, X, Y, Z, X, Y, Z, X, 5, X]
                                      (hit at position 11, outside the top 10) recall 0/0/0, rr 0
(recall columns are @1 / @5 / @10)
"""

import json
from pathlib import Path

import pytest
import yaml

from scitech_eval.__main__ import main
from scitech_eval.golden import load_golden
from scitech_eval.retrievers import CannedRetriever, canned
from scitech_eval.runner import load_config, run_from_config, run_retrieval

REPO = Path(__file__).resolve().parents[2]
DATA = Path(__file__).parent / "data"


def _config(**overrides):
    config = {
        "name": "toy",
        "golden_path": str(DATA / "toy_golden.jsonl"),
        "retriever": {"factory": "scitech_eval.retrievers:canned", "params": {}},
    }
    config.update(overrides)
    return config


def _load(tmp_path, **overrides):
    # round-trip through YAML so that defaults come from load_config, as in a real run
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(_config(**overrides)), encoding="utf-8")
    return load_config(path)


@pytest.fixture
def run(tmp_path):
    def _run(**overrides):
        config = _load(tmp_path, **overrides)
        retriever = canned(str(DATA / "toy_rankings.json"))
        return run_retrieval(config, load_golden(DATA / "toy_golden.jsonl"), retriever)

    return _run


def test_headline_numbers_match_hand_computation(run):
    result = run()
    assert result["golden"]["n_evaluated"] == 5
    assert result["golden"]["n_unanswerable_excluded"] == 1
    m = result["metrics"]
    assert m["recall@1"]["mean"] == pytest.approx(0.3)
    assert m["recall@5"]["mean"] == pytest.approx(0.7)
    assert m["recall@10"]["mean"] == pytest.approx(0.8)
    assert m["mrr"]["mean"] == pytest.approx((0.5 + 1 + 1 / 3 + 1 + 0) / 5)
    for value in m.values():
        low, high = value["ci95"]
        assert low <= value["mean"] <= high


def test_by_type_breakdown_has_cell_sizes(run):
    by_type = run()["by_type"]
    assert by_type["factual"]["n"] == 2
    assert by_type["factual"]["recall@5"] == pytest.approx(0.5)
    assert by_type["factual"]["mrr"] == pytest.approx(0.25)
    assert by_type["comparison"]["n"] == 1
    assert by_type["comparison"]["recall@5"] == pytest.approx(0.5)
    assert by_type["comparison"]["mrr"] == pytest.approx(1 / 3)
    assert by_type["multi_hop"]["recall@1"] == pytest.approx(0.5)
    assert "unanswerable" not in by_type


def test_per_question_rows_keep_the_retrieved_list(run):
    rows = {r["id"]: r for r in run()["per_question"]}
    assert rows["gs-003"]["recall"] == {"1": 0.0, "5": 0.5, "10": 1.0}
    assert rows["gs-003"]["rr"] == pytest.approx(1 / 3)
    assert len(rows["gs-005"]["retrieved"]) == 10  # the retriever is asked for 10 chunks


def test_split_all_includes_test_items(run):
    result = run(split="all")
    assert result["golden"]["n_evaluated"] == 6  # gs-031 added; the Vietnamese item stays out
    assert result["metrics"]["recall@1"]["mean"] == pytest.approx(2.5 / 6)


def test_language_vi_is_reported_separately(run):
    result = run(language="vi")
    assert result["golden"]["n_evaluated"] == 1
    assert result["metrics"]["mrr"]["mean"] == 1.0


def test_custom_ks(run):
    result = run(ks=[3])
    assert set(result["metrics"]) == {"recall@3", "mrr"}
    # top-3 chunks find: gs-001 yes, gs-002 yes, gs-003 half, gs-004 both, gs-005 none
    assert result["metrics"]["recall@3"]["mean"] == pytest.approx((1 + 1 + 0.5 + 1 + 0) / 5)


def test_run_records_what_is_needed_to_reproduce_it(run):
    result = run(dataset_snapshot="toy-v1")
    assert result["dataset_snapshot"] == "toy-v1"
    assert result["config"]["split"] == "dev"
    assert len(result["golden"]["sha256"]) == 64
    assert result["git_commit"]
    assert result["timestamp"].endswith("Z")


def test_no_matching_items_is_an_error(run):
    with pytest.raises(ValueError, match="no answerable"):
        run(split="test", language="vi")


def test_missing_ranking_is_an_error(tmp_path):
    retriever = CannedRetriever({})
    config = _load(tmp_path)
    with pytest.raises(KeyError):
        run_retrieval(config, load_golden(DATA / "toy_golden.jsonl"), retriever)


def test_config_validation(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="golden_path"):
        load_config(bad)
    bad.write_text(
        "name: x\ngolden_path: g\nretriever: {factory: a:b}\nks: [0]\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="ks"):
        load_config(bad)


def test_shipped_example_config_runs_and_writes_a_run_file(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(REPO)
    path = run_from_config(Path("evaluation/configs/toy.yaml"), tmp_path)
    assert path.parent == tmp_path
    assert path.name.endswith("-toy-canned.json")
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["metrics"]["recall@5"]["mean"] == pytest.approx(0.7)

    argv = ["retrieval", "--config", "evaluation/configs/toy.yaml", "--out-dir", str(tmp_path)]
    assert main(argv) == 0
    assert "recall@10" in capsys.readouterr().out


def test_check_golden_command(capsys):
    assert main(["check-golden", str(DATA / "toy_golden.jsonl")]) == 0
    assert "OK" in capsys.readouterr().out
