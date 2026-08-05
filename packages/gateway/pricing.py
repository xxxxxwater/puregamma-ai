from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from packages.gateway.contracts import GatewayUsage


TOKEN_PRICE_KEYS = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cache": "cache_tokens",
    "reasoning": "reasoning_tokens",
    "long_context": "long_context_tokens",
}
UNIT_PRICE_KEYS = {
    "image": "image_units",
    "audio": "audio_units",
    "search": "search_units",
    "upload": "upload_units",
    "download": "download_units",
    "batch": "batch_units",
}
MONEY_QUANTUM = Decimal("0.00000001")


def decimal_value(value: Any) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid price: {value!r}") from exc
    if parsed < 0:
        raise ValueError("Price cannot be negative")
    return parsed


def _default_unit(key: str) -> str:
    return "per_million_tokens" if key in TOKEN_PRICE_KEYS else "per_unit"


def normalize_official_prices(prices: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Normalize provider JSON/YAML prices without constraining future SKUs."""
    normalized: dict[str, dict[str, str]] = {}
    for raw_key, raw_value in (prices or {}).items():
        key = str(raw_key).strip().lower()
        if not key:
            continue
        value = raw_value if isinstance(raw_value, dict) else {"usd": raw_value}
        amount = value.get("usd", value.get("price"))
        if amount is None:
            continue
        normalized[key] = {
            "usd": format(decimal_value(amount), "f"),
            "unit": str(value.get("unit") or _default_unit(key)),
        }
        for field in ("description", "currency", "minimum"):
            if field in value:
                normalized[key][field] = str(value[field])
    return normalized


def final_prices(official_prices: dict[str, Any], markup_bps: int) -> dict[str, dict[str, str]]:
    if markup_bps < 0 or markup_bps > 100_000:
        raise ValueError("Markup must be between 0 and 100000 basis points")
    multiplier = Decimal("1") + Decimal(markup_bps) / Decimal("10000")
    result: dict[str, dict[str, str]] = {}
    for key, item in normalize_official_prices(official_prices).items():
        amount = (decimal_value(item["usd"]) * multiplier).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        result[key] = {**item, "usd": format(amount, "f")}
    return result


def usage_cost(prices: dict[str, Any], usage: GatewayUsage) -> Decimal:
    total = Decimal("0")
    normalized = normalize_official_prices(prices)
    for key, field in {**TOKEN_PRICE_KEYS, **UNIT_PRICE_KEYS}.items():
        item = normalized.get(key)
        amount = int(getattr(usage, field))
        # OpenAI-compatible providers normally report prompt_tokens as the
        # complete prompt and cached_tokens as a subset. Bill cache misses at
        # the input tariff and hits at the cache tariff, never both.
        if key == "input":
            amount = max(0, amount - max(0, int(usage.cache_tokens)))
        if not item or amount <= 0:
            continue
        price = decimal_value(item["usd"])
        unit = item.get("unit") or _default_unit(key)
        divisor = Decimal("1000000") if unit == "per_million_tokens" else Decimal("1")
        total += Decimal(amount) * price / divisor
    return total.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def usage_payload(usage: GatewayUsage) -> dict[str, int]:
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_tokens": usage.cache_tokens,
        "reasoning_tokens": usage.reasoning_tokens,
        "long_context_tokens": usage.long_context_tokens,
        "image_units": usage.image_units,
        "audio_units": usage.audio_units,
        "search_units": usage.search_units,
        "upload_units": usage.upload_units,
        "download_units": usage.download_units,
        "batch_units": usage.batch_units,
    }
