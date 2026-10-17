#!/usr/bin/env bash
# Authenticated, read-only smoke of existing workflows and the Document journey through the web proxy.
# Usage: SMOKE_EMAIL=.. SMOKE_PASSWORD=.. SMOKE_CASE=<existing case id> [BASE=http://localhost:3001] bash scripts/live-smoke.sh
# Only login (creates one session) and GETs; no records are created or changed.
set -euo pipefail
: "${SMOKE_EMAIL:?}" "${SMOKE_PASSWORD:?}" "${SMOKE_CASE:?}"
BASE=${BASE:-http://localhost:3001}; jar=$(mktemp); trap 'rm -f "$jar"' EXIT
# The proxy rejects POSTs whose Origin differs from the app origin; credentials go via stdin as JSON, never argv.
resp=$(mktemp); trap 'rm -f "$jar" "$resp"' EXIT
code=$(python3 -c 'import json,os;print(json.dumps({"email":os.environ["SMOKE_EMAIL"],"password":os.environ["SMOKE_PASSWORD"]}))' \
  | curl -s -o "$resp" -w '%{http_code}' -c "$jar" -H 'Content-Type: application/json' -H "Origin: $BASE" -d @- "$BASE/api/auth/login") || code=000
[ "$code" = 200 ] || { echo "FAIL login $code: $(python3 -c 'import json,sys;d=json.load(open(sys.argv[1])).get("detail");print(d if isinstance(d,str) else "see server response")' "$resp" 2>/dev/null | head -c 120)"; exit 1; }
for p in auth/me cases "cases/$SMOKE_CASE" "cases/$SMOKE_CASE/journey" "cases/$SMOKE_CASE/journey/priority" "cases/$SMOKE_CASE/package.json"; do
  code=$(curl -s -o /dev/null -w '%{http_code}' -b "$jar" "$BASE/api/$p"); echo "$code /api/$p"; [ "$code" = 200 ] || exit 1
done
curl -sf -o /dev/null -b "$jar" "$BASE/workspace" && echo "200 /workspace"
echo "PASS: authenticated smoke"
