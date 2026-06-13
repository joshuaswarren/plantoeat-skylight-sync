"""Tests for fetching and parsing the Plan to Eat iCal feed."""

from __future__ import annotations

import httpx
import pytest
import respx
from httpx import Response

from plantoeat_skylight_sync.errors import SyncError
from plantoeat_skylight_sync.ical import fetch_feed, parse_feed

SAMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Plan to Eat//EN
BEGIN:VEVENT
UID:evt-1@plantoeat.com
SUMMARY:Sheet Pan Chicken
DTSTART;VALUE=DATE:20260620
DESCRIPTION:2 lbs chicken thighs\\n1 lemon
END:VEVENT
BEGIN:VEVENT
UID:evt-2@plantoeat.com
SUMMARY:Breakfast: Oatmeal
DTSTART:20260621T080000Z
END:VEVENT
BEGIN:VEVENT
SUMMARY:
DTSTART;VALUE=DATE:20260622
END:VEVENT
END:VCALENDAR
"""


def test_parse_feed_basic():
    entries = parse_feed(SAMPLE_ICS)
    assert len(entries) == 2  # the empty-summary event is skipped
    first = entries[0]
    assert first.date == "2026-06-20"
    assert first.title == "Sheet Pan Chicken"
    assert first.slot == "dinner"  # all-day, no keyword -> default
    assert "chicken" in (first.description or "").lower()
    assert first.uid == "evt-1@plantoeat.com"
    second = entries[1]
    assert second.date == "2026-06-21"
    assert second.slot == "breakfast"  # keyword wins
    assert second.title == "Oatmeal"  # prefix stripped


def test_parse_feed_default_slot_override():
    ics = (
        "BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nSUMMARY:Soup\n"
        "DTSTART;VALUE=DATE:20260620\nEND:VEVENT\nEND:VCALENDAR\n"
    )
    assert parse_feed(ics, default_slot="lunch")[0].slot == "lunch"


def test_parse_feed_invalid():
    with pytest.raises(SyncError):
        parse_feed("not a calendar at all")


@respx.mock
def test_fetch_feed_ok():
    url = "https://www.plantoeat.com/planner/XYZ/recipes/plantoeat-ical"
    respx.get(url).mock(return_value=Response(200, text=SAMPLE_ICS))
    assert "VCALENDAR" in fetch_feed(url)


@respx.mock
def test_fetch_feed_http_error():
    url = "https://www.plantoeat.com/planner/XYZ/recipes/plantoeat-ical"
    respx.get(url).mock(return_value=Response(404))
    with pytest.raises(SyncError):
        fetch_feed(url)


@respx.mock
def test_fetch_feed_network_error():
    url = "https://www.plantoeat.com/planner/XYZ/recipes/plantoeat-ical"
    respx.get(url).mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(SyncError):
        fetch_feed(url)
