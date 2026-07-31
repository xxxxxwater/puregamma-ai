from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from apps.api.config import get_settings


def artifact_root() -> Path:
    root = Path(get_settings().backtest_artifact_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def artifact_path(relative_path: Path) -> Path:
    """Resolve an artifact path while keeping it inside the configured root."""
    root = artifact_root()
    path = (root / relative_path).resolve()
    if root not in path.parents:
        raise ValueError("invalid artifact path")
    return path


def write_json_artifact(user_id: str, backtest_id: str, artifact_type: str, payload: Any) -> dict:
    """Write a bounded, deterministic JSON artifact below the server artifact root."""
    relative = Path(user_id) / backtest_id / f"{artifact_type}.json"
    path = artifact_path(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    path.write_bytes(raw)
    return {
        "relative_path": relative.as_posix(),
        "size_bytes": len(raw),
        "checksum": hashlib.sha256(raw).hexdigest(),
        "format": "json",
    }
