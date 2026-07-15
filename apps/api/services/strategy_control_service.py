from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from apps.api.services.backtest_service import run_backtest
from apps.api.services.credit_service import quote_task, refund_task, reserve_task, settle_task
from apps.api.services.entitlement_service import get_user_entitlement
from packages.database.models import (
    AgentConversation,
    NormalizedDocument,
    SignalEvent,
    StrategyActivation,
    StrategyIntent,
    StrategyRiskPolicy,
    StrategyRun,
    StrategyVersion,
    TradingAccount,
    TradingAuditLog,
    TradingStrategy,
    utcnow,
)
from packages.trading.domain.enums import ExecutionMode, IntentType
from packages.trading.policies.safety import (
    assert_execution_mode_allowed,
    confirmation_hash,
    strategy_config_hash,
)
from packages.trading.runtime_client import NautilusRuntimeClient, RuntimeUnavailable
from packages.trading.schemas.models import StrategyDraft


class StrategyControlError(RuntimeError):
    pass


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _assert_trading_entitlement(db: Session, user_id: str, action: str) -> None:
    entitlement = get_user_entitlement(db, user_id)
    if not entitlement["high_cost_tasks"]:
        raise StrategyControlError(
            f"{action} requires an active Pro, Max, or Enterprise entitlement"
        )


def _owned_strategy(db: Session, user_id: str, strategy_id: str) -> TradingStrategy:
    row = (
        db.query(TradingStrategy)
        .filter_by(id=strategy_id, user_id=user_id)
        .one_or_none()
    )
    if not row:
        raise LookupError("Strategy not found")
    return row


def _version(
    db: Session, strategy: TradingStrategy, version: int | None = None
) -> StrategyVersion:
    number = version or strategy.current_version
    row = (
        db.query(StrategyVersion)
        .filter_by(strategy_id=strategy.id, user_id=strategy.user_id, version=number)
        .one_or_none()
    )
    if not row:
        raise LookupError("Strategy version not found")
    return row


def _account(
    db: Session, user_id: str, account_id: str | None = None
) -> TradingAccount:
    query = db.query(TradingAccount).filter_by(user_id=user_id, status="ACTIVE")
    row = (
        query.filter_by(id=account_id).one_or_none()
        if account_id
        else query.filter_by(venue="MOCK", account_type="PAPER").first()
    )
    if not row:
        raise StrategyControlError("An active paper trading account is required")
    return row


def _audit(
    db: Session,
    *,
    user_id: str,
    action: str,
    status: str,
    idempotency_key: str,
    strategy_id: str | None = None,
    conversation_id: str | None = None,
    run_id: str | None = None,
    request: dict | None = None,
    result: dict | None = None,
    error: str | None = None,
) -> TradingAuditLog:
    existing = (
        db.query(TradingAuditLog)
        .filter_by(idempotency_key=idempotency_key)
        .one_or_none()
    )
    if existing:
        return existing
    row = TradingAuditLog(
        user_id=user_id,
        conversation_id=conversation_id,
        strategy_id=strategy_id,
        run_id=run_id,
        action=action,
        status=status,
        actor_type="user",
        request_json=request or {},
        result_json=result or {},
        idempotency_key=idempotency_key,
        error_message=error,
    )
    db.add(row)
    return row


def validate_draft(draft: dict) -> dict:
    parsed = StrategyDraft.model_validate(draft)
    errors: list[str] = []
    warnings: list[str] = []
    if parsed.execution_mode == ExecutionMode.LIVE:
        errors.append("LIVE execution is disabled")
    unsupported_sources = set(parsed.sentiment_sources) - {
        "rss",
        "fintwit",
        "x-twitter",
        "bloomberg",
    }
    if unsupported_sources:
        errors.append(
            f"Unsupported sentiment sources: {', '.join(sorted(unsupported_sources))}"
        )
    if not parsed.entry_rules:
        warnings.append("No entry rules have been defined")
    if not parsed.exit_rules:
        warnings.append("No exit rules have been defined")
    if parsed.leverage > 3:
        warnings.append(
            "Leverage above 3x requires additional review even in paper mode"
        )
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "draft": parsed.model_dump(mode="json"),
    }


def create_strategy(
    db: Session,
    user_id: str,
    draft_data: dict,
    *,
    conversation_id: str | None = None,
    idempotency_key: str | None = None,
) -> TradingStrategy:
    _assert_trading_entitlement(db, user_id, "strategy_generation")
    if (
        conversation_id
        and not db.query(AgentConversation)
        .filter_by(id=conversation_id, user_id=user_id)
        .one_or_none()
    ):
        raise StrategyControlError("Conversation does not belong to the current user")
    key = idempotency_key or f"strategy-create:{user_id}:{uuid.uuid4()}"
    existing = db.query(TradingAuditLog).filter_by(idempotency_key=key).one_or_none()
    if existing and existing.result_json.get("strategy_id"):
        return _owned_strategy(db, user_id, existing.result_json["strategy_id"])
    checked = validate_draft(draft_data)
    if not checked["valid"]:
        raise StrategyControlError("; ".join(checked["errors"]))
    draft = StrategyDraft.model_validate(checked["draft"])
    draft.created_by = user_id
    draft.version = 1
    payload = draft.model_dump(mode="json")
    quote = quote_task(task_type="strategy_generation")
    reservation = reserve_task(
        db,
        user_id,
        quote,
        f"strategy-charge:{key}",
        {"strategy_idempotency_key": key},
    )
    strategy = TradingStrategy(
        user_id=user_id,
        conversation_id=conversation_id,
        name=draft.name,
        description=draft.description,
        status="DRAFT",
        current_version=1,
        execution_mode=draft.execution_mode.value,
    )
    db.add(strategy)
    db.flush()
    version = StrategyVersion(
        user_id=user_id,
        strategy_id=strategy.id,
        version=1,
        draft_json=payload,
        config_hash=strategy_config_hash(payload),
        status="VALIDATED",
        created_by=user_id,
    )
    db.add(version)
    db.add(_risk_policy(user_id, strategy.id, draft))
    _audit(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        strategy_id=strategy.id,
        action="CREATE_STRATEGY",
        status="COMPLETED",
        idempotency_key=key,
        request={"draft": payload},
        result={"strategy_id": strategy.id, "version": 1},
    )
    settle_task(db, user_id, reservation, quote.credits, metadata={"strategy_id": strategy.id})
    db.commit()
    db.refresh(strategy)
    return strategy


def modify_strategy(
    db: Session,
    user_id: str,
    strategy_id: str,
    changes: dict,
    *,
    idempotency_key: str | None = None,
) -> TradingStrategy:
    _assert_trading_entitlement(db, user_id, "strategy_modification")
    strategy = _owned_strategy(db, user_id, strategy_id)
    key = idempotency_key or f"strategy-modify:{strategy_id}:{uuid.uuid4()}"
    existing = db.query(TradingAuditLog).filter_by(idempotency_key=key).one_or_none()
    if existing:
        return strategy
    current = _version(db, strategy)
    merged = {
        **current.draft_json,
        **changes,
        "version": strategy.current_version + 1,
        "created_by": user_id,
        "created_at": utcnow().isoformat(),
    }
    checked = validate_draft(merged)
    if not checked["valid"]:
        raise StrategyControlError("; ".join(checked["errors"]))
    draft = StrategyDraft.model_validate(checked["draft"])
    payload = draft.model_dump(mode="json")
    quote = quote_task(task_type="strategy_modification")
    reservation = reserve_task(
        db,
        user_id,
        quote,
        f"strategy-charge:{key}",
        {"strategy_id": strategy.id, "strategy_idempotency_key": key},
    )
    strategy.current_version = draft.version
    strategy.name = draft.name
    strategy.description = draft.description
    strategy.execution_mode = draft.execution_mode.value
    strategy.status = "DRAFT"
    db.add(
        StrategyVersion(
            user_id=user_id,
            strategy_id=strategy.id,
            version=draft.version,
            draft_json=payload,
            config_hash=strategy_config_hash(payload),
            status="VALIDATED",
            created_by=user_id,
        )
    )
    db.add(_risk_policy(user_id, strategy.id, draft))
    db.query(StrategyIntent).filter_by(
        strategy_id=strategy.id, approval_status="PENDING"
    ).update({"approval_status": "INVALIDATED", "status": "INVALIDATED"})
    _audit(
        db,
        user_id=user_id,
        strategy_id=strategy.id,
        action="MODIFY_STRATEGY",
        status="COMPLETED",
        idempotency_key=key,
        request=changes,
        result={"version": draft.version},
    )
    settle_task(db, user_id, reservation, quote.credits, metadata={"strategy_id": strategy.id, "version": draft.version})
    db.commit()
    db.refresh(strategy)
    return strategy


def preview_activation(
    db: Session,
    user_id: str,
    strategy_id: str,
    *,
    mode: str,
    account_id: str | None,
    conversation_id: str | None,
    idempotency_key: str | None = None,
) -> tuple[StrategyIntent, str]:
    _assert_trading_entitlement(db, user_id, "strategy_activation")
    resolved_mode = assert_execution_mode_allowed(mode)
    if resolved_mode not in {ExecutionMode.PAPER, ExecutionMode.SHADOW}:
        raise StrategyControlError("Only PAPER and SHADOW activation are available")
    strategy = _owned_strategy(db, user_id, strategy_id)
    version = _version(db, strategy)
    account = _account(db, user_id, account_id)
    if (
        conversation_id
        and not db.query(AgentConversation)
        .filter_by(id=conversation_id, user_id=user_id)
        .one_or_none()
    ):
        raise StrategyControlError("Conversation does not belong to the current user")
    key = (
        idempotency_key
        or f"strategy-preview:{strategy_id}:{version.version}:{resolved_mode.value}:{uuid.uuid4()}"
    )
    existing = db.query(StrategyIntent).filter_by(idempotency_key=key).one_or_none()
    if existing:
        return existing, ""
    token = f"CONFIRM STRATEGY {strategy.id} VERSION {version.version} {secrets.token_urlsafe(18)}"
    intent_type = (
        IntentType.START_PAPER_STRATEGY
        if resolved_mode == ExecutionMode.PAPER
        else IntentType.START_SHADOW_STRATEGY
    )
    intent = StrategyIntent(
        user_id=user_id,
        conversation_id=conversation_id,
        strategy_id=strategy.id,
        strategy_version=version.version,
        intent_type=intent_type.value,
        execution_mode=resolved_mode.value,
        payload_json={
            "account_id": account.id,
            "strategy": version.draft_json,
            "risk": serialize_risk_policy(
                db.query(StrategyRiskPolicy)
                .filter_by(strategy_id=strategy.id, strategy_version=version.version)
                .one()
            ),
        },
        config_hash=version.config_hash,
        idempotency_key=key,
        confirmation_required=True,
        confirmation_token_hash=confirmation_hash(token),
        approval_status="PENDING",
        status="PREVIEWED",
        expires_at=utcnow() + timedelta(minutes=15),
    )
    db.add(intent)
    _audit(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        strategy_id=strategy.id,
        action="PREVIEW_STRATEGY_ACTIVATION",
        status="PENDING_CONFIRMATION",
        idempotency_key=f"audit:{key}",
        request={"mode": resolved_mode.value, "account_id": account.id},
        result={"intent_id": intent.id, "strategy_version": version.version},
    )
    db.commit()
    db.refresh(intent)
    return intent, token


def activate_strategy(
    db: Session,
    user_id: str,
    strategy_id: str,
    intent_id: str,
    confirmation: str,
    *,
    runtime: NautilusRuntimeClient | None = None,
) -> tuple[StrategyActivation, StrategyRun]:
    _assert_trading_entitlement(db, user_id, "strategy_activation")
    strategy = _owned_strategy(db, user_id, strategy_id)
    intent = (
        db.query(StrategyIntent)
        .filter_by(id=intent_id, strategy_id=strategy.id, user_id=user_id)
        .one_or_none()
    )
    if not intent:
        raise LookupError("Activation intent not found")
    existing = (
        db.query(StrategyActivation)
        .filter_by(intent_id=intent.id, user_id=user_id)
        .one_or_none()
    )
    if existing:
        run = (
            db.query(StrategyRun)
            .filter_by(activation_id=existing.id, user_id=user_id)
            .one()
        )
        return existing, run
    if intent.approval_status != "PENDING" or intent.status != "PREVIEWED":
        raise StrategyControlError("Activation intent is no longer pending")
    if _aware(intent.expires_at) < utcnow():
        intent.approval_status = "EXPIRED"
        db.commit()
        raise StrategyControlError("Activation confirmation has expired")
    if not hmac_compare(
        intent.confirmation_token_hash or "", confirmation_hash(confirmation)
    ):
        raise StrategyControlError(
            "Explicit activation confirmation does not match the preview"
        )
    version = _version(db, strategy, intent.strategy_version)
    if (
        strategy.current_version != intent.strategy_version
        or version.config_hash != intent.config_hash
    ):
        intent.approval_status = "INVALIDATED"
        intent.status = "INVALIDATED"
        db.commit()
        raise StrategyControlError(
            "Strategy changed after preview; create a new activation preview"
        )
    assert_execution_mode_allowed(intent.execution_mode)
    account = _account(db, user_id, intent.payload_json.get("account_id"))
    permission = "paper_order" if intent.execution_mode == "PAPER" else "shadow_order"
    if not account.permissions_json.get(permission):
        raise StrategyControlError(
            f"Account does not allow {intent.execution_mode} execution"
        )
    quote = quote_task(task_type="strategy_activation", async_execution=True)
    reservation = reserve_task(
        db,
        user_id,
        quote,
        f"strategy-activation-charge:{intent.id}",
        {"intent_id": intent.id},
    )
    # Persist the reservation before the external runtime command so a process
    # failure can be reconciled and refunded instead of losing billing state.
    db.commit()
    activation = StrategyActivation(
        user_id=user_id,
        conversation_id=intent.conversation_id,
        strategy_id=strategy.id,
        strategy_version=version.version,
        intent_id=intent.id,
        execution_mode=intent.execution_mode,
        status="PENDING",
    )
    db.add(activation)
    db.flush()
    run = StrategyRun(
        user_id=user_id,
        strategy_id=strategy.id,
        strategy_version=version.version,
        account_id=account.id,
        activation_id=activation.id,
        runtime_run_id=str(uuid.uuid4()),
        execution_mode=intent.execution_mode,
        status="STARTING",
    )
    db.add(run)
    db.flush()
    client = runtime or NautilusRuntimeClient()
    payload = {
        "run_id": run.runtime_run_id,
        "strategy_id": strategy.id,
        "strategy_version": version.version,
        "account_id": account.id,
        "mode": intent.execution_mode,
        "strategy": version.draft_json,
        "risk_policy": intent.payload_json.get("risk", {}),
    }
    try:
        ack = client.command("activate", f"activation:{activation.id}", payload)
    except RuntimeUnavailable:
        db.rollback()
        refund_task(db, user_id, reservation, "STRATEGY_RUNTIME_UNAVAILABLE", metadata={"intent_id": intent.id})
        db.commit()
        raise
    if ack.get("status") in {"REJECTED", "ERROR"}:
        db.rollback()
        refund_task(db, user_id, reservation, "STRATEGY_RUNTIME_REJECTED", metadata={"intent_id": intent.id})
        db.commit()
        raise StrategyControlError(ack.get("error", "Runtime rejected activation"))
    intent.approval_status = "APPROVED"
    intent.approved_at = utcnow()
    intent.status = "EXECUTED"
    activation.status = "RUNNING"
    activation.runtime_command_id = ack.get("command_id")
    activation.runtime_ack_json = ack
    activation.activated_at = utcnow()
    run.status = "RUNNING"
    run.started_at = utcnow()
    strategy.status = "RUNNING"
    strategy.execution_mode = intent.execution_mode
    _record_source_signal(db, strategy, version, run)
    _audit(
        db,
        user_id=user_id,
        conversation_id=intent.conversation_id,
        strategy_id=strategy.id,
        run_id=run.id,
        action="ACTIVATE_STRATEGY",
        status="COMPLETED",
        idempotency_key=f"audit:activation:{activation.id}",
        request={"intent_id": intent.id, "version": version.version},
        result=ack,
    )
    settle_task(db, user_id, reservation, quote.credits, metadata={"activation_id": activation.id, "run_id": run.id})
    db.commit()
    db.refresh(activation)
    db.refresh(run)
    return activation, run


def transition_strategy(
    db: Session,
    user_id: str,
    strategy_id: str,
    action: str,
    *,
    runtime: NautilusRuntimeClient | None = None,
) -> StrategyRun:
    strategy = _owned_strategy(db, user_id, strategy_id)
    run = (
        db.query(StrategyRun)
        .filter_by(strategy_id=strategy.id, user_id=user_id)
        .order_by(StrategyRun.created_at.desc())
        .first()
    )
    if not run:
        raise StrategyControlError("No strategy runtime exists")
    if action not in {"pause", "resume", "stop"}:
        raise StrategyControlError("Unsupported strategy action")
    ack = (runtime or NautilusRuntimeClient()).command(
        action,
        f"run:{run.id}:{action}:{run.updated_at.isoformat()}",
        {"run_id": run.runtime_run_id},
    )
    if ack.get("status") == "REJECTED":
        raise StrategyControlError(ack.get("error", "Runtime rejected command"))
    status = {"pause": "PAUSED", "resume": "RUNNING", "stop": "STOPPED"}[action]
    run.status = status
    strategy.status = status
    if action == "stop":
        run.stopped_at = utcnow()
    _audit(
        db,
        user_id=user_id,
        strategy_id=strategy.id,
        run_id=run.id,
        action=f"{action.upper()}_STRATEGY",
        status="COMPLETED",
        idempotency_key=f"audit:{ack.get('command_id', uuid.uuid4())}",
        result=ack,
    )
    db.commit()
    db.refresh(run)
    return run


def run_strategy_backtest(
    db: Session, user_id: str, strategy_id: str, engine: str = "mock"
):
    strategy = _owned_strategy(db, user_id, strategy_id)
    version = _version(db, strategy)
    draft = version.draft_json
    instrument = draft["instruments"][0]
    asset = instrument.replace("USDT", "").replace("USD", "")
    return run_backtest(
        db,
        user_id,
        strategy.name,
        asset,
        draft.get("backtest_config", {}),
        engine=engine,
        strategy_id=strategy.id,
    )


def serialize_strategy(db: Session, row: TradingStrategy) -> dict:
    version = _version(db, row)
    latest_run = (
        db.query(StrategyRun)
        .filter_by(strategy_id=row.id, user_id=row.user_id)
        .order_by(StrategyRun.created_at.desc())
        .first()
    )
    return {
        "id": row.id,
        "user_id": row.user_id,
        "conversation_id": row.conversation_id,
        "name": row.name,
        "description": row.description,
        "status": row.status,
        "current_version": row.current_version,
        "execution_mode": row.execution_mode,
        "draft": version.draft_json,
        "config_hash": version.config_hash,
        "latest_run": serialize_run(latest_run) if latest_run else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def serialize_run(row: StrategyRun) -> dict:
    return {
        "id": row.id,
        "strategy_id": row.strategy_id,
        "strategy_version": row.strategy_version,
        "account_id": row.account_id,
        "runtime_run_id": row.runtime_run_id,
        "execution_mode": row.execution_mode,
        "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "stopped_at": row.stopped_at.isoformat() if row.stopped_at else None,
        "performance": row.performance_json,
        "error_code": row.error_code,
        "error_message": row.error_message,
    }


def serialize_intent(row: StrategyIntent, confirmation: str = "") -> dict:
    return {
        "id": row.id,
        "strategy_id": row.strategy_id,
        "strategy_version": row.strategy_version,
        "intent_type": row.intent_type,
        "execution_mode": row.execution_mode,
        "approval_status": row.approval_status,
        "status": row.status,
        "expires_at": row.expires_at.isoformat(),
        "payload": row.payload_json,
        "confirmation": confirmation,
        "confirmation_required": row.confirmation_required,
    }


def serialize_activation(row: StrategyActivation) -> dict:
    return {
        "id": row.id,
        "strategy_id": row.strategy_id,
        "strategy_version": row.strategy_version,
        "intent_id": row.intent_id,
        "execution_mode": row.execution_mode,
        "status": row.status,
        "runtime_command_id": row.runtime_command_id,
        "runtime_ack": row.runtime_ack_json,
        "activated_at": row.activated_at.isoformat() if row.activated_at else None,
    }


def serialize_risk_policy(row: StrategyRiskPolicy) -> dict:
    return {
        "max_position": row.max_position,
        "max_notional": row.max_notional,
        "max_leverage": row.max_leverage,
        "max_daily_loss": row.max_daily_loss,
        "max_drawdown": row.max_drawdown,
        "max_orders_per_minute": row.max_orders_per_minute,
        "reduce_only": row.reduce_only,
        "pause_opening": row.pause_opening,
        "global_kill_switch": row.global_kill_switch,
        **(row.policy_json or {}),
    }


def _risk_policy(
    user_id: str, strategy_id: str, draft: StrategyDraft
) -> StrategyRiskPolicy:
    return StrategyRiskPolicy(
        user_id=user_id,
        strategy_id=strategy_id,
        strategy_version=draft.version,
        max_position=draft.max_position,
        max_notional=draft.max_notional,
        max_leverage=draft.leverage,
        max_daily_loss=draft.max_daily_loss,
        max_drawdown=draft.max_drawdown,
        max_orders_per_minute=draft.max_orders_per_minute,
        reduce_only=draft.reduce_only,
        pause_opening=False,
        global_kill_switch=False,
        policy_json=draft.risk_policy,
    )


def _record_source_signal(
    db: Session, strategy: TradingStrategy, version: StrategyVersion, run: StrategyRun
) -> None:
    draft = version.draft_json
    asset = (
        str(draft.get("instruments", ["BTCUSDT"])[0])
        .replace("USDT", "")
        .replace("USD", "")
    )
    allowed = set(draft.get("sentiment_sources") or [])
    cutoff = utcnow() - timedelta(hours=24)
    rows = (
        db.query(NormalizedDocument)
        .filter(NormalizedDocument.created_at >= cutoff)
        .order_by(NormalizedDocument.created_at.desc())
        .limit(200)
        .all()
    )
    evidence = [
        row
        for row in rows
        if asset in (row.symbols or []) and (not allowed or row.provider in allowed)
    ][:20]
    weighted = (
        sum(row.final_score for row in evidence) / len(evidence) if evidence else 0.0
    )
    confidence = (
        min(1.0, 0.25 + len({row.provider for row in evidence}) * 0.15)
        if evidence
        else 0.1
    )
    direction = (
        "LONG" if weighted > 0.05 else "SHORT" if weighted < -0.05 else "NEUTRAL"
    )
    latest_data = max(
        (row.published_at or row.created_at for row in evidence), default=utcnow()
    )
    latest_fetch = max((row.created_at for row in evidence), default=utcnow())
    freshness = max(
        0.0, 1.0 - ((utcnow() - _aware(latest_fetch)).total_seconds() / 86400)
    )
    db.add(
        SignalEvent(
            user_id=strategy.user_id,
            strategy_id=strategy.id,
            strategy_version=version.version,
            run_id=run.id,
            source_ids=[row.id for row in evidence],
            source_urls=[row.url for row in evidence if row.url],
            data_timestamp=_aware(latest_data),
            fetch_timestamp=_aware(latest_fetch),
            freshness=freshness,
            credibility_score=sum(row.credibility_score for row in evidence)
            / len(evidence)
            if evidence
            else 0.0,
            sentiment_score=weighted,
            confidence=confidence,
            asset=asset,
            model_version=str(draft.get("model_version", "rules-v1")),
            feature_version="source-features-v1",
            signal_direction=direction,
            signal_strength=abs(weighted),
            target_position=0.0,
            execution_note="Initial evidence snapshot; does not directly create an order",
            risk_state="PENDING_STRATEGY_EVALUATION",
            raw_event_reference={
                "evidenceTypes": [
                    "reported_fact",
                    "source_opinion",
                    "puregamma_calculation",
                ],
                "sourceProviders": sorted({row.provider for row in evidence}),
            },
            idempotency_key=f"signal:activation:{run.id}",
        )
    )


def hmac_compare(left: str, right: str) -> bool:
    return secrets.compare_digest(left, right)
