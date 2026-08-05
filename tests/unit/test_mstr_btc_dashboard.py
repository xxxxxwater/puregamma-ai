"""Contract tests for the MSTR/BTC opportunity dashboard pipeline."""
from __future__ import annotations

import pytest

from apps.api.services import mstr_btc_service


@pytest.fixture()
def recorded_pack() -> dict:
    """Recorded shape of the real strategy.com payloads (2026-07-24).

    Market timestamps are generated relative to *now* because the service
    marks data older than 30 minutes as delayed.
    """
    from datetime import datetime, timedelta, timezone

    recent = datetime.now(timezone.utc) - timedelta(minutes=2)
    market_ts = recent.strftime("%Y-%m-%dT%H:%M:%S")
    return {
        "fetched_at": recent.isoformat(),
        "errors": [],
        "kpis_timestamp": market_ts,
        "kpis": {
            "ufPrice": 63942.25,
            "latestPrice": 63942,
            "priceVarPerc": "-2.24",
            "mNav": 1.0016,
            "mNavVarPerc": "-0.32",
            "btcNavNumber": 53953,
            "netBtcReserve": 34999663593.75,
            "netBtcPerShareUsd": 91.3307,
            "netBtcPerShareUsdVarPerc": "-3.41",
            "btcPerShareUsd": 131.969,
            "satsPerShare": 206387.7406,
            "netSatsPerShare": 142833.1199,
            "totalAnnualDividends": 1762796824.5,
            "btcYearsOfDividends": 30.606404120936173,
            "usdMonthsOfDividends": 21.953749554193166,
            "drawdownFromAth": -49.3,
            "amplification": 1.5415,
            "totalDuration": 5.807,
            "bitcoinHurdleArr": 10.791,
            "timestamp": "2026-07-24T14:59:00",
        },
        "mstr": {
            "company": "MSTR",
            "ufPrice": 91.3905,
            "priceVarPerc": "-2.39",
            "marketCap": "34,652",
            "marketCapVarPerc": "-2.39",
            "entVal": "53,645",
            "entValPerc": "-1.56",
            "debt": "6,754",
            "pref": "15,464",
            "oneYear": "-78",
            "bseAnnualized": 40,
            "timeStampUtc": "2026-07-24T14:59:00",
        },
        "options": {"impliedVolatility": 86, "totalOi": "23,332", "putCallRatio": "0.96"},
        "tracker": {
            "latest": {
                "as_of_date": "2026-07-20",
                "title": "July 20, 2026 Statistics",
                "btc_holdings": 843775,
                "debt": 6754000000,
                "pref": 15464458400,
                "cash": 3225000000,
                "basic_shares_outstanding": 379160000,
                "shares": {"convert_2028": 5513000, "convert_2029": 2231000, "options_outstanding": 3171000, "rsu_psu_unvested": 888000},
                "debt_years": 3.7,
                "btc_yield_ytd": 5.8,
                "btc_gain_ytd": 39325,
            },
            "previous": {"as_of_date": "2026-05-11", "btc_holdings": 818869},
            "tooltips": {"MSTR Price": "The latest traded price of MSTR.", "mNAV": "MSTR Price, divided by Net Bitcoin Per Share ($)."},
        },
    }


def _metric(dashboard: dict, metric_id: str) -> dict:
    return next(m for m in dashboard["metrics"] if m["id"] == metric_id)


def test_unavailable_contract_when_all_sources_fail(monkeypatch):
    monkeypatch.setattr(mstr_btc_service, "fetch_fact_pack", lambda: {"fetched_at": None, "errors": ["bitcoinKpis:Timeout"], "kpis": None, "mstr": None, "tracker": None})
    dashboard = mstr_btc_service.get_dashboard("en")
    assert dashboard["sourceStatus"] == "unavailable"
    assert dashboard["unavailable"] is True
    assert dashboard["error_code"] == "SOURCE_UNAVAILABLE"
    assert dashboard["metrics"] == []
    assert dashboard["research"] is None
    assert dashboard["notes"]


def test_live_contract_from_recorded_pack(monkeypatch, recorded_pack):
    monkeypatch.setattr(mstr_btc_service, "refresh_fact_pack", lambda: recorded_pack)
    dashboard = mstr_btc_service.get_dashboard("en")
    assert dashboard["sourceStatus"] == "live"
    assert dashboard["asOf"] == recorded_pack["kpis_timestamp"] + "+00:00"
    ids = {m["id"] for m in dashboard["metrics"]}
    for expected in ("mstr_price", "btc_price", "mnav", "market_cap", "enterprise_value", "total_btc_reserves", "total_debt", "preferred_equity", "diluted_shares", "btc_yield", "breakeven", "downside_buffer"):
        assert expected in ids, expected
    assert _metric(dashboard, "mnav")["formattedValue"] == "1.0016"
    assert _metric(dashboard, "mstr_price")["change24h"] == -2.39
    assert _metric(dashboard, "total_btc_reserves")["value"] == 843775
    # diluted = basic + converts + options + RSU
    assert _metric(dashboard, "diluted_shares")["value"] == 379160000 + 5513000 + 2231000 + 3171000 + 888000
    # breakeven = (debt + pref - cash) / holdings
    expected_breakeven = (6754000000 + 15464458400 - 3225000000) / 843775
    assert _metric(dashboard, "breakeven")["value"] == pytest.approx(expected_breakeven, rel=1e-6)
    # earnings must never be fabricated
    assert _metric(dashboard, "earnings")["status"] == "unavailable"
    assert _metric(dashboard, "earnings")["value"] is None
    assert _metric(dashboard, "estimated_earnings_impact")["status"] == "unavailable"
    # every metric carries provenance
    for metric in dashboard["metrics"]:
        assert metric["sourceUrl"]
        assert metric["status"] in {"live", "delayed", "unavailable"}
        if metric["status"] != "unavailable":
            assert metric["asOf"]
            assert metric["formattedValue"]
    scenario_ids = {s["id"] for s in dashboard["scenarios"]}
    assert {"mnav_parity", "balance_sheet_floor", "dilution_schedule", "coverage_stress"} <= scenario_ids
    research = dashboard["research"]
    assert research["conclusion"]
    assert research["bullCase"] and research["baseCase"] and research["bearCase"]
    assert research["citations"]
    assert 0 < research["confidence"] <= 1


def test_zh_locale_labels_and_research(monkeypatch, recorded_pack):
    monkeypatch.setattr(mstr_btc_service, "refresh_fact_pack", lambda: recorded_pack)
    dashboard = mstr_btc_service.get_dashboard("zh")
    assert _metric(dashboard, "mstr_price")["label"] == "MSTR 价格"
    assert _metric(dashboard, "total_btc_reserves")["label"] == "BTC 持仓量"
    assert "mNAV" in dashboard["research"]["conclusion"]
    assert _metric(dashboard, "mnav")["definition"]


def test_partial_pack_marks_market_metrics_unavailable(monkeypatch, recorded_pack):
    partial = dict(recorded_pack)
    partial["kpis"] = None
    partial["mstr"] = None
    partial["options"] = None
    partial["errors"] = ["bitcoinKpis:Timeout"]
    monkeypatch.setattr(mstr_btc_service, "refresh_fact_pack", lambda: partial)
    dashboard = mstr_btc_service.get_dashboard("en")
    assert dashboard["sourceStatus"] == "delayed"
    mstr_price = _metric(dashboard, "mstr_price")
    assert mstr_price["status"] == "unavailable"
    assert mstr_price["value"] is None
    assert mstr_price["unavailableReason"]
    # treasury metrics still render from the tracker page
    assert _metric(dashboard, "total_btc_reserves")["value"] == 843775
    assert dashboard["research"] is not None
    assert dashboard["research"]["evidenceGaps"]


def test_endpoint_contract(monkeypatch, api_client, recorded_pack):
    monkeypatch.setattr(mstr_btc_service, "refresh_fact_pack", lambda: recorded_pack)
    response = api_client.get("/opportunities/mstr-btc")
    assert response.status_code == 200
    body = response.json()
    for key in ("asOf", "sourceStatus", "sourceUrl", "metrics", "series", "scenarios", "research", "notes"):
        assert key in body
    assert body["sourceUrl"] == "https://www.strategy.com/"

    zh = api_client.get("/opportunities/mstr-btc", headers={"X-PG-Locale": "zh"})
    assert zh.status_code == 200
    zh_metric = next(m for m in zh.json()["metrics"] if m["id"] == "mstr_price")
    assert zh_metric["label"] == "MSTR 价格"
