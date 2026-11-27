from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from packages.gateway.pricing import final_prices
from packages.gateway.time_prices import deepseek_peak, effective_prices


@pytest.mark.parametrize("hour,expected", [(0, False), (1, True), (4, False), (6, True), (10, False)])
def test_weekday_tariff_boundaries(hour, expected):
    assert deepseek_peak(datetime(2026, 11, 27, hour, tzinfo=timezone.utc)) is expected


@pytest.mark.parametrize("month,day", [(10, 1), (11, 28)])
def test_holiday_and_weekend_use_off_peak(month, day):
    assert not deepseek_peak(datetime(2026, month, day, 2, tzinfo=timezone.utc))


@pytest.mark.parametrize("peak", [False, True])
def test_quote_and_reservation_at_half_price(peak):
    official = {"input": {"usd": "0.15", "unit": "per_million_tokens"}}
    revision = SimpleNamespace(
        source_reference="https://api-docs.deepseek.com/quick_start/pricing/",
        official_prices_json=official,
        final_prices_json=final_prices(official, -5000),
    )
    retail = Decimal(effective_prices(revision, retail=True, peak=peak)["input"]["usd"])
    upstream = Decimal(effective_prices(revision, retail=False, peak=peak)["input"]["usd"])
    ceiling = Decimal(effective_prices(revision, retail=True, maximum=True)["input"]["usd"])
    assert retail == upstream / 2
    assert ceiling == Decimal("0.15")
    assert ceiling >= retail
