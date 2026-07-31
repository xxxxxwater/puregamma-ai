from packages.risk.engine import evaluate_portfolio


def test_stale_portfolio_blocks_risk_assessment():
    result = evaluate_portfolio({"connected": True, "stale": True, "total_nav": 1000, "data_as_of": "2026-07-14T00:00:00Z"})
    assert result.data_quality == "STALE"
    assert result.breaches[0]["code"] == "DATA_STALE"
    assert result.result["leverage"] is None


def test_risk_engine_is_deterministic_and_stresses_holdings():
    context = {
        "connected": True, "stale": False, "total_nav": 1000, "data_as_of": "2026-07-14T00:00:00Z",
        "portfolio_ids": ["account-1"], "top_holdings": [{"symbol": "BTC", "value": 700}, {"symbol": "ETH", "value": 300}], "missing_data": [],
    }
    first = evaluate_portfolio(context, "btc_minus_20").to_dict()
    second = evaluate_portfolio(context, "btc_minus_20").to_dict()
    assert first == second
    assert first["result"]["stress_nav"] == "860.00"
    assert any(item["code"] == "CONCENTRATION" for item in first["breaches"])
