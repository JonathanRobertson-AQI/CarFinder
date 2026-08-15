"""Unit tests for the AutoTrader, CarGurus, and TrueCar integrations."""
from __future__ import annotations

import json

from carfinder.config import SearchConfig
from carfinder.scrapers import SCRAPER_REGISTRY
from carfinder.scrapers.aggregator import extract_jsonld_listings
from carfinder.scrapers.autotrader import AutoTraderScraper
from carfinder.scrapers.cargurus import CarGurusScraper
from carfinder.scrapers.truecar import TrueCarScraper


def make_config() -> SearchConfig:
    return SearchConfig(
        make="Honda",
        model="Pilot",
        year_min=2011,
        year_max=2015,
        price_min=5000,
        price_max=20000,
        location="80550",
        radius_miles=40,
        max_mileage=150000,
    )


def test_new_sources_are_registered():
    assert {
        "autotrader", "cargurus", "truecar"
    }.issubset(SCRAPER_REGISTRY)


def test_autotrader_url_contains_search_filters():
    url = AutoTraderScraper(make_config()).search_url()
    assert "makeCode=HONDA" in url
    assert "modelCode=PILOT" in url
    assert "zip=80550" in url
    assert "startYear=2011" in url
    assert "endYear=2015" in url
    assert "maxPrice=20000" in url


def test_cargurus_url_contains_search_filters():
    url = CarGurusScraper(make_config()).search_url()
    assert "zip=80550" in url
    assert "distance=40" in url
    assert "make=Honda" in url
    assert "model=Pilot" in url
    assert "minPrice=5000" in url


def test_truecar_url_contains_search_filters():
    url = TrueCarScraper(make_config()).search_url()
    assert "/used-cars-for-sale/listings/honda/pilot/location-80550/" in url
    assert "distance=40" in url
    assert "start_year=2011" in url
    assert "max_price=20000" in url


def test_extracts_vehicle_jsonld_record():
    script = json.dumps({
        "@type": "Vehicle",
        "name": "2013 Honda Pilot EX-L",
        "url": "/vehicle/abc123",
        "modelDate": "2013",
        "brand": {"name": "Honda"},
        "model": "Pilot",
        "vehicleIdentificationNumber": "5FNYF4H42DB000001",
        "mileageFromOdometer": {"value": 98123},
        "offers": {"price": "14995"},
        "datePosted": "2026-08-10T12:30:00Z",
        "address": {"addressLocality": "Loveland"},
    })
    listings = extract_jsonld_listings(
        [script], "autotrader", "https://www.autotrader.com", "Honda", "Pilot"
    )
    assert len(listings) == 1
    listing = listings[0]
    assert listing.url == "https://www.autotrader.com/vehicle/abc123"
    assert listing.year == 2013
    assert listing.price == 14995
    assert listing.mileage == 98123
    assert listing.vin == "5FNYF4H42DB000001"
    assert listing.posted_at == "2026-08-10"


def test_ignores_unrelated_jsonld_records():
    script = json.dumps({
        "@type": "Product",
        "name": "Honda Civic floor mats",
        "url": "/products/mats",
        "offers": {"price": 100},
    })
    assert extract_jsonld_listings(
        [script], "truecar", "https://www.truecar.com", "Honda", "Pilot"
    ) == []
