#!/usr/bin/env bash
# Post-deploy acceptance smoke for the PureGamma API.
#
# Checks (curl + jq, exits non-zero on any failure, prints a PASS/FAIL table):
#   1. GET /health                         -> 200, status=ok
#   2. GET /ready                          -> 200, database=ok
#   3. GET /opportunities/mstr-btc         -> 200, sourceStatus in live|delayed|unavailable,
#                                             every metric carries sourceUrl
#   4. GET /api/research/today (no auth)   -> 401
#   5. POST /auth/email/login (demo)       -> 200 (cookie jar)
#   6. GET /reports (demo cookie)          -> 200
#   7. PUT /notifications/preferences/daily-brief (multi-select channels)
#      + GET round-trip                    -> channels echoed back exactly
#   8. POST /auth/internal-admin-login     -> 200 (admin cookie jar)
#   9. GET /admin/overview (admin cookie)  -> 200
#
# Credentials come from the environment ONLY — never hardcoded:
#   PG_SMOKE_BASE_URL        e.g. https://api.puregamma.ai (default http://localhost:8000)
#   PG_SMOKE_DEMO_EMAIL      demo user email
#   PG_SMOKE_DEMO_PASSWORD   demo user password
#   PG_SMOKE_ADMIN_USERNAME  internal admin username
#   PG_SMOKE_ADMIN_PASSWORD  internal admin password
#   PG_SMOKE_CHANNELS        JSON array for the multi-select round-trip
#                            (default ["email","telegram"]; every channel must
#                            be entitled for the demo user's plan, e.g. Pro+)
#
# Usage:
#   PG_SMOKE_BASE_URL=https://api.puregamma.ai \
#   PG_SMOKE_DEMO_EMAIL=... PG_SMOKE_DEMO_PASSWORD=... \
#   PG_SMOKE_ADMIN_USERNAME=... PG_SMOKE_ADMIN_PASSWORD=... \
#   bash scripts/acceptance-smoke.sh
set -u

BASE_URL="${PG_SMOKE_BASE_URL:-http://localhost:8000}"
BASE_URL="${BASE_URL%/}"
DEMO_EMAIL="${PG_SMOKE_DEMO_EMAIL:-}"
DEMO_PASSWORD="${PG_SMOKE_DEMO_PASSWORD:-}"
ADMIN_USERNAME="${PG_SMOKE_ADMIN_USERNAME:-}"
ADMIN_PASSWORD="${PG_SMOKE_ADMIN_PASSWORD:-}"
CHANNELS="${PG_SMOKE_CHANNELS:-[\"email\",\"telegram\"]}"

DEMO_JAR="$(mktemp)"
ADMIN_JAR="$(mktemp)"
trap 'rm -f "$DEMO_JAR" "$ADMIN_JAR"' EXIT

FAILURES=0
RESULTS=()

record() { # record <name> <ok 0|1> <detail>
  if [ "$2" -eq 0 ]; then
    RESULTS+=("PASS|$1|$3")
  else
    RESULTS+=("FAIL|$1|$3")
    FAILURES=$((FAILURES + 1))
  fi
}

# request <method> <path> [curl extra args...] -> sets CODE and BODY
request() {
  local method="$1" path="$2"
  shift 2
  local response
  response="$(curl -sS -m 30 -w $'\n%{http_code}' -X "$method" \
    -H "Origin: $BASE_URL" -H "Content-Type: application/json" \
    "$@" "$BASE_URL$path" 2>&1)"
  CODE="$(printf '%s' "$response" | tail -n1)"
  BODY="$(printf '%s' "$response" | sed '$d')"
}

jq_check() { # jq_check <expr> : 0 when jq -e succeeds
  printf '%s' "$BODY" | jq -e "$1" >/dev/null 2>&1
}

echo "acceptance-smoke: $BASE_URL"

# 1. /health
request GET /health
if [ "$CODE" = "200" ] && jq_check '.status == "ok"'; then
  record "GET /health" 0 "status=ok"
else
  record "GET /health" 1 "http=$CODE body=$(printf '%s' "$BODY" | head -c 200)"
fi

# 2. /ready
request GET /ready
if [ "$CODE" = "200" ] && jq_check '.database == "ok"'; then
  record "GET /ready" 0 "database=ok"
else
  record "GET /ready" 1 "http=$CODE body=$(printf '%s' "$BODY" | head -c 200)"
fi

# 3. /opportunities/mstr-btc
request GET /opportunities/mstr-btc
if [ "$CODE" = "200" ] \
  && jq_check '.sourceStatus == "live" or .sourceStatus == "delayed" or .sourceStatus == "unavailable"' \
  && jq_check '([.metrics[]? | select((.sourceUrl // "") == "")] | length) == 0'; then
  STATUS="$(printf '%s' "$BODY" | jq -r '.sourceStatus' 2>/dev/null)"
  record "GET /opportunities/mstr-btc" 0 "sourceStatus=$STATUS metrics carry sourceUrl"
else
  record "GET /opportunities/mstr-btc" 1 "http=$CODE body=$(printf '%s' "$BODY" | head -c 200)"
fi

# 4. /api/research/today unauthenticated -> 401
request GET /api/research/today
if [ "$CODE" = "401" ]; then
  record "GET /api/research/today (unauth)" 0 "http=401"
else
  record "GET /api/research/today (unauth)" 1 "expected 401, got http=$CODE"
fi

# 5. demo login
if [ -n "$DEMO_EMAIL" ] && [ -n "$DEMO_PASSWORD" ]; then
  request POST /auth/email/login -d "{\"email\":\"$DEMO_EMAIL\",\"password\":\"$DEMO_PASSWORD\"}" -c "$DEMO_JAR"
  if [ "$CODE" = "200" ] && jq_check '.user.id'; then
    record "POST /auth/email/login (demo)" 0 "user=$DEMO_EMAIL"
  else
    record "POST /auth/email/login (demo)" 1 "http=$CODE body=$(printf '%s' "$BODY" | head -c 200)"
  fi

  # 6. /reports with demo cookie
  request GET /reports -b "$DEMO_JAR"
  if [ "$CODE" = "200" ] && jq_check 'has("reports")'; then
    record "GET /reports (demo)" 0 "http=200"
  else
    record "GET /reports (demo)" 1 "http=$CODE body=$(printf '%s' "$BODY" | head -c 200)"
  fi

  # 7. digest preference PUT (multi-select channels) + GET round-trip
  request PUT /notifications/preferences/daily-brief -b "$DEMO_JAR" \
    -d "{\"enabled\":true,\"channels\":$CHANNELS,\"timezone\":\"UTC\",\"local_time\":\"08:30\"}"
  if [ "$CODE" = "200" ] && jq_check ".preference.channels == $CHANNELS"; then
    request GET /notifications/preferences/daily-brief -b "$DEMO_JAR"
    if [ "$CODE" = "200" ] && jq_check ".preference.channels == $CHANNELS"; then
      record "daily-brief channels round-trip" 0 "channels=$CHANNELS"
    else
      record "daily-brief channels round-trip" 1 "GET mismatch: http=$CODE body=$(printf '%s' "$BODY" | head -c 200)"
    fi
  else
    record "daily-brief channels round-trip" 1 "PUT failed: http=$CODE body=$(printf '%s' "$BODY" | head -c 200)"
  fi
else
  record "demo login + authenticated checks" 1 "PG_SMOKE_DEMO_EMAIL/PG_SMOKE_DEMO_PASSWORD not set"
fi

# 8. admin login
if [ -n "$ADMIN_USERNAME" ] && [ -n "$ADMIN_PASSWORD" ]; then
  request POST /auth/internal-admin-login -d "{\"username\":\"$ADMIN_USERNAME\",\"password\":\"$ADMIN_PASSWORD\"}" -c "$ADMIN_JAR"
  if [ "$CODE" = "200" ] && jq_check '.user.role == "admin"'; then
    record "POST /auth/internal-admin-login" 0 "role=admin"
  else
    record "POST /auth/internal-admin-login" 1 "http=$CODE body=$(printf '%s' "$BODY" | head -c 200)"
  fi

  # 9. /admin/overview with admin cookie
  request GET /admin/overview -b "$ADMIN_JAR"
  if [ "$CODE" = "200" ]; then
    record "GET /admin/overview (admin)" 0 "http=200"
  else
    record "GET /admin/overview (admin)" 1 "http=$CODE body=$(printf '%s' "$BODY" | head -c 200)"
  fi
else
  record "admin login + overview" 1 "PG_SMOKE_ADMIN_USERNAME/PG_SMOKE_ADMIN_PASSWORD not set"
fi

echo "------------------------------ ACCEPTANCE SMOKE ------------------------------"
for row in "${RESULTS[@]}"; do
  status="${row%%|*}"
  rest="${row#*|}"
  name="${rest%%|*}"
  detail="${rest#*|}"
  printf '%-4s  %-42s %s\n' "$status" "$name" "$detail"
done
echo "------------------------------------------------------------------------------"
if [ "$FAILURES" -gt 0 ]; then
  echo "RESULT: FAIL ($FAILURES failing checks)"
  exit 1
fi
echo "RESULT: PASS"
exit 0
