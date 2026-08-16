from __future__ import annotations

from tests.conftest import auth_headers


def test_default_tier_is_silver(normal_user):
    assert normal_user.membership_tier == "silver"


def test_non_admin_cannot_change_tier(api_client, normal_user):
    response = api_client.patch(
        f"/admin/users/{normal_user.id}/tier",
        json={"tier": "gold"},
        headers=auth_headers(normal_user),
    )

    assert response.status_code == 403


def test_admin_can_upgrade_and_downgrade_tier(api_client, db, normal_user, admin_user):
    headers = auth_headers(admin_user)

    upgrade = api_client.patch(
        f"/admin/users/{normal_user.id}/tier",
        json={"tier": "gold"},
        headers=headers,
    )
    db.refresh(normal_user)

    assert upgrade.status_code == 200
    assert upgrade.json()["tier"] == "gold"
    assert upgrade.json()["previous_tier"] == "silver"
    assert normal_user.membership_tier == "gold"
    # Tier is the membership source for non-Stripe users: plan follows.
    assert normal_user.plan == "Max"

    downgrade = api_client.patch(
        f"/admin/users/{normal_user.id}/tier",
        json={"tier": "silver"},
        headers=headers,
    )
    db.refresh(normal_user)

    assert downgrade.status_code == 200
    assert downgrade.json()["tier"] == "silver"
    assert downgrade.json()["previous_tier"] == "gold"
    assert normal_user.membership_tier == "silver"
    assert normal_user.plan == "Pro"


def test_legacy_bronze_tier_rejected(api_client, normal_user, admin_user):
    response = api_client.patch(
        f"/admin/users/{normal_user.id}/tier",
        json={"tier": "bronze"},
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 400


def test_invalid_tier_rejected(api_client, normal_user, admin_user):
    response = api_client.patch(
        f"/admin/users/{normal_user.id}/tier",
        json={"tier": "platinum"},
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 400


def test_admin_cannot_change_own_tier(api_client, admin_user):
    response = api_client.patch(
        f"/admin/users/{admin_user.id}/tier",
        json={"tier": "gold"},
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 400


def test_tier_change_rejected_on_active_stripe_subscription(
    api_client, db, normal_user, admin_user
):
    from packages.database.models import Subscription

    sub = Subscription(
        user_id=normal_user.id,
        plan_name="Max",
        status="active",
        stripe_subscription_id="sub_active_1",
    )
    db.add(sub)
    normal_user.plan = "Max"
    db.commit()

    response = api_client.patch(
        f"/admin/users/{normal_user.id}/tier",
        json={"tier": "gold"},
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 409
    db.refresh(normal_user)
    assert normal_user.membership_tier == "silver"
    assert normal_user.plan == "Max"


def test_tier_change_allowed_without_subscription_and_entitlement_follows(
    api_client, db, normal_user, admin_user
):
    from apps.api.services.entitlement_service import get_user_entitlement

    response = api_client.patch(
        f"/admin/users/{normal_user.id}/tier",
        json={"tier": "gold"},
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 200

    entitlement = get_user_entitlement(db, normal_user.id)
    assert entitlement["membership_tier"] == "gold"
    assert entitlement["plan"] == "Max"
    assert entitlement["subscribed_plan"] == "Max"
    assert entitlement["effective_plan"] == "Max"


def test_past_due_subscription_keeps_free_baseline_and_tier(api_client, db, normal_user):
    from apps.api.services.entitlement_service import get_user_entitlement
    from packages.database.models import Subscription

    sub = Subscription(
        user_id=normal_user.id,
        plan_name="Max",
        status="past_due",
        stripe_subscription_id="sub_past_due_1",
    )
    db.add(sub)
    normal_user.plan = "Max"
    normal_user.membership_tier = "gold"
    db.commit()

    entitlement = get_user_entitlement(db, normal_user.id)
    assert entitlement["subscribed_plan"] == "Max"
    assert entitlement["effective_plan"] == "Free"
    assert entitlement["plan"] == "Free"
    assert entitlement["membership_tier"] == "gold"
    assert entitlement["restricted_reason"] == "payment_failed"


def test_tier_change_requires_admin_and_unknown_user_returns_404(api_client, admin_user):
    missing = api_client.patch(
        "/admin/users/does-not-exist/tier",
        json={"tier": "gold"},
        headers=auth_headers(admin_user),
    )

    assert missing.status_code == 404
