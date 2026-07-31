"""Isolated Python research runner service.

POST /api/research/run creates a run after a static AST safety check; the
worker task ``puregamma.execute_research_run`` then executes the code inside
an ephemeral Docker container (no network, read-only root fs, resource caps).
User code is never executed in the API or worker process. When Docker is not
available the run is honestly marked ``unavailable`` — never fake success.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.orm import Session

from apps.api.services.credit_service import quote_task, refund_task, reserve_task, settle_task
from apps.api.services.entitlement_service import assert_action_allowed
from packages.backtest.artifacts import artifact_root
from packages.billing.metering import CreditReservation
from packages.database.models import ResearchRun
from packages.research_runner.datasets import approved_data_roots, materialize_datasets, normalize_dataset_ref
from packages.research_runner.docker_runner import (
    default_timeout_seconds,
    docker_available,
    execute_in_container,
    job_root,
    max_output_bytes,
    runner_image,
)
from packages.research_runner.validator import validate_research_code

logger = logging.getLogger(__name__)

MAX_CODE_BYTES = 64 * 1024
MAX_LOG_CHARS = 64_000
LOG_TAIL_CHARS = 4_000
MAX_FIGURES = 8
RESEARCH_RUN_CREDITS = 20
TERMINAL_STATUSES = {"completed", "failed", "cancelled", "unavailable"}

_FIGURE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{0,119}$")

# Generated wrapper executed INSIDE the container. It reads the user code from
# /job/user_code.py and runs it with dataset/metrics helpers in scope.
RUN_WRAPPER = '''"""Generated research run wrapper (container entrypoint)."""
import json
import os
import traceback

DATA_DIR = os.environ.get("PG_DATASET_DIR", "/data")
OUT_DIR = "/job/out"
os.makedirs(OUT_DIR, exist_ok=True)


def save_metrics(metrics):
    with open(os.path.join(OUT_DIR, "metrics.json"), "w", encoding="utf-8") as handle:
        json.dump(metrics, handle)


def main():
    with open("/job/user_code.py", "r", encoding="utf-8") as handle:
        source = handle.read()
    namespace = {"DATA_DIR": DATA_DIR, "OUT_DIR": OUT_DIR, "save_metrics": save_metrics}
    exec(compile(source, "user_code.py", "exec"), namespace)  # noqa: S102 - container-isolated by design


try:
    main()
except SystemExit:
    raise
except Exception:
    traceback.print_exc()
    raise SystemExit(1)
'''


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sanitize_limits(limits: dict | None) -> dict:
    limits = dict(limits or {})
    sanitized: dict = {}
    if "timeout_seconds" in limits:
        try:
            sanitized["timeout_seconds"] = max(1, min(int(limits["timeout_seconds"]), 600))
        except (TypeError, ValueError):
            raise ValueError("limits.timeout_seconds must be an integer")
    if "max_output_bytes" in limits:
        try:
            sanitized["max_output_bytes"] = max(1024, min(int(limits["max_output_bytes"]), max_output_bytes()))
        except (TypeError, ValueError):
            raise ValueError("limits.max_output_bytes must be an integer")
    return sanitized


def _reservation_for(row: ResearchRun) -> CreditReservation:
    return CreditReservation(
        idempotency_key=f"research-run-charge:{row.idempotency_key}",
        credits=row.credits_reserved or RESEARCH_RUN_CREDITS,
    )


def _refund_run_reservation(db: Session, row: ResearchRun, reason: str) -> None:
    """Refund the reservation exactly once; no-op when nothing was reserved."""
    if not (row.credits_reserved or 0):
        return
    try:
        refund_task(db, row.user_id, _reservation_for(row), reason)
    except Exception:
        logger.exception("research_run_refund_failed run_id=%s reason=%s", row.id, reason)


def create_research_run(
    db: Session,
    user_id: str,
    code: str,
    dataset_refs: list[str],
    *,
    limits: dict | None = None,
    idempotency_key: str | None = None,
) -> ResearchRun:
    if not code or not code.strip():
        raise ValueError("code must not be empty")
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise ValueError(f"code exceeds the {MAX_CODE_BYTES // 1024}KB limit")
    # AST rejection happens before any credit movement: rejected code is free.
    validate_research_code(code)
    # Expensive Python execution must never bypass plan entitlements.
    assert_action_allowed(db, user_id, "research_run")
    refs = [normalize_dataset_ref(ref) for ref in dataset_refs]
    sanitized_limits = _sanitize_limits(limits)
    key = f"research-run:{user_id}:{idempotency_key or os.urandom(8).hex()}"
    existing = db.query(ResearchRun).filter_by(idempotency_key=key).one_or_none()
    if existing:
        return existing
    available, reason = docker_available()
    reserved = 0
    if available:
        # Reserve only when a container can actually be spawned; an honestly
        # unavailable runner is never charged.
        quote = quote_task(task_type="research_run", requested_model="default", async_execution=True)
        reservation = reserve_task(
            db,
            user_id,
            quote,
            f"research-run-charge:{key}",
            {"runner": "docker", "datasets": refs},
        )
        reserved = reservation.credits
    row = ResearchRun(
        user_id=user_id,
        idempotency_key=key,
        status="queued" if available else "unavailable",
        code_hash=hashlib.sha256(code.encode("utf-8")).hexdigest(),
        code=code,
        dataset_refs_json=refs,
        limits_json=sanitized_limits,
        credits_reserved=reserved,
        credits_spent=0,
        error=None if available else f"research runner unavailable: {reason}",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def queue_research_run(db: Session, run_id: str) -> str:
    """Hand a queued research run to the worker; inline only outside production."""
    try:
        from apps.api.redis_client import get_redis
        get_redis().ping()
        from packages.workers.tasks import execute_research_run
        execute_research_run.delay(run_id)
        return "celery"
    except Exception as exc:
        from apps.api.config import get_settings
        if get_settings().app_environment.lower() == "production":
            row = db.get(ResearchRun, run_id)
            if row and row.status == "queued":
                row.status = "failed"
                row.error = f"research runner queue unavailable: {str(exc)[:300]}"
                row.completed_at = _now()
                _refund_run_reservation(db, row, "RESEARCH_QUEUE_UNAVAILABLE")
                db.commit()
            raise RuntimeError("Research runner queue is temporarily unavailable") from exc
        execute_research_run(db, run_id)
        return "inline"


def cancel_research_run(db: Session, user_id: str, run_id: str) -> ResearchRun:
    """Cancel a queued/running research run and refund the reservation.

    Idempotent. A running container is killed by the worker's cancel probe
    (``should_cancel``) within about a second; a queued celery task that was
    already dispatched exits immediately because cancelled is terminal.
    """
    row = db.query(ResearchRun).filter_by(id=run_id, user_id=user_id).one_or_none()
    if not row:
        raise ValueError("Research run not found")
    if row.status == "cancelled":
        return row
    if row.status in {"completed", "failed", "unavailable"}:
        raise ValueError(f"cannot cancel a {row.status} research run")
    # Atomic state flip (run row first, then the reservation — the worker
    # finalize path uses the same order) so a concurrent completion can never
    # clobber the cancellation.
    updated = db.execute(
        update(ResearchRun)
        .where(ResearchRun.id == run_id, ResearchRun.status.in_(["queued", "running"]))
        .values(status="cancelled", error="cancelled by user", completed_at=_now())
    ).rowcount
    if not updated:
        db.expire_all()
        row = db.get(ResearchRun, run_id)
        if row.status == "cancelled":
            return row
        raise ValueError(f"cannot cancel a {row.status} research run")
    db.expire_all()
    row = db.get(ResearchRun, run_id)
    _refund_run_reservation(db, row, "RESEARCH_RUN_CANCELLED_BY_USER")
    db.commit()
    db.refresh(row)
    return row


def _data_dir_for(run_id: str) -> Path:
    """The job dataset dir must live under an approved (whitelisted) root."""
    root = approved_data_roots()[0]
    path = (root / "research_datasets" / run_id).resolve()
    if root not in path.parents:
        raise ValueError("invalid dataset dir")
    return path


def _persist_figures(row: ResearchRun, figures: list[Path]) -> list[str]:
    """Copy produced figures into the durable artifact store; return URLs."""
    urls: list[str] = []
    target_dir = (artifact_root() / "research" / row.user_id / row.id).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    for path in figures[:MAX_FIGURES]:
        if not _FIGURE_NAME.match(path.name):
            continue
        target = (target_dir / path.name).resolve()
        if target.parent != target_dir:
            continue
        shutil.copyfile(path, target)
        urls.append(f"/api/research/run/{row.id}/files/{path.name}")
    return urls


def figure_path(row: ResearchRun, name: str) -> Path | None:
    """Resolve a persisted figure path for download (path traversal safe)."""
    if not _FIGURE_NAME.match(name):
        return None
    root = (artifact_root() / "research" / row.user_id / row.id).resolve()
    path = (root / name).resolve()
    if root not in path.parents or not path.exists():
        return None
    return path


def _read_metrics(out_dir: Path) -> dict:
    path = out_dir / "metrics.json"
    if not path.exists():
        return {}
    try:
        raw = path.read_bytes()[: 256 * 1024]
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def execute_research_run(db: Session, run_id: str) -> ResearchRun:
    """Worker entrypoint: execute one queued research run in a container."""
    row = db.get(ResearchRun, run_id)
    if not row:
        raise ValueError("Research run not found")
    if row.status in TERMINAL_STATUSES:
        return row
    available, reason = docker_available()
    if not available:
        row.status = "unavailable"
        row.error = f"research runner unavailable: {reason}"
        row.completed_at = _now()
        _refund_run_reservation(db, row, "RESEARCH_RUNNER_UNAVAILABLE")
        db.commit()
        db.refresh(row)
        return row
    row.status = "running"
    row.started_at = _now()
    db.commit()
    job_dir = (job_root() / row.id).resolve()
    data_dir = _data_dir_for(row.id)
    try:
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "user_code.py").write_text(row.code, encoding="utf-8")
        (job_dir / "run.py").write_text(RUN_WRAPPER, encoding="utf-8")
        manifest = materialize_datasets(db, row.dataset_refs_json or [], data_dir)
        limits = row.limits_json or {}

        def _cancel_requested() -> bool:
            # Poll the shared row; the API flips it to ``cancelled`` on user
            # cancel. Fresh SELECT each probe (session has no pending writes).
            db.expire_all()
            current = db.get(ResearchRun, run_id)
            return bool(current and current.status == "cancelled")

        outcome = execute_in_container(
            run_id=row.id,
            job_dir=job_dir,
            data_dir=data_dir,
            image=runner_image(),
            timeout_seconds=limits.get("timeout_seconds") or default_timeout_seconds(),
            max_output_bytes=limits.get("max_output_bytes") or max_output_bytes(),
            should_cancel=_cancel_requested,
        )
        logs = outcome.stdout
        if outcome.stderr:
            logs = f"{logs}\n{outcome.stderr}" if logs else outcome.stderr
        if outcome.output_truncated:
            logs = f"{logs}\n[output truncated]"
        db.expire_all()
        row = db.get(ResearchRun, run_id)
        if row.status == "cancelled":
            # The cancel path already refunded; never overwrite or settle.
            row.logs = logs[-MAX_LOG_CHARS:]
            db.commit()
            db.refresh(row)
            return row
        # Finalize with a consistent lock order (run row first, then the credit
        # reservation — the same order cancel uses) so a concurrent cancel can
        # never deadlock or be clobbered.
        locked = db.execute(
            update(ResearchRun)
            .where(ResearchRun.id == run_id, ResearchRun.status == "running")
            .values(status="running")
        ).rowcount
        if not locked:
            db.rollback()
            row = db.get(ResearchRun, run_id)
            return row
        row.logs = logs[-MAX_LOG_CHARS:]
        if outcome.cancelled:
            row.status = "cancelled"
            row.error = outcome.error
            _refund_run_reservation(db, row, "RESEARCH_RUN_CANCELLED_BY_USER")
        elif outcome.error:
            row.status = "failed"
            row.error = outcome.error
            _refund_run_reservation(db, row, "RESEARCH_RUN_EXECUTION_FAILED")
        else:
            row.metrics_json = _read_metrics(job_dir / "out")
            row.figures_json = _persist_figures(row, outcome.figures)
            row.status = "completed"
            row.error = None
            if row.credits_reserved:
                settlement = settle_task(
                    db,
                    row.user_id,
                    _reservation_for(row),
                    RESEARCH_RUN_CREDITS,
                    {"research_run_id": row.id},
                )
                row.credits_spent = settlement.actual
        row.completed_at = _now()
        db.commit()
        db.refresh(row)
        logger.info("research_run_finished run_id=%s status=%s datasets=%d", row.id, row.status, len(manifest))
        return row
    except Exception as exc:
        db.rollback()
        row = db.get(ResearchRun, run_id)
        row.status = "failed"
        row.error = str(exc)[:500]
        row.completed_at = _now()
        _refund_run_reservation(db, row, "RESEARCH_RUN_WORKER_FAILED")
        db.commit()
        logger.exception("research_run_failed run_id=%s", run_id)
        return row
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def serialize_research_run(row: ResearchRun) -> dict:
    return {
        "run_id": row.id,
        "status": row.status,
        "code_hash": row.code_hash,
        "dataset_refs": row.dataset_refs_json or [],
        "limits": row.limits_json or {},
        "metrics_json": row.metrics_json or {},
        "figures": list(row.figures_json or []),
        "logs_tail": (row.logs or "")[-LOG_TAIL_CHARS:],
        "error": row.error,
        "credits_reserved": row.credits_reserved or 0,
        "credits_spent": row.credits_spent or 0,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }
