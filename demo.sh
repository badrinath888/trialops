#!/usr/bin/env bash
# Zero-paid-service demo (port 3003). Usage: bash demo.sh start|tunnel|stop|status
# start  : create secrets/images if missing, start db/api/worker/web on http://127.0.0.1:3003
# tunnel : open a Cloudflare Quick Tunnel to web only and point web's APP_ORIGIN at the new URL
# stop   : close the tunnel and stop the demo (data kept in the demo volume)
set -euo pipefail
cd "$(dirname "$0")"
D=.demo; mkdir -p $D
dc() { docker compose -p trialops-release-demo -f compose.demo.yaml "$@"; }
origin() { cat $D/origin 2>/dev/null || echo http://localhost:3003; }
tunnel_pid() { [ -f $D/tunnel.pid ] && kill -0 "$(cat $D/tunnel.pid)" 2>/dev/null && cat $D/tunnel.pid || true; }
case ${1:-} in
start)
  mkdir -p .secrets-demo; chmod 700 .secrets-demo
  for n in db_password internal_key; do [ -s .secrets-demo/$n ] || { (umask 077; openssl rand -hex 32 > .secrets-demo/$n); }; chmod 444 .secrets-demo/$n; done
  for s in api web; do   # snapshot the tested images so later rebuilds of 3001/3002 do not change the demo
    docker image inspect trialops-release-demo-$s:current >/dev/null 2>&1 || docker tag trialops-release-test-$s:latest trialops-release-demo-$s:current
  done
  APP_ORIGIN=$(origin) dc up -d --no-build --wait
  echo "Demo running: $(origin)   (local: http://127.0.0.1:3003)";;
tunnel)
  command -v cloudflared >/dev/null || { echo "Install first: brew install cloudflared"; exit 1; }
  [ -z "$(tunnel_pid)" ] || { echo "Tunnel already running: $(origin)"; exit 0; }
  dc ps --status running --services | grep -qx web || { echo "Run: bash demo.sh start"; exit 1; }
  : > $D/tunnel.log
  nohup cloudflared tunnel --no-autoupdate --url http://127.0.0.1:3003 > $D/tunnel.log 2>&1 &
  echo $! > $D/tunnel.pid
  for _ in $(seq 1 40); do url=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' $D/tunnel.log | head -1 || true); [ -n "$url" ] && break; sleep 1; done
  [ -n "${url:-}" ] || { echo "No tunnel URL; see $D/tunnel.log"; kill "$(cat $D/tunnel.pid)" 2>/dev/null || true; rm -f $D/tunnel.pid; exit 1; }
  echo "$url" > $D/origin
  APP_ORIGIN=$url dc up -d --no-deps --no-build --wait web   # the URL changes every run, so web must be recreated with it
  echo "Public demo URL: $url";;
stop)
  [ -z "$(tunnel_pid)" ] || kill "$(tunnel_pid)"; rm -f $D/tunnel.pid $D/origin
  dc stop; echo "Stopped. Data kept in volume trialops-release-demo_database.";;
status)
  echo "origin: $(origin)  tunnel pid: $(tunnel_pid)"
  dc ps --format '{{.Name}} {{.Status}}';;
*) echo "Usage: bash demo.sh start|tunnel|stop|status"; exit 1;;
esac
