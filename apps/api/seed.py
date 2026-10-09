import json, os
from uuid import uuid4
from pathlib import Path
from psycopg.types.json import Jsonb
from content import chunks

ARTICLES = json.loads(Path(__file__).with_name("seed_data.json").read_text())


def operations(site="104"):
    study = "CT-204" if site == "104" else "CT-205"
    snapshot = {
        "id": f"OPS-{site}-SAMPLE",
        "study_id": study,
        "site_id": f"SITE-{site}",
        "synthetic": True,
        "observed_at": "2026-10-07T20:00:00Z",
    }
    failed = site == "104"
    job = {
        "id": f"SYNC-{site}-001",
        "snapshot_id": snapshot["id"],
        "source_binder_id": f"BINDER-{site}-SOURCE",
        "destination_binder_id": f"BINDER-{site}-DEST",
        "status": "failed" if failed else "completed",
        "source_updated_at": (
            "2026-10-07T19:40:00Z" if failed else "2026-10-07T19:55:00Z"
        ),
        "destination_updated_at": (
            "2026-10-07T19:10:00Z" if failed else "2026-10-07T19:55:00Z"
        ),
        "last_attempt_at": "2026-10-07T19:50:00Z" if failed else "2026-10-07T19:56:00Z",
        "error_code": "SYNC_TIMEOUT" if failed else None,
    }
    docs = [
        {
            "id": f"PROC-{site}-001",
            "snapshot_id": snapshot["id"],
            "document_id": f"DOC-{site}-CERT-001",
            "document_type": "training_certificate",
            "upload_receipt_id": f"UPLOAD-{site}-001",
            "uploaded_at": "2026-10-07T19:35:00Z" if failed else "2026-10-07T19:55:00Z",
            "status_since": (
                "2026-10-07T19:35:00Z" if failed else "2026-10-07T19:55:00Z"
            ),
            "processing_status": "pending",
            "assigned_study_id": study,
            "binder_visible": False,
        }
    ]
    return {
        "synchronization": {"snapshot": snapshot, "records": [job], "truncated": False},
        "document_processing": {
            "snapshot": snapshot,
            "records": docs,
            "truncated": False,
        },
    }


def seed(c, w):
    for n in [204, 205, 206]:
        c.execute(
            "INSERT INTO studies VALUES (%s,%s,%s)",
            (w, f"CT-{n}", f"Synthetic Study {n-200}"),
        )
        c.execute(
            "INSERT INTO sites VALUES (%s,%s,%s,%s)",
            (w, f"SITE-{n-100}", f"CT-{n}", f"Synthetic Research Site {n-200}"),
        )
    for a in ARTICLES:
        c.execute(
            """INSERT INTO knowledge(workspace_id,id,title,content,category,indexing_status) VALUES(%s,%s,%s,%s,%s,'text_ready')""",
            (w, a["id"], a["title"], a["content"], a["category"]),
        )
        for i, text in enumerate(chunks(a["content"]), 1):
            c.execute(
                "INSERT INTO knowledge_chunks(workspace_id,article_id,version,number,content) VALUES(%s,%s,1,%s,%s)",
                (w, a["id"], i, text),
            )
    if os.getenv("AI_MODE") == "ollama":
        c.execute(
            "UPDATE knowledge SET indexing_status='queued' WHERE workspace_id=%s", (w,)
        )
        for a in ARTICLES:
            c.execute(
                "INSERT INTO jobs(id,workspace_id,kind,target_id) VALUES(%s,%s,'index',%s)",
                (uuid4(), w, a["id"]),
            )
    descriptions = {
        "KB-001": "Training certificates were uploaded, but they are not visible in the destination binder. Please review the upload and processing records.",
        "KB-002": "The study monitor cannot access the assigned study after receiving an invitation. Please review identity and access assignment.",
        "KB-003": "The electronic signature request is still pending. Please review the recipient and delivery status.",
        "KB-004": "Source binder documents stopped updating in the destination binder. Please investigate synchronization using the available records.",
        "KB-005": "A completed training course is not reflected in the dashboard. Please review completion and refresh records.",
    }
    for i, a in enumerate(ARTICLES, 1):
        c.execute(
            """INSERT INTO cases(workspace_id,id,study_id,site_id,title,description,category,priority)
                     VALUES(%s,%s,'CT-204','SITE-104',%s,%s,%s,%s)""",
            (
                w,
                f"CASE-{i}",
                a["title"],
                descriptions[a["id"]],
                a["category"],
                "high" if i == 1 else "medium",
            ),
        )
    for cid, title, description, study, site, category in [
        (
            "CASE-6",
            "Binder synchronization status check",
            "Review the binder synchronization status at this synthetic site.",
            "CT-205",
            "SITE-105",
            "synchronization",
        ),
        (
            "CASE-7",
            "Office cafeteria lunch menu",
            "What meals will the office cafeteria serve tomorrow?",
            "CT-204",
            "SITE-104",
            "unknown",
        ),
        (
            "CASE-8",
            "Synchronization issue without telemetry",
            "Binder synchronization appears delayed. Please check whether records are available.",
            "CT-206",
            "SITE-106",
            "synchronization",
        ),
    ]:
        c.execute(
            """INSERT INTO cases(workspace_id,id,study_id,site_id,title,description,category,priority) VALUES(%s,%s,%s,%s,%s,%s,%s,'low')""",
            (w, cid, study, site, title, description, category),
        )
    for site in ["104", "105"]:
        c.execute(
            "INSERT INTO operations VALUES(%s,%s,%s,%s,now())",
            (
                w,
                "CT-204" if site == "104" else "CT-205",
                f"SITE-{site}",
                Jsonb(operations(site)),
            ),
        )
