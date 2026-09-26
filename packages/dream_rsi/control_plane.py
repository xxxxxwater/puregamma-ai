"""Dream-RSI control plane for research-only strategy discovery.

It optimizes the Agent's exploration policy, not model weights or trading
permissions. A chat goal such as:

    找一个 BTC 15m，最大回撤 < 12%，Sharpe > 1.8 的策略

becomes an auditable research goal. PureGamma evaluates a bounded discovery
tree on its existing historical catalog, then replays alternative traversal
policies over the observed nodes. No order or strategy activation path exists
in this module.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from sqlalchemy.orm import Session

from packages.backtest.engine import run_parameter_sweep_for_agent
from packages.data.lexicon import understand_query


_TIMEFRAME_RE = re.compile(
    r"(?<![A-Za-z0-9])(\d{1,4})\s*(m|min|mins|minute|minutes|分钟|h|hr|hrs|hour|hours|小时|d|day|days|天)(?![A-Za-z])",
    re.I,
)
_DRAWDOWN_RE = re.compile(
    r"(?:max(?:imum)?\s*drawdown|max\s*dd|mdd|最大回撤|回撤)"
    r"\s*(?:<=|<|≤|不超过|低于|小于)?\s*([0-9]+(?:\.[0-9]+)?)\s*(%)?",
    re.I,
)
_SHARPE_RE = re.compile(
    r"(?:sharpe(?:\s*ratio)?|夏普(?:率|比率)?)"
    r"\s*(?:>=|>|≥|至少|高于|大于)?\s*([0-9]+(?:\.[0-9]+)?)",
    re.I,
)


@dataclass(frozen=True)
class DreamGoal:
    symbol: str
    timeframe: str = "1h"
    min_sharpe: float | None = None
    max_drawdown: float | None = None
    lookback_days: int = 90
    max_evaluations: int = 6

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.max_drawdown is not None:
            payload["max_drawdown_pct"] = round(self.max_drawdown * 100, 4)
        return payload


def _normalize_timeframe(value: str, unit: str) -> str:
    count = max(1, int(value))
    normalized = unit.lower()
    if normalized in {"m", "min", "mins", "minute", "minutes", "分钟"}:
        return f"{count}m"
    if normalized in {"h", "hr", "hrs", "hour", "hours", "小时"}:
        return f"{count}h"
    return f"{count}d"


def parse_dream_goal(query: str) -> DreamGoal:
    understanding = understand_query(query)
    if not understanding.assets:
        raise ValueError("DREAM_RSI_ASSET_REQUIRED")
    timeframe_match = _TIMEFRAME_RE.search(query)
    timeframe = (
        _normalize_timeframe(timeframe_match.group(1), timeframe_match.group(2))
        if timeframe_match
        else "1h"
    )
    drawdown_match = _DRAWDOWN_RE.search(query)
    max_drawdown: float | None = None
    if drawdown_match:
        raw = float(drawdown_match.group(1))
        max_drawdown = raw / 100.0 if drawdown_match.group(2) or raw > 1 else raw
    sharpe_match = _SHARPE_RE.search(query)
    min_sharpe = float(sharpe_match.group(1)) if sharpe_match else None
    return DreamGoal(
        symbol=understanding.assets[0],
        timeframe=timeframe,
        min_sharpe=min_sharpe,
        max_drawdown=max_drawdown,
    )


def is_dream_strategy_request(query: str) -> bool:
    lowered = " ".join(query.lower().split())
    strategy = any(term in lowered for term in ("strategy", "策略", "交易系统", "alpha"))
    exploration = any(
        term in lowered
        for term in (
            "find", "search", "discover", "optimize", "explore",
            "寻找", "找一个", "找出", "搜索", "发现", "筛选", "优化", "探索",
        )
    )
    objective = bool(_SHARPE_RE.search(query) or _DRAWDOWN_RE.search(query))
    return strategy and (exploration or objective)


def _score(metrics: dict[str, Any], goal: DreamGoal) -> float:
    sharpe = float(metrics.get("sharpe_ratio") or 0.0)
    drawdown = abs(float(metrics.get("max_drawdown") or 0.0))
    total_return = float(metrics.get("total_return") or 0.0)
    penalty = 0.0
    if goal.min_sharpe is not None:
        penalty += max(0.0, goal.min_sharpe - sharpe) * 2.0
    if goal.max_drawdown is not None:
        penalty += max(0.0, drawdown - goal.max_drawdown) * 6.0
    return round(sharpe - 1.5 * drawdown + 0.10 * total_return - penalty, 6)


def _meets(metrics: dict[str, Any], goal: DreamGoal) -> bool:
    sharpe = float(metrics.get("sharpe_ratio") or 0.0)
    drawdown = abs(float(metrics.get("max_drawdown") or 0.0))
    if goal.min_sharpe is not None and sharpe < goal.min_sharpe:
        return False
    if goal.max_drawdown is not None and drawdown > goal.max_drawdown:
        return False
    return True


def _node(result: dict[str, Any], goal: DreamGoal, *, node_id: str, generation: int, parent_id: str) -> dict[str, Any]:
    metrics = {
        "sharpe_ratio": float(result.get("sharpe_ratio") or 0.0),
        "max_drawdown": float(result.get("max_drawdown") or 0.0),
        "total_return": float(result.get("total_return") or 0.0),
        "win_rate": float(result.get("win_rate") or 0.0),
        "trade_count": int(result.get("trade_count") or 0),
    }
    return {
        "id": node_id,
        "generation": generation,
        "parent_id": parent_id,
        "params": dict(result.get("params") or {}),
        "metrics": metrics,
        "validation": {
            "in_sample": dict(result.get("in_sample") or {}),
            "out_of_sample": dict(result.get("out_of_sample") or {}),
        },
        "meets_constraints": _meets(metrics, goal),
        "score": _score(metrics, goal),
    }


def _initial_candidates(goal: DreamGoal) -> list[dict[str, Any]]:
    return [
        {"fast_window": 4, "slow_window": 12, "fee_bps": 5.0},
        {"fast_window": 6, "slow_window": 18, "fee_bps": 5.0},
        {"fast_window": 8, "slow_window": 24, "fee_bps": 10.0},
        {"fast_window": 12, "slow_window": 36, "fee_bps": 10.0},
    ][: max(1, min(4, goal.max_evaluations))]


def _mutations(seed: dict[str, Any], remaining: int) -> list[dict[str, Any]]:
    fast = max(2, int(seed.get("fast_window", 6)))
    slow = max(fast + 1, int(seed.get("slow_window", 18)))
    fee = max(0.0, float(seed.get("fee_bps", 10.0)))
    candidates = [
        {"fast_window": max(2, fast - 2), "slow_window": max(fast + 2, slow - 4), "fee_bps": fee},
        {"fast_window": fast + 2, "slow_window": max(fast + 4, slow + 4), "fee_bps": fee},
        {"fast_window": fast, "slow_window": max(fast + 2, slow - 2), "fee_bps": max(0.0, fee - 2.5)},
        {"fast_window": fast, "slow_window": slow + 6, "fee_bps": fee + 2.5},
    ]
    unique: list[dict[str, Any]] = []
    seen: set[tuple[int, int, float]] = set()
    for item in candidates:
        key = (int(item["fast_window"]), int(item["slow_window"]), float(item["fee_bps"]))
        if item["slow_window"] <= item["fast_window"] or key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= remaining:
            break
    return unique


def replay_history(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Replay alternative traversal policies without re-running backtests."""
    if not nodes:
        return {"selected_policy": "observed_order", "policies": []}
    policies = {
        "observed_order": list(nodes),
        "sharpe_first": sorted(
            nodes,
            key=lambda n: (
                float(n["metrics"].get("sharpe_ratio") or 0.0),
                -abs(float(n["metrics"].get("max_drawdown") or 0.0)),
            ),
            reverse=True,
        ),
        "drawdown_first": sorted(
            nodes,
            key=lambda n: (
                abs(float(n["metrics"].get("max_drawdown") or 0.0)),
                -float(n["metrics"].get("sharpe_ratio") or 0.0),
            ),
        ),
        "constraint_first": sorted(
            nodes,
            key=lambda n: (bool(n.get("meets_constraints")), float(n.get("score") or 0.0)),
            reverse=True,
        ),
    }
    scored: list[dict[str, Any]] = []
    for name, ordered in policies.items():
        observed: list[dict[str, Any]] = []
        for node in ordered:
            observed.append(node)
            if node.get("meets_constraints"):
                break
        best = max(observed, key=lambda n: float(n.get("score") or 0.0))
        visited = len(observed)
        scored.append(
            {
                "policy": name,
                "visited_nodes": visited,
                "best_node_id": best["id"],
                "found_constraint_match": any(bool(n.get("meets_constraints")) for n in observed),
                "replay_objective": round(float(best.get("score") or 0.0) - 0.02 * visited, 6),
            }
        )
    selected = max(scored, key=lambda item: item["replay_objective"])
    return {"selected_policy": selected["policy"], "policies": scored}


def run_dream_strategy_search(db: Session, query: str) -> dict[str, Any]:
    goal = parse_dream_goal(query)
    first = run_parameter_sweep_for_agent(
        db,
        asset=goal.symbol,
        parameter_sets=_initial_candidates(goal),
        timeframe=goal.timeframe,
        lookback_days=goal.lookback_days,
    )
    nodes = [
        _node(result, goal, node_id=f"g0-{index + 1}", generation=0, parent_id="root")
        for index, result in enumerate(first["candidates"])
    ]
    seed = max(nodes, key=lambda item: float(item["score"]))
    remaining = max(0, goal.max_evaluations - len(nodes))
    mutations = _mutations(seed["params"], min(2, remaining))
    second = None
    if mutations:
        second = run_parameter_sweep_for_agent(
            db,
            asset=goal.symbol,
            parameter_sets=mutations,
            timeframe=goal.timeframe,
            lookback_days=goal.lookback_days,
        )
        nodes.extend(
            _node(result, goal, node_id=f"g1-{index + 1}", generation=1, parent_id=seed["id"])
            for index, result in enumerate(second["candidates"])
        )

    matches = [item for item in nodes if item["meets_constraints"]]
    best = max(matches or nodes, key=lambda item: float(item["score"]))
    replay = replay_history(nodes)
    coverage = min(
        float(first.get("coverage_ratio") or 0.0),
        float((second or first).get("coverage_ratio") or 0.0),
    )
    coverage_verified = coverage >= 0.70
    data_freshness = str(first.get("data_freshness") or "unknown")
    status = (
        "development_mock_only"
        if data_freshness == "mock"
        else "timeframe_coverage_insufficient"
        if not coverage_verified
        else "constraint_satisfied"
        if matches
        else "best_effort"
    )
    return {
        "kind": "dream_rsi_strategy_discovery",
        "version": "0.1",
        "status": status,
        "goal": goal.as_dict(),
        "best_candidate": best,
        "discovery_tree": {"root": {"id": "root", "goal": goal.as_dict()}, "nodes": nodes},
        "history_replay": replay,
        "data": {
            "engine": first.get("engine"),
            "bar_count": first.get("bar_count"),
            "timeframe": first.get("timeframe"),
            "coverage_ratio": round(coverage, 4),
            "coverage_verified": coverage_verified,
            "data_freshness": data_freshness,
            "bar_construction": first.get("bar_construction"),
            "validation": first.get("validation"),
        },
        "compute": {
            "evaluations": len(nodes),
            "generations": 2 if second else 1,
            "replayed_policies": len(replay.get("policies", [])),
        },
        "safety": {
            "research_only": True,
            "creates_orders": False,
            "activates_strategy": False,
            "live_trading": False,
        },
    }
