#!/usr/bin/env python3
"""Verify and install 1.4.1 source. Never delete deployment data or unknown files."""
import hashlib, json, os, shutil, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

source = Path(__file__).resolve().parent

def fail(message):
    raise SystemExit(message + ' No changes made.')

def safe(root, relative):
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts or not p.parts:
        fail('Unsafe package path: ' + relative)
    if p.parts[0] in {'.env', '.secrets', 'backups', '.git'}:
        fail('Protected package path: ' + relative)
    dest = root / p
    if any(part.is_symlink() for part in [dest, *dest.parents] if part != root.parent):
        fail('Symlink path rejected: ' + relative)
    if root not in dest.resolve().parents:
        fail('Path escapes installation: ' + relative)
    return dest

def manifest(root):
    entries = []
    for line in (root / 'SHA256SUMS').read_text().splitlines():
        checksum, relative = line.split(None, 1)
        relative = relative.strip()
        file = safe(root, relative)
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != checksum:
            fail('Package verification failed: ' + relative)
        entries.append((file, relative))
    return entries

if len(sys.argv) != 2:
    raise SystemExit('Usage: python3 upgrade.py /path/to/existing/trialops-release')
target = Path(sys.argv[1]).expanduser().resolve()
if target == source:
    fail('Choose the existing installation, not this download.')
for name in ['compose.yaml', '.env', '.secrets/db_password', '.secrets/internal_key']:
    if not (target / name).is_file():
        fail('Existing installation is missing ' + name + '.')
if (target / "backups").is_symlink():
    fail("The backups directory must not be a symlink.")
entries = manifest(source)
for _, relative in entries:
    safe(target, relative)
safe(target, "SHA256SUMS")
obsolete = ['apps/web/app/design-system.css', 'COMPACT-UPDATE.md']
for relative in obsolete:
    safe(target, relative)
backup = target / 'backups' / ('source-before-1.4.1-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))
backup.mkdir(parents=True)
# Save only files being replaced or retired. No credentials or data are copied.
for relative in [r for _, r in entries] + obsolete + ['SHA256SUMS']:
    old = target / relative
    if old.is_file():
        saved = backup / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old, saved)
new_files = []
for file, relative in entries:
    dest = target / relative
    if not dest.exists():
        new_files.append(relative)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + dest.name + '.upgrade-', dir=dest.parent)
    staged = Path(name)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(file.read_bytes())
        shutil.copymode(file, staged)
        staged.replace(dest)
    finally:
        staged.unlink(missing_ok=True)
retired = []
for relative in obsolete:
    dest = target / relative
    if dest.is_file():
        dest.unlink()
        retired.append(relative)
shutil.copy2(source / 'SHA256SUMS', target / 'SHA256SUMS')
(backup / 'upgrade-record.json').write_text(json.dumps({'version':'1.4.1','new_files':new_files,'retired':retired}, indent=2))
print('TrialOps 1.4.1 source installed. Existing accounts, database, environment, and secrets preserved.')
print('Rollback source:', backup)
print('Obsolete files removed:', ', '.join(retired) or 'none present')
