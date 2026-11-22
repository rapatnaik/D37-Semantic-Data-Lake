# D37-Semantic-Data-Lake
DSC 180A Capstone D37 - Quarter 1 Project

## Install `d37-agent`

Install `uv` with a compatible Python version (3.11 or newer). Clone the
`analysis_agent` branch and install the locked dependencies from the repository
root.

```sh
git clone --branch analysis_agent https://github.com/rapatnaik/D37-Semantic-Data-Lake.git
cd D37-Semantic-Data-Lake
uv sync --locked
uv run --locked d37-agent --help
```

## Run your first investigation

Copy the six-row demo so you can edit its dictionary without modifying the
repository fixture.

```sh
demo_dir="$(mktemp -d)"
cp examples/status_dictionary_demo/* "$demo_dir/"
uv run --locked d37-agent run "$demo_dir" --no-model
uv run --locked d37-agent status "$demo_dir"
uv run --locked d37-agent runs "$demo_dir"
```

The run prints the path to `reports/revision-001/report.md` under
`DATA_DIR/.d37-agent/runs/<run-id>/`. The report shows observed values,
dictionary definitions with citations, and meanings that need verification.
The run directory also contains versioned JSON evidence and a marimo notebook.

To test resume, change `1 = pending` to `1 = active` in
`$demo_dir/dictionary_b.txt` and resume the run.

```sh
uv run --locked d37-agent resume "$demo_dir"
```

Code `1` now has one definition with two citations. Resume reuses the table
profile and saves a new report revision.

### Run with Qwen

Copy `.env.example` to `.env` if you need a local credentials file, and set
`NRP_KEY` to your NRP key. Replace `path/to/data` with the directory to investigate.

```sh
uv run --locked --env-file .env d37-agent run path/to/data
uv run --locked --env-file .env d37-agent resume path/to/data
```

With model calls enabled and credentials available, `qwen3` receives table
metadata and, in separate requests, TIFF first-frame PNG previews with selected
image metadata. The report labels the interpretations and links to the saved
TIFF previews. Resume uses the model settings from the saved run. Use
`run --no-model` for an offline run.

To link a text dictionary to a table, declare the table path and exact column
name in the document.

```text
Table: status.csv
Column: status
0 = inactive
1 = active
```

Use a path relative to the data directory or a filename that uniquely identifies
the table.

## Subcommand reference

Run `uv run --locked d37-agent <subcommand> --help` for all flags.
`RUN_OR_DATA_DIR` is either a saved run directory or a data directory whose
latest run you want to use.

| Subcommand | Purpose | Useful options |
| --- | --- | --- |
| `run DATA_DIR` | Start a new investigation and write the report. | `--no-model` runs offline. `--workers N` limits local workers. `--time-limit SECONDS` sets the run time limit. |
| `resume [RUN_OR_DATA_DIR]` | Continue a saved run and refresh outputs affected by changes. | `--retry-failed` retries jobs marked failed. |
| `status [RUN_OR_DATA_DIR]` | Show job status, model request usage, and the report path. | `--json` emits a machine-readable summary. |
| `runs DATA_DIR` | List saved runs, their statuses, and their paths. | `--state-dir DIR` locates runs stored outside the default directory. |
| `ask RUN_OR_DATA_DIR "QUESTION"` | Run a follow-up analysis using supplied Python and selected inputs. | `--code FILE` supplies the script. Repeat `--input PATH` for each input. `--param KEY=VALUE` passes parameters. `--json` emits the session record. |

Use `d37-agent --config FILE run DATA_DIR` to load TOML settings. See the
[investigator guide](agents/investigator/README.md) for configuration, report files,
and worker details.

### Run a follow-up analysis

Start Docker and build the worker image once from the repository root. The
worker runs the supplied script against the selected inputs.

```sh
docker build -f containers/investigator/Dockerfile -t d37-investigator-worker:latest .

analysis_file="$(mktemp -d)/count_status.py"
cat > "$analysis_file" <<'PY'
import csv

with open(INPUT_FILES["status.csv"], newline="") as source:
    row_count = sum(1 for _ in csv.DictReader(source))
save_json("row_count.json", {"rows": row_count})
PY
uv run --locked d37-agent ask "$demo_dir" "How many status records are there?" \
    --code "$analysis_file" --input status.csv
```

## Running the standalone semantic agent

For NRP model calls, set `NRP_KEY` in the local `.env`. The following command
interprets the chest pain column.

```sh
uv run --locked --env-file .env python -m agents.semantic_agent outputs/metadata/heart_metadata.json cp
```

To generate interpretations for every column in all metadata profiles, run:

```sh
uv run --locked --env-file .env python -m agents.semantic_agent
```

Outputs from the first test run are in [outputs/semantic_agent_profiles/](outputs/semantic_agent_profiles/):
[`test_001_cardio.json`](outputs/semantic_agent_profiles/test_001_cardio.json) and
[`test_001_heart.json`](outputs/semantic_agent_profiles/test_001_heart.json).
Each new run saves one file per dataset under the next test number.

## Running the agent integration pipeline

`run_pipeline.py` runs the metadata agent and the semantic agent on every dataset, then compares their output with the Assignment 1 data dictionaries and EDA findings. The pipeline code lives in `agents/agent_integration.py`.

To reuse the latest saved semantic run, which needs no API key:

```sh
uv run --locked python run_pipeline.py --offline
```

To call the LLM for a new semantic run:

```sh
uv run --locked --env-file .env python run_pipeline.py
```

Outputs from the first test run are in [outputs/agent_integration/](outputs/agent_integration/):
[`test_001_evaluation_results.json`](outputs/agent_integration/test_001_evaluation_results.json).
It starts with a summary for each dataset, followed by the per-column results.
Each new run saves its results under the next test number. The metadata agent's profiles are written to `outputs/agent_integration/metadata/`, and the semantic agent reads them from there.

[`evaluation/agent_comparison.md`](evaluation/agent_comparison.md) compares the agents' output with the human-written Assignment 1 profiles. It covers accuracy, errors, missing information and limitations. [`notebooks/agent_integration_tests.ipynb`](notebooks/agent_integration_tests.ipynb) runs each pipeline step and checks the results.

## AI and Human Contribution Statements

*AI Contribution*: Our team used AI tools such as ChatGPT to help with every portion of the codebase, including data cleaning decisions and for the design of our EDA, agents, and evaluation pipeline. After coding, we used AI to fix bugs and check for discrepancies across functions. 

*Human Contribution*: Team members were still responsible for confirming the scope of responsibilities, choosing and cleaning our datasets, defining the project architecture and scope, building the metadata and semantic agents, evaluating the outputs, and interpreting all results. Throughout any AI usage, we made sure to thoroughly examine any AI-generated code and made sure to manually tweak and change any mistakes before adding it to our codebase.
