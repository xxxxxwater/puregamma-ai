#!/usr/bin/env bash
# Final state check after a release: containers, images, data, public routes.
set -uo pipefail
SHORT="${1:-8c165132}"

echo "=== containers ==="
docker ps --filter 'name=puregamma-ai-' --format '{{.Names}}\t{{.Status}}\t{{.Image}}'

echo "=== image ids for $SHORT ==="
for s in api worker scheduler web; do
  docker image inspect "puregamma-ai-$s:$SHORT" --format "$s {{.Id}}" 2>/dev/null || echo "$s MISSING"
done

echo "=== data (users/convs/msgs/attachments/ledger/head) ==="
docker exec puregamma-ai-postgres-1 psql -U puregamma -d puregamma -tAc \
  "select (select count(*) from users), (select count(*) from agent_conversations), (select count(*) from agent_messages), (select count(*) from agent_attachments), (select count(*) from credit_ledger), (select version_num from alembic_version);"

echo "=== acceptance leftovers (must be 0) ==="
docker exec puregamma-ai-postgres-1 psql -U puregamma -d puregamma -tAc \
  "select count(*) from users where email like '%@example.invalid';"

echo "=== public routes ==="
curl -s -o /dev/null -w 'api /health %{http_code}\n' https://api.puregamma.ai/health
curl -s -o /dev/null -w 'app /zh %{http_code}\n' https://app.puregamma.ai/zh
curl -s -o /dev/null -w 'app /zh/chat anon %{http_code}\n' https://app.puregamma.ai/zh/chat
curl -s -o /dev/null -w 'capabilities anon %{http_code}\n' https://api.puregamma.ai/api/agent/workspace-capabilities

echo "=== served web bundle matches the running image ==="
chunk="$(curl -s https://app.puregamma.ai/zh | grep -o '/_next/static/chunks/[A-Za-z0-9._-]*\.js' | head -1)"
echo "sampled chunk: $chunk"
docker exec puregamma-ai-web-1 sh -c "ls /app/.next-build/static/chunks | head -3"
docker exec puregamma-ai-web-1 grep -rl 'chat-composer-input' /app/.next-build/static/chunks | head -2

echo "=== api errors in the last 10 minutes ==="
docker logs --since 10m puregamma-ai-api-1 2>&1 | grep -icE 'traceback|exception'
