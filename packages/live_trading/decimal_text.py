"""Wire formatting for money and quantities.

``str(Decimal)`` switches to exponent notation for small or zero values with a
fixed exponent, so a zero ``Numeric(20, 8)`` column serialised as ``"0E-8"``.
Clients render these strings verbatim (they never parse them through binary
floats), which put ``0E-8`` on the LIVE console. ``format(value, "f")`` keeps
the exact digits and scale and never uses exponent notation.
"""
from __future__ import annotations

from decimal import Decimal


def decimal_text(value: Decimal | int | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    return format(Decimal(str(value)), "f")
