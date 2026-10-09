#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
mkdir -p backups
backup_file="backups/trialops-$(date +%Y%m%d-%H%M%S).dump"
docker compose exec -T db pg_dump -U trialops -d trialops -Fc > "$backup_file.tmp"
docker compose exec -T db pg_restore --list < "$backup_file.tmp" >/dev/null
mv "$backup_file.tmp" "$backup_file"
ls -lh "$backup_file"
echo "Copy this backup to separate, access-controlled storage."
