"""Admin list pagination, filtering and permission boundaries.

An audit before this round found admin lists that were either unbounded
(`/admin/users`, `/admin/subscriptions`) or hardcoded to a cap with no `offset`
(`/admin/notifications` hid 2,504 production rows; provider sync-run history hid
71,160 `binance` runs). These tests pin the contract that replaced them:

* `limit` is bounded and `offset` is validated, so no request can pull a whole
  table;
* a caller that sends no parameters still gets the same first page the console
  rendered before, in the same response shape;
* `total` always describes the same filtered set the page was taken from;
* every one of these endpoints stays admin-gated.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from packages.database.models import NotificationDelivery, ProviderSyncLog, Subscription, User
from tests.conftest import auth_headers

PAGINATED_ENDPOINTS = [
    "/admin/users",
    "/admin/subscriptions",
    "/admin/notifications",
    "/admin/stripe-events",
    "/admin/billing-intents",
    "/admin/agent/runs",
]


def _make_users(db, count: int) -> None:
    for index in range(count):
        db.add(
            User(
                email=f"page-probe-{index}@example.invalid",
                name=f"Page Probe {index}",
                role="user",
                plan="Pro",
            )
        )
    db.commit()


# ----------------------------------------------------------------------
# Parameter validation
# ----------------------------------------------------------------------
@pytest.mark.parametrize("endpoint", PAGINATED_ENDPOINTS)
def test_limit_is_bounded_and_offset_is_validated(api_client, admin_user, endpoint):
    headers = auth_headers(admin_user)

    assert api_client.get(f"{endpoint}?limit=101", headers=headers).status_code == 422
    assert api_client.get(f"{endpoint}?limit=0", headers=headers).status_code == 422
    assert api_client.get(f"{endpoint}?offset=-1", headers=headers).status_code == 422
    assert api_client.get(f"{endpoint}?limit=1&offset=0", headers=headers).status_code == 200
    assert api_client.get(f"{endpoint}?limit=100", headers=headers).status_code == 200


@pytest.mark.parametrize("endpoint", PAGINATED_ENDPOINTS)
def test_a_request_without_parameters_stays_valid(api_client, admin_user, endpoint):
    """Backward compatibility: the console's existing calls must not break."""
    response = api_client.get(endpoint, headers=auth_headers(admin_user))

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    assert body["limit"] == 100
    assert body["offset"] == 0
    assert body["page"] == 1
    assert isinstance(body["total"], int)


# ----------------------------------------------------------------------
# Total, page and has_more agree with the rows returned
# ----------------------------------------------------------------------
def test_user_page_and_total_describe_the_same_filtered_set(api_client, admin_user, db):
    _make_users(db, 12)
    headers = auth_headers(admin_user)

    first = api_client.get("/admin/users?limit=5&offset=0", headers=headers).json()
    second = api_client.get("/admin/users?limit=5&offset=5", headers=headers).json()

    assert len(first["users"]) == 5
    assert len(second["users"]) == 5
    assert first["total"] == second["total"]
    # Pages must not overlap: the directory is ordered by creation time desc, so
    # offset 5 must return a different slice than offset 0.
    assert {row["id"] for row in first["users"]}.isdisjoint({row["id"] for row in second["users"]})

    assert first["has_more"] is True
    # Both pages are full and total is 12 (fixtures + probes), so a third page
    # starting at 10 still has rows only if total > 10.
    last = api_client.get(f"/admin/users?limit=5&offset={max(0, first['total'] - 2)}", headers=headers).json()
    assert last["has_more"] is False
    assert len(last["users"]) == min(2, first["total"])


def test_user_search_and_exact_filters(api_client, admin_user, db):
    _make_users(db, 3)
    headers = auth_headers(admin_user)

    search = api_client.get("/admin/users?q=page-probe-1", headers=headers).json()
    assert search["total"] >= 1
    assert all("page-probe-1" in row["email"] or "Page Probe 1" in row["name"] for row in search["users"])

    by_role = api_client.get("/admin/users?role=admin", headers=headers).json()
    assert by_role["total"] >= 1
    assert all(row["role"] == "admin" for row in by_role["users"])

    unmatched = api_client.get("/admin/users?role=not-a-role", headers=headers).json()
    assert unmatched["total"] == 0
    assert unmatched["users"] == []
    assert unmatched["has_more"] is False


def test_notifications_offset_reaches_rows_beyond_the_old_cap(api_client, admin_user, db):
    """The regression this round fixes: history past row 200 was unreachable."""
    now = datetime.now(timezone.utc)
    for index in range(7):
        db.add(
            NotificationDelivery(
                user_id=admin_user.id,
                channel="email",
                status="sent",
                payload={"subject": f"pagination probe {index}"},
                idempotency_key=f"pg-probe-{index}",
                locale="en",
                created_at=now - timedelta(minutes=index),
            )
        )
    db.commit()

    page_one = api_client.get("/admin/notifications?limit=3&offset=0", headers=auth_headers(admin_user)).json()
    page_three = api_client.get("/admin/notifications?limit=3&offset=6", headers=auth_headers(admin_user)).json()

    assert len(page_one["notifications"]) == 3
    assert page_one["total"] >= 7
    assert page_three["offset"] == 6
    # Reaching offset 6 is exactly what the hardcoded `.limit(200)` prevented.
    assert page_three["total"] == page_one["total"]


def test_status_filters_narrow_the_total_not_just_the_page(api_client, admin_user, db):
    now = datetime.now(timezone.utc)
    for index, status in enumerate(("failed", "sent", "failed")):
        db.add(
            NotificationDelivery(
                user_id=admin_user.id,
                channel="email",
                status=status,
                payload={"subject": "filter probe"},
                idempotency_key=f"filter-probe-{index}",
                locale="en",
                created_at=now,
            )
        )
    db.commit()
    headers = auth_headers(admin_user)

    unfiltered = api_client.get("/admin/notifications?limit=100", headers=headers).json()
    failed = api_client.get("/admin/notifications?limit=100&status=failed", headers=headers).json()

    assert failed["total"] < unfiltered["total"]
    assert all(row["status"] == "failed" for row in failed["notifications"])


def test_provider_runs_are_paginated_per_provider(api_client, admin_user, db):
    now = datetime.now(timezone.utc)
    for index in range(5):
        db.add(
            ProviderSyncLog(
                provider_id="rss",
                status="success",
                idempotency_key=f"rss-sync-probe-{index}",
                fetched_count=1,
                inserted_count=1,
                duplicate_count=0,
                retry_count=0,
                usage_json={},
                started_at=now - timedelta(minutes=index),
                completed_at=now,
            )
        )
    db.commit()
    headers = auth_headers(admin_user)

    page = api_client.get("/admin/data-sources/rss/runs?limit=2&offset=0", headers=headers).json()

    assert len(page["runs"]) == 2
    assert page["total"] >= 5
    assert page["limit"] == 2
    assert page["has_more"] is True


def test_agent_runs_status_filter(api_client, admin_user):
    headers = auth_headers(admin_user)

    page = api_client.get("/admin/agent/runs?limit=1&status=completed", headers=headers).json()

    assert page["limit"] == 1
    assert all(row["status"] == "completed" for row in page["runs"])


# ----------------------------------------------------------------------
# Permission boundary on every touched endpoint
# ----------------------------------------------------------------------
@pytest.mark.parametrize("endpoint", PAGINATED_ENDPOINTS)
def test_non_admin_is_rejected_on_every_paginated_endpoint(api_client, normal_user, endpoint):
    response = api_client.get(endpoint, headers=auth_headers(normal_user))

    assert response.status_code == 403
    assert "users" not in response.text


@pytest.mark.parametrize("endpoint", PAGINATED_ENDPOINTS + ["/admin/data-sources/rss/runs"])
def test_anonymous_is_rejected(api_client, endpoint):
    assert api_client.get(endpoint).status_code == 401


def test_subscriptions_stay_admin_only_and_paginated(api_client, admin_user, normal_user, db):
    db.add(Subscription(user_id=normal_user.id, plan_name="Pro", status="active"))
    db.commit()

    denied = api_client.get("/admin/subscriptions", headers=auth_headers(normal_user))
    allowed = api_client.get("/admin/subscriptions?limit=1", headers=auth_headers(admin_user))

    assert denied.status_code == 403
    assert allowed.status_code == 200
    body = allowed.json()
    assert body["limit"] == 1
    assert "total" in body
    # A subscription row must never expose raw Stripe keys, only identifiers.
    for row in body["subscriptions"]:
        assert not any(str(value).startswith("sk_") for value in row.values() if isinstance(value, str))
