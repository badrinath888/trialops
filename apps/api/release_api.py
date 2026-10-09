"""Workspace-scoped routes extending the existing case/evidence workflows."""

import difflib, json
from datetime import datetime, timezone
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, Response
from psycopg.types.json import Jsonb
from db import connect, query, one
from security import actor, require, rate
from models import (
    CheckEdit,
    RequestCreate,
    RequestEdit,
    EvidenceCreate,
    ComparisonCreate,
    RelatedLink,
    EffortCreate,
    PolicyEdit,
    ReassessmentEdit,
    VisitCreate,
    VisitEdit,
    ImportPreview,
    ImportCommit,
    NotificationPrefs,
    EvaluationCreate,
    WalkthroughUpdate,
    Note,
    Versioned,
)
from workflows import (
    checklist_suggestions,
    check_items,
    compare_snapshots,
    evidence_flags,
    preview_rows,
    save_snapshot,
    canonical,
)
from tools import terms

router = APIRouter()


def case(a, cid, c=None, lock=False):
    from main import get_case

    return get_case(a, cid, c, lock)


def run(a, rid, c=None, lock=False):
    from main import get_run

    return get_run(a, rid, c, lock)


def audit(c, a, cid, kind, notes="", rid=None, payload=None):
    from main import event

    return event(c, a, cid, kind, notes, rid, payload)


def member(c, a, uid):
    if (
        uid
        and not c.execute(
            "SELECT 1 FROM memberships WHERE workspace_id=%s AND user_id=%s",
            (a["workspace_id"], uid),
        ).fetchone()
    ):
        raise HTTPException(422, "Owner must belong to this workspace.")


def refs(c, a, cid, ids):
    for eid in ids:
        if not c.execute(
            "SELECT 1 FROM case_evidence WHERE workspace_id=%s AND case_id=%s AND id=%s",
            (a["workspace_id"], cid, eid),
        ).fetchone():
            raise HTTPException(
                422, "Evidence reference must belong to this case and workspace."
            )


def row_version(c, a, table, rid, expected):
    # Only internal, constant table names reach this helper.
    row = c.execute(
        f"SELECT * FROM {table} WHERE workspace_id=%s AND id=%s FOR UPDATE",
        (a["workspace_id"], rid),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Record not found in this workspace.")
    if row["version"] != expected:
        raise HTTPException(409, "This record changed. Reload before saving.")
    return row


def request_view(row):
    row = dict(row)
    row["effective_status"] = (
        "overdue"
        if row["status"] == "requested"
        and row["due_at"]
        and row["due_at"] < datetime.now(timezone.utc)
        else row["status"]
    )
    row["copy_text"] = (
        "Information request: "
        + row["title"]
        + "\nCase: "
        + row["case_id"]
        + "\nRequested items:\n"
        + "\n".join("- " + x for x in row["items"])
        + "\nDue: "
        + str(row["due_at"] or "Not specified")
        + "\nOwner: "
        + str(row.get("owner_name") or "Unassigned")
        + "\nCopying or saving this request does not send a message."
    )
    return row


@router.get("/cases/{cid}/workflow")
def case_workflow(cid: str, a=Depends(actor)):
    item = case(a, cid)
    w = a["workspace_id"]
    checks = query(
        "SELECT * FROM investigation_checks WHERE workspace_id=%s AND case_id=%s ORDER BY created_at",
        (w, cid),
    )
    requests = query(
        "SELECT r.*,u.name AS owner_name FROM information_requests r LEFT JOIN users u ON u.id=r.owner_id WHERE r.workspace_id=%s AND r.case_id=%s ORDER BY r.created_at DESC",
        (w, cid),
    )
    evidence = query(
        "SELECT * FROM case_evidence WHERE workspace_id=%s AND case_id=%s ORDER BY created_at DESC",
        (w, cid),
    )
    comparisons = query(
        "SELECT * FROM snapshot_comparisons WHERE workspace_id=%s AND case_id=%s ORDER BY created_at DESC",
        (w, cid),
    )
    policy = one("SELECT * FROM workspace_policies WHERE workspace_id=%s", (w,))
    current = one(
        "SELECT evidence FROM operations WHERE workspace_id=%s AND study_id=%s AND site_id=%s",
        (w, item["study_id"], item["site_id"]),
    )
    return {
        "checks": checks,
        "requests": [request_view(r) for r in requests],
        "evidence": evidence,
        "comparisons": comparisons,
        "flags": evidence_flags(
            item,
            current["evidence"] if current else {},
            policy["freshness_hours"] if policy else None,
        ),
        "reassessments": query(
            "SELECT * FROM procedure_reassessments WHERE workspace_id=%s AND case_id=%s ORDER BY created_at DESC",
            (w, cid),
        ),
        "effort": query(
            "SELECT * FROM human_effort WHERE workspace_id=%s AND case_id=%s ORDER BY recorded_at DESC",
            (w, cid),
        ),
    }


@router.post("/runs/{rid}/checks", status_code=201)
def create_checks(rid: UUID, a=Depends(actor)):
    with connect() as c:
        r = run(a, rid, c)
        case(a, r["case_id"], c, True)
        if r["result"]["recommendation"]["status"] != "supported":
            raise HTTPException(
                422, "No supported cited procedures are available for checks."
            )
        old = c.execute(
            "SELECT * FROM investigation_checks WHERE workspace_id=%s AND run_id=%s",
            (a["workspace_id"], rid),
        ).fetchone()
        if old:
            return old
        sources, items = checklist_suggestions(r["result"])
        row = c.execute(
            "INSERT INTO investigation_checks(workspace_id,id,case_id,run_id,sources,items,actor_id) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                a["workspace_id"],
                uuid4(),
                r["case_id"],
                rid,
                Jsonb(sources),
                Jsonb(items),
                a["user_id"],
            ),
        ).fetchone()
        audit(
            c,
            a,
            r["case_id"],
            "checks_suggested",
            rid=rid,
            payload={
                "checklist_id": str(row["id"]),
                "sources": [s["id"] for s in sources],
                "suggestions_only": True,
            },
        )
        return row


@router.post("/cases/{cid}/checks/{check_id}")
def edit_checks(cid: str, check_id: UUID, body: CheckEdit, a=Depends(actor)):
    with connect() as c:
        case(a, cid, c, True)
        row = row_version(c, a, "investigation_checks", check_id, body.expected_version)
        if row["case_id"] != cid:
            raise HTTPException(404, "Checklist not found for this case.")
        items = body.model_dump(mode="json")["items"]
        for item in items:
            refs(c, a, cid, item["evidence_refs"])
        structure = lambda xs: [(x["id"], x["text"], x["source_id"]) for x in xs]
        changed = structure(items) != structure(row["items"])
        if row["status"] == "active" and changed:
            require(a)
        if row["status"] == "draft" and any(i["state"] != "not_checked" for i in items):
            raise HTTPException(
                422, "Activate the reviewed checklist before recording check outcomes."
            )
        saved = check_items(items, row["sources"], row["items"], a)
        old_by = {i["id"]: i for i in row["items"]}
        for i in saved:
            i["suggestion"] = old_by.get(i["id"], {}).get("suggestion", False)
        status = "draft" if changed else row["status"]
        if changed:
            for i in saved:
                i.update(state="not_checked", notes="", evidence_refs=[])
        result = c.execute(
            "UPDATE investigation_checks SET items=%s,due_at=%s,status=%s,version=version+1,updated_at=now(),activated_by=CASE WHEN %s THEN NULL ELSE activated_by END,activated_at=CASE WHEN %s THEN NULL ELSE activated_at END WHERE workspace_id=%s AND id=%s RETURNING *",
            (
                Jsonb(saved),
                body.due_at,
                status,
                changed,
                changed,
                a["workspace_id"],
                check_id,
            ),
        ).fetchone()
        audit(
            c,
            a,
            cid,
            "checks_updated",
            rid=row["run_id"],
            payload={
                "checklist_id": str(check_id),
                "version": result["version"],
                "status": status,
                "items": saved,
            },
        )
        return result


@router.post("/cases/{cid}/checks/{check_id}/activate")
def activate_checks(cid: str, check_id: UUID, body: Versioned, a=Depends(actor)):
    require(a)
    with connect() as c:
        case(a, cid, c, True)
        row = row_version(c, a, "investigation_checks", check_id, body.expected_version)
        if row["case_id"] != cid:
            raise HTTPException(404, "Checklist not found for this case.")
        if row["status"] != "draft":
            raise HTTPException(409, "Checklist is already active.")
        row = c.execute(
            "UPDATE investigation_checks SET status='active',activated_by=%s,activated_at=now(),updated_at=now(),version=version+1 WHERE workspace_id=%s AND id=%s RETURNING *",
            (a["user_id"], a["workspace_id"], check_id),
        ).fetchone()
        audit(
            c,
            a,
            cid,
            "checks_activated",
            rid=row["run_id"],
            payload={
                "checklist_id": str(check_id),
                "version": row["version"],
                "items": row["items"],
            },
        )
        return row


@router.post("/cases/{cid}/evidence", status_code=201)
def add_evidence(cid: str, body: EvidenceCreate, a=Depends(actor)):
    if body.observed_at > datetime.now(timezone.utc):
        raise HTTPException(422, "Observation time cannot be in the future.")
    with connect() as c:
        item = case(a, cid, c, True)
        old = c.execute(
            "SELECT * FROM case_evidence WHERE workspace_id=%s AND id=%s",
            (a["workspace_id"], body.id),
        ).fetchone()
        if old:
            if (
                old["case_id"] != cid
                or old["summary"] != body.summary
                or old["kind"] != body.kind
                or old["observed_at"] != body.observed_at
                or old["reference_id"] != body.reference_id
            ):
                raise HTTPException(
                    409, "Evidence ID already contains a different observation."
                )
            return old
        if body.kind == "snapshot":
            try:
                rid = UUID(body.reference_id or "")
            except ValueError:
                raise HTTPException(422, "Choose a snapshot identifier.")
            snap = c.execute(
                "SELECT * FROM snapshot_history WHERE workspace_id=%s AND id=%s",
                (a["workspace_id"], rid),
            ).fetchone()
            if (
                not snap
                or (snap["study_id"], snap["site_id"])
                != (item["study_id"], item["site_id"])
                or body.observed_at != snap["observed_at"]
            ):
                raise HTTPException(
                    422,
                    "Snapshot evidence must preserve its scope and observation timestamp.",
                )
        if body.kind == "request_response":
            try:
                rid = UUID(body.reference_id or "")
            except ValueError:
                raise HTTPException(422, "Choose a request identifier.")
            if not c.execute(
                "SELECT 1 FROM information_requests WHERE workspace_id=%s AND id=%s AND case_id=%s",
                (a["workspace_id"], rid, cid),
            ).fetchone():
                raise HTTPException(422, "Response request must belong to this case.")
        row = c.execute(
            "INSERT INTO case_evidence(workspace_id,id,case_id,kind,reference_id,summary,observed_at,actor_id,actor_name) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                a["workspace_id"],
                body.id,
                cid,
                body.kind,
                body.reference_id,
                body.summary,
                body.observed_at,
                a["user_id"],
                a["name"],
            ),
        ).fetchone()
        audit(
            c,
            a,
            cid,
            "evidence_recorded",
            body.summary,
            payload={
                "evidence_id": str(body.id),
                "kind": body.kind,
                "observed_at": body.observed_at.isoformat(),
            },
        )
        return row


@router.post("/cases/{cid}/requests", status_code=201)
def create_request(cid: str, body: RequestCreate, a=Depends(actor)):
    with connect() as c:
        case(a, cid, c, True)
        r = run(a, body.run_id, c)
        if r["case_id"] != cid:
            raise HTTPException(422, "Request investigation must belong to this case.")
        member(c, a, body.owner_id)
        old = c.execute(
            "SELECT * FROM information_requests WHERE workspace_id=%s AND id=%s",
            (a["workspace_id"], body.id),
        ).fetchone()
        if old:
            if (
                old["case_id"] != cid
                or old["title"] != body.title
                or old["items"] != body.items
                or old["run_id"] != body.run_id
                or old["owner_id"] != body.owner_id
                or old["due_at"] != body.due_at
            ):
                raise HTTPException(
                    409, "Request ID already contains a different request."
                )
            return request_view(old)
        row = c.execute(
            "INSERT INTO information_requests(workspace_id,id,case_id,run_id,title,items,owner_id,due_at,actor_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                a["workspace_id"],
                body.id,
                cid,
                body.run_id,
                body.title,
                Jsonb(body.items),
                body.owner_id,
                body.due_at,
                a["user_id"],
            ),
        ).fetchone()
        audit(
            c,
            a,
            cid,
            "information_request_drafted",
            body.title,
            body.run_id,
            {"request_id": str(body.id), "items": body.items, "no_message_sent": True},
        )
        return request_view(row)


@router.post("/cases/{cid}/requests/{request_id}")
def edit_request(cid: str, request_id: UUID, body: RequestEdit, a=Depends(actor)):
    with connect() as c:
        case(a, cid, c, True)
        row = row_version(
            c, a, "information_requests", request_id, body.expected_version
        )
        if row["case_id"] != cid:
            raise HTTPException(404, "Request not found for this case.")
        member(c, a, body.owner_id)
        refs(c, a, cid, body.evidence_refs)
        allowed = {
            "draft": {"draft", "requested", "cancelled"},
            "requested": {"requested", "received", "cancelled"},
            "received": {"received"},
            "cancelled": {"cancelled"},
        }
        if body.status not in allowed[row["status"]]:
            raise HTTPException(422, "Invalid request status transition.")
        responses = row["responses"]
        if body.response.strip():
            responses = [
                *responses,
                {
                    "text": body.response.strip(),
                    "evidence_refs": [str(x) for x in body.evidence_refs],
                    "actor_id": str(a["user_id"]),
                    "actor_name": a["name"],
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                },
            ]
        if body.status == "received" and not responses:
            raise HTTPException(
                422, "Record the received response before marking received."
            )
        if row["status"] != "draft" and (
            row["title"] != body.title or row["items"] != body.items
        ):
            raise HTTPException(
                422,
                "Requested items are frozen; draft a new request for different items.",
            )
        updated = c.execute(
            "UPDATE information_requests SET title=%s,items=%s,owner_id=%s,due_at=%s,status=%s,responses=%s,version=version+1,updated_at=now() WHERE workspace_id=%s AND id=%s RETURNING *",
            (
                body.title,
                Jsonb(body.items),
                body.owner_id,
                body.due_at,
                body.status,
                Jsonb(responses),
                a["workspace_id"],
                request_id,
            ),
        ).fetchone()
        audit(
            c,
            a,
            cid,
            "information_request_updated",
            body.response or body.title,
            row["run_id"],
            {
                "request_id": str(request_id),
                "status": body.status,
                "responses": responses,
                "no_message_sent": True,
            },
        )
        return request_view(updated)


@router.get("/operations/history")
def snapshot_list(study_id: str = "", site_id: str = "", a=Depends(actor)):
    return query(
        "SELECT id,study_id,site_id,external_id,observed_at,created_at FROM snapshot_history WHERE workspace_id=%s AND (%s='' OR study_id=%s) AND (%s='' OR site_id=%s) ORDER BY observed_at DESC LIMIT 500",
        (a["workspace_id"], study_id, study_id, site_id, site_id),
    )


@router.post("/cases/{cid}/comparisons", status_code=201)
def comparison(cid: str, body: ComparisonCreate, a=Depends(actor)):
    with connect() as c:
        item = case(a, cid, c, True)
        snapshots = [
            c.execute(
                "SELECT * FROM snapshot_history WHERE workspace_id=%s AND id=%s",
                (a["workspace_id"], rid),
            ).fetchone()
            for rid in (body.before_id, body.after_id)
        ]
        if any(s is None for s in snapshots):
            raise HTTPException(404, "Snapshot not found in this workspace.")
        if any(
            (s["study_id"], s["site_id"]) != (item["study_id"], item["site_id"])
            for s in snapshots
        ):
            raise HTTPException(422, "Snapshots must match this case study and site.")
        result = compare_snapshots(*snapshots)
        old = c.execute(
            "SELECT * FROM snapshot_comparisons WHERE workspace_id=%s AND case_id=%s AND before_id=%s AND after_id=%s",
            (a["workspace_id"], cid, body.before_id, body.after_id),
        ).fetchone()
        if old:
            return old
        row = c.execute(
            "INSERT INTO snapshot_comparisons(workspace_id,id,case_id,before_id,after_id,comparison,actor_id) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                a["workspace_id"],
                uuid4(),
                cid,
                body.before_id,
                body.after_id,
                Jsonb(result),
                a["user_id"],
            ),
        ).fetchone()
        audit(
            c,
            a,
            cid,
            "snapshots_compared",
            payload={
                "comparison_id": str(row["id"]),
                "before_id": str(body.before_id),
                "after_id": str(body.after_id),
                "absence_is_resolution": False,
            },
        )
        return row


@router.get("/cases/{cid}/related")
def related(cid: str, a=Depends(actor)):
    item = case(a, cid)
    needle = terms(item["title"] + " " + item["description"])
    matches = []
    for other in query(
        "SELECT id,title,description,category,study_id,site_id,status,resolution,resolved_at FROM cases WHERE workspace_id=%s AND id<>%s ORDER BY updated_at DESC LIMIT 500",
        (a["workspace_id"], cid),
    ):
        overlap = sorted(needle & terms(other["title"] + " " + other["description"]))
        if len(overlap) < 2:
            continue
        differences = [
            k.replace("_", " ")
            + ": "
            + str(other[k])
            + " (this case: "
            + str(item[k])
            + ")"
            for k in ("study_id", "site_id", "category", "status")
            if other[k] != item[k]
        ]
        matches.append(
            {
                **other,
                "matched_terms": overlap,
                "reason": "Shared operational terms: " + ", ".join(overlap[:10]),
                "differences": differences,
                "root_cause_confirmed": False,
            }
        )
    matches.sort(key=lambda r: (-len(r["matched_terms"]), r["id"]))
    links = query(
        "SELECT * FROM case_links WHERE workspace_id=%s AND (case_id=%s OR related_id=%s)",
        (a["workspace_id"], cid, cid),
    )
    return {
        "suggestions": matches[:10],
        "links": links,
        "interpretation": "Similarity suggests review; it does not establish a shared root cause.",
    }


@router.post("/cases/{cid}/related", status_code=201)
def link_case(cid: str, body: RelatedLink, a=Depends(actor)):
    if cid == body.related_id:
        raise HTTPException(422, "Choose another case.")
    with connect() as c:
        left, right = sorted([cid, body.related_id])
        case(a, left, c, True)
        case(a, right, c, True)
        row = c.execute(
            "INSERT INTO case_links(workspace_id,case_id,related_id,actor_id,rationale) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING *",
            (a["workspace_id"], left, right, a["user_id"], body.rationale),
        ).fetchone()
        if not row:
            raise HTTPException(409, "These cases are already linked.")
        audit(
            c,
            a,
            cid,
            "related_case_linked",
            body.rationale,
            payload={
                "related_case": body.related_id,
                "shared_root_cause_established": False,
            },
        )
        return row


@router.post("/cases/{cid}/effort", status_code=201)
def effort(cid: str, body: EffortCreate, a=Depends(actor)):
    with connect() as c:
        case(a, cid, c, True)
        if body.run_id and run(a, body.run_id, c)["case_id"] != cid:
            raise HTTPException(422, "Effort run must belong to this case.")
        old = c.execute(
            "SELECT * FROM human_effort WHERE workspace_id=%s AND id=%s",
            (a["workspace_id"], body.id),
        ).fetchone()
        if old:
            if (
                old["case_id"] != cid
                or float(old["minutes"]) != body.minutes
                or old["notes"] != body.notes
                or old["activity"] != body.activity
                or old["run_id"] != body.run_id
            ):
                raise HTTPException(409, "Effort ID already contains another entry.")
            return old
        row = c.execute(
            "INSERT INTO human_effort(workspace_id,id,case_id,run_id,minutes,activity,notes,actor_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                a["workspace_id"],
                body.id,
                cid,
                body.run_id,
                body.minutes,
                body.activity,
                body.notes,
                a["user_id"],
            ),
        ).fetchone()
        audit(
            c,
            a,
            cid,
            "human_effort_recorded",
            body.notes,
            body.run_id,
            {
                "minutes": body.minutes,
                "activity": body.activity,
                "effort_id": str(body.id),
            },
        )
        return row


@router.get("/metrics")
def metrics(a=Depends(actor)):
    w = a["workspace_id"]
    jobs = query(
        "SELECT id,target_id,status,attempts,created_at,started_at,finished_at FROM jobs WHERE workspace_id=%s AND kind='investigate' ORDER BY created_at",
        (w,),
    )
    runs = query(
        "SELECT id,case_id,created_at,reviewed_at,duration_seconds,decision FROM runs WHERE workspace_id=%s ORDER BY created_at",
        (w,),
    )
    cases = query(
        "SELECT id,created_at,status FROM cases WHERE workspace_id=%s ORDER BY created_at",
        (w,),
    )
    events = query(
        "SELECT case_id,event_type,created_at FROM case_events WHERE workspace_id=%s AND event_type IN ('case_resolved','case_reopened') ORDER BY id",
        (w,),
    )
    cycles = []
    for item in cases:
        started = item["created_at"]
        cycle = 1
        for e in [e for e in events if e["case_id"] == item["id"]]:
            if e["event_type"] == "case_resolved":
                cycles.append(
                    {
                        "case_id": item["id"],
                        "cycle": cycle,
                        "opened_at": started,
                        "resolved_at": e["created_at"],
                        "elapsed_seconds": (e["created_at"] - started).total_seconds(),
                    }
                )
            else:
                started = e["created_at"]
                cycle += 1
        if item["status"] == "open":
            cycles.append(
                {
                    "case_id": item["id"],
                    "cycle": cycle,
                    "opened_at": started,
                    "resolved_at": None,
                    "elapsed_seconds": (
                        datetime.now(timezone.utc) - started
                    ).total_seconds(),
                }
            )
    return {
        "jobs": [
            {
                **j,
                "queue_seconds": (j["started_at"] - j["created_at"]).total_seconds()
                if j["started_at"]
                else None,
                "worker_elapsed_seconds": (
                    j["finished_at"] - j["started_at"]
                ).total_seconds()
                if j["started_at"] and j["finished_at"]
                else None,
            }
            for j in jobs
        ],
        "runs": [
            {
                **r,
                "review_turnaround_seconds": (
                    r["reviewed_at"] - r["created_at"]
                ).total_seconds()
                if r["reviewed_at"]
                else None,
            }
            for r in runs
        ],
        "resolution_cycles": cycles,
        "human_effort": query(
            "SELECT * FROM human_effort WHERE workspace_id=%s ORDER BY recorded_at",
            (w,),
        ),
        "definitions": {
            "queue": "Job creation to current attempt start; failed/interrupted attempts remain distinct jobs.",
            "execution": "Measured successful investigation execution, including evidence tools/model; repeated runs are separate.",
            "review": "Saved investigation creation to recorded recommendation decision. Pending review has no measured turnaround.",
            "resolution": "Case creation or reopening to next resolution event; open cycle age is elapsed time, not labor.",
            "human_effort": "Only explicitly entered minutes; no elapsed duration is labor savings.",
            "roi": "Assumed ROI remains in ROI scenarios and is not merged into measured activity.",
        },
    }


@router.get("/policies")
def policies(a=Depends(actor)):
    return one(
        "SELECT * FROM workspace_policies WHERE workspace_id=%s", (a["workspace_id"],)
    ) or {
        "version": 1,
        "freshness_hours": None,
        "reminder_lead_hours": 24,
        "reminder_frequency_minutes": 60,
        "visit_checklist": [],
    }


@router.post("/policies")
def save_policy(body: PolicyEdit, a=Depends(actor)):
    require(a, ("owner",))
    with connect() as c:
        c.execute(
            "SELECT id FROM workspaces WHERE id=%s FOR UPDATE", (a["workspace_id"],)
        )
        old = c.execute(
            "SELECT * FROM workspace_policies WHERE workspace_id=%s",
            (a["workspace_id"],),
        ).fetchone()
        version = old["version"] if old else 1
        if body.expected_version != version:
            raise HTTPException(409, "Workspace policy changed. Reload before saving.")
        return c.execute(
            "INSERT INTO workspace_policies(workspace_id,freshness_hours,reminder_lead_hours,reminder_frequency_minutes,visit_checklist,version) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(workspace_id) DO UPDATE SET freshness_hours=EXCLUDED.freshness_hours,reminder_lead_hours=EXCLUDED.reminder_lead_hours,reminder_frequency_minutes=EXCLUDED.reminder_frequency_minutes,visit_checklist=EXCLUDED.visit_checklist,version=EXCLUDED.version,updated_at=now() RETURNING *",
            (
                a["workspace_id"],
                body.freshness_hours,
                body.reminder_lead_hours,
                body.reminder_frequency_minutes,
                Jsonb(body.visit_checklist),
                version + 1,
            ),
        ).fetchone()


@router.get("/knowledge/impact")
def impact(a=Depends(actor)):
    rows = query(
        "SELECT r.*,c.title AS case_title,k.title AS procedure_title FROM procedure_reassessments r JOIN cases c ON (c.workspace_id,c.id)=(r.workspace_id,r.case_id) JOIN knowledge k ON (k.workspace_id,k.id)=(r.workspace_id,r.article_id) WHERE r.workspace_id=%s ORDER BY r.created_at DESC LIMIT 500",
        (a["workspace_id"],),
    )
    for row in rows:
        old = one(
            "SELECT content FROM procedure_versions WHERE workspace_id=%s AND article_id=%s AND version=%s",
            (a["workspace_id"], row["article_id"], row["old_version"]),
        )
        new = one(
            "SELECT content FROM procedure_versions WHERE workspace_id=%s AND article_id=%s AND version=%s",
            (a["workspace_id"], row["article_id"], row["new_version"]),
        )
        if not old:
            r = run(a, row["run_id"])
            old = {
                "content": "\n\n".join(
                    s["content"]
                    for s in r["result"].get("sources", [])
                    if s.get("article_id") == row["article_id"]
                    and s["id"] in r["result"]["recommendation"]["evidence_ids"]
                )
            }
            row["old_content_scope"] = (
                "Frozen cited sections; complete earlier version was not retained before this release."
            )
        else:
            row["old_content_scope"] = "Complete retained procedure version."
        row["diff"] = "\n".join(
            difflib.unified_diff(
                old["content"].splitlines(),
                (new or {"content": ""})["content"].splitlines(),
                fromfile="v" + str(row["old_version"]),
                tofile="v" + str(row["new_version"]),
                lineterm="",
            )
        )
    return rows


@router.post("/runs/{rid}/reassessment/{article}/{version}")
def reassess(
    rid: UUID, article: str, version: int, body: ReassessmentEdit, a=Depends(actor)
):
    require(a)
    with connect() as c:
        r = run(a, rid, c)
        case(a, r["case_id"], c, True)
        old = c.execute(
            "SELECT * FROM procedure_reassessments WHERE workspace_id=%s AND run_id=%s AND article_id=%s AND new_version=%s FOR UPDATE",
            (a["workspace_id"], rid, article, version),
        ).fetchone()
        if not old:
            raise HTTPException(404, "Reassessment not found.")
        if old["version"] != body.expected_version:
            raise HTTPException(409, "Reassessment changed. Reload before saving.")
        row = c.execute(
            "UPDATE procedure_reassessments SET status=%s,rationale=%s,reviewer_id=%s,reviewed_at=now(),version=version+1 WHERE workspace_id=%s AND run_id=%s AND article_id=%s AND new_version=%s RETURNING *",
            (
                body.status,
                body.rationale,
                a["user_id"],
                a["workspace_id"],
                rid,
                article,
                version,
            ),
        ).fetchone()
        audit(
            c,
            a,
            r["case_id"],
            "procedure_reassessed",
            body.rationale,
            rid,
            {"article_id": article, "new_version": version, "status": body.status},
        )
        return row


@router.post("/operations/import-preview", status_code=201)
def import_preview(body: ImportPreview, a=Depends(actor)):
    require(a, ("owner",))
    rate("import-preview:" + str(a["workspace_id"]), 30)
    sites = {
        (s["study_id"], s["id"])
        for s in query(
            "SELECT study_id,id FROM sites WHERE workspace_id=%s", (a["workspace_id"],)
        )
    }
    accepted, rejected, groups = preview_rows(
        body.content, body.format, body.mapping, sites
    )
    rid = uuid4()
    with connect() as c:
        # Reveal immutable-ID conflicts before the user approves the preview.
        valid = []
        for group in groups:
            sid = group["evidence"]["synchronization"]["snapshot"]["id"]
            old = c.execute(
                "SELECT content_hash FROM snapshot_history WHERE workspace_id=%s AND study_id=%s AND site_id=%s AND external_id=%s",
                (a["workspace_id"], group["study_id"], group["site_id"], sid),
            ).fetchone()
            if old and old["content_hash"] != canonical(group["evidence"]):
                accepted = [r for r in accepted if r["row"] not in group["rows"]]
                rejected.extend(
                    {
                        "row": i,
                        "reason": "Existing snapshot ID contains different immutable evidence.",
                    }
                    for i in group["rows"]
                )
            else:
                valid.append(group)
        c.execute(
            "INSERT INTO import_previews(workspace_id,id,actor_id,format,content_hash,accepted,rejected) VALUES(%s,%s,%s,%s,%s,%s,%s)",
            (
                a["workspace_id"],
                rid,
                a["user_id"],
                body.format,
                canonical({"content": body.content, "mapping": body.mapping}),
                Jsonb(valid),
                Jsonb(rejected),
            ),
        )
    return {
        "id": rid,
        "accepted": accepted,
        "rejected": rejected,
        "snapshots": len(valid),
        "message": "Preview only. No operational records were changed.",
    }


@router.post("/operations/import-preview/{rid}/commit")
def commit_import(rid: UUID, body: ImportCommit, a=Depends(actor)):
    require(a, ("owner",))
    with connect() as c:
        c.execute(
            "SELECT id FROM workspaces WHERE id=%s FOR UPDATE", (a["workspace_id"],)
        )
        row = c.execute(
            "SELECT * FROM import_previews WHERE workspace_id=%s AND id=%s AND actor_id=%s FOR UPDATE",
            (a["workspace_id"], rid, a["user_id"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Import preview not found for this account.")
        if row["committed_at"]:
            return {"status": "already_committed", "snapshots": len(row["accepted"])}
        if row["expires_at"] < datetime.now(timezone.utc):
            raise HTTPException(409, "Preview expired. Validate the input again.")
        if not row["accepted"]:
            raise HTTPException(422, "There are no accepted snapshots to import.")
        for group in row["accepted"]:
            if not c.execute(
                "SELECT 1 FROM sites WHERE workspace_id=%s AND id=%s AND study_id=%s",
                (a["workspace_id"], group["site_id"], group["study_id"]),
            ).fetchone():
                raise HTTPException(
                    409, "Study/site relationship changed. Preview again."
                )
            save_snapshot(
                c,
                a["workspace_id"],
                group["study_id"],
                group["site_id"],
                group["evidence"],
                a["user_id"],
            )
        c.execute(
            "UPDATE import_previews SET committed_at=now() WHERE workspace_id=%s AND id=%s",
            (a["workspace_id"], rid),
        )
        return {
            "status": "committed",
            "snapshots": len(row["accepted"]),
            "rejected_rows": len(row["rejected"]),
        }


@router.get("/visits")
def visits(a=Depends(actor)):
    return query(
        "SELECT * FROM monitoring_visits WHERE workspace_id=%s ORDER BY visit_at DESC LIMIT 100",
        (a["workspace_id"],),
    )


@router.post("/visits", status_code=201)
def create_visit(body: VisitCreate, a=Depends(actor)):
    require(a)
    with connect() as c:
        c.execute(
            "SELECT id FROM workspaces WHERE id=%s FOR UPDATE", (a["workspace_id"],)
        )
        if not c.execute(
            "SELECT 1 FROM sites WHERE workspace_id=%s AND study_id=%s AND id=%s",
            (a["workspace_id"], body.study_id, body.site_id),
        ).fetchone():
            raise HTTPException(422, "Choose a study/site from this workspace.")
        old = c.execute(
            "SELECT * FROM monitoring_visits WHERE workspace_id=%s AND id=%s",
            (a["workspace_id"], body.id),
        ).fetchone()
        if old:
            if (old["study_id"], old["site_id"], old["title"], old["visit_at"]) != (
                body.study_id,
                body.site_id,
                body.title,
                body.visit_at,
            ):
                raise HTTPException(409, "Visit ID already contains a different visit.")
            return old
        policy = c.execute(
            "SELECT visit_checklist FROM workspace_policies WHERE workspace_id=%s",
            (a["workspace_id"],),
        ).fetchone()
        items = (
            [
                {"id": str(uuid4()), "text": text, "state": "not_checked", "notes": ""}
                for text in policy["visit_checklist"]
            ]
            if policy
            else []
        )
        return c.execute(
            "INSERT INTO monitoring_visits(workspace_id,id,study_id,site_id,visit_at,title,checklist,actor_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                a["workspace_id"],
                body.id,
                body.study_id,
                body.site_id,
                body.visit_at,
                body.title,
                Jsonb(items),
                a["user_id"],
            ),
        ).fetchone()


def visit_data(a, rid):
    item = one(
        "SELECT * FROM monitoring_visits WHERE workspace_id=%s AND id=%s",
        (a["workspace_id"], rid),
    )
    if not item:
        raise HTTPException(404, "Visit not found in this workspace.")
    cases = query(
        "SELECT c.*,u.name AS owner_name FROM cases c LEFT JOIN users u ON u.id=c.owner_id WHERE c.workspace_id=%s AND c.study_id=%s AND c.site_id=%s AND c.status='open' ORDER BY c.priority,c.due_at NULLS LAST",
        (a["workspace_id"], item["study_id"], item["site_id"]),
    )
    cids = [c["id"] for c in cases]
    return {
        "visit": item,
        "open_cases": cases,
        "checks": query(
            "SELECT * FROM investigation_checks WHERE workspace_id=%s AND case_id=ANY(%s) AND status='active'",
            (a["workspace_id"], cids),
        ),
        "requests": [
            request_view(r)
            for r in query(
                "SELECT r.*,u.name AS owner_name FROM information_requests r LEFT JOIN users u ON u.id=r.owner_id WHERE r.workspace_id=%s AND r.case_id=ANY(%s) AND r.status IN ('draft','requested')",
                (a["workspace_id"], cids),
            )
        ],
        "interpretation": "Preparation inventory; no validated compliance or readiness score is calculated.",
    }


@router.get("/visits/{rid}")
def visit_detail(rid: UUID, a=Depends(actor)):
    return visit_data(a, rid)


@router.post("/visits/{rid}")
def edit_visit(rid: UUID, body: VisitEdit, a=Depends(actor)):
    require(a)
    with connect() as c:
        row = row_version(c, a, "monitoring_visits", rid, body.expected_version)
        items = body.model_dump(mode="json")["checklist"]
        if len({i["id"] for i in items}) != len(items):
            raise HTTPException(422, "Checklist identifiers must be unique.")
        previous = {i["id"]: i for i in row["checklist"]}
        for i in items:
            if (
                i["state"] in {"not_applicable", "needs_follow_up"}
                and len(i["notes"].strip()) < 5
            ):
                raise HTTPException(422, "Explain exceptions and follow-up items.")
            old = previous.get(i["id"])
            if not old or any(
                old.get(k) != i.get(k) for k in ("text", "state", "notes")
            ):
                i["actor_id"] = str(a["user_id"])
                i["actor_name"] = a["name"]
                i["recorded_at"] = datetime.now(timezone.utc).isoformat()
            else:
                for k in ("actor_id", "actor_name", "recorded_at"):
                    i[k] = old.get(k)
        return c.execute(
            "UPDATE monitoring_visits SET checklist=%s,visit_at=%s,version=version+1,updated_at=now() WHERE workspace_id=%s AND id=%s RETURNING *",
            (Jsonb(items), body.visit_at, a["workspace_id"], rid),
        ).fetchone()


@router.get("/visits/{rid}/export.txt")
def visit_export(rid: UUID, a=Depends(actor)):
    d = visit_data(a, rid)
    v = d["visit"]
    lines = [
        v["title"],
        f"Study/site: {v['study_id']} / {v['site_id']}",
        f"Visit: {v['visit_at']}",
        d["interpretation"],
        "",
        "Open issues:",
    ]
    lines += [
        f"- {c['title']} | {c['owner_name'] or 'Unassigned'} | due {c['due_at'] or 'Not set'}"
        for c in d["open_cases"]
    ]
    lines += ["", "Incomplete checks:"] + [
        f"- {i['text']} | {i['state']} | due {ch['due_at'] or 'Not set'}"
        for ch in d["checks"]
        for i in ch["items"]
        if i["state"] not in {"verified", "not_applicable"}
    ]
    lines += ["", "Missing information:"] + [
        f"- {r['title']} | {r['effective_status']} | {r['owner_name'] or 'Unassigned'} | due {r['due_at'] or 'Not set'}"
        for r in d["requests"]
    ]
    lines += ["", "Visit checklist:"] + [
        f"- {i['text']} | {i['state']} | {i['notes']}" for i in v["checklist"]
    ]
    return Response(
        "\n".join(lines),
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="trialops-visit-{rid}.txt"'
        },
    )


@router.get("/notifications")
def notifications(a=Depends(actor)):
    return query(
        "SELECT * FROM notifications WHERE workspace_id=%s AND user_id=%s ORDER BY created_at DESC LIMIT 100",
        (a["workspace_id"], a["user_id"]),
    )


@router.post("/notifications/{rid}/read")
def read_notification(rid: UUID, a=Depends(actor)):
    rows = query(
        "UPDATE notifications SET read_at=coalesce(read_at,now()) WHERE workspace_id=%s AND user_id=%s AND id=%s RETURNING *",
        (a["workspace_id"], a["user_id"], rid),
    )
    if not rows:
        raise HTTPException(404, "Notification not found.")
    return rows[0]


@router.get("/notification-preferences")
def notification_prefs(a=Depends(actor)):
    return one(
        "SELECT enabled,kinds FROM notification_preferences WHERE workspace_id=%s AND user_id=%s",
        (a["workspace_id"], a["user_id"]),
    ) or {"enabled": True, "kinds": ["request", "check", "reassessment", "deadline"]}


@router.post("/notification-preferences")
def save_notification_prefs(body: NotificationPrefs, a=Depends(actor)):
    return query(
        "INSERT INTO notification_preferences(workspace_id,user_id,enabled,kinds) VALUES(%s,%s,%s,%s) ON CONFLICT(workspace_id,user_id) DO UPDATE SET enabled=EXCLUDED.enabled,kinds=EXCLUDED.kinds RETURNING enabled,kinds",
        (a["workspace_id"], a["user_id"], body.enabled, Jsonb(sorted(set(body.kinds)))),
    )[0]


@router.get("/evaluations")
def evaluations(a=Depends(actor)):
    require(a)
    from evaluation import dataset

    return {
        "dataset": dataset(),
        "runs": query(
            "SELECT e.*,j.status,j.error,j.attempts FROM evaluation_runs e LEFT JOIN LATERAL (SELECT * FROM jobs WHERE workspace_id=e.workspace_id AND target_id=e.id::text AND kind='evaluate' ORDER BY created_at DESC,id DESC LIMIT 1) j ON true WHERE e.workspace_id=%s ORDER BY e.created_at DESC LIMIT 50",
            (a["workspace_id"],),
        ),
    }


@router.post("/evaluations", status_code=202)
def enqueue_evaluation(body: EvaluationCreate, a=Depends(actor)):
    require(a)
    rate("evaluation:" + str(a["workspace_id"]), 5)
    from evaluation import dataset, configuration

    with connect() as c:
        c.execute(
            "SELECT id FROM workspaces WHERE id=%s FOR UPDATE", (a["workspace_id"],)
        )
        old = c.execute(
            "SELECT * FROM evaluation_runs WHERE workspace_id=%s AND id=%s",
            (a["workspace_id"], body.id),
        ).fetchone()
        if old:
            return old
        if c.execute(
            "SELECT 1 FROM jobs WHERE workspace_id=%s AND kind='evaluate' AND status IN ('queued','running')",
            (a["workspace_id"],),
        ).fetchone():
            raise HTTPException(409, "Wait for this workspace evaluation to finish.")
        config = configuration(body.mode)
        data = dataset()
        c.execute(
            "INSERT INTO evaluation_runs(workspace_id,id,dataset_version,model,configuration,actor_id) VALUES(%s,%s,%s,%s,%s,%s)",
            (
                a["workspace_id"],
                body.id,
                data["version"],
                config["model"],
                Jsonb(config),
                a["user_id"],
            ),
        )
        return c.execute(
            "INSERT INTO jobs(id,workspace_id,actor_id,kind,target_id) VALUES(%s,%s,%s,'evaluate',%s) RETURNING *",
            (uuid4(), a["workspace_id"], a["user_id"], str(body.id)),
        ).fetchone()


@router.post("/evaluations/{rid}/judgment")
def judge_evaluation(rid: UUID, body: Note, a=Depends(actor)):
    require(a)
    rows = query(
        "UPDATE evaluation_runs SET judgment=%s,judgment_by=%s,judged_at=now() WHERE workspace_id=%s AND id=%s AND results IS NOT NULL RETURNING *",
        (body.notes, a["user_id"], a["workspace_id"], rid),
    )
    if not rows:
        raise HTTPException(404, "Completed evaluation not found.")
    return rows[0]


@router.get("/walkthrough")
def walkthrough(a=Depends(actor)):
    if not a["demo"]:
        raise HTTPException(
            403, "The walkthrough only operates on an isolated sample workspace."
        )
    return one(
        "SELECT step,skipped FROM walkthrough_progress WHERE workspace_id=%s AND user_id=%s",
        (a["workspace_id"], a["user_id"]),
    ) or {"step": 0, "skipped": False}


@router.post("/walkthrough")
def save_walkthrough(body: WalkthroughUpdate, a=Depends(actor)):
    if not a["demo"]:
        raise HTTPException(
            403, "The walkthrough only operates on an isolated sample workspace."
        )
    return query(
        "INSERT INTO walkthrough_progress(workspace_id,user_id,step,skipped) VALUES(%s,%s,%s,%s) ON CONFLICT(workspace_id,user_id) DO UPDATE SET step=EXCLUDED.step,skipped=EXCLUDED.skipped,updated_at=now() RETURNING step,skipped",
        (a["workspace_id"], a["user_id"], body.step, body.skipped),
    )[0]


@router.post("/evaluations/{rid}/retry", status_code=202)
def retry_evaluation(rid: UUID, a=Depends(actor)):
    require(a)
    with connect() as c:
        c.execute(
            "SELECT id FROM workspaces WHERE id=%s FOR UPDATE", (a["workspace_id"],)
        )
        item = c.execute(
            "SELECT * FROM evaluation_runs WHERE workspace_id=%s AND id=%s",
            (a["workspace_id"], rid),
        ).fetchone()
        if not item:
            raise HTTPException(404, "Evaluation not found.")
        if item["results"] is not None:
            raise HTTPException(409, "Evaluation is complete. Create a new run.")
        if c.execute(
            "SELECT 1 FROM jobs WHERE workspace_id=%s AND kind='evaluate' AND status IN ('queued','running')",
            (a["workspace_id"],),
        ).fetchone():
            raise HTTPException(409, "Evaluation is already queued or running.")
        return c.execute(
            "INSERT INTO jobs(id,workspace_id,actor_id,kind,target_id) VALUES(%s,%s,%s,'evaluate',%s) RETURNING *",
            (uuid4(), a["workspace_id"], a["user_id"], str(rid)),
        ).fetchone()


def case_package(a, cid):
    with connect() as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        item = case(a, cid, c)
        w = a["workspace_id"]
        tables = {
            "runs": "runs",
            "events": "case_events",
            "checks": "investigation_checks",
            "requests": "information_requests",
            "evidence": "case_evidence",
            "comparisons": "snapshot_comparisons",
            "reassessments": "procedure_reassessments",
            "effort": "human_effort",
        }
        package = {
            key: c.execute(
                "SELECT * FROM " + table + " WHERE workspace_id=%s AND case_id=%s",
                (w, cid),
            ).fetchall()
            for key, table in tables.items()
        }
        package["case"] = item
        package["events"].sort(key=lambda e: e["id"])
        package["runs"].sort(key=lambda r: r["created_at"])
        package["links"] = c.execute(
            "SELECT * FROM case_links WHERE workspace_id=%s AND (case_id=%s OR related_id=%s)",
            (w, cid, cid),
        ).fetchall()
        package["snapshots"] = c.execute(
            "SELECT * FROM snapshot_history WHERE workspace_id=%s AND study_id=%s AND site_id=%s ORDER BY observed_at",
            (w, item["study_id"], item["site_id"]),
        ).fetchall()
        aids = {
            s.get("article_id")
            for r in package["runs"]
            for s in r["result"].get("sources", [])
            if s["id"] in r["result"]["recommendation"]["evidence_ids"]
        }
        package["procedure_versions"] = c.execute(
            "SELECT * FROM procedure_versions WHERE workspace_id=%s AND article_id=ANY(%s) ORDER BY article_id,version",
            (w, list(aids)),
        ).fetchall()
        policy = c.execute(
            "SELECT * FROM workspace_policies WHERE workspace_id=%s", (w,)
        ).fetchone()
        current = c.execute(
            "SELECT evidence FROM operations WHERE workspace_id=%s AND study_id=%s AND site_id=%s",
            (w, item["study_id"], item["site_id"]),
        ).fetchone()
        package["flags"] = evidence_flags(
            item,
            current["evidence"] if current else {},
            policy["freshness_hours"] if policy else None,
        )
        missing = []
        if not package["runs"]:
            missing.append("No saved investigation.")
        if not package["snapshots"]:
            missing.append("No historical operational snapshot for this study/site.")
        if not any(e["kind"] == "human_observation" for e in package["evidence"]):
            missing.append("No human verification observation recorded.")
        for check in package["checks"]:
            if check["status"] == "draft":
                missing.append("Investigation checklist awaits human activation.")
            for i in check["items"]:
                if i["state"] in {"not_checked", "needs_follow_up"}:
                    missing.append("Incomplete check: " + i["text"])
                if i["state"] == "not_applicable":
                    missing.append("Check exception: " + i["notes"])
        missing += [
            "Information request " + r["status"] + ": " + r["title"]
            for r in package["requests"]
            if r["status"] in {"draft", "requested"}
        ]
        missing += [
            "Procedure reassessment " + r["status"] + ": " + r["article_id"]
            for r in package["reassessments"]
            if r["status"] in {"pending", "needed"}
        ]
        package.update(
            version="2.0.0",
            exported_at=datetime.now(timezone.utc),
            missing_evidence=missing,
            interpretation="Case evidence and frozen decisions. Site snapshots are context; absent records do not establish resolution. Historical evidence is not current verification. Approval does not close cases. Request text and drafts are unsent. Elapsed durations are not labor savings.",
        )
        return package


@router.get("/cases/{cid}/package.json")
def package_json(cid: str, a=Depends(actor)):
    return case_package(a, cid)


@router.get("/cases/{cid}/package.pdf")
def package_pdf(cid: str, a=Depends(actor)):
    from report import build_case_report

    data = case_package(a, cid)
    # Filename uses only the generated/validated case ID, never a title.
    import re

    name = re.sub("[^A-Za-z0-9_-]", "_", cid)
    return Response(
        build_case_report(data),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="trialops-case-{name}.pdf"'
        },
    )


@router.get("/operations/import-example")
def import_example(format: str = "json", a=Depends(actor)):
    import csv, io
    from seed import operations

    evidence = operations()
    rows = []
    snapshot_id = "IMPORT-EXAMPLE-" + str(uuid4())[:12]
    observed_at = datetime.now(timezone.utc).isoformat()
    for group in evidence.values():
        group["snapshot"].update(id=snapshot_id, observed_at=observed_at)
        for record in group["records"]:
            record["snapshot_id"] = snapshot_id
    for kind, group in evidence.items():
        for record in group["records"]:
            rows.append(
                {
                    **record,
                    "study_id": group["snapshot"]["study_id"],
                    "site_id": group["snapshot"]["site_id"],
                    "observed_at": group["snapshot"]["observed_at"],
                    "synthetic": True,
                    "kind": kind,
                }
            )
    if format == "csv":
        output = io.StringIO()
        fields = list(dict.fromkeys(k for r in rows for k in r))
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        content = output.getvalue()
    elif format == "json":
        content = json.dumps(rows, indent=2)
    else:
        raise HTTPException(422, "Use csv or json.")
    return {"format": format, "content": content}


@router.post("/walkthrough/updated-records")
def walkthrough_records(a=Depends(actor)):
    if not a["demo"]:
        raise HTTPException(
            403, "Walkthrough changes only apply to isolated sample workspaces."
        )
    from seed import operations

    with connect() as c:
        c.execute(
            "SELECT id FROM workspaces WHERE id=%s FOR UPDATE", (a["workspace_id"],)
        )
        old = c.execute(
            "SELECT * FROM snapshot_history WHERE workspace_id=%s AND external_id='WALKTHROUGH-UPDATED-104'",
            (a["workspace_id"],),
        ).fetchone()
        if old:
            return {"snapshot_id": old["id"], "status": "already_saved"}
        evidence = operations()
        now = datetime.now(timezone.utc).isoformat()
        for group in evidence.values():
            group["snapshot"].update(id="WALKTHROUGH-UPDATED-104", observed_at=now)
            for record in group["records"]:
                record["snapshot_id"] = "WALKTHROUGH-UPDATED-104"
        sync = evidence["synchronization"]["records"][0]
        sync.update(
            status="completed",
            source_updated_at=now,
            destination_updated_at=now,
            last_attempt_at=now,
            error_code=None,
        )
        evidence["document_processing"]["records"][0].update(
            processing_status="processed", binder_visible=True, status_since=now
        )
        row, _ = save_snapshot(
            c, a["workspace_id"], "CT-204", "SITE-104", evidence, a["user_id"]
        )
        return {
            "snapshot_id": row["id"],
            "status": "saved",
            "case_status_changed": False,
        }
