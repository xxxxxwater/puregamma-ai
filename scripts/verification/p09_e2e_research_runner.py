"""P0-9 production-path E2E verification (runs inside the staging api container).

Drives the real HTTP API (uvicorn), the real Celery worker, the real docker
daemon, the real Binance/FMP providers, and the real credit ledger. Every
finding is appended to /tmp/p09_evidence.json and printed as a summary.
"""
from __future__ import annotations

import json
import os
import sys
import time

import httpx

sys.path.insert(0, "/app")

BASE = "http://127.0.0.1:8000"
EVIDENCE_PATH = "/var/lib/puregamma/backtests/p09_evidence.json"

evidence: dict = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "steps": []}


def step(name: str, **kw) -> None:
    entry = {"name": name, **{k: v for k, v in kw.items()}}
    evidence["steps"].append(entry)
    print(f"[STEP] {name}: {json.dumps(kw, default=str)[:900]}", flush=True)


def fail(msg: str) -> None:
    step("FATAL", error=msg)
    _dump()
    raise SystemExit(msg)


def _dump() -> None:
    with open(EVIDENCE_PATH, "w", encoding="utf-8") as fh:
        json.dump(evidence, fh, indent=2, default=str)


from packages.database.session import SessionLocal  # noqa: E402
from packages.database.models import User, UserPreference  # noqa: E402
from apps.api.dependencies import create_access_token  # noqa: E402

db = SessionLocal()


def make_user(email: str, plan: str, credits: int) -> User:
    user = db.query(User).filter_by(email=email).one_or_none()
    if not user:
        user = User(email=email, name=email.split("@")[0], role="user", plan=plan, credit_balance=credits)
        db.add(user)
        db.flush()
        db.add(UserPreference(user_id=user.id, email_recipient=email, notification_channels=["email"]))
    else:
        user.plan = plan
        user.credit_balance = credits
    db.commit()
    db.refresh(user)
    return user


def balance(user_id: str) -> int:
    db.expire_all()
    return db.get(User, user_id).credit_balance


def wait_terminal(run_id: str, headers: dict, kind: str = "research", timeout: float = 240.0) -> dict:
    url = f"{BASE}/api/research/run/{run_id}" if kind == "research" else f"{BASE}/api/backtest/{run_id}"
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        resp = httpx.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        last = resp.json()
        status = last.get("status") or (last.get("backtest") or {}).get("status")
        if status in {"completed", "failed", "cancelled", "unavailable"}:
            return last
        time.sleep(2)
    fail(f"run {run_id} did not reach a terminal state in {timeout}s (last={last})")


pro = make_user("p09-pro@puregamma.ai", "Pro", 100000)
free = make_user("p09-free@puregamma.ai", "Free", 150)
PRO = {"Authorization": f"Bearer {create_access_token(pro)}"}
FREE = {"Authorization": f"Bearer {create_access_token(free)}"}
step("users_ready", pro_balance=balance(pro.id), free_balance=balance(free.id))

ready = httpx.get(f"{BASE}/ready", timeout=10).json()
step("api_ready", **ready)

# Seed real daily candles from Binance (real network fetch, stored in the
# shared candle table the research datasets are exported from).
from packages.backtest.daily_data import refresh_daily_candles  # noqa: E402

refresh_daily_candles(db, ["BTC", "ETH", "SOL", "HYPE"])
db.commit()
from packages.database.models import BacktestCandle  # noqa: E402

candle_counts = {
    sym: db.query(BacktestCandle).filter_by(symbol=sym, interval="1d").count()
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "HYPEUSDT"]
}
step("seed_candles", **candle_counts)
assert all(count > 300 for count in candle_counts.values()), candle_counts

# 鈹€鈹€ A. Research runner 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
start_balance = balance(pro.id)

# A1: AST rejection is free.
resp = httpx.post(f"{BASE}/api/research/run", json={"code": "import os\nos.system('ls')", "dataset_refs": []}, headers=PRO, timeout=15)
step("A1_ast_reject", status_code=resp.status_code, body=resp.json(), balance=balance(pro.id))
assert resp.status_code == 400 and balance(pro.id) == start_balance

# A2: Free plan is denied by entitlement.
resp = httpx.post(f"{BASE}/api/research/run", json={"code": "print(1)"}, headers=FREE, timeout=15)
step("A2_free_plan_denied", status_code=resp.status_code, body=resp.json(), free_balance=balance(free.id))
assert resp.status_code == 402 and balance(free.id) == 150

# A3: real containerized run with dataset + matplotlib figure.
code = (
    "import csv, os\n"
    "import matplotlib\n"
    "matplotlib.use('Agg')\n"
    "import matplotlib.pyplot as plt\n"
    "with open(os.path.join(DATA_DIR, 'BTC.csv')) as fh:\n"
    "    rows = list(csv.DictReader(fh))\n"
    "closes = [float(r['close']) for r in rows]\n"
    "rets = [closes[i] / closes[i-1] - 1 for i in range(1, len(closes))]\n"
    "save_metrics({'rows': len(rows), 'total_return': closes[-1] / closes[0] - 1, 'mean_daily': sum(rets) / len(rets)})\n"
    "fig, ax = plt.subplots()\n"
    "ax.plot(closes)\n"
    "ax.set_title('BTC daily close')\n"
    "fig.savefig(os.path.join(OUT_DIR, 'btc_close.png'))\n"
    "print('research ok', len(rows))\n"
)
resp = httpx.post(f"{BASE}/api/research/run", json={"code": code, "dataset_refs": ["BTC"]}, headers=PRO, timeout=15)
run = resp.json()
step("A3_created", status_code=resp.status_code, body=run, balance=balance(pro.id))
assert resp.status_code == 200 and run["status"] == "queued" and balance(pro.id) == start_balance - 20
final = wait_terminal(run["run_id"], PRO)
step("A3_final", status=final["status"], metrics=final["metrics_json"], figures=final["figures"],
     credits_reserved=final["credits_reserved"], credits_spent=final["credits_spent"],
     logs_tail=final["logs_tail"][-200:], balance=balance(pro.id))
assert final["status"] == "completed" and final["metrics_json"]["rows"] > 100
assert final["figures"], "expected a persisted figure"
fig_url = final["figures"][0]
fig = httpx.get(f"{BASE}{fig_url}", headers=PRO, timeout=15)
step("A3_figure_download", url=fig_url, status_code=fig.status_code, content_type=fig.headers.get("content-type"), bytes=len(fig.content))
assert fig.status_code == 200 and len(fig.content) > 1000

# A4: timeout is killed and refunded.
before = balance(pro.id)
resp = httpx.post(f"{BASE}/api/research/run", json={"code": "x = 0\nwhile True:\n    x += 1\n", "limits": {"timeout_seconds": 15}}, headers=PRO, timeout=15)
run = resp.json()
assert run["status"] == "queued"
final = wait_terminal(run["run_id"], PRO, timeout=120)
step("A4_timeout", status=final["status"], error=final["error"], credits_spent=final["credits_spent"], balance=balance(pro.id), expected_balance=before)
assert final["status"] == "failed" and "exceeded" in (final["error"] or "") and balance(pro.id) == before

# A5: cancel a running run; container killed; refunded.
before = balance(pro.id)
resp = httpx.post(f"{BASE}/api/research/run", json={"code": "x = 0\nwhile True:\n    x += 1\n", "limits": {"timeout_seconds": 300}}, headers=PRO, timeout=15)
run = resp.json()
run_id = run["run_id"]
for _ in range(30):
    cur = httpx.get(f"{BASE}/api/research/run/{run_id}", headers=PRO, timeout=15).json()
    if cur["status"] == "running":
        break
    time.sleep(1)
assert cur["status"] == "running", f"run never entered running: {cur['status']}"
cancel = httpx.post(f"{BASE}/api/research/run/{run_id}/cancel", headers=PRO, timeout=15)
final = wait_terminal(run_id, PRO, timeout=60)
step("A5_cancel_running", cancel_status_code=cancel.status_code, final_status=final["status"], error=final["error"],
     credits_spent=final["credits_spent"], balance=balance(pro.id), expected_balance=before)
assert final["status"] == "cancelled" and balance(pro.id) == before

step("research_runner_done", pro_balance=balance(pro.id))
_dump()
print("[P09-E2E] research runner scenarios complete", flush=True)
