from __future__ import annotations

from packages.dream_rsi.control_plane import (
    is_dream_strategy_request,
    parse_dream_goal,
    replay_history,
)
from packages.nautilus.data_adapter import timeframe_minutes
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
