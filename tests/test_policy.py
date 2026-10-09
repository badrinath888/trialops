"""Deterministic policy regressions; does not call a model or modify the database."""

import copy
import json
import unittest
from unittest.mock import patch

from operational_evidence import (
    DRAFT_PROCEDURES,
    build_operational_review,
    validate_operations,
)

CASE = {
    "id": "TEST-CASE",
    "title": "Binder synchronization has stalled",
    "description": "Synthetic issue",
    "study_id": "CT-204",
    "site_id": "SITE-104",
}


def fixture(minutes=25, sync_status="failed", processing_status="pending"):
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 10, 7, 20, tzinfo=timezone.utc)
    snapshot = {
        "id": "OPS-TEST",
        "study_id": "CT-204",
        "site_id": "SITE-104",
        "synthetic": True,
        "observed_at": now.isoformat(),
    }
    return {
        "study": {"id": "CT-204"},
        "site": {"id": "SITE-104", "study_id": "CT-204"},
        "cases": [],
        "articles": [
            {"id": key, "content": content, "title": key}
            for key, content in DRAFT_PROCEDURES.items()
        ],
        "synchronization": {
            "snapshot": copy.deepcopy(snapshot),
            "truncated": False,
            "records": [
                {
                    "id": "SYNC-TEST",
                    "snapshot_id": "OPS-TEST",
                    "source_binder_id": "SRC",
                    "destination_binder_id": "DST",
                    "status": sync_status,
                    "last_attempt_at": (now - timedelta(minutes=10)).isoformat(),
                    "source_updated_at": (now - timedelta(minutes=20)).isoformat(),
                    "destination_updated_at": (now - timedelta(minutes=50)).isoformat(),
                    "error_code": "SYNC_TIMEOUT" if sync_status == "failed" else None,
                }
            ],
        },
        "document_processing": {
            "snapshot": copy.deepcopy(snapshot),
            "truncated": False,
            "records": [
                {
                    "id": "PROC-TEST",
                    "snapshot_id": "OPS-TEST",
                    "document_id": "DOC-TEST",
                    "document_type": "training_certificate",
                    "upload_receipt_id": "UPLOAD-TEST",
                    "uploaded_at": (now - timedelta(minutes=minutes)).isoformat(),
                    "status_since": (now - timedelta(minutes=minutes)).isoformat(),
                    "processing_status": processing_status,
                    "assigned_study_id": "CT-204",
                    "binder_visible": processing_status == "processed",
                }
            ],
        },
    }


class OperationalPolicyTests(unittest.TestCase):
    def test_failed_sync_drafts_only_with_cited_procedure(self):
        result = build_operational_review(CASE, fixture(), ["KB-004"])
        self.assertEqual(
            [x["record_ids"] for x in result["escalation_drafts"]], [["SYNC-TEST"]]
        )
        draft = result["escalation_drafts"][0]
        self.assertTrue(draft["requires_human_review"])
        self.assertEqual(draft["status"], "draft")
        self.assertIn("No external action", draft["body"])
        self.assertIn("2026-10-07", draft["body"])
        self.assertEqual(len(draft["procedure_sha256"]), 64)

    def test_no_citations_yields_no_issue_findings_or_drafts(self):
        result = build_operational_review(CASE, fixture(), [])
        self.assertEqual(result["operational_findings"], [])
        self.assertEqual(result["escalation_drafts"], [])

    def test_pending_threshold_boundary(self):
        for minutes, expected in [(0, 0), (5, 0), (14.999, 0), (15, 1), (25, 1)]:
            with self.subTest(minutes=minutes):
                result = build_operational_review(
                    CASE, fixture(minutes=minutes), ["KB-001"]
                )
                self.assertEqual(len(result["escalation_drafts"]), expected)

    def test_processed_and_failed_documents_do_not_trigger_pending_rule(self):
        for status in ["processed", "failed"]:
            result = build_operational_review(
                CASE, fixture(processing_status=status), ["KB-001"]
            )
            self.assertEqual(result["escalation_drafts"], [])

    def test_healthy_and_running_sync_never_trigger_failed_rule(self):
        for status in ["completed", "queued", "running"]:
            result = build_operational_review(
                CASE, fixture(sync_status=status), ["KB-004"]
            )
            self.assertEqual(result["escalation_drafts"], [])

    def test_rule_does_not_require_both_pending_and_sync_failure(self):
        result = build_operational_review(
            CASE, fixture(sync_status="completed"), ["KB-001", "KB-004"]
        )
        self.assertEqual(
            [x["record_ids"] for x in result["escalation_drafts"]], [["PROC-TEST"]]
        )

    def test_pending_age_uses_snapshot_not_wall_clock(self):
        data = fixture(minutes=25)
        result = build_operational_review(CASE, data, ["KB-001"])
        self.assertIn("25 minutes", result["operational_findings"][0]["facts"][-1])

    def test_old_upload_with_recent_pending_transition_does_not_escalate(self):
        data = fixture(minutes=25)
        data["document_processing"]["records"][0][
            "status_since"
        ] = "2026-10-07T19:55:00Z"
        self.assertEqual(
            build_operational_review(CASE, data, ["KB-001"])["escalation_drafts"], []
        )

    def test_source_drift_blocks_drafts(self):
        for key in DRAFT_PROCEDURES:
            data = fixture()
            next(x for x in data["articles"] if x["id"] == key)[
                "content"
            ] = "Changed procedure: ask a reviewer."
            result = build_operational_review(CASE, data, [key])
            self.assertTrue(result["operational_findings"])
            self.assertEqual(result["escalation_drafts"], [])

    def test_other_document_types_do_not_use_certificate_rule(self):
        data = fixture()
        data["document_processing"]["records"][0]["document_type"] = "other"
        self.assertEqual(
            build_operational_review(CASE, data, ["KB-001"])["operational_findings"], []
        )

    def test_no_operational_coverage_is_valid(self):
        self.assertEqual(
            build_operational_review(CASE, {}, ["KB-004"])["escalation_drafts"], []
        )

    def test_scope_identity_status_and_time_are_validated(self):
        changes = [
            ("synchronization", "snapshot", "study_id", "CT-205"),
            ("synchronization", "snapshot", "site_id", "SITE-105"),
            ("synchronization", "snapshot", "synthetic", False),
            ("synchronization", "snapshot", "observed_at", "2026-10-07T20:00:00"),
            ("synchronization", "snapshot", "id", "DIFFERENT"),
            ("synchronization", "record", "snapshot_id", "DIFFERENT"),
            ("synchronization", "record", "last_attempt_at", "2026-10-07T20:01:00Z"),
            ("synchronization", "record", "status", "invented"),
            ("document_processing", "record", "uploaded_at", "2026-10-07T20:01:00Z"),
            ("document_processing", "record", "binder_visible", "false"),
            ("document_processing", "record", "processing_status", "invented"),
        ]
        for kind, level, field, value in changes:
            with self.subTest(change=(kind, field)):
                data = fixture()
                target = (
                    data[kind]["snapshot"]
                    if level == "snapshot"
                    else data[kind]["records"][0]
                )
                target[field] = value
                with self.assertRaises(ValueError):
                    validate_operations(CASE, data)
        data = fixture()
        data["synchronization"]["snapshot"] = None
        with self.assertRaises(ValueError):
            validate_operations(CASE, data)
        data = fixture()
        data["synchronization"]["records"].append(
            copy.deepcopy(data["synchronization"]["records"][0])
        )
        with self.assertRaises(ValueError):
            validate_operations(CASE, data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
