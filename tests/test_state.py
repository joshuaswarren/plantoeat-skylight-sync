"""Tests for the local sync state."""

from __future__ import annotations

from plantoeat_skylight_sync.state import SyncState


def test_load_missing_returns_empty(tmp_path):
    st = SyncState.load(tmp_path / "nope.json")
    assert st.sittings == {} and st.recipes == {}


def test_load_none_path():
    st = SyncState.load(None)
    assert st.path is None
    st.save()  # no-op, must not raise


def test_roundtrip(tmp_path):
    path = tmp_path / "s.json"
    st = SyncState(path=path)
    st.record_recipe("tacos", "55")
    st.record_sitting(
        "k1", recipe_id="55", sitting_id="900", date="2026-06-20", slot="dinner", title="Tacos"
    )
    st.save()

    loaded = SyncState.load(path)
    assert loaded.recipes["tacos"] == "55"
    assert loaded.sittings["k1"]["sitting_id"] == "900"


def test_corrupt_file_returns_empty(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{broken", encoding="utf-8")
    assert SyncState.load(path).sittings == {}


def test_remove(tmp_path):
    st = SyncState(path=tmp_path / "s.json")
    st.record_sitting("k1", sitting_id="1")
    st.remove_sitting("k1")
    st.remove_sitting("missing")  # idempotent
    assert "k1" not in st.sittings
