#!/usr/bin/env bash
# Single-server resource + queue alerts for LIVE trading operations.
#
# Alerts on: disk, memory, CPU load, docker container health, and Celery
# queue depth. Sends email via the existing ops alert path (IMessage/webhook
# fallback handled by ops_alert.py on the server) and exits non-zero so cron
# can report failures.
#
# cron example (root, every 5 minutes):
#   */5 * * * * /puregamma/app/deploy/live-trading/resource-alerts.sh >> /var/log/puregamma-alerts.log 2>&1
set -Eeuo pipefail

ROOT_DIR="${PUREGAMMA_ROOT:-/puregamma/app}"
DISK_ALERT_PCT="${LIVE_ALERT_DISK_PCT:-85}"
MEM_ALERT_PCT="${LIVE_ALERT_MEM_PCT:-90}"
LOAD_ALERT="${LIVE_ALERT_LOAD:-8}"          # 1-min load average threshold
QUEUE_ALERT="${LIVE_ALERT_QUEUE_DEPTH:-200}"
ALERT_EMAIL="${OPS_ALERT_EMAIL:-}"
problems=()

# --- disk ------------------------------------------------------------------
disk_pct="$(df -P /var/backups | awk 'NR==2 {gsub("%","",$5); print $5}')"
if [[ -n "${disk_pct}" && "${disk_pct}" -ge "${DISK_ALERT_PCT}" ]]; then
  problems+=("disk=${disk_pct}%")
fi

# --- memory ----------------------------------------------------------------
mem_pct="$(free 2>/dev/null | awk '/Mem:/ {printf "%d", ($3/$2)*100}')"
if [[ -n "${mem_pct}" && "${mem_pct}" -ge "${MEM_ALERT_PCT}" ]]; then
  problems+=("memory=${mem_pct}%")
fi

# --- CPU load --------------------------------------------------------------
load1="$(awk '{print $1}' /proc/loadavg 2>/dev/null | tr -d '\n')"
if [[ -n "${load1}" ]]; then
  if awk -v load="${load1}" -v limit="${LOAD_ALERT}" 'BEGIN { exit !(load >= limit) }'; then
    problems+=("load1=${load1}")
  fi
fi

# --- container health ------------------------------------------------------
cd "${ROOT_DIR}"
compose=(docker compose --env-file .env -f docker-compose.production.yml)
unhealthy="$("${compose[@]}" ps --format '{{.Name}} {{.Status}}' 2>/dev/null | grep -ci 'unhealthy' || true)"
if [[ "${unhealthy}" -gt 0 ]]; then
  problems+=("unhealthy_containers=${unhealthy}")
fi

# --- Celery queue depth ----------------------------------------------------
queue_depth="$("${compose[@]}" exec -T redis redis-cli -a "${REDIS_PASSWORD:-}" llen celery 2>/dev/null | tr -dc '0-9')"
if [[ -n "${queue_depth}" && "${queue_depth}" -ge "${QUEUE_ALERT}" ]]; then
  problems+=("celery_queue=${queue_depth}")
fi

if [[ "${#problems[@]}" -gt 0 ]]; then
  message="[live-trading-resource-alert] $(IFS=' '; echo "${problems[*]}")"
  echo "${message}" >&2
  if [[ -n "${ALERT_EMAIL}" ]] && command -v mail >/dev/null 2>&1; then
    echo "${message}" | mail -s "PureGamma LIVE resource alert" "${ALERT_EMAIL}"
  fi
  exit 1
fi
exit 0
