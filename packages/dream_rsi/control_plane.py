"""Dream-RSI control plane for research-only strategy-family discovery."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from sqlalchemy.orm import Session

from packages.backtest.engine import run_strategy_family_sweep_for_agent
from packages.backtest.family_research import (
    FAMILY_LABELS, FAMILY_ORDER, allocate_family_compute, family_candidate_library,
    initial_family_candidates, next_family_candidates,
)
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
    max_evaluations: int = 16

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
    timeframe = _normalize_timeframe(timeframe_match.group(1), timeframe_match.group(2)) if timeframe_match else "1h"
    drawdown_match = _DRAWDOWN_RE.search(query)
    max_drawdown = None
    if drawdown_match:
        raw = float(drawdown_match.group(1))
        max_drawdown = raw / 100.0 if drawdown_match.group(2) or raw > 1 else raw
    sharpe_match = _SHARPE_RE.search(query)
    return DreamGoal(
        symbol=understanding.assets[0],
        timeframe=timeframe,
        min_sharpe=float(sharpe_match.group(1)) if sharpe_match else None,
        max_drawdown=max_drawdown,
    )


def is_dream_strategy_request(query: str) -> bool:
    lowered = " ".join(query.lower().split())
    strategy = any(term in lowered for term in ("strategy", "策略", "交易系统", "alpha"))
    exploration = any(term in lowered for term in (
        "find", "search", "discover", "optimize", "explore",
        "寻找", "找一个", "找出", "搜索", "发现", "筛选", "优化", "探索",
    ))
    return strategy and (exploration or bool(_SHARPE_RE.search(query) or _DRAWDOWN_RE.search(query)))


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
    return not (
        goal.min_sharpe is not None and sharpe < goal.min_sharpe
        or goal.max_drawdown is not None and drawdown > goal.max_drawdown
    )


def _node(result: dict[str, Any], goal: DreamGoal, *, node_id: str, generation: int, parent_id: str) -> dict[str, Any]:
    metrics = {
        "sharpe_ratio": float(result.get("sharpe_ratio") or 0.0),
        "max_drawdown": float(result.get("max_drawdown") or 0.0),
        "total_return": float(result.get("total_return") or 0.0),
        "win_rate": float(result.get("win_rate") or 0.0),
        "trade_count": int(result.get("trade_count") or 0),
    }
    params = dict(result.get("params") or {})
    family = str(result.get("family") or params.get("family") or "unknown")
    return {
        "id": node_id, "generation": generation, "parent_id": parent_id,
        "family": family, "family_label": FAMILY_LABELS.get(family, family),
        "factor_variant": str(result.get("factor_variant") or params.get("factor_variant") or "unknown"),
        "factor_quality": result.get("factor_quality"),
        "factor_coverage": dict(result.get("factor_coverage") or {}),
        "params": params, "metrics": metrics,
        "validation": {"in_sample": dict(result.get("in_sample") or {}), "out_of_sample": dict(result.get("out_of_sample") or {})},
        "meets_constraints": _meets(metrics, goal), "score": _score(metrics, goal),
    }


def replay_history(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    if not nodes:
        return {"selected_policy": "observed_order", "policies": []}
    policies = {
        "observed_order": list(nodes),
        "sharpe_first": sorted(nodes, key=lambda n: (float(n["metrics"].get("sharpe_ratio") or 0.0), -abs(float(n["metrics"].get("max_drawdown") or 0.0))), reverse=True),
        "drawdown_first": sorted(nodes, key=lambda n: (abs(float(n["metrics"].get("max_drawdown") or 0.0)), -float(n["metrics"].get("sharpe_ratio") or 0.0))),
        "constraint_first": sorted(nodes, key=lambda n: (bool(n.get("meets_constraints")), float(n.get("score") or 0.0)), reverse=True),
        "family_best_first": sorted(nodes, key=lambda n: (float(n.get("score") or 0.0), -int(n.get("generation") or 0)), reverse=True),
    }
    scored = []
    for name, ordered in policies.items():
        observed = []
        for node in ordered:
            observed.append(node)
            if node.get("meets_constraints"):
                break
        best = max(observed, key=lambda n: float(n.get("score") or 0.0))
        scored.append({
            "policy": name, "visited_nodes": len(observed), "best_node_id": best["id"],
            "best_family": best.get("family"),
            "found_constraint_match": any(bool(n.get("meets_constraints")) for n in observed),
            "replay_objective": round(float(best.get("score") or 0.0) - 0.02 * len(observed), 6),
        })
    selected = max(scored, key=lambda item: item["replay_objective"])
    return {"selected_policy": selected["policy"], "policies": scored}


def _dedupe_unavailable(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {}
    for row in rows:
        family = str(row.get("family") or "unknown")
        existing = merged.get(family)
        if existing is None:
            merged[family] = {
                "family": family, "label": FAMILY_LABELS.get(family, family),
                "reason": row.get("reason") or "factor_unavailable",
                "missing_factors": list(row.get("missing_factors") or []),
                "factor_coverage": dict(row.get("factor_coverage") or {}),
                "factor_quality": row.get("factor_quality"),
            }
        else:
            existing["missing_factors"] = sorted(set(existing["missing_factors"]).union(row.get("missing_factors") or []))
    return list(merged.values())


def _family_tree(nodes: list[dict[str, Any]], policy: dict[str, Any], unavailable: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unavailable_map = {str(row.get("family")): row for row in unavailable}
    allocation = dict(policy.get("allocation") or {})
    families = []
    for family in FAMILY_ORDER:
        rows = [node for node in nodes if node.get("family") == family]
        best = max(rows, key=lambda row: float(row.get("score") or 0.0)) if rows else None
        missing = unavailable_map.get(family)
        families.append({
            "id": f"family:{family}", "family": family, "label": FAMILY_LABELS[family],
            "status": "factor_unavailable" if missing and not rows else "evaluated",
            "evaluations": len(rows), "generation_1_budget": int(allocation.get(family, 0)),
            "best_node_id": best.get("id") if best else None,
            "best_oos_score": float(best.get("score") or 0.0) if best else None,
            "constraint_matches": sum(1 for row in rows if row.get("meets_constraints")),
            "factor_quality": best.get("factor_quality") if best else missing.get("factor_quality") if missing else None,
            "missing_factors": list(missing.get("missing_factors") or []) if missing else [],
        })
    return families


def run_dream_strategy_search(db: Session, query: str) -> dict[str, Any]:
    goal = parse_dream_goal(query)
    first = run_strategy_family_sweep_for_agent(
        db, asset=goal.symbol, candidates=initial_family_candidates(),
        timeframe=goal.timeframe, lookback_days=goal.lookback_days,
    )
    initial_nodes = [
        _node(result, goal, node_id=f"g0-{result.get('family')}-{index + 1}",
              generation=0, parent_id=f"family:{result.get('family')}")
        for index, result in enumerate(first["candidates"])
    ]
    unavailable = _dedupe_unavailable(list(first.get("skipped_families") or []))
    policy = allocate_family_compute(initial_nodes, max(0, goal.max_evaluations - len(initial_nodes)), unavailable)
    second_candidates = next_family_candidates(initial_nodes, dict(policy.get("allocation") or {}))
    nodes = list(initial_nodes)
    second = None
    if second_candidates:
        second = run_strategy_family_sweep_for_agent(
            db, asset=goal.symbol, candidates=second_candidates,
            timeframe=goal.timeframe, lookback_days=goal.lookback_days,
        )
        parent_by_family = {}
        for family in FAMILY_ORDER:
            rows = [node for node in initial_nodes if node.get("family") == family]
            if rows:
                parent_by_family[family] = max(rows, key=lambda row: float(row.get("score") or 0.0))["id"]
        for index, result in enumerate(second["candidates"]):
            family = str(result.get("family") or "unknown")
            nodes.append(_node(
                result, goal, node_id=f"g1-{family}-{index + 1}", generation=1,
                parent_id=parent_by_family.get(family, f"family:{family}"),
            ))
        unavailable = _dedupe_unavailable(unavailable + list(second.get("skipped_families") or []))

    replay = replay_history(nodes)
    coverage = min(float(first.get("coverage_ratio") or 0.0), float((second or first).get("coverage_ratio") or 0.0))
    coverage_verified = coverage >= 0.70
    data_freshness = str(first.get("data_freshness") or "unknown")
    matches = [item for item in nodes if item["meets_constraints"]]
    best = max(matches or nodes, key=lambda item: float(item["score"])) if nodes else None
    status = (
        "no_evaluable_families" if not nodes else
        "development_mock_only" if data_freshness == "mock" else
        "timeframe_coverage_insufficient" if not coverage_verified else
        "constraint_satisfied" if matches else "best_effort"
    )
    return {
        "kind": "dream_rsi_strategy_family_discovery", "version": "0.2",
        "status": status, "goal": goal.as_dict(),
        "strategy_space": {
            "families": [FAMILY_LABELS[family] for family in FAMILY_ORDER],
            "candidate_capacity": sum(len(values) for values in family_candidate_library().values()),
        },
        "best_candidate": best,
        "discovery_tree": {
            "root": {"id": "root", "goal": goal.as_dict(), "children": [f"family:{family}" for family in FAMILY_ORDER]},
            "families": _family_tree(nodes, policy, unavailable), "nodes": nodes,
            "unavailable_families": unavailable,
        },
        "exploration_policy": policy, "history_replay": replay,
        "data": {
            "engine": first.get("engine"), "bar_count": first.get("bar_count"),
            "timeframe": first.get("timeframe"), "coverage_ratio": round(coverage, 4),
            "coverage_verified": coverage_verified, "factor_coverage": first.get("factor_coverage", {}),
            "factor_quality": first.get("factor_quality", {}), "data_freshness": data_freshness,
            "bar_construction": first.get("bar_construction"), "validation": first.get("validation"),
        },
        "compute": {
            "evaluations": len(nodes), "generations": 2 if second else 1,
            "replayed_policies": len(replay.get("policies", [])),
            "generation_1_family_budget": policy.get("allocation", {}),
        },
        "safety": {"research_only": True, "creates_orders": False, "activates_strategy": False, "live_trading": False},
    }
