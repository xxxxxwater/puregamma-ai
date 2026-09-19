"""Jev Trader ingestion: schema adaptation, dedup and boundedness.

Fixtures here are copied from real responses captured during the P1 audit and
the live verification run, because the whole point of this module is that the
upstream's actual shape is not what its source code says. In particular the
audit recorded `totals` as a positional array; the live feed sends an object
with named keys. Both are covered so a future upstream switch neither breaks
parsing nor silently relabels a statistic.
"""
from __future__ import annotations

import pytest

from apps.api.services.jev_trader_service import (
    EVENT_BUFFER_SIZE,
    TOTALS_FIELDS,
    JevTraderIngestion,
    event_fingerprint,
    normalize_event,
    normalize_totals,
)

#: Verbatim from GET https://jev-trader-production.up.railway.app/ (2026-09-19).
LIVE_TOTALS = {
    "blocks": 582955,
    "decisions": 531259,
    "trades": 531259,
    "lateBlocks": 46675,
    "jevUsd": 32.74864,
    "gasMon": 0,
    "gasUsd": 0,
    "realizedUsd": -558.1296,
    "pnlUsd": -558.1326,
    "pnlMon": -22653.3241,
    "pnlPct": -1162.776,
}

LIVE_EVENT = {
    "block": 106064772,
    "ts": 1789785071685,
    "mid": 0.024621999999999998,
    "bestBid": 0.024621,
    "bestAsk": 0.024623,
    "spreadBps": 3.25,
    "decision": {
        "action": "buy",
        "probabilities": {"buy": 0.73, "sell": 0.27, "hold": 0.0},
        "upIn10": 0.73,
        "latencyMs": 119,
        "late": False,
    },
    "fill": {
        "side": "buy",
        "size": 200,
        "price": 0.024626,
        "simulated": True,
        "txHash": None,
        "gasMon": 0,
    },
    "position": {"size": 200},
    "totals": LIVE_TOTALS,
}


# --------------------------------------------------------------------------
# Totals: the live shape is an object, not the array the audit recorded
# --------------------------------------------------------------------------


def test_live_object_totals_are_named_by_key():
    result = normalize_totals(LIVE_TOTALS)
    assert result["schema_mismatch"] is False
    assert result["length"] == 11
    assert result["fields"]["decisions"] == 531259
    assert result["fields"]["late_blocks"] == 46675
    assert result["fields"]["jev_usd"] == 32.74864
    assert result["missing_keys"] == []
    assert result["unknown_keys"] == []


def test_object_totals_survive_a_reordered_or_extended_upstream():
    """Named keys cannot suffer index drift, which is the whole reason to
    prefer them over the array form."""
    reordered = dict(reversed(list(LIVE_TOTALS.items())))
    reordered["newMetric"] = 1
    result = normalize_totals(reordered)
    assert result["fields"]["decisions"] == 531259
    assert result["unknown_keys"] == ["newMetric"]
    assert result["schema_mismatch"] is False


def test_object_totals_report_missing_keys_without_failing():
    partial = {"blocks": 10, "decisions": 9}
    result = normalize_totals(partial)
    assert result["fields"] == {"blocks": 10, "decisions": 9}
    assert "jevUsd" in result["missing_keys"]
    assert result["schema_mismatch"] is False


def test_positional_totals_still_parse_at_the_audited_length():
    result = normalize_totals(list(range(len(TOTALS_FIELDS))))
    assert result["schema_mismatch"] is False
    assert result["fields"]["blocks"] == 0


def test_a_shifted_array_is_refused_rather_than_relabelled():
    """The failure this guards: a reordered array would silently rename every
    statistic and the page would show wrong numbers with no error."""
    short = list(range(len(TOTALS_FIELDS) - 1))
    result = normalize_totals(short)
    assert result["schema_mismatch"] is True
    assert result["fields"] == {}


def test_non_totals_payloads_do_not_raise():
    assert normalize_totals(None)["schema_mismatch"] is False
    assert normalize_totals("nope")["schema_mismatch"] is True
    assert normalize_totals(42)["schema_mismatch"] is True


# --------------------------------------------------------------------------
# Event normalisation
# --------------------------------------------------------------------------


def test_live_event_normalises_to_the_published_shape():
    event = normalize_event(LIVE_EVENT)
    assert event is not None
    assert event["block"] == 106064772
    # Approx: the upstream sends 0.024621999999999998 for what is 0.024622.
    assert event["mid"] == pytest.approx(0.024622)
    assert event["best_bid"] == pytest.approx(0.024621)
    assert event["spread_bps"] == pytest.approx(3.25)
    assert event["decision"]["action"] == "buy"
    assert event["decision"]["latency_ms"] == 119
    assert event["decision"]["late"] is False
    # Evidence that no real trade happened travels with the event.
    assert event["fill"]["simulated"] is True
    assert event["fill"]["tx_hash"] is None


def test_probabilities_are_not_assumed_complete_or_normalised():
    raw = {**LIVE_EVENT, "decision": {"action": "buy", "probabilities": {"buy": 0.6}, "late": False}}
    event = normalize_event(raw)
    assert event is not None
    assert event["decision"]["probabilities"] == {"buy": 0.6}


def test_missing_fields_stay_absent_and_never_become_zero():
    event = normalize_event({"block": 5})
    assert event is not None
    assert event["mid"] is None
    assert event["spread_bps"] is None
    assert event["decision"]["latency_ms"] is None
    assert event["fill"] is None
    assert event["decision"]["probabilities"] == {}


def test_events_without_a_block_are_dropped():
    assert normalize_event({"mid": 1.0}) is None
    assert normalize_event({"block": "not-a-number"}) is None
    assert normalize_event("nope") is None
    assert normalize_event(None) is None


def test_late_decisions_are_preserved_as_such():
    raw = {**LIVE_EVENT, "decision": {**LIVE_EVENT["decision"], "late": True, "action": "hold"}}
    event = normalize_event(raw)
    assert event is not None
    assert event["decision"]["late"] is True


# --------------------------------------------------------------------------
# Identity and boundedness
# --------------------------------------------------------------------------


def test_fingerprint_is_stable_and_distinguishes_same_timestamp_events():
    a = normalize_event(LIVE_EVENT)
    b = normalize_event({**LIVE_EVENT, "decision": {**LIVE_EVENT["decision"], "action": "sell"}})
    c = normalize_event({**LIVE_EVENT, "block": 999})
    assert a and b and c
    # Same ts and block but a different action must NOT collide.
    assert event_fingerprint(a) != event_fingerprint(b)
    assert event_fingerprint(a) != event_fingerprint(c)
    assert event_fingerprint(a) == event_fingerprint(normalize_event(LIVE_EVENT))


class _NoNetwork(JevTraderIngestion):
    def start(self) -> None:      # never open a socket in tests
        self._connection = "test"


def test_duplicate_events_are_ingested_once():
    ing = _NoNetwork("https://example.invalid")
    ing._apply_block_obj(LIVE_EVENT)
    ing._apply_block_obj(LIVE_EVENT)
    ing._apply_block_obj(LIVE_EVENT)
    assert ing.snapshot()["buffer_size"] == 1
    assert ing.live_seq() == 1


def test_buffer_is_bounded_and_sequences_stay_monotonic():
    ing = _NoNetwork("https://example.invalid")
    for i in range(EVENT_BUFFER_SIZE + 250):
        ing._apply_block_obj({**LIVE_EVENT, "block": 1_000_000 + i})
    snapshot = ing.snapshot()
    assert snapshot["buffer_size"] == EVENT_BUFFER_SIZE
    assert snapshot["event_buffer_limit"] == EVENT_BUFFER_SIZE
    assert snapshot["seq"] == EVENT_BUFFER_SIZE + 250


def test_replay_reports_when_a_cursor_has_rolled_out_of_the_buffer():
    ing = _NoNetwork("https://example.invalid")
    for i in range(EVENT_BUFFER_SIZE + 10):
        ing._apply_block_obj({**LIVE_EVENT, "block": 2_000_000 + i})
    # A cursor from before the window cannot be served honestly.
    events, covered = ing.replay_from(0)
    assert covered is False
    assert events == []
    # A recent cursor is served.
    events, covered = ing.replay_from(ing.live_seq() - 5)
    assert covered is True
    assert len(events) == 5


def test_totals_survive_an_event_that_lacks_them():
    """A later event with no totals must not erase the last known snapshot."""
    ing = _NoNetwork("https://example.invalid")
    ing._apply_block_obj(LIVE_EVENT)
    assert ing.snapshot()["totals"]["fields"]["decisions"] == 531259
    ing._apply_block_obj({"block": 999, "ts": 1})
    assert ing.snapshot()["totals"]["fields"]["decisions"] == 531259


def test_schema_mismatch_is_flagged_and_not_hidden():
    ing = _NoNetwork("https://example.invalid")
    ing._apply_block_obj({**LIVE_EVENT, "totals": [1, 2, 3]})
    assert ing.status()["schema_mismatch"] is True
