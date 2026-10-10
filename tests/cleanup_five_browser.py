"""Host helper: remove only exact registered accounts recorded by our browser test."""
import json,subprocess,sys
from pathlib import Path
fixtures=json.loads(Path(sys.argv[1]).read_text());project=sys.argv[2] if len(sys.argv)>2 else 'trialops-release-test'
assert project in ('trialops-release-test','trialops-release')
code="""
import json,sys
from db import connect
rows=json.load(sys.stdin)
with connect() as c:
 for r in rows:
  u=c.execute('SELECT email,created_at FROM users WHERE id=%s',(r['user'],)).fetchone()
  if not u:continue
  assert u['email'].startswith('five-browser-') and u['email'].endswith('@sample.invalid')
  assert u['created_at'].isoformat()>='2026-10-10'
  assert c.execute("SELECT 1 FROM memberships WHERE workspace_id=%s AND user_id=%s AND role='owner'",(r['workspace'],r['user'])).fetchone()
 for r in rows:
  c.execute('DELETE FROM workspaces WHERE id=%s',(r['workspace'],))
  c.execute('DELETE FROM users WHERE id=%s',(r['user'],))
print('Fresh recorded browser fixtures cleaned; existing accounts untouched.')
"""
subprocess.run(['docker','compose','-p',project,'exec','-T','api','python','-c',code],input=json.dumps(fixtures),text=True,check=True)
