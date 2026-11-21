"""Tests for read-only, bounded document extraction."""
import tempfile
import unittest
from pathlib import Path

from agents.investigator.context import ToolContext, ToolLimits
from agents.investigator.contracts import ToolResult
from agents.investigator.discovery import discover
from agents.investigator.tools.documents import extract_document


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "data"
        self.root.mkdir()
        self.out = Path(self.tmp.name) / "artifacts"

    def profile(self, filename, limits=None):
        inventory = discover(self.root)
        source = next(s for s in inventory.sources if s.relative_path == filename)
        component = next(c for c in inventory.components if source.source_id in c.source_ids)
        context = ToolContext(self.root, self.out, component.component_id, "r1", limits=limits or ToolLimits())
        result = extract_document(source, context)
        result.validate_references(inventory)
        self.assertEqual(ToolResult.from_json(result.to_json()), result)
        return result

    def test_txt_and_markdown_preserve_source(self):
        for name, content in [("notes.txt", "Hello world\nsecond line"), ("README.md", "# Study\nA note")]:
            path = self.root / name
            path.write_text(content, encoding="utf-8")
            original = path.read_bytes()
            result = self.profile(name)
            self.assertEqual(result.status, "complete")
            self.assertGreaterEqual(result.measurements["documents"][result.inputs[0]]["word_count"], 3)
            self.assertEqual((self.out / result.artifacts[0].relative_path).read_text(), content)
            self.assertEqual(path.read_bytes(), original)

    def test_empty_document_flagged(self):
        (self.root / "empty.txt").write_text("")
        result = self.profile("empty.txt")
        self.assertEqual(result.status, "partial")
        self.assertTrue(result.limitations)

    def test_utf8_failure(self):
        (self.root / "broken.txt").write_bytes(b"Valid prefix\n\xff")
        # Discovery correctly refuses to classify this as a text document.
        inventory = discover(self.root)
        source = inventory.sources[0]
        component = inventory.components[0]
        result = extract_document(source, ToolContext(self.root, self.out, component.component_id, "bad"))
        self.assertEqual(result.status, "unsupported")

    def test_bounded_text(self):
        (self.root / "large.txt").write_text("abcdef\n" * 100)
        result = self.profile("large.txt", ToolLimits(max_text_chars=25))
        self.assertEqual(result.status, "partial")
        self.assertLessEqual(result.measurements["documents"][result.inputs[0]]["character_count"], 26)

    def test_pdf_page_references(self):
        from reportlab.pdfgen import canvas
        path = self.root / "paper.pdf"
        c = canvas.Canvas(str(path))
        c.drawString(80, 700, "Patient report")
        c.showPage()
        c.drawString(80, 700, "Second page")
        c.save()
        result = self.profile("paper.pdf")
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.coverage.total, 2)
        self.assertIn("page 1", str(result.measurements))

    def test_docx_paragraphs_and_tables(self):
        from docx import Document
        doc = Document()
        doc.add_heading("Study", level=1)
        doc.add_paragraph("Participant details")
        doc.add_table(rows=1, cols=2).rows[0].cells[0].text = "Age"
        doc.save(self.root / "study.docx")
        result = self.profile("study.docx")
        self.assertEqual(result.status, "complete")
        self.assertIn("Age", (self.out / result.artifacts[0].relative_path).read_text())


if __name__ == "__main__":
    unittest.main()
