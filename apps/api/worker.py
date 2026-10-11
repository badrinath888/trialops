import json, logging, os, time
from uuid import uuid4
from pathlib import Path
from psycopg.types.json import Jsonb
from db import connect, query, one
from embeddings import embed, MODEL
from investigation import investigate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def claim():
    with connect() as c:
        expired = c.execute(
            "UPDATE jobs SET status='failed',error='Worker interrupted. Retry the task.',finished_at=now(),lease_token=NULL WHERE status='running' AND coalesce(lease_expires_at,started_at+interval '10 minutes')<now() RETURNING workspace_id,kind,target_id"
        ).fetchall()
        for item in expired:
            if item["kind"] == "index":
                c.execute(
                    "UPDATE knowledge SET indexing_status='text_ready',indexing_error='Indexing interrupted. Save the procedure again to retry.' WHERE workspace_id=%s AND id=%s",
                    (item["workspace_id"], item["target_id"]),
                )
        job = c.execute(
            "SELECT * FROM jobs WHERE status='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"
        ).fetchone()
        if not job:
            return None
        token = uuid4()
        c.execute(
            "UPDATE jobs SET status='running',started_at=now(),attempts=attempts+1,lease_token=%s,lease_expires_at=now()+interval '10 minutes' WHERE id=%s",
            (token, job["id"]),
        )
        job["lease_token"] = token
        return job


def process(job):
    started = time.monotonic()
    w = job["workspace_id"]
    if job["kind"] == "watch":
        from case_watch import process_watch
        process_watch(job)
        return
    if job["kind"] == "assess":
        from assessments import process_assessment
        process_assessment(job)
        return
    if job["kind"] == "evaluate":
        from evaluation import evaluate
        from reminders import scan_reminders

        entry = one(
            "SELECT * FROM evaluation_runs WHERE workspace_id=%s AND id=%s",
            (w, job["target_id"]),
        )
        if not entry:
            raise ValueError("Evaluation removed")

        def renew():
            with connect() as c:
                lease = c.execute(
                    "UPDATE jobs SET lease_expires_at=now()+interval '10 minutes' WHERE id=%s AND lease_token=%s AND status='running' RETURNING id",
                    (job["id"], job["lease_token"]),
                ).fetchone()
                if not lease:
                    raise ValueError("Evaluation lease lost")
            scan_reminders()

        if entry["configuration"].get("suite") == "assessments":
            from assessments import fresh_actor
            with connect() as c: fresh_actor(c,w,job["actor_id"])
        result = evaluate(entry["configuration"], renew)
        with connect() as c:
            if entry["configuration"].get("suite") == "assessments": fresh_actor(c,w,job["actor_id"])
            lease = c.execute(
                "SELECT * FROM jobs WHERE id=%s FOR UPDATE", (job["id"],)
            ).fetchone()
            if (
                not lease
                or lease["status"] != "running"
                or lease["lease_token"] != job["lease_token"]
            ):
                return
            c.execute(
                "UPDATE evaluation_runs SET results=%s,finished_at=now() WHERE workspace_id=%s AND id=%s",
                (Jsonb(result), w, entry["id"]),
            )
            c.execute(
                "UPDATE jobs SET status='completed',finished_at=now(),result_id=%s WHERE id=%s",
                (entry["id"], job["id"]),
            )
        return
    if job["kind"] == "index":
        article = one(
            "SELECT * FROM knowledge WHERE workspace_id=%s AND id=%s",
            (w, job["target_id"]),
        )
        if not article:
            raise ValueError("Article removed")
        rows = query(
            "SELECT * FROM knowledge_chunks WHERE workspace_id=%s AND article_id=%s AND version=%s ORDER BY number",
            (w, article["id"], article["version"]),
        )
        vectors = (
            embed([x["content"] for x in rows], "search_document")
            if os.getenv("AI_MODE") == "ollama"
            else None
        )
        with connect() as c:
            lease = c.execute(
                "SELECT status,lease_token FROM jobs WHERE id=%s FOR UPDATE",
                (job["id"],),
            ).fetchone()
            if (
                not lease
                or lease["status"] != "running"
                or lease["lease_token"] != job["lease_token"]
            ):
                return
            for i, row in enumerate(rows):
                if vectors:
                    c.execute(
                        "UPDATE knowledge_chunks SET embedding=%s::vector,embedding_model=%s WHERE workspace_id=%s AND article_id=%s AND version=%s AND number=%s",
                        (
                            json.dumps(vectors[i]),
                            MODEL,
                            w,
                            article["id"],
                            article["version"],
                            row["number"],
                        ),
                    )
            c.execute(
                "UPDATE knowledge SET indexing_status=%s,indexing_error=NULL WHERE workspace_id=%s AND id=%s AND version=%s",
                (
                    "vector_ready" if vectors else "text_ready",
                    w,
                    article["id"],
                    article["version"],
                ),
            )
            c.execute(
                "UPDATE jobs SET status='completed',finished_at=now() WHERE id=%s AND lease_token=%s AND status='running'",
                (job["id"], job["lease_token"]),
            )
            # A document edited during indexing needs its newest version indexed too.
            current = c.execute(
                "SELECT version FROM knowledge WHERE workspace_id=%s AND id=%s",
                (w, article["id"]),
            ).fetchone()
            if current and current["version"] != article["version"]:
                c.execute(
                    "INSERT INTO jobs(id,workspace_id,actor_id,kind,target_id) VALUES(%s,%s,%s,'index',%s) ON CONFLICT DO NOTHING",
                    (uuid4(), w, job["actor_id"], article["id"]),
                )
        return
    case = one(
        "SELECT * FROM cases WHERE workspace_id=%s AND id=%s", (w, job["target_id"])
    )
    if not case or case["status"] != "open":
        raise ValueError("Case no longer open")
    result = investigate(w, case)
    run_id = uuid4()
    with connect() as c:
        lease = c.execute(
            "SELECT status,lease_token FROM jobs WHERE id=%s FOR UPDATE", (job["id"],)
        ).fetchone()
        if (
            not lease
            or lease["status"] != "running"
            or lease["lease_token"] != job["lease_token"]
        ):
            return
        current = c.execute(
            "SELECT status FROM cases WHERE workspace_id=%s AND id=%s FOR UPDATE",
            (w, case["id"]),
        ).fetchone()
        if not current or current["status"] != "open":
            raise ValueError("Case status changed during investigation")
        c.execute(
            "INSERT INTO runs(workspace_id,id,case_id,result,duration_seconds,model) VALUES(%s,%s,%s,%s,%s,%s)",
            (
                w,
                run_id,
                case["id"],
                Jsonb(result),
                round(time.monotonic() - started, 3),
                (
                    os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
                    if os.getenv("AI_MODE") == "ollama"
                    else "procedure-matcher"
                ),
            ),
        )
        from workflows import procedure_impact

        for source in result.get("sources", []):
            if source["id"] in result["recommendation"]["evidence_ids"]:
                article = c.execute(
                    "SELECT version FROM knowledge WHERE workspace_id=%s AND id=%s",
                    (w, source["article_id"]),
                ).fetchone()
                if article and article["version"] > source["version"]:
                    procedure_impact(c, w, source["article_id"], article["version"])
        user = c.execute(
            "SELECT name FROM users WHERE id=%s", (job["actor_id"],)
        ).fetchone()
        c.execute(
            """INSERT INTO case_events(workspace_id,case_id,run_id,actor_id,actor_name,event_type,payload)
        VALUES(%s,%s,%s,%s,%s,'investigation_completed',%s)""",
            (
                w,
                case["id"],
                run_id,
                job["actor_id"],
                user["name"] if user else "Former member",
                Jsonb(
                    {
                        "cited_sources": result["recommendation"]["evidence_ids"],
                        "draft_ids": [d["id"] for d in result["escalation_drafts"]],
                        "external_actions_executed": [],
                    }
                ),
            ),
        )
        c.execute(
            "UPDATE jobs SET status='completed',result_id=%s,finished_at=now() WHERE id=%s",
            (run_id, job["id"]),
        )


def run_once():
    job = claim()
    if not job:
        return False
    try:
        process(job)
    except Exception:
        logging.exception("Job %s failed", job["id"])
        message = (
            "Investigation failed. Check the model connection and retry. No decision or external action was executed."
            if job["kind"] == "investigate"
            else "Evaluation failed. Retry the evaluation; no operational cases were changed."
            if job["kind"] == "evaluate"
            else "Assessment unavailable or failed. Check local Ollama, evidence and reviewer permissions; retry within the limit. No external action was executed."
            if job["kind"] == "assess"
            else "Case watch update failed. Retry from the case; no evidence was confirmed and nothing was sent."
            if job["kind"] == "watch"
            else "Embedding failed. Text search remains available. Check the model and save the procedure again to retry."
        )
        with connect() as c:
            failed = c.execute(
                "UPDATE jobs SET status='failed',error=%s,finished_at=now() WHERE id=%s AND lease_token=%s AND status='running' RETURNING id",
                (message, job["id"], job["lease_token"]),
            ).fetchone()
            if failed and job["kind"] == "index":
                c.execute(
                    "UPDATE knowledge SET indexing_status='text_ready',indexing_error=%s WHERE workspace_id=%s AND id=%s",
                    (message, job["workspace_id"], job["target_id"]),
                )
    return True


def cleanup():
    with connect() as c:
        c.execute("DELETE FROM workspaces WHERE expires_at<now()")
        c.execute("DELETE FROM sessions WHERE expires_at<now()")
        c.execute("DELETE FROM account_tokens WHERE expires_at<now()-interval '2 days'")
        c.execute(
            "DELETE FROM users WHERE guest AND NOT EXISTS(SELECT 1 FROM memberships m WHERE m.user_id=users.id)"
        )
        c.execute("DELETE FROM feedback WHERE created_at<now()-interval '30 days'")
        c.execute("DELETE FROM rate_limits WHERE window_start<now()-interval '2 days'")


if __name__ == "__main__":
    last = 0
    last_reminders = 0
    last_watch = 0
    while True:
        try:
            Path("/tmp/trialops-worker-heartbeat").touch()
            if time.monotonic() - last > 300:
                cleanup()
                last = time.monotonic()
            if time.monotonic() - last_reminders > 60:
                from reminders import scan_reminders

                scan_reminders()
                last_reminders = time.monotonic()
            if time.monotonic() - last_watch > 10:
                from case_watch import scan_watches

                scan_watches()
                last_watch = time.monotonic()
            if not run_once():
                time.sleep(1)
        except Exception:
            logging.exception("Worker loop failed")
            time.sleep(3)
