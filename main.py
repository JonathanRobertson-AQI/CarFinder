"""CLI entrypoint: run scrapers, persist listings, decode VINs, and generate
the daily report.

Usage:
    python main.py                      # use config.json (or defaults)
    python main.py --config my.json
    python main.py --sources craigslist,cars_com

For a non-technical, point-and-click experience (including Facebook login),
run the web UI instead: `python app.py`.
"""
from __future__ import annotations

import argparse
import logging
import sys

from carfinder.config import SearchConfig
from carfinder.pipeline import run_pipeline

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("carfinder.main")

DEFAULT_STORAGE_STATE_PATH = "facebook_session.json"


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
    parser.add_argument(
        "--facebook-session",
        default=DEFAULT_STORAGE_STATE_PATH,
        help=(
            "Path to a saved Facebook login session (created via `python "
            "facebook_login.py` or the web UI's 'Log into Facebook' button)"
        ),
    )
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    config = (
        SearchConfig.from_file(args.config)
        if args.config
        else SearchConfig.load_default()
    )
    sources = args.sources.split(",") if args.sources else config.sources

    _rows, report_path = run_pipeline(
        config,
        sources=sources,
        headless=not args.no_headless,
        decode_vins=args.decode_vins,
        db_path=args.db,
        report_dir=args.report_dir,
        storage_state_path=args.facebook_session,
    )
    print(f"Report written to {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
