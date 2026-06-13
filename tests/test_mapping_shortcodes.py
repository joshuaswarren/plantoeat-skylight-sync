"""Tests for single-letter course-code handling (B:/L:/D:/S:)."""

from __future__ import annotations

from plantoeat_skylight_sync.mapping import clean_title, infer_slot


def test_clean_title_strips_short_codes():
    assert clean_title("B: eggs") == "eggs"
    assert clean_title("L: ranch chicken") == "ranch chicken"
    assert clean_title("D: Turkey Lasagna") == "Turkey Lasagna"
    assert clean_title("S: cookies") == "cookies"


def test_clean_title_leaves_real_titles():
    assert clean_title("S'mores") == "S'mores"  # apostrophe, not a course code
    assert clean_title("Bacon") == "Bacon"


def test_infer_slot_from_short_code():
    assert infer_slot("B: eggs") == "breakfast"
    assert infer_slot("L: soup") == "lunch"
    assert infer_slot("D: tacos") == "dinner"
    assert infer_slot("S: cookies") == "snack"


def test_keyword_still_wins_over_short_code():
    # "Dinner" keyword present -> dinner regardless of leading letter
    assert infer_slot("Dinner leftovers") == "dinner"
