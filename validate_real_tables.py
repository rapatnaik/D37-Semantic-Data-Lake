
"""
Validate the D37 tabular investigator on real cardiovascular files.

Original datasets are never modified.
No cleaning transformations are authorized.
Outputs are written separately under outputs/real_table_validation.
"""

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from agents.investigator.contracts import SourceRef
from agents.investigator.tools.tables import profile_table
from agents.investigator.tools.cleaning import normalize_table


ROOT = Path.cwd().resolve()
DATASET_ROOT = (ROOT / "datasets" / "original").resolve()
OUTPUT_ROOT = (ROOT / "outputs" / "real_table_validation").resolve()

DATASETS = [
    "Cardiovascular_Disease_Dataset.csv",
    "heart_disease.csv",
]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_dataset(filename):
    path = DATASET_ROOT / filename
    before_hash = sha256(path)
    stat = path.stat()

    source = SourceRef(
        source_id=f"real_{path.stem.lower()}",
        relative_path=filename,
        format="csv",
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
    )

    def make_context(operation):
        return SimpleNamespace(
            dataset_root=DATASET_ROOT,
            output_dir=OUTPUT_ROOT / path.stem / operation,
            component_id=f"component_{path.stem}_{operation}",
            result_id=f"result_{path.stem}_{operation}",
            seed=42,
            resolve_source=lambda item: DATASET_ROOT / item.relative_path,
        )

    profile_context = make_context("profile")
    cleaning_context = make_context("cleaning")

    profile = profile_table(source, profile_context)
    cleaning = normalize_table(source, cleaning_context)

    print(f"\n=== {filename} ===")
    print("Profile status:", profile.status)
    print("Profile coverage:", profile.coverage.mode)
    print("Profile artifacts:", len(profile.artifacts))
    print("Cleaning status:", cleaning.status)
    print("Cleaning changed cells:",
          cleaning.measurements.get("total_changed_cells"))
    print("Cleaning artifacts:", len(cleaning.artifacts))

    assert profile.status == "complete", profile.limitations
    assert cleaning.status == "complete", cleaning.limitations
    assert profile.coverage.mode == "full"
    assert cleaning.coverage.mode == "full"
    assert cleaning.measurements["total_changed_cells"] == 0

    original = pd.read_csv(path)

    parquet_artifacts = [
        artifact for artifact in cleaning.artifacts
        if artifact.relative_path.endswith(".parquet")
    ]

    assert len(parquet_artifacts) == 1

    normalized_path = (
        cleaning_context.output_dir
        / parquet_artifacts[0].relative_path
    )

    normalized = pd.read_parquet(normalized_path)

    pd.testing.assert_frame_equal(
        original.reset_index(drop=True),
        normalized.reset_index(drop=True),
        check_dtype=False,
        check_exact=True,
    )

    assert sha256(path) == before_hash
    assert len(profile.artifacts) >= 1

    for artifact in profile.artifacts:
        artifact_path = (
            profile_context.output_dir / artifact.relative_path
        ).resolve()

        assert artifact_path.is_relative_to(
            profile_context.output_dir.resolve()
        )
        assert artifact_path.is_file()

    print("Original file preserved: YES")
    print("Normalized data matches original: YES")
    print("Profile artifacts verified: YES")


def main():
    for filename in DATASETS:
        validate_dataset(filename)

    print("\nALL REAL-DATA VALIDATIONS PASSED")


if __name__ == "__main__":
    main()
