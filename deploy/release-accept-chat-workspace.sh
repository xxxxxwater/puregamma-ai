#!/usr/bin/env bash
# Post-deploy acceptance against the live site, run from the server.
set -uo pipefail

echo "=== scheduler state ==="
docker ps -a --filter 'name=puregamma-ai-scheduler-1' --format '{{.Names}}\t{{.Status}}\t{{.Image}}'
docker logs --tail 6 puregamma-ai-scheduler-1 2>&1 | tail -6

echo "=== scheduler lock holder vs container hostnames ==="
docker exec puregamma-ai-redis-1 sh -c 'redis-cli -a "$REDIS_PASSWORD" --no-auth-warning get pg:lock:scheduler' 2>/dev/null
docker inspect puregamma-ai-scheduler-1 --format 'scheduler hostname {{.Config.Hostname}} state={{.State.Status}} restarts={{.RestartCount}}'

echo "=== served JS chunks that carry the composer ==="
html="$(curl -s https://app.puregamma.ai/zh/chat)"
echo "$html" | grep -o '/_next/static/chunks/[A-Za-z0-9._/-]*\.js' | sort -u > /tmp/chunks.txt
wc -l < /tmp/chunks.txt
found=0
while read -r chunk; do
  if curl -s "https://app.puregamma.ai$chunk" | grep -q 'chat-composer-input'; then
    echo "FOUND chat-composer-input in $chunk"
    found=1
  fi
done < /tmp/chunks.txt
[ "$found" = "1" ] || echo "NOT FOUND in the /zh/chat payload chunks"
for extra in $(echo "$html" | grep -o '/_next/static/chunks/app/%5Blocale%5D/chat/[A-Za-z0-9._/-]*\.js' | sort -u); do
  curl -s "https://app.puregamma.ai$extra" | grep -q 'chat-composer-input' && echo "FOUND chat-composer-input in $extra"
done

echo "=== existing conversations still readable (counts + newest titles) ==="
docker exec puregamma-ai-postgres-1 psql -U puregamma -d puregamma -c \
  "select title, status, permission_mode, left(created_at::text,16) created from agent_conversations order by created_at desc limit 5;"

echo "=== a pre-existing conversation's messages are intact ==="
docker exec puregamma-ai-postgres-1 psql -U puregamma -d puregamma -tAc \
  "select c.id, c.permission_mode, count(m.id) msgs, max(left(m.content,40)) sample from agent_conversations c join agent_messages m on m.conversation_id=c.id group by c.id, c.permission_mode order by count(m.id) desc limit 3;"

echo "=== api errors since the promote ==="
docker logs --since 15m puregamma-ai-api-1 2>&1 | grep -iE 'traceback|error|exception' | grep -v 'INFO' | tail -10 || echo "(none)"

echo "=== acceptance done ==="
