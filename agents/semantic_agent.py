import argparse
import json
import os
from urllib.request import Request, urlopen


def load_metadata(path):
    """Read one dataset profile exported by the metadata agent."""
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def build_column_context(profile, column_name):
    """Collect the table context and measured facts for one column."""
    columns = profile["columns"]
    return {
        "dataset": profile["dataset"],
        "row_count": profile["row_count"],
        "table_columns": list(columns),
        "column_name": column_name,
        "column_profile": columns[column_name],
    }


def build_column_prompt(profile, column_name):
    """Ask for a column interpretation grounded in the metadata profile."""
    context = build_column_context(profile, column_name)
    instructions = (
        "Interpret the selected column using the supplied metadata. "
        "Use column_sample as examples and distinct_count for the number of "
        "distinct nonmissing values. Return a JSON object with description, "
        "semantic_type, unit, evidence, and needs_verification. "
        "Phrase inferred meanings as hypotheses. Use null for an unknown unit. "
        "In evidence, cite specific clues from the profile. In needs_verification, "
        "list unresolved questions, including undocumented code meanings."
    )
    return instructions + "\n\n" + json.dumps(context, indent=2)


def interpret_column(profile, column_name, model="gpt-oss"):
    """Send one column prompt to NRP and return the model's answer as text."""
    token = os.environ.get("NRP_KEY")
    if not token:
        raise ValueError("Set NRP_KEY to your NRP LLM API key.")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": build_column_prompt(profile, column_name)}],
    }
    request = Request(
        "https://ellm.nrp-nautilus.io/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=120) as response:
        completion = json.load(response)
    return completion["choices"][0]["message"]["content"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Interpret one column using NRP.")
    parser.add_argument("profile", help="Path to a metadata JSON file")
    parser.add_argument("column", help="Column name in the profile")
    parser.add_argument("--model", default="gpt-oss", help="NRP model ID")
    args = parser.parse_args()
    print(interpret_column(load_metadata(args.profile), args.column, args.model))
