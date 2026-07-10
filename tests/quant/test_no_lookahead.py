from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from packages.backtest.validation import LookAheadBiasError, assert_no_lookahead, has_lookahead


def test_feature_timestamp_after_decision_is_lookahead():
    decision = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    feature = decision + timedelta(minutes=1)
    assert has_lookahead(feature, decision)


def test_assert_no_lookahead_rejects_future_feature():
    decision = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    with pytest.raises(LookAheadBiasError):
        assert_no_lookahead(
            [
                {
                    "feature_timestamp": decision + timedelta(seconds=1),
                    "decision_timestamp": decision,
                }
            ]
        )


def test_assert_no_lookahead_accepts_bar_close_available_before_decision():
    decision = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    assert_no_lookahead(
        [
            {
                "feature_timestamp": decision - timedelta(seconds=1),
                "decision_timestamp": decision,
            }
        ]
    )
