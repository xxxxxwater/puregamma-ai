"""The boundary between the private PM account and any third-party model.

Every byte that leaves this process for a third party goes through
:func:`redact_account_view`. It is the only place that decides what a model is
allowed to see, which is why it is an **allowlist**: the projection is built
field by field into a new structure, so anything riskbot adds to the bundle
later is dropped by default instead of quietly published.

What is removed, and why
------------------------
The owner's stated boundary is *not* "hide the strategy" but "do not leak the
absolute scale". So symbols, sides and leverage stay -- a judgment about a book
is worthless without them -- while every absolute quantity goes:

* equity, wallet balance, margin, available balance, withdrawable
* notional (gross, net, signed, per position) and its BTC equivalent
* position quantity, entry/mark/break-even/liquidation price
* drawdown and peak equity in BTC
* exchange order ids and riskbot rule fingerprints

What is kept is the *shape* a judgment actually needs: booleans, categorical
levels, and ratios. Where a useful shape is only expressible from absolute
numbers -- how concentrated the book is, how much of it is net -- the ratio is
computed **here**, locally, and only the ratio is sent.

Freshness metadata (``age_seconds``, ``stale``, ``partial``) is kept intact and
never rounded: a judgment about stale data is only meaningful if the model can
see how stale it is.

This module is pure: no I/O, no config, no network. It is trivially testable,
and :func:`assert_no_absolute_scale` exists to prove the output is scale-free.
"""
from __future__ import annotations

from typing import Any

#: Bumped whenever the emitted shape changes, so a cached judgment can be
#: invalidated instead of being reused against a different question set.
REDACTED_STATE_SCHEMA = "puregamma.pm_judgment_state.v1"

# --------------------------------------------------------------------------
# What may pass. Anything not named here is dropped.
# --------------------------------------------------------------------------

#: Account fields that are already ratios or categories. Every *_usd and
#: *_btc_equivalent field is absent by omission -- that is the point.
_ACCOUNT_SAFE_KEYS = (
    "account_status",
    "uni_mmr",
    "uni_mmr_is_official",
    "uni_mmr_pct",
    "maint_margin_usage_derived_pct",
    "available_balance_ratio_derived",
    "total_margin_open_loss_ratio_derived",
    "gross_leverage_derived",
)

_POSITION_SAFE_KEYS = (
    "symbol",
    "side",
    "leverage",
    "quantity_unit",
    "position_mode",
    "adl_quantile",
    "has_liquidation_price",
)

_ORDER_SAFE_KEYS = (
    "symbol",
    "side",
    "order_type",
    "algo_type",
    "status",
    "is_live",
    "is_protective",
    "reduce_only",
    "close_position",
    "percent_from_mark",
)

_PROTECTION_SAFE_KEYS = (
    "symbol",
    "side",
    "covered",
    "partial",
    "coverage_known",
    "reason",
)

_FIRING_SAFE_KEYS = ("rule", "level", "status")


def _num(value: Any) -> float | None:
    """Parse one of the bundle's string-encoded numbers, or None.

    The bundle stores every figure as a string. A value that will not parse is
    reported as absent rather than coerced to 0.0 -- the same fail-closed rule
    the reader itself follows.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0.0):
        return None
    return numerator / denominator


def _pick(source: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(source, dict):
        return {}
    return {k: source[k] for k in keys if k in source}


def book_shape(positions: list[dict[str, Any]]) -> dict[str, Any]:
    """Scale-free description of the book, computed from absolute notionals.

    The absolute inputs never leave this function; only these ratios do.
    """
    signed: list[float] = []
    for pos in positions:
        if not isinstance(pos, dict):
            continue
        value = _num(pos.get("signed_notional_usd"))
        if value is None:
            value = _num(pos.get("notional_usd"))
        if value is not None:
            signed.append(value)

    gross = sum(abs(v) for v in signed)
    net = sum(signed)
    # Herfindahl index over gross weights: 1/n when evenly spread, 1.0 when a
    # single position is the whole book. Meaningful without knowing the size.
    hhi = sum((abs(v) / gross) ** 2 for v in signed) if gross > 0 else None
    return {
        "position_count": len(positions),
        "valued_position_count": len(signed),
        "long_count": sum(1 for v in signed if v > 0),
        "short_count": sum(1 for v in signed if v < 0),
        "concentration_hhi": hhi,
        "net_to_gross": _ratio(net, gross),
    }


def activity_shape(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Turnover summary from the snapshot-diff history, without any sizes."""
    kinds: dict[str, int] = {}
    symbols: set[str] = set()
    for event in history:
        if not isinstance(event, dict):
            continue
        kind = event.get("kind")
        if isinstance(kind, str) and kind:
            kinds[kind] = kinds.get(kind, 0) + 1
        symbol = event.get("symbol")
        if isinstance(symbol, str) and symbol:
            symbols.add(symbol)
    return {
        "event_count": len(history),
        "by_kind": kinds,
        "distinct_symbols": sorted(symbols),
    }


def _degraded_parts(coverage: dict[str, Any]) -> list[str]:
    """Names of collection parts that did not report ok."""
    parts = coverage.get("parts")
    if not isinstance(parts, dict):
        return []
    return sorted(name for name, status in parts.items() if status != "ok")


def redact_account_view(view: dict[str, Any]) -> dict[str, Any]:
    """Project an ``account_view()`` onto a state safe to send to a third party.

    Returns a structure that is scale-free by construction. Callers must not
    add fields to the result by hand -- extend this function instead, so the
    allowlist stays the single place a disclosure decision is made.
    """
    view = view if isinstance(view, dict) else {}
    positions = view.get("positions") or []
    orders = view.get("orders") or []
    protection = view.get("protection") or []
    history = view.get("positions_history") or []
    balances = view.get("balances") or []
    account = view.get("account") or {}
    coverage = view.get("coverage") or {}
    quality = view.get("quality") or {}
    risk = view.get("risk") or {}
    orders_meta = view.get("orders_meta") or {}

    firing = risk.get("firing") or []
    return {
        "schema": REDACTED_STATE_SCHEMA,
        "freshness": {
            "available": bool(view.get("available")),
            "stale": bool(view.get("stale")),
            "partial": bool(view.get("partial")),
            "age_seconds": view.get("age_seconds"),
            "stale_after_seconds": view.get("stale_after_seconds"),
        },
        "read_only_source": {
            "collector": (view.get("source") or {}).get("collector"),
            "read_only": (view.get("source") or {}).get("read_only"),
            "venue": (view.get("source") or {}).get("venue"),
        },
        "margin": _pick(account, _ACCOUNT_SAFE_KEYS),
        "book": {
            **book_shape(positions),
            "balance_count": len(balances),
            "liability_count": sum(
                1 for b in balances if isinstance(b, dict) and b.get("is_liability")
            ),
        },
        "positions": [_pick(p, _POSITION_SAFE_KEYS) for p in positions if isinstance(p, dict)],
        "orders": {
            "count": len(orders),
            "live_count": sum(1 for o in orders if isinstance(o, dict) and o.get("is_live")),
            "protective_count": sum(
                1 for o in orders if isinstance(o, dict) and o.get("is_protective")
            ),
            "by_status": _tally(orders, "status"),
            "by_side": _tally(orders, "side"),
            "symbols": sorted({o.get("symbol") for o in orders
                               if isinstance(o, dict) and isinstance(o.get("symbol"), str)}),
            "fully_covered": orders_meta.get("fully_covered"),
            "age_seconds": orders_meta.get("age_seconds"),
        },
        "protection": [_pick(p, _PROTECTION_SAFE_KEYS)
                       for p in protection if isinstance(p, dict)],
        "risk": {
            "firing_count": risk.get("firing_count"),
            # `value` is the rule's measured figure and can be absolute, so it
            # is dropped; rule/level/status carry the categorical signal.
            "firing": [_pick(f, _FIRING_SAFE_KEYS) for f in firing if isinstance(f, dict)],
        },
        "coverage": {
            "essential_ok": coverage.get("essential_ok"),
            "orders_covered": coverage.get("orders_covered"),
            "failure_count": len(coverage.get("failures") or []),
            "essential_failure_count": len(coverage.get("essential_failures") or []),
            "degraded_parts": _degraded_parts(coverage),
        },
        "quality": {
            "rest_ok": quality.get("rest_ok"),
            "ws_connected": quality.get("ws_connected"),
            "partial": quality.get("partial"),
            "mismatch": quality.get("mismatch"),
            "consecutive_failures": quality.get("consecutive_failures"),
            # The message itself can carry URLs and upstream identifiers, so
            # only its presence is published.
            "last_error_present": bool(quality.get("last_error")),
        },
        "activity": activity_shape(history),
        "disclaimer_present": bool(view.get("disclaimer")),
    }


def _tally(rows: list[Any], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        if isinstance(row, dict):
            value = row.get(key)
            if isinstance(value, str) and value:
                out[value] = out.get(value, 0) + 1
    return out


# --------------------------------------------------------------------------
# Proof helper
# --------------------------------------------------------------------------

#: Substrings that mark a field as an absolute quantity. Used only by the
#: assertion below and by tests -- never to filter, so that filtering stays
#: allowlist-driven.
_ABSOLUTE_MARKERS = ("_usd", "btc_equivalent", "quantity", "price", "notional")


def _is_quantity(value: Any) -> bool:
    """True when *value* is a number, or a string holding one.

    The bundle encodes every figure as a string, so a name-only check would
    miss the real leaks and flag harmless ones.
    """
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value.strip())
        except ValueError:
            return False
        return True
    return False


def assert_no_absolute_scale(state: Any, _path: str = "") -> None:
    """Raise if *state* carries a numeric field that looks absolute in scale.

    A guard rail for tests and for anyone editing the allowlist: if a numeric
    ``something_usd`` survives redaction, the projection is wrong. Names alone
    are not enough -- ``has_liquidation_price`` is a boolean and safe, while
    ``quantity_unit`` is a string and safe, but ``notional_usd: "12.5"`` is a
    leak. The redactor itself never calls this.
    """
    if isinstance(state, dict):
        for key, value in state.items():
            path = f"{_path}.{key}" if _path else key
            if any(marker in key for marker in _ABSOLUTE_MARKERS) and _is_quantity(value):
                raise AssertionError(f"absolute-scale field leaked into state: {path}={value!r}")
            assert_no_absolute_scale(value, path)
    elif isinstance(state, list):
        for index, value in enumerate(state):
            assert_no_absolute_scale(value, f"{_path}[{index}]")
