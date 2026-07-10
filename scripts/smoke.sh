#!/usr/bin/env bash
# Smoke-test the local API: health, payments, idempotency.
#
# Usage:
#   ./scripts/smoke.sh
#   BASE_URL=http://localhost:8000 API_KEY=secret ./scripts/smoke.sh
#   make smoke

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BASE_URL="${BASE_URL:-http://localhost:8000}"
IDEM_KEY="${IDEM_KEY:-order-$(date +%s)}"

if [[ -z "${API_KEY:-}" && -f .env ]]; then
  # shellcheck disable=SC2046
  export $(grep -E '^API_KEY=' .env | xargs)
fi
API_KEY="${API_KEY:-change-me-in-production}"

PASS=0
FAIL=0

green() { printf '\033[0;32m%s\033[0m\n' "$*"; }
red() { printf '\033[0;31m%s\033[0m\n' "$*"; }
bold() { printf '\033[1m%s\033[0m\n' "$*"; }

assert_http() {
  local label="$1"
  local expected="$2"
  local actual="$3"
  local body="$4"

  if [[ "$actual" == "$expected" ]]; then
    green "  OK   $label (HTTP $actual)"
    PASS=$((PASS + 1))
    if [[ -n "$body" ]]; then
      echo "       $body"
    fi
  else
    red "  FAIL $label (expected HTTP $expected, got $actual)"
    FAIL=$((FAIL + 1))
    if [[ -n "$body" ]]; then
      echo "       $body"
    fi
  fi
}

curl_json() {
  local method="$1"
  local url="$2"
  shift 2
  curl -sS -w "\n%{http_code}" -X "$method" "$url" "$@"
}

bold "Smoke test → $BASE_URL"
echo "API_KEY=${API_KEY:0:8}..."
echo

# --- Health ---
bold "1. Liveness"
RESP=$(curl_json GET "$BASE_URL/api/v1/health")
BODY=$(echo "$RESP" | sed '$d')
CODE=$(echo "$RESP" | tail -n1)
assert_http "GET /api/v1/health" "200" "$CODE" "$BODY"
echo

bold "2. Readiness"
RESP=$(curl_json GET "$BASE_URL/api/v1/health/ready")
BODY=$(echo "$RESP" | sed '$d')
CODE=$(echo "$RESP" | tail -n1)
assert_http "GET /api/v1/health/ready" "200" "$CODE" "$BODY"
echo

# --- Create payment ---
bold "3. Create payment"
CREATE_PAYLOAD='{
  "amount": "100.50",
  "currency": "RUB",
  "description": "Smoke test payment",
  "metadata": {"order_id": "smoke-1"},
  "webhook_url": "https://example.com/webhook"
}'

RESP=$(curl_json POST "$BASE_URL/api/v1/payments" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -H "Idempotency-Key: $IDEM_KEY" \
  -d "$CREATE_PAYLOAD")
BODY=$(echo "$RESP" | sed '$d')
CODE=$(echo "$RESP" | tail -n1)
assert_http "POST /api/v1/payments" "202" "$CODE" "$BODY"

PAYMENT_ID=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin)['payment_id'])" 2>/dev/null || true)
if [[ -z "${PAYMENT_ID:-}" ]]; then
  red "  FAIL could not parse payment_id"
  FAIL=$((FAIL + 1))
  echo
  red "Aborted: remaining checks skipped."
  exit 1
fi
echo "       payment_id=$PAYMENT_ID"
echo

# --- Get payment ---
bold "4. Get payment"
RESP=$(curl_json GET "$BASE_URL/api/v1/payments/$PAYMENT_ID" \
  -H "X-API-Key: $API_KEY")
BODY=$(echo "$RESP" | sed '$d')
CODE=$(echo "$RESP" | tail -n1)
assert_http "GET /api/v1/payments/{id}" "200" "$CODE" "$BODY"
echo

# --- Idempotency ---
bold "5. Idempotency (same Idempotency-Key)"
RESP=$(curl_json POST "$BASE_URL/api/v1/payments" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -H "Idempotency-Key: $IDEM_KEY" \
  -d '{
    "amount": "999.99",
    "currency": "RUB",
    "description": "Different body",
    "metadata": {},
    "webhook_url": "https://example.com/other"
  }')
BODY=$(echo "$RESP" | sed '$d')
CODE=$(echo "$RESP" | tail -n1)

IDEM_ID=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin)['payment_id'])" 2>/dev/null || true)
if [[ "$CODE" == "202" && "$IDEM_ID" == "$PAYMENT_ID" ]]; then
  green "  OK   idempotent replay returns same payment_id"
  PASS=$((PASS + 1))
else
  red "  FAIL idempotency (HTTP $CODE, id=$IDEM_ID, expected $PAYMENT_ID)"
  FAIL=$((FAIL + 1))
fi
echo

# --- Negative: no API key ---
bold "6. Negative: missing API key"
RESP=$(curl_json POST "$BASE_URL/api/v1/payments" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: smoke-no-key-$(date +%s)" \
  -d "$CREATE_PAYLOAD")
BODY=$(echo "$RESP" | sed '$d')
CODE=$(echo "$RESP" | tail -n1)
assert_http "POST without X-API-Key" "401" "$CODE" ""
echo

# --- Negative: not found ---
bold "7. Negative: payment not found"
RESP=$(curl_json GET "$BASE_URL/api/v1/payments/00000000-0000-0000-0000-000000000000" \
  -H "X-API-Key: $API_KEY")
BODY=$(echo "$RESP" | sed '$d')
CODE=$(echo "$RESP" | tail -n1)
assert_http "GET unknown payment" "404" "$CODE" ""
echo

# --- Outbox (optional, if postgres container is running) ---
bold "8. Outbox status (optional)"
if docker compose -p test-task ps --status running postgres 2>/dev/null | grep -q postgres; then
  sleep 6
  OUTBOX_ROWS=$(docker compose -p test-task exec -T postgres \
    psql -U payments -d payments -t -A -c \
    "SELECT status FROM outbox WHERE aggregate_id = '$PAYMENT_ID' LIMIT 1;" 2>/dev/null || true)
  OUTBOX_ROWS="${OUTBOX_ROWS//$'\r'/}"
  OUTBOX_ROWS="${OUTBOX_ROWS//$'\n'/}"

  if [[ "$OUTBOX_ROWS" == "published" ]]; then
    green "  OK   outbox status=published"
    PASS=$((PASS + 1))
  elif [[ -n "$OUTBOX_ROWS" ]]; then
    red "  FAIL outbox status=$OUTBOX_ROWS (expected published; wait and retry)"
    FAIL=$((FAIL + 1))
  else
    red "  FAIL outbox row not found for payment_id"
    FAIL=$((FAIL + 1))
  fi
else
  echo "       skipped (postgres container not running)"
fi
echo

bold "Result: $PASS passed, $FAIL failed"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
