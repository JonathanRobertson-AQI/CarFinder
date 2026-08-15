"""Core scrape -> persist -> valuate -> report pipeline.

Shared by the CLI (main.py) and the web UI (app.py) so both stay in sync.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from carfinder.config import SearchConfig
from carfinder.db import ListingStore
from carfinder.models import Listing
from carfinder.report import ReportRow, dedupe_rows, rank_rows, write_report
from carfinder.scrapers import SCRAPER_REGISTRY
from carfinder.valuation import evaluate_listing
from carfinder.vin import decode_vin

logger = logging.getLogger("carfinder.pipeline")

ProgressCallback = Callable[[str], None]


def _within_filters(listing: Listing, config: SearchConfig) -> bool:
    """Check a scraped listing against year/price/mileage filters.

    Not every source's search URL reliably honors these filters server-side
    (notably Facebook Marketplace, which has no year/mileage query params at
    all), so this is applied uniformly after scraping as a safety net --
    without it, a search for e.g. 2011-2015 could silently include much
    older/newer or out-of-budget listings just because the site returned
    them anyway.
    """
    if listing.year is not None:
        if config.year_min and listing.year < config.year_min:
            return False
        if config.year_max and listing.year > config.year_max:
            return False
    if listing.price is not None:
        if config.price_min and listing.price < config.price_min:
            return False
        if config.price_max and listing.price > config.price_max:
            return False
    if listing.mileage is not None and config.max_mileage:
        if listing.mileage > config.max_mileage:
            return False
    return True


def run_pipeline(
    config: SearchConfig,
    sources: Optional[list[str]] = None,
    headless: bool = True,
    decode_vins: bool = False,
    db_path: Optional[str | Path] = None,
    report_dir: str | Path = "reports",
    storage_state_path: Optional[str | Path] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> tuple[list[ReportRow], Path]:
    """Run the full pipeline and return (rows, report_path).

    ``storage_state_path`` is passed through to scrapers that support a
    saved login session (currently Facebook Marketplace).
    ``on_progress`` is an optional callback invoked with short human-readable
    status strings, useful for surfacing progress in a web UI.
    """
    def notify(message: str) -> None:
        logger.info(message)
        if on_progress:
            on_progress(message)

    sources = sources or config.sources
    store = ListingStore(db_path) if db_path else ListingStore()

    # Track is_new/previous_price across ALL sources, not just the last one.
    is_new_by_id: dict[str, tuple[bool, Optional[float]]] = {}

    for source in sources:
        scraper_cls = SCRAPER_REGISTRY.get(source)
        if scraper_cls is None:
            notify(f"Unknown source '{source}', skipping")
            continue

        notify(f"Searching {source}...")
        kwargs = {}
        if source == "facebook" and storage_state_path:
            kwargs["storage_state_path"] = storage_state_path
        scraper = scraper_cls(config, headless=headless, on_progress=on_progress, **kwargs)
        listings: list[Listing] = scraper.run()
        notify(f"{source}: found {len(listings)} listing(s)")

        before_filter = len(listings)
        listings = [l for l in listings if _within_filters(l, config)]
        if len(listings) != before_filter:
            notify(
                f"{source}: filtered out {before_filter - len(listings)} listing(s) "
                f"outside the year/price/mileage filters"
            )

        if decode_vins:
            for listing in listings:
                if listing.vin:
                    decoded = decode_vin(listing.vin)
                    if decoded:
                        listing.trim = listing.trim or decoded.get("trim")

        for listing in listings:
            is_new, previous_price = store.upsert(listing)
            is_new_by_id[listing.listing_id] = (is_new, previous_price)
        store.mark_inactive_except((l.listing_id for l in listings), source)

    notify("Scoring listings against comparable prices...")
    active = store.active_listings(make=config.make, model=config.model)
    comparable_prices = store.comparable_prices(
        config.make, config.model, config.year_min, config.year_max
    )

    rows: list[ReportRow] = []
    for record in active:
        others = [
            p for p in comparable_prices
            if record["price"] is None or p != record["price"]
        ]
        valuation = evaluate_listing(
            record["price"],
            others or comparable_prices,
            min_sample_size=config.min_sample_size_for_valuation,
            good_deal_percentile=config.good_deal_percentile,
        )
        is_new, previous_price = is_new_by_id.get(record["listing_id"], (False, None))
        rows.append(
            ReportRow(
                title=record["title"],
                url=record["url"],
                source=record["source"],
                price=record["price"],
                year=record["year"],
                mileage=record["mileage"],
                location=record["location"],
                is_new=is_new,
                previous_price=previous_price,
                valuation=valuation,
                posted_at=record["posted_at"],
            )
        )

    rows = rank_rows(dedupe_rows(rows))
    report_path = write_report(rows, config.make, config.model, output_dir=report_dir)
    notify(f"Report written to {report_path}")
    return rows, report_path
