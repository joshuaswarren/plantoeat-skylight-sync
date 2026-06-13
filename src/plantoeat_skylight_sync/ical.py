"""Fetch and parse the Plan to Eat iCal meal-plan feed.

Plan to Eat exposes a per-user ICS feed (``/planner/{ID}/recipes/plantoeat-ical``).
Each VEVENT is roughly one planned meal: ``SUMMARY`` is the recipe title, ``DTSTART``
the date (and time, if "custom meal times" is enabled), ``DESCRIPTION`` carries
ingredients/notes depending on the chosen feed variant. The feed is human-readable
text, not a structured recipe export, so this is intentionally lossy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional

import httpx
from icalendar import Calendar

from .errors import SyncError
from .mapping import DEFAULT_SLOT, clean_title, infer_slot

USER_AGENT = "plantoeat-skylight-sync (+https://github.com/joshuaswarren/plantoeat-skylight-sync)"


@dataclass
class MealPlanEntry:
    """One planned meal parsed from the feed."""

    date: str  # YYYY-MM-DD
    slot: str  # breakfast | lunch | dinner | snack
    title: str
    description: Optional[str] = None
    uid: Optional[str] = None
    start: Optional[datetime] = None
    recipe_url: Optional[str] = None  # link to the Plan to Eat recipe, if any


def fetch_feed(url: str, *, http: Optional[httpx.Client] = None, timeout: float = 30.0) -> str:
    """Fetch the raw ICS text. Raises :class:`SyncError` on any failure."""
    owns = http is None
    client = http or httpx.Client(timeout=timeout, follow_redirects=True)
    try:
        try:
            resp = client.get(url, headers={"User-Agent": USER_AGENT})
        except httpx.HTTPError as exc:
            raise SyncError(f"Failed to fetch Plan to Eat feed: {exc}") from exc
        if resp.status_code >= 400:
            raise SyncError(f"Plan to Eat feed returned HTTP {resp.status_code}")
        return resp.text
    finally:
        if owns:
            client.close()


def parse_feed(text: str, *, default_slot: str = DEFAULT_SLOT) -> List[MealPlanEntry]:
    """Parse ICS text into :class:`MealPlanEntry` objects."""
    try:
        cal = Calendar.from_ical(text)
    except Exception as exc:  # icalendar raises ValueError/various on bad input
        raise SyncError(f"Could not parse iCal feed: {exc}") from exc

    entries: List[MealPlanEntry] = []
    for comp in cal.walk("VEVENT"):
        summary = str(comp.get("SUMMARY", "")).strip()
        if not summary:
            continue
        dtstart = comp.get("DTSTART")
        if dtstart is None:
            continue
        value = dtstart.dt
        start: Optional[datetime] = None
        if isinstance(value, datetime):  # check datetime before date (datetime subclasses date)
            start = value
            date_str = value.date().isoformat()
        elif isinstance(value, date):
            date_str = value.isoformat()
        else:
            continue
        raw_desc = comp.get("DESCRIPTION")
        description = str(raw_desc).strip() if raw_desc not in (None, "") else None
        raw_uid = comp.get("UID")
        uid = str(raw_uid) if raw_uid else None
        raw_url = comp.get("URL")
        recipe_url = str(raw_url).strip() if raw_url else None
        # The "All" feed often only carries the recipe link in DESCRIPTION.
        if not recipe_url and description and "/recipes/" in description:
            recipe_url = description.split()[0]
        entries.append(
            MealPlanEntry(
                date=date_str,
                slot=infer_slot(summary, start, default_slot),
                title=clean_title(summary),
                description=description,
                uid=uid,
                start=start,
                recipe_url=recipe_url,
            )
        )
    return entries
