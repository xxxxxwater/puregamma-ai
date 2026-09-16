"""Exact-match patch for the INDEPENDENT /opt/riskbot checkout only.

Requires explicit write permissions to that checkout; does NOT touch any
strategy path, trading key, Docker service or live order. Run on a backup
or staging checkout before deployment. Abort if upstream code differs.

Usage: python3 integrations/riskbot/apply_readonly_fixes.py /path/to/riskbot
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path


def replace_once(source: str, old: str, new: str, path: Path) -> str:
    if source.count(old) != 1:
        raise ValueError(f"Patch anchor does not match exactly once: {path.name}: {old[:55]!r}")
    return source.replace(old, new, 1)


def patch(root: Path) -> None:
    changes: dict[Path, str] = {}
    orders = (root / "app/services/snapshot.py")
    content = orders.read_text(encoding="utf-8")
    content = replace_once(content,
        'coverage.account != "ok" and coverage.balance != "ok"\n            and coverage.um_positions != "ok" and coverage.cm_positions != "ok"',
        'coverage.account != "ok" or coverage.balance != "ok"\n            or coverage.um_positions != "ok" or coverage.cm_positions != "ok"', orders)
    content = replace_once(content,
        '            self._last_full_orders_at = self._clock()',
        '            if all(getattr(coverage, name) == "ok" for name in ("um_orders", "cm_orders", "margin_orders", "um_algo_orders", "cm_conditional_orders", "margin_oco_orders")):\n                self._last_full_orders_at = self._clock()', orders)
    content = replace_once(content,
        '        self.quality.rest_ok = True\n        self.quality.consecutive_failures = 0',
        '        self.quality.rest_ok = not errors\n        self.quality.consecutive_failures = 0 if not errors else self.quality.consecutive_failures + 1', orders)
    content = replace_once(content,
        '                rest_ok=True,\n                ws_connected=self.quality.ws_connected,',
        '                rest_ok=self.quality.rest_ok,\n                ws_connected=self.quality.ws_connected,', orders)
    content = replace_once(content,
        '                consecutive_failures=0,\n                last_success_at=self.quality.last_success_at,',
        '                consecutive_failures=self.quality.consecutive_failures,\n                last_success_at=self.quality.last_success_at,', orders)
    content = replace_once(content,
        '        if not include_orders:\n            return list(self._cache.orders) if self._cache is not None else []\n        out: list[OpenOrder] = []',
        '        if not include_orders or any(results.get(name) is None for name in ("um_orders", "cm_orders", "margin_orders", "um_algo_orders", "cm_conditional_orders", "margin_oco_orders")):\n            # Never convert a failed order query into a false zero-orders result.\n            return list(self._cache.orders) if self._cache is not None else []\n        out: list[OpenOrder] = []', orders)
    content = replace_once(content,
        'order_type=str(entry.get("type") or entry.get("algoType") or entry.get("strategyType") or ""),',
        'order_type=str(entry.get("orderType") or entry.get("type") or entry.get("strategyType") or ""),', orders)
    content = replace_once(content,
        'stop_price=cv.to_decimal(entry.get("stopPrice")),',
        'stop_price=cv.to_decimal(_first(entry, "triggerPrice", "stopPrice")),', orders)
    content = replace_once(content,
        'status=str(entry.get("status") or ""),',
        'status=str(entry.get("algoStatus") or entry.get("status") or ""),', orders)
    content = replace_once(content,
        'create_time=cv.to_decimal(entry.get("time")),',
        'create_time=cv.to_decimal(_first(entry, "createTime", "time")),', orders)
    changes[orders] = content

    risk = root / "app/services/risk_engine.py"
    content = risk.read_text(encoding="utf-8")
    start = '''        protective = [o for o in snap.orders if o.reduce_only and o.product in ("UM", "CM")
                      and self._is_stop_order(o)]'''
    end = '''        protective = [o for o in snap.orders if (o.reduce_only or o.raw.get("closePosition") is True)
                      and o.product in ("UM", "CM") and self._is_stop_order(o)
                      and o.status.upper() in ("NEW", "WORKING", "PARTIALLY_FILLED", "PENDING_NEW")]'''
    content = replace_once(content, start, end, risk)
    start = '''            matches = [o for o in protective if o.product == pos.product
                       and o.symbol == pos.symbol and o.side.upper() == expected_order_side]
            state["evaluated"].add(fingerprint)
            if not matches:'''
    end = '''            matches = [o for o in protective if o.product == pos.product
                       and o.symbol == pos.symbol and o.side.upper() == expected_order_side
                       and str(o.raw.get("positionSide") or "BOTH").upper() ==
                       (pos.side if pos.position_mode == "hedge" else "BOTH")
                       and o.stop_price is not None and o.stop_price > cv.ZERO]
            # A small reduce-only stop does not protect an entire large position.
            full_close = any(o.raw.get("closePosition") is True for o in matches)
            covered = sum((abs(o.quantity) for o in matches
                           if o.reduce_only and o.quantity is not None), cv.ZERO)
            state["evaluated"].add(fingerprint)
            if not full_close and covered < abs(pos.position_amt):'''
    content = replace_once(content, start, end, risk)
    changes[risk] = content

    repo = root / "app/storage/repositories.py"
    content = repo.read_text(encoding="utf-8")
    content = replace_once(content, '(fingerprint, rule, level, value, cooldown_until, now, int(transient), now),', '(fingerprint, rule, level, value, cooldown_until, now, int(transient), time.time()),', repo)
    content = replace_once(content, '(value, now, fingerprint))', '(value, time.time(), fingerprint))', repo)
    content = replace_once(content, '(now, fingerprint))', '(time.time(), fingerprint))', repo)
    content = replace_once(content, '(now, fingerprint))', '(time.time(), fingerprint))', repo)
    changes[repo] = content

    # Parse EVERY candidate before writing ANY file. Do not mutate unrelated
    # paths or apply partially if current upstream has moved.
    for path, candidate in changes.items():
        ast.parse(candidate, filename=str(path))
    for path, candidate in changes.items():
        path.with_suffix(path.suffix + ".pre-private-pm.bak").write_bytes(path.read_bytes())
        path.write_text(candidate, encoding="utf-8")
        print("patched", path.relative_to(root))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply_readonly_fixes.py /path/to/riskbot")
    patch(Path(sys.argv[1]).resolve())
