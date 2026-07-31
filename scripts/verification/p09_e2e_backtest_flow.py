"""P0-9 E2E part 2: native VectorBT backtests, equity provider chain, and the
full Agent -> run -> artifact -> save-as-strategy user flow with credits.

Runs inside the staging api container; appends to /tmp/p09_evidence.json.
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


def _dump() -> None:
    with open(EVIDENCE_PATH, "w", encoding="utf-8") as fh:
        json.dump(evidence, fh, indent=2, default=str)


from packages.database.session import SessionLocal  # noqa: E402
from packages.database.models import User  # noqa: E402
from apps.api.dependencies import create_access_token  # noqa: E402

db = SessionLocal()
pro = db.query(User).filter_by(email="p09-pro@puregamma.ai").one()
PRO = {"Authorization": f"Bearer {create_access_token(pro)}"}


def balance() -> int:
    db.expire_all()
    return db.get(User, pro.id).credit_balance


def _get_tolerant(url: str) -> httpx.Response:
    """GET that rides out the production expensive-path rate limit (20/min)."""
    for _ in range(20):
        resp = httpx.get(url, headers=PRO, timeout=20)
        if resp.status_code != 429:
            return resp
        time.sleep(7)
    return resp


def wait_backtest(run_id: str, timeout: float = 300.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = _get_tolerant(f"{BASE}/backtest-lab/runs/{run_id}")
        resp.raise_for_status()
        payload = resp.json()["run"]
        if payload["status"] in {"completed", "failed", "cancelled"}:
            return payload
        time.sleep(8)
    raise SystemExit(f"backtest {run_id} never went terminal")


def run_backtest(asset: str, *, lookback_days: int = 365, slippage_bps: float = 0.0, fee_bps: float = 10.0) -> dict:
    for _ in range(20):
        resp = httpx.post(
            f"{BASE}/backtest",
            json={
                "strategy_name": f"{asset} momentum acceptance",
                "asset": asset,
                "engine": "vectorbt",
                "params": {"signal": "momentum", "fast_window": 12, "slow_window": 26, "fee_bps": fee_bps, "slippage_bps": slippage_bps, "lookback_days": lookback_days},
            },
            headers=PRO,
            timeout=20,
        )
        if resp.status_code != 429:
            break
        time.sleep(7)
    resp.raise_for_status()
    payload = resp.json()["backtest"]
    return payload


# 鈹€鈹€ B. Native VectorBT on real data: BTC, ETH, SOL, HYPE + one US equity 鈹€鈹€
import vectorbt  # noqa: E402,F401  (prove native lib exists in this image)

step("B0_vectorbt_native_available", version=vectorbt.__version__)

results = {}
import os as _os

for asset in ([] if _os.getenv("SKIP_CRYPTO") else ["BTC", "ETH", "SOL", "HYPE"]):
    before = balance()
    queued = run_backtest(asset)
    final = wait_backtest(queued["id"])
    results[asset] = final
    snap = final["data_snapshot"]
    assumptions = final["assumptions"]
    step(
        f"B_{asset}",
        status=final["status"],
        engine_result=(final["result"] or {}).get("engine"),
        provider=snap.get("provider"),
        bar_count=snap.get("bar_count"),
        window_start=snap.get("window_start"),
        window_end=snap.get("window_end"),
        fee_bps=assumptions.get("fee_bps"),
        slippage_bps=assumptions.get("slippage_bps"),
        lookahead=assumptions.get("lookahead_guard"),
        equity_points=len(final["equity_curve"]),
        drawdown_points=len(final["drawdown_curve"]),
        benchmark_points=len(final["benchmark_curve"]),
        trades=len(final["trades"]),
        positions=len(final["positions"]),
        final_equity=(final["performance"] or {}).get("final_equity"),
        credits_spent=final["credits_spent"],
        balance=balance(),
        charged=before - balance(),
    )
    assert final["status"] == "completed", final["error"]
    assert (final["result"] or {}).get("engine") == "vectorbt", "native vectorbt path not used"
    expected_provider = {"HYPE": "hyperliquid"}.get(asset, "binance")
    assert snap.get("provider") == expected_provider and (snap.get("bar_count") or 0) > 300
    assert final["equity_curve"] and final["drawdown_curve"] and final["benchmark_curve"]
    assert before - balance() == 50

# US equity via the keyed chain (FMP first) — requires real provider keys.
from packages.backtest.equity_daily import EquityDailyLoader  # noqa: E402

configured = EquityDailyLoader().configured_providers
step("C_equity_keys", configured_providers=configured)
if configured:
    before = balance()
    queued = run_backtest("AAPL")
    aapl = wait_backtest(queued["id"])
    step(
        "C_AAPL",
        status=aapl["status"],
        engine_result=(aapl["result"] or {}).get("engine"),
        data_sources=(aapl["result"] or {}).get("data_sources"),
        bar_count=(aapl["data_snapshot"] or {}).get("bar_count"),
        window_start=(aapl["data_snapshot"] or {}).get("window_start"),
        equity_points=len(aapl["equity_curve"]),
        trades=len(aapl["trades"]),
        credits_spent=aapl["credits_spent"],
        charged=before - balance(),
    )
    assert aapl["status"] == "completed", aapl["error"]
    assert (aapl["result"] or {}).get("data_sources", {}).get("AAPL", "").startswith("equity:")
else:
    step("C_AAPL", status="SKIPPED", reason="no equity provider keys configured in staging env")

# Unknown equity must be honestly UNAVAILABLE and refunded (never synthetic).
before = balance()
queued = run_backtest("ZZQXZ")
zzz = wait_backtest(queued["id"])
step(
    "C_unknown_equity_unavailable",
    status=zzz["status"],
    error=zzz["error"],
    charged=before - balance(),
)
assert zzz["status"] == "failed"
assert zzz["error"].get("code") == "EQUITY_DATA_UNAVAILABLE"
assert before - balance() == 0, "failed equity run must be fully refunded"

# Slippage must change the outcome (cost plumbing is real, not decorative).
if not _os.getenv("SKIP_SLIPPAGE"):
    base = wait_backtest(run_backtest("BTC", slippage_bps=0.0)["id"])
    slip = wait_backtest(run_backtest("BTC", slippage_bps=100.0)["id"])
    step(
        "B_slippage_effect",
        base_final=(base["performance"] or {}).get("final_equity"),
        slip_final=(slip["performance"] or {}).get("final_equity"),
        base_trades=len(base["trades"]),
        slip_assumption=slip["assumptions"].get("slippage_bps"),
    )
    assert len(base["trades"]) > 0
    assert (slip["performance"] or {}).get("final_equity") < (base["performance"] or {}).get("final_equity")


def _post_tolerant(url: str) -> httpx.Response:
    for _ in range(25):
        resp = httpx.post(url, headers=PRO, timeout=20)
        if resp.status_code != 429:
            return resp
        time.sleep(7)
    return resp

# 鈹€鈹€ D. Agent tool -> run -> artifact -> save-as-strategy (idempotent) 鈹€鈹€
from packages.agents.chat.tools import AgentToolRegistry  # noqa: E402

# The exact tool code path the agent executes when the LLM selects it.
tool_registry = AgentToolRegistry(db, pro.id)
tool_result = tool_registry.run_nautilus_backtest(["BTC"], lookback_days=365)
queued = tool_result.data[0]
step(
    "D_agent_tool_queued",
    tool=tool_result.tool_name,
    run_id=queued.get("run_id"),
    status=queued.get("status"),
    poll_url=queued.get("poll_url"),
)
assert queued.get("run_id") and queued.get("status") == "queued"
run_id = queued["run_id"]
final = wait_backtest(run_id)
step("D_agent_run_completed", status=final["status"], engine=(final["result"] or {}).get("engine"), trades=len(final["trades"]))
assert final["status"] == "completed"

# Artifact export (json) + download.
resp = _post_tolerant(f"{BASE}/backtest/{run_id}/export?format=json")
resp.raise_for_status()
artifact = resp.json()["artifact"]
dl = _get_tolerant(f"{BASE}/backtest/artifacts/{artifact['id']}")
step(
    "D_artifact",
    artifact_id=artifact["id"],
    size_bytes=artifact["size_bytes"],
    checksum=artifact["checksum"][:16],
    download_status=dl.status_code,
    download_bytes=len(dl.content),
    credits_spent=artifact["credits_spent"],
)
assert dl.status_code == 200 and len(dl.content) == artifact["size_bytes"]

# save-as-strategy twice: the second call must return the same strategy.
first = _post_tolerant(f"{BASE}/backtest/{run_id}/save-as-strategy")
first.raise_for_status()
s1 = first.json()["strategy"]
second = _post_tolerant(f"{BASE}/backtest/{run_id}/save-as-strategy")
second.raise_for_status()
s2 = second.json()["strategy"]
step(
    "D_save_as_strategy",
    first_id=s1["id"],
    first_created=s1["created"],
    first_status=s1["status"],
    execution_mode=s1["execution_mode"],
    second_id=s2["id"],
    second_created=s2["created"],
)
assert s1["created"] is True and s2["created"] is False and s1["id"] == s2["id"]

# Cancel a queued backtest (created while worker is busy is racy; cancel right
# after creation accepts queued-or-running but must end cancelled + refunded).
before = balance()
queued = run_backtest("ETH")
cancel = _post_tolerant(f"{BASE}/backtest/{queued['id']}/cancel")
cancel.raise_for_status()
final = wait_backtest(queued["id"], timeout=60)
step(
    "D_backtest_cancel",
    cancel_response=cancel.json()["backtest"]["status"],
    final_status=final["status"],
    credits_spent=final["credits_spent"],
    charged=before - balance(),
)
assert final["status"] == "cancelled" and before - balance() == 0

_dump()
print("[P09-E2E] backtest + user-flow scenarios complete", flush=True)
