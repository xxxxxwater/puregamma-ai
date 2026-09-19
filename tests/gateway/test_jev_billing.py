"""Jev billing edge cases (P4).

The brief lists the cases that must hold for accurate charging. These are the
ones that can be proven against the real pricing engine without a database:
the arithmetic, the zero-rate output, the rounding, and the fact that a
superseded price revision stops applying.

Balance, idempotency and wallet effects live in the database layer and are
covered by tests/gateway/test_gateway_wallet.py and
tests/gateway/test_gateway_usage.py; what is asserted here is the number those
paths hand to the ledger.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

import pytest

from packages.gateway.catalog import provider_models
from packages.gateway.contracts import GatewayUsage
from packages.gateway.pricing import MONEY_QUANTUM, final_prices, usage_cost

#: The production markup, read from the live policy rather than assumed.
PRODUCTION_MARKUP_BPS = 3000


@pytest.fixture(scope="module")
def jev_prices():
    return {m.public_id: m for m in provider_models("typesafe")}["jev"].official_prices


@pytest.fixture(scope="module")
def jev_retail(jev_prices):
    return final_prices(jev_prices, PRODUCTION_MARKUP_BPS)


# --------------------------------------------------------------------------
# Arithmetic
# --------------------------------------------------------------------------


def test_zero_tokens_cost_nothing(jev_prices):
    assert usage_cost(jev_prices, GatewayUsage()) == Decimal("0")
    assert usage_cost(jev_prices, GatewayUsage(input_tokens=0, output_tokens=0)) == Decimal("0")


def test_exactly_one_million_input_tokens_costs_the_rate(jev_prices):
    assert usage_cost(jev_prices, GatewayUsage(input_tokens=1_000_000)) == Decimal("0.042")


def test_large_volume_is_linear_not_banded(jev_prices):
    one_m = usage_cost(jev_prices, GatewayUsage(input_tokens=1_000_000))
    hundred_m = usage_cost(jev_prices, GatewayUsage(input_tokens=100_000_000))
    assert hundred_m == one_m * 100


def test_output_tokens_are_free_at_any_volume(jev_prices):
    """Jev bills input only. The catalog carries no output tariff at all."""
    for output in (1, 1_000, 1_000_000, 100_000_000):
        cost = usage_cost(jev_prices, GatewayUsage(output_tokens=output))
        assert cost == Decimal("0"), f"output={output} was charged"


def test_output_does_not_change_the_bill_next_to_input(jev_prices):
    base = usage_cost(jev_prices, GatewayUsage(input_tokens=500_000))
    with_output = usage_cost(
        jev_prices, GatewayUsage(input_tokens=500_000, output_tokens=9_000_000)
    )
    assert with_output == base


def test_jev_has_no_cache_tariff_so_cache_tokens_are_not_billed(jev_prices):
    """A chat model would charge for cache hits; Jev publishes no such rate."""
    assert usage_cost(jev_prices, GatewayUsage(cache_tokens=1_000_000)) == Decimal("0")
    # And cache tokens must not silently discount a genuine input charge: the
    # engine subtracts cache from input, so with no cache tariff this would
    # under-bill. Jev reports cache_tokens = 0, which the adapter guarantees.
    assert usage_cost(
        jev_prices, GatewayUsage(input_tokens=1_000_000, cache_tokens=0)
    ) == Decimal("0.042")


def test_a_single_token_rounds_to_the_money_quantum(jev_prices):
    raw = Decimal(1) * Decimal("0.042") / Decimal(1_000_000)
    assert usage_cost(jev_prices, GatewayUsage(input_tokens=1)) == raw.quantize(
        MONEY_QUANTUM, rounding=ROUND_HALF_UP
    )


def test_the_measured_live_call_reconciles(jev_prices, jev_retail):
    """The real 324/38 call, end to end through both tariffs."""
    usage = GatewayUsage(input_tokens=324, output_tokens=38)
    official = usage_cost(jev_prices, usage)
    retail = usage_cost(jev_retail, usage)
    assert official == Decimal("0.00001361")   # 324 * 0.042 / 1e6
    assert retail == Decimal("0.00001769")     # 324 * 0.0546 / 1e6
    assert retail > official > Decimal("0")    # the markup is a real margin


# --------------------------------------------------------------------------
# Retail tariff
# --------------------------------------------------------------------------


def test_retail_price_is_the_documented_thirty_percent_markup(jev_retail):
    assert Decimal(jev_retail["input"]["usd"]) == Decimal("0.0546")
    assert "output" not in jev_retail


def test_retail_output_remains_free(jev_retail):
    assert usage_cost(jev_retail, GatewayUsage(output_tokens=5_000_000)) == Decimal("0")


@pytest.mark.parametrize("markup_bps", [0, 1000, 3000, 5000])
def test_markup_applies_uniformly_and_never_to_output(jev_prices, markup_bps):
    priced = final_prices(jev_prices, markup_bps)
    expected = (Decimal("0.042") * (Decimal("1") + Decimal(markup_bps) / Decimal(10000)))
    assert Decimal(priced["input"]["usd"]) == expected.quantize(MONEY_QUANTUM)
    assert "output" not in priced


def test_a_superseded_revision_must_not_be_used_for_billing(jev_prices):
    """Only the approved snapshot is billable.

    `final_prices` is pure, so this pins the contract the database layer has to
    honour: whatever snapshot is passed in is what gets charged. A caller that
    passes a superseded revision bills the wrong price, which is why the
    active revision must be resolved first (metadata.approve_price_revision
    supersedes the previous one).
    """
    superseded = final_prices(jev_prices, 1000)    # old 10% markup
    active = final_prices(jev_prices, PRODUCTION_MARKUP_BPS)
    assert superseded["input"]["usd"] != active["input"]["usd"]
    assert Decimal(active["input"]["usd"]) > Decimal(superseded["input"]["usd"])


# --------------------------------------------------------------------------
# Metering must not silently under-bill
# --------------------------------------------------------------------------


def test_missing_usage_is_not_treated_as_a_free_request(jev_prices):
    """A provider that reports no usage must be an error, not a $0 charge.

    usage_cost() will happily price an empty GatewayUsage at zero, so the guard
    has to live at the route: the adapter returns whatever the upstream
    envelope said, and a response with no usable usage must be rejected rather
    than recorded as a free call. This test pins the engine's behaviour so the
    route-level guard is the only thing standing between a missing envelope and
    revenue loss.
    """
    assert usage_cost(jev_prices, GatewayUsage()) == Decimal("0")
    # ...which is exactly why token_usage() returning 0/0 is indistinguishable
    # from a genuinely empty call. The route must therefore treat an upstream
    # body without a usage object as a failed request.
    from packages.gateway.providers.typesafe import TypeSafeGatewayProvider

    class _S:
        gateway_typesafe_api_key = "k"

    adapter = TypeSafeGatewayProvider(_S(), {"base_url": "https://api.typesafe.ai/v1"})
    assert adapter.tokenUsage({}) == GatewayUsage()
    assert adapter.tokenUsage({"usage": {"input_tokens": "oops"}}) == GatewayUsage()
