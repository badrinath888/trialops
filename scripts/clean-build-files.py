#!/usr/bin/env python3
"""Remove only known disposable files inside this installation."""
import shutil
from pathlib import Path
root = Path(__file__).resolve().parents[1]
paths = [root/'apps/web/.next',root/'apps/web/node_modules',root/'apps/web/tsconfig.tsbuildinfo',root/'tests/browser/node_modules',root/'apps/web/.DS_Store']
paths += list((root/'apps/web').glob('.next-cache-before-*'))
paths += [root/'__pycache__',root/'apps/api/__pycache__',root/'tests/__pycache__']
removed = []
for path in paths:
    if any(p.is_symlink() for p in [path,*path.parents] if p != root.parent):
        print('Skipped symlink:', path.relative_to(root));continue
    if path.exists():
        if path.is_dir(): shutil.rmtree(path)
        else: path.unlink()
        removed.append(str(path.relative_to(root)))
print('Disposable files removed:', ', '.join(removed) or 'none present')
print('Database, .env, .secrets, Git history, user uploads, and backups preserved.')
