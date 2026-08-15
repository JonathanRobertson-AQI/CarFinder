"""AutoTrader scraper."""
from __future__ import annotations

from urllib.parse import quote_plus

from carfinder.scrapers.aggregator import AggregatorScraper


class AutoTraderScraper(AggregatorScraper):
    source_name = "autotrader"
    base_url = "https://www.autotrader.com"

    def search_url(self) -> str:
        params = [
            f"makeCode={quote_plus(self.config.make.upper())}",
            f"modelCode={quote_plus(self.config.model.upper())}",
            f"zip={quote_plus(self.config.location)}",
            f"searchRadius={int(self.config.radius_miles)}",
            f"startYear={int(self.config.year_min)}",
            f"endYear={int(self.config.year_max)}",
        ]
        if self.config.price_min is not None:
            params.append(f"minPrice={int(self.config.price_min)}")
        if self.config.price_max is not None:
            params.append(f"maxPrice={int(self.config.price_max)}")
        if self.config.max_mileage is not None:
            params.append(f"maxMileage={int(self.config.max_mileage)}")
        return "https://www.autotrader.com/cars-for-sale/all-cars?" + "&".join(params)
