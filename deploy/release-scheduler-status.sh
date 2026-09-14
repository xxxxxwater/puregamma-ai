#!/usr/bin/env bash
# Check the scheduler's lock and uptime. Read-only.
set -uo pipefail
echo "=== scheduler container ==="
docker ps -a --filter name=puregamma-ai-scheduler-1 --format '{{.Status}}\t{{.Image}}'
docker inspect puregamma-ai-scheduler-1 --format 'hostname={{.Config.Hostname}} status={{.State.Status}} restarts={{.RestartCount}} since={{.State.StartedAt}}'
echo "=== lock (holder should be that hostname) ==="
docker exec puregamma-ai-redis-1 sh -c 'redis-cli -a "$REDIS_PASSWORD" --no-auth-warning get pg:lock:scheduler'
docker exec puregamma-ai-redis-1 sh -c 'redis-cli -a "$REDIS_PASSWORD" --no-auth-warning pttl pg:lock:scheduler'
