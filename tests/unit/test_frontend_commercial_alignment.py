import json
from pathlib import Path

from packages.billing.plans import get_plan


ROOT = Path(__file__).resolve().parents[2]


def test_billing_copy_matches_core_server_capabilities():
    for locale in ("en", "zh"):
        copy = json.loads((ROOT / "apps" / "web" / "messages" / locale / "billing.json").read_text())
        plans = {item["name"]: item for item in copy["plans"]}

        assert str(get_plan("Pro").monthly_credits) in plans["Pro"]["credits"].replace(",", "")
        assert str(get_plan("Max").monthly_credits) in plans["Max"]["credits"].replace(",", "")
        assert "Telegram" in " ".join(plans["Pro"]["benefits"])
        assert "iMessage" in " ".join(plans["Max"]["benefits"])
        plan_copy = json.dumps(copy["plans"], ensure_ascii=False).lower()
        assert "guaranteed" not in plan_copy
        assert "保证收益" not in plan_copy
