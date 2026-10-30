"""`POST /feedback` (W6-D3-DAT-2, issue #147)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import main
from app.feedback import feedback_log_from_env, feedback_record
from app.schemas import FeedbackRequest


class ListLog:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def write(self, record: dict[str, Any]) -> None:
        self.records.append(dict(record))


@pytest.fixture
def log() -> Iterator[ListLog]:
    log = ListLog()
    main.app.dependency_overrides[main.get_feedback_log] = lambda: log
    yield log
    main.app.dependency_overrides.pop(main.get_feedback_log, None)


def post(body: dict[str, Any]) -> Any:
    return TestClient(main.app).post("/feedback", json=body)


def test_answer_rating_is_logged(log: ListLog) -> None:
    response = post({"session_id": "s1", "message_id": "m1", "target": "answer", "rating": "up"})
    assert response.status_code == 204
    assert response.content == b""
    [record] = log.records
    assert {k: v for k, v in record.items() if k != "ts"} == {
        "session_id": "s1",
        "message_id": "m1",
        "target": "answer",
        "rating": "up",
    }
    assert record["ts"].endswith("Z")


def test_followup_click_keeps_the_text(log: ListLog) -> None:
    body = {
        "session_id": "s1",
        "message_id": "m1",
        "target": "followup",
        "rating": "click",
        "followup": "What is LoRA?",
    }
    assert post(body).status_code == 204
    assert log.records[0]["followup"] == "What is LoRA?"


@pytest.mark.parametrize(
    "body",
    [
        {"session_id": "s1", "message_id": "m1", "target": "answer", "rating": "click"},
        {"session_id": "s1", "message_id": "m1", "target": "answer", "rating": "up", "followup": "x"},  # noqa: E501
        {"session_id": "s1", "message_id": "m1", "target": "followup", "rating": "down"},
        {"session_id": "s1", "message_id": "", "target": "answer", "rating": "up"},
        {"session_id": "s1", "message_id": "m1", "target": "source", "rating": "up"},
        {"session_id": "s1", "message_id": "m1", "target": "answer", "rating": "5"},
        {"message_id": "m1", "target": "answer", "rating": "up"},
    ],
)
def test_invalid_body_is_rejected_and_not_logged(log: ListLog, body: dict[str, Any]) -> None:
    assert post(body).status_code == 422
    assert log.records == []


def test_log_off_still_accepts(monkeypatch: pytest.MonkeyPatch) -> None:
    main.app.dependency_overrides[main.get_feedback_log] = lambda: None
    try:
        body = {"session_id": "s1", "message_id": "m1", "target": "answer", "rating": "down"}
        assert post(body).status_code == 204
    finally:
        main.app.dependency_overrides.pop(main.get_feedback_log, None)


def test_log_from_env(tmp_path: Path) -> None:
    assert feedback_log_from_env({"FEEDBACK_LOG": "off"}) is None
    default = feedback_log_from_env({"DATA_DIR": str(tmp_path)})
    assert default is not None
    assert default.path == tmp_path / "logs" / "feedback.jsonl"
    explicit = feedback_log_from_env({"FEEDBACK_LOG": str(tmp_path / "f.jsonl")})
    assert explicit is not None
    assert explicit.path == tmp_path / "f.jsonl"


def test_file_gets_one_json_line_per_request(tmp_path: Path) -> None:
    log = feedback_log_from_env({"FEEDBACK_LOG": str(tmp_path / "logs" / "feedback.jsonl")})
    assert log is not None
    request = FeedbackRequest(session_id="s1", message_id="m1", target="answer", rating="up")
    now = datetime(2026, 10, 29, 10, 0, tzinfo=timezone.utc)
    log.write(feedback_record(request, now))
    log.write(feedback_record(request, now))
    lines = (tmp_path / "logs" / "feedback.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["ts"] for line in lines] == ["2026-10-29T10:00:00Z"] * 2
