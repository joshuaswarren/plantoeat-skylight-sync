"""Tests for .env loading and the --env-file CLI option."""

from __future__ import annotations

import json
import os
from datetime import date, timedelta

from _helpers import FakeClient
from typer.testing import CliRunner

from plantoeat_skylight_sync import cli
from plantoeat_skylight_sync.config import load_dotenv

runner = CliRunner()


def test_load_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("FOO", raising=False)
    monkeypatch.delenv("BAR", raising=False)
    monkeypatch.setenv("BAZ", "already")
    env = tmp_path / ".env"
    env.write_text(
        "# a comment\n"
        "FOO=plain\n"
        "BAR='has;semicolon and # hash'\n"
        'QUOTED="double"\n'
        "BAZ=should-not-override\n"
        "noequalsline\n",
        encoding="utf-8",
    )
    load_dotenv(str(env))
    assert os.environ["FOO"] == "plain"
    assert os.environ["BAR"] == "has;semicolon and # hash"
    assert os.environ["QUOTED"] == "double"
    assert os.environ["BAZ"] == "already"  # existing env wins
    for k in ("FOO", "BAR", "QUOTED"):
        monkeypatch.delenv(k, raising=False)


def test_load_dotenv_missing_file_is_noop():
    load_dotenv("/nonexistent/path/.env")  # must not raise


def test_cli_env_file(tmp_path, monkeypatch):
    d = (date.today() + timedelta(days=2)).strftime("%Y%m%d")
    ics = (
        "BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:e\nSUMMARY:D: Tacos\n"
        f"DTSTART;VALUE=DATE:{d}\nEND:VEVENT\nEND:VCALENDAR\n"
    )
    env = tmp_path / ".env"
    env.write_text(
        "PTE_ICAL_URL=https://x/feed\n"
        "SKYLIGHT_EMAIL=you@example.com\n"
        "SKYLIGHT_PASSWORD=pw\n"
        "SKYLIGHT_FRAME_ID=7\n"
        f"SYNC_STATE_PATH={tmp_path / 'state.json'}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "fetch_feed", lambda url: ics)
    monkeypatch.setattr(cli, "_build_client", lambda cfg: FakeClient())
    result = runner.invoke(cli.app, ["--env-file", str(env), "run", "--dry-run"])
    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)["ok"] is True
