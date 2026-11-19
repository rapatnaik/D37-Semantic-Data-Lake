
"""Checks for metadata assembly."""

import json
import unittest
from agents.investigator.contracts import Coverage, ToolResult, ArtifactRef
from agents.investigator.metadata import build_metadata

class MetadataTests(unittest.TestCase):

    def setUp(self):
        self.coverage = Coverage(
            mode="full",
            unit="rows",
            examined=10,
            total=10,
            selection="all rows"
        )
        self.result = ToolResult(
            result_id="r_counts",
            component_id="c_patients",
            status="complete",
            inputs=["s_patients"],
            method="example_csv_counts",
            parameters={},
            coverage=self.coverage,
            measurements={
                "row_count": 10,
                "columns": {
                    "age": {"null_count": 2}
                }
            }
        )

    def test_basic_metadata_assembly(self):
        metadata = build_metadata(
            "c_patients",
            [self.result]
        )
        self.assertEqual(metadata["component_id"], "c_patients")
        self.assertEqual(metadata["result_count"], 1)
        self.assertEqual(metadata["source_ids"], ["s_patients"])
        self.assertEqual(
            metadata["results"][0]["measurements"]["row_count"],
            10
        )

    def test_multiple_results(self):
        second_result = ToolResult(
            result_id="r_summary",
            component_id="c_patients",
            status="complete",
            inputs=["s_patients"],
            method="numeric_summary",
            parameters={},
            coverage=self.coverage,
            measurements={"mean_age": 45}
        )
        metadata = build_metadata(
            "c_patients",
            [self.result, second_result]
        )
        self.assertEqual(metadata["result_count"], 2)
        self.assertEqual(metadata["source_ids"], ["s_patients"])
        self.assertEqual(len(metadata["results"]), 2)

    def test_mismatched_component(self):
        with self.assertRaises(ValueError):
            build_metadata("other_component", [self.result])

    def test_duplicate_result_ids(self):
        with self.assertRaises(ValueError):
            build_metadata(
                "c_patients",
                [self.result, self.result]
            )

    def test_empty_results(self):
        with self.assertRaises(ValueError):
            build_metadata("c_patients", [])

    
    def test_sampled_metadata_preserves_coverage(self):
        # to ensure semantic agent can distinguish between sample statistics and dataset statistics
        sampled_result = ToolResult(
            result_id="r_sample",
            component_id="c_patients",
            status="complete",
            inputs=["s_patients"],
            method="sample_profile",
            parameters={"sample_size": 100},
            coverage=Coverage(
                mode="sample",
                unit="rows",
                examined=100,
                total=1000,
                selection="random sample",
                seed=42
            ),
            measurements={"mean_age": 45.2}
        )

        metadata = build_metadata("c_patients", [sampled_result])
        coverage = metadata["results"][0]["coverage"]

        self.assertEqual(coverage["mode"], "sample")
        self.assertEqual(coverage["examined"], 100)
        self.assertEqual(coverage["total"], 1000)
        self.assertEqual(coverage["seed"], 42)

    
    def test_partial_metadata_preserves_limitations(self):
        # Metadata should preserve limitations of an incomplete analysis
        partial_result = ToolResult(
            result_id="r_partial",
            component_id="c_patients",
            status="partial",
            inputs=["s_patients"],
            method="numeric_profile",
            parameters={},
            coverage=Coverage(
                mode="sample",
                unit="rows",
                examined=50,
                total=1000,
                selection="first 50 rows"
            ),
            measurements={"row_count_sampled": 50},
            limitations=[
                "Full dataset could not be processed."
            ]
        )

        metadata = build_metadata("c_patients", [partial_result])
        result = metadata["results"][0]

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["limitations"], ["Full dataset could not be processed."])
        self.assertEqual(result["coverage"]["examined"], 50)

    
    def test_metadata_preserves_artifacts_and_parameters(self):
        # metadata must preserve analysis methods, parameters, and artifact references.
        result = ToolResult(
            result_id="r_plot",
            component_id="c_patients",
            status="complete",
            inputs=["s_patients"],
            method="age_distribution",
            parameters={
                "bins": 10,
                "code_reference": "tools/tables.py"
            },
            coverage=self.coverage,
            measurements={"age_min": 20, "age_max": 80},
            artifacts=[
                ArtifactRef(
                    artifact_id="a_age",
                    relative_path="artifacts/age.png",
                    media_type="image/png"
                )
            ]
        )

        metadata = build_metadata("c_patients", [result])
        saved_result = metadata["results"][0]

        self.assertEqual(saved_result["method"], "age_distribution")
        self.assertEqual(saved_result["parameters"]["bins"], 10)
        self.assertEqual(saved_result["parameters"]["code_reference"], "tools/tables.py")
        self.assertEqual(saved_result["artifacts"][0]["relative_path"], "artifacts/age.png")


    def test_metadata_json_round_trip(self):
        # ensure metadata is JSON-compatible to be used by downstream agents
        metadata = build_metadata(
            "c_patients",
            [self.result]
        )
        json_text = json.dumps(
            metadata,
            indent=2,
            allow_nan=False
        )
        restored = json.loads(json_text)
        self.assertEqual(restored, metadata)
        self.assertEqual(restored["schema_version"], "1.0")
        self.assertEqual(restored["result_count"], 1)
        self.assertEqual(
            restored["results"][0]["measurements"]["row_count"],
            10
        )


