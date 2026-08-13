"""Valuation via comparable listings.

There's no free KBB API, so instead of scraping KBB (also ToS-restricted and
fragile), we estimate a fair-market price for each listing by comparing it
against the distribution of prices for comparable vehicles found across the
current batch of scraped listings (same make/model/year range). Listings
priced notably below that distribution are flagged as good deals.
"""
from __future__ import annotations

from dataclasses import dataclass
import statistics
from typing import Optional, Sequence


@dataclass
class ValuationResult:
    sample_size: int
    median_price: Optional[float]
    percentile_rank: Optional[float]  # where this listing's price sits, 0-100
    is_good_deal: bool
    note: str


def _percentile_rank(value: float, population: Sequence[float]) -> float:
    """Percentage of ``population`` at or below ``value`` (0-100)."""
    if not population:
        return 50.0
    count_below_or_equal = sum(1 for p in population if p <= value)
    return 100.0 * count_below_or_equal / len(population)


def evaluate_listing(
    price: Optional[float],
    comparable_prices: Sequence[float],
    min_sample_size: int = 5,
    good_deal_percentile: float = 25.0,
) -> ValuationResult:
    """Score a listing's price against comparable listings.

    ``comparable_prices`` should exclude the listing being evaluated when
    possible, but including it does not materially skew results once the
    sample is reasonably sized.
    """
    if price is None:
        return ValuationResult(
            sample_size=len(comparable_prices),
            median_price=None,
            percentile_rank=None,
            is_good_deal=False,
            note="No price listed; cannot evaluate.",
        )

    sample_size = len(comparable_prices)
    if sample_size < min_sample_size:
        return ValuationResult(
            sample_size=sample_size,
            median_price=(
                statistics.median(comparable_prices) if comparable_prices else None
            ),
            percentile_rank=None,
            is_good_deal=False,
            note=(
                f"Only {sample_size} comparable listing(s) found "
                f"(need {min_sample_size}+) to estimate value confidently."
            ),
        )

    median_price = statistics.median(comparable_prices)
    rank = _percentile_rank(price, comparable_prices)
    is_good_deal = rank <= good_deal_percentile

    diff = price - median_price
    pct_diff = (diff / median_price * 100) if median_price else 0.0
    direction = "below" if diff < 0 else "above"
    note = (
        f"Priced {abs(pct_diff):.1f}% {direction} the median of "
        f"{sample_size} comparable listings (${median_price:,.0f})."
    )

    return ValuationResult(
        sample_size=sample_size,
        median_price=median_price,
        percentile_rank=rank,
        is_good_deal=is_good_deal,
        note=note,
    )
