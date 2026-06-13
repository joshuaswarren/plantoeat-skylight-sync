"""Tests for SyncConfig."""

from __future__ import annotations

from pathlib import Path

import pytest

from plantoeat_skylight_sync.config import SyncConfig
from plantoeat_skylight_sync.errors import SyncError


def test_missing_ical_url_raises():
    with pytest.raises(SyncError):
        SyncConfig.from_env({})


def test_full_env():
    cfg = SyncConfig.from_env(
        {
            "PTE_ICAL_URL": "https://www.plantoeat.com/planner/X/recipes/plantoeat-ical",
            "SKYLIGHT_EMAIL": "you@example.com",
            "SKYLIGHT_PASSWORD": "pw",
            "SKYLIGHT_FRAME_ID": "55",
            "SKYLIGHT_BASE_URL": "https://example.test/",
            "SYNC_PAST_DAYS": "3",
            "SYNC_FUTURE_DAYS": "14",
            "SYNC_DEFAULT_SLOT": "lunch",
            "SYNC_ALLOW_DELETE": "true",
            "SYNC_STATE_PATH": "/tmp/state.json",
        }
    )
    assert cfg.frame_id == "55"
    assert cfg.skylight_base_url == "https://example.test"
    assert cfg.past_days == 3
    assert cfg.future_days == 14
    assert cfg.default_slot == "lunch"
    assert cfg.allow_delete is True
    assert cfg.state_path == Path("/tmp/state.json")


@pytest.mark.parametrize(
    "value,expected",
    [
        ("true", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("", False),
        (None, False),
    ],
)
def test_allow_delete_parsing(value, expected):
    env = {"PTE_ICAL_URL": "x"}
    if value is not None:
        env["SYNC_ALLOW_DELETE"] = value
    assert SyncConfig.from_env(env).allow_delete is expected


def test_defaults():
    cfg = SyncConfig.from_env({"PTE_ICAL_URL": "x"})
    assert cfg.past_days == 1
    assert cfg.future_days == 21
    assert cfg.default_slot == "dinner"
    assert cfg.allow_delete is False
    assert "plantoeat-skylight-sync" in str(cfg.state_path)
