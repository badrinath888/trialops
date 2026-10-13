# Zero-paid-service demo (Mac, port 3003)

Separate Compose project `trialops-release-demo`, its own database volume and secrets (`.secrets-demo/`), web on `127.0.0.1:3003` only.
Images are snapshots of the tested 3002 images (`trialops-release-demo-{api,web}:current`, created on first `start`); rebuilding 3001/3002 does not change the demo.
Settings (in `compose.demo.yaml`): real local Ollama (`AI_MODE=ollama`, model `qwen2.5:7b`), sample workspaces on (24 h expiry, 20/hour overall, 3/hour per visitor),
permanent signup off, no SMTP (no email is ever sent), Secure cookies, API docs off, one worker (one job and so one model call at a time), per-workspace assessment/evaluation limits, container memory caps.

## Commands
```bash
bash demo.sh start     # create secrets/images if needed, start the demo; local use http://127.0.0.1:3003
brew install cloudflared   # once, free
bash demo.sh tunnel    # opens a Cloudflare Quick Tunnel to web only and prints https://<random>.trycloudflare.com
bash demo.sh status
bash demo.sh stop      # closes the tunnel, stops the demo; data kept
bash tests/demo_check.sh   # local checks (origin/cookies/isolation/IP/exposure); removes what it creates
```
Ollama must be running on the Mac. Keep the Mac awake while sharing (`caffeinate -dims &`).

## The changing tunnel URL
A Quick Tunnel gets a new random URL every run. The web tier only accepts POSTs whose `Origin` equals `APP_ORIGIN`, so `demo.sh tunnel` reads the URL
from cloudflared's log, saves it in `.demo/origin`, and recreates only the web container with `APP_ORIGIN=<that URL>` (about 10 s; the database and sessions are untouched).
While a tunnel is active, use the tunnel URL in the browser (the local `http://localhost:3003` origin is then rejected by design). `demo.sh stop` / `start` returns to the local origin.
`APP_PUBLIC_URL` is used only for emailed links, which are disabled, so API/worker are not restarted.

## Visitor addresses
Web uses the last `X-Forwarded-For` entry (`TRUST_PROXY=true`); a client-supplied prefix is ignored. This relies on Cloudflare's edge appending the visitor address,
which is documented Cloudflare behavior but has **not** been observed here because no tunnel was opened. The port is loopback-only, so only this Mac can reach it without Cloudflare.
If the tunnel shows every visitor as one address, per-visitor limits collapse to one shared bucket (safe but strict).

## What is exposed
Only web (3003) is tunnelled. API, worker and database have no published ports; Ollama listens on 127.0.0.1:11434 and has no route through web.
Quick Tunnels have no uptime guarantee, and the URL is reachable by anyone who has it: use synthetic data only.
