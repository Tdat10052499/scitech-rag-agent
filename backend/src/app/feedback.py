"""`POST /feedback` log (W6-D3-DAT-2, issue #147): one JSON line per rating or follow-up click."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from scitech_agent.trace import JsonlTraceWriter

from .schemas import FeedbackRequest

DEFAULT_FEEDBACK_FILE = Path("logs") / "feedback.jsonl"  # under DATA_DIR
_OFF = {"off", "false", "0", "none"}


def feedback_log_from_env(env: Mapping[str, str] | None = None) -> JsonlTraceWriter | None:
    """`FEEDBACK_LOG`: a file path, `off` for no log, empty for
    `<DATA_DIR>/logs/feedback.jsonl` (`DATA_DIR` empty: `data`)."""
    env = os.environ if env is None else env
    value = (env.get("FEEDBACK_LOG") or "").strip()
    if value.lower() in _OFF:
        return None
    if value:
        return JsonlTraceWriter(value)
    return JsonlTraceWriter(Path(env.get("DATA_DIR") or "data") / DEFAULT_FEEDBACK_FILE)


def feedback_record(request: FeedbackRequest, now: datetime | None = None) -> dict[str, str]:
    """The logged line: the request fields (without an absent `followup`) and `ts` in UTC."""
    now = now or datetime.now(timezone.utc)
    record = {"ts": now.isoformat(timespec="seconds").replace("+00:00", "Z")}
    record.update(request.model_dump(exclude_none=True))
    return record
