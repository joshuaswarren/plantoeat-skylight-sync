"""Tests for the reconciler."""

from __future__ import annotations

from _helpers import FakeClient, mc, rcp, sit

from plantoeat_skylight_sync.ical import MealPlanEntry
from plantoeat_skylight_sync.mapping import dedup_key
from plantoeat_skylight_sync.state import SyncState
from plantoeat_skylight_sync.sync import Syncer

WS, WE = "2026-06-01", "2026-06-30"


def entry(date: str, slot: str, title: str, desc=None) -> MealPlanEntry:
    return MealPlanEntry(date=date, slot=slot, title=title, description=desc)


def test_dry_run_writes_nothing():
    client = FakeClient()
    state = SyncState()
    report = Syncer(client, "7", state).reconcile(
        [entry("2026-06-20", "dinner", "Tacos")], window_start=WS, window_end=WE, dry_run=True
    )
    assert report.dry_run is True
    assert report.summary()["created_recipes"] == 1
    assert report.summary()["created_sittings"] == 1
    assert client.created_recipes == []
    assert client.created_sittings == []
    assert state.recipes == {}


def test_apply_then_idempotent(tmp_path):
    client = FakeClient()
    state = SyncState(path=tmp_path / "s.json")
    syncer = Syncer(client, "7", state)
    entries = [entry("2026-06-20", "dinner", "Tacos", desc="2 tortillas")]

    first = syncer.reconcile(entries, window_start=WS, window_end=WE, dry_run=False)
    assert first.summary()["created_recipes"] == 1
    assert first.summary()["created_sittings"] == 1
    assert len(client.created_sittings) == 1
    assert state.recipes  # persisted mapping

    second = syncer.reconcile(entries, window_start=WS, window_end=WE, dry_run=False)
    assert second.summary()["created_sittings"] == 0
    assert second.summary()["skipped"] >= 1
    assert len(client.created_sittings) == 1  # no new writes


def test_existing_recipe_reused():
    client = FakeClient(recipes=[rcp("55", "Tacos")])
    report = Syncer(client, "7", SyncState()).reconcile(
        [entry("2026-06-20", "dinner", "Tacos")], window_start=WS, window_end=WE, dry_run=False
    )
    assert report.summary()["created_recipes"] == 0
    assert client.created_recipes == []
    assert client.created_sittings[0][2] == "55"  # sitting points at existing recipe


def test_no_matching_category_skips():
    client = FakeClient(categories=[mc("d", "Dinner")])
    report = Syncer(client, "7", SyncState()).reconcile(
        [entry("2026-06-20", "breakfast", "Eggs")], window_start=WS, window_end=WE, dry_run=False
    )
    assert report.summary()["skipped"] == 1
    assert report.summary()["created_sittings"] == 0


def test_window_filtering():
    report = Syncer(FakeClient(), "7", SyncState()).reconcile(
        [entry("2026-07-15", "dinner", "Future")], window_start=WS, window_end=WE, dry_run=True
    )
    assert report.summary()["total"] == 0


def test_stale_recorded_sitting_is_recreated():
    # State remembers a sitting whose id no longer exists in Skylight -> recreate.
    client = FakeClient(recipes=[rcp("55", "Tacos")], sittings=[])
    state = SyncState()
    key = dedup_key("2026-06-20", "dinner", "Tacos")
    state.record_sitting(
        key, recipe_id="55", sitting_id="gone", date="2026-06-20", slot="dinner", title="Tacos"
    )
    report = Syncer(client, "7", state).reconcile(
        [entry("2026-06-20", "dinner", "Tacos")], window_start=WS, window_end=WE, dry_run=False
    )
    assert report.summary()["created_sittings"] == 1
    assert len(client.created_sittings) == 1


def test_delete_orphans_when_enabled():
    existing = sit("999", "2026-06-10")
    client = FakeClient(sittings=[existing])
    state = SyncState()
    state.record_sitting(
        "oldkey", recipe_id="5", sitting_id="999", date="2026-06-10", slot="dinner", title="Old"
    )
    report = Syncer(client, "7", state).reconcile(
        [entry("2026-06-20", "dinner", "Tacos")],
        window_start=WS,
        window_end=WE,
        dry_run=False,
        allow_delete=True,
    )
    assert report.summary()["deleted_sittings"] == 1
    assert client.deleted == ["999"]
    assert "oldkey" not in state.sittings


def test_delete_dry_run_does_not_delete():
    client = FakeClient(sittings=[sit("999", "2026-06-10")])
    state = SyncState()
    state.record_sitting("oldkey", sitting_id="999", date="2026-06-10", slot="dinner", title="Old")
    report = Syncer(client, "7", state).reconcile(
        [], window_start=WS, window_end=WE, dry_run=True, allow_delete=True
    )
    assert report.summary()["deleted_sittings"] == 1
    assert client.deleted == []
    assert "oldkey" in state.sittings


def test_delete_skips_out_of_window():
    client = FakeClient()
    state = SyncState()
    state.record_sitting("oldkey", sitting_id="999", date="2026-01-01", slot="dinner", title="Old")
    report = Syncer(client, "7", state).reconcile(
        [], window_start=WS, window_end=WE, dry_run=False, allow_delete=True
    )
    assert report.summary()["deleted_sittings"] == 0
    assert client.deleted == []
