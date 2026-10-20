"""Run setup fields, timings, and `compare`; every number is computed by hand.

Run A replays tests/data/toy_rankings.json (see the table in test_eval_runner.py):

  per question      gs-001  gs-002  gs-003  gs-004  gs-005   mean
  recall@1           0       1       0       .5      0       0.3
  recall@5           1       1       .5      1       0       0.7
  recall@10          1       1       1       1       0       0.8
  rr                 1/2     1       1/3     1       0       0.5667

Run B replays the rankings below (X, Y are irrelevant documents):

  gs-001 relevant {1}     [1, X, Y]        recall 1 / 1 / 1       rr 1
  gs-002 relevant {2}     [2, X, Y]        recall 1 / 1 / 1       rr 1
  gs-003 relevant {1, 3}  [1, 3, X]        recall .5 / 1 / 1      rr 1
  gs-004 relevant {2, 4}  [X, 4, Y]        recall 0 / .5 / .5     rr 1/2
  gs-005 relevant {5}     [X, Y, 5]        recall 0 / 1 / 1       rr 1/3

  B means: recall@1 0.5, recall@5 0.9, recall@10 0.9, mrr 0.7667

Differences B - A per question, with wins / losses / ties of B:

  recall@1   +1, 0, +.5, -.5, 0       mean +0.2   2 / 1 / 2
  recall@5    0, 0, +.5, -.5, +1      mean +0.2   2 / 1 / 2
  recall@10   0, 0, 0, -.5, +1        mean +0.1   1 / 1 / 3
  mrr        +.5, 0, +2/3, -.5, +1/3  mean +0.2   3 / 1 / 1
"""

import json
import sys
import types
from pathlib import Path

import pytest
import yaml

from scitech_eval.__main__ import main
from scitech_eval.compare import compare_runs, format_comparison, load_run
from scitech_eval.golden import load_golden
from scitech_eval.retrievers import CannedRetriever, agent_retriever, canned
from scitech_eval.runner import load_config, run_from_config, run_retrieval, write_run

DATA = Path(__file__).parent / "data"


def _doc(doc_id, n=0):
    return {"chunk_id": f"{doc_id}#{n}", "doc_id": doc_id}


RANKINGS_B = {
    "Toy question one?": [_doc("2001.00001"), _doc("2009.00001", 1), _doc("2009.00002", 2)],
    "Toy question two?": [_doc("2001.00002"), _doc("2009.00001", 1), _doc("2009.00002", 2)],
    "Toy question three?": [_doc("2001.00001"), _doc("2001.00003", 1), _doc("2009.00001", 2)],
    "Toy question four?": [_doc("2009.00001"), _doc("2001.00004", 1), _doc("2009.00002", 2)],
    "Toy question five?": [_doc("2009.00001"), _doc("2009.00002", 1), _doc("2001.00005", 2)],
}


def _config(tmp_path, **overrides):
    config = {
        "name": "toy",
        "golden_path": str(DATA / "toy_golden.jsonl"),
        "retriever": {"factory": "scitech_eval.retrievers:canned", "params": {}},
    }
    config.update(overrides)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return load_config(path)


def _run_a(tmp_path, **overrides):
    retriever = canned(str(DATA / "toy_rankings.json"))
    config = _config(tmp_path, name="run-a", **overrides)
    return run_retrieval(config, load_golden(DATA / "toy_golden.jsonl"), retriever)


def _run_b(tmp_path, **overrides):
    config = _config(tmp_path, name="run-b", **overrides)
    return run_retrieval(
        config, load_golden(DATA / "toy_golden.jsonl"), CannedRetriever(RANKINGS_B)
    )


def test_run_records_the_setup_given_in_the_config(tmp_path):
    result = _run_a(
        tmp_path,
        retriever_type="dense",
        embedding_model="BAAI/bge-base-en-v1.5",
        index_snapshot="qdrant-2026-10-21",
        notes="first dense run",
        dataset_snapshot="arxiv-307",
    )
    assert result["retriever_type"] == "dense"
    assert result["embedding_model"] == "BAAI/bge-base-en-v1.5"
    assert result["index_snapshot"] == "qdrant-2026-10-21"
    assert result["dataset_snapshot"] == "arxiv-307"
    assert result["notes"] == "first dense run"
    assert result["config"]["retriever_type"] == "dense"
    assert result["schema_version"] == 2


def test_setup_fields_have_defaults_and_are_validated(tmp_path):
    result = _run_a(tmp_path)
    assert result["retriever_type"] == "unspecified"
    assert result["embedding_model"] is None
    assert result["index_snapshot"] == "unspecified"
    assert result["notes"] == ""
    with pytest.raises(ValueError, match="'retriever_type'"):
        _config(tmp_path, retriever_type=3)
    with pytest.raises(ValueError, match="'embedding_model'"):
        _config(tmp_path, embedding_model=["a"])


def test_blank_setup_values_in_the_yaml_file_get_the_defaults(tmp_path):
    # "notes:" with nothing after it is loaded as None; it must mean "not given", not stop the run.
    path = tmp_path / "blank.yaml"
    path.write_text(
        "name: blank\n"
        f"golden_path: {DATA / 'toy_golden.jsonl'}\n"
        "retriever:\n"
        "  factory: scitech_eval.retrievers:canned\n"
        "retriever_type:\n"
        "index_snapshot:\n"
        "dataset_snapshot:\n"
        "notes:\n"
        "embedding_model:\n",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config["retriever_type"] == "unspecified"
    assert config["index_snapshot"] == "unspecified"
    assert config["dataset_snapshot"] == "unspecified"
    assert config["notes"] == ""
    assert config["embedding_model"] is None


def test_blank_bootstrap_means_the_defaults_and_a_wrong_type_is_rejected(tmp_path):
    # "bootstrap:" with nothing under it used to fail later with 'NoneType' has no attribute 'get'.
    result = _run_a(tmp_path, bootstrap=None)
    assert result["config"]["bootstrap"] == {}
    assert result["metrics"]["recall@1"]["mean"] == pytest.approx(0.3)
    with pytest.raises(ValueError, match="'bootstrap' must be a mapping"):
        _config(tmp_path, bootstrap=5)


def test_timings_come_from_the_clock(tmp_path):
    ticks = iter(i * 0.25 for i in range(100))  # every read of the clock advances by 0.25 s
    config = _config(tmp_path)
    retriever = canned(str(DATA / "toy_rankings.json"))
    result = run_retrieval(
        config, load_golden(DATA / "toy_golden.jsonl"), retriever, clock=ticks.__next__
    )
    # reads: start, then before and after each of the 5 searches, then the end = 12 reads
    assert result["timings"]["run_seconds"] == pytest.approx(11 * 0.25)
    assert result["timings"]["search_seconds"] == {"total": 1.25, "median": 0.25, "max": 0.25}
    assert [r["search_seconds"] for r in result["per_question"]] == [0.25] * 5


def test_real_clock_gives_non_negative_timings(tmp_path):
    result = _run_a(tmp_path)
    assert result["timings"]["run_seconds"] >= result["timings"]["search_seconds"]["total"] >= 0
    assert all(r["search_seconds"] >= 0 for r in result["per_question"])


SAME_DATA = {"index_snapshot": "idx-1", "dataset_snapshot": "ds-1"}


def test_compare_numbers_match_hand_computation(tmp_path):
    result = compare_runs([_run_a(tmp_path, **SAME_DATA), _run_b(tmp_path, **SAME_DATA)])
    means = {n: [v["mean"] for v in values] for n, values in result["metrics"].items()}
    assert means["recall@1"] == pytest.approx([0.3, 0.5])
    assert means["recall@5"] == pytest.approx([0.7, 0.9])
    assert means["recall@10"] == pytest.approx([0.8, 0.9])
    assert means["mrr"] == pytest.approx(
        [(0.5 + 1 + 1 / 3 + 1 + 0) / 5, (1 + 1 + 1 + 0.5 + 1 / 3) / 5]
    )

    (paired,) = result["paired"]
    assert (paired["label"], paired["baseline"], paired["n"]) == ("B", "A", 5)
    expected = {
        "recall@1": (0.2, 2, 1, 2),
        "recall@5": (0.2, 2, 1, 2),
        "recall@10": (0.1, 1, 1, 3),
        "mrr": (0.2, 3, 1, 1),
    }
    for name, (diff, wins, losses, ties) in expected.items():
        m = paired["metrics"][name]
        assert m["mean_diff"] == pytest.approx(diff), name
        assert (m["wins"], m["losses"], m["ties"]) == (wins, losses, ties), name
        assert m["ci95"][0] <= m["mean_diff"] <= m["ci95"][1], name
    assert result["warnings"] == []

    # recall rows also give the difference in questions (mean diff x 5); MRR has none
    assert paired["metrics"]["recall@1"]["questions_diff"] == pytest.approx(1.0)
    assert paired["metrics"]["recall@10"]["questions_diff"] == pytest.approx(0.5)
    assert paired["metrics"]["mrr"]["questions_diff"] is None


def test_compare_warns_when_the_index_or_dataset_snapshot_differs(tmp_path):
    a = _run_a(tmp_path, **SAME_DATA)
    b = _run_b(tmp_path, index_snapshot="idx-2", dataset_snapshot="ds-2")
    text = " ".join(compare_runs([a, b])["warnings"])
    assert "B has index_snapshot idx-2, A has idx-1" in text
    assert "B has dataset_snapshot ds-2, A has ds-1" in text


def test_compare_warns_about_each_run_that_left_a_snapshot_unspecified(tmp_path):
    a = _run_a(tmp_path, dataset_snapshot="ds-1")
    b = _run_b(tmp_path, **SAME_DATA)
    warnings = compare_runs([a, b])["warnings"]
    assert any(w.startswith("A did not record index_snapshot") for w in warnings)
    assert not any(w.startswith("B did not record") for w in warnings)
    assert any("B has index_snapshot idx-1, A has unspecified" in w for w in warnings)


def test_report_shows_the_difference_in_questions(tmp_path):
    text = format_comparison(compare_runs([_run_a(tmp_path), _run_b(tmp_path)]))
    assert "questions" in text and "+1.0" in text and "+0.5" in text
    rows = {line.split()[0]: line.split() for line in text.splitlines() if line.startswith("mrr")}
    assert rows["mrr"][2] == "-"


def test_compare_with_a_different_golden_file_pairs_the_shared_questions(tmp_path):
    a, b = _run_a(tmp_path), _run_b(tmp_path)
    b["golden"]["sha256"] = "0" * 64
    b["per_question"] = b["per_question"][:4]  # gs-005 was not scored in B
    result = compare_runs([a, b])
    assert result["paired"][0]["n"] == 4
    text = " ".join(result["warnings"])
    assert "different golden file" in text
    assert "share 4 questions" in text


def test_compare_warns_when_the_runs_scored_different_items(tmp_path):
    result = compare_runs([_run_a(tmp_path), _run_b(tmp_path, query="standalone_query")])
    assert any("query=standalone_query" in w for w in result["warnings"])


def test_compare_leaves_out_metrics_that_are_not_in_every_run(tmp_path):
    result = compare_runs([_run_a(tmp_path), _run_b(tmp_path, ks=[1, 3])])
    assert list(result["metrics"]) == ["recall@1", "mrr"]
    assert any("recall@10" in w and "left out" in w for w in result["warnings"])


def test_compare_reads_runs_without_the_new_fields(tmp_path):
    a, b = _run_a(tmp_path), _run_b(tmp_path)
    for run in (a, b):  # what a schema version 1 run file looks like
        for key in ("retriever_type", "embedding_model", "index_snapshot", "notes", "timings"):
            del run[key]
    result = compare_runs([a, b])
    assert result["runs"][0]["retriever_type"] == "unspecified"
    assert "search median" not in format_comparison(result)


def test_compare_needs_two_runs_and_common_questions(tmp_path):
    a, b = _run_a(tmp_path), _run_b(tmp_path)
    with pytest.raises(ValueError, match="at least two"):
        compare_runs([a])
    b["per_question"] = []
    with pytest.raises(ValueError, match="no question in common"):
        compare_runs([a, b])


def test_report_text_has_the_setup_the_table_and_the_paired_part(tmp_path):
    a = _run_a(tmp_path, retriever_type="dense", embedding_model="bge", index_snapshot="idx-1")
    b = _run_b(tmp_path, retriever_type="bm25", notes="keyword only")
    text = format_comparison(compare_runs([a, b]))
    assert "A  run-a  type=dense  embedding=bge  index=idx-1" in text
    assert "B  run-b  type=bm25  embedding=-" in text
    assert "notes: keyword only" in text
    assert "recall@5" in text and "0.700" in text and "0.900" in text
    assert "B against A, 5 questions in common" in text
    assert "mean diff" in text and "wins" in text and "+0.200" in text


def test_compare_command(tmp_path, capsys):
    path_a = write_run(_run_a(tmp_path), tmp_path)
    path_b = write_run(_run_b(tmp_path), tmp_path)
    assert main(["compare", str(path_a), str(path_b)]) == 0
    out = capsys.readouterr().out
    assert "recall@10" in out and "B against A" in out
    assert load_run(path_a)["name"] == "run-a"


def test_compare_command_errors(tmp_path, capsys):
    path_a = write_run(_run_a(tmp_path), tmp_path)
    with pytest.raises(SystemExit) as one_file:
        main(["compare", str(path_a)])
    assert one_file.value.code == 2

    assert main(["compare", str(path_a), str(tmp_path / "missing.json")]) == 2
    assert "missing.json" in capsys.readouterr().err

    not_a_run = tmp_path / "other.json"
    not_a_run.write_text(json.dumps({"hello": 1}), encoding="utf-8")
    assert main(["compare", str(path_a), str(not_a_run)]) == 2
    assert "not a run file" in capsys.readouterr().err


def test_shipped_example_config_records_its_setup(tmp_path, monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[2])
    run = json.loads(
        run_from_config(Path("evaluation/configs/toy.yaml"), tmp_path).read_text("utf-8")
    )
    assert run["retriever_type"] == "canned"
    assert run["embedding_model"] is None
    assert run["index_snapshot"] == "toy"
    assert run["notes"].startswith("Replays")


def test_agent_retriever_passes_the_name_and_params_as_strings(monkeypatch):
    seen = {}
    module = types.ModuleType("scitech_agent.retrieval.hybrid")
    module.retriever_from_env = lambda env: seen.update(env) or "retriever"
    for name in ("scitech_agent", "scitech_agent.retrieval"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "scitech_agent.retrieval.hybrid", module)
    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")
    monkeypatch.setenv("RRF_K", "10")

    assert agent_retriever("hybrid", RRF_K=60, EMBEDDING_QUERY_PREFIX="Q:") == "retriever"
    assert seen["RETRIEVER"] == "hybrid"
    assert seen["RRF_K"] == "60"  # the param wins over the process environment
    assert seen["EMBEDDING_QUERY_PREFIX"] == "Q:"
    assert seen["QDRANT_URL"] == "http://qdrant:6333"  # the rest comes from the environment


def test_agent_retriever_rejects_an_unknown_name():
    with pytest.raises(ValueError, match="dense, bm25, hybrid"):
        agent_retriever("tfidf")


@pytest.mark.parametrize("kind", ["dense", "bm25", "hybrid"])
def test_retrieval_v1_configs_agree_except_for_the_retriever(kind):
    root = Path(__file__).resolve().parents[2]
    config = load_config(root / f"evaluation/configs/retrieval-v1-{kind}.yaml")
    hybrid = load_config(root / "evaluation/configs/retrieval-v1-hybrid.yaml")
    for key in (
        "golden_path",
        "split",
        "language",
        "query",
        "ks",
        "dataset_snapshot",
        "index_snapshot",
        "bootstrap",
    ):
        assert config[key] == hybrid[key], key
    assert config["name"] == f"retrieval-v1-{kind}"
    assert config["retriever_type"] == kind
    assert config["retriever"]["factory"] == "scitech_eval.retrievers:agent_retriever"
    assert config["retriever"]["params"]["retriever"] == kind
    assert "unspecified" not in (config["index_snapshot"], config["dataset_snapshot"])
    assert bool(config["embedding_model"]) == (kind != "bm25")
