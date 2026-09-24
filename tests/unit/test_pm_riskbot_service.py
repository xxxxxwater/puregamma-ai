from __future__ import annotations

import json
import time
from pathlib import Path

from apps.api.services.pm_riskbot_service import (
    LATEST_SCHEMA,
    SERIES_SCHEMA,
    SERIES_STALE_AFTER_SECONDS,
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


def test_nav_history_reports_the_newest_observation_not_the_file_mtime(tmp_path: Path):
    """A freshly written bundle must not make a frozen curve look current.

    Regression: series.json was regenerated every 30s while its points stopped
    days earlier, because the collector's query returned the OLDEST rows of the
    window.  The page then drew a stale amount scale under a live headline.
    """
    now = time.time()
    write_bundle(
        tmp_path,
        "series.json",
        SERIES_SCHEMA,
        {
            "generated_at": "2026-09-24T00:00:00Z",
            "first_point_at": "2026-09-16T10:54:48Z",
            "points": [{"t": now - 7 * 86400}, {"t": now - 6 * 86400}],
        },
    )
    history = PmAccountReader(tmp_path).nav_history_view()
    assert history["available"] is True
    assert history["sufficient"] is True
    assert history["stale"] is True
    assert history["age_seconds"] > 5 * 86400
    assert history["stale_after_seconds"] == SERIES_STALE_AFTER_SECONDS
    assert history["latest_point_at"] == time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 6 * 86400)
    )


def test_nav_history_is_current_when_the_newest_point_is_fresh(tmp_path: Path):
    now = time.time()
    write_bundle(
        tmp_path,
        "series.json",
        SERIES_SCHEMA,
        {"points": [{"t": now - 60}, {"t": now - 30}]},
    )
    history = PmAccountReader(tmp_path).nav_history_view()
    assert history["stale"] is False
    assert history["age_seconds"] < 120
