"""Remove exact newly created expiring browser samples only, never existing accounts."""
import json,subprocess,sys
from pathlib import Path
rows=json.loads(Path(sys.argv[1]).read_text());project=sys.argv[2] if len(sys.argv)>2 else 'trialops-release-test'
assert project in ('trialops-release-test','trialops-release')
code="""
import json,sys
from db import connect
rows=json.load(sys.stdin)
with connect() as c:
 for r in rows:
  w=c.execute('SELECT demo,created_at FROM workspaces WHERE id=%s',(r['workspace'],)).fetchone()
  if not w:continue
  u=c.execute('SELECT guest FROM users WHERE id=%s',(r['user'],)).fetchone()
  assert w['demo'] and u and u['guest'] and w['created_at'].isoformat()>='2026-10-10'
  assert c.execute("SELECT 1 FROM memberships WHERE workspace_id=%s AND user_id=%s AND role='owner'",(r['workspace'],r['user'])).fetchone()
 for r in rows:
  c.execute('DELETE FROM workspaces WHERE id=%s',(r['workspace'],))
  c.execute('DELETE FROM users WHERE id=%s',(r['user'],))
print('Only exact fresh expiring browser samples removed.')
"""
subprocess.run(['docker','compose','-p',project,'exec','-T','api','python','-c',code],input=json.dumps(rows),text=True,check=True)
