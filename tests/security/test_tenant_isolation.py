from __future__ import annotations

from apps.api.services.report_service import create_daily_report
from tests.conftest import auth_headers


def test_user_cannot_read_other_users_report(api_client, db, normal_user, max_user):
    report = create_daily_report(db, max_user.id)

    response = api_client.get(f"/reports/{report.id}", headers=auth_headers(normal_user))

    assert response.status_code == 404


def test_user_cannot_read_other_users_backtest(api_client, db, pro_user, max_user):
    from apps.api.services.backtest_service import run_backtest

    run = run_backtest(db, max_user.id, "BTC momentum breakout", "BTC", {"lookback_days": 10})

    response = api_client.get(f"/backtest/{run.id}", headers=auth_headers(pro_user))

    assert response.status_code == 404
