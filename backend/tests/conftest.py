"""Shared pytest setup of the backend tests: the offline demo agent unless a test says otherwise
(the real agent needs an index and an LLM server, W4-D2-DAT-1)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app import main


@pytest.fixture(autouse=True)
def demo_agent_mode(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("AGENT_MODE", "demo")
    main._demo_agent.cache_clear()
    main._real_agent.cache_clear()
    yield
    main._demo_agent.cache_clear()
    main._real_agent.cache_clear()
