from __future__ import annotations

"""Read-only catalog of BUILT-IN frontend (Cordis) plugins.

FastAPI decides WHO may load which frontend plugin based on subscription,
feature flags and entitlements. It never executes frontend code: every
entry carries entry="builtin" and the browser resolves ids through a
compiled dynamic-import whitelist, never a server-provided URL. Permission
fields in this manifest are UX-only; data access, credit charges and
trading rights continue to be enforced exclusively by the API.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.dependencies import get_current_user, get_db
from apps.api.services.entitlement_service import get_user_entitlement
from packages.database.models import User

router = APIRouter(prefix="/api/frontend", tags=["frontend"])


BUILTIN_PLUGINS: tuple[dict, ...] = (
    {
        "id": "puregamma.portfolio",
        "version": "1.0.0",
        "entry": "builtin",
        "required_entitlements": ["portfolio_access"],
        "permissions": ["read:portfolio"],
        "routes": ["/portfolio"],
    },
    {
        "id": "puregamma.research",
        "version": "1.0.0",
        "entry": "builtin",
        "required_entitlements": ["agent_daily_runs"],
        "permissions": ["read:research"],
        "routes": ["/research", "/reports", "/backtest"],
        "feature_flags": {"harness_research_enabled": True},
    },
    {
        "id": "puregamma.options",
        "version": "1.0.0",
        "entry": "builtin",
        "required_entitlements": [],
        "permissions": ["read:research"],
        "routes": ["/options"],
    },
    {
        "id": "puregamma.secretary",
        "version": "1.0.0",
        "entry": "builtin",
        "required_entitlements": ["agent_daily_runs"],
        "permissions": ["read:research"],
        "routes": ["/secretary", "/chat"],
    },
    {
        "id": "puregamma.trading",
        "version": "1.0.0",
        "entry": "builtin",
        "required_entitlements": [],
        "permissions": ["trade:paper"],
        "routes": ["/trading/paper", "/trading/positions", "/trading/risk", "/trading/runtime"],
        "feature_flags": {"auto_trading_paper_enabled": True},
    },
)


def _entitlement_satisfied(entitlement: dict, required: list[str]) -> bool:
    for key in required:
        value = entitlement.get(key)
        if value in (None, False, 0, "", []):
            return False
    return True


def _flags_satisfied(plugin: dict, settings) -> bool:
    for name, expected in (plugin.get("feature_flags") or {}).items():
        if bool(getattr(settings, name)) is not bool(expected):
            return False
    return True


@router.get("/plugins")
def list_plugins(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """Plugin manifest for the signed-in user. The browser may ONLY load
    entries with enabled=true through its compiled whitelist."""
    entitlement = get_user_entitlement(db, user.id)
    settings = get_settings()
    plugins = []
    for plugin in BUILTIN_PLUGINS:
        enabled = _flags_satisfied(plugin, settings) and _entitlement_satisfied(
            entitlement, plugin["required_entitlements"]
        )
        plugins.append(
            {
                "id": plugin["id"],
                "version": plugin["version"],
                "enabled": enabled,
                "entry": plugin["entry"],
                "required_entitlements": plugin["required_entitlements"],
                "permissions": plugin["permissions"],
                "routes": plugin["routes"],
            }
        )
    return {"plugins": plugins}
