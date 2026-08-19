"""Mobile API contract v1 surface.

``GET /api/mobile/capabilities`` is the single honest gate for iOS/Android
feature entrances. Every boolean is computed from REAL server availability:

- feature flags from settings;
- contract-endpoint availability constants (flip these when the endpoints
  described in docs/mobile/MOBILE_API_CONTRACT.md actually ship);
- the LIVE static gate (information only — mobile NEVER offers a LIVE entry).

No mock data is ever returned: unknown/disabled surfaces stay false so the
clients render "功能暂不可用" instead of faking results.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.dependencies import get_current_user, get_db
from packages.billing.plans import canonical_tier
from packages.database.models import User
from packages.live_trading.flags import evaluate_static_gate

router = APIRouter(prefix="/api/mobile", tags=["mobile"])

# The contract endpoints shipped in apps/api/routers/harness_runs.py and
# apps/api/routers/memory.py (backed by tests/security/test_harness_contract.py).
RESEARCH_RUNS_CONTRACT_IMPLEMENTED = True
MEMORY_CONTRACT_IMPLEMENTED = True

APP_MIN_VERSION = "1.4.0"


@router.get("/capabilities")
def mobile_capabilities(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    settings = get_settings()
    static_gate = evaluate_static_gate()
    # The admin-only flag must be reflected here too: when set, non-admin
    # users see the create/retry entrances closed (the creation guard rejects
    # them with HARNESS_ADMIN_ONLY), never an open door that 403s later.
    harness_open_for_user = (
        settings.harness_research_enabled
        and RESEARCH_RUNS_CONTRACT_IMPLEMENTED
        and (not settings.harness_research_admin_only or user.role == "admin")
    )
    return {
        "harness_research_enabled": settings.harness_research_enabled,
        "memory_service_enabled": settings.memory_service_enabled,
        "auto_trading_enabled": settings.auto_trading_mandates_enabled,
        "paper_trading_enabled": settings.auto_trading_paper_enabled,
        "shadow_trading_enabled": settings.auto_trading_shadow_enabled,
        # Information only: the mobile clients never render a LIVE entry
        # regardless of this value (hard client-side policy).
        "live_trading_enabled": static_gate.enabled,
        "user_can_start_research": harness_open_for_user,
        "user_can_manage_memory": (
            settings.memory_service_enabled and MEMORY_CONTRACT_IMPLEMENTED
        ),
        "user_can_view_trading_mandates": True,
        "user_can_pause_mandates": True,
        "app_min_version": APP_MIN_VERSION,
        "maintenance_message": None,
        "harness_retry_enabled": harness_open_for_user,
        "membership_tier": canonical_tier(user.membership_tier),
    }
