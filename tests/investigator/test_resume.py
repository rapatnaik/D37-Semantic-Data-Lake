"""Checkpoint recovery and source-change invalidation."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from agents.investigator.scheduler import ToolSpec, resume_run, start_run
from agents.investigator.state import RunLockedError, RunState
from test_scheduler import NO_STAGES, config, make_dataset

TOOLS = {"table": ToolSpec("fake_tools:count_lines")}


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = make_dataset(Path(self.temp.name))
        self.state, status = start_run(self.data, config(), tools=TOOLS, stages=NO_STAGES)
        self.assertEqual(status, "completed")

    def tearDown(self):
        self.temp.cleanup()

    def resume(self, tools=TOOLS, **options):
        state, status = resume_run(self.state.run_dir, tools=tools, stages=NO_STAGES, **options)
        self.assertEqual(status, "completed")
        return state

    def attempts(self, state):
        return {job_id: job.get("attempts", 0) for job_id, job in state.checkpoint["jobs"].items()}

    def last_plan(self, state):
        return [e for e in state.events() if e["type"] == "plan_reconciled"][-1]

    def tool_job(self, state, relative_path):
        inventory = state.load_inventory()
        source = next(s for s in inventory.sources if s.relative_path == relative_path)
        component = next(c for c in inventory.components if source.source_id in c.source_ids)
        return next(j for j in state.checkpoint["jobs"].values()
                    if j["kind"] == "tool" and j["component_id"] == component.component_id)

    def test_resume_without_changes_reuses_everything(self):
        before = self.attempts(self.state)
        state = self.resume()
        self.assertEqual(self.attempts(state), before)
        self.assertEqual(self.last_plan(state)["invalidated"], 0)
        self.assertEqual(self.last_plan(state)["new"], 0)

    def test_changed_source_invalidates_only_its_chain(self):
        (self.data / "patients.csv").write_text("id,age\n1,30\n", encoding="utf-8")
        state = self.resume()
        plan = self.last_plan(state)
        self.assertEqual(plan["invalidated"], 3)  # its tool job, its metadata, and the report
        changed = self.tool_job(state, "patients.csv")
        self.assertEqual(changed["attempts"], 2)
        self.assertEqual(changed["outputs"]["result"].rsplit("/", 1)[1], "v002.json")
        self.assertEqual(self.tool_job(state, "nested/visits.csv")["attempts"], 1)
        self.assertTrue((state.run_dir / "results" / changed["outputs"]["result"].split("/")[1] / "v001.json").exists(),
                        "older versions are retained")
        self.assertTrue((state.run_dir / "reports" / "revision-002").is_dir())
        self.assertIn("source_changed", [e["type"] for e in state.events()])

    def test_touched_but_identical_file_is_not_rerun(self):
        path = self.data / "patients.csv"
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
        state = self.resume()
        self.assertEqual(self.last_plan(state)["invalidated"], 0)
        self.assertEqual(self.tool_job(state, "patients.csv")["attempts"], 1)

    def test_added_and_removed_sources(self):
        (self.data / "nested" / "visits.csv").unlink()
        (self.data / "extra.csv").write_text("a\n1\n2\n", encoding="utf-8")
        state = self.resume()
        plan = self.last_plan(state)
        self.assertEqual(plan["removed"], 2)  # tool + metadata jobs for visits.csv
        self.assertEqual(plan["new"], 2)
        self.assertEqual(self.tool_job(state, "extra.csv")["result_status"], "complete")
        types = [e["type"] for e in state.events()]
        self.assertIn("source_added", types)
        self.assertIn("source_removed", types)

    def test_crash_recovery_from_running_jobs_and_torn_events(self):
        checkpoint = json.loads((self.state.run_dir / "checkpoint.json").read_text())
        job = self.tool_job(self.state, "patients.csv")
        job_id = next(k for k, v in checkpoint["jobs"].items() if v["component_id"] == job["component_id"] and v["kind"] == "tool")
        checkpoint["jobs"][job_id]["status"] = "running"
        checkpoint["status"] = "running"
        (self.state.run_dir / "checkpoint.json").write_text(json.dumps(checkpoint))
        with (self.state.run_dir / "events.jsonl").open("a") as handle:
            handle.write('{"type": "job_comp')  # torn line from a crash
        (self.state.run_dir / "lock").write_text("999999999")  # dead process
        state = self.resume()
        self.assertEqual(state.checkpoint["jobs"][job_id]["status"], "done")
        self.assertEqual(state.checkpoint["jobs"][job_id]["attempts"], 2)
        self.assertIn("stale_lock_removed", [e["type"] for e in state.events()])

    def test_live_lock_blocks_a_second_process(self):
        (self.state.run_dir / "lock").write_text(str(os.getppid()))
        with self.assertRaises(RunLockedError):
            resume_run(self.state.run_dir, tools=TOOLS, stages=NO_STAGES)
        (self.state.run_dir / "lock").unlink()

    def test_deferred_tool_runs_once_it_exists(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        data = make_dataset(Path(temp.name))
        state, _ = start_run(data, config(), tools={"table": ToolSpec("missing_module:profile")}, stages=NO_STAGES)
        self.assertEqual(self.tool_job(state, "patients.csv")["result_status"], "deferred")
        state, _ = resume_run(state.run_dir, tools=TOOLS, stages=NO_STAGES)
        self.assertEqual(self.tool_job(state, "patients.csv")["result_status"], "complete")

    def test_retry_failed_reruns_dependents(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        data = make_dataset(Path(temp.name))
        state, _ = start_run(data, config(), tools={"table": ToolSpec("fake_tools:explode")}, stages=NO_STAGES)
        state, _ = resume_run(state.run_dir, tools={"table": ToolSpec("fake_tools:explode")}, stages=NO_STAGES)
        self.assertEqual(self.tool_job(state, "patients.csv")["attempts"], 1, "failed results are kept by default")
        state, _ = resume_run(state.run_dir, tools={"table": ToolSpec("fake_tools:explode")}, stages=NO_STAGES,
                              retry_failed=True)
        self.assertEqual(self.tool_job(state, "patients.csv")["attempts"], 2)
        metadata = [j for j in state.checkpoint["jobs"].values() if j["kind"] == "metadata"]
        self.assertTrue(all(j["outputs"]["metadata"].endswith("v002.json") for j in metadata
                            if j["component_id"] == self.tool_job(state, "patients.csv")["component_id"]))

    def test_checkpoint_survives_reopen(self):
        reopened = RunState.open(self.state.run_dir)
        self.assertEqual(reopened.checkpoint["jobs"], self.state.checkpoint["jobs"])
        self.assertEqual(reopened.config(), self.state.config())


if __name__ == "__main__":
    unittest.main()
