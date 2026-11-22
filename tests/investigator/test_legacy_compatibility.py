import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents.metadata_agent import extract_metadata_csv, export_metadata
from agents import semantic_agent

class LegacyCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.root = Path(self.temp_dir.name)
        self.csv_path = self.root / "patients.csv"

        self.csv_path.write_text(
            "patient_id,age,group\n"
            "1,20,A\n"
            "2,,B\n"
            "3,40,A\n",
            encoding="utf-8"
        )

    def test_legacy_csv_metadata_structure(self):
        # ensures original metadata extractor produces expected CSV metadata fields / measures
        metadata = extract_metadata_csv(str(self.csv_path))
        #top-level statistics
        for field in ("dataset", "row_count", "column_count", "columns", "potential_keys"):
            self.assertIn(field, metadata)

        self.assertEqual(metadata["row_count"], 3)
        self.assertEqual(metadata["column_count"], 3)

        # per-column statistics
        age = metadata["columns"]["age"]

        self.assertEqual(age["null_count"], 1)
        self.assertEqual(age["distinct_count"], 2)
        self.assertIn("statistics", age)
        self.assertIn("sql_profile", age)

        # original candidate key behavior
        self.assertIn("patient_id", metadata["potential_keys"])

    def test_legacy_export_and_semantic_compatibility(self):
        # ensures metadata can still be exported and used by original semantic agent
        metadata = extract_metadata_csv(str(self.csv_path))

        # so original export JSON function still works
        output = self.root / "outputs" / "metadata.json"
        export_metadata(metadata, str(output))

        self.assertTrue(output.exists())

        restored = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(restored, metadata)

        # so semantic agent accepts profile
        prompt = semantic_agent.build_table_prompt(restored)

        self.assertIsInstance(prompt, str)
        self.assertIn("patient_id", prompt)
        self.assertIn("age", prompt)

    def test_legacy_batch_uses_existing_metadata_and_output_formats(self):
        metadata = extract_metadata_csv(str(self.csv_path))
        metadata_dir, output_dir = self.root / "metadata", self.root / "semantics"
        export_metadata(metadata, str(metadata_dir / "patients_metadata.json"))
        columns = {
            name: {"description": name, "semantic_type": "unknown", "unit": None,
                   "evidence": [], "needs_verification": []}
            for name in metadata["columns"]
        }
        with patch.object(semantic_agent, "request_completion", return_value=json.dumps(columns)) as request:
            semantic_agent.run_batch("fake-model", metadata_dir, output_dir)
        request.assert_called_once_with(semantic_agent.build_table_prompt(metadata), "fake-model")
        saved = json.loads((output_dir / "test_001_patients.json").read_text())
        self.assertEqual(saved, {"dataset": metadata["dataset"], "model": "fake-model", "columns": columns})
