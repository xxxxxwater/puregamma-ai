"""Nautilus-spec prompt builder for lab strategy generation.

The LLM is instructed to emit a declarative JSON spec that maps one-to-one onto
NautilusTrader strategy semantics (bar-driven signals, no look-ahead, next-bar
execution), so generated strategies remain replayable inside the Nautilus
backtest contract used by PureGamma.
"""

from __future__ import annotations

NAUTILUS_SPEC_CONTRACT = """
You generate daily-frequency crypto strategy specifications that follow the
NautilusTrader backtest contract:
- Data: 1d OHLCV bars for BTC and ETH, ascending, up to three years.
- Signal timing: the signal for bar N may only use bars before N (no look-ahead);
  the position earns bar N's close-to-close return.
- Modes:
  * "daily": evaluate each asset independently (momentum / mean_reversion / breakout).
  * "cross_sectional": rank BTC vs ETH every rebalance_days by trailing
    slow_window momentum; hold the stronger leg long and, when long_short is
    true, the weaker leg short (market-neutral style).
- Costs: fee_bps is charged per unit of position change.
- Risk: optional stop_loss_pct flattens the position until the next rebalance window.

Respond with STRICT JSON only (no markdown fences, no commentary) matching:
{
  "name": string (3-120 chars),
  "mode": "daily" | "cross_sectional",
  "signal": "momentum" | "mean_reversion" | "breakout" | "relative_strength",
  "assets": ["BTC", "ETH"] (cross_sectional requires both),
  "fast_window": int 2-120,
  "slow_window": int > fast_window, <= 250,
  "entry_threshold": float 0-0.5,
  "exit_threshold": float 0-0.5,
  "rebalance_days": int 1-60,
  "long_short": bool,
  "max_position": float 0-1,
  "fee_bps": float 0-100,
  "stop_loss_pct": float 0.01-0.5 or null,
  "thesis": string (<= 600 chars, first-person reasoning summary)
}
Rules: prefer slow_window between 20 and 90 for three-year daily data; keep
entry_threshold at 0 unless the thesis calls for a deadband; cross_sectional
mode should normally use signal "relative_strength" and long_short true.
""".strip()


def build_strategy_prompt(
    idea: str,
    *,
    locale: str,
    secretary_notes: list[str],
    conversation_notes: list[str],
) -> str:
    notes = [note.strip() for note in [*secretary_notes, *conversation_notes] if note.strip()]
    context_block = "\n".join(f"- {note}" for note in notes[:12]) or "- (no prior conversation context)"
    language = "Chinese" if locale == "zh" else "English"
    idea_block = idea.strip() or "Create a robust baseline daily strategy for BTC and ETH."
    return (
        f"{NAUTILUS_SPEC_CONTRACT}\n\n"
        f"The user's research context from their private secretary and agent conversations:\n{context_block}\n\n"
        f"User idea: {idea_block}\n\n"
        f"Write the thesis field in {language}. Emit one JSON object only."
    )
