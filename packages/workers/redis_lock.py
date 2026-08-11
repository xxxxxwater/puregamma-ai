from __future__ import annotations

import logging

logger = logging.getLogger("puregamma.workers.lock")


def acquire_redis_lock(name: str, ttl_seconds: int = 600) -> bool:
    """Acquire a distributed lock via Redis SET NX EX.

    Guards Celery tasks against duplicate execution when more than one worker
    or scheduler instance runs (e.g. after a failed restart that left a stale
    scheduler behind). Idempotency keys remain the last line of defense.
    """
    try:
        from apps.api.redis_client import get_redis

        ok = get_redis().set(f"pg:lock:{name}", "1", nx=True, ex=ttl_seconds)
        return bool(ok)
    except Exception:
        # Redis down: fail open for liveness, idempotency keys still apply.
        logger.warning("redis_lock_unavailable name=%s", name)
        return True


def release_redis_lock(name: str) -> None:
    try:
        from apps.api.redis_client import get_redis

        get_redis().delete(f"pg:lock:{name}")
    except Exception:
        pass
