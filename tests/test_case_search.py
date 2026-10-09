"""Case search query regressions; no database writes or model calls."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
import main


class CaseSearchTests(unittest.TestCase):
    def search(self, term, view="all", offset=0):
        actor = {"workspace_id": "workspace-A", "user_id": "user-A"}
        with patch.object(main, "one", return_value={"n": 1}) as count, patch.object(
            main, "query", return_value=[{"id": "CASE-1", "review_status": "pending"}]
        ) as rows:
            result = main.cases(status="open", q=term, priority="high", offset=offset, view=view, a=actor)
        return result, count.call_args.args, rows.call_args.args

    def test_numeric_aliases_use_exact_id_and_keep_workspace_and_priority(self):
        for term in ("1", "case 1", "CASE-1", " Case 001 "):
            with self.subTest(term=term):
                result, count, rows = self.search(term)
                self.assertIn("c.id=%s", count[0])
                self.assertNotIn("ILIKE", count[0])
                self.assertEqual(count[1], ("workspace-A", "open", "CASE-1", "high", "high"))
                self.assertEqual(rows[1], (*count[1], 0))
                self.assertEqual(result["items"][0]["review_status"], "pending")

    def test_text_search_remains_parameterized(self):
        for term in ("certificate", "CT-204", "SITE-104", "CASE-ab12", "case missing", "' OR 1=1 --"):
            with self.subTest(term=term):
                _, count, _ = self.search(term)
                self.assertIn("ILIKE %s", count[0])
                self.assertEqual(count[1][2], "%" + term + "%")
                self.assertNotIn(term, count[0])

    def test_review_status_is_latest_and_workspace_scoped_with_pagination(self):
        _, count, rows = self.search("1", view="mine", offset=25)
        self.assertIn("c.owner_id=%s", count[0])
        self.assertEqual(count[1][-1], "user-A")
        self.assertIn("r.workspace_id=c.workspace_id AND r.case_id=c.id", rows[0])
        self.assertIn("ORDER BY r.created_at DESC,r.id DESC LIMIT 1", rows[0])
        self.assertIn("COALESCE(r.decision,'pending')", rows[0])
        self.assertEqual(rows[1][-1], 25)


if __name__ == "__main__":
    unittest.main()
