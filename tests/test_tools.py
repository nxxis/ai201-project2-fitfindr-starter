"""
tests/test_tools.py

Pytest tests for all three FitFindr tools.

Run from your repo root with:
    pytest tests/ -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── helpers ───────────────────────────────────────────────────────────────────

def _sample_item():
    return {
        "id": "L001",
        "title": "Faded Band Tee",
        "category": "tops",
        "style_tags": ["vintage", "grunge", "graphic"],
        "size": "M",
        "condition": "Good",
        "price": 22.0,
        "colors": ["black"],
        "brand": "Unknown",
        "platform": "Depop",
        "description": "Classic faded band tee with natural wear.",
    }


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_list():
    results = search_listings("vintage tee")
    assert isinstance(results, list)


def test_search_happy_path_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0


def test_search_empty_results_for_impossible_query():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    max_p = 25.0
    results = search_listings("tee", size=None, max_price=max_p)
    for item in results:
        assert item["price"] <= max_p


def test_search_size_filter():
    results = search_listings("top shirt", size="M", max_price=None)
    for item in results:
        assert item["size"].upper() == "M"


def test_search_no_size_filter_returns_more():
    results_m   = search_listings("jacket", size="M", max_price=None)
    results_all = search_listings("jacket", size=None, max_price=None)
    assert len(results_all) >= len(results_m)


def test_search_result_dicts_have_required_keys():
    required = {"id", "title", "description", "category", "style_tags",
                "size", "condition", "price", "colors", "brand", "platform"}
    results = search_listings("tee", size=None, max_price=100)
    for item in results:
        assert required.issubset(item.keys())


def test_search_empty_description_does_not_crash():
    results = search_listings("", size=None, max_price=100)
    assert isinstance(results, list)


def test_search_first_result_most_relevant():
    results = search_listings("vintage band tee grunge")
    assert len(results) > 0
    first = results[0]
    searchable = (
        first["title"].lower()
        + " " + " ".join(first.get("style_tags", [])).lower()
        + " " + first.get("description", "").lower()
    )
    assert any(kw in searchable for kw in ["vintage", "band", "tee", "grunge"])


# ── suggest_outfit ────────────────────────────────────────────────────────────

def test_suggest_outfit_empty_item_returns_error_string():
    result = suggest_outfit({}, get_example_wardrobe())
    assert isinstance(result, str)
    assert result.startswith("[Error]"), f"Expected error string, got: {result[:80]}"


def test_suggest_outfit_none_item_does_not_crash():
    result = suggest_outfit(None, get_example_wardrobe())  # type: ignore
    assert isinstance(result, str)


def test_suggest_outfit_empty_wardrobe_does_not_crash():
    result = suggest_outfit(_sample_item(), get_empty_wardrobe())
    assert isinstance(result, str)
    assert len(result) > 0


def test_suggest_outfit_returns_string_type():
    result = suggest_outfit(_sample_item(), get_example_wardrobe())
    assert isinstance(result, str)


# ── create_fit_card ───────────────────────────────────────────────────────────

def test_fit_card_empty_outfit_returns_error():
    result = create_fit_card("", _sample_item())
    assert isinstance(result, str)
    assert result.startswith("[Error]"), f"Expected error string, got: {result[:80]}"


def test_fit_card_whitespace_outfit_returns_error():
    result = create_fit_card("   ", _sample_item())
    assert isinstance(result, str)
    assert result.startswith("[Error]")


def test_fit_card_none_item_returns_error():
    result = create_fit_card("Pair with wide-leg jeans and boots.", None)  # type: ignore
    assert isinstance(result, str)
    assert result.startswith("[Error]")


def test_fit_card_empty_item_returns_error():
    result = create_fit_card("Great outfit with jeans.", {})
    assert isinstance(result, str)
    assert result.startswith("[Error]")


def test_fit_card_always_returns_string():
    result = create_fit_card(
        "Pair this band tee with wide-leg jeans and platform boots.",
        _sample_item(),
    )
    assert isinstance(result, str)
    assert len(result) > 0