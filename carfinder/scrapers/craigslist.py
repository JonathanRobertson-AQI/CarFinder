"""Craigslist scraper.

Craigslist has no official listings API but has a relatively stable, simple
search-results HTML structure and does not require login, making it the most
reliable of the three sources to scrape.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from carfinder.models import Listing
from carfinder.scrapers.base import (
    BaseScraper,
    parse_mileage,
    parse_posted_date,
    parse_price,
    parse_year,
)

# Craigslist is organized by city subdomain. Users outside these regions
# should override `region_subdomain` (e.g. via a config field) or add more
# to this map.
DEFAULT_REGION_SUBDOMAIN = "denver"


class CraigslistScraper(BaseScraper):
    source_name = "craigslist"
    region_subdomain = DEFAULT_REGION_SUBDOMAIN

    def search_url(self) -> str:
        query = quote_plus(f"{self.config.make} {self.config.model}")
        url = (
            f"https://{self.region_subdomain}.craigslist.org/search/cta"
            f"?query={query}&auto_make_model={quote_plus(self.config.model)}"
        )
        if self.config.price_max:
            url += f"&max_price={int(self.config.price_max)}"
        if self.config.price_min:
            url += f"&min_price={int(self.config.price_min)}"
        if self.config.year_min:
            url += f"&min_auto_year={self.config.year_min}"
        if self.config.year_max:
            url += f"&max_auto_year={self.config.year_max}"
        if self.config.max_mileage:
            url += f"&max_auto_miles={self.config.max_mileage}"
        return url

    def extract_listings(self, page) -> list[Listing]:
        listings: list[Listing] = []
        # Craigslist's current search-results markup uses div.cl-search-result
        # cards (not the old li.result-row), each with a single a.posting-title
        # link (the gallery/image carousel has its own separate anchors we
        # must avoid), a .meta line containing mileage/location, and a
        # .priceinfo span for price.
        rows = page.locator("div.cl-search-result").all()

        for row in rows:
            try:
                link = row.locator("a.posting-title").first
                url = link.get_attribute("href") or ""
                title = link.inner_text().strip()
                price_text = row.locator(".priceinfo").first.inner_text()
            except Exception:
                continue

            if not url:
                continue

            meta_text = ""
            try:
                meta_text = row.locator(".meta").first.inner_text()
            except Exception:
                pass

            posted_at = None
            try:
                posted_text = row.locator("span.result-posted-date").first.inner_text()
                posted_at = parse_posted_date(posted_text)
            except Exception:
                pass

            listings.append(
                Listing(
                    source=self.source_name,
                    url=url,
                    title=title,
                    price=parse_price(price_text),
                    year=parse_year(title),
                    make=self.config.make,
                    model=self.config.model,
                    mileage=parse_mileage(meta_text),
                    location=self.region_subdomain,
                    posted_at=posted_at,
                )
            )

        return listings
