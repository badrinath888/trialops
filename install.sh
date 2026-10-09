#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
command -v docker >/dev/null || { echo "Install and open Docker Desktop first."; exit 1; }
docker info >/dev/null 2>&1 || { echo "Open Docker Desktop, wait until it is running, then run bash install.sh again."; exit 1; }
docker compose version >/dev/null
if [ ! -s .secrets/db_password ] && docker volume inspect trialops-release_database >/dev/null 2>&1; then
  echo "An existing TrialOps release database was found."
  echo "Use: python3 upgrade.py /path/to/your/existing/trialops-release"
  echo "This prevents creating different credentials for your existing database."
  exit 1
fi
mkdir -p .secrets backups
chmod 700 .secrets
for name in db_password internal_key; do
  if [ ! -s ".secrets/$name" ]; then
    (umask 077; openssl rand -hex 32 > ".secrets/$name")
  fi
  chmod 444 ".secrets/$name"
done
if [ ! -f .env ]; then
  cp .env.example .env
  mode=procedure
  if command -v curl >/dev/null && command -v python3 >/dev/null; then
    if curl -fsS --max-time 5 http://localhost:11434/api/tags | python3 -c 'import json,sys; names={m["name"] for m in json.load(sys.stdin)["models"]};sys.exit(0 if "qwen2.5:7b" in names and "nomic-embed-text:v1.5" in names else 1)' >/dev/null 2>&1; then mode=ollama; fi
  fi
  if [ "$mode" = ollama ]; then
    awk -v value="$mode" '$0 ~ /^AI_MODE=/ {$0="AI_MODE=" value} {print}' .env > .env.tmp
    mv .env.tmp .env
    echo "Local Qwen and embedding models found. LLM-assisted mode enabled."
  else
    echo "Starting in procedure mode: all workflows work, and no LLM is used."
    echo "To enable AI later, see README.md (Local models)."
  fi
fi
chmod 600 .env
echo "Building the complete application. The first build may take several minutes."
docker compose up -d --build --wait --wait-timeout 240
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U trialops -d trialops < database/schema.sql >/dev/null
echo ""
domain=$(sed -n 's/^DOMAIN=//p' .env | tail -n 1)
address=$(sed -n 's/^APP_ORIGIN=//p' .env | tail -n 1)
if [ -n "$domain" ]; then address="https://$domain"; fi
echo "TrialOps is ready: ${address:-http://localhost:3001}"
echo "Your previous trialops-ai project and its database are separate."
echo "Open the page and choose Try sample workspace."
echo "Run bash scripts/test.sh to verify this installation."
