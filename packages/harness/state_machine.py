"""Idempotent, auditable state machine for HarnessResearchRun.

States: queued -> preparing -> running -> validating ->
completed | degraded | failed | canceled | timed_out.

Every transition writes a ``HarnessRunStateTransition`` audit row. Calling
``transition_run`` twice with the same target is a no-op (idempotent), which
makes Celery retries and duplicate events safe.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from packages.database.models import HarnessResearchRun, HarnessRunStateTransition, utcnow

HARNESS_RUN_STATES: frozenset[str] = frozenset(
    {"queued", "preparing", "running", "validating", "completed", "degraded", "failed", "canceled", "timed_out"}
)

TERMINAL_STATES: frozenset[str] = frozenset({"completed", "degraded", "failed", "canceled", "timed_out"})

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"preparing", "canceled", "failed", "timed_out"}),
    "preparing": frozenset({"running", "canceled", "failed", "timed_out"}),
    "running": frozenset({"validating", "canceled", "failed", "timed_out"}),
    "validating": frozenset({"completed", "degraded", "canceled", "failed", "timed_out"}),
    "completed": frozenset(),
    "degraded": frozenset(),
    "failed": frozenset(),
    "canceled": frozenset(),
    "timed_out": frozenset(),
}


class IllegalStateTransition(RuntimeError):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"illegal harness run transition: {current} -> {target}")
        self.current = current
        self.target = target


def transition_run(
    db: Session,
    run: HarnessResearchRun,
    to_status: str,
    *,
    reason: str | None = None,
    actor: str = "system",
    timeout_seconds: int | None = None,
) -> bool:
    """Move ``run`` to ``to_status`` if legal and different. Returns True on change.

    Idempotent: if the run already has ``to_status`` this is a no-op and
    returns False. Illegal transitions raise ``IllegalStateTransition``.

    Concurrency safety: the state change is a conditional UPDATE
    (``WHERE status = expected``), so two workers racing on the same run can
    only ever apply ONE effective transition; the loser observes rowcount 0,
    reloads the current state, and returns False without writing an audit
    row. This makes Celery retries and duplicate events safe without a
    separate lock.
    """
    if to_status not in HARNESS_RUN_STATES:
        raise IllegalStateTransition(run.status, to_status)
    if run.status == to_status:
        return False
    if to_status not in ALLOWED_TRANSITIONS.get(run.status, frozenset()):
        raise IllegalStateTransition(run.status, to_status)

    now = utcnow()
    from_status = run.status
    values: dict[str, Any] = {"status": to_status}
    if to_status == "running":
        values["started_at"] = now
    if to_status in TERMINAL_STATES:
        values["completed_at"] = now
    if to_status == "canceled":
        values["canceled_at"] = now
    if to_status == "timed_out":
        values["timeout_at"] = now
    if timeout_seconds is not None and to_status == "preparing" and run.timeout_at is None:
        values["timeout_at"] = now + timedelta(seconds=timeout_seconds)

    updated = (
        db.query(HarnessResearchRun)
        .filter(
            HarnessResearchRun.id == run.id,
            HarnessResearchRun.status == from_status,
        )
        .update(values, synchronize_session=False)
    )
    if updated != 1:
        # Another worker already transitioned this run. Realign the caller's
        # object with the authoritative row and treat this as a no-op.
        fresh = db.get(HarnessResearchRun, run.id)
        if fresh is not None:
            run.status = fresh.status
        return False

    run.status = to_status
    if to_status == "running" and run.started_at is None:
        run.started_at = now
    if to_status in TERMINAL_STATES:
        run.completed_at = now
    if to_status == "canceled":
        run.canceled_at = now
    if to_status == "timed_out":
        run.timeout_at = run.timeout_at or now
    if timeout_seconds is not None and run.timeout_at is None:
        run.timeout_at = now + timedelta(seconds=timeout_seconds)

    db.add(
        HarnessRunStateTransition(
            research_run_id=run.id,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            actor=actor,
            trace_id=run.trace_id,
        )
    )
    return True
