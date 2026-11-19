"""Run model-proposed analysis code in an isolated worker and validate the output.

``execute_analysis(request, context) -> ExecutionResult``

An ``AnalysisRequest`` grants nothing by itself. This module decides what the
code may read (only the requested inventory sources), where it may write (one
dedicated ``outputs/`` folder), and how long and how much it may use.

Backends
  docker   no network, no credentials, read-only root filesystem and inputs,
           memory/CPU/PID limits, all capabilities dropped, unprivileged user.
  process  development fallback without Docker. Credentials are stripped from
           the environment and rlimits are applied, but network access is NOT
           blocked and memory limits are best-effort on macOS. Results say so.

Everything is retained under ``analyses/<job-id>/``: the request, code, logs,
validated outputs, worker environment versions, and ``result.json``.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from .config import Config, redact
from .contracts import (
    SCHEMA_VERSION, AnalysisRequest, ArtifactRef, Contract, Inventory, SourceRef, _require, _text,
)

WORKER_PATH = Path(__file__).with_name("worker.py")
CONTAINER_WORKER = "/opt/d37/worker.py"
VERIFY_NOTE = "Successful execution does not establish correctness; verify findings before reporting them."
PROCESS_NOTE = (
    "Process backend: credentials were removed and rlimits applied, but network access "
    "was not blocked and memory limits are best-effort on this OS."
)
OUTPUT_MEDIA_TYPES = {
    ".json": "application/json",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".png": "image/png",
    ".parquet": "application/vnd.apache.parquet",
}
_CUSTOM_CODE_SLOT = threading.BoundedSemaphore(1)


@dataclass
class ExecutionResult(Contract):
    job_id: str
    status: str
    request: AnalysisRequest
    backend: str
    attempt: int
    exit_code: int | None
    duration_seconds: float
    outputs: list[ArtifactRef] = field(default_factory=list)
    logs: list[ArtifactRef] = field(default_factory=list)
    error: str | None = None
    input_fingerprints: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    repair_of: str | None = None
    schema_version: str = SCHEMA_VERSION

    STATUSES: ClassVar[frozenset[str]] = frozenset({"succeeded", "failed", "timed_out", "rejected", "unsupported"})

    def _check(self) -> None:
        _require(self.schema_version == SCHEMA_VERSION, "Unsupported execution schema version")
        _text(self.job_id, "job_id")
        _require(self.status in self.STATUSES, "Invalid execution status")
        _require(self.backend in {"docker", "process", "none"}, "Invalid backend")
        _require(self.attempt >= 0 and self.duration_seconds >= 0, "attempt and duration must be nonnegative")
        if self.status != "succeeded":
            _require(bool(self.error) or any(t.strip() for t in self.limitations), "Unsuccessful runs must explain why")
        paths = [a.relative_path for a in self.outputs + self.logs]
        _require(len(paths) == len(set(paths)), "Duplicate output paths")

    @property
    def succeeded(self) -> bool:
        return self.status == "succeeded"


@dataclass
class ExecutionContext:
    """Local-only context; never sent to the model."""

    run_dir: Path
    dataset_root: Path
    inventory: Inventory
    config: Config
    job_id: str | None = None
    attempt: int = 0
    repair_of: str | None = None
    seed: int | None = None
    on_event: Any = None  # optional callable(kind, **fields)

    def emit(self, kind: str, **fields: Any) -> None:
        if callable(self.on_event):
            self.on_event(kind, **fields)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _job_id(request: AnalysisRequest, analyses: Path) -> str:
    digest = hashlib.sha256(request.to_json().encode()).hexdigest()[:10]
    number = 1 + sum(1 for _ in analyses.glob("a[0-9][0-9][0-9]*"))
    while True:
        candidate = f"a{number:03d}-{digest}"
        if not (analyses / candidate).exists():
            return candidate
        number += 1


def _resolve_inputs(request: AnalysisRequest, context: ExecutionContext) -> tuple[list[tuple[SourceRef, Path]], str | None]:
    sources = {s.source_id: s for s in context.inventory.sources}
    unknown = [i for i in request.input_ids if i not in sources]
    if unknown:
        return [], f"Unknown input IDs (only inventory source IDs are allowed): {unknown}"
    root = Path(context.dataset_root).resolve(strict=True)
    resolved = []
    total = 0
    for source_id in request.input_ids:
        source = sources[source_id]
        try:
            path = (root / source.relative_path).resolve(strict=True)
        except OSError:
            return [], f"Input no longer exists: {source.relative_path}"
        if not path.is_relative_to(root) or not path.is_file():
            return [], f"Input is outside the dataset root or not a file: {source.relative_path}"
        stat = path.stat()
        if (stat.st_size, stat.st_mtime_ns) != (source.size_bytes, source.mtime_ns):
            return [], f"Input changed since discovery; rerun discovery first: {source.relative_path}"
        total += stat.st_size
        resolved.append((source, path))
    if total > context.config.limits.max_input_bytes:
        return [], f"Selected inputs total {total} bytes, above limits.max_input_bytes"
    return resolved, None


def _result(context: ExecutionContext, job_id: str, request: AnalysisRequest, status: str, *,
            backend: str = "none", error: str | None = None, limitations: list[str] | None = None,
            **values: Any) -> ExecutionResult:
    return ExecutionResult(
        job_id=job_id, status=status, request=request, backend=backend, attempt=context.attempt,
        exit_code=values.pop("exit_code", None), duration_seconds=float(values.pop("duration_seconds", 0.0)),
        error=error, limitations=limitations or [], repair_of=context.repair_of, **values,
    )


def execute_analysis(request: AnalysisRequest, context: ExecutionContext) -> ExecutionResult:
    request.validate()
    run_dir = Path(context.run_dir).resolve()
    analyses = run_dir / "analyses"
    analyses.mkdir(parents=True, exist_ok=True)
    job_id = context.job_id or _job_id(request, analyses)
    job_dir = analyses / job_id
    job_dir.mkdir()
    (job_dir / "request.json").write_text(request.to_json(), encoding="utf-8")
    (job_dir / "code.py").write_text(request.code, encoding="utf-8")
    context.emit("analysis_started", job_id=job_id, attempt=context.attempt, repair_of=context.repair_of)

    limits = context.config.limits
    if limits.custom_code_workers < 1:
        result = _result(context, job_id, request, "unsupported",
                         limitations=["Custom-code execution is disabled (limits.custom_code_workers = 0)."])
        return _finish(result, job_dir, context)
    inputs, problem = _resolve_inputs(request, context)
    if problem:
        return _finish(_result(context, job_id, request, "rejected", error=problem), job_dir, context)

    backend = context.config.execution.backend
    if backend == "docker":
        problem = _docker_unavailable(context.config)
        if problem:
            return _finish(_result(context, job_id, request, "unsupported", backend="docker",
                                   limitations=[problem]), job_dir, context)

    fingerprints = {
        s.source_id: {"relative_path": s.relative_path, "size_bytes": s.size_bytes,
                      "mtime_ns": s.mtime_ns, "sha256": _sha256(p)}
        for s, p in inputs
    }
    for name in ("outputs", "meta", "inputs"):
        (job_dir / name).mkdir()
    seed = context.config.seed if context.seed is None else context.seed
    sandbox = {
        "inputs": {s.source_id: {"path": f"inputs/{s.relative_path}", "relative_path": s.relative_path}
                   for s, _ in inputs},
        "parameters": request.parameters,
        "seed": seed,
    }
    (job_dir / "sandbox.json").write_text(json.dumps(sandbox, indent=2), encoding="utf-8")

    with _CUSTOM_CODE_SLOT:
        started = time.monotonic()
        if backend == "docker":
            exit_code, timed_out = _run_docker(job_dir, inputs, context)
        else:
            exit_code, timed_out = _run_process(job_dir, inputs, context)
        duration = round(time.monotonic() - started, 3)

    return _collect(context, job_id, job_dir, request, backend, exit_code, timed_out, duration, fingerprints)


# ----- backends ----------------------------------------------------------------

def _sandbox_env(job_dir: Path) -> dict[str, str]:
    """A fresh environment: nothing inherited, so no credentials."""
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(job_dir / "meta"),
        "LANG": "C.UTF-8",
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "MPLBACKEND": "Agg",
        "MPLCONFIGDIR": str(job_dir / "meta" / "mpl"),
    }


def _rlimits(limits: Any) -> Any:
    def apply() -> None:
        import resource  # POSIX only

        def setlimit(kind: int, value: int) -> None:
            try:
                resource.setrlimit(kind, (value, value))
            except (ValueError, OSError):
                pass  # unsupported on this OS; Docker enforces these properly

        setlimit(resource.RLIMIT_CPU, int(limits.analysis_timeout_seconds) + 1)
        setlimit(resource.RLIMIT_FSIZE, int(limits.max_output_bytes))
        setlimit(resource.RLIMIT_CORE, 0)
        setlimit(resource.RLIMIT_NOFILE, 256)
        if sys.platform.startswith("linux"):
            setlimit(resource.RLIMIT_AS, int(limits.analysis_memory_mb) * 1024 * 1024)
    return apply


def _run_process(job_dir: Path, inputs: list[tuple[SourceRef, Path]], context: ExecutionContext) -> tuple[int | None, bool]:
    for source, path in inputs:
        target = job_dir / "inputs" / source.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)  # a copy: chmod below never touches originals
        target.chmod(0o444)
    for name in ("request.json", "sandbox.json", "code.py"):
        (job_dir / name).chmod(0o444)
    limits = context.config.limits
    command = [sys.executable, "-I", str(WORKER_PATH), str(job_dir)]
    with (job_dir / "stdout.log").open("wb") as out, (job_dir / "stderr.log").open("wb") as err:
        process = subprocess.Popen(
            command, cwd=job_dir, env=_sandbox_env(job_dir), stdin=subprocess.DEVNULL,
            stdout=out, stderr=err, start_new_session=True,
            preexec_fn=_rlimits(limits) if os.name == "posix" else None,
        )
        try:
            return process.wait(timeout=limits.analysis_timeout_seconds), False
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            return None, True
        finally:
            for source, _ in inputs:  # copies are disposable; keep fingerprints only
                copy = job_dir / "inputs" / source.relative_path
                if copy.exists():
                    copy.chmod(0o644)
                    copy.unlink()


def _docker_unavailable(config: Config) -> str | None:
    docker = config.execution.docker_command
    if shutil.which(docker) is None:
        return "Docker is not installed; set execution.backend = 'process' for development only."
    try:
        found = subprocess.run([docker, "image", "inspect", config.execution.image],
                               capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return "Docker did not respond."
    if found.returncode != 0:
        return (f"Worker image {config.execution.image} is missing; build it with "
                f"`docker build -f containers/investigator/Dockerfile -t {config.execution.image} .`")
    return None


def _mount(src: Path, dst: str, readonly: bool) -> str:
    buffer = io.StringIO()
    fields = ["type=bind", f"src={src}", f"dst={dst}"] + (["readonly"] if readonly else [])
    csv.writer(buffer, lineterminator="").writerow(fields)  # quotes paths containing commas
    return buffer.getvalue()


def docker_command(job_dir: Path, inputs: list[tuple[SourceRef, Path]], config: Config, name: str) -> list[str]:
    limits = config.limits
    command = [
        config.execution.docker_command, "run", "--rm", "--name", name, "--pull", "never",
        "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--user", "65534:65534",
        "--memory", f"{limits.analysis_memory_mb}m", "--memory-swap", f"{limits.analysis_memory_mb}m",
        "--cpus", str(limits.analysis_cpus), "--pids-limit", str(limits.analysis_pids),
        "--ulimit", f"fsize={limits.max_output_bytes}", "--ulimit", "nofile=256:256",
        "--tmpfs", "/tmp:rw,size=64m,mode=1777", "--workdir", "/work",
        "-e", "HOME=/tmp", "-e", "PYTHONHASHSEED=0", "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", "MPLBACKEND=Agg", "-e", "MPLCONFIGDIR=/tmp/mpl",
        "--mount", _mount(WORKER_PATH.resolve(), CONTAINER_WORKER, True),
        "--mount", _mount(job_dir / "code.py", "/work/code.py", True),
        "--mount", _mount(job_dir / "sandbox.json", "/work/sandbox.json", True),
        "--mount", _mount(job_dir / "outputs", "/work/outputs", False),
        "--mount", _mount(job_dir / "meta", "/work/meta", False),
    ]
    for source, path in inputs:
        command += ["--mount", _mount(path, f"/work/inputs/{source.relative_path}", True)]
    command += [config.execution.image, "python", "-I", CONTAINER_WORKER, "/work"]
    return command


def _run_docker(job_dir: Path, inputs: list[tuple[SourceRef, Path]], context: ExecutionContext) -> tuple[int | None, bool]:
    config = context.config
    for name in ("outputs", "meta"):
        (job_dir / name).chmod(0o777)  # writable by the container's unprivileged user
    container = f"d37-{job_dir.name}-{os.getpid()}"
    command = docker_command(job_dir, inputs, config, container)
    (job_dir / "docker_command.json").write_text(json.dumps(command, indent=2), encoding="utf-8")
    with (job_dir / "stdout.log").open("wb") as out, (job_dir / "stderr.log").open("wb") as err:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
        try:
            # allow container start-up time on top of the analysis budget
            return process.wait(timeout=config.limits.analysis_timeout_seconds + 30), False
        except subprocess.TimeoutExpired:
            subprocess.run([config.execution.docker_command, "kill", container],
                           capture_output=True, timeout=30, check=False)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            return None, True


# ----- validation --------------------------------------------------------------

def _valid_output(path: Path, media_type: str) -> str | None:
    if media_type == "application/json":
        def strict(value: str) -> Any:
            raise ValueError(f"non-finite number {value}")
        try:
            json.loads(path.read_text(encoding="utf-8"), parse_constant=strict)
        except (ValueError, UnicodeDecodeError) as error:
            return f"invalid JSON ({type(error).__name__})"
    elif media_type == "image/png":
        with path.open("rb") as handle:
            if handle.read(8) != b"\x89PNG\r\n\x1a\n":
                return "not a PNG file"
    elif media_type == "application/vnd.apache.parquet":
        with path.open("rb") as handle:
            if handle.read(4) != b"PAR1":
                return "not a Parquet file"
    elif media_type.startswith("text/"):
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return "not UTF-8 text"
    return None


def validate_outputs(out_dir: Path, run_dir: Path, limits: Any, expected: list[str]) -> tuple[list[ArtifactRef], list[str]]:
    """Return accepted outputs and problems. Rejected files are removed."""
    accepted: list[ArtifactRef] = []
    problems: list[str] = []
    total = 0
    root = out_dir.resolve()
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs):
            if (Path(directory) / name).is_symlink():
                problems.append(f"Symlinked directory rejected: {name}")
                (Path(directory) / name).unlink()
        dirs[:] = sorted(d for d in dirs if (Path(directory) / d).exists())
        for name in sorted(files):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink() or not path.is_file():
                problems.append(f"Non-regular output rejected: {relative}")
                path.unlink()
                continue
            media_type = OUTPUT_MEDIA_TYPES.get(path.suffix.lower())
            if media_type is None:
                problems.append(f"Unsupported output type rejected: {relative}")
                path.unlink()
                continue
            size = path.stat().st_size
            total += size
            if len(accepted) >= limits.max_output_files or total > limits.max_output_bytes:
                problems.append(f"Output limit exceeded; rejected: {relative}")
                path.unlink()
                continue
            invalid = _valid_output(path, media_type)
            if invalid:
                problems.append(f"Invalid output rejected ({invalid}): {relative}")
                path.unlink()
                continue
            run_relative = path.relative_to(run_dir.resolve()).as_posix()
            try:
                accepted.append(ArtifactRef(f"{run_relative}", run_relative, media_type))
            except ValueError:
                problems.append(f"Unsafe output path rejected: {relative}")
                path.unlink()
    produced = {a.media_type for a in accepted}
    for media_type in expected:
        if media_type not in produced:
            problems.append(f"Expected output not produced: {media_type}")
    return accepted, problems


def _truncate_log(path: Path, limit: int, config: Config, job_dir: Path) -> None:
    if not path.exists():
        path.write_text("", encoding="utf-8")
        return
    data = path.read_bytes()
    note = b""
    if len(data) > limit:
        data, note = data[:limit], f"\n[truncated: {len(data) - limit} more bytes]\n".encode()
    text = data.decode("utf-8", errors="replace").replace(str(job_dir), "/work")
    path.write_text(redact(text, config) + note.decode(), encoding="utf-8")


def _collect(context: ExecutionContext, job_id: str, job_dir: Path, request: AnalysisRequest, backend: str,
             exit_code: int | None, timed_out: bool, duration: float, fingerprints: dict[str, Any]) -> ExecutionResult:
    config = context.config
    run_dir = Path(context.run_dir).resolve()
    for name in ("stdout.log", "stderr.log"):
        _truncate_log(job_dir / name, config.limits.max_log_bytes, config, job_dir)
    logs = [ArtifactRef(f"analyses/{job_id}/{n}", f"analyses/{job_id}/{n}", "text/plain")
            for n in ("stdout.log", "stderr.log")]
    worker_status: dict[str, Any] = {}
    status_path = job_dir / "meta" / "worker_status.json"
    if status_path.is_file() and not status_path.is_symlink():
        try:
            worker_status = json.loads(status_path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            worker_status = {}
    environment = {"backend": backend, "python": worker_status.get("python"),
                   "packages": worker_status.get("packages", {}), "platform": worker_status.get("platform")}
    if backend == "docker":
        environment["image"] = config.execution.image

    outputs, problems = validate_outputs(job_dir / "outputs", run_dir, config.limits, request.expected_outputs)
    limitations = [VERIFY_NOTE] + ([PROCESS_NOTE] if backend == "process" else []) + problems
    error = None
    if timed_out:
        status = "timed_out"
        error = f"Analysis exceeded {config.limits.analysis_timeout_seconds} s and was stopped."
    elif exit_code != 0:
        status = "failed"
        detail = worker_status.get("error_type"), worker_status.get("error")
        error = (f"{detail[0]}: {detail[1]}" if detail[0] else f"Worker exited with code {exit_code}")
        tail = worker_status.get("traceback") or (job_dir / "stderr.log").read_text(encoding="utf-8")[-4000:]
        error = redact((error + "\n" + str(tail)).replace(str(job_dir), "/work"), config)[-6000:]
    elif problems:
        status = "failed"
        error = "Outputs failed validation: " + "; ".join(problems)
    else:
        status = "succeeded"
    result = _result(context, job_id, request, status, backend=backend, error=error, limitations=limitations,
                     exit_code=exit_code, duration_seconds=duration, outputs=outputs, logs=logs,
                     input_fingerprints=fingerprints, environment=environment)
    return _finish(result, job_dir, context)


def _finish(result: ExecutionResult, job_dir: Path, context: ExecutionContext) -> ExecutionResult:
    path = job_dir / "result.json"
    path.write_text(result.to_json(), encoding="utf-8")
    context.emit("analysis_finished", job_id=result.job_id, status=result.status,
                 attempt=result.attempt, outputs=len(result.outputs))
    return result


def load_execution_result(path: Path) -> ExecutionResult:
    return ExecutionResult.from_json(Path(path).read_text(encoding="utf-8"))
