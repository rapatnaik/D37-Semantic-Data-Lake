"""Plan, schedule, checkpoint, and resume investigation jobs.

Job graph per run (one tool job per inventory component)::

    tools -> metadata -> resolve dictionary links -> table semantics -> report

* Tool jobs are independent and run in parallel, up to ``limits.local_workers``,
  each in its own spawned process so a hung tool can be stopped.
* Every job has a fingerprint built from its inputs and implementation.
  Table semantics also depend on linked dictionary evidence, resolved after
  the metadata phase.
* Teammates' modules are resolved lazily. Until a tool exists, its components
  get a ``deferred`` ToolResult; once the module appears its code hash changes
  the fingerprint and resume runs it.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import multiprocessing
import os
import sys
import threading
import time
import traceback
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Iterator

from .config import Config, redact
from .context import ToolContext, ToolLimits
from .contracts import ArtifactRef, ComponentRef, Coverage, Inventory, SourceRef, ToolResult
from .discovery import discover
from .metadata import build_metadata
from .state import RunState, Stopwatch, write_text_atomic

ProgressFn = Callable[[dict[str, Any]], None]
TERMINAL = {"done", "removed"}
DEFAULT_SEMANTICS = "agents.investigator.semantics:build_semantic_profile"
TIFF_SEMANTICS = "agents.investigator.image_semantics:build_tiff_profile"
EVIDENCE_KINDS = {"tool", "metadata"}
INTERPRETATION_KINDS = {"semantics", "report"}


# ----- registry -----------------------------------------------------------------

@dataclass(frozen=True)
class ToolSpec:
    """``module:function`` paths. ``collection`` is used for multi-source components."""

    single: str | None
    collection: str | None = None


DEFAULT_TOOLS: dict[str, ToolSpec] = {
    "table": ToolSpec("agents.investigator.tools.tables:profile_table"),
    "images": ToolSpec("agents.investigator.tools.images:inspect_image",
                       "agents.investigator.tools.images:profile_image_collection"),
    "documents": ToolSpec("agents.investigator.tools.documents:extract_document"),
}


@dataclass(frozen=True)
class Stages:
    """Optional downstream stages; each is skipped until its module exists.

    The built-in semantic stage receives linked dictionary evidence.
    Custom stages receive (metadata, *, budget, config).
    report(run_dir: Path) -> str       Markdown
    notebook(run_dir: Path) -> str     marimo notebook source
    """

    semantics: str | None = DEFAULT_SEMANTICS
    report: str | None = "agents.investigator.reporting:render_report"
    notebook: str | None = "agents.investigator.reporting:render_notebook"


def code_hash(spec: str | None) -> str | None:
    """Hash of the module source that implements ``spec``; None when missing."""
    if not spec:
        return None
    module = spec.split(":", 1)[0]
    try:
        found = importlib.util.find_spec(module)
    except (ImportError, ValueError):
        return None
    if found is None or not found.origin or not os.path.isfile(found.origin):
        return None
    return hashlib.sha256(Path(found.origin).read_bytes()).hexdigest()[:16]


def load_callable(spec: str) -> Callable[..., Any]:
    module, _, name = spec.partition(":")
    function = getattr(importlib.import_module(module), name)
    if not callable(function):
        raise TypeError(f"{spec} is not callable")
    return function


# ----- model budget ---------------------------------------------------------------

class BudgetExhausted(RuntimeError):
    pass


class ModelBudget:
    """Shared limit on model calls: ``with budget.request(): call_model(...)``."""

    def __init__(self, max_total: int, max_concurrent: int, used: int = 0,
                 on_use: Callable[[int], None] | None = None):
        self.max_total = max_total
        self.used = used
        self._lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(max_concurrent)
        self._on_use = on_use

    @property
    def remaining(self) -> int:
        return max(0, self.max_total - self.used)

    @contextmanager
    def request(self) -> Iterator[None]:
        with self._lock:
            if self.used >= self.max_total:
                raise BudgetExhausted(f"Model request budget of {self.max_total} is used up")
            self.used += 1
            if self._on_use:
                self._on_use(self.used)
        with self._slots:
            yield


# ----- fingerprints -------------------------------------------------------------

def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:24]


def _short(component_id: str) -> str:
    return hashlib.sha256(component_id.encode()).hexdigest()[:16]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def content_keys(inventory: Inventory, state: RunState, config: Config, root: Path) -> tuple[dict[str, str], Inventory]:
    """Content key per source, reusing cached hashes when size and mtime match."""
    cache = state.checkpoint.setdefault("source_hashes", {})
    keys: dict[str, str] = {}
    sources = []
    for source in inventory.sources:
        if not config.hash_inputs:
            keys[source.source_id] = f"stat:{source.size_bytes}:{source.mtime_ns}"
            sources.append(source)
            continue
        entry = cache.get(source.source_id)
        if not (entry and entry["size_bytes"] == source.size_bytes and entry["mtime_ns"] == source.mtime_ns):
            try:
                entry = {"size_bytes": source.size_bytes, "mtime_ns": source.mtime_ns,
                         "sha256": _sha256(root / source.relative_path)}
            except OSError:
                keys[source.source_id] = f"unreadable:{source.size_bytes}:{source.mtime_ns}"
                sources.append(source)
                continue
            cache[source.source_id] = entry
        keys[source.source_id] = "sha256:" + entry["sha256"]
        sources.append(replace(source, sha256=entry["sha256"]))
    return keys, replace(inventory, sources=sources)


# ----- planning -----------------------------------------------------------------

def plan_jobs(inventory: Inventory, keys: dict[str, str], config: Config,
              tools: dict[str, ToolSpec], stages: Stages) -> dict[str, dict[str, Any]]:
    jobs: dict[str, dict[str, Any]] = {}
    tool_limits = asdict(ToolLimits())
    meta_hash = code_hash("agents.investigator.metadata:build_metadata")
    builtin_semantics = stages.semantics == DEFAULT_SEMANTICS
    sem_hash = code_hash(stages.semantics) if config.model.enabled and not builtin_semantics else None
    has_key = bool(sem_hash and config.api_key())
    for order, component in enumerate(inventory.components):
        short = _short(component.component_id)
        spec = tools.get(component.kind)
        tool = None
        if spec is not None:
            tool = spec.collection if len(component.source_ids) > 1 and spec.collection else spec.single
        tool_hash = code_hash(tool)
        tool_id = f"tool-{short}"
        jobs[tool_id] = {
            "kind": "tool", "order": order, "component_id": component.component_id, "tool": tool,
            "collection": len(component.source_ids) > 1, "deps": [],
            "fingerprint": _digest({
                "tool": tool, "code": tool_hash, "sources": [keys[s] for s in component.source_ids],
                "selector": component.selector, "kind": component.kind,
                "seed": config.seed, "limits": tool_limits,
            }),
        }
        meta_id = f"meta-{short}"
        jobs[meta_id] = {"kind": "metadata", "order": order, "component_id": component.component_id,
                         "deps": [tool_id], "fingerprint": _digest([jobs[tool_id]["fingerprint"], meta_hash])}
        if sem_hash:
            sem_id = f"sem-{short}"
            jobs[sem_id] = {"kind": "semantics", "order": order, "component_id": component.component_id,
                            "deps": [meta_id], "fingerprint": _digest([jobs[meta_id]["fingerprint"], sem_hash,
                                                                      config.model.name, has_key])}
    if not builtin_semantics:
        jobs["report"] = _report_plan(jobs, stages)
    return jobs


def _report_plan(jobs: dict[str, dict[str, Any]], stages: Stages) -> dict[str, Any]:
    dependencies = {job_id: job for job_id, job in jobs.items()
                    if job["kind"] in {"metadata", "semantics"} and job.get("status") != "removed"}
    report_code = [code_hash(stages.report), code_hash(stages.notebook), code_hash(__name__ + ":x")]
    return {"kind": "report", "order": len(dependencies), "component_id": None,
            "deps": sorted(dependencies),
            "fingerprint": _digest([report_code, {
                job_id: [job["fingerprint"], job.get("outputs")] for job_id, job in dependencies.items()
            }])}


def reconcile(state: RunState, planned: dict[str, dict[str, Any]], *, retry_failed: bool = False,
              kinds: set[str] | None = None) -> dict[str, int]:
    """Merge a fresh plan into the checkpoint; returns counts of what changed."""
    jobs = state.checkpoint.setdefault("jobs", {})
    counts = {"new": 0, "invalidated": 0, "removed": 0, "reused": 0, "retry": 0}
    for job_id, plan in planned.items():
        old = jobs.get(job_id)
        if old is None:
            jobs[job_id] = {**plan, "status": "pending", "attempts": 0, "outputs": {}}
            counts["new"] += 1
            continue
        stale = old.get("fingerprint") != plan["fingerprint"]
        rerun = stale or old.get("status") not in TERMINAL or old.get("status") == "removed"
        if retry_failed and old.get("result_status") == "failed":
            rerun = True
            counts["retry"] += 1
        old.update(plan)
        if rerun:
            if old.get("status") == "done" and stale:
                counts["invalidated"] += 1
                state.event("job_invalidated", job_id=job_id, reason="inputs, code, or settings changed")
            old["status"] = "pending"
        else:
            counts["reused"] += 1
    for job_id, old in jobs.items():
        if job_id not in planned and old.get("status") != "removed" and (kinds is None or old["kind"] in kinds):
            old["status"] = "removed"
            counts["removed"] += 1
            state.event("job_removed", job_id=job_id, reason="component no longer in inventory")
    # Anything downstream of a rerun must rerun too, even if its fingerprint held.
    cascading = True
    while cascading:
        cascading = False
        for job_id in planned:
            job = jobs[job_id]
            if job["status"] == "done" and any(jobs.get(d, {}).get("status") == "pending" for d in job.get("deps", [])):
                job["status"] = "pending"
                counts["reused"] -= 1
                cascading = True
    return counts


# ----- tool execution -------------------------------------------------------------

def _tool_child(payload: dict[str, Any], result_path: str, log_path: str) -> None:
    """Runs in a spawned process: call one tool, write its ToolResult JSON."""
    log = open(log_path, "a", encoding="utf-8", buffering=1)
    os.dup2(log.fileno(), 1)
    os.dup2(log.fileno(), 2)
    sys.stdout = sys.stderr = log
    try:
        text = _call_tool(payload)
        Path(result_path).write_text(text, encoding="utf-8")
    except BaseException as error:
        traceback.print_exc()
        Path(result_path + ".error").write_text(
            json.dumps({"error_type": type(error).__name__, "message": str(error)[:2000]}), encoding="utf-8")
        sys.exit(1)


def _call_tool(payload: dict[str, Any]) -> str:
    function = load_callable(payload["tool"])
    sources = [SourceRef(**s) for s in payload["sources"]]
    limits = payload["limits"]
    context = ToolContext(
        dataset_root=Path(payload["dataset_root"]), output_dir=Path(payload["output_dir"]),
        component_id=payload["component_id"], result_id=payload["result_id"],
        seed=payload["seed"], limits=ToolLimits(**limits),
    )
    result = function(sources if payload["collection"] else sources[0], context)
    if not isinstance(result, ToolResult):
        raise TypeError(f"{payload['tool']} returned {type(result).__name__}, expected ToolResult")
    return result.to_json()


@dataclass
class _Running:
    job_id: str
    process: Any
    started: float
    result_path: Path
    log_path: Path
    output_dir: Path
    payload: dict[str, Any] = field(default_factory=dict)


class Scheduler:
    def __init__(self, state: RunState, inventory: Inventory, config: Config, *,
                 tools: dict[str, ToolSpec] | None = None, stages: Stages | None = None,
                 progress: ProgressFn | None = None):
        self.state = state
        self.inventory = inventory
        self.config = config
        self.tools = DEFAULT_TOOLS if tools is None else tools
        self.stages = stages or Stages()
        self.progress = progress
        self.components = {c.component_id: c for c in inventory.components}
        self.sources = {s.source_id: s for s in inventory.sources}
        self.builtin_semantics = self.stages.semantics == DEFAULT_SEMANTICS
        self.semantic_evidence: dict[str, dict] = {}
        self.budget = ModelBudget(
            config.limits.model_requests_per_run, config.limits.concurrent_model_requests,
            used=state.checkpoint.get("model_requests_used", 0), on_use=self._model_used,
        )
        self._mp = multiprocessing.get_context("spawn")

    # -- bookkeeping
    def _model_used(self, used: int) -> None:
        self.state.checkpoint["model_requests_used"] = used
        self.state.save_checkpoint()

    def _emit(self, event_type: str, /, **fields: Any) -> None:
        record = self.state.event(event_type, **fields)
        if self.progress:
            self.progress(record)

    def _jobs(self) -> dict[str, dict[str, Any]]:
        return self.state.checkpoint["jobs"]

    def _ready(self, running: dict[str, _Running], *, evidence_only: bool) -> list[str]:
        jobs = self._jobs()
        ready = [
            job_id for job_id, job in jobs.items()
            if job["status"] == "pending" and job_id not in running
            and (not evidence_only or job["kind"] in EVIDENCE_KINDS)
            and all(jobs.get(dep, {}).get("status") in TERMINAL for dep in job["deps"])
        ]
        return sorted(ready, key=lambda j: (jobs[j]["kind"] == "report", jobs[j]["order"], j))

    def _component_sources(self, component: ComponentRef) -> list[SourceRef]:
        return [self.sources[s] for s in component.source_ids]

    def _synthetic(self, job_id: str, status: str, method: str, limitation: str) -> ToolResult:
        job = self._jobs()[job_id]
        component = self.components[job["component_id"]]
        return ToolResult(
            result_id=f"r-{job_id}", component_id=component.component_id, status=status,
            inputs=list(component.source_ids), method=method, parameters={},
            coverage=Coverage("none", "files", 0, len(component.source_ids), "not examined"),
            measurements={}, limitations=[limitation],
        )

    def _finish_job(self, job_id: str, outputs: dict[str, str], **fields: Any) -> None:
        job = self._jobs()[job_id]
        job.update(status="done", outputs=outputs, finished_at=time.time(), **fields)
        self.state.save_checkpoint()
        self._emit("job_completed", job_id=job_id, kind=job["kind"],
                   component_id=job.get("component_id"), result_status=fields.get("result_status"))

    # -- main loop
    def _schedule_started(self, *, evidence_only: bool) -> None:
        jobs = [job for job in self._jobs().values()
                if job["status"] != "removed" and (not evidence_only or job["kind"] in EVIDENCE_KINDS)]
        self._emit("schedule_started", pending=sum(job["status"] == "pending" for job in jobs),
                   total=len(jobs), workers=self.config.limits.local_workers)

    def run(self, *, retry_failed: bool = False) -> str:
        stopwatch = Stopwatch(self.config.limits.run_seconds)
        running: dict[str, _Running] = {}
        self.state.checkpoint["status"] = "running"
        self.state.checkpoint["invocations"] = self.state.checkpoint.get("invocations", 0) + 1
        for job in self._jobs().values():
            if job["status"] == "running":  # left over from a crash
                job["status"] = "pending"
        self.state.save_checkpoint()
        evidence_only = self.builtin_semantics
        self._schedule_started(evidence_only=evidence_only)
        status = "completed"
        try:
            while True:
                if stopwatch.expired():
                    self._stop_all(running, "run time limit reached")
                    self._emit("deadline_reached", seconds=self.config.limits.run_seconds)
                    status = "incomplete"
                    break
                self._reap(running)
                ready = self._ready(running, evidence_only=evidence_only)
                if not ready and not running:
                    if evidence_only:
                        self._plan_semantics(retry_failed=retry_failed)
                        evidence_only = False
                        self._schedule_started(evidence_only=False)
                        continue
                    break
                for job_id in ready:
                    job = self._jobs()[job_id]
                    if job["kind"] == "tool":
                        if self.config.execution.tool_isolation == "inline":
                            self._run_tool_inline(job_id)
                        elif len(running) < self.config.limits.local_workers:
                            self._launch(job_id, running)
                    elif not running or job["kind"] != "report":
                        self._run_stage(job_id)
                    if stopwatch.expired():
                        break
                if running:
                    time.sleep(0.02)
        except KeyboardInterrupt:
            self._stop_all(running, "interrupted")
            self.state.checkpoint["status"] = "interrupted"
            self._emit("interrupted")
            raise
        finally:
            self.state.checkpoint["elapsed_seconds"] = round(
                self.state.checkpoint.get("elapsed_seconds", 0.0) + stopwatch.elapsed(), 3)
            if status == "completed" and any(j["status"] == "pending" for j in self._jobs().values()):
                status = "incomplete"
            if self.state.checkpoint.get("status") != "interrupted":
                self.state.checkpoint["status"] = status
            self.state.save_checkpoint()
        self._emit("schedule_finished", status=status, elapsed_seconds=round(stopwatch.elapsed(), 3))
        return status

    # -- tool jobs
    def _prepare(self, job_id: str) -> tuple[dict[str, Any], Path, Path, Path]:
        job = self._jobs()[job_id]
        job["attempts"] = job.get("attempts", 0) + 1
        attempt = job["attempts"]
        component = self.components[job["component_id"]]
        output_dir = self.state.run_dir / "artifacts" / job_id / f"attempt-{attempt:03d}"
        output_dir.mkdir(parents=True, exist_ok=True)
        logs = self.state.run_dir / "logs"
        payload = {
            "tool": job["tool"], "collection": job["collection"],
            "sources": [s.to_dict() for s in self._component_sources(component)],
            "dataset_root": str(self.state.dataset_root), "output_dir": str(output_dir),
            "component_id": component.component_id, "result_id": f"r-{job_id}",
            "seed": self.config.seed, "limits": asdict(ToolLimits()),
        }
        return payload, output_dir, logs / f"{job_id}.attempt-{attempt:03d}.result.json", \
            logs / f"{job_id}.attempt-{attempt:03d}.log"

    def _unavailable(self, job_id: str) -> bool:
        job = self._jobs()[job_id]
        component = self.components[job["component_id"]]
        if component.kind == "unknown" or job["tool"] is None:
            result = self._synthetic(job_id, "unsupported", "none",
                                     f"No tool handles component kind '{component.kind}'; input recorded without analysis.")
        elif code_hash(job["tool"]) is None:
            result = self._synthetic(job_id, "deferred", job["tool"],
                                     f"Tool {job['tool']} is not available yet; rerun or resume once it is implemented.")
        else:
            return False
        self._save_tool_result(job_id, result)
        return True

    def _launch(self, job_id: str, running: dict[str, _Running]) -> None:
        if self._unavailable(job_id):
            return
        payload, output_dir, result_path, log_path = self._prepare(job_id)
        process = self._mp.Process(target=_tool_child, args=(payload, str(result_path), str(log_path)), daemon=True)
        process.start()
        self._jobs()[job_id]["status"] = "running"
        self.state.save_checkpoint()
        running[job_id] = _Running(job_id, process, time.monotonic(), result_path, log_path, output_dir, payload)
        self._emit("job_started", job_id=job_id, kind="tool", tool=payload["tool"],
                   component_id=payload["component_id"])

    def _run_tool_inline(self, job_id: str) -> None:
        if self._unavailable(job_id):
            return
        payload, output_dir, _, log_path = self._prepare(job_id)
        self._emit("job_started", job_id=job_id, kind="tool", tool=payload["tool"],
                   component_id=payload["component_id"])
        try:
            text = _call_tool(payload)
        except Exception as error:  # noqa: BLE001 - tool failures become failed results
            log_path.write_text(redact(traceback.format_exc()), encoding="utf-8")
            self._tool_failed(job_id, f"{type(error).__name__}: {error}", log_path)
            return
        self._accept(job_id, text, output_dir, log_path)

    def _reap(self, running: dict[str, _Running]) -> None:
        timeout = self.config.limits.tool_timeout_seconds
        for job_id, item in list(running.items()):
            if item.process.is_alive():
                if time.monotonic() - item.started > timeout:
                    item.process.kill()
                    item.process.join()
                    del running[job_id]
                    self._tool_failed(job_id, f"Tool exceeded {timeout} s and was stopped.", item.log_path)
                continue
            item.process.join()
            del running[job_id]
            if item.result_path.exists():
                self._accept(job_id, item.result_path.read_text(encoding="utf-8"), item.output_dir, item.log_path)
                item.result_path.unlink()
                continue
            error_path = Path(str(item.result_path) + ".error")
            if error_path.exists():
                info = json.loads(error_path.read_text(encoding="utf-8"))
                message = f"{info['error_type']}: {info['message']}"
                error_path.unlink()
            else:
                message = f"Tool process exited with code {item.process.exitcode} without a result."
            self._tool_failed(job_id, message, item.log_path)

    def _stop_all(self, running: dict[str, _Running], reason: str) -> None:
        for job_id, item in list(running.items()):
            item.process.kill()
            item.process.join()
            self._jobs()[job_id]["status"] = "pending"  # resume will run it again
            self._emit("job_stopped", job_id=job_id, reason=reason)
            del running[job_id]
        self.state.save_checkpoint()

    def _tool_failed(self, job_id: str, message: str, log_path: Path) -> None:
        job = self._jobs()[job_id]
        message = redact(message.replace(str(self.state.dataset_root), "<dataset>"))
        result = self._synthetic(job_id, "failed", job["tool"] or "none", f"Tool failed: {message}")
        self._save_tool_result(job_id, result, log=log_path)

    def _accept(self, job_id: str, text: str, output_dir: Path, log_path: Path) -> None:
        try:
            result = ToolResult.from_json(text)
            if result.result_id != f"r-{job_id}" or result.component_id != self._jobs()[job_id]["component_id"]:
                raise ValueError("Tool must reuse context.result_id and context.component_id")
            result.validate_references(self.inventory)
        except ValueError as error:
            self._tool_failed(job_id, f"Invalid ToolResult: {error}", log_path)
            return
        result = self._publish_artifacts(result, output_dir)
        self._save_tool_result(job_id, result, log=log_path)

    def _publish_artifacts(self, result: ToolResult, output_dir: Path) -> ToolResult:
        """Validate tool-relative artifact paths; rewrite them run-relative."""
        root = output_dir.resolve()
        run = self.state.run_dir.resolve()
        published, problems = [], []
        for artifact in result.artifacts:
            path = root / artifact.relative_path
            if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
                problems.append(f"Artifact missing or unsafe, dropped: {artifact.relative_path}")
                continue
            if path.stat().st_size > self.config.limits.max_output_bytes:
                problems.append(f"Artifact too large, dropped: {artifact.relative_path}")
                continue
            published.append(replace(artifact, relative_path=path.relative_to(run).as_posix()))
        return replace(result, artifacts=published, limitations=result.limitations + problems)

    def _save_tool_result(self, job_id: str, result: ToolResult, log: Path | None = None) -> None:
        path = self.state.save_versioned("results", job_id, result.to_json())
        outputs = {"result": path}
        if log is not None and log.exists() and log.stat().st_size:
            outputs["log"] = log.relative_to(self.state.run_dir).as_posix()
        self._finish_job(job_id, outputs, result_status=result.status)

    # -- in-process stages
    def _latest_result(self, job_id: str) -> ToolResult | None:
        path = self._jobs().get(job_id, {}).get("outputs", {}).get("result")
        return ToolResult.from_json(self.state.read_relative(path)) if path else None

    def _component_metadata(self, component_id: str) -> dict:
        path = self._jobs()[f"meta-{_short(component_id)}"]["outputs"].get("metadata")
        return json.loads(self.state.read_relative(path)) if path else {"component_id": component_id}

    def _plan_semantics(self, *, retry_failed: bool) -> None:
        from .semantics import resolve_dictionaries

        jobs = self._jobs()
        tables, tiffs, documents = {}, {}, []
        for cid, component in self.components.items():
            if component.kind == "table":
                tables[cid] = self._component_metadata(cid)
            elif component.kind == "images" and any(source.format == "tiff" for source in self._component_sources(component)):
                tiffs[cid] = self._component_metadata(cid)
            elif component.kind == "documents":
                result = self._latest_result(f"tool-{_short(cid)}")
                if result is not None:
                    documents.append(result)
        self.semantic_evidence, issues = resolve_dictionaries(self.inventory, tables, documents)
        self.state.checkpoint["dictionary_reference_issues"] = issues
        sem_hash = code_hash(self.stages.semantics)
        tiff_hash = code_hash(TIFF_SEMANTICS) if tiffs else None
        model_fingerprint = vision_fingerprint = None
        settings = self.config.model
        if settings.enabled and settings.interpret_semantics:
            table_settings = asdict(settings)
            vision_name = table_settings.pop("vision_name")
            shared = [self.config.api_key() is not None, self.config.limits.model_requests_per_run,
                      code_hash("agents.semantic_agent:request_completion")]
            model_fingerprint = _digest([table_settings, *shared])
            vision_fingerprint = _digest([{**table_settings, "name": vision_name}, *shared])

        planned = {}
        for order, (cid, metadata) in enumerate({**tables, **tiffs}.items()):
            short = _short(cid)
            is_tiff = cid in tiffs
            evidence = _digest([metadata, self.semantic_evidence.get(cid), tiff_hash if is_tiff else sem_hash,
                                jobs[f"tool-{short}"]["outputs"].get("result")])
            model = vision_fingerprint if is_tiff else model_fingerprint
            enrichment = _digest([evidence, model]) if model else None
            planned[f"sem-{short}"] = {
                "kind": "semantics", "order": order, "component_id": cid, "deps": [f"meta-{short}"],
                "enrichment_fingerprint": enrichment, "fingerprint": _digest([evidence, enrichment]),
            }
        metadata_jobs = {job_id: job for job_id, job in jobs.items() if job["kind"] == "metadata"}
        report = _report_plan({**metadata_jobs, **planned}, self.stages)
        report["fingerprint"] = _digest([report["fingerprint"], issues])
        planned["report"] = report
        counts = reconcile(self.state, planned, retry_failed=retry_failed, kinds=INTERPRETATION_KINDS)
        self.state.event("semantic_plan_reconciled", **counts)
        self.state.save_checkpoint()

    def _run_stage(self, job_id: str) -> None:
        job = self._jobs()[job_id]
        self._emit("job_started", job_id=job_id, kind=job["kind"], component_id=job.get("component_id"))
        try:
            if job["kind"] == "metadata":
                results = [r for r in (self._latest_result(d) for d in job["deps"]) if r is not None]
                metadata = build_metadata(job["component_id"], results)
                path = self.state.save_versioned("metadata", job["component_id"], json.dumps(metadata, indent=2) + "\n")
                self._finish_job(job_id, {"metadata": path}, result_status="complete")
            elif job["kind"] == "semantics":
                self._run_semantics(job_id)
            elif job["kind"] == "report":
                self._run_report(job_id)
        except Exception as error:  # noqa: BLE001 - recorded, run continues
            log = self.state.run_dir / "logs" / f"{job_id}.log"
            log.write_text(redact(traceback.format_exc()), encoding="utf-8")
            self._finish_job(job_id, {"log": log.relative_to(self.state.run_dir).as_posix()},
                             result_status="failed", error=redact(f"{type(error).__name__}: {error}"))

    def _run_semantics(self, job_id: str) -> None:
        job = self._jobs()[job_id]
        cid = job["component_id"]
        metadata = self._component_metadata(cid)
        component = self.components[cid]
        if self.builtin_semantics and component.kind == "images":
            profile = load_callable(TIFF_SEMANTICS)(
                metadata, sources=self._component_sources(component), run_dir=self.state.run_dir,
                budget=self.budget, config=self.config,
            )
        elif self.builtin_semantics:
            tool = self._jobs()[f"tool-{_short(cid)}"]
            source = self._component_sources(component)[0]
            profile = load_callable(self.stages.semantics)(
                metadata, source=source, result_path=tool["outputs"].get("result"),
                dictionary=self.semantic_evidence[cid], budget=self.budget, config=self.config,
            )
        else:
            if self.config.api_key() is None:
                self._finish_job(job_id, {}, result_status="skipped",
                                 error=f"No model credentials in ${self.config.model.api_key_env}")
                return
            try:
                profile = load_callable(self.stages.semantics)(metadata, budget=self.budget, config=self.config)
            except BudgetExhausted as error:
                self._finish_job(job_id, {}, result_status="skipped", error=str(error))
                return
        text = json.dumps(profile, indent=2, allow_nan=False) + "\n"
        path = self.state.save_versioned("semantics", job["component_id"], text)
        self._finish_job(job_id, {"semantics": path}, result_status="complete")

    def refresh_report(self) -> str | None:
        """Write a new report revision (e.g. after a follow-up session)."""
        self.state.acquire_lock()
        try:
            self._jobs().setdefault("report", {"kind": "report", "order": 0, "component_id": None, "deps": [],
                                               "fingerprint": "", "attempts": 0, "outputs": {}})
            self._jobs()["report"]["status"] = "pending"
            self._run_stage("report")
            return self._jobs()["report"].get("outputs", {}).get("revision")
        finally:
            self.state.release_lock()

    def _run_report(self, job_id: str) -> None:
        revision = self.state.new_report_revision()
        outputs = {"revision": revision.relative_to(self.state.run_dir).as_posix()}
        notes = []
        if code_hash(self.stages.report):
            markdown = load_callable(self.stages.report)(self.state.run_dir)
        else:
            markdown = fallback_report(self.state, self.inventory)
            notes.append("reporting module not available; wrote fallback report")
        write_text_atomic(revision / "report.md", str(markdown))
        outputs["report"] = (revision / "report.md").relative_to(self.state.run_dir).as_posix()
        if code_hash(self.stages.notebook):
            source = load_callable(self.stages.notebook)(self.state.run_dir)
            write_text_atomic(revision / "notebook.py", str(source))
            outputs["notebook"] = (revision / "notebook.py").relative_to(self.state.run_dir).as_posix()
        self._finish_job(job_id, outputs, result_status="complete", notes=notes)
        self._emit("report_written", revision=outputs["revision"])


# ----- fallback report --------------------------------------------------------------

def fallback_report(state: RunState, inventory: Inventory) -> str:
    """Minimal Markdown from saved results until reporting.py exists."""
    jobs = state.checkpoint["jobs"]
    by_component = {j["component_id"]: j for j in jobs.values() if j["kind"] == "tool" and j["status"] == "done"}
    paths = {s.source_id: s.relative_path for s in inventory.sources}
    lines = [
        f"# Investigation report — run {state.run_id}", "",
        "_Fallback report written by the scheduler from saved results; the reporting module is not installed yet._",
        "", f"- Sources discovered: {len(inventory.sources)}", f"- Components: {len(inventory.components)}", "",
        "## Components", "",
        "| Component | Kind | Files | Result | Coverage |", "|---|---|---|---|---|",
    ]
    limitations: list[str] = []
    for component in inventory.components:
        job = by_component.get(component.component_id)
        status, coverage = "not run", ""
        if job and job.get("outputs", {}).get("result"):
            result = ToolResult.from_json(state.read_relative(job["outputs"]["result"]))
            status = result.status
            c = result.coverage
            coverage = f"{c.mode}: {c.examined}/{c.total if c.total is not None else '?'} {c.unit}"
            name = ", ".join(paths[s] for s in component.source_ids)
            limitations += [f"{name}: {text}" for text in result.limitations]
        files = ", ".join(f"`{paths[s]}`" for s in component.source_ids)
        lines.append(f"| `{component.component_id[:18]}…` | {component.kind} | {files} | {status} | {coverage} |")
    lines += ["", "## Limitations", ""]
    lines += [f"- {text}" for text in inventory.limitations + limitations] or ["- None recorded."]
    analyses = sorted((state.run_dir / "analyses").glob("*/result.json"))
    if analyses:
        lines += ["", "## Custom analyses", ""]
        for path in analyses:
            data = json.loads(path.read_text(encoding="utf-8"))
            lines.append(f"- `{data['job_id']}` ({data['status']}): {data['request']['question']}")
    return "\n".join(lines) + "\n"


# ----- orchestration ------------------------------------------------------------------

def discover_inventory(dataset_root: Path, state_root: Path) -> Inventory:
    """Discover inputs, excluding the agent's own state directory."""
    inventory = discover(dataset_root)
    root = Path(dataset_root).resolve()
    state = Path(state_root).resolve()
    if not state.is_relative_to(root):
        return inventory
    prefix = state.relative_to(root).as_posix() + "/"
    keep = [s for s in inventory.sources if not s.relative_path.startswith(prefix)]
    ids = {s.source_id for s in keep}
    components = [c for c in inventory.components if set(c.source_ids) <= ids]
    return replace(inventory, sources=keep, components=components)


def compare_inventories(old: Inventory | None, new: Inventory) -> dict[str, list[str]]:
    before = {s.source_id: s for s in (old.sources if old else [])}
    after = {s.source_id: s for s in new.sources}
    changed = [
        after[i].relative_path for i in after.keys() & before.keys()
        if (after[i].size_bytes, after[i].mtime_ns) != (before[i].size_bytes, before[i].mtime_ns)
    ]
    return {
        "added": sorted(after[i].relative_path for i in after.keys() - before.keys()),
        "removed": sorted(before[i].relative_path for i in before.keys() - after.keys()),
        "changed": sorted(changed),
    }


def state_root_for(dataset_root: Path, config: Config) -> Path:
    if config.state_dir:
        path = Path(config.state_dir).expanduser()
        return path if path.is_absolute() else Path(dataset_root) / path
    return Path(dataset_root) / ".d37-agent"


def execute_run(state: RunState, config: Config, *, tools: dict[str, ToolSpec] | None = None,
                stages: Stages | None = None, progress: ProgressFn | None = None,
                retry_failed: bool = False) -> str:
    """Discover, reconcile with the checkpoint, and schedule. Used by run and resume."""
    state.acquire_lock()
    try:
        state_root = state.run_dir.parent.parent
        inventory = discover_inventory(state.dataset_root, state_root)
        changes = compare_inventories(state.load_inventory(), inventory)
        keys, inventory = content_keys(inventory, state, config, state.dataset_root)
        state.save_inventory(inventory)
        state.event("discovery_completed", sources=len(inventory.sources),
                    components=len(inventory.components), **{k: len(v) for k, v in changes.items()})
        for kind in ("added", "removed", "changed"):
            for path in changes[kind]:
                state.event(f"source_{kind}", relative_path=path)
        scheduler = Scheduler(state, inventory, config, tools=tools, stages=stages, progress=progress)
        counts = reconcile(state, plan_jobs(inventory, keys, config, scheduler.tools, scheduler.stages),
                           retry_failed=retry_failed, kinds=EVIDENCE_KINDS if scheduler.builtin_semantics else None)
        state.event("plan_reconciled", **counts)
        state.save_checkpoint()
        if progress:
            progress({"type": "plan", "changes": changes, **counts})
        return scheduler.run(retry_failed=retry_failed)
    finally:
        state.release_lock()


def start_run(dataset_root: str | Path, config: Config, **options: Any) -> tuple[RunState, str]:
    root = Path(dataset_root).resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(root)
    state = RunState.create(state_root_for(root, config), root, config)
    return state, execute_run(state, config, **options)


def resume_run(run_dir: str | Path, **options: Any) -> tuple[RunState, str]:
    state = RunState.open(Path(run_dir))
    config = state.config()
    state.event("run_resumed", previous_status=state.checkpoint.get("status"))
    return state, execute_run(state, config, **options)
