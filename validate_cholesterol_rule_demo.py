"""Exercise dictionary-backed cholesterol cleaning on a COPY of project data.

This is a reproducibility test of an existing project cleaning decision,
NOT independent clinical validation of a missing-value rule.

Run from the D37-Semantic-Data-Lake repository root:
    python validate_cholesterol_rule_demo.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from agents.investigator.contracts import SourceRef
from agents.investigator.tools.cleaning import normalize_table


ROOT = Path(__file__).resolve().parent
ORIGINAL = ROOT / "datasets" / "original" / "Cardiovascular_Disease_Dataset.csv"
DEMO_ROOT = ROOT / "outputs" / "real_table_validation" / "cholesterol_rule_demo"
INPUT_ROOT = DEMO_ROOT / "inputs"
OUTPUT_ROOT = DEMO_ROOT / "results"
FILENAME = ORIGINAL.name
SOURCE_ID = "cardiovascular_rule_reproduction_demo"
DICTIONARY_FILENAME = "cardiovascular_rule_demo_dictionary.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    if not ORIGINAL.is_file():
        raise FileNotFoundError(f"Original dataset not found: {ORIGINAL}")

    INPUT_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    original_hash = sha256(ORIGINAL)
    original_frame = pd.read_csv(ORIGINAL)
    zeros = original_frame["serumcholestrol"].eq(0)
    expected_changes = int(zeros.sum())
    assert expected_changes == 53, (
        f"Expected 53 zero cholesterol values, found {expected_changes}"
    )

    # Work on a separate, disposable copy; the original stays untouched.
    staged_source = INPUT_ROOT / FILENAME
    shutil.copy2(ORIGINAL, staged_source)

    # Demonstration manifest reproducing the existing project's cleaning rule.
    # This is not the original data dictionary or a clinical authorization.
    manifest = {
        "source_id": SOURCE_ID,
        "columns": {
            "serumcholestrol": {"missing_values": [0]}
        },
    }
    manifest_path = INPUT_ROOT / DICTIONARY_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    stat = staged_source.stat()
    source = SourceRef(
        source_id=SOURCE_ID,
        relative_path=FILENAME,
        format="csv",
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
    )
    context = SimpleNamespace(
        dataset_root=INPUT_ROOT,
        output_dir=OUTPUT_ROOT,
        component_id="cardiovascular_rule_demo_component",
        result_id="cardiovascular_rule_demo_result",
        resolve_source=lambda item: INPUT_ROOT / item.relative_path,
    )
    rules = {
        "dictionary_relative_path": DICTIONARY_FILENAME,
        "columns": {"serumcholestrol": {"missing_values": [0]}},
    }

    result = normalize_table(source, context, rules=rules)
    print("Cleaning status:", result.status)
    print("Changed cells:", result.measurements.get("total_changed_cells"))
    print("Rule count applied:", result.measurements.get("rules_applied"))
    print("Limitations:", result.limitations)
    assert result.status == "complete", result.limitations
    assert result.measurements["total_changed_cells"] == 53
    assert result.measurements["rules_applied"] == 1
    assert result.measurements["rules_skipped"] == 0

    def artifact_path(suffix: str) -> Path:
        matches = [
            item for item in result.artifacts
            if item.relative_path.endswith(suffix)
        ]
        assert len(matches) == 1, f"Expected one {suffix} artifact"
        path = (OUTPUT_ROOT / matches[0].relative_path).resolve()
        assert path.is_relative_to(OUTPUT_ROOT.resolve())
        assert path.is_file(), path
        return path

    normalized = pd.read_parquet(artifact_path("_normalized.parquet"))
    audit = json.loads(
        artifact_path("_cleaning_log.json").read_text(encoding="utf-8")
    )

    expected = original_frame.copy()
    expected.loc[zeros, "serumcholestrol"] = float("nan")
    pd.testing.assert_frame_equal(
        expected.reset_index(drop=True),
        normalized.reset_index(drop=True),
        check_dtype=False,
        check_exact=True,
    )
    assert len(normalized) == len(original_frame) == 1000
    assert list(normalized.columns) == list(original_frame.columns)
    assert int(normalized["serumcholestrol"].isna().sum()) == 53
    assert audit["total_changed_cells"] == 53
    assert audit["source_sha256_before"] == audit["source_sha256_after"]
    assert sha256(staged_source) == original_hash
    assert sha256(ORIGINAL) == original_hash

    print("Rows preserved: 1000")
    print("Only 53 cholesterol zeros replaced: YES")
    print("Other values and columns preserved: YES")
    print("Original CSV preserved: YES")
    print("Cleaning audit verified: YES")
    print("PASS: rule-reproduction demo complete")
    print("Generated outputs:", OUTPUT_ROOT)
    print("NOTE: This demo does not establish clinical rule provenance.")


if __name__ == "__main__":
    main()
