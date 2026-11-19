"""Local execution context handed to tested tools. Never sent to the model.

Tool signature::

    def profile_table(source: SourceRef, context: ToolContext) -> ToolResult
    def profile_image_collection(sources: list[SourceRef], context: ToolContext) -> ToolResult

Tools must:
  * open inputs only through ``context.resolve_source(source)``;
  * write files only under ``context.output_dir`` (use ``context.artifact``);
  * return ``ToolResult(result_id=context.result_id,
    component_id=context.component_id, ...)``.

ArtifactRef paths returned by a tool are relative to ``output_dir``. The
scheduler validates them and rewrites them to run-relative paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from .contracts import ArtifactRef, SourceRef, _relative_path


class SourceChangedError(RuntimeError):
    """The file differs from the inventory entry the job was planned with."""


@dataclass(frozen=True)
class ToolLimits:
    """Resource bounds tools should honour when reading and sampling."""

    max_bytes_read: int = 512 * 1024 * 1024
    max_sample_rows: int = 100_000
    # image limits use the names read by tools/images.py
    max_decode_pixels: int = 16_000_000
    max_decode_bytes: int = 96 * 1024 * 1024
    max_sample_pixels: int = 100_000
    preview_max_side: int = 800
    max_text_chars: int = 2_000_000
    max_collection_files: int = 500
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolContext:
    dataset_root: Path
    output_dir: Path
    component_id: str
    result_id: str
    seed: int = 0
    limits: ToolLimits = field(default_factory=ToolLimits)
    check_unchanged: bool = True

    def resolve_source(self, source: SourceRef) -> Path:
        """Return the absolute path of an approved input inside dataset_root."""
        source.validate()
        root = Path(self.dataset_root).resolve(strict=True)
        path = (root / source.relative_path).resolve(strict=True)
        if not path.is_relative_to(root):
            raise PermissionError(f"Source escapes the dataset root: {source.relative_path}")
        if not path.is_file():
            raise PermissionError(f"Source is not a regular file: {source.relative_path}")
        if self.check_unchanged:
            stat = path.stat()
            if (stat.st_size, stat.st_mtime_ns) != (source.size_bytes, source.mtime_ns):
                raise SourceChangedError(f"Source changed since discovery: {source.relative_path}")
        return path

    def artifact_path(self, relative_path: str) -> Path:
        """A safe path for a new file under output_dir; parent dirs are created."""
        _relative_path(relative_path)
        out = Path(self.output_dir).resolve()
        path = (out / PurePosixPath(relative_path)).resolve()
        if not path.is_relative_to(out) or path == out:
            raise PermissionError(f"Artifact escapes the output directory: {relative_path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def artifact(self, relative_path: str, media_type: str, artifact_id: str | None = None) -> ArtifactRef:
        """Reference a file the tool already wrote under output_dir."""
        self.artifact_path(relative_path)
        stem = PurePosixPath(relative_path).as_posix().replace("/", "_")
        return ArtifactRef(artifact_id or f"{self.result_id}:{stem}", relative_path, media_type)
