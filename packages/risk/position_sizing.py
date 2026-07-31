from __future__ import annotations


def suggested_position_size(risk_score: int, max_risk_pct: float = 1.0) -> float:
    multiplier = max(0.1, 1 - (risk_score / 125))
    return round(max_risk_pct * multiplier, 2)
