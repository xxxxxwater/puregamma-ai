"""P0-9 E2E A6: cancel a QUEUED research run (created while the worker is
stopped), then confirm the restarted worker never executes it.
"""
from __future__ import annotations

import json
import sys
import time

import httpx

sys.path.insert(0, "/app")

BASE = "http://127.0.0.1:8000"
EVIDENCE_PATH = "/var/lib/puregamma/backtests/p09_evidence.json"

with open(EVIDENCE_PATH, "r", encoding="utf-8") as fh:
    evidence = json.load(fh)


def step(name: str, **kw) -> None:
    evidence["steps"].append({"name": name, **kw})
    print(f"[STEP] {name}: {json.dumps(kw, default=str)[:900]}", flush=True)


from packages.database.session import SessionLocal  # noqa: E402
from packages.database.models import User  # noqa: E402
from apps.api.dependencies import create_access_token  # noqa: E402

db = SessionLocal()
pro = db.query(User).filter_by(email="p09-pro@puregamma.ai").one()
PRO = {"Authorization": f"Bearer {create_access_token(pro)}"}


def balance() -> int:
    db.expire_all()
    return db.get(User, pro.id).credit_balance


mode = sys.argv[1] if len(sys.argv) > 1 else "create"

if mode == "create":
    before = balance()
    resp = httpx.post(f"{BASE}/api/research/run", json={"code": "print('must-not-run')"}, headers=PRO, timeout=15)
    run = resp.json()
    run_id = run["run_id"]
    step("A6_created_while_worker_down", body=run, balance=balance(), expected=before - 20)
    assert run["status"] == "queued" and balance() == before - 20
    cancel = httpx.post(f"{BASE}/api/research/run/{run_id}/cancel", headers=PRO, timeout=15)
    final = cancel.json()
    step("A6_cancel_queued", status_code=cancel.status_code, final_status=final["status"], balance=balance(), expected=before)
    assert final["status"] == "cancelled" and balance() == before
    evidence["A6_run_id"] = run_id
    evidence["A6_balance_after_cancel"] = balance()
else:
    run_id = evidence["A6_run_id"]
    time.sleep(8)  # give the restarted worker a chance to pick the task up
    final = httpx.get(f"{BASE}/api/research/run/{run_id}", headers=PRO, timeout=15).json()
    step(
        "A6_after_worker_restart",
        status=final["status"],
        error=final["error"],
        logs=final["logs_tail"][-100:],
        balance=balance(),
        expected=evidence["A6_balance_after_cancel"],
    )
    assert final["status"] == "cancelled", f"worker executed a cancelled run: {final['status']}"
    assert "must-not-run" not in (final["logs_tail"] or "")
    assert balance() == evidence["A6_balance_after_cancel"]

with open(EVIDENCE_PATH, "w", encoding="utf-8") as fh:
    json.dump(evidence, fh, indent=2, default=str)
print(f"[P09-E2E] A6 {mode} complete", flush=True)
