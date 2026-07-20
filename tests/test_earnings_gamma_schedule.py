from datetime import date

from packages.options.earnings_gamma import (
    _score_stock,
    is_us_equity_trading_day,
    refresh_earnings_candidates,
)
from packages.workers.scheduler import build_scheduler


class BrokenNewsSession:
    rolled_back = False

    def query(self, *_args, **_kwargs):
        raise RuntimeError("news database unavailable")

    def rollback(self):
        self.rolled_back = True


def test_us_equity_trading_day_excludes_weekends_and_holidays():
    assert is_us_equity_trading_day(date(2026, 7, 20)) is True
    assert is_us_equity_trading_day(date(2026, 7, 19)) is False
    assert is_us_equity_trading_day(date(2026, 7, 3)) is False
    assert is_us_equity_trading_day(date(2026, 12, 25)) is False


def test_earnings_refresh_runs_each_weekday_after_us_market_open():
    scheduler = build_scheduler()
    job = scheduler.get_job("earnings_gamma_refresh")

    assert job is not None
    assert str(job.trigger.timezone) == "America/New_York"
    assert str(job.trigger.fields[4]) == "mon-fri"
    assert str(job.trigger.fields[5]) == "9"
    assert str(job.trigger.fields[6]) == "35"


def test_news_lookup_failure_does_not_remove_candidate():
    db = BrokenNewsSession()
    candidate = _score_stock(
        {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "earnings_date": "2026-07-24",
            "sector": "Technology",
            "market_cap_category": "large",
        },
        db,
    )

    assert candidate["symbol"] == "AAPL"
    assert candidate["research_score"] > 0
    assert db.rolled_back is True


def test_refresh_stores_one_candidate_set_for_both_languages(monkeypatch):
    source = {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "earnings_date": "2026-07-24",
        "sector": "Technology",
        "market_cap_category": "large",
    }
    stored = {}
    monkeypatch.setattr(
        "packages.options.earnings_gamma._discover_earnings_stocks",
        lambda _db, _language: [source],
    )
    monkeypatch.setattr(
        "packages.options.earnings_gamma._store_candidates",
        lambda language, candidates: stored.update({language: candidates}),
    )

    candidates = refresh_earnings_candidates(BrokenNewsSession(), "en")

    assert stored["en"] == candidates
    assert stored["zh"] == candidates
