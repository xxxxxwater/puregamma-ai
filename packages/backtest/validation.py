from __future__ import annotations

from datetime import datetime
from typing import Iterable, Mapping


class LookAheadBiasError(ValueError):
    pass


def has_lookahead(feature_timestamp: datetime, decision_timestamp: datetime) -> bool:
    return feature_timestamp > decision_timestamp


def assert_no_lookahead(records: Iterable[Mapping[str, datetime]]) -> None:
    for index, record in enumerate(records):
        feature_timestamp = record["feature_timestamp"]
        decision_timestamp = record["decision_timestamp"]
        if has_lookahead(feature_timestamp, decision_timestamp):
            raise LookAheadBiasError(f"Record {index} uses feature data after the decision timestamp.")
