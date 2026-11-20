"""Tests for conservative, dictionary-backed table normalization."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from agents.investigator.contracts import SourceRef, ToolResult
from agents.investigator.tools.cleaning import normalize_table


class CleaningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "patients.csv"
        self.original = pd.DataFrame({
            "patient_id": ["P1", "P2", "P3"],
            "age": [40, 50, 60],
            "cholesterol": [200, 0, 250],
        })
        self.original.to_csv(self.path, index=False)
        stat = self.path.stat()
        self.source = SourceRef(
            source_id="patients_source",
            relative_path="patients.csv",
            format="csv",
            size_bytes=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
        )
        self.context = SimpleNamespace(
            dataset_root=self.root,
            output_dir=self.root / "outputs",
            component_id="patients_component",
            result_id="cleaning_result",
            resolve_source=lambda source: self.root / source.relative_path,
        )

    def source_hash(self):
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def get_artifact(self, result, suffix):
        for artifact in result.artifacts:
            if artifact.relative_path.endswith(suffix):
                return self.context.output_dir / artifact.relative_path
        self.fail(f"Missing expected artifact: {suffix}")

    def make_dictionary(self, columns=None, source_id="patients_source"):
        document = {
            "source_id": source_id,
            "columns": columns if columns is not None else {
                "cholesterol": {"missing_values": [0]}
            },
        }
        path = self.root / "patients_dictionary.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def documented_rules(self, markers=None):
        return {
            "dictionary_relative_path": "patients_dictionary.json",
            "columns": {
                "cholesterol": {"missing_values": [0] if markers is None else markers}
            },
        }

    def test_no_rules_preserve_values(self):
        """No rules means no changes to values or the original file."""
        before = self.source_hash()
        result = normalize_table(self.source, self.context)
        self.assertEqual(result.status, "complete", result.limitations)
        self.assertEqual(result.measurements["total_changed_cells"], 0)
        normalized = pd.read_parquet(self.get_artifact(result, "_normalized.parquet"))
        pd.testing.assert_frame_equal(normalized, self.original, check_dtype=False)
        self.assertEqual(self.source_hash(), before)

    def test_documented_missing_marker(self):
        """An on-disk dictionary explicitly authorizes the zero marker."""
        self.make_dictionary()
        before = self.source_hash()
        result = normalize_table(self.source, self.context, rules=self.documented_rules())
        self.assertEqual(result.status, "complete", result.limitations)
        self.assertEqual(result.measurements["total_changed_cells"], 1)
        normalized = pd.read_parquet(self.get_artifact(result, "_normalized.parquet"))
        self.assertTrue(pd.isna(normalized.loc[1, "cholesterol"]))
        self.assertEqual(normalized.loc[0, "cholesterol"], 200)
        self.assertEqual(self.source_hash(), before)
        audit = json.loads(self.get_artifact(result, "_cleaning_log.json").read_text())
        self.assertEqual(audit["dictionary_relative_path"], "patients_dictionary.json")
        self.assertEqual(len(audit["dictionary_sha256"]), 64)

    def test_missing_evidence_skips_change(self):
        """Unverified evidence text alone cannot authorize a change."""
        rules = {"columns": {"cholesterol": {
            "missing_values": [0], "evidence": "I claim zero means missing"
        }}}
        result = normalize_table(self.source, self.context, rules=rules)
        self.assertEqual(result.status, "complete", result.limitations)
        self.assertEqual(result.measurements["total_changed_cells"], 0)
        self.assertEqual(result.measurements["rules_skipped"], 1)
        normalized = pd.read_parquet(self.get_artifact(result, "_normalized.parquet"))
        self.assertEqual(normalized.loc[1, "cholesterol"], 0)

    def test_audit_log_is_created(self):
        """Every successful run produces a JSON cleaning audit."""
        result = normalize_table(self.source, self.context)
        audit = json.loads(self.get_artifact(result, "_cleaning_log.json").read_text())
        self.assertEqual(audit["source_id"], "patients_source")
        self.assertEqual(audit["row_count"], 3)
        self.assertEqual(audit["total_changed_cells"], 0)
        self.assertEqual(audit["source_sha256_before"], audit["source_sha256_after"])

    def test_tool_result_round_trip(self):
        result = normalize_table(self.source, self.context)
        self.assertIsInstance(result, ToolResult)
        restored = ToolResult.from_json(result.to_json())
        self.assertEqual(restored.status, "complete")
        self.assertEqual(restored.coverage.mode, "full")
        self.assertEqual(restored.coverage.examined, 3)
        self.assertEqual(len(restored.artifacts), 2)

    def test_unsupported_format(self):
        unsupported_source = SourceRef(
            source_id="unknown_source", relative_path="patients.csv",
            format="unknown", size_bytes=self.source.size_bytes,
            mtime_ns=self.source.mtime_ns,
        )
        result = normalize_table(unsupported_source, self.context)
        self.assertEqual(result.status, "unsupported")
        self.assertTrue(result.limitations)
        self.assertEqual(result.artifacts, [])

    def test_dictionary_source_mismatch_skips(self):
        self.make_dictionary(source_id="someone_else")
        result = normalize_table(self.source, self.context, self.documented_rules())
        self.assertEqual(result.status, "complete", result.limitations)
        self.assertEqual(result.measurements["total_changed_cells"], 0)
        self.assertEqual(result.measurements["rules_skipped"], 1)

    def test_marker_not_in_dictionary_skips(self):
        self.make_dictionary(columns={"cholesterol": {"missing_values": [-99]}})
        result = normalize_table(self.source, self.context, self.documented_rules())
        self.assertEqual(result.measurements["total_changed_cells"], 0)
        self.assertEqual(result.measurements["rules_skipped"], 1)

    def test_dictionary_without_column_skips(self):
        self.make_dictionary(columns={"age": {"missing_values": [-99]}})
        result = normalize_table(self.source, self.context, self.documented_rules())
        self.assertEqual(result.measurements["total_changed_cells"], 0)
        self.assertEqual(result.measurements["rules_skipped"], 1)

    def test_missing_dictionary_file_skips(self):
        result = normalize_table(self.source, self.context, self.documented_rules())
        self.assertEqual(result.measurements["total_changed_cells"], 0)
        self.assertEqual(result.measurements["rules_skipped"], 1)

    def test_traversal_dictionary_path_skips(self):
        rules = self.documented_rules()
        rules["dictionary_relative_path"] = "../outside.json"
        result = normalize_table(self.source, self.context, rules)
        self.assertEqual(result.measurements["total_changed_cells"], 0)
        self.assertEqual(result.measurements["rules_skipped"], 1)

    def test_invalid_dictionary_json_skips(self):
        (self.root / "patients_dictionary.json").write_text("not JSON", encoding="utf-8")
        result = normalize_table(self.source, self.context, self.documented_rules())
        self.assertEqual(result.measurements["total_changed_cells"], 0)
        self.assertEqual(result.measurements["rules_skipped"], 1)

    def test_undocumented_zero_is_preserved(self):
        self.make_dictionary(columns={"cholesterol": {"missing_values": [-99]}})
        result = normalize_table(self.source, self.context)
        normalized = pd.read_parquet(self.get_artifact(result, "_normalized.parquet"))
        self.assertEqual(normalized.loc[1, "cholesterol"], 0)


if __name__ == "__main__":
    unittest.main()
