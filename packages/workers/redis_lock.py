from __future__ import annotations

import logging
import os
import socket

logger = logging.getLogger("puregamma.workers.lock")

#: TTL applied to a lock while it is being held. It must be comfortably longer
#: than the renewal interval used by long-running holders (the scheduler renews
#: every 5 minutes), so a missed renewal never drops a still-live lock.
LOCK_HOLDER_TTL_SECONDS = 900


def instance_identity() -> str:
    """Identify this process as a lock owner.

    Hostname plus pid is enough for an operator to answer "is this holder still
    alive?" — which is the question that previously could not be answered, and
    is why stale locks had to be inferred from timing.
    """
    try:
        host = socket.gethostname()
    except Exception:  # noqa: BLE001 - a lock must never fail on identification
        host = "unknown-host"
    return f"{host}:{os.getpid()}"


def lock_key(name: str) -> str:
    """Lock keys are shared with other services, so the format is unchanged."""
    return f"pg:lock:{name}"


def acquire_redis_lock(name: str, ttl_seconds: int = 600, *, token: str | None = None) -> tuple[bool, str | None]:
    """Acquire a distributed lock, recording who holds it.

    Returns ``(acquired, token)``. The token is what an owner must present to
    renew or release, so one instance can never extend or delete another
    instance's lock.

    Fails open when Redis is unavailable: liveness wins, and the idempotency
    keys on the underlying tasks remain the last line of defense.
    """
    owner = token or instance_identity()
    try:
        from apps.api.redis_client import get_redis

        ok = get_redis().set(lock_key(name), owner, nx=True, ex=ttl_seconds)
        return bool(ok), (owner if ok else None)
    except Exception:
        logger.warning("redis_lock_unavailable name=%s", name)
        return True, owner


def renew_redis_lock(name: str, token: str, ttl_seconds: int = 600) -> bool:
    """Extend a lock we still own.

    ``acquire_redis_lock`` uses ``SET NX``, so calling it again to "renew" is a
    no-op that returns False and leaves the TTL untouched — a previous version
    of this module did exactly that from the scheduler's renewal job, so the
    lock was never actually kept alive. This compares the stored owner instead
    of blindly overwriting, so a lock that has legitimately moved on is never
    revived.
    """
    try:
        from apps.api.redis_client import get_redis

        current = get_redis().get(lock_key(name))
        if current is None:
            return False
        if isinstance(current, bytes):
            current = current.decode("utf-8", "replace")
        if current != token:
            return False
        get_redis().expire(lock_key(name), ttl_seconds)
        return True
    except Exception:
        logger.warning("redis_lock_renew_failed name=%s", name)
        return False


def release_redis_lock(name: str, token: str | None = None) -> bool:
    """Release a lock, but only the one we hold.

    A token-less call keeps the historical unconditional behaviour; callers that
    hold a token get ownership checking, so shutting down one instance cannot
    delete a successor's lock.
    """
    try:
        from apps.api.redis_client import get_redis

        client = get_redis()
        if token is None:
            client.delete(lock_key(name))
            return True
        current = client.get(lock_key(name))
        if isinstance(current, bytes):
            current = current.decode("utf-8", "replace")
        if current != token:
            return False
        client.delete(lock_key(name))
        return True
    except Exception:
        return False


def lock_status(name: str) -> dict[str, object]:
    """Describe the current lock for operators and deployment checks.

    ``owner_alive_hint`` is deliberately not derived here: deciding whether a
    hostname:pid is still alive is an operational judgement (the process may
    live in another container), so this reports the facts and leaves the call
    to the caller.
    """
    try:
        from apps.api.redis_client import get_redis

        client = get_redis()
        holder = client.get(lock_key(name))
        if isinstance(holder, bytes):
            holder = holder.decode("utf-8", "replace")
        return {
            "key": lock_key(name),
            "held": holder is not None,
            "holder": holder,
            "ttl_seconds": client.ttl(lock_key(name)) if holder is not None else None,
        }
    except Exception as exc:  # noqa: BLE001
        return {"key": lock_key(name), "held": None, "holder": None, "ttl_seconds": None, "error": type(exc).__name__}
