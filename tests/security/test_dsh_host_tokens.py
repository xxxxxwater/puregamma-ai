"""Per-user DSH Host tokens minted for the session broker.

Pins: the mint endpoint is off by default and needs both the broker secret and
the served user's own credential; tokens are user-scoped, short-lived,
Bearer-only and route-limited; refresh chains end at the re-auth horizon and
logout revokes them; one user's Host token never reads another user's data.
"""
from __future__ import annotations

import base64
import dataclasses
import json
import time
from pathlib import Path

import pytest

from apps.api.config import get_settings
from apps.api.dependencies import create_dsh_host_token
from tests.conftest import auth_headers

BROKER_SECRET = "b" * 40
MINT = "/internal/dsh/host-tokens"


@pytest.fixture()
def enabled(monkeypatch):
    settings = dataclasses.replace(
        get_settings(),
        dsh_multi_tenant_enabled=True,
        dsh_broker_secret=BROKER_SECRET,
        dsh_host_token_ttl_seconds=600,
        dsh_host_session_max_seconds=3600,
    )
    monkeypatch.setattr("apps.api.routers.internal.get_settings", lambda: settings)
    return settings


def claims_of(token: str) -> dict:
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def mint(api_client, user, headers=None, *, secret=BROKER_SECRET, expected=None):
    hdrs = dict(headers if headers is not None else auth_headers(user))
    if secret is not None:
        hdrs["X-PureGamma-Broker-Secret"] = secret
    return api_client.post(MINT, json={"expected_user_id": expected or user.id}, headers=hdrs)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_mint_is_disabled_by_default(api_client, normal_user):
    assert get_settings().dsh_multi_tenant_enabled is False
    assert mint(api_client, normal_user).status_code == 404


def test_mint_needs_the_broker_secret_and_the_users_own_credential(api_client, enabled, normal_user):
    assert mint(api_client, normal_user, secret=None).status_code == 403
    assert mint(api_client, normal_user, secret="x" * 40).status_code == 403
    assert mint(api_client, normal_user, headers={}).status_code == 401


def test_minted_token_is_user_scoped_short_lived_and_minimal(api_client, enabled, normal_user):
    response = mint(api_client, normal_user)
    assert response.status_code == 200
    body = response.json()
    claims = claims_of(body["token"])
    assert claims["sub"] == normal_user.id == body["user_id"]
    assert claims["aud"] == "puregamma-dsh-host" and claims["scope"] == "dsh-host"
    assert claims["exp"] - claims["iat"] <= 900
    assert "email" not in claims and "role" not in claims


def test_owner_comes_from_the_credential_not_the_request(api_client, enabled, normal_user, max_user):
    # The broker thinks it serves max_user but holds normal_user's credential.
    response = mint(api_client, normal_user, expected=max_user.id)
    assert response.status_code == 409


def test_host_token_reaches_provider_routes_but_not_credential_admin_or_account_routes(api_client, enabled, normal_user, admin_user):
    token = mint(api_client, normal_user).json()["token"]
    me = api_client.get("/me", headers=bearer(token))
    assert me.status_code == 200 and me.json()["user"]["id"] == normal_user.id
    assert api_client.get("/billing/credits", headers=bearer(token)).status_code != 403
    for method, path in [
        ("GET", "/internal/capabilities"),
        ("POST", "/gateway/keys"),
        ("DELETE", "/me"),
        ("GET", "/me/export"),
        ("POST", "/auth/logout"),
    ]:
        assert api_client.request(method, path, headers=bearer(token), json={}).status_code == 403, (method, path)
    admin_token = mint(api_client, admin_user).json()["token"]
    assert api_client.get("/admin/overview", headers=bearer(admin_token)).status_code == 403


def test_host_token_cannot_mint_a_longer_lived_credential(api_client, enabled, normal_user):
    token = mint(api_client, normal_user).json()["token"]
    # Rotation keeps the original auth_time, so it cannot extend the session.
    rotated = mint(api_client, normal_user, headers=bearer(token))
    assert rotated.status_code == 200
    assert claims_of(rotated.json()["token"])["auth_time"] == claims_of(token)["auth_time"]


def test_host_token_is_never_a_session_cookie(api_client, enabled, normal_user):
    token = mint(api_client, normal_user).json()["token"]
    api_client.cookies.set(get_settings().session_cookie_name, token)
    try:
        assert api_client.get("/me").status_code == 401
    finally:
        api_client.cookies.clear()


def test_expired_overlong_and_stale_chain_tokens_are_refused(api_client, enabled, db, normal_user):
    # Mint with the real key on a clock one hour in the past: already expired.
    original = time.time
    try:
        time.time = lambda: original() - 3600  # type: ignore[assignment]
        expired, _ = create_dsh_host_token(normal_user, ttl_seconds=60, auth_time=int(original()) - 3600)
    finally:
        time.time = original  # type: ignore[assignment]
    assert api_client.get("/me", headers=bearer(expired)).status_code == 401

    stale_chain, _ = create_dsh_host_token(normal_user, ttl_seconds=600, auth_time=int(time.time()) - 7200)
    response = mint(api_client, normal_user, headers=bearer(stale_chain))
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "DSH_HOST_REAUTH_REQUIRED"


def test_logout_revokes_host_tokens(api_client, enabled, db, normal_user):
    token = mint(api_client, normal_user).json()["token"]
    normal_user.session_version = int(normal_user.session_version or 0) + 1
    db.commit()
    assert api_client.get("/me", headers=bearer(token)).status_code == 401
    assert mint(api_client, normal_user, headers=bearer(token)).status_code == 401


def test_one_users_host_token_cannot_read_another_users_data(api_client, enabled, db, pro_user, max_user):
    from apps.api.services.backtest_service import run_backtest

    theirs = run_backtest(db, max_user.id, "BTC momentum breakout", "BTC", {"lookback_days": 10})
    mine = run_backtest(db, pro_user.id, "BTC momentum breakout", "BTC", {"lookback_days": 10})
    token = mint(api_client, pro_user).json()["token"]
    assert api_client.get(f"/backtest/{mine.id}", headers=bearer(token)).status_code == 200
    assert api_client.get(f"/backtest/{theirs.id}", headers=bearer(token)).status_code == 404
    assert api_client.get("/me", headers=bearer(token)).json()["user"]["id"] == pro_user.id


def test_host_token_allowlist_covers_the_resource_view_reads():
    # The puregammaClient gateway reads behind @puregamma/dsh-ui-research-resources
    # (research runs, artifacts, evidence, SSE progress; backtest runs and results).
    from apps.api.dependencies import dsh_host_route_allowed

    for path in [
        "/api/research/runs",
        "/api/research/runs/run-1",
        "/api/research/runs/run-1/artifacts",
        "/api/research/runs/run-1/evidence",
        "/api/research/runs/run-1/events",
        "/backtest-lab/runs",
        "/backtest-lab/runs/bt-1",
    ]:
        assert dsh_host_route_allowed("GET", path), path


def test_host_token_never_reaches_legacy_skills_routes(api_client, enabled, normal_user):
    """Skills stay refused for Host tokens, in both directions.

    The public profile does not mount @puregamma/dsh-skills-legacy-api (CI
    greps for it; DSH's native skill registry serves skills), and that
    provider needs write routes (run/import/install). Opening /skills to a
    Host token would only widen what a per-user Host may do with no consumer.
    """
    from apps.api.dependencies import dsh_host_route_allowed

    profile = json.loads((Path(__file__).resolve().parents[2] / "harness" / "profile" / "package.json").read_text())
    assert "@puregamma/dsh-skills-legacy-api" not in profile["dependencies"]
    for method, path in [("GET", "/api/skills"), ("GET", "/api/skills/runs"), ("POST", "/api/skills/x/run"), ("POST", "/api/skills/import"), ("DELETE", "/api/skills/installations/x")]:
        assert not dsh_host_route_allowed(method, path), (method, path)
    token = mint(api_client, normal_user).json()["token"]
    assert api_client.get("/api/skills", headers=bearer(token)).status_code == 403
