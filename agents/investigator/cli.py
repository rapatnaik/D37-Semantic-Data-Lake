"""``d37-agent`` command line.

    d37-agent run DATA_DIR            investigate a directory (new run)
    d37-agent resume [RUN|DATA_DIR]   continue an interrupted/incomplete run;
                                      re-runs only what changed sources affect
    d37-agent status [RUN|DATA_DIR]   job and budget summary
    d37-agent runs DATA_DIR           list saved runs
    d37-agent ask RUN|DATA_DIR "question" [--code FILE --input PATH ...]

Exit codes: 0 completed, 1 error, 2 usage, 3 stopped at the run time limit
(resumable), 130 interrupted (resumable).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence, TextIO

from .config import Config, load_config, redact, with_overrides
from .contracts import AnalysisRequest
from .state import RunLockedError, RunState, latest_run
from .scheduler import execute_run, resume_run, state_root_for

EXIT_OK, EXIT_ERROR, EXIT_INCOMPLETE, EXIT_INTERRUPTED = 0, 1, 3, 130


class Progress:
    """Line-based progress on stderr; quiet mode prints only the summary."""

    def __init__(self, stream: TextIO | None = None, quiet: bool = False):
        self.stream, self.quiet = stream, quiet
        self.done = self.total = 0
        self.paths: dict[str, str] = {}
        self.run_dir: Path | None = None

    def _label(self, component_id: str | None) -> str:
        if not component_id:
            return ""
        if not self.paths and self.run_dir and (self.run_dir / "inventory.json").exists():
            data = json.loads((self.run_dir / "inventory.json").read_text(encoding="utf-8"))
            names = {s["source_id"]: s["relative_path"] for s in data["sources"]}
            self.paths = {c["component_id"]: ", ".join(names[i] for i in c["source_ids"]) for c in data["components"]}
        return self.paths.get(component_id, component_id[:20])

    def __call__(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "plan":
            changes = event["changes"]
            if any(changes.values()):
                self._print(f"changes since last run: {len(changes['added'])} added, "
                            f"{len(changes['changed'])} changed, {len(changes['removed'])} removed")
            self._print(f"plan: {event['new']} new, {event['invalidated']} invalidated, "
                        f"{event['reused']} reused, {event['removed']} removed")
        elif kind == "schedule_started":
            self.total, self.done = event["total"], event["total"] - event["pending"]
        elif kind == "job_completed":
            self.done += 1
            status = event.get("result_status") or "done"
            self._print(f"[{self.done}/{self.total}] {event['kind']:<9} {status:<11} {self._label(event.get('component_id'))}")
        elif kind == "deadline_reached":
            self._print(f"run time limit ({event['seconds']} s) reached; use `d37-agent resume` to continue", force=True)
        elif kind == "report_written":
            self._print(f"report: {event['revision']}/report.md")

    def _print(self, text: str, force: bool = False) -> None:
        if force or not self.quiet:
            print(text, file=self.stream or sys.stderr, flush=True)


def _config(args: argparse.Namespace) -> Config:
    config = load_config(args.config, search_dir=None if args.config else Path.cwd())
    execution, limits, model, top = {}, {}, {}, {}
    if getattr(args, "backend", None):
        execution["backend"] = args.backend
    if getattr(args, "workers", None):
        limits["local_workers"] = args.workers
    if getattr(args, "time_limit", None):
        limits["run_seconds"] = args.time_limit
    if getattr(args, "no_model", False):
        model["enabled"] = False
    if getattr(args, "interpret_semantics", False):
        model.update(enabled=True, interpret_semantics=True)
    config = with_overrides(config, execution=execution, limits=limits, model=model)
    if getattr(args, "no_hash", False):
        top["hash_inputs"] = False
    if getattr(args, "state_dir", None):
        top["state_dir"] = str(Path(args.state_dir).resolve())
    if top:
        config = replace(config, **top)
        config.check()
    return config


def _find_run(target: str | None, args: argparse.Namespace) -> Path:
    path = Path(target or ".").resolve()
    if (path / "manifest.json").is_file() and (path / "checkpoint.json").is_file():
        return path
    if not path.is_dir():
        raise FileNotFoundError(f"No run or data directory at {path}")
    found = latest_run(state_root_for(path, _config(args)))
    if found is None:
        raise FileNotFoundError(f"No saved runs for {path}; start one with `d37-agent run {target or '.'}`")
    return found


def _summary(state: RunState) -> dict[str, Any]:
    jobs = state.checkpoint.get("jobs", {})
    by_status: dict[str, int] = {}
    by_result: dict[str, int] = {}
    for job in jobs.values():
        by_status[job["status"]] = by_status.get(job["status"], 0) + 1
        if job["status"] == "done" and job.get("result_status"):
            by_result[job["result_status"]] = by_result.get(job["result_status"], 0) + 1
    revisions = state.checkpoint.get("report_revisions", [])
    return {
        "run_id": state.run_id, "run_dir": str(state.run_dir), "status": state.checkpoint.get("status"),
        "jobs": by_status, "results": by_result,
        "model_requests_used": state.checkpoint.get("model_requests_used", 0),
        "elapsed_seconds": state.checkpoint.get("elapsed_seconds", 0.0),
        "latest_report": f"{revisions[-1]}/report.md" if revisions else None,
        "sessions": len(list((state.run_dir / "sessions").glob("*.json"))),
    }


def _print_summary(summary: dict[str, Any], stream: TextIO | None = None) -> None:
    stream = stream or sys.stdout
    print(f"run {summary['run_id']}: {summary['status']}", file=stream)
    print(f"  directory: {summary['run_dir']}", file=stream)
    print("  jobs: " + ", ".join(f"{k} {v}" for k, v in sorted(summary["jobs"].items())), file=stream)
    if summary["results"]:
        print("  results: " + ", ".join(f"{k} {v}" for k, v in sorted(summary["results"].items())), file=stream)
    print(f"  model requests: {summary['model_requests_used']}; elapsed: {summary['elapsed_seconds']} s", file=stream)
    if summary["latest_report"]:
        print(f"  report: {Path(summary['run_dir']) / summary['latest_report']}", file=stream)


def _exit_for(status: str) -> int:
    return {"completed": EXIT_OK, "incomplete": EXIT_INCOMPLETE, "interrupted": EXIT_INTERRUPTED}.get(status, EXIT_ERROR)


# ----- commands ---------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> int:
    config = _config(args)
    root = Path(args.data_dir).resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")
    state = RunState.create(state_root_for(root, config), root, config)
    print(f"run {state.run_id} → {state.run_dir}", file=sys.stderr, flush=True)
    progress = Progress(quiet=args.quiet)
    progress.run_dir = state.run_dir
    status = execute_run(state, config, progress=progress)
    _print_summary(_summary(state))
    return _exit_for(status)


def cmd_resume(args: argparse.Namespace) -> int:
    run_dir = _find_run(args.target, args)
    progress = Progress(quiet=args.quiet)
    progress.run_dir = run_dir
    state, status = resume_run(run_dir, progress=progress, retry_failed=args.retry_failed)
    _print_summary(_summary(state))
    return _exit_for(status)


def cmd_status(args: argparse.Namespace) -> int:
    state = RunState.open(_find_run(args.target, args))
    summary = _summary(state)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        _print_summary(summary)
    return EXIT_OK


def cmd_runs(args: argparse.Namespace) -> int:
    root = state_root_for(Path(args.data_dir).resolve(), _config(args)) / "runs"
    runs = sorted(root.glob("*/checkpoint.json")) if root.is_dir() else []
    if not runs:
        print("no runs")
    for path in runs:
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
        print(f"{path.parent.name}  {checkpoint.get('status'):<11}  {path.parent}")
    return EXIT_OK


def _parameters(pairs: Sequence[str]) -> dict[str, Any]:
    parameters: dict[str, Any] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise ValueError(f"--param expects KEY=VALUE, got {pair!r}")
        try:
            parameters[key] = json.loads(value)
        except json.JSONDecodeError:
            parameters[key] = value
    return parameters


def cmd_ask(args: argparse.Namespace) -> int:
    from .session import manual_chooser, resolve_input_ids, run_followup

    state = RunState.open(_find_run(args.target, args))
    config = state.config()
    if args.backend:
        config = with_overrides(config, execution={"backend": args.backend})
    chooser = None
    if args.code:
        inventory = state.load_inventory()
        if not args.inputs:
            raise ValueError("--code needs at least one --input")
        request = AnalysisRequest(
            question=args.question, code=Path(args.code).read_text(encoding="utf-8"),
            input_ids=resolve_input_ids(inventory, args.inputs), parameters=_parameters(args.param),
            expected_outputs=args.expect or ["application/json"],
        )
        chooser = manual_chooser(request)
    record = run_followup(state, args.question, chooser=chooser, config=config)
    if args.json:
        print(json.dumps(record, indent=2))
    else:
        print(f"session {record['session_id']}: {record['status']}")
        if record.get("answer"):
            print(record["answer"]["answer"])
        if record.get("error"):
            print(f"error: {record['error']}")
        for step in record["steps"]:
            if step["action"] == "analysis":
                print(f"  analysis {step['job_id']} (attempt {step['attempt']}): {step['status']}")
                for output in step["outputs"]:
                    print(f"    {state.run_dir / output}")
    return EXIT_OK if record["status"] == "answered" else EXIT_ERROR


# ----- parser -------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="d37-agent", description="Investigate an unfamiliar data directory.")
    parser.add_argument("--config", help="TOML settings (default: ./d37-agent.toml if present)")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--state-dir", help="where runs are saved (default: DATA_DIR/.d37-agent)")
        p.add_argument("--quiet", "-q", action="store_true", help="only print the final summary")

    run = sub.add_parser("run", help="start a new run")
    run.add_argument("data_dir")
    common(run)
    run.add_argument("--backend", choices=["docker", "process"], help="custom-code isolation backend")
    run.add_argument("--workers", type=int, help="local worker processes (default 4)")
    run.add_argument("--time-limit", type=int, help="seconds per invocation (default 900)")
    model = run.add_mutually_exclusive_group()
    model.add_argument("--no-model", action="store_true", help="skip model-backed stages")
    model.add_argument("--interpret-semantics", action="store_true", help="request optional model interpretations")
    run.add_argument("--no-hash", action="store_true", help="detect changes by size/mtime only")
    run.set_defaults(func=cmd_run)

    resume = sub.add_parser("resume", help="continue the latest (or given) run")
    resume.add_argument("target", nargs="?", help="run directory or data directory (default: .)")
    common(resume)
    resume.add_argument("--retry-failed", action="store_true", help="also re-run tools whose result failed")
    resume.set_defaults(func=cmd_resume)

    status = sub.add_parser("status", help="summarise a run")
    status.add_argument("target", nargs="?")
    common(status)
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    runs = sub.add_parser("runs", help="list runs for a data directory")
    runs.add_argument("data_dir")
    common(runs)
    runs.set_defaults(func=cmd_runs)

    ask = sub.add_parser("ask", help="follow-up question on a run")
    ask.add_argument("target", help="run directory or data directory")
    ask.add_argument("question")
    common(ask)
    ask.add_argument("--code", help="run this Python file instead of asking the model")
    ask.add_argument("--input", dest="inputs", action="append", default=[], help="dataset-relative path or source ID")
    ask.add_argument("--param", action="append", default=[], help="KEY=VALUE (JSON values allowed)")
    ask.add_argument("--expect", action="append", help="expected output media type (default application/json)")
    ask.add_argument("--backend", choices=["docker", "process"])
    ask.add_argument("--json", action="store_true")
    ask.set_defaults(func=cmd_ask)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("interrupted; progress was checkpointed — run `d37-agent resume` to continue", file=sys.stderr)
        return EXIT_INTERRUPTED
    except RunLockedError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_ERROR
    except (OSError, ValueError, RuntimeError) as error:
        print(f"error: {redact(str(error))}", file=sys.stderr)
        if os.environ.get("D37_AGENT_DEBUG"):
            raise
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
