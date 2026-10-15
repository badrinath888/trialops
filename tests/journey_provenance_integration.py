"""Reviewed-response attestations, adoption of existing confirmed snapshot links, conflicting/stale links, permissions, immutability.
TEST stack only; fresh expiring demo workspaces removed in finally. Run in the test API container: python /app/tests/journey_provenance_integration.py"""
import sys, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/api'))
from integration import Client
from db import connect
from psycopg.types.json import Jsonb
from journey import example_export
from assessments import context, config

A, B = Client(), Client()
n = 0
def passed(s):
    global n; n += 1; print('PASS:', s, flush=True)
def sql(q, *p):
    with connect() as c:
        cur = c.execute(q, p)
        return cur.fetchall() if cur.description else None
def role(r): sql('UPDATE memberships SET role=%s WHERE workspace_id=%s AND user_id=%s', r, W, UID)
now = datetime.now(timezone.utc).replace(microsecond=0)
ago = lambda h: now - timedelta(hours=h)
PORTAL, HUB = 'mock-upload-portal', 'mock-binder-hub'
workspaces = []
try:
    W = A.call('/auth/demo', {})['workspace_id']; workspaces.append(W); WB = B.call('/auth/demo', {})['workspace_id']; workspaces.append(WB)
    UID = A.call('/auth/me')['user_id']
    for w, cid in ((W, 'JRN-P'), (WB, 'JRN-OTHER')):
        sql("INSERT INTO cases(workspace_id,id,study_id,site_id,title,description,category,priority,status) VALUES(%s,'"+cid+"','CT-204','SITE-104','Journey provenance','Synthetic.','document_workflow','medium','open')", w)
    run_id = uuid4(); sql("INSERT INTO runs(workspace_id,id,case_id,result,duration_seconds,model) VALUES(%s,%s,'JRN-P',%s,0,'test')", W, run_id, Jsonb({'recommendation': {'status': 'supported', 'evidence_ids': []}, 'sources': []}))
    req_id = uuid4(); sql("INSERT INTO information_requests(workspace_id,id,case_id,run_id,title,items,status,responses) VALUES(%s,%s,'JRN-P',%s,'Ask hub','[\"Which job?\"]','requested',%s)", W, req_id, run_id,
                          Jsonb([{'text': 'Internal note: hub says filing completed.', 'actor_name': 'Sample visitor', 'recorded_at': ago(0.5).isoformat(), 'evidence_refs': []}]))
    def ext(status):
        lid, rid = uuid4(), uuid4()
        sql("INSERT INTO external_response_links(workspace_id,id,case_id,request_id,token_hash,question,expires_at) VALUES(%s,%s,'JRN-P',%s,%s,'{}',now()+interval '1 day')", W, lid, req_id, uuid4().hex)
        sql("INSERT INTO external_responses(workspace_id,id,case_id,request_id,link_id,submission_id,text,status,reviewer_name,reviewed_at,submitted_at) VALUES(%s,%s,'JRN-P',%s,%s,%s,'The hub says the filing completed in BND-77 for DOC-5001.',%s,%s,%s,%s)",
            W, rid, req_id, lid, uuid4(), status, 'Sample visitor' if status == 'accepted' else None, now if status == 'accepted' else None, ago(0.5))
        return rid
    pending, accepted = ext('pending'), ext('accepted')

    def imp(client, shape, ref, at, rows=None):
        ex = example_export(shape, 'CT-204', 'SITE-104', ref=ref, observed_at=at, rows=rows)
        return client.call('/operations/journey-import', {'export': ex['export'], 'mapping': ex['mapping']}, 201)
    subj = {'id': str(uuid4()), 'expected_rev': 0, 'document_system': PORTAL, 'document_ref': 'DOC-5001', 'document_version': '2', 'destination_system': HUB, 'binder_ref': 'BND-77'}
    A.call('/cases/JRN-P/journey/subject', subj)
    imp(A, 'portal', 'P1', ago(6), [{'event': 'RECEIPT', 'receipt_no': 'RCPT-5001', 'doc_id': 'DOC-5001', 'doc_rev': '2', 'state': 'RECEIVED', 'at': ago(6).isoformat()}])
    imp(A, 'hub', 'H1', ago(5), [{'kind': 'sync_job', 'job': {'id': 'JOB-7001'}, 'item': {}, 'outcome': 'failed', 'when': ago(5).isoformat(), 'target': 'BND-77'},
                                 {'kind': 'sync_job', 'job': {'id': 'JOB-7002'}, 'item': {}, 'outcome': 'ok', 'when': ago(5).isoformat(), 'target': 'BND-77'}])
    imp(A, 'hub', 'H2', ago(2), [{'kind': 'visibility', 'job': {'id': 'VIS-A'}, 'item': {'upstream': 'DOC-5001', 'rev': '2'}, 'outcome': 'shown', 'when': ago(2).isoformat(), 'target': 'BND-77'}])  # hub record naming DOC-5001 (unmapped until linked)
    stages = lambda: {s['stage']: s for s in A.call('/cases/JRN-P/journey')['journey']['stages']}

    # ---- 1. reviewed responses: unreviewed excluded; reviewed ones are attested context only
    att = lambda **k: {'id': str(uuid4()), 'response_ref': 'external:' + str(accepted), 'stage': 'destination_filing', 'source_system': HUB, 'source_ref': 'FILE-A', 'document_ref': 'DOC-5001', 'version': '2', 'binder_ref': 'BND-77',
                       'transfer_ref': None, 'status': 'completed', 'observed_at': ago(1).isoformat(), 'rationale': 'Reviewer transcribed the identifiers the hub reported.', **k}
    A.call('/cases/JRN-P/journey/attestations', att(response_ref='external:' + str(pending)), 422)
    A.call('/cases/JRN-P/journey/attestations', att(response_ref='external:' + str(uuid4())), 404)
    A.call('/cases/JRN-P/journey/attestations', att(response_ref='nonsense'), 422)
    A.call('/cases/JRN-P/journey/attestations', att(observed_at=(now + timedelta(hours=1)).isoformat()), 422)  # later than the response that reports it
    A.call('/cases/JRN-P/journey/attestations', att(status='visible'), 422)
    A.call('/cases/JRN-P/journey/attestations', att(document_ref='DOC 5001 filed'), 422)
    A.call('/cases/JRN-P/journey/attestations', att(observed_at=ago(1).replace(tzinfo=None).isoformat()), 422)
    B.call('/cases/JRN-P/journey/attestations', att(), 404)
    role('analyst'); A.call('/cases/JRN-P/journey/attestations', att(), 403); role('owner')
    a1 = att(); r = A.call('/cases/JRN-P/journey/attestations', a1, 201)
    assert A.call('/cases/JRN-P/journey/attestations', a1, 201)['id'] == r['id'] and len(sql('SELECT 1 FROM journey_attestations WHERE workspace_id=%s', W)) == 1
    A.call('/cases/JRN-P/journey/attestations', {**a1, 'rationale': 'A different rationale for the same id.'}, 409)
    assert r['response_reviewer'] == 'Sample visitor' and r['response_reviewed_at'] and r['response_submitted_at'] and r['actor_name'] == 'Sample visitor'
    ir = att(response_ref=f'request:{req_id}:0', source_ref='FILE-B'); A.call('/cases/JRN-P/journey/attestations', ir, 201)
    A.call('/cases/JRN-P/journey/attestations', att(response_ref=f'request:{req_id}:9'), 404)
    link = lambda **k: {'id': str(uuid4()), 'kind': 'document', 'from_system': HUB, 'from_ref': 'DOC-5001', 'rationale': 'Hub admin record names this portal document.', 'evidence': 'Hub admin record 44', **k}
    A.call('/cases/JRN-P/journey/links', link(), 201)
    st = stages()['destination_filing']
    assert st['assessment'] == 'unknown' and st['operational_status'] is None and len(st['attested']) == 2 and 'no system record supports it' in ' '.join(st['missing']), st
    assert st['attested'][0]['raw']['response_reviewer'] == 'Sample visitor' and st['attested'][0]['attested_by'] == 'Sample visitor'
    O = {'id': str(uuid4()), 'key': str(uuid4()), 'expected_rev': 0, 'description': 'The same document/version is filed in the intended binder.', 'requirements': [{'stage': 'destination_filing', 'status': 'completed'}], 'required': True, 'remediation_at': ago(3).isoformat()}
    A.call('/cases/JRN-P/journey/outcomes', O, 201)
    v = A.call('/cases/JRN-P/journey/verify', {'id': str(uuid4()), 'rationale': 'Checked with attested response only.', 'human': {}}, 201)
    assert v['overall'] == 'insufficient_evidence', 'a reviewed response must not verify an outcome'
    pkg = A.call('/cases/JRN-P/package.json'); assert len(pkg['journey_attestations']) == 2
    role('analyst'); assert A.call('/cases/JRN-P/package.json')['journey_attestations'] == [] and A.call('/cases/JRN-P/journey')['responses'] == []; role('owner')
    passed('unreviewed/foreign/malformed/future/free-text responses rejected; reviewed responses are stored with provenance, reviewer and dates but stay attested context: stage unknown, outcome insufficient')

    # ---- 2. existing confirmed (snapshot-only) linkage: listed separately, adopted explicitly, validated
    def confirmed(exact, w=None, stale=False, case='JRN-P'):
        w = w or W
        actor = {'workspace_id': w, 'user_id': UID, 'name': 'Sample visitor', 'role': 'owner'}
        with connect() as c: _, h, _ = context(c, actor, case)
        aid, did = uuid4(), uuid4()
        sql("INSERT INTO case_assessments(workspace_id,id,case_id,kind,actor_id,input,context_hash,configuration,frozen_evidence,result,finished_at) VALUES(%s,%s,%s,'linkage',%s,'{}',%s,%s,'{}','{}',now())", w, aid, case, UID, 'stale' if stale else h, Jsonb(config('linkage')))
        sql("INSERT INTO assessment_decisions(workspace_id,id,assessment_id,case_id,actor_id,actor_name,action,target,reason,details) VALUES(%s,%s,%s,%s,%s,'Sample visitor','confirm_link','c1','Exact IDs confirmed by reviewer.',%s)", w, did, aid, case, UID, Jsonb({'candidate': {'left_id': 'snapshot:S:document_processing:P1', 'right_id': 'snapshot:S:synchronization:SY1', 'exact_matches': exact}, 'not_root_cause': True}))
        return str(did)
    d_ok = confirmed([{'field': 'document_id', 'left': 'DOC-5001', 'right': 'DOC-5001'}, {'field': 'job_id', 'left': 'JOB-7001', 'right': 'JOB-7001'}])
    d_other = confirmed([{'field': 'document_id', 'left': 'DOC-9999', 'right': 'DOC-9999'}, {'field': 'job_id', 'left': 'JOB-7002', 'right': 'JOB-7002'}])
    d_nodoc = confirmed([{'field': 'job_id', 'left': 'JOB-7002', 'right': 'JOB-7002'}])
    d_foreign = confirmed([{'field': 'document_id', 'left': 'DOC-5001', 'right': 'DOC-5001'}], w=WB, case='JRN-OTHER')
    before = sql('SELECT details,reason FROM assessment_decisions WHERE workspace_id=%s', W)
    g = A.call('/cases/JRN-P/journey')
    assert {x['id'] for x in g['snapshot_links']} == {d_ok, d_other, d_nodoc} and all('saved snapshots only' in x['applies_to'] for x in g['snapshot_links'])
    assert all(l.get('snapshot_decision_id') is None for l in g['links']) and g['journey']['stages'][2]['assessment'] == 'unknown'  # nothing was mapped by existing links alone
    A.call('/cases/JRN-P/journey/links', link(kind='record', from_ref='JOB-7001', snapshot_decision_id=d_other), 422)   # job not in that link's matches... and it names another document
    A.call('/cases/JRN-P/journey/links', link(kind='record', from_ref='JOB-7002', snapshot_decision_id=d_other), 422)   # confirmed link concerns DOC-9999
    A.call('/cases/JRN-P/journey/links', link(kind='record', from_ref='JOB-7002', snapshot_decision_id=d_nodoc), 422)    # no document or recorded receipt named
    A.call('/cases/JRN-P/journey/links', link(kind='record', from_ref='JOB-7002', snapshot_decision_id=d_ok), 422)       # identifier is not one of the confirmed exact matches
    A.call('/cases/JRN-P/journey/links', link(kind='record', from_ref='JOB-7001', snapshot_decision_id=d_foreign), 422)  # other workspace's decision
    A.call('/cases/JRN-P/journey/links', link(kind='record', from_ref='JOB-7001', snapshot_decision_id=str(uuid4())), 422)
    A.call('/cases/JRN-P/journey/links', link(kind='destination', from_ref='BND-77', from_system=HUB, snapshot_decision_id=d_ok), 422)
    role('analyst'); A.call('/cases/JRN-P/journey/links', link(kind='record', from_ref='JOB-7001', snapshot_decision_id=d_ok), 403); assert A.call('/cases/JRN-P/journey')['snapshot_links'] == []; role('owner')
    B.call('/cases/JRN-P/journey/links', link(kind='record', from_ref='JOB-7001', snapshot_decision_id=d_ok), 404)
    adopt = link(kind='record', from_ref='JOB-7001', snapshot_decision_id=d_ok, rationale='Adopting the reviewer-confirmed job/document link for this journey.'); row = A.call('/cases/JRN-P/journey/links', adopt, 201)
    assert row['snapshot_decision_id'] == d_ok and A.call('/cases/JRN-P/journey/links', adopt, 201)['id'] == row['id']
    t = stages()['transfer']; assert (t['assessment'], t['operational_status']) == ('verified', 'failed'), t
    assert t['records'][0]['link']['rationale'].startswith('Adopting')
    A.call('/cases/JRN-P/journey/links', link(kind='record', from_ref='JOB-7001', snapshot_decision_id=d_ok), 409)  # conflicting/duplicate active link for the same source identifier
    assert sql('SELECT details,reason FROM assessment_decisions WHERE workspace_id=%s', W) == before, 'existing confirmed decisions must be untouched'
    passed('existing confirmed links stay snapshot-only until a reviewer adopts them; document/identifier/workspace/stale checks, duplicate-link conflict, roles and untouched history verified')

    # ---- 3. changed evidence: stale confirmed link is refused; revision of the definition stops old links applying
    sql("INSERT INTO case_evidence(workspace_id,id,case_id,kind,reference_id,summary,observed_at,actor_name) VALUES(%s,%s,'JRN-P','human_observation','OBS-9','Changes the assessment context',now(),'Test')", W, uuid4())
    A.call('/cases/JRN-P/journey/links', link(kind='record', from_ref='JOB-7002', from_system=HUB, snapshot_decision_id=d_ok, id=str(uuid4())), 409)
    assert all(x['stale'] for x in A.call('/cases/JRN-P/journey')['snapshot_links'])
    s2 = {**subj, 'id': str(uuid4()), 'expected_rev': 1, 'document_ref': 'DOC-6001'}; A.call('/cases/JRN-P/journey/subject', s2)
    g = A.call('/cases/JRN-P/journey'); assert all(not l['applies_to_current_definition'] for l in g['links']) and {s['stage']: s for s in g['journey']['stages']}['transfer']['assessment'] == 'unknown'
    assert len(sql('SELECT 1 FROM journey_links WHERE workspace_id=%s', W)) == 2 and len(sql('SELECT 1 FROM journey_subjects WHERE workspace_id=%s', W)) == 2
    passed('stale confirmed evidence refused (409); after the definition changes old links no longer apply but remain in history')
    print(f'PASS: {n} journey provenance groups. Temporary records removed in finally.', flush=True)
finally:
    with connect() as c:
        for w in workspaces: c.execute('DELETE FROM workspaces WHERE id=%s', (w,))
        c.execute("DELETE FROM users WHERE guest AND NOT EXISTS(SELECT 1 FROM memberships m WHERE m.user_id=users.id)")
