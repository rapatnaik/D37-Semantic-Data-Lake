"""Follow-up sessions: question -> choose_next_action loop -> answer.

Handoff with investigation.py (Jacob)::

    def choose_next_action(context: InvestigationContext) -> ToolCall | AnalysisRequest | Completion

``context`` is local. Its ``budget`` must wrap every model call
(``with context.budget.request(): ...``); only bounded evidence should be sent
to the model. After a failed analysis, ``context.last_execution`` holds the
failure and the next AnalysisRequest counts as a repair (at most two).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .config import Config
from .contracts import AnalysisRequest, Contract, Inventory, ToolResult, _require, _text
from .execution import ExecutionContext, ExecutionResult, execute_analysis
from .scheduler import BudgetExhausted, ModelBudget, Scheduler, load_callable
from .state import RunState, utc_now, write_json_atomic

DEFAULT_CHOOSER = "agents.investigator.investigation:choose_next_action"


@dataclass
class ToolCall(Contract):
    """Ask for the saved result of a tested tool on one component."""

    component_id: str
    reason: str = ""

    def _check(self) -> None:
        _text(self.component_id, "component_id")


@dataclass
class Completion(Contract):
    """Final answer, with references to the evidence that supports it."""

    answer: str
    evidence: list[str] = field(default_factory=list)
    uncertainty: str = ""

    def _check(self) -> None:
        _text(self.answer, "answer")


@dataclass
class InvestigationContext:
    question: str
    inventory: Inventory
    metadata: dict[str, Any]
    history: list[dict[str, Any]]
    budget: ModelBudget
    config: Config
    repairs_remaining: int
    steps_remaining: int
    last_execution: ExecutionResult | None = None


Chooser = Callable[[InvestigationContext], Any]


def default_chooser() -> Chooser:
    try:
        return load_callable(DEFAULT_CHOOSER)
    except (ImportError, AttributeError) as error:
        raise RuntimeError(
            "The reasoning module (investigation.choose_next_action) is not available yet; "
            "use `d37-agent ask --code FILE` to run a hand-written analysis."
        ) from error


def _latest_metadata(state: RunState) -> dict[str, Any]:
    found = {}
    for job in state.checkpoint.get("jobs", {}).values():
        path = job.get("outputs", {}).get("metadata")
        if job.get("kind") == "metadata" and job.get("status") == "done" and path:
            found[job["component_id"]] = json.loads(state.read_relative(path))
    return found


def _tool_evidence(state: RunState, component_id: str) -> dict[str, Any]:
    for job_id, job in state.checkpoint.get("jobs", {}).items():
        if job.get("kind") == "tool" and job.get("component_id") == component_id and job.get("outputs", {}).get("result"):
            result = ToolResult.from_json(state.read_relative(job["outputs"]["result"]))
            return {"status": "found", "result_path": job["outputs"]["result"], "result_status": result.status}
    return {"status": "missing", "error": "No saved tool result for this component; run or resume first."}


def run_followup(state: RunState, question: str, *, chooser: Chooser | None = None,
                 config: Config | None = None, refresh_report: bool = True) -> dict[str, Any]:
    _require(bool(question.strip()), "question must not be blank")
    config = config or state.config()
    chooser = chooser or default_chooser()
    inventory = state.load_inventory()
    if inventory is None:
        raise RuntimeError("This run has no inventory yet; run or resume it first.")
    sessions = state.run_dir / "sessions"
    number = 1 + sum(1 for _ in sessions.glob("s[0-9][0-9][0-9]-*.json"))
    session_id = f"s{number:03d}-{hashlib.sha256(question.encode()).hexdigest()[:8]}"
    budget = ModelBudget(config.limits.model_requests_per_run, config.limits.concurrent_model_requests)
    record: dict[str, Any] = {"session_id": session_id, "question": question, "started_at": utc_now(),
                              "steps": [], "status": "running"}
    state.acquire_lock()
    state.event("session_started", session_id=session_id)
    history: list[dict[str, Any]] = record["steps"]
    attempt, repair_of, last = 0, None, None
    try:
        for step in range(config.limits.followup_steps):
            context = InvestigationContext(
                question=question, inventory=inventory, metadata=_latest_metadata(state), history=history,
                budget=budget, config=config, repairs_remaining=config.limits.repair_attempts - attempt,
                steps_remaining=config.limits.followup_steps - step, last_execution=last,
            )
            try:
                action = chooser(context)
            except BudgetExhausted as error:
                record.update(status="budget_exhausted", error=str(error))
                break
            if isinstance(action, Completion):
                action.validate()
                record.update(status="answered", answer=action.to_dict())
                break
            if isinstance(action, ToolCall):
                action.validate()
                history.append({"action": "tool_call", **action.to_dict(),
                                **_tool_evidence(state, action.component_id)})
                continue
            if not isinstance(action, AnalysisRequest):
                record.update(status="failed", error=f"Unsupported action type {type(action).__name__}")
                break
            if attempt > config.limits.repair_attempts:
                record.update(status="failed", error="Repair limit reached; analysis not executed")
                break
            result = execute_analysis(action, ExecutionContext(
                run_dir=state.run_dir, dataset_root=state.dataset_root, inventory=inventory, config=config,
                attempt=attempt, repair_of=repair_of, on_event=state.event,
            ))
            history.append({"action": "analysis", "job_id": result.job_id, "status": result.status,
                            "attempt": attempt, "error": result.error,
                            "outputs": [a.relative_path for a in result.outputs],
                            "result_path": f"analyses/{result.job_id}/result.json"})
            last = result
            if result.succeeded:
                attempt, repair_of = 0, None
            elif result.status in {"rejected", "unsupported"}:
                record.update(status="failed", error=result.error or "; ".join(result.limitations))
                break
            else:
                attempt, repair_of = attempt + 1, result.job_id
                if attempt > config.limits.repair_attempts:
                    record.update(status="failed", error="Analysis failed after the allowed repair attempts")
                    break
        else:
            record.update(status="incomplete", error="Step limit reached without an answer")
    finally:
        record["finished_at"] = utc_now()
        record["model_requests_used"] = budget.used
        write_json_atomic(sessions / f"{session_id}.json", record)
        state.event("session_finished", session_id=session_id, status=record["status"])
        state.release_lock()
    if refresh_report:
        Scheduler(state, inventory, config).refresh_report()
    return record


def manual_chooser(request: AnalysisRequest) -> Chooser:
    """Run one hand-written analysis, then report where its outputs are."""
    def choose(context: InvestigationContext) -> Any:
        if context.last_execution is None:
            return request
        result = context.last_execution
        return Completion(
            answer=f"Analysis {result.job_id} {result.status}; see analyses/{result.job_id}/.",
            evidence=[a.relative_path for a in result.outputs],
            uncertainty="Hand-written analysis; output not interpreted by a model.",
        )
    return choose


def resolve_input_ids(inventory: Inventory, names: list[str]) -> list[str]:
    """Accept source IDs or dataset-relative paths."""
    by_path = {s.relative_path: s.source_id for s in inventory.sources}
    ids = {s.source_id for s in inventory.sources}
    resolved = []
    for name in names:
        key = Path(name).as_posix()
        if name in ids:
            resolved.append(name)
        elif key in by_path:
            resolved.append(by_path[key])
        else:
            raise ValueError(f"Unknown input (not a source ID or discovered path): {name}")
    return resolved
