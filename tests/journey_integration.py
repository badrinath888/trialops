"""Document journey against the running TEST stack (port 3002 API only). Only fresh expiring demo workspaces are created; removed in finally.
Run inside the test API container: python /app/tests/journey_integration.py"""
import sys, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/api'))
from integration import Client, URL
from db import connect, secret
from psycopg.types.json import Jsonb
from journey import example_export
import urllib.request

A, B, AN = Client(), Client(), Client()
n = 0
def passed(s):
    global n; n += 1; print('PASS:', s, flush=True)
def sql(q, *p):
    with connect() as c:
        cur = c.execute(q, p)
        return cur.fetchall() if cur.description else None
def role(r, uid=None, w=None): sql('UPDATE memberships SET role=%s WHERE workspace_id=%s AND user_id=%s', r, w or W, uid or UID)
def events(cid, kind): return sql('SELECT * FROM case_events WHERE workspace_id=%s AND case_id=%s AND event_type=%s', W, cid, kind)
def raw(client, path):
    req = urllib.request.Request(URL + path, headers={'X-Internal-Key': secret('INTERNAL_KEY'), 'X-Client-IP': str(id(client)), 'Cookie': '; '.join(c.name + '=' + c.value for c in client.cookies)})
    with urllib.request.urlopen(req, timeout=60) as r: return r.read()

now = datetime.now(timezone.utc).replace(microsecond=0)
ago = lambda h: now - timedelta(hours=h)
workspaces = []
PORTAL, HUB = 'mock-upload-portal', 'mock-binder-hub'
try:
    W = A.call('/auth/demo', {})['workspace_id']; workspaces.append(W); WB = B.call('/auth/demo', {})['workspace_id']; workspaces.append(WB)
    UID = A.call('/auth/me')['user_id']
    sql("INSERT INTO cases(workspace_id,id,study_id,site_id,title,description,category,priority,status) VALUES(%s,'JRN-1','CT-204','SITE-104','Certificate missing from binder','Synthetic journey case.','document_workflow','medium','open')", W)
    sql("INSERT INTO cases(workspace_id,id,study_id,site_id,title,description,category,priority,status) VALUES(%s,'JRN-2','CT-204','SITE-104','Second case no run','Synthetic.','document_workflow','medium','open')", WB)
    peer = uuid4(); sql("INSERT INTO users(id,email,name,guest) VALUES(%s,%s,'Peer analyst',true)", peer, f'{peer}@sample.invalid'); sql("INSERT INTO memberships(workspace_id,user_id,role) VALUES(%s,%s,'analyst')", W, peer)

    def imp(client, shape, ref, at, rows=None, complete=True, expected=201, study='CT-204', site='SITE-104'):
        ex = example_export(shape, study, site, ref=ref, observed_at=at, rows=rows, complete=complete)
        return client.call('/operations/journey-import', {'export': ex['export'], 'mapping': ex['mapping']}, expected), ex

    # ---- 1. import: owner only, synthetic provenance, immutable references, workspace-scoped
    role('reviewer'); imp(A, 'portal', 'P1', ago(6), expected=403); role('owner')
    imp(A, 'portal', 'BAD', now + timedelta(days=1), expected=422)
    imp(A, 'portal', 'BAD2', ago(6), study='CT-999', expected=422)
    pr = [{'event': 'RECEIPT', 'receipt_no': 'RCPT-5001', 'doc_id': 'DOC-5001', 'doc_rev': '2', 'state': 'RECEIVED', 'at': ago(6).isoformat(), 'comment': 'DOC-9999 version 7 filed after 3 minutes'},
          {'event': 'PROCESS', 'receipt_no': 'PROC-5001', 'doc_id': 'DOC-5001', 'doc_rev': '2', 'state': 'WAIT', 'at': ago(6).isoformat()}]
    r1, ex1 = imp(A, 'portal', 'P1', ago(6), pr)
    assert imp(A, 'portal', 'P1', ago(6), pr, expected=201)[0]['status'] == 'already_imported'
    imp(A, 'portal', 'P1', ago(6), pr[:1], expected=409)
    imp(B, 'portal', 'P1', ago(6), pr)  # same reference in another workspace is independent
    hub_failed = [{'kind': 'sync_job', 'job': {'id': 'JOB-7001'}, 'item': {}, 'outcome': 'failed', 'when': ago(5).isoformat(), 'target': 'BND-77'}]
    imp(A, 'hub', 'H1', ago(5), hub_failed, complete=False)
    assert sql('SELECT count(*) AS n FROM journey_exports WHERE workspace_id=%s', W)[0]['n'] == 2
    passed('import is owner-only, synthetic, scoped to workspace sites, immutable per source reference, idempotent, and keeps free text unparsed')

    # ---- 2. subject definition: roles, idempotency, optimistic revision, isolation
    S = str(uuid4()); subj = {'id': S, 'expected_rev': 0, 'document_system': PORTAL, 'document_ref': 'DOC-5001', 'document_version': '2', 'destination_system': HUB, 'binder_ref': 'BND-77'}
    A.call('/cases/JRN-1/journey/subject', {**subj, 'document_ref': 'DOC 5001'}, 422)
    B.call('/cases/JRN-1/journey/subject', subj, 404)
    role('analyst'); A.call('/cases/JRN-1/journey/subject', subj, 403)
    assert A.call('/cases/JRN-1/journey')['subject'] is None; role('owner')
    assert A.call('/cases/JRN-1/journey/subject', subj)['rev'] == 1 and A.call('/cases/JRN-1/journey/subject', subj)['rev'] == 1
    A.call('/cases/JRN-1/journey/subject', {**subj, 'binder_ref': 'BND-88'}, 409)
    A.call('/cases/JRN-1/journey/subject', {**subj, 'id': str(uuid4())}, 409)
    assert len(sql('SELECT 1 FROM journey_subjects WHERE workspace_id=%s', W)) == 1 and len(events('JRN-1', 'journey_subject_set')) == 1
    passed('document/binder definition: role, validation, idempotent retry, stale revision and cross-workspace access enforced')

    # ---- 3. scenario: receipt exists, processing pending, failed sync unlinked => transfer unknown
    j = A.call('/cases/JRN-1/journey')
    st = {s['stage']: s for s in j['journey']['stages']}
    assert (st['upload_receipt']['assessment'], st['processing']['operational_status'], st['processing']['assessment']) == ('verified', 'pending', 'verified'), st
    t = st['transfer']; assert t['assessment'] == 'unknown' and t['operational_status'] is None and t['candidates'][0]['problems'] == ['unlinked'], t
    assert st['processing']['records'][0]['raw']['doc_id'] == 'DOC-5001' and st['upload_receipt']['records'][0]['source_system'] == PORTAL
    assert 'DOC-9999' not in json.dumps(j['journey']['findings']) and st['upload_receipt']['records'][0]['document_ref'] == 'DOC-5001'
    role('analyst'); assert A.call('/cases/JRN-1/journey')['can_write'] is False; role('owner')
    B.call('/cases/JRN-1/journey', expected=404)
    passed('unlinked failed sync leaves transfer unknown (candidate kept, status not assigned); hostile free text ignored; analyst can read, outsider cannot')

    # ---- 4. reviewed linkage => supported failure without root cause; revoke
    L = str(uuid4()); link = {'id': L, 'kind': 'record', 'from_system': HUB, 'from_ref': 'JOB-7001', 'rationale': 'Hub job log names this document and receipt.', 'evidence': 'Hub job log line 12'}
    A.call('/cases/JRN-1/journey/links', {**link, 'from_ref': 'JOB-0000', 'id': str(uuid4())}, 422)
    A.call('/cases/JRN-1/journey/links', {**link, 'rationale': 'short'}, 422)
    B.call('/cases/JRN-1/journey/links', link, 404)
    role('analyst'); A.call('/cases/JRN-1/journey/links', link, 403); role('owner')
    A.call('/cases/JRN-1/journey/links', link, 201); A.call('/cases/JRN-1/journey/links', link, 201)
    A.call('/cases/JRN-1/journey/links', {**link, 'rationale': 'A different rationale entirely.'}, 409)
    assert len(sql('SELECT 1 FROM journey_links WHERE workspace_id=%s', W)) == 1
    t = {s['stage']: s for s in A.call('/cases/JRN-1/journey')['journey']['stages']}['transfer']
    assert (t['assessment'], t['operational_status'], t['records'][0]['match_basis']) == ('verified', 'failed', 'reviewer_link') and 'root cause is not established' in ' '.join(t['notes'])
    assert t['records'][0]['link']['rationale'].startswith('Hub job log')
    assert A.call(f'/cases/JRN-1/journey/links/{L}/revoke', {'reason': 'Testing revoke path.'})['revoked_at'] and A.call(f'/cases/JRN-1/journey/links/{L}/revoke', {'reason': 'Testing revoke path.'})['revoked_at']
    assert {s['stage']: s for s in A.call('/cases/JRN-1/journey')['journey']['stages']}['transfer']['assessment'] == 'unknown'
    L2 = str(uuid4()); A.call('/cases/JRN-1/journey/links', {**link, 'id': L2}, 201)
    passed('human-confirmed link (with rationale+evidence) yields a verified failure without root cause; revocation restores unknown; history kept')

    # ---- 5. collection plan through the existing request workflow
    G = 'export_incomplete:destination_filing'
    plan = lambda **k: {'id': str(uuid4()), 'request_id': str(uuid4()), 'stage': 'destination_filing', 'gap_key': G, 'question': 'Please provide a complete mock-binder-hub export covering destination filing for this study and site, or confirm no record exists.', 'would_settle': 'A filing record naming the exact version.', 'contact_id': None, **k}
    A.call('/cases/JRN-1/journey/collection', plan(), 409)  # no investigation yet
    run_id = uuid4(); sql("INSERT INTO runs(workspace_id,id,case_id,result,duration_seconds,model,decision,review_notes,reviewed_at,reviewer_id) VALUES(%s,%s,'JRN-1',%s,0,'test','approved','Earlier approved recommendation.',now(),%s)", W, run_id, Jsonb({'recommendation': {'status': 'supported', 'evidence_ids': ['KB-001']}, 'sources': [{'id': 'KB-001', 'version': 1, 'title': 'Upload checks'}]}), UID)
    A.call('/cases/JRN-1/journey/collection', plan(gap_key='no_record:processing'), 409)
    A.call('/cases/JRN-1/journey/collection', plan(contact_id=str(uuid4())), 422)
    B.call('/cases/JRN-1/journey/collection', plan(), 404)
    role('analyst'); A.call('/cases/JRN-1/journey/collection', plan(), 403); role('owner')
    A.call('/contacts', {'id': (cid := str(uuid4())), 'name': 'Binder hub support', 'category': 'sync', 'primary_contact': 'hub-support@sample.invalid', 'study_id': 'CT-204', 'site_id': 'SITE-104'})
    p1 = plan(contact_id=cid); item = A.call('/cases/JRN-1/journey/collection', p1, 201)
    assert A.call('/cases/JRN-1/journey/collection', p1, 201)['id'] == item['id'] and len(sql('SELECT 1 FROM journey_plan_items WHERE workspace_id=%s', W)) == 1
    A.call('/cases/JRN-1/journey/collection', {**p1, 'question': 'A changed question that should be refused.'}, 409)
    req = sql('SELECT * FROM information_requests WHERE workspace_id=%s AND id=%s', W, p1['request_id'])[0]
    assert req['status'] == 'draft' and str(req['contact_id']) == cid and req['items'] == [p1['question']] and not req['responses']
    dup = A.call('/cases/JRN-1/journey/collection', plan(contact_id=cid), 409)
    assert dup['detail']['matches'], dup
    ok = plan(contact_id=cid, duplicate_reason='Separate vendor contact needed for this stage.'); A.call('/cases/JRN-1/journey/collection', ok, 201)
    ev = events('JRN-1', 'journey_collection_drafted'); assert len(ev) == 2 and ev[0]['payload']['no_message_sent'] is True
    jj = A.call('/cases/JRN-1/journey'); assert len(jj['plan_items']) == 2 and jj['plan_items'][0]['request_status'] == 'draft'
    passed('collection draft reuses the existing request workflow: duplicate warning, contact validation, human contact choice, idempotency, nothing sent, no unreviewed response used')

    # ---- 6. expected outcomes: validation, revisions, optimistic concurrency, retire
    K1, K2 = str(uuid4()), str(uuid4())
    reqs = [{'stage': 'destination_filing', 'status': 'completed'}, {'stage': 'binder_visibility', 'status': 'visible'}]
    oc = lambda **k: {'id': str(uuid4()), 'key': K1, 'expected_rev': 0, 'description': 'The same document/version is filed and visible in the intended binder.', 'requirements': reqs, 'required': True, 'remediation_at': ago(3).isoformat(), **k}
    A.call('/cases/JRN-1/journey/outcomes', oc(remediation_at=None), 422)
    A.call('/cases/JRN-1/journey/outcomes', oc(remediation_at=(now + timedelta(days=1)).isoformat()), 422)
    A.call('/cases/JRN-1/journey/outcomes', oc(requirements=[{'stage': 'transfer', 'status': 'visible'}]), 422)
    A.call('/cases/JRN-1/journey/outcomes', oc(remediation_at=ago(3).replace(tzinfo=None).isoformat()), 422)
    B.call('/cases/JRN-1/journey/outcomes', oc(), 404)
    role('analyst'); A.call('/cases/JRN-1/journey/outcomes', oc(), 403); role('owner')
    o1 = oc(); r1o = A.call('/cases/JRN-1/journey/outcomes', o1, 201); assert A.call('/cases/JRN-1/journey/outcomes', o1, 201)['id'] == r1o['id']
    A.call('/cases/JRN-1/journey/outcomes', {**o1, 'description': 'Changed description for the same id.'}, 409)
    A.call('/cases/JRN-1/journey/outcomes', oc(expected_rev=0), 409)
    o2 = {'id': str(uuid4()), 'key': K2, 'expected_rev': 0, 'description': 'A reviewer confirms the certificate opens in the binder viewer.', 'requirements': None, 'required': True, 'remediation_at': None}
    A.call('/cases/JRN-1/journey/outcomes', o2, 201)
    assert [o['outcome_key'] for o in A.call('/cases/JRN-1/journey')['outcomes']] == [K1, K2] and len(events('JRN-1', 'journey_outcome_saved')) == 2
    passed('outcomes need a structured check with a remediation time or are human-only; revisions are append-only, idempotent and concurrency-checked')

    # ---- 7. verification: insufficient -> pre-remediation -> collision -> verified, never changing the case
    case_state = lambda: sql("SELECT status,resolution,updated_at FROM cases WHERE workspace_id=%s AND id='JRN-1'", W)[0]
    run_state = lambda: sql("SELECT decision,review_notes FROM runs WHERE workspace_id=%s AND case_id='JRN-1'", W)
    before_case, before_runs = case_state(), run_state()
    V = lambda **k: {'id': str(uuid4()), 'rationale': 'Checked after the sync fix was applied.', 'human': {}, **k}
    A.call('/cases/JRN-1/journey/verify', V(rationale='short'), 422)
    A.call('/cases/JRN-1/journey/verify', V(human={str(uuid4()): {'result': 'verified', 'rationale': 'Not an outcome of this case.'}}), 422)
    B.call('/cases/JRN-1/journey/verify', V(), 404)
    role('analyst'); A.call('/cases/JRN-1/journey/verify', V(), 403); role('owner')
    v1 = A.call('/cases/JRN-1/journey/verify', V(), 201)
    assert v1['overall'] == 'insufficient_evidence' and {r['method'] for r in v1['results']} == {'deterministic', 'needs_human_assessment'}
    pre = [{'kind': 'filing', 'job': {'id': 'FILE-OLD'}, 'item': {'upstream': 'DOC-5001', 'rev': '2'}, 'outcome': 'filed', 'when': ago(4).isoformat(), 'target': 'BND-77'},
           {'kind': 'visibility', 'job': {'id': 'VIS-OLD'}, 'item': {'upstream': 'DOC-5001', 'rev': '2'}, 'outcome': 'shown', 'when': ago(4).isoformat(), 'target': 'BND-77'}]
    imp(A, 'hub', 'H2', ago(4), pre)
    v2 = A.call('/cases/JRN-1/journey/verify', V(), 201)  # same ID text in the hub, no mapping yet: collision, and pre-remediation anyway
    assert v2['overall'] == 'insufficient_evidence'
    st = {s['stage']: s for s in A.call('/cases/JRN-1/journey')['journey']['stages']}
    assert st['destination_filing']['assessment'] == 'unknown' and st['destination_filing']['candidates'][0]['problems'] == ['id_collision']
    DL = str(uuid4()); A.call('/cases/JRN-1/journey/links', {'id': DL, 'kind': 'document', 'from_system': HUB, 'from_ref': 'DOC-5001', 'rationale': 'Hub document DOC-5001 is the portal document per the hub admin record.', 'evidence': 'Hub admin record #44'}, 201)
    v3 = A.call('/cases/JRN-1/journey/verify', V(), 201)
    assert v3['overall'] == 'insufficient_evidence'
    first = [r for r in v3['results'] if r['method'] == 'deterministic'][0]
    assert first['result'] == 'insufficient' and first['parts'][0]['before'] and not first['parts'][0]['after'], first
    post = [{**pre[0], 'job': {'id': 'FILE-NEW'}, 'when': ago(1).isoformat()}, {**pre[1], 'job': {'id': 'VIS-NEW'}, 'when': ago(1).isoformat()}]
    imp(A, 'hub', 'H3', ago(1), post)
    o2id = [o['id'] for o in A.call('/cases/JRN-1/journey')['outcomes'] if not o['requirements']][0]
    v4 = A.call('/cases/JRN-1/journey/verify', V(), 201)
    assert v4['overall'] == 'partially_verified' and [r['result'] for r in v4['results']] == ['verified', 'insufficient'], v4['results']
    hv = {'human': {o2id: {'result': 'verified', 'rationale': 'Opened the certificate in the binder viewer.'}}}
    vid = str(uuid4()); v5 = A.call('/cases/JRN-1/journey/verify', V(id=vid, **hv), 201)
    assert v5['overall'] == 'verified' and v5['results'][1]['method'] == 'human'
    assert A.call('/cases/JRN-1/journey/verify', V(id=vid, **hv), 201)['id'] == vid
    A.call('/cases/JRN-1/journey/verify', V(id=vid, rationale='Different rationale text here.', **hv), 409)
    assert case_state() == before_case and run_state() == before_runs and case_state()['status'] == 'open'
    assert not events('JRN-1', 'case_resolved') and not events('JRN-1', 'run_decision')
    passed('verification: insufficient without evidence; collision/pre-remediation evidence never verifies; mapped later exact evidence verifies; human outcome labelled; case/approval untouched')

    # ---- 8. contradiction, wrong version/binder, history immutability, outcome changes
    rows_before = {str(r['id']): json.dumps(r['results'], sort_keys=True, default=str) for r in sql('SELECT id,results FROM journey_verifications WHERE workspace_id=%s', W)}
    cur = A.call('/cases/JRN-1/journey')
    assert cur['verifications'][0]['id'] == vid and cur['verifications'][0]['current'] is True and all(not v['current'] for v in cur['verifications'][1:])
    bad = [{**post[1], 'job': {'id': 'VIS-BAD'}, 'outcome': 'hidden', 'when': ago(0.5).isoformat()}]
    imp(A, 'hub', 'H4', ago(0.5), bad)
    cur = A.call('/cases/JRN-1/journey'); assert not cur['verifications'][0]['current'], 'new relevant evidence must make the earlier verification historical'
    v6 = A.call('/cases/JRN-1/journey/verify', V(**hv), 201)
    assert v6['overall'] == 'not_verified' and v6['results'][0]['result'] == 'contradicted', v6['results']
    wrong = [{**post[0], 'job': {'id': 'FILE-V1'}, 'item': {'upstream': 'DOC-5001', 'rev': '1'}, 'when': ago(0.4).isoformat()}]
    imp(A, 'hub', 'H5', ago(0.4), wrong)
    st = {s['stage']: s for s in A.call('/cases/JRN-1/journey')['journey']['stages']}
    assert any(c['problems'] == ['wrong_version'] for c in st['destination_filing']['candidates'])
    wb = [{**post[0], 'job': {'id': 'FILE-B9'}, 'target': 'BND-99', 'when': ago(0.3).isoformat()}]
    imp(A, 'hub', 'H6', ago(0.3), wb)
    st = {s['stage']: s for s in A.call('/cases/JRN-1/journey')['journey']['stages']}
    assert any(c['problems'] == ['wrong_destination'] for c in st['destination_filing']['candidates'])
    A.call('/cases/JRN-1/journey/outcomes', oc(id=str(uuid4()), expected_rev=1, description='The same document/version is filed in the intended binder.', requirements=reqs[:1]), 201)
    jn = A.call('/cases/JRN-1/journey'); assert [o['rev'] for o in jn['outcomes'] if o['outcome_key'] == K1] == [2] and len(jn['outcome_history']) == 3
    assert all(not v['current'] for v in jn['verifications'])
    after = {str(r['id']): json.dumps(r['results'], sort_keys=True, default=str) for r in sql('SELECT id,results FROM journey_verifications WHERE workspace_id=%s', W)}
    assert all(after[k] == v for k, v in rows_before.items()), 'saved verifications must be immutable'
    retire = oc(id=str(uuid4()), key=K2, expected_rev=1, description=o2['description'], requirements=None, remediation_at=None, retired=True); A.call('/cases/JRN-1/journey/outcomes', retire, 201)
    assert [o['outcome_key'] for o in A.call('/cases/JRN-1/journey')['outcomes']] == [K1]
    passed('contrary exact evidence contradicts (not verified); wrong version/binder excluded; new evidence or outcome revisions make earlier verifications historical without rewriting them')

    # ---- 9. decision replay
    role('analyst'); A.call('/cases/JRN-1/journey/replay', expected=403); assert A.call('/cases/JRN-1/journey')['verifications'] == []; role('owner')
    B.call('/cases/JRN-1/journey/replay', expected=404)
    rp = A.call('/cases/JRN-1/journey/replay')['decisions']
    byid = {d['id']: d for d in rp}
    d5 = byid[v5['id']]
    assert d5['complete'] and d5['rationale'] == v5['rationale'] and d5['decision'] == 'verified' and d5['inputs']['human_assessments'][o2id]['rationale'].startswith('Opened')
    assert d5['changed_since']['exports'] and d5['changed_since']['outcome_revisions'] and not d5['changed_since']['same_evidence_as_now'] and d5['changed_since']['stages'], d5['changed_since']
    assert {x['stage'] for x in d5['known']} >= {'destination_filing', 'binder_visibility'}
    run_d = byid[str(run_id)]
    assert run_d['complete'] is False and 'not reconstructed' in run_d['incomplete_reason'] and run_d['inputs']['cited_procedures'][0]['version'] == 1
    passed('replay shows frozen inputs, rationale, unknowns and later changes; older decisions are marked incomplete, not reconstructed; reviewer-only')

    # ---- 10. exports
    pkg = A.call('/cases/JRN-1/package.json')
    for k in ('journey', 'journey_summary', 'journey_subjects', 'journey_links', 'journey_assessments', 'journey_plan_items', 'journey_outcomes', 'journey_verifications'):
        assert pkg[k], k
    assert len(pkg['journey_outcomes']) == 4 and len(pkg['journey_verifications']) >= 5 and pkg['journey_plan_items'][0]['request_id']
    assert raw(A, '/cases/JRN-1/package.pdf')[:5] == b'%PDF-' and len(raw(A, '/cases/JRN-1/package.pdf')) > 2000
    role('analyst'); ap = A.call('/cases/JRN-1/package.json'); assert ap['journey_verifications'] == [] and ap['journey_assessments'] == [] and ap['journey_summary']; role('owner')
    B.call('/cases/JRN-1/package.json', expected=404)
    passed('case JSON/PDF include journey assessments, plan references, outcome revisions and verification history under existing role boundaries')
    print(f'PASS: {n} journey integration groups. Temporary records removed in finally.', flush=True)
finally:
    with connect() as c:
        for w in workspaces: c.execute('DELETE FROM workspaces WHERE id=%s', (w,))
        c.execute("DELETE FROM users WHERE guest AND NOT EXISTS(SELECT 1 FROM memberships m WHERE m.user_id=users.id)")
