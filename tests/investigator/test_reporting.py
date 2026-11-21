"""Saved-result reporting and generated notebook tests."""
import ast
import json
import tempfile
import unittest
from pathlib import Path

from agents.investigator.contracts import Coverage, ToolResult
from agents.investigator.discovery import discover
from agents.investigator.reporting import render_report, render_notebook


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        data = root / "dataset"
        data.mkdir()
        (data / "study.txt").write_text("hello")
        inventory = discover(data)
        source = inventory.sources[0]
        component = inventory.components[0]
        self.run = root / "run-001"
        self.run.mkdir()
        (self.run / "inventory.json").write_text(inventory.to_json())
        result = ToolResult("r1", component.component_id, "complete", [source.source_id],
                            "test", {}, Coverage("full", "files", 1, 1, "all"),
                            {"documents": {source.source_id: {"word_count": 1}}})
        result.validate_references(inventory)
        path = self.run / "results" / "tool" / "v001.json"
        path.parent.mkdir(parents=True)
        path.write_text(result.to_json())
        (self.run / "checkpoint.json").write_text(json.dumps({"jobs": {"tool": {
            "kind": "tool", "component_id": component.component_id,
            "outputs": {"result": "results/tool/v001.json"}}}}))

    def test_report_contains_evidence(self):
        report = render_report(self.run)
        self.assertIn("study.txt", report)
        self.assertIn("word_count", report)
        self.assertIn("full: 1/1 files", report)
        self.assertIn("Reproducibility", report)

    def test_notebook_syntax_and_no_cloud_or_code_execution(self):
        source = render_notebook(self.run)
        ast.parse(source)
        self.assertIn("marimo.App", source)
        self.assertIn("word_count", source)
        self.assertNotIn("exec(", source)
        self.assertNotIn("NRP_KEY", source)

    def test_missing_results_are_explicit(self):
        (self.run / "checkpoint.json").unlink()
        self.assertIn("No validated tool result", render_report(self.run))


if __name__ == "__main__":
    unittest.main()
