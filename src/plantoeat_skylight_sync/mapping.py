"""Pure helpers for mapping Plan to Eat entries onto Skylight Meals.

These are deliberately side-effect-free so they can be unit-tested in isolation:
- inferring a meal slot (breakfast/lunch/dinner/snack) from an event,
- normalizing recipe titles for de-duplication,
- a deterministic de-dup key for a planned meal,
- choosing a Skylight meal-category id for a slot.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Iterable, Optional

#: Slot used when nothing else can be inferred (Plan to Eat all-day events carry no
#: time-of-day, and the summary often has no course keyword).
DEFAULT_SLOT = "dinner"

#: Checked in this order so a keyword match is deterministic.
SLOT_ORDER = ("breakfast", "lunch", "dinner", "snack")
SLOT_KEYWORDS = {
    "breakfast": ("breakfast", "brunch"),
    "lunch": ("lunch",),
    "dinner": ("dinner", "supper"),
    "snack": ("snack", "dessert", "treat"),
}
_COURSE_PREFIXES = ("breakfast", "brunch", "lunch", "dinner", "supper", "snack", "dessert")
_SEPARATORS = (":", "-", "—")


def normalize_title(title: Optional[str]) -> str:
    """Lower-case, trim, and collapse whitespace for stable comparison/de-dup."""
    return " ".join((title or "").strip().lower().split())


def clean_title(title: Optional[str]) -> str:
    """Strip a leading course prefix like ``"Dinner: "`` or ``"Lunch - "``."""
    text = (title or "").strip()
    low = text.lower()
    for prefix in _COURSE_PREFIXES:
        if low.startswith(prefix):
            rest = text[len(prefix) :].lstrip()
            if rest[:1] in _SEPARATORS:
                return rest[1:].strip()
    return text


def infer_slot(
    title: Optional[str],
    start: Optional[datetime] = None,
    default_slot: str = DEFAULT_SLOT,
) -> str:
    """Infer a meal slot from a course keyword, else the event time, else the default."""
    low = (title or "").lower()
    for slot in SLOT_ORDER:
        if any(kw in low for kw in SLOT_KEYWORDS[slot]):
            return slot
    if start is not None and (start.hour or start.minute):
        hour = start.hour
        if hour < 11:
            return "breakfast"
        if hour < 16:
            return "lunch"
        return "dinner"
    return default_slot


def dedup_key(date: str, slot: str, title: str) -> str:
    """A short, stable key for one planned meal (date + slot + normalized title)."""
    raw = f"{date}|{slot}|{normalize_title(title)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def choose_category_id(slot: str, categories: Iterable[Any]) -> Optional[str]:
    """Find the Skylight meal-category id whose label best matches ``slot``.

    Tries an exact (case-insensitive) label match first, then a substring match.
    ``categories`` items must expose ``.label`` and ``.id`` (pyskylight MealCategory).
    """
    slot_l = slot.strip().lower()
    items = list(categories)
    for cat in items:
        if (getattr(cat, "label", None) or "").strip().lower() == slot_l:
            return cat.id
    for cat in items:
        if slot_l and slot_l in (getattr(cat, "label", None) or "").strip().lower():
            return cat.id
    return None
