#!/usr/bin/env bash
# Restore into a uniquely named temporary database. Never restores over the live database.
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p backups
backup_file="backups/trialops-verified-$(date +%Y%m%d-%H%M%S)-$$.dump"
check_db="trialops_restorecheck_$(date +%Y%m%d%H%M%S)_$$"
created=false
cleanup() {
  if [ "$created" = true ]; then
    docker compose exec -T db dropdb -U trialops --if-exists "$check_db" >/dev/null || echo "Temporary verification database needs cleanup: $check_db"
  fi
}
trap cleanup EXIT
printf 'Creating backup and checking a separate restore...\n'
docker compose exec -T db pg_dump -U trialops -d trialops -Fc > "$backup_file.tmp"
docker compose exec -T db pg_restore --list < "$backup_file.tmp" >/dev/null
mv "$backup_file.tmp" "$backup_file"
docker compose exec -T db createdb -U trialops "$check_db"
created=true
docker compose exec -T db pg_restore -U trialops -d "$check_db" --no-owner --exit-on-error < "$backup_file"
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U trialops -d "$check_db" -c "
SELECT 'workspaces' AS restored_table, count(*) AS records FROM workspaces
UNION ALL SELECT 'users',count(*) FROM users
UNION ALL SELECT 'cases',count(*) FROM cases
UNION ALL SELECT 'investigations',count(*) FROM runs
UNION ALL SELECT 'knowledge',count(*) FROM knowledge;
SELECT extname FROM pg_extension WHERE extname='vector';
"
if command -v shasum >/dev/null; then shasum -a 256 "$backup_file" > "$backup_file.sha256"; fi
printf 'PASS: archive restored successfully into a separate test database.\nLive database unchanged. Backup: %s\n' "$backup_file"
