"""Tests for Facebook Marketplace location-scoped search URL building.

Facebook's plain /marketplace/search/?query=... endpoint ignores the
logged-in account's real location and falls back to an unrelated region
(observed: consistently the San Francisco Bay Area). The scraper discovers
the account's actual Marketplace location id via prepare() (a live browser
step) and then threads it into search_url(); these tests cover the pure
URL-building logic given a location id is (or isn't) already known.
"""
from __future__ import annotations

from carfinder.config import SearchConfig
from carfinder.scrapers.facebook import FacebookMarketplaceScraper


def _make_scraper(**config_overrides) -> FacebookMarketplaceScraper:
    config = SearchConfig(**config_overrides)
    return FacebookMarketplaceScraper(config=config)


def test_search_url_uses_location_scoped_endpoint_once_location_id_known():
    scraper = _make_scraper(radius_miles=100)
    scraper._location_id = "103797106325848"
    url = scraper.search_url()
    assert url.startswith(
        "https://www.facebook.com/marketplace/103797106325848/search/?query="
    )
    assert "radius=100" in url


def test_search_url_falls_back_to_plain_endpoint_without_location_id():
    scraper = _make_scraper()
    assert scraper._location_id is None
    url = scraper.search_url()
    assert url.startswith("https://www.facebook.com/marketplace/search/?query=")


def test_search_url_includes_price_filters_with_location_id():
    scraper = _make_scraper(price_min=5000, price_max=15000)
    scraper._location_id = "103797106325848"
    url = scraper.search_url()
    assert "maxPrice=15000" in url
    assert "minPrice=5000" in url


def test_search_url_omits_radius_param_when_radius_is_zero():
    scraper = _make_scraper(radius_miles=0)
    scraper._location_id = "103797106325848"
    url = scraper.search_url()
    assert "radius=" not in url
