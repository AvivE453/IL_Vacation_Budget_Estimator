#!/usr/bin/env bash
# A few real requests to the live site after a deploy: the API
# reaches Neon, a search runs end to end, and an inner page loads on refresh.
# Exits non-zero on the first failure, which turns CI's deploy job red.
# Each run saves one search to Neon, like a visitor's would.
#
# Run with: scripts/smoke_test.sh https://<site>/

set -euo pipefail
site=${1%/}
body=$(mktemp)
trap 'rm -f "$body"' EXIT

# check <name> <expected status> <text the body must contain> <curl args...>
check() {
  local name=$1 expected=$2 text=$3
  shift 3
  local status
  status=$(curl -sS -o "$body" -w "%{http_code}" --max-time 30 "$@")
  if [ "$status" != "$expected" ] || ! grep -q "$text" "$body"; then
    echo "FAIL $name: status $status, expected $expected with \"$text\" in the body:" >&2
    head -c 500 "$body" >&2
    echo >&2
    exit 1
  fi
  echo "ok   $name"
}

depart_date=$(date -u -d "+30 days" +%F)
return_date=$(date -u -d "+37 days" +%F)

echo "== Smoke tests against $site"
check "health" 200 '"status":"ok"' "$site/api/v1/health"
check "search" 200 '"search_id"' -X POST "$site/api/v1/estimates" -H "Content-Type: application/json" \
  -d "{\"origin_iata\": \"TLV\", \"depart_date\": \"$depart_date\", \"return_date\": \"$return_date\", \"budget_amount\": 20000, \"travelers\": 2}"
check "inner page on refresh" 200 'id="root"' "$site/data-quality"
