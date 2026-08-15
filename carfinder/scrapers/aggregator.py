"""Shared parsing for dealer/aggregator listing sites.

AutoTrader, CarGurus, and TrueCar expose different markup and periodically
enable bot protection. Their pages commonly contain schema.org vehicle JSON-LD,
so the parser prefers that stable representation and falls back to broad card
selectors when only rendered markup is available.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable
from urllib.parse import urljoin

from carfinder.models import Listing
from carfinder.scrapers.base import BaseScraper, parse_mileage, parse_posted_date, parse_price, parse_year

_DATE_FIELD_NAMES = ("datePosted", "datePublished", "dateCreated", "dateModified")
_CARD_SELECTORS = (
    "[data-testid*='vehicle']",
    "[data-testid*='listing']",
    "[data-qa*='vehicle']",
    "[data-qa*='listing']",
    "[data-cmp*='vehicle']",
    "article",
)
_DETAIL_HREF_RE = re.compile(
    r"/(?:vehicle|listing|cars-for-sale|inventory|vehicledetail)[^\"'?#\s]*",
    re.IGNORECASE,
)


def _as_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def _first_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list):
        for item in value:
            result = _first_string(item)
            if result:
                return result
    if isinstance(value, dict):
        for key in ("value", "name", "text", "@value"):
            result = _first_string(value.get(key))
            if result:
                return result
    return None


def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _jsonld_documents(script_texts: Iterable[str]) -> Iterable[dict[str, Any]]:
    for text in script_texts:
        try:
            parsed = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            continue
        yield from _walk_dicts(parsed)


def _is_vehicle_record(record: dict[str, Any], make: str, model: str) -> bool:
    record_type = record.get("@type", record.get("type"))
    types = {str(item).lower() for item in record_type} if isinstance(record_type, list) else {str(record_type).lower()}
    if types.intersection({"vehicle", "car"}):
        return True
    name = str(record.get("name", "")).lower()
    return bool(types.intersection({"product", "offer"}) and make.lower() in name and model.lower() in name)


def _date_value(record: dict[str, Any]) -> str | None:
    for field in _DATE_FIELD_NAMES:
        value = record.get(field)
        if not value:
            continue
        parsed = parse_posted_date(str(value))
        if parsed:
            return parsed
        match = re.match(r"(\d{4}-\d{2}-\d{2})", str(value))
        if match:
            return match.group(1)
    return None


def _record_to_listing(
    record: dict[str, Any],
    source_name: str,
    base_url: str,
    make: str,
    model: str,
) -> Listing | None:
    if not _is_vehicle_record(record, make, model):
        return None

    name = _first_string(record.get("name")) or f"{make} {model}"
    url = _first_string(record.get("url")) or ""
    if url:
        url = urljoin(base_url, url)
    if not url:
        return None

    offers = record.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price = _as_number(record.get("price")) or _as_number(offers.get("price"))
    mileage_data = record.get("mileageFromOdometer") or record.get("mileage")
    mileage = _as_number(mileage_data.get("value") if isinstance(mileage_data, dict) else mileage_data)
    year = record.get("modelDate") or record.get("vehicleModelDate") or parse_year(name)
    try:
        year = int(year) if year else None
    except (TypeError, ValueError):
        year = None
    brand = record.get("brand")
    record_make = _first_string(brand) or make
    record_model = _first_string(record.get("model")) or model
    address = record.get("address") or {}
    location = _first_string(address.get("addressLocality")) if isinstance(address, dict) else None

    return Listing(
        source=source_name,
        url=url,
        title=name,
        price=price,
        year=year,
        make=record_make,
        model=record_model,
        trim=_first_string(record.get("vehicleConfiguration")),
        mileage=int(mileage) if mileage is not None else None,
        location=location,
        vin=_first_string(record.get("vehicleIdentificationNumber")) or _first_string(record.get("sku")),
        posted_at=_date_value(record),
    )


def extract_jsonld_listings(
    script_texts: Iterable[str],
    source_name: str,
    base_url: str,
    make: str,
    model: str,
) -> list[Listing]:
    """Extract unique vehicle listings from schema.org JSON-LD scripts."""
    listings: list[Listing] = []
    seen: set[str] = set()
    for record in _jsonld_documents(script_texts):
        listing = _record_to_listing(record, source_name, base_url, make, model)
        if listing and listing.url not in seen:
            seen.add(listing.url)
            listings.append(listing)
    return listings


class AggregatorScraper(BaseScraper):
    """Base implementation for AutoTrader/CarGurus/TrueCar."""

    base_url = ""
    card_selectors = _CARD_SELECTORS

    def extract_listings(self, page) -> list[Listing]:
        scripts = page.locator("script[type='application/ld+json']").all_text_contents()
        listings = extract_jsonld_listings(
            scripts, self.source_name, self.base_url, self.config.make, self.config.model
        )
        if listings:
            return listings

        return self._extract_cards(page)

    def _extract_cards(self, page) -> list[Listing]:
        listings: list[Listing] = []
        seen: set[str] = set()
        for selector in self.card_selectors:
            for card in page.locator(selector).all()[:100]:
                try:
                    hrefs = card.locator("a[href]").evaluate_all(
                        "(els) => els.map((el) => el.href)"
                    )
                    url = next((href for href in hrefs if _DETAIL_HREF_RE.search(href)), None)
                    text = card.inner_text().strip()
                except Exception:
                    continue
                if not url or not text or url in seen:
                    continue
                title = self._card_title(card, text)
                if self.config.make.lower() not in text.lower() or self.config.model.lower() not in text.lower():
                    continue
                listing = Listing(
                    source=self.source_name,
                    url=url,
                    title=title,
                    price=parse_price(text),
                    year=parse_year(text),
                    make=self.config.make,
                    model=self.config.model,
                    mileage=parse_mileage(text),
                    location=self.config.location,
                    posted_at=self._card_date(text),
                )
                seen.add(url)
                listings.append(listing)
        return listings

    @staticmethod
    def _card_title(card, text: str) -> str:
        try:
            for selector in ("h2", "h3", "[data-testid*='title']", "[data-qa*='title']"):
                title = card.locator(selector).first.inner_text(timeout=1000).strip()
                if title:
                    return title
        except Exception:
            pass
        return text.splitlines()[0].strip()

    @staticmethod
    def _card_date(text: str) -> str | None:
        for line in text.splitlines():
            parsed = parse_posted_date(line)
            if parsed:
                return parsed
        return None
