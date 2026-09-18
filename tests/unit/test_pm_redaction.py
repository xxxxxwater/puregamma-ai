"""The redaction boundary must drop absolute scale and keep the shape.

The fixture below mirrors the real riskbot bundle field names (read off the
live export), including the detail that every figure arrives as a *string*.
"""
from __future__ import annotations

import pytest

from packages.decisions.redaction import (
    REDACTED_STATE_SCHEMA,
    assert_no_absolute_scale,
    book_shape,
    redact_account_view,
)


def _view(**overrides):
    """A realistic ``account_view()`` payload, sized to look like a real book."""
    view = {
        "available": True,
        "stale": False,
        "partial": False,
        "age_seconds": 12.5,
        "stale_after_seconds": 180.0,
        "source": {
            "collector": "riskbot",
            "read_only": True,
            "venue": "Binance Portfolio Margin (Classic)",
        },
        "account": {
            # Absolute -- must not survive.
            "account_equity_usd": "184230.55",
            "total_available_balance_usd": "90211.10",
            "virtual_max_withdraw_usd": "88120.00",
            "equity_btc_equivalent": "1.8423",
            "btc_price_usd": "99990.11",
            "adjusted_equity_usd": "184000.00",
            "valued_assets_usd": "190000.00",
            # Ratios and categories -- must survive.
            "account_status": "NORMAL",
            "uni_mmr": "0.0162",
            "uni_mmr_pct": "1.62",
            "uni_mmr_is_official": True,
            "maint_margin_usage_derived_pct": "31.4",
            "available_balance_ratio_derived": "0.49",
            "total_margin_open_loss_ratio_derived": "-0.0021",
            "gross_leverage_derived": "2.13",
            "derived_note": "free text",
        },
        "btc": {"quantity": "1.8423", "price_usd": "99990.11", "collateral_value_usd": "184230"},
        "exposure": {
            "gross_notional_usd": "392120.00",
            "gross_notional_btc_equivalent": "3.92",
            "net_notional_btc_equivalent": "0.41",
            "gross_leverage_derived": "2.13",
        },
        "balances": [
            {"asset": "BTC", "net_quantity": "1.8", "wallet_balance": "1.8",
             "value_usd": "180000", "is_liability": False},
            {"asset": "USDT", "net_quantity": "-4200", "wallet_balance": "0",
             "value_usd": "-4200", "is_liability": True},
        ],
        "positions": [
            {"symbol": "BTCUSDT", "side": "LONG", "quantity": "1.2",
             "base_quantity": "1.2", "quantity_unit": "BTC", "leverage": "3",
             "notional_usd": "120000", "signed_notional_usd": "120000",
             "notional_btc_equivalent": "1.2", "unrealized_pnl": "820.5",
             "entry_price": "95000", "mark_price": "100000",
             "liquidation_price": "61000", "has_liquidation_price": True,
             "initial_margin_usd": "40000", "adl_quantile": 2,
             "position_mode": "one-way"},
            {"symbol": "ETHUSDT", "side": "SHORT", "quantity": "-300",
             "base_quantity": "-300", "quantity_unit": "ETH", "leverage": "2",
             "notional_usd": "-60000", "signed_notional_usd": "-60000",
             "notional_btc_equivalent": "0.6", "unrealized_pnl": "-120.0",
             "entry_price": "4000", "mark_price": "3800",
             "has_liquidation_price": False, "adl_quantile": 1,
             "position_mode": "one-way"},
            {"symbol": "SOLUSDT", "side": "LONG", "quantity": "200",
             "base_quantity": "200", "quantity_unit": "SOL", "leverage": "1",
             "notional_usd": "20000", "signed_notional_usd": "20000",
             "has_liquidation_price": False, "position_mode": "one-way"},
        ],
        "positions_history": [
            {"symbol": "BTCUSDT", "side": "LONG", "kind": "opened",
             "qty_before": "0", "qty_after": "1.2", "notional_usd": "120000"},
            {"symbol": "ETHUSDT", "side": "SHORT", "kind": "opened",
             "qty_before": "0", "qty_after": "-300", "notional_usd": "-60000"},
            {"symbol": "SOLUSDT", "side": "LONG", "kind": "increased",
             "qty_before": "150", "qty_after": "200", "notional_usd": "20000"},
        ],
        "orders": [
            {"symbol": "BTCUSDT", "side": "SELL", "order_id": "8817263",
             "order_type": "LIMIT", "status": "NEW", "is_live": True,
             "is_protective": True, "quantity": "1.2", "price": "105000",
             "percent_from_mark": "5.0"},
            {"symbol": "ETHUSDT", "side": "BUY", "order_id": "8817264",
             "order_type": "STOP_MARKET", "status": "NEW", "is_live": True,
             "is_protective": False, "quantity": "300", "price": "4200",
             "percent_from_mark": "10.5"},
        ],
        "orders_meta": {"fully_covered": True, "age_seconds": 3.0,
                        "refresh_interval_seconds": 5},
        "protection": [
            {"symbol": "BTCUSDT", "side": "LONG", "position_quantity": "1.2",
             "protected_quantity": "1.2", "covered": True, "partial": False,
             "coverage_known": True, "reason": "stop order present", "stops": []},
        ],
        "risk": {
            "firing_count": 2,
            "firing": [
                {"rule": "drawdown_day", "level": "warn", "fingerprint": "ab12cd",
                 "value": "0.041", "status": "firing", "updated_at": "2026-09-18T09:00:00Z"},
                {"rule": "leverage_gross", "level": "info", "fingerprint": "ef34gh",
                 "value": "2.13", "status": "firing", "updated_at": "2026-09-18T09:00:00Z"},
            ],
            "drawdown_peak_btc_equivalent": "0.31",
            "drawdown_day_btc_equivalent": "0.041",
            "peak_equity_btc_equivalent": "2.10",
        },
        "coverage": {"essential_ok": True, "orders_covered": True,
                     "failures": [], "essential_failures": [],
                     "parts": {"account": "ok", "balance": "ok",
                               "cm_positions": "timeout", "um_orders": "ok"}},
        "quality": {"rest_ok": True, "ws_connected": True, "partial": False,
                    "mismatch": False, "consecutive_failures": 0,
                    "last_error": "https://api.binance.com/sapi/v1/... 418"},
        "disclaimer": "read-only",
    }
    view.update(overrides)
    return view


# --------------------------------------------------------------------------
# The boundary itself
# --------------------------------------------------------------------------

def test_output_is_scale_free_by_construction():
    """The whole point: nothing absolute survives, under the guard's own rules."""
    state = redact_account_view(_view())
    assert_no_absolute_scale(state)          # raises on any leak
    assert state["schema"] == REDACTED_STATE_SCHEMA


def test_guard_actually_catches_a_planted_leak():
    """A guard that cannot fail is not a guard -- prove it fires."""
    state = redact_account_view(_view())
    state["positions"][0]["notional_usd"] = "120000"
    with pytest.raises(AssertionError, match="notional_usd"):
        assert_no_absolute_scale(state)


def test_guard_tolerates_safe_names_that_look_absolute():
    """Booleans and unit strings share the vocabulary but carry no scale."""
    assert_no_absolute_scale({
        "has_liquidation_price": True,      # bool
        "quantity_unit": "BTC",             # not a number
        "percent_from_mark": "-2.5",        # contains no marker
    })


def test_absolute_account_figures_do_not_survive():
    state = redact_account_view(_view())
    margin = state["margin"]
    assert margin["uni_mmr_pct"] == "1.62"
    assert margin["gross_leverage_derived"] == "2.13"
    for leaked in ("account_equity_usd", "total_available_balance_usd",
                   "virtual_max_withdraw_usd", "equity_btc_equivalent",
                   "btc_price_usd", "valued_assets_usd"):
        assert leaked not in margin
    # The btc and exposure sections are dropped wholesale.
    assert "btc" not in state and "exposure" not in state


def test_position_keeps_shape_and_drops_size_and_prices():
    state = redact_account_view(_view())
    btc = state["positions"][0]
    assert btc["symbol"] == "BTCUSDT"
    assert btc["side"] == "LONG"
    assert btc["has_liquidation_price"] is True
    for leaked in ("quantity", "notional_usd", "signed_notional_usd",
                   "entry_price", "mark_price", "liquidation_price",
                   "unrealized_pnl", "initial_margin_usd", "max_notional_value"):
        assert leaked not in btc


def test_order_ids_and_sizes_are_dropped():
    state = redact_account_view(_view())
    order = state["orders"]
    assert order["count"] == 2
    assert order["live_count"] == 2
    assert order["protective_count"] == 1
    assert order["by_status"] == {"NEW": 2}
    assert order["symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert order["fully_covered"] is True


def test_risk_firing_keeps_categories_and_drops_measured_value():
    state = redact_account_view(_view())
    rules = state["risk"]["firing"]
    assert [r["rule"] for r in rules] == ["drawdown_day", "leverage_gross"]
    assert rules[0]["level"] == "warn"
    for entry in rules:
        assert "value" not in entry
        assert "fingerprint" not in entry


def test_last_error_is_reduced_to_presence():
    """The message carries upstream URLs; only its existence is published."""
    state = redact_account_view(_view())
    assert state["quality"]["last_error_present"] is True
    assert "last_error" not in state["quality"]
    assert "binance.com" not in str(state)


def test_coverage_reports_only_the_degraded_parts():
    state = redact_account_view(_view())
    assert state["coverage"]["degraded_parts"] == ["cm_positions"]
    assert state["coverage"]["essential_ok"] is True


# --------------------------------------------------------------------------
# Derived shape, computed locally from absolute inputs
# --------------------------------------------------------------------------

def test_book_shape_is_a_ratio_not_a_size():
    shape = book_shape(_view()["positions"])
    # 120k long, 60k short, 20k long -> gross 200k, net 80k
    assert shape["valued_position_count"] == 3
    assert shape["long_count"] == 2
    assert shape["short_count"] == 1
    assert shape["net_to_gross"] == pytest.approx(0.4)
    # (0.6^2 + 0.3^2 + 0.1^2) = 0.46
    assert shape["concentration_hhi"] == pytest.approx(0.46)


def test_book_shape_of_an_empty_book_is_none_not_zero():
    shape = book_shape([])
    assert shape["position_count"] == 0
    assert shape["concentration_hhi"] is None
    assert shape["net_to_gross"] is None


def test_unparseable_numbers_are_absent_never_zero():
    """Fail closed: a figure we cannot read must not be reported as 0."""
    shape = book_shape([{"signed_notional_usd": "n/a"}, {"signed_notional_usd": ""}])
    assert shape["valued_position_count"] == 0
    assert shape["net_to_gross"] is None


def test_activity_counts_events_without_sizes():
    activity = redact_account_view(_view())["activity"]
    assert activity["event_count"] == 3
    assert activity["by_kind"] == {"opened": 2, "increased": 1}
    assert activity["distinct_symbols"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


# --------------------------------------------------------------------------
# Fail closed
# --------------------------------------------------------------------------

def test_unavailable_bundle_yields_no_fabricated_numbers():
    state = redact_account_view({
        "available": False,
        "reason": "riskbot export bundle not found",
        "source": {"collector": "riskbot", "read_only": True},
    })
    assert state["freshness"]["available"] is False
    assert state["margin"] == {}
    assert state["positions"] == []
    assert state["book"]["concentration_hhi"] is None
    assert_no_absolute_scale(state)


def test_garbage_input_does_not_raise():
    """The redactor must never be the thing that takes the route down."""
    assert_no_absolute_scale(redact_account_view({}))          # type: ignore[arg-type]
    assert_no_absolute_scale(redact_account_view(None))        # type: ignore[arg-type]
    state = redact_account_view({"positions": "not-a-list", "account": 7})
    assert_no_absolute_scale(state)
    assert state["positions"] == []
