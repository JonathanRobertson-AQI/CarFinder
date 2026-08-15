"""TrueCar scraper."""
from __future__ import annotations

from urllib.parse import quote

from carfinder.scrapers.aggregator import AggregatorScraper


class TrueCarScraper(AggregatorScraper):
    source_name = "truecar"
    base_url = "https://www.truecar.com"

    def search_url(self) -> str:
        path = (
            f"/used-cars-for-sale/listings/{quote(self.config.make.lower())}/"
            f"{quote(self.config.model.lower())}/location-{quote(self.config.location)}/"
        )
        params = [
            f"distance={int(self.config.radius_miles)}",
            f"start_year={int(self.config.year_min)}",
            f"end_year={int(self.config.year_max)}",
        ]
        if self.config.price_min is not None:
            params.append(f"min_price={int(self.config.price_min)}")
        if self.config.price_max is not None:
            params.append(f"max_price={int(self.config.price_max)}")
        if self.config.max_mileage is not None:
            params.append(f"max_mileage={int(self.config.max_mileage)}")
        return self.base_url + path + "?" + "&".join(params)
