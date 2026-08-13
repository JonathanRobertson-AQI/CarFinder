"""Daily report generation.

Produces a self-contained Markdown report summarizing active listings,
highlighting new listings since the last run, price drops, and good deals
(per the comparable-pricing valuation).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from carfinder.valuation import ValuationResult


@dataclass
class ReportRow:
    title: str
    url: str
    source: str
    price: Optional[float]
    year: Optional[int]
    mileage: Optional[int]
    location: Optional[str]
    is_new: bool
    previous_price: Optional[float]
    valuation: ValuationResult


def _fmt_price(price: Optional[float]) -> str:
    return f"${price:,.0f}" if price is not None else "N/A"


def _fmt_mileage(mileage: Optional[int]) -> str:
    return f"{mileage:,} mi" if mileage is not None else "N/A"


def render_markdown_report(
    rows: list[ReportRow],
    make: str,
    model: str,
    generated_at: Optional[datetime] = None,
) -> str:
    generated_at = generated_at or datetime.now()
    lines: list[str] = []
    lines.append(f"# {make} {model} Listings Report")
    lines.append("")
    lines.append(f"Generated: {generated_at.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Active listings: {len(rows)}")

    new_rows = [r for r in rows if r.is_new]
    deal_rows = [r for r in rows if r.valuation.is_good_deal]
    price_drop_rows = [
        r for r in rows
        if r.previous_price is not None
        and r.price is not None
        and r.price < r.previous_price
    ]

    lines.append(f"New since last run: {len(new_rows)}")
    lines.append(f"Flagged as good deals: {len(deal_rows)}")
    lines.append(f"Price drops: {len(price_drop_rows)}")
    lines.append("")

    def render_section(title: str, section_rows: list[ReportRow]) -> None:
        lines.append(f"## {title}")
        lines.append("")
        if not section_rows:
            lines.append("_None._")
            lines.append("")
            return
        lines.append(
            "| Year | Price | Mileage | Source | Deal Note | Link |"
        )
        lines.append("|---|---|---|---|---|---|")
        for r in section_rows:
            price_cell = _fmt_price(r.price)
            if r.previous_price is not None and r.price is not None and r.price != r.previous_price:
                price_cell += f" (was {_fmt_price(r.previous_price)})"
            flag = "🆕 " if r.is_new else ""
            flag += "💰 " if r.valuation.is_good_deal else ""
            lines.append(
                f"| {r.year or 'N/A'} | {flag}{price_cell} | {_fmt_mileage(r.mileage)} "
                f"| {r.source} | {r.valuation.note} | [{r.title}]({r.url}) |"
            )
        lines.append("")

    render_section("🆕 New Listings", new_rows)
    render_section("💰 Good Deals", deal_rows)
    render_section("All Active Listings", rows)

    return "\n".join(lines)


def write_report(
    rows: list[ReportRow],
    make: str,
    model: str,
    output_dir: str | Path = "reports",
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{datetime.now().strftime('%Y-%m-%d')}_{make}_{model}.md".replace(" ", "_")
    path = output_dir / filename
    path.write_text(render_markdown_report(rows, make, model), encoding="utf-8")
    return path
