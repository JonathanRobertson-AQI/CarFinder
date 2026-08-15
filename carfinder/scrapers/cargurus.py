"""CarGurus scraper."""
from __future__ import annotations

from urllib.parse import quote_plus

from carfinder.scrapers.aggregator import AggregatorScraper


class CarGurusScraper(AggregatorScraper):
    source_name = "cargurus"
    base_url = "https://www.cargurus.com"

    def search_url(self) -> str:
        params = [
            f"zip={quote_plus(self.config.location)}",
            f"distance={int(self.config.radius_miles)}",
            f"make={quote_plus(self.config.make)}",
            f"model={quote_plus(self.config.model)}",
            f"startYear={int(self.config.year_min)}",
            f"endYear={int(self.config.year_max)}",
            "sourceContext=carGurusHomePageModel",
        ]
        if self.config.price_min is not None:
            params.append(f"minPrice={int(self.config.price_min)}")
        if self.config.price_max is not None:
            params.append(f"maxPrice={int(self.config.price_max)}")
        if self.config.max_mileage is not None:
            params.append(f"maxMileage={int(self.config.max_mileage)}")
        return (
            "https://www.cargurus.com/Cars/inventorylisting/"
            "viewDetailsFilterViewInventoryListing.action?" + "&".join(params)
        )
