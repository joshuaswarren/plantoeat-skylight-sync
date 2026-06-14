"""The reconciler: make Skylight's meal plan match the Plan to Eat feed.

One-way, Plan to Eat -> Skylight. Every run is an idempotent diff: compute the
desired set of planned meals from the feed, compare against the recipes + sittings
that already exist on Skylight, then create only what's missing. Re-running with no
feed changes performs zero writes. Deletion of orphaned meals is opt-in and only
touches sittings this tool created (tracked in local state).

When a feed entry links to a Plan to Eat recipe, the recipe's real content
(ingredients, and directions when present, plus a source link) is fetched and stored
in the Skylight recipe, instead of an unclickable link. Recipes that already carry
that content are left untouched.

De-dup of planned meals is content-based — a meal is "already planned" if a sitting
already exists for the same (date, meal category, recipe). Skylight's
``meals/sittings`` GET treats ``date_max`` as exclusive, so the existing-sittings
read uses an inclusive end to avoid recreating the last day's meals every run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from datetime import timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

from .errors import SyncError
from .ical import MealPlanEntry
from .mapping import choose_category_id, dedup_key, normalize_title
from .recipe import fetch_recipe_content, format_description
from .state import SyncState

CREATE_RECIPE = "create_recipe"
UPDATE_RECIPE = "update_recipe"
CREATE_SITTING = "create_sitting"
DELETE_SITTING = "delete_sitting"
SKIP = "skip"

Triple = Tuple[str, Optional[str], Optional[str]]  # (date, meal_category_id, meal_recipe_id)


def _inclusive_end(window_end: str) -> str:
    """Skylight's sittings GET excludes ``date_max``; add a day to make it inclusive."""
    try:
        return (_date.fromisoformat(window_end) + timedelta(days=1)).isoformat()
    except ValueError:
        return window_end


def _as_str(value: object) -> Optional[str]:
    return str(value) if value is not None else None


@dataclass
class SyncAction:
    kind: str
    date: str
    slot: str
    title: str
    detail: str = ""


@dataclass
class SyncReport:
    actions: List[SyncAction]
    dry_run: bool

    def _count(self, kind: str) -> int:
        return sum(1 for a in self.actions if a.kind == kind)

    def summary(self) -> Dict[str, int]:
        return {
            "created_recipes": self._count(CREATE_RECIPE),
            "updated_recipes": self._count(UPDATE_RECIPE),
            "created_sittings": self._count(CREATE_SITTING),
            "deleted_sittings": self._count(DELETE_SITTING),
            "skipped": self._count(SKIP),
            "total": len(self.actions),
        }


class Syncer:
    """Reconciles a list of feed entries into Skylight Meals."""

    def __init__(self, client: Any, frame_id: str, state: SyncState) -> None:
        self.client = client
        self.frame_id = frame_id
        self.state = state

    def reconcile(
        self,
        entries: List[MealPlanEntry],
        *,
        window_start: str,
        window_end: str,
        dry_run: bool = True,
        allow_delete: bool = False,
        fetch_content: bool = True,
    ) -> SyncReport:
        actions: List[SyncAction] = []
        in_window = [e for e in entries if window_start <= e.date <= window_end]

        categories = self.client.list_meal_categories(self.frame_id)
        existing_recipes: Dict[str, Any] = {
            normalize_title(r.summary): r
            for r in self.client.list_recipes(self.frame_id)
            if r.summary
        }
        existing: Dict[Triple, str] = {}
        for sitting in self.client.list_sittings(
            self.frame_id, window_start, _inclusive_end(window_end)
        ):
            for day in sitting.dates:
                existing.setdefault(
                    (day, _as_str(sitting.meal_category_id), _as_str(sitting.meal_recipe_id)),
                    sitting.id,
                )

        desired_keys: Set[str] = set()
        recipe_http = httpx.Client(timeout=30.0, follow_redirects=True) if fetch_content else None
        try:
            for entry in in_window:
                category_id = choose_category_id(entry.slot, categories)
                if category_id is None:
                    actions.append(
                        SyncAction(
                            SKIP, entry.date, entry.slot, entry.title, "no matching meal category"
                        )
                    )
                    continue
                desired_keys.add(dedup_key(entry.date, entry.slot, entry.title))
                recipe_id = self._ensure_recipe(
                    entry, category_id, existing_recipes, recipe_http, dry_run, actions
                )

                triple: Triple = (entry.date, _as_str(category_id), _as_str(recipe_id))
                if recipe_id is not None and triple in existing:
                    if not dry_run:
                        self.state.record_sitting(
                            dedup_key(entry.date, entry.slot, entry.title),
                            recipe_id=recipe_id,
                            sitting_id=existing[triple],
                            date=entry.date,
                            slot=entry.slot,
                            title=entry.title,
                        )
                    actions.append(
                        SyncAction(SKIP, entry.date, entry.slot, entry.title, "already planned")
                    )
                    continue

                actions.append(SyncAction(CREATE_SITTING, entry.date, entry.slot, entry.title))
                if not dry_run:
                    sitting = self.client.create_sitting(
                        self.frame_id, entry.date, category_id, meal_recipe_id=recipe_id
                    )
                    existing[triple] = sitting.id
                    self.state.record_sitting(
                        dedup_key(entry.date, entry.slot, entry.title),
                        recipe_id=recipe_id,
                        sitting_id=sitting.id,
                        date=entry.date,
                        slot=entry.slot,
                        title=entry.title,
                    )

            if allow_delete:
                actions.extend(
                    self._reconcile_deletes(window_start, window_end, desired_keys, dry_run)
                )
        finally:
            if recipe_http is not None:
                recipe_http.close()

        if not dry_run:
            self.state.save()
        return SyncReport(actions=actions, dry_run=dry_run)

    def _ensure_recipe(
        self,
        entry: MealPlanEntry,
        category_id: str,
        existing_recipes: Dict[str, Any],
        recipe_http: Optional[httpx.Client],
        dry_run: bool,
        actions: List[SyncAction],
    ) -> Optional[str]:
        """Ensure a recipe exists for ``entry`` (creating or enriching it). Returns its id."""
        norm = normalize_title(entry.title)
        existing_recipe = existing_recipes.get(norm)
        recipe_id: Optional[str] = self.state.recipes.get(norm) or (
            existing_recipe.id if existing_recipe else None
        )

        # Fetch full content once per recipe (tracked in state), then leave it alone.
        new_desc = ""
        if recipe_http is not None and entry.recipe_url and norm not in self.state.content:
            try:
                new_desc = format_description(
                    fetch_recipe_content(entry.recipe_url, http=recipe_http)
                )
            except SyncError:
                new_desc = ""

        if recipe_id is None:
            actions.append(SyncAction(CREATE_RECIPE, entry.date, entry.slot, entry.title))
            if not dry_run:
                recipe = self.client.create_recipe(
                    self.frame_id,
                    entry.title,
                    description=(new_desc or entry.description),
                    meal_category_id=category_id,
                )
                recipe_id = recipe.id
                self.state.record_recipe(norm, recipe_id)
                existing_recipes[norm] = recipe
                if new_desc:
                    self.state.record_content(norm, recipe_id)
        elif new_desc and recipe_id is not None:
            actions.append(SyncAction(UPDATE_RECIPE, entry.date, entry.slot, entry.title))
            if not dry_run:
                existing_recipes[norm] = self.client.update_recipe(
                    self.frame_id, recipe_id, description=new_desc
                )
                self.state.record_content(norm, recipe_id)
        return recipe_id

    def _reconcile_deletes(
        self, window_start: str, window_end: str, desired_keys: Set[str], dry_run: bool
    ) -> List[SyncAction]:
        actions: List[SyncAction] = []
        for key, rec in list(self.state.sittings.items()):
            rec_date = rec.get("date")
            if not rec_date or not (window_start <= rec_date <= window_end):
                continue
            if key in desired_keys:
                continue
            actions.append(
                SyncAction(
                    DELETE_SITTING,
                    rec_date,
                    rec.get("slot", ""),
                    rec.get("title", ""),
                    "no longer in feed",
                )
            )
            if not dry_run:
                sitting_id = rec.get("sitting_id")
                if sitting_id is not None:
                    self.client.delete_sitting(self.frame_id, sitting_id, rec_date)
                self.state.remove_sitting(key)
        return actions
