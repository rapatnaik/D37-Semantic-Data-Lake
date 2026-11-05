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
