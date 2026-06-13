"""Tests for the pte-skylight-sync CLI."""

from __future__ import annotations

import json
from datetime import date, timedelta

from _helpers import FakeClient
from typer.testing import CliRunner

from plantoeat_skylight_sync import cli

runner = CliRunner()


def _ics_for(d: date) -> str:
    return (
        "BEGIN:VCALENDAR\nVERSION:2.0\n"
        "BEGIN:VEVENT\nUID:e1\nSUMMARY:Dinner: Tacos\n"
        f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}\nEND:VEVENT\n"
        "END:VCALENDAR\n"
    )


def _set_env(monkeypatch, tmp_path):
    monkeypatch.setenv("PTE_ICAL_URL", "https://www.plantoeat.com/planner/X/recipes/plantoeat-ical")
    monkeypatch.setenv("SKYLIGHT_EMAIL", "you@example.com")
    monkeypatch.setenv("SKYLIGHT_PASSWORD", "pw")
    monkeypatch.setenv("SKYLIGHT_FRAME_ID", "7")
    monkeypatch.setenv("SYNC_STATE_PATH", str(tmp_path / "state.json"))


def test_run_dry_run(monkeypatch, tmp_path):
    _set_env(monkeypatch, tmp_path)
    client = FakeClient()
    monkeypatch.setattr(cli, "fetch_feed", lambda url: _ics_for(date.today() + timedelta(days=2)))
    monkeypatch.setattr(cli, "_build_client", lambda cfg: client)
    result = runner.invoke(cli.app, ["run", "--dry-run"])
    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["ok"] is True
    assert out["dry_run"] is True
    assert out["created_sittings"] == 1
    assert client.created_sittings == []  # dry run -> nothing applied


def test_run_applies(monkeypatch, tmp_path):
    _set_env(monkeypatch, tmp_path)
    client = FakeClient()
    monkeypatch.setattr(cli, "fetch_feed", lambda url: _ics_for(date.today() + timedelta(days=2)))
    monkeypatch.setattr(cli, "_build_client", lambda cfg: client)
    result = runner.invoke(cli.app, ["run"])
    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["dry_run"] is False
    assert len(client.created_sittings) == 1


def test_plan_command(monkeypatch, tmp_path):
    _set_env(monkeypatch, tmp_path)
    client = FakeClient()
    monkeypatch.setattr(cli, "fetch_feed", lambda url: _ics_for(date.today() + timedelta(days=2)))
    monkeypatch.setattr(cli, "_build_client", lambda cfg: client)
    result = runner.invoke(cli.app, ["plan"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["dry_run"] is True


def test_missing_ical_url(monkeypatch, tmp_path):
    monkeypatch.setenv("SKYLIGHT_FRAME_ID", "7")
    result = runner.invoke(cli.app, ["run", "--dry-run"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["ok"] is False


def test_missing_frame_id(monkeypatch, tmp_path):
    monkeypatch.setenv("PTE_ICAL_URL", "https://x/feed")
    result = runner.invoke(cli.app, ["run", "--dry-run"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["ok"] is False


def test_build_client_requires_skylight_creds(monkeypatch, tmp_path):
    from plantoeat_skylight_sync.config import SyncConfig
    from plantoeat_skylight_sync.errors import SyncError

    cfg = SyncConfig.from_env({"PTE_ICAL_URL": "x", "SKYLIGHT_FRAME_ID": "7"})
    try:
        cli._build_client(cfg)
        assert False, "expected SyncError"
    except SyncError:
        pass
