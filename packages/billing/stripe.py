from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from apps.api.config import Settings, get_settings


ROOT = Path(__file__).resolve().parents[2]
PLAN_MAPPING_PATH = ROOT / "config" / "stripe_plan_mapping.yaml"


@lru_cache
def load_plan_mapping() -> dict[str, Any]:
    if not PLAN_MAPPING_PATH.exists():
        return {"plans": {}}
    with PLAN_MAPPING_PATH.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {"plans": {}}


def price_id_for_plan(plan_name: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    try:
        return settings.stripe_price_by_plan[plan_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported checkout plan: {plan_name}") from exc


def plan_for_price_id(price_id: str | None, settings: Settings | None = None) -> str:
    plan = plan_for_price_id_or_none(price_id, settings)
    return plan or "Free"


def plan_for_price_id_or_none(price_id: str | None, settings: Settings | None = None) -> str | None:
    settings = settings or get_settings()
    for plan, configured_price in settings.stripe_price_by_plan.items():
        if price_id and configured_price == price_id:
            return plan
    mapping = load_plan_mapping().get("plans", {})
    for plan, config in mapping.items():
        price_env = (config or {}).get("price_env")
        if price_env and price_id and os.getenv(price_env, "") == price_id:
            return plan
    return None


def payment_link_for_plan(plan_name: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    try:
        return settings.stripe_payment_link_by_plan[plan_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported checkout plan: {plan_name}") from exc


def allowed_checkout_plan(plan_name: str) -> bool:
    return plan_name in {"Pro", "Max", "Enterprise"}
