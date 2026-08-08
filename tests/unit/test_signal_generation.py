from __future__ import annotations

from apps.api.services.signal_service import scan_signals, serialize_signal


def test_signal_contains_required_research_fields(db):
    signal = scan_signals(db, ["BTC"])[0]
    payload = serialize_signal(signal)

    assert payload["thesis"]
    assert payload["catalyst"]
    assert payload["invalidation"]
    assert payload["timeframe"]


def test_signal_confidence_and_risk_are_bounded(db):
    signals = scan_signals(db, ["BTC", "ETH", "SOL"])

    assert all(0 <= signal.confidence <= 1 for signal in signals)
    assert all(0 <= signal.risk_score <= 100 for signal in signals)
