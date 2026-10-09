import io, json, os, sys, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from investigation import investigate
from seed import ARTICLES, operations
from content import extract, chunks
from fastapi import HTTPException

CASE = {
    "id": "CASE-4",
    "title": "Binder synchronization has stalled",
    "description": "Source binder documents stopped updating in the destination binder.",
    "study_id": "CT-204",
    "site_id": "SITE-104",
}


def evidence(site="104"):
    return {
        "study": {"id": "CT-204"},
        "site": {"id": "SITE-" + site, "study_id": "CT-204"},
        "cases": [],
        **operations(site),
        "articles": [
            dict(
                a,
                article_id=a["id"],
                id=a["id"] + "#v1-s1",
                version=1,
                number=1,
                similarity=0.8,
            )
            for a in ARTICLES
        ],
    }


class PipelineTests(unittest.TestCase):
    def model(self, selection, data=None):
        response = io.BytesIO(
            json.dumps({"message": {"content": json.dumps(selection)}}).encode()
        )
        with patch.dict(os.environ, {"AI_MODE": "ollama"}), patch(
            "investigation.collect_evidence", return_value=(data or evidence(), [])
        ), patch("investigation.urllib.request.urlopen", return_value=response):
            return investigate("workspace", CASE)

    def test_model_cannot_replace_procedure(self):
        r = self.model({"status": "supported", "evidence_ids": ["KB-004#v1-s1"]})
        self.assertEqual(
            r["recommendation"]["recommended_next_step"],
            "KB-004#v1-s1: " + ARTICLES[3]["content"],
        )
        self.assertIn("No root cause", r["recommendation"]["hypothesis"])
        self.assertEqual(len(r["escalation_drafts"]), 1)

    def test_unavailable_citation_rejected(self):
        with self.assertRaises(ValueError):
            self.model({"status": "supported", "evidence_ids": ["invented"]})

    def test_unsupported_never_generates_draft(self):
        r = self.model(
            {"status": "insufficient_evidence", "evidence_ids": ["KB-004#v1-s1"]}
        )
        self.assertEqual(r["recommendation"]["evidence_ids"], [])
        self.assertEqual(r["escalation_drafts"], [])

    def test_supported_requires_citations(self):
        with self.assertRaises(ValueError):
            self.model({"status": "supported", "evidence_ids": []})

    def test_model_extra_instructions_rejected(self):
        with self.assertRaises(ValueError):
            self.model(
                {
                    "status": "supported",
                    "evidence_ids": ["KB-004#v1-s1"],
                    "summary": "Network caused failure",
                }
            )

    def test_text_mode_abstains_on_cafeteria(self):
        with patch.dict(os.environ, {"AI_MODE": "procedure"}), patch(
            "investigation.collect_evidence", return_value=(evidence(), [])
        ):
            r = investigate(
                "workspace",
                {
                    **CASE,
                    "title": "Office cafeteria lunch menu",
                    "description": "What meals will the office cafeteria serve tomorrow?",
                },
            )
        self.assertEqual(r["recommendation"]["status"], "insufficient_evidence")

    def test_text_upload_and_chunk_coverage(self):
        s = "Document processing instructions and escalation conditions. " * 200
        self.assertEqual(extract("procedure.md", s.encode())["content"], s.strip())
        self.assertGreater(len(chunks(s)), 1)
        self.assertTrue(all(len(p) <= 1400 for p in chunks(s)))

    def test_text_pdf_extracts_in_bounded_subprocess(self):
        from pypdf import PdfWriter
        from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject

        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): writer._add_object(font)}
                )
            }
        )
        stream = DecodedStreamObject()
        stream.set_data(
            b"BT /F1 12 Tf 40 700 Td (Verify the synthetic document processing status and upload receipt.) Tj ET"
        )
        page[NameObject("/Contents")] = writer._add_object(stream)
        data = io.BytesIO()
        writer.write(data)
        result = extract("Synthetic procedure.pdf", data.getvalue())
        self.assertIn("synthetic document processing status", result["content"])

    def test_invalid_uploads_are_rejected(self):
        for name, data in [
            ("a.exe", b"abc" * 30),
            ("a.txt", b"abc"),
            ("a.txt", b"\xff" * 40),
            ("a.pdf", b"not a pdf"),
            ("a.txt", b"x" * (2 * 1024 * 1024 + 1)),
        ]:
            with self.subTest(name=name):
                with self.assertRaises(HTTPException):
                    extract(name, data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
