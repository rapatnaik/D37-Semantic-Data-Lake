"""Run the full agent pipeline: metadata agent -> semantic agent -> evaluation.

Run from the repository root:

    # reuse the saved semantic run (no API key needed)
    uv run --locked python run_pipeline.py --offline

    # call the LLM for a new semantic run (needs NRP_KEY in .env)
    uv run --locked --env-file .env python run_pipeline.py

The pipeline itself lives in agents/agent_integration.py.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)  # the pipeline uses paths relative to the repository root
sys.path.insert(0, str(ROOT))

from agents.agent_integration import main  # noqa: E402

if __name__ == "__main__":
    main()
