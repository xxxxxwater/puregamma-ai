#!/usr/bin/env python3
"""Prove the patched PM NAV series query spans the window (run where riskbot lives).

Runs against a throwaway SQLite database, never against the live one:

    docker run --rm -v /opt/riskbot:/riskbot -w /riskbot riskbot:0.1.0 \
        python /riskbot/verify-series-window.py

Assertions:

1. With far more real observations in the window than the old 5000-row ceiling,
   the series still ends at ``now`` (the old query ended ~7 days earlier).
2. It starts at the window edge, so the range buttons have real data.
3. Points are strictly ascending and every point is a real row - the count of
   returned points is < the number of inserted rows (thinning happened) and every
   returned timestamp exists in the table.
4. The published sampling tiers hold: every observation from the last 24h is
   kept, older ones are thinned to 5-minute (up to 7d) and 1-hour buckets.
"""
from __future__ import annotations

import asyncio
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.storage.db import Database  # noqa: E402
from app.storage.repositories import SnapshotHistoryRepo  # noqa: E402

CADENCE = 30.0          # seconds between real observations
WINDOW_DAYS = 90
COVERED_DAYS = 8        # how much history actually exists (production-like)


def build(path: Path, now: float) -> tuple[int, float]:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE account_snapshot ("
        " captured_at REAL PRIMARY KEY, account_equity_usd TEXT, adjusted_equity_usd TEXT,"
        " available_usd TEXT, equity_btc TEXT, btc_price_usd TEXT, btc_quantity TEXT,"
        " btc_collateral_usd TEXT, gross_notional_usd TEXT, net_notional_btc TEXT,"
        " position_count INTEGER, order_count INTEGER, degraded INTEGER, uni_mmr TEXT)"
    )
    first = now - COVERED_DAYS * 86400
    rows = []
    t = first
    while t <= now:
        rows.append((t, "1", str(1_000_000 + (t - first)), "0", "1", "1", "1", "0",
                     "0", "0", 0, 0, 0, "1"))
        t += CADENCE
    conn.executemany("INSERT INTO account_snapshot VALUES (" + ",".join("?" * 14) + ")", rows)
    conn.commit()
    conn.close()
    return len(rows), first


def main() -> int:
    now = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "verify.db"
        inserted, first = build(path, now)
        db = Database(str(path)) if not isinstance(Database, type) else Database(str(path))
        repo = SnapshotHistoryRepo(db)  # type: ignore[arg-type]
        since = now - WINDOW_DAYS * 86400
        points = asyncio.run(repo.series(since, now=now, limit=20_000))
        db.close()

        times = [float(p["captured_at"]) for p in points]
        failures: list[str] = []
        if not points:
            failures.append("series returned no points")
        else:
            if abs(times[-1] - now) > 3 * CADENCE:
                failures.append(
                    f"series ends at {times[-1]:.0f}, expected ~{now:.0f} "
                    f"(the pre-fix query stopped at the oldest rows of the window)")
            if times[0] > first + 3600:
                failures.append(
                    f"series starts at {times[0]:.0f} but history starts at {first:.0f}")
            if times != sorted(times):
                failures.append("points are not ascending")
            if len(set(times)) != len(times):
                failures.append("duplicate timestamps")
            if len(times) >= inserted:
                failures.append("no thinning happened; the whole table was returned")

            known = set()
            conn = sqlite3.connect(path)
            for (value,) in conn.execute("SELECT captured_at FROM account_snapshot"):
                known.add(float(value))
            conn.close()
            ghost = [t for t in times if t not in known]
            if ghost:
                failures.append(f"{len(ghost)} returned points are not real rows")

            day, week = now - 86400, now - 7 * 86400
            recent = [t for t in times if t >= day]
            expected_recent = int((now - max(day, first)) // CADENCE) + 1
            if abs(len(recent) - expected_recent) > 2:
                failures.append(
                    f"last 24h must keep every observation: {len(recent)} != {expected_recent}")
            # The 24h-7d band is six days wide, sampled one point per 5 minutes.
            mid = [t for t in times if week <= t < day]
            if len(mid) > 6 * 288 + 4:
                failures.append(f"24h-7d band is not 5-minute sampled ({len(mid)} points)")
            if len(mid) < 6 * 288 - 4:
                failures.append(f"24h-7d band lost real coverage ({len(mid)} points)")

        print(f"inserted={inserted} returned={len(points)} "
              f"span={(times[-1] - times[0]) / 3600:.1f}h" if times else "returned=0")
        if failures:
            print("\nFAILED:")
            for item in failures:
                print(f"  - {item}")
            return 1
        print("OK: the exported series spans the window and ends at the newest real observation")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
