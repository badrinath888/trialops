"""Document-processing source automation against the running TEST stack (3002 API + worker only). Synthetic mock sources; fresh expiring demo workspaces removed in finally.
Run in the test API container: python /app/tests/source_events_integration.py"""
import sys, json, time, threading, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/api'))
from integration import Client, URL
from db import connect, secret
from psycopg.types.json import Jsonb
from journey import example_export

A, B = Client(), Client()
n = 0
def passed(s):
    global n; n += 1; print('PASS:', s, flush=True)
def sql(q, *p):
    with connect() as c:
        cur = c.execute(q, p)
        return cur.fetchall() if cur.description else None
def role(r): sql('UPDATE memberships SET role=%s WHERE workspace_id=%s AND user_id=%s', r, W, UID)
def wait(pred, timeout=60, what=''):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = pred()
        if v: return v
        time.sleep(0.5)
    raise AssertionError('timed out waiting for ' + what)
def post(key, body=None, raw=None):
    data = raw if raw is not None else json.dumps(body).encode()
    req = urllib.request.Request(URL + '/sources/events', data=data, headers={'Content-Type': 'application/json', 'X-Internal-Key': secret('INTERNAL_KEY'), 'X-Source-Key': key, 'X-Client-IP': '10.9.8.7'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r: return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read())
        except ValueError: return e.code, {}
now = datetime.now(timezone.utc).replace(microsecond=0)
ago = lambda h: now - timedelta(hours=h)
PORTAL, HUB, STUDY, SITE = 'mock-upload-portal', 'mock-binder-hub', 'CT-204', 'SITE-104'
workspaces = []
def ev_of(eid): return sql('SELECT * FROM source_events WHERE workspace_id=%s AND external_id=%s', W, eid)[0]
def status_of(eid): return ev_of(eid)['status']
def settled(eid): return wait(lambda: status_of(eid) in ('processed', 'unmatched', 'ambiguous', 'failed', 'ignored') and status_of(eid), 60, eid)
def count(table, extra='', *p): return sql(f'SELECT count(*) AS n FROM {table} WHERE workspace_id=%s {extra}', W, *p)[0]['n']
def portal(doc, ver, state, at, ref, event, rev=1):
    ex = example_export('portal', STUDY, SITE, None, ref=ref, observed_at=at, rows=[
        {'event': 'RECEIPT', 'receipt_no': 'RCPT-' + ref[-6:], 'doc_id': doc, 'doc_rev': ver, 'state': 'RECEIVED', 'at': at.isoformat()},
        {'event': 'PROCESS', 'receipt_no': 'PROC-' + ref[-6:], 'doc_id': doc, 'doc_rev': ver, 'state': state, 'at': at.isoformat()}])
    return {'schema_version': '1', 'event_id': event, 'source_rev': rev, 'observed_at': at.isoformat(), 'export': ex['export'], 'mapping': ex['mapping']}
def tag(): return uuid4().hex[:10]
try:
    W = A.call('/auth/demo', {})['workspace_id']; workspaces.append(W); WB = B.call('/auth/demo', {})['workspace_id']; workspaces.append(WB)
    UID = A.call('/auth/me')['user_id']
    def mkcase(cid, w=None):
        sql("INSERT INTO cases(workspace_id,id,study_id,site_id,title,description,category,priority,status) VALUES(%s,%s,%s,%s,'Source case','Synthetic.','document_workflow','medium','open')", w or W, cid, STUDY, SITE)
    CID = 'SRC-1'; mkcase(CID)
    run_id = uuid4(); sql("INSERT INTO runs(workspace_id,id,case_id,result,duration_seconds,model) VALUES(%s,%s,%s,%s,0,'test')", W, run_id, CID, Jsonb({'recommendation': {'status': 'supported', 'evidence_ids': []}, 'sources': []}))
    runs_hash = sql('SELECT md5(string_agg(result::text,\'\')) AS h FROM runs WHERE workspace_id=%s', W)[0]['h']
    P = f'/cases/{CID}/journey'
    A.call(P + '/subject', {'id': str(uuid4()), 'expected_rev': 0, 'document_system': PORTAL, 'document_ref': 'DOC-5001', 'document_version': '2', 'destination_system': HUB, 'binder_ref': 'BND-77'})
    A.call(P + '/outcomes', {'id': str(uuid4()), 'key': str(uuid4()), 'expected_rev': 0, 'description': 'Document processing is complete for the filed version.', 'requirements': [{'stage': 'processing', 'status': 'completed'}], 'required': True, 'remediation_at': ago(48).isoformat()}, 201)

    # ---- 1. source configuration and authentication
    assert A.call('/sources')['sources'] == [] and B.call('/sources')['sources'] == []
    A.call('/sources', {'name': 'x', 'adapter': 'mock_portal'}, 422); A.call('/sources', {'name': 'Real vendor', 'adapter': 'real_vendor'}, 422)
    r = A.call('/sources', {'name': 'Mock portal A', 'adapter': 'mock_portal'}, 201); SRC, KEY = r['id'], r['source_key']
    assert KEY.startswith('tos_') and 'source_key' not in A.call('/sources')['sources'][0] and sql('SELECT token_hash FROM source_connections WHERE workspace_id=%s', W)[0]['token_hash'] != KEY
    rB = B.call('/sources', {'name': 'Mock portal B', 'adapter': 'mock_portal'}, 201); KEYB = rB['source_key']
    t0 = tag(); good = portal('DOC-5001', '2', 'WAIT', ago(5), 'EX-%s' % t0, 'EVT-' + t0)
    assert post('', good)[0] == 401 and post('tos_bogus', good)[0] == 401 and post('Bearer ' + KEY, good)[0] == 401
    B.call(f'/sources/{SRC}/status', {'status': 'paused'}, 404); B.call(f'/sources/{SRC}/mock-event', {'case_id': CID, 'scenario': 'processing_completed'}, 404)
    role('reviewer'); A.call('/sources', {'name': 'Nope nope', 'adapter': 'mock_portal'}, 403); A.call('/sources/automation', {'draft_preparation': True}, 403); A.call(f'/sources/{SRC}/status', {'status': 'paused'}, 403); role('owner')
    assert len(B.call('/sources')['sources']) == 1 and B.call('/sources')['sources'][0]['id'] != SRC
    passed('owner-only configuration; keys stored hashed and shown once; bad/missing keys rejected; other workspace cannot see or change the source')

    # ---- 2. validation before storage; workspace comes from the key
    base_events = count('source_events')
    assert post(KEY, raw=b'x' * 70000)[0] == 413
    assert post(KEY, {**good, 'schema_version': '2'})[0] == 422 and post(KEY, {**good, 'workspace_id': str(WB)})[0] == 422  # caller-supplied workspace is not a field
    nonrows = {**good, 'export': {**good['export'], 'rows': []}}; assert post(KEY, nonrows)[0] == 422                      # notification without structured rows is not evidence
    nocov = {**good, 'export': {k: v for k, v in good['export'].items() if k != 'coverage'}}; assert post(KEY, nocov)[0] == 422
    assert post(KEY, {**good, 'export': {**good['export'], 'source_system': HUB}})[0] == 422                                 # source identity must match the connection
    assert post(KEY, {**good, 'export': {**good['export'], 'study_id': 'CT-999'}})[0] == 422 and post(KEY, {**good, 'observed_at': ago(1).isoformat()})[0] == 422
    assert post(KEY, {**good, 'source_rev': 0})[0] == 422 and post(KEY, {**good, 'event_id': 'bad id!'})[0] == 422
    assert count('source_events') == base_events
    passed('payload size, schema version, structured fields, coverage, source identity, scope and workspace binding validated before anything is stored')

    # ---- 3. acceptance scenario: pending document -> exact completed update
    exp0 = count('journey_exports'); notif0 = count('notifications', "AND dedupe_key LIKE 'source-update:%%'")
    assert post(KEY, good)[0] == 202; assert settled('EVT-' + t0) == 'processed'
    e1 = ev_of('EVT-' + t0); assert e1['case_id'] == CID and e1['result']['checks_updated'] >= 1 and count('journey_exports') == exp0 + 1
    t1 = tag(); done = portal('DOC-5001', '2', 'DONE', ago(1), 'EX-%s' % t1, 'EVT-' + t1, 2)
    jobs0 = count('jobs', "AND kind='source_event'"); reqs0 = count('information_requests'); assess0 = count('journey_assessments')
    s, b = post(KEY, done); assert s == 202
    assert settled('EVT-' + t1) == 'processed'
    e2 = ev_of('EVT-' + t1); assert e2['result']['checks_updated'] >= 1 and e2['result']['stages_changed'] == ['processing']
    w = A.call(f'/cases/{CID}/watch'); up = w['updates'][0]
    assert up['source_event_id'] and up['changes'][0].startswith('New evidence received. ') and 'updated. Review changes.' in up['changes'][0], up['changes']
    d = up['detail']; assert d['source']['event_id'] == 'EVT-' + t1 and d['source']['source_rev'] == 2 and len(d['source']['content_hash']) == 64 and d['source']['received_at'] and d['source']['observed_at']
    assert any('processing' in x['label'].lower() for x in d['checks_updated']) and d['evidence_after'] and d['evidence_before'] is not None
    j = A.call(P)['journey']; st = {x['stage']: x for x in j['stages']}
    assert st['processing']['operational_status'] == 'completed' and st['binder_visibility']['assessment'] == 'unknown' and st['destination_filing']['assessment'] == 'unknown'
    assert any('Binder visibility: unknown' in u for u in up['uncertain']) and 'Recorded evidence does not establish root cause or resolution' in ' '.join(up['uncertain'])
    assert 'Suggested next request' in up['next_action'] and d['draft'] is None and count('information_requests') == reqs0, 'draft setting is off by default: suggestion only'
    assert sql("SELECT status FROM cases WHERE workspace_id=%s AND id=%s", W, CID)[0]['status'] == 'open'
    notes = sql("SELECT * FROM notifications WHERE workspace_id=%s AND dedupe_key LIKE 'source-update:%%'", W); assert len(notes) - notif0 == 1 and 'check' in notes[-1]['title'] and 'resolved' not in notes[-1]['title'].lower()
    passed('acceptance: pending then exact completed update saves evidence, updates only affected checks, keeps destination visibility unknown, suggests one next action, case stays open, one notification')

    # ---- 4. duplicates and conflicting reuse
    snap = lambda: (count('journey_exports'), count('case_watch_updates'), count('notifications'), count('journey_assessments'), count('information_requests'), count('source_events'))
    before = snap()
    for _ in range(3): s, b = post(KEY, done); assert (s, b['status']) == (200, 'duplicate')
    assert snap() == before and ev_of('EVT-' + t1)['duplicates'] == 3 and count('jobs', "AND kind='source_event' AND status IN ('queued','running')") == 0
    conflict = {**done, 'source_rev': 9}; s, b = post(KEY, conflict); assert s == 409 and 'quarantined' in b['detail']
    assert snap() == before and count('source_event_conflicts') == 1 and ev_of('EVT-' + t1)['content_hash'] == e2['content_hash']
    assert post(KEY, conflict)[0] == 409 and count('source_event_conflicts') == 1, 'repeating the same conflicting delivery adds nothing'
    passed('duplicate delivery creates no evidence, job result, update, draft or notification; conflicting event-ID reuse is quarantined and the original is untouched')

    # ---- 5. routing: wrong version, unmatched, collision, ambiguity, reviewer-confirmed link
    cases0 = count('cases')
    for name, ev in (('wrong', portal('DOC-5001', '9', 'DONE', ago(1), 'EX-w' + tag(), 'EVT-w' + tag())), ('other', portal('DOC-0000', '2', 'DONE', ago(1), 'EX-o' + tag(), 'EVT-o' + tag()))):
        assert post(KEY, ev)[0] == 202; assert settled(ev['event_id']) == 'unmatched'
        assert ev_of(ev['event_id'])['reason'] == ('wrong_version' if name == 'wrong' else 'no_exact_mapping') and ev_of(ev['event_id'])['case_id'] is None
    assert snap()[0] == before[0] and count('cases') == cases0, 'nothing saved as evidence; no case created'
    # a second source system with the same document id: source-scoped collision, not a match
    rh = A.call('/sources', {'name': 'Mock hub A', 'adapter': 'mock_hub'}, 201); HSRC, HKEY = rh['id'], rh['source_key']
    hv = A.call(f'/sources/{HSRC}/mock-event', {'case_id': CID, 'scenario': 'processing_completed'}); assert hv['delivery'] == 'accepted'
    hid = sql('SELECT external_id FROM source_events WHERE workspace_id=%s AND source_id=%s', W, HSRC)[0]['external_id']; assert settled(hid) == 'unmatched' and count('journey_exports', "AND source_system='mock-binder-hub'") == 0
    # reviewer-confirmed link makes it exactly routable on explicit re-evaluation
    mi = example_export('hub', STUDY, SITE, None, ref='MAN-' + tag(), observed_at=ago(40)); A.call('/operations/journey-import', {'export': mi['export'], 'mapping': mi['mapping']}, 201)  # existing manual import path
    A.call(P + '/links', {'id': str(uuid4()), 'kind': 'document', 'from_system': HUB, 'from_ref': 'DOC-5001', 'rationale': 'Reviewer confirmed the hub id is this document.', 'evidence': 'Mapping table row 12'}, 201)
    hev = sql('SELECT id FROM source_events WHERE workspace_id=%s AND external_id=%s', W, hid)[0]['id']
    role('analyst'); A.call(f'/sources/events/{hev}/reroute', {}, 403); role('owner')
    A.call(f'/sources/events/{hev}/reroute', {}); assert settled(hid) == 'processed' and ev_of(hid)['case_id'] == CID and ev_of(hid)['reason'] is None
    # ambiguity: a second open case with the same exact mapping
    mkcase('SRC-2'); A.call('/cases/SRC-2/journey/subject', {'id': str(uuid4()), 'expected_rev': 0, 'document_system': PORTAL, 'document_ref': 'DOC-5001', 'document_version': '2', 'destination_system': HUB, 'binder_ref': 'BND-77'})
    ta = tag(); amb = portal('DOC-5001', '2', 'DONE', ago(0.5), 'EX-a' + ta, 'EVT-a' + ta); assert post(KEY, amb)[0] == 202; assert settled('EVT-a' + ta) == 'ambiguous' and ev_of('EVT-a' + ta)['reason'] == 'multiple_exact_cases'
    sql("DELETE FROM cases WHERE workspace_id=%s AND id='SRC-2'", W)
    # another workspace's key can never route into this workspace
    assert post(KEYB, portal('DOC-5001', '2', 'DONE', ago(0.5), 'EX-b' + ta, 'EVT-b' + ta))[0] == 202
    wait(lambda: sql('SELECT status FROM source_events WHERE workspace_id=%s', WB)[0]['status'] == 'unmatched', 30, 'cross workspace'); assert count('journey_exports', "AND export_ref LIKE 'EX-b%%'") == 0
    passed('exact routing only: wrong version, unmatched, source-scoped ID collision and ambiguous mappings stay unrouted; reviewer-confirmed link routes on explicit re-evaluation; other workspaces never match')

    # ---- 6. out-of-order observation and conflicting sources; history preserved
    ex_before = sql("SELECT id,content_hash,md5(records::text) AS r FROM journey_exports WHERE workspace_id=%s ORDER BY id", W)
    as_before = sql("SELECT id,fingerprint,md5(result::text) AS r FROM journey_assessments WHERE workspace_id=%s ORDER BY id", W)
    to = tag(); old = portal('DOC-5001', '2', 'WAIT', ago(30), 'EX-old' + to, 'EVT-old' + to, 3)
    u0 = count('case_watch_updates'); n0 = count('notifications'); assert post(KEY, old)[0] == 202; assert settled('EVT-old' + to) == 'processed'
    assert ev_of('EVT-old' + to)['result']['checks_updated'] == 0 and count('case_watch_updates') == u0 and count('notifications') == n0
    st = {x['stage']: x for x in A.call(P)['journey']['stages']}; assert st['processing']['operational_status'] == 'completed' and st['processing']['earlier_observations'] >= 1
    assert all(sql("SELECT md5(records::text) AS r FROM journey_exports WHERE workspace_id=%s AND id=%s", W, x['id'])[0]['r'] == x['r'] for x in ex_before), 'earlier evidence rows unchanged'
    assert all(sql("SELECT md5(result::text) AS r FROM journey_assessments WHERE workspace_id=%s AND id=%s", W, x['id'])[0]['r'] == x['r'] for x in as_before), 'earlier assessments unchanged'
    assert sql('SELECT md5(string_agg(result::text,\'\')) AS h FROM runs WHERE workspace_id=%s', W)[0]['h'] == runs_hash, 'frozen investigation evidence unchanged'
    tc = tag()  # a second system reports processing failed after the portal's completed record -> sources disagree
    cf = {'schema_version': '1', 'event_id': 'EVT-c' + tc, 'source_rev': 1, 'observed_at': ago(0.2).isoformat(), 'export': {'source_system': HUB, 'export_ref': 'EX-c' + tc, 'study_id': STUDY, 'site_id': SITE, 'observed_at': ago(0.2).isoformat(), 'synthetic': True,
          'coverage': {'complete': True, 'stages': ['processing']}, 'rows': [{'id': 'PR-' + tc, 'doc': 'DOC-5001', 'ver': '2', 'st': 'BAD', 'at': ago(0.2).isoformat()}]},
          'mapping': {'stage': 'processing', 'fields': {'source_ref': 'id', 'document_ref': 'doc', 'version': 'ver', 'status': 'st', 'observed_at': 'at'}, 'status_values': {'BAD': 'failed'}}}
    assert post(HKEY, cf)[0] == 202; assert settled('EVT-c' + tc) == 'processed'
    up = A.call(f'/cases/{CID}/watch')['updates'][0]; assert any('Processing: conflicting sources' in x for x in up['uncertain']) and ev_of('EVT-c' + tc)['result']['checks_updated'] >= 1
    assert 'caused' not in ' '.join(up['changes'] + up['uncertain']).lower() or 'root cause' in ' '.join(up['uncertain']).lower()
    passed('out-of-order observation is kept as history without changing current state or notifying; conflicting sources surface as unresolved; earlier evidence, assessments and frozen investigations unchanged')

    # ---- 7. stale ranking and reviewer overrides preserved
    PR = P + '/priority'
    sv = A.call(PR + '/save', {'id': str(uuid4()), 'expected_rev': 0}, 201); cands = [c['key'] for c in A.call(PR)['candidates']]
    if len(cands) > 1: A.call(PR + '/override', {'id': str(uuid4()), 'expected_rev': 1, 'order': list(reversed(cands)), 'reason': 'Reviewer prefers this order for now.'}, 201)
    revs = sql('SELECT rev,md5(override::text) AS o FROM journey_prioritizations WHERE workspace_id=%s ORDER BY rev', W)
    tr = tag(); assert post(HKEY, {**cf, 'event_id': 'EVT-r' + tr, 'observed_at': ago(0.1).isoformat(), 'export': {**cf['export'], 'export_ref': 'EX-r' + tr, 'observed_at': ago(0.1).isoformat(), 'rows': [{**cf['export']['rows'][0], 'id': 'PR-r' + tr, 'at': ago(0.1).isoformat(), 'st': 'BAD'}]}})[0] == 202
    settled('EVT-r' + tr); g = A.call(PR)
    assert g['saved']['stale'] is True and sql('SELECT rev,md5(override::text) AS o FROM journey_prioritizations WHERE workspace_id=%s ORDER BY rev', W) == revs, 'ranking marked stale; no version refreshed; override untouched'
    passed('saved request ranking turns stale by existing rules; no refresh and no carried override')

    # ---- 8. draft preparation: off -> on, duplicate prevention, authority
    reqs0 = count('information_requests')
    CIDD = 'SRC-D'; mkcase(CIDD); sql("INSERT INTO runs(workspace_id,id,case_id,result,duration_seconds,model) VALUES(%s,%s,%s,%s,0,'test')", W, uuid4(), CIDD, Jsonb({'recommendation': {'status': 'supported', 'evidence_ids': []}, 'sources': []}))
    A.call(f'/cases/{CIDD}/journey/subject', {'id': str(uuid4()), 'expected_rev': 0, 'document_system': PORTAL, 'document_ref': 'DOC-7001', 'document_version': '1', 'destination_system': HUB, 'binder_ref': 'BND-91'})
    toff = tag(); assert post(KEY, portal('DOC-7001', '1', 'WAIT', ago(0.06), 'EX-f' + toff, 'EVT-f' + toff, 3))[0] == 202; settled('EVT-f' + toff)
    off = ev_of('EVT-f' + toff)['result']; assert off['checks_updated'] >= 1 and off['candidate'] and not off.get('draft') and count('information_requests') == reqs0, 'setting off: suggestion only'
    reqs0 = count('information_requests')
    A.call('/sources/automation', {'draft_preparation': True})
    reqs = reqs0; td = tag(); nd = portal('DOC-7001', '1', 'DONE', ago(0.05), 'EX-d' + td, 'EVT-d' + td, 4)
    assert post(KEY, nd)[0] == 202; assert settled('EVT-d' + td) == 'processed'
    res = ev_of('EVT-d' + td)['result']
    assert res['checks_updated'] >= 1
    if True:
        dr = res.get('draft'); assert dr and dr['state'] == 'prepared' and dr['unsent'] is True, res
        rq = sql('SELECT * FROM information_requests WHERE workspace_id=%s AND id=%s', W, dr['request_id'])[0]; assert rq['status'] == 'draft' and rq['contact_id'] is None and count('information_requests') == reqs + 1
        assert A.call(f'/cases/{CIDD}/watch')['updates'][0]['detail']['draft']['request_id'] == dr['request_id']
        for _ in range(2): assert post(KEY, nd)[1]['status'] == 'duplicate'
        assert count('information_requests') == reqs + 1
        again = tag(); assert post(KEY, portal('DOC-7001', '1', 'ERR', ago(0.04), 'EX-d' + again, 'EVT-d' + again, 5))[0] == 202; settled('EVT-d' + again)
        assert count('information_requests') == reqs + 1, 'an equivalent active draft/request already exists'
    sql("DELETE FROM information_requests WHERE workspace_id=%s AND status='draft'", W)
    sql("UPDATE memberships SET role='reviewer' WHERE workspace_id=%s AND user_id=%s", W, UID)  # enabling owner lost owner permission
    tp = tag(); assert post(KEY, portal('DOC-7001', '1', 'DONE', ago(0.03), 'EX-p' + tp, 'EVT-p' + tp, 6))[0] == 202; settled('EVT-p' + tp)
    assert not (ev_of('EVT-p' + tp)['result'].get('draft') or {}).get('request_id'); role('owner')
    A.call('/sources/automation', {'draft_preparation': False}); assert A.call('/sources')['draft_preparation'] is False
    passed('drafts are prepared only when the owner setting is on, unsent, contact-less, never duplicated and need the owner’s current permission; off shows the suggestion only')

    # ---- 9. nothing approved, sent, resolved or confirmed
    assert count('information_requests', "AND status NOT IN ('draft','cancelled')") == 0 and count('external_responses') == 0 and count('assessment_decisions') == 0
    assert sql("SELECT status FROM cases WHERE workspace_id=%s AND id=%s", W, CID)[0]['status'] == 'open' and count('journey_links', "AND revoked_at IS NULL") == 1
    assert not sql("SELECT 1 FROM case_events WHERE workspace_id=%s AND event_type IN ('case_resolved','case_reopened','recommendation_approved','request_sent')", W)
    passed('no approval, sending, response acceptance, linkage confirmation or case resolution happened automatically')

    # ---- 10. paused / revoked source during queued work; resume
    ps = A.call('/sources', {'name': 'Mock portal P', 'adapter': 'mock_portal'}, 201); PID, PKEY = ps['id'], ps['source_key']
    tq = tag(); qe = portal('DOC-5001', '2', 'DONE', ago(0.02), 'EX-q' + tq, 'EVT-q' + tq, 7)
    A.call(f'/sources/{PID}/status', {'status': 'paused'}); s, b = post(PKEY, qe); assert s == 403
    A.call(f'/sources/{PID}/status', {'status': 'enabled'})
    sql("UPDATE source_connections SET status='paused' WHERE workspace_id=%s AND id=%s", W, PID)
    sql("INSERT INTO source_events(workspace_id,id,source_id,external_id,source_rev,observed_at,schema_version,content_hash,payload) VALUES(%s,%s,%s,%s,7,%s,'1','q',%s)", W, uuid4(), PID, 'EVT-q' + tq, ago(0.02), Jsonb({'export': qe['export'], 'mapping': qe['mapping']}))
    ex_n = count('journey_exports'); time.sleep(14); assert status_of('EVT-q' + tq) == 'received' and count('journey_exports') == ex_n, 'paused source: queued event persists nothing'
    A.call(f'/sources/{PID}/status', {'status': 'revoked'}); wait(lambda: status_of('EVT-q' + tq) == 'ignored', 40, 'revoked'); assert ev_of('EVT-q' + tq)['reason'] == 'source_revoked' and count('journey_exports') == ex_n
    A.call(f'/sources/{PID}/status', {'status': 'enabled'}, 409); assert post(PKEY, qe)[0] == 401
    passed('paused source holds queued events without saving evidence; revoked source discards them; revoked keys and sources cannot be revived')

    # ---- 11. worker restart / interrupted lease resumes without duplicates; bounded retries
    tw = tag(); rs = portal('DOC-5001', '2', 'DONE', ago(0.01), 'EX-r2' + tw, 'EVT-r2' + tw, 8); assert post(KEY, rs)[0] == 202
    eid = ev_of('EVT-r2' + tw)['id']
    sql("UPDATE jobs SET status='running',started_at=now()-interval '20 minutes',lease_expires_at=now()-interval '10 minutes',lease_token=gen_random_uuid() WHERE workspace_id=%s AND target_id=%s AND status='queued'", W, str(eid))  # a worker died holding it
    settled('EVT-r2' + tw); assert status_of('EVT-r2' + tw) == 'processed' and count('journey_exports', "AND export_ref=%s", 'EX-r2' + tw) == 1 and count('case_watch_updates', "AND source_event_id=%s", eid) <= 1
    bad = uuid4(); sql("INSERT INTO source_events(workspace_id,id,source_id,external_id,source_rev,observed_at,schema_version,content_hash,payload) VALUES(%s,%s,%s,'EVT-bad',1,now(),'1','b',%s)", W, bad, SRC, Jsonb({'export': {'broken': True}, 'mapping': {}}))
    sql("INSERT INTO jobs(id,workspace_id,actor_id,kind,target_id) VALUES(%s,%s,NULL,'source_event',%s)", uuid4(), W, str(bad))
    wait(lambda: status_of('EVT-bad') == 'failed', 150, 'bounded retries'); fb = ev_of('EVT-bad'); assert fb['attempts'] == 3 and fb['reason'] == 'retries_exhausted' and fb['case_id'] is None
    err = A.call('/sources')['sources'][0]['last_error']; assert err and 'Traceback' not in err and 'broken' not in err
    assert count('jobs', "AND kind='source_event' AND status IN ('queued','running')") == 0
    passed('interrupted work resumes once with no duplicate evidence or update; a failing event is retried at most 3 times with backoff, ends failed with a sanitized message and is never marked processed')

    # ---- 12. concurrency: parallel identical deliveries and parallel distinct updates for one case
    tdp = tag(); same = portal('DOC-5001', '2', 'DONE', ago(0.005), 'EX-s' + tdp, 'EVT-s' + tdp, 9); out = []
    ths = [threading.Thread(target=lambda: out.append(post(KEY, same)[0])) for _ in range(6)]; [t.start() for t in ths]; [t.join() for t in ths]
    assert sorted(out) == [200] * 5 + [202], out; settled('EVT-s' + tdp); assert count('journey_exports', "AND export_ref=%s", 'EX-s' + tdp) == 1
    ids = []; out = []
    for i in range(4):
        t_ = tag(); ids.append('EVT-m' + t_); ev = portal('DOC-5001', '2', ['WAIT', 'DONE'][i % 2], ago(0.004 - i * 0.0001), 'EX-m' + t_, 'EVT-m' + t_, 10 + i); ths_ = ev
        out.append(ev)
    ths = [threading.Thread(target=post, args=(KEY, e)) for e in out]; [t.start() for t in ths]; [t.join() for t in ths]
    assert all(settled(i) == 'processed' for i in ids) and sum(count('journey_exports', "AND export_ref=%s", e['export']['export_ref']) for e in out) == 4
    unread = sql("SELECT count(*) AS n FROM notifications WHERE workspace_id=%s AND case_id=%s AND dedupe_key LIKE 'source-update:%%' AND read_at IS NULL", W, CID)[0]['n']; assert unread <= 1, unread
    passed('parallel identical deliveries create one event; parallel distinct updates for one case are all processed once, serialized per case, with at most one unread actionable notification')

    # ---- 13. review action, notification dedupe, activity
    up = A.call(f'/cases/{CID}/watch')['updates'][0]
    if up.get('detail'):
        assert A.call(f'/cases/{CID}/watch/updates/{up["id"]}/review', {})['status'] == 'reviewed' and A.call(f'/cases/{CID}/watch/updates/{up["id"]}/review', {})['status'] == 'already_reviewed'
        assert sql("SELECT count(*) AS n FROM notifications WHERE workspace_id=%s AND case_id=%s AND dedupe_key LIKE 'source-update:%%' AND read_at IS NULL", W, CID)[0]['n'] == 0
    A.call(f'/cases/{CID}/watch/updates/{uuid4()}/review', {}, 404); B.call(f'/cases/{CID}/watch/updates/{up["id"]}/review', {}, 404)
    act = A.call('/sources')['activity']
    assert act['received'] >= 10 and act['deduplicated'] >= 10 and act['quarantined'] == 1 and act['unmatched'] == 3 and act['drafts_prepared'] == 1 and act['failed'] == 1 and act['processed'] >= 8 and act['reviewer_actions'] == 1 and 'not time-saved' in act['note']
    assert count('case_events', "AND event_type='source_update_processed'") >= 3
    passed('reviewer action recorded and clears the notification; activity counts come from recorded events and make no time-saved claim')
    print(f'PASS: {n} source automation groups. Temporary records removed in finally.', flush=True)
finally:
    with connect() as c:
        for w in workspaces: c.execute('DELETE FROM workspaces WHERE id=%s', (w,))
        c.execute("DELETE FROM users WHERE guest AND NOT EXISTS(SELECT 1 FROM memberships m WHERE m.user_id=users.id)")
