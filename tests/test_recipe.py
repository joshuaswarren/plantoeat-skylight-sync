"""Tests for Plan to Eat recipe-content fetching/parsing."""

from __future__ import annotations

import httpx
import pytest
import respx
from httpx import Response

from plantoeat_skylight_sync.errors import SyncError
from plantoeat_skylight_sync.recipe import (
    RecipeContent,
    fetch_recipe_content,
    format_description,
    has_real_content,
    parse_recipe_html,
    recipe_id_from_url,
)

NATIVE_HTML = """
<html><head>
<script type="application/ld+json">
{"@type":"Recipe","name":"Tacos","recipeIngredient":["1 lb beef","2 tortillas"]}
</script></head><body>
<div class="show-edit-section show directions" data-recipe-id="1">
  <div class="directions simple-menu"><h4>Directions</h4><p>Cook beef. Assemble tacos.</p></div>
</div>
<div class="show-edit-section show prep_notes">notes</div>
</body></html>
"""

CLIPPED_HTML = """
<html><head>
<script type="application/ld+json">
{"@type":"Recipe","name":"Lasagna","recipeIngredient":["noodles","cheese"]}
</script></head><body>
<div class="directions simple-menu"><h4>Directions</h4><p>Visit
<a class="visit-source-url" href="http://example.com/lasagna">example.com</a>
to view the directions for this recipe.</p></div>
<div class="show-edit-section show prep_notes">notes</div>
</body></html>
"""


def test_recipe_id_from_url():
    assert recipe_id_from_url("https://app.plantoeat.com/recipes/5025724") == "5025724"
    assert recipe_id_from_url("nope") is None


def test_parse_native_recipe():
    c = parse_recipe_html(NATIVE_HTML, "https://app.plantoeat.com/recipes/1")
    assert c.title == "Tacos"
    assert c.ingredients == ["1 lb beef", "2 tortillas"]
    assert "Cook beef" in (c.directions or "")
    assert not (c.directions or "").lower().startswith("directions")
    assert c.recipe_url.endswith("/recipes/1")


def test_parse_clipped_recipe_captures_source():
    c = parse_recipe_html(CLIPPED_HTML)
    assert c.ingredients == ["noodles", "cheese"]
    assert c.source_url == "http://example.com/lasagna"


def test_format_description_native():
    c = RecipeContent(ingredients=["1 lb beef"], directions="Cook.", source_url="http://s")
    text = format_description(c)
    assert "Ingredients:" in text and "- 1 lb beef" in text
    assert "Directions:" in text and "Cook." in text
    assert "Source: http://s" in text


def test_format_description_drops_placeholder_directions():
    c = parse_recipe_html(CLIPPED_HTML)
    text = format_description(c)
    assert "Ingredients:" in text
    assert "Directions:" not in text  # placeholder "visit source" excluded
    assert "Source: http://example.com/lasagna" in text


def test_format_description_truncates():
    c = RecipeContent(ingredients=["x" * 100 for _ in range(100)])
    assert len(format_description(c, max_len=200)) <= 200


def test_has_real_content():
    assert has_real_content("Ingredients:\n- x") is True
    assert has_real_content("https://app.plantoeat.com/recipes/1") is False
    assert has_real_content(None) is False


@respx.mock
def test_fetch_recipe_content_ok():
    url = "https://app.plantoeat.com/recipes/1"
    respx.get(url).mock(return_value=Response(200, html=NATIVE_HTML))
    c = fetch_recipe_content(url)
    assert c.ingredients == ["1 lb beef", "2 tortillas"]


@respx.mock
def test_fetch_recipe_content_http_error():
    url = "https://app.plantoeat.com/recipes/1"
    respx.get(url).mock(return_value=Response(404))
    with pytest.raises(SyncError):
        fetch_recipe_content(url)


@respx.mock
def test_fetch_recipe_content_network_error():
    url = "https://app.plantoeat.com/recipes/1"
    respx.get(url).mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(SyncError):
        fetch_recipe_content(url)
