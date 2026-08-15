"""Search configuration for CarFinder.

Configuration is intentionally generic (make/model/year range/price/location)
so the tool can be reused for any vehicle search, not just the 2nd-gen Honda
Pilot this was originally built for.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path


@dataclass
class SearchConfig:
    """Defines what to search for.

    Attributes:
        make: Vehicle make, e.g. "Honda".
        model: Vehicle model, e.g. "Pilot".
        year_min: Minimum model year (inclusive).
        year_max: Maximum model year (inclusive).
        price_max: Maximum listing price in USD. None means no cap.
        price_min: Minimum listing price in USD. None means no floor.
        location: Free-text location (zip code or city/state) used as the
            search origin.
        radius_miles: Search radius in miles around ``location``.
        max_mileage: Maximum odometer reading to consider. None means no cap.
        sources: Which scrapers to run. Defaults to all built-in sources.
        min_sample_size_for_valuation: Minimum number of comparable listings
            required before a deal score is computed for a listing.
        good_deal_percentile: A listing priced at or below this percentile of
            comparable prices is flagged as a "good deal" in the report.
    """

    make: str = "Honda"
    model: str = "Pilot"
    year_min: int = 2009
    year_max: int = 2015
    price_max: float | None = 20000
    price_min: float | None = None
    location: str = "80301"
    radius_miles: int = 100
    max_mileage: int | None = 150000
    sources: list[str] = field(
        default_factory=lambda: [
            "facebook", "craigslist", "cars_com", "autotrader", "cargurus", "truecar"
        ]
    )
    min_sample_size_for_valuation: int = 5
    good_deal_percentile: float = 25.0

    @classmethod
    def from_file(cls, path: str | Path) -> "SearchConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**data)

    @classmethod
    def default_path(cls) -> Path:
        return Path(__file__).resolve().parent.parent / "config.json"

    @classmethod
    def load_default(cls) -> "SearchConfig":
        path = cls.default_path()
        if path.exists():
            return cls.from_file(path)
        return cls()

    def to_file(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.__dict__, indent=2), encoding="utf-8"
        )
