from __future__ import annotations

from datetime import datetime, timezone


def discover_long_gamma(instruments: list[dict], limit: int = 10) -> list[dict]:
    now = datetime.now(timezone.utc)
    candidates = []
    for item in instruments:
        greeks = item.get("greeks") or {}
        gamma = float(greeks.get("gamma", 0) or 0)
        theta = abs(float(greeks.get("theta", 0) or 0))
        if gamma <= 0 or theta <= 0:
            continue
        expiry = datetime.fromisoformat(item["expiry"].replace("Z", "+00:00"))
        days = max(0.0, (expiry - now).total_seconds() / 86400)
        if days < 2 or days > 120:
            continue
        spread = item.get("spread_pct")
        spread_score = max(0.0, 1 - min(float(spread or 1), 1))
        liquidity = min(
            1.0, (float(item["volume_24h"]) + float(item["open_interest"]) / 10) / 500
        )
        convexity = min(1.0, gamma / max(theta, 1e-9) * 100)
        tenor = 1.0 if 7 <= days <= 45 else 0.55
        score = round(
            100
            * (0.35 * convexity + 0.3 * liquidity + 0.2 * spread_score + 0.15 * tenor),
            1,
        )
        candidates.append(
            {
                **item,
                "days_to_expiry": round(days, 1),
                "gamma_theta_ratio": gamma / theta,
                "research_score": score,
                "rationale": [
                    "positive gamma",
                    "liquidity and spread filter",
                    "theta cost included",
                ],
                "execution_enabled": False,
            }
        )
    candidates.sort(key=lambda row: row["research_score"], reverse=True)
    return candidates[: max(1, min(limit, 25))]
