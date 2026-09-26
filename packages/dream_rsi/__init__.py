"""Dream-RSI research control plane for PureGamma Agent."""

from packages.dream_rsi.control_plane import (
    DreamGoal,
    is_dream_strategy_request,
    parse_dream_goal,
    replay_history,
    run_dream_strategy_search,
)

__all__ = [
    "DreamGoal",
    "is_dream_strategy_request",
    "parse_dream_goal",
    "replay_history",
    "run_dream_strategy_search",
]
