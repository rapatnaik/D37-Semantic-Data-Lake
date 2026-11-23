"""Render evidence-linked Markdown and offline marimo notebooks from saved runs.

No model calls, source-file execution, or custom-code execution occur here.
The scheduler owns revision creation and writes returned strings atomically.
"""
from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .contracts import Inventory, ToolResult


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except (OSError, ValueError):
        return None


def _safe_file(root: Path, relative: str) -> Path | None:
    if not isinstance(relative, str) or not relative:
        return None
    target = (root / relative).resolve()
    return target if target.is_relative_to(root.resolve()) and target.is_file() else None


def _snapshot(run_dir: Path) -> dict[str, Any]:
    root = Path(run_dir).resolve()
    inventory_data = _load_json(root / "inventory.json")
    if inventory_data is None:
        raise FileNotFoundError("Missing or invalid inventory.json")
    inventory = Inventory.from_dict(inventory_data)
    checkpoint = _load_json(root / "checkpoint.json") or {}
    jobs = checkpoint.get("jobs", {})
    results: dict[str, dict] = {}
    metadata: dict[str, dict] = {}
    semantics: dict[str, dict] = {}
    semantic_artifacts: dict[str, str] = {}
    document_artifacts: dict[str, str] = {}
    for job in jobs.values():
        if not isinstance(job, dict) or job.get("status") in {"pending", "running", "removed"}:
            continue
        component_id = job.get("component_id")
        outputs = job.get("outputs", {})
        if not isinstance(outputs, dict) or not component_id:
            continue
        if job.get("kind") == "tool" and "result" in outputs:
            file = _safe_file(root, outputs["result"])
            if file:
                try:
                    result = ToolResult.from_json(file.read_text(encoding="utf-8"))
                    result.validate_references(inventory)
                    results[component_id] = result.to_dict()
                    for source_id, document in result.measurements.get("documents", {}).items():
                        name = document.get("text_artifact")
                        if name:
                            for artifact in result.artifacts:
                                if artifact.relative_path.endswith("/" + name) and _safe_file(root, artifact.relative_path):
                                    document_artifacts[source_id] = artifact.relative_path
                except (ValueError, OSError):
                    pass
        for kind, destination in (("metadata", metadata), ("semantics", semantics)):
            if job.get("kind") == kind and kind in outputs:
                file = _safe_file(root, outputs[kind])
                if file and (data := _load_json(file)) is not None:
                    destination[component_id] = data
                    if kind == "semantics":
                        semantic_artifacts[component_id] = outputs[kind]
    # Snapshot references only saved, validated paths. Do not read raw inputs.
    analyses = []
    for file in sorted((root / "analyses").glob("*/result.json")):
        if file.is_symlink() or not file.resolve().is_relative_to(root):
            continue
        if (data := _load_json(file)) is not None:
            analyses.append({"job_id": data.get("job_id", file.parent.name),
                             "status": data.get("status", "unknown"),
                             "question": (data.get("request") or {}).get("question", "")})
    return {"inventory": inventory.to_dict(), "results": results,
            "metadata": metadata, "semantics": semantics, "analyses": analyses,
            "document_artifacts": document_artifacts, "semantic_artifacts": semantic_artifacts,
            "dictionary_reference_issues": checkpoint.get("dictionary_reference_issues", []),
            "run_id": root.name}


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").replace("`", "'")


def _json_block(data: Any) -> str:
    body = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
    fence = "`" * max(3, 1 + max(map(len, re.findall(r"`+", body)), default=0))
    return f"{fence}json\n{body}\n{fence}"


def _literal(value: Any) -> str:
    text = escape(str(value), quote=False)
    return re.sub(r"([\\`*_\[\]|~])", r"\\\1", " ".join(text.splitlines()))


def _citation(citation: dict, documents: dict[str, str]) -> str:
    label = _literal(citation["source_path"])
    if citation.get("locator"):
        label += f" ({_literal(citation['locator'])})"
    artifact = citation.get("result_path") or documents.get(citation["source_id"])
    return f"[{label}](../../{quote(artifact)})" if artifact else label


def _reference_issue(issue: dict, documents: dict[str, str]) -> str:
    table = _literal(issue["table"])
    reason = issue["reason"]
    if reason == "ambiguous_table":
        message = f"Table reference **{table}** matches multiple tables."
    elif reason == "missing_table":
        message = f"Table reference **{table}** has no match in the inventory."
    elif reason == "missing_column":
        message = f"Table **{table}** has no column named **{_literal(issue['column'])}**."
    else:
        message = f"Column **{_literal(issue['column'])}** could not be verified in the table profile for **{table}**."
    citations = ", ".join(_citation(citation, documents) for citation in issue["citations"])
    return f"- {message} {citations}"


def _column_interpretations(model: dict) -> list[str]:
    lines = []
    if model["status"] in {"complete", "partial"}:
        lines.extend([f"**Model interpretations ({_literal(model['model'])})**", "",
                      "| Column | Description | Semantic type | Unit | Evidence cited by model | Needs verification |",
                      "|---|---|---|---|---|---|"])
        for name, interpretation in model["columns"].items():
            evidence = "<br>".join(map(_literal, interpretation["evidence"])) or "—"
            verification = "<br>".join(map(_literal, interpretation["needs_verification"])) or "—"
            cells = [_literal(name), _literal(interpretation["description"]),
                     _literal(interpretation["semantic_type"]), _literal(interpretation["unit"] or "—"),
                     evidence, verification]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    elif model["status"] in {"skipped", "failed"}:
        lines.extend([f"Model interpretation {model['status']}. {_literal(model['reason'])}", ""])
    for issue in model.get("batch_issues", []):
        names = ", ".join(_literal(name) for name in issue["columns"])
        lines.extend([f"Model batch {issue['status']} for {names}. {_literal(issue['reason'])}", ""])
    return lines


def _tiff_semantics(profile: dict) -> list[str]:
    lines = []
    for image in profile["images"]:
        lines.extend([f"#### TIFF interpretation for {_literal(image['source_path'])}", ""])
        if preview := image["preview_path"]:
            total = image["frame_count"]
            frame = f"frame {image['frame_number']}" + (f" of {total}" if total is not None else "")
            lines.extend([f"Image evidence [{frame} PNG preview](../../{quote(preview)}).", ""])
        model = image["model_interpretation"]
        if model["status"] == "complete":
            lines.extend([f"**Vision model interpretation ({_literal(model['model'])})**",
                          "", _literal(model["description"]), ""])
            for hypothesis in model["needs_verification"]:
                lines.append(f"- **Needs verification** {_literal(hypothesis)}")
            if model["needs_verification"]:
                lines.append("")
        elif model["status"] == "disabled":
            lines.extend(["Vision model interpretation disabled.", ""])
        else:
            lines.extend([f"Vision model interpretation {model['status']}. {_literal(model['reason'])}", ""])
    return lines


def _component_labels(components: list[dict]) -> dict[str, str]:
    """Display the shortest unique hash prefixes starting at eight characters."""
    ids = [component["component_id"] for component in components]
    digests = {cid: match[1] for cid in ids if (match := re.fullmatch(r"component_([0-9a-f]{64})", cid))}
    for length in range(8, 64):
        labels = {cid: f"{digests[cid][:length]}…" if cid in digests else cid for cid in ids}
        if len(set(labels.values())) == len(ids):
            return labels
    return {cid: cid for cid in ids}


def _markdown(data: dict[str, Any]) -> str:
    inventory = data["inventory"]
    component_labels = _component_labels(inventory["components"])
    sources = {s["source_id"]: s["relative_path"] for s in inventory["sources"]}
    lines = [f"# D37 investigation — {data['run_id']}", ""]
    lines += ["## Inventory and coverage", "",
             f"Sources: {len(sources)}; components: {len(inventory['components'])}.", "",
             "| Component ID | Kind | Sources | Status | Coverage |", "|---|---|---|---|---|"]
    for comp in inventory["components"]:
        cid = comp["component_id"]
        result = data["results"].get(cid, {})
        coverage = result.get("coverage", {})
        summary = f"{coverage.get('mode', 'not measured')}: {coverage.get('examined', '?')}/{coverage.get('total', '?')} {coverage.get('unit', '')}"
        lines.append(f"| `{_cell(component_labels[cid])}` | {_cell(comp['kind'])} | {_cell(', '.join(sources.get(s, s) for s in comp['source_ids']))} | {_cell(result.get('status', 'not run'))} | {_cell(summary)} |")
    lines.append("")
    tables = []
    linked_profiles = set()
    for comp in inventory["components"]:
        cid = comp["component_id"]
        profile = data["semantics"].get(cid, {})
        if comp["kind"] != "table" or not (model := profile.get("model_interpretation")):
            continue
        interpretations = _column_interpretations(model)
        if interpretations:
            linked_profiles.add(cid)
            path = profile["observation"]["source_path"]
            artifact = data["semantic_artifacts"][cid]
            tables.extend([f"### {_literal(path)}", "", *interpretations,
                           f"[Saved semantic profile JSON](../../{quote(artifact)})", ""])
    if tables:
        lines += ["## Column descriptions", "",
                  "The model produced these interpretations during the investigation. "
                  "The report displays the saved replies. Verify inferred meanings against source documentation.",
                  "", *tables]
    lines.extend(["## Measurements and evidence", ""])
    for comp in inventory["components"]:
        cid = comp["component_id"]
        source_names = ", ".join(sources.get(source_id, source_id) for source_id in comp["source_ids"])
        lines += [f"### {_literal(source_names or comp['kind'])}", ""]
        result = data["results"].get(cid)
        if not result:
            lines += ["No validated tool result is available.", ""]
            continue
        lines += [f"**Method:** `{_cell(result['method'])}`. **Status:** {result['status']}.", "",
                  "<details>", "<summary>Coverage and measured facts</summary>", "",
                  "**Coverage**", "", _json_block(result["coverage"]), "",
                  "**Measured facts**", "", _json_block(result["measurements"]), "",
                  "</details>", ""]
        if result["artifacts"]:
            lines += ["**Saved artifacts** (paths relative to run directory):", ""]
            lines += [f"- `{_cell(a['relative_path'])}` ({_cell(a['media_type'])})" for a in result["artifacts"]]
            lines.append("")
        if cid in data["metadata"]:
            lines += ["<details>", "<summary>Assembled metadata</summary>", "",
                      _json_block(data["metadata"][cid]), "", "</details>", ""]
        if profile := data["semantics"].get(cid):
            if profile.get("kind") == "tiff":
                lines += _tiff_semantics(profile)
            elif cid not in linked_profiles:
                artifact = data["semantic_artifacts"][cid]
                lines += [f"[Saved semantic profile JSON](../../{quote(artifact)})", ""]
            issues = [issue for issue in profile.get("needs_verification", [])
                      if isinstance(issue, dict) and issue.get("reason") in
                      {"missing_column", "table_columns_unavailable"}]
            if issues:
                lines += [_reference_issue(issue, data["document_artifacts"]) for issue in issues] + [""]
        if result["limitations"]:
            lines += ["**Limitations and uncertainty:**", ""]
            lines += [f"- {_cell(x)}" for x in result["limitations"]]
            lines.append("")
    if data["dictionary_reference_issues"]:
        lines += ["## Dictionary references that need verification", ""]
        lines += [_reference_issue(issue, data["document_artifacts"]) for issue in data["dictionary_reference_issues"]]
        lines.append("")
    lines += ["## Follow-up analyses", ""]
    if data["analyses"]:
        lines += [f"- `{_cell(a['job_id'])}` — {_cell(a['status'])}: {_cell(a['question'])}" for a in data["analyses"]]
    else:
        lines.append("No saved follow-up analyses.")
    lines += ["", "## Reproducibility and caveats", "",
              "- Tool measurements are quoted from validated saved ToolResult records; sampled measurements are not full-dataset claims.",
              "- Saved interpretations are labeled as model interpretations, not verified measurements.",
              "- The companion marimo notebook reads saved run artifacts and redraws supported PNGs without model calls or executing generated analysis code.",
              "- Original data remain untouched. Run input hashes, seeds, environment and provenance are retained in the run manifest/checkpoint when available.",
              "- Extracted text may contain sensitive information; review outputs before sharing.", ""]
    if inventory["limitations"]:
        lines += ["**Discovery limitations:**", ""] + [f"- {_cell(x)}" for x in inventory["limitations"]] + [""]
    return "\n".join(lines) + "\n"


def render_report(run_dir: str | Path) -> str:
    """Return report.md content; scheduler writes it into a new revision."""
    return _markdown(_snapshot(Path(run_dir)))


def render_notebook(run_dir: str | Path) -> str:
    """Return a marimo notebook; no model calls and no arbitrary code execution.

    The notebook embeds a sanitized snapshot of validated saved measurements,
    and resolves artifact paths relative to the run directory at runtime.
    """
    snapshot = _snapshot(Path(run_dir))
    # No extracted text or raw source files are embedded in the notebook.
    serialized = json.dumps(snapshot, ensure_ascii=True, allow_nan=False)
    # repr prevents breaking the generated Python string literal.
    template = (Path(__file__).parent / "templates" / "notebook.py.tmpl").read_text(encoding="utf-8")
    return template.replace("__D37_SNAPSHOT__", repr(serialized))
