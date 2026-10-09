"""Validate snapshot boundaries and derive facts/drafts without model-written rules."""

from datetime import datetime, timezone
from hashlib import sha256

DRAFT_PROCEDURES = {
    "KB-001": "Check the upload receipt, document processing status, study assignment, and binder filters. A processing delay is one possible cause. If processing remains pending for 15 minutes, draft an engineering escalation with the document ID and upload timestamp. Do not alter the document.",
    "KB-004": "Compare source and destination synchronization timestamps and inspect the synchronization job status. Draft an escalation if the job has failed. Do not overwrite regulatory records.",
}

KINDS = ("synchronization", "document_processing")


def instant(value):
    parsed = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(value.replace("Z", "+00:00"))
    )
    if parsed.tzinfo is None:
        raise ValueError("Operational timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_operations(case, evidence):
    snapshots = set()
    record_ids = set()
    for kind in KINDS:
        group = evidence.get(
            kind, {"snapshot": None, "records": [], "truncated": False}
        )
        snapshot, records = group.get("snapshot"), group.get("records", [])
        if not snapshot:
            if records:
                raise ValueError("Operational records require a snapshot")
            continue
        if snapshot["synthetic"] is not True:
            raise ValueError(
                "This prototype accepts synthetic operational snapshots only"
            )
        if (
            snapshot["study_id"] != case["study_id"]
            or snapshot["site_id"] != case["site_id"]
        ):
            raise ValueError("Operational snapshot scope mismatch")
        observed = instant(snapshot["observed_at"])
        snapshots.add((snapshot["id"], observed))
        for record in records:
            if record["snapshot_id"] != snapshot["id"] or record["id"] in record_ids:
                raise ValueError("Operational record identity mismatch")
            record_ids.add(record["id"])
            if kind == "synchronization":
                if record["status"] not in {"queued", "running", "completed", "failed"}:
                    raise ValueError("Invalid synchronization status")
                fields = (
                    "last_attempt_at",
                    "source_updated_at",
                    "destination_updated_at",
                )
                if not record.get("last_attempt_at"):
                    raise ValueError("Synchronization attempt timestamp missing")
            else:
                if record["processing_status"] not in {
                    "pending",
                    "processed",
                    "failed",
                }:
                    raise ValueError("Invalid document processing status")
                if (
                    record["document_type"] not in {"training_certificate", "other"}
                    or type(record["binder_visible"]) is not bool
                ):
                    raise ValueError("Invalid document record")
                fields = ("uploaded_at", "status_since")
                if instant(record["status_since"]) < instant(record["uploaded_at"]):
                    raise ValueError("Processing status predates upload")
            for field in fields:
                if record.get(field) is not None and instant(record[field]) > observed:
                    raise ValueError("Record timestamp is later than its snapshot")
    if len(snapshots) > 1:
        raise ValueError("Operational tools returned different snapshot versions")
    if snapshots and any(not evidence.get(kind, {}).get("snapshot") for kind in KINDS):
        raise ValueError("Operational snapshot coverage is inconsistent")


def build_operational_review(case, evidence, cited_ids):
    validate_operations(case, evidence)
    findings, drafts = [], []
    articles = {item["id"]: item for item in evidence.get("articles", [])}
    for kind in KINDS:
        group = evidence.get(kind, {})
        snapshot = group.get("snapshot")
        if not snapshot:
            continue
        observed = instant(snapshot["observed_at"])
        for record in group.get("records", []):
            if kind == "synchronization" and "KB-004" in cited_ids:
                facts = [f"Job {record['id']} reported status '{record['status']}'."]
                source, destination = (
                    record.get("source_updated_at"),
                    record.get("destination_updated_at"),
                )
                if source and destination:
                    lag = (instant(source) - instant(destination)).total_seconds() / 60
                    facts.append(
                        f"Source timestamp: {source}; destination timestamp: {destination}."
                    )
                    if lag > 0:
                        facts.append(
                            f"Destination timestamp trails the source by {lag:g} minutes; this does not establish a root cause."
                        )
                if record.get("error_code"):
                    facts.append(
                        f"Recorded error code: {record['error_code']} (not independently verified)."
                    )
                rule = "KB-004"
                should_draft = record["status"] == "failed"
                trigger = "Synchronization job reported failed."
                detail = f"Job: {record['id']}\nSource binder: {record['source_binder_id']}\nDestination binder: {record['destination_binder_id']}\nLast attempt: {record['last_attempt_at']}\nStatus: {record['status']}\nError code: {record.get('error_code') or 'not recorded'}"
            elif (
                kind == "document_processing"
                and "KB-001" in cited_ids
                and record["document_type"] == "training_certificate"
            ):
                age = (observed - instant(record["status_since"])).total_seconds() / 60
                facts = [
                    f"Document {record['document_id']} reported processing status '{record['processing_status']}'.",
                    f"Upload receipt: {record['upload_receipt_id']}; assigned study: {record['assigned_study_id']}; binder visible: {'yes' if record['binder_visible'] else 'no'}.",
                ]
                if record["processing_status"] == "pending":
                    facts.append(
                        f"Recorded pending duration: {age:g} minutes, as of this snapshot."
                    )
                rule = "KB-001"
                should_draft = record["processing_status"] == "pending" and age >= 15
                trigger = f"Document remained pending for {age:g} minutes, meeting the documented 15-minute threshold."
                detail = f"Document: {record['document_id']}\nProcessing record: {record['id']}\nUpload receipt: {record['upload_receipt_id']}\nUpload timestamp: {record['uploaded_at']}\nStatus: {record['processing_status']}\nAssigned study: {record['assigned_study_id']}\nPending since: {record['status_since']}\nRecorded pending duration at snapshot: {age:g} minutes"
            else:
                continue
            findings.append(
                {
                    "record_id": record["id"],
                    "snapshot_id": snapshot["id"],
                    "observed_at": str(snapshot["observed_at"]),
                    "kind": kind,
                    "knowledge_ids": [rule],
                    "facts": facts,
                    "scope": "site-level context; exact case linkage and root cause are unverified",
                }
            )
            # Fail closed if the source procedure has changed since this rule was implemented.
            if (
                should_draft
                and articles.get(rule, {}).get("content") == DRAFT_PROCEDURES[rule]
            ):
                drafts.append(
                    {
                        "id": "DRAFT-" + record["id"],
                        "status": "draft",
                        "subject": f"Synthetic engineering escalation: {case['study_id']} / {case['site_id']} / {record['id']}",
                        "body": f"Synthetic demo — human review required.\nCase: {case['id']}\nStudy: {case['study_id']}\nSite: {case['site_id']}\nSnapshot: {snapshot['id']}\nObserved at: {snapshot['observed_at']}\n\nTrigger: {trigger}\n{detail}\n\nProcedure source: {rule}\nThese are site-level observations; the exact case linkage and root cause are not confirmed. Verify current status before taking action. Do not alter documents or overwrite regulatory records. No external action has been executed.",
                        "record_ids": [record["id"]],
                        "snapshot_id": snapshot["id"],
                        "knowledge_ids": [rule],
                        "requires_human_review": True,
                        "procedure_sha256": sha256(
                            articles[rule]["content"].encode()
                        ).hexdigest(),
                    }
                )
    return {
        "operational_evidence": {
            kind: evidence.get(
                kind, {"snapshot": None, "records": [], "truncated": False}
            )
            for kind in KINDS
        },
        "operational_findings": findings,
        "escalation_drafts": drafts,
    }
