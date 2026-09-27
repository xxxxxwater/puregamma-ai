from __future__ import annotations

from packages.dream_rsi.control_plane import (
    is_dream_strategy_request,
    parse_dream_goal,
    replay_history,
)
from packages.nautilus.data_adapter import timeframe_minutes
from packages.backtest.metrics import calculate_metrics
from packages.backtest.family_research import (
    FAMILY_ORDER,
    allocate_family_compute,
    evaluate_family_candidate,
    initial_family_candidates,
)
from apps.api.services.chat_workspace import tool_permission


def test_parse_chinese_dream_goal():
    goal = parse_dream_goal("找一个 BTC 15m，最大回撤 < 12%，Sharpe > 1.8 的策略")
    assert goal.symbol == "BTC"
    assert goal.timeframe == "15m"
    assert goal.max_drawdown == 0.12
    assert goal.min_sharpe == 1.8


def test_dream_intent_requires_strategy_context():
    assert is_dream_strategy_request(
        "Find a BTC 1h strategy with Sharpe > 2 and max drawdown < 10%"
    )
    assert not is_dream_strategy_request("What is BTC price?")


def test_replay_history_finds_constraint_match():
    nodes = [
        {
            "id": "a",
            "metrics": {"sharpe_ratio": 1.1, "max_drawdown": -0.08},
            "meets_constraints": False,
            "score": 0.5,
        },
        {
            "id": "b",
            "metrics": {"sharpe_ratio": 2.0, "max_drawdown": -0.09},
            "meets_constraints": True,
            "score": 1.5,
        },
    ]
    replay = replay_history(nodes)
    assert replay["selected_policy"] in {
        "sharpe_first", "drawdown_first", "constraint_first", "observed_order"
    }
    assert any(item["found_constraint_match"] for item in replay["policies"])


def test_timeframe_parser():
    assert timeframe_minutes("15m") == 15
    assert timeframe_minutes("4h") == 240
    assert timeframe_minutes("1d") == 1440



def test_dream_search_is_read_only_in_agent_workspace():
    assert tool_permission("read-only", "run_dream_strategy_search") == "allow"
    assert tool_permission("workspace-write", "run_dream_strategy_search") == "allow"



def test_sharpe_annualization_respects_bar_frequency():
    returns = [0.01, -0.004, 0.006, -0.002, 0.008, -0.003] * 20
    daily = calculate_metrics(returns, periods_per_year=365)["sharpe"]
    hourly = calculate_metrics(returns, periods_per_year=365 * 24)["sharpe"]
    assert hourly > daily



def test_family_seed_covers_the_six_dream_roots():
    seeds = initial_family_candidates()
    assert [item["family"] for item in seeds] == list(FAMILY_ORDER)


def test_family_budget_rewards_better_oos_family_without_starving_exploration():
    nodes = [
        {"id": "m", "family": "momentum", "score": 2.0, "meets_constraints": True, "params": {"family": "momentum", "factor_variant": "ma_cross", "fast_window": 6, "slow_window": 24}},
        {"id": "v", "family": "vwap", "score": 1.0, "meets_constraints": False, "params": {"family": "vwap", "factor_variant": "vwap_reclaim", "vwap_window": 24}},
        {"id": "o", "family": "orderflow", "score": 0.4, "meets_constraints": False, "params": {"family": "orderflow", "factor_variant": "signed_volume_pressure", "pressure_window": 12}},
    ]
    allocation = allocate_family_compute(nodes, remaining=8)["allocation"]
    assert allocation["momentum"] >= allocation["vwap"] >= 1
    assert allocation["orderflow"] >= 1


def test_funding_oi_family_fails_closed_without_real_factor_series():
    bars = [
        {"open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100 + i,
         "volume": 1000, "bid": 99.9 + i, "ask": 100.1 + i,
         "funding_rate": None, "open_interest": None}
        for i in range(220)
    ]
    candidate = next(item for item in initial_family_candidates() if item["family"] == "funding_oi")
    result = evaluate_family_candidate(bars, candidate, timeframe="15m", split_index=154)
    assert result["available"] is False
    assert set(result["missing_factors"]) == {"funding_rate", "open_interest"}
