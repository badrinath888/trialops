#!/usr/bin/env bash
# Run on the server only, after DNS and Docker have been configured.
set -euo pipefail
cd "$(dirname "$0")"
domain=${1:-}
[[ "$domain" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]] || { echo 'Usage: bash deploy.sh trialops.YOUR-DOMAIN.com'; exit 1; }
if [ -f .env ]; then
  echo "Existing configuration found. Set DOMAIN and COMPOSE_FILE in .env as described in PUBLIC-DEPLOY.md."
  exit 1
fi
cp .env.example .env
printf '\nDOMAIN=%s\nCOMPOSE_FILE=compose.yaml:compose.production.yaml\n' "$domain" >> .env
bash install.sh
echo "Public endpoint: https://$domain"
echo "Complete the browser acceptance checklist before announcing this endpoint."
