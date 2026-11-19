
# Assemble metadata from validated analysis results.
# Preserves the evidence, coverage, and limitations supplied by tools.
# Does not recalculate from original datasets.

from __future__ import annotations
from typing import Iterable
from .contracts import SCHEMA_VERSION, ToolResult

def build_metadata(
    # Build JSON-compatible metadata for one logical component.
    # Results in a dictionary with component metadata and sources.
    component_id: str,
    results: Iterable[ToolResult],
) -> dict:
    # invalid component
    if not isinstance(component_id, str) or not component_id.strip():
        raise ValueError("component_id must be a nonempty string")
    # input is not ToolResult (output of analyses)
    result_list = list(results)
    if not result_list:
        raise ValueError("At least one ToolResult is required")
    
    seen_result_ids = set()
    source_ids = set()
    serialized_results = []

    for result in result_list:
        if not isinstance(result, ToolResult):
            raise TypeError("All results must be ToolResult objects")
        # validate the contract before using its contents.
        result.validate()
        # results should be from the same component and every result must be unique
        if result.component_id != component_id:
            raise ValueError(
                f"Result {result.result_id} belongs to "
                f"{result.component_id}, not {component_id}"
            )
        if result.result_id in seen_result_ids:
            raise ValueError(
                f"Duplicate result_id: {result.result_id}"
            )
        seen_result_ids.add(result.result_id)
        source_ids.update(result.inputs)
        serialized_results.append(result.to_dict())

    return {
        "schema_version": SCHEMA_VERSION,
        "component_id": component_id,
        "result_count": len(serialized_results),
        "source_ids": sorted(source_ids),
        "results": serialized_results,
    }
