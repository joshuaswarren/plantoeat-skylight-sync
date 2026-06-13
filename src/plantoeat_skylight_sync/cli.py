"""The ``pte-skylight-sync`` CLI."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Optional, Tuple

import typer
from pyskylight import SkylightClient

from .config import SyncConfig
from .errors import SyncError
from .ical import fetch_feed, parse_feed
from .state import SyncState
from .sync import Syncer

app = typer.Typer(
    add_completion=False,
    help="Sync a Plan to Eat meal plan into Skylight Meals (one-way).",
    no_args_is_help=True,
)


def _build_client(cfg: SyncConfig) -> SkylightClient:
    if not (cfg.skylight_email and cfg.skylight_password):
        raise SyncError("SKYLIGHT_EMAIL and SKYLIGHT_PASSWORD are required for writes.")
    return SkylightClient.login(
        cfg.skylight_email, cfg.skylight_password, base_url=cfg.skylight_base_url
    )


def _window(cfg: SyncConfig, today: Optional[date] = None) -> Tuple[str, str]:
    base = today or date.today()
    start = (base - timedelta(days=cfg.past_days)).isoformat()
    end = (base + timedelta(days=cfg.future_days)).isoformat()
    return start, end


def _execute(dry_run: bool, allow_delete_override: Optional[bool]) -> None:
    try:
        cfg = SyncConfig.from_env()
        if not cfg.frame_id:
            raise SyncError("SKYLIGHT_FRAME_ID is required.")
        text = fetch_feed(cfg.ical_url)
        entries = parse_feed(text, default_slot=cfg.default_slot)
        client = _build_client(cfg)
        state = SyncState.load(cfg.state_path)
        syncer = Syncer(client, cfg.frame_id, state)
        window_start, window_end = _window(cfg)
        allow_delete = cfg.allow_delete if allow_delete_override is None else allow_delete_override
        report = syncer.reconcile(
            entries,
            window_start=window_start,
            window_end=window_end,
            dry_run=dry_run,
            allow_delete=allow_delete,
        )
    except SyncError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}))
        raise typer.Exit(code=1)

    typer.echo(
        json.dumps(
            {
                "ok": True,
                "dry_run": report.dry_run,
                "window": {"start": window_start, "end": window_end},
                **report.summary(),
                "actions": [a.__dict__ for a in report.actions],
            },
            indent=2,
        )
    )


@app.command()
def run(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Compute and print the plan without writing."
    ),
    allow_delete: Optional[bool] = typer.Option(
        None,
        "--allow-delete/--no-allow-delete",
        help="Remove sittings this tool created that are no longer in the feed.",
    ),
) -> None:
    """Reconcile the Plan to Eat feed into Skylight Meals."""
    _execute(dry_run=dry_run, allow_delete_override=allow_delete)


@app.command()
def plan() -> None:
    """Show what a sync would do, without writing anything (alias for run --dry-run)."""
    _execute(dry_run=True, allow_delete_override=None)


def main() -> None:  # pragma: no cover - entry point shim
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
