# End-to-end integration of discovery, EDA tools, and metadata assembly.

import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image

from agents.investigator.config import (
    Config,
    ExecutionSettings,
    ModelSettings,
)
from agents.investigator.contracts import ToolResult
from agents.investigator.scheduler import (
    start_run,
    Stages,
)


class PipelineIntegrationTests(unittest.TestCase):
    def test_mixed_directory_through_scheduler(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "data"
            root.mkdir()

            # synthetic table
            csv_path = root / "patients.csv"
            csv_path.write_text(
                "patient_id,age\n"
                "P001,40\n"
                "P002,50\n"
                "P003,60\n",
                encoding="utf-8"
            )

            # synthetic image
            image_path = root / "scan.png"
            Image.new("L", (20, 15), color=80).save(image_path)

            # synthetic document
            readme_path = root / "README.md"
            readme_path.write_text(
                "# Patient study\n",
                encoding="utf-8"
            )

            original = {
                path.name: path.read_bytes()
                for path in (csv_path, image_path, readme_path)
            }

            # running Victor's actual scheduler
            config = Config(
                model=ModelSettings(enabled=False),
                execution=ExecutionSettings(
                    backend="process",
                    tool_isolation="process"
                )
            )

            # Exercise the fallback report alongside the tool and metadata stages.
            stages = Stages(
                semantics=None,
                report=None,
                notebook=None
            )

            state, status = start_run(
                root,
                config,
                stages=stages
            )

            self.assertEqual(status, "completed")

            # discovery inventory
            inventory = state.load_inventory()
            self.assertEqual(len(inventory.sources), 3)
            self.assertEqual(len(inventory.components), 3)

            sources = {
                s.relative_path: s
                for s in inventory.sources
            }

            components = {c.component_id: c for c in inventory.components}

            self.assertEqual(sources["patients.csv"].format, "csv")
            self.assertEqual(sources["scan.png"].format, "png")
            self.assertEqual(sources["README.md"].format, "md")

            # read each tool result and metadata output
            results_by_kind = {}
            metadata_by_kind = {}

            for job in state.checkpoint["jobs"].values():
                if job["kind"] == "tool":
                    result = ToolResult.from_json(
                        state.read_relative(
                            job["outputs"]["result"]
                        )
                    )

                    component = components[job["component_id"]]
                    results_by_kind[component.kind] = result

                elif job["kind"] == "metadata":
                    metadata = json.loads(
                        state.read_relative(
                            job["outputs"]["metadata"]
                        )
                    )

                    component = components[job["component_id"]]
                    metadata_by_kind[component.kind] = metadata

            # running all EDA tools
            self.assertEqual(
                results_by_kind["table"].status,
                "complete"
            )
            self.assertEqual(
                results_by_kind["images"].status,
                "complete"
            )

            self.assertEqual(
                results_by_kind["documents"].status,
                "complete"
            )

            # Metadata must be saved for each component.
            self.assertEqual(
                set(metadata_by_kind),
                {"table", "images", "documents"}
            )

            # verifying table metadata
            table_metadata = metadata_by_kind["table"]
            self.assertEqual(
                table_metadata["results"][0]
                ["measurements"]["row_count"],
                3
            )

            # verifying image metadata
            image_metadata = metadata_by_kind["images"]
            image_source_id = image_metadata["source_ids"][0]

            self.assertEqual(
                image_metadata["results"][0]
                ["measurements"]["images"]
                [image_source_id]["width"],
                20
            )

            # verifying document metadata
            document_metadata = metadata_by_kind["documents"]
            document_result = document_metadata["results"][0]
            document_source_id = document_metadata["source_ids"][0]
            self.assertEqual(
                document_result["status"],
                "complete"
            )
            self.assertEqual(
                document_result["measurements"]["documents"][document_source_id]["word_count"],
                2
            )

            # check whether fallback report was generated
            report = (
                state.run_dir / "reports"
                / "revision-001" / "report.md"
            )
            self.assertTrue(report.is_file())

            for path in (csv_path, image_path, readme_path):
                self.assertEqual(
                    path.read_bytes(),
                    original[path.name]
                )
