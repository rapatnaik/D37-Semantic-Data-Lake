"""Agent integration, evaluation and validation.

Runs the metadata agent and the semantic agent on every dataset, then compares
their output with the human-written profiles from Assignment 1.
Run it with run_pipeline.py (see the README).
"""

import argparse
import itertools
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from agents import metadata_agent, semantic_agent

OUTPUT_DIR = Path("outputs/agent_integration")
METADATA_DIR = OUTPUT_DIR / "metadata"
SEMANTIC_DIR = Path("outputs/semantic_agent_profiles")

# One entry per dataset. To add a dataset, add an entry here and its
# reference facts below.
DATASETS = {
    "heart": {
        "cleaned_csv": "datasets/cleaned/heart_disease_cleaned.csv",
        "raw_csv": "datasets/original/heart_disease.csv",
        "data_dictionary": "data_dictionaries/heart_disease_metadata.json",
    },
    "cardio": {
        "cleaned_csv": "datasets/cleaned/cardiovascular_cleaned.csv",
        "raw_csv": "datasets/original/Cardiovascular_Disease_Dataset.csv",
        "data_dictionary": "data_dictionaries/cardiovascular_disease_dataset_metadata.json",
    },
}

# ------------------------------------------------------------------ references
# Human ground truth from Assignment 1 (EDA notebooks and data dictionaries).

# Facts and data-quality issues found in the EDA notebooks.
EDA_FACTS = {
    "heart": {
        "rows": 297, "columns": 16, "primary_key": "patient_id",
        "raw_issues": [
            {"type": "null_count", "column": "ca", "expected": 4, "summary": "4 missing values in ca"},
            {"type": "null_count", "column": "thal", "expected": 2, "summary": "2 missing values in thal"},
            {"type": "rare_level", "column": "restecg", "code": 1, "summary": "restecg = 1 has only 4 patients"},
            {"type": "rare_level", "column": "thal", "code": 6, "summary": "thal = 6 has only 18 patients"},
        ],
    },
    "cardio": {
        "rows": 1000, "columns": 15, "primary_key": "patientid",
        "raw_issues": [
            {"type": "disguised_zero", "column": "serumcholestrol", "summary": "53 cholesterol readings of 0 are really missing"},
            {"type": "undocumented_code", "column": "slope", "code": 0, "summary": "slope = 0 (180 rows) is undocumented"},
            {"type": "cross_column", "column": "serumcholestrol", "summary": "all missing cholesterol is in target = 1 patients"},
        ],
    },
}

# Column pairs that describe the same concept in two datasets.
CROSSWALK = {
    ("heart", "cardio"): [
        ("patient_id", "patientid"), ("age", "age"), ("sex", "gender"), ("cp", "chestpain"),
        ("trestbps", "restingBP"), ("chol", "serumcholestrol"), ("fbs", "fastingbloodsugar"),
        ("restecg", "restingrelectro"), ("thalach", "maxheartrate"), ("exang", "exerciseangia"),
        ("oldpeak", "oldpeak"), ("slope", "slope"), ("ca", "noofmajorvessels"), ("disease", "target"),
    ],
}

# Manual verdicts on the semantic agent's descriptions (run test_001).
# Columns not listed were judged correct.
REVIEWED_RUN = 1
MANUAL_REVIEW = {
    "heart": {
        "thal": ("partially_correct", "calls it thalassemia; human profile says thallium stress test (codes right)"),
        "num": ("partially_correct", "first reading (vessel count 0-3) is wrong; second (0 = no disease, 1-4 = disease) is right"),
    },
    "cardio": {
        "slope": ("partially_correct", "labels in wrong codes: implies 0 = upsloping; human has 0 = undocumented, 1-3 = up/flat/down"),
        "noofmajorvessels": ("partially_correct", "adds 'with significant narrowing', which is unsupported and not flagged"),
    },
}
# Label equivalences the text parser cannot see.
CODE_OVERRIDES = {("cardio", "cholesterol_missing")}


# ------------------------------------------------------------------- pipeline

def test_numbers(folder, pattern):
    """Run numbers in file names like test_001_<...>.json, as {number: [rest of name]}."""
    runs = {}
    for path in folder.glob(pattern):
        _, number, rest = path.stem.split("_", 2)
        if number.isdigit():
            runs.setdefault(int(number), []).append(rest)
    return runs


def run_metadata_agent(datasets):
    profiles = {}
    for key, spec in datasets.items():
        profiles[key] = metadata_agent.extract_metadata(spec["cleaned_csv"])
        metadata_agent.export_metadata(profiles[key], str(METADATA_DIR / f"{key}_metadata.json"))
    return profiles


def run_relationships(datasets):
    frames = {key: pd.read_csv(spec["cleaned_csv"]) for key, spec in datasets.items()}
    return {
        (left, right): metadata_agent.possible_relationships(frames[left], frames[right])
        for left, right in itertools.combinations(datasets, 2)
    }


def latest_semantic_run(keys):
    runs = test_numbers(SEMANTIC_DIR, "test_*_*.json")
    complete = [n for n, saved in runs.items() if set(keys) <= set(saved)]
    if not complete:
        raise FileNotFoundError(f"No saved semantic run in {SEMANTIC_DIR} covers {sorted(keys)}.")
    return max(complete)


def run_semantic_agent(datasets, model, offline):
    if not offline:
        semantic_agent.run_batch(model, metadata_dir=METADATA_DIR, output_dir=SEMANTIC_DIR)
    run = latest_semantic_run(datasets)
    profiles = {
        key: json.loads((SEMANTIC_DIR / f"test_{run:03d}_{key}.json").read_text(encoding="utf-8"))
        for key in datasets
    }
    return run, profiles


# ----------------------------------------------------------------- evaluation

def close(a, b):
    if a is None or b is None:
        return a is b
    return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9)


def check_metadata(spec, profile, facts):
    """Compare every statistic the metadata agent reported with pandas."""
    df = pd.read_csv(spec["cleaned_csv"])
    checks = [
        ("row_count", profile["row_count"], len(df)),
        ("column_count", profile["column_count"], df.shape[1]),
        ("row_count vs EDA", profile["row_count"], facts["rows"]),
        ("column_count vs EDA", profile["column_count"], facts["columns"]),
    ]
    for column in df.columns:
        series, entry = df[column], profile["columns"][column]
        for source, stats in (("pandas", entry), ("sql", entry["sql_profile"])):
            checks.append((f"{column} {source} nulls", stats["null_count"], int(series.isna().sum())))
            checks.append((f"{column} {source} distinct", stats["distinct_count"], int(series.nunique())))
            if pd.api.types.is_numeric_dtype(series):
                values = series.dropna()
                truth = {"min": values.min(), "max": values.max(), "mean": values.mean(), "median": values.median()}
                for stat, value in truth.items():
                    checks.append((f"{column} {source} {stat}", stats["statistics"][stat], value))
    failed = [name for name, agent, truth in checks if not close(agent, truth)]
    return {
        "checks": len(checks),
        "passed": len(checks) - len(failed),
        "failed": failed,
        "primary_key_found": facts["primary_key"] in profile["potential_keys"],
    }


def check_raw_issues(spec, facts):
    """Run the metadata agent on the raw CSV: does it surface each EDA issue?"""
    raw = metadata_agent.extract_metadata(spec["raw_csv"])
    results = []
    for issue in facts["raw_issues"]:
        entry = raw["columns"][issue["column"]]
        stats = entry.get("statistics") or {}
        if issue["type"] == "null_count":
            outcome = "detected" if entry["null_count"] == issue["expected"] else "missed"
        elif issue["type"] in ("disguised_zero", "undocumented_code"):
            # visible = only inferable from min = 0; nothing flags it
            outcome = "visible" if stats.get("min") == 0 else "missed"
        elif str(issue.get("code")) in (entry.get("frequent_values") or {}):
            outcome = "detected"
        else:
            outcome = "missed"
        results.append({"issue": issue["summary"], "outcome": outcome})
    return results


def normalize(text):
    """Replace the LLM's special dashes and spaces with plain ones."""
    for char in "\u2011\u2013\u2014":  # non-breaking hyphen, en dash, em dash
        text = text.replace(char, "-")
    return text.replace("\u202f", " ").replace("\u00a0", " ")  # non-breaking spaces


UNITS = [("mmHg", r"mm\s*hg"), ("mg/dL", r"mg\s*/\s*dl"), ("beats/min", r"beats\s*(/|per)\s*min|\bbpm\b"),
         ("years", r"\byears?\b"), ("mm", r"\bmm\b")]


def canonical_unit(text):
    if text is None:
        return None
    text = normalize(text).lower()
    if "not stated" in text or "not specified" in text:
        return "unspecified"
    return next((name for name, pattern in UNITS if re.search(pattern, text)), None)


def compare_unit(human_text, agent_unit):
    human, agent = canonical_unit(human_text), canonical_unit(agent_unit)
    if human is None:
        return None  # no unit to compare
    if human == "unspecified":
        return "match" if agent is None else "hedged_guess" if "hypothes" in agent_unit.lower() else "unsupported"
    return "missing" if agent is None else "match" if agent == human else "mismatch"


CODE_RE = re.compile(r"(?<![\d.])(\d+)(?:\s*-\s*(\d+))?\s*=\s*")
LIST_RE = re.compile(r"(\d+)\s*-\s*(\d+)\s*\((?:e\.?g\.?,?\s*)?([^()]*)\)")


def parse_codes(text):
    """'0 = normal, 1 = ST-T abnormality' or 'coded as 0-2 (a, b, c)' -> {code: label}."""
    text = normalize(text)
    matches = list(CODE_RE.finditer(text))
    codes = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        label = text[match.end():end].strip(" ,;.")
        if label.count("(") < label.count(")"):
            label = label.rstrip(")").strip(" ,;.")
        for code in range(int(match.group(1)), int(match.group(2) or match.group(1)) + 1):
            codes[code] = label
    if codes:
        return codes
    for match in LIST_RE.finditer(text):
        low, high = int(match.group(1)), int(match.group(2))
        items = [item.strip() for item in match.group(3).split(",") if item.strip()]
        if len(items) == high - low + 1:
            return dict(zip(range(low, high + 1), items))
    return {}


def label_words(label):
    synonyms = {"absence": "no", "absent": "no"}
    ignore = {"a", "an", "the", "of", "in", "at", "least", "one", "category", "records", "presence", "present", "heart"}
    words = (synonyms.get(w, w) for w in re.sub(r"[^a-z0-9]+", " ", normalize(label).lower()).split())
    return {w for w in words if w not in ignore and not w.isdigit()}


def labels_match(human, agent):
    h, a = label_words(human), label_words(agent)
    return bool(h and a) and (h <= a or a <= h or len(h & a) / len(h | a) >= 0.5)


def compare_codes(human_text, agent_description):
    human = parse_codes(human_text)
    if not human:
        return None  # no codes to compare
    agent = parse_codes(agent_description)
    if not agent:
        return "not_stated"
    hits = sum(code in agent and labels_match(label, agent[code]) for code, label in human.items())
    return "match" if hits == len(human) else "mismatch" if hits == 0 else "partial"


def check_semantic(key, spec, profile):
    human_rows = {row["column"]: row for row in json.loads(Path(spec["data_dictionary"]).read_text())}
    review = MANUAL_REVIEW.get(key, {})
    rows = []
    for column, entry in profile["columns"].items():
        human = human_rows.get(column, {})
        verdict, note = review.get(column, ("correct", ""))
        codes = compare_codes(human.get("values_units", ""), entry["description"])
        if (key, column) in CODE_OVERRIDES and codes in ("partial", "mismatch"):
            codes = "match"
        unit = compare_unit(human.get("values_units"), entry["unit"]) if human else None
        error = verdict != "correct" or unit in ("mismatch", "unsupported") or codes in ("partial", "mismatch")
        rows.append({
            "column": column,
            "meaning": verdict,
            "unit": unit,
            "codes": codes,
            "flagged": bool(entry["needs_verification"]),
            "error": error,
            "note": note,
        })
    return rows


def check_relationships(relationships):
    results = []
    for (left, right), found in relationships.items():
        expected = set(CROSSWALK.get((left, right), []))
        if not expected:
            continue
        found = {(column, column) for column in found}
        results.append({
            "pair": f"{left} vs {right}",
            "expected": len(expected),
            "found": len(found),
            "correct": len(found & expected),
            "missed": sorted(f"{a}/{b}" for a, b in expected - found),
        })
    return results


def count(rows, field):
    totals = {}
    for row in rows:
        if row[field] is not None:
            totals[row[field]] = totals.get(row[field], 0) + 1
    return totals


def evaluate_dataset(key, spec, metadata_profile, semantic_profile):
    metadata = check_metadata(spec, metadata_profile, EDA_FACTS[key])
    raw_issues = check_raw_issues(spec, EDA_FACTS[key])
    semantic = check_semantic(key, spec, semantic_profile)
    return {
        "summary": {
            "metadata_checks_passed": f"{metadata['passed']}/{metadata['checks']}",
            "raw_issues": count(raw_issues, "outcome"),
            "semantic_meaning": count(semantic, "meaning"),
            "semantic_units": count(semantic, "unit"),
            "semantic_codes": count(semantic, "codes"),
            "errors_flagged_by_agent": f"{sum(r['error'] and r['flagged'] for r in semantic)}"
                                       f"/{sum(r['error'] for r in semantic)}",
        },
        "metadata": metadata,
        "raw_issues": raw_issues,
        "semantic": semantic,
    }


# ----------------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description="Run both agents and evaluate them against Assignment 1.")
    parser.add_argument("--offline", action="store_true", help="reuse the latest saved semantic run (no LLM call)")
    parser.add_argument("--model", default="gpt-oss", help="NRP model ID")
    args = parser.parse_args()

    print("Running metadata agent...")
    metadata = run_metadata_agent(DATASETS)
    relationships = run_relationships(DATASETS)
    print("Running semantic agent..." if not args.offline else "Reusing saved semantic run...")
    run, semantic = run_semantic_agent(DATASETS, args.model, args.offline)
    if run != REVIEWED_RUN:
        print(f"Note: manual verdicts are for test_{REVIEWED_RUN:03d}; re-review test_{run:03d}.")

    print("Evaluating against Assignment 1 profiles...")
    results = {
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "semantic_run": run,
        "datasets": {
            key: evaluate_dataset(key, spec, metadata[key], semantic[key]) for key, spec in DATASETS.items()
        },
        "relationships": check_relationships(relationships),
    }
    number = max(test_numbers(OUTPUT_DIR, "test_*_evaluation_results.json"), default=0) + 1
    path = OUTPUT_DIR / f"test_{number:03d}_evaluation_results.json"
    path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"Done. See {path}")


if __name__ == "__main__":
    main()
