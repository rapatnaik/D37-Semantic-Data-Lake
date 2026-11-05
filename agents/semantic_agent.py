import argparse
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import Request, urlopen


FIELDS = "description, semantic_type, unit (null if unknown), evidence (list), and needs_verification (list)."
RULES = (
    "State a claim as fact only when the supplied metadata directly supports it. "
    "If the evidence suggests a meaning but leaves room for other interpretations, "
    "label it as a hypothesis and put any details that need confirmation in `needs_verification`."
)


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
    return f"Interpret the selected column. Return one JSON object with {FIELDS}\n{RULES}\n\n" + json.dumps(context, indent=2)


def interpret_column(profile, column_name, model="gpt-oss"):
    """Send one column prompt to NRP and return the model's answer as text."""
    return request_completion(build_column_prompt(profile, column_name), model)


def request_completion(prompt, model):
    token = os.environ.get("NRP_KEY")
    if not token:
        raise ValueError("Set NRP_KEY to your NRP LLM API key.")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    request = Request(
        "https://ellm.nrp-nautilus.io/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=120) as response:
        completion = json.load(response)
    return completion["choices"][0]["message"]["content"]


def build_table_prompt(profile):
    # SQL profiling repeats measurements already present in each column profile.
    columns = {
        name: {key: value for key, value in facts.items() if key != "sql_profile"}
        for name, facts in profile["columns"].items()
    }
    context = {
        "dataset": profile["dataset"],
        "row_count": profile["row_count"],
        "potential_keys": profile.get("potential_keys", []),
        "columns": columns,
    }
    return (
        "Interpret every column. Return one JSON object keyed by the exact column names. "
        f"Each value must contain {FIELDS} Keep each entry concise.\n{RULES}\n\n"
        + json.dumps(context, separators=(",", ":"))
    )


def parse_columns(reply, expected):
    text = reply.strip()
    if text.startswith("```"):
        text = text.partition("\n")[2].removesuffix("```").strip()
    columns = json.loads(text)
    if not isinstance(columns, dict) or columns.keys() != expected.keys():
        raise ValueError("Model reply must include exactly the input columns.")
    for name, entry in columns.items():
        if not isinstance(entry, dict):
            raise ValueError(f"Expected an interpretation object for {name}.")
        for field in ("description", "semantic_type", "unit", "evidence", "needs_verification"):
            if field not in entry:
                raise ValueError(f"Missing {field} for {name}.")
            value = entry[field]
            if field in ("evidence", "needs_verification"):
                valid = isinstance(value, list) and all(isinstance(item, str) for item in value)
            else:
                valid = isinstance(value, str) or (field == "unit" and value is None)
            if not valid:
                raise ValueError(f"Unexpected {field} value for {name}.")
    return columns


def run_batch(model, metadata_dir=Path("outputs/metadata"), output_dir=Path("outputs/semantic_agent_profiles")):
    paths = sorted(metadata_dir.glob("*_metadata.json"))
    if not paths:
        raise FileNotFoundError(f"No metadata profiles found in {metadata_dir}.")
    output_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output_dir) as staging:
        results = []
        for index, path in enumerate(paths, start=1):
            profile = load_metadata(path)
            print(f"[{index}/{len(paths)}] Asking {model} about {path.name} "
                  f"({len(profile['columns'])} columns)...", flush=True)
            reply = request_completion(build_table_prompt(profile), model)
            columns = parse_columns(reply, profile["columns"])
            print(f"Validated {len(columns)} column interpretations.", flush=True)
            result = {"dataset": profile["dataset"], "model": model, "columns": columns}
            filename = path.stem.removesuffix("_metadata") + ".json"
            staged = Path(staging) / filename
            staged.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            results.append(staged)

        numbers = (p.name.split("_", 2)[1] for p in output_dir.glob("test_*_*.json"))
        number = max((int(n) for n in numbers if n.isascii() and n.isdigit()), default=0) + 1
        while True:
            prefix = f"test_{number:03d}_"
            reservation = output_dir / f".test_{number:03d}.lock"
            try:
                reservation.mkdir()
            except FileExistsError:
                number += 1
                continue
            try:
                if not any(output_dir.glob(prefix + "*.json")):
                    for staged in results:
                        target = output_dir / (prefix + staged.name)
                        os.link(staged, target)
                        print(f"Saved {target}")
                    return
            finally:
                reservation.rmdir()
            number += 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate semantic profiles using NRP.")
    parser.add_argument("profile", nargs="?", help="Metadata JSON for a single-column run")
    parser.add_argument("column", nargs="?", help="Column name for a single-column run")
    parser.add_argument("--model", default="gpt-oss", help="NRP model ID")
    args = parser.parse_args()
    if bool(args.profile) != bool(args.column):
        parser.error("Supply both profile and column, or neither to process all profiles.")
    if args.profile:
        print(interpret_column(load_metadata(args.profile), args.column, args.model))
    else:
        run_batch(args.model)
