#!/usr/bin/env bash
set -eu
# =========================================================================
# PureGamma AI Gateway Activation Script
# Usage: bash deploy/activate-gateway.sh <admin-jwt-token>
# =========================================================================

TOKEN="${1:?Usage: $0 <admin-jwt-token>}"
BASE="${2:-https://api.puregamma.ai}"
H="Authorization: Bearer $TOKEN"
H2="Content-Type: application/json"

echo "=== Bootstrap Gateway Catalog ==="
curl -sf -X POST "$BASE/admin/gateway/bootstrap" -H "$H" | python3 -m json.tool
echo ""

echo "=== Enable Providers ==="
for p in deepseek moonshot glm; do
  status=$(curl -sf -X PUT "$BASE/admin/gateway/providers/$p" -H "$H" -H "$H2" -d '{"enabled":true}' | python3 -c "import sys,json; print(json.load(sys.stdin)['enabled'])" 2>/dev/null || echo "failed")
  echo "  $p: $status"
done
echo ""

echo "=== Sync Provider Metadata ==="
curl -sf -X POST "$BASE/admin/gateway/sync" -H "$H" | python3 -m json.tool
echo ""

echo "=== Run Health Checks ==="
curl -sf -X POST "$BASE/admin/gateway/providers/healthcheck" -H "$H" | python3 -m json.tool
echo ""

echo "=== Approve Pending Price Revisions ==="
REVISIONS=$(curl -sf "$BASE/admin/gateway/prices/pending" -H "$H")
if echo "$REVISIONS" | python3 -c "
import sys, json
revisions = json.load(sys.stdin).get('revisions', [])
if not revisions:
    print('No pending revisions.')
    sys.exit(0)
for r in revisions:
    print(r['id'])
" 2>/dev/null; then
  echo ""
else
  echo "  No pending pricing revisions."
fi

echo ""
echo "=== Gateway Activation Complete ==="
echo "Test: curl -s $BASE/v1/models -H 'Authorization: Bearer sk-pg-...' | python3 -m json.tool"
echo ""
echo "Gateway dashboard: https://app.puregamma.ai/gateway"
echo "Admin management: POST $BASE/admin/gateway/*"
