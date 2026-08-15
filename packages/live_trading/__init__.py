"""PureGamma LIVE Trading Control Plane.

Additive layer on top of the existing FastAPI + PostgreSQL + Redis + Celery +
Nautilus Runtime stack. Nothing in this package is reachable unless the LIVE
feature gates pass (see ``flags.py`` and docs/live-trading/).

Modules:
- flags:        multi-condition feature gate evaluation
- enums:        shared LIVE enums
- secret_store: encrypted broker credential storage (no plaintext in DB)
- audit:        append-only audit writer with trace ids
- price_feed:   server-recorded market prices for NAV marking
- risk_engine:  pre-trade risk checks (Numeric only, no floats)
- ledger:       append-only immutable ledger
- kill_switch:  global/user/mandate/connection kill switches
- gateway_adapter: Execution Gateway interface (nautilus/mock)
- nav:          server-side NAV calculator
- reconciliation: daily exchange vs ledger vs NAV comparison
- control_plane: order pipeline (preview -> risk -> submit -> fill -> ledger -> NAV)
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]
