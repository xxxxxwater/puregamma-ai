"""Daily brief e-mail: Markdown rendering, the market brief from the sidecar, and the fallback."""
from __future__ import annotations

import io
import json
import urllib.error
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from apps.api.services.notification_service import send_notification
from packages.database.models import DailyBriefPreference, NotificationDelivery, utcnow
from packages.notifications import dispatcher as dispatcher_module
from packages.notifications import email as email_module
from packages.notifications import market_brief
from packages.notifications.base import NotificationResult
from packages.workers import tasks

NOW = 1_793_190_000.0
BRIEF = {
    "ok": True,
    "locale": "zh",
    "snapshot_id": 42,
    "taken_at": NOW - 300,
    "age_seconds": 300,
    "subject": "市场简报 10-29 08:30｜BTC 80,558 +0.6%｜美股资金净流入 $2.1B",
    "html": "<!DOCTYPE html><html><body><table><tr><td>市场简报</td></tr></table></body></html>",
    "text": "PureGamma AI 市场简报 · 2026-10-29 08:30 北京时间\n\n今日要点:\n- BTC 80,558",
    "parts": {"crypto": "ok", "deriv": "ok", "equity": "ok", "forecast": "ok"},
}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class FakeOpener:
    def __init__(self, *responses):
        self.responses, self.urls = list(responses), []

    def open(self, url, timeout=None):
        self.urls.append((url, timeout))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item if isinstance(item, bytes) else json.dumps(item).encode())


class FakeEmailProvider:
    calls: list = []
    channel = "email"

    def send(self, recipient, message, idempotency_key, **overrides):
        FakeEmailProvider.calls.append({"recipient": recipient, "message": message, **overrides})
        return NotificationResult(True, "email", {"mode": "smtp"})


@pytest.fixture(autouse=True)
def _clean_market_brief(monkeypatch):
    monkeypatch.setenv("MARKET_BRIEF_URL", "http://market-brief:8790/")
    monkeypatch.delenv("MARKET_BRIEF_MAX_AGE_SECONDS", raising=False)
    market_brief._cache.clear()
    market_brief._failed_at.clear()
    FakeEmailProvider.calls = []
    yield
    market_brief._cache.clear()
    market_brief._failed_at.clear()


# ----- rendering -----------------------------------------------------------------------------


def test_report_digest_markdown_is_rendered_not_shown_raw():
    digest = (
        "## BTC 日报\n**结论**：偏多，*短线*震荡。详见 https://puregamma.ai/zh/reports。\n"
        "- 资金 **净流入**\n- 费率 `0.01%`\n\n| 标的 | 涨跌 |\n|---|---|\n| BTC | +1.2% |\n\n---\n\n"
        "### 美股\n1. 第一\n2. 第二\n> 风险提示\n\na<b & \"c\""
    )
    html = email_module._text_to_html(digest)
    for raw in ("##", "**", "---", "| 标的", "`"):
        assert raw not in html
    assert '<div style="margin:18px 0 10px 0;' in html and "BTC 日报</div>" in html
    assert "<strong>结论</strong>" in html and "<em>短线</em>" in html
    assert '<a href="https://puregamma.ai/zh/reports" ' in html and "</a>。" in html
    assert html.count("<li ") == 4 and "<ul " in html and "<ol " in html
    assert "<th " in html and "<td " in html and "<hr " in html
    assert "a&lt;b &amp; &quot;c&quot;" in html


def test_branded_frame_uses_a_text_wordmark_not_an_image():
    message = email_module._build_message("a@example.com", "Line1\nLine2", "## Hi\n- one", "PureGamma AI <noreply@puregamma.ai>")
    html = message.get_payload()[-1].get_content()
    assert message["Subject"] == "Line1 Line2"
    assert "<img" not in html and "cid:" not in html
    assert "PureGamma AI</span>" in html and "<li " in html
    assert [part.get_content_type() for part in message.iter_parts()] == ["text/plain", "text/html"]


def test_prerendered_html_is_sent_as_is():
    message = email_module._build_message("a@example.com", "S", "plain", "PureGamma AI <x@y.z>", html=BRIEF["html"])
    assert message.get_payload()[-1].get_content().strip() == BRIEF["html"]
    assert message.get_payload()[0].get_content().strip() == "plain"


def test_email_provider_passes_subject_and_html(monkeypatch):
    sent = []
    monkeypatch.setattr(email_module, "get_settings", lambda: SimpleNamespace(smtp_host="smtp.example.com", smtp_user="noreply@puregamma.ai"))
    monkeypatch.setattr(email_module, "_deliver", sent.append)
    result = email_module.EmailProvider().send("a@example.com", "plain", "key-1", email_subject="Brief", email_html=BRIEF["html"])
    assert result.ok and result.response == {"mode": "smtp", "branded": True, "html": "provided"}
    assert sent[0]["Subject"] == "Brief" and sent[0].get_payload()[-1].get_content().strip() == BRIEF["html"]
    email_module.EmailProvider().send("a@example.com", "plain", "key-2")
    assert sent[1]["Subject"] == "PureGamma AI"


# ----- fetching the market brief ------------------------------------------------------------------


def test_fetch_validates_caches_and_maps_locale():
    opener = FakeOpener(BRIEF)
    brief = market_brief.fetch_market_brief("zh-CN", now=NOW, opener=opener)
    assert brief["subject"] == BRIEF["subject"] and brief["html"] == BRIEF["html"] and brief["snapshot_id"] == 42
    assert opener.urls == [("http://market-brief:8790/brief?locale=zh", 8.0)]
    assert market_brief.fetch_market_brief("zh", now=NOW + 60, opener=opener) == brief  # cached, no new request
    assert len(opener.urls) == 1


def test_fetch_is_off_without_url(monkeypatch):
    monkeypatch.setenv("MARKET_BRIEF_URL", "")
    assert market_brief.fetch_market_brief("en", now=NOW, opener=FakeOpener()) is None


@pytest.mark.parametrize(
    "response",
    [
        urllib.error.HTTPError("http://market-brief:8790/brief", 503, "no snapshot", {}, io.BytesIO(b"{}")),
        urllib.error.URLError("connection refused"),
        b"not json",
        {"ok": False, "error": "no snapshot yet"},
        dict(BRIEF, html=""),
        dict(BRIEF, subject=None),
        dict(BRIEF, taken_at="yesterday"),
        dict(BRIEF, html="x" * (market_brief.MAX_HTML_BYTES + 1)),
    ],
)
def test_fetch_failures_fall_back_and_back_off(response):
    opener = FakeOpener(response, BRIEF)
    assert market_brief.fetch_market_brief("en", now=NOW, opener=opener) is None
    assert market_brief.fetch_market_brief("en", now=NOW + 30, opener=opener) is None  # backoff: no new request
    assert len(opener.urls) == 1
    assert market_brief.fetch_market_brief("en", now=NOW + 61, opener=opener)["snapshot_id"] == 42


def test_stale_brief_is_not_used(monkeypatch):
    monkeypatch.setenv("MARKET_BRIEF_MAX_AGE_SECONDS", "600")
    assert market_brief.fetch_market_brief("zh", now=NOW, opener=FakeOpener(dict(BRIEF, taken_at=NOW - 601))) is None


def test_cli_check_preview_and_single_address_test_send(monkeypatch, tmp_path, capsys):
    sent = []
    monkeypatch.setattr(market_brief, "_opener", FakeOpener(BRIEF, dict(BRIEF, locale="en"), BRIEF))
    monkeypatch.setattr(email_module, "send_email", lambda *args, **kwargs: sent.append((args, kwargs)) or True)
    assert market_brief.main(["--preview", str(tmp_path / "brief.html")]) == 0
    assert (tmp_path / "brief-zh.html").read_text(encoding="utf-8") == BRIEF["html"]
    assert (tmp_path / "brief-en.html").exists()
    assert market_brief.main(["--test-send", "me@example.com", "--locale", "zh"]) == 0
    (address, subject, text), kwargs = sent[0]
    assert (address, subject, text, kwargs["html"]) == ("me@example.com", "[测试] " + BRIEF["subject"], BRIEF["text"], BRIEF["html"])
    with pytest.raises(SystemExit):
        market_brief.main(["--test-send", "a@example.com, b@example.com"])
    assert "subject:" in capsys.readouterr().out


# ----- dispatcher and the daily brief orchestrator -------------------------------------------------


def test_dispatcher_hands_email_overrides_to_the_provider_only(monkeypatch, db, demo_user):
    monkeypatch.setattr(dispatcher_module, "EmailProvider", FakeEmailProvider)
    delivery = send_notification(
        db, demo_user.id, "email", "plain text",
        {"idempotency_key": "brief-override-1", "email_subject": "Subject", "email_html": BRIEF["html"]},
    )
    assert delivery.status == "sent"
    assert FakeEmailProvider.calls == [
        {"recipient": demo_user.email, "message": "plain text", "email_subject": "Subject", "email_html": BRIEF["html"]}
    ]
    assert delivery.payload == {"message": "plain text"}  # the HTML is not stored per delivery


def _due_preference(db, user, locale):
    db.add(
        DailyBriefPreference(
            user_id=user.id,
            enabled=True,
            channel="email",
            locale=locale,
            timezone="UTC",
            local_time="08:30",
            next_delivery_at=utcnow() - timedelta(minutes=1),
            recipient=user.email,
        )
    )
    db.commit()


def test_daily_brief_email_uses_the_market_brief(monkeypatch, db, demo_user):
    monkeypatch.setattr(dispatcher_module, "EmailProvider", FakeEmailProvider)
    monkeypatch.setattr(tasks, "fetch_market_brief", lambda locale: dict(BRIEF, locale=locale))
    _due_preference(db, demo_user, "zh")

    result = tasks._orchestrate_due_daily_briefs(db)

    assert result["due"] == 1 and result["failed"] == 0
    assert len(FakeEmailProvider.calls) == 1
    call = FakeEmailProvider.calls[0]
    assert (call["message"], call["email_subject"], call["email_html"]) == (BRIEF["text"], BRIEF["subject"], BRIEF["html"])
    delivery = db.query(NotificationDelivery).filter(NotificationDelivery.idempotency_key.like("daily-brief:%:email:combined:%")).one()
    assert delivery.status == "sent" and delivery.payload["message"] == BRIEF["text"]
    # The personalised reports are still generated and land in the web inbox as before.
    assert db.query(NotificationDelivery).filter_by(user_id=demo_user.id, channel="web").count() >= 1


def test_daily_brief_email_falls_back_to_the_report_digest(monkeypatch, db, demo_user):
    monkeypatch.setattr(dispatcher_module, "EmailProvider", FakeEmailProvider)
    monkeypatch.setattr(tasks, "fetch_market_brief", lambda locale: None)
    _due_preference(db, demo_user, "en")

    tasks._orchestrate_due_daily_briefs(db)

    call = FakeEmailProvider.calls[0]
    today = utcnow().date()
    assert call["email_subject"] == f"PureGamma AI Daily Brief · {today:%b} {today.day}"
    assert "email_html" not in call and call["message"].strip()


def test_fallback_subjects():
    assert tasks._daily_brief_subject("zh", date(2026, 10, 29)) == "PureGamma AI 每日简报 · 10月29日"
    assert tasks._daily_brief_subject("en", date(2026, 10, 9)) == "PureGamma AI Daily Brief · Oct 9"
