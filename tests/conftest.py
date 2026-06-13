"""Pytest fixtures."""

from __future__ import annotations

import pytest

_ENV_VARS = [
    "PTE_ICAL_URL",
    "SKYLIGHT_EMAIL",
    "SKYLIGHT_PASSWORD",
    "SKYLIGHT_FRAME_ID",
    "SKYLIGHT_BASE_URL",
    "SYNC_PAST_DAYS",
    "SYNC_FUTURE_DAYS",
    "SYNC_DEFAULT_SLOT",
    "SYNC_ALLOW_DELETE",
    "SYNC_STATE_PATH",
    "XDG_STATE_HOME",
]


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path, monkeypatch):
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    yield
