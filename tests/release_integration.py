"""Complete synthetic workflow; run only on the isolated release test stack."""

import copy, json, time, sys, concurrent.futures, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from integration import Client, URL
from db import connect, secret
from reminders import scan_reminders

now = lambda: datetime.now(timezone.utc).isoformat()
a, b = Client(), Client()
workspaces = []
users = []
groups = 0


def passed(label):
    global groups
    groups += 1
    print("PASS:", label, flush=True)


def edit_request(r, status="requested", **extra):
    return {
        "expected_version": r["version"],
        "title": r["title"],
        "items": r["items"],
        "owner_id": r["owner_id"],
        "due_at": r["due_at"],
        "status": status,
        **extra,
    }


try:
    for c in (a, b):
        w = c.call("/auth/demo", {})["workspace_id"]
        workspaces.append(w)
        users.append(c.call("/auth/me")["user_id"])
    rid = a.run("CASE-4")["id"]
    old_run = copy.deepcopy(a.call("/runs/" + rid)["run"])
    a.call(
        "/runs/" + rid + "/decision",
        {
            "decision": "approved",
            "notes": "Reviewer checked the exact cited procedures and historical context.",
        },
    )
    assert a.call("/cases/CASE-4")["case"]["status"] == "open"
    checks = a.call("/runs/" + rid + "/checks", {}, 201)
    assert a.call("/runs/" + rid + "/checks", {}, 201)["id"] == checks["id"]
    assert all(i["suggestion"] and i["state"] == "not_checked" for i in checks["items"])
    b.call(
        "/cases/CASE-4/checks/" + checks["id"] + "/activate",
        {"expected_version": checks["version"]},
        404,
    )
    checks = a.call(
        "/cases/CASE-4/checks/" + checks["id"] + "/activate",
        {"expected_version": checks["version"]},
    )
    a.call(
        "/cases/CASE-4/checks/" + checks["id"] + "/activate",
        {"expected_version": 1},
        409,
    )
    passed(
        "frozen citations, human-only activation, repeat creation and wrong-workspace boundaries"
    )
    request = a.call(
        "/cases/CASE-4/requests",
        {
            "id": str(uuid4()),
            "run_id": rid,
            "title": "Current binder verification",
            "items": [
                "Current synchronization receipt",
                "Destination binder visibility",
            ],
            "owner_id": users[0],
            "due_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        },
        201,
    )
    assert request["status"] == "draft" and "does not send" in request["copy_text"]
    requested = a.call("/cases/CASE-4/requests/" + request["id"], edit_request(request))
    assert requested["effective_status"] == "overdue"
    a.call("/cases/CASE-4/requests/" + request["id"], edit_request(request), 409)
    a.call(
        "/cases/CASE-4/requests/" + request["id"],
        edit_request(requested, "received"),
        422,
    )
    with connect() as c:
        c.execute(
            "UPDATE reminder_scans SET last_scan_at=now()-interval '2 hours' WHERE workspace_id=%s",
            (workspaces[0],),
        )
    scan_reminders()
    notifications = a.call("/notifications")
    assert any(n["kind"] == "request" for n in notifications)
    with connect() as c:
        c.execute(
            "UPDATE reminder_scans SET last_scan_at=now()-interval '2 hours' WHERE workspace_id=%s",
            (workspaces[0],),
        )
    scan_reminders()
    assert len(a.call("/notifications")) == len(notifications)
    assert b.call("/notifications/" + notifications[0]["id"] + "/read", {}, 404)
    assert a.call("/notifications/" + notifications[0]["id"] + "/read", {})["read_at"]
    passed(
        "structured overdue requests, invalid transitions, concurrent versions and durable deduplicated private reminders"
    )
    history = a.call("/operations/history?study_id=CT-204&site_id=SITE-104")
    before = history[0]
    updated = a.call("/walkthrough/updated-records", {})
    assert a.call("/walkthrough/updated-records", {})["status"] == "already_saved"
    comparison = a.call(
        "/cases/CASE-4/comparisons",
        {"before_id": before["id"], "after_id": updated["snapshot_id"]},
        201,
    )
    assert any(r["state"] == "changed" for r in comparison["comparison"]["records"])
    a.call(
        "/cases/CASE-4/comparisons",
        {"before_id": updated["snapshot_id"], "after_id": before["id"]},
        422,
    )
    b.call(
        "/cases/CASE-4/comparisons",
        {"before_id": before["id"], "after_id": updated["snapshot_id"]},
        404,
    )
    assert a.call("/cases/CASE-4")["case"]["status"] == "open"
    assert a.call("/runs/" + rid)["run"]["result"] == old_run["result"]
    passed(
        "immutable scoped snapshot comparison and updated observations without mutating frozen runs or closing cases"
    )
    for fmt in ("json", "csv"):
        example = a.call("/operations/import-example?format=" + fmt)
        preview = a.call(
            "/operations/import-preview",
            {"format": fmt, "content": example["content"], "mapping": {}},
            201,
        )
        assert len(preview["accepted"]) == 2 and not preview["rejected"], preview
        b.call(
            "/operations/import-preview/" + preview["id"] + "/commit",
            {"confirmed": True},
            404,
        )
        a.call(
            "/operations/import-preview/" + preview["id"] + "/commit",
            {"confirmed": False},
            422,
        )
        assert (
            a.call(
                "/operations/import-preview/" + preview["id"] + "/commit",
                {"confirmed": True},
            )["status"]
            == "committed"
        )
        assert (
            a.call(
                "/operations/import-preview/" + preview["id"] + "/commit",
                {"confirmed": True},
            )["status"]
            == "already_committed"
        )
    example = a.call("/operations/import-example")
    rows = json.loads(example["content"])
    rows.append({**rows[0], "site_id": "WRONG"})
    preview = a.call(
        "/operations/import-preview",
        {"format": "json", "content": json.dumps(rows), "mapping": {}},
        201,
    )
    assert len(preview["accepted"]) == 2 and len(preview["rejected"]) == 1
    a.call(
        "/operations/import-preview/" + preview["id"] + "/commit", {"confirmed": True}
    )
    changed = copy.deepcopy(rows[:2])
    changed[0]["status"] = "running"
    conflict = a.call(
        "/operations/import-preview",
        {"format": "json", "content": json.dumps(changed), "mapping": {}},
        201,
    )
    assert not conflict["accepted"] and conflict["rejected"]
    passed(
        "CSV/JSON preview, rejected scope, immutable-ID conflicts, confirmed atomic commit and repeat idempotency"
    )
    related = a.call("/cases/CASE-4/related")
    assert all(not r["root_cause_confirmed"] for r in related["suggestions"])
    a.call(
        "/cases/CASE-4/related",
        {
            "related_id": "CASE-1",
            "rationale": "Reviewer checked the similar binder symptoms and differences.",
            "confirmed": False,
        },
        422,
    )
    a.call(
        "/cases/CASE-4/related",
        {
            "related_id": "CASE-1",
            "rationale": "Reviewer checked the similar binder symptoms and differences.",
            "confirmed": True,
        },
        201,
    )
    assert a.call("/cases/CASE-1")["case"]["status"] == "open"
    passed(
        "explained related-case suggestions and explicit links without linked-case closure"
    )
    evidence = a.call(
        "/cases/CASE-4/evidence",
        {
            "id": str(uuid4()),
            "kind": "human_observation",
            "summary": "Personally checked current synthetic binder visibility and successful synchronization receipt.",
            "observed_at": now(),
        },
        201,
    )
    request = a.call(
        "/cases/CASE-4/requests/" + requested["id"],
        edit_request(
            requested,
            "received",
            response="Current records received and manually reviewed.",
            evidence_refs=[evidence["id"]],
        ),
    )
    assert request["responses"][-1]["actor_name"] == "Sample visitor"
    body = {
        "run_id": rid,
        "notes": "Reviewer confirmed the current synthetic binder records and all checks.",
        "confirmed": True,
        "verified_at": now(),
        "evidence_refs": [evidence["id"]],
        "expected_updated_at": a.call("/cases/CASE-4")["case"]["updated_at"],
    }
    a.call("/cases/CASE-4/resolve", body, 422)
    for i in checks["items"]:
        i.update(
            state="verified",
            notes="Personally checked current synthetic records.",
            evidence_refs=[evidence["id"]],
        )
    checks = a.call(
        "/cases/CASE-4/checks/" + checks["id"],
        {"expected_version": checks["version"], "items": checks["items"]},
    )
    a.call(
        "/cases/CASE-4/resolve",
        {**body, "expected_updated_at": "2020-01-01T00:00:00Z"},
        409,
    )
    a.call("/cases/CASE-4/resolve", {**body, "verified_at": now()})
    a.call(
        "/cases/CASE-4/reopen",
        {"notes": "Reopened for a new current-record verification cycle."},
    )
    a.call(
        "/cases/CASE-4/resolve",
        {
            **body,
            "expected_updated_at": a.call("/cases/CASE-4")["case"]["updated_at"],
            "verified_at": now(),
        },
        422,
    )
    passed(
        "evidence-backed separate resolution, unchecked protection, stale writes, frozen audit and renewed verification after reopening"
    )
    effort = {
        "id": str(uuid4()),
        "run_id": rid,
        "minutes": 12.5,
        "activity": "review",
        "notes": "Actual human review time entered explicitly.",
    }
    a.call("/cases/CASE-4/effort", effort, 201)
    a.call("/cases/CASE-4/effort", effort, 201)
    metrics = a.call("/metrics")
    assert len([e for e in metrics["human_effort"] if e["id"] == effort["id"]]) == 1
    assert (
        len([c for c in metrics["resolution_cycles"] if c["case_id"] == "CASE-4"]) == 2
    )
    assert (
        metrics["jobs"]
        and metrics["runs"]
        and "labor" in metrics["definitions"]["human_effort"]
    )
    passed(
        "separate queue/execution/review/resolution-cycle measurements and idempotent explicit human effort"
    )
    knowledge = next(k for k in a.call("/knowledge") if k["id"] == "KB-004")
    frozen = a.call("/runs/" + rid)["run"]
    a.call(
        "/knowledge/KB-004",
        {
            "title": knowledge["title"],
            "category": knowledge["category"],
            "content": knowledge["content"]
            + " Require an additional human review of new records.",
            "expected_version": knowledge["version"],
        },
    )
    impact = a.call("/knowledge/impact")
    notice = next(
        i for i in impact if i["run_id"] == rid and i["article_id"] == "KB-004"
    )
    assert "additional human review" in notice["diff"]
    assert (
        a.call("/runs/" + rid)["run"]["result"] == frozen["result"]
        and a.call("/runs/" + rid)["run"]["decision"] == "approved"
    )
    reassess = "/runs/" + rid + "/reassessment/KB-004/" + str(notice["new_version"])
    a.call(
        reassess,
        {
            "expected_version": notice["version"],
            "status": "needed",
            "rationale": "New procedure requires review of the current record before further action.",
        },
    )
    a.call(
        reassess,
        {
            "expected_version": notice["version"],
            "status": "not_needed",
            "rationale": "Stale update must be rejected.",
        },
        409,
    )
    passed(
        "retained procedure versions, open-case impact/diff and explicit reassessment without rewriting historical approval"
    )
    policy = a.call("/policies")
    assert policy["freshness_hours"] is None
    policy_body = {
        "expected_version": policy["version"],
        "freshness_hours": 24,
        "reminder_lead_hours": 24,
        "reminder_frequency_minutes": 15,
        "visit_checklist": [
            "Review outstanding request owners",
            "Review unresolved exceptions",
        ],
    }
    policy = a.call("/policies", policy_body)
    a.call("/policies", policy_body, 409)
    visit = a.call(
        "/visits",
        {
            "id": str(uuid4()),
            "study_id": "CT-204",
            "site_id": "SITE-104",
            "visit_at": now(),
            "title": "Synthetic monitoring preparation",
        },
        201,
    )
    assert len(visit["checklist"]) == 2
    detail = a.call("/visits/" + visit["id"])
    assert (
        detail["open_cases"]
        and detail["checks"]
        and "score" in detail["interpretation"]
    )
    visit["checklist"][0].update(
        state="needs_follow_up",
        notes="Reviewer needs the current request owner to confirm.",
    )
    edited = a.call(
        "/visits/" + visit["id"],
        {
            "expected_version": visit["version"],
            "visit_at": visit["visit_at"],
            "checklist": visit["checklist"],
        },
    )
    a.call(
        "/visits/" + visit["id"],
        {
            "expected_version": visit["version"],
            "visit_at": visit["visit_at"],
            "checklist": visit["checklist"],
        },
        409,
    )
    passed(
        "configurable freshness/reminder policy and dated monitoring preparation with version protection"
    )
    eval_job = a.call("/evaluations", {"id": str(uuid4()), "mode": "procedure"}, 202)
    for _ in range(90):
        job = a.call("/jobs/" + eval_job["id"])
        if job["status"] == "completed":
            break
        assert job["status"] != "failed", job
        time.sleep(1)
    else:
        raise AssertionError("Evaluation worker timed out")
    result = next(
        r for r in a.call("/evaluations")["runs"] if r["id"] == job["result_id"]
    )
    assert (
        result["results"]["counts"]["scenarios"] == 9
        and result["results"]["counts"]["execution_failures"] == 0
    )
    assert all(
        s["escalation_rule_correct"]
        and s["abstention_correct"]
        and s["citation_validity"]
        and s["flag_correct"]
        for s in result["results"]["scenarios"]
    ), result["results"]
    a.call(
        "/evaluations/" + result["id"] + "/judgment",
        {
            "notes": "Human reviewer finds the synthetic results useful; this is subjective."
        },
    )
    a.call("/walkthrough", {"step": 4, "skipped": False})
    assert a.call("/walkthrough")["step"] == 4
    a.call("/walkthrough", {"step": 4, "skipped": True})
    assert a.call("/walkthrough")["skipped"]
    passed(
        "actual nine-scenario worker evaluation, separate human judgment and resumable/skippable sample walkthrough"
    )
    package = a.call("/cases/CASE-4/package.json")
    for key in [
        "runs",
        "events",
        "checks",
        "requests",
        "evidence",
        "comparisons",
        "snapshots",
        "procedure_versions",
        "reassessments",
        "effort",
        "links",
    ]:
        assert package[key], key
    assert any(
        e["event_type"] == "case_resolved"
        and e["payload"]["checks"]
        and e["payload"]["evidence"]
        for e in package["events"]
    )
    assert a.call("/export")["workflows"]["snapshot_history"]
    b.call("/runs/" + rid, expected=404)
    print(
        "PASS:",
        groups,
        "integrated feature groups; no existing workspace modified.",
        flush=True,
    )
finally:
    with connect() as c:
        for w in workspaces:
            c.execute("DELETE FROM workspaces WHERE id=%s", (w,))
        for u in users:
            c.execute("DELETE FROM users WHERE id=%s", (u,))
