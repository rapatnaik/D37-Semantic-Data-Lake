# d37-agent runtime: CLI, scheduling, execution

This is the runtime that connects everyone's parts. It discovers inputs, runs the
tested tools in parallel, assembles metadata, reconciles dictionary definitions,
executes generated analysis code in an isolated worker, and writes the report.
It checkpoints after every job, so a run can be resumed.

## Quick start

```sh
uv sync --locked                     # installs the d37-agent command
docker build -f containers/investigator/Dockerfile -t d37-investigator-worker:latest .

uv run d37-agent run path/to/data    # new run → path/to/data/.d37-agent/runs/<run-id>/
uv run d37-agent status path/to/data
uv run d37-agent resume path/to/data # continue; reruns only what changed
uv run d37-agent ask path/to/data "Blank ages by group" \
    --code analysis.py --input patients.csv --param group_column=group
```

`python -m agents.investigator ...` works without installing. For model stages,
put `NRP_KEY` in `.env` and add `--env-file .env` to `uv run`.

## Coded columns

A run profiles table values and checks them against explicit dictionary entries
in extracted document text. A TXT or Markdown dictionary uses this format.

```text
Table: data/status.csv
Column: status
0 = inactive
1 = active
```

Use an inventory-relative table path or a filename that is unique among the
tables. Use `./status.csv` to specify a root-level table when its filename is
shared. Column names are case-sensitive.

The report and versioned JSON profile show measured counts, cited definitions,
conflicts, and unresolved values. Complete frequency summaries cover up to 20
distinct non-null values in the profiled rows. The report identifies sampled
counts, incomplete dictionary extraction, and frequency limits. To try the
six-row demo, copy `examples/status_dictionary_demo` to a temporary directory
and run `d37-agent run` on the copy. Change `1 = pending` to `1 = active` in
`dictionary_b.txt` and resume the same run to clear the conflict for code 1.

The semantic agent sends table metadata to `qwen3` by default
when credentials are available, including for tables without dictionaries.
The report labels model descriptions and hypotheses alongside the cited
dictionary findings. For an offline run, pass `--no-model` or set
`interpret_semantics = false` in the model settings.

## TIFF interpretation

With model calls enabled and credentials available, TIFF inputs go through the
image profiler and then a vision model. The request carries the saved PNG
preview of the first frame, its frame number and total frame count, the image
dimensions and mode, and how the preview was transformed. The default vision
model is `qwen3`. The semantic profile and report link to the preview. TIFF
and table interpretation share the run's model request budget.

**macOS: `ModuleNotFoundError: No module named 'agents'` from `d37-agent`.**
macOS sometimes marks the files in `.venv` as hidden, and Python 3.12 or newer
skips hidden `.pth` files, which breaks the editable install. To fix it, run
`chflags nohidden .venv/lib/python3.*/site-packages/*.pth`, or use
`python -m agents.investigator` from the repository root.

Exit codes: `0` completed, `1` error, `3` stopped at the time limit, `130`
interrupted. After exit codes 3 and 130, `d37-agent resume` picks up where the
run stopped.

## Settings (`d37-agent.toml` in the current directory, or `--config FILE`)

```toml
seed = 0
hash_inputs = true            # SHA-256 inputs for change detection and reproduction
# state_dir = "/elsewhere"    # default: <data>/.d37-agent

[limits]                      # defaults from the work split
run_seconds = 900             # 15 minutes per invocation
local_workers = 4             # tool worker processes
custom_code_workers = 1       # 0 disables generated code; at most 1
concurrent_model_requests = 2
model_requests_per_run = 30
repair_attempts = 2
analysis_timeout_seconds = 120
analysis_memory_mb = 1024

[model]
endpoint = "https://ellm.nrp-nautilus.io/v1/chat/completions"
name = "qwen3"
vision_name = "qwen3"         # interprets TIFF previews on the same endpoint
api_key_env = "NRP_KEY"       # the name of the environment variable, never the key
interpret_semantics = true   # request model descriptions and hypotheses

[execution]
backend = "docker"            # or "process" (development only, see below)
```

Credentials are read only from the environment. A settings key that looks like
a credential (`*key*`, `*token*`, `*secret*`, `*password*`) is rejected. Known
credential values are removed from logs, events and error messages before
they're saved.

## Run directory

```
.d37-agent/runs/<run-id>/
  manifest.json      settings, environment and package versions, Docker version
  inventory.json     sources with SHA-256 fingerprints
  checkpoint.json    job states, fingerprints, budget use (atomic rewrite)
  events.jsonl       append-only history (a torn last line after a crash is ignored)
  results/<job>/v001.json            ToolResult versions (old versions kept)
  metadata/<component>/v001.json     build_metadata output
  semantics/<component>/v001.json    semantic profiles
  artifacts/<job>/attempt-001/...    files written by tools
  analyses/<job-id>/                 request.json, code.py, sandbox.json, outputs/,
                                     stdout.log, stderr.log, result.json
  sessions/<id>.json                 follow-up questions, steps, answer
  reports/revision-001/              report.md, notebook.py (new revision per change)
  logs/                              tool tracebacks
```

Original files are only read. Discovery skips hidden entries, so `.d37-agent/`
is never treated as input. A `state_dir` placed inside the data directory is
also excluded.

## Scheduling and invalidation

Each component gets a tool and metadata job. The scheduler links extracted
dictionaries to tables once metadata is ready, then runs table semantic jobs
and generates the report.
Tool jobs run in parallel in separate spawned processes, so a hung tool can be
stopped (`tool_timeout_seconds`, default 300). Metadata, semantics and report
jobs run in the main process.

Each job's fingerprint covers its inputs' content (SHA-256), the source code of
the module that runs it, the selector, the seed and the limits, plus the
fingerprints of the jobs it depends on. On `resume`:

- A **changed file** reruns its tool and metadata jobs. The semantic profile
  advances for tables whose measurements or linked dictionary evidence changed.
  Dictionary additions, removals, and retargeting are resolved on each resume.
- A **touched file with identical content** (only its mtime changed) is not rerun.
- **Added or removed files** add or remove their jobs.
- **Teammate code that has changed or newly appeared** reruns the jobs that use
  it. Until a tool module exists, its components get a `deferred` result.
- `--retry-failed` reruns tools whose result was `failed`, along with the jobs
  that depend on them.

At the 15-minute limit, running jobs are stopped and stay `pending`, and the
command exits with code 3. On Ctrl-C, the checkpoint is saved and the command
exits with code 130.

## Handoffs: what each module needs to provide

The runtime loads these lazily. Until a module exists, its stage is skipped
or deferred, and that is recorded in the run.

| Owner | Module:function | Called as |
|---|---|---|
| Manasa | `agents.investigator.tools.tables:profile_table` | `(source, context) -> ToolResult` |
| Deepal | `agents.investigator.tools.images:inspect_image` | `(source, context) -> ToolResult` |
| Deepal | `agents.investigator.tools.images:profile_image_collection` | `(sources, context)`, for components with several sources |
| Vaidehi | `agents.investigator.tools.documents:extract_document` | `(source, context) -> ToolResult` |
| Vaidehi | `agents.investigator.reporting:render_report` | `(run_dir) -> str` (Markdown) |
| Vaidehi | `agents.investigator.reporting:render_notebook` | `(run_dir) -> str` (marimo source) |
| Jacob | `agents.investigator.semantics:build_semantic_profile` | `(metadata, *, source, result_path, dictionary, budget, config) -> dict` |
| Jacob | `agents.investigator.investigation:choose_next_action` | `(InvestigationContext) -> ToolCall \| AnalysisRequest \| Completion` |

The registry is `DEFAULT_TOOLS` / `Stages` in `scheduler.py`. If a name or
signature differs, change it there, in one place.

**Tools** (`context.py`). Open inputs only through
`context.resolve_source(source)`, which keeps reads inside the dataset root and
rejects files that changed since discovery. Write files only with
`context.artifact_path("plots/age.png")`, and reference them with
`context.artifact("plots/age.png", "image/png")`. Return
`ToolResult(result_id=context.result_id, component_id=context.component_id, ...)`.
Use `context.seed` and `context.limits` (a `ToolLimits`) for sampling and
size bounds. An exception raised by a tool becomes a `failed` result. A
missing or unsafe artifact is dropped, and the drop is listed as a limitation.

**Model calls** (Jacob). Wrap every request in `with context.budget.request(): ...`.
This enforces 2 concurrent requests and 30 per run, and raises
`BudgetExhausted` when the budget is used up. `InvestigationContext` and
`budget` stay local; only send bounded evidence to the model.

**Generated code** (Jacob's prompts). The worker runs the code with these globals:
`INPUTS` (`{source_id: Path}`), `INPUT_FILES` (`{relative_path: Path}`),
`PARAMETERS`, `OUTPUT_DIR` (also the working directory), `SEED`, and
`save_json(name, obj)`. Allowed output types are `.json`, `.csv`, `.txt`,
`.md`, `.png` and `.parquet`; every type listed in `expected_outputs` must be
produced. After a failure, `context.last_execution.error` holds the error and
traceback. The next `AnalysisRequest` counts as a repair, and there are at
most two repairs.

**Contracts** (Rakshan). `ExecutionResult`, `ToolCall` and `Completion` are
`Contract` dataclasses defined in `execution.py` and `session.py`. They could
move into `contracts.py` if the team prefers.

## Isolation of generated code (`execution.py`)

`execute_analysis(request, context) -> ExecutionResult`. A request can name
only inventory source IDs, and those files must be unchanged since discovery.

| | Docker backend (default) | Process backend (development) |
|---|---|---|
| Network | `--network none` | **not blocked** |
| Credentials | none passed; empty environment | environment replaced, nothing inherited |
| Inputs | read-only bind mounts of the selected files only | read-only copies of the selected files |
| Writes | `outputs/` and `meta/` only; read-only root filesystem | anywhere the user can write |
| Limits | memory, CPUs, PIDs, file size, timeout; `--cap-drop ALL`, no-new-privileges, uid 65534 | timeout, CPU time, file size; memory limit only on Linux |

If Docker or the worker image is missing, the result is `unsupported`. The
runtime never quietly falls back to running code without isolation. Process
backend results say in their limitations that the network wasn't blocked.

Outputs are validated after every run. Symlinks, unknown file types, invalid
JSON (including NaN), files that aren't really PNG or Parquet, and anything
over the file-count or size limits are removed and listed as limitations. Each
`ExecutionResult` keeps the code, the logs (truncated and redacted), the
SHA-256 of every input, the worker's Python and package versions, and the
repair chain (`attempt`, `repair_of`). Every result also carries the note that
successful execution does not establish correctness.

## Tests

```sh
python3 -m unittest discover -s tests/investigator -p 'test_*.py' -v
```

| File | Covers |
|---|---|
| `test_execution.py` | success and records, no credentials in the environment, read-only inputs, failures, timeouts, rejected inputs, output validation, Docker flags, a real Docker run with no network (skipped if the image isn't built), the repair loop |
| `test_scheduler.py` | parallel tool processes, failed/hung/invalid tools, artifact publishing, run deadline, credential redaction, state-directory exclusion, model budget |
| `test_resume.py` | reuse, invalidation chains, touch-only changes, added/removed files, crash recovery, run locks, deferred → available tools, `--retry-failed` |
| `test_cli.py` | settings and credential rules, end-to-end `run`/`status`/`runs`/`resume`/`ask`, exit codes, `python -m` entry point |

`fake_tools.py` contains stand-in tools that follow the `ToolContext` contract.

## Known limitations

- Run-time and model budgets apply per invocation and per follow-up session. A
  resumed run gets a fresh 15 minutes, and the cumulative time is recorded.
- Tools are trusted, tested code. They run in separate processes with a timeout
  but without a sandbox. Only generated code goes through the isolated worker.
- The process backend is for development only.
- Until `reporting.py` exists, the scheduler writes a minimal fallback
  `report.md` and no notebook.
- The existing assignment pipeline (`run_pipeline.py`, `agents/*_agent.py`) is
  unchanged and still runs with `uv run --locked python run_pipeline.py --offline`.
