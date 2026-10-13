#!/usr/bin/env bash
# Client-IP handling through Caddy -> web -> API on the 3002 test stack. Needs: Caddy (production directives, plain HTTP) at PROXY_URL
# reaching a web with TRUST_PROXY=true; DIRECT_URL = web without TRUST_PROXY (TRUST_PROXY unset). Login limit is 20 per 15 minutes per client key.
# Creates only rate_limits rows (removed at the end by window_start) for unknown-email logins.
set -u
PROXY_URL=${PROXY_URL:-http://127.0.0.1:8088}; DIRECT_URL=${DIRECT_URL:-http://127.0.0.1:3002}; ORIGIN=${ORIGIN:-http://localhost:3002}
API=${API:-trialops-release-test-api-1}; DB=${DB:-trialops-release-test-db-1}
start=$(docker exec -i $DB psql -U trialops -d trialops -At -c "select now()")
login() { # url, spoofed XFF (optional) -> status
  curl -s -o /dev/null -w '%{http_code}' -X POST "$1/api/auth/login" -H "Origin: $ORIGIN" -H 'Content-Type: application/json' ${2:+-H "X-Forwarded-For: $2"} -d "{\"email\":\"nobody-$RANDOM$RANDOM@example.invalid\",\"password\":\"wrong-password-1\"}"; }  # unique email: only the per-IP limit is exercised
inner() { docker exec -i $API python - "$1" "$2" <<'P'
import sys,urllib.request,urllib.error,json
r=urllib.request.Request(sys.argv[1]+'/api/auth/login',json.dumps({'email':'nobody-%d@example.invalid'%__import__('random').randrange(10**9),'password':'wrong-password-1'}).encode(),{'Origin':'http://localhost:3002','Content-Type':'application/json','X-Forwarded-For':sys.argv[2]})
try:print(urllib.request.urlopen(r).status)
except urllib.error.HTTPError as e:print(e.code)
P
}
fail=0; ok() { if [ "$2" = "$3" ]; then echo "PASS: $1"; else echo "FAIL: $1 (got $3, want $2)"; fail=1; fi; }
# 1. Visitor A (host) rotates spoofed forwarded IPs through the proxy: all count against A's real address -> limited.
last=""; for i in $(seq 1 22); do last=$(login $PROXY_URL 10.9.9.$i); done
ok "spoof rotation through proxy does not evade the limit" 429 "$last"
# 2. Visitor B (different real source address: container on the network) is unaffected, even when copying A's spoofed value.
ok "separate visitor has a separate limit (fresh, spoofing A's value)" 401 "$(inner http://tp-caddy-test:8080 10.9.9.1)"
# 3. Visitor A stays limited; B stays allowed.
ok "visitor A still limited" 429 "$(login $PROXY_URL 203.0.113.50)"
ok "visitor B still allowed" 401 "$(inner http://tp-caddy-test:8080 203.0.113.50)"
# 4. Without a trusted proxy the header is ignored: rotating spoofed values share one bucket.
last=""; for i in $(seq 1 22); do last=$(login $DIRECT_URL 10.8.8.$i); done
ok "untrusted mode ignores spoofed forwarded header" 429 "$last"
docker exec -i $DB psql -U trialops -d trialops -At -c "delete from rate_limits where window_start >= '$start'" >/dev/null
exit $fail
