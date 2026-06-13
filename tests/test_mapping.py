"""Tests for the pure mapping helpers."""

from __future__ import annotations

from datetime import datetime

from _helpers import mc

from plantoeat_skylight_sync.mapping import (
    choose_category_id,
    clean_title,
    dedup_key,
    infer_slot,
    normalize_title,
)


def test_normalize_title():
    assert normalize_title("  Sheet  Pan   Chicken ") == "sheet pan chicken"
    assert normalize_title(None) == ""


def test_clean_title_strips_course_prefix():
    assert clean_title("Dinner: Tacos") == "Tacos"
    assert clean_title("Lunch - Soup") == "Soup"
    assert clean_title("Breakfast — Oatmeal") == "Oatmeal"
    assert clean_title("Dinnertime Stew") == "Dinnertime Stew"  # no separator -> unchanged
    assert clean_title("Tacos") == "Tacos"


def test_infer_slot_keyword():
    assert infer_slot("Breakfast: Eggs") == "breakfast"
    assert infer_slot("Dessert bars") == "snack"


def test_infer_slot_by_time():
    assert infer_slot("Eggs", datetime(2026, 6, 20, 8, 0)) == "breakfast"
    assert infer_slot("Sandwich", datetime(2026, 6, 20, 12, 30)) == "lunch"
    assert infer_slot("Roast", datetime(2026, 6, 20, 19, 0)) == "dinner"


def test_infer_slot_default_for_all_day():
    # midnight datetime is treated as no time -> default
    assert infer_slot("Tacos", datetime(2026, 6, 20, 0, 0)) == "dinner"
    assert infer_slot("Tacos", None, default_slot="lunch") == "lunch"


def test_dedup_key_stable_and_title_insensitive_to_case():
    a = dedup_key("2026-06-20", "dinner", "Tacos ")
    b = dedup_key("2026-06-20", "dinner", "tacos")
    assert a == b
    assert a != dedup_key("2026-06-21", "dinner", "Tacos")


def test_choose_category_id():
    cats = [mc("d", "Dinner"), mc("l", "Lunch")]
    assert choose_category_id("dinner", cats) == "d"
    assert choose_category_id("lunch", cats) == "l"
    assert choose_category_id("breakfast", cats) is None


def test_choose_category_id_substring():
    cats = [mc("x", "Weeknight Dinners")]
    assert choose_category_id("dinner", cats) == "x"
