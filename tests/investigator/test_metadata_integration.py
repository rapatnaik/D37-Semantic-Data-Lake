# Integration tests for discovery, table profiling, and metadata assembly.

import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from PIL import Image

from agents.investigator.discovery import discover
from agents.investigator.context import ToolContext
from agents.investigator.contracts import ToolResult
from agents.investigator.tools.tables import profile_table
from agents.investigator.metadata import build_metadata
from agents.investigator.relationships import validate_candidate_key
from agents.investigator.tools.images import inspect_image

class MetadataIntegrationTests(unittest.TestCase):
    def test_discovery_to_table_profile_to_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            # Create a small synthetic CSV.
            csv_path = root / "patients.csv"
            csv_path.write_text(
                "patient_id,age,diagnosis\n"
                "P001,45,A\n"
                "P002,,B\n"
                "P003,60,A\n",
                encoding="utf-8"
            )

            original_bytes = csv_path.read_bytes()

            # 1. discover the file and its component.
            inventory = discover(root)

            self.assertEqual(len(inventory.sources), 1)
            self.assertEqual(len(inventory.components), 1)

            source = inventory.sources[0]
            component = inventory.components[0]

            self.assertEqual(source.relative_path, "patients.csv")
            self.assertEqual(source.format, "csv")
            self.assertEqual(component.kind, "table")
            self.assertIn(source.source_id, component.source_ids)

            # 2. creating the tool execution context
            context = ToolContext(
                dataset_root=root,
                output_dir=root / "test_outputs",
                component_id=component.component_id,
                result_id="r_patients_profile",
                seed=42
            )

            # Manasa's table profiler.
            result = profile_table(source, context)

            self.assertIsInstance(result, ToolResult)
            self.assertEqual(result.status, "complete")
            self.assertEqual(result.component_id, component.component_id)
            self.assertEqual(result.inputs, [source.source_id])

            # profiling measurements.
            measurements = result.measurements

            self.assertEqual(measurements["row_count"], 3)
            self.assertEqual(measurements["column_count"], 3)
            self.assertEqual(
                measurements["columns"]["age"]["null_count"], 1
            )
            self.assertEqual(
                measurements["columns"]["patient_id"]["distinct_count"], 3
            )
            self.assertTrue(
                measurements["columns"]["patient_id"]["candidate_key"]
            )
            self.assertEqual(result.coverage.mode, "full")
            self.assertEqual(result.coverage.examined, 3)
            # validate references against discovery.
            result.validate_references(inventory)

            # 3. assemble metadata using the real ToolResult.
            metadata = build_metadata(
                component.component_id,
                [result]
            )

            self.assertEqual(
                metadata["component_id"],
                component.component_id
            )
            self.assertEqual(metadata["result_count"], 1)
            self.assertEqual(
                metadata["source_ids"],
                [source.source_id]
            )

            # verify Manasa's measurements are preserved and unchanged
            saved_result = metadata["results"][0]
            
            self.assertEqual(
                saved_result["measurements"],
                result.measurements
            )
            self.assertEqual(
                saved_result["coverage"],
                result.coverage.to_dict()
            )

            # verify generated plot references are preserved.
            self.assertGreaterEqual(len(result.artifacts), 1)
            self.assertEqual(
                saved_result["artifacts"],
                [artifact.to_dict() for artifact in result.artifacts]
            )

            for artifact in result.artifacts:
                artifact_path = (
                    context.output_dir / artifact.relative_path
                )
                self.assertTrue(artifact_path.is_file())

            # 4. ensure JSON serialization works.
            serialized = json.dumps(metadata, allow_nan=False)
            restored = json.loads(serialized)

            self.assertEqual(restored, metadata)
            self.assertEqual(csv_path.read_bytes(), original_bytes)

        
    def test_full_profile_supports_candidate_key(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            # every patient has a unique, non-null ID
            (root / "patients.csv").write_text(
                "patient_id,age\n"
                "P001,40\n"
                "P002,50\n"
                "P003,60\n",
                encoding="utf-8"
            )

            inventory = discover(root)
            source = inventory.sources[0]
            component = inventory.components[0]

            context = ToolContext(
                dataset_root=root,
                output_dir=root / "outputs",
                component_id=component.component_id,
                result_id="r_unique_patients",
                seed=42
            )

            # analysis using Manasa's profiler.
            result = profile_table(source, context)

            self.assertEqual(result.status, "complete")
            self.assertEqual(result.coverage.mode, "full")
            result.validate_references(inventory)

            # checking for relationships
            relationship = validate_candidate_key(
                result, "patient_id"
            )

            self.assertEqual(
                relationship["status"], "supported"
            )
            self.assertEqual(
                relationship["evidence"]["result_id"],
                result.result_id
            )

            # confirm agreement from manasa's profiler
            self.assertTrue(
                result.measurements["columns"]
                ["patient_id"]["candidate_key"]
            )

    
    def test_full_profile_rejects_duplicate_key(self):
        # testing on a table where patient IDs aren't unique
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "patients.csv").write_text(
                "patient_id,age\n"
                "P001,40\n"
                "P002,50\n"
                "P002,60\n",
                encoding="utf-8"
            )
            inventory = discover(root)
            source = inventory.sources[0]
            component = inventory.components[0]

            context = ToolContext(
                dataset_root=root,
                output_dir=root / "outputs",
                component_id=component.component_id,
                result_id="r_duplicate_patients",
                seed=42
            )
            result = profile_table(source, context)

            self.assertEqual(result.status, "complete")

            result.validate_references(inventory)

            relationship = validate_candidate_key(
                result, "patient_id"
            )

            self.assertEqual(
                relationship["status"], "rejected"
            )
            self.assertFalse(
                result.measurements["columns"]
                ["patient_id"]["candidate_key"]
            )

    def test_sampled_profile_cannot_confirm_key(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            csv_path = root / "patients.csv"
            rows = ["patient_id,age"]
            rows.extend(
                f"P{i:04d},{20 + i % 50}"
                for i in range(1500)
            )
            csv_path.write_text(
                "\n".join(rows) + "\n",
                encoding="utf-8"
            )

            inventory = discover(root)
            source = inventory.sources[0]
            component = inventory.components[0]

            context = ToolContext(
                dataset_root=root,
                output_dir=root / "outputs",
                component_id=component.component_id,
                result_id="r_sampled_patients",
                seed=42
            )
            # force profile_table() to use its large-CSV sampling path
            with patch(
                "agents.investigator.tools.tables.MAX_SOURCE_BYTES",
                100
            ):
                result = profile_table(source, context)

            self.assertEqual(result.status, "complete")
            self.assertEqual(result.coverage.mode, "sample")
            self.assertEqual(result.coverage.examined, 1000)
            self.assertEqual(result.coverage.total, 1500)

            result.validate_references(inventory)
            # check that profiler left patient_id unconfirmed because it analyzed only a sample
            self.assertIsNone(
                result.measurements["columns"]
                ["patient_id"]["candidate_key"]
            )

            relationship = validate_candidate_key(
                result, "patient_id"
            )
            # uniqueness in sampled rows does not prove uniqueness across ALL rows
            self.assertEqual(
                relationship["status"],
                "insufficient_evidence"
            )
            # confirm that the relationship keeps original sampling info
            self.assertEqual(
                relationship["evidence"]["coverage"]["mode"],
                "sample"
            )

    # integration with Deepal's imaging analyses
    def test_image_profile_to_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)

            # creating a small synthetic grayscale image
            image_path = root / "scan.png"
            Image.new("L", (30, 20), color=100).save(image_path)
            original_bytes = image_path.read_bytes()

            # discovery
            inventory = discover(root)
            source = inventory.sources[0]
            component = inventory.components[0]
            self.assertEqual(source.format, "png")
            self.assertEqual(component.kind, "images")

            # Deepal's image analysis
            context = ToolContext(
                dataset_root=root,
                output_dir=root / "outputs",
                component_id=component.component_id,
                result_id="r_image_profile",
                seed=42
            )
            result = inspect_image(source, context)
            self.assertEqual(result.status, "complete")
            result.validate_references(inventory)

            # read the image-specific measurements.
            image_stats = result.measurements["images"][source.source_id]
            self.assertEqual(image_stats["width"], 30)
            self.assertEqual(image_stats["height"], 20)
            self.assertEqual(image_stats["channel_count"], 1)
            self.assertEqual(
                image_stats["intensity_by_channel"][0]["mean"],
                100.0
            )
            self.assertEqual(result.coverage.mode, "full")
            self.assertEqual(result.coverage.examined, 600)

            # building metadata
            metadata = build_metadata(
                component.component_id,
                [result]
            )
            saved = metadata["results"][0]

            self.assertEqual(
                saved["measurements"],
                result.measurements
            )
            self.assertEqual(
                saved["coverage"],
                result.coverage.to_dict()
            )
            self.assertEqual(
                saved["source_ids"] if "source_ids" in saved else saved["inputs"],
                [source.source_id]
            )

            # verify Deepal's plots
            self.assertEqual(len(result.artifacts), 2)

            self.assertEqual(
                saved["artifacts"],
                [a.to_dict() for a in result.artifacts]
            )

            for artifact in result.artifacts:
                self.assertTrue(
                    (context.output_dir / artifact.relative_path).is_file()
                )

            # verify JSON compatibility
            restored = json.loads(
                json.dumps(metadata, allow_nan=False)
            )

            self.assertEqual(restored, metadata)
            self.assertEqual(image_path.read_bytes(), original_bytes)

    # testing a mixed directory
    def test_mixed_table_and_image_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)

            # creating a table and an image in the same directory
            (root / "patients.csv").write_text(
                "patient_id,age\n"
                "P001,45\n"
                "P002,60\n",
                encoding="utf-8"
            )

            Image.new("L", (16, 12), color=80).save(root / "scan.png")
            inventory = discover(root)
            self.assertEqual(len(inventory.sources), 2)
            self.assertEqual(len(inventory.components), 2)

            metadata_by_kind = {}
            for component in inventory.components:
                source = next(
                    source for source in inventory.sources
                    if source.source_id in component.source_ids
                )

                # analysis per type
                context = ToolContext(
                    dataset_root=root,
                    output_dir=root / "outputs" / component.component_id,
                    component_id=component.component_id,
                    result_id=f"result_{component.component_id}",
                    seed=42
                )
                if component.kind == "table":
                    result = profile_table(source, context)
                elif component.kind == "images":
                    result = inspect_image(source, context)
                else:
                    self.fail(f"Unexpected component: {component.kind}")

                self.assertEqual(result.status, "complete")
                result.validate_references(inventory)
                
                # building metadata
                metadata = build_metadata(
                    component.component_id, [result]
                )
                metadata_by_kind[component.kind] = metadata

            # checking if both types were successfully handled
            self.assertEqual(
                set(metadata_by_kind),
                {"table", "images"}
            )
            table_result = metadata_by_kind["table"]["results"][0]
            image_result = metadata_by_kind["images"]["results"][0]

            # verify both have different measurement structures:
            # table
            self.assertEqual(
                table_result["measurements"]["row_count"], 2
            )
            # image
            image_source_id = metadata_by_kind["images"]["source_ids"][0]
            self.assertEqual(
                image_result["measurements"]["images"]
                [image_source_id]["width"],
                16
            )

            # metadata profiles should be different and separate
            self.assertNotEqual(
                metadata_by_kind["table"]["component_id"],
                metadata_by_kind["images"]["component_id"]
            )
            self.assertNotEqual(
                metadata_by_kind["table"]["source_ids"],
                metadata_by_kind["images"]["source_ids"]
            )




