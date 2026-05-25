#!/usr/bin/env bash
# Демонстрационный сценарий happy path для защиты прототипа.
# Создаёт сделку SPOT EUR/RUB, валидирует, отправляет, согласовывает,
# проверяет что статус EXECUTED достигнут и аудит непуст.
#
# Требования: identity-provider :8083 и fx-deal-manager :8000 запущены,
# демо-пользователи созданы через scripts/seed-demo-users.sh.

set -euo pipefail

IDP_URL="${IDP_URL:-http://localhost:8083}"
API_URL="${API_URL:-http://localhost:8000}"

login() {
    local email="$1"
    local password="$2"
    curl -sS "${IDP_URL}/api/v1/auth/login" \
        -H 'Content-Type: application/json' \
        -d "{\"email\":\"${email}\",\"password\":\"${password}\"}" \
        | jq -r '.accessToken'
}

echo "[1/5] Login trader"
TRADER_TOKEN=$(login "trader@demo.local" "DemoPassword1!")
test -n "$TRADER_TOKEN"

echo "[2/5] Create SPOT EUR/RUB deal"
DEAL_PAYLOAD=$(cat <<'EOF'
{
    "trade_date": "2026-05-24",
    "deal_type": "SPOT",
    "operation_direction": "BUY",
    "buy_currency": "EUR",
    "sell_currency": "RUB",
    "amount": "1000000.00",
    "rate": "98.50",
    "counterparty_id": "SBER",
    "comment": "demo run"
}
EOF
)
DEAL=$(curl -sS -X POST "${API_URL}/api/v1/deals" \
    -H "Authorization: Bearer ${TRADER_TOKEN}" \
    -H 'Content-Type: application/json' \
    -d "$DEAL_PAYLOAD")
DEAL_ID=$(echo "$DEAL" | jq -r '.id')
echo "  deal_id=${DEAL_ID}"

echo "[3/5] Validate and submit"
curl -sS -X POST "${API_URL}/api/v1/deals/${DEAL_ID}/validate" \
    -H "Authorization: Bearer ${TRADER_TOKEN}" > /dev/null
curl -sS -X POST "${API_URL}/api/v1/deals/${DEAL_ID}/submit" \
    -H "Authorization: Bearer ${TRADER_TOKEN}" > /dev/null

echo "[4/5] Login positioner, approve"
POS_TOKEN=$(login "positioner@demo.local" "DemoPassword1!")
APPROVED=$(curl -sS -X POST "${API_URL}/api/v1/deals/${DEAL_ID}/approve" \
    -H "Authorization: Bearer ${POS_TOKEN}")
STATUS=$(echo "$APPROVED" | jq -r '.status')
echo "  status=${STATUS}"
test "$STATUS" = "EXECUTED" || { echo "FAIL: expected EXECUTED"; exit 1; }

echo "[5/5] Pull audit trail"
AUDITOR_TOKEN=$(login "auditor@demo.local" "DemoPassword1!")
AUDIT=$(curl -sS "${API_URL}/api/v1/audit-events?entity_id=${DEAL_ID}" \
    -H "Authorization: Bearer ${AUDITOR_TOKEN}")
EVENT_COUNT=$(echo "$AUDIT" | jq -r '.items | length')
echo "  audit events=${EVENT_COUNT}"
test "$EVENT_COUNT" -ge 5 || { echo "FAIL: audit too short"; exit 1; }

echo
echo "Demo OK: deal ${DEAL_ID} reached EXECUTED, audit contains ${EVENT_COUNT} events."
