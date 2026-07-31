#!/usr/bin/env bash
set -eu
# ============================================================================
# Gateway 激活脚本 — 在服务器上执行
# Usage: bash setup-gateway.sh
# ============================================================================

ROOT_DIR="/opt/puregamma-ai"
cd "${ROOT_DIR}"

# 1. 生成 GATEWAY_API_KEY_PEPPER
PEPPER=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
echo "Generated GATEWAY_API_KEY_PEPPER"

# 2. 更新 .env（只写入本次生成的独立 pepper；Provider Key 必须由运维
#    通过服务器密钥管理或 .env 预先提供，绝不写在脚本中。）
if grep -q '^GATEWAY_API_KEY_PEPPER=' .env; then
  if grep -q '^GATEWAY_API_KEY_PEPPER=$' .env; then
    sed -i '' "s|^GATEWAY_API_KEY_PEPPER=$|GATEWAY_API_KEY_PEPPER=${PEPPER}|" .env 2>/dev/null || \
      sed -i "s|^GATEWAY_API_KEY_PEPPER=$|GATEWAY_API_KEY_PEPPER=${PEPPER}|" .env
  else
    echo "GATEWAY_API_KEY_PEPPER already exists; leaving it unchanged."
  fi
else
  printf '\nGATEWAY_API_KEY_PEPPER=%s\n' "${PEPPER}" >> .env
fi

if ! grep -q '^GATEWAY_DEEPSEEK_API_KEY=.' .env \
  && ! grep -q '^GATEWAY_MOONSHOT_API_KEY=.' .env \
  && ! grep -q '^GATEWAY_GLM_API_KEY=.' .env; then
  echo "ERROR: Configure at least one Provider Key in the server's .env before enabling Gateway."
  exit 1
fi

echo "Updated Gateway pepper; Provider keys remain server-managed."

# 3. 重启 API
echo "Restarting API container..."
docker compose --env-file .env -f docker-compose.production.yml up -d --build api

echo "Waiting for API to be healthy..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    echo "API is healthy."
    break
  fi
  sleep 3
done

# 4. 获取 Admin Token（使用 internal admin login）
ADMIN_TOKEN=""
if grep -q "INTERNAL_ADMIN_LOGIN_ENABLED=true" .env 2>/dev/null; then
  ADMIN_USERNAME=$(grep INTERNAL_ADMIN_USERNAME .env | cut -d= -f2- | tr -d ' ')
  ADMIN_PASSWORD_HASH=$(grep INTERNAL_ADMIN_PASSWORD_HASH .env | cut -d= -f2- | tr -d ' ')
  if [ -n "$ADMIN_USERNAME" ] && [ -n "$ADMIN_PASSWORD_HASH" ]; then
    echo "Found internal admin config. Attempting login..."
    ADMIN_TOKEN=$(curl -sf -X POST http://localhost:8000/auth/internal-login \
      -H "Content-Type: application/json" \
      -d "{\"username\":\"$ADMIN_USERNAME\",\"password_hash\":\"$ADMIN_PASSWORD_HASH\"}" \
      | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])" 2>/dev/null || echo "")
  fi
fi

if [ -z "$ADMIN_TOKEN" ]; then
  echo "=== Manual Step Required ==="
  echo "Login to https://app.puregamma.ai as admin, get your JWT token (from browser DevTools > Network > request headers > Authorization)"
  echo "Then run: bash /opt/puregamma-ai/deploy/activate-gateway.sh <YOUR_ADMIN_JWT_TOKEN>"
  echo ""
  echo "--- OR paste your admin JWT token here: ---"
  read -r -p "Admin JWT Token: " ADMIN_TOKEN
fi

if [ -z "$ADMIN_TOKEN" ] || [ "$ADMIN_TOKEN" = "skip" ]; then
  echo "Skipping bootstrap. Run manually: bash /opt/puregamma-ai/deploy/activate-gateway.sh <token>"
  exit 0
fi

# 5. Bootstrap & Activate
echo ""
echo "=== Bootstrapping Gateway ==="
curl -sf -X POST http://localhost:8000/admin/gateway/bootstrap \
  -H "Authorization: Bearer $ADMIN_TOKEN" | python3 -m json.tool

echo ""
echo "=== Enabling Providers ==="
for p in deepseek moonshot; do
  RESULT=$(curl -sf -X PUT "http://localhost:8000/admin/gateway/providers/$p" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"enabled":true}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('enabled','?'))" 2>/dev/null || echo "failed")
  echo "  $p: enabled=$RESULT"
done

echo ""
echo "=== Syncing ==="
curl -sf -X POST http://localhost:8000/admin/gateway/sync \
  -H "Authorization: Bearer $ADMIN_TOKEN" | python3 -m json.tool

echo ""
echo "=== Approving Pricing ==="
PENDING=$(curl -sf http://localhost:8000/admin/gateway/prices/pending \
  -H "Authorization: Bearer $ADMIN_TOKEN")

REVISION_IDS=$(echo "$PENDING" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for r in data.get('revisions', []):
    print(r['id'])
" 2>/dev/null)

if [ -z "$REVISION_IDS" ]; then
  echo "  No pending revisions to approve."
else
  for rid in $REVISION_IDS; do
    curl -sf -X POST "http://localhost:8000/admin/gateway/prices/$rid/approve" \
      -H "Authorization: Bearer $ADMIN_TOKEN" >/dev/null
    echo "  Approved: $rid"
  done
fi

echo ""
echo "=== Setting Markup to 3000 bps (30%, i.e. 130% of official) ==="
curl -sf -X PUT http://localhost:8000/admin/gateway/pricing/markup \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"markup_bps": 3000}' | python3 -m json.tool

echo ""
echo "=== Verifying ==="
echo "Provider health:"
curl -sf -X POST http://localhost:8000/admin/gateway/providers/healthcheck \
  -H "Authorization: Bearer $ADMIN_TOKEN" | python3 -m json.tool

echo ""
echo "=== Gateway Activated ==="
echo "Public endpoint: https://api.puregamma.ai/v1"
echo "To verify: curl -s https://api.puregamma.ai/v1/models -H 'Authorization: Bearer sk-pg-...'"
