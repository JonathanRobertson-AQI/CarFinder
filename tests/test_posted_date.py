"""Tests for the shared posted/listed-date parsing helper used by the
Craigslist and Facebook scrapers.

Each source presents "date listed" differently:
  - Facebook detail pages: spelled-out relative time, e.g. "a day ago",
    "2 weeks ago".
  - Craigslist search cards: abbreviated relative time for recent postings
    ("4h ago", "2d ago") and a bare short date once postings are old enough
    to scroll off relative time ("8/14", "8/14/24").
Cars.com's structured JSON has no posted-date field at all, so it isn't
covered here.
"""
from __future__ import annotations

from datetime import date, timedelta

from carfinder.scrapers.base import parse_posted_date


def test_parses_facebook_style_a_day_ago():
    assert parse_posted_date("a day ago") == (date.today() - timedelta(days=1)).isoformat()


def test_parses_facebook_style_plural_weeks_ago():
    assert parse_posted_date("2 weeks ago") == (date.today() - timedelta(days=14)).isoformat()


def test_parses_facebook_style_an_hour_ago_as_today():
    assert parse_posted_date("an hour ago") == date.today().isoformat()


def test_parses_craigslist_abbreviated_hours_ago():
    assert parse_posted_date("4h ago") == date.today().isoformat()


def test_parses_craigslist_abbreviated_days_ago():
    assert parse_posted_date("2d ago") == (date.today() - timedelta(days=2)).isoformat()


def test_parses_craigslist_short_date_without_year_as_most_recent_past_occurrence():
    yesterday = date.today() - timedelta(days=1)
    result = parse_posted_date(f"{yesterday.month}/{yesterday.day}")
    assert result == yesterday.isoformat()


def test_parses_craigslist_short_date_with_explicit_year():
    assert parse_posted_date("8/14/24") == "2024-08-14"


def test_returns_none_for_unrecognized_text():
    assert parse_posted_date("Sold") is None
    assert parse_posted_date("") is None
    assert parse_posted_date(None) is None
