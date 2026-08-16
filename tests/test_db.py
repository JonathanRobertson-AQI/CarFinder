import tempfile
from pathlib import Path

import pytest

from carfinder.db import ListingStore
from carfinder.models import Listing


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as tmp:
        yield ListingStore(Path(tmp) / "test.db")


def make_listing(url="https://example.com/1", price=15000, **kwargs):
    defaults = dict(
        source="craigslist",
        url=url,
        title="2012 Honda Pilot EX-L",
        price=price,
        year=2012,
        make="Honda",
        model="Pilot",
    )
    defaults.update(kwargs)
    return Listing(**defaults)


def test_upsert_new_listing_is_new(store):
    listing = make_listing()
    is_new, previous_price = store.upsert(listing)
    assert is_new is True
    assert previous_price is None


def test_upsert_existing_listing_not_new_and_tracks_previous_price(store):
    listing = make_listing(price=15000)
    store.upsert(listing)

    updated = make_listing(price=13500)  # same URL -> same listing_id
    is_new, previous_price = store.upsert(updated)

    assert is_new is False
    assert previous_price == 15000


def test_active_listings_filters_by_make_model(store):
    store.upsert(make_listing(url="https://example.com/1"))
    store.upsert(
        make_listing(url="https://example.com/2", make="Toyota", model="RAV4")
    )

    results = store.active_listings(make="Honda", model="Pilot")
    assert len(results) == 1
    assert results[0]["url"] == "https://example.com/1"


def test_active_listings_make_model_filter_is_case_insensitive(store):
    store.upsert(make_listing(make="Honda", model="Pilot"))

    results = store.active_listings(make="honda", model="pilot")

    assert len(results) == 1


def test_mark_inactive_except_deactivates_missing_listings(store):
    l1 = make_listing(url="https://example.com/1")
    l2 = make_listing(url="https://example.com/2")
    store.upsert(l1)
    store.upsert(l2)

    # Simulate a re-scrape where only l1 is still present.
    store.mark_inactive_except([l1.listing_id], source="craigslist")

    active = store.active_listings(make="Honda", model="Pilot")
    active_urls = {row["url"] for row in active}
    assert active_urls == {"https://example.com/1"}


def test_comparable_prices_respects_year_range(store):
    store.upsert(make_listing(url="https://example.com/1", year=2012, price=15000))
    store.upsert(make_listing(url="https://example.com/2", year=2005, price=5000))

    prices = store.comparable_prices("Honda", "Pilot", 2009, 2015)
    assert prices == [15000]
