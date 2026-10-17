"""The retriever interface of the agent, and the `query` setting for follow-up items."""

from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from scitech_eval.__main__ import main
from scitech_eval.golden import GoldenItem, load_golden
from scitech_eval.retrievers import CannedRetriever
from scitech_eval.runner import load_config, run_retrieval

DATA = Path(__file__).parent / "data"


def _load(tmp_path, **overrides):
    config = {
        "name": "toy",
        "golden_path": str(DATA / "toy_golden.jsonl"),
        "retriever": {"factory": "scitech_eval.retrievers:canned", "params": {}},
    }
    config.update(overrides)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return load_config(path)


def _item(**overrides):
    base = {
        "id": "gs-001",
        "question": "Plain question?",
        "type": "factual",
        "relevant_doc_ids": ("2001.00001",),
        "reference_answer": "A.",
        "notes": "plain.",
        "author": "LDN",
        "split": "dev",
    }
    base.update(overrides)
    return GoldenItem(**base)


def test_retriever_with_the_agent_interface_can_be_scored(tmp_path):
    """An object shaped like the agent's Retriever (filters argument, extra fields) works as is."""

    @dataclass(frozen=True)
    class ScoredChunk:
        chunk_id: str
        doc_id: str
        score: float
        text: str = ""

    class AgentLike:
        def search(self, query, k, filters=None):
            assert filters is None
            return [ScoredChunk("2001.00001#0", "2001.00001", 0.9)][:k]

    result = run_retrieval(_load(tmp_path), load_golden(DATA / "toy_golden.jsonl"), AgentLike())
    rows = {r["id"]: r for r in result["per_question"]}
    assert rows["gs-001"]["recall"]["1"] == 1.0
    assert rows["gs-002"]["recall"]["1"] == 0.0


def test_query_mode_standalone_query_is_used_and_recorded(tmp_path):
    items = [
        _item(
            id="gs-001",
            question="Does it help?",
            type="follow_up",
            history=({"role": "user", "content": "x"},),
            standalone_query="Does prompting help reduce bias?",
        ),
        _item(id="gs-002", relevant_doc_ids=("2001.00002",)),
    ]
    retriever = CannedRetriever(
        {
            "Does prompting help reduce bias?": [{"chunk_id": "c1", "doc_id": "2001.00001"}],
            "Plain question?": [{"chunk_id": "c2", "doc_id": "2001.00002"}],
        }
    )

    result = run_retrieval(_load(tmp_path, query="standalone_query"), items, retriever)
    assert result["config"]["query"] == "standalone_query"
    assert [r["query"] for r in result["per_question"]] == [
        "Does prompting help reduce bias?",
        "Plain question?",
    ]
    assert result["metrics"]["recall@1"]["mean"] == 1.0

    # default: the follow-up question is sent as asked, which this retriever does not know
    with pytest.raises(KeyError, match="Does it help"):
        run_retrieval(_load(tmp_path), items, retriever)


def test_query_defaults_to_question_and_is_validated(tmp_path):
    assert _load(tmp_path)["query"] == "question"
    with pytest.raises(ValueError, match="'query'"):
        _load(tmp_path, query="rewrite")


def test_check_golden_on_a_missing_file_prints_an_error_line(tmp_path, capsys):
    assert main(["check-golden", str(tmp_path / "missing.jsonl")]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err and "missing.jsonl" in captured.err
