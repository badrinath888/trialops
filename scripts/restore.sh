#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
backup_file=${1:-}
[ -f "$backup_file" ] || { echo "Usage: bash scripts/restore.sh backups/FILE.dump"; exit 1; }
docker compose exec -T db pg_restore --list < "$backup_file" >/dev/null
echo "This replaces the TrialOps RELEASE database with $backup_file."
read -r -p 'Type RESTORE to continue: ' confirmation
[ "$confirmation" = RESTORE ] || exit 1
bash scripts/backup.sh
docker compose stop web api worker
docker compose exec -T db pg_restore -U trialops -d trialops --clean --if-exists --exit-on-error < "$backup_file"
docker compose up -d --wait
echo "Restore completed."
