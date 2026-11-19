"""Isolated execution of generated analysis code, plus the repair loop."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from agents.investigator import discover
from agents.investigator.config import Config, ExecutionSettings, Limits
from agents.investigator.contracts import AnalysisRequest
from agents.investigator.execution import (
    ExecutionContext, ExecutionResult, docker_command, execute_analysis, load_execution_result,
)
from agents.investigator.session import Completion, manual_chooser, run_followup
from agents.investigator.state import RunState

SECRET = "nrp-secret-value-123456"


def process_config(**limits):
    return Config(limits=Limits(**{"analysis_timeout_seconds": 20, **limits}),
                  execution=ExecutionSettings(backend="process", tool_isolation="inline"))


class ExecutionTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.data = base / "data"
        self.data.mkdir()
        (self.data / "patients.csv").write_text("id,age,group\n1,30,A\n2,,A\n3,41,B\n", encoding="utf-8")
        self.inventory = discover(self.data)
        self.source = self.inventory.sources[0]
        self.run_dir = base / "run"
        (self.run_dir / "analyses").mkdir(parents=True)
        self.original = (self.data / "patients.csv").read_bytes(), (self.data / "patients.csv").stat().st_mtime_ns

    def tearDown(self):
        self.temp.cleanup()

    def request(self, code, expected=("application/json",), inputs=None, parameters=None):
        return AnalysisRequest(question="test question", code=code,
                               input_ids=inputs or [self.source.source_id],
                               parameters=parameters or {}, expected_outputs=list(expected))

    def execute(self, code, config=None, **kwargs):
        context = ExecutionContext(self.run_dir, self.data, self.inventory, config or process_config())
        return execute_analysis(self.request(code, **kwargs), context)

    def assertOriginalUnchanged(self):
        path = self.data / "patients.csv"
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), self.original)


class ProcessBackendTests(ExecutionTestCase):
    def test_success_validates_outputs_and_retains_records(self):
        code = (
            "import csv\n"
            "rows = list(csv.DictReader(open(INPUTS[list(INPUTS)[0]])))\n"
            "blank = sum(r['age'] == '' for r in rows if r['group'] == PARAMETERS['group'])\n"
            "save_json('counts.json', {'rows': len(rows), 'blank': blank, 'seed': SEED})\n"
            "print('done')\n"
        )
        result = self.execute(code, parameters={"group": "A"})
        self.assertEqual(result.status, "succeeded", result.error)
        self.assertEqual(result.backend, "process")
        output = result.outputs[0]
        self.assertEqual(output.media_type, "application/json")
        self.assertTrue(output.relative_path.startswith(f"analyses/{result.job_id}/outputs/"))
        self.assertEqual(json.loads((self.run_dir / output.relative_path).read_text()),
                         {"rows": 3, "blank": 1, "seed": 0})
        job = self.run_dir / "analyses" / result.job_id
        for name in ("request.json", "code.py", "result.json", "stdout.log", "stderr.log"):
            self.assertTrue((job / name).is_file(), name)
        self.assertIn("done", (job / "stdout.log").read_text())
        self.assertEqual(load_execution_result(job / "result.json"), result)
        fingerprint = result.input_fingerprints[self.source.source_id]
        self.assertEqual(len(fingerprint["sha256"]), 64)
        self.assertTrue(result.environment["python"])
        self.assertTrue(any("does not establish correctness" in t for t in result.limitations))
        self.assertTrue(any("network access was not blocked" in t for t in result.limitations))
        self.assertFalse(any((job / "inputs").rglob("*.csv")), "input copies are removed after the run")
        self.assertOriginalUnchanged()

    def test_environment_has_no_credentials(self):
        code = "import os\nsave_json('env.json', sorted(os.environ))\n"
        with patch.dict(os.environ, {"NRP_KEY": SECRET, "AWS_SECRET_ACCESS_KEY": SECRET}):
            result = self.execute(code)
        self.assertEqual(result.status, "succeeded", result.error)
        names = json.loads((self.run_dir / result.outputs[0].relative_path).read_text())
        self.assertNotIn("NRP_KEY", names)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", names)

    def test_inputs_are_read_only_copies(self):
        code = (
            "path = list(INPUTS.values())[0]\n"
            "try:\n"
            "    open(path, 'a').write('tamper')\n"
            "    outcome = 'written'\n"
            "except PermissionError:\n"
            "    outcome = 'denied'\n"
            "save_json('attempt.json', {'outcome': outcome})\n"
        )
        result = self.execute(code)
        self.assertEqual(result.status, "succeeded", result.error)
        self.assertEqual(json.loads((self.run_dir / result.outputs[0].relative_path).read_text())["outcome"], "denied")
        self.assertOriginalUnchanged()

    def test_failure_reports_error_without_host_paths(self):
        result = self.execute("raise ValueError('bad column')\n")
        self.assertEqual(result.status, "failed")
        self.assertIn("ValueError: bad column", result.error)
        self.assertNotIn(str(self.run_dir), result.error)

    def test_timeout_stops_the_worker(self):
        result = self.execute("while True:\n    pass\n", config=process_config(analysis_timeout_seconds=1))
        self.assertEqual(result.status, "timed_out")
        self.assertIn("exceeded", result.error)

    def test_unknown_inputs_are_rejected_before_running(self):
        marker = Path(self.temp.name) / "ran"
        result = self.execute(f"open({str(marker)!r}, 'w').write('x')\n", inputs=["source_unknown"])
        self.assertEqual(result.status, "rejected")
        self.assertFalse(marker.exists())

    def test_changed_input_is_rejected(self):
        os.utime(self.data / "patients.csv", ns=(1, 1))
        result = self.execute("save_json('x.json', 1)\n")
        self.assertEqual(result.status, "rejected")
        self.assertIn("changed since discovery", result.error)

    def test_disallowed_and_invalid_outputs_are_removed(self):
        code = (
            "import os\n"
            "open('tool.exe', 'w').write('x')\n"
            "open('bad.json', 'w').write('{\"x\": NaN}')\n"
            "open('fake.png', 'w').write('not a png')\n"
            "os.symlink('/etc/passwd', 'link.txt')\n"
            "save_json('good.json', {'ok': True})\n"
        )
        result = self.execute(code)
        self.assertEqual(result.status, "failed")
        self.assertEqual([a.relative_path.rsplit('/', 1)[1] for a in result.outputs], ["good.json"])
        remaining = sorted(p.name for p in (self.run_dir / "analyses" / result.job_id / "outputs").iterdir())
        self.assertEqual(remaining, ["good.json"])
        for fragment in ("Unsupported output type", "invalid JSON", "not a PNG", "Non-regular output"):
            self.assertTrue(any(fragment in t for t in result.limitations), fragment)

    def test_missing_expected_output_fails(self):
        result = self.execute("save_json('a.json', 1)\n", expected=("application/json", "image/png"))
        self.assertEqual(result.status, "failed")
        self.assertIn("Expected output not produced: image/png", result.error)

    def test_output_count_limit(self):
        code = "for i in range(5):\n    save_json(f'{i}.json', i)\n"
        result = self.execute(code, config=process_config(max_output_files=2))
        self.assertEqual(len(result.outputs), 2)
        self.assertEqual(result.status, "failed")

    def test_custom_code_can_be_disabled(self):
        config = replace(process_config(), limits=replace(Limits(), custom_code_workers=0))
        result = self.execute("save_json('x.json', 1)\n", config=config)
        self.assertEqual(result.status, "unsupported")

    def test_execution_result_contract(self):
        result = self.execute("save_json('x.json', 1)\n")
        self.assertEqual(ExecutionResult.from_json(result.to_json()), result)
        with self.assertRaises(ValueError):
            replace(result, status="exploded")
        with self.assertRaises(ValueError):
            replace(result, status="failed", error=None, limitations=[])


class DockerCommandTests(ExecutionTestCase):
    def test_command_isolates_network_credentials_and_inputs(self):
        job = self.run_dir / "analyses" / "a001-x"
        odd = self.data / "a, b.csv"
        command = docker_command(job, [(self.source, odd)], Config(), "d37-test")
        text = " ".join(command)
        for flag in ("--network none", "--read-only", "--cap-drop ALL", "no-new-privileges",
                     "--user 65534:65534", "--pids-limit", "--memory 1024m", "--pull never"):
            self.assertIn(flag, text)
        self.assertNotIn("NRP_KEY", text)
        self.assertNotIn("--env-file", text)
        mounts = [command[i + 1] for i, part in enumerate(command) if part == "--mount"]
        inputs = [m for m in mounts if "/work/inputs/" in m]
        self.assertEqual(len(inputs), 1)
        self.assertTrue(inputs[0].endswith("readonly"))
        self.assertIn('"src=', inputs[0])  # comma in path is quoted
        writable = [m for m in mounts if not m.endswith("readonly")]
        self.assertEqual(sorted(m.rsplit("dst=", 1)[1] for m in writable), ["/work/meta", "/work/outputs"])

    def test_missing_docker_is_reported_not_bypassed(self):
        config = Config(execution=ExecutionSettings(backend="docker", docker_command="no-such-docker-binary"))
        result = self.execute("save_json('x.json', 1)\n", config=config)
        self.assertEqual(result.status, "unsupported")
        self.assertIn("Docker is not installed", result.limitations[0])


def _docker_image_ready():
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "image", "inspect", Config().execution.image],
                              capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@unittest.skipUnless(_docker_image_ready(), "worker image not built (see containers/investigator/Dockerfile)")
class DockerIntegrationTests(ExecutionTestCase):
    def test_docker_worker_runs_without_network(self):
        code = (
            "import socket, pandas\n"
            "try:\n"
            "    socket.create_connection(('1.1.1.1', 53), timeout=3)\n"
            "    network = 'open'\n"
            "except OSError:\n"
            "    network = 'blocked'\n"
            "frame = pandas.read_csv(INPUT_FILES['patients.csv'])\n"
            "save_json('out.json', {'network': network, 'rows': len(frame)})\n"
        )
        with patch.dict(os.environ, {"NRP_KEY": SECRET}):
            result = self.execute(code, config=Config())
        self.assertEqual(result.status, "succeeded", result.error)
        self.assertEqual(json.loads((self.run_dir / result.outputs[0].relative_path).read_text()),
                         {"network": "blocked", "rows": 3})
        self.assertEqual(result.environment["backend"], "docker")
        self.assertIn("pandas", result.environment["packages"])
        self.assertOriginalUnchanged()


class RepairLoopTests(ExecutionTestCase):
    def setUp(self):
        super().setUp()
        shutil.rmtree(self.run_dir)
        self.state = RunState.create(Path(self.temp.name) / "state", self.data, process_config())
        self.state.save_inventory(self.inventory)

    def scripted(self, codes):
        calls = []

        def choose(context):
            calls.append(context)
            if context.last_execution is not None and context.last_execution.succeeded:
                return Completion("done", evidence=[o.relative_path for o in context.last_execution.outputs])
            return self.request(codes[min(len(calls) - 1, len(codes) - 1)])
        return choose, calls

    def test_two_repairs_then_success(self):
        choose, calls = self.scripted(["raise KeyError('a')", "raise KeyError('b')", "save_json('ok.json', 1)"])
        record = run_followup(self.state, "q", chooser=choose, config=process_config(), refresh_report=False)
        self.assertEqual(record["status"], "answered")
        analyses = [s for s in record["steps"] if s["action"] == "analysis"]
        self.assertEqual([s["attempt"] for s in analyses], [0, 1, 2])
        self.assertEqual(calls[1].repairs_remaining, 1)
        self.assertIn("KeyError", calls[1].last_execution.error)
        repaired = load_execution_result(self.state.run_dir / analyses[1]["result_path"])
        self.assertEqual(repaired.repair_of, analyses[0]["job_id"])

    def test_third_failure_stops(self):
        choose, _ = self.scripted(["raise KeyError('x')"])
        record = run_followup(self.state, "q", chooser=choose, config=process_config(), refresh_report=False)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(sum(s["action"] == "analysis" for s in record["steps"]), 3)
        saved = json.loads((self.state.run_dir / "sessions" / f"{record['session_id']}.json").read_text())
        self.assertEqual(saved["status"], "failed")

    def test_manual_analysis_and_report_revision(self):
        record = run_followup(self.state, "q", chooser=manual_chooser(self.request("save_json('a.json', 2)")),
                              config=process_config())
        self.assertEqual(record["status"], "answered")
        self.assertTrue((self.state.run_dir / "reports" / "revision-001" / "report.md").is_file())


if __name__ == "__main__":
    unittest.main()
