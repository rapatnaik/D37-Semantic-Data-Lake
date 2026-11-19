"""Run directories, JSON checkpoints, and the JSONL event log.

Layout under ``<state_dir>/runs/<run-id>/``::

    manifest.json          settings (no credentials), environment versions
    inventory.json         latest discovered inventory
    checkpoint.json        job states, fingerprints, budgets (atomic rewrite)
    events.jsonl           append-only history
    results/<job>/v001.json      versioned ToolResults
    metadata/<component>/v001.json, semantics/<component>/v001.json
    analyses/<job-id>/     request, code, outputs, logs, result
    artifacts/<job>/v001/  files produced by tools
    sessions/<id>.json     follow-up questions and their outcomes
    reports/revision-001/  report.md, notebook.py
    logs/                  tool tracebacks and captured output

Writes go through a temporary file plus ``os.replace`` so a crash leaves the
previous checkpoint intact; a torn final event line is ignored on reading.
"""

from __future__ import annotations

import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Iterator

from .config import Config, config_from_dict, redact
from .contracts import Inventory

STATE_SCHEMA_VERSION = "1.0"
RUN_SUBDIRS = ("results", "metadata", "semantics", "analyses", "artifacts", "sessions", "reports", "logs")
_TRACKED_PACKAGES = ("numpy", "pandas", "pyarrow", "matplotlib", "pillow", "tifffile", "openpyxl", "marimo")


class RunLockedError(RuntimeError):
    """Another live process is working on this run."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n"
    write_text_atomic(path, text)


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def environment_versions(config: Config | None = None) -> dict[str, Any]:
    packages = {}
    for name in _TRACKED_PACKAGES:
        try:
            packages[name] = importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            pass
    info: dict[str, Any] = {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "packages": packages,
    }
    if config is not None and config.execution.backend == "docker":
        info["docker"] = docker_version(config.execution.docker_command)
    return info


def docker_version(command: str = "docker") -> str | None:
    if shutil.which(command) is None:
        return None
    try:
        completed = subprocess.run(
            [command, "version", "--format", "{{.Server.Version}}"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@dataclass
class RunState:
    run_dir: Path
    manifest: dict[str, Any]
    checkpoint: dict[str, Any]

    _event_lock = threading.Lock()

    # ----- lifecycle -------------------------------------------------------
    @classmethod
    def create(cls, state_root: Path, dataset_root: Path, config: Config, *, command: str = "run") -> "RunState":
        run_id = new_run_id()
        run_dir = Path(state_root) / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        for name in RUN_SUBDIRS:
            (run_dir / name).mkdir()
        manifest = {
            "schema_version": STATE_SCHEMA_VERSION,
            "run_id": run_id,
            "created_at": utc_now(),
            "dataset_root": str(Path(dataset_root).resolve()),
            "command": command,
            "config": config.public_dict(),
            "environment": environment_versions(config),
        }
        checkpoint = {
            "schema_version": STATE_SCHEMA_VERSION,
            "run_id": run_id,
            "status": "created",
            "jobs": {},
            "source_hashes": {},
            "model_requests_used": 0,
            "elapsed_seconds": 0.0,
            "invocations": 0,
            "report_revisions": [],
            "updated_at": utc_now(),
        }
        state = cls(run_dir, manifest, checkpoint)
        write_json_atomic(run_dir / "manifest.json", manifest)
        state.save_checkpoint()
        state.event("run_created", run_id=run_id)
        return state

    @classmethod
    def open(cls, run_dir: Path) -> "RunState":
        run_dir = Path(run_dir).resolve(strict=True)
        manifest = read_json(run_dir / "manifest.json")
        checkpoint = read_json(run_dir / "checkpoint.json")
        if manifest.get("schema_version") != STATE_SCHEMA_VERSION or checkpoint.get("schema_version") != STATE_SCHEMA_VERSION:
            raise ValueError(f"Unsupported run schema in {run_dir}")
        return cls(run_dir, manifest, checkpoint)

    @property
    def run_id(self) -> str:
        return self.manifest["run_id"]

    @property
    def dataset_root(self) -> Path:
        return Path(self.manifest["dataset_root"])

    def config(self) -> Config:
        return config_from_dict(self.manifest["config"])

    # ----- locking ---------------------------------------------------------
    def acquire_lock(self) -> None:
        lock = self.run_dir / "lock"
        for _ in range(2):
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                try:
                    pid = int(lock.read_text().strip() or 0)
                except (OSError, ValueError):
                    pid = 0
                if _pid_alive(pid) and pid != os.getpid():
                    raise RunLockedError(f"Run {self.run_id} is in use by process {pid}")
                lock.unlink(missing_ok=True)
                self.event("stale_lock_removed", pid=pid)
                continue
            with os.fdopen(fd, "w") as handle:
                handle.write(str(os.getpid()))
            return
        raise RunLockedError(f"Could not lock run {self.run_id}")

    def release_lock(self) -> None:
        lock = self.run_dir / "lock"
        try:
            if int(lock.read_text().strip() or 0) == os.getpid():
                lock.unlink()
        except (OSError, ValueError):
            pass

    # ----- events and checkpoints -----------------------------------------
    def event(self, event_type: str, /, **fields: Any) -> dict[str, Any]:
        record = {"time": utc_now(), "type": event_type, **fields}
        line = redact(json.dumps(record, sort_keys=True, allow_nan=False, default=str))
        with self._event_lock:
            with (self.run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
        return record

    def events(self) -> Iterator[dict[str, Any]]:
        path = self.run_dir / "events.jsonl"
        if not path.exists():
            return
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue  # torn final line after a crash

    def save_checkpoint(self) -> None:
        self.checkpoint["updated_at"] = utc_now()
        write_json_atomic(self.run_dir / "checkpoint.json", self.checkpoint)

    # ----- inventory and versioned outputs --------------------------------
    def save_inventory(self, inventory: Inventory) -> None:
        write_text_atomic(self.run_dir / "inventory.json", inventory.to_json())

    def load_inventory(self) -> Inventory | None:
        path = self.run_dir / "inventory.json"
        return Inventory.from_json(path.read_text(encoding="utf-8")) if path.exists() else None

    def save_versioned(self, area: str, name: str, text: str) -> str:
        """Save ``text`` as the next version; returns the run-relative path."""
        if area not in RUN_SUBDIRS or not name or "/" in name or name.startswith("."):
            raise ValueError(f"Invalid output location {area}/{name}")
        folder = self.run_dir / area / name
        folder.mkdir(parents=True, exist_ok=True)
        version = 1 + max((int(p.stem[1:]) for p in folder.glob("v[0-9][0-9][0-9]*.json")), default=0)
        path = folder / f"v{version:03d}.json"
        write_text_atomic(path, text)
        return path.relative_to(self.run_dir).as_posix()

    def read_relative(self, relative: str) -> str:
        path = (self.run_dir / relative).resolve()
        if not path.is_relative_to(self.run_dir.resolve()):
            raise PermissionError(relative)
        return path.read_text(encoding="utf-8")

    def new_report_revision(self) -> Path:
        reports = self.run_dir / "reports"
        number = 1 + max((int(p.name.split("-")[1]) for p in reports.glob("revision-[0-9]*")), default=0)
        path = reports / f"revision-{number:03d}"
        path.mkdir(parents=True)
        self.checkpoint.setdefault("report_revisions", []).append(path.relative_to(self.run_dir).as_posix())
        return path


def latest_run(state_root: Path) -> Path | None:
    runs = sorted((Path(state_root) / "runs").glob("*/manifest.json"))
    return runs[-1].parent if runs else None


class Stopwatch:
    def __init__(self, budget_seconds: float):
        self.start = time.monotonic()
        self.budget = budget_seconds

    def elapsed(self) -> float:
        return time.monotonic() - self.start

    def remaining(self) -> float:
        return self.budget - self.elapsed()

    def expired(self) -> bool:
        return self.remaining() <= 0
