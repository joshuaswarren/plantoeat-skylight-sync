"""Test helpers: a fake Skylight client and model factories."""

from __future__ import annotations

from typing import Any, List, Optional

from pyskylight.models import MealCategory, Recipe, Sitting


def mc(cid: str, label: str) -> MealCategory:
    return MealCategory.from_jsonapi({"id": cid, "attributes": {"label": label}})


def rcp(rid: str, summary: str) -> Recipe:
    return Recipe.from_jsonapi({"id": rid, "attributes": {"summary": summary}})


def sit(sid: str, date: str, meal_category_id=None, meal_recipe_id=None) -> Sitting:
    rels = {}
    if meal_category_id is not None:
        rels["meal_category"] = {"data": {"id": str(meal_category_id)}}
    if meal_recipe_id is not None:
        rels["meal_recipe"] = {"data": {"id": str(meal_recipe_id)}}
    return Sitting.from_jsonapi(
        {"id": sid, "attributes": {"instances": [date]}, "relationships": rels}
    )


class FakeClient:
    """Mimics the subset of pyskylight.SkylightClient the Syncer uses."""

    def __init__(
        self,
        categories: Optional[List[MealCategory]] = None,
        recipes: Optional[List[Recipe]] = None,
        sittings: Optional[List[Sitting]] = None,
    ) -> None:
        self._categories = (
            categories
            if categories is not None
            else [
                mc("d", "Dinner"),
                mc("l", "Lunch"),
                mc("b", "Breakfast"),
            ]
        )
        self._recipes = list(recipes or [])
        self._sittings = list(sittings or [])
        self.created_recipes: list = []
        self.updated_recipes: list = []
        self.created_sittings: list = []
        self.deleted: list = []
        self._rid = 100
        self._sid = 200

    def list_meal_categories(self, frame_id: Any) -> List[MealCategory]:
        return self._categories

    def list_recipes(self, frame_id: Any) -> List[Recipe]:
        return self._recipes

    def list_sittings(
        self, frame_id: Any, date_min: Any = None, date_max: Any = None
    ) -> List[Sitting]:
        return self._sittings

    def create_recipe(self, frame_id, summary, description=None, meal_category_id=None):
        self._rid += 1
        recipe = Recipe.from_jsonapi(
            {"id": str(self._rid), "attributes": {"summary": summary, "description": description}}
        )
        self._recipes.append(recipe)
        self.created_recipes.append((summary, meal_category_id, description))
        return recipe

    def update_recipe(self, frame_id, recipe_id, **fields):
        self.updated_recipes.append((str(recipe_id), fields))
        return Recipe.from_jsonapi(
            {
                "id": str(recipe_id),
                "attributes": {"summary": "x", "description": fields.get("description")},
            }
        )

    def create_sitting(self, frame_id, date, meal_category_id, meal_recipe_id=None):
        self._sid += 1
        sitting = sit(str(self._sid), date, meal_category_id, meal_recipe_id)
        self._sittings.append(sitting)
        self.created_sittings.append((date, meal_category_id, meal_recipe_id))
        return sitting

    def delete_sitting(self, frame_id, sitting_id, date=None):
        self.deleted.append(sitting_id)
