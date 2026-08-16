"""Tests for the scrape -> persist -> report pipeline, focused on the
year/price/mileage post-scrape filter (carfinder.pipeline._within_filters).

Some sources' search URLs don't reliably filter server-side (Facebook
Marketplace in particular sends no year/mileage query params at all), so
these filters need to be enforced after scraping regardless of source.
"""
from __future__ import annotations

from unittest.mock import patch

from carfinder.config import SearchConfig
from carfinder.models import Listing
from carfinder.pipeline import _values_within_filters, _within_filters, run_pipeline


def make_listing(**kwargs) -> Listing:
    defaults = dict(
        source="facebook",
        url="https://example.com/1",
        title="2012 Honda Pilot EX-L",
        price=15000,
        year=2012,
        make="Honda",
        model="Pilot",
        mileage=90000,
    )
    defaults.update(kwargs)
    return Listing(**defaults)


def test_within_filters_rejects_year_below_range():
    config = SearchConfig(year_min=2011, year_max=2015)
    assert not _within_filters(make_listing(year=2004), config)


def test_within_filters_rejects_year_above_range():
    config = SearchConfig(year_min=2011, year_max=2015)
    assert not _within_filters(make_listing(year=2018), config)


def test_within_filters_accepts_year_in_range():
    config = SearchConfig(year_min=2011, year_max=2015)
    assert _within_filters(make_listing(year=2013), config)


def test_within_filters_accepts_unknown_year():
    # Can't judge what we don't know -- don't drop listings with no parsed
    # year just because a year filter is set.
    config = SearchConfig(year_min=2011, year_max=2015)
    assert _within_filters(make_listing(year=None), config)


def test_within_filters_rejects_price_and_mileage_out_of_range():
    config = SearchConfig(price_min=10000, price_max=20000, max_mileage=100000)
    assert not _within_filters(make_listing(price=5000), config)
    assert not _within_filters(make_listing(price=25000), config)
    assert not _within_filters(make_listing(mileage=150000), config)


def test_values_within_filters_rejects_years_outside_selected_range():
    config = SearchConfig(year_min=2011, year_max=2015)
    assert not _values_within_filters(2008, 10000, 90000, config)
    assert not _values_within_filters(2018, 10000, 90000, config)
    assert _values_within_filters(2013, 10000, 90000, config)


def test_run_pipeline_filters_out_of_range_listings_before_persisting(tmp_path):
    config = SearchConfig(
        make="Honda", model="Pilot", year_min=2011, year_max=2015,
        sources=["facebook"],
    )
    in_range = make_listing(url="https://example.com/in-range", year=2013)
    out_of_range = make_listing(url="https://example.com/out-of-range", year=2004)

    class StubScraper:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            return [in_range, out_of_range]

    db_path = tmp_path / "test.db"
    report_dir = tmp_path / "reports"
    with patch.dict("carfinder.pipeline.SCRAPER_REGISTRY", {"facebook": StubScraper}):
        rows, _ = run_pipeline(
            config, db_path=db_path, report_dir=report_dir,
        )

    urls = {row.url for row in rows}
    assert "https://example.com/in-range" in urls
    assert "https://example.com/out-of-range" not in urls
