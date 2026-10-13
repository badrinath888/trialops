#!/usr/bin/env bash
# Scheduled backup: dump -> (optional) separate restore check -> offsite copy -> retention. Reports failure.
# Configure in .backup.env (see .backup.env.example). Needs rclone on the host for the offsite copy.
set -uo pipefail
umask 077
cd "$(dirname "$0")/.."
[ -f .backup.env ] && { set -a; . ./.backup.env; set +a; }
: "${RETENTION_DAYS:=14}" "${RESTORE_VERIFY:=true}"
status=backups/backup-offsite.status
mkdir -p backups
step=start
ping() { [ -n "${HEALTHCHECK_URL:-}" ] && curl -fsS -m 10 --retry 2 -o /dev/null "${HEALTHCHECK_URL%/}$1" || true; }
fail() {
  msg="FAILED $(date -u +%FT%TZ) at step: $step"
  echo "$msg" > "$status"; echo "$msg" >&2
  ping /fail
  exit 1
}
trap fail ERR
set -e
[[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] && [ "$RETENTION_DAYS" -ge 2 ] || { step="config: RETENTION_DAYS must be an integer >= 2"; fail; }
[ -n "${OFFSITE_REMOTE:-}" ] || { step="config: OFFSITE_REMOTE not set"; fail; }
command -v rclone >/dev/null || { step="config: rclone not installed"; fail; }

step="dump"
if [ "$RESTORE_VERIFY" = true ]; then step="dump and separate-database restore check"; bash scripts/verify-backup.sh >/dev/null; else bash scripts/backup.sh >/dev/null; fi
file=$(ls -t backups/trialops-*.dump 2>/dev/null | head -1); [ -n "$file" ]
name=$(basename "$file")

step="offsite copy"
rclone copyto "$file" "${OFFSITE_REMOTE%/}/$name"
step="offsite size check"
local_size=$(wc -c < "$file" | tr -d ' ')
remote_size=$(rclone size --json "${OFFSITE_REMOTE%/}/$name" | python3 -c 'import json,sys;print(json.load(sys.stdin)["bytes"])')
[ "$local_size" = "$remote_size" ]

step="retention"
find backups -maxdepth 1 -name 'trialops-*.dump*' -mtime +"$RETENTION_DAYS" -delete
rclone delete "${OFFSITE_REMOTE%/}" --min-age "${RETENTION_DAYS}d" --include 'trialops-*.dump'

echo "OK $(date -u +%FT%TZ) file=$name bytes=$local_size offsite_size_match=true restore_checked=$RESTORE_VERIFY retention_days=$RETENTION_DAYS" > "$status"
cat "$status"
ping ""
