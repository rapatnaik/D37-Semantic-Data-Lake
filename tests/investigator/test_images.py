"""Self-contained checks for D37 image EDA, using synthetic images only."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from agents.investigator import discover
from agents.investigator.contracts import ComponentRef, Inventory, ToolResult
from agents.investigator.tools.images import inspect_image, profile_image_collection


class DemoContext:
    """Temporary stand-in until Victor implements the production ToolContext."""

    def __init__(self, root: Path, output: Path, component_id: str,
                 result_id: str = "test_result", limits: dict | None = None):
        self.dataset_root = root
        self.output_dir = output
        self.component_id = component_id
        self.result_id = result_id
        self.seed = 0
        self.limits = limits or {}

    def resolve_source(self, source):
        path = (self.dataset_root / source.relative_path).resolve(strict=True)
        if not path.is_relative_to(self.dataset_root.resolve()):
            raise ValueError("Out-of-root source")
        return path


class ImageEDATests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "data"
        self.out = Path(self.tmp.name) / "output"
        self.root.mkdir()

    def _single(self, name, limits=None):
        inventory = discover(self.root)
        source = next(s for s in inventory.sources if s.relative_path == name)
        component = next(c for c in inventory.components if source.source_id in c.source_ids)
        return inventory, source, DemoContext(self.root, self.out, component.component_id, limits=limits)

    def test_png_statistics_preview_and_preserved_source(self):
        values = np.full((20, 30, 3), 12, dtype=np.uint8)
        values[0, 0] = [0, 100, 200]
        path = self.root / "rgb.png"
        Image.fromarray(values).save(path)
        before = path.read_bytes()
        inventory, source, context = self._single("rgb.png")
        result = inspect_image(source, context)
        result.validate_references(inventory)
        self.assertEqual(ToolResult.from_json(result.to_json()), result)
        self.assertEqual(result.status, "complete")
        stats = result.measurements["images"][source.source_id]
        self.assertEqual((stats["width"], stats["height"], stats["channel_count"]), (30, 20, 3))
        self.assertEqual(stats["intensity_by_channel"][0]["minimum"], 0)
        self.assertEqual(result.coverage.mode, "full")
        self.assertEqual(len(result.artifacts), 2)
        self.assertTrue(all((self.out / a.relative_path).exists() for a in result.artifacts))
        self.assertEqual(before, path.read_bytes())

    def test_jpeg_and_deterministic_pixel_sampling(self):
        Image.fromarray(np.full((150, 200, 3), 25, dtype=np.uint8)).save(self.root / "rgb.jpg")
        inventory, source, context = self._single("rgb.jpg", {"max_sample_pixels": 80})
        result = inspect_image(source, context)
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.coverage.mode, "sample")
        self.assertLessEqual(result.coverage.examined, 80)
        self.assertEqual(result.coverage.total, 150 * 200)
        self.assertEqual(result.coverage.examined, inspect_image(source, context).coverage.examined)

    def test_uint16_tiff_and_skinny_sampling(self):
        original = (np.arange(1000, dtype=np.uint16) * 3).reshape(1000, 1)
        path = self.root / "sixteen_bit.tiff"
        Image.fromarray(original).save(path)
        inventory, source, context = self._single("sixteen_bit.tiff", {"max_sample_pixels": 10})
        result = inspect_image(source, context)
        result.validate_references(inventory)
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.measurements["images"][source.source_id]["dtype"], "uint16")
        self.assertLessEqual(result.coverage.examined, 10)

    def test_multipage_tiff_is_flagged(self):
        a = Image.fromarray(np.full((25, 35), 30, dtype=np.uint8))
        b = Image.fromarray(np.full((25, 35), 80, dtype=np.uint8))
        a.save(self.root / "pages.tiff", save_all=True, append_images=[b])
        inventory, source, context = self._single("pages.tiff")
        result = inspect_image(source, context)
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.measurements["images"][source.source_id]["frame_count"], 2)
        self.assertTrue(any("first frame" in x for x in result.limitations))

    def test_corrupted_image_is_failed_not_crash(self):
        (self.root / "bad.png").write_bytes(b"\x89PNG\r\n\x1a\nnot_an_image")
        inventory, source, context = self._single("bad.png")
        result = inspect_image(source, context)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.coverage.mode, "none")
        self.assertTrue(result.limitations)
        result.validate_references(inventory)

    def test_decode_memory_limit_blocks_before_pixels(self):
        Image.fromarray(np.zeros((120, 120), dtype=np.uint8)).save(self.root / "large.png")
        inventory, source, context = self._single("large.png", {"max_decode_pixels": 100})
        result = inspect_image(source, context)
        self.assertEqual(result.status, "deferred")
        self.assertEqual(result.coverage.examined, 0)
        self.assertEqual(len(result.artifacts), 0)

    def test_collection_handles_failed_and_good_files(self):
        Image.fromarray(np.full((20, 25), 42, dtype=np.uint8)).save(self.root / "good.png")
        (self.root / "bad.png").write_bytes(b"\x89PNG\r\n\x1a\ncorrupt")
        inventory = discover(self.root)
        image_sources = [s for s in inventory.sources if s.format == "png"]
        # Explicit collection component, as the future scheduler will create.
        group = ComponentRef("image_group", "images", [s.source_id for s in image_sources])
        inventory.components.append(group)
        context = DemoContext(self.root, self.out, group.component_id)
        result = profile_image_collection(image_sources, context)
        result.validate_references(inventory)
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.coverage.unit, "files")
        self.assertEqual(result.measurements["collection"]["file_count"], 2)
        self.assertEqual(result.measurements["collection"]["success_count"], 1)
        self.assertEqual(sum(a.relative_path.startswith("figures/") for a in result.artifacts), 2)
        ToolResult.from_json(result.to_json())


if __name__ == "__main__":
    unittest.main()
