"""Facebook Marketplace scraper.

Facebook Marketplace has no public API. Most searches also require a
logged-in session; this scraper accepts an optional Playwright storage_state
(see carfinder/facebook_auth.py and the web UI's "Log into Facebook" button)
but does not handle login itself. In testing, a logged-out session still
returned public results for a plain vehicle search, though a login wall may
appear for some searches/locations/accounts -- if you see zero results,
log in via the web UI first.

Marketplace's DOM is heavily obfuscated (auto-generated class names) and
changes frequently, so selectors here are deliberately broad (role/text based
where possible) and this scraper should be expected to need maintenance.
"""
from __future__ import annotations

import re
import time
from urllib.parse import quote_plus

from carfinder.models import Listing
from carfinder.scrapers.base import BaseScraper, parse_price, parse_year

# A marketplace card's text is a set of newline-separated lines with no
# reliable fixed position for title/price/location, e.g.:
#   "$5,000\n$6,000\n2014 Honda pilot EX Sport Utility 4D\nHayward, CA"
#   (current price, then a crossed-out original price, then title, location)
#   "Just listed\n$4,300\n2012 Honda pilot LX Sport Utility 4D\nStockton, CA"
#   (a "Just listed"/"New" badge line before the price)
# So rather than assuming a fixed line index, classify each line as either a
# bare price (e.g. "$5,000") or text, and take the first price line as the
# current price and the first non-badge text line as the title.
_PRICE_LINE_RE = re.compile(r"^\$[\d,]+(?:\.\d{2})?$")
_BADGE_WORDS = {"just listed", "new"}

# Unlike the search-results cards, a listing's own detail page includes a
# structured "About this vehicle" section (e.g. "Driven 135,000 miles") and
# often a more precise figure in the seller's free-text description (e.g.
# "Mileage: 133,690 miles"). Search results themselves never include
# mileage at all, so it has to be fetched from each listing's detail page.
# Some listings skip the structured section and just mention mileage in
# free text (English or Spanish, e.g. "with 183,596 miles" / "132mil
# millas"), so several fallback patterns are tried in order of reliability.
_DRIVEN_MILEAGE_RE = re.compile(r"Driven\s+([\d,]+)\s*miles?", re.IGNORECASE)
_DESCRIPTION_MILEAGE_RE = re.compile(r"Mileage[:\s]+([\d,]+)\s*miles?", re.IGNORECASE)
# Requires a comma-grouped number or 4-6 plain digits directly followed by
# the full word "miles" (not "mi"), to avoid false positives like the
# sidebar's "Within 40 mi" search-radius text.
_GENERIC_MILES_RE = re.compile(r"\b(\d{1,3}(?:,\d{3})+|\d{4,6})\s*miles\b", re.IGNORECASE)
_SPANISH_MIL_MILLAS_RE = re.compile(r"(\d+)\s*mil\s*millas", re.IGNORECASE)
_SPANISH_MILLAS_RE = re.compile(r"\b(\d{1,3}(?:,\d{3})+|\d{4,6})\s*millas\b", re.IGNORECASE)
MILEAGE_PATTERNS = [
    (_DRIVEN_MILEAGE_RE, 1),
    (_DESCRIPTION_MILEAGE_RE, 1),
    (_GENERIC_MILES_RE, 1),
    (_SPANISH_MIL_MILLAS_RE, 1000),  # "132mil millas" == 132 thousand miles
    (_SPANISH_MILLAS_RE, 1),
]
DETAIL_PAGE_DELAY_SECONDS = 1.5


class FacebookMarketplaceScraper(BaseScraper):
    source_name = "facebook"

    def search_url(self) -> str:
        query = quote_plus(f"{self.config.make} {self.config.model}")
        # "propertyoftype=cars" search within Marketplace's vehicles category.
        base = f"https://www.facebook.com/marketplace/search/?query={query}"
        if self.config.price_max:
            base += f"&maxPrice={int(self.config.price_max)}"
        if self.config.price_min:
            base += f"&minPrice={int(self.config.price_min)}"
        return base

    def extract_listings(self, page) -> list[Listing]:
        listings: list[Listing] = []

        # Marketplace search results are anchors linking to /marketplace/item/...
        cards = page.locator("a[href*='/marketplace/item/']").all()
        seen_urls: set[str] = set()

        for card in cards:
            try:
                href = card.get_attribute("href") or ""
                if not href:
                    continue
                url = "https://www.facebook.com" + href.split("?")[0]
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                text = card.inner_text()
            except Exception:
                continue

            if not text:
                continue

            lines = [line.strip() for line in text.split("\n") if line.strip()]
            price_lines = [l for l in lines if _PRICE_LINE_RE.match(l)]
            text_lines = [
                l for l in lines
                if not _PRICE_LINE_RE.match(l) and l.lower() not in _BADGE_WORDS
            ]

            price = parse_price(price_lines[0]) if price_lines else None
            title = text_lines[0] if text_lines else ""
            location = text_lines[-1] if len(text_lines) > 1 else self.config.location
            year = parse_year(title)

            listings.append(
                Listing(
                    source=self.source_name,
                    url=url,
                    title=title,
                    price=price,
                    year=year,
                    make=self.config.make,
                    model=self.config.model,
                    location=location,
                )
            )

        # Mileage isn't shown on the search-results cards at all, so visit
        # each listing's own detail page for it. This adds real time (one
        # extra page load per listing) but is the only way to get it.
        for listing in listings:
            listing.mileage = self._fetch_mileage(page, listing.url)

        return listings

    def _fetch_mileage(self, page, url: str) -> int | None:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(DETAIL_PAGE_DELAY_SECONDS)
            body_text = page.locator("body").inner_text()
        except Exception:
            return None

        for pattern, multiplier in MILEAGE_PATTERNS:
            match = pattern.search(body_text)
            if match:
                try:
                    return int(float(match.group(1).replace(",", "")) * multiplier)
                except ValueError:
                    continue
        return None
