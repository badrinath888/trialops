"""Manual vs automated handling of the SAME synthetic update on the 3002 test stack. Counts user-initiated API calls (what the reviewer/owner must do) to reach:
evidence saved -> journey reassessed -> next action identified -> unsent draft prepared. One-time configuration is counted separately; clicks, reading and typing are NOT counted.
Run in the test API container: python /app/tests/source_automation_comparison.py"""
import sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/api'))
from integration import Client
from db import connect
from psycopg.types.json import Jsonb
from journey import example_export

class Counted(Client):
    def __init__(s): super().__init__(); s.n = 0; s.log = []
    def call(s, path, body=None, expected=200):
        if s.counting: s.n += 1; s.log.append(('POST' if body is not None else 'GET') + ' ' + path.split('?')[0])
        return super().call(path, body, expected)
    counting = False
def sql(q, *p):
    with connect() as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
now = datetime.now(timezone.utc).replace(microsecond=0)
PORTAL, HUB = 'mock-upload-portal', 'mock-binder-hub'
ws, out = [], {}
def setup(u):
    w = u.call('/auth/demo', {})['workspace_id']; ws.append(w)
    sql("INSERT INTO cases(workspace_id,id,study_id,site_id,title,description,category,priority,status) VALUES(%s,'CMP-1','CT-204','SITE-104','Comparison','Synthetic.','document_workflow','medium','open')", w)
    sql("INSERT INTO runs(workspace_id,id,case_id,result,duration_seconds,model) VALUES(%s,%s,'CMP-1',%s,0,'test')", w, uuid4(), Jsonb({'recommendation': {'status': 'supported', 'evidence_ids': []}, 'sources': []}))
    u.call('/cases/CMP-1/journey/subject', {'id': str(uuid4()), 'expected_rev': 0, 'document_system': PORTAL, 'document_ref': 'DOC-8001', 'document_version': '1', 'destination_system': HUB, 'binder_ref': 'BND-8'})
    return w
def export(ref):
    at = now - timedelta(minutes=3)
    return example_export('portal', 'CT-204', 'SITE-104', None, ref=ref, observed_at=at, rows=[
        {'event': 'RECEIPT', 'receipt_no': 'RCPT-8001', 'doc_id': 'DOC-8001', 'doc_rev': '1', 'state': 'RECEIVED', 'at': at.isoformat()},
        {'event': 'PROCESS', 'receipt_no': 'PROC-8001', 'doc_id': 'DOC-8001', 'doc_rev': '1', 'state': 'DONE', 'at': at.isoformat()}]), at
def end_state(u):
    j = u.call('/cases/CMP-1/journey')['journey']; return {s['stage']: (s['operational_status'], s['assessment']) for s in j['stages']}
try:
    # --- manual: what the owner/reviewer does today
    M = Counted(); setup(M); M.counting = True; ex, _ = export('MAN-' + uuid4().hex[:8])
    M.call('/operations/journey-import', {'export': ex['export'], 'mapping': ex['mapping']}, 201)       # 1 import the export
    state_m = end_state(M)                                                                              # 2 open the journey to see reassessed stages
    cand = [c for c in M.call('/cases/CMP-1/journey/priority')['candidates'] if c['state'] == 'ready'][0]  # 3 open the suggested order
    M.call('/cases/CMP-1/journey/collection', {'id': str(uuid4()), 'request_id': str(uuid4()), 'stage': cand['stage'], 'gap_key': cand['key'], 'question': cand['question'], 'would_settle': cand['would_settle']}, 201)  # 4 draft the request
    out['manual'] = (M.n, M.log, state_m)
    # --- automated: same update delivered by a mock source
    Au = Counted(); w = setup(Au)
    src = Au.call('/sources', {'name': 'Mock portal', 'adapter': 'mock_portal'}, 201); Au.call('/sources/automation', {'draft_preparation': True})   # one-time configuration (not counted)
    import json, urllib.request
    from integration import URL
    from db import secret
    ex2, at = export('AUTO-' + uuid4().hex[:8]); body = {'schema_version': '1', 'event_id': 'EVT-' + uuid4().hex[:10], 'source_rev': 1, 'observed_at': at.isoformat(), 'export': ex2['export'], 'mapping': ex2['mapping']}
    req = urllib.request.Request(URL + '/sources/events', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'X-Internal-Key': secret('INTERNAL_KEY'), 'X-Source-Key': src['source_key'], 'X-Client-IP': '10.1.1.1'})
    assert urllib.request.urlopen(req, timeout=30).status == 202   # the SOURCE delivers; this is not a user action
    for _ in range(90):
        st = sql("SELECT status,result FROM source_events WHERE workspace_id=%s", w)[0]
        if st['status'] != 'received': break
        time.sleep(1)
    assert st['status'] == 'processed', st
    Au.counting = True
    up = Au.call('/cases/CMP-1/watch')['updates'][0]                     # 1 the reviewer opens the case and reads the update (already reassessed, with next action and draft)
    state_a = end_state(Au)                                              # (verification read of the journey; counted)
    Au.call(f'/cases/CMP-1/watch/updates/{up["id"]}/review', {})          # 2 optional: record that it was reviewed
    out['automated'] = (Au.n, Au.log, state_a)
    assert up['detail']['draft']['state'] == 'prepared' and up['detail']['draft']['unsent']
    assert out['manual'][2] == out['automated'][2], 'both versions must reach the same assessed state'
    d = sql("SELECT status FROM information_requests WHERE workspace_id=%s", w); assert [x['status'] for x in d] == ['draft']
    print('Same synthetic update (portal: receipt + processing completed for one document), same end state: stages', out['manual'][2])
    print('MANUAL    user-initiated API calls:', out['manual'][0], out['manual'][1])
    print('AUTOMATED user-initiated API calls:', out['automated'][0], out['automated'][1], '(+ one-time source setup, not per update: create source, enable draft setting)')
    print('Not counted: clicks, reading, typing, choosing a file/mapping, time. No time-saved figure is claimed. One synthetic scenario, one run.')
finally:
    with connect() as c:
        for w in ws: c.execute('DELETE FROM workspaces WHERE id=%s', (w,))
        c.execute("DELETE FROM users WHERE guest AND NOT EXISTS(SELECT 1 FROM memberships m WHERE m.user_id=users.id)")
