from __future__ import annotations

from apps.api.i18n import resolve_locale
from tests.conftest import auth_headers


def test_user_preference_locale_saved(api_client, normal_user):
    response = api_client.post("/auth/preferences/locale", json={"locale": "zh"}, headers=auth_headers(normal_user))

    assert response.status_code == 200
    assert response.json()["locale"] == "zh"
    assert normal_user.preference.locale == "zh"


def test_daily_report_accepts_locale_en(api_client, max_user):
    response = api_client.post("/reports/daily?locale=en", headers=auth_headers(max_user))

    assert response.status_code == 200
    report = response.json()["report"]
    assert report["language"] == "en"
    assert report["title"] == "PureGamma Daily Brief"


def test_daily_report_accepts_locale_zh(api_client, max_user):
    response = api_client.post("/reports/daily?locale=zh", headers=auth_headers(max_user))

    assert response.status_code == 200
    report = response.json()["report"]
    assert report["language"] == "zh"
    assert report["title"] == "PureGamma 每日简报"


def test_report_language_saved(api_client, max_user):
    response = api_client.post("/reports/event?locale=zh", json={"asset": "BTC", "event": "ETF flow update"}, headers=auth_headers(max_user))

    assert response.status_code == 200
    report = response.json()["report"]
    assert report["language"] == "zh"
    assert report["title"] == "PureGamma 事件报告：BTC"


def test_notification_delivery_locale_saved(api_client, max_user):
    response = api_client.post(
        "/notifications/send?locale=zh",
        json={"channel": "imessage", "message": "PureGamma AI 每日简报", "metadata": {"idempotency_key": "locale-imessage"}},
        headers=auth_headers(max_user),
    )

    assert response.status_code == 200
    assert response.json()["delivery"]["locale"] == "zh"


def test_invalid_locale_falls_back_to_en(max_user):
    max_user.preference.locale = "zh"

    assert resolve_locale(query_locale="fr", header_locale=None, user=max_user, cookie_locale=None) == "en"
