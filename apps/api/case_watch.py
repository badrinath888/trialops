"""Case watch: persisted, deterministic change detection over authorized case inputs.
Reuses assessment linkage/gap/validation and the durable job queue. The optional local
model only phrases bounded follow-up questions; it never reviews, confirms, sends or resolves."""
import logging, urllib.error
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb
from pydantic import Field
from db import connect
from security import actor, require, rate
from workflows import canonical
from assessments import Strict, fresh_actor, context, select_sources, linkage, gaps, assess, config

router = APIRouter()
DEBOUNCE = 15          # seconds a changed state must stay stable (combines bursts)
MAX_WATCHES = 20       # active watches per workspace
MAX_JOBS = 3           # queued/running watch jobs per workspace
MAX_CHANGES = 12
RECORDS = ('document_processing', 'synchronization')
INTERRUPTED = 'Worker interrupted'


class WatchSettings(Strict):
    status: Literal['active', 'paused', 'disabled']
    evidence_ids: list[str] = Field(default_factory=list, max_length=10)


def observe(c, w, case, selected, catalog):
    """Relevant, authorized inputs only: responses, same study/site snapshots, selected evidence, confirmed links."""
    cid = case['id']
    s = {'responses': {}, 'snapshots': {}, 'selected': {}, 'links': {}}
    for r in c.execute("SELECT id,responses FROM information_requests WHERE workspace_id=%s AND case_id=%s AND status<>'cancelled'", (w, cid)).fetchall():
        for i, v in enumerate(r['responses'] or []):
            s['responses'][f"request:{r['id']}:{i}"] = canonical(v)
    for r in c.execute('SELECT id FROM external_responses WHERE workspace_id=%s AND case_id=%s', (w, cid)).fetchall():
        s['responses'][f"external:{r['id']}"] = 'present'  # reviewer decisions are not new responses
    for r in c.execute('SELECT id,content_hash FROM snapshot_history WHERE workspace_id=%s AND study_id=%s AND site_id=%s', (w, case['study_id'], case['site_id'])).fetchall():
        s['snapshots'][str(r['id'])] = r['content_hash']
    for r in c.execute("SELECT id,target FROM assessment_decisions WHERE workspace_id=%s AND case_id=%s AND action='confirm_link'", (w, cid)).fetchall():
        s['links'][str(r['id'])] = r['target']
    by = {x['id']: x['version'] for x in catalog}
    s['selected'] = {i: by.get(i, 'removed') for i in selected}
    return s


def flat(state):
    return {**state['responses'], **{'snapshot:' + k: v for k, v in state['snapshots'].items()},
            **state['selected'], **{'link:' + k: v for k, v in state['links'].items()}}


def diff(prev, cur):
    out = []
    for sec in ('responses', 'snapshots', 'selected', 'links'):
        p, n = prev.get(sec, {}), cur.get(sec, {})
        out += [(sec, 'added' if k not in p else 'changed', k) for k, v in n.items() if k not in p or p[k] != v]
    return [x for x in out if not (x[0] == 'selected' and x[1] == 'added')]


def build(c, w, case, ctx, catalog, changes, cur):
    """Return the saved update body. Deterministic fields first; model questions are optional and labelled."""
    out, refs, uncertain = [], [], []
    new_snaps = {k for sec, _, k in changes if sec == 'snapshots'}
    snap_rows = {str(r['id']): r for r in c.execute('SELECT id,observed_at,content_hash FROM snapshot_history WHERE workspace_id=%s AND study_id=%s AND site_id=%s', (w, case['study_id'], case['site_id'])).fetchall()}
    ext = {f"external:{r['id']}": r for r in c.execute('SELECT id,status,submitted_at FROM external_responses WHERE workspace_id=%s AND case_id=%s', (w, case['id'])).fetchall()}
    reqs = {str(r['id']): r for r in c.execute('SELECT id,title,responses FROM information_requests WHERE workspace_id=%s AND case_id=%s', (w, case['id'])).fetchall()}
    by = {x['id']: x for x in catalog}
    for sec, kind, k in changes[:MAX_CHANGES]:
        if sec == 'responses' and k.startswith('external:'):
            out.append(f"New external response received on this case. It is unreviewed and unverified; a human must review it. (status now: {ext[k]['status']})" if k in ext else 'External response changed.')
            refs.append({'id': k, 'version': cur['responses'][k], 'observed_at': str(ext[k]['submitted_at']) if k in ext else None})
        elif sec == 'responses':
            _, rid, i = k.split(':')
            r = reqs.get(rid)
            at = r['responses'][int(i)].get('recorded_at') if r and int(i) < len(r['responses']) else None
            out.append(f"Information request '{r['title'] if r else rid}': response {int(i) + 1} {kind}.")
            refs.append({'id': k, 'version': cur['responses'][k], 'observed_at': at})
        elif sec == 'snapshots':
            row = snap_rows.get(k)
            out.append(f"New operational snapshot for study {case['study_id']} / site {case['site_id']}, observed {row['observed_at'] if row else 'unknown'}.")
            refs.append({'id': 'snapshot:' + k, 'version': cur['snapshots'][k], 'observed_at': str(row['observed_at']) if row else None})
        elif sec == 'selected':
            gone = cur['selected'][k] == 'removed'
            out.append(f"Selected evidence {k} " + ('is no longer available.' if gone else 'changed. Earlier assessments that used it are stale.'))
            refs.append({'id': k, 'version': cur['selected'][k], 'observed_at': (by.get(k) or {}).get('observed_at')})
        else:
            out.append('A human-confirmed record linkage was recorded.')
            refs.append({'id': 'link:' + k, 'version': cur['links'][k], 'observed_at': None})
    if len(changes) > MAX_CHANGES: out.append(f'{len(changes) - MAX_CHANGES} further changes omitted; review the case.')
    # Snapshot records: exact-identifier linkage only; same site alone never links a record to the case.
    fresh, bad = [], 0
    records = [s for s in catalog if s['kind'] in RECORDS][:60]
    for s in records:
        if s['id'].split(':')[1] in new_snaps:
            try: select_sources([s], [s['id']], case); fresh.append(s)
            except ValueError: bad += 1
    if new_snaps:
        pool = fresh + [s for s in records if s['id'].split(':')[1] not in new_snaps]
        try: cands = [x for x in linkage(pool, case)['candidates'] if x['left_id'] in {f['id'] for f in fresh} or x['right_id'] in {f['id'] for f in fresh}]
        except ValueError: cands = []
        ok = [x for x in cands if x['eligible_for_confirmation']]
        for x in ok[:3]: out.append(f"Exact identifier match between {x['left_id']} and {x['right_id']}. Not confirmed; a reviewer must verify it.")
        out.append(f"{len(fresh)} same-site record(s) in the new snapshot; {len(ok)} with an exact identifier match to this case. Same site alone does not link a record to a case.")
        if bad: uncertain.append(f'{bad} record(s) had malformed identifiers or dates and were ignored.')
        uncertain.append('Snapshot records are historical observations; they do not establish current status or root cause.')
    ext_new = any(sec == 'responses' and k.startswith('external:') for sec, _, k in changes)
    if ext_new:
        uncertain.append('The external response is unverified and not evidence until a human reviews it; its text was not used here.')
    if any(sec == 'responses' and not k.startswith('external:') for sec, _, k in changes):
        uncertain.append('A recorded response is not verification of the underlying records.')
    changed_sel = [by[k] for sec, _, k in changes if sec == 'selected' and k in by]
    model_sources = (fresh[:6] + changed_sel)[:8]
    try: open_gaps = gaps(model_sources + [s for s in records if s not in fresh], ctx)[0]
    except ValueError: open_gaps = []
    uncertain += [g['uncertainty'] for g in open_gaps[:3]]
    if ext_new: action = 'Review the external response: accept it for consideration or request clarification.'
    elif any(sec == 'links' for sec, _, _ in changes): action = 'Re-check dependent assessments; confirmed linkage does not establish root cause or resolution.'
    elif new_snaps: action = 'Compare the new observation with your selected evidence and verify current status separately.'
    elif any(sec == 'selected' for sec, _, _ in changes): action = 'Re-run the assessment on the changed evidence; the earlier assessment is stale.'
    else: action = 'Review the new response and decide whether a check or request needs updating.'
    body = {'changes': out, 'uncertain': list(dict.fromkeys(uncertain)), 'next_action': action, 'refs': refs, 'model': {'engine': 'none', 'status': 'not_needed'}}
    return body, (model_sources, ctx) if model_sources and open_gaps else None


def add_model(body, pending, call=None):
    """Bounded, optional local-model questions, run outside any DB transaction. Failure keeps the deterministic update."""
    if not pending: return body
    sources, ctx = pending
    cfg = config('questions')
    body['model'] = {'engine': 'local_ollama', 'status': 'unavailable', 'detail': 'Model-assisted questions unavailable; deterministic update saved.'}
    for _ in range(2):
        try:
            r = (call or assess)('questions', '', sources, ctx, cfg)
            if r.get('engine') == 'local_ollama':
                body['model'] = {'engine': 'local_ollama', 'status': 'completed', 'model': cfg['model'], 'questions': [{k: q[k] for k in ('question', 'uncertainty', 'citations')} for q in r['questions']]}
            break
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
        except Exception:
            break
    return body


def _finish(c, job, rid=None):
    c.execute("UPDATE jobs SET status='completed',finished_at=now(),result_id=%s WHERE id=%s AND lease_token=%s AND status='running'", (rid, job['id'], job['lease_token']))


def _pause(c, w, cid, reason):
    c.execute("UPDATE case_watches SET status='paused',pause_reason=%s,pending_hash=NULL,version=version+1,updated_at=now() WHERE workspace_id=%s AND case_id=%s", (reason, w, cid))


def process_watch(job, call=None):
    w, cid = job['workspace_id'], job['target_id']
    with connect() as c:
        watch = c.execute('SELECT * FROM case_watches WHERE workspace_id=%s AND case_id=%s', (w, cid)).fetchone()
        if not watch or watch['status'] != 'active': return _finish(c, job)
        try: fresh_actor(c, w, watch['actor_id'])
        except HTTPException:
            _pause(c, w, cid, 'The enabling reviewer no longer has reviewer permission. Watch paused; nothing was saved.')
            return _finish(c, job)
        catalog, _, ctx = context(c, {'workspace_id': w}, cid)
        cur = observe(c, w, ctx['case'], watch['selected_evidence'], catalog)
        changes = diff(watch['cursor'], cur)
        body, pending = build(c, w, ctx['case'], ctx, catalog, changes, cur) if changes else (None, None)
    persist(job, watch, cur, add_model(body, pending, call) if body else None)


def persist(job, watch, cur, body):
    w, cid = job['workspace_id'], watch['case_id']
    with connect() as c:
        lease = c.execute('SELECT status,lease_token FROM jobs WHERE id=%s FOR UPDATE', (job['id'],)).fetchone()
        if not lease or lease['status'] != 'running' or lease['lease_token'] != job['lease_token']: return
        now = c.execute('SELECT * FROM case_watches WHERE workspace_id=%s AND case_id=%s FOR UPDATE', (w, cid)).fetchone()
        if not now or now['status'] != 'active' or now['cursor_hash'] != watch['cursor_hash'] or now['version'] != watch['version']:
            return _finish(c, job)  # paused, disabled or settings changed mid-run: discard
        try: a = fresh_actor(c, w, now['actor_id'])
        except HTTPException:
            _pause(c, w, cid, 'The enabling reviewer no longer has reviewer permission. Watch paused; nothing was saved.')
            return _finish(c, job)
        h = canonical(cur); rid = None
        if body:
            rid = uuid4()
            row = c.execute('INSERT INTO case_watch_updates(workspace_id,id,case_id,trigger_key,state_hash,changes,uncertain,next_action,refs,model) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id',
                            (w, rid, cid, canonical([now['cursor_hash'], h]), h, Jsonb(body['changes']), Jsonb(body['uncertain']), body['next_action'], Jsonb(body['refs']), Jsonb(body['model']))).fetchone()
            if row:
                c.execute('UPDATE case_watch_updates SET superseded=true WHERE workspace_id=%s AND case_id=%s AND id<>%s', (w, cid, rid))
                title = c.execute('SELECT title FROM cases WHERE workspace_id=%s AND id=%s', (w, cid)).fetchone()['title']
                pref = c.execute('SELECT enabled FROM notification_preferences WHERE workspace_id=%s AND user_id=%s', (w, now['actor_id'])).fetchone()
                if not pref or pref['enabled']:
                    c.execute("INSERT INTO notifications(workspace_id,user_id,id,dedupe_key,kind,title,case_id) VALUES(%s,%s,%s,%s,'watch',%s,%s) ON CONFLICT DO NOTHING",
                              (w, now['actor_id'], uuid4(), 'case-watch:' + str(rid), 'Case watch update: ' + title[:200], cid))
                from release_api import audit
                audit(c, {'workspace_id': w, 'user_id': None, 'name': 'Case watch'}, cid, 'case_watch_update', payload={'update_id': str(rid), 'changes': len(body['changes']), 'model': body['model']['status']})
            else: rid = None
        c.execute('UPDATE case_watches SET cursor=%s,cursor_hash=%s,pending_hash=NULL,pending_since=NULL,version=version+1,updated_at=now() WHERE workspace_id=%s AND case_id=%s', (Jsonb(cur), h, w, cid))
        _finish(c, job, rid)


def enqueue(c, w, uid, cid):
    return c.execute("INSERT INTO jobs(id,workspace_id,actor_id,kind,target_id) VALUES(%s,%s,%s,'watch',%s) ON CONFLICT DO NOTHING RETURNING id", (uuid4(), w, uid, cid)).fetchone()


def blocked(c, w, cid, since):
    """Failed jobs need a manual retry; interrupted ones recover automatically, at most 3 times per 10 minutes."""
    j = c.execute("SELECT status,error,created_at FROM jobs WHERE workspace_id=%s AND kind='watch' AND target_id=%s ORDER BY created_at DESC LIMIT 1", (w, cid)).fetchone()
    if j and j['status'] == 'failed' and not (j['error'] or '').startswith(INTERRUPTED) and j['created_at'] >= since: return True
    return c.execute("SELECT count(*) AS n FROM jobs WHERE workspace_id=%s AND kind='watch' AND target_id=%s AND status='failed' AND finished_at>now()-interval '10 minutes'", (w, cid)).fetchone()['n'] >= 3


def scan_watches():
    """Cheap periodic scan (worker loop). Enqueues a job only for a stable, relevant change."""
    queued = 0
    with connect() as c:
        if not c.execute('SELECT pg_try_advisory_xact_lock(82419733) AS ok').fetchone()['ok']: return 0
        rows = c.execute("SELECT t.* FROM case_watches t JOIN cases k ON k.workspace_id=t.workspace_id AND k.id=t.case_id JOIN workspaces s ON s.id=t.workspace_id WHERE t.status='active' AND k.status='open' AND t.cursor_hash<>'' AND (s.expires_at IS NULL OR s.expires_at>now())").fetchall()
        for t in rows:
            w, cid = t['workspace_id'], t['case_id']
            try:
                catalog, _, ctx = context(c, {'workspace_id': w}, cid) if t['selected_evidence'] else ([], '', {'case': c.execute('SELECT * FROM cases WHERE workspace_id=%s AND id=%s', (w, cid)).fetchone()})
                cur = observe(c, w, ctx['case'], t['selected_evidence'], catalog); h = canonical(cur)
                if h == t['cursor_hash']:
                    if t['pending_hash']: c.execute('UPDATE case_watches SET pending_hash=NULL,pending_since=NULL WHERE workspace_id=%s AND case_id=%s', (w, cid))
                    continue
                if not diff(t['cursor'], cur):  # nothing relevant and material: advance silently, no inference
                    c.execute('UPDATE case_watches SET cursor=%s,cursor_hash=%s,pending_hash=NULL,pending_since=NULL,version=version+1 WHERE workspace_id=%s AND case_id=%s', (Jsonb(cur), h, w, cid)); continue
                if t['pending_hash'] != h:
                    c.execute('UPDATE case_watches SET pending_hash=%s,pending_since=now() WHERE workspace_id=%s AND case_id=%s', (h, w, cid)); continue
                if datetime.now(timezone.utc) - t['pending_since'] < timedelta(seconds=DEBOUNCE) or blocked(c, w, cid, t['updated_at']): continue
                if c.execute("SELECT count(*) AS n FROM jobs WHERE workspace_id=%s AND kind='watch' AND status IN ('queued','running')", (w,)).fetchone()['n'] >= MAX_JOBS: continue
                queued += bool(enqueue(c, w, t['actor_id'], cid))
            except Exception:
                logging.exception('Case watch scan failed for %s', cid)
    return queued


def state_of(c, w, row, case):
    if not row or row['status'] == 'disabled': return 'off'
    if row['status'] == 'paused': return 'paused'
    if case['status'] != 'open': return 'unavailable'
    j = c.execute("SELECT status,error,created_at FROM jobs WHERE workspace_id=%s AND kind='watch' AND target_id=%s ORDER BY created_at DESC LIMIT 1", (w, case['id'])).fetchone()
    if j and j['status'] in ('queued', 'running'): return 'processing'
    if j and j['status'] == 'failed' and j['created_at'] >= row['updated_at'] and not (j['error'] or '').startswith(INTERRUPTED): return 'failed'
    return 'pending' if row['pending_hash'] else 'watching'


@router.get('/cases/{cid}/watch')
def get_watch(cid: str, a=Depends(actor)):
    require(a)
    with connect() as c:
        fresh_actor(c, a['workspace_id'], a['user_id'])
        w = a['workspace_id']
        catalog, _, ctx = context(c, a, cid)
        case = ctx['case']
        row = c.execute('SELECT * FROM case_watches WHERE workspace_id=%s AND case_id=%s', (w, cid)).fetchone()
        ups = c.execute('SELECT * FROM case_watch_updates WHERE workspace_id=%s AND case_id=%s ORDER BY created_at DESC,id LIMIT 20', (w, cid)).fetchall()
        now = flat(observe(c, w, case, row['selected_evidence'] if row else [], catalog))
        for u in ups: u['stale'] = u['superseded'] or any(now.get(r['id']) != r['version'] for r in u['refs'])
        label = lambda s: s['id'] + ' · ' + s['kind'] + (' · observed ' + s['observed_at'][:10] if s['observed_at'] else '')
        return {'state': state_of(c, w, row, case), 'status': row['status'] if row else 'disabled', 'pause_reason': row['pause_reason'] if row else None,
                'evidence_ids': row['selected_evidence'] if row else [], 'updates': ups,
                'sources': [{'id': s['id'], 'label': label(s)} for s in catalog if s['kind'] != 'procedure'][:40]}


@router.post('/cases/{cid}/watch')
def set_watch(cid: str, body: WatchSettings, a=Depends(actor)):
    require(a); rate('watch:' + str(a['workspace_id']), 60)
    w = a['workspace_id']
    with connect() as c:
        c.execute('SELECT id FROM workspaces WHERE id=%s FOR UPDATE', (w,)); fresh_actor(c, w, a['user_id'])
        catalog, _, ctx = context(c, a, cid)
        case = ctx['case']
        if body.status == 'active' and case['status'] != 'open': raise HTTPException(409, 'Resolved cases cannot be watched. Reopen the case first.')
        try: chosen = select_sources(catalog, body.evidence_ids, case)
        except ValueError as e: raise HTTPException(422, str(e))
        if any(x['kind'] == 'procedure' for x in chosen): raise HTTPException(422, 'Select case records or observations, not procedures.')
        old = c.execute('SELECT * FROM case_watches WHERE workspace_id=%s AND case_id=%s FOR UPDATE', (w, cid)).fetchone()
        if body.status == 'active' and (not old or old['status'] != 'active') and c.execute("SELECT count(*) AS n FROM case_watches WHERE workspace_id=%s AND status='active'", (w,)).fetchone()['n'] >= MAX_WATCHES:
            raise HTTPException(429, f'At most {MAX_WATCHES} cases can be watched at once. Pause or disable another watch.')
        cur = observe(c, w, case, body.evidence_ids, catalog)  # settings changes re-baseline: only later changes are reported
        c.execute("""INSERT INTO case_watches(workspace_id,case_id,status,actor_id,selected_evidence,cursor,cursor_hash) VALUES(%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(workspace_id,case_id) DO UPDATE SET status=EXCLUDED.status,actor_id=EXCLUDED.actor_id,selected_evidence=EXCLUDED.selected_evidence,cursor=EXCLUDED.cursor,cursor_hash=EXCLUDED.cursor_hash,
            pending_hash=NULL,pending_since=NULL,pause_reason=NULL,version=case_watches.version+1,updated_at=now()""",
                  (w, cid, body.status, a['user_id'], Jsonb(body.evidence_ids), Jsonb(cur), canonical(cur)))
        from release_api import audit
        audit(c, a, cid, 'case_watch_' + body.status, payload={'evidence_ids': body.evidence_ids})
    return get_watch(cid, a)


@router.post('/cases/{cid}/watch/retry')
def retry_watch(cid: str, a=Depends(actor)):
    require(a); rate('watch-retry:' + str(a['workspace_id']), 30)
    w = a['workspace_id']
    with connect() as c:
        fresh_actor(c, w, a['user_id'])
        row = c.execute('SELECT * FROM case_watches WHERE workspace_id=%s AND case_id=%s FOR UPDATE', (w, cid)).fetchone()
        if not row or row['status'] != 'active': raise HTTPException(409, 'Watch is not active.')
        c.execute('UPDATE case_watches SET updated_at=now(),pending_hash=NULL,pending_since=NULL WHERE workspace_id=%s AND case_id=%s', (w, cid))
        enqueue(c, w, row['actor_id'], cid)
    return get_watch(cid, a)
