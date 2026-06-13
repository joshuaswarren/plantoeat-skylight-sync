"""Environment-driven configuration for the sync.

Environment variables:
  PTE_ICAL_URL        Plan to Eat iCal feed URL (or an ``op://`` reference). Required.
  SKYLIGHT_EMAIL      Skylight account email (or ``op://``). Required for writes.
  SKYLIGHT_PASSWORD   Skylight account password (or ``op://``). Required for writes.
  SKYLIGHT_FRAME_ID   Skylight frame/household id. Required.
  SKYLIGHT_BASE_URL   Override the Skylight API base URL.
  SYNC_PAST_DAYS      Days of history to reconcile (default 1).
  SYNC_FUTURE_DAYS    Days ahead to reconcile (default 21).
  SYNC_DEFAULT_SLOT   Slot for events with no inferable course (default "dinner").
  SYNC_ALLOW_DELETE   "true" to remove sittings this tool created that left the feed.
  SYNC_STATE_PATH     Override the local state file path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from pyskylight.config import resolve_secret
from pyskylight.constants import DEFAULT_BASE_URL

from .errors import SyncError

DEFAULT_PAST_DAYS = 1
DEFAULT_FUTURE_DAYS = 21
DEFAULT_SLOT = "dinner"


def _bool(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _default_state_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "state"
    )
    return Path(base) / "plantoeat-skylight-sync" / "state.json"


def load_dotenv(path: str) -> None:
    """Load ``KEY=VALUE`` lines from a .env file into the environment.

    Existing environment variables win (``setdefault``). Surrounding single/double
    quotes are stripped. Lines are parsed literally (no shell interpretation), so
    values may safely contain characters like ``;`` or ``#`` mid-value.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


@dataclass
class SyncConfig:
    ical_url: str
    skylight_email: Optional[str]
    skylight_password: Optional[str]
    skylight_base_url: str
    frame_id: Optional[str]
    past_days: int
    future_days: int
    default_slot: str
    allow_delete: bool
    state_path: Path
    fetch_recipe_content: bool = True

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "SyncConfig":
        source: Mapping[str, str] = env if env is not None else os.environ
        ical_url = resolve_secret(source.get("PTE_ICAL_URL"))
        if not ical_url:
            raise SyncError("PTE_ICAL_URL is required (the Plan to Eat iCal feed URL).")
        state_override = source.get("SYNC_STATE_PATH")
        return cls(
            ical_url=ical_url,
            skylight_email=resolve_secret(source.get("SKYLIGHT_EMAIL")),
            skylight_password=resolve_secret(source.get("SKYLIGHT_PASSWORD")),
            skylight_base_url=(source.get("SKYLIGHT_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
            frame_id=source.get("SKYLIGHT_FRAME_ID"),
            past_days=int(source.get("SYNC_PAST_DAYS", DEFAULT_PAST_DAYS)),
            future_days=int(source.get("SYNC_FUTURE_DAYS", DEFAULT_FUTURE_DAYS)),
            default_slot=source.get("SYNC_DEFAULT_SLOT", DEFAULT_SLOT),
            allow_delete=_bool(source.get("SYNC_ALLOW_DELETE")),
            state_path=Path(state_override) if state_override else _default_state_path(),
            fetch_recipe_content=_bool(source.get("SYNC_FETCH_RECIPE_CONTENT", "true")),
        )
