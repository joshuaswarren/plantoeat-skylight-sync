"""Fetch full recipe content from a public Plan to Eat recipe page.

Plan to Eat recipe pages (``https://app.plantoeat.com/recipes/{id}``) are publicly
readable with the link and embed a schema.org Recipe in JSON-LD (clean ingredient
list) plus a directions block in the HTML. For recipes clipped from another site,
Plan to Eat stores only a "visit source" link for the directions; we capture the
source URL in that case. This lets us put real ingredients (and directions when
present) into the Skylight recipe instead of an unclickable link.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html import unescape as _html_unescape
from typing import List, Optional

import httpx

from .errors import SyncError

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_LDJSON_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_RECIPE_ID_RE = re.compile(r"/recipes/(\d+)")
_DIR_HEADER_RE = re.compile(r"^\W*directions\s*(\(\s*default\s*\|\s*numbered\s*\))?\s*", re.I)
_VISIT_SOURCE_RE = re.compile(r'class="visit-source-url"[^>]*href="([^"]+)"', re.I)


@dataclass
class RecipeContent:
    title: Optional[str] = None
    ingredients: List[str] = field(default_factory=list)
    directions: Optional[str] = None
    source_url: Optional[str] = None
    recipe_url: Optional[str] = None


def recipe_id_from_url(url: Optional[str]) -> Optional[str]:
    match = _RECIPE_ID_RE.search(url or "")
    return match.group(1) if match else None


def _strip_html(fragment: str) -> str:
    return _WS_RE.sub(" ", _html_unescape(_TAG_RE.sub(" ", fragment or ""))).strip()


def _find_recipe_ldjson(html: str) -> Optional[dict]:
    for block in _LDJSON_RE.findall(html):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            if "Recipe" in str(obj.get("@type", "")):
                return obj
            graph = obj.get("@graph")
            if isinstance(graph, list):
                for node in graph:
                    if isinstance(node, dict) and "Recipe" in str(node.get("@type", "")):
                        return node
    return None


def _extract_directions(html: str) -> Optional[str]:
    idx = html.lower().find('class="directions')
    if idx < 0:
        return None
    # The directions block ends where the next edit section begins.
    end = html.find("show-edit-section", idx + 20)
    segment = html[idx : end if end > idx else idx + 5000]
    text = _DIR_HEADER_RE.sub("", _strip_html(segment)).strip()
    return text or None


def parse_recipe_html(html: str, recipe_url: Optional[str] = None) -> RecipeContent:
    ld = _find_recipe_ldjson(html) or {}
    ingredients: List[str] = []
    raw = ld.get("recipeIngredient") or ld.get("ingredients")
    if isinstance(raw, list):
        ingredients = [_html_unescape(str(x).strip()) for x in raw if str(x).strip()]
    elif isinstance(raw, str) and raw.strip():
        ingredients = [_html_unescape(line.strip()) for line in raw.splitlines() if line.strip()]
    source = None
    match = _VISIT_SOURCE_RE.search(html)
    if match:
        source = match.group(1)
    elif isinstance(ld.get("url"), str):
        source = ld["url"]
    title = ld.get("name") if isinstance(ld.get("name"), str) else None
    return RecipeContent(
        title=title,
        ingredients=ingredients,
        directions=_extract_directions(html),
        source_url=source,
        recipe_url=recipe_url,
    )


def fetch_recipe_content(
    recipe_url: str, *, http: Optional[httpx.Client] = None, timeout: float = 30.0
) -> RecipeContent:
    owns = http is None
    client = http or httpx.Client(timeout=timeout, follow_redirects=True)
    try:
        try:
            resp = client.get(recipe_url, headers={"User-Agent": USER_AGENT})
        except httpx.HTTPError as exc:
            raise SyncError(f"Failed to fetch recipe {recipe_url}: {exc}") from exc
        if resp.status_code >= 400:
            raise SyncError(f"Recipe {recipe_url} returned HTTP {resp.status_code}")
        content = parse_recipe_html(resp.text, recipe_url)
        # Recipes "clipped" into Plan to Eat from another site store only a
        # "visit source" link for the directions. Follow that source one hop and
        # pull the steps from its schema.org JSON-LD so every recipe has directions.
        if (
            _is_placeholder_directions(content.directions)
            and content.source_url
            and "plantoeat.com" not in content.source_url
        ):
            sourced = fetch_source_directions(content.source_url, http=client)
            if sourced:
                content.directions = sourced
        return content
    finally:
        if owns:
            client.close()


def _collect_steps(value: object) -> List[str]:
    out: List[str] = []
    if isinstance(value, str):
        text = _strip_html(value).strip()
        if text:
            out.append(text)
    elif isinstance(value, list):
        for item in value:
            out.extend(_collect_steps(item))
    elif isinstance(value, dict):
        if "HowToSection" in str(value.get("@type", "")):
            out.extend(_collect_steps(value.get("itemListElement") or []))
        else:
            raw = value.get("text") or value.get("name")
            if raw:
                stripped = _strip_html(str(raw)).strip()
                if stripped:
                    out.append(stripped)
    return out


def _render_instructions(value: object) -> Optional[str]:
    steps = _collect_steps(value)
    if not steps:
        return None
    return "\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1))


def fetch_source_directions(source_url: str, *, http: httpx.Client) -> Optional[str]:
    """Best-effort: pull directions from the original source site's recipe JSON-LD.

    Returns ``None`` (never raises) if the source can't be fetched or has no
    machine-readable instructions, so a flaky external site never fails a sync.
    """
    try:
        resp = http.get(source_url, headers={"User-Agent": USER_AGENT})
    except httpx.HTTPError:
        return None
    if resp.status_code >= 400:
        return None
    node = _find_recipe_ldjson(resp.text)
    if not node:
        return None
    return _render_instructions(node.get("recipeInstructions"))


def _is_placeholder_directions(directions: Optional[str]) -> bool:
    if not directions:
        return True
    low = directions.lower()
    return "view the directions" in low or "view directions" in low


def format_description(content: RecipeContent, max_len: int = 4000) -> str:
    """Render recipe content as plain text suitable for a Skylight recipe."""
    parts: List[str] = []
    if content.ingredients:
        parts.append("Ingredients:\n" + "\n".join("- " + i for i in content.ingredients))
    if content.directions and not _is_placeholder_directions(content.directions):
        parts.append("Directions:\n" + content.directions)
    if content.source_url:
        parts.append("Source: " + content.source_url)
    elif content.recipe_url:
        parts.append("Recipe: " + content.recipe_url)
    text = "\n\n".join(parts).strip()
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


def has_real_content(description: Optional[str]) -> bool:
    """True if a Skylight recipe description already carries fetched content."""
    return "ingredients:" in (description or "").lower()
