"""Local sync state.

Skylight has no documented external-id field, so we own the mapping locally:
- ``sittings``: dedup-key -> {recipe_id, sitting_id, date, slot, title}
- ``recipes``: normalized-title -> recipe_id  (so recurring dishes reuse one recipe)

This lets every run be an idempotent reconcile and lets opt-in deletion target only
the sittings this tool created.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class SyncState:
    sittings: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    recipes: Dict[str, str] = field(default_factory=dict)
    # normalized title -> recipe id, for recipes whose full content was already fetched
    content: Dict[str, str] = field(default_factory=dict)
    path: Optional[Path] = None

    @classmethod
    def load(cls, path: Optional[Path]) -> "SyncState":
        if path is None:
            return cls()
        p = Path(path)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            return cls(path=p)
        return cls(
            sittings=dict(data.get("sittings") or {}),
            recipes=dict(data.get("recipes") or {}),
            content=dict(data.get("content") or {}),
            path=p,
        )

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {"sittings": self.sittings, "recipes": self.recipes, "content": self.content},
                indent=2,
            ),
            encoding="utf-8",
        )

    def record_recipe(self, normalized_title: str, recipe_id: str) -> None:
        self.recipes[normalized_title] = str(recipe_id)

    def record_content(self, normalized_title: str, recipe_id: str) -> None:
        self.content[normalized_title] = str(recipe_id)

    def record_sitting(self, key: str, **info: Any) -> None:
        self.sittings[key] = info

    def remove_sitting(self, key: str) -> None:
        self.sittings.pop(key, None)
