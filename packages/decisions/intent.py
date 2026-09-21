"""Jev-backed intent routing for the Agent surface.

Jev answers typed questions; it does not write prose. So it is used here for the
one job it is actually good at -- deciding which handler a request belongs to --
and the chosen handler still produces the reply with the normal model.

Fail-closed by construction. Every path that is not a confident, well-formed
answer returns None, and the caller keeps whatever routing it already had. A
missing key, a timeout, a rate limit, a malformed response, a choice outside
the offered set, or a score below the threshold all look the same to the
caller: no opinion. Nothing is invented from a low-confidence answer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from packages.decisions.jev_client import (
    JevClient,
    JevError,
    JevUnavailable,
    choice,
)

#: Handler families the router can pick between. These are the same task
#: families the deterministic router already knows, so a Jev decision can never
#: route somewhere the platform cannot serve.
INTENTS: dict[str, str] = {
    "research": "Gathering or investigating information, news, or market context",
    "portfolio": "Questions about the user's own holdings, accounts, or NAV",
    "backtest": "Testing or evaluating a strategy against historical data",
    "market_data": "Looking up prices, candles, instruments, or exchange data",
    "chat": "General conversation, explanation, or product help",
}

#: A choice below this confidence is treated as no opinion. Jev reports
#: confidence as distribution concentration, so a split vote means the request
#: is genuinely ambiguous and the deterministic router should keep it.
MIN_CONFIDENCE = 0.55

#: Longest request Jev is asked about. Beyond this the text is truncated rather
#: than sent whole; the intent is almost always visible in the opening.
MAX_INPUT_CHARS = 2_000


@dataclass(frozen=True)
class IntentDecision:
    intent: str
    confidence: float
    model: str
    probabilities: dict[str, float]


def classify_intent(
    text: str,
    *,
    client: JevClient | None = None,
    min_confidence: float = MIN_CONFIDENCE,
) -> IntentDecision | None:
    """Return a routing decision, or None when there is no usable opinion.

    The caller must treat None as "keep your existing routing", never as a
    default intent.
    """
    body = (text or "").strip()
    if not body:
        return None

    jev = client or JevClient()
    if not jev.configured:
        return None

    state = body[:MAX_INPUT_CHARS]
    try:
        result = jev.ask(
            state,
            {"intent": choice("Which handler should answer this request?", INTENTS)},
        )
    except (JevUnavailable, JevError, ValueError):
        # No key, transport failure, rate limit, malformed reply: no opinion.
        return None

    answer = (result.get("answers") or {}).get("intent") or {}
    if answer.get("type") != "choice":
        return None
    picked = answer.get("choice")
    if picked not in INTENTS:
        return None          # an option we never offered cannot be trusted
    confidence = answer.get("confidence")
    if not isinstance(confidence, (int, float)) or confidence < min_confidence:
        return None

    probabilities = {
        key: float(value)
        for key, value in (answer.get("probabilities") or {}).items()
        if isinstance(value, (int, float))
    }
    return IntentDecision(
        intent=str(picked),
        confidence=float(confidence),
        # The versioned id that answered, never the moving alias.
        model=str(result.get("model") or ""),
        probabilities=probabilities,
    )
