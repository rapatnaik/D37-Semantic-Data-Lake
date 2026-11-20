
"""
Conservative table normalization for the D37 Investigator Agent.

- Never changes the original dataset.
- Creates a separate Parquet copy.
- Changes values only with an explicit documented rule.
- Logs applied and skipped cleaning rules to JSON.
- Returns the team's ToolResult contract.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from ..contracts import ArtifactRef, Coverage, SourceRef, ToolResult
from .tables import read_table


MAX_CLEANING_BYTES = 25 * 1024 * 1024

SUPPORTED = {
    "csv", "tsv", "parquet", "xlsx",
    "xls", "json", "jsonl"
}


def _approved_source_path(source: SourceRef, context: Any) -> Path:
    """Resolve the source using the approved dataset context."""

    root = Path(context.dataset_root).resolve(strict=True)
    path = Path(context.resolve_source(source)).resolve(strict=True)
    expected = (root / source.relative_path).resolve(strict=True)

    if (
        path != expected
        or not path.is_relative_to(root)
        or not path.is_file()
    ):
        raise ValueError("Source is not an approved regular file.")

    return path


def _output_path(context: Any, relative_path: str) -> Path:
    """Keep generated files inside the approved output directory."""

    root = Path(context.output_dir).resolve()
    path = (root / relative_path).resolve()

    if not path.is_relative_to(root):
        raise ValueError("Output path escapes the output directory.")

    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _file_sha256(path: Path) -> str:
    """Calculate a SHA-256 hash to verify source preservation."""

    digest = hashlib.sha256()

    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def _valid_markers(markers: Any) -> bool:
    """Accept finite scalar markers only; never interpret NaN as a code."""
    return (
        isinstance(markers, list)
        and bool(markers)
        and all(
            type(value) in (str, int, float, bool)
            and (type(value) is not float or math.isfinite(value))
            for value in markers
        )
    )


def _marker_equal(left: Any, right: Any) -> bool:
    """Match documented marker types as well as values (True is not 1)."""
    return type(left) is type(right) and left == right


def _load_dictionary(
    source: SourceRef, context: Any, rules: dict[str, Any]
) -> tuple[dict[str, Any] | None, str, str | None]:
    """Load an approved, source-specific JSON dictionary from dataset_root.

    A free-form evidence string does not authorize any cleaning. The dictionary
    itself needs to be curated/trusted by the dataset owner; path containment
    alone does not establish its authenticity.
    """
    relative = rules.get("dictionary_relative_path")
    if not isinstance(relative, str) or not relative.strip():
        return None, "No data dictionary file was specified.", None

    root = Path(context.dataset_root).resolve(strict=True)
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None, "Dictionary path is not an approved relative path.", None

    try:
        path = (root / candidate).resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            return None, "Dictionary is outside the approved dataset root.", None
        if path.stat().st_size > 1024 * 1024:
            return None, "Dictionary exceeds the 1 MB limit.", None
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as error:
        return None, f"Dictionary could not be loaded: {type(error).__name__}.", None

    if not isinstance(document, dict) or document.get("source_id") != source.source_id:
        return None, "Dictionary source_id does not match the table.", None
    if not isinstance(document.get("columns"), dict):
        return None, "Dictionary has no valid columns mapping.", None
    return document, "", _file_sha256(path)


def _apply_documented_rules(
    df: pd.DataFrame,
    rules: dict[str, Any],
    dictionary: dict[str, Any] | None = None,
    dictionary_error: str = ""
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Apply only rules exactly authorized by a source-specific JSON dictionary.

    Example rules:
      {"dictionary_relative_path": "patients_dictionary.json",
       "columns": {"cholesterol": {"missing_values": [0]}}}

    The approved dictionary must contain:
      {"source_id": "patients_source",
       "columns": {"cholesterol": {"missing_values": [0]}}}
    """
    if df.columns.has_duplicates:
        raise ValueError("Duplicate column names are not supported.")
    if not isinstance(rules, dict):
        raise ValueError("Cleaning rules must be a dictionary.")
    column_rules = rules.get("columns", {})
    if not isinstance(column_rules, dict):
        raise ValueError("rules['columns'] must be a dictionary.")

    normalized = df.copy(deep=True)
    change_log = []
    documented_columns = dictionary.get("columns", {}) if dictionary else {}

    for column, rule in column_rules.items():
        entry = {
            "column": str(column),
            "operation": "replace_documented_missing_markers",
            "status": "skipped",
            "affected_rows": 0,
            "reason": ""
        }
        if column not in normalized.columns:
            entry["reason"] = "Column does not exist."
        elif not isinstance(rule, dict):
            entry["reason"] = "Rule must be a dictionary."
        elif dictionary is None:
            entry["reason"] = dictionary_error or "Verified dictionary required."
        elif column not in documented_columns:
            entry["reason"] = "Column is not documented in the dictionary."
        else:
            requested = rule.get("missing_values")
            documented_entry = documented_columns[column]
            documented = (
                documented_entry.get("missing_values")
                if isinstance(documented_entry, dict) else None
            )
            if not _valid_markers(requested):
                entry["reason"] = "Invalid requested missing-value markers."
            elif not _valid_markers(documented):
                entry["reason"] = "No valid dictionary missing-value markers."
            elif not all(any(_marker_equal(a, b) for b in documented) for a in requested):
                entry["reason"] = "Requested markers are not documented for this column."
            else:
                series = normalized[column]
                mask = pd.Series(False, index=normalized.index)
                for marker in requested:
                    if type(marker) is bool:
                        if not pd.api.types.is_bool_dtype(series):
                            continue
                        match = series.eq(marker)
                    elif type(marker) is str:
                        if not (pd.api.types.is_string_dtype(series) or series.dtype == object):
                            continue
                        match = series.map(lambda value: isinstance(value, str) and value == marker)
                    else:
                        if not (pd.api.types.is_numeric_dtype(series)
                                and not pd.api.types.is_bool_dtype(series)):
                            continue
                        match = series.eq(marker)
                    mask = mask | match.fillna(False).astype(bool)
                affected = int(mask.sum())
                if affected:
                    normalized.loc[mask, column] = pd.NA
                entry["status"] = "applied"
                entry["affected_rows"] = affected
                entry["reason"] = "Marker verified against source-specific JSON dictionary."
        change_log.append(entry)
    return normalized, change_log


def normalize_table(
    source: SourceRef,
    context: Any,
    rules: dict[str, Any] | None = None
) -> ToolResult:
    """
    Create a normalized Parquet copy and JSON audit log.

    rules=None means no value transformations are authorized.

    The original source is never intentionally modified.
    """

    parameters = {
        "format": source.format,
        "max_source_bytes": MAX_CLEANING_BYTES,
        "policy": "documented_missing_markers_only"
    }

    def make_result(
        status: str,
        *,
        rows: int = 0,
        measurements: dict[str, Any] | None = None,
        artifacts: list[ArtifactRef] | None = None,
        limitations: list[str] | None = None
    ) -> ToolResult:
        return ToolResult(
            result_id=context.result_id,
            component_id=context.component_id,
            status=status,
            inputs=[source.source_id],
            method="conservative_table_normalization_v1",
            parameters=parameters,
            coverage=Coverage(
                mode="full" if status == "complete" else "none",
                unit="rows",
                examined=rows if status == "complete" else 0,
                total=rows if status == "complete" else None,
                selection=(
                    "All source rows"
                    if status == "complete"
                    else "No completed normalization"
                ),
                seed=None
            ),
            measurements=measurements or {},
            artifacts=artifacts or [],
            limitations=limitations or []
        )

    if source.format not in SUPPORTED:
        return make_result(
            "unsupported",
            limitations=[
                f"Unsupported table format: {source.format}"
            ]
        )

    output_parquet = None
    output_log = None

    try:
        source_path = _approved_source_path(source, context)

        if source_path.stat().st_size > MAX_CLEANING_BYTES:
            return make_result(
                "deferred",
                limitations=[
                    "Source exceeds the 25 MB normalization limit. "
                    "Large-file normalization is not implemented."
                ]
            )

        # Capture the original file hash before processing.
        original_hash = _file_sha256(source_path)

        df = read_table(source_path)

        if rules is None:
            rules = {}

        if not isinstance(rules, dict):
            raise ValueError("Cleaning rules must be a dictionary.")

        dictionary, dictionary_error, dictionary_sha256 = _load_dictionary(
            source, context, rules
        ) if rules.get("columns") else (None, "", None)

        normalized, changes = _apply_documented_rules(
            df, rules, dictionary, dictionary_error
        )

        # Stable, safe filename based on the source ID.
        token = hashlib.sha256(
            source.source_id.encode("utf-8")
        ).hexdigest()[:16]

        relative_parquet = (
            f"tables/{token}_normalized.parquet"
        )

        relative_log = (
            f"tables/{token}_cleaning_log.json"
        )

        output_parquet = _output_path(
            context,
            relative_parquet
        )

        output_log = _output_path(
            context,
            relative_log
        )

        # Save a separate Parquet output.
        normalized.to_parquet(
            output_parquet,
            index=False,
            engine="pyarrow"
        )

        # Verify the data can be loaded again.
        restored = pd.read_parquet(
            output_parquet,
            engine="pyarrow"
        )

        pd.testing.assert_frame_equal(
            normalized.reset_index(drop=True),
            restored.reset_index(drop=True),
            check_dtype=False,
            check_exact=True
        )

        # Verify the source file was not changed.
        if _file_sha256(source_path) != original_hash:
            raise ValueError(
                "Original source changed during normalization."
            )

        applied_changes = sum(
            entry["affected_rows"]
            for entry in changes
            if entry["status"] == "applied"
        )

        audit = {
            "schema_version": "1.0",
            "source_id": source.source_id,
            "source_relative_path": source.relative_path,
            "source_sha256_before": original_hash,
            "source_sha256_after": _file_sha256(source_path),
            "normalized_relative_path": relative_parquet,
            "row_count": int(len(df)),
            "column_count": int(len(df.columns)),
            "dictionary_relative_path": rules.get("dictionary_relative_path") if dictionary else None,
            "dictionary_sha256": dictionary_sha256,
            "total_changed_cells": int(applied_changes),
            "rules": changes,
            "policy": (
                "Only source-specific JSON dictionary markers authorize changes."
            )
        }

        output_log.write_text(
            json.dumps(
                audit,
                indent=2,
                allow_nan=False
            ) + "\n",
            encoding="utf-8"
        )

        return make_result(
            "complete",
            rows=len(df),
            measurements={
                "row_count": int(len(df)),
                "column_count": int(len(df.columns)),
                "total_changed_cells": int(applied_changes),
                "original_source_preserved": True,
                "rules_applied": sum(
                    item["status"] == "applied"
                    for item in changes
                ),
                "rules_skipped": sum(
                    item["status"] == "skipped"
                    for item in changes
                )
            },
            artifacts=[
                ArtifactRef(
                    artifact_id=f"normalized_{token}",
                    relative_path=relative_parquet,
                    media_type="application/vnd.apache.parquet"
                ),
                ArtifactRef(
                    artifact_id=f"cleaning_log_{token}",
                    relative_path=relative_log,
                    media_type="application/json"
                )
            ]
        )

    except Exception as error:
        # Remove incomplete outputs if the operation failed.
        for path in (output_parquet, output_log):
            if path is not None and path.is_file():
                path.unlink()

        return make_result(
            "failed",
            limitations=[
                f"Normalization failed: "
                f"{type(error).__name__}: {error}"
            ]
        )
