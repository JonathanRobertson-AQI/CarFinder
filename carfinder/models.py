"""Shared data model for a scraped vehicle listing."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
from typing import Any, Optional


@dataclass
class Listing:
    """A single vehicle-for-sale listing scraped from a source.

    ``listing_id`` is a stable identifier derived from the source and the
    source's native listing URL/ID, so the same real-world listing is
    recognized across repeated scrapes even if incidental fields (like the
    scraped price, in case of a price drop) change.
    """

    source: str
    url: str
    title: str
    price: Optional[float]
    year: Optional[int]
    make: Optional[str]
    model: Optional[str]
    trim: Optional[str] = None
    mileage: Optional[int] = None
    location: Optional[str] = None
    vin: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    posted_at: Optional[str] = None
    scraped_at: str = ""
    listing_id: str = ""

    def __post_init__(self) -> None:
        if not self.scraped_at:
            self.scraped_at = datetime.now(timezone.utc).isoformat()
        if not self.listing_id:
            self.listing_id = self.compute_id()

    def compute_id(self) -> str:
        basis = f"{self.source}:{self.url}".encode("utf-8")
        return hashlib.sha256(basis).hexdigest()[:24]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
