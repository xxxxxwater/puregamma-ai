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

    downgrade = api_client.patch(
        f"/admin/users/{normal_user.id}/tier",
        json={"tier": "bronze"},
        headers=headers,
    )
    db.refresh(normal_user)

    assert downgrade.status_code == 200
    assert downgrade.json()["tier"] == "bronze"
    assert downgrade.json()["previous_tier"] == "gold"
    assert normal_user.membership_tier == "bronze"


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


def test_tier_change_requires_admin_and_unknown_user_returns_404(api_client, admin_user):
    missing = api_client.patch(
        "/admin/users/does-not-exist/tier",
        json={"tier": "gold"},
        headers=auth_headers(admin_user),
    )

    assert missing.status_code == 404
