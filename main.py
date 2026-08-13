"""CLI entrypoint: run scrapers, persist listings, decode VINs, and generate
the daily report.

Usage:
    python main.py                      # use config.json (or defaults)
    python main.py --config my.json
    python main.py --sources craigslist,cars_com
"""
from __future__ import annotations

import argparse
import logging
import sys

from carfinder.config import SearchConfig
from carfinder.db import ListingStore
from carfinder.models import Listing
from carfinder.report import ReportRow, write_report
from carfinder.scrapers import SCRAPER_REGISTRY
from carfinder.valuation import evaluate_listing
from carfinder.vin import decode_vin

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("carfinder.main")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CarFinder: used car search tool")
    parser.add_argument("--config", help="Path to a JSON config file")
    parser.add_argument(
        "--sources",
        help="Comma-separated list of sources to run (default: from config)",
    )
    parser.add_argument(
        "--no-headless", action="store_true", help="Show the browser window"
    )
    parser.add_argument(
        "--decode-vins",
        action="store_true",
        help="Decode VINs via NHTSA for listings that include one",
    )
    parser.add_argument(
        "--db", default=None, help="Path to the SQLite database file"
    )
    parser.add_argument(
        "--report-dir", default="reports", help="Directory to write the report"
    )
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    config = SearchConfig.from_file(args.config) if args.config else SearchConfig.load_default()
    sources = args.sources.split(",") if args.sources else config.sources

    store = ListingStore(args.db) if args.db else ListingStore()

    all_listings: list[Listing] = []
    for source in sources:
        scraper_cls = SCRAPER_REGISTRY.get(source)
        if scraper_cls is None:
            logger.warning("Unknown source '%s', skipping", source)
            continue
        scraper = scraper_cls(config, headless=not args.no_headless)
        listings = scraper.run()
        all_listings.extend(listings)

        if args.decode_vins:
            for listing in listings:
                if listing.vin:
                    decoded = decode_vin(listing.vin)
                    if decoded:
                        listing.trim = listing.trim or decoded.get("trim")

        is_new_by_id: dict[str, tuple[bool, float | None]] = {}
        for listing in listings:
            is_new, previous_price = store.upsert(listing)
            is_new_by_id[listing.listing_id] = (is_new, previous_price)
        store.mark_inactive_except((l.listing_id for l in listings), source)

    active = store.active_listings(make=config.make, model=config.model)
    comparable_prices = store.comparable_prices(
        config.make, config.model, config.year_min, config.year_max
    )

    rows: list[ReportRow] = []
    for record in active:
        others = [p for p in comparable_prices if record["price"] is None or p != record["price"]]
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
            )
        )

    report_path = write_report(rows, config.make, config.model, output_dir=args.report_dir)
    logger.info("Report written to %s", report_path)
    print(f"Report written to {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
