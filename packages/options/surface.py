from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


SURFACE_TYPES = ("mark_iv", "mark_price", "gamma", "theta", "vega", "spread_pct")


def resolve_surface_value(instrument: dict, type_str: str) -> float | None:
    """Extract the Z-axis value for one instrument row."""
    if type_str == "mark_iv":
        return instrument.get("mark_iv")
    if type_str == "mark_price":
        return instrument.get("mark_price")
    greeks = instrument.get("greeks") or {}
    if type_str in ("gamma", "theta", "vega"):
        value = greeks.get(type_str, 0) or 0
        return float(value)
    if type_str == "spread_pct":
        return instrument.get("spread_pct")
    return None


def days_to_expiry(expiry: str, now: datetime | None = None) -> float:
    try:
        parsed = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return 0.0
    reference = now or datetime.now(timezone.utc)
    return max(0.0, (parsed - reference).total_seconds() / 86400)


def build_surface(chain: dict, type_str: str = "mark_iv") -> dict:
    """Build a 3D surface matrix (moneyness × DTE × value) from an option chain."""
    instruments = chain.get("instruments") or []
    based = next(
        (
            float(inst.get("underlying_price") or 0)
            for inst in instruments
            if inst.get("underlying_price")
        ),
        0.0,
    )
    if type_str not in SURFACE_TYPES:
        type_str = "mark_iv"
    rows = []
    for inst in instruments:
        strike = float(inst.get("strike") or 0)
        if strike <= 0:
            continue
        dte = days_to_expiry(inst.get("expiry", ""))
        value = resolve_surface_value(inst, type_str)
        rows.append(
            {
                "x": round(strike / based, 4) if based else strike,
                "y": round(dte, 1),
                "z": round(float(value), 6) if value is not None else 0,
                "strike": strike,
                "expiry": inst.get("expiry"),
                "instrument": inst.get("instrument"),
                "open_interest": float(inst.get("open_interest") or 0),
                "volume_24h": float(inst.get("volume_24h") or 0),
                "option_type": inst.get("option_type"),
            }
        )
    rows.sort(key=lambda row: (row["y"], row["x"]))
    return {
        "x": [row["x"] for row in rows],
        "y": [row["y"] for row in rows],
        "z": [row["z"] for row in rows],
        "type": type_str,
        "underlying_price": based,
        "rows": rows,
    }


def compute_atm_snapshot(surface: dict, dte_target: float = 30, tolerance: float = 3) -> dict[str, Any]:
    """ATM (moneyness ~1.0) implied vol at a target tenor, plus 25-delta skew."""
    rows = surface.get("rows") or []
    underlying = float(surface.get("underlying_price") or 0)
    atm = [row for row in rows if abs(row["x"] - 1.0) < 0.02]
    dte30 = next(
        (row for row in atm if abs(row["y"] - dte_target) < tolerance),
        (atm[0] if atm else None),
    )
    # 25-delta proxies: moneyness ~0.95 (put) and ~1.05 (call) within the
    # same tenor band. Falls back to the closest available strike.
    band = [row for row in rows if abs(row["y"] - dte_target) < tolerance]
    if not band:
        band = rows
    put25 = min(band, key=lambda row: abs(row["x"] - 0.95), default=None)
    call25 = min(band, key=lambda row: abs(row["x"] - 1.05), default=None)
    put_iv = float(put25["z"]) if put25 and surface["type"] == "mark_iv" else None
    call_iv = float(call25["z"]) if call25 and surface["type"] == "mark_iv" else None
    skew_pct = (put_iv - call_iv) if (put_iv is not None and call_iv is not None) else None
    return {
        "atm_iv": float(dte30["z"]) if dte30 and surface["type"] == "mark_iv" else None,
        "dte": float(dte30["y"]) if dte30 else None,
        "strike": float(dte30["strike"]) if dte30 else None,
        "put25_iv": put_iv,
        "call25_iv": call_iv,
        "skew_pct": round(skew_pct, 4) if skew_pct is not None else None,
        "underlying_price": underlying,
    }
