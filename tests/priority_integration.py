"""Suggested request order against the running TEST stack (3002 API only). Fresh expiring demo workspaces, removed in finally.
Run in the test API container: python /app/tests/priority_integration.py"""
import sys, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
import urllib.request
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
def events(kind): return sql('SELECT * FROM case_events WHERE workspace_id=%s AND case_id=%s AND event_type=%s ORDER BY id', W, CID, kind)
def raw(path):
    req = urllib.request.Request(URL + path, headers={'X-Internal-Key': secret('INTERNAL_KEY'), 'X-Client-IP': str(id(A)), 'Cookie': '; '.join(c.name + '=' + c.value for c in A.cookies)})
    with urllib.request.urlopen(req, timeout=60) as r: return r.read()
now = datetime.now(timezone.utc).replace(microsecond=0)
ago = lambda h: now - timedelta(hours=h)
CID, PORTAL, HUB = 'JRN-R', 'mock-upload-portal', 'mock-binder-hub'
workspaces = []
try:
    W = A.call('/auth/demo', {})['workspace_id']; workspaces.append(W); WB = B.call('/auth/demo', {})['workspace_id']; workspaces.append(WB)
    UID = A.call('/auth/me')['user_id']
    sql("INSERT INTO cases(workspace_id,id,study_id,site_id,title,description,category,priority,status) VALUES(%s,%s,'CT-204','SITE-104','Priority case','Synthetic.','document_workflow','medium','open')", W, CID)
    run_id = uuid4(); sql("INSERT INTO runs(workspace_id,id,case_id,result,duration_seconds,model) VALUES(%s,%s,%s,%s,0,'test')", W, run_id, CID, Jsonb({'recommendation': {'status': 'supported', 'evidence_ids': []}, 'sources': []}))
    P = f'/cases/{CID}/journey'; PR = P + '/priority'
    assert A.call(PR)['available'] is False
    A.call(P + '/subject', {'id': str(uuid4()), 'expected_rev': 0, 'document_system': PORTAL, 'document_ref': 'DOC-5001', 'document_version': '2', 'destination_system': HUB, 'binder_ref': 'BND-77'})
    def imp(shape, ref, at, rows=None, complete=True):
        ex = example_export(shape, 'CT-204', 'SITE-104', ref=ref, observed_at=at, rows=rows, complete=complete)
        return A.call('/operations/journey-import', {'export': ex['export'], 'mapping': ex['mapping']}, 201)
    imp('portal', 'P1', ago(6), [{'event': 'RECEIPT', 'receipt_no': 'RCPT-1', 'doc_id': 'DOC-5001', 'doc_rev': '2', 'state': 'RECEIVED', 'at': ago(6).isoformat()}])
    reqs = [{'stage': 'destination_filing', 'status': 'completed'}, {'stage': 'binder_visibility', 'status': 'visible'}]
    O = {'id': str(uuid4()), 'key': str(uuid4()), 'expected_rev': 0, 'description': 'The same document/version is filed and visible in the intended binder.', 'requirements': reqs, 'required': True, 'remediation_at': ago(3).isoformat()}
    A.call(P + '/outcomes', O, 201)
    A.call('/contacts', {'id': (contact := str(uuid4())), 'name': 'Hub support', 'category': 'sync', 'primary_contact': 'hub@sample.invalid', 'study_id': 'CT-204', 'site_id': 'SITE-104'})
    pr = A.call(PR)
    by = {c['key']: c for c in pr['candidates'] + pr['waiting']}
    FILING, VIS, TRANSFER = 'no_record:destination_filing', 'no_record:binder_visibility', 'no_record:transfer'
    assert pr['rule_version'] == 'suggested-order-1' and {FILING, VIS, TRANSFER} <= set(by)
    assert len(by[FILING]['unresolved']) == 2 and all(k.startswith(('stage:', 'outcome:')) for k in by[FILING]['unresolved']), by[FILING]
    assert by[FILING]['target'] == {'stage': 'destination_filing', 'code': 'no_record', 'source_system': HUB, 'document_ref': 'DOC-5001', 'document_version': '2', 'binder_ref': 'BND-77', 'record': None}
    assert 'could help assess 2 checks' in by[FILING]['explanation'] and 'will resolve' not in by[FILING]['explanation'].lower() and by[FILING]['effort'] == 'unknown'
    passed('requests map by structured rule to distinct unresolved checks (outcome requirement + stage check) with an exact target; wording says "could help assess"; effort stays unknown')

    # ---- inputs: validation, cycles, roles, idempotency, concurrency
    inp = lambda gap, **k: {'id': str(uuid4()), 'gap_key': gap, 'expected_rev': 0, 'effort': 'low', 'effort_note': 'Usually a one-line lookup.', 'prerequisites': [], **k}
    A.call(PR + '/inputs', inp('nope:gap'), 409)
    A.call(PR + '/inputs', inp(FILING, prerequisites=[{'kind': 'gap', 'key': FILING}]), 422)
    A.call(PR + '/inputs', inp(FILING, prerequisites=[{'kind': 'gap', 'key': 'nope:gap'}]), 422)
    A.call(PR + '/inputs', inp(FILING, prerequisites=[{'kind': 'check', 'key': 'stage:nope'}]), 422)
    A.call(PR + '/inputs', inp(FILING, effort='certain'), 422)
    A.call(PR + '/inputs', inp(FILING, effort_note='x' * 201), 422)
    B.call(PR + '/inputs', inp(FILING), 404)
    role('analyst'); A.call(PR + '/inputs', inp(FILING), 403); assert A.call(PR)['candidates'] and A.call(PR)['saved'] is None; role('owner')
    dep = {'kind': 'gap', 'key': TRANSFER}
    i1 = inp(FILING, prerequisites=[dep]); r1 = A.call(PR + '/inputs', i1, 201); assert A.call(PR + '/inputs', i1, 201)['id'] == r1['id']
    A.call(PR + '/inputs', {**i1, 'effort': 'high'}, 409); A.call(PR + '/inputs', inp(FILING), 409)  # same id/different payload; stale revision
    A.call(PR + '/inputs', inp(TRANSFER, prerequisites=[{'kind': 'gap', 'key': FILING}]), 422)  # cycle FILING -> TRANSFER -> FILING
    assert len(sql('SELECT 1 FROM journey_priority_inputs WHERE workspace_id=%s', W)) == 1 and len(events('journey_priority_inputs_saved')) == 1
    pr = A.call(PR); by = {c['key']: c for c in pr['candidates'] + pr['waiting']}
    assert by[FILING]['state'] == 'blocked' and by[FILING]['effort'] == 'low' and by[FILING]['prerequisites'][0]['state'] == 'unmet'
    assert by[FILING]['rank'] > by[TRANSFER]['rank'] and 'blocked until 1 prerequisite is met' in by[FILING]['explanation']
    passed('effort/prerequisites validated (workspace, self, missing, cycle, roles, retries, revisions); unmet prerequisite blocks and sorts after ready requests')

    # ---- mapping corrections with reasons
    chk = [c['key'] for c in pr['checks'] if c['key'].endswith('binder_visibility:visible')][0]
    mp = lambda **k: {'id': str(uuid4()), 'gap_key': FILING, 'check_key': chk, 'action': 'add', 'reason': 'The filing record also shows visibility.', **k}
    A.call(PR + '/mappings', mp(reason='short'), 422); A.call(PR + '/mappings', mp(check_key='stage:nope'), 409); B.call(PR + '/mappings', mp(), 404)
    role('analyst'); A.call(PR + '/mappings', mp(), 403); role('owner')
    m1 = mp(); A.call(PR + '/mappings', m1, 201); assert A.call(PR + '/mappings', m1, 201)['id'] == m1['id']
    A.call(PR + '/mappings', mp(), 422)  # already mapped
    assert len({c for c in {c['key']: c for c in A.call(PR)['candidates'] + A.call(PR)['waiting']}[FILING]['unresolved']}) == 3
    A.call(PR + '/mappings', mp(action='reset', reason='Reverting the correction.'), 201)
    assert len({c['key']: c for c in A.call(PR)['candidates'] + A.call(PR)['waiting']}[FILING]['unresolved']) == 2 and len(A.call(PR)['mappings']) == 2
    passed('reviewer mapping corrections need a reason, are idempotent, counted once, resettable, and kept as history')

    # ---- saved versions, stale detection, override history
    sv = lambda **k: {'id': str(uuid4()), 'expected_rev': 0, **k}
    B.call(PR + '/save', sv(), 404); role('analyst'); A.call(PR + '/save', sv(), 403); role('owner')
    s1 = sv(); v1 = A.call(PR + '/save', s1, 201); assert A.call(PR + '/save', s1, 201)['id'] == v1['id'] and v1['rev'] == 1 and v1['rule_version'] == 'suggested-order-1'
    assert v1['inputs']['journey_fingerprint'] and v1['inputs']['candidates'] and v1['inputs']['outcome_ids'] and v1['suggested'][0]['explanation']
    A.call(PR + '/save', sv(expected_rev=0), 409)
    assert A.call(PR + '/save', sv(expected_rev=1), 201)['id'] == v1['id']  # unchanged inputs: no new version
    order = [c['key'] for c in A.call(PR)['candidates']]; assert A.call(PR)['saved']['stale'] is False
    new = list(reversed(order))
    ov = {'id': str(uuid4()), 'expected_rev': 1, 'order': new, 'reason': 'Hub contact is available today, so ask about visibility first.'}
    A.call(PR + '/override', {**ov, 'order': order}, 422); A.call(PR + '/override', {**ov, 'order': order[:-1]}, 422); A.call(PR + '/override', {**ov, 'reason': 'short'}, 422); B.call(PR + '/override', ov, 404)
    role('analyst'); A.call(PR + '/override', ov, 403); role('owner')
    v2 = A.call(PR + '/override', ov, 201); assert A.call(PR + '/override', ov, 201)['id'] == v2['id'] and v2['rev'] == 2
    assert v2['override']['order'] == new and v2['override']['suggested_order'] == order and [x['key'] for x in v2['suggested']] == order, 'calculated and reviewer orders stay distinct'
    A.call(PR + '/override', {**ov, 'id': str(uuid4())}, 409)  # stale expected_rev
    assert len(events('journey_priority_overridden')) == 1
    imp('hub', 'H1', ago(2), [{'kind': 'sync_job', 'job': {'id': 'JOB-1'}, 'item': {}, 'outcome': 'failed', 'when': ago(2).isoformat(), 'target': 'BND-77'}])  # new evidence
    g = A.call(PR); assert g['saved']['stale'] is True and g['saved']['rev'] == 2 and g['saved']['override']['order'] == new
    A.call(PR + '/override', {**ov, 'id': str(uuid4()), 'expected_rev': 2, 'order': new}, 409)  # stale ranking cannot be re-overridden
    v3 = A.call(PR + '/save', sv(expected_rev=2), 201)
    assert v3['rev'] == 3 and v3['override'] is None, 'refresh must not silently carry or rewrite the reviewer ordering'
    h = A.call(PR)['history']; assert [x['rev'] for x in h] == [3, 2, 1] and h[1]['override']['reason'].startswith('Hub contact') and h[1]['stale'] and not h[0]['stale']
    rows = sql('SELECT rev,override,input_hash FROM journey_prioritizations WHERE workspace_id=%s ORDER BY rev', W); assert rows[1]['override']['order'] == new and rows[0]['override'] is None
    O2 = {**O, 'id': str(uuid4()), 'expected_rev': 1, 'description': 'The same document/version is filed in the intended binder.', 'requirements': reqs[:1]}; A.call(P + '/outcomes', O2, 201)
    assert A.call(PR)['saved']['stale'] is True, 'an outcome revision makes the saved order stale'
    A.call(PR + '/save', sv(expected_rev=3), 201)
    A.call(PR + '/inputs', {**inp(VIS, effort='medium')}, 201); assert A.call(PR)['saved']['stale'] is True, 'an effort change makes it stale'
    A.call(PR + '/save', sv(expected_rev=4), 201)
    passed('saved orders keep rule version, inputs and evidence versions; evidence/outcome/effort changes mark them stale; refresh adds a version and never rewrites or carries the reviewer override; history preserved')

    # ---- drafts: structured duplicate, retry safety, waiting/received, responses never resolve checks
    latest = A.call(PR)['saved']['id']
    dr = lambda gap, **k: {'id': str(uuid4()), 'request_id': str(uuid4()), 'stage': by[gap]['stage'], 'gap_key': gap, 'question': by[gap]['question'] + ' Please include the export reference.', 'would_settle': by[gap]['would_settle'], 'contact_id': contact, 'prioritization_id': latest, **k}
    A.call(P + '/collection', dr(TRANSFER, prioritization_id=str(uuid4())), 422)
    d1 = dr(TRANSFER); a1 = A.call(P + '/collection', d1, 201); assert A.call(P + '/collection', d1, 201)['id'] == a1['id']
    assert len(sql('SELECT 1 FROM information_requests WHERE workspace_id=%s AND id=%s', W, d1['request_id'])) == 1 and len(sql('SELECT 1 FROM journey_plan_items WHERE workspace_id=%s', W)) == 1
    dup = A.call(P + '/collection', dr(TRANSFER, question='A completely different wording of the same ask here.'), 409)
    assert dup['detail']['matches'][0]['status'] == 'draft'   # same structured target, different wording: no second proposal
    ev = events('journey_collection_drafted'); assert ev[0]['payload']['from_suggested_order'] is True and ev[0]['payload']['prioritization_id'] == latest and ev[0]['payload']['no_message_sent'] is True
    pr = A.call(PR); t = {c['key']: c for c in pr['candidates'] + pr['waiting']}[TRANSFER]
    assert t['existing']['request_status'] == 'draft' and t['state'] in ('ready', 'blocked') and t['rank'] is not None
    before_unres = {c['key']: c['unresolved'] for c in pr['candidates'] + pr['waiting']}
    sql("UPDATE information_requests SET status='requested' WHERE workspace_id=%s AND id=%s", W, d1['request_id'])
    pr = A.call(PR); t = {c['key']: c for c in pr['candidates'] + pr['waiting']}[TRANSFER]
    assert t['state'] == 'waiting' and t['rank'] is None and TRANSFER not in [c['key'] for c in pr['candidates']] and 'Waiting' in t['explanation']
    sql("UPDATE information_requests SET status='received',responses=%s WHERE workspace_id=%s AND id=%s", Jsonb([{'text': 'Everything was fixed.', 'actor_name': 'Hub', 'recorded_at': now.isoformat()}]), W, d1['request_id'])
    pr = A.call(PR); allc = {c['key']: c for c in pr['candidates'] + pr['waiting']}
    assert allc[TRANSFER]['state'] == 'received' and allc[TRANSFER]['unresolved'] == before_unres[TRANSFER], 'a received response must not resolve any check'
    assert allc[FILING]['state'] == 'blocked' and allc[FILING]['prerequisites'][0]['state'] == 'unmet', 'a received response must not satisfy a prerequisite'
    sql("UPDATE information_requests SET status='cancelled' WHERE workspace_id=%s AND id=%s", W, d1['request_id'])
    assert {c['key']: c for c in A.call(PR)['candidates'] + A.call(PR)['waiting']}[TRANSFER]['existing'] is None  # cancelled requests no longer occupy the target
    role('analyst'); A.call(P + '/collection', dr(VIS), 403); role('owner')
    B.call(P + '/collection', dr(VIS), 404)
    passed('drafts via the existing workflow: same structured target is not proposed twice, retries are safe, sent requests wait, received responses neither resolve checks nor satisfy prerequisites, cancelled ones free the target')

    # ---- measurement from recorded events only, then exact evidence assesses mapped checks
    A.call(P + '/collection', dr(FILING, prioritization_id=A.call(PR)['saved']['id']), 201)  # a second draft taken from the suggested order
    imp('hub', 'H2', ago(1), [{'kind': 'filing', 'job': {'id': 'F1'}, 'item': {'upstream': 'DOC-5001', 'rev': '2'}, 'outcome': 'filed', 'when': ago(1).isoformat(), 'target': 'BND-77'}])
    A.call(P + '/links', {'id': str(uuid4()), 'kind': 'document', 'from_system': HUB, 'from_ref': 'DOC-5001', 'rationale': 'Hub admin record names the portal document.', 'evidence': 'Hub admin record 44'}, 201)
    pr = A.call(PR)
    act = pr['activity']; assert act['drafts_from_suggestion'] == 2 and act['order_overrides'] == 1 and act['responses_reviewed'] == 0 and act['mapped_checks_now_verified'] >= 1 and 'do not show that any request caused' in act['note'] and set(act) == {'drafts_from_suggestion', 'order_overrides', 'responses_reviewed', 'mapped_checks_now_verified', 'note'}
    passed('activity counts come only from recorded events (draft from suggestion, override, reviewed responses, mapped checks now verified) with an explicit no-causation note')

    # ---- exports
    pkg = A.call(f'/cases/{CID}/package.json')
    assert pkg['journey_priority_summary'] and 'could help assess' in json.dumps(pkg['journey_priority_summary']) and len(pkg['journey_prioritizations']) >= 4 and pkg['journey_priority_inputs'] and pkg['journey_priority_mappings']
    assert any(x['override'] for x in pkg['journey_prioritizations']) and pkg['journey_prioritizations'][0]['rule_version'] == 'suggested-order-1'
    assert raw(f'/cases/{CID}/package.pdf')[:5] == b'%PDF-'
    role('analyst'); ap = A.call(f'/cases/{CID}/package.json'); assert ap['journey_prioritizations'] == [] and ap['journey_priority_mappings'] == [] and ap['journey_priority_inputs'] == [] and ap['journey_priority_summary']; role('owner')
    B.call(f'/cases/{CID}/package.json', expected=404)
    passed('case JSON/PDF include suggested order, inputs, mapping corrections and override history under existing role boundaries')

    # ---- vanished/unmatched prerequisites stay blocked until an authorized, reasoned removal/replacement
    O3 = {'id': str(uuid4()), 'key': str(uuid4()), 'expected_rev': 0, 'description': 'Visible outcome used only as a dependency.', 'requirements': [{'stage': 'binder_visibility', 'status': 'visible'}], 'required': True, 'remediation_at': ago(3).isoformat()}
    A.call(P + '/outcomes', O3, 201)
    ck = [c for c in A.call(PR)['checks'] if c['key'].startswith('outcome:') and O3['description'][:20] in c['label']][0]
    assert '#' + O3['key'][:8] in ck['label'] and O3['description'][:20] in ck['label'], 'name and short stable id shown in selectors'
    assert len({c['label'] for c in A.call(PR)['checks']}) == len(A.call(PR)['checks']), 'labels are distinguishable'
    G, DEP = [c['key'] for c in A.call(PR)['candidates']][:2]  # gaps still open after the earlier evidence import
    cur = sql('SELECT max(rev) AS r FROM journey_priority_inputs WHERE workspace_id=%s AND case_id=%s AND gap_key=%s', W, CID, G)[0]['r'] or 0
    ge = lambda **k: {'id': str(uuid4()), 'gap_key': G, 'expected_rev': cur, 'effort': 'low', 'effort_note': 'Usually a one-line lookup.', **k}
    keep = [{'kind': 'gap', 'key': DEP}, {'kind': 'check', 'key': ck['key']}]
    A.call(PR + '/inputs', ge(prerequisites=keep), 201); cur += 1
    A.call(P + '/outcomes', {**O3, 'id': str(uuid4()), 'expected_rev': 1, 'retired': True}, 201)  # the required check vanishes
    f = {c['key']: c for c in A.call(PR)['candidates']}[G]
    assert f['state'] == 'blocked' and [p['state'] for p in f['prerequisites']][1] == 'unmatched' and 'still blocks' in f['explanation'], f
    A.call(PR + '/inputs', ge(effort='medium', prerequisites=keep), 201); cur += 1  # unrelated edit keeps the unmatched dependency
    assert {c['key']: c for c in A.call(PR)['candidates']}[G]['state'] == 'blocked'
    drop = [keep[0]]
    A.call(PR + '/inputs', ge(prerequisites=drop), 422)                                   # no reason
    A.call(PR + '/inputs', ge(prerequisites=drop, change_reason='short'), 422)
    role('analyst'); A.call(PR + '/inputs', ge(prerequisites=drop, change_reason='Retired outcome, replaced by the filing check.'), 403); role('owner')
    assert {c['key']: c for c in A.call(PR)['candidates']}[G]['state'] == 'blocked'
    n_before = len(sql('SELECT 1 FROM journey_priority_inputs WHERE workspace_id=%s', W))
    A.call(PR + '/inputs', ge(prerequisites=drop, change_reason='Retired outcome, replaced by the filing check.'), 201)
    ev = events('journey_priority_inputs_saved')[-1]['payload']
    assert ev['change_reason'].startswith('Retired') and ev['removed_prerequisites'][0]['key'] == ck['key']
    assert len(sql('SELECT 1 FROM journey_priority_inputs WHERE workspace_id=%s', W)) == n_before + 1, 'earlier dependency revisions are preserved'
    assert [p['key'] for p in {c['key']: c for c in A.call(PR)['candidates'] + A.call(PR)['waiting']}[G]['prerequisites']] == [DEP], 'only the reasoned removal changed the dependency'
    assert A.call(PR)['saved']['stale'] is True
    passed('unmatched prerequisites stay blocked; only a reasoned reviewer/owner removal unblocks; history and stale ranking preserved; labels show name and short id')
    print(f'PASS: {n} priority integration groups. Temporary records removed in finally.', flush=True)
finally:
    with connect() as c:
        for w in workspaces: c.execute('DELETE FROM workspaces WHERE id=%s', (w,))
        c.execute("DELETE FROM users WHERE guest AND NOT EXISTS(SELECT 1 FROM memberships m WHERE m.user_id=users.id)")
