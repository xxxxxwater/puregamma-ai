from __future__ import annotations

from apps.api.config import Settings
from packages.security.passwords import hash_password, verify_password


def test_internal_admin_password_hash_round_trip():
    encoded = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password value", encoded)
    assert "correct horse" not in encoded


def test_internal_admin_login_is_hidden_when_disabled(api_client):
    response = api_client.post("/auth/internal-admin-login", json={"username": "root", "password": "anything"})
    assert response.status_code == 404


def test_internal_admin_login_requires_database_admin(api_client, admin_user, monkeypatch):
    password = "correct horse battery staple"
    settings = Settings(
        app_environment="test",
        internal_admin_login_enabled=True,
        internal_admin_username="root",
        internal_admin_user_email=admin_user.email,
        internal_admin_password_hash=hash_password(password),
    )
    monkeypatch.setattr("apps.api.routers.auth.get_settings", lambda: settings)

    rejected = api_client.post("/auth/internal-admin-login", json={"username": "root", "password": "wrong password value"})
    assert rejected.status_code == 401

    accepted = api_client.post("/auth/internal-admin-login", json={"username": "root", "password": password})
    assert accepted.status_code == 200
    assert accepted.json()["user"]["role"] == "admin"
    assert accepted.cookies.get("pg_session")
    assert api_client.get("/admin/users").status_code == 200


def test_internal_admin_login_rejects_non_admin_database_user(api_client, normal_user, monkeypatch):
    password = "correct horse battery staple"
    settings = Settings(
        app_environment="test",
        internal_admin_login_enabled=True,
        internal_admin_username="root",
        internal_admin_user_email=normal_user.email,
        internal_admin_password_hash=hash_password(password),
    )
    monkeypatch.setattr("apps.api.routers.auth.get_settings", lambda: settings)
    response = api_client.post("/auth/internal-admin-login", json={"username": "root", "password": password})
    assert response.status_code == 403
