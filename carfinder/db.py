"""SQLite persistence for tracking listings across runs.

Tracking previously-seen listings lets the daily report highlight what's new
since the last run and detect price drops on listings we've already seen.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from carfinder.models import Listing

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "carfinder.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    listing_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    price REAL,
    year INTEGER,
    make TEXT,
    model TEXT,
    trim TEXT,
    mileage INTEGER,
    location TEXT,
    vin TEXT,
    description TEXT,
    image_url TEXT,
    posted_at TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id TEXT NOT NULL,
    price REAL,
    observed_at TEXT NOT NULL,
    FOREIGN KEY (listing_id) REFERENCES listings (listing_id)
);

CREATE INDEX IF NOT EXISTS idx_listings_model_year
    ON listings (make, model, year);
"""


class ListingStore:
    """Wraps a SQLite database of tracked listings."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = str(db_path)
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        # busy_timeout + WAL let multiple concurrent searches (e.g. from
        # separate browser tabs) write to the shared DB without hitting
        # "database is locked" errors.
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        return conn

    def upsert(self, listing: Listing) -> tuple[bool, Optional[float]]:
        """Insert or update a listing.

        Returns a tuple of ``(is_new, previous_price)``. ``previous_price``
        is None for new listings, or the last-known price for existing ones
        (which lets the caller detect price drops).
        """
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT price FROM listings WHERE listing_id = ?",
                (listing.listing_id,),
            ).fetchone()
            is_new = row is None
            previous_price = row["price"] if row is not None else None

            if is_new:
                conn.execute(
                    """
                    INSERT INTO listings (
                        listing_id, source, url, title, price, year, make,
                        model, trim, mileage, location, vin, description,
                        image_url, posted_at, first_seen_at, last_seen_at,
                        active
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (
                        listing.listing_id, listing.source, listing.url,
                        listing.title, listing.price, listing.year,
                        listing.make, listing.model, listing.trim,
                        listing.mileage, listing.location, listing.vin,
                        listing.description, listing.image_url,
                        listing.posted_at, now, now,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE listings SET
                        title = ?, price = ?, mileage = ?, description = ?,
                        image_url = ?, last_seen_at = ?, active = 1
                    WHERE listing_id = ?
                    """,
                    (
                        listing.title, listing.price, listing.mileage,
                        listing.description, listing.image_url, now,
                        listing.listing_id,
                    ),
                )

            conn.execute(
                "INSERT INTO price_history (listing_id, price, observed_at) "
                "VALUES (?, ?, ?)",
                (listing.listing_id, listing.price, now),
            )
            conn.commit()
        return is_new, previous_price

    def mark_inactive_except(self, seen_ids: Iterable[str], source: str) -> int:
        """Mark listings from ``source`` not in ``seen_ids`` as inactive.

        Called after a full scrape of a source so listings that disappeared
        (sold/removed) stop showing up in the "active" report.
        """
        seen_ids = list(seen_ids)
        with closing(self._connect()) as conn:
            placeholders = ",".join("?" for _ in seen_ids)
            if seen_ids:
                query = (
                    f"UPDATE listings SET active = 0 "
                    f"WHERE source = ? AND listing_id NOT IN ({placeholders})"
                )
                cur = conn.execute(query, (source, *seen_ids))
            else:
                cur = conn.execute(
                    "UPDATE listings SET active = 0 WHERE source = ?",
                    (source,),
                )
            conn.commit()
            return cur.rowcount

    def active_listings(
        self, make: Optional[str] = None, model: Optional[str] = None
    ) -> list[sqlite3.Row]:
        with closing(self._connect()) as conn:
            query = "SELECT * FROM listings WHERE active = 1"
            params: list[str] = []
            if make:
                query += " AND make = ?"
                params.append(make)
            if model:
                query += " AND model = ?"
                params.append(model)
            query += " ORDER BY price ASC"
            return conn.execute(query, params).fetchall()

    def comparable_prices(
        self, make: str, model: str, year_min: int, year_max: int
    ) -> list[float]:
        """Prices of active comparable listings, for valuation."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT price FROM listings
                WHERE active = 1 AND make = ? AND model = ?
                  AND year BETWEEN ? AND ?
                  AND price IS NOT NULL
                """,
                (make, model, year_min, year_max),
            ).fetchall()
            return [r["price"] for r in rows]
