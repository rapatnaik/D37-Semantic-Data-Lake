"""Stand-in tools for runtime tests; they follow the ToolContext contract."""

import os
import time

from agents.investigator.contracts import ArtifactRef, Coverage, ToolResult


def _result(source, context, **values):
    defaults = dict(
        result_id=context.result_id, component_id=context.component_id, status="complete",
        inputs=[source.source_id], method="fake", parameters={},
        coverage=Coverage("full", "files", 1, 1, "whole file"), measurements={},
    )
    defaults.update(values)
    return ToolResult(**defaults)


def count_lines(source, context):
    text = context.resolve_source(source).read_text(encoding="utf-8")
    count = len(text.splitlines())
    context.artifact_path("summary/lines.txt").write_text(f"{count}\n", encoding="utf-8")
    return _result(source, context, method="fake_count_lines",
                   coverage=Coverage("full", "rows", count, count, "all lines"),
                   measurements={"line_count": count},
                   artifacts=[context.artifact("summary/lines.txt", "text/plain")])


def explode(source, context):
    raise RuntimeError("boom " + os.environ.get("NRP_KEY", ""))


def hang(source, context):
    time.sleep(120)


def wrong_ids(source, context):
    result = _result(source, context)
    result.result_id = "not-the-scheduler-id"
    return result


def unsafe_artifact(source, context):
    return _result(source, context, artifacts=[ArtifactRef("x", "missing.png", "image/png")])


def not_a_result(source, context):
    return {"status": "complete"}


def collection(sources, context):
    return ToolResult(
        result_id=context.result_id, component_id=context.component_id, status="complete",
        inputs=[s.source_id for s in sources], method="fake_collection", parameters={},
        coverage=Coverage("full", "files", len(sources), len(sources), "all files"),
        measurements={"file_count": len(sources)},
    )
