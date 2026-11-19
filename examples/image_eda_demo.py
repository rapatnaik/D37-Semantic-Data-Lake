"""Standalone demonstration until d37-agent's production CLI/context is ready.

Example (from repository root):
    python3 -m examples.image_eda_demo tests/investigator/fixtures --output /tmp/d37-image-demo
Use a directory with actual PNG/JPEG/TIFF images; .lif is unsupported.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from agents.investigator import discover
from agents.investigator.contracts import ComponentRef
from agents.investigator.tools.images import profile_image_collection


class LocalDemoContext:
    def __init__(self, root: Path, output: Path, component_id: str):
        self.dataset_root = root.resolve(strict=True)
        self.output_dir = output.resolve()
        self.component_id = component_id
        self.result_id = "demo_image_collection"
        self.seed = 0
        self.limits = {}

    def resolve_source(self, source):
        path = (self.dataset_root / source.relative_path).resolve(strict=True)
        if not path.is_relative_to(self.dataset_root):
            raise ValueError("Source outside selected dataset")
        return path


def main():
    parser = argparse.ArgumentParser(description="Inspect a PNG/JPEG/TIFF folder with D37 image EDA")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, default=Path(".d37-agent/image-demo"))
    args = parser.parse_args()

    inventory = discover(args.directory)
    images = [s for s in inventory.sources if s.format in {"png", "jpeg", "tiff"}]
    if not images:
        raise SystemExit("No supported PNG/JPEG/TIFF files found. .lif decoding is out of scope.")
    collection = ComponentRef("demo_image_collection", "images", [s.source_id for s in images])
    inventory.components.append(collection)
    context = LocalDemoContext(args.directory, args.output, collection.component_id)
    result = profile_image_collection(images, context)
    result.validate_references(inventory)
    context.output_dir.mkdir(parents=True, exist_ok=True)
    output = context.output_dir / "image_results.json"
    output.write_text(result.to_json(), encoding="utf-8")
    print(f"Processed {len(images)} discovered images; result status: {result.status}")
    print(f"Saved {len(result.artifacts)} preview/plot files under: {context.output_dir}")
    print(f"Saved JSON result: {output}")
    for note in result.limitations:
        print("NOTE:", note)


if __name__ == "__main__":
    main()
