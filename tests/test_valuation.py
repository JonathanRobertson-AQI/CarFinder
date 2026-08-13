from carfinder.valuation import evaluate_listing


def test_no_price_cannot_be_evaluated():
    result = evaluate_listing(None, [10000, 12000, 14000])
    assert result.is_good_deal is False
    assert "No price" in result.note


def test_insufficient_sample_size_is_not_flagged():
    result = evaluate_listing(9000, [10000, 11000], min_sample_size=5)
    assert result.is_good_deal is False
    assert "comparable listing" in result.note


def test_low_priced_listing_flagged_as_good_deal():
    comparable = [15000, 16000, 17000, 18000, 19000, 20000]
    result = evaluate_listing(15000, comparable, min_sample_size=5, good_deal_percentile=25.0)
    assert result.is_good_deal is True
    assert result.median_price == 17500


def test_high_priced_listing_not_flagged():
    comparable = [15000, 16000, 17000, 18000, 19000, 20000]
    result = evaluate_listing(20000, comparable, min_sample_size=5, good_deal_percentile=25.0)
    assert result.is_good_deal is False
