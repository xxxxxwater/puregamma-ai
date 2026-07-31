from __future__ import annotations

from datetime import timedelta

import pytest

from apps.api.dependencies import create_access_token
from apps.api.services.credit_service import (
    quote_task,
    reconcile_credit_account,
    recover_stale_reservations,
    refund_task,
    reserve_task,
    settle_task,
)
from packages.billing.budgets import AutomationBudgetExceeded, get_or_create_policy
from packages.billing.rewards import grant_reward
from packages.database.models import CreditBudgetPolicy, CreditLedger, CreditReservationRecord, CreditRewardGrant, utcnow


def test_automation_budget_hard_stops_before_second_charge(db, normal_user):
    policy = get_or_create_policy(db, normal_user, "daily_brief")
    policy.daily_limit = 4
    policy.monthly_limit = 4
    policy.per_run_limit = 4
    db.commit()

    quote = quote_task(task_type="daily_market_report")
    first = reserve_task(
        db,
        normal_user.id,
        quote,
        "budget-first-run",
        {"automation_key": "daily_brief"},
    )
    settle_task(db, normal_user.id, first, quote.credits)
    db.commit()
    balance_after_first = normal_user.credit_balance

    with pytest.raises(AutomationBudgetExceeded, match="AUTOMATION_DAILY_BUDGET"):
        reserve_task(
            db,
            normal_user.id,
            quote,
            "budget-second-run",
            {"automation_key": "daily_brief"},
        )
    db.commit()
    db.refresh(normal_user)

    assert normal_user.credit_balance == balance_after_first
    assert db.query(CreditLedger).filter_by(idempotency_key="budget-second-run").count() == 0
    persisted = db.query(CreditBudgetPolicy).filter_by(user_id=normal_user.id, automation_key="daily_brief").one()
    assert persisted.paused is True
    assert persisted.pause_reason == "AUTOMATION_DAILY_BUDGET"


def test_refunded_automation_run_does_not_consume_budget(db, normal_user):
    policy = get_or_create_policy(db, normal_user, "portfolio_monitor")
    policy.daily_limit = 4
    policy.monthly_limit = 4
    policy.per_run_limit = 4
    db.commit()
    quote = quote_task(task_type="daily_market_report")

    failed = reserve_task(
        db,
        normal_user.id,
        quote,
        "budget-refunded-run",
        {"automation_key": "portfolio_monitor"},
    )
    refund_task(db, normal_user.id, failed, "PROVIDER_FAILED")
    replacement = reserve_task(
        db,
        normal_user.id,
        quote,
        "budget-replacement-run",
        {"automation_key": "portfolio_monitor"},
    )
    db.commit()

    assert replacement.credits == quote.credits


def test_reward_is_idempotent_and_audited(db, normal_user):
    starting_balance = normal_user.credit_balance
    first = grant_reward(
        db,
        normal_user.id,
        "onboarding_portfolio_grant",
        100,
        idempotency_key="portfolio-onboarding:normal-user",
        source="portfolio_onboarding",
        metadata={"portfolio_id": "portfolio-1"},
    )
    second = grant_reward(
        db,
        normal_user.id,
        "onboarding_portfolio_grant",
        100,
        idempotency_key="portfolio-onboarding:normal-user",
        source="replayed_request",
    )
    db.commit()
    db.refresh(normal_user)

    assert first.id == second.id
    assert normal_user.credit_balance == starting_balance + 100
    assert db.query(CreditRewardGrant).count() == 1
    ledger = db.query(CreditLedger).filter_by(idempotency_key="reward:portfolio-onboarding:normal-user").one()
    assert ledger.metadata_json["source"] == "portfolio_onboarding"


def test_reward_caps_and_manual_admin_audit(db, normal_user, admin_user):
    with pytest.raises(ValueError, match="audited administrator"):
        grant_reward(
            db,
            normal_user.id,
            "manual_admin_grant",
            10,
            idempotency_key="manual-without-admin",
            source="admin_console",
        )

    grant_reward(
        db,
        normal_user.id,
        "daily_brief_feedback_grant",
        20,
        idempotency_key="feedback-one",
        source="daily_brief_feedback",
    )
    with pytest.raises(ValueError, match="Reward cap exceeded"):
        grant_reward(
            db,
            normal_user.id,
            "daily_brief_feedback_grant",
            20,
            idempotency_key="feedback-two",
            source="daily_brief_feedback",
        )

    grant = grant_reward(
        db,
        normal_user.id,
        "manual_admin_grant",
        10,
        idempotency_key="manual-with-admin",
        source="admin_console",
        granted_by_user_id=admin_user.id,
    )
    db.commit()
    assert grant.granted_by_user_id == admin_user.id


def test_ledger_reconciliation_detects_balance_drift(db, normal_user):
    quote = quote_task(task_type="default_chat")
    reservation = reserve_task(db, normal_user.id, quote, "reconciliation-run")
    settle_task(db, normal_user.id, reservation, quote.credits)
    db.commit()

    assert reconcile_credit_account(db, normal_user.id)["matches"] is True
    normal_user.credit_balance += 1
    db.flush()
    assert reconcile_credit_account(db, normal_user.id)["matches"] is False


def test_budget_and_reward_history_are_user_scoped(api_client, db, normal_user, admin_user):
    get_or_create_policy(db, normal_user, "daily_brief")
    grant_reward(
        db,
        normal_user.id,
        "onboarding_portfolio_grant",
        50,
        idempotency_key="normal-user-history",
        source="test",
    )
    grant_reward(
        db,
        admin_user.id,
        "onboarding_portfolio_grant",
        50,
        idempotency_key="admin-user-history",
        source="test",
    )
    db.commit()
    headers = {"Authorization": f"Bearer {create_access_token(normal_user)}"}

    budgets = api_client.get("/billing/budget", headers=headers)
    rewards = api_client.get("/billing/rewards", headers=headers)

    assert budgets.status_code == 200
    assert [row["automation_key"] for row in budgets.json()["budgets"]] == ["daily_brief"]
    assert rewards.status_code == 200
    assert [row["source"] for row in rewards.json()["rewards"]] == ["test"]


def test_stale_reservation_recovery_refunds_once(db, normal_user):
    starting_balance = normal_user.credit_balance
    reservation = reserve_task(
        db,
        normal_user.id,
        quote_task(task_type="default_chat"),
        "abandoned-reservation",
    )
    db.commit()
    row = db.query(CreditReservationRecord).filter_by(idempotency_key=reservation.idempotency_key).one()
    row.created_at = utcnow() - timedelta(hours=7)
    db.commit()

    assert recover_stale_reservations(db) == 1
    assert recover_stale_reservations(db) == 0
    db.refresh(normal_user)
    db.refresh(row)

    assert normal_user.credit_balance == starting_balance
    assert row.status == "REFUNDED"
