#!/usr/bin/env bash
# Run from this NEW extracted download; target defaults to the existing Mac installation.
set -euo pipefail
package_dir="$(cd "$(dirname "$0")" && pwd)"
target_dir="${1:-$HOME/Downloads/trialops-release}"
command -v python3 >/dev/null || { echo "Python 3 is required."; exit 1; }
command -v docker >/dev/null || { echo "Open Docker Desktop first."; exit 1; }
docker info >/dev/null 2>&1 || { echo "Open Docker Desktop and wait until it is running."; exit 1; }
python3 - "$package_dir" "$target_dir" <<'PY'
import hashlib,sys
from pathlib import Path
source,target=map(lambda x:Path(x).expanduser().resolve(),sys.argv[1:])
if source==target:raise SystemExit('Extract the NEW package separately from your existing installation.')
for name in ['compose.yaml','.env','.secrets/db_password','.secrets/internal_key']:
 if not (target/name).is_file():raise SystemExit('Existing installation missing '+name+'. No changes made.')
for line in (source/'SHA256SUMS').read_text().splitlines():
 checksum,name=line.split(None,1);p=Path(name.strip())
 if p.is_absolute() or '..' in p.parts:raise SystemExit('Invalid package path.')
 file=source/p
 if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest()!=checksum:raise SystemExit('Package verification failed: '+str(p))
print('Package verified.')
PY
cd "$target_dir"
lock_dir=.trialops-update-lock
mkdir "$lock_dir" 2>/dev/null || { echo "Another update may be running. Check before removing $target_dir/$lock_dir."; exit 1; }
trap 'rmdir "$lock_dir" 2>/dev/null || true' EXIT
# Stop writers while taking the database snapshot; leave the database volume intact.
docker compose up -d --wait --wait-timeout 180 db
docker compose stop api worker web
if ! bash scripts/backup.sh; then
  docker compose up -d api worker web
  echo "Backup failed. Source was not changed."
  exit 1
fi
python3 "$package_dir/upgrade.py" "$target_dir"
docker compose up -d --build --wait --wait-timeout 300 api worker web
bash scripts/test.sh
# Cleanup runs only after the update and target installation checks pass.
python3 scripts/clean-build-files.py
printf '\nUpdate verified. TrialOps is ready at your existing APP_ORIGIN (normally http://localhost:3001).\n'
echo "Use Cmd+Shift+R in the browser to load the new design."
echo "Rollback source and database backup are in $target_dir/backups."
