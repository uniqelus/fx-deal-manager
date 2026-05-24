#!/usr/bin/env bash
# Seed demo users in identity-provider (read-only repo — calls HTTP API only).
# Requires: curl, jq, running IdP on IDP_URL (default http://localhost:8083)

set -euo pipefail

IDP_URL="${IDP_URL:-http://localhost:8083}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-change-this-local-admin-password}"
DEMO_PASSWORD="${DEMO_PASSWORD:-DemoPassword1!}"

login() {
  local email="$1"
  local password="$2"
  curl -sf "${IDP_URL}/api/v1/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"${email}\",\"password\":\"${password}\"}" \
    | jq -r '.accessToken'
}

register_user() {
  local email="$1"
  local first="$2"
  local last="$3"
  curl -sf "${IDP_URL}/api/v1/auth/register" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"${email}\",\"firstName\":\"${first}\",\"lastName\":\"${last}\",\"password\":\"${DEMO_PASSWORD}\"}" \
    | jq -r '.id'
}

set_role() {
  local admin_token="$1"
  local user_id="$2"
  local role="$3"
  curl -sf -X PATCH "${IDP_URL}/api/v1/users/${user_id}/role" \
    -H "Authorization: Bearer ${admin_token}" \
    -H 'Content-Type: application/json' \
    -d "{\"role\":\"${role}\"}" > /dev/null
}

echo "Logging in as admin..."
ADMIN_TOKEN="$(login "${ADMIN_EMAIL}" "${ADMIN_PASSWORD}")"

declare -A USERS=(
  ["trader@demo.local"]="TRADER|Илья|Смирнов"
  ["positioner@demo.local"]="POSITIONER|Софья|Борисова"
  ["auditor@demo.local"]="AUDITOR|Глеб|Павлюк"
)

for email in "${!USERS[@]}"; do
  IFS='|' read -r role first last <<< "${USERS[$email]}"
  echo "Registering ${email} (${role})..."
  if user_id="$(register_user "${email}" "${first}" "${last}" 2>/dev/null)"; then
    echo "  created id=${user_id}"
  else
    echo "  already exists or register failed — skipping register"
    user_id=""
  fi
  if [[ -n "${user_id}" ]]; then
    set_role "${ADMIN_TOKEN}" "${user_id}" "${role}"
    echo "  role set to ${role}"
  fi
done

echo ""
echo "Demo users (password: ${DEMO_PASSWORD}):"
echo "  trader@demo.local      — TRADER"
echo "  positioner@demo.local  — POSITIONER"
echo "  auditor@demo.local     — AUDITOR"
echo "Admin: ${ADMIN_EMAIL} / ${ADMIN_PASSWORD}"
