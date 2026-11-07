# D37-Semantic-Data-Lake
DSC 180A Capstone D37 - Quarter 1 Project

## Running the agents

From the repository root, run `uv sync --locked` to install the agent dependencies.
For NRP model calls, create a local `.env` using `.env.example` as a template
and set `NRP_KEY` to your personal key. To interpret the chest pain column:

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
