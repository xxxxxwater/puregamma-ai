#!/usr/bin/env python3
"""Fix the exported PM NAV series so it covers the window instead of the oldest rows.

Background (verified on production 2026-09-24):

``app/storage/repositories.py`` served the export with

    SELECT ... FROM account_snapshot WHERE captured_at >= ?
    ORDER BY captured_at ASC LIMIT 5000

``since`` is ``generated_at - export_history_days * 86400`` (90 days).  The window
holds far more than 5000 real observations, so ``ORDER BY captured_at ASC``
selected the **oldest** 5000 rows of the window.  ``series.json`` therefore froze
at the first ~21 hours of collection while ``latest.json`` kept advancing, and the
NAV chart showed an amount scale that no longer matched the account:

    account_snapshot: 23,248 rows, 09-16 10:54Z .. today
    row 5000 (ORDER BY captured_at ASC) = 09-17 08:25:38Z
    series.json last point              = 09-17 08:25:38Z   (identical)
    latest.json                         = today

Fix: sample once, in SQL, with the same tiers ``app.services.export.downsample``
documents - keep every real observation from the last 24h, one per 5 minutes up to
7 days, one per hour beyond.  Each tier keeps the LAST real observation in its
bucket, so the series always spans the whole window; ordering is newest-first with
a hard row ceiling, so if the ceiling ever bites it drops the OLDEST buckets and
never the newest ones.  No point is interpolated and no financial value is
rewritten.

Usage (on the host that runs riskbot):

    python3 apply_series_window_fix.py --check   # report only
    python3 apply_series_window_fix.py --apply   # backup + patch + verify

Idempotent: a second run detects the patched text and exits 0 without writing.
"""
from __future__ import annotations

import argparse
import ast
import shutil
import sys
import time
from pathlib import Path

DEFAULT_ROOT = Path("/opt/riskbot")

OLD_SERIES = '''    async def series(self, since: float, limit: int = 5000) -> list[dict[str, Any]]:
        rows = self._db.fetch_all(
            "SELECT captured_at, account_equity_usd, adjusted_equity_usd, available_usd, "
            "equity_btc, btc_price_usd, btc_quantity, btc_collateral_usd, gross_notional_usd, "
            "net_notional_btc, position_count, order_count, degraded, uni_mmr "
            "FROM account_snapshot WHERE captured_at >= ? ORDER BY captured_at ASC LIMIT ?",
            (since, limit))
'''

NEW_SERIES = '''    #: Coverage-preserving sampling for the exported NAV series.
    #:
    #: ``(max_age_seconds, bucket_seconds)``; the first tier whose age bound the
    #: observation falls under wins.  A bucket keeps the LAST real observation
    #: inside it, so the series always spans the whole window.
    SERIES_TIERS: tuple[tuple[float, int], ...] = ((86400.0, 1), (7 * 86400.0, 300))
    #: Bucket for everything older than the last tier (matches downsample()).
    SERIES_TAIL_BUCKET_SECONDS = 3600
    #: Hard row ceiling.  Ordering is newest-first, so if the ceiling is ever hit
    #: the OLDEST buckets are dropped, never the newest ones.
    SERIES_MAX_ROWS = 20000

    async def series(self, since: float, now: float | None = None,
                     limit: int = SERIES_MAX_ROWS) -> list[dict[str, Any]]:
        """Real observations spanning ``[since, now]``, oldest first.

        The previous ``ORDER BY captured_at ASC LIMIT n`` returned the OLDEST n
        rows of a 90-day window, which pinned the exported curve to the first
        hours of collection while ``latest.json`` kept advancing.
        """
        clock = time.time() if now is None else now
        rows = self._db.fetch_all(
            "WITH windowed AS ("
            "  SELECT captured_at, account_equity_usd, adjusted_equity_usd, available_usd, "
            "         equity_btc, btc_price_usd, btc_quantity, btc_collateral_usd, "
            "         gross_notional_usd, net_notional_btc, position_count, order_count, "
            "         degraded, uni_mmr, "
            "         CAST(captured_at / (CASE WHEN captured_at >= ? THEN ? "
            "                                WHEN captured_at >= ? THEN ? "
            "                                ELSE ? END) AS INTEGER) AS bucket "
            "  FROM account_snapshot WHERE captured_at >= ?"
            "), ranked AS ("
            "  SELECT *, ROW_NUMBER() OVER (PARTITION BY bucket ORDER BY captured_at DESC)"
            "         AS rn "
            "  FROM windowed"
            ") "
            "SELECT captured_at, account_equity_usd, adjusted_equity_usd, available_usd, "
            "       equity_btc, btc_price_usd, btc_quantity, btc_collateral_usd, "
            "       gross_notional_usd, net_notional_btc, position_count, order_count, "
            "       degraded, uni_mmr "
            "FROM ranked WHERE rn = 1 ORDER BY captured_at DESC LIMIT ?",
            (clock - self.SERIES_TIERS[0][0], self.SERIES_TIERS[0][1],
             clock - self.SERIES_TIERS[1][0], self.SERIES_TIERS[1][1],
             self.SERIES_TAIL_BUCKET_SECONDS, since, limit))
        rows = list(reversed(rows))
'''

OLD_CALL = "        rows = await self._history.series(since)\n"
NEW_CALL = "        rows = await self._history.series(since, now=generated_at)\n"

TARGETS = (
    ("app/storage/repositories.py", OLD_SERIES, NEW_SERIES),
    ("app/services/export.py", OLD_CALL, NEW_CALL),
)


def _read(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--check", action="store_true", help="report only, write nothing")
    parser.add_argument("--apply", action="store_true", help="backup, patch, verify")
    args = parser.parse_args()
    if not (args.check or args.apply):
        parser.error("choose --check or --apply")

    root = Path(args.root)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    failures: list[str] = []

    for relative, old, new in TARGETS:
        path = root / relative
        if not path.exists():
            failures.append(f"{relative}: not found under {root}")
            continue
        text = _read(path)
        if new.split("\n")[0] and new in text:
            print(f"[skip]  {relative}: already patched")
            continue
        if old not in text:
            failures.append(f"{relative}: expected source text not found (refusing to guess)")
            continue
        patched = text.replace(old, new, 1)
        try:
            ast.parse(patched)
        except SyntaxError as exc:  # pragma: no cover - defensive
            failures.append(f"{relative}: patched file does not parse: {exc}")
            continue
        if args.check:
            print(f"[would patch] {relative}")
            continue
        backup = path.with_name(f"{path.name}.before-series-window-fix-{stamp}")
        shutil.copy2(path, backup)
        _write(path, patched)
        print(f"[patched] {relative}  (backup: {backup.name})")

    if failures:
        print("\nFAILED:", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
