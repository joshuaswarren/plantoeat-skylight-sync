"""Tests for following a clipped recipe's source site to get full directions."""

from __future__ import annotations

import httpx
import respx
from httpx import Response

from plantoeat_skylight_sync.recipe import (
    _render_instructions,
    fetch_recipe_content,
    fetch_source_directions,
)

SRC = "https://example.com/lasagna"

PTE_CLIPPED = (
    '<script type="application/ld+json">'
    '{"@type":"Recipe","name":"Lasagna","recipeIngredient":["noodles","cheese"]}</script>'
    '<div class="directions simple-menu"><h4>Directions</h4><p>Visit '
    f'<a class="visit-source-url" href="{SRC}">example.com</a> to view the directions.</p></div>'
    '<div class="show-edit-section show prep_notes">x</div>'
)


def _src_with(instructions_json: str) -> str:
    return (
        '<script type="application/ld+json">'
        '{"@type":"Recipe","recipeInstructions":' + instructions_json + "}</script>"
    )


def test_render_instructions_forms():
    assert _render_instructions("Just do it.") == "1. Just do it."
    assert _render_instructions(["Step A", "Step B"]) == "1. Step A\n2. Step B"
    howto = [{"@type": "HowToStep", "text": "Mix"}, {"@type": "HowToStep", "text": "Bake"}]
    assert _render_instructions(howto) == "1. Mix\n2. Bake"
    section = [{"@type": "HowToSection", "itemListElement": [{"@type": "HowToStep", "text": "A"}]}]
    assert _render_instructions(section) == "1. A"
    assert _render_instructions([]) is None


@respx.mock
def test_fetch_source_directions_ok():
    respx.get(SRC).mock(
        return_value=Response(200, html=_src_with('[{"@type":"HowToStep","text":"Cook it."}]'))
    )
    with httpx.Client() as c:
        assert fetch_source_directions(SRC, http=c) == "1. Cook it."


@respx.mock
def test_fetch_source_directions_http_and_network_and_no_ld():
    respx.get("https://a.test/x").mock(return_value=Response(404))
    respx.get("https://b.test/x").mock(side_effect=httpx.ConnectError("down"))
    respx.get("https://c.test/x").mock(return_value=Response(200, html="<html>no ld</html>"))
    with httpx.Client() as c:
        assert fetch_source_directions("https://a.test/x", http=c) is None
        assert fetch_source_directions("https://b.test/x", http=c) is None
        assert fetch_source_directions("https://c.test/x", http=c) is None


@respx.mock
def test_fetch_recipe_content_follows_source_for_directions():
    pte = "https://app.plantoeat.com/recipes/1"
    respx.get(pte).mock(return_value=Response(200, html=PTE_CLIPPED))
    respx.get(SRC).mock(
        return_value=Response(200, html=_src_with('["Boil noodles","Layer and bake"]'))
    )
    content = fetch_recipe_content(pte)
    assert content.ingredients == ["noodles", "cheese"]
    assert content.directions == "1. Boil noodles\n2. Layer and bake"
    assert content.source_url == SRC
