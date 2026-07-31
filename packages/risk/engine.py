"""Deterministic, explainable portfolio risk calculations.

This module intentionally accepts a Portfolio Context rather than an LLM response.
It never places orders and treats stale or missing facts as a blocking condition.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

STRESS_SCENARIOS: dict[str, dict[str, Decimal]] = {
    "baseline": {},
    "btc_minus_10": {"BTC": Decimal("-0.10")},
    "btc_minus_20": {"BTC": Decimal("-0.20")},
    "btc_minus_35": {"BTC": Decimal("-0.35")},
    "eth_minus_25": {"ETH": Decimal("-0.25")},
    "sol_minus_30": {"SOL": Decimal("-0.30")},
    "stablecoin_minus_10": {"USDC": Decimal("-0.10"), "USDT": Decimal("-0.10")},
    "liquidity_minus_80": {"__all__": Decimal("-0.80")},
}


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _snapshot_id(context: dict[str, Any]) -> str:
    source = f"{context.get('data_as_of')}|{context.get('portfolio_ids')}|{context.get('total_nav')}"
    return hashlib.sha256(source.encode()).hexdigest()[:24]


@dataclass(frozen=True)
class RiskAssessment:
    snapshot_id: str
    method: str
    inputs: dict[str, Any]
    assumptions: list[str]
    as_of: str | None
    confidence: str
    data_quality: str
    result: dict[str, Any]
    breaches: list[dict[str, Any]]
    recommended_actions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id, "method": self.method, "inputs": self.inputs,
            "assumptions": self.assumptions, "as_of": self.as_of, "confidence": self.confidence,
            "data_quality": self.data_quality, "result": self.result, "breaches": self.breaches,
            "recommended_actions": self.recommended_actions,
        }


def evaluate_portfolio(context: dict[str, Any], scenario: str = "baseline") -> RiskAssessment:
    scenario_key = scenario.strip().lower()
    if scenario_key not in STRESS_SCENARIOS:
        raise ValueError(f"Unknown stress scenario: {scenario}")
    nav = _decimal(context.get("total_nav"))
    holdings = context.get("top_holdings") or []
    stale = bool(context.get("stale"))
    connected = bool(context.get("connected"))
    data_quality = "STALE" if stale else "FRESH" if connected and nav > 0 else "NOT_CONNECTED"
    snapshot_id = _snapshot_id(context)
    if data_quality != "FRESH":
        return RiskAssessment(snapshot_id, "portfolio-risk-v1", {"scenario": scenario_key, "nav": str(nav)},
            ["Risk calculations require a connected, non-stale portfolio snapshot."], context.get("data_as_of"), "none", data_quality,
            {"total_nav": str(nav), "gross_exposure": None, "net_exposure": None, "leverage": None, "concentration_hhi": None, "stress_nav": None},
            [{"code": "DATA_STALE" if stale else "PORTFOLIO_NOT_CONNECTED", "severity": "high", "message": "Portfolio facts are not fresh enough for risk assessment."}],
            ["Synchronize the portfolio and resolve data quality issues before relying on this assessment."])

    values = {str(item.get("symbol", "UNKNOWN")).upper(): _decimal(item.get("value")) for item in holdings}
    total_holdings = sum(values.values(), Decimal("0"))
    weights = {symbol: (value / nav if nav else Decimal("0")) for symbol, value in values.items()}
    hhi = sum(weight * weight for weight in weights.values())
    top_symbol, top_weight = max(weights.items(), key=lambda pair: pair[1], default=(None, Decimal("0")))
    breaches: list[dict[str, Any]] = []
    if top_weight >= Decimal("0.35"):
        breaches.append({"code": "CONCENTRATION", "severity": "high", "symbol": top_symbol, "weight": str(top_weight.quantize(Decimal('0.0001')))})
    if total_holdings > nav * Decimal("1.05"):
        breaches.append({"code": "GROSS_EXPOSURE", "severity": "high", "gross_exposure": str(total_holdings)})
    shocks = STRESS_SCENARIOS[scenario_key]
    stress_nav = nav
    for symbol, value in values.items():
        shock = shocks.get(symbol, shocks.get("__all__", Decimal("0")))
        stress_nav += value * shock
    if stress_nav < 0:
        stress_nav = Decimal("0")
    if scenario_key != "baseline" and stress_nav < nav * Decimal("0.8"):
        breaches.append({"code": "STRESS_LOSS", "severity": "high", "scenario": scenario_key, "loss_pct": str(((nav - stress_nav) / nav).quantize(Decimal('0.0001')))})
    actions = ["Review concentration and liquidity before increasing exposure."] if breaches else ["No configured limit breach detected; continue monitoring freshness."]
    return RiskAssessment(snapshot_id, "portfolio-risk-v1", {"scenario": scenario_key, "nav": str(nav), "holding_count": len(values)},
        ["Unpriced positions are excluded from value totals.", "Leverage, derivatives Greeks and VaR require instrument-level facts not present in this snapshot."],
        context.get("data_as_of"), "medium" if context.get("missing_data") else "high", "FRESH",
        {"total_nav": str(nav), "gross_exposure": str(total_holdings), "net_exposure": str(total_holdings), "leverage": None,
         "concentration_hhi": str(hhi.quantize(Decimal('0.000001'))), "top_holding": top_symbol, "top_weight": str(top_weight.quantize(Decimal('0.0001'))),
         "stress_nav": str(stress_nav), "stress_loss": str((nav - stress_nav).quantize(Decimal('0.01')))}, breaches, actions)
