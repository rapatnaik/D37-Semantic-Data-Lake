"""Shared inputs and outputs for the directory investigator.

These contracts describe data exchanged between discovery, analysis, metadata,
model reasoning, and reporting. They do not open datasets or execute tools.
Paths use POSIX separators and are relative to the dataset or run directory.
Runtime code must additionally enforce containment after resolving symlinks.
"""

from __future__ import annotations

import json
import math
import types
from dataclasses import asdict, dataclass, field, fields
from pathlib import PurePosixPath
from typing import Any, ClassVar, get_args, get_origin, get_type_hints

SCHEMA_VERSION = "1.0"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _text(value: str, name: str) -> None:
    _require(bool(value.strip()), f"{name} must not be blank")


def _relative_path(value: str) -> None:
    path = PurePosixPath(value)
    _require(
        bool(value) and not path.is_absolute() and ".." not in path.parts
        and "\\" not in value and ":" not in value and "\x00" not in value
        and str(path) != ".",
        f"Expected a relative path without traversal: {value!r}",
    )


def _json_value(value: Any, name: str) -> None:
    """Reject objects, non-string keys, and nonfinite numbers before saving."""
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _json_value(item, name)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _json_value(item, name)
        return
    raise ValueError(f"{name} must contain only finite JSON-compatible values")


def _typed(value: Any, annotation: Any, name: str, *, decode: bool) -> Any:
    """Validate annotations; reconstruct nested contracts when decoding JSON."""
    origin = get_origin(annotation)
    args = get_args(annotation)
    if annotation is Any:
        _json_value(value, name)
        return value
    if origin is types.UnionType:
        for choice in args:
            try:
                return _typed(value, choice, name, decode=decode)
            except ValueError:
                pass
        raise ValueError(f"{name} has an unexpected type")
    if origin is list:
        _require(type(value) is list, f"{name} must be a list")
        return [_typed(item, args[0], name, decode=decode) for item in value]
    if origin is dict:
        _require(type(value) is dict, f"{name} must be an object")
        return {
            _typed(key, args[0], name, decode=decode):
            _typed(item, args[1], name, decode=decode)
            for key, item in value.items()
        }
    if isinstance(annotation, type) and issubclass(annotation, Contract):
        if decode and type(value) is dict:
            return annotation.from_dict(value)
        _require(isinstance(value, annotation), f"{name} must be {annotation.__name__}")
        value.validate()
        return value
    _require(type(value) is annotation, f"{name} must be {annotation.__name__}")
    return value


class Contract:
    """Validation and serialization shared by all public dataclasses.

    Validation runs on construction and again before serialization, including
    after callers modify mutable lists or dictionaries. Errors are ValueError.
    """

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        hints = get_type_hints(type(self))
        for item in fields(self):
            _typed(getattr(self, item.name), hints[item.name], item.name, decode=False)
        self._check()

    def _check(self) -> None:
        pass

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, allow_nan=False) + "\n"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Any:
        _require(type(data) is dict, f"{cls.__name__} must be an object")
        names = {item.name for item in fields(cls)}
        _require(not (data.keys() - names), f"Unknown fields for {cls.__name__}: {data.keys() - names}")
        hints = get_type_hints(cls)
        values = {
            key: _typed(value, hints[key], key, decode=True)
            for key, value in data.items()
        }
        try:
            return cls(**values)
        except TypeError as error:
            raise ValueError(f"Invalid {cls.__name__} fields: {error}") from error

    @classmethod
    def from_json(cls, text: str) -> Any:
        def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                _require(key not in result, f"Duplicate JSON key: {key}")
                result[key] = value
            return result

        return cls.from_dict(json.loads(text, object_pairs_hook=unique_object))


@dataclass
class SourceRef(Contract):
    """A physical file, with its path relative to the selected dataset root."""

    source_id: str
    relative_path: str
    format: str
    size_bytes: int
    mtime_ns: int
    sha256: str | None = None

    def _check(self) -> None:
        _text(self.source_id, "source_id")
        _text(self.format, "format")
        _relative_path(self.relative_path)
        _require(self.size_bytes >= 0 and self.mtime_ns >= 0, "File size and mtime must be nonnegative")
        if self.sha256 is not None:
            _require(len(self.sha256) == 64 and all(c in "0123456789abcdef" for c in self.sha256), "sha256 must be a lowercase hexadecimal SHA-256 digest")


@dataclass
class ComponentRef(Contract):
    """A logical table, image/document collection, or unclassified input."""

    component_id: str
    kind: str
    source_ids: list[str]
    selector: dict[str, Any] = field(default_factory=dict)

    def _check(self) -> None:
        _text(self.component_id, "component_id")
        _require(self.kind in {"table", "images", "documents", "unknown"}, "Invalid component kind")
        _require(bool(self.source_ids) and len(set(self.source_ids)) == len(self.source_ids), "Component sources must be nonempty and unique")
        for source_id in self.source_ids:
            _text(source_id, "source_id")


@dataclass
class Inventory(Contract):
    sources: list[SourceRef]
    components: list[ComponentRef]
    limitations: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def _check(self) -> None:
        _require(self.schema_version == SCHEMA_VERSION, "Unsupported inventory schema version")
        ids = [source.source_id for source in self.sources]
        paths = [source.relative_path for source in self.sources]
        components = [component.component_id for component in self.components]
        _require(len(set(ids)) == len(ids), "Duplicate source IDs")
        _require(len(set(paths)) == len(paths), "Duplicate source paths")
        _require(len(set(components)) == len(components), "Duplicate component IDs")
        for component in self.components:
            _require(set(component.source_ids) <= set(ids), "Component references unknown sources")


@dataclass
class Coverage(Contract):
    """Scope of the measurement, including how any sample was selected."""

    mode: str
    unit: str
    examined: int
    total: int | None
    selection: str
    seed: int | None = None

    def _check(self) -> None:
        _require(self.mode in {"full", "sample", "none"}, "Invalid coverage mode")
        _require(self.unit in {"rows", "files", "pages", "pixels"}, "Invalid coverage unit")
        _text(self.selection, "selection")
        _require(self.examined >= 0, "examined must be nonnegative")
        if self.total is not None:
            _require(self.total >= self.examined, "total must be at least examined")
        if self.mode == "full":
            _require(self.total == self.examined, "Full coverage requires total == examined")
        if self.mode == "none":
            _require(self.examined == 0, "No coverage requires examined == 0")


@dataclass
class ArtifactRef(Contract):
    """A saved output; published paths are relative to the run directory."""

    artifact_id: str
    relative_path: str
    media_type: str

    def _check(self) -> None:
        _text(self.artifact_id, "artifact_id")
        _relative_path(self.relative_path)
        _require("/" in self.media_type and not any(c.isspace() for c in self.media_type), "Expected a media type such as image/png")


@dataclass
class ToolResult(Contract):
    result_id: str
    component_id: str
    status: str
    inputs: list[str]
    method: str
    parameters: dict[str, Any]
    coverage: Coverage
    measurements: dict[str, Any]
    artifacts: list[ArtifactRef] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    STATUSES: ClassVar[frozenset[str]] = frozenset({"complete", "partial", "unsupported", "failed", "deferred"})

    def _check(self) -> None:
        _require(self.schema_version == SCHEMA_VERSION, "Unsupported result schema version")
        for name in ("result_id", "component_id", "method"):
            _text(getattr(self, name), name)
        _require(self.status in self.STATUSES, "Invalid analysis status")
        _require(bool(self.inputs) and len(set(self.inputs)) == len(self.inputs), "Result inputs must be nonempty and unique")
        for source_id in self.inputs:
            _text(source_id, "input source ID")
        ids = [artifact.artifact_id for artifact in self.artifacts]
        paths = [artifact.relative_path for artifact in self.artifacts]
        _require(len(set(ids)) == len(ids) and len(set(paths)) == len(paths), "Duplicate artifacts")
        if self.status != "complete":
            _require(any(text.strip() for text in self.limitations), "Incomplete results must explain their limitations")

    def validate_references(self, inventory: Inventory) -> None:
        """Check references when the coordinator has the complete inventory."""
        self.validate()
        inventory.validate()
        components = {item.component_id: item for item in inventory.components}
        _require(self.component_id in components, "Result references an unknown component")
        _require(set(self.inputs) <= {item.source_id for item in inventory.sources}, "Result references unknown input sources")
        _require(bool(set(self.inputs) & set(components[self.component_id].source_ids)), "Result must reference a source of its component")


@dataclass
class AnalysisRequest(Contract):
    """Model-proposed analysis; contains IDs, never execution permissions."""

    question: str
    code: str
    input_ids: list[str]
    parameters: dict[str, Any]
    expected_outputs: list[str]

    def _check(self) -> None:
        _text(self.question, "question")
        _text(self.code, "code")
        _require(bool(self.input_ids) and len(set(self.input_ids)) == len(self.input_ids), "Analysis inputs must be nonempty and unique")
        for source_id in self.input_ids:
            _text(source_id, "input source ID")
        _require(bool(self.expected_outputs), "Declare at least one expected output type")
        for media_type in self.expected_outputs:
            _require("/" in media_type and not any(c.isspace() for c in media_type), "Expected output must be a media type")
