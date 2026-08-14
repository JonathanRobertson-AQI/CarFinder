"""Cars.com scraper.

Represents the Cars.com/AutoTrader/CarGurus aggregator-site family. Cars.com
is implemented directly; AutoTrader and CarGurus follow a very similar
search-results structure and can reuse most of this logic (see README) --
they're left as follow-up work since each requires its own selector tuning.

Cars.com's search results page embeds a full JSON array of structured
vehicle data (make/model/year/mileage/price/VIN/trim/dealer) in a
`data-vehicle-array` HTML attribute on a `<search-provider>` element. This
is far more robust than scraping visible card text, since it doesn't depend
on the visual layout at all -- only on Cars.com continuing to embed this
attribute, which is a smaller and more stable surface than CSS classes.
"""
from __future__ import annotations

import json
from urllib.parse import quote_plus

from carfinder.models import Listing
from carfinder.scrapers.base import BaseScraper

DETAIL_URL_TEMPLATE = "https://www.cars.com/vehicledetail/{listing_id}/"


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
        raw = page.locator("search-provider").first.get_attribute(
            "data-vehicle-array"
        )
        if not raw:
            return []

        try:
            vehicles = json.loads(raw)
        except json.JSONDecodeError:
            return []

        listings: list[Listing] = []
        for vehicle in vehicles:
            listing_id = vehicle.get("listingId")
            if not listing_id:
                continue

            year = vehicle.get("year")
            try:
                year = int(year) if year else None
            except (TypeError, ValueError):
                year = None

            mileage = vehicle.get("mileage")
            try:
                mileage = int(mileage) if mileage else None
            except (TypeError, ValueError):
                mileage = None

            price = vehicle.get("price")
            try:
                price = float(price) if price else None
            except (TypeError, ValueError):
                price = None

            seller = vehicle.get("seller") or {}
            title_parts = [
                str(year) if year else None,
                vehicle.get("make"),
                vehicle.get("model"),
                vehicle.get("trim"),
            ]
            title = " ".join(p for p in title_parts if p)

            listings.append(
                Listing(
                    source=self.source_name,
                    url=DETAIL_URL_TEMPLATE.format(listing_id=listing_id),
                    title=title,
                    price=price,
                    year=year,
                    make=vehicle.get("make") or self.config.make,
                    model=vehicle.get("model") or self.config.model,
                    trim=vehicle.get("trim"),
                    mileage=mileage,
                    location=seller.get("zip") or self.config.location,
                    vin=vehicle.get("vin"),
                )
            )

        return listings
