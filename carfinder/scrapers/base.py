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
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

from carfinder.config import SearchConfig
from carfinder.models import Listing

logger = logging.getLogger("carfinder.scrapers")

# Minimum delay between page navigations, to be a reasonably polite scraper.
DEFAULT_REQUEST_DELAY_SECONDS = 3.0

_PRICE_RE = re.compile(r"[\$]?\s*([\d,]+(?:\.\d{2})?)")
_MILEAGE_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*(k)?\s*(?:mi\b|miles)", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")

# Approximate day-equivalents used to turn a relative "posted" phrase into a
# concrete date. Only precise to the day, which is all a "date listed"
# report column needs.
_RELATIVE_UNIT_TO_DAYS = {
    "minute": 0, "min": 0, "m": 0,
    "hour": 0, "hr": 0, "h": 0,
    "day": 1, "d": 1,
    "week": 7, "w": 7,
    "month": 30, "mo": 30,
    "year": 365, "yr": 365, "y": 365,
}
# Spelled-out relative phrasing, e.g. Facebook's "a day ago", "2 weeks ago".
_RELATIVE_WORDS_RE = re.compile(
    r"^(a|an|\d+)\s*(minute|hour|day|week|month|year)s?\s*ago$", re.IGNORECASE
)
# Abbreviated relative phrasing, e.g. Craigslist's "4h ago", "2d ago".
_RELATIVE_ABBR_RE = re.compile(
    r"^(\d+)\s*(min|hr|mo|[mhdwy])\s*ago$", re.IGNORECASE
)
# A bare month/day (optionally /year) with no "ago" wording, e.g. Craigslist's
# short-form dates for postings old enough to have scrolled off relative time
# (e.g. "8/14", "8/14/24").
_SHORT_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$")


def parse_posted_date(text: Optional[str]) -> Optional[str]:
    """Parse a source's compact "posted"/"listed" date text into an ISO
    ``YYYY-MM-DD`` string, or ``None`` if the text doesn't match a known
    format. Handles the formats observed across sources: spelled-out
    relative time ("a day ago", "2 weeks ago"), abbreviated relative time
    ("4h ago", "2d ago"), and bare short dates ("8/14", "8/14/24")."""
    if not text:
        return None
    candidate = text.strip().lower()

    match = _RELATIVE_WORDS_RE.match(candidate)
    if match:
        amount = 1 if match.group(1) in ("a", "an") else int(match.group(1))
        return _relative_to_iso(amount, match.group(2))

    match = _RELATIVE_ABBR_RE.match(candidate)
    if match:
        return _relative_to_iso(int(match.group(1)), match.group(2))

    match = _SHORT_DATE_RE.match(candidate)
    if match:
        month, day = int(match.group(1)), int(match.group(2))
        year_text = match.group(3)
        today = date.today()
        year = today.year
        if year_text:
            year = int(year_text)
            if year < 100:
                year += 2000
        try:
            candidate_date = date(year, month, day)
        except ValueError:
            return None
        # A bare "M/D" with no year is always the most recent such date not
        # in the future (Craigslist never shows upcoming dates as "posted").
        if not year_text and candidate_date > today:
            candidate_date = date(year - 1, month, day)
        return candidate_date.isoformat()

    return None


def _relative_to_iso(amount: int, unit: str) -> str:
    days = amount * _RELATIVE_UNIT_TO_DAYS.get(unit.lower(), 0)
    return (date.today() - timedelta(days=days)).isoformat()


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
        on_progress: Optional[Callable[[str], None]] = None,
    ):
        self.config = config
        self.headless = headless
        self.request_delay_seconds = request_delay_seconds
        # Path to a Playwright storage_state JSON file (cookies/localStorage)
        # from a prior manual login. Used by scrapers that require a logged
        # in session (e.g. Facebook Marketplace). Ignored if the file
        # doesn't exist.
        self.storage_state_path = storage_state_path
        # Optional callback for short human-readable progress updates, so a
        # slow multi-step scrape (e.g. Facebook's per-listing detail page
        # visits for mileage) can surface interim status to a web UI instead
        # of looking stuck between the "Searching..." and "found N" lines.
        self.on_progress = on_progress

    def _notify(self, message: str) -> None:
        logger.info("[%s] %s", self.source_name, message)
        if self.on_progress:
            self.on_progress(message)

    def prepare(self, page) -> None:
        """Optional hook run once, right after the page/context is created
        but before :meth:`search_url` / navigation. Default no-op. Override
        for sources that need to establish state (e.g. a location) via the
        browser before a search URL can be correctly built."""

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
                    self.prepare(page)
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
