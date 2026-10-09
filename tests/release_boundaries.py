"""Additional concurrency, expiry, worker retry and empty-scope boundaries."""

import concurrent.futures, json, time, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from integration import Client
from db import connect
from evaluation import configuration, dataset
from psycopg.types.json import Jsonb
from worker import process

a = Client()
w = a.call("/auth/demo", {})["workspace_id"]
me = a.call("/auth/me")
uid = me["user_id"]
try:
    policy = a.call("/policies")
    body = {
        "expected_version": policy["version"],
        "freshness_hours": 12,
        "reminder_lead_hours": 24,
        "reminder_frequency_minutes": 15,
        "visit_checklist": [],
    }

    def save_concurrently(path, body):
        try:
            a.call(path, body)
            return 200
        except AssertionError as e:
            assert e.args[0][1] == 409, e
            return 409

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(
            pool.map(lambda _: save_concurrently("/policies", body), range(2))
        ) == [200, 409]
    print(
        "PASS: actual simultaneous policy writes permit one version and reject the stale writer",
        flush=True,
    )
    case = {
        "submission_id": str(uuid4()),
        "title": "Concurrent synthetic binder intake",
        "description": "Synthetic binder receipt needs review without duplicated intake.",
        "study_id": "CT-204",
        "site_id": "SITE-104",
        "category": "synchronization",
        "priority": "medium",
    }
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        created = list(pool.map(lambda _: a.call("/cases", case, 201), range(2)))
    assert created[0]["id"] == created[1]["id"]
    example = a.call("/operations/import-example")
    preview = a.call(
        "/operations/import-preview",
        {"format": "json", "content": example["content"], "mapping": {}},
        201,
    )
    with connect() as c:
        c.execute(
            "UPDATE import_previews SET expires_at=now()-interval '1 minute' WHERE workspace_id=%s AND id=%s",
            (w, preview["id"]),
        )
    a.call(
        "/operations/import-preview/" + preview["id"] + "/commit",
        {"confirmed": True},
        409,
    )
    print(
        "PASS: simultaneous intake is idempotent and expired previews cannot commit",
        flush=True,
    )
    eid = str(uuid4())
    jid = str(uuid4())
    token = uuid4()
    with connect() as c:
        c.execute(
            "INSERT INTO evaluation_runs(workspace_id,id,dataset_version,model,configuration,actor_id) VALUES(%s,%s,%s,%s,%s,%s)",
            (
                w,
                eid,
                dataset()["version"],
                "procedure-matcher",
                Jsonb(configuration("procedure")),
                uid,
            ),
        )
        c.execute(
            "INSERT INTO jobs(id,workspace_id,actor_id,kind,target_id,status,lease_token,started_at,lease_expires_at) VALUES(%s,%s,%s,'evaluate',%s,'running',%s,now()-interval '11 minutes',now()-interval '1 minute')",
            (jid, w, uid, eid, token),
        )
    for _ in range(30):
        if a.call("/jobs/" + jid)["status"] == "failed":
            break
        time.sleep(1)
    else:
        raise AssertionError("Expired evaluation lease not recovered")
    retried = a.call("/evaluations/" + eid + "/retry", {}, 202)
    a.call("/evaluations/" + eid + "/retry", {}, 409)
    for _ in range(60):
        status = a.call("/jobs/" + retried["id"])
        if status["status"] == "completed":
            break
        assert status["status"] != "failed", status
        time.sleep(1)
    else:
        raise AssertionError("Evaluation retry did not finish")
    rows = [r for r in a.call("/evaluations")["runs"] if r["id"] == eid]
    assert len(rows) == 1 and rows[0]["status"] == "completed" and rows[0]["results"]
    print(
        "PASS: interrupted evaluation fails visibly, retry completes, and the dashboard returns only its latest job state",
        flush=True,
    )
    with connect() as c:
        before = c.execute(
            "SELECT results FROM evaluation_runs WHERE workspace_id=%s AND id=%s",
            (w, eid),
        ).fetchone()["results"]
    try:
        process(
            {
                "id": retried["id"],
                "workspace_id": w,
                "target_id": eid,
                "kind": "evaluate",
                "lease_token": uuid4(),
            }
        )
    except ValueError as e:
        assert "lease lost" in str(e)
    with connect() as c:
        assert (
            c.execute(
                "SELECT results FROM evaluation_runs WHERE workspace_id=%s AND id=%s",
                (w, eid),
            ).fetchone()["results"]
            == before
        )
    print(
        "PASS: a worker with a lost lease cannot overwrite completed evaluation results",
        flush=True,
    )
    # Delete only synthetic fixtures in this explicitly isolated temporary workspace.
    with connect() as c:
        c.execute("DELETE FROM cases WHERE workspace_id=%s", (w,))
        c.execute("DELETE FROM operations WHERE workspace_id=%s", (w,))
        c.execute("DELETE FROM snapshot_history WHERE workspace_id=%s", (w,))
        c.execute("DELETE FROM knowledge WHERE workspace_id=%s", (w,))
    assert (
        a.call("/cases")["total"] == 0
        and not a.call("/operations/history")
        and not a.call("/knowledge")
    )
    assert not a.call("/metrics")["resolution_cycles"]
    print(
        "PASS: empty workspace APIs have explicit empty results without fabricated evidence",
        flush=True,
    )
finally:
    with connect() as c:
        c.execute("DELETE FROM workspaces WHERE id=%s", (w,))
        c.execute("DELETE FROM users WHERE id=%s", (uid,))
