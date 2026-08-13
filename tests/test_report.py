from datetime import datetime

from carfinder.report import ReportRow, render_markdown_report
from carfinder.valuation import ValuationResult


def make_row(**kwargs):
    defaults = dict(
        title="2012 Honda Pilot EX-L",
        url="https://example.com/1",
        source="craigslist",
        price=15000,
        year=2012,
        mileage=95000,
        location="80301",
        is_new=False,
        previous_price=None,
        valuation=ValuationResult(
            sample_size=6, median_price=17500, percentile_rank=10.0,
            is_good_deal=True, note="Priced 14.3% below the median of 6 comparable listings ($17,500).",
        ),
    )
    defaults.update(kwargs)
    return ReportRow(**defaults)


def test_report_includes_summary_counts():
    rows = [make_row(), make_row(is_new=True, valuation=ValuationResult(
        sample_size=6, median_price=17500, percentile_rank=80.0, is_good_deal=False, note="x"
    ))]
    report = render_markdown_report(rows, "Honda", "Pilot", generated_at=datetime(2026, 8, 13))

    assert "New since last run: 1" in report
    assert "Flagged as good deals: 1" in report
    assert "Active listings: 2" in report


def test_report_flags_price_drop():
    rows = [make_row(price=13000, previous_price=15000)]
    report = render_markdown_report(rows, "Honda", "Pilot")
    assert "was $15,000" in report


def test_report_handles_no_listings():
    report = render_markdown_report([], "Honda", "Pilot")
    assert "Active listings: 0" in report
    assert "_None._" in report
