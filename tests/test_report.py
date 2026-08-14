from datetime import datetime

from carfinder.report import ReportRow, dedupe_rows, render_markdown_report
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


def test_dedupe_rows_collapses_same_listing_different_url():
    rows = [
        make_row(url="https://example.com/1", source="craigslist"),
        make_row(url="https://facebook.com/marketplace/item/2", source="facebook"),
    ]
    deduped = dedupe_rows(rows)
    assert len(deduped) == 1
    assert deduped[0].url == "https://example.com/1"


def test_dedupe_rows_is_case_and_whitespace_insensitive():
    rows = [
        make_row(url="https://example.com/1", title="  2012 Honda Pilot EX-L  "),
        make_row(url="https://example.com/2", title="2012 HONDA PILOT ex-l"),
    ]
    assert len(dedupe_rows(rows)) == 1


def test_dedupe_rows_keeps_distinct_listings():
    rows = [
        make_row(url="https://example.com/1", price=15000),
        make_row(url="https://example.com/2", price=16000),
    ]
    assert len(dedupe_rows(rows)) == 2


def test_dedupe_rows_merges_is_new_and_previous_price():
    rows = [
        make_row(url="https://example.com/1", is_new=False, previous_price=None),
        make_row(url="https://example.com/2", is_new=True, previous_price=14000),
    ]
    deduped = dedupe_rows(rows)
    assert len(deduped) == 1
    assert deduped[0].is_new is True
    assert deduped[0].previous_price == 14000
