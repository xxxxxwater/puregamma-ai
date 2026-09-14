#!/usr/bin/env bash
# Wait for the previous holder's pg:lock:scheduler TTL to expire, then restart
# the scheduler so it acquires the lock immediately instead of at its next
# crash-loop backoff. Read-only until the key is free.
set -uo pipefail

for i in $(seq 1 40); do
  holder="$(docker exec puregamma-ai-redis-1 sh -c 'redis-cli -a "$REDIS_PASSWORD" --no-auth-warning get pg:lock:scheduler' 2>/dev/null | tr -d '\r')"
  ttl="$(docker exec puregamma-ai-redis-1 sh -c 'redis-cli -a "$REDIS_PASSWORD" --no-auth-warning ttl pg:lock:scheduler' 2>/dev/null | tr -d '\r')"
  status="$(docker inspect puregamma-ai-scheduler-1 --format '{{.State.Status}}' 2>/dev/null)"
  hostname="$(docker inspect puregamma-ai-scheduler-1 --format '{{.Config.Hostname}}' 2>/dev/null)"
  echo "$(date -u +%T) ttl=$ttl holder=$holder status=$status host=$hostname"

  if [ "$status" = "running" ] && [ "${holder%%:*}" = "$hostname" ]; then
    echo "TAKEOVER_OK (already holding the lock)"
    break
  fi
  if [ "$ttl" = "-2" ]; then
    echo "lock is free; restarting the scheduler so it starts now"
    docker restart puregamma-ai-scheduler-1 >/dev/null
    sleep 25
    status="$(docker inspect puregamma-ai-scheduler-1 --format '{{.State.Status}}' 2>/dev/null)"
    holder="$(docker exec puregamma-ai-redis-1 sh -c 'redis-cli -a "$REDIS_PASSWORD" --no-auth-warning get pg:lock:scheduler' 2>/dev/null | tr -d '\r')"
    hostname="$(docker inspect puregamma-ai-scheduler-1 --format '{{.Config.Hostname}}' 2>/dev/null)"
    echo "after restart: status=$status holder=$holder host=$hostname"
    [ "$status" = "running" ] && { echo "TAKEOVER_OK"; break; }
  fi
  sleep 60
done

echo "=== final ==="
docker ps -a --filter 'name=puregamma-ai-scheduler-1' --format '{{.Status}}\t{{.Image}}'
docker exec puregamma-ai-redis-1 sh -c 'redis-cli -a "$REDIS_PASSWORD" --no-auth-warning get pg:lock:scheduler'
