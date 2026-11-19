# Validating relationships using existing profiling measurements, not re-reading datasets

from __future__ import annotations
from .contracts import ToolResult
from pathlib import PurePosixPath
from .contracts import SourceRef, ToolResult

def validate_candidate_key(
    result: ToolResult,
    column: str,
) -> dict:
    # Check if a single column could be a key
    if not isinstance(result, ToolResult):
        raise TypeError("result must be a ToolResult")
    result.validate()
    if not isinstance(column, str) or not column.strip():
        raise ValueError("column must be a nonempty string")
    if not column == column.strip():
        raise ValueError("column must not contain surrounding whitespace")

    measurements = result.measurements
    columns = measurements.get("columns", {})
    stats = columns.get(column, {}) if isinstance(columns, dict) else {}

    # profile measurements of that column
    evidence = {
        "result_id": result.result_id,
        "component_id": result.component_id,
        "source_ids": list(result.inputs),
        "column": column,
        "coverage": result.coverage.to_dict(),
    }

    def outcome(status: str, reason: str) -> dict:
        return {
            "relationship_type": "candidate_key",
            "status": status,
            "evidence": evidence,
            "reason": reason,
        }

    if not isinstance(stats, dict):
        return outcome("insufficient_evidence", "Invalid column statistics")

    row_count = measurements.get("row_count")
    null_count = stats.get("null_count")
    distinct_count = stats.get("distinct_count")

    # checking that all counts are exact integers
    counts = (row_count, null_count, distinct_count)
    if not all(type(value) is int and value >= 0 for value in counts):
        return outcome("insufficient_evidence", "Missing or invalid row/null/distinct counts")
    if null_count > row_count or distinct_count > row_count:
        return outcome("insufficient_evidence", "Inconsistent profiling counts")
    if result.status not in {"complete", "partial"}:
        return outcome(
            "insufficient_evidence",
            "Analysis did not provide usable completed measurements"
        )
    
    # if there are NOT no null values or not all values are distinct, then it is NOT a key
    if null_count > 0:
        return outcome("rejected", "Column contains null values")
    if distinct_count < row_count:
        return outcome("rejected", "Column contains duplicate values")
    
    # if coverage is not full, then full uniqueness does not mean anything.
    if (
        result.status != "complete"
        or result.coverage.mode != "full"
        or result.coverage.unit != "rows"
        or result.coverage.examined != row_count
        or row_count == 0
    ):
        return outcome(
            "insufficient_evidence",
            "Full-table key uniqueness has not been established"
        )
    
    # if it passes value type checks, null and unique checks, and coverage check:
    return outcome(
        "supported",
        "Full-table counts support a non-null, unique candidate key"
    )


def validate_file_sample_match(source_a: SourceRef, source_b: SourceRef,) -> dict:
    # find possible sample matches using filename evidence only.
    if not isinstance(source_a, SourceRef):
        raise TypeError("source_a must be a SourceRef")
    if not isinstance(source_b, SourceRef):
        raise TypeError("source_b must be a SourceRef")

    source_a.validate()
    source_b.validate()

    if source_a.source_id == source_b.source_id:
        raise ValueError("Cannot compare a source with itself")

    # extracting the file names without the extension
    name_a = PurePosixPath(source_a.relative_path).stem.lower()
    name_b = PurePosixPath(source_b.relative_path).stem.lower()

    evidence = {
        "source_ids": [source_a.source_id, source_b.source_id],
        "paths": [source_a.relative_path, source_b.relative_path],
        "filename_stems": [name_a, name_b],
        "method": "exact_filename_stem_match",
    }

    def outcome(status: str, reason: str) -> dict:
        return {
            "relationship_type": "file_sample_match",
            "status": status,
            "evidence": evidence,
            "reason": reason,
        }

    # Generic filenames are not reliable sample identifiers.
    generic_names = {
        "readme", "metadata", "data", "dataset", "table", 
        "image", "images", "results", "summary", "notes"
    }

    if not name_a or not name_b:
        return outcome("insufficient_evidence", "One or both filenames lack an identifiable stem")

    if name_a in generic_names or name_b in generic_names:
        return outcome("insufficient_evidence", "Generic filenames do not identify individual samples")

    if name_a == name_b:
        return outcome("candidate", "Matching filename stems suggest a possible sample association")

    # if no possible relationship:
    return outcome("no_match", "No exact filename-stem match was found")

#Evaluating document to source references
def validate_document_association(
    document: SourceRef, # documentation file
    target: SourceRef, # target dataset we're checking association with
    referenced_paths: list[str], # found upstream within analysis
) -> dict:
    if not isinstance(document, SourceRef):
        raise TypeError("document must be a SourceRef")
    if not isinstance(target, SourceRef):
        raise TypeError("target must be a SourceRef")
    
    document.validate()
    target.validate()

    # type checks
    if document.source_id == target.source_id:
        raise ValueError("A document cannot be associated with itself")
    if document.format not in {"txt", "md", "pdf", "docx"}:
        raise ValueError("document must be a supported document source")
    if not isinstance(referenced_paths, list) or not all(
        isinstance(path, str) for path in referenced_paths
    ):
        raise TypeError("referenced_paths must be a list of strings")
    
    # metadata of original inputs
    evidence = {
        "document_source_id": document.source_id,
        "target_source_id": target.source_id,
        "document_path": document.relative_path,
        "target_path": target.relative_path,
        "referenced_paths": list(referenced_paths),
        "method": "explicit_relative_path_reference",
    }

    def outcome(status: str, reason: str) -> dict:
        return {
            "relationship_type": "documentation_association",
            "status": status,
            "evidence": evidence,
            "reason": reason,
        }

    # path matching
    if not referenced_paths:
        return outcome(
            "insufficient_evidence",
            "No document references were supplied"
        )
    if target.relative_path in referenced_paths:
        return outcome(
            "candidate",
            "Document references the target's dataset-relative path"
        )

    return outcome(
        "no_match",
        "No exact target path appears in the supplied references"
    )
