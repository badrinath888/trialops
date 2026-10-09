"""Pure workflow boundaries; no operational accounts or database mutations."""

import copy, io, json, sys, unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from fastapi import HTTPException
from pypdf import PdfReader
from seed import operations, ARTICLES
from workflows import (
    compare_snapshots,
    evidence_flags,
    preview_rows,
    check_items,
    checklist_suggestions,
)
from operational_evidence import validate_operations
from report import build_case_report
from evaluation import configuration, evaluate

CASE = {
    "id": "CASE-TEST",
    "study_id": "CT-204",
    "site_id": "SITE-104",
    "title": "Binder problem",
}


def snap(evidence=None, time="2026-10-07T20:00:00Z"):
    return {
        "workspace_id": "test",
        "study_id": "CT-204",
        "site_id": "SITE-104",
        "observed_at": time,
        "evidence": evidence or operations(),
    }


class WorkflowTests(unittest.TestCase):
    def test_comparison_preserves_missing_and_unchanged(self):
        before = snap()
        after = snap(time="2026-10-08T20:00:00Z")
        after["evidence"] = copy.deepcopy(before["evidence"])
        after["evidence"]["synchronization"]["records"] = []
        original = copy.deepcopy(before)
        r = compare_snapshots(before, after)
        self.assertEqual([x["state"] for x in r["records"]], ["missing", "unchanged"])
        self.assertIn("does not establish resolution", r["interpretation"])
        self.assertEqual(before, original)

    def test_comparison_rejects_scope_and_reverse_time(self):
        before = snap()
        after = snap()
        after["site_id"] = "other"
        with self.assertRaises(HTTPException):
            compare_snapshots(before, after)
        with self.assertRaises(HTTPException):
            compare_snapshots(before, snap())

    def test_comparison_stable_identity_changed_fields(self):
        before = snap()
        after = snap(time="2026-10-08T20:00:00Z")
        after["evidence"]["synchronization"]["records"][0].update(
            snapshot_id="NEW", status="completed"
        )
        row = compare_snapshots(before, after)["records"][0]
        self.assertEqual(row["state"], "changed")
        self.assertEqual([f["field"] for f in row["fields"]], ["status"])

    def test_age_requires_explicit_policy(self):
        now = datetime(2030, 1, 1, tzinfo=timezone.utc)
        self.assertFalse(
            any(
                x["type"] == "stale"
                for x in evidence_flags(CASE, operations(), None, now)
            )
        )
        self.assertTrue(
            any(
                x["type"] == "stale"
                for x in evidence_flags(CASE, operations(), 24, now)
            )
        )

    def test_conflict_names_actual_records(self):
        evidence = operations()
        r = copy.deepcopy(evidence["document_processing"]["records"][0])
        r.update(id="PROC-OTHER", processing_status="processed")
        evidence["document_processing"]["records"].append(r)
        flag = next(
            x for x in evidence_flags(CASE, evidence) if x["type"] == "conflict"
        )
        self.assertEqual(flag["entity"], "DOC-104-CERT-001")
        self.assertEqual(len(flag["records"]), 2)

    def test_chronology_scope_and_absence_flags(self):
        evidence = operations()
        evidence["synchronization"]["snapshot"]["site_id"] = "WRONG"
        evidence["synchronization"]["records"][0]["last_attempt_at"] = (
            "2030-01-01T00:00:00Z"
        )
        evidence["document_processing"] = {"snapshot": None, "records": []}
        self.assertTrue(
            {"scope", "chronology", "missing"}
            <= {x["type"] for x in evidence_flags(CASE, evidence)}
        )

    def test_two_group_observation_times_must_match(self):
        e = operations()
        e["document_processing"]["snapshot"] = copy.deepcopy(
            e["document_processing"]["snapshot"]
        )
        e["document_processing"]["snapshot"]["observed_at"] = "2026-10-08T20:00:00Z"
        with self.assertRaises(ValueError):
            validate_operations(CASE, e)

    def rows(self):
        result = []
        for kind, group in operations().items():
            result += [
                {
                    **r,
                    **{
                        k: group["snapshot"][k]
                        for k in ("study_id", "site_id", "observed_at", "synthetic")
                    },
                    "kind": kind,
                }
                for r in group["records"]
            ]
        return result

    def test_preview_maps_fields_rejects_duplicates_and_wrong_scope(self):
        rows = self.rows()
        rows[0]["Study"] = rows[0].pop("study_id")
        rows += [copy.deepcopy(rows[0]), {**rows[1], "site_id": "WRONG"}]
        accepted, rejected, groups = preview_rows(
            json.dumps(rows), "json", {"Study": "study_id"}, {("CT-204", "SITE-104")}
        )
        self.assertEqual(len(accepted), 2)
        self.assertEqual(len(rejected), 2)
        self.assertEqual(len(groups), 1)

    def test_preview_invalid_json_and_future_timestamp(self):
        with self.assertRaises(HTTPException):
            preview_rows("{broken", "json", {}, set())
        rows = self.rows()
        rows[0]["observed_at"] = "2030-01-01T00:00:00Z"
        accepted, rejected, _ = preview_rows(
            json.dumps(rows), "json", {}, {("CT-204", "SITE-104")}
        )
        self.assertEqual(len(rejected), 1)

    def test_suggested_checks_preserve_exact_content(self):
        source = {"id": "KB-001#v1-s1", "content": ARTICLES[0]["content"], "version": 1}
        sources, items = checklist_suggestions(
            {"recommendation": {"evidence_ids": [source["id"]]}, "sources": [source]}
        )
        self.assertEqual(items[0]["text"], source["content"])
        self.assertTrue(items[0]["suggestion"])
        self.assertEqual(sources, [source])

    def test_verified_check_requires_evidence_and_exception_notes(self):
        item = {
            "id": str(uuid4()),
            "text": "Check the record",
            "source_id": "exact",
            "state": "verified",
            "evidence_refs": [],
            "notes": "",
        }
        actor = {"user_id": uuid4(), "name": "Reviewer"}
        with self.assertRaises(HTTPException):
            check_items([item], [{"id": "exact"}], actor=actor)
        item.update(state="needs_follow_up")
        with self.assertRaises(HTTPException):
            check_items([item], [{"id": "exact"}], actor=actor)
        item.update(notes="Waiting for the current record.")
        saved = check_items([item], [{"id": "exact"}], actor=actor)
        self.assertEqual(saved[0]["actor_name"], "Reviewer")

    def test_case_package_long_untrusted_text_paginated(self):
        package = {
            "case": CASE,
            "version": "2",
            "exported_at": "2026-10-09",
            "interpretation": "Historical evidence is not current verification.",
            "missing_evidence": ["Unresolved request"],
            "flags": [],
            "runs": [],
        }
        for k in [
            "procedure_versions",
            "snapshots",
            "comparisons",
            "checks",
            "requests",
            "evidence",
            "links",
            "reassessments",
            "effort",
            "events",
        ]:
            package[k] = []
        package["checks"] = [
            {
                "items": [
                    {
                        "text": ("Preserve <script> & " + ("x" * 160) + "\n") * 90,
                        "state": "needs_follow_up",
                    }
                ]
            }
        ]
        pdf = build_case_report(package)
        reader = PdfReader(io.BytesIO(pdf))
        self.assertGreater(len(reader.pages), 2)
        text = "\n".join(p.extract_text() for p in reader.pages)
        self.assertIn("<script>", text)
        self.assertIn("Unresolved request", text)


if __name__ == "__main__":
    unittest.main()
