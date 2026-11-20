
"""
Tests for tabular EDA in the D37 Investigator Agent.

Covers file reading, missingness, numeric statistics,
duplicates, candidate keys, sampling, contracts, and plots.
"""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from agents.investigator.contracts import SourceRef, ToolResult

from agents.investigator.tools.tables import (
    read_table,
    calculate_table_statistics,
    sample_delimited_table,
    profile_table,
    plot_table_profile
)


class TableTests(unittest.TestCase):

    # ---------------------------------------------------------
    # 1. CSV reading
    # ---------------------------------------------------------

    def test_csv_reading(self):
        """CSV files should load correctly."""

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "patients.csv"

            path.write_text(
                "age,cholesterol\n"
                "45,200\n"
                "50,250\n",
                encoding="utf-8"
            )

            df = read_table(path)

            self.assertEqual(len(df), 2)
            self.assertEqual(len(df.columns), 2)
            self.assertEqual(df["cholesterol"].mean(), 225)

    # ---------------------------------------------------------
    # 2. Missing values
    # ---------------------------------------------------------

    def test_missing_values(self):
        """Missing values should be counted correctly."""

        df = pd.DataFrame({
            "age": [45, None, 60, 55],
            "cholesterol": [200, 250, None, 300]
        })

        result = calculate_table_statistics(df)

        self.assertEqual(
            result["columns"]["age"]["null_count"],
            1
        )

        self.assertEqual(
            result["columns"]["age"]["null_percentage"],
            25.0
        )

        self.assertEqual(
            result["columns"]["cholesterol"]["null_count"],
            1
        )

    # ---------------------------------------------------------
    # 3. Numerical statistics
    # ---------------------------------------------------------

    def test_numerical_statistics(self):
        """Numeric calculations should be accurate."""

        df = pd.DataFrame({
            "age": [40, 50, 60],
            "cholesterol": [200, 250, 300]
        })

        result = calculate_table_statistics(df)

        self.assertEqual(
            result["columns"]["age"]["mean"],
            50.0
        )

        self.assertEqual(
            result["columns"]["cholesterol"]["median"],
            250.0
        )

        self.assertEqual(
            result["columns"]["cholesterol"]["max"],
            300.0
        )

    # ---------------------------------------------------------
    # 4. Duplicate rows
    # ---------------------------------------------------------

    def test_duplicate_rows(self):
        """Repeated rows should be detected."""

        df = pd.DataFrame({
            "age": [40, 40, 60],
            "cholesterol": [200, 200, 300]
        })

        result = calculate_table_statistics(df)

        self.assertEqual(
            result["duplicate_row_count"],
            1
        )

    # ---------------------------------------------------------
    # 5. Candidate keys
    # ---------------------------------------------------------

    def test_candidate_keys(self):
        """Unique and complete columns are candidate keys."""

        df = pd.DataFrame({
            "patient_id": ["P1", "P2", "P3"],
            "age": [40, 40, 60]
        })

        result = calculate_table_statistics(df)

        self.assertTrue(
            result["columns"]["patient_id"]["candidate_key"]
        )

        self.assertFalse(
            result["columns"]["age"]["candidate_key"]
        )

    # ---------------------------------------------------------
    # 6. Preserve zeros
    # ---------------------------------------------------------

    def test_zeros_are_preserved(self):
        """Zeros should not automatically become missing."""

        df = pd.DataFrame({
            "cholesterol": [0, 200, 250]
        })

        result = calculate_table_statistics(df)

        self.assertEqual(
            result["columns"]["cholesterol"]["min"],
            0.0
        )

        self.assertEqual(
            result["columns"]["cholesterol"]["null_count"],
            0
        )

    # ---------------------------------------------------------
    # 7. Empty data
    # ---------------------------------------------------------

    def test_empty_dataframe(self):
        """Empty tables should not cause division errors."""

        df = pd.DataFrame({
            "age": pd.Series(dtype="float64")
        })

        result = calculate_table_statistics(df)

        self.assertEqual(
            result["row_count"],
            0
        )

        self.assertEqual(
            result["columns"]["age"]["null_percentage"],
            0.0
        )

    # ---------------------------------------------------------
    # 8. Unsupported format
    # ---------------------------------------------------------

    def test_unsupported_format(self):
        """Unsupported extensions should raise an error."""

        with self.assertRaises(ValueError):
            read_table("patients.xyz")

    # ---------------------------------------------------------
    # 9. ToolResult integration
    # ---------------------------------------------------------

    def test_profile_table_returns_tool_result(self):
        """Profiler must return the team's ToolResult."""

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "patients.csv"

            path.write_text(
                "patient_id,age,cholesterol\n"
                "P1,40,200\n"
                "P2,,250\n"
                "P3,60,0\n",
                encoding="utf-8"
            )

            stat = path.stat()

            source = SourceRef(
                source_id="source_patients",
                relative_path="patients.csv",
                format="csv",
                size_bytes=stat.st_size,
                mtime_ns=stat.st_mtime_ns
            )

            context = SimpleNamespace(
                dataset_root=root,
                output_dir=root / "outputs",
                component_id="component_patients",
                result_id="result_patients",
                seed=42,
                limits={},
                resolve_source=lambda source: (
                    root / source.relative_path
                )
            )

            result = profile_table(source, context)

            self.assertIsInstance(
                result,
                ToolResult
            )

            self.assertEqual(
                result.status,
                "complete"
            )

            self.assertEqual(
                result.coverage.mode,
                "full"
            )

            self.assertEqual(
                result.coverage.examined,
                3
            )

            self.assertEqual(
                result.measurements["row_count"],
                3
            )

            self.assertEqual(
                result.measurements["columns"]["age"]["null_count"],
                1
            )

            self.assertEqual(
                result.measurements["columns"]["cholesterol"]["min"],
                0.0
            )

            restored = ToolResult.from_json(
                result.to_json()
            )

            self.assertEqual(
                restored.measurements,
                result.measurements
            )

    # ---------------------------------------------------------
    # 10. Reproducible sampling
    # ---------------------------------------------------------

    def test_sampling_is_reproducible(self):
        """Same seed should select the same rows."""

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "large.csv"

            df = pd.DataFrame({
                "id": range(500),
                "value": range(500)
            })

            df.to_csv(
                path,
                index=False
            )

            sample1, total1 = sample_delimited_table(
                path,
                sample_size=30,
                seed=42
            )

            sample2, total2 = sample_delimited_table(
                path,
                sample_size=30,
                seed=42
            )

            self.assertEqual(total1, 500)
            self.assertEqual(total2, 500)
            self.assertEqual(len(sample1), 30)

            pd.testing.assert_frame_equal(
                sample1,
                sample2
            )

    # ---------------------------------------------------------
    # 11. Sampling small tables
    # ---------------------------------------------------------

    def test_sampling_preserves_full_small_table(self):
        """A small table should retain every row."""

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "small.csv"

            original = pd.DataFrame({
                "age": [40, 50, 60],
                "cholesterol": [200, 250, 300]
            })

            original.to_csv(
                path,
                index=False
            )

            sample, total = sample_delimited_table(
                path,
                sample_size=100,
                seed=42
            )

            self.assertEqual(
                total,
                3
            )

            pd.testing.assert_frame_equal(
                sample,
                original
            )

    # ---------------------------------------------------------
    # 12. Sampled ToolResult coverage
    # ---------------------------------------------------------

    def test_profile_table_sampled_coverage(self):
        """Large CSV profiling must report sampled coverage."""

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "large.csv"

            original = pd.DataFrame({
                "patient_id": range(1500),
                "age": [
                    30 + i % 50
                    for i in range(1500)
                ],
                "cholesterol": [
                    150 + i % 100
                    for i in range(1500)
                ]
            })

            original.to_csv(
                path,
                index=False
            )

            stat = path.stat()

            source = SourceRef(
                source_id="source_large",
                relative_path="large.csv",
                format="csv",
                size_bytes=stat.st_size,
                mtime_ns=stat.st_mtime_ns
            )

            context = SimpleNamespace(
                dataset_root=root,
                output_dir=root / "outputs",
                component_id="component_large",
                result_id="result_large",
                seed=42,
                limits={},
                resolve_source=lambda source: (
                    root / source.relative_path
                )
            )

            # Force the sample path without generating
            # an actual 25 MB test fixture.
            with patch(
                "agents.investigator.tools.tables.MAX_SOURCE_BYTES",
                100
            ):
                result = profile_table(
                    source,
                    context
                )

            self.assertEqual(
                result.status,
                "complete"
            )

            self.assertEqual(
                result.coverage.mode,
                "sample"
            )

            self.assertEqual(
                result.coverage.examined,
                1000
            )

            self.assertEqual(
                result.coverage.total,
                1500
            )

            self.assertEqual(
                result.coverage.seed,
                42
            )

            self.assertEqual(
                result.measurements["profile_scope"],
                "sample"
            )

            self.assertEqual(
                result.measurements["total_source_rows"],
                1500
            )

            self.assertIsNone(
                result.measurements["columns"]["patient_id"]["candidate_key"]
            )

            restored = ToolResult.from_json(
                result.to_json()
            )

            self.assertEqual(
                restored.coverage.mode,
                "sample"
            )

            self.assertEqual(
                restored.coverage.total,
                1500
            )

    # ---------------------------------------------------------
    # 13. PNG creation
    # ---------------------------------------------------------

    def test_plot_table_profile_creates_pngs(self):
        """Plotting should create valid PNG files."""

        with tempfile.TemporaryDirectory() as temp:
            df = pd.DataFrame({
                "age": [40, 50, None, 60],
                "cholesterol": [200, 220, 250, 300],
                "diagnosis": ["A", "B", "A", "B"]
            })

            paths = plot_table_profile(
                df,
                Path(temp)
            )

            self.assertEqual(
                len(paths),
                2
            )

            for path in paths:
                self.assertTrue(
                    path.exists()
                )

                self.assertEqual(
                    path.suffix,
                    ".png"
                )

                # PNG magic bytes.
                self.assertEqual(
                    path.read_bytes()[:8],
                    b"\x89PNG\r\n\x1a\n"
                )

    # ---------------------------------------------------------
    # 14. Plotting must not change data
    # ---------------------------------------------------------

    def test_plotting_preserves_original_dataframe(self):
        """Plot generation must preserve input values."""

        with tempfile.TemporaryDirectory() as temp:
            df = pd.DataFrame({
                "age": [40, None, 60],
                "cholesterol": [0, 250, 300]
            })

            original = df.copy(deep=True)

            plot_table_profile(
                df,
                Path(temp)
            )

            pd.testing.assert_frame_equal(
                df,
                original
            )


if __name__ == "__main__":
    unittest.main()
