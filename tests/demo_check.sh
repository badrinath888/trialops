#!/usr/bin/env bash
# Checks the 3003 demo through web only: origin handling, cookie attributes, forwarded-IP trust, per-visitor limit, workspace isolation, exposure.
# ORIGIN must equal the origin web was started with (bash demo.sh sets it). Removes the sample workspaces and rate-limit rows it creates.
set -u
cd "$(dirname "$0")/.."
URL=${URL:-http://127.0.0.1:3003}; ORIGIN=${ORIGIN:-http://localhost:3003}; DB=trialops-release-demo-db-1
start=$(docker exec -i $DB psql -U trialops -d trialops -At -c "select now()"); fail=0; ws=()
ok() { if [ "$2" = "$3" ]; then echo "PASS: $1"; else echo "FAIL: $1 (got '$3', want '$2')"; fail=1; fi; }
post() { curl -s -D "$T/h" -o "$T/b" -w '%{http_code}' -X POST "$URL/api$1" -H "Origin: ${ORIGINOVERRIDE:-$ORIGIN}" -H 'Content-Type: application/json' ${XFF:+-H "X-Forwarded-For: $XFF"} ${COOKIE:+-H "Cookie: $COOKIE"} -d "${2:-{\}}"; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
start_session() { CODE=$(XFF=$1 post /auth/demo); code=$CODE; if [ "$code" = 200 ]; then COOKIE_OUT=$(grep -i '^set-cookie' "$T/h" | sed 's/^[^:]*: //; s/;.*//' | tr -d '\r' | paste -sd';' -); ws+=("$(python3 -c "import json;print(json.load(open('$T/b'))['workspace_id'])")"); fi; }
# 1. origin and cookie attributes
ok "wrong origin is rejected" 403 "$(ORIGINOVERRIDE=https://evil.example XFF=1.1.1.1 post /auth/demo)"
start_session 10.0.0.1; A="$COOKIE_OUT"; ok "sample workspace starts from the configured origin" 200 "$CODE"
attrs=$(grep -i '^set-cookie' "$T/h" | tr -d '\r'); for a in Secure HttpOnly 'SameSite=Lax'; do ok "cookie has $a" yes "$(echo "$attrs" | grep -qi "$a" && echo yes || echo no)"; done
ok "permanent signup is disabled" 403 "$(XFF=10.0.0.9 post /auth/register '{"email":"x-demo-check@example.invalid","password":"correct-horse-battery-9","name":"Check"}')"
# 2. isolation
start_session 10.0.0.2; B="$COOKIE_OUT"; ok "second visitor gets its own workspace" 200 "$CODE"
get() { G=$(curl -s -o "$T/g" -w '%{http_code}' "$URL/api$1" -H "Cookie: $2"); }
n() { python3 -c "import json;d=json.load(open('$T/g'));print(len(d['items']) if isinstance(d,dict) else len(d))"; }
get /cases "$A"; na=$(n); get /cases "$B"; nb=$(n); ok "fresh workspaces start with the same sample cases" "$na" "$nb"
get /cases "$A"; read -r cat study site <<<"$(python3 -c "import json;d=json.load(open('$T/g'));c=(d['items'] if isinstance(d,dict) else d)[0];print(c['category'],c['study_id'],c['site_id'])")"
COOKIE="$A" XFF=10.0.0.1 post /cases "{\"title\":\"Isolation probe for A\",\"description\":\"Created only in visitor A workspace.\",\"study_id\":\"$study\",\"site_id\":\"$site\",\"category\":\"$cat\",\"priority\":\"low\"}" >/dev/null
cid=$(python3 -c "import json;print(json.load(open('$T/b'))['id'])" 2>/dev/null)
get /cases "$A"; ok "visitor A sees its new case" "$((na+1))" "$(n)"
get /cases "$B"; ok "visitor B does not" "$nb" "$(n)"
get "/cases/$cid" "$B"; ok "visitor B cannot open A's case by id" 404 "$G"; get "/cases/$cid" "$A"; ok "visitor A can open it" 200 "$G"
# 3. forwarded-IP trust: only the last entry counts (limit 3 sample workspaces per visitor per hour)
for i in 1 2 3 4; do start_session "spoof-$i, 9.9.9.9"; done
ok "spoofed leading entries do not create new visitors (4th from one visitor)" 429 "$CODE"
start_session 'spoof-1, 8.8.8.8'; ok "a different last entry is a different visitor" 200 "$CODE"
# 4. exposure
ok "API docs are not served" 404 "$(curl -s -o /dev/null -w '%{http_code}' "$URL/api/docs")"
pub=$(docker ps --filter label=com.docker.compose.project=trialops-release-demo --format '{{.Ports}}' | grep -o '[0-9.]*:[0-9]*->' | sort -u | tr '\n' ' ')
ok "only 127.0.0.1:3003 is published by the demo project" "127.0.0.1:3003-> " "$pub"
ok "Ollama listens on loopback only" "127.0.0.1:11434" "$(lsof -nP -iTCP:11434 -sTCP:LISTEN | awk 'NR==2{print $9}')"
# cleanup of records created by this run
list=$(printf "'%s'," "${ws[@]}"); list=${list%,}
docker exec -i $DB psql -U trialops -d trialops -At -c "delete from workspaces where id in ($list); delete from users where guest and email like '%@sample.invalid' and not exists(select 1 from memberships m where m.user_id=users.id); delete from rate_limits where window_start >= '$start'" >/dev/null
exit $fail
