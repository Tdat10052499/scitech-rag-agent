"""Shared pytest setup of the agent tests."""

from __future__ import annotations


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: needs a running service (Qdrant at QDRANT_URL); skipped if absent"
    )
