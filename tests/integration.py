"""Creates isolated temporary workspaces against a running API and worker.
Run inside the API container: python /app/tests/integration.py.
Temporary accounts are removed in finally; no existing cases are modified.
"""

import concurrent.futures, copy, http.cookiejar, json, os, sys, time, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from db import secret, connect

URL = os.getenv("TEST_API_URL", "http://api:8000")


class Client:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies)
        )

    def call(self, path, body=None, expected=200):
        req = urllib.request.Request(
            URL + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Content-Type": "application/json",
                "X-Internal-Key": secret("INTERNAL_KEY"),
                "X-Client-IP": str(id(self)),
                "Cookie": "; ".join(c.name + "=" + c.value for c in self.cookies),
            },
        )
        try:
            with self.opener.open(req, timeout=30) as res:
                status = res.status
                data = json.load(res)
        except urllib.error.HTTPError as e:
            status = e.code
            raw = e.read().decode()
            try: data = json.loads(raw)
            except ValueError: data = {"detail":raw}
        assert status == expected, (path, status, data)
        return data

    def run(self, case):
        job = self.call("/cases/" + case + "/investigate", {}, 202)
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            current = self.call("/jobs/" + job["id"])
            if current["status"] == "failed":
                raise AssertionError(current["error"])
            if current["status"] == "completed":
                return self.call("/runs/" + current["result_id"])["run"]
            time.sleep(2)
        raise AssertionError("Worker did not finish within ten minutes")


def main():
    accounts = []
    workspaces = []
    checks = 0

    def passed(label):
        nonlocal checks
        checks += 1
        print("PASS:", label, flush=True)

    try:
        a, b = Client(), Client()
        a.call("/auth/me", expected=401)
        for c in (a, b):
            w = c.call("/auth/demo", {})["workspace_id"]
            workspaces.append(w)
            accounts.append(c.call("/auth/me")["user_id"])
        passed("unauthenticated access blocked; isolated sample sessions created")
        a.call(
            "/catalog/studies", {"id": "CT-NEW", "name": "Synthetic added study"}, 201
        )
        a.call("/catalog/studies", {"id": "CT-NEW", "name": "Duplicate study"}, 409)
        a.call(
            "/catalog/sites",
            {
                "id": "SITE-NEW",
                "study_id": "CT-MISSING",
                "name": "Synthetic added site",
            },
            422,
        )
        a.call(
            "/catalog/sites",
            {"id": "SITE-NEW", "study_id": "CT-NEW", "name": "Synthetic added site"},
            201,
        )
        assert not any(x["id"] == "CT-NEW" for x in b.call("/catalog")["studies"])
        passed(
            "owner-managed study/site catalog validates unique IDs and workspace scope"
        )
        case = a.call(
            "/cases",
            {
                "title": "Private certificate issue",
                "description": "Uploaded training certificate is missing from the regulatory binder.",
                "study_id": "CT-204",
                "site_id": "SITE-104",
                "category": "document_workflow",
                "priority": "high",
            },
            201,
        )
        b.call("/cases/" + case["id"], expected=404)
        a.call(
            "/cases",
            {
                "title": "Mismatched study issue",
                "description": "Synthetic issue for wrong study site.",
                "study_id": "CT-205",
                "site_id": "SITE-104",
                "category": "unknown",
                "priority": "low",
            },
            422,
        )
        passed("cross-workspace case access and mismatched study/site blocked")
        a.call("/cases/" + case["id"] + "/assignment", {"owner_id": None, "due_at": "2020-01-01T00:00:00Z"})
        attention = a.call("/dashboard")["attention"]
        assert case["id"] in [x["id"] for x in attention["overdue"]["items"]]
        assert case["id"] in [x["id"] for x in attention["unassigned"]["items"]]
        foreign = b.call("/dashboard")["attention"]
        assert case["id"] not in [x["id"] for group in foreign.values() for x in group["items"]]
        passed("attention queue shows overdue/high-priority cases and isolates workspaces")

        a.call("/cases/" + case["id"] + "/assignment", {"owner_id": accounts[0], "due_at": "2020-01-01T00:00:00Z"})
        assert case["id"] in [x["id"] for x in a.call("/cases?view=mine")["items"]]
        assert case["id"] in [x["id"] for x in a.call("/cases?view=overdue")["items"]]
        assert case["id"] not in [x["id"] for x in a.call("/cases?view=unassigned")["items"]]
        assert not any(x["id"] == case["id"] for x in b.call("/cases?view=mine")["items"])
        # More than one page: server filtering and totals must span the full workspace.
        for i in range(27):
            a.call("/cases", {"title": "Pagination fixture %02d" % i, "description": "Synthetic pagination test. No patient information.", "study_id":"CT-204", "site_id":"SITE-104", "category":"synchronization", "priority":"low"}, 201)
        first=a.call("/cases?q=Pagination%20fixture&priority=low")
        second=a.call("/cases?q=Pagination%20fixture&priority=low&offset=25")
        assert first["total"] == second["total"] == 27
        assert len(first["items"]) == 25 and len(second["items"]) == 2
        assert not set(x["id"] for x in first["items"]) & set(x["id"] for x in second["items"])
        assert b.call("/cases?q=Pagination%20fixture")["total"] == 0
        a.call("/cases?view=not-a-view", expected=422)
        recent=a.call("/dashboard")["recent_cases"]
        assert len(recent)==5 and all(x["title"].startswith("Pagination fixture") for x in recent)
        assert not any(x["title"].startswith("Pagination fixture") for x in b.call("/dashboard")["recent_cases"])
        passed("personal/overdue views, workspace isolation, full-result pagination, and invalid view rejection")

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(a.call, "/cases/CASE-4/investigate", {}, 202)
                for _ in range(2)
            ]
            jobs = [f.result() for f in futures]
        assert jobs[0]["id"] == jobs[1]["id"]
        passed("concurrent investigation requests reuse one active job")
        r = a.run("CASE-4")
        rid = r["id"]
        assert "CASE-4" in [x["id"] for x in a.call("/cases?view=review")["items"]]
        assert r["result"]["recommendation"]["status"] == "supported"
        reviews = a.call("/dashboard")["attention"]["reviews"]["items"]
        assert any(item["id"] == rid for item in reviews)

        assert len(r["result"]["tool_calls"]) == 6
        assert len(r["result"]["escalation_drafts"]) >= 1
        b.call("/runs/" + rid, expected=404)
        passed(
            "background worker completed six actual MCP tool calls; scoped saved evidence and drafts"
        )
        a.call(
            "/cases/CASE-4/resolve",
            {
                "run_id": rid,
                "notes": "Checked current synthetic status and completed the review.",
                "confirmed": True,
            },
            422,
        )
        a.call(
            "/runs/" + rid + "/decision",
            {
                "decision": "approved",
                "notes": "Reviewed the documented checks and historical scope.",
            },
        )
        assert a.call("/cases/CASE-4")["case"]["status"] == "open"
        assert "CASE-4" not in [x["id"] for x in a.call("/cases?view=review")["items"]]
        a.call(
            "/runs/" + rid + "/decision",
            {"decision": "approved", "notes": "Duplicate review attempt."},
            409,
        )
        passed(
            "approval needs support, preserves open status, and rejects duplicate decisions"
        )
        observation = a.call("/cases/CASE-4/evidence", {"id": str(uuid4()), "kind": "human_observation", "summary": "Personally reviewed current synthetic records for this test.", "observed_at": datetime.now(timezone.utc).isoformat()}, 201)
        checklist = a.call("/runs/"+rid+"/checks", {}, 201)
        checklist = a.call("/cases/CASE-4/checks/"+checklist["id"]+"/activate", {"expected_version": checklist["version"]})
        for item in checklist["items"]:
            item.update(state="verified", evidence_refs=[observation["id"]], notes="Current records checked by test reviewer.")
        a.call("/cases/CASE-4/checks/"+checklist["id"], {"expected_version": checklist["version"], "items": checklist["items"]})
        body = {
            "expected_updated_at": a.call("/cases/CASE-4")["case"]["updated_at"],
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "evidence_refs": [observation["id"]],
            "run_id": rid,
            "notes": "Verified current synthetic status and completed all checks.",
            "confirmed": True,
        }
        a.call("/cases/CASE-1/resolve", body, 422)
        a.call("/cases/CASE-4/resolve", {**body, "confirmed": False}, 422)
        a.call("/cases/CASE-4/resolve", body)
        a.call("/cases/CASE-4/resolve", body, 409)
        a.call(
            "/cases/CASE-4/reopen",
            {"notes": "Reopening to check updated synthetic operational conditions."},
        )
        events = a.call("/cases/CASE-4")["events"]
        assert sum(x["event_type"] == "case_resolved" for x in events) == 1
        assert any(x["event_type"] == "case_reopened" for x in events)
        passed(
            "manual resolution, wrong-case protection, duplicate protection, and preserved reopening audit"
        )
        unsupported = a.run("CASE-7")
        assert (
            unsupported["result"]["recommendation"]["status"] == "insufficient_evidence"
        )
        assert not unsupported["result"]["escalation_drafts"]
        a.call(
            "/runs/" + unsupported["id"] + "/decision",
            {
                "decision": "approved",
                "notes": "This unsupported decision should be blocked.",
            },
            422,
        )
        a.call(
            "/runs/" + unsupported["id"] + "/decision",
            {
                "decision": "rejected",
                "notes": "No relevant operational procedure supports cafeteria requests.",
            },
        )
        healthy = a.run("CASE-6")
        assert not healthy["result"]["escalation_drafts"]
        uncovered = a.run("CASE-8")
        assert not uncovered["result"]["escalation_drafts"]
        passed(
            "unsupported abstention, healthy/no-coverage cases, and escalation boundaries"
        )
        old = next(x for x in a.call("/knowledge") if x["id"] == "KB-004")
        update = {
            "title": old["title"],
            "content": old["content"]
            + " Manual review of the newer procedure is required.",
            "category": old["category"],
            "expected_version": old["version"],
        }
        a.call("/knowledge/KB-004", update)
        a.call("/knowledge/KB-004", update, 409)
        assert a.call("/runs/" + rid)["run"]["result"] == r["result"]
        a.call("/knowledge/KB-004/archive", {"archived": True, "expected_version": 2})
        a.call("/knowledge/KB-004/archive", {"archived": False, "expected_version": 2})
        passed(
            "knowledge version conflict, archive/restore, and immutable saved evidence"
        )
        snapshot = a.call("/operations/example")
        bad = copy.deepcopy(snapshot)
        bad["evidence"]["synchronization"]["snapshot"]["site_id"] = "SITE-105"
        a.call("/operations", bad, 422)
        a.call("/operations", snapshot)
        passed("snapshot import validates scope and timestamps")
        a.call(
            "/cases/CASE-4/assignment", {"owner_id": accounts[1], "due_at": None}, 422
        )
        a.call(
            "/cases/CASE-4/notes",
            {"notes": "Operational follow-up note for the synthetic case."},
        )
        a.call(
            "/roi/" + rid,
            {
                "baseline": 8,
                "assisted": 30,
                "hourly_cost": 55,
                "ai_cost": 0,
                "confirmed": True,
            },
        )
        a.call(
            "/roi/" + rid,
            {
                "baseline": 30,
                "assisted": 8,
                "hourly_cost": 55,
                "ai_cost": 0,
                "confirmed": True,
            },
            409,
        )
        assert float(a.call("/roi")[0]["baseline"]) == 8
        a.call(
            "/feedback",
            {
                "rating": 4,
                "message": "The evidence workflow is clear and helpful for this sample.",
            },
            201,
        )
        assert len(a.call("/export")["runs"]) == 4
        passed(
            "member assignment validation, notes, negative ROI assumptions, feedback, and export"
        )
        interrupted = str(uuid4())
        with connect() as c:
            c.execute(
                "UPDATE knowledge SET indexing_status='queued' WHERE workspace_id=%s AND id='KB-005'",
                (workspaces[0],),
            )
            c.execute(
                "INSERT INTO jobs(id,workspace_id,actor_id,kind,target_id,status,lease_token,started_at) VALUES(%s,%s,%s,'index','KB-005','running',%s,now()-interval '11 minutes')",
                (interrupted, workspaces[0], accounts[0], uuid4()),
            )
        for _ in range(20):
            if a.call("/jobs/" + interrupted)["status"] == "failed":
                break
            time.sleep(1)
        else:
            raise AssertionError("Interrupted task lease was not recovered")
        recovered = next(x for x in a.call("/knowledge") if x["id"] == "KB-005")
        assert (
            recovered["indexing_status"] == "text_ready" and recovered["indexing_error"]
        )
        passed("interrupted worker lease fails visibly and preserves text retrieval")
        owner, analyst = Client(), Client()
        password = "Integration-check-only-phrase"
        for c, name in ((owner, "Owner"), (analyst, "Analyst")):
            email = str(uuid4()) + "@tests.invalid"
            c.call(
                "/auth/register",
                {"name": name, "email": email, "password": password},
                201,
            )
            me = c.call("/auth/me")
            accounts.append(me["user_id"])
            workspaces.append(me["workspace_id"])
        code = owner.call("/invitations", {"role": "analyst"})["code"]
        joined = analyst.call("/invitations/accept", {"code": code})
        analyst.call("/auth/switch", {"workspace_id": joined["workspace_id"]})
        analyst.call("/invitations/accept", {"code": code}, 422)
        analyst.call(
            "/knowledge",
            {
                "title": "Forbidden procedure",
                "content": "An analyst cannot maintain documented procedures.",
                "category": "unknown",
            },
            403,
        )
        rr = analyst.run("CASE-4")
        analyst.call(
            "/runs/" + rr["id"] + "/decision",
            {
                "decision": "approved",
                "notes": "An analyst cannot approve this recommendation.",
            },
            403,
        )
        analyst.call(
            "/catalog/studies", {"id": "CT-BLOCKED", "name": "Blocked study"}, 403
        )
        analyst.call("/export", expected=403)
        analyst.call("/evaluations", expected=403)
        analyst.call("/evaluations", {"id":str(uuid4()),"mode":"procedure"},403)
        analyst.call("/policies", {"expected_version":1,"freshness_hours":24,"reminder_lead_hours":24,"reminder_frequency_minutes":60,"visit_checklist":[]},403)
        cl=analyst.call("/runs/"+rr["id"]+"/checks",{},201)
        analyst.call("/cases/CASE-4/checks/"+cl["id"]+"/activate",{"expected_version":cl["version"]},403)
        analyst.call("/visits",{"id":str(uuid4()),"title":"Blocked analyst visit","study_id":"CT-204","site_id":"SITE-104","visit_at":datetime.now(timezone.utc).isoformat()},403)
        owner.call("/walkthrough",expected=403)
        owner.call("/walkthrough/updated-records",{},403)
        passed(
            "registered accounts, one-use invitations, workspace switching, and server-enforced analyst permissions"
        )
        owner.call("/auth/logout", {})
        owner.call("/auth/me", expected=401)
        print(
            f"PASS: {checks} integration groups. Temporary test records removed in finally.",
            flush=True,
        )
    finally:
        with connect() as c:
            for w in workspaces:
                c.execute("DELETE FROM workspaces WHERE id=%s", (w,))
            for u in accounts:
                c.execute("DELETE FROM feedback WHERE actor_id=%s", (u,))
                c.execute("DELETE FROM users WHERE id=%s", (u,))


if __name__ == "__main__":
    main()
