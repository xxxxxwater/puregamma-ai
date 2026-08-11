from __future__ import annotations

import logging
import time
from collections import defaultdict

from apps.api.config import get_settings

logger = logging.getLogger("puregamma.ops")


# Process-level counters for the /metrics endpoint (reset on restart).
METRICS_COUNTERS: dict[str, int] = defaultdict(int)
METRICS_STARTED_AT = time.time()


def bump_metric(name: str) -> None:
    METRICS_COUNTERS[name] += 1


def notify_ops(message: str, *, level: str = "warning") -> None:
    """Ship an operations alert to the configured Slack webhook / Telegram chat.

    Alerts cover webhook failures, job timeouts, relay outages and other
    operational events that would otherwise only surface through customer
    complaints. When no channel is configured the alert is logged (with the
    severity) so a deployment without OPS_ALERT_* still leaves a trail.
    """
    settings = get_settings()
    if settings.ops_alert_webhook:
        try:
            import httpx

            httpx.post(
                settings.ops_alert_webhook,
                json={"text": f"[{level.upper()}] PureGamma: {message}"},
                timeout=10,
            )
        except Exception as exc:  # never let alerting break the caller
            logger.exception("ops_alert_send_failed: %s", exc)
    elif settings.ops_alert_chat_id and settings.telegram_bot_token:
        try:
            import httpx

            httpx.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={"chat_id": settings.ops_alert_chat_id, "text": f"[{level.upper()}] PureGamma: {message}"},
                timeout=10,
            )
        except Exception as exc:
            logger.exception("ops_alert_send_failed: %s", exc)
    else:
        log = logger.warning if level == "warning" else logger.error
        log("ops_alert(%s): %s", level, message)
