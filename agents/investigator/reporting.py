"""Render evidence-linked Markdown and offline marimo notebooks from saved runs.

No model calls, source-file execution, or custom-code execution occur here.
The scheduler owns revision creation and writes returned strings atomically.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
    for job in jobs.values():
        if not isinstance(job, dict):
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
                except (ValueError, OSError):
                    pass
        for kind, destination in (("metadata", metadata), ("semantics", semantics)):
            if job.get("kind") == kind and kind in outputs:
                file = _safe_file(root, outputs[kind])
                if file and (data := _load_json(file)) is not None:
                    destination[component_id] = data
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
            "run_id": root.name}


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").replace("`", "'")


def _json_block(data: Any) -> str:
    return "```json\n" + json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n```"


def _markdown(data: dict[str, Any]) -> str:
    inventory = data["inventory"]
    sources = {s["source_id"]: s["relative_path"] for s in inventory["sources"]}
    lines = [f"# D37 investigation — {data['run_id']}", "",
             "Generated from saved evidence only. No cloud reasoning or generated code was executed during reporting.", "",
             "## Inventory and coverage", "",
             f"Sources: {len(sources)}; components: {len(inventory['components'])}.", "",
             "| Component | Kind | Sources | Status | Coverage |", "|---|---|---|---|---|"]
    for comp in inventory["components"]:
        cid = comp["component_id"]
        result = data["results"].get(cid, {})
        coverage = result.get("coverage", {})
        summary = f"{coverage.get('mode', 'not measured')}: {coverage.get('examined', '?')}/{coverage.get('total', '?')} {coverage.get('unit', '')}"
        lines.append(f"| `{_cell(cid)}` | {_cell(comp['kind'])} | {_cell(', '.join(sources.get(s, s) for s in comp['source_ids']))} | {_cell(result.get('status', 'not run'))} | {_cell(summary)} |")
    lines.extend(["", "## Measurements and evidence", ""])
    for comp in inventory["components"]:
        cid = comp["component_id"]
        lines += [f"### Component `{_cell(cid)}`", ""]
        result = data["results"].get(cid)
        if not result:
            lines += ["No validated tool result is available.", ""]
            continue
        lines += [f"**Method:** `{_cell(result['method'])}`. **Status:** {result['status']}.", "",
                  "**Coverage:** " + _json_block(result["coverage"]), "",
                  "**Measured facts:**", "", _json_block(result["measurements"]), ""]
        if result["artifacts"]:
            lines += ["**Saved artifacts** (paths relative to run directory):", ""]
            lines += [f"- `{_cell(a['relative_path'])}` ({_cell(a['media_type'])})" for a in result["artifacts"]]
            lines.append("")
        if cid in data["metadata"]:
            lines += ["**Assembled metadata (not independently remeasured):**", "", _json_block(data["metadata"][cid]), ""]
        if cid in data["semantics"]:
            lines += ["**Saved model interpretation (not independently verified):**", "", _json_block(data["semantics"][cid]), ""]
        if result["limitations"]:
            lines += ["**Limitations and uncertainty:**", ""]
            lines += [f"- {_cell(x)}" for x in result["limitations"]]
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
