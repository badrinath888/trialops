"""Durable, idempotent in-app reminder scans. No external message delivery."""

from datetime import datetime, timezone, timedelta
from uuid import uuid4
from db import connect


def scan_reminders():
    with connect() as c:
        if not c.execute(
            "SELECT pg_try_advisory_xact_lock(82419732) AS acquired"
        ).fetchone()["acquired"]:
            return 0
        workspaces = c.execute(
            "SELECT w.id,p.reminder_lead_hours,p.reminder_frequency_minutes FROM workspaces w LEFT JOIN workspace_policies p ON p.workspace_id=w.id WHERE w.expires_at IS NULL OR w.expires_at>now()"
        ).fetchall()
        inserted = 0
        now = datetime.now(timezone.utc)
        for w in workspaces:
            frequency = w["reminder_frequency_minutes"] or 60
            scan = c.execute(
                "INSERT INTO reminder_scans(workspace_id) VALUES(%s) ON CONFLICT(workspace_id) DO UPDATE SET last_scan_at=now() WHERE reminder_scans.last_scan_at<now()-(%s * interval '1 minute') RETURNING workspace_id",
                (w["id"], frequency),
            ).fetchone()
            if not scan:
                continue
            members = c.execute(
                'SELECT m.user_id,coalesce(p.enabled,true) AS enabled,coalesce(p.kinds,\'["request","check","reassessment","deadline"]\'::jsonb) AS kinds FROM memberships m LEFT JOIN notification_preferences p ON (p.workspace_id,p.user_id)=(m.workspace_id,m.user_id) WHERE m.workspace_id=%s',
                (w["id"],),
            ).fetchall()
            cases = c.execute(
                "SELECT * FROM cases WHERE workspace_id=%s AND status='open'",
                (w["id"],),
            ).fetchall()
            open_cases = {r["id"]: r for r in cases}
            alerts = []
            for item in cases:
                if item["due_at"] and item["due_at"] <= now + timedelta(
                    hours=w["reminder_lead_hours"]
                    if w["reminder_lead_hours"] is not None
                    else 24
                ):
                    alerts.append(
                        (
                            "deadline",
                            item["id"],
                            "Case follow-up "
                            + ("overdue" if item["due_at"] < now else "approaching")
                            + ": "
                            + item["title"],
                            "deadline:"
                            + item["id"]
                            + ":"
                            + item["due_at"].isoformat()
                            + ":"
                            + str(item["due_at"] < now),
                            item["owner_id"],
                        )
                    )
            for r in c.execute(
                "SELECT * FROM information_requests WHERE workspace_id=%s AND status='requested' AND due_at<now()",
                (w["id"],),
            ).fetchall():
                if r["case_id"] in open_cases:
                    alerts.append(
                        (
                            "request",
                            r["case_id"],
                            "Information request overdue: " + r["title"],
                            "request:" + str(r["id"]) + ":" + r["due_at"].isoformat(),
                            r["owner_id"],
                        )
                    )
            for r in c.execute(
                "SELECT * FROM investigation_checks WHERE workspace_id=%s AND status='active'",
                (w["id"],),
            ).fetchall():
                if r["case_id"] not in open_cases:
                    continue
                for item in r["items"]:
                    if item["state"] in {"not_checked", "needs_follow_up"}:
                        alerts.append(
                            (
                                "check",
                                r["case_id"],
                                "Unfinished investigation check: "
                                + open_cases[r["case_id"]]["title"],
                                "check:"
                                + str(r["id"])
                                + ":"
                                + item["id"]
                                + ":"
                                + item["state"],
                                open_cases[r["case_id"]]["owner_id"],
                            )
                        )
            for r in c.execute(
                "SELECT * FROM procedure_reassessments WHERE workspace_id=%s AND status IN ('pending','needed')",
                (w["id"],),
            ).fetchall():
                if r["case_id"] in open_cases:
                    alerts.append(
                        (
                            "reassessment",
                            r["case_id"],
                            "Procedure reassessment: "
                            + open_cases[r["case_id"]]["title"],
                            "reassessment:"
                            + str(r["run_id"])
                            + ":"
                            + r["article_id"]
                            + ":"
                            + str(r["new_version"])
                            + ":"
                            + r["status"],
                            open_cases[r["case_id"]]["owner_id"],
                        )
                    )
            for kind, cid, title, dedupe, owner in alerts:
                for m in members:
                    if (
                        not m["enabled"]
                        or kind not in m["kinds"]
                        or (owner and m["user_id"] != owner)
                    ):
                        continue
                    result = c.execute(
                        "INSERT INTO notifications(workspace_id,user_id,id,dedupe_key,kind,title,case_id) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id",
                        (w["id"], m["user_id"], uuid4(), dedupe, kind, title, cid),
                    ).fetchone()
                    inserted += bool(result)
        return inserted
