"""Edge-case coverage for recipe parsing."""

from __future__ import annotations

from plantoeat_skylight_sync.recipe import RecipeContent, format_description, parse_recipe_html


def test_ldjson_graph_form():
    html = (
        '<script type="application/ld+json">'
        '{"@graph":[{"@type":"WebPage"},{"@type":"Recipe","name":"Stew",'
        '"recipeIngredient":["beef","carrot"]}]}</script>'
    )
    c = parse_recipe_html(html)
    assert c.title == "Stew"
    assert c.ingredients == ["beef", "carrot"]


def test_ldjson_string_ingredients():
    html = (
        '<script type="application/ld+json">'
        '{"@type":"Recipe","recipeIngredient":"line one\\nline two"}</script>'
    )
    assert parse_recipe_html(html).ingredients == ["line one", "line two"]


def test_invalid_ldjson_is_skipped():
    html = '<script type="application/ld+json">{ not valid json }</script><body>x</body>'
    c = parse_recipe_html(html)
    assert c.ingredients == []
    assert c.directions is None


def test_no_ldjson_no_directions():
    c = parse_recipe_html("<html><body>nothing here</body></html>", "https://x/recipes/9")
    assert c.ingredients == []
    assert c.directions is None
    # falls back to the recipe link
    assert format_description(c) == "Recipe: https://x/recipes/9"


def test_format_description_empty():
    assert format_description(RecipeContent()) == ""
