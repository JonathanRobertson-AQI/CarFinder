"""Cars.com scraper.

Represents the Cars.com/AutoTrader/CarGurus aggregator-site family. Cars.com
is implemented directly; AutoTrader and CarGurus follow a very similar
search-results structure and can reuse most of this logic (see README) --
they're left as follow-up work since each requires its own selector tuning.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from carfinder.models import Listing
from carfinder.scrapers.base import BaseScraper, parse_mileage, parse_price


class CarsComScraper(BaseScraper):
    source_name = "cars_com"

    def search_url(self) -> str:
        make = quote_plus(self.config.make)
        model = quote_plus(self.config.model)
        url = (
            "https://www.cars.com/shopping/results/"
            f"?makes[]={make}&models[]={make}-{model}"
            f"&year_min={self.config.year_min}&year_max={self.config.year_max}"
            f"&zip={self.config.location}&maximum_distance={self.config.radius_miles}"
            "&stock_type=used"
        )
        if self.config.price_max:
            url += f"&list_price_max={int(self.config.price_max)}"
        if self.config.price_min:
            url += f"&list_price_min={int(self.config.price_min)}"
        if self.config.max_mileage:
            url += f"&mileage_max={self.config.max_mileage}"
        return url

    def extract_listings(self, page) -> list[Listing]:
        listings: list[Listing] = []
        cards = page.locator("div.vehicle-card").all()

        for card in cards:
            try:
                title = card.locator(".title").first.inner_text().strip()
                link_el = card.locator("a.vehicle-card-link").first
                href = link_el.get_attribute("href") or ""
                url = (
                    href if href.startswith("http") else f"https://www.cars.com{href}"
                )
                price_text = card.locator(".primary-price").first.inner_text()
                mileage_text = card.locator(".mileage").first.inner_text()
            except Exception:
                continue

            if not href:
                continue

            year = None
            parts = title.split(" ", 1)
            if parts and parts[0].isdigit():
                year = int(parts[0])

            listings.append(
                Listing(
                    source=self.source_name,
                    url=url,
                    title=title,
                    price=parse_price(price_text),
                    year=year,
                    make=self.config.make,
                    model=self.config.model,
                    mileage=parse_mileage(mileage_text),
                    location=self.config.location,
                )
            )

        return listings
