"""Integration tests for the P0-12 admin console read-only surfaces.

Every endpoint is admin-gated, serves real database rows (no fixtures), uses
limit/offset pagination, and never serializes credential material.
"""
from __future__ import annotations

from datetime import timedelta

from packages.database.models import (
    AccountSnapshot,
    AgentConversation,
    AgentMessage,
    AgentRun,
    Alert,
    AssetImpact,
    BacktestRun,
    BillingCheckoutIntent,
    CreditLedger,
    CustodyAccount,
    CustodyDeposit,
    CustodyLedgerEntry,
    CustodyReconciliation,
    CustodySubAccount,
    CustodyWithdrawal,
    DataSourceSyncRun,
    ExchangeConnection,
    LLMCallLog,
    MarketEvent,
    NotificationDelivery,
    OrderIntent,
    OrderJournal,
    PositionSnapshot,
    ReconciliationRecord,
    Report,
    ResearchAction,
    ResearchSnapshot,
    RiskDecision,
    Skill,
    SkillRun,
    SkillVersion,
    StrategyRun,
    StripeWebhookEvent,
    Subscription,
    TradingAccount,
    TradingStrategy,
    UserPortfolioImpact,
    utcnow,
)
from tests.conftest import auth_headers

SECRET_MARKER = "AKIA-TEST-CIPHERTEXT-MARKER-7f3c9d"
SECRET_REF_MARKER = "vault://secret-ref-marker-9e2b"


def _seed_operational_data(db, user) -> dict:
    """Seed one of each operational row so every admin surface has real data."""
    now = utcnow()
    seeded = {}

    snapshot = ResearchSnapshot(
        kind="intraday",
        as_of=now,
        data_cutoff_at=now,
        window_start=now - timedelta(hours=24),
        window_end=now,
        status="completed",
        health_json={"news": {"status": "ok", "last_success_at": now.isoformat(), "items": 3}},
        source_counts_json={"news": 3},
    )
    db.add(snapshot)
    db.flush()
    seeded["snapshot"] = snapshot

    events = []
    for index, (event_type, title) in enumerate(
        [("news", "BTC ETF inflows surge"), ("news", "ETH upgrade scheduled"), ("price_move", "SOL 8% intraday move")]
    ):
        event = MarketEvent(
            event_type=event_type,
            title=title,
            summary=f"summary {index}",
            source_provider="test_provider",
            source_url=f"https://example.com/{index}",
            source_published_at=now,
            collected_at=now,
            data_cutoff_at=now,
            fingerprint=f"admcon-fp-{index}",
            assets=["BTC"] if index == 0 else ["ETH"],
            direction="up",
            time_horizon="intraday",
            confidence=0.8,
            evidence_json=[],
            evidence_gaps=[],
            research_snapshot_id=snapshot.id,
            status="active",
        )
        db.add(event)
        events.append(event)
    db.flush()
    seeded["events"] = events

    impact = AssetImpact(
        event_id=events[0].id,
        symbol="BTC",
        relation_type="direct",
        direction="up",
        magnitude=4.2,
        confidence=0.7,
        horizon="intraday",
        rationale="ETF flow linkage",
    )
    db.add(impact)
    db.flush()
    seeded["impact"] = impact
    db.add(
        UserPortfolioImpact(
            user_id=user.id,
            event_id=events[0].id,
            asset_impact_id=impact.id,
            symbol="BTC",
            exposure_value=1200.0,
            exposure_weight=0.4,
            direction="up",
            confidence=0.7,
        )
    )
    db.add(
        ResearchAction(
            user_id=user.id,
            event_id=events[0].id,
            action_type="generate_report",
            title="Generate BTC brief",
            payload_json={},
            status="open",
            dedup_key="admcon-action-1",
        )
    )

    for index, (provider, model, latency, tokens) in enumerate(
        [("deepseek", "deepseek-chat", 420, 1200), ("deepseek", "deepseek-reasoner", 980, 2400), ("mock", "mock-model", 10, 100)]
    ):
        db.add(
            LLMCallLog(
                user_id=user.id,
                provider=provider,
                model=model,
                task_type="agent_answer" if index < 2 else "report",
                prompt_summary=f"call {index}",
                prompt_tokens=tokens // 2,
                completion_tokens=tokens // 2,
                total_tokens=tokens,
                estimated_cost_usd=0.01 * (index + 1),
                status="success",
                latency_ms=latency,
            )
        )

    report = Report(
        user_id=user.id,
        title="BTC Daily",
        report_type="daily_brief",
        content_markdown="# BTC",
        assets=["BTC"],
        status="completed",
        idempotency_key="admcon-report-1",
    )
    db.add(report)
    db.flush()
    seeded["report"] = report

    deliveries = [
        NotificationDelivery(
            user_id=user.id,
            channel="email",
            payload={"report_id": report.id},
            status="sent",
            idempotency_key="admcon-dlv-sent",
            attempt_count=1,
            sent_at=now,
        ),
        NotificationDelivery(
            user_id=user.id,
            channel="telegram",
            payload={},
            status="failed",
            idempotency_key="admcon-dlv-failed",
            retry_count=2,
            attempt_count=3,
            next_retry_at=now + timedelta(minutes=15),
            last_error="provider timeout",
        ),
        NotificationDelivery(
            user_id=user.id,
            channel="imessage",
            payload={},
            status="pending",
            idempotency_key="admcon-dlv-pending",
        ),
    ]
    for delivery in deliveries:
        db.add(delivery)
    seeded["deliveries"] = deliveries

    db.add(
        Alert(
            user_id=user.id,
            asset="BTC",
            message="BTC above threshold",
            severity="high",
            channel="email",
            status="sent",
            idempotency_key="admcon-alert-1",
            sent_at=now,
        )
    )

    skill = db.query(Skill).first()
    version = db.query(SkillVersion).filter(SkillVersion.skill_id == skill.id).first()
    skill_run = SkillRun(
        skill_id=skill.id,
        skill_version_id=version.id,
        user_id=user.id,
        trigger_source="manual",
        status="completed",
        evidence_json={
            "workflow": {
                "status": "completed",
                "latency_ms": 55,
                "degraded_steps": [],
                "error": None,
                "steps": [
                    {"id": "collect", "tool": "get_market_quote", "status": "ok", "latency_ms": 12, "error": None},
                    {"id": "analyze", "tool": "scan_anomalies", "status": "degraded", "latency_ms": 43, "error": {"code": "INSUFFICIENT_EVIDENCE", "message": "missing"}},
                ],
            }
        },
        usage_json={},
        credits_reserved=5,
        credits_used=4,
        trace_id="admcon-trace-1",
        idempotency_key="admcon-skillrun-1",
    )
    db.add(skill_run)
    db.flush()
    seeded["skill_run"] = skill_run
    seeded["skill_slug"] = skill.slug

    custody_account = CustodyAccount(venue="anchorage", environment="testnet", status="ACTIVE", deposit_address="addr-1")
    db.add(custody_account)
    db.flush()
    sub_account = CustodySubAccount(
        custody_account_id=custody_account.id,
        user_id=user.id,
        asset="BTC",
        available=10,
        frozen=2,
    )
    db.add(sub_account)
    db.flush()
    db.add(
        CustodyLedgerEntry(
            sub_account_id=sub_account.id,
            entry_type="deposit_confirm",
            amount=10,
            available_after=10,
            frozen_after=0,
            ref_type="deposit",
            ref_id="admcon-dep-1",
            idempotency_key="admcon-ledger-1",
        )
    )
    db.add(
        CustodyDeposit(
            sub_account_id=sub_account.id,
            asset="BTC",
            amount=10,
            tx_ref="tx-1",
            confirmations=6,
            status="credited",
            external_ref="admcon-ext-1",
        )
    )
    db.add(
        CustodyWithdrawal(
            sub_account_id=sub_account.id,
            asset="BTC",
            amount=1,
            address="bc1-test",
            status="intent",
            idempotency_key="admcon-wd-1",
        )
    )
    db.add(
        CustodyReconciliation(
            custody_account_id=custody_account.id,
            asset="BTC",
            local_available=10,
            local_frozen=2,
            external_balance=12,
            difference=0,
            status="MATCHED",
        )
    )
    seeded["custody_account"] = custody_account
    seeded["sub_account"] = sub_account

    trading_account = TradingAccount(user_id=user.id, name="Paper", venue="MOCK", account_type="PAPER", status="ACTIVE")
    db.add(trading_account)
    db.flush()
    connection = ExchangeConnection(
        user_id=user.id,
        account_id=trading_account.id,
        adapter="binance",
        environment="paper",
        status="CONNECTED",
        credential_reference=SECRET_REF_MARKER,
        credential_ciphertext=SECRET_MARKER,
        error_message=None,
    )
    db.add(connection)
    db.flush()
    seeded["connection"] = connection

    db.add(
        BacktestRun(
            user_id=user.id,
            status="completed",
            engine="vectorbt",
            strategy_name="BTC momentum",
            asset="BTC",
            credits_spent=3,
            credits_reserved=5,
            idempotency_key="admcon-bt-1",
            completed_at=now,
        )
    )

    strategy = TradingStrategy(user_id=user.id, name="BTC momentum live", status="ACTIVE", execution_mode="PAPER")
    db.add(strategy)
    db.flush()
    strategy_run = StrategyRun(
        user_id=user.id,
        strategy_id=strategy.id,
        strategy_version=1,
        runtime_run_id="admcon-runtime-1",
        execution_mode="PAPER",
        status="RUNNING",
    )
    db.add(strategy_run)
    db.flush()
    order_intent = OrderIntent(
        user_id=user.id,
        strategy_id=strategy.id,
        account_id=trading_account.id,
        instrument="BTC-USDT",
        venue="MOCK",
        direction="BUY",
        quantity=0.1,
        notional=1000.0,
        order_type="MARKET",
        execution_mode="PAPER",
        status="APPROVED",
        idempotency_key="admcon-oi-1",
        expires_at=now + timedelta(hours=1),
    )
    db.add(order_intent)
    db.flush()
    db.add(
        RiskDecision(
            user_id=user.id,
            strategy_id=strategy.id,
            order_intent_id=order_intent.id,
            decision="APPROVE",
            reasons=["within_limits"],
        )
    )
    db.add(
        OrderJournal(
            user_id=user.id,
            account_id=trading_account.id,
            strategy_id=strategy.id,
            order_intent_id=order_intent.id,
            client_order_id="admcon-co-1",
            sequence=1,
            state="FILLED",
            instrument="BTC-USDT",
            side="BUY",
            quantity=0.1,
            filled_quantity=0.1,
            remaining_quantity=0.0,
            average_price=10000.0,
            idempotency_key="admcon-oj-1",
        )
    )
    db.add(
        PositionSnapshot(
            user_id=user.id,
            account_id=trading_account.id,
            strategy_id=strategy.id,
            instrument="BTC-USDT",
            quantity=0.1,
            side="LONG",
            average_price=10000.0,
            mark_price=10100.0,
            unrealized_pnl=10.0,
        )
    )
    db.add(
        AccountSnapshot(
            user_id=user.id,
            account_id=trading_account.id,
            balance=10000.0,
            equity=10010.0,
            available_margin=9000.0,
        )
    )
    db.add(
        ReconciliationRecord(
            user_id=user.id,
            account_id=trading_account.id,
            strategy_id=strategy.id,
            status="MATCHED",
            differences_json=[],
        )
    )
    seeded["strategy"] = strategy

    db.add(
        StripeWebhookEvent(
            stripe_event_id="evt_admcon_1",
            event_type="checkout.session.completed",
            processed=False,
            raw_payload_hash="hash-1",
            error_message="signature mismatch",
        )
    )
    db.add(
        BillingCheckoutIntent(
            public_reference="admcon-intent-1",
            user_id=user.id,
            plan_name="Pro",
            checkout_mode="session",
            status="created",
        )
    )
    db.add(
        Subscription(
            user_id=user.id,
            plan_name="Pro",
            status="active",
            stripe_customer_id="cus_admcon",
            stripe_subscription_id="sub_admcon",
        )
    )

    db.add(
        DataSourceSyncRun(
            provider_id="rss",
            status="FAILED",
            trace_id="admcon-sync-1",
            idempotency_key="admcon-sync-1",
            error_message="fetch failed",
        )
    )

    conversation = AgentConversation(user_id=user.id, title="Research")
    db.add(conversation)
    db.flush()
    user_message = AgentMessage(conversation_id=conversation.id, user_id=user.id, role="user", content="hi")
    assistant_message = AgentMessage(conversation_id=conversation.id, user_id=user.id, role="assistant", content="ok")
    db.add_all([user_message, assistant_message])
    db.flush()
    db.add(
        AgentRun(
            conversation_id=conversation.id,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
            user_id=user.id,
            model="deepseek-chat",
            status="completed",
            trace_id="admcon-agent-1",
        )
    )

    db.commit()
    return seeded


def _collect_keys(payload, found=None):
    found = found if found is not None else set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            found.add(str(key).lower())
            _collect_keys(value, found)
    elif isinstance(payload, list):
        for item in payload:
            _collect_keys(item, found)
    return found


# ---------------------------------------------------------------------------
# Admin gating
# ---------------------------------------------------------------------------


def test_non_admin_forbidden_on_new_endpoints(api_client, normal_user):
    headers = auth_headers(normal_user)
    for path in (
        "/admin/overview",
        f"/admin/users/{normal_user.id}",
        "/admin/deliveries",
        "/admin/research/events",
        "/admin/research/impacts",
        "/admin/alerts",
        "/admin/skill-runs",
        "/admin/stripe/summary",
        "/admin/portfolio-sync",
        "/admin/backtests",
        "/admin/trading",
        "/admin/custody",
        "/admin/workers",
        "/admin/data-sources/health",
    ):
        response = api_client.get(path, headers=headers)
        assert response.status_code == 403, path


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


def test_overview_counts_match_seeded_rows(api_client, db, admin_user):
    _seed_operational_data(db, admin_user)
    response = api_client.get("/admin/overview", headers=auth_headers(admin_user))
    assert response.status_code == 200
    payload = response.json()
    counts = payload["counts"]
    assert counts["users"] == db.query(type(admin_user)).count()
    assert counts["reports"] == db.query(Report).count()
    assert counts["events"] == db.query(MarketEvent).count()
    assert counts["alerts"] == db.query(Alert).count()
    assert counts["deliveries_failed_24h"] == 1
    assert counts["llm_calls_24h"] == db.query(LLMCallLog).count()
    assert counts["active_strategies"] == 1
    assert counts["custody_accounts"] == 1
    assert payload["snapshot"]["kind"] == "intraday"
    news_health = next(item for item in payload["source_health"] if item["id"] == "news")
    assert news_health["research"]["status"] == "ok"
    assert news_health["items"] == 3


# ---------------------------------------------------------------------------
# User detail
# ---------------------------------------------------------------------------


def test_admin_user_detail(api_client, db, admin_user, normal_user):
    _seed_operational_data(db, normal_user)
    response = api_client.get(f"/admin/users/{normal_user.id}", headers=auth_headers(admin_user))
    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["id"] == normal_user.id
    assert payload["plan"] == normal_user.plan
    assert payload["credits"]["balance"] == normal_user.credit_balance
    assert payload["subscriptions"][0]["plan_name"] == "Pro"
    assert payload["connections"][0]["adapter"] == "binance"
    assert payload["reports"][0]["id"] is not None
    assert len(payload["deliveries"]) == 3
    assert len(payload["agent_runs"]) == 1
    missing = api_client.get("/admin/users/does-not-exist", headers=auth_headers(admin_user))
    assert missing.status_code == 404


# ---------------------------------------------------------------------------
# Reports & deliveries
# ---------------------------------------------------------------------------


def test_reports_filters_and_pagination(api_client, db, admin_user, normal_user):
    _seed_operational_data(db, normal_user)
    headers = auth_headers(admin_user)
    response = api_client.get("/admin/reports", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 20
    assert payload["offset"] == 0
    assert payload["reports"][0]["title"] == "BTC Daily"
    filtered = api_client.get("/admin/reports?status=failed", headers=headers)
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 0
    by_user = api_client.get(f"/admin/reports?user_id={normal_user.id}", headers=headers)
    assert by_user.json()["total"] == 1


def test_deliveries_filters_keys_and_pagination(api_client, db, admin_user, normal_user):
    _seed_operational_data(db, normal_user)
    headers = auth_headers(admin_user)
    response = api_client.get("/admin/deliveries", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    first_page = api_client.get("/admin/deliveries?limit=2&offset=0", headers=headers).json()
    assert len(first_page["deliveries"]) == 2
    assert first_page["total"] == 3
    second_page = api_client.get("/admin/deliveries?limit=2&offset=2", headers=headers).json()
    assert len(second_page["deliveries"]) == 1

    failed = api_client.get("/admin/deliveries?status=failed", headers=headers).json()
    assert failed["total"] == 1
    row = failed["deliveries"][0]
    for key in (
        "id",
        "user_id",
        "channel",
        "status",
        "retry_count",
        "attempt_count",
        "next_retry_at",
        "last_error",
        "created_at",
        "sent_at",
        "report_id",
    ):
        assert key in row
    assert row["retry_count"] == 2
    assert row["attempt_count"] == 3
    assert row["next_retry_at"] is not None
    assert row["last_error"] == "provider timeout"

    by_channel = api_client.get("/admin/deliveries?channel=email", headers=headers).json()
    assert by_channel["total"] == 1
    assert by_channel["deliveries"][0]["report_id"] is not None


# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------


def test_data_source_health_merges_snapshot(api_client, db, admin_user):
    _seed_operational_data(db, admin_user)
    response = api_client.get("/admin/data-sources/health", headers=auth_headers(admin_user))
    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot"]["kind"] == "intraday"
    sources = {item["id"]: item for item in payload["sources"]}
    assert "news" in sources
    assert sources["news"]["research"]["status"] == "ok"
    # Seeded DataSource rows keep their own status and appear alongside research health.
    assert any(item["category"] != "research" for item in payload["sources"])


# ---------------------------------------------------------------------------
# Research events & impacts
# ---------------------------------------------------------------------------


def test_research_events_and_impacts(api_client, db, admin_user):
    seeded = _seed_operational_data(db, admin_user)
    headers = auth_headers(admin_user)
    response = api_client.get("/admin/research/events", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    titles = {event["title"] for event in payload["events"]}
    assert "BTC ETF inflows surge" in titles
    for key in ("id", "event_type", "title", "source_provider", "assets", "status", "created_at"):
        assert key in payload["events"][0]
    assert payload["counts_by_day"], "expected counts by type/day for the last 7d"
    assert {entry["event_type"] for entry in payload["counts_by_day"]} >= {"news", "price_move"}
    assert {entry["relation_type"] for entry in payload["impacts_by_relation_type"]} == {"direct"}
    assert payload["actions_by_status"] == [{"status": "open", "count": 1}]

    by_type = api_client.get("/admin/research/events?event_type=price_move", headers=headers).json()
    assert by_type["total"] == 1
    by_symbol = api_client.get("/admin/research/events?symbol=BTC", headers=headers).json()
    assert by_symbol["total"] == 1
    page = api_client.get("/admin/research/events?limit=2&offset=2", headers=headers).json()
    assert len(page["events"]) == 1

    impacts = api_client.get("/admin/research/impacts", headers=headers).json()
    assert impacts["total"] == 1
    assert impacts["impacts"][0]["event_title"] == "BTC ETF inflows surge"
    assert impacts["impacts"][0]["relation_type"] == "direct"
    assert impacts["user_portfolio_impacts"] == 1
    direct = api_client.get("/admin/research/impacts?relation_type=macro", headers=headers).json()
    assert direct["total"] == 0
    assert seeded["impact"].id == impacts["impacts"][0]["id"]


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


def test_alerts_include_linked_deliveries(api_client, db, admin_user, normal_user):
    _seed_operational_data(db, normal_user)
    response = api_client.get("/admin/alerts", headers=auth_headers(admin_user))
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    alert = payload["alerts"][0]
    assert alert["asset"] == "BTC"
    assert alert["channel"] == "email"
    assert alert["deliveries"], "expected deliveries linked by user+channel"
    assert alert["deliveries"][0]["channel"] == "email"


# ---------------------------------------------------------------------------
# LLM calls
# ---------------------------------------------------------------------------


def test_llm_calls_filters_and_aggregates(api_client, db, admin_user):
    _seed_operational_data(db, admin_user)
    headers = auth_headers(admin_user)
    response = api_client.get("/admin/llm-calls", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["llm_calls"][0]["latency_ms"] is not None

    deepseek = api_client.get("/admin/llm-calls?provider=deepseek", headers=headers).json()
    assert deepseek["total"] == 2
    aggregates = {row["model"]: row for row in deepseek["aggregates"]}
    assert set(aggregates) == {"deepseek-chat", "deepseek-reasoner"}
    chat = aggregates["deepseek-chat"]
    assert chat["calls"] == 1
    assert chat["avg_latency_ms"] == 420.0
    assert chat["total_tokens"] == 1200
    assert chat["estimated_cost_usd"] == 0.01

    by_task = api_client.get("/admin/llm-calls?task_type=report", headers=headers).json()
    assert by_task["total"] == 1
    page = api_client.get("/admin/llm-calls?limit=1&offset=2", headers=headers).json()
    assert len(page["llm_calls"]) == 1
    assert page["total"] == 3


# ---------------------------------------------------------------------------
# Skill runs
# ---------------------------------------------------------------------------


def test_skill_runs_include_workflow_evidence(api_client, db, admin_user):
    seeded = _seed_operational_data(db, admin_user)
    headers = auth_headers(admin_user)
    response = api_client.get("/admin/skill-runs", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    row = payload["skill_runs"][0]
    assert row["skill_slug"] == seeded["skill_slug"]
    assert row["workflow"]["step_count"] == 2
    assert row["workflow"]["steps"][0]["tool"] == "get_market_quote"
    assert row["workflow"]["steps"][1]["status"] == "degraded"

    by_slug = api_client.get(f"/admin/skill-runs?slug={seeded['skill_slug']}", headers=headers).json()
    assert by_slug["total"] == 1
    by_slug_miss = api_client.get("/admin/skill-runs?slug=nope", headers=headers).json()
    assert by_slug_miss["total"] == 0
    by_status = api_client.get("/admin/skill-runs?status=failed", headers=headers).json()
    assert by_status["total"] == 0


# ---------------------------------------------------------------------------
# Stripe
# ---------------------------------------------------------------------------


def test_stripe_summary(api_client, db, admin_user, normal_user):
    _seed_operational_data(db, normal_user)
    response = api_client.get("/admin/stripe/summary", headers=auth_headers(admin_user))
    assert response.status_code == 200
    payload = response.json()
    assert payload["checkout_intents_by_status"] == [{"status": "created", "count": 1}]
    assert payload["subscriptions_by_status"] == [{"status": "active", "count": 1}]
    assert payload["subscriptions_by_plan"] == [{"plan_name": "Pro", "status": "active", "count": 1}]
    assert payload["recent_webhook_errors"][0]["error_message"] == "signature mismatch"
    alias = api_client.get("/admin/stripe/events", headers=auth_headers(admin_user))
    assert alias.status_code == 200
    assert "stripe_events" in alias.json()


# ---------------------------------------------------------------------------
# Portfolio sync
# ---------------------------------------------------------------------------


def test_portfolio_sync(api_client, db, admin_user, normal_user):
    _seed_operational_data(db, normal_user)
    response = api_client.get("/admin/portfolio-sync", headers=auth_headers(admin_user))
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    connection = payload["connections"][0]
    assert connection["adapter"] == "binance"
    assert connection["status"] == "CONNECTED"
    assert set(connection) == {
        "id",
        "user_id",
        "account_id",
        "adapter",
        "environment",
        "status",
        "last_health_at",
        "error_code",
        "error_message",
        "created_at",
        "updated_at",
    }
    assert payload["recent_sync_runs"][0]["status"] == "FAILED"


# ---------------------------------------------------------------------------
# Backtests
# ---------------------------------------------------------------------------


def test_backtests(api_client, db, admin_user, normal_user):
    _seed_operational_data(db, normal_user)
    headers = auth_headers(admin_user)
    response = api_client.get("/admin/backtests", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    row = payload["backtests"][0]
    for key in ("id", "user_id", "status", "engine", "asset", "credits_spent", "duration_seconds", "created_at"):
        assert key in row
    assert row["engine"] == "vectorbt"
    assert row["duration_seconds"] is not None
    filtered = api_client.get("/admin/backtests?asset=ETH", headers=headers).json()
    assert filtered["total"] == 0
    by_engine = api_client.get("/admin/backtests?engine=vectorbt", headers=headers).json()
    assert by_engine["total"] == 1


# ---------------------------------------------------------------------------
# Trading
# ---------------------------------------------------------------------------


def test_trading(api_client, db, admin_user, normal_user):
    seeded = _seed_operational_data(db, normal_user)
    response = api_client.get("/admin/trading", headers=auth_headers(admin_user))
    assert response.status_code == 200
    payload = response.json()
    assert payload["strategies"]["total"] == 1
    assert payload["strategies"]["items"][0]["name"] == "BTC momentum live"
    assert payload["runs"][0]["runtime_run_id"] == "admcon-runtime-1"
    assert payload["order_intents"][0]["instrument"] == "BTC-USDT"
    assert payload["risk_decisions"][0]["decision"] == "APPROVE"
    assert payload["position_snapshots"][0]["unrealized_pnl"] == 10.0
    assert payload["account_snapshots"][0]["equity"] == 10010.0
    assert payload["order_journal"][0]["state"] == "FILLED"
    assert payload["reconciliations"][0]["status"] == "MATCHED"
    assert payload["strategies"]["items"][0]["id"] == seeded["strategy"].id


# ---------------------------------------------------------------------------
# Custody
# ---------------------------------------------------------------------------


def test_custody(api_client, db, admin_user, normal_user):
    _seed_operational_data(db, normal_user)
    response = api_client.get("/admin/custody", headers=auth_headers(admin_user))
    assert response.status_code == 200
    payload = response.json()
    assert payload["accounts"][0]["venue"] == "anchorage"
    sub = payload["sub_accounts"]
    assert sub["total"] == 1
    assert sub["items"][0]["asset"] == "BTC"
    assert sub["items"][0]["available"] == 10.0
    assert sub["items"][0]["frozen"] == 2.0
    assert payload["recent_ledger"][0]["entry_type"] == "deposit_confirm"
    assert payload["deposits_by_status"] == [{"status": "credited", "count": 1}]
    assert payload["withdrawals_by_status"] == [{"status": "intent", "count": 1}]
    assert payload["recent_deposits"][0]["tx_ref"] == "tx-1"
    assert payload["recent_withdrawals"][0]["status"] == "intent"
    assert payload["reconciliations"][0]["status"] == "MATCHED"


def test_custody_empty_state_is_real_zeros(api_client, admin_user):
    response = api_client.get("/admin/custody", headers=auth_headers(admin_user))
    assert response.status_code == 200
    payload = response.json()
    assert payload["accounts"] == []
    assert payload["sub_accounts"]["total"] == 0
    assert payload["deposits_by_status"] == []


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------


def test_workers(api_client, db, admin_user):
    _seed_operational_data(db, admin_user)
    response = api_client.get("/admin/workers", headers=auth_headers(admin_user))
    assert response.status_code == 200
    payload = response.json()
    assert payload["celery"]["status"] in {"ok", "unavailable"}
    if payload["celery"]["status"] == "unavailable":
        assert payload["celery"]["reason"]
    assert isinstance(payload["queues"], dict)
    assert payload["recent_sync_failures"][0]["status"] == "FAILED"


# ---------------------------------------------------------------------------
# No-secret guarantee
# ---------------------------------------------------------------------------


def test_admin_payloads_never_expose_credentials(api_client, db, admin_user, normal_user):
    _seed_operational_data(db, normal_user)
    headers = auth_headers(admin_user)
    for path in (
        "/admin/overview",
        f"/admin/users/{normal_user.id}",
        "/admin/portfolio-sync",
        "/admin/trading",
        "/admin/custody",
        "/admin/deliveries",
        "/admin/workers",
    ):
        response = api_client.get(path, headers=headers)
        assert response.status_code == 200, path
        assert SECRET_MARKER not in response.text, path
        assert SECRET_REF_MARKER not in response.text, path
        keys = _collect_keys(response.json())
        assert not any("credential" in key or "api_key" in key or "secret" in key or "ciphertext" in key for key in keys), path
