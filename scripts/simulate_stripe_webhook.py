"""Simulate Stripe webhook events for local testing.

Usage:
  python scripts/simulate_stripe_webhook.py checkout_completed <user_id> <plan_name>
  python scripts/simulate_stripe_webhook.py invoice_paid <user_id> <plan_name>
  python scripts/simulate_stripe_webhook.py subscription_deleted <user_id>
  python scripts/simulate_stripe_webhook.py subscription_updated <user_id> <plan_name> <price_id>

Examples:
  python scripts/simulate_stripe_webhook.py checkout_completed demo_user_id Pro
  python scripts/simulate_stripe_webhook.py invoice_paid demo_user_id Max
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from urllib.request import Request, urlopen

API_BASE = "http://localhost:8000"
WEBHOOK_URL = f"{API_BASE}/stripe/webhook"


def make_event_id() -> str:
    return f"evt_test_{uuid.uuid4().hex[:16]}"


def make_subscription_id() -> str:
    return f"sub_test_{uuid.uuid4().hex[:12]}"


def make_invoice_id() -> str:
    return f"in_test_{uuid.uuid4().hex[:12]}"


def price_id_for_plan(plan: str) -> str:
    prices = {
        "Pro": "price_mock_pro",
        "Max": "price_mock_max",
        "Enterprise": "price_mock_enterprise",
    }
    return prices.get(plan, f"price_{plan.lower()}")


def checkout_completed(user_id: str, plan: str, customer_id: str | None = None) -> dict:
    subscription_id = make_subscription_id()
    event_id = make_event_id()
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": f"cs_test_{uuid.uuid4().hex[:16]}",
                "customer": customer_id or f"cus_test_{user_id[:8]}",
                "subscription": subscription_id,
                "payment_status": "paid",
                "metadata": {
                    "user_id": user_id,
                    "plan_name": plan,
                },
            }
        },
    }


def invoice_paid(user_id: str, plan: str, customer_id: str | None = None) -> dict:
    invoice_id = make_invoice_id()
    subscription_id = make_subscription_id()
    return {
        "id": make_event_id(),
        "type": "invoice.paid",
        "data": {
            "object": {
                "id": invoice_id,
                "customer": customer_id or f"cus_test_{user_id[:8]}",
                "subscription": subscription_id,
                "billing_reason": "subscription_cycle",
                "lines": {
                    "data": [
                        {
                            "price": {
                                "id": price_id_for_plan(plan),
                            }
                        }
                    ]
                },
            }
        },
    }


def subscription_updated(user_id: str, plan: str, price_id: str, customer_id: str | None = None) -> dict:
    return {
        "id": make_event_id(),
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": make_subscription_id(),
                "customer": customer_id or f"cus_test_{user_id[:8]}",
                "status": "active",
                "items": {
                    "data": [
                        {
                            "price": {
                                "id": price_id or price_id_for_plan(plan),
                            }
                        }
                    ]
                },
                "metadata": {
                    "plan_name": plan,
                },
                "current_period_start": int(time.time()) - 86400,
                "current_period_end": int(time.time()) + 30 * 86400,
                "cancel_at_period_end": False,
            }
        },
    }


def subscription_deleted(user_id: str, customer_id: str | None = None) -> dict:
    return {
        "id": make_event_id(),
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": make_subscription_id(),
                "customer": customer_id or f"cus_test_{user_id[:8]}",
                "status": "canceled",
            }
        },
    }


def send_event(event: dict) -> None:
    payload = json.dumps(event).encode("utf-8")
    req = Request(
        WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            print(f"OK {result}")
    except Exception as exc:
        print(f"ERROR: {exc}")
        if hasattr(exc, "read"):
            print(exc.read().decode())


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "checkout_completed":
        if len(sys.argv) < 4:
            print("Usage: simulate_stripe_webhook.py checkout_completed <user_id> <plan> [customer_id]")
            sys.exit(1)
        user_id = sys.argv[2]
        plan = sys.argv[3]
        customer_id = sys.argv[4] if len(sys.argv) > 4 else None
        event = checkout_completed(user_id, plan, customer_id)
    elif command == "invoice_paid":
        if len(sys.argv) < 4:
            print("Usage: simulate_stripe_webhook.py invoice_paid <user_id> <plan> [customer_id]")
            sys.exit(1)
        user_id = sys.argv[2]
        plan = sys.argv[3]
        customer_id = sys.argv[4] if len(sys.argv) > 4 else None
        event = invoice_paid(user_id, plan, customer_id)
    elif command == "subscription_updated":
        if len(sys.argv) < 5:
            print("Usage: simulate_stripe_webhook.py subscription_updated <user_id> <plan> <price_id> [customer_id]")
            sys.exit(1)
        user_id = sys.argv[2]
        plan = sys.argv[3]
        price_id = sys.argv[4]
        customer_id = sys.argv[5] if len(sys.argv) > 5 else None
        event = subscription_updated(user_id, plan, price_id, customer_id)
    elif command == "subscription_deleted":
        if len(sys.argv) < 3:
            print("Usage: simulate_stripe_webhook.py subscription_deleted <user_id> [customer_id]")
            sys.exit(1)
        user_id = sys.argv[2]
        customer_id = sys.argv[3] if len(sys.argv) > 3 else None
        event = subscription_deleted(user_id, customer_id)
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)

    print(f"Sending {event['type']} event (id={event['id']})...")
    send_event(event)


if __name__ == "__main__":
    main()
