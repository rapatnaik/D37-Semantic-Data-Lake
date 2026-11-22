"""Reconcile measured table values with explicit, cited dictionary entries."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath

from agents import semantic_agent

from .config import Config
from .contracts import Inventory, SourceRef, ToolResult
from .scheduler import BudgetExhausted, ModelBudget

PROFILE_VERSION = "1.0"


def table_result(metadata: dict) -> dict:
    return next(iter(metadata.get("results", [])), {})


def resolve_dictionaries(
    inventory: Inventory, tables: dict[str, dict], documents: list[ToolResult],
) -> tuple[dict[str, dict], list[dict]]:
    """Link entries to an exact path or an unambiguous basename and column."""
    source_paths = {source.source_id: source.relative_path for source in inventory.sources}
    paths: dict[str, list[str]] = defaultdict(list)
    basenames: dict[str, list[str]] = defaultdict(list)
    for component in inventory.components:
        if component.component_id in tables:
            for source_id in component.source_ids:
                path = source_paths[source_id]
                paths[path].append(component.component_id)
                basenames[PurePosixPath(path).name].append(component.component_id)

    def candidates(reference: str) -> list[str]:
        found = paths.get(reference.removeprefix("./"), []) if "/" in reference else basenames.get(reference, [])
        return sorted(set(found))

    linked = {cid: {"entries": [], "reference_issues": [], "coverage_limitations": []} for cid in tables}
    columns = {cid: table_result(metadata).get("measurements", {}).get("columns")
               for cid, metadata in tables.items()}
    unlinked_issues: dict[tuple, dict] = {}
    table_issues: dict[tuple, dict] = {}
    for result in documents:
        for source_id in result.inputs:
            dictionary = result.measurements.get("documents", {}).get(source_id, {}).get("dictionary", {})
            path = source_paths[source_id]
            if result.status != "complete":
                citations_by_table: dict[str, list[dict]] = defaultdict(list)
                for declaration in dictionary.get("tables", []):
                    matches = candidates(declaration["table"])
                    if len(matches) == 1:
                        citations_by_table[matches[0]].append({**declaration["citation"], "source_path": path})
                for cid, citations in citations_by_table.items():
                    linked[cid]["coverage_limitations"].append({
                        "status": result.status, "coverage": result.coverage.to_dict(),
                        "limitations": result.limitations, "citations": citations,
                    })
            for entry in dictionary.get("entries", []):
                reference, column = entry["table"], entry["column"]
                citation = {**entry["citation"], "source_path": path}
                matches = candidates(reference)
                if len(matches) != 1:
                    reason = "ambiguous_table" if matches else "missing_table"
                    issue = unlinked_issues.setdefault((source_id, reference), {
                        "reason": reason, "table": reference, "citations": [],
                    })
                    issue["citations"].append(citation)
                    continue
                cid = matches[0]
                if columns[cid] is None or column not in columns[cid]:
                    reason = "table_columns_unavailable" if columns[cid] is None else "missing_column"
                    key = (cid, source_id, reference, column)
                    if key not in table_issues:
                        table_issues[key] = {"reason": reason, "table": reference, "column": column, "citations": []}
                        linked[cid]["reference_issues"].append(table_issues[key])
                    table_issues[key]["citations"].append(citation)
                    continue
                linked[cid]["entries"].append({**entry, "citation": citation})

    for evidence in linked.values():
        evidence["entries"].sort(key=lambda entry: (
            entry["column"], entry["code"], entry["label"], entry["table"],
            entry["citation"]["source_path"], entry["citation"]["locator"],
        ))
    return linked, [unlinked_issues[key] for key in sorted(unlinked_issues)]


def _code(value, *, numeric: bool):
    if numeric:
        try:
            number = Decimal(str(value))
            if not number.is_nan():
                return number
        except InvalidOperation:
            pass
    return str(value)


def build_semantic_profile(
    metadata: dict, *, source: SourceRef, result_path: str | None, dictionary: dict,
    budget: ModelBudget, config: Config,
) -> dict:
    result = table_result(metadata)
    measured = result.get("measurements", {})
    coverage = result.get("coverage", {})
    observation = {
        "source_id": source.source_id, "source_path": source.relative_path,
        "result_id": result.get("result_id"), "result_path": result_path,
    }
    verification = list(dictionary["reference_issues"])
    profile = {
        "schema_version": PROFILE_VERSION, "component_id": metadata["component_id"],
        "observation": observation, "coverage": coverage, "columns": {},
        "dictionary_entries": dictionary["entries"],
        "dictionary_coverage_limitations": dictionary["coverage_limitations"],
        "needs_verification": verification,
    }
    entries_by_column: dict[str, list[dict]] = defaultdict(list)
    for entry in dictionary["entries"]:
        entries_by_column[entry["column"]].append(entry)
    for name, facts in measured.get("columns", {}).items():
        frequencies = facts.get("value_frequencies", {})
        entries = entries_by_column.get(name, [])
        truncated = frequencies.get("truncated", False)
        observations = facts.get("top_values", []) if truncated else frequencies.get("values", [])
        if not entries and not observations:
            continue

        column_citation = {**observation, "locator": f"column {name}"}
        column = {
            "column": name, "dtype": facts["dtype"], "null_count": facts["null_count"],
            "distinct_count": facts["distinct_count"], "sampled": frequencies.get("sampled", False),
            "truncated": truncated, "max_distinct": frequencies.get("max_distinct"),
            "observation_citation": column_citation, "values": [],
        }
        profile["columns"][name] = column
        if not entries:
            verification.append({"reason": "no_linked_dictionary", "column": name, "citations": [column_citation]})
        if truncated:
            verification.append({"reason": "frequencies_truncated", "column": name, "citations": [column_citation]})

        numeric = frequencies.get("numeric", False)
        definitions_by_code = defaultdict(lambda: defaultdict(list))
        for entry in entries:
            definitions_by_code[_code(entry["code"], numeric=numeric)][entry["label"]].append(entry["citation"])
        for observed in observations:
            value = observed["value"]
            definitions = definitions_by_code.get(_code(value, numeric=numeric), {})
            status = "documented" if len(definitions) == 1 else "conflict" if definitions else "unresolved"
            column["values"].append({
                **observed, "status": status,
                "definitions": [{"label": label, "citations": citations} for label, citations in sorted(definitions.items())],
            })
            if status == "conflict":
                verification.append({
                    "reason": "conflicting_definitions", "column": name, "value": value,
                    "citations": [citation for citations in definitions.values() for citation in citations],
                })
            elif status == "unresolved" and entries:
                verification.append({"reason": "undocumented_code", "column": name, "value": value,
                                     "citations": [column_citation]})

    profile["model_interpretation"] = _interpret(source, measured, budget, config)
    return profile


def _interpret(source: SourceRef, measured: dict, budget: ModelBudget, config: Config) -> dict:
    settings = config.model
    if not (settings.enabled and settings.interpret_semantics):
        return {"status": "disabled"}
    columns = measured.get("columns", {})
    if not columns:
        return {"status": "skipped", "reason": "No column measurements are available."}
    key = config.api_key()
    if key is None:
        return {"status": "skipped", "reason": f"No model credentials in ${settings.api_key_env}."}
    context = {
        "dataset": source.relative_path, "row_count": measured["row_count"], "columns": columns,
        "potential_keys": [name for name, facts in columns.items() if facts.get("candidate_key")],
    }
    try:
        prompt = semantic_agent.build_table_prompt(context)
        with budget.request():
            reply = semantic_agent.request_completion(prompt, settings.name, endpoint=settings.endpoint, api_key=key)
        interpretations = semantic_agent.parse_columns(reply, columns)
    except BudgetExhausted as error:
        return {"status": "skipped", "reason": str(error)}
    except Exception as error:
        return {"status": "failed", "reason": f"Model interpretation failed ({type(error).__name__})."}
    return {
        "status": "complete", "model": settings.name,
        "columns": {name: {field: entry[field] for field in semantic_agent.COLUMN_FIELDS}
                    for name, entry in interpretations.items()},
    }
