#!/usr/bin/env bash
# Wait for the promoted scheduler to take over once the previous holder's Redis
# lock TTL expires, then report. Read-only apart from the wait itself.
set -uo pipefail

for i in $(seq 1 30); do
  ttl="$(docker exec puregamma-ai-redis-1 sh -c 'redis-cli -a "$REDIS_PASSWORD" --no-auth-warning ttl pg:lock:scheduler' 2>/dev/null | tr -d '\r')"
  holder="$(docker exec puregamma-ai-redis-1 sh -c 'redis-cli -a "$REDIS_PASSWORD" --no-auth-warning get pg:lock:scheduler' 2>/dev/null | tr -d '\r')"
  status="$(docker inspect puregamma-ai-scheduler-1 --format '{{.State.Status}}' 2>/dev/null)"
  restarts="$(docker inspect puregamma-ai-scheduler-1 --format '{{.RestartCount}}' 2>/dev/null)"
  hostname="$(docker inspect puregamma-ai-scheduler-1 --format '{{.Config.Hostname}}' 2>/dev/null)"
  echo "$(date -u +%T) ttl=$ttl holder=$holder status=$status restarts=$restarts host=$hostname"
  # The lock value is "<hostname>:<pid>", so the container owns it when its own
  # hostname is the prefix. Comparing the whole value never matches.
  if [ "$status" = "running" ] && [ "${holder%%:*}" = "$hostname" ]; then
    echo "SCHEDULER_TAKEOVER_OK"
    break
  fi
  sleep 60
done

echo "--- final state ---"
docker ps -a --filter 'name=puregamma-ai-scheduler-1' --format '{{.Status}}\t{{.Image}}'
echo "--- last log lines ---"
docker logs --tail 12 puregamma-ai-scheduler-1 2>&1 | tail -12
echo "=== all puregamma containers ==="
docker ps --filter 'name=puregamma-ai-' --format '{{.Names}}\t{{.Status}}\t{{.Image}}'
