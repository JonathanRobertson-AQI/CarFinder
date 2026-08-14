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

        return listings
