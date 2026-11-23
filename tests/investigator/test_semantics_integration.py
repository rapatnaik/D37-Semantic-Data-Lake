"""Verify dictionary reconciliation, provenance, and selective resume."""

import base64
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from agents import semantic_agent
from agents.investigator import scheduler
from agents.investigator.config import Config, ExecutionSettings, Limits, ModelSettings
from agents.investigator.scheduler import resume_run, start_run
from agents.investigator.state import RunState, latest_run
from agents.investigator.tools import documents, tables


REPO = Path(__file__).resolve().parents[2]
DEMO = REPO / "examples" / "status_dictionary_demo"


def outputs(state, kind):
    inventory = state.load_inventory()
    sources = {source.source_id: source.relative_path for source in inventory.sources}
    paths = {c.component_id: sources[c.source_ids[0]] for c in inventory.components}
    return {
        paths[job["component_id"]]: job["outputs"][kind]
        for job in state.checkpoint["jobs"].values()
        if job["kind"] == ("tool" if kind == "result" else kind) and job["status"] == "done"
    }


def report_path(state):
    return state.run_dir / state.checkpoint["jobs"]["report"]["outputs"]["report"]


def profile(state, path):
    return json.loads(state.read_relative(outputs(state, "semantics")[path]))


def rows(profile, name):
    return {row["value"]: row for row in profile["columns"][name]["values"]}


def definitions(row):
    return {item["label"]: [(c["source_path"], c["locator"]) for c in item["citations"]]
            for item in row["definitions"]}


class SemanticCLITests(unittest.TestCase):
    def test_offline_fixture_and_dictionary_correction(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / "data"
            shutil.copytree(DEMO, data)
            environ = {name: value for name, value in os.environ.items() if name != "NRP_KEY"}

            def cli(*args):
                proc = subprocess.run([sys.executable, "-m", "agents.investigator", *args, str(data)],
                                      cwd=REPO, env=environ, capture_output=True, text=True, timeout=120)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                return RunState.open(latest_run(data / ".d37-agent"))

            state = cli("run", "--backend", "process")
            table = "status.csv"
            original_tool = outputs(state, "result")[table]
            original_metadata = outputs(state, "metadata")[table]
            original_profile = outputs(state, "semantics")[table]
            original_report = report_path(state)
            self.assertEqual(state.checkpoint["model_requests_used"], 0)
            saved = profile(state, table)
            self.assertEqual(saved["coverage"]["examined"], 6)
            codes = rows(saved, "status")
            self.assertEqual({k: v["count"] for k, v in codes.items()}, {0: 2, 1: 3, 9: 1})
            self.assertEqual(definitions(codes[0]), {"inactive": [("dictionary_a.txt", "line 3"),
                                                                 ("dictionary_b.txt", "line 3")]})
            self.assertEqual(definitions(codes[1]), {"active": [("dictionary_a.txt", "line 4")],
                                                    "pending": [("dictionary_b.txt", "line 4")]})
            self.assertEqual([(k, v["status"]) for k, v in sorted(codes.items())],
                             [(0, "documented"), (1, "conflict"), (9, "unresolved")])
            self.assertEqual({(item["reason"], item["value"]) for item in saved["needs_verification"]},
                             {("conflicting_definitions", 1), ("undocumented_code", 9)})
            self.assertEqual(saved["observation"]["result_path"], original_tool)

            text = original_report.read_text()
            self.assertNotIn("Coded columns", text)
            self.assertIn(f"[Saved semantic profile JSON](../../{original_profile})", text)

            dictionary_b = data / "dictionary_b.txt"
            dictionary_b.write_text(dictionary_b.read_text().replace("pending", "active"), encoding="utf-8")
            updated = cli("resume")
            self.assertEqual(updated.run_id, state.run_id)
            self.assertEqual(outputs(updated, "result")[table], original_tool)
            self.assertEqual(outputs(updated, "metadata")[table], original_metadata)
            self.assertNotEqual(outputs(updated, "semantics")[table], original_profile)
            self.assertNotEqual(report_path(updated), original_report)
            self.assertEqual(updated.checkpoint["model_requests_used"], 0)
            corrected = profile(updated, table)
            corrected_codes = rows(corrected, "status")
            self.assertEqual(definitions(corrected_codes[1]), {"active": [("dictionary_a.txt", "line 4"),
                                                                           ("dictionary_b.txt", "line 4")]})
            self.assertEqual(corrected_codes[1]["status"], "documented")
            self.assertEqual(corrected_codes[9], codes[9])
            self.assertEqual([item["reason"] for item in corrected["needs_verification"]], ["undocumented_code"])
            refreshed_profile = outputs(updated, "semantics")[table]
            self.assertIn(f"[Saved semantic profile JSON](../../{refreshed_profile})", report_path(updated).read_text())
            self.assertEqual(original_report.read_text(), text)
            self.assertEqual(json.loads(updated.read_relative(original_profile)), saved)

            unchanged = cli("resume")
            for kind in ("result", "metadata", "semantics"):
                self.assertEqual(outputs(unchanged, kind), outputs(updated, kind))
            self.assertEqual(report_path(unchanged), report_path(updated))
            self.assertEqual(unchanged.checkpoint["report_revisions"], updated.checkpoint["report_revisions"])


class SemanticStageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name)
        self.config = Config(model=ModelSettings(enabled=False),
                             execution=ExecutionSettings(backend="process", tool_isolation="inline"))
        plots = patch.object(tables, "attach_table_plots", side_effect=lambda result, *_: result)
        plots.start()
        self.addCleanup(plots.stop)

    def write(self, name, content):
        path = self.data / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def run_dataset(self, config=None):
        state, status = start_run(self.data, config or self.config)
        self.assertEqual(status, "completed")
        self.assertEqual(state.checkpoint["jobs"]["report"]["result_status"], "complete")
        return state

    def resume_dataset(self, state):
        updated, status = resume_run(state.run_dir)
        self.assertEqual(status, "completed")
        self.assertEqual(updated.checkpoint["jobs"]["report"]["result_status"], "complete")
        return updated

    def test_link_addition_retargeting_and_removal(self):
        north, south = "north/events.csv", "south/events.csv"
        self.write(north, "code\n1\n")
        self.write(south, "code\n1\n")
        state = self.run_dataset()

        def changed(state, expected):
            before, table_results = outputs(state, "semantics"), outputs(state, "result")
            updated = self.resume_dataset(state)
            after, new_results = outputs(updated, "semantics"), outputs(updated, "result")
            self.assertEqual({name for name in before if before[name] != after[name]}, expected)
            self.assertEqual({name: table_results[name] for name in before}, {name: new_results[name] for name in after})
            return updated

        a = f"Table: {north}\nColumn: code\n1 = North\n"
        b = f"Table: {south}\nColumn: code\n1 = South\n"
        dictionary = self.write("linked.txt", a)
        state = changed(state, {north})
        self.assertEqual(rows(profile(state, north), "code")[1]["status"], "documented")
        self.write("linked.txt", a + b)
        state = changed(state, {south})
        self.write("linked.txt", b)
        state = changed(state, {north, south})  # South's citation moved to a new line.
        self.assertEqual(rows(profile(state, north), "code")[1]["status"], "unresolved")
        self.write("linked.txt", a)
        state = changed(state, {north, south})
        dictionary.unlink()
        state = changed(state, {north})

        self.write("ambiguous.txt", "Table: events.csv\nColumn: code\n1 = Ambiguous\n")
        self.write("unrelated.txt", "Table: unrelated.csv\nColumn: code\n1 = Unrelated\n")
        state = changed(state, set())
        self.assertEqual({issue["reason"] for issue in state.checkpoint["dictionary_reference_issues"]},
                         {"ambiguous_table", "missing_table"})
        for name in (north, south):
            saved = profile(state, name)
            self.assertEqual(rows(saved, "code")[1]["definitions"], [])
            self.assertEqual(saved["needs_verification"][0]["reason"], "no_linked_dictionary")
        text = report_path(state).read_text()
        self.assertIn("matches multiple tables", text)
        self.assertIn("ambiguous.txt (line 3)", text)
        self.assertIn("unrelated.txt (line 3)", text)

        self.write("wrong-column.txt", f"Table: {north}\nColumn: Code\n1 = Incorrect\n")
        state = changed(state, {north})
        issue = next(item for item in profile(state, north)["needs_verification"] if item["reason"] == "missing_column")
        self.assertEqual(issue["citations"][0]["locator"], "line 3")
        self.assertIn("wrong-column.txt (line 3)", report_path(state).read_text())

    def test_sampled_values_missingness_truncation_and_text_codes(self):
        data = "status,text_code,identifier,category\n"
        for i in range(40):
            data += f"{i % 3},{('01', '1', '')[i % 3]},{100 + i},category{i % 10}\n"
        self.write("sample.csv", data)
        self.write("dictionary.txt", "Table: sample.csv\nColumn: text_code\n01 = padded\n1 = plain\n"
                   "2 = absent\nColumn: identifier\n100 = first\n")
        with patch.object(tables, "MAX_SOURCE_BYTES", 1), patch.object(tables, "DEFAULT_SAMPLE_SIZE", 30):
            state = self.run_dataset()
        saved = profile(state, "sample.csv")
        measurement = json.loads(state.read_relative(outputs(state, "result")["sample.csv"]))["measurements"]
        self.assertEqual((saved["coverage"]["mode"], saved["coverage"]["examined"], saved["coverage"]["total"]),
                         ("sample", 30, 40))
        for name in ("status", "text_code", "category"):
            facts = measurement["columns"][name]
            column = saved["columns"][name]
            self.assertEqual(column["null_count"], facts["null_count"])
            self.assertTrue(column["sampled"])
            self.assertFalse(column["truncated"])
            observed = {row["value"]: row["count"] for row in column["values"]}
            self.assertEqual(observed, {row["value"]: row["count"] for row in facts["value_frequencies"]["values"]})
            self.assertEqual(sum(observed.values()) + column["null_count"], 30)
        self.assertEqual(len(measurement["columns"]["category"]["top_values"]), 5)
        self.assertEqual(len(rows(saved, "category")), 10)
        self.assertTrue(saved["columns"]["identifier"]["truncated"])
        self.assertEqual(rows(saved, "identifier"), {})
        text = rows(saved, "text_code")
        self.assertEqual(set(text), {"01", "1"})
        self.assertEqual(set(definitions(text["01"])), {"padded"})
        self.assertEqual(set(definitions(text["1"])), {"plain"})
        self.assertEqual(saved["columns"]["text_code"]["null_count"], rows(saved, "status")[2]["count"])
        self.assertIn("absent", [e["label"] for e in saved["dictionary_entries"]])
        self.assertIn("sample: 30/40 rows", report_path(state).read_text())

    def test_partial_document_cites_only_complete_definitions(self):
        self.write("sample.csv", "code\n0\n1\n")
        complete = "Table: sample.csv\nColumn: code\n0 = inactive\n"
        self.write("dictionary.txt", complete + "1 = active with a long qualification\n")
        original_limit = documents._limit
        with patch.object(documents, "_limit",
                          side_effect=lambda context, key, default: len(complete) + 8 if key == "max_text_chars"
                          else original_limit(context, key, default)):
            state = self.run_dataset()
        saved = profile(state, "sample.csv")
        self.assertEqual(rows(saved, "code")[0]["status"], "documented")
        self.assertEqual(rows(saved, "code")[1]["status"], "unresolved")
        limitation, = saved["dictionary_coverage_limitations"]
        self.assertEqual(limitation["status"], "partial")
        self.assertEqual(limitation["citations"][0]["locator"], "line 1")

    def test_checkpoint_resumes_between_each_phase(self):
        self.write("sample.csv", "code\n1\n")
        self.write("dictionary.txt", "Table: sample.csv\nColumn: code\n1 = active\n")
        with patch.object(scheduler.Scheduler, "_run_semantics", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                start_run(self.data, self.config)
        run = latest_run(self.data / ".d37-agent")
        interrupted = RunState.open(run)
        self.assertEqual(interrupted.checkpoint["status"], "interrupted")
        self.assertEqual(len(outputs(interrupted, "metadata")), 2)
        self.assertEqual(outputs(interrupted, "semantics"), {})
        with patch.object(scheduler.Scheduler, "_run_report", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                resume_run(run)
        reconciled = RunState.open(run)
        self.assertEqual(outputs(reconciled, "metadata"), outputs(interrupted, "metadata"))
        self.assertEqual(len(outputs(reconciled, "semantics")), 1)
        updated = self.resume_dataset(reconciled)
        self.assertEqual(outputs(updated, "semantics"), outputs(reconciled, "semantics"))
        self.assertEqual(rows(profile(updated, "sample.csv"), "code")[1]["status"], "documented")

    def test_concurrent_five_column_batches_merge_out_of_order(self):
        names = [f"col{i:02d}" for i in range(16)]
        self.write("wide.csv", ",".join(names) + "\n" + ",".join(["1"] * len(names)) + "\n")
        overlap = threading.Barrier(3)
        final_batch_started = threading.Event()
        seen = []

        def request(prompt, *args, **kwargs):
            batch = list(json.loads(prompt.split("\n\n")[-1])["columns"])
            seen.append(batch)
            if len(batch) == 5:
                overlap.wait(timeout=5)
            else:
                final_batch_started.set()
            if batch == names[:5]:
                self.assertTrue(final_batch_started.wait(timeout=5))
            if batch == names[5:10]:
                raise TimeoutError()
            return json.dumps({name: {"description": name, "semantic_type": "code", "unit": None,
                                      "evidence": [], "needs_verification": []} for name in batch})

        config = replace(self.config, model=ModelSettings())
        with patch.dict(os.environ, {config.model.api_key_env: "test-key"}), \
                patch.object(semantic_agent, "request_completion", side_effect=request):
            state = self.run_dataset(config)
        self.assertCountEqual(seen, [names[:5], names[5:10], names[10:15], names[15:]])
        interpretation = profile(state, "wide.csv")["model_interpretation"]
        self.assertEqual(interpretation["status"], "partial")
        self.assertEqual(list(interpretation["columns"]), names[:5] + names[10:])
        for name, entry in interpretation["columns"].items():
            self.assertEqual(entry["description"], name)
        self.assertEqual(interpretation["batch_issues"][0]["columns"], names[5:10])
        self.assertEqual(state.checkpoint["model_requests_used"], 4)
        self.assertIn("Model batch failed for col05", report_path(state).read_text())

    def test_default_model_valid_malformed_missing_and_shared_budget(self):
        self.write("a.csv", "code\n1\n1\n")
        self.write("b.csv", "code\n1\n1\n")
        self.write("dictionary.txt", "Table: b.csv\nColumn: code\n1 = active\n1 = pending\n")
        reply = json.dumps({"code": {"description": "A status code", "semantic_type": "code", "unit": None,
                                     "evidence": [], "needs_verification": ["Verify encoding"], "count": 100}})
        model = ModelSettings(endpoint="https://model.example/v1/chat/completions", name="test-model",
                              api_key_env="D37_TEST_SEMANTIC_KEY")
        config = Config(model=model, limits=Limits(model_requests_per_run=1), execution=self.config.execution)
        with patch.object(semantic_agent, "request_completion", return_value=reply) as request:
            with patch.dict(os.environ, {model.api_key_env: "test-credential"}):
                offline = self.run_dataset(replace(config, model=replace(model, enabled=False)))
                request.assert_not_called()
                enriched = self.run_dataset(config)
            request.assert_called_once()
            args, kwargs = request.call_args
            self.assertIn('"dataset":"a.csv"', args[0])
            self.assertEqual(args[1], model.name)
            self.assertEqual(kwargs, {"endpoint": model.endpoint, "api_key": "test-credential"})
        self.assertEqual(enriched.checkpoint["model_requests_used"], 1)
        model_a = profile(enriched, "a.csv")["model_interpretation"]
        self.assertEqual(model_a["status"], "complete")
        self.assertNotIn("count", model_a["columns"]["code"])
        self.assertIn("budget", profile(enriched, "b.csv")["model_interpretation"]["reason"])
        report = report_path(enriched).read_text()
        self.assertIn("Model interpretations (test-model)", report)
        self.assertIn("| code | A status code | code | — | — | Verify encoding |", report)
        self.assertIn("[Saved semantic profile JSON]", report)
        self.assertLess(report.index("## Inventory and coverage"), report.index("## Column descriptions"))
        self.assertLess(report.index("## Column descriptions"), report.index("## Measurements and evidence"))

        with patch.dict(os.environ, {model.api_key_env: "test-credential"}), \
                patch.object(semantic_agent, "request_completion", return_value='{"code": {}}'):
            malformed = self.run_dataset(config)
        self.assertEqual(profile(malformed, "a.csv")["model_interpretation"]["status"], "failed")

        with patch.dict(os.environ, {model.api_key_env: ""}), \
                patch.object(semantic_agent, "request_completion") as request:
            missing = self.run_dataset(config)
            request.assert_not_called()
        self.assertIn("No model credentials", profile(missing, "a.csv")["model_interpretation"]["reason"])
        self.assertEqual(missing.checkpoint["model_requests_used"], 0)

        for state in (enriched, malformed, missing):
            for name in ("a.csv", "b.csv"):
                deterministic = profile(offline, name)
                actual = profile(state, name)
                for field in ("columns", "needs_verification", "coverage"):
                    self.assertEqual(actual[field], deterministic[field])
                self.assertEqual(rows(actual, "code")[1]["status"], "conflict" if name == "b.csv" else "unresolved")
                self.assertEqual(rows(actual, "code")[1]["count"], 2)

    def test_tiff_vision_sends_the_saved_first_frame_and_reuses_it_on_resume(self):
        first = Image.new("RGB", (16, 16), "red")
        second = Image.new("RGB", (16, 16), "blue")
        first.save(self.data / "stack.tif", save_all=True, append_images=[second])
        first.save(self.data / "extra.png")
        model = ModelSettings(endpoint="https://model.example/v1/chat/completions",
                              api_key_env="D37_TEST_VISION_KEY")
        config = replace(self.config, model=model)
        completion = {"choices": [{"message": {"content": json.dumps({
            "description": "A red preview.", "needs_verification": ["Check the other frame."],
        })}}]}
        with patch.dict(os.environ, {model.api_key_env: "test-credential"}), \
                patch.object(semantic_agent, "urlopen", return_value=io.BytesIO(json.dumps(completion).encode())) as send:
            state = self.run_dataset(config)
            send.assert_called_once()
            updated = self.resume_dataset(state)
            send.assert_called_once()

        self.assertEqual(set(outputs(state, "semantics")), {"stack.tif"})
        saved = profile(state, "stack.tif")
        self.assertEqual(saved["kind"], "tiff")
        image, = saved["images"]
        self.assertEqual((image["frame_number"], image["frame_count"]), (1, 2))
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, model.endpoint)
        body = json.loads(request.data)
        self.assertEqual(body["model"], "qwen3")
        text, visual = body["messages"][0]["content"]
        self.assertIn('"frame_count": 2', text["text"])
        prefix, encoded = visual["image_url"]["url"].split(",", 1)
        self.assertEqual(prefix, "data:image/png;base64")
        preview = base64.b64decode(encoded, validate=True)
        self.assertEqual(preview, (state.run_dir / image["preview_path"]).read_bytes())
        with Image.open(io.BytesIO(preview)) as decoded:
            self.assertEqual(decoded.getpixel((0, 0)), (255, 0, 0))
        self.assertEqual(image["model_interpretation"]["status"], "complete")
        self.assertEqual(updated.checkpoint["model_requests_used"], 1)
        self.assertEqual(outputs(updated, "semantics"), outputs(state, "semantics"))
        report = report_path(state).read_text()
        self.assertIn("frame 1 of 2 PNG preview", report)
        self.assertIn("Vision model interpretation (qwen3)", report)
        self.assertIn("A red preview.", report)

        with patch.dict(os.environ, {model.api_key_env: "test-credential"}), \
                patch.object(semantic_agent, "request_completion", return_value='{"description": []}') as send:
            failed = self.run_dataset(config)
            disabled = self.run_dataset(self.config)
            send.assert_called_once()
        for run, status in ((failed, "failed"), (disabled, "disabled")):
            image, = profile(run, "stack.tif")["images"]
            self.assertTrue((run.run_dir / image["preview_path"]).is_file())
            self.assertEqual(image["model_interpretation"]["status"], status)
        self.assertEqual(disabled.checkpoint["model_requests_used"], 0)
