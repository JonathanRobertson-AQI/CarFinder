"""Common scraper infrastructure shared across sources.

All scrapers use Playwright to drive a real (or headless) browser since none
of the target sites offer a public listings API. This is inherently fragile
(sites change their markup) and may run against sites' Terms of Service if
run automated/repeatedly -- this tool is intended for personal, on-demand,
rate-limited use only.
"""
from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from carfinder.config import SearchConfig
from carfinder.models import Listing

logger = logging.getLogger("carfinder.scrapers")

# Minimum delay between page navigations, to be a reasonably polite scraper.
DEFAULT_REQUEST_DELAY_SECONDS = 3.0

_PRICE_RE = re.compile(r"[\$]?\s*([\d,]+(?:\.\d{2})?)")
_MILEAGE_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*(k)?\s*(?:mi\b|miles)", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")


def parse_price(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    match = _PRICE_RE.search(text.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def parse_mileage(text: Optional[str]) -> Optional[int]:
    """Parse an odometer reading, handling both "95,000 mi" and Craigslist's
    abbreviated "131k mi" formats."""
    if not text:
        return None
    match = _MILEAGE_RE.search(text.replace(",", ""))
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    if match.group(2):  # "k" suffix, e.g. "131k mi" -> 131000
        value *= 1000
    return int(value)


def parse_year(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    match = _YEAR_RE.search(text)
    if not match:
        return None
    return int(match.group(1))


class BaseScraper(ABC):
    """Base class for a listing-source scraper.

    Subclasses implement :meth:`search_url` (builds the source's search URL
    from the config) and :meth:`extract_listings` (parses the loaded page
    into :class:`Listing` objects). :meth:`run` wires these together with a
    Playwright browser and polite delays.
    """

    source_name: str = "base"

    def __init__(
        self,
        config: SearchConfig,
        headless: bool = True,
        request_delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
        storage_state_path: Optional[str] = None,
    ):
        self.config = config
        self.headless = headless
        self.request_delay_seconds = request_delay_seconds
        # Path to a Playwright storage_state JSON file (cookies/localStorage)
        # from a prior manual login. Used by scrapers that require a logged
        # in session (e.g. Facebook Marketplace). Ignored if the file
        # doesn't exist.
        self.storage_state_path = storage_state_path

    @abstractmethod
    def search_url(self) -> str:
        """Build the search URL for this source from ``self.config``."""

    @abstractmethod
    def extract_listings(self, page) -> list[Listing]:
        """Parse the currently-loaded Playwright ``page`` into listings."""

    def run(self) -> list[Listing]:
        """Launch a browser, load the search page, and return listings.

        Any failure is logged and results in an empty list rather than
        raising, so one source failing (e.g. due to a site layout change)
        doesn't abort the whole run.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error(
                "Playwright is not installed. Run `pip install playwright` "
                "and `playwright install chromium` to enable scraping."
            )
            return []

        listings: list[Listing] = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                try:
                    context_kwargs: dict = {
                        "user_agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/124.0 Safari/537.36"
                        )
                    }
                    if self.storage_state_path and Path(self.storage_state_path).exists():
                        context_kwargs["storage_state"] = str(self.storage_state_path)
                        logger.info(
                            "[%s] using saved login session from %s",
                            self.source_name, self.storage_state_path,
                        )
                    context = browser.new_context(**context_kwargs)
                    page = context.new_page()
                    url = self.search_url()
                    logger.info("[%s] navigating to %s", self.source_name, url)
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(self.request_delay_seconds)
                    listings = self.extract_listings(page)
                finally:
                    browser.close()
        except Exception:
            logger.exception("[%s] scrape failed", self.source_name)
            return []

        logger.info("[%s] found %d listing(s)", self.source_name, len(listings))
        return listings
