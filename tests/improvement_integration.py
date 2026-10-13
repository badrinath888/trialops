"""Recurrence/prevention, bulk actions, readiness, procedure impact and feedback queue against the running TEST stack.
Only fresh expiring demo workspaces (and rows inside them) are created and removed in finally.
Run inside the test API container: python /app/tests/improvement_integration.py"""
import json, sys, copy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/api'))
from integration import Client
from db import connect
from psycopg.types.json import Jsonb

A, B = Client(), Client()
n = 0
def passed(s):
    global n; n += 1; print('PASS:', s, flush=True)
def sql(q, *p):
    with connect() as c:
        cur = c.execute(q, p)
        return cur.fetchall() if cur.description else None
def iso(d): return d.isoformat()
def new_case(cid, category='document_workflow', site='SITE-104', status='open', created=None, w=None):
    sql("INSERT INTO cases(workspace_id,id,study_id,site_id,title,description,category,priority,status,created_at,resolution) VALUES(%s,%s,'CT-204',%s,%s,'Synthetic recurring upload receipt gap for testing.',%s,'medium',%s,%s,%s)",
        w or W, cid, site, 'Receipt gap ' + cid, category, status, created or datetime.now(timezone.utc), 'done' if status == 'resolved' else None)
def role(r, uid=None): sql('UPDATE memberships SET role=%s WHERE workspace_id=%s AND user_id=%s', r, W, uid or UID)
def events(cid, kind): return sql('SELECT * FROM case_events WHERE workspace_id=%s AND case_id=%s AND event_type=%s', W, cid, kind)

workspaces = []
try:
    W = A.call('/auth/demo', {})['workspace_id']; workspaces.append(W); WB = B.call('/auth/demo', {})['workspace_id']; workspaces.append(WB)
    UID = A.call('/auth/me')['user_id']; UB = B.call('/auth/me')['user_id']
    peer = uuid4(); sql("INSERT INTO users(id,email,name,guest) VALUES(%s,%s,'Peer reviewer',true)", peer, f'{peer}@sample.invalid'); sql("INSERT INTO memberships(workspace_id,user_id,role) VALUES(%s,%s,'reviewer')", W, peer)
    outsider = uuid4(); sql("INSERT INTO users(id,email,name,guest) VALUES(%s,%s,'Outsider',true)", outsider, f'{outsider}@sample.invalid')
    A.call('/assessment-demo', {'stage': 'start'})
    now = datetime.now(timezone.utc)
    sql("INSERT INTO sites(workspace_id,id,study_id,name) VALUES(%s,'SITE-101','CT-204','Second site')", W)
    for i in range(1, 4): new_case(f'REC-{i}', created=now - timedelta(days=i))
    new_case('REC-OTHERSITE', site='SITE-101'); new_case('REC-OTHERCAT', category='access'); new_case('REC-RESOLVED', status='resolved')

    # ---- 1. recurrence: structured suggestions only, human confirmation, scope, history
    s = A.call('/recurrence/suggestions?case_id=REC-1')
    ids = {c['id'] for c in s['candidates']}
    assert {'REC-2', 'REC-3', 'REC-RESOLVED'} <= ids and not ids & {'REC-OTHERSITE', 'REC-OTHERCAT'}, ids
    assert 'neither recurrence nor a shared root cause is established until a reviewer confirms' in s['interpretation'] and s['groups'] == []
    passed('suggestions come from category/study/site (and explicit links) only; similar text in another category/site is not suggested')
    G = str(uuid4()); body = {'id': G, 'title': 'Receipt gaps at SITE-104', 'case_ids': ['REC-1', 'REC-2', 'REC-3'], 'basis': 'category_study_site', 'site_scope': 'site', 'pattern': 'Three document uploads lacked receipts after the sync window.'}
    B.call('/recurrence/groups', {**body, 'id': str(uuid4())}, 422)
    A.call('/recurrence/groups', {**body, 'id': str(uuid4()), 'pattern': 'too short'}, 422)
    A.call('/recurrence/groups', {**body, 'id': str(uuid4()), 'case_ids': ['REC-1', 'REC-OTHERCAT']}, 422)
    A.call('/recurrence/groups', {**body, 'id': str(uuid4()), 'case_ids': ['REC-1', 'REC-OTHERSITE']}, 422)
    role('analyst'); A.call('/recurrence/groups', body, 403); role('owner')
    g = A.call('/recurrence/groups', body, 201)
    assert A.call('/recurrence/groups', body, 201)['group']['id'] == G and len(sql('SELECT 1 FROM recurrence_groups WHERE workspace_id=%s', W)) == 1
    A.call('/recurrence/groups', {**body, 'pattern': 'A different explanation of the pattern here.'}, 409)
    assert len(events('REC-1', 'recurrence_membership_confirmed')) == 1 and events('REC-1', 'recurrence_membership_confirmed')[0]['payload']['recurrence_or_root_cause_established'] is False
    B.call(f'/recurrence/groups/{G}', expected=404)
    passed('reviewer confirms membership with an explained pattern; scope/role/idempotency/workspace isolation enforced; audit never claims root cause')
    v = g['group']['version']
    A.call(f'/recurrence/groups/{G}/members', {'expected_version': v + 5, 'add': []}, 409)
    A.call(f'/recurrence/groups/{G}/members', {'expected_version': v, 'remove': [{'case_id': 'REC-3', 'reason': 'no'}]}, 422)
    r = A.call(f'/recurrence/groups/{G}/members', {'expected_version': v, 'remove': [{'case_id': 'REC-3', 'reason': 'Different cause on review'}], 'add': ['REC-RESOLVED']})
    assert sum(1 for m in r['members'] if m['removed_at']) == 1 and len(r['members']) == 4 and r['group']['version'] == v + 1
    A.call(f'/recurrence/groups/{G}/members', {'expected_version': v, 'add': []}, 409)
    A.call(f'/recurrence/groups/{G}/members', {'expected_version': v + 1, 'remove': [{'case_id': 'REC-1', 'reason': 'Testing the floor'}, {'case_id': 'REC-2', 'reason': 'Testing the floor'}]}, 422)
    assert any(e['kind'] == 'membership_changed' for e in A.call(f'/recurrence/groups/{G}')['events']) and events('REC-3', 'recurrence_membership_removed')
    passed('membership changes keep removed members with reasons, history and audit; stale edits rejected; group keeps at least two cases')

    # ---- 2. prevention plans
    P = str(uuid4()); A.call(f'/recurrence/groups/{G}/plans', {'id': P, 'title': 'Receipt prevention', 'summary': 'Check receipts nightly.'}, 201)
    A.call(f'/recurrence/groups/{G}/plans', {'id': P, 'title': 'Receipt prevention', 'summary': 'Check receipts nightly.'}, 201)
    assert len(sql('SELECT 1 FROM prevention_plans WHERE workspace_id=%s', W)) == 1
    sql("INSERT INTO case_evidence(workspace_id,id,case_id,kind,reference_id,summary,observed_at,actor_name) VALUES(%s,%s,'REC-1','human_observation','OBS-1','Receipt absent on 2026-10-01',now(),'Test')", W, (eid := uuid4()))
    act = lambda **k: {'id': str(uuid4()), 'text': 'Add nightly receipt reconciliation', 'owner_id': str(UID), 'due_at': iso(now + timedelta(days=14)), 'evidence': [{'case_id': 'REC-1', 'evidence_id': str(eid), 'note': 'observation'}], 'done': False, **k}
    plan = lambda v, actions, status='draft', **k: {'expected_version': v, 'title': 'Receipt prevention', 'summary': 'Check receipts nightly.', 'actions': actions, 'status': status, 'completion_note': '', **k}
    A.call(f'/prevention-plans/{P}', plan(1, [act(owner_id=str(outsider))], 'draft'), 422)
    A.call(f'/prevention-plans/{P}', plan(1, [act(evidence=[{'case_id': 'REC-OTHERSITE'}])], 'draft'), 422)
    A.call(f'/prevention-plans/{P}', plan(1, [act(evidence=[])], 'active'), 422)
    A.call(f'/prevention-plans/{P}', plan(1, [], 'active'), 422)
    a1 = act(); d = A.call(f'/prevention-plans/{P}', plan(1, [a1], 'draft'))
    A.call(f'/prevention-plans/{P}', plan(1, [a1], 'active'), 409)
    role('analyst'); A.call(f'/prevention-plans/{P}', plan(2, [a1], 'active'), 403); role('owner')
    d = A.call(f'/prevention-plans/{P}', plan(2, [a1, act(text='Alert owners when receipts are missing', owner_id=str(peer))], 'active'))
    pl = d['plans'][0]; assert pl['status'] == 'active' and len(pl['actions']) == 2 and pl['version'] == 3
    A.call(f'/prevention-plans/{P}', plan(3, [a1], 'draft'), 422)
    A.call(f'/prevention-plans/{P}', plan(3, [{**a1, 'done': True}], 'completed', completion_note='short'), 422)
    d = A.call(f'/prevention-plans/{P}', plan(3, [{**a1, 'done': True}], 'completed', completion_note='Reconciliation added and verified by the owner.'))
    assert d['plans'][0]['status'] == 'completed' and len(d['plans'][0]['actions']) == 1
    A.call(f'/prevention-plans/{P}', plan(4, [a1], 'completed'), 409)
    removed = sql('SELECT removed FROM prevention_actions WHERE workspace_id=%s AND plan_id=%s AND removed', W, P)
    kinds = [e['kind'] for e in d['events'] if e['kind'].startswith('plan_')]
    assert len(removed) == 1 and kinds == ['plan_created', 'plan_revised', 'plan_active', 'plan_completed'], kinds
    assert all('actions' in e['payload'] for e in d['events'] if e['kind'] in ('plan_revised', 'plan_active', 'plan_completed')) and events('REC-1', 'prevention_plan_revised')
    passed('plans need member owners, deadlines and group evidence to activate; stale/backward/completed edits rejected; revisions, removed actions and audit preserved')

    # ---- 3. measurement limits
    def win(label, role_, start, end, **k): return A.call(f'/recurrence/groups/{G}/windows', {'id': str(uuid4()), 'label': label, 'role': role_, 'start_at': iso(start), 'end_at': iso(end), **k}, 201)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    win('Baseline', 'baseline', t0, t0 + timedelta(days=30))
    A.call(f'/recurrence/groups/{G}/windows', {'id': str(uuid4()), 'label': 'Overlap', 'role': 'follow_up', 'start_at': iso(t0 + timedelta(days=10)), 'end_at': iso(t0 + timedelta(days=40))}, 422)
    A.call(f'/recurrence/groups/{G}/windows', {'id': str(uuid4()), 'label': 'Half exposure', 'role': 'follow_up', 'start_at': iso(t0 + timedelta(days=31)), 'end_at': iso(t0 + timedelta(days=61)), 'exposure_count': 5}, 422)
    d = win('Follow-up short', 'follow_up', t0 + timedelta(days=31), t0 + timedelta(days=51))
    c = d['comparison']; assert c['can_compare'] is False and len(c['reasons']) >= 3 and 'unequal' in ' '.join(c['reasons']) and 'missing' in ' '.join(c['reasons']) and 'Baseline has 0' in ' '.join(c['reasons']) and 'baseline_rate_per_unit' not in c
    for i in range(6): new_case(f'BASE-{i}', created=t0 + timedelta(days=2 + i))
    for i in range(2): new_case(f'FOLLOW-{i}', created=t0 + timedelta(days=33 + i))
    d = A.call(f'/recurrence/groups/{G}'); assert d['windows'][0]['matching_cases'] == 6 and d['comparison']['can_compare'] is False
    sql("DELETE FROM recurrence_windows WHERE workspace_id=%s AND label='Follow-up short'", W)
    win('Baseline2', 'baseline', t0 + timedelta(days=-60), t0 + timedelta(days=-30), exposure_count=100, exposure_unit='visits')
    sql("DELETE FROM recurrence_windows WHERE workspace_id=%s AND label='Baseline2'", W)
    sql('UPDATE recurrence_windows SET exposure_count=100,exposure_unit=%s WHERE workspace_id=%s', 'visits', W)
    d = win('Follow-up', 'follow_up', t0 + timedelta(days=31), t0 + timedelta(days=61), exposure_count=100, exposure_unit='visits')
    c = d['comparison']; assert c['can_compare'] and c['baseline_cases'] == 6 and c['follow_up_cases'] == 2 and 'Descriptive only' in c['note'] and 'percent' not in json.dumps(c).lower() and 'reduction' not in json.dumps(c).lower()
    sql("UPDATE recurrence_windows SET exposure_unit='documents' WHERE workspace_id=%s AND label='Follow-up'", W)
    assert A.call(f'/recurrence/groups/{G}')['comparison']['can_compare'] is False
    passed('windows must not overlap; comparison refused for unequal windows, missing/mismatched exposure or <5 baseline cases; when allowed it is descriptive with no percentage or causal claim')

    # ---- 4. bulk actions
    for i in range(1, 6): new_case(f'BULK-{i}')
    due = iso(now + timedelta(days=7)); rq = lambda **k: {'request_id': str(uuid4()), 'case_ids': ['BULK-1', 'BULK-2', 'BULK-3', 'REC-RESOLVED', 'NOPE-1'], 'set_owner': True, 'owner_id': str(peer), 'set_due': True, 'due_at': due, **k}
    pv = A.call('/cases/bulk/preview', rq())
    byid = {i['case_id']: i for i in pv['items']}
    assert byid['BULK-1']['ok'] and not byid['REC-RESOLVED']['ok'] and 'reopen' in byid['REC-RESOLVED']['reason'] and byid['NOPE-1']['reason'].startswith('Case not found') and pv['will_change'] == 3
    assert A.call('/cases/bulk/preview', rq(owner_id=str(outsider)))['items'][0]['reason'].startswith('Assignee')
    A.call('/cases/bulk/preview', rq(case_ids=[f'BULK-{i}' for i in range(1, 6)] * 6), 422)
    A.call('/cases/bulk/preview', rq(set_owner=False, set_due=False), 422)
    assert A.call('/cases/bulk/preview', rq(case_ids=['BULK-1']), 200)['items'][0]['ok']
    assert B.call('/cases/bulk/preview', rq(case_ids=['BULK-1']))['items'][0]['reason'].startswith('Case not found')
    role('analyst'); A.call('/cases/bulk/preview', rq(), 403); A.call('/cases/bulk/apply', rq(), 403); role('owner')
    req = rq(expected={i['case_id']: i['updated_at'] for i in pv['items'] if i['updated_at']})
    # concurrent edit between preview and apply: BULK-2 is reassigned by someone else
    sql('UPDATE cases SET owner_id=%s,updated_at=now() WHERE workspace_id=%s AND id=%s', UID, W, 'BULK-2')
    res = A.call('/cases/bulk/apply', req)
    st = {r['case_id']: r['status'] for r in res['results']}
    assert st == {'BULK-1': 'updated', 'BULK-2': 'stale', 'BULK-3': 'updated', 'REC-RESOLVED': 'failed', 'NOPE-1': 'failed'}, st
    assert sql('SELECT owner_id FROM cases WHERE workspace_id=%s AND id=%s', W, 'BULK-2')[0]['owner_id'] == __import__('uuid').UUID(UID)
    assert sql("SELECT status FROM cases WHERE workspace_id=%s AND id='REC-RESOLVED'", W)[0]['status'] == 'resolved'
    before = len(events('BULK-1', 'case_assignment_updated'))
    again = A.call('/cases/bulk/apply', req); assert again['results'] == res['results'] and len(events('BULK-1', 'case_assignment_updated')) == before == 1
    A.call('/cases/bulk/apply', {**req, 'owner_id': str(UID)}, 409)
    assert events('BULK-1', 'case_assignment_updated')[0]['payload']['bulk_batch'] == req['request_id']
    # partial progress is resumable: pre-seed a batch where BULK-4 is already done
    r2 = rq(case_ids=['BULK-4', 'BULK-5'], set_due=False, due_at=None); rq2 = {k: v for k, v in r2.items()}
    sql("INSERT INTO bulk_batches(workspace_id,id,actor_id,request,results) VALUES(%s,%s,%s,%s,%s)", W, r2['request_id'], UID, Jsonb({**{k: v for k, v in r2.items() if k not in ('expected',)}, 'case_ids': sorted(r2['case_ids'])}), Jsonb([{'case_id': 'BULK-4', 'status': 'updated', 'reason': None}]))
    out = A.call('/cases/bulk/apply', r2); assert [r['case_id'] for r in out['results']] == ['BULK-4', 'BULK-5'] and out['results'][1]['status'] == 'updated' and not events('BULK-4', 'case_assignment_updated')
    sql("INSERT INTO case_handovers(workspace_id,id,case_id,sender_id,recipient_id,reason,summary) VALUES(%s,%s,'BULK-3',%s,%s,'Testing handover guard',%s)", W, uuid4(), UID, peer, Jsonb({}))
    pv3 = A.call('/cases/bulk/preview', rq(case_ids=['BULK-3'], owner_id=str(UID)))
    assert not pv3['items'][0]['ok'] and 'handover' in pv3['items'][0]['reason']
    assert sql("SELECT count(*) AS n FROM cases WHERE workspace_id=%s AND id LIKE 'BULK-%%' AND status<>'open'", W)[0]['n'] == 0
    passed('bulk: preview validates scope/state/role/member/handover; partial failures reported per case; concurrent edit -> stale not overwritten; retry returns same results with one audit event; changed payload 409; resumable; never resolves/reopens')

    # ---- 5. readiness
    RQ = str(uuid4()); rb = lambda **k: {'id': RQ, 'study_id': 'CT-204', 'site_id': None, 'name': 'Delegation log', 'guidance': 'Signed and dated', 'requires_expiry': False, 'archived': False, 'expected_version': 0, **k}
    role('analyst'); A.call('/readiness/requirements', rb(), 403); role('owner')
    A.call('/readiness/requirements', rb(study_id='NOPE'), 422)
    A.call('/readiness/requirements', rb(site_id='SITE-DOES-NOT-EXIST'), 422)
    A.call('/readiness/requirements', rb())
    rows = A.call('/readiness?study_id=CT-204&site_id=SITE-104')['rows']; assert rows[0]['status'] == 'missing' and rows[0]['record'] is None
    assert B.call('/readiness?study_id=CT-204&site_id=SITE-104')['rows'] == []
    rec = lambda **k: {'requirement_id': RQ, 'site_id': 'SITE-104', 'applicable': True, 'applicability_reason': '', 'document_identity': 'DEL-LOG-001', 'document_version': '3', 'expiry_date': None, 'as_of': str(date.today()), 'evidence': [{'kind': 'note', 'ref': 'TMF 4.2.1', 'note': 'filed copy'}], 'expected_version': 0, **k}
    A.call('/readiness/records', rec(as_of=None), 422); A.call('/readiness/records', rec(as_of=str(date.today() + timedelta(days=2))), 422)
    A.call('/readiness/records', rec(applicable=False, document_identity=''), 422)
    A.call('/readiness/records', rec(evidence=[{'kind': 'case_evidence', 'ref': str(uuid4())}]), 422)
    r1 = A.call('/readiness/records', rec()); assert r1['review_status'] == 'awaiting_review' and r1['expiry_date'] is None
    assert A.call('/readiness?study_id=CT-204&site_id=SITE-104')['rows'][0]['status'] == 'awaiting_review'
    A.call('/readiness/records', rec(), 409)
    role('analyst'); A.call(f"/readiness/records/{r1['id']}/review", {'expected_version': 1}, 403); role('owner')
    rv = A.call(f"/readiness/records/{r1['id']}/review", {'expected_version': 1, 'note': 'Checked against TMF'}); assert rv['review_status'] == 'reviewed'
    row = A.call('/readiness?study_id=CT-204&site_id=SITE-104')['rows'][0]; assert row['status'] == 'reviewed' and 'not a current verification' in row['reason'] and 'compliance certification' in A.call('/readiness?study_id=CT-204')['interpretation']
    passed('readiness: missing -> awaiting review -> reviewed; reviews need evidence/identity/date; analyst cannot write; other workspace sees nothing; reviewed text says dated observation, not certification')
    A.call('/readiness/requirements', rb(name='Delegation log (current)', expected_version=1))
    row = A.call('/readiness?study_id=CT-204&site_id=SITE-104')['rows'][0]; assert row['status'] == 'awaiting_review' and row['stale'] and 'changed' in row['reason']
    A.call(f"/readiness/records/{r1['id']}/review", {'expected_version': 2}, 409)
    A.call('/readiness/requirements', rb(name='Delegation log (current)', expected_version=1), 409)
    r2_ = A.call('/readiness/records', rec(expected_version=2)); assert r2_['requirement_version'] == 2 and r2_['review_status'] == 'awaiting_review' and r2_['reviewer_id'] is None
    A.call('/readiness/requirements', rb(name='Delegation log (current)', requires_expiry=True, expected_version=2))
    assert A.call('/readiness?study_id=CT-204&site_id=SITE-104')['rows'][0]['status'] == 'missing' and 'expiry' in A.call('/readiness?study_id=CT-204&site_id=SITE-104')['rows'][0]['reason']
    r3 = A.call('/readiness/records', rec(expected_version=3, expiry_date=str(date.today() - timedelta(days=1))))
    assert A.call('/readiness?study_id=CT-204&site_id=SITE-104')['rows'][0]['status'] == 'expired'
    hist = A.call('/readiness/history?study_id=CT-204'); assert {'requirement_defined', 'requirement_changed', 'record_saved', 'record_reviewed'} <= {h['kind'] for h in hist}
    vid = A.call('/visits', {'id': str(uuid4()), 'study_id': 'CT-204', 'site_id': 'SITE-104', 'title': 'Readiness visit', 'visit_at': iso(now + timedelta(days=3))}, 201)['id']
    vd = A.call(f'/visits/{vid}'); assert vd['readiness']['counts'] == {'expired': 1} and 'not a current verification' in vd['readiness']['note']
    passed('changing a requirement invalidates affected records (stale -> awaiting review, review blocked until re-recorded); expiry never inferred; expired/missing derived; history kept; visit shows readiness')

    # ---- 6. procedure impact review
    art = 'KB-IMPACT'; text1 = '# Escalation\nEscalate after 15 minutes.\n\n# Receipts\nCheck the upload receipt.\n\n# Notes\nKeep records.'
    text2 = '# Escalation\nEscalate after 30 minutes.\n\n# Receipts\nCheck the upload receipt.\n\n# Notes\nKeep records.\n\n# Audit\nRecord the reviewer.'
    sql("INSERT INTO knowledge(workspace_id,id,title,content,category,version) VALUES(%s,%s,'Impact procedure',%s,'document_workflow',2)", W, art, text2)
    for v_, t in ((1, text1), (2, text2)): sql("INSERT INTO procedure_versions(workspace_id,article_id,version,title,content,category) VALUES(%s,%s,%s,'Impact procedure',%s,'document_workflow')", W, art, v_, t)
    src = {'id': 'src-1', 'article_id': art, 'version': 1, 'title': 'Escalation', 'content': 'Escalate after 15 minutes.'}
    run_id = uuid4(); res_ = {'sources': [src], 'recommendation': {'evidence_ids': ['src-1']}}
    sql("INSERT INTO runs(workspace_id,id,case_id,result,duration_seconds,model,decision) VALUES(%s,%s,'REC-1',%s,0,'test','approved')", W, run_id, Jsonb(res_))
    ck_items = [{'id': 'i1', 'text': 'Escalate after 15 minutes', 'state': 'not_checked', 'notes': '', 'source_ids': ['src-1']}]
    sql("INSERT INTO investigation_checks(workspace_id,id,case_id,run_id,sources,items,status) VALUES(%s,%s,'REC-1',%s,%s,%s,'active')", W, uuid4(), run_id, Jsonb([src]), Jsonb(ck_items))
    d = A.call(f'/knowledge/{art}/impact-review?old=1&new=2')
    assert [c['change'] for c in d['changes']] == ['changed', 'added'] and d['changes'][0]['old_text'].endswith('15 minutes.') and d['changes'][0]['new_text'].endswith('30 minutes.') and 'not AI' in d['method']
    assert len(d['affected_checks']) == 1 and d['affected_cases'][0]['case_id'] == 'REC-1' and d['affected_cases'][0]['past_decision'] == 'approved' and d['review'] is None
    B.call(f'/knowledge/{art}/impact-review?old=1&new=2', expected=404)
    A.call(f'/knowledge/{art}/impact-review?old=2&new=1', expected=422)
    ib = lambda **k: {'old_version': 1, 'new_version': 2, 'status': 'needed', 'rationale': 'Threshold changed from 15 to 30 minutes.', 'comparison_hash': d['comparison_hash'], 'expected_version': 0, **k}
    role('analyst'); A.call(f'/knowledge/{art}/impact-review', ib(), 403); role('owner')
    A.call(f'/knowledge/{art}/impact-review', ib(comparison_hash='0' * 64), 409)
    A.call(f'/knowledge/{art}/impact-review', ib(rationale='short'), 422)
    out = A.call(f'/knowledge/{art}/impact-review', ib()); assert out['review']['status'] == 'needed' and out['review']['version'] == 1
    A.call(f'/knowledge/{art}/impact-review', ib(), 409)
    out = A.call(f'/knowledge/{art}/impact-review', ib(status='not_needed', rationale='On reflection the case threshold is unaffected.', expected_version=1)); assert out['review']['status'] == 'not_needed' and out['review']['version'] == 2
    A.call(f'/knowledge/{art}/impact-review', ib(expected_version=1), 409)
    assert sql('SELECT items,status FROM investigation_checks WHERE workspace_id=%s', W)[0]['items'] == ck_items and sql('SELECT result,decision FROM runs WHERE workspace_id=%s AND id=%s', W, run_id)[0]['decision'] == 'approved'
    assert sql("SELECT version FROM procedure_versions WHERE workspace_id=%s AND article_id=%s ORDER BY version", W, art) == [{'version': 1}, {'version': 2}] and events('REC-1', 'procedure_impact_reviewed')
    sql("UPDATE knowledge SET archived=true WHERE workspace_id=%s AND id=%s", W, art)
    assert A.call(f'/knowledge/{art}/impact-review?old=1&new=2')['archived'] is True
    sql("UPDATE knowledge SET version=3,archived=false WHERE workspace_id=%s AND id=%s", W, art); sql("INSERT INTO procedure_versions(workspace_id,article_id,version,title,content,category) VALUES(%s,%s,3,'Impact procedure',%s,'document_workflow')", W, art, text2 + '\n\n# Extra\nMore.')
    dd = A.call(f'/knowledge/{art}/impact-review?old=1&new=2'); assert dd['superseded_by'] == 3 and dd['review']['status'] == 'not_needed'
    assert A.call(f'/knowledge/{art}/impact-review')['old_version'] == 2 and A.call(f'/knowledge/{art}/impact-review')['review'] is None
    passed('procedure impact: exact changed/added passages, affected checks/cases/past decisions, labelled deterministic; human review versioned (stale/hash/role/workspace checks); checks, runs, versions untouched; archived and superseded flagged')

    # ---- 7. feedback queue and privacy
    fa = A.call('/feedback', {'rating': 3, 'message': 'The recurrence panel is hard to find on narrow screens.'}, 201)['id']
    fb = B.call('/feedback', {'rating': 2, 'message': 'SECURITY: other workspace report that must stay private.'}, 201)['id']
    peer_fb = uuid4(); sql("INSERT INTO feedback(id,workspace_id,actor_id,rating,message) VALUES(%s,%s,%s,4,'A peer comment that the owner may read in the queue.')", peer_fb, W, peer)
    q = A.call('/feedback/queue'); ids_ = {i['id'] for i in q['items']}; assert fa in ids_ and str(peer_fb) in ids_ and fb not in ids_ and all(i['status'] == 'received' for i in q['items']) and q['states'] == ['received', 'reviewing', 'planned', 'in_progress', 'completed', 'declined']
    assert fa not in {i['id'] for i in B.call('/feedback/queue')['items']}
    imp = str(uuid4()); ib_ = lambda **k: {'id': imp, 'title': 'Responsive recurrence panel', 'description': 'Improve narrow layout', 'status': 'planned', 'owner_id': str(UID), 'explanation': '', 'expected_version': 0, **k}
    A.call('/improvements', ib_(owner_id=str(outsider)), 422); A.call('/improvements', ib_(status='declined'), 422)
    A.call('/improvements', ib_())
    A.call('/improvements', ib_(status='in_progress', expected_version=1)); A.call('/improvements', ib_(expected_version=1), 409)
    tr = lambda fid_, **k: A.call(f'/feedback/{fid_}/triage', {'expected_version': 0, 'status': 'reviewing', 'owner_id': str(UID), 'internal_note': 'INTERNAL: customer is frustrated', 'public_note': 'We are looking at this.', 'confidential': False, 'improvement_id': None, 'related_feedback': [], **k})
    A.call(f'/feedback/{fb}/triage', {'expected_version': 0, 'status': 'reviewing'}, 404)
    A.call(f'/feedback/{fa}/triage', {'expected_version': 0, 'status': 'reviewing', 'owner_id': str(outsider)}, 422)
    A.call(f'/feedback/{fa}/triage', {'expected_version': 0, 'status': 'planned', 'improvement_id': str(uuid4())}, 422)
    A.call(f'/feedback/{fa}/triage', {'expected_version': 0, 'status': 'reviewing', 'related_feedback': [fb]}, 422)
    A.call(f'/feedback/{fa}/triage', {'expected_version': 0, 'status': 'declined'}, 422)
    tr(fa); tr(fa, expected_version=1, status='planned', improvement_id=imp, related_feedback=[str(peer_fb)], public_note='Planned for the next release.')
    A.call(f'/feedback/{fa}/triage', {'expected_version': 1, 'status': 'planned'}, 409)
    mine = A.call('/feedback/mine'); assert [m['id'] for m in mine] == [fa] and mine[0]['status'] == 'planned' and mine[0]['public_note'] == 'Planned for the next release.' and mine[0]['improvement_title'] == 'Responsive recurrence panel'
    assert 'INTERNAL' not in json.dumps(mine) and 'owner_id' not in mine[0] and 'internal_note' not in mine[0]
    role('analyst'); A.call('/feedback/queue', expected=403); A.call('/improvements', ib_(id=str(uuid4())), 403); A.call(f'/feedback/{fa}/triage', {'expected_version': 2, 'status': 'completed', 'public_note': 'Done now'}, 403)
    assert [m['id'] for m in A.call('/feedback/mine')] == [fa] and str(peer_fb) not in json.dumps(A.call('/feedback/mine')); role('owner')
    A.call(f'/feedback/{fa}/triage', {'expected_version': 2, 'status': 'completed', 'public_note': 'Fixed in this release.', 'confidential': True, 'internal_note': 'Security-sensitive details here', 'improvement_id': imp})
    mine = A.call('/feedback/mine')[0]; assert mine['status'] == 'reviewing' and mine['public_note'] == '' and mine['improvement_title'] is None and 'Security' not in json.dumps(mine)
    assert [m['id'] for m in B.call('/feedback/mine')] == [fb] and B.call('/feedback/mine')[0]['status'] == 'received'
    passed('feedback queue: owner-only triage with owner/explanations/improvement links/related items; stale/foreign/invalid links rejected; submitters see only own safe status; confidential hides detail; other workspace isolated')

    # ---- 8. exports
    pkg = A.call('/cases/REC-1/package.json'); txt = json.dumps(pkg, default=str)
    assert {'group', 'member', 'plan', 'action', 'window', 'history'} <= {r['type'] for r in pkg['recurrence']} and pkg['procedure_impact'] and 'prevention_plan_revised' in txt and 'procedure_impact_reviewed' in txt
    exp = json.dumps(A.call('/export'), default=str)
    for needle in ('recurrence_groups', 'prevention_plans', 'readiness_records', 'procedure_impact_reviews', 'improvement_history', 'Receipt gaps at SITE-104', 'Delegation log'):
        assert needle in exp, needle
    for secret in ('INTERNAL: customer', 'Security-sensitive', 'Planned for the next release', 'recurrence panel is hard to find', 'Responsive recurrence panel', 'feedback_triage', '"improvements"'):
        assert secret not in exp and secret not in txt, secret
    role('analyst'); assert A.call('/cases/REC-1/package.json')['recurrence'] == []; role('owner')
    from report import build_case_report
    assert len(build_case_report(json.loads(json.dumps(pkg, default=str)))) > 1500
    passed('JSON/PDF case package and workspace export include recurrence, plans, windows, impact reviews, readiness history; feedback, triage notes and improvements are excluded; analysts get no recurrence detail')
    print(f'PASS: {n} improvement integration groups. Temporary records removed in finally.', flush=True)
finally:
    with connect() as c:
        for w in workspaces: c.execute('DELETE FROM workspaces WHERE id=%s', (w,))
        c.execute("DELETE FROM feedback WHERE workspace_id IS NULL AND message LIKE 'SECURITY: other workspace%%'")
        c.execute("DELETE FROM users WHERE guest AND NOT EXISTS(SELECT 1 FROM memberships m WHERE m.user_id=users.id)")
