"""Approved dataset materialization for research runs.

The only approved dataset is the shared backtest candle store: requested
symbols are exported to read-only CSV files inside the job's data dir, which
is the single mount exposed to the container at ``/data:ro``. Dataset roots
are additionally whitelisted through ``RESEARCH_RUNNER_DATA_DIRS`` (default:
the backtest artifact dir) so operators can pre-stage read-only corpora.
"""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path

from sqlalchemy.orm import Session

from packages.backtest.daily_data import LAB_SYMBOLS
from packages.database.models import BacktestCandle

MAX_DATASET_ROWS = 5000
MAX_DATASETS = 8

_CANDLE_REF = re.compile(r"^(?:candles[:/])?([A-Za-z][A-Za-z0-9]{0,9})$")


def approved_data_roots() -> list[Path]:
    """Whitelisted dataset roots (RESEARCH_RUNNER_DATA_DIRS)."""
    raw = os.getenv("RESEARCH_RUNNER_DATA_DIRS", "")
    roots = [Path(item).resolve() for item in raw.split(os.pathsep) if item.strip()]
    if not roots:
        from apps.api.config import get_settings

        roots = [Path(get_settings().backtest_artifact_dir).resolve()]
    return roots


def normalize_dataset_ref(ref: str) -> str:
    """Validate a dataset ref and return the canonical candle asset symbol."""
    match = _CANDLE_REF.match(ref.strip())
    if not match:
        raise ValueError(f"unsupported dataset ref: {ref!r} (expected a candle symbol like 'BTC' or 'candles:BTC')")
    asset = match.group(1).upper()
    if asset not in LAB_SYMBOLS:
        raise ValueError(f"dataset not approved: {asset} (approved: {', '.join(sorted(LAB_SYMBOLS))})")
    return asset


def materialize_datasets(db: Session, refs: list[str], data_dir: Path) -> list[dict]:
    """Export requested candle symbols to CSV under ``data_dir`` (read-only mount)."""
    if len(refs) > MAX_DATASETS:
        raise ValueError(f"too many dataset refs (max {MAX_DATASETS})")
    data_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    for ref in refs:
        asset = normalize_dataset_ref(ref)
        symbol = LAB_SYMBOLS[asset]
        rows = (
            db.query(BacktestCandle)
            .filter(BacktestCandle.symbol == symbol, BacktestCandle.interval == "1d")
            .order_by(BacktestCandle.ts.asc())
            .limit(MAX_DATASET_ROWS)
            .all()
        )
        path = data_dir / f"{asset}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["ts", "open", "high", "low", "close", "volume"])
            for row in rows:
                writer.writerow([row.ts.isoformat(), row.open, row.high, row.low, row.close, row.volume])
        manifest.append({"ref": ref, "asset": asset, "file": path.name, "rows": len(rows)})
    return manifest
