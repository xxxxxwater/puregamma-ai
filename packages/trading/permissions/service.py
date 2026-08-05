from __future__ import annotations


class TradingPermissionDenied(RuntimeError):
    pass


def assert_account_permission(account_permissions: dict, action: str) -> None:
    if action in {"withdraw", "transfer", "sign_raw_transaction"}:
        raise TradingPermissionDenied(f"Forbidden trading capability: {action}")
    if not bool(account_permissions.get(action, False)):
        raise TradingPermissionDenied(f"Account permission denied: {action}")
