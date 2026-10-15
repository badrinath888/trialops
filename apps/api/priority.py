"""Suggested request order for the Document journey collection plan. Deterministic and versioned: structured mappings from journey gaps to
unresolved checks, user-entered effort and prerequisites, a fixed ordering rule. No model, similarity or probability is used, and nothing is
sent, approved, accepted or resolved. A suggested order is not an optimal or predicted ranking."""
import hashlib
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb
from journey import LABEL, T, Model, actor, canon, case_for, audit, connect, current_journey, current_outcomes, evaluate, hours, outcome_rows, plan_items, verification_view, verifications, writer

router = APIRouter()
RULE = "suggested-order-1"
RULE_TEXT = ("Ready requests before blocked ones; then more distinct unresolved, applicable checks it could help assess; then lower stated effort "
             "(low, medium, high, then not estimated); then a stable key. Requests already sent are listed as waiting. Unknown effort sorts after high only as a tie-break "
             "and is not assumed to be high. Receiving evidence does not guarantee it is complete, relevant or supportive.")
EFFORTS = ("low", "medium", "high", "unknown")
RANK = {e: i for i, e in enumerate(EFFORTS)}
EFFORT_TEXT = {"low": "low effort", "medium": "medium effort", "high": "high effort", "unknown": "effort not estimated"}


def plural(n, word):
    return "%d %s" % (n, word if n == 1 else word + "s")


# ------------------------------------------------------------------ pure engine
def build_checks(j, outcomes, results, ver):
    checks = [{"key": "stage:" + s["stage"], "label": s["label"] + ": evidence assessment", "stage": s["stage"], "kind": "stage",
               "resolved": s["assessment"] == "verified", "applicable": True} for s in j["stages"]]
    by = {r["outcome_id"]: r for r in results}
    for o in outcomes:
        short = o["description"][:48] + ("…" if len(o["description"]) > 48 else "") + " · #" + str(o["outcome_key"])[:8]  # name + stable short id; check keys unchanged
        r = by[str(o["id"])]
        if o["requirements"]:
            for q, part in zip(o["requirements"], r["parts"]):
                checks.append({"key": "outcome:%s:%s:%s" % (o["id"], q["stage"], q["status"]), "label": "Outcome %s: %s = %s" % (short, LABEL[q["stage"]], q["status"].replace("_", " ")),
                               "stage": q["stage"], "kind": "outcome", "resolved": part["result"] == "verified", "applicable": o["required"]})
        else:  # human-only outcome: resolved only by a current verification that records a human 'verified'
            done = bool(ver and ver["current"] and any(x["outcome_id"] == str(o["id"]) and x["result"] == "verified" for x in ver["results"]))
            checks.append({"key": "outcome:%s" % o["id"], "label": short + " (human assessment)", "stage": None, "kind": "outcome", "resolved": done, "applicable": o["required"]})
    return checks


def mapped_checks(gap, stage, checks, corrections):
    """Rule: a gap on a stage maps to that stage's checks. Reviewer corrections (add/remove, with a recorded reason) adjust it. Sets, so repeats count once."""
    keys = {c["key"] for c in checks}
    out = {c["key"] for c in checks if c["stage"] == stage}
    for (gk, ck), action in corrections.items():
        if gk == gap and ck in keys:
            (out.add if action == "add" else out.discard)(ck)
    return sorted(out)


def prereq_state(p, gap_keys, stages, checks_by):
    """met only when actually satisfied; a vanished or unmatched prerequisite is 'unmatched' and still blocks until a reviewer removes or replaces it."""
    if p["kind"] == "gap":
        if p["key"] in gap_keys:
            return "unmet"
        st = stages.get(p.get("stage"))
        return "met" if st and st["assessment"] == "verified" else "unmatched"
    c = checks_by.get(p["key"])
    if not c or not c["applicable"]:
        return "unmatched"
    return "met" if c["resolved"] else "unmet"


def build_candidates(j, checks, corrections, inputs, plan):
    by = {c["key"]: c for c in checks}
    stages = {s["stage"]: s for s in j["stages"]}
    gap_keys = {g["key"] for s in j["stages"] for g in s["gaps"]}
    cands = []
    for s in j["stages"]:
        for g in s["gaps"]:
            mapped = mapped_checks(g["key"], s["stage"], checks, corrections)
            unresolved = [k for k in mapped if by[k]["applicable"] and not by[k]["resolved"]]
            inp = inputs.get(g["key"])
            pre = [{**p, "state": prereq_state(p, gap_keys, stages, by)} for p in (inp["prerequisites"] if inp else [])]
            item = plan.get(g["key"])
            blocked = any(p["state"] != "met" for p in pre)
            state = "waiting" if item and item["request_status"] == "requested" else "received" if item and item["request_status"] == "received" else "blocked" if blocked else "ready"
            cands.append({"key": g["key"], "stage": s["stage"], "stage_label": s["label"], "description": g["description"], "question": g["question"], "would_settle": g["would_settle"], "target": g["target"],
                          "mapped": mapped, "unresolved": unresolved, "excluded": [k for k in mapped if k not in unresolved],
                          "effort": inp["effort"] if inp else "unknown", "effort_note": inp["effort_note"] if inp else "", "input_rev": inp["rev"] if inp else 0,
                          "prerequisites": pre, "state": state, "existing": item and {"plan_item_id": str(item["id"]), "request_id": str(item["request_id"]), "request_status": item["request_status"], "question": item["question"]}})
    return cands


def explain(c, pos, labels):
    n = len(c["unresolved"])
    names = ", ".join(labels[k] for k in c["unresolved"][:3]) + (" and %d more" % (n - 3) if n > 3 else "")
    cover = "could help assess %s (%s)" % (plural(n, "check"), names) if n else "maps to no unresolved check, so it is not expected to help assess any"
    unmet = [p for p in c["prerequisites"] if p["state"] != "met"]
    stale = [p for p in c["prerequisites"] if p["state"] == "unmatched"]
    dep = "blocked until %s" % plural(len(unmet), "prerequisite") + " is met" if unmet else "no prerequisites" if not c["prerequisites"] else "prerequisites met"
    if unmet and len(unmet) > 1:
        dep = "blocked until %d prerequisites are met" % len(unmet)
    if stale:
        dep += " (%s no longer matches a current gap or check and still blocks; a reviewer must remove or replace it with a reason)" % plural(len(stale), "prerequisite")
    eff = EFFORT_TEXT[c["effort"]]
    return "%s: %s; %s; %s." % ("Suggested first" if pos == 1 else "Suggested #%d" % pos, cover, dep, eff)


def rank(cands, checks):
    labels = {c["key"]: c["label"] for c in checks}
    live = sorted([c for c in cands if c["state"] in ("ready", "blocked")], key=lambda c: (c["state"] == "blocked", -len(c["unresolved"]), RANK[c["effort"]], c["key"]))
    for i, c in enumerate(live, 1):
        c["rank"], c["explanation"] = i, explain(c, i, labels)
    waiting = sorted([c for c in cands if c["state"] in ("waiting", "received")], key=lambda c: c["key"])
    for c in waiting:
        c["rank"] = None
        c["explanation"] = ("Waiting: a request for this exact evidence has been sent." if c["state"] == "waiting" else
                            "Response received; it is not counted as assessed until the journey evidence or a reviewed check reflects it.")
    return live, waiting


def would_cycle(graph, start, targets):
    seen, stack = set(), list(targets)
    while stack:
        k = stack.pop()
        if k == start:
            return True
        if k not in seen:
            seen.add(k)
            stack.extend(graph.get(k, []))
    return False


# ------------------------------------------------------------------ data
def latest(rows, key):
    out = {}
    for r in rows:
        out[key(r)] = r
    return out


def compute(c, a, item):
    j, subj, links, exports, _ = current_journey(c, a, item)
    if not j:
        return None
    w, cid, now = a["workspace_id"], item["id"], datetime.now(timezone.utc)
    outcomes = current_outcomes(outcome_rows(c, w, cid))
    results = evaluate(outcomes, {}, j, subj, links, now, hours(c, w))
    vers = verifications(c, w, cid)
    ver = verification_view(vers[0], j, outcomes) if vers else None
    checks = build_checks(j, outcomes, results, ver)
    corr = {}
    for r in c.execute("SELECT * FROM journey_priority_mappings WHERE workspace_id=%s AND case_id=%s ORDER BY created_at,id", (w, cid)).fetchall():
        if r["action"] == "reset":
            corr.pop((r["gap_key"], r["check_key"]), None)
        else:
            corr[(r["gap_key"], r["check_key"])] = r["action"]
    inputs = latest(c.execute("SELECT * FROM journey_priority_inputs WHERE workspace_id=%s AND case_id=%s ORDER BY rev", (w, cid)).fetchall(), lambda r: r["gap_key"])
    plan = {}
    for p in plan_items(c, w, cid):  # newest first
        if p["request_status"] != "cancelled" and p["gap_key"] not in plan:
            plan[p["gap_key"]] = p
    cands = build_candidates(j, checks, corr, inputs, plan)
    live, waiting = rank(cands, checks)
    digest = hashlib.sha256(canon({"journey": j["fingerprint"], "checks": [(x["key"], x["resolved"], x["applicable"]) for x in checks],
                                   "cands": [(x["key"], x["unresolved"], x["effort"], x["input_rev"], [(p["kind"], p["key"], p["state"]) for p in x["prerequisites"]], x["state"]) for x in cands]}).encode()).hexdigest()
    return {"rule_version": RULE, "rule": RULE_TEXT, "checks": checks, "candidates": live, "waiting": waiting, "hash": digest, "journey_fingerprint": j["fingerprint"],
            "outcome_ids": sorted(str(o["id"]) for o in outcomes)}


def saved_rows(c, w, cid):
    return c.execute("SELECT * FROM journey_prioritizations WHERE workspace_id=%s AND case_id=%s ORDER BY rev DESC", (w, cid)).fetchall()


def activity(c, w, cid, data):
    """Recorded events only. Counts do not show that a request caused any assessment."""
    ev = c.execute("SELECT event_type,payload FROM case_events WHERE workspace_id=%s AND case_id=%s AND event_type IN ('journey_collection_drafted','journey_priority_overridden','external_response_reviewed')", (w, cid)).fetchall()
    req_ids = {str(p["request_id"]) for p in plan_items(c, w, cid)}
    drafts = [e["payload"] for e in ev if e["event_type"] == "journey_collection_drafted" and e["payload"].get("from_suggested_order")]
    resolved = {x["key"] for x in data["checks"] if x["applicable"] and x["resolved"]}
    mapped_now = set()
    for d in drafts:
        row = c.execute("SELECT inputs FROM journey_prioritizations WHERE workspace_id=%s AND id=%s", (w, d["prioritization_id"])).fetchone()
        cand = next((x for x in row["inputs"]["candidates"] if x["key"] == d["gap_key"]), None) if row else None
        mapped_now |= {k for k in (cand["unresolved"] if cand else []) if k in resolved}
    return {"drafts_from_suggestion": len(drafts), "order_overrides": sum(1 for e in ev if e["event_type"] == "journey_priority_overridden"),
            "responses_reviewed": sum(1 for e in ev if e["event_type"] == "external_response_reviewed" and e["payload"].get("request_id") in req_ids),
            "mapped_checks_now_verified": len(mapped_now), "note": "Counts of recorded events. They do not show that any request caused a check to be assessed."}


def summary_rows(data):
    return [{"rank": x["rank"], "request": x["description"], "could_help_assess": [next(c["label"] for c in data["checks"] if c["key"] == k) for k in x["unresolved"]],
             "effort": x["effort"], "state": x["state"], "explanation": x["explanation"]} for x in data["candidates"] + data["waiting"]]


@router.get("/cases/{cid}/journey/priority")
def get_priority(cid: str, a=Depends(actor)):
    with connect() as c:
        item = case_for(c, a, cid)
        data = compute(c, a, item)
        if not data:
            return {"available": False}
        w = a["workspace_id"]
        reviewer = a["role"] in ("owner", "reviewer")
        rows = saved_rows(c, w, cid) if reviewer else []
        cur = rows[0] if rows else None
        mappings = c.execute("SELECT * FROM journey_priority_mappings WHERE workspace_id=%s AND case_id=%s ORDER BY created_at DESC", (w, cid)).fetchall() if reviewer else []
        return {"available": True, **data, "saved": cur and {**cur, "stale": cur["input_hash"] != data["hash"]}, "history": [{k: r[k] for k in ("id", "rev", "rule_version", "created_at", "actor_name", "override")} | {"stale": r["input_hash"] != data["hash"], "order": [x["key"] for x in r["suggested"]]} for r in rows],
                "mappings": mappings, "activity": activity(c, w, cid, data), "can_write": reviewer}


class Prereq(Model):
    kind: Literal["gap", "check"]
    key: T(1, 300)


class InputEdit(Model):
    id: UUID
    gap_key: T(1, 300)
    expected_rev: int = 0
    effort: Literal["low", "medium", "high", "unknown"]
    effort_note: str = ""
    prerequisites: list[Prereq] = []
    change_reason: str = ""  # required, with reviewer/owner role, when an existing prerequisite is removed or replaced


class MappingEdit(Model):
    id: UUID
    gap_key: T(1, 300)
    check_key: T(1, 300)
    action: Literal["add", "remove", "reset"]
    reason: T(10, 1000)


class Save(Model):
    id: UUID
    expected_rev: int = 0


class Override(Model):
    id: UUID
    expected_rev: int
    order: list[T(1, 300)]
    reason: T(10, 1000)


def everything(data):
    return data["candidates"] + data["waiting"]


@router.post("/cases/{cid}/journey/priority/inputs", status_code=201)
def save_inputs(cid: str, body: InputEdit, a=Depends(actor)):
    if len(body.effort_note) > 200:
        raise HTTPException(422, "Keep the effort explanation under 200 characters.")
    with connect() as c:
        item = case_for(c, a, cid, True)
        writer(c, a)
        w = a["workspace_id"]
        data = compute(c, a, item)
        if not data:
            raise HTTPException(409, "Define the document and intended binder first.")
        by_gap = {x["key"]: x for x in everything(data)}
        if body.gap_key not in by_gap:
            raise HTTPException(409, "That request no longer matches a current gap. Reload the plan.")
        pre, seen = [], set()
        checks = {x["key"] for x in data["checks"]}
        prev = c.execute("SELECT prerequisites FROM journey_priority_inputs WHERE workspace_id=%s AND case_id=%s AND gap_key=%s ORDER BY rev DESC LIMIT 1", (w, cid, body.gap_key)).fetchone()
        prev = {(p["kind"], p["key"]): p for p in (prev["prerequisites"] if prev else [])}
        for p in body.prerequisites:
            if (p.kind, p.key) in seen:
                continue
            seen.add((p.kind, p.key))
            if (p.kind, p.key) in prev:  # kept as recorded, even if it no longer matches (it stays blocking)
                pre.append(prev[(p.kind, p.key)])
            elif p.kind == "gap":
                if p.key == body.gap_key:
                    raise HTTPException(422, "A request cannot depend on itself.")
                if p.key not in by_gap:
                    raise HTTPException(422, "Prerequisite request is not a current gap in this case.")
                pre.append({"kind": "gap", "key": p.key, "stage": by_gap[p.key]["stage"]})
            else:
                if p.key not in checks:
                    raise HTTPException(422, "Prerequisite check is not a current check in this case.")
                pre.append({"kind": "check", "key": p.key})
        graph = {k: [p["key"] for p in v["prerequisites"] if p["kind"] == "gap"] for k, v in by_gap.items() if k != body.gap_key}
        if would_cycle(graph, body.gap_key, [p["key"] for p in pre if p["kind"] == "gap"]):
            raise HTTPException(422, "Those prerequisites would create a dependency cycle.")
        old = c.execute("SELECT * FROM journey_priority_inputs WHERE workspace_id=%s AND id=%s", (w, body.id)).fetchone()
        if old:
            if old["case_id"] != cid or (old["gap_key"], old["effort"], old["effort_note"], old["prerequisites"]) != (body.gap_key, body.effort, body.effort_note, pre):
                raise HTTPException(409, "Input ID already holds different inputs.")
            return old
        last = c.execute("SELECT max(rev) AS rev FROM journey_priority_inputs WHERE workspace_id=%s AND case_id=%s AND gap_key=%s", (w, cid, body.gap_key)).fetchone()["rev"] or 0
        if last != body.expected_rev:
            raise HTTPException(409, "These inputs changed. Reload before saving.")
        removed = [p for k, p in prev.items() if k not in seen]
        if removed:
            if len(body.change_reason.strip()) < 10:
                raise HTTPException(422, "Give a reason (at least 10 characters) for removing or replacing a prerequisite.")
        row = c.execute("INSERT INTO journey_priority_inputs(workspace_id,id,case_id,gap_key,rev,effort,effort_note,prerequisites,actor_id,actor_name) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                        (w, body.id, cid, body.gap_key, last + 1, body.effort, body.effort_note.strip(), Jsonb(pre), a["user_id"], a["name"])).fetchone()
        audit(c, a, cid, "journey_priority_inputs_saved", body.effort_note, {"input_id": str(body.id), "gap_key": body.gap_key, "effort": body.effort, "prerequisites": pre, "rev": row["rev"],
                                                                                         **({"removed_prerequisites": removed, "change_reason": body.change_reason.strip()} if removed else {})})
        return row


@router.post("/cases/{cid}/journey/priority/mappings", status_code=201)
def save_mapping(cid: str, body: MappingEdit, a=Depends(actor)):
    with connect() as c:
        item = case_for(c, a, cid, True)
        writer(c, a)
        w = a["workspace_id"]
        data = compute(c, a, item)
        if not data:
            raise HTTPException(409, "Define the document and intended binder first.")
        cand = next((x for x in everything(data) if x["key"] == body.gap_key), None)
        if not cand or body.check_key not in {x["key"] for x in data["checks"]}:
            raise HTTPException(409, "That request or check no longer exists. Reload the plan.")
        old = c.execute("SELECT * FROM journey_priority_mappings WHERE workspace_id=%s AND id=%s", (w, body.id)).fetchone()
        if old:
            if old["case_id"] != cid or (old["gap_key"], old["check_key"], old["action"], old["reason"]) != (body.gap_key, body.check_key, body.action, body.reason):
                raise HTTPException(409, "Mapping ID already holds a different correction.")
            return old
        has = body.check_key in cand["mapped"]
        corrected = c.execute("SELECT action FROM journey_priority_mappings WHERE workspace_id=%s AND case_id=%s AND gap_key=%s AND check_key=%s ORDER BY created_at DESC,id LIMIT 1", (w, cid, body.gap_key, body.check_key)).fetchone()
        if (body.action == "add" and has) or (body.action == "remove" and not has) or (body.action == "reset" and (not corrected or corrected["action"] == "reset")):
            raise HTTPException(422, "That does not change the current mapping.")
        row = c.execute("INSERT INTO journey_priority_mappings(workspace_id,id,case_id,gap_key,check_key,action,reason,actor_id,actor_name) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                        (w, body.id, cid, body.gap_key, body.check_key, body.action, body.reason, a["user_id"], a["name"])).fetchone()
        audit(c, a, cid, "journey_priority_mapping_changed", body.reason, {"mapping_id": str(body.id), "gap_key": body.gap_key, "check_key": body.check_key, "action": body.action})
        return row


def snapshot_inputs(data):
    cols = ("key", "stage", "description", "target", "mapped", "unresolved", "excluded", "effort", "effort_note", "input_rev", "prerequisites", "state", "rank", "existing")
    return {"journey_fingerprint": data["journey_fingerprint"], "outcome_ids": data["outcome_ids"], "checks": data["checks"], "candidates": [{k: x[k] for k in cols} for x in everything(data)], "rule": data["rule"]}


@router.post("/cases/{cid}/journey/priority/save", status_code=201)
def save_order(cid: str, body: Save, a=Depends(actor)):
    with connect() as c:
        item = case_for(c, a, cid, True)
        writer(c, a)
        w = a["workspace_id"]
        old = c.execute("SELECT * FROM journey_prioritizations WHERE workspace_id=%s AND id=%s", (w, body.id)).fetchone()
        if old:
            if old["case_id"] != cid:
                raise HTTPException(409, "Prioritization ID already used.")
            return old
        data = compute(c, a, item)
        if not data:
            raise HTTPException(409, "Define the document and intended binder first.")
        rows = saved_rows(c, w, cid)
        last = rows[0]["rev"] if rows else 0
        if last != body.expected_rev:
            raise HTTPException(409, "The saved order changed. Reload before saving.")
        if rows and rows[0]["input_hash"] == data["hash"]:
            return rows[0]
        row = c.execute("INSERT INTO journey_prioritizations(workspace_id,id,case_id,rev,rule_version,input_hash,inputs,suggested,actor_id,actor_name) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                        (w, body.id, cid, last + 1, RULE, data["hash"], Jsonb(snapshot_inputs(data)), Jsonb([{"key": x["key"], "rank": x["rank"], "explanation": x["explanation"]} for x in data["candidates"]]), a["user_id"], a["name"])).fetchone()
        audit(c, a, cid, "journey_priority_saved", "Suggested request order saved (revision %d)." % row["rev"], {"prioritization_id": str(body.id), "rev": row["rev"], "rule_version": RULE, "refresh": bool(rows)})
        return row


@router.post("/cases/{cid}/journey/priority/override", status_code=201)
def override_order(cid: str, body: Override, a=Depends(actor)):
    with connect() as c:
        item = case_for(c, a, cid, True)
        writer(c, a)
        w = a["workspace_id"]
        old = c.execute("SELECT * FROM journey_prioritizations WHERE workspace_id=%s AND id=%s", (w, body.id)).fetchone()
        if old:
            if old["case_id"] != cid or not old["override"] or old["override"]["order"] != body.order or old["override"]["reason"] != body.reason:
                raise HTTPException(409, "Prioritization ID already holds a different order.")
            return old
        data = compute(c, a, item)
        if not data:
            raise HTTPException(409, "Define the document and intended binder first.")
        rows = saved_rows(c, w, cid)
        if not rows or rows[0]["rev"] != body.expected_rev:
            raise HTTPException(409, "The saved order changed. Reload before saving.")
        if rows[0]["input_hash"] != data["hash"]:
            raise HTTPException(409, "The saved order is stale: evidence, outcomes or dependencies changed. Refresh it before overriding.")
        keys = [x["key"] for x in data["candidates"]]
        if sorted(body.order) != sorted(keys) or len(set(body.order)) != len(body.order):
            raise HTTPException(422, "The reviewer order must list each current candidate request exactly once.")
        if body.order == keys:
            raise HTTPException(422, "That is the suggested order. Change the order before saving an override.")
        ov = {"order": body.order, "reason": body.reason, "actor": a["name"], "actor_id": str(a["user_id"]), "at": datetime.now(timezone.utc).isoformat(), "suggested_order": keys}
        row = c.execute("INSERT INTO journey_prioritizations(workspace_id,id,case_id,rev,rule_version,input_hash,inputs,suggested,override,actor_id,actor_name) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                        (w, body.id, cid, rows[0]["rev"] + 1, RULE, data["hash"], Jsonb(rows[0]["inputs"]), Jsonb(rows[0]["suggested"]), Jsonb(ov), a["user_id"], a["name"])).fetchone()
        audit(c, a, cid, "journey_priority_overridden", body.reason, {"prioritization_id": str(body.id), "rev": row["rev"], "from": keys, "to": body.order})
        return row
