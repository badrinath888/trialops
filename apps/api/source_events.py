"""Document-processing automation over MOCK sources only (synthetic fixtures; no real vendor, no remote URL).
A source-authenticated event is stored immutably, routed only by exact source-scoped identifiers or reviewer-confirmed links, saved as Document journey
evidence (journey_exports), reassessed by the existing journey/priority engines, and shown through the existing Case watch update list.
Nothing here confirms linkage, accepts responses, approves, sends, resolves or reopens a case. Routing, matching and verification are deterministic."""
import hashlib, json, logging, secrets
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import ValidationError
from db import connect
from models import Model
from security import actor, rate, require
from workflows import canonical
from journey import (IDENT, LABEL, T, canon, classify, current_journey, example_export, identity, load, normalize_export, save_assessment, case_for, audit)

router = APIRouter()
ADAPTERS = {"mock_portal": "mock-upload-portal", "mock_hub": "mock-binder-hub"}
MAX_BYTES, MAX_SOURCES, MAX_PENDING, MAX_ATTEMPTS = 64_000, 5, 200, 3
BACKOFF = (5, 20, 60)  # seconds before the next automatic attempt
SYSTEM_ACTOR = {"user_id": None, "name": "Source automation", "role": "owner"}
WORDS = ("No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine")
SUPPORTED_DRAFT = ("no_record", "export_incomplete")  # structured gaps that name an exact record to request
SCENARIOS = ("processing_completed", "duplicate_delivery", "conflicting_event_id", "older_observation", "wrong_version", "unmatched_document")


class SourceCreate(Model):
    name: T(3, 60)
    adapter: Literal["mock_portal", "mock_hub"]


class SourceStatus(Model):
    status: Literal["enabled", "paused", "revoked"]


class EventIn(Model):
    schema_version: Literal["1"]
    event_id: T(1, 100, "^" + IDENT.pattern + "$")
    source_rev: int
    observed_at: datetime
    export: dict
    mapping: dict


class Automation(Model):
    draft_preparation: bool


class MockEvent(Model):
    case_id: T(1, 100)
    scenario: Literal[SCENARIOS]


def digest(v):
    return hashlib.sha256(v.encode()).hexdigest()


def owner(c, a):
    from five_features import current
    require({**a, "role": current(c, a)}, ("owner",))


def reviewer(c, a):
    from five_features import current
    require({**a, "role": current(c, a)})


# ------------------------------------------------------------------ ingestion
def validate(src, ev):
    """Structured validation before anything is stored. Raises ValueError (422)."""
    if not 1 <= ev.source_rev <= 1_000_000:
        raise ValueError("source_rev must be between 1 and 1,000,000")
    if ev.observed_at.tzinfo is None:
        raise ValueError("observed_at needs a timezone")
    n = normalize_export(ev.export, ev.mapping)
    if n["source_system"] != ADAPTERS[src["adapter"]]:
        raise ValueError("The export's source_system does not match this source connection")
    if datetime.fromisoformat(n["observed_at"]) != ev.observed_at:
        raise ValueError("Event observed_at must equal the export observation time")
    return n


def accept(src, ev):
    """Store one authenticated event. Returns (http_status, body). Duplicate = same content under the same event id; different content = quarantined."""
    w = src["workspace_id"]
    n = validate(src, ev)
    study, site = ev.export.get("study_id"), ev.export.get("site_id")
    chash = digest(canon({"schema_version": ev.schema_version, "source_rev": ev.source_rev, "observed_at": n["observed_at"], "export": ev.export, "mapping": ev.mapping}))
    with connect() as c:
        if not c.execute("SELECT 1 FROM sites WHERE workspace_id=%s AND id=%s AND study_id=%s", (w, site, study)).fetchone():
            raise ValueError("Study/site relationship is outside this workspace")
        live = c.execute("SELECT status FROM source_connections WHERE workspace_id=%s AND id=%s FOR SHARE", (w, src["id"])).fetchone()
        if not live or live["status"] != "enabled":
            raise PermissionError("Source is not enabled")
        if c.execute("SELECT count(*) AS n FROM source_events WHERE workspace_id=%s AND status='received'", (w,)).fetchone()["n"] >= MAX_PENDING:
            raise OverflowError("Too many events are waiting for processing")
        eid = uuid4()
        row = c.execute("""INSERT INTO source_events(workspace_id,id,source_id,external_id,source_rev,observed_at,schema_version,content_hash,payload)
                           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(workspace_id,source_id,external_id) DO NOTHING RETURNING id""",
                        (w, eid, src["id"], ev.event_id, ev.source_rev, n["observed_at"], ev.schema_version, chash,
                         Jsonb({"export": ev.export, "mapping": ev.mapping}))).fetchone()
        if row:
            c.execute("INSERT INTO jobs(id,workspace_id,actor_id,kind,target_id) VALUES(%s,%s,%s,'source_event',%s) ON CONFLICT DO NOTHING", (uuid4(), w, src["actor_id"], str(eid)))
            return 202, {"status": "accepted", "id": str(eid)}
        old = c.execute("SELECT id,content_hash FROM source_events WHERE workspace_id=%s AND source_id=%s AND external_id=%s FOR UPDATE", (w, src["id"], ev.event_id)).fetchone()
        if old["content_hash"] == chash:
            c.execute("UPDATE source_events SET duplicates=duplicates+1 WHERE workspace_id=%s AND id=%s", (w, old["id"]))
            return 200, {"status": "duplicate", "id": str(old["id"])}
        if not c.execute("SELECT 1 FROM source_event_conflicts WHERE workspace_id=%s AND event_id=%s AND content_hash=%s", (w, old["id"], chash)).fetchone():
            c.execute("INSERT INTO source_event_conflicts(workspace_id,id,event_id,content_hash,payload) VALUES(%s,%s,%s,%s,%s)", (w, uuid4(), old["id"], chash, Jsonb({"export": ev.export, "mapping": ev.mapping})))
            c.execute("UPDATE source_connections SET last_error='A delivery reused an event ID with different content and was quarantined.',last_error_at=now() WHERE workspace_id=%s AND id=%s", (w, src["id"]))
        return 409, {"status": "quarantined", "detail": "This event ID already holds different content; the new delivery was quarantined and nothing was changed."}


def source_auth(request: Request):
    key = request.headers.get("x-source-key", "")
    row = None
    if key.startswith("tos_") and len(key) < 120:
        with connect() as c:
            row = c.execute("SELECT * FROM source_connections WHERE token_hash=%s", (digest(key),)).fetchone()
    if not row or row["status"] == "revoked":
        raise HTTPException(401, "Source key rejected.")
    if row["status"] != "enabled":
        raise HTTPException(403, "This source is paused.")
    return row


@router.post("/sources/events")
async def post_event(request: Request, src=Depends(source_auth)):
    rate("source-event:" + str(src["id"]), 120, 60)
    raw = await request.body()
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "Event payload exceeds %d bytes." % MAX_BYTES)
    try:
        ev = EventIn.model_validate_json(raw)
        status, body = accept(src, ev)
    except ValidationError as e:
        raise HTTPException(422, "Malformed event: " + "; ".join("%s: %s" % (".".join(map(str, x["loc"])), x["msg"]) for x in e.errors()[:3]))
    except ValueError as e:
        raise HTTPException(422, str(e))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except OverflowError as e:
        raise HTTPException(429, str(e))
    if status == 409:
        raise HTTPException(409, body["detail"])
    return JSONResponse(body, status_code=status)


# ------------------------------------------------------------------ routing + reassessment (worker)
def stage_sig(j):
    return {s["stage"]: (s["operational_status"], s["assessment"]) for s in j["stages"]}  # a re-observation of the same status is evidence, not a changed check


def sig_of(check, stages):
    return (check["resolved"], check["applicable"], stages.get(check["stage"]) if check["stage"] else None)


def route(c, w, n, export):
    """Exact routing only. Returns ('matched', case, subject, links) or ('unmatched'|'ambiguous', reason)."""
    study, site = export["study_id"], export["site_id"]
    hits, reason = [], "no_exact_mapping"
    for case in c.execute("SELECT * FROM cases WHERE workspace_id=%s AND study_id=%s AND site_id=%s AND status='open' ORDER BY id", (w, study, site)).fetchall():
        subj = c.execute("SELECT * FROM journey_subjects WHERE workspace_id=%s AND case_id=%s ORDER BY rev DESC LIMIT 1", (w, case["id"])).fetchone()
        if not subj:
            continue
        links = c.execute("SELECT * FROM journey_links WHERE workspace_id=%s AND case_id=%s", (w, case["id"])).fetchall()
        for l in links:
            l["id"] = str(l["id"])
        ok = False
        for r in n["records"]:
            basis, _ = identity(r, subj, links)
            if basis in ("native", "reviewer_link"):
                if r["version"] is not None and r["version"] != subj["document_version"]:
                    reason = "wrong_version"
                elif classify(r, subj, links)["exact"]:
                    ok = True
        if ok:
            hits.append((case, subj, links))
    if len(hits) == 1:
        return ("matched",) + hits[0]
    return ("ambiguous", "multiple_exact_cases") if hits else ("unmatched", reason)


def word(n):
    return WORDS[n] if n < len(WORDS) else str(n)


def refs_of(j, stages):
    return [{"ref": r["ref"], "source_system": r["source_system"], "source_ref": r["source_ref"], "status": r["status"], "observed_at": r["observed_at"], "stage": s["stage"], "role": r["role"]}
            for s in j["stages"] if s["stage"] in stages for r in s["records"]]


def finish(c, job):
    c.execute("UPDATE jobs SET status='completed',finished_at=now() WHERE id=%s AND lease_token=%s AND status='running'", (job["id"], job["lease_token"]))


def holds(c, job):
    lease = c.execute("SELECT status,lease_token FROM jobs WHERE id=%s FOR UPDATE", (job["id"],)).fetchone()
    return bool(lease and lease["status"] == "running" and lease["lease_token"] == job["lease_token"])


def set_event(c, w, eid, status, reason=None, case_id=None, result=None):
    c.execute("UPDATE source_events SET status=%s,reason=%s,case_id=coalesce(%s,case_id),result=coalesce(%s,result),processed_at=now() WHERE workspace_id=%s AND id=%s",
              (status, reason, case_id, Jsonb(result) if result is not None else None, w, eid))


def process_source_event(job):
    from priority import compute
    w, eid = job["workspace_id"], UUID(job["target_id"])
    with connect() as c:  # attempt accounting is committed before any work so a crash still counts
        if not holds(c, job):
            return
        ev = c.execute("SELECT * FROM source_events WHERE workspace_id=%s AND id=%s FOR UPDATE", (w, eid)).fetchone()
        src = c.execute("SELECT * FROM source_connections WHERE workspace_id=%s AND id=%s", (w, ev["source_id"])).fetchone() if ev else None
        if not ev or ev["status"] != "received":
            return finish(c, job)
        if not src or src["status"] == "revoked":
            set_event(c, w, eid, "ignored", "source_revoked")
            return finish(c, job)
        if src["status"] == "paused":  # stays queued as evidence of receipt; resumes when the source is enabled again
            c.execute("UPDATE source_events SET reason='source_paused' WHERE workspace_id=%s AND id=%s", (w, eid))
            return finish(c, job)
        if ev["attempts"] >= MAX_ATTEMPTS:
            set_event(c, w, eid, "failed", "retries_exhausted")
            return finish(c, job)
        c.execute("UPDATE source_events SET attempts=attempts+1,next_attempt_at=now()+(%s * interval '1 second') WHERE workspace_id=%s AND id=%s", (BACKOFF[min(ev["attempts"], 2)], w, eid))
    try:
        phase = evidence_phase(job, ev, src, compute) if not (ev["result"] or {}).get("phase") else (ev["result"], ev["case_id"])
    except Exception:
        logging.exception("Source event %s failed", eid)
        with connect() as c:
            c.execute("UPDATE source_connections SET last_error='Processing a source event failed; it will be retried a bounded number of times.',last_error_at=now() WHERE workspace_id=%s AND id=%s", (w, src["id"]))
        raise
    if phase is None:
        return
    result, cid = phase
    draft = prepare_draft(w, eid, cid, result, src)
    with connect() as c:
        if not holds(c, job):
            return
        if draft:
            result = {**result, "draft": draft}
            c.execute("UPDATE case_watch_updates SET detail=jsonb_set(detail,'{draft}',%s) WHERE workspace_id=%s AND source_event_id=%s", (Jsonb(draft), w, eid))
        set_event(c, w, eid, "processed", None, None, {**result, "phase": "done"})
        c.execute("UPDATE source_connections SET last_success_at=now(),last_error=NULL,last_error_at=NULL WHERE workspace_id=%s AND id=%s", (w, src["id"]))
        finish(c, job)


def evidence_phase(job, ev, src, compute):
    """One transaction: route, save evidence, reassess, write the update + notification. Idempotent: the event row records the outcome."""
    w, eid = job["workspace_id"], ev["id"]
    payload = ev["payload"]
    n = normalize_export(payload["export"], payload["mapping"])
    with connect() as c:
        if not holds(c, job):
            return None
        cur = c.execute("SELECT * FROM source_events WHERE workspace_id=%s AND id=%s FOR UPDATE", (w, eid)).fetchone()
        s = c.execute("SELECT status FROM source_connections WHERE workspace_id=%s AND id=%s FOR SHARE", (w, src["id"])).fetchone()
        if cur["status"] != "received" or not s or s["status"] != "enabled":  # revoked/paused while queued: discard, persist nothing
            if cur["status"] == "received" and s and s["status"] == "revoked":
                set_event(c, w, eid, "ignored", "source_revoked")
            finish(c, job)
            return None
        routed = route(c, w, n, payload["export"])
        if routed[0] != "matched":
            set_event(c, w, eid, routed[0], routed[1])
            finish(c, job)
            return None
        _, case, subj, links = routed
        cid = case["id"]
        a = {"workspace_id": w, **SYSTEM_ACTOR}
        item = case_for(c, a, cid, True)  # serializes work on this case
        j0, pr0 = current_journey(c, a, item)[0], compute(c, a, item)
        sha = hashlib.sha256(canon({"export": payload["export"], "mapping": payload["mapping"]}).encode()).hexdigest()
        old = c.execute("SELECT id,content_hash FROM journey_exports WHERE workspace_id=%s AND source_system=%s AND export_ref=%s FOR UPDATE", (w, n["source_system"], n["export_ref"])).fetchone()
        if old and old["content_hash"] != sha:
            set_event(c, w, eid, "failed", "evidence_conflict", cid)  # same export reference, different immutable content: nothing overwritten
            c.execute("UPDATE source_connections SET last_error='An export reference already holds different evidence; the event was not applied.',last_error_at=now() WHERE workspace_id=%s AND id=%s", (w, src["id"]))
            finish(c, job)
            return None
        export_id = old["id"] if old else uuid4()
        if not old:
            c.execute("INSERT INTO journey_exports(workspace_id,id,study_id,site_id,source_system,export_ref,observed_at,coverage,mapping,records,content_hash,actor_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL)",
                      (w, export_id, payload["export"]["study_id"], payload["export"]["site_id"], n["source_system"], n["export_ref"], n["observed_at"], Jsonb(n["coverage"]), Jsonb(payload["mapping"]), Jsonb(n["records"]), sha))
        j1, pr1 = current_journey(c, a, item)[0], compute(c, a, item)
        s0, s1 = stage_sig(j0), stage_sig(j1)
        stages_changed = [k for k in s1 if s0.get(k) != s1[k]]
        b0 = {x["key"]: sig_of(x, s0) for x in pr0["checks"]}
        changed = [x for x in pr1["checks"] if x["applicable"] and b0.get(x["key"]) != sig_of(x, s1)]
        aid = save_assessment(c, a, cid, j1)
        unknown = [("%s: %s" % (s["label"], "conflicting sources" if s["assessment"] == "conflicting" else "unknown")) + (" — " + s["missing"][0] if s["missing"] and s["assessment"] != "conflicting" else "") for s in j1["stages"] if s["assessment"] != "verified"]
        notes = [x for s in j1["stages"] if s["stage"] in stages_changed for x in s["notes"]]
        cand = next((x for x in pr1["candidates"] if x["state"] == "ready"), None) or next(iter(pr1["candidates"]), None)
        saved = c.execute("SELECT input_hash FROM journey_prioritizations WHERE workspace_id=%s AND case_id=%s ORDER BY rev DESC LIMIT 1", (w, cid)).fetchone()
        nchg = len(changed)
        action = ("Suggested next request: %s (%s). %s" % (cand["description"], cand["state"], cand["explanation"])) if cand else "No open request candidate. Review the journey and decide whether a human assessment is needed."
        result = {"phase": "evidence_saved", "export_id": str(export_id), "assessment_id": str(aid), "stages_changed": stages_changed, "checks_updated": nchg,
                  "candidate": ({"key": cand["key"], "stage": cand["stage"], "state": cand["state"], "target": cand["target"], "question": cand["question"], "would_settle": cand["would_settle"],
                                 "existing": cand["existing"], "code": cand["key"].split(":")[0]} if cand else None), "ranking_stale": bool(saved and saved["input_hash"] != pr1["hash"]),
                  "considered": [{"key": x["key"], "state": x["state"], "existing": bool(x["existing"])} for x in (pr1["candidates"] + pr1["waiting"])[:8]],
                  "unresolved_checks": [x["key"] for x in pr1["checks"] if x["applicable"] and not x["resolved"]][:12],
                  "older_than_current": not stages_changed and not old}
        c.execute("UPDATE source_events SET case_id=%s,result=%s WHERE workspace_id=%s AND id=%s", (cid, Jsonb(result), w, eid))  # status flips to processed after the draft phase
        if nchg:
            body = {"changes": ["New evidence received. %s %s updated. Review changes." % (word(nchg), "check" if nchg == 1 else "checks")] +
                              ["Source %s (%s), observed %s: %d record(s) saved as immutable evidence." % (src["name"], n["source_system"], n["observed_at"][:16].replace("T", " "), len(n["records"]))] +
                              ["%s: %s" % (x["label"], "now resolved" if x["resolved"] else "assessment changed, not resolved") for x in changed[:6]],
                    "uncertain": (unknown + notes + ["Recorded evidence does not establish root cause or resolution; the case stays open until a human resolves it."])[:8], "next_action": action}
            ref = lambda j, st: refs_of(j, set(st) | {s for s in stages_changed})
            detail = {"source": {"id": str(src["id"]), "name": src["name"], "adapter": src["adapter"], "event_id": ev["external_id"], "source_rev": ev["source_rev"], "observed_at": n["observed_at"],
                                 "received_at": ev["received_at"].isoformat(), "content_hash": ev["content_hash"], "schema_version": ev["schema_version"]},
                      "checks_updated": [{"key": x["key"], "label": x["label"], "resolved": x["resolved"]} for x in changed], "stages_changed": stages_changed,
                      "evidence_before": ref(j0, stages_changed), "evidence_after": ref(j1, stages_changed), "ranking_stale": result["ranking_stale"], "draft": None}
            rid = uuid4()
            made = c.execute("""INSERT INTO case_watch_updates(workspace_id,id,case_id,trigger_key,state_hash,changes,uncertain,next_action,refs,model,source_event_id,detail)
                                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id""",
                             (w, rid, cid, canonical(["source_event", str(eid)]), j1["fingerprint"], Jsonb(body["changes"]), Jsonb(body["uncertain"]), body["next_action"], Jsonb([]),
                              Jsonb({"engine": "none", "status": "not_needed"}), eid, Jsonb(detail))).fetchone()
            if made:
                c.execute("UPDATE case_watch_updates SET superseded=true WHERE workspace_id=%s AND case_id=%s AND id<>%s", (w, cid, rid))
                notify(c, w, src, case, j1["fingerprint"], nchg)
                audit(c, a, cid, "source_update_processed", "", {"update_id": str(rid), "source_event": str(eid), "source_id": str(src["id"]), "checks_updated": nchg, "stages_changed": stages_changed,
                                                                     "no_message_sent": True, "no_resolution": True})
        else:
            audit(c, a, cid, "source_update_recorded", "", {"source_event": str(eid), "checks_updated": 0, "note": "Evidence saved; no check changed."})
        return result, cid


def notify(c, w, src, case, fp, n):
    uid = src["actor_id"]
    if not uid or not c.execute("SELECT 1 FROM memberships WHERE workspace_id=%s AND user_id=%s AND role IN ('owner','reviewer')", (w, uid)).fetchone():
        return
    pref = c.execute("SELECT enabled FROM notification_preferences WHERE workspace_id=%s AND user_id=%s", (w, uid)).fetchone()
    if pref and not pref["enabled"]:
        return
    if c.execute("SELECT 1 FROM notifications WHERE workspace_id=%s AND user_id=%s AND case_id=%s AND kind='watch' AND dedupe_key LIKE 'source-update:%%' AND read_at IS NULL", (w, uid, case["id"])).fetchone():
        return  # one unread actionable notification per case; the update list holds the detail
    c.execute("INSERT INTO notifications(workspace_id,user_id,id,dedupe_key,kind,title,case_id) VALUES(%s,%s,%s,%s,'watch',%s,%s) ON CONFLICT DO NOTHING",
              (w, uid, uuid4(), "source-update:%s:%s" % (case["id"], fp[:16]), ("New evidence on %s: %s updated. Review changes." % (case["title"][:120], "%d check%s" % (n, "" if n == 1 else "s"))), case["id"]))


def prepare_draft(w, eid, cid, result, src):
    """Optional, off by default. Uses the owner's current permission and the existing collection workflow; the draft is never sent."""
    cand = result["candidate"]
    with connect() as c:
        st = c.execute("SELECT draft_preparation,actor_id FROM automation_settings WHERE workspace_id=%s", (w,)).fetchone()
    if not st or not st["draft_preparation"]:
        return None
    why = ("No open check needs a request, so no draft was prepared." if not cand else
           "A request for the suggested check already exists; no new draft was prepared." if cand["existing"] else
           "The suggested check is not ready for a request (%s); no draft was prepared." % cand["state"] if cand["state"] != "ready" else
           "This kind of check cannot be drafted automatically; the suggestion is shown only." if cand["code"] not in SUPPORTED_DRAFT else None)
    if why:
        return {"state": "not_prepared", "reason": why}
    from assessments import fresh_actor
    from journey import Collection, draft_collection
    try:
        with connect() as c:
            a = fresh_actor(c, w, st["actor_id"])
            if a["role"] != "owner" or not c.execute("SELECT 1 FROM runs WHERE workspace_id=%s AND case_id=%s LIMIT 1", (w, cid)).fetchone():
                return {"state": "not_prepared", "reason": "No investigation run or no current owner permission; suggestion only."}
        key = "%s:%s:%s" % (eid, cand["key"], cand["stage"])
        body = Collection(id=uuid5(NAMESPACE_URL, "plan:" + key), request_id=uuid5(NAMESPACE_URL, "request:" + key), stage=cand["stage"], gap_key=cand["key"], question=cand["question"], would_settle=cand["would_settle"])
        item = draft_collection(cid, body, a)
        return {"state": "prepared", "plan_item_id": str(item["id"]), "request_id": str(item["request_id"]), "unsent": True}
    except HTTPException as e:
        return {"state": "not_prepared", "reason": str(e.detail)[:200]}


# ------------------------------------------------------------------ scheduler (worker loop)
def scan_sources():
    """Re-queue received events that have no live job (worker restart, interrupted lease, backoff elapsed); fail those out of attempts."""
    queued = 0
    with connect() as c:
        if not c.execute("SELECT pg_try_advisory_xact_lock(82419737) AS ok").fetchone()["ok"]:
            return 0
        c.execute("""UPDATE source_events e SET status='ignored',reason='source_revoked',processed_at=now() FROM source_connections s
                     WHERE (s.workspace_id,s.id)=(e.workspace_id,e.source_id) AND e.status='received' AND s.status='revoked'""")
        for e in c.execute("""SELECT e.workspace_id,e.id,e.attempts,s.actor_id FROM source_events e JOIN source_connections s ON (s.workspace_id,s.id)=(e.workspace_id,e.source_id)
                              WHERE e.status='received' AND s.status='enabled' AND (e.next_attempt_at IS NULL OR e.next_attempt_at<=now())
                              AND NOT EXISTS(SELECT 1 FROM jobs j WHERE j.workspace_id=e.workspace_id AND j.kind='source_event' AND j.target_id=e.id::text AND j.status IN ('queued','running'))
                              ORDER BY e.received_at LIMIT 50""").fetchall():
            if e["attempts"] >= MAX_ATTEMPTS:
                set_event(c, e["workspace_id"], e["id"], "failed", "retries_exhausted")
                c.execute("UPDATE source_connections s SET last_error='A source event failed after the maximum number of attempts.',last_error_at=now() FROM source_events x WHERE x.id=%s AND (s.workspace_id,s.id)=(x.workspace_id,x.source_id)", (e["id"],))
                continue
            queued += bool(c.execute("INSERT INTO jobs(id,workspace_id,actor_id,kind,target_id) VALUES(%s,%s,%s,'source_event',%s) ON CONFLICT DO NOTHING RETURNING id", (uuid4(), e["workspace_id"], e["actor_id"], str(e["id"]))).fetchone())
    return queued


# ------------------------------------------------------------------ settings, mock producer, activity, review
def source_view(s):
    return {"id": str(s["id"]), "name": s["name"], "adapter": s["adapter"], "system": ADAPTERS[s["adapter"]], "status": s["status"], "last_success_at": s["last_success_at"],
            "last_error": s["last_error"], "last_error_at": s["last_error_at"], "created_at": s["created_at"]}


@router.get("/sources")
def list_sources(a=Depends(actor)):
    with connect() as c:
        reviewer(c, a)
        w = a["workspace_id"]
        is_owner = a["role"] == "owner"
        evs = c.execute("""SELECT e.id,e.external_id,e.source_rev,e.status,e.reason,e.case_id,e.observed_at,e.received_at,e.duplicates,e.attempts,s.name AS source_name,
                           (SELECT count(*) FROM source_event_conflicts k WHERE k.workspace_id=e.workspace_id AND k.event_id=e.id) AS conflicts
                           FROM source_events e JOIN source_connections s ON (s.workspace_id,s.id)=(e.workspace_id,e.source_id) WHERE e.workspace_id=%s
                           AND (e.status<>'processed' OR e.received_at>now()-interval '1 day') ORDER BY e.received_at DESC LIMIT 25""", (w,)).fetchall()
        row = c.execute("SELECT draft_preparation FROM automation_settings WHERE workspace_id=%s", (w,)).fetchone()
        return {"sources": [source_view(s) for s in c.execute("SELECT * FROM source_connections WHERE workspace_id=%s ORDER BY created_at", (w,)).fetchall()],
                "events": evs, "draft_preparation": bool(row and row["draft_preparation"]), "can_configure": is_owner, "scenarios": list(SCENARIOS),
                "activity": activity(c, w)}


@router.post("/sources", status_code=201)
def create_source(body: SourceCreate, a=Depends(actor)):
    rate("source-config:" + str(a["workspace_id"]), 30)
    with connect() as c:
        owner(c, a)
        w = a["workspace_id"]
        c.execute("SELECT id FROM workspaces WHERE id=%s FOR UPDATE", (w,))
        if c.execute("SELECT count(*) AS n FROM source_connections WHERE workspace_id=%s AND status<>'revoked'", (w,)).fetchone()["n"] >= MAX_SOURCES:
            raise HTTPException(409, "At most %d active mock sources per workspace." % MAX_SOURCES)
        key = "tos_" + secrets.token_urlsafe(32)
        row = c.execute("INSERT INTO source_connections(workspace_id,id,name,adapter,status,token_hash,actor_id) VALUES(%s,%s,%s,%s,'enabled',%s,%s) RETURNING *", (w, uuid4(), body.name, body.adapter, digest(key), a["user_id"])).fetchone()
        return {**source_view(row), "source_key": key, "key_note": "Shown once. Mock source only; do not use for a real system."}


@router.post("/sources/{sid}/status")
def set_status(sid: UUID, body: SourceStatus, a=Depends(actor)):
    with connect() as c:
        owner(c, a)
        row = c.execute("SELECT * FROM source_connections WHERE workspace_id=%s AND id=%s FOR UPDATE", (a["workspace_id"], sid)).fetchone()
        if not row:
            raise HTTPException(404, "Source not found.")
        if row["status"] == "revoked":
            raise HTTPException(409, "A revoked source cannot be re-enabled. Create a new source.")
        row = c.execute("UPDATE source_connections SET status=%s,updated_at=now() WHERE workspace_id=%s AND id=%s RETURNING *", (body.status, a["workspace_id"], sid)).fetchone()
        return source_view(row)


@router.post("/sources/automation")
def set_automation(body: Automation, a=Depends(actor)):
    with connect() as c:
        owner(c, a)
        c.execute("INSERT INTO automation_settings(workspace_id,draft_preparation,actor_id) VALUES(%s,%s,%s) ON CONFLICT(workspace_id) DO UPDATE SET draft_preparation=EXCLUDED.draft_preparation,actor_id=EXCLUDED.actor_id,updated_at=now()",
                  (a["workspace_id"], body.draft_preparation, a["user_id"]))
        return {"draft_preparation": body.draft_preparation}


def fixture(src, case_row, subj, scenario, last):
    """Locally controlled synthetic events built from this case's own document reference. No network, no remote URL."""
    shape = "portal" if src["adapter"] == "mock_portal" else "hub"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    tag = uuid4().hex[:10]
    ref = "%s-%s" % (str(src["id"])[:8], tag)
    study, site = case_row["study_id"], case_row["site_id"]
    if scenario in ("duplicate_delivery", "conflicting_event_id"):
        if not last:
            raise ValueError("Send an event first.")
        p = last["payload"]
        ev = {"schema_version": last["schema_version"], "event_id": last["external_id"], "source_rev": last["source_rev"], "observed_at": last["observed_at"].isoformat(), **p}
        if scenario == "conflicting_event_id":
            ev["source_rev"] += 1
        return ev
    stage_rows = None
    if shape == "portal":
        d, v = subj["document_ref"], subj["document_version"]
        if scenario == "wrong_version":
            v = "99"
        if scenario == "unmatched_document":
            d = "DOC-UNRELATED-1"
        t = now.isoformat() if scenario != "older_observation" else (now.replace(year=now.year - 1)).isoformat()
        stage_rows = [{"event": "RECEIPT", "receipt_no": "RCPT-" + tag[:6], "doc_id": d, "doc_rev": v, "state": "RECEIVED", "at": t},
                      {"event": "PROCESS", "receipt_no": "PROC-" + tag[:6], "doc_id": d, "doc_rev": v, "state": "DONE", "at": t}]
        when = datetime.fromisoformat(t)
    else:
        d, v = subj["document_ref"], subj["document_version"]
        if scenario == "wrong_version":
            v = "99"
        if scenario == "unmatched_document":
            d = "DOC-UNRELATED-1"
        when = now if scenario != "older_observation" else now.replace(year=now.year - 1)
        t = when.isoformat()
        stage_rows = [{"kind": "sync_job", "job": {"id": "JOB-" + tag[:6]}, "item": {"upstream": d, "rev": v}, "outcome": "ok", "when": t, "target": subj["binder_ref"]}]
    out = example_export(shape, study, site, subj, ref=ref, observed_at=when, rows=stage_rows)
    if shape == "hub":  # this mock hub event only covers transfer; filing and visibility stay unknown unless separately reported
        out["export"]["coverage"]["stages"] = ["transfer"]
    return {"schema_version": "1", "event_id": "EVT-" + tag, "source_rev": 1, "observed_at": out["export"]["observed_at"], "export": out["export"], "mapping": out["mapping"]}


@router.post("/sources/{sid}/mock-event")
def mock_event(sid: UUID, body: MockEvent, a=Depends(actor)):
    """Mock producer: builds a synthetic event and delivers it through the same validation and storage as the authenticated endpoint."""
    rate("source-mock:" + str(a["workspace_id"]), 60)
    with connect() as c:
        owner(c, a)
        w = a["workspace_id"]
        src = c.execute("SELECT * FROM source_connections WHERE workspace_id=%s AND id=%s", (w, sid)).fetchone()
        if not src:
            raise HTTPException(404, "Source not found.")
        if src["status"] != "enabled":
            raise HTTPException(409, "Enable the source first.")
        case_row = case_for(c, a, body.case_id)
        subj = current_journey(c, a, case_row)[1]
        if not subj:
            raise HTTPException(409, "Define the case's document and intended binder in its Document journey first.")
        last = c.execute("SELECT * FROM source_events WHERE workspace_id=%s AND source_id=%s ORDER BY received_at DESC LIMIT 1", (w, sid)).fetchone()
    try:
        ev = EventIn.model_validate(fixture(src, case_row, subj, body.scenario, last))
        status, out = accept(src, ev)
    except ValueError as e:
        raise HTTPException(409 if "Send an event" in str(e) else 422, str(e))
    return {"delivery": out["status"], "http_status": status, "id": out.get("id"), "scenario": body.scenario}


def activity(c, w):
    """Counts of recorded events only. They do not measure time saved."""
    n = lambda q, *p: c.execute(q, (w,) + p).fetchone()["n"]
    ev = {r["status"]: r["n"] for r in c.execute("SELECT status,count(*) AS n FROM source_events WHERE workspace_id=%s GROUP BY status", (w,)).fetchall()}
    kinds = {r["event_type"]: r["n"] for r in c.execute("SELECT event_type,count(*) AS n FROM case_events WHERE workspace_id=%s AND event_type IN ('source_update_processed','source_update_reviewed','source_update_recorded','source_draft_prepared') GROUP BY event_type", (w,)).fetchall()}
    done = c.execute("SELECT result FROM source_events WHERE workspace_id=%s AND status='processed'", (w,)).fetchall()
    return {"received": sum(ev.values()), "deduplicated": n("SELECT coalesce(sum(duplicates),0) AS n FROM source_events WHERE workspace_id=%s"), "quarantined": n("SELECT count(*) AS n FROM source_event_conflicts WHERE workspace_id=%s"),
            "unmatched": ev.get("unmatched", 0) + ev.get("ambiguous", 0), "failed": ev.get("failed", 0), "processed": ev.get("processed", 0), "waiting": ev.get("received", 0),
            "affected_cases": n("SELECT count(DISTINCT case_id) AS n FROM source_events WHERE workspace_id=%s AND status='processed'"), "checks_updated": sum((r["result"] or {}).get("checks_updated", 0) for r in done),
            "suggestions": sum(1 for r in done if (r["result"] or {}).get("candidate")), "drafts_prepared": sum(1 for r in done if ((r["result"] or {}).get("draft") or {}).get("state") == "prepared"),
            "reviewer_actions": kinds.get("source_update_reviewed", 0), "note": "Counts of recorded events. They are not time-saved figures."}


@router.post("/sources/events/{eid}/reroute")
def reroute(eid: UUID, a=Depends(actor)):
    """Explicit review: re-run exact routing for an unmatched/ambiguous event (e.g. after a reviewer confirmed a link). Creates no case and links nothing."""
    rate("source-reroute:" + str(a["workspace_id"]), 30)
    with connect() as c:
        reviewer(c, a)
        w = a["workspace_id"]
        ev = c.execute("SELECT * FROM source_events WHERE workspace_id=%s AND id=%s FOR UPDATE", (w, eid)).fetchone()
        if not ev:
            raise HTTPException(404, "Event not found.")
        if ev["status"] not in ("unmatched", "ambiguous"):
            raise HTTPException(409, "Only unmatched or ambiguous events can be re-evaluated.")
        c.execute("UPDATE source_events SET status='received',reason=NULL,attempts=0,next_attempt_at=NULL,processed_at=NULL WHERE workspace_id=%s AND id=%s", (w, eid))
        c.execute("INSERT INTO jobs(id,workspace_id,actor_id,kind,target_id) VALUES(%s,%s,%s,'source_event',%s) ON CONFLICT DO NOTHING", (uuid4(), w, a["user_id"], str(eid)))
        return {"status": "queued"}


@router.post("/cases/{cid}/watch/updates/{uid}/review")
def review_update(cid: str, uid: UUID, a=Depends(actor)):
    with connect() as c:
        reviewer(c, a)
        w = a["workspace_id"]
        case_for(c, a, cid)
        u = c.execute("SELECT id,source_event_id FROM case_watch_updates WHERE workspace_id=%s AND case_id=%s AND id=%s", (w, cid, uid)).fetchone()
        if not u or not u["source_event_id"]:
            raise HTTPException(404, "Update not found.")
        if c.execute("SELECT 1 FROM case_events WHERE workspace_id=%s AND case_id=%s AND event_type='source_update_reviewed' AND payload->>'update_id'=%s AND actor_id=%s", (w, cid, str(uid), a["user_id"])).fetchone():
            return {"status": "already_reviewed"}
        audit(c, a, cid, "source_update_reviewed", "", {"update_id": str(uid)})
        c.execute("UPDATE notifications SET read_at=now() WHERE workspace_id=%s AND user_id=%s AND case_id=%s AND dedupe_key LIKE 'source-update:%%' AND read_at IS NULL", (w, a["user_id"], cid))
        return {"status": "reviewed"}
