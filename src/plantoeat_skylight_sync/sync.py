"""The reconciler: make Skylight's meal plan match the Plan to Eat feed.

One-way, Plan to Eat -> Skylight. Every run is an idempotent diff: compute the
desired set of planned meals from the feed, compare against existing Skylight recipes
+ sittings (and our local state), then create what's missing. Re-running with no feed
changes performs zero writes. Deletion of orphaned meals is opt-in and only touches
sittings this tool created.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .ical import MealPlanEntry
from .mapping import choose_category_id, dedup_key, normalize_title
from .state import SyncState

CREATE_RECIPE = "create_recipe"
CREATE_SITTING = "create_sitting"
DELETE_SITTING = "delete_sitting"
SKIP = "skip"


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
    ) -> SyncReport:
        actions: List[SyncAction] = []
        in_window = [e for e in entries if window_start <= e.date <= window_end]

        categories = self.client.list_meal_categories(self.frame_id)
        existing_recipes: Dict[str, str] = {
            normalize_title(r.summary): r.id
            for r in self.client.list_recipes(self.frame_id)
            if r.summary
        }
        existing_sitting_ids = {
            s.id for s in self.client.list_sittings(self.frame_id, window_start, window_end)
        }
        desired_keys: set[str] = set()

        for entry in in_window:
            category_id = choose_category_id(entry.slot, categories)
            if category_id is None:
                actions.append(
                    SyncAction(
                        SKIP, entry.date, entry.slot, entry.title, "no matching meal category"
                    )
                )
                continue
            key = dedup_key(entry.date, entry.slot, entry.title)
            desired_keys.add(key)
            norm = normalize_title(entry.title)

            recipe_id: Optional[str] = self.state.recipes.get(norm) or existing_recipes.get(norm)
            if recipe_id is None:
                actions.append(SyncAction(CREATE_RECIPE, entry.date, entry.slot, entry.title))
                if not dry_run:
                    recipe = self.client.create_recipe(
                        self.frame_id,
                        entry.title,
                        description=entry.description,
                        meal_category_id=category_id,
                    )
                    recipe_id = recipe.id
                    self.state.record_recipe(norm, recipe_id)
                    existing_recipes[norm] = recipe_id

            recorded = self.state.sittings.get(key)
            already_planned = (
                recorded is not None and recorded.get("sitting_id") in existing_sitting_ids
            )
            if already_planned:
                actions.append(
                    SyncAction(SKIP, entry.date, entry.slot, entry.title, "already planned")
                )
                continue

            actions.append(SyncAction(CREATE_SITTING, entry.date, entry.slot, entry.title))
            if not dry_run:
                sitting = self.client.create_sitting(
                    self.frame_id, entry.date, category_id, meal_recipe_id=recipe_id
                )
                self.state.record_sitting(
                    key,
                    recipe_id=recipe_id,
                    sitting_id=sitting.id,
                    date=entry.date,
                    slot=entry.slot,
                    title=entry.title,
                )

        if allow_delete:
            actions.extend(self._reconcile_deletes(window_start, window_end, desired_keys, dry_run))

        if not dry_run:
            self.state.save()
        return SyncReport(actions=actions, dry_run=dry_run)

    def _reconcile_deletes(
        self, window_start: str, window_end: str, desired_keys: set[str], dry_run: bool
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
                    self.client.delete_sitting(self.frame_id, sitting_id)
                self.state.remove_sitting(key)
        return actions
