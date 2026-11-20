
"""
Tests for conservative table normalization.

Checks original data preservation, documented cleaning,
skipped rules, Parquet outputs, and JSON audit logs.
"""

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
            "cholesterol": [200, 0, 250]
        })

        self.original.to_csv(
            self.path,
            index=False
        )

        stat = self.path.stat()

        self.source = SourceRef(
            source_id="patients_source",
            relative_path="patients.csv",
            format="csv",
            size_bytes=stat.st_size,
            mtime_ns=stat.st_mtime_ns
        )

        self.context = SimpleNamespace(
            dataset_root=self.root,
            output_dir=self.root / "outputs",
            component_id="patients_component",
            result_id="cleaning_result",
            resolve_source=lambda source: (
                self.root / source.relative_path
            )
        )

    def source_hash(self):
        """Hash the original source file."""

        return hashlib.sha256(
            self.path.read_bytes()
        ).hexdigest()

    def get_artifact(self, result, suffix):
        """Get a generated file using its ArtifactRef."""

        for artifact in result.artifacts:
            if artifact.relative_path.endswith(suffix):
                return (
                    self.context.output_dir
                    / artifact.relative_path
                )

        self.fail(
            f"Missing expected artifact: {suffix}"
        )

    # ---------------------------------------------------------
    # 1. No rules should preserve values
    # ---------------------------------------------------------

    def test_no_rules_preserve_values(self):
        """No dictionary rules means no value changes."""

        before = self.source_hash()

        result = normalize_table(
            self.source,
            self.context
        )

        self.assertEqual(
            result.status,
            "complete"
        )

        self.assertEqual(
            result.measurements["total_changed_cells"],
            0
        )

        output = self.get_artifact(
            result,
            "_normalized.parquet"
        )

        normalized = pd.read_parquet(output)

        pd.testing.assert_frame_equal(
            normalized,
            self.original,
            check_dtype=False
        )

        self.assertEqual(
            self.source_hash(),
            before
        )

    # ---------------------------------------------------------
    # 2. Documented missing values can be replaced
    # ---------------------------------------------------------

    def test_documented_missing_marker(self):
        """Explicit evidence allows documented replacement."""

        rules = {
            "columns": {
                "cholesterol": {
                    "missing_values": [0],
                    "evidence": (
                        "Synthetic test dictionary: "
                        "0 represents a missing measurement."
                    )
                }
            }
        }

        result = normalize_table(
            self.source,
            self.context,
            rules=rules
        )

        self.assertEqual(
            result.status,
            "complete"
        )

        self.assertEqual(
            result.measurements["total_changed_cells"],
            1
        )

        output = self.get_artifact(
            result,
            "_normalized.parquet"
        )

        normalized = pd.read_parquet(output)

        self.assertTrue(
            pd.isna(
                normalized.loc[1, "cholesterol"]
            )
        )

        self.assertEqual(
            normalized.loc[0, "cholesterol"],
            200
        )

        # Confirm original CSV still has zero.
        original = pd.read_csv(self.path)

        self.assertEqual(
            original.loc[1, "cholesterol"],
            0
        )

    # ---------------------------------------------------------
    # 3. Rules without evidence must be skipped
    # ---------------------------------------------------------

    def test_missing_evidence_skips_change(self):
        """Cleaning without evidence should be skipped."""

        rules = {
            "columns": {
                "cholesterol": {
                    "missing_values": [0]
                }
            }
        }

        result = normalize_table(
            self.source,
            self.context,
            rules=rules
        )

        self.assertEqual(
            result.status,
            "complete"
        )

        self.assertEqual(
            result.measurements["total_changed_cells"],
            0
        )

        self.assertEqual(
            result.measurements["rules_skipped"],
            1
        )

        output = self.get_artifact(
            result,
            "_normalized.parquet"
        )

        normalized = pd.read_parquet(output)

        self.assertEqual(
            normalized.loc[1, "cholesterol"],
            0
        )

    # ---------------------------------------------------------
    # 4. JSON audit log is generated
    # ---------------------------------------------------------

    def test_audit_log_is_created(self):
        """Every run should create a JSON cleaning audit."""

        result = normalize_table(
            self.source,
            self.context
        )

        log_path = self.get_artifact(
            result,
            "_cleaning_log.json"
        )

        self.assertTrue(
            log_path.is_file()
        )

        audit = json.loads(
            log_path.read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(
            audit["source_id"],
            "patients_source"
        )

        self.assertEqual(
            audit["row_count"],
            3
        )

        self.assertEqual(
            audit["total_changed_cells"],
            0
        )

        self.assertEqual(
            audit["source_sha256_before"],
            audit["source_sha256_after"]
        )

    # ---------------------------------------------------------
    # 5. ToolResult contract round trip
    # ---------------------------------------------------------

    def test_tool_result_round_trip(self):
        """Cleaning results should satisfy the team's contract."""

        result = normalize_table(
            self.source,
            self.context
        )

        self.assertIsInstance(
            result,
            ToolResult
        )

        restored = ToolResult.from_json(
            result.to_json()
        )

        self.assertEqual(
            restored.status,
            "complete"
        )

        self.assertEqual(
            restored.coverage.mode,
            "full"
        )

        self.assertEqual(
            restored.coverage.examined,
            3
        )

        self.assertEqual(
            len(restored.artifacts),
            2
        )

    # ---------------------------------------------------------
    # 6. Unsupported format
    # ---------------------------------------------------------

    def test_unsupported_format(self):
        """Unsupported formats should be reported safely."""

        unsupported_source = SourceRef(
            source_id="unknown_source",
            relative_path="patients.csv",
            format="unknown",
            size_bytes=self.source.size_bytes,
            mtime_ns=self.source.mtime_ns
        )

        result = normalize_table(
            unsupported_source,
            self.context
        )

        self.assertEqual(
            result.status,
            "unsupported"
        )

        self.assertTrue(
            result.limitations
        )

        self.assertEqual(
            result.artifacts,
            []
        )


if __name__ == "__main__":
    unittest.main()
