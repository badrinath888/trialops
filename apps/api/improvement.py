"""Recurrence/prevention plans, bulk case actions, readiness tracker, procedure impact review, feedback queue.
Deterministic and human-reviewed throughout: nothing here calls a model, confirms evidence, resolves cases or sends messages."""
import difflib, hashlib, json
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb
from pydantic import Field, field_validator
from db import connect, query, one
from typing import Annotated
from pydantic import StringConstraints
from models import Model, Text


def T(lo, hi):
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=lo, max_length=hi)]

from security import actor, require, rate

router = APIRouter()
MAX_GROUP = 25
MAX_ACTIONS = 20
MAX_BATCH = 25
MIN_BASELINE_EVENTS = 5


def aware(v):
    if v is not None and v.tzinfo is None:
        raise ValueError("Timezone required")
    return v


def hist(c, a, scope, ref, kind, payload=None):
    c.execute(
        "INSERT INTO improvement_events(workspace_id,id,scope,ref_id,kind,actor_id,actor_name,payload) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
        (a["workspace_id"], uuid4(), scope, str(ref), kind, a["user_id"], a["name"], Jsonb(payload or {})),
    )


def case_audit(c, a, cid, kind, notes="", payload=None):
    from main import event
    return event(c, a, cid, kind, notes, None, payload)


def writer(c, a):
    """Fresh membership/role check inside the transaction (role may have changed since the session started)."""
    from five_features import current
    return current(c, a, True)


def members_only(c, a, uid):
    if uid and not c.execute("SELECT 1 FROM memberships WHERE workspace_id=%s AND user_id=%s", (a["workspace_id"], uid)).fetchone():
        raise HTTPException(422, "Owner must belong to this workspace.")


def stale(old, expected):
    if old["version"] != expected:
        raise HTTPException(409, "This record changed. Reload before saving.")


# ---------------------------------------------------------------- recurrence groups and prevention plans
def criteria(g):
    return {"category": g["category"], "study_id": g["study_id"], "site_id": g["site_id"]}


def matching_cases(c, w, g, start=None, end=None, limit=None):
    sql = "SELECT id,title,status,created_at FROM cases WHERE workspace_id=%s AND category=%s AND study_id=%s AND (%s::text IS NULL OR site_id=%s)"
    p = [w, g["category"], g["study_id"], g["site_id"], g["site_id"]]
    if start is not None:
        sql += " AND created_at>=%s AND created_at<%s"
        p += [start, end]
    sql += " ORDER BY created_at, id" + (" LIMIT %d" % limit if limit else "")
    return c.execute(sql, p).fetchall()


@router.get("/recurrence/suggestions")
def suggestions(case_id: str, a=Depends(actor)):
    with connect() as c:
        from main import get_case
        item = get_case(a, case_id, c)
        w = a["workspace_id"]
        same = c.execute(
            "SELECT id,title,status,created_at FROM cases WHERE workspace_id=%s AND id<>%s AND category=%s AND study_id=%s AND site_id=%s ORDER BY created_at DESC LIMIT 30",
            (w, case_id, item["category"], item["study_id"], item["site_id"]),
        ).fetchall()
        linked = c.execute(
            "SELECT k.id,k.title,k.status,k.created_at,l.rationale FROM case_links l JOIN cases k ON k.workspace_id=l.workspace_id AND k.id=CASE WHEN l.case_id=%s THEN l.related_id ELSE l.case_id END WHERE l.workspace_id=%s AND (l.case_id=%s OR l.related_id=%s) LIMIT 30",
            (case_id, w, case_id, case_id),
        ).fetchall()
        by = {}
        for r in same:
            by[r["id"]] = {**r, "via": ["same category, study and site"]}
        for r in linked:
            e = by.setdefault(r["id"], {k: r[k] for k in ("id", "title", "status", "created_at")} | {"via": []})
            e["via"].append("reviewer-confirmed link")
        groups = c.execute(
            "SELECT g.id,g.title,g.status FROM recurrence_groups g JOIN recurrence_members m ON m.workspace_id=g.workspace_id AND m.group_id=g.id WHERE g.workspace_id=%s AND m.case_id=%s AND m.removed_at IS NULL",
            (w, case_id),
        ).fetchall()
        return {
            "criteria": {"category": item["category"], "study_id": item["study_id"], "site_id": item["site_id"]},
            "candidates": list(by.values()),
            "groups": groups,
            "interpretation": "Candidates share structured fields or a reviewer-confirmed link. Text similarity is not used, and neither recurrence nor a shared root cause is established until a reviewer confirms membership and explains the observed pattern.",
        }


class GroupCreate(Model):
    id: UUID
    title: T(1, 120)
    case_ids: list[Text] = Field(min_length=2, max_length=MAX_GROUP)
    basis: Literal["category_study_site", "explicit_links"]
    site_scope: Literal["site", "study"] = "site"
    pattern: T(20, 1000)


def check_members(c, w, g, ids, basis):
    rows = c.execute("SELECT id,category,study_id,site_id,status FROM cases WHERE workspace_id=%s AND id=ANY(%s) FOR SHARE", (w, ids)).fetchall()
    if len(rows) != len(set(ids)):
        raise HTTPException(422, "Every case must exist in this workspace.")
    for r in rows:
        if r["category"] != g["category"] or r["study_id"] != g["study_id"] or (g["site_id"] and r["site_id"] != g["site_id"]):
            raise HTTPException(422, r["id"] + " does not match the group's category, study and site scope.")
    if basis == "explicit_links":
        linked = c.execute("SELECT case_id,related_id FROM case_links WHERE workspace_id=%s AND case_id=ANY(%s) AND related_id=ANY(%s)", (w, ids, ids)).fetchall()
        touched = {x for l in linked for x in (l["case_id"], l["related_id"])}
        if any(i not in touched for i in ids):
            raise HTTPException(422, "With the explicit-link basis every member needs a reviewer-confirmed link to another member.")


def group_view(c, w, gid):
    g = c.execute("SELECT * FROM recurrence_groups WHERE workspace_id=%s AND id=%s", (w, gid)).fetchone()
    if not g:
        raise HTTPException(404, "Recurrence group not found in this workspace.")
    members = c.execute(
        "SELECT m.id,m.case_id,k.title,k.status,m.added_at,m.removed_at,m.removal_reason,u.name AS added_by_name FROM recurrence_members m JOIN cases k ON (k.workspace_id,k.id)=(m.workspace_id,m.case_id) LEFT JOIN users u ON u.id=m.added_by WHERE m.workspace_id=%s AND m.group_id=%s ORDER BY m.added_at,m.id",
        (w, gid),
    ).fetchall()
    plans = c.execute("SELECT * FROM prevention_plans WHERE workspace_id=%s AND group_id=%s ORDER BY created_at", (w, gid)).fetchall()
    for p in plans:
        p["actions"] = c.execute(
            "SELECT x.*,u.name AS owner_name FROM prevention_actions x LEFT JOIN users u ON u.id=x.owner_id WHERE x.workspace_id=%s AND x.plan_id=%s AND NOT x.removed ORDER BY x.position",
            (w, p["id"]),
        ).fetchall()
    windows = c.execute("SELECT * FROM recurrence_windows WHERE workspace_id=%s AND group_id=%s ORDER BY start_at", (w, gid)).fetchall()
    for x in windows:
        found = matching_cases(c, w, g, x["start_at"], x["end_at"])
        x["matching_cases"] = len(found)
        x["case_ids"] = [f["id"] for f in found[:20]]
        x["days"] = round((x["end_at"] - x["start_at"]).total_seconds() / 86400, 2)
    events = c.execute("SELECT id,kind,actor_name,payload,created_at FROM improvement_events WHERE workspace_id=%s AND scope IN ('recurrence','plan') AND ref_id=ANY(%s) ORDER BY created_at,id", (w, [str(gid)] + [str(p["id"]) for p in plans])).fetchall()
    return {"group": g, "criteria": criteria(g), "members": members, "plans": plans, "windows": windows, "comparison": compare(windows), "events": events,
            "interpretation": "Counts are matching cases created in reviewer-selected windows. They do not establish a shared root cause or that a plan caused any change."}


def compare(windows):
    base = [x for x in windows if x["role"] == "baseline"]
    follow = [x for x in windows if x["role"] == "follow_up"]
    if not base or not follow:
        return {"can_compare": False, "reasons": ["Define a baseline and a follow-up window."]}
    b, f = base[-1], follow[-1]
    reasons = []
    if abs(b["days"] - f["days"]) > 0.05:
        reasons.append("Windows have unequal lengths (%s vs %s days)." % (b["days"], f["days"]))
    if b["exposure_count"] is None or f["exposure_count"] is None:
        reasons.append("Exposure denominators are missing for at least one window.")
    elif (b["exposure_unit"] or "").strip().lower() != (f["exposure_unit"] or "").strip().lower():
        reasons.append("Exposure units differ between windows.")
    if b["matching_cases"] < MIN_BASELINE_EVENTS:
        reasons.append("Baseline has %d matching cases; at least %d are needed for a descriptive comparison." % (b["matching_cases"], MIN_BASELINE_EVENTS))
    out = {"baseline": b["label"], "follow_up": f["label"], "baseline_cases": b["matching_cases"], "follow_up_cases": f["matching_cases"], "can_compare": not reasons, "reasons": reasons,
           "note": "Descriptive only. Counts from different windows do not show that a plan caused any change."}
    if not reasons:
        rb, rf = b["matching_cases"] / float(b["exposure_count"]), f["matching_cases"] / float(f["exposure_count"])
        out |= {"unit": b["exposure_unit"], "baseline_rate_per_unit": round(rb, 4), "follow_up_rate_per_unit": round(rf, 4)}
    return out


@router.post("/recurrence/groups", status_code=201)
def create_group(body: GroupCreate, a=Depends(actor)):
    rate("recurrence-write:" + str(a["workspace_id"]), 120)
    with connect() as c:
        writer(c, a)
        w = a["workspace_id"]
        old = c.execute("SELECT * FROM recurrence_groups WHERE workspace_id=%s AND id=%s", (w, body.id)).fetchone()
        if old:
            if (old["title"], old["pattern"], old["basis"]) != (body.title, body.pattern, body.basis):
                raise HTTPException(409, "Group ID already contains a different group.")
            return group_view(c, w, body.id)
        first = c.execute("SELECT category,study_id,site_id FROM cases WHERE workspace_id=%s AND id=%s", (w, body.case_ids[0])).fetchone()
        if not first:
            raise HTTPException(422, "Every case must exist in this workspace.")
        g = {"category": first["category"], "study_id": first["study_id"], "site_id": first["site_id"] if body.site_scope == "site" else None}
        check_members(c, w, g, body.case_ids, body.basis)
        c.execute("INSERT INTO recurrence_groups(workspace_id,id,title,category,study_id,site_id,basis,pattern,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)", (w, body.id, body.title, g["category"], g["study_id"], g["site_id"], body.basis, body.pattern, a["user_id"]))
        for cid in dict.fromkeys(body.case_ids):
            c.execute("INSERT INTO recurrence_members(workspace_id,id,group_id,case_id,added_by) VALUES(%s,%s,%s,%s,%s)", (w, uuid4(), body.id, cid, a["user_id"]))
            case_audit(c, a, cid, "recurrence_membership_confirmed", body.pattern, {"group_id": str(body.id), "recurrence_or_root_cause_established": False})
        hist(c, a, "recurrence", body.id, "group_confirmed", {"title": body.title, "basis": body.basis, "pattern": body.pattern, "criteria": criteria(g), "cases": body.case_ids})
        return group_view(c, w, body.id)


@router.get("/recurrence/groups")
def groups(case_id: str, a=Depends(actor)):
    with connect() as c:
        from main import get_case
        get_case(a, case_id, c)
        ids = [r["group_id"] for r in c.execute("SELECT DISTINCT group_id FROM recurrence_members WHERE workspace_id=%s AND case_id=%s", (a["workspace_id"], case_id)).fetchall()]
        return [group_view(c, a["workspace_id"], g) for g in ids]


@router.get("/recurrence/groups/{gid}")
def group(gid: UUID, a=Depends(actor)):
    with connect() as c:
        return group_view(c, a["workspace_id"], gid)


class MemberEdit(Model):
    expected_version: int = Field(ge=1)
    add: list[Text] = Field(default=[], max_length=MAX_GROUP)
    remove: list[dict] = Field(default=[], max_length=MAX_GROUP)
    pattern: T(20, 1000) | None = None

    @field_validator("remove")
    @classmethod
    def reasons(cls, v):
        for r in v:
            if set(r) != {"case_id", "reason"} or len(str(r["reason"]).strip()) < 5:
                raise ValueError("Each removal needs a case_id and a reason of at least 5 characters")
        return v


@router.post("/recurrence/groups/{gid}/members")
def edit_members(gid: UUID, body: MemberEdit, a=Depends(actor)):
    with connect() as c:
        writer(c, a)
        w = a["workspace_id"]
        g = c.execute("SELECT * FROM recurrence_groups WHERE workspace_id=%s AND id=%s FOR UPDATE", (w, gid)).fetchone()
        if not g:
            raise HTTPException(404, "Recurrence group not found in this workspace.")
        stale(g, body.expected_version)
        if g["status"] != "active":
            raise HTTPException(409, "This group is closed.")
        if body.add:
            check_members(c, w, g, list(dict.fromkeys(body.add)), g["basis"] if g["basis"] == "category_study_site" else "category_study_site")
        for cid in dict.fromkeys(body.add):
            if c.execute("INSERT INTO recurrence_members(workspace_id,id,group_id,case_id,added_by) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id", (w, uuid4(), gid, cid, a["user_id"])).fetchone():
                case_audit(c, a, cid, "recurrence_membership_confirmed", g["pattern"], {"group_id": str(gid), "recurrence_or_root_cause_established": False})
        for r in body.remove:
            if c.execute("UPDATE recurrence_members SET removed_at=now(),removed_by=%s,removal_reason=%s WHERE workspace_id=%s AND group_id=%s AND case_id=%s AND removed_at IS NULL RETURNING id", (a["user_id"], r["reason"], w, gid, r["case_id"])).fetchone():
                case_audit(c, a, r["case_id"], "recurrence_membership_removed", r["reason"], {"group_id": str(gid)})
        if body.pattern and body.pattern != g["pattern"]:
            c.execute("UPDATE recurrence_groups SET pattern=%s WHERE workspace_id=%s AND id=%s", (body.pattern, w, gid))
            hist(c, a, "recurrence", gid, "pattern_revised", {"previous": g["pattern"], "current": body.pattern})
        c.execute("UPDATE recurrence_groups SET version=version+1,updated_at=now() WHERE workspace_id=%s AND id=%s", (w, gid))
        if body.add or body.remove:
            hist(c, a, "recurrence", gid, "membership_changed", {"added": body.add, "removed": body.remove})
        left = c.execute("SELECT count(*) AS n FROM recurrence_members WHERE workspace_id=%s AND group_id=%s AND removed_at IS NULL", (w, gid)).fetchone()["n"]
        if left < 2:
            raise HTTPException(422, "A recurrence group needs at least two confirmed cases.")
        return group_view(c, w, gid)


class PlanCreate(Model):
    id: UUID
    title: T(1, 120)
    summary: str = Field(default="", max_length=1000)


@router.post("/recurrence/groups/{gid}/plans", status_code=201)
def create_plan(gid: UUID, body: PlanCreate, a=Depends(actor)):
    with connect() as c:
        writer(c, a)
        w = a["workspace_id"]
        g = c.execute("SELECT * FROM recurrence_groups WHERE workspace_id=%s AND id=%s FOR SHARE", (w, gid)).fetchone()
        if not g:
            raise HTTPException(404, "Recurrence group not found in this workspace.")
        old = c.execute("SELECT * FROM prevention_plans WHERE workspace_id=%s AND id=%s", (w, body.id)).fetchone()
        if not old:
            c.execute("INSERT INTO prevention_plans(workspace_id,id,group_id,title,summary,created_by) VALUES(%s,%s,%s,%s,%s,%s)", (w, body.id, gid, body.title, body.summary, a["user_id"]))
            hist(c, a, "plan", body.id, "plan_created", {"title": body.title, "group_id": str(gid)})
        elif old["group_id"] != gid or old["title"] != body.title:
            raise HTTPException(409, "Plan ID already contains a different plan.")
        return group_view(c, w, gid)


class ActionIn(Model):
    id: UUID
    text: T(1, 300)
    owner_id: UUID | None = None
    due_at: datetime | None = None
    evidence: list[dict] = Field(default=[], max_length=10)
    done: bool = False

    @field_validator("due_at")
    @classmethod
    def _aw(cls, v):
        return aware(v)


class PlanEdit(Model):
    expected_version: int = Field(ge=1)
    title: T(1, 120)
    summary: str = Field(default="", max_length=1000)
    actions: list[ActionIn] = Field(max_length=MAX_ACTIONS)
    status: Literal["draft", "active", "completed"]
    completion_note: str = Field(default="", max_length=1000)


def check_action_evidence(c, w, gid, ev):
    members = {r["case_id"] for r in c.execute("SELECT DISTINCT case_id FROM recurrence_members WHERE workspace_id=%s AND group_id=%s", (w, gid)).fetchall()}
    out = []
    for e in ev:
        if set(e) - {"case_id", "evidence_id", "note"} or e.get("case_id") not in members:
            raise HTTPException(422, "Supporting evidence must reference a case that is or was a member of this group.")
        if e.get("evidence_id") and not c.execute("SELECT 1 FROM case_evidence WHERE workspace_id=%s AND case_id=%s AND id::text=%s", (w, e["case_id"], str(e["evidence_id"]))).fetchone():
            raise HTTPException(422, "Evidence reference must belong to that case and workspace.")
        out.append({"case_id": e["case_id"], "evidence_id": e.get("evidence_id"), "note": str(e.get("note", ""))[:300]})
    return out


@router.post("/prevention-plans/{pid}")
def edit_plan(pid: UUID, body: PlanEdit, a=Depends(actor)):
    with connect() as c:
        writer(c, a)
        w = a["workspace_id"]
        p = c.execute("SELECT * FROM prevention_plans WHERE workspace_id=%s AND id=%s FOR UPDATE", (w, pid)).fetchone()
        if not p:
            raise HTTPException(404, "Plan not found in this workspace.")
        stale(p, body.expected_version)
        if p["status"] == "completed":
            raise HTTPException(409, "A completed plan is read-only; create a new plan for further work.")
        order = {"draft": 0, "active": 1, "completed": 2}
        if order[body.status] < order[p["status"]]:
            raise HTTPException(422, "A plan cannot move back to an earlier state.")
        if len({x.id for x in body.actions}) != len(body.actions):
            raise HTTPException(422, "Action identifiers must be unique.")
        prepared = []
        for i, x in enumerate(body.actions):
            members_only(c, a, x.owner_id)
            prepared.append((x, check_action_evidence(c, w, p["group_id"], x.evidence), i))
        if body.status in ("active", "completed"):
            if not prepared:
                raise HTTPException(422, "Add at least one action before activating the plan.")
            for x, ev, _ in prepared:
                if not x.owner_id or not x.due_at or not ev:
                    raise HTTPException(422, "Every action needs an owner, a deadline and supporting evidence before the plan is active.")
        if body.status == "completed":
            if not all(x.done for x, _, _ in prepared) or len(body.completion_note.strip()) < 10:
                raise HTTPException(422, "Complete all actions and explain the outcome before completing the plan.")
        kept = set()
        for x, ev, pos in prepared:
            kept.add(x.id)
            before = c.execute("SELECT status FROM prevention_actions WHERE workspace_id=%s AND id=%s AND plan_id=%s", (w, x.id, pid)).fetchone()
            c.execute(
                """INSERT INTO prevention_actions(workspace_id,id,plan_id,text,owner_id,due_at,status,evidence,position,done_at,removed) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,false)
                ON CONFLICT(workspace_id,id) DO UPDATE SET text=EXCLUDED.text,owner_id=EXCLUDED.owner_id,due_at=EXCLUDED.due_at,status=EXCLUDED.status,evidence=EXCLUDED.evidence,position=EXCLUDED.position,removed=false,
                done_at=CASE WHEN EXCLUDED.status='done' THEN coalesce(prevention_actions.done_at,now()) ELSE NULL END WHERE prevention_actions.plan_id=EXCLUDED.plan_id""",
                (w, x.id, pid, x.text, x.owner_id, x.due_at, "done" if x.done else "open", Jsonb(ev), pos, datetime.now(timezone.utc) if x.done else None),
            )
        c.execute("UPDATE prevention_actions SET removed=true WHERE workspace_id=%s AND plan_id=%s AND NOT (id=ANY(%s))", (w, pid, list(kept)))
        c.execute(
            "UPDATE prevention_plans SET title=%s,summary=%s,status=%s,completion_note=%s,version=version+1,updated_at=now(),activated_at=CASE WHEN %s='active' AND activated_at IS NULL THEN now() ELSE activated_at END,completed_at=CASE WHEN %s='completed' THEN now() ELSE completed_at END WHERE workspace_id=%s AND id=%s",
            (body.title, body.summary, body.status, body.completion_note or None, body.status, body.status, w, pid),
        )
        snapshot = {"title": body.title, "summary": body.summary, "status": body.status, "completion_note": body.completion_note, "actions": [{"id": str(x.id), "text": x.text, "owner_id": str(x.owner_id) if x.owner_id else None, "due_at": str(x.due_at) if x.due_at else None, "done": x.done, "evidence": ev} for x, ev, _ in prepared], "revision": p["version"] + 1}
        hist(c, a, "plan", pid, "plan_revised" if body.status == p["status"] else "plan_" + body.status, snapshot)
        for cid in {e["case_id"] for _, ev, _ in prepared for e in ev}:
            case_audit(c, a, cid, "prevention_plan_revised", body.title, {"plan_id": str(pid), "status": body.status, "revision": p["version"] + 1})
        return group_view(c, w, p["group_id"])


class WindowCreate(Model):
    id: UUID
    label: T(1, 80)
    role: Literal["baseline", "follow_up"]
    start_at: datetime
    end_at: datetime
    exposure_count: float | None = Field(default=None, gt=0)
    exposure_unit: str | None = Field(default=None, max_length=40)

    @field_validator("start_at", "end_at")
    @classmethod
    def _aw(cls, v):
        return aware(v)


@router.post("/recurrence/groups/{gid}/windows", status_code=201)
def add_window(gid: UUID, body: WindowCreate, a=Depends(actor)):
    if body.end_at <= body.start_at:
        raise HTTPException(422, "The window must end after it starts.")
    if (body.exposure_count is None) != (not (body.exposure_unit or "").strip()):
        raise HTTPException(422, "Provide both an exposure count and its unit, or neither.")
    with connect() as c:
        writer(c, a)
        w = a["workspace_id"]
        c.execute("SELECT 1 FROM recurrence_groups WHERE workspace_id=%s AND id=%s FOR UPDATE", (w, gid))
        old = c.execute("SELECT * FROM recurrence_windows WHERE workspace_id=%s AND id=%s", (w, body.id)).fetchone()
        if old:
            if (old["group_id"], old["label"], old["start_at"], old["end_at"]) != (gid, body.label, body.start_at, body.end_at):
                raise HTTPException(409, "Window ID already contains a different window.")
            return group_view(c, w, gid)
        if not c.execute("SELECT 1 FROM recurrence_groups WHERE workspace_id=%s AND id=%s", (w, gid)).fetchone():
            raise HTTPException(404, "Recurrence group not found in this workspace.")
        if c.execute("SELECT 1 FROM recurrence_windows WHERE workspace_id=%s AND group_id=%s AND start_at<%s AND end_at>%s", (w, gid, body.end_at, body.start_at)).fetchone():
            raise HTTPException(422, "Windows for one group must not overlap.")
        c.execute("INSERT INTO recurrence_windows(workspace_id,id,group_id,label,role,start_at,end_at,exposure_count,exposure_unit,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (w, body.id, gid, body.label, body.role, body.start_at, body.end_at, body.exposure_count, (body.exposure_unit or None), a["user_id"]))
        hist(c, a, "recurrence", gid, "window_recorded", {"label": body.label, "role": body.role, "start_at": str(body.start_at), "end_at": str(body.end_at), "exposure": [body.exposure_count, body.exposure_unit]})
        return group_view(c, w, gid)


# ---------------------------------------------------------------- bulk owner / deadline changes
class BulkIn(Model):
    request_id: UUID
    case_ids: list[Text] = Field(min_length=1, max_length=MAX_BATCH)
    set_owner: bool = False
    owner_id: UUID | None = None
    set_due: bool = False
    due_at: datetime | None = None
    expected: dict[str, datetime] = {}

    @field_validator("due_at")
    @classmethod
    def _aw(cls, v):
        return aware(v)

    @field_validator("case_ids")
    @classmethod
    def unique(cls, v):
        if len(set(v)) != len(v):
            raise ValueError("Each case can appear once")
        return v

    def check(self):
        if not (self.set_owner or self.set_due):
            raise HTTPException(422, "Choose an owner or deadline change.")


def evaluate(c, a, body, cid, lock):
    sql = "SELECT id,title,status,owner_id,due_at,updated_at FROM cases WHERE workspace_id=%s AND id=%s" + (" FOR UPDATE" if lock else "")
    row = c.execute(sql, (a["workspace_id"], cid)).fetchone()
    if not row:
        return None, "Case not found in this workspace."
    if row["status"] != "open":
        return row, "Case is resolved; bulk actions never reopen cases."
    if body.set_owner:
        if body.owner_id and not c.execute("SELECT 1 FROM memberships WHERE workspace_id=%s AND user_id=%s", (a["workspace_id"], body.owner_id)).fetchone():
            return row, "Assignee is not a member of this workspace."
        if body.owner_id != row["owner_id"] and c.execute("SELECT 1 FROM case_handovers WHERE workspace_id=%s AND case_id=%s AND status='pending'", (a["workspace_id"], cid)).fetchone():
            return row, "A handover is pending; the current owner is retained until it is accepted or cancelled."
    return row, None


def after(row, body):
    return {"owner_id": str(body.owner_id) if body.owner_id else None, "due_at": body.due_at} if body.set_owner and body.set_due else (
        {"owner_id": str(body.owner_id) if body.owner_id else None, "due_at": row["due_at"]} if body.set_owner else {"owner_id": str(row["owner_id"]) if row["owner_id"] else None, "due_at": body.due_at})


@router.post("/cases/bulk/preview")
def bulk_preview(body: BulkIn, a=Depends(actor)):
    body.check()
    rate("bulk-preview:" + str(a["user_id"]), 120)
    with connect() as c:
        writer(c, a)
        items = []
        for cid in body.case_ids:
            row, why = evaluate(c, a, body, cid, False)
            items.append({"case_id": cid, "title": row["title"] if row else None, "ok": why is None, "reason": why,
                          "before": {"owner_id": str(row["owner_id"]) if row and row["owner_id"] else None, "due_at": row["due_at"]} if row else None,
                          "after": after(row, body) if row and not why else None, "updated_at": row["updated_at"] if row else None})
        return {"items": items, "will_change": sum(1 for i in items if i["ok"]), "limit": MAX_BATCH,
                "interpretation": "Preview only. Nothing changes until you confirm; approval, evidence confirmation, resolution and reopening are never part of a bulk action."}


@router.post("/cases/bulk/apply")
def bulk_apply(body: BulkIn, a=Depends(actor)):
    body.check()
    rate("bulk-apply:" + str(a["user_id"]), 60)
    request = body.model_dump(mode="json", exclude={"expected"})
    request["case_ids"] = sorted(request["case_ids"])
    with connect() as c:
        writer(c, a)
        row = c.execute("INSERT INTO bulk_batches(workspace_id,id,actor_id,request,results) VALUES(%s,%s,%s,%s,'[]') ON CONFLICT DO NOTHING RETURNING id", (a["workspace_id"], body.request_id, a["user_id"], Jsonb(request))).fetchone()
        if not row:
            old = c.execute("SELECT request FROM bulk_batches WHERE workspace_id=%s AND id=%s", (a["workspace_id"], body.request_id)).fetchone()
            if old["request"] != request:
                raise HTTPException(409, "This request ID was already used for a different bulk action.")
    for cid in body.case_ids:  # one transaction per case: a failure never rolls back other cases, and a retry resumes where it stopped
        with connect() as c:
            writer(c, a)
            batch = c.execute("SELECT results,actor_id FROM bulk_batches WHERE workspace_id=%s AND id=%s FOR UPDATE", (a["workspace_id"], body.request_id)).fetchone()
            if batch["actor_id"] != a["user_id"]:
                raise HTTPException(403, "This request belongs to another user.")
            if any(r["case_id"] == cid for r in batch["results"]):
                continue
            row, why = evaluate(c, a, body, cid, True)
            result = {"case_id": cid, "status": "failed", "reason": why}
            if not why and body.expected.get(cid) and body.expected[cid] != row["updated_at"]:
                result = {"case_id": cid, "status": "stale", "reason": "The case changed after the preview. Preview again."}
            elif not why:
                new = after(row, body)
                if (new["owner_id"], new["due_at"]) == (str(row["owner_id"]) if row["owner_id"] else None, row["due_at"]):
                    result = {"case_id": cid, "status": "unchanged", "reason": None}
                else:
                    c.execute("UPDATE cases SET owner_id=%s,due_at=%s,updated_at=now() WHERE workspace_id=%s AND id=%s", (new["owner_id"], new["due_at"], a["workspace_id"], cid))
                    case_audit(c, a, cid, "case_assignment_updated", payload={"owner_id": new["owner_id"], "due_at": str(new["due_at"]) if new["due_at"] else None, "bulk_batch": str(body.request_id)})
                    result = {"case_id": cid, "status": "updated", "reason": None}
            c.execute("UPDATE bulk_batches SET results=results||%s WHERE workspace_id=%s AND id=%s", (Jsonb([result]), a["workspace_id"], body.request_id))
    results = one("SELECT results FROM bulk_batches WHERE workspace_id=%s AND id=%s", (a["workspace_id"], body.request_id))["results"]
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"batch_id": body.request_id, "results": results, "counts": counts}


# ---------------------------------------------------------------- document readiness tracker
class ReqIn(Model):
    id: UUID
    study_id: Text
    site_id: Text | None = None
    name: T(1, 120)
    guidance: str = Field(default="", max_length=500)
    requires_expiry: bool = False
    archived: bool = False
    expected_version: int = Field(ge=0)


def derive(req, rec, today):
    if rec is None or (rec["applicable"] and not rec["document_identity"].strip()):
        return "missing", "No document identity recorded."
    if not rec["applicable"]:
        return "not_applicable", rec["applicability_reason"]
    if req["requires_expiry"] and rec["expiry_date"] is None:
        return "missing", "An expiry date is required and none is recorded."
    if rec["expiry_date"] is not None and rec["expiry_date"] < today:
        return "expired", "Recorded expiry date has passed."
    if rec["requirement_version"] != req["version"]:
        return "awaiting_review", "The requirement changed after this record was reviewed; re-review it."
    if rec["review_status"] != "reviewed":
        return "awaiting_review", "Not yet reviewed."
    return "reviewed", "Reviewed as recorded for %s; this is a dated observation, not a current verification or compliance certification." % (rec["as_of"] or "an unrecorded date")


def readiness_rows(c, w, study, site=None):
    sites = c.execute("SELECT id,study_id FROM sites WHERE workspace_id=%s AND study_id=%s AND (%s::text IS NULL OR id=%s) ORDER BY id LIMIT 50", (w, study, site, site)).fetchall()
    reqs = c.execute("SELECT * FROM readiness_requirements WHERE workspace_id=%s AND study_id=%s ORDER BY name", (w, study)).fetchall()
    recs = {(r["requirement_id"], r["site_id"]): r for r in c.execute("SELECT * FROM readiness_records WHERE workspace_id=%s AND study_id=%s", (w, study)).fetchall()}
    today = datetime.now(timezone.utc).date()
    rows = []
    for s in sites:
        for q in reqs:
            if q["archived"] or (q["site_id"] and q["site_id"] != s["id"]):
                continue
            rec = recs.get((q["id"], s["id"]))
            status, why = derive(q, rec, today)
            rows.append({"requirement": q, "site_id": s["id"], "record": rec, "status": status, "reason": why,
                         "stale": bool(rec and rec["requirement_version"] != q["version"])})
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return rows, counts


@router.get("/readiness")
def readiness(study_id: str, site_id: str | None = None, a=Depends(actor)):
    with connect() as c:
        rows, counts = readiness_rows(c, a["workspace_id"], study_id, site_id)
        return {"rows": rows, "counts": counts, "interpretation": "Statuses reflect the records entered here as of their recorded dates. Historical snapshots and earlier reviews do not establish current readiness, expiry dates are never inferred, and this is not a compliance certification."}


@router.post("/readiness/requirements")
def save_requirement(body: ReqIn, a=Depends(actor)):
    rate("readiness-write:" + str(a["workspace_id"]), 200)
    with connect() as c:
        writer(c, a)
        w = a["workspace_id"]
        if not c.execute("SELECT 1 FROM studies WHERE workspace_id=%s AND id=%s", (w, body.study_id)).fetchone():
            raise HTTPException(422, "Choose a study from this workspace.")
        if body.site_id and not c.execute("SELECT 1 FROM sites WHERE workspace_id=%s AND study_id=%s AND id=%s", (w, body.study_id, body.site_id)).fetchone():
            raise HTTPException(422, "Choose a site belonging to the selected study.")
        old = c.execute("SELECT * FROM readiness_requirements WHERE workspace_id=%s AND id=%s FOR UPDATE", (w, body.id)).fetchone()
        if not old:
            if body.expected_version != 0:
                raise HTTPException(404, "Requirement not found in this workspace.")
            c.execute("INSERT INTO readiness_requirements(workspace_id,id,study_id,site_id,name,guidance,requires_expiry,archived,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)", (w, body.id, body.study_id, body.site_id, body.name, body.guidance, body.requires_expiry, body.archived, a["user_id"]))
            hist(c, a, "readiness", body.id, "requirement_defined", body.model_dump(mode="json", exclude={"expected_version"}))
        else:
            stale(old, body.expected_version)
            if old["study_id"] != body.study_id:
                raise HTTPException(422, "A requirement cannot move to another study.")
            changed = {k: [old[k], getattr(body, k)] for k in ("site_id", "name", "guidance", "requires_expiry", "archived") if old[k] != getattr(body, k)}
            if changed:
                c.execute("UPDATE readiness_requirements SET site_id=%s,name=%s,guidance=%s,requires_expiry=%s,archived=%s,version=version+1,updated_at=now() WHERE workspace_id=%s AND id=%s", (body.site_id, body.name, body.guidance, body.requires_expiry, body.archived, w, body.id))
                n = c.execute("SELECT count(*) AS n FROM readiness_records WHERE workspace_id=%s AND requirement_id=%s", (w, body.id)).fetchone()["n"]
                hist(c, a, "readiness", body.id, "requirement_changed", {"changed": changed, "records_needing_re_review": n})
        rows, counts = readiness_rows(c, w, body.study_id)
        return {"counts": counts, "requirement": c.execute("SELECT * FROM readiness_requirements WHERE workspace_id=%s AND id=%s", (w, body.id)).fetchone()}


class RecIn(Model):
    requirement_id: UUID
    site_id: Text
    applicable: bool = True
    applicability_reason: str = Field(default="", max_length=300)
    document_identity: str = Field(default="", max_length=200)
    document_version: str = Field(default="", max_length=60)
    expiry_date: date | None = None
    as_of: date | None = None
    evidence: list[dict] = Field(default=[], max_length=10)
    expected_version: int = Field(ge=0)


@router.post("/readiness/records")
def save_record(body: RecIn, a=Depends(actor)):
    rate("readiness-write:" + str(a["workspace_id"]), 200)
    with connect() as c:
        writer(c, a)
        w = a["workspace_id"]
        req = c.execute("SELECT * FROM readiness_requirements WHERE workspace_id=%s AND id=%s FOR SHARE", (w, body.requirement_id)).fetchone()
        if not req or req["archived"]:
            raise HTTPException(404, "Requirement not found or archived.")
        if (req["site_id"] and req["site_id"] != body.site_id) or not c.execute("SELECT 1 FROM sites WHERE workspace_id=%s AND study_id=%s AND id=%s", (w, req["study_id"], body.site_id)).fetchone():
            raise HTTPException(422, "This requirement does not apply to that site.")
        if not body.applicable and len(body.applicability_reason.strip()) < 5:
            raise HTTPException(422, "Explain why the requirement is not applicable.")
        if body.applicable and body.document_identity.strip() and not body.as_of:
            raise HTTPException(422, "Record the date the document was observed.")
        if body.as_of and body.as_of > datetime.now(timezone.utc).date():
            raise HTTPException(422, "The observation date cannot be in the future.")
        ev = []
        for e in body.evidence:
            if set(e) - {"kind", "ref", "note"} or e.get("kind") not in ("case_evidence", "note") or len(str(e.get("ref", "")).strip()) < 3:
                raise HTTPException(422, "Evidence must be a case evidence ID or a located reference note.")
            if e["kind"] == "case_evidence" and not c.execute("SELECT 1 FROM case_evidence ce JOIN cases k ON (k.workspace_id,k.id)=(ce.workspace_id,ce.case_id) WHERE ce.workspace_id=%s AND ce.id::text=%s AND k.study_id=%s AND k.site_id=%s", (w, str(e["ref"]), req["study_id"], body.site_id)).fetchone():
                raise HTTPException(422, "Case evidence must belong to this study and site in this workspace.")
            ev.append({"kind": e["kind"], "ref": str(e["ref"]).strip(), "note": str(e.get("note", ""))[:200]})
        review = "awaiting_review" if body.applicable and body.document_identity.strip() else "not_reviewed"
        old = c.execute("SELECT * FROM readiness_records WHERE workspace_id=%s AND requirement_id=%s AND site_id=%s FOR UPDATE", (w, body.requirement_id, body.site_id)).fetchone()
        vals = (body.applicable, body.applicability_reason, body.document_identity.strip(), body.document_version.strip(), body.expiry_date, body.as_of, Jsonb(ev), review, req["version"])
        if not old:
            if body.expected_version != 0:
                raise HTTPException(409, "This record changed. Reload before saving.")
            rid = uuid4()
            c.execute("INSERT INTO readiness_records(workspace_id,id,requirement_id,study_id,site_id,applicable,applicability_reason,document_identity,document_version,expiry_date,as_of,evidence,review_status,requirement_version,recorded_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (w, rid, body.requirement_id, req["study_id"], body.site_id) + vals + (a["user_id"],))
        else:
            stale(old, body.expected_version)
            rid = old["id"]
            c.execute("UPDATE readiness_records SET applicable=%s,applicability_reason=%s,document_identity=%s,document_version=%s,expiry_date=%s,as_of=%s,evidence=%s,review_status=%s,requirement_version=%s,reviewer_id=NULL,reviewed_at=NULL,version=version+1,updated_at=now(),recorded_by=%s WHERE workspace_id=%s AND id=%s", vals + (a["user_id"], w, rid))
        hist(c, a, "readiness", rid, "record_saved", {"requirement": str(body.requirement_id), "site_id": body.site_id, "applicable": body.applicable, "document_identity": body.document_identity, "document_version": body.document_version, "expiry_date": str(body.expiry_date) if body.expiry_date else None, "as_of": str(body.as_of) if body.as_of else None, "evidence": ev, "requirement_version": req["version"]})
        return c.execute("SELECT * FROM readiness_records WHERE workspace_id=%s AND id=%s", (w, rid)).fetchone()


class ReviewIn(Model):
    expected_version: int = Field(ge=1)
    note: str = Field(default="", max_length=300)


@router.post("/readiness/records/{rid}/review")
def review_record(rid: UUID, body: ReviewIn, a=Depends(actor)):
    with connect() as c:
        writer(c, a)
        w = a["workspace_id"]
        rec = c.execute("SELECT * FROM readiness_records WHERE workspace_id=%s AND id=%s FOR UPDATE", (w, rid)).fetchone()
        if not rec:
            raise HTTPException(404, "Record not found in this workspace.")
        stale(rec, body.expected_version)
        req = c.execute("SELECT * FROM readiness_requirements WHERE workspace_id=%s AND id=%s FOR SHARE", (w, rec["requirement_id"])).fetchone()
        if req["version"] != rec["requirement_version"]:
            raise HTTPException(409, "The requirement changed. Update the record against the current requirement before reviewing.")
        if not rec["applicable"] or not rec["document_identity"].strip() or not rec["evidence"]:
            raise HTTPException(422, "A reviewed record needs an applicable requirement, a document identity and supporting evidence.")
        if req["requires_expiry"] and rec["expiry_date"] is None:
            raise HTTPException(422, "This requirement needs an expiry date before review.")
        c.execute("UPDATE readiness_records SET review_status='reviewed',reviewer_id=%s,reviewed_at=now(),version=version+1,updated_at=now() WHERE workspace_id=%s AND id=%s", (a["user_id"], w, rid))
        hist(c, a, "readiness", rid, "record_reviewed", {"note": body.note, "requirement_version": rec["requirement_version"], "record_version": rec["version"] + 1})
        return c.execute("SELECT * FROM readiness_records WHERE workspace_id=%s AND id=%s", (w, rid)).fetchone()


@router.get("/readiness/history")
def readiness_history(study_id: str, a=Depends(actor)):
    require(a)
    with connect() as c:
        w = a["workspace_id"]
        ids = [str(r["id"]) for r in c.execute("SELECT id FROM readiness_requirements WHERE workspace_id=%s AND study_id=%s UNION SELECT id FROM readiness_records WHERE workspace_id=%s AND study_id=%s", (w, study_id, w, study_id)).fetchall()]
        return c.execute("SELECT id,ref_id,kind,actor_name,payload,created_at FROM improvement_events WHERE workspace_id=%s AND scope='readiness' AND ref_id=ANY(%s) ORDER BY created_at DESC LIMIT 100", (w, ids)).fetchall()


# ---------------------------------------------------------------- procedure-change impact review (deterministic comparison, not AI)
def passages(text):
    out, head, buf = [], "", []

    def flush():
        if buf:
            out.append({"section": head or "Passage %d" % (len(out) + 1), "text": "\n".join(buf).strip()})
            buf.clear()

    for line in text.replace("\r\n", "\n").split("\n"):
        if line.lstrip().startswith("#"):
            flush()
            head = line.lstrip("# ").strip() or head
        elif not line.strip():
            flush()
        else:
            buf.append(line.rstrip())
    flush()
    return [p for p in out if p["text"]]


def compare_versions(old_text, new_text):
    o, n = passages(old_text), passages(new_text)
    changes = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, [p["text"] for p in o], [p["text"] for p in n], autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        for k in range(max(i2 - i1, j2 - j1)):
            before = o[i1 + k] if i1 + k < i2 else None
            now = n[j1 + k] if j1 + k < j2 else None
            changes.append({"change": "changed" if before and now else "removed" if before else "added", "section_old": before["section"] if before else None, "section_new": now["section"] if now else None,
                            "old_text": before["text"] if before else "", "new_text": now["text"] if now else "",
                            "lines": list(difflib.unified_diff((before or {"text": ""})["text"].splitlines(), (now or {"text": ""})["text"].splitlines(), "old", "new", lineterm="", n=0))[2:]})
    return changes[:60], len(changes)


def impact_data(c, w, article, old, new):
    k = c.execute("SELECT id,title,archived,version FROM knowledge WHERE workspace_id=%s AND id=%s", (w, article)).fetchone()
    if not k:
        raise HTTPException(404, "Procedure not found in this workspace.")
    vs = {r["version"]: r for r in c.execute("SELECT version,title,content,created_at FROM procedure_versions WHERE workspace_id=%s AND article_id=%s ORDER BY version", (w, article)).fetchall()}
    if old not in vs or new not in vs or old >= new:
        raise HTTPException(422, "Choose two retained versions, older first. Versions saved before this release may not have been retained.")
    changes, total = compare_versions(vs[old]["content"], vs[new]["content"])
    digest = hashlib.sha256(json.dumps([vs[old]["content"], vs[new]["content"]]).encode()).hexdigest()
    checks = [x for x in c.execute("SELECT id,case_id,run_id,status,due_at,sources FROM investigation_checks WHERE workspace_id=%s AND status IN ('active','draft') AND sources @> %s LIMIT 200", (w, Jsonb([{"article_id": article}]))).fetchall()
              if any(s.get("article_id") == article and s.get("version") == old for s in x["sources"])]
    runs = []
    for r in c.execute("SELECT r.id,r.case_id,r.result,r.decision,r.review_notes,r.reviewed_at,k.status AS case_status,k.title FROM runs r JOIN cases k ON (k.workspace_id,k.id)=(r.workspace_id,r.case_id) WHERE r.workspace_id=%s AND r.result->'sources' @> %s ORDER BY r.created_at DESC LIMIT 200", (w, Jsonb([{"article_id": article}]))).fetchall():
        cited = set(r["result"]["recommendation"]["evidence_ids"])
        srcs = [s for s in r["result"].get("sources", []) if s.get("article_id") == article and s["id"] in cited and s.get("version") == old]
        if not srcs:
            continue
        re = c.execute("SELECT status,rationale FROM procedure_reassessments WHERE workspace_id=%s AND run_id=%s AND article_id=%s AND new_version=%s", (w, r["id"], article, new)).fetchone()
        runs.append({"run_id": r["id"], "case_id": r["case_id"], "case_title": r["title"], "case_status": r["case_status"], "cited_passages": [{"source_id": s["id"], "section": s.get("title") or s.get("heading"), "version": s["version"]} for s in srcs],
                     "past_decision": r["decision"], "past_decision_at": r["reviewed_at"], "reassessment": re["status"] if re else None})
    review = c.execute("SELECT x.*,u.name AS reviewer_name FROM procedure_impact_reviews x LEFT JOIN users u ON u.id=x.reviewer_id WHERE x.workspace_id=%s AND x.article_id=%s AND x.old_version=%s AND x.new_version=%s", (w, article, old, new)).fetchone()
    return {"procedure": k, "old_version": old, "new_version": new, "versions": [{"version": v, "title": r["title"], "created_at": r["created_at"]} for v, r in vs.items()],
            "method": "Deterministic passage comparison; this is not AI output and it does not decide whether anything must be reassessed.",
            "changes": changes, "total_changes": total, "comparison_hash": digest,
            "affected_checks": [{"check_id": x["id"], "case_id": x["case_id"], "status": x["status"], "due_at": x["due_at"]} for x in checks],
            "affected_cases": runs, "review": review,
            "superseded_by": k["version"] if k["version"] > new else None, "archived": k["archived"],
            "preserved": "Cited versions, checks and past decisions are never rewritten; changing any of them is a separate human action."}


@router.get("/knowledge/{article}/impact-review")
def impact_review(article: str, old: int | None = None, new: int | None = None, a=Depends(actor)):
    with connect() as c:
        w = a["workspace_id"]
        k = c.execute("SELECT version FROM knowledge WHERE workspace_id=%s AND id=%s", (w, article)).fetchone()
        if not k:
            raise HTTPException(404, "Procedure not found in this workspace.")
        new = new or k["version"]
        return impact_data(c, w, article, old or new - 1, new)


class ImpactIn(Model):
    old_version: int = Field(ge=1)
    new_version: int = Field(ge=2)
    status: Literal["needed", "not_needed"]
    rationale: T(10, 1000)
    comparison_hash: Text
    expected_version: int = Field(ge=0)


@router.post("/knowledge/{article}/impact-review")
def record_impact(article: str, body: ImpactIn, a=Depends(actor)):
    with connect() as c:
        writer(c, a)
        w = a["workspace_id"]
        c.execute("SELECT 1 FROM knowledge WHERE workspace_id=%s AND id=%s FOR SHARE", (w, article))
        d = impact_data(c, w, article, body.old_version, body.new_version)
        if d["comparison_hash"] != body.comparison_hash:
            raise HTTPException(409, "The compared procedure text changed. Reload the comparison before recording a decision.")
        old = c.execute("SELECT * FROM procedure_impact_reviews WHERE workspace_id=%s AND article_id=%s AND old_version=%s AND new_version=%s FOR UPDATE", (w, article, body.old_version, body.new_version)).fetchone()
        if not old:
            if body.expected_version != 0:
                raise HTTPException(409, "This review changed. Reload before saving.")
            row = c.execute("INSERT INTO procedure_impact_reviews(workspace_id,id,article_id,old_version,new_version,status,rationale,reviewer_id,comparison_hash) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *", (w, uuid4(), article, body.old_version, body.new_version, body.status, body.rationale, a["user_id"], body.comparison_hash)).fetchone()
        else:
            stale(old, body.expected_version)
            row = c.execute("UPDATE procedure_impact_reviews SET status=%s,rationale=%s,reviewer_id=%s,reviewed_at=now(),version=version+1 WHERE workspace_id=%s AND id=%s RETURNING *", (body.status, body.rationale, a["user_id"], w, old["id"])).fetchone()
        hist(c, a, "procedure", article, "impact_reviewed", {"old_version": body.old_version, "new_version": body.new_version, "status": body.status, "rationale": body.rationale, "affected_cases": [x["case_id"] for x in d["affected_cases"]], "affected_checks": len(d["affected_checks"]), "review_version": row["version"]})
        for cid in list(dict.fromkeys(x["case_id"] for x in d["affected_cases"] if x["case_status"] == "open"))[:50]:
            case_audit(c, a, cid, "procedure_impact_reviewed", body.rationale, {"article_id": article, "old_version": body.old_version, "new_version": body.new_version, "reassessment_needed": body.status == "needed"})
        return impact_data(c, w, article, body.old_version, body.new_version)


# ---------------------------------------------------------------- feedback triage queue
STATES = ("received", "reviewing", "planned", "in_progress", "completed", "declined")


def maintainer(c, a):
    from five_features import current
    if current(c, a) != "owner":
        raise HTTPException(403, "Only workspace owners can triage feedback.")


@router.get("/feedback/queue")
def feedback_queue(a=Depends(actor)):
    with connect() as c:
        maintainer(c, a)
        w = a["workspace_id"]
        items = c.execute(
            """SELECT f.id,f.rating,f.message,f.created_at,u.name AS submitter,coalesce(t.status,'received') AS status,t.owner_id,o.name AS owner_name,coalesce(t.internal_note,'') AS internal_note,
            coalesce(t.public_note,'') AS public_note,coalesce(t.confidential,false) AS confidential,t.improvement_id,coalesce(t.related_feedback,'[]') AS related_feedback,coalesce(t.version,0) AS version,
            t.status_changed_at,t.updated_at FROM feedback f LEFT JOIN users u ON u.id=f.actor_id LEFT JOIN feedback_triage t ON t.workspace_id=f.workspace_id AND t.feedback_id=f.id
            LEFT JOIN users o ON o.id=t.owner_id WHERE f.workspace_id=%s ORDER BY f.created_at DESC LIMIT 100""", (w,)).fetchall()
        imps = c.execute("SELECT i.*,u.name AS owner_name FROM improvements i LEFT JOIN users u ON u.id=i.owner_id WHERE i.workspace_id=%s ORDER BY i.updated_at DESC LIMIT 100", (w,)).fetchall()
        owners = c.execute("SELECT u.id,u.name FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.workspace_id=%s AND m.role='owner' ORDER BY u.name", (w,)).fetchall()
        return {"items": items, "improvements": imps, "owners": owners, "states": STATES}


class ImprovementIn(Model):
    id: UUID
    title: T(1, 120)
    description: str = Field(default="", max_length=1000)
    status: Literal["planned", "in_progress", "completed", "declined"] = "planned"
    owner_id: UUID | None = None
    explanation: str = Field(default="", max_length=1000)
    expected_version: int = Field(ge=0)


@router.post("/improvements")
def save_improvement(body: ImprovementIn, a=Depends(actor)):
    with connect() as c:
        maintainer(c, a)
        w = a["workspace_id"]
        if body.owner_id and not c.execute("SELECT 1 FROM memberships WHERE workspace_id=%s AND user_id=%s AND role='owner'", (w, body.owner_id)).fetchone():
            raise HTTPException(422, "The owner must be a workspace owner.")
        if body.status in ("completed", "declined") and len(body.explanation.strip()) < 5:
            raise HTTPException(422, "Explain the outcome.")
        old = c.execute("SELECT * FROM improvements WHERE workspace_id=%s AND id=%s FOR UPDATE", (w, body.id)).fetchone()
        if not old:
            if body.expected_version != 0:
                raise HTTPException(404, "Improvement not found in this workspace.")
            c.execute("INSERT INTO improvements(workspace_id,id,title,description,status,owner_id,explanation,created_by,completed_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s='completed' THEN now() END)", (w, body.id, body.title, body.description, body.status, body.owner_id, body.explanation, a["user_id"], body.status))
        else:
            stale(old, body.expected_version)
            c.execute("UPDATE improvements SET title=%s,description=%s,status=%s,owner_id=%s,explanation=%s,version=version+1,updated_at=now(),completed_at=CASE WHEN %s='completed' THEN coalesce(completed_at,now()) ELSE NULL END WHERE workspace_id=%s AND id=%s", (body.title, body.description, body.status, body.owner_id, body.explanation, body.status, w, body.id))
        hist(c, a, "improvement", body.id, "improvement_saved", {"title": body.title, "status": body.status, "owner_id": str(body.owner_id) if body.owner_id else None, "explanation": body.explanation})
        return c.execute("SELECT * FROM improvements WHERE workspace_id=%s AND id=%s", (w, body.id)).fetchone()


class TriageIn(Model):
    expected_version: int = Field(ge=0)
    status: Literal["received", "reviewing", "planned", "in_progress", "completed", "declined"]
    owner_id: UUID | None = None
    internal_note: str = Field(default="", max_length=1000)
    public_note: str = Field(default="", max_length=500)
    confidential: bool = False
    improvement_id: UUID | None = None
    related_feedback: list[UUID] = Field(default=[], max_length=10)


@router.post("/feedback/{fid}/triage")
def triage(fid: UUID, body: TriageIn, a=Depends(actor)):
    with connect() as c:
        maintainer(c, a)
        w = a["workspace_id"]
        if not c.execute("SELECT 1 FROM feedback WHERE workspace_id=%s AND id=%s", (w, fid)).fetchone():
            raise HTTPException(404, "Feedback not found in this workspace.")
        if body.owner_id and not c.execute("SELECT 1 FROM memberships WHERE workspace_id=%s AND user_id=%s AND role='owner'", (w, body.owner_id)).fetchone():
            raise HTTPException(422, "The owner must be a workspace owner.")
        if body.improvement_id and not c.execute("SELECT 1 FROM improvements WHERE workspace_id=%s AND id=%s", (w, body.improvement_id)).fetchone():
            raise HTTPException(422, "Choose an improvement from this workspace.")
        rel = list(dict.fromkeys(body.related_feedback))
        if fid in rel or (rel and c.execute("SELECT count(*) AS n FROM feedback WHERE workspace_id=%s AND id=ANY(%s)", (w, rel)).fetchone()["n"] != len(rel)):
            raise HTTPException(422, "Related feedback must be other feedback from this workspace.")
        if body.status in ("completed", "declined") and len((body.internal_note + body.public_note).strip()) < 5:
            raise HTTPException(422, "Explain the outcome.")
        old = c.execute("SELECT * FROM feedback_triage WHERE workspace_id=%s AND feedback_id=%s FOR UPDATE", (w, fid)).fetchone()
        if not old:
            if body.expected_version != 0:
                raise HTTPException(409, "This item changed. Reload before saving.")
            c.execute("INSERT INTO feedback_triage(workspace_id,feedback_id,status,owner_id,internal_note,public_note,confidential,improvement_id,related_feedback) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)", (w, fid, body.status, body.owner_id, body.internal_note, body.public_note, body.confidential, body.improvement_id, Jsonb([str(x) for x in rel])))
        else:
            stale(old, body.expected_version)
            c.execute("UPDATE feedback_triage SET status=%s,owner_id=%s,internal_note=%s,public_note=%s,confidential=%s,improvement_id=%s,related_feedback=%s,version=version+1,updated_at=now(),status_changed_at=CASE WHEN status<>%s THEN now() ELSE status_changed_at END WHERE workspace_id=%s AND feedback_id=%s", (body.status, body.owner_id, body.internal_note, body.public_note, body.confidential, body.improvement_id, Jsonb([str(x) for x in rel]), body.status, w, fid))
        hist(c, a, "feedback", fid, "triaged", {"status": body.status, "owner_id": str(body.owner_id) if body.owner_id else None, "improvement_id": str(body.improvement_id) if body.improvement_id else None, "confidential": body.confidential})
        return {"status": "saved"}


@router.get("/feedback/mine")
def my_feedback(a=Depends(actor)):
    """Submitters see only their own feedback in the current workspace and only the safe parts of its status."""
    with connect() as c:
        rows = c.execute(
            """SELECT f.id,f.rating,f.message,f.created_at,coalesce(t.status,'received') AS status,t.status_changed_at,coalesce(t.confidential,false) AS confidential,
            CASE WHEN coalesce(t.confidential,false) THEN '' ELSE coalesce(t.public_note,'') END AS public_note,
            CASE WHEN t.confidential THEN NULL ELSE i.title END AS improvement_title, CASE WHEN t.confidential THEN NULL ELSE i.status END AS improvement_status
            FROM feedback f LEFT JOIN feedback_triage t ON t.workspace_id=f.workspace_id AND t.feedback_id=f.id LEFT JOIN improvements i ON i.workspace_id=t.workspace_id AND i.id=t.improvement_id
            WHERE f.workspace_id=%s AND f.actor_id=%s ORDER BY f.created_at DESC LIMIT 50""", (a["workspace_id"], a["user_id"])).fetchall()
        for r in rows:
            if r["confidential"]:
                r["status"] = "received" if r["status"] == "received" else "reviewing"
            r.pop("confidential")
        return rows
