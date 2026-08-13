"""Craigslist scraper.

Craigslist has no official listings API but has a relatively stable, simple
search-results HTML structure and does not require login, making it the most
reliable of the three sources to scrape.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from carfinder.models import Listing
from carfinder.scrapers.base import BaseScraper, parse_price, parse_year

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
        rows = page.locator("li.cl-search-result").all()

        for row in rows:
            try:
                link = row.locator("a.cl-app-anchor").first
                url = link.get_attribute("href") or ""
                title = link.inner_text().strip()
                price_text = row.locator(".priceinfo").first.inner_text()
            except Exception:
                continue

            if not url:
                continue

            listings.append(
                Listing(
                    source=self.source_name,
                    url=url,
                    title=title,
                    price=parse_price(price_text),
                    year=parse_year(title),
                    make=self.config.make,
                    model=self.config.model,
                    location=self.region_subdomain,
                )
            )

        return listings
