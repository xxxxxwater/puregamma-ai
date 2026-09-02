from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from apps.api.services import daily_report_renderers
from packages.data.earnings_calendar import ProviderUnavailable
from packages.database.models import MarketEvent


def _event(
    symbol: str,
    scheduled_for: datetime,
    *,
    market_cap_billions: float,
    event_type: str = "earnings_confirmed",
) -> MarketEvent:
    if event_type == "earnings_confirmed":
        title = f"{symbol} earnings confirmed for {scheduled_for.date().isoformat()}"
        summary = (
            f"{symbol} ({symbol}) reports earnings on {scheduled_for.date().isoformat()} (time-after-hours). "
            f"Confirmed via the Nasdaq earnings calendar. EPS forecast: $1.25. Market cap: ${market_cap_billions}B."
        )
        assets = [symbol]
    else:
        title = f"CPI — {scheduled_for.date().isoformat()}"
        summary = "CPI is scheduled by the rule-based macro calendar."
        assets = []
    return MarketEvent(
        event_type=event_type,
        title=title,
        summary=summary,
        source_provider="test",
        source_published_at=scheduled_for,
        collected_at=scheduled_for - timedelta(hours=1),
        data_cutoff_at=scheduled_for - timedelta(hours=1),
        fingerprint=f"test:{event_type}:{symbol}:{scheduled_for.isoformat()}",
        assets=assets,
        status="active",
    )


def _live_row(symbol: str, scheduled_for: datetime, market_cap_billions: float) -> dict:
    return {
        "event_type": "earnings_confirmed",
        "title": f"{symbol} earnings confirmed for {scheduled_for.date().isoformat()}",
        "summary": (
            f"{symbol} ({symbol}) reports earnings on {scheduled_for.date().isoformat()} (After Market Close). "
            f"Confirmed via the Nasdaq earnings calendar. EPS forecast: $1.25. Market cap: ${market_cap_billions}B."
        ),
        "assets": [symbol],
        "source_published_at": scheduled_for,
    }


def test_us_daily_shows_only_highest_priority_earnings_and_a_remainder_count(db, demo_user, monkeypatch):
    report_day = date(2026, 9, 1)
    today = datetime(2026, 9, 1, tzinfo=timezone.utc)
    tomorrow = today + timedelta(days=1)
    live_rows = [
        *[_live_row(f"TODAY{index}", today, float(index + 1)) for index in range(7)],
        *[_live_row(f"TOMORROW{index}", tomorrow, float(index + 1)) for index in range(6)],
    ]
    monkeypatch.setattr(daily_report_renderers, "_live_confirmed_earnings", lambda *_args, **_kwargs: live_rows)
    monkeypatch.setattr(daily_report_renderers, "_earnings_gamma_section", lambda _language: ("", []))

    rendered = daily_report_renderers.render_daily_report(db, demo_user.id, "us_daily", "zh", report_day)["content_markdown"]

    assert "## 今日重点财报" in rendered
    assert "## 明日预告" in rendered
    assert "TODAY6" in rendered and "TODAY2" in rendered
    assert "TODAY1" not in rendered and "TODAY0" not in rendered
    assert "TOMORROW5" in rendered and "TOMORROW1" in rendered
    assert "TOMORROW0" not in rendered
    assert "其余 2 家见事件日历" in rendered
    assert "earnings confirmed for" not in rendered


def test_week_ahead_summarizes_each_earnings_day_without_dumping_all_symbols(db, demo_user, monkeypatch):
    report_day = date(2026, 9, 1)
    day = datetime(2026, 9, 1, tzinfo=timezone.utc)
    live_rows = []
    for index in range(6):
        live_rows.append(_live_row(f"WEEK{index}", day, float(index + 1)))
    macro_events = [
        {
            "event_type": "macro_scheduled",
            "title": f"Macro {index} — {report_day.isoformat()}",
            "summary": "",
            "assets": [],
            "source": {"published_at": day.isoformat()},
        }
        for index in range(7)
    ]
    monkeypatch.setattr(daily_report_renderers, "_live_confirmed_earnings", lambda *_args, **_kwargs: live_rows)
    monkeypatch.setattr(
        daily_report_renderers.research_event_service,
        "get_upcoming_events",
        lambda _db, days: {"events": macro_events, "as_of": day.isoformat()},
    )

    rendered = daily_report_renderers.render_daily_report(db, demo_user.id, "week_ahead_events", "zh", report_day)["content_markdown"]

    assert "## 财报节奏" in rendered
    assert "WEEK5、WEEK4、WEEK3（等 6 家）" in rendered
    assert "WEEK2" not in rendered
    assert "## 关键宏观" in rendered
    assert "其余 2 项见事件日历" in rendered


def test_us_daily_never_falls_back_to_stored_earnings_when_live_calendar_is_down(db, demo_user, monkeypatch):
    report_day = date(2026, 9, 1)
    db.add(_event("HISTORICAL", datetime(2026, 9, 1, tzinfo=timezone.utc), market_cap_billions=100))
    db.commit()
    monkeypatch.setenv("ENABLE_MOCK_MARKET_DATA", "false")
    monkeypatch.setattr(
        daily_report_renderers,
        "upcoming_confirmed_earnings",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ProviderUnavailable("Nasdaq unavailable")),
    )
    monkeypatch.setattr(daily_report_renderers, "_earnings_gamma_section", lambda _language: ("", []))

    rendered = daily_report_renderers.render_daily_report(db, demo_user.id, "us_daily", "en", report_day)["content_markdown"]

    assert "live Nasdaq earnings calendar is unavailable" in rendered
    assert "HISTORICAL" not in rendered
