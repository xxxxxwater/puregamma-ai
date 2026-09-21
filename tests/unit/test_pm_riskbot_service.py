from __future__ import annotations

import json
from pathlib import Path

from apps.api.services.pm_riskbot_service import (
    LATEST_SCHEMA,
    SERIES_SCHEMA,
    PmAccountReader,
)


def write_bundle(directory: Path, name: str, schema: str, payload: dict) -> None:
    (directory / name).write_text(json.dumps({"schema": schema, **payload}), encoding="utf-8")


def test_private_bundle_is_read_only_and_never_fabricates_missing_values(tmp_path: Path):
    reader = PmAccountReader(tmp_path)
    missing = reader.account_view()
    assert missing["available"] is False
    assert "account" not in missing

    write_bundle(
        tmp_path,
        "latest.json",
        LATEST_SCHEMA,
        {
            "snapshot": {"captured_at": "2026-09-21T00:00:00Z"},
            "collector": {"name": "riskbot", "read_only": True},
            "account": {"account_equity_usd": "12.34"},
            "balances": [],
        },
    )
    view = reader.account_view()
    assert view["available"] is True
    assert view["source"]["read_only"] is True
    assert view["account"]["account_equity_usd"] == "12.34"


def test_nav_history_is_observational_and_requires_real_points(tmp_path: Path):
    write_bundle(tmp_path, "series.json", SERIES_SCHEMA, {"points": [{"t": 1}]})
    history = PmAccountReader(tmp_path).nav_history_view()
    assert history["available"] is True
    assert history["points"] == [{"t": 1}]
    assert history["sufficient"] is False
