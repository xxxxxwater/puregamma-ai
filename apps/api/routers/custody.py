"""Custody API (P0-10b): user-facing custody account, balances, ledger,
deposits (testnet manual confirmation), withdrawals, and admin reconcile.

Honesty rules enforced here:
- Without provider credentials the account reports status=UNCONFIGURED with a
  NULL deposit address — the API never displays a fake address, never calls
  the funds "custodied", and never reports balances as venue-verified.
- Manual deposit confirmation is a testnet/sandbox path only: in a production
  app environment (or for a non-testnet custody account) it is 403
  CUSTODY_LIVE_DISABLED.
- All money is serialized as strings (Decimal -> str), timestamps as UTC ISO.
- Error payloads are bilingual: {"code", "message_en", "message_zh"}.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.dependencies import get_current_user, get_db, require_admin
from apps.api.services import custody_service
from packages.database.models import (
    CustodyAccount,
    CustodyDeposit,
    CustodyLedgerEntry,
    CustodyReconciliation,
    CustodySubAccount,
    CustodyWithdrawal,
    User,
)

router = APIRouter(prefix="/custody", tags=["custody"])


class DepositConfirmRequest(BaseModel):
    asset: str = Field(min_length=1, max_length=20)
    amount: Decimal = Field(gt=0)
    tx_ref: str = Field(min_length=3, max_length=200)


class WithdrawalCreateRequest(BaseModel):
    asset: str = Field(min_length=1, max_length=20)
    amount: Decimal = Field(gt=0)
    address: str = Field(min_length=8, max_length=200)
    idempotency_key: str = Field(min_length=8, max_length=200)


class ReconcileRequest(BaseModel):
    asset: str = Field(min_length=1, max_length=20)
    external_balance: Decimal | None = Field(default=None, ge=0)


def _error(status_code: int, code: str, message_en: str, message_zh: str) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message_en": message_en, "message_zh": message_zh},
    )


def _money(value) -> str | None:
    if value is None:
        return None
    return str(Decimal(str(value)))


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.astimezone(timezone.utc).isoformat()


def _serialize_account(account: CustodyAccount, provider_configured: bool) -> dict:
    return {
        "account_id": account.id,
        "venue": account.venue,
        "environment": account.environment,
        "status": account.status,
        "deposit_address": account.deposit_address,  # NULL until the provider supplies one
        "provider_configured": provider_configured,
        "label": "testnet-sandbox" if provider_configured else "unavailable-unconfigured",
    }


def _serialize_deposit(row: CustodyDeposit) -> dict:
    return {
        "id": row.id,
        "asset": row.asset,
        "amount": _money(row.amount),
        "tx_ref": row.tx_ref,
        "confirmations": row.confirmations,
        "status": row.status,
        "external_ref": row.external_ref,
        "created_at": _iso(row.created_at),
        "confirmed_at": _iso(row.confirmed_at),
    }


def _serialize_withdrawal(row: CustodyWithdrawal) -> dict:
    return {
        "id": row.id,
        "asset": row.asset,
        "amount": _money(row.amount),
        "address": row.address,
        "status": row.status,
        "idempotency_key": row.idempotency_key,
        "tx_ref": row.tx_ref,
        "error": row.error,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _serialize_ledger_entry(row: CustodyLedgerEntry, asset: str) -> dict:
    return {
        "id": row.id,
        "sub_account_id": row.sub_account_id,
        "asset": asset,
        "entry_type": row.entry_type,
        "amount": _money(row.amount),
        "available_after": _money(row.available_after),
        "frozen_after": _money(row.frozen_after),
        "ref_type": row.ref_type,
        "ref_id": row.ref_id,
        "idempotency_key": row.idempotency_key,
        "created_at": _iso(row.created_at),
    }


def _serialize_reconciliation(row: CustodyReconciliation) -> dict:
    return {
        "id": row.id,
        "asset": row.asset,
        "local_available": _money(row.local_available),
        "local_frozen": _money(row.local_frozen),
        "external_balance": _money(row.external_balance),
        "difference": _money(row.difference),
        "status": row.status,
        "details": row.details_json,
        "created_at": _iso(row.created_at),
    }


def _assert_testnet_mutation_allowed(account: CustodyAccount) -> None:
    """Mutating custody paths are testnet/sandbox-only in this MVP."""
    if get_settings().app_environment.lower() == "production":
        _error(
            403,
            "CUSTODY_LIVE_DISABLED",
            "Manual custody mutations are disabled in production.",
            "生产环境已禁用手动托管资金操作。",
        )
    if account.environment != "testnet":
        _error(
            403,
            "CUSTODY_LIVE_DISABLED",
            "This custody account is not a testnet account; manual mutations are disabled.",
            "该托管账户不是测试网账户，已禁用手动资金操作。",
        )


@router.get("/account")
def custody_account_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    settings = get_settings()
    account = custody_service.get_or_create_custody_account(db)
    db.commit()
    return {
        "account": _serialize_account(
            account, custody_service.provider_credentials_configured(settings)
        )
    }


@router.get("/balances")
def custody_balances(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    view = custody_service.sub_account_view(db, user.id)
    return {
        "balances": [
            {
                "sub_account_id": row["sub_account_id"],
                "asset": row["asset"],
                "available": _money(row["available"]),
                "frozen": _money(row["frozen"]),
                "account": row["account"],
            }
            for row in view
        ]
    }


@router.get("/ledger")
def custody_ledger(
    asset: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    query = (
        db.query(CustodyLedgerEntry, CustodySubAccount.asset)
        .join(CustodySubAccount, CustodyLedgerEntry.sub_account_id == CustodySubAccount.id)
        .filter(CustodySubAccount.user_id == user.id)
    )
    if asset:
        query = query.filter(CustodySubAccount.asset == asset.upper())
    total = query.count()
    rows = (
        query.order_by(CustodyLedgerEntry.created_at.desc(), CustodyLedgerEntry.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "items": [_serialize_ledger_entry(entry, entry_asset) for entry, entry_asset in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/deposits/confirm")
def confirm_deposit(
    payload: DepositConfirmRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Testnet/sandbox manual deposit confirmation. Idempotent on tx_ref:
    repeating the same tx_ref returns the original deposit without a second
    credit."""
    account = custody_service.get_or_create_custody_account(db)
    _assert_testnet_mutation_allowed(account)
    sub_account = custody_service.ensure_sub_account(db, account, user.id, payload.asset)
    deposit = custody_service.credit_deposit(
        db,
        sub_account,
        payload.amount,
        tx_ref=payload.tx_ref,
        external_ref=payload.tx_ref,
    )
    db.commit()
    return {"deposit": _serialize_deposit(deposit)}


@router.post("/withdrawals")
def create_withdrawal(
    payload: WithdrawalCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    account = custody_service.get_or_create_custody_account(db)
    _assert_testnet_mutation_allowed(account)
    sub_account = custody_service.ensure_sub_account(db, account, user.id, payload.asset)
    try:
        withdrawal = custody_service.request_withdrawal(
            db,
            sub_account,
            payload.asset,
            payload.amount,
            payload.address,
            payload.idempotency_key,
        )
    except custody_service.UnsupportedWithdrawalAsset:
        _error(400, "UNSUPPORTED_ASSET", f"Unsupported withdrawal asset: {payload.asset}", f"不支持的提现资产：{payload.asset}")
    except custody_service.InvalidWithdrawalAddress:
        _error(400, "INVALID_ADDRESS", f"Invalid {payload.asset.upper()} withdrawal address.", "提现地址格式无效。")
    except custody_service.InsufficientCustodyBalance:
        _error(400, "INSUFFICIENT_CUSTODY_BALANCE", "Insufficient available custody balance.", "托管可用余额不足。")
    db.commit()
    return {"withdrawal": _serialize_withdrawal(withdrawal)}


@router.get("/withdrawals")
def list_withdrawals(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    query = (
        db.query(CustodyWithdrawal)
        .join(CustodySubAccount, CustodyWithdrawal.sub_account_id == CustodySubAccount.id)
        .filter(CustodySubAccount.user_id == user.id)
    )
    total = query.count()
    rows = (
        query.order_by(CustodyWithdrawal.created_at.desc(), CustodyWithdrawal.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "items": [_serialize_withdrawal(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/withdrawals/{withdrawal_id}/cancel")
def cancel_withdrawal(
    withdrawal_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    withdrawal = (
        db.query(CustodyWithdrawal)
        .join(CustodySubAccount, CustodyWithdrawal.sub_account_id == CustodySubAccount.id)
        .filter(CustodyWithdrawal.id == withdrawal_id, CustodySubAccount.user_id == user.id)
        .one_or_none()
    )
    if withdrawal is None:
        _error(404, "WITHDRAWAL_NOT_FOUND", "Withdrawal not found.", "未找到该提现记录。")
    if withdrawal.status not in {"intent", "approved"}:
        _error(
            409,
            "WITHDRAWAL_NOT_CANCELLABLE",
            f"Withdrawal in status {withdrawal.status} cannot be cancelled.",
            "当前状态的提现已无法取消。",
        )
    withdrawal = custody_service.mark_withdrawal_status(
        db, withdrawal, "rejected", error="USER_CANCELLED"
    )
    db.commit()
    return {"withdrawal": _serialize_withdrawal(withdrawal)}


@router.post("/reconcile")
def reconcile_custody(
    payload: ReconcileRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Admin-only balance reconciliation. Without an external balance the
    result is UNAVAILABLE — never a fabricated match."""
    require_admin(user)
    account = custody_service.get_or_create_custody_account(db)
    record = custody_service.reconcile(db, account, payload.asset, payload.external_balance)
    db.commit()
    return {"reconciliation": _serialize_reconciliation(record)}
