"""Tests for recipe-content enrichment during reconcile."""

from __future__ import annotations

from _helpers import FakeClient
from pyskylight.models import Recipe

from plantoeat_skylight_sync import sync
from plantoeat_skylight_sync.config import SyncConfig
from plantoeat_skylight_sync.ical import MealPlanEntry
from plantoeat_skylight_sync.recipe import RecipeContent
from plantoeat_skylight_sync.state import SyncState

WS, WE = "2026-06-01", "2026-06-30"


def _entry():
    return MealPlanEntry(
        date="2026-06-20",
        slot="dinner",
        title="Tacos",
        recipe_url="https://app.plantoeat.com/recipes/1",
    )


def _recipe(rid, summary, description):
    return Recipe.from_jsonapi(
        {"id": rid, "attributes": {"summary": summary, "description": description}}
    )


def test_create_recipe_with_fetched_content(monkeypatch):
    monkeypatch.setattr(
        sync,
        "fetch_recipe_content",
        lambda url, http=None: RecipeContent(
            ingredients=["1 lb beef"], directions="Cook.", source_url="http://s"
        ),
    )
    client = FakeClient()
    sync.Syncer(client, "7", SyncState()).reconcile(
        [_entry()], window_start=WS, window_end=WE, dry_run=False
    )
    summary, cat, desc = client.created_recipes[0]
    assert "Ingredients:" in desc and "1 lb beef" in desc


def test_update_existing_bare_recipe(monkeypatch):
    monkeypatch.setattr(
        sync,
        "fetch_recipe_content",
        lambda url, http=None: RecipeContent(ingredients=["1 lb beef"], source_url="http://s"),
    )
    # existing recipe whose description is just a link (no real content)
    client = FakeClient(recipes=[_recipe("55", "Tacos", "https://app.plantoeat.com/recipes/1")])
    report = sync.Syncer(client, "7", SyncState()).reconcile(
        [_entry()], window_start=WS, window_end=WE, dry_run=False
    )
    assert client.created_recipes == []  # reused, not recreated
    assert report.summary()["updated_recipes"] == 1
    assert "Ingredients:" in client.updated_recipes[0][1]["description"]


def test_no_update_when_content_already_present(monkeypatch):
    def boom(url, http=None):
        raise AssertionError("should not fetch when content already present")

    monkeypatch.setattr(sync, "fetch_recipe_content", boom)
    client = FakeClient(recipes=[_recipe("55", "Tacos", "Ingredients:\n- beef")])
    report = sync.Syncer(client, "7", SyncState()).reconcile(
        [_entry()], window_start=WS, window_end=WE, dry_run=False
    )
    assert report.summary()["updated_recipes"] == 0
    assert client.updated_recipes == []


def test_fetch_disabled_skips_content(monkeypatch):
    def boom(url, http=None):
        raise AssertionError("should not fetch when fetch_content=False")

    monkeypatch.setattr(sync, "fetch_recipe_content", boom)
    client = FakeClient()
    sync.Syncer(client, "7", SyncState()).reconcile(
        [_entry()], window_start=WS, window_end=WE, dry_run=False, fetch_content=False
    )
    assert len(client.created_recipes) == 1  # created without fetching


def test_config_fetch_recipe_content_flag():
    assert SyncConfig.from_env({"PTE_ICAL_URL": "x"}).fetch_recipe_content is True
    assert (
        SyncConfig.from_env(
            {"PTE_ICAL_URL": "x", "SYNC_FETCH_RECIPE_CONTENT": "false"}
        ).fetch_recipe_content
        is False
    )
