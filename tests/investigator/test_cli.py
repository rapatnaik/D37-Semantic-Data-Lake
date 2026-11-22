"""Settings, credentials, and end-to-end CLI integration."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agents.investigator.cli import main
from agents.investigator.config import Config, config_from_dict, load_config, redact
from test_scheduler import make_dataset, snapshot

SECRET = "nrp-secret-value-123456"
REPO = Path(__file__).resolve().parents[2]


def cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main([str(a) for a in args])
    return code, out.getvalue(), err.getvalue()


class ConfigTests(unittest.TestCase):
    def test_defaults_match_the_work_split(self):
        limits = Config().limits
        self.assertEqual(limits.run_seconds, 900)
        self.assertEqual(limits.local_workers, 4)
        self.assertEqual(limits.custom_code_workers, 1)
        self.assertEqual(limits.concurrent_model_requests, 2)
        self.assertEqual(limits.model_requests_per_run, 30)
        self.assertEqual(limits.repair_attempts, 2)
        self.assertEqual(Config().execution.backend, "docker")
        self.assertEqual(Config().model.name, "qwen3")
        self.assertEqual(Config().model.vision_name, "qwen3")

    def test_toml_settings(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "d37-agent.toml"
            path.write_text('seed = 7\n[limits]\nlocal_workers = 2\n[execution]\nbackend = "process"\n')
            config = load_config(path)
            self.assertEqual((config.seed, config.limits.local_workers, config.execution.backend), (7, 2, "process"))
            self.assertEqual(load_config(search_dir=temp), config)
        self.assertEqual(load_config(), Config())

    def test_invalid_settings_are_rejected(self):
        for data in ({"model": {"api_key": "abc"}}, {"nrp_token": "abc"}, {"limits": {"unknown": 1}},
                     {"limits": {"custom_code_workers": 2}}, {"limits": {"local_workers": "4"}},
                     {"execution": {"backend": "ssh"}}, {"limits": {"repair_attempts": 3}}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                config_from_dict(data)

    def test_credentials_come_from_the_environment(self):
        config = Config()
        self.assertIsNone(config.api_key({}))
        self.assertEqual(config.api_key({"NRP_KEY": SECRET}), SECRET)
        self.assertNotIn(SECRET, json.dumps(config.public_dict()))
        self.assertEqual(redact(f"token={SECRET}", environ={"NRP_KEY": SECRET}), "token=<redacted:NRP_KEY>")


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = make_dataset(Path(self.temp.name))
        self.before = snapshot(self.data)
        self.cwd = os.getcwd()
        os.chdir(self.temp.name)  # no stray d37-agent.toml from the repo

    def tearDown(self):
        os.chdir(self.cwd)
        self.temp.cleanup()

    def test_run_status_resume_ask_end_to_end(self):
        with patch.dict(os.environ, {"NRP_KEY": SECRET}):
            code, out, err = cli("run", self.data, "--backend", "process", "--no-model")
        self.assertEqual(code, 0, err)
        self.assertIn("completed", out)
        self.assertIn("[", err)  # progress lines
        run_dir = next((self.data / ".d37-agent" / "runs").iterdir())
        for name in ("manifest.json", "inventory.json", "checkpoint.json", "events.jsonl"):
            self.assertTrue((run_dir / name).is_file(), name)
        self.assertTrue((run_dir / "reports" / "revision-001" / "report.md").is_file())

        code, out, _ = cli("status", self.data, "--json")
        status = json.loads(out)
        self.assertEqual((code, status["status"], status["run_id"]), (0, "completed", run_dir.name))

        code, out, _ = cli("runs", self.data)
        self.assertIn(run_dir.name, out)

        (self.data / "notes.md").write_text("# Changed\n", encoding="utf-8")
        code, _, err = cli("resume", run_dir)
        self.assertEqual(code, 0)
        self.assertIn("1 changed", err)
        self.before["notes.md"] = ((self.data / "notes.md").read_bytes(), (self.data / "notes.md").stat().st_mtime_ns)

        script = Path(self.temp.name) / "analysis.py"
        script.write_text("save_json('rows.json', {'n': len(open(INPUT_FILES['patients.csv']).read().splitlines())})\n")
        code, out, err = cli("ask", self.data, "How many lines?", "--code", script, "--input", "patients.csv")
        self.assertEqual(code, 0, out + err)
        self.assertIn("succeeded", out)
        outputs = list((run_dir / "analyses").glob("*/outputs/rows.json"))
        self.assertEqual(json.loads(outputs[0].read_text()), {"n": 4})
        self.assertEqual(len(list((run_dir / "sessions").glob("*.json"))), 1)

        for path in run_dir.rglob("*"):
            if path.is_file():
                self.assertNotIn(SECRET, path.read_text(errors="ignore"), path.name)
        self.assertEqual(snapshot(self.data), self.before)

    def test_errors_exit_nonzero(self):
        code, _, err = cli("status", Path(self.temp.name) / "empty")
        self.assertEqual(code, 1)
        self.assertIn("error:", err)
        code, _, err = cli("ask", self.data, "q")
        self.assertEqual(code, 1)

    def test_ask_without_reasoning_module_explains(self):
        cli("run", self.data, "--backend", "process", "--no-model", "-q")
        code, _, err = cli("ask", self.data, "What is in here?")
        self.assertEqual(code, 1)
        self.assertIn("reasoning module", err)

    def test_time_limit_exit_code(self):
        with patch("agents.investigator.scheduler.Stopwatch.expired", return_value=True):
            code, _, err = cli("run", self.data, "--backend", "process", "--no-model", "-q")
        self.assertEqual(code, 3)
        self.assertIn("resume", err)

    def test_module_entry_point(self):
        completed = subprocess.run([sys.executable, "-m", "agents.investigator", "--help"],
                                   cwd=REPO, capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 0)
        for command in ("run", "resume", "status", "ask"):
            self.assertIn(command, completed.stdout)


if __name__ == "__main__":
    unittest.main()
