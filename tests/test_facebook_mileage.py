"""Tests for Facebook Marketplace listing-detail mileage extraction.

Search-results cards never include mileage at all, so it's scraped from
each listing's own detail page text, which can present it in several
different formats depending on how the seller filled out the listing.
"""
from __future__ import annotations

from carfinder.scrapers.facebook import MILEAGE_PATTERNS


def _extract(body_text: str):
    for pattern, multiplier in MILEAGE_PATTERNS:
        match = pattern.search(body_text)
        if match:
            return int(float(match.group(1).replace(",", "")) * multiplier)
    return None


def test_extracts_from_structured_driven_field():
    text = "About this vehicle\nDriven 135,000 miles\nAutomatic transmission"
    assert _extract(text) == 135000


def test_extracts_from_description_mileage_label():
    text = "Seller's description\n? Mileage: 133,690 miles\n? Clean Title"
    assert _extract(text) == 133690


def test_prefers_driven_field_over_description_mileage_label():
    text = "Driven 135,000 miles\n...\nMileage: 133,690 miles"
    assert _extract(text) == 135000


def test_falls_back_to_generic_miles_mention_in_free_text():
    text = "Selling my 2007 Honda Pilot EX-L with 183,596 miles. Clean title."
    assert _extract(text) == 183596


def test_generic_pattern_ignores_search_radius_text():
    text = "Location\nHayward, California\n? Within 40 mi\n2014 Honda Pilot\n$5,000"
    assert _extract(text) is None


def test_extracts_spanish_colloquial_mil_millas():
    text = "Vendo Honda pilot 2006 titulo limpio. 132mil millas ha tenido dos duenos."
    assert _extract(text) == 132000


def test_extracts_spanish_millas_with_commas():
    text = "Se vende con 132,000 millas, titulo limpio."
    assert _extract(text) == 132000


def test_returns_none_when_no_mileage_mentioned_anywhere():
    text = "2014 Honda Pilot EX\n$5,000\nGreat condition, no issues."
    assert _extract(text) is None
