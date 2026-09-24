from pathlib import Path

from apps.api.services.pm_riskbot_service import LATEST_SCHEMA, SERIES_SCHEMA, PmAccountReader
from tests.unit.test_pm_riskbot_service import write_bundle


def test_pm_nav_contract_keeps_account_equity_as_history_nav(tmp_path: Path):
    write_bundle(
        tmp_path,
        "series.json",
        SERIES_SCHEMA,
        {
            "points": [
                {
                    "t": 1,
                    "equity_usd": "1670611.91",
                    "adjusted_equity_usd": None,
                    "equity_btc_equivalent": "19.8124",
                    "btc_price_usd": "84321.36",
                }
            ]
        },
    )
    point = PmAccountReader(tmp_path).nav_history_view()["points"][0]
    assert point["equity_usd"] == "1670611.91"
    assert point["adjusted_equity_usd"] is None


def test_pm_account_bundle_does_not_require_adjusted_equity(tmp_path: Path):
    write_bundle(
        tmp_path,
        "latest.json",
        LATEST_SCHEMA,
        {
            "snapshot": {"captured_at": "2026-09-24T00:00:00Z"},
            "collector": {"name": "riskbot", "read_only": True},
            "account": {
                "account_equity_usd": "1670611.91",
                "adjusted_equity_usd": None,
            },
            "btc": {
                "equity_btc_equivalent": "19.8124",
                "price_usd": "84321.36",
            },
            "balances": [],
        },
    )
    view = PmAccountReader(tmp_path).account_view()
    assert view["account"]["account_equity_usd"] == "1670611.91"
    assert view["account"]["adjusted_equity_usd"] is None


def test_pm_web_panel_uses_account_equity_for_hero_and_history_curve():
    source = Path("apps/web/components/pm-account-panel.tsx").read_text(encoding="utf-8")
    assert "const netUsd = num(point.equity_usd);" in source
    assert 'const heroValue = currency === "USD" ? equityUsd : equityBtc;' in source
    assert "const netUsd = num(point.adjusted_equity_usd);" not in source
