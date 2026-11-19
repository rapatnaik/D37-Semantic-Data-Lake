"""Scheduling, tool isolation, artifact publishing, budgets, and deadlines."""

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agents.investigator.config import Config, ExecutionSettings, Limits, ModelSettings
from agents.investigator.contracts import ToolResult
from agents.investigator.scheduler import (
    BudgetExhausted, ModelBudget, Stages, ToolSpec, discover_inventory, start_run,
)

SECRET = "nrp-secret-value-123456"
NO_STAGES = Stages(semantics=None, report=None, notebook=None)


def config(isolation="inline", **limits):
    return Config(limits=Limits(**limits), model=ModelSettings(enabled=False),
                  execution=ExecutionSettings(backend="process", tool_isolation=isolation))


def make_dataset(root: Path) -> Path:
    data = root / "data"
    (data / "nested").mkdir(parents=True)
    (data / "patients.csv").write_text("id,age\n1,30\n2,\n3,41\n", encoding="utf-8")
    (data / "nested" / "visits.csv").write_text("id,visit\n1,a\n", encoding="utf-8")
    (data / "notes.md").write_text("# Notes\n", encoding="utf-8")
    (data / "blob.bin").write_bytes(b"\x00\x01\x02")
    return data


def snapshot(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted(root.rglob("*")) if p.is_file() and ".d37-agent" not in p.parts}


class SchedulerTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = make_dataset(Path(self.temp.name))
        self.before = snapshot(self.data)

    def tearDown(self):
        self.temp.cleanup()

    def run_with(self, table_tool, cfg=None, documents=None):
        tools = {"table": ToolSpec(f"fake_tools:{table_tool}")}
        if documents:
            tools["documents"] = ToolSpec(f"fake_tools:{documents}")
        return start_run(self.data, cfg or config(), tools=tools, stages=NO_STAGES)

    def results(self, state):
        found = {}
        inventory = state.load_inventory()
        paths = {c.component_id: inventory.sources[[s.source_id for s in inventory.sources].index(c.source_ids[0])].relative_path
                 for c in inventory.components}
        for job in state.checkpoint["jobs"].values():
            if job["kind"] == "tool":
                found[paths[job["component_id"]]] = ToolResult.from_json(state.read_relative(job["outputs"]["result"]))
        return found


class RunTests(SchedulerTestCase):
    def test_full_run_in_worker_processes(self):
        state, status = self.run_with("count_lines", config("process", local_workers=2))
        self.assertEqual(status, "completed")
        results = self.results(state)
        self.assertEqual(results["patients.csv"].status, "complete")
        self.assertEqual(results["patients.csv"].measurements, {"line_count": 4})
        self.assertEqual(results["nested/visits.csv"].status, "complete")
        self.assertEqual(results["notes.md"].status, "unsupported")  # no documents tool registered
        self.assertEqual(results["blob.bin"].status, "unsupported")
        artifact = results["patients.csv"].artifacts[0]
        self.assertTrue(artifact.relative_path.startswith("artifacts/tool-"))
        self.assertEqual((state.run_dir / artifact.relative_path).read_text(), "4\n")
        for job in state.checkpoint["jobs"].values():
            self.assertEqual(job["status"], "done")
            if job["kind"] == "metadata":
                metadata = json.loads(state.read_relative(job["outputs"]["metadata"]))
                self.assertEqual(metadata["component_id"], job["component_id"])
        report = state.run_dir / "reports" / "revision-001" / "report.md"
        self.assertIn("patients.csv", report.read_text())
        types = [e["type"] for e in state.events()]
        for kind in ("run_created", "discovery_completed", "plan_reconciled", "job_started",
                     "job_completed", "report_written", "schedule_finished"):
            self.assertIn(kind, types)
        self.assertEqual(snapshot(self.data), self.before, "original data must not change")
        manifest = json.loads((state.run_dir / "manifest.json").read_text())
        self.assertIn("python", manifest["environment"])
        inventory = state.load_inventory()
        self.assertTrue(all(s.sha256 and len(s.sha256) == 64 for s in inventory.sources))

    def test_tool_exception_becomes_failed_result(self):
        state, status = self.run_with("explode")
        self.assertEqual(status, "completed")
        result = self.results(state)["patients.csv"]
        self.assertEqual(result.status, "failed")
        self.assertIn("RuntimeError: boom", result.limitations[0])
        self.assertEqual(result.coverage.mode, "none")

    def test_tool_timeout_in_worker_process(self):
        started = time.monotonic()
        state, status = self.run_with("hang", config("process", tool_timeout_seconds=1))
        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual(status, "completed")
        self.assertIn("exceeded 1 s", self.results(state)["patients.csv"].limitations[0])

    def test_invalid_results_are_rejected(self):
        for tool, message in (("wrong_ids", "reuse context.result_id"),
                              ("not_a_result", "expected ToolResult")):
            with self.subTest(tool=tool):
                state, _ = self.run_with(tool)
                result = self.results(state)["patients.csv"]
                self.assertEqual(result.status, "failed")
                self.assertIn(message, result.limitations[0])

    def test_unsafe_artifacts_are_dropped(self):
        state, _ = self.run_with("unsafe_artifact")
        result = self.results(state)["patients.csv"]
        self.assertEqual(result.artifacts, [])
        self.assertTrue(any("missing or unsafe" in t for t in result.limitations))

    def test_deadline_stops_and_leaves_resumable_jobs(self):
        state, status = self.run_with("hang", config("process", run_seconds=1))
        self.assertEqual(status, "incomplete")
        self.assertEqual(state.checkpoint["status"], "incomplete")
        pending = [j for j in state.checkpoint["jobs"].values() if j["status"] == "pending"]
        self.assertTrue(any(j["kind"] == "tool" for j in pending))
        self.assertIn("deadline_reached", [e["type"] for e in state.events()])
        self.assertFalse((state.run_dir / "lock").exists())

    def test_credentials_are_redacted_from_saved_outputs(self):
        with patch.dict(os.environ, {"NRP_KEY": SECRET}):
            state, _ = self.run_with("explode")
        for path in state.run_dir.rglob("*"):
            if path.is_file():
                self.assertNotIn(SECRET, path.read_text(errors="ignore"), path.name)

    def test_state_directory_inside_dataset_is_not_discovered(self):
        state_root = self.data / "agent-state"
        (state_root / "runs" / "old").mkdir(parents=True)
        (state_root / "runs" / "old" / "x.csv").write_text("a\n1\n")
        inventory = discover_inventory(self.data, state_root)
        self.assertFalse(any(s.relative_path.startswith("agent-state/") for s in inventory.sources))

    def test_collection_tool_for_multi_source_components(self):
        from agents.investigator.scheduler import plan_jobs
        from agents.investigator.discovery import discover
        from dataclasses import replace
        from agents.investigator.contracts import ComponentRef
        inventory = discover(self.data)
        ids = [s.source_id for s in inventory.sources if s.format == "csv"]
        grouped = replace(inventory, components=[ComponentRef("c_tables", "table", ids)])
        jobs = plan_jobs(grouped, {s.source_id: s.source_id for s in inventory.sources}, config(),
                         {"table": ToolSpec("fake_tools:count_lines", "fake_tools:collection")}, NO_STAGES)
        tool = next(j for j in jobs.values() if j["kind"] == "tool")
        self.assertEqual(tool["tool"], "fake_tools:collection")
        self.assertTrue(tool["collection"])


class StageTests(SchedulerTestCase):
    def test_semantics_stage_skipped_without_credentials(self):
        cfg = Config(limits=Limits(), execution=ExecutionSettings(backend="process", tool_isolation="inline"),
                     model=ModelSettings(api_key_env="D37_TEST_MISSING_KEY"))
        stages = Stages(semantics="fake_tools:count_lines", report=None, notebook=None)
        state, status = start_run(self.data, cfg, tools={"table": ToolSpec("fake_tools:count_lines")}, stages=stages)
        self.assertEqual(status, "completed")
        semantics = [j for j in state.checkpoint["jobs"].values() if j["kind"] == "semantics"]
        self.assertEqual(len(semantics), 4)
        self.assertTrue(all(j["result_status"] == "skipped" for j in semantics))


class ModelBudgetTests(unittest.TestCase):
    def test_total_budget(self):
        used = []
        budget = ModelBudget(max_total=3, max_concurrent=2, on_use=used.append)
        for _ in range(3):
            with budget.request():
                pass
        with self.assertRaises(BudgetExhausted):
            with budget.request():
                pass
        self.assertEqual((used, budget.remaining), ([1, 2, 3], 0))

    def test_concurrency_limit(self):
        budget = ModelBudget(max_total=30, max_concurrent=2)
        active, peak, lock = [0], [0], threading.Lock()

        def call():
            with budget.request():
                with lock:
                    active[0] += 1
                    peak[0] = max(peak[0], active[0])
                time.sleep(0.05)
                with lock:
                    active[0] -= 1

        threads = [threading.Thread(target=call) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(peak[0], 2)


if __name__ == "__main__":
    unittest.main()
