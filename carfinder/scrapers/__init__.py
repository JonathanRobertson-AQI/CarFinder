"""Scraper package: one module per listing source.

Each scraper implements :class:`carfinder.scrapers.base.BaseScraper` and
returns a list of :class:`carfinder.models.Listing`. All scrapers use
Playwright browser automation since none of these sources offer an official
public listings API.
"""
from carfinder.scrapers.base import BaseScraper
from carfinder.scrapers.facebook import FacebookMarketplaceScraper
from carfinder.scrapers.craigslist import CraigslistScraper
from carfinder.scrapers.cars_com import CarsComScraper
from carfinder.scrapers.autotrader import AutoTraderScraper
from carfinder.scrapers.cargurus import CarGurusScraper
from carfinder.scrapers.truecar import TrueCarScraper

SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "facebook": FacebookMarketplaceScraper,
    "craigslist": CraigslistScraper,
    "cars_com": CarsComScraper,
    "autotrader": AutoTraderScraper,
    "cargurus": CarGurusScraper,
    "truecar": TrueCarScraper,
}

__all__ = [
    "BaseScraper",
    "FacebookMarketplaceScraper",
    "CraigslistScraper",
    "CarsComScraper",
    "AutoTraderScraper",
    "CarGurusScraper",
    "TrueCarScraper",
    "SCRAPER_REGISTRY",
]
