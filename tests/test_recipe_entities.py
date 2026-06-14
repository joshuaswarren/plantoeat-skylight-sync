"""HTML entities in recipe text are decoded."""

from __future__ import annotations

from plantoeat_skylight_sync.recipe import _render_instructions, parse_recipe_html


def test_instruction_entities_decoded():
    steps = [{"@type": "HowToStep", "text": "Don&#39;t overdo &amp; enjoy"}]
    assert _render_instructions(steps) == "1. Don't overdo & enjoy"


def test_ingredient_text_is_clean():
    html = (
        '<script type="application/ld+json">'
        '{"@type":"Recipe","recipeIngredient":["2 cups flour &amp; sugar"]}</script>'
    )
    assert parse_recipe_html(html).ingredients == ["2 cups flour & sugar"]
