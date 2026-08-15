"""Feature gate evaluation for LIVE trading.

LIVE can never be enabled by a single environment variable. The static gate
combines environment variables and deployment markers; the full gate
additionally requires DB-backed conditions (user approval, mandate approval,
broker connection health, kill switches, reconciliation health) which are
evaluated in ``evaluate_full_gate``.

Any condition failing keeps the system in LIVE_DISABLED state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.database.models import (
    BrokerConnection,
    LiveUserApproval,
    TradingKillSwitch,
    TradingMandate,
    TradingReconciliation,
    utcnow,
)


@dataclass
class GateResult:
    enabled: bool
    checks: dict[str, dict[str, Any]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "state": "LIVE_ENABLED" if self.enabled else "LIVE_DISABLED",
            "checks": self.checks,
        }


def _check(name: str, ok: bool, detail: Any = "") -> dict[str, Any]:
    return {"ok": bool(ok), "detail": detail}


def evaluate_static_gate() -> GateResult:
    """Environment/deployment-level gate. No database access.

    Withdrawal and transfer flags are checked as denial conditions: if either
    is ever true, LIVE is refused outright.
    """
    settings = get_settings()
    enabled_flag = settings.live_trading_enabled
    deployment_approved = settings.live_trading_deployment_approved
    provider = bool(settings.live_trading_provider)
    withdrawal_forbidden = not settings.nautilus_allow_withdrawal
    transfer_forbidden = not settings.nautilus_allow_transfer
    live_order_flag_off = not settings.nautilus_allow_live_order
    # The runtime legacy LIVE env flag must stay false: live submission flows
    # through this control plane, not through the old runtime toggle.
    legacy_runtime_live_off = not settings.nautilus_live_trading_enabled

    checks = {
        "live_trading_enabled": _check(
            "LIVE_TRADING_ENABLED=true", enabled_flag, settings.live_trading_enabled
        ),
        "deployment_approved": _check(
            "deployment marker approved", deployment_approved,
            settings.live_trading_deployment_approved,
        ),
        "provider_configured": _check(
            "LIVE_TRADING_PROVIDER set", provider, settings.live_trading_provider,
        ),
        "withdrawal_disabled": _check(
            "withdrawal must remain disabled", withdrawal_forbidden,
        ),
        "transfer_disabled": _check(
            "transfer must remain disabled", transfer_forbidden,
        ),
        "legacy_runtime_live_off": _check(
            "NAUTILUS_LIVE_TRADING_ENABLED must stay false", legacy_runtime_live_off,
        ),
        "legacy_live_order_off": _check(
            "NAUTILUS_ALLOW_LIVE_ORDER must stay false", live_order_flag_off,
        ),
    }
    enabled = enabled_flag and deployment_approved and withdrawal_forbidden and transfer_forbidden and legacy_runtime_live_off and live_order_flag_off
    return GateResult(enabled=enabled, checks=checks)


def _global_kill_switch_active(db: Session) -> bool:
    return (
        db.query(TradingKillSwitch)
        .filter_by(scope="global", state="active")
        .first()
        is not None
    )


def _scope_kill_switch_active(db: Session, scope: str, scope_id: str | None) -> bool:
    if not scope_id:
        return False
    return (
        db.query(TradingKillSwitch)
        .filter_by(scope=scope, scope_id=scope_id, state="active")
        .first()
        is not None
    )


def _reconciliation_healthy(db: Session, user_id: str, account_id: str | None) -> bool:
    """Latest reconciliation for the account must not be a discrepancy."""
    query = db.query(TradingReconciliation).filter_by(user_id=user_id)
    if account_id:
        query = query.filter_by(account_id=account_id)
    latest = query.order_by(TradingReconciliation.created_at.desc()).first()
    return latest is None or latest.status == "ok"


def evaluate_full_gate(
    db: Session,
    user_id: str,
    mandate: TradingMandate | None = None,
    connection: BrokerConnection | None = None,
) -> GateResult:
    """Full per-user/per-mandate gate. The control plane must refuse any
    submission when ``enabled`` is False and surface the failing checks."""
    static = evaluate_static_gate()
    checks = dict(static.checks)

    approval = (
        db.query(LiveUserApproval).filter_by(user_id=user_id).one_or_none()
    )
    user_approved = approval is not None and approval.status == "approved"
    checks["user_live_approved"] = _check(
        "user passed LIVE eligibility review",
        user_approved,
        approval.status if approval else "no approval row",
    )

    checks["kill_switch_global"] = _check(
        "global kill switch off", not _global_kill_switch_active(db),
    )
    checks["kill_switch_user"] = _check(
        "user kill switch off", not _scope_kill_switch_active(db, "user", user_id),
    )

    mandate_ok = True
    if mandate is not None:
        mandate_approved = mandate.approval_status == "approved" and not mandate.paused
        mandate_live = mandate.execution_mode == "live" and mandate.environment == "production"
        mandate_active = mandate.status in {"active", "draft"} and not (
            mandate.revoked_at or (mandate.expires_at and mandate.expires_at < utcnow())
        )
        checks["mandate_approved"] = _check(
            "mandate approved and not paused", mandate_approved,
            f"approval={mandate.approval_status} paused={mandate.paused}",
        )
        checks["mandate_live_mode"] = _check(
            "mandate execution_mode=live environment=production", mandate_live,
            f"{mandate.execution_mode}/{mandate.environment}",
        )
        checks["mandate_status_active"] = _check(
            "mandate lifecycle active", mandate_active, mandate.status,
        )
        checks["mandate_kill_switch"] = _check(
            "mandate kill switch inactive",
            mandate.kill_switch_state != "active"
            and not _scope_kill_switch_active(db, "mandate", mandate.id),
        )
        connection_id = mandate.broker_connection_id
        checks["connection_kill_switch"] = _check(
            "connection kill switch inactive",
            not _scope_kill_switch_active(db, "connection", connection_id),
        )
        checks["reconciliation_healthy"] = _check(
            "latest reconciliation is ok",
            _reconciliation_healthy(db, user_id, mandate.account_id),
        )
        if connection is None and connection_id:
            connection = (
                db.query(BrokerConnection).filter_by(id=connection_id).one_or_none()
            )
        connection_healthy = (
            connection is not None
            and connection.status in {"CONNECTED", "HEALTHY"}
            and connection.revoked_at is None
            and connection.environment == "production"
        )
        checks["broker_connection_healthy"] = _check(
            "broker connection healthy and not revoked",
            connection_healthy,
            connection.status if connection else "missing",
        )
        mandate_ok = (
            mandate_approved and mandate_live and mandate_active
            and mandate.kill_switch_state != "active"
            and checks["connection_kill_switch"]["ok"]
            and connection_healthy
            and checks["reconciliation_healthy"]["ok"]
        )

    risk_config_complete = True
    if mandate is not None:
        risk_config_complete = (
            mandate.max_total_notional is not None
            and float(mandate.max_total_notional) > 0
            and mandate.max_per_order_notional is not None
            and float(mandate.max_per_order_notional) > 0
            and mandate.max_position_notional is not None
            and mandate.max_daily_loss is not None
            and mandate.allowed_symbols_json is not None
        )
    checks["risk_config_complete"] = _check(
        "risk configuration complete on mandate", risk_config_complete,
    )

    enabled = (
        static.enabled
        and user_approved
        and mandate_ok
        and risk_config_complete
        and checks["kill_switch_global"]["ok"]
        and checks["kill_switch_user"]["ok"]
    )
    return GateResult(enabled=enabled, checks=checks)
