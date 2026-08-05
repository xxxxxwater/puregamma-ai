from __future__ import annotations

import re


POSITIVE = {"rally", "surge", "gain", "approval", "adoption", "inflow", "breakout", "growth", "bullish"}
NEGATIVE = {"hack", "exploit", "loss", "decline", "outflow", "ban", "liquidation", "bearish", "fraud"}


def score_text(text: str) -> tuple[float, str]:
    words = set(re.findall(r"[a-z]+", text.lower()))
    score = len(words & POSITIVE) - len(words & NEGATIVE)
    normalized = max(-1.0, min(1.0, score / 4.0))
    label = "positive" if normalized > 0.15 else "negative" if normalized < -0.15 else "neutral"
    return normalized, label
