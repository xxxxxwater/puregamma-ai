from __future__ import annotations

from fastapi import HTTPException

from apps.api.config import Settings
from apps.api.dependencies import create_access_token, get_current_user
from apps.api.routers import google_auth
from apps.api.routers.auth import MockLoginRequest, mock_login
from packages.database.models import User, UserIdentity
from starlette.requests import Request
from starlette.responses import Response


def request_with_cookies(cookies: str = "") -> Request:
    return Request({"type": "http", "headers": [(b"cookie", cookies.encode())] if cookies else []})


def test_mock_login_does_not_allow_admin_escalation(db):
    response = Response()
    result = mock_login(MockLoginRequest(email="attacker@example.com", name="Attacker"), response, db)
    assert result["user"]["role"] == "user"
    assert "access_token" not in result
    assert "httponly" in response.headers["set-cookie"].lower()


def test_bearer_token_authenticates_user(db, demo_user):
    token = create_access_token(demo_user)
    user = get_current_user(request=request_with_cookies(), db=db, authorization=f"Bearer {token}")
    assert user.id == demo_user.id


def test_missing_bearer_token_denied(db):
    try:
        get_current_user(request=request_with_cookies(), db=db, authorization=None)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("Expected missing token to be denied")


def test_google_oauth_callback_registers_verified_user(api_client, db, monkeypatch):
    monkeypatch.setattr(google_auth, "get_settings", lambda: Settings(google_client_id="google-client", google_client_secret="google-secret"))
    state_holder = {"nonce": ""}
    monkeypatch.setattr(google_auth, "_exchange_code_for_token", lambda code, redirect_uri, client_id, client_secret, code_verifier: {"id_token": "id-token"})
    monkeypatch.setattr(
        google_auth,
        "_verify_google_id_token",
        lambda token, client_id: {
            "sub": "google-sub-1",
            "email": "google-user@example.com",
            "name": "Google User",
            "picture": "https://example.com/avatar.png",
            "email_verified": True,
            "iss": "https://accounts.google.com",
            "aud": client_id,
            "nonce": state_holder["nonce"],
        },
    )
    authorize = api_client.get("/auth/google/authorize")
    state_holder["nonce"] = authorize.cookies.get("pg_google_oauth_nonce")
    state = authorize.json()["state"]

    callback = api_client.get(
        f"/auth/google/callback?code=mock-code&state={state}",
        follow_redirects=False,
    )
    user = db.query(User).filter(User.email == "google-user@example.com").one()

    assert callback.status_code == 303
    assert callback.headers["location"] == "http://localhost:3000/chat"
    assert not callback.content
    assert "httponly" in callback.headers["set-cookie"].lower()
    assert user.google_user_id == "google-sub-1"
    assert user.avatar_url == "https://example.com/avatar.png"
    assert db.query(UserIdentity).filter_by(provider="google", provider_subject="google-sub-1").count() == 1


def test_google_oauth_rejects_unverified_email(api_client, monkeypatch):
    monkeypatch.setattr(google_auth, "get_settings", lambda: Settings(google_client_id="google-client", google_client_secret="google-secret"))
    state_holder = {"nonce": ""}
    monkeypatch.setattr(google_auth, "_exchange_code_for_token", lambda code, redirect_uri, client_id, client_secret, code_verifier: {"id_token": "id-token"})
    monkeypatch.setattr(google_auth, "_verify_google_id_token", lambda token, client_id: {"sub": "google-sub-2", "email": "unverified@example.com", "email_verified": False, "nonce": state_holder["nonce"]})
    authorize = api_client.get("/auth/google/authorize")
    state_holder["nonce"] = authorize.cookies.get("pg_google_oauth_nonce")
    state = authorize.json()["state"]

    callback = api_client.get(f"/auth/google/callback?code=mock-code&state={state}")

    assert callback.status_code == 400
    assert "not verified" in callback.json()["detail"]


def test_google_oauth_rejects_invalid_state(api_client, monkeypatch):
    monkeypatch.setattr(google_auth, "get_settings", lambda: Settings(google_client_id="google-client", google_client_secret="google-secret"))

    callback = api_client.get("/auth/google/callback?code=mock-code&state=forged")

    assert callback.status_code == 400
    assert "Invalid OAuth state" in callback.json()["detail"]


def test_google_oauth_repeated_login_reuses_identity(api_client, db, monkeypatch):
    monkeypatch.setattr(google_auth, "get_settings", lambda: Settings(google_client_id="google-client", google_client_secret="google-secret"))
    holder = {"nonce": ""}
    monkeypatch.setattr(google_auth, "_exchange_code_for_token", lambda code, redirect_uri, client_id, client_secret, code_verifier: {"id_token": "id-token"})
    monkeypatch.setattr(google_auth, "_verify_google_id_token", lambda token, client_id: {"sub": "stable-google-sub", "email": "stable@example.com", "name": "Stable", "email_verified": True, "nonce": holder["nonce"]})
    for _ in range(2):
        authorize = api_client.get("/auth/google/authorize")
        holder["nonce"] = authorize.cookies.get("pg_google_oauth_nonce")
        callback = api_client.get(
            f"/auth/google/callback?code=code&state={authorize.json()['state']}",
            follow_redirects=False,
        )
        assert callback.status_code == 303

    assert db.query(User).filter_by(email="stable@example.com").count() == 1
    assert db.query(UserIdentity).filter_by(provider="google", provider_subject="stable-google-sub").count() == 1


def test_logout_revokes_cookie_session(api_client):
    login = api_client.post("/auth/mock-login", json={"email": "logout@example.com", "name": "Logout"})
    assert login.status_code == 200
    assert api_client.get("/me").status_code == 200
    assert api_client.post("/auth/logout").status_code == 200
    assert api_client.get("/me").status_code == 401
