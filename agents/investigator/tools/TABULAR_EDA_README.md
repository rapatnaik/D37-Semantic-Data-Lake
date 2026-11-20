
# Tabular EDA and Conservative Cleaning

## Overview

This module provides tabular data profiling and conservative cleaning for the D37 Semantic Data Lake Investigator Agent.

The goal is to help the agent understand structured datasets while preserving original source files and avoiding unsupported data transformations.

## Implemented Tools

### 1. Table Profiling

**File:** `agents/investigator/tools/tables.py`

Main function:

`profile_table(source, context)`

Features:
- Reads structured datasets.
- Calculates row counts, column counts, and data types.
- Measures missing values and missing percentages.
- Detects duplicate rows.
- Identifies candidate key columns.
- Calculates numerical statistics.
- Summarizes categorical values.
- Supports reproducible reservoir sampling.
- Generates PNG visualizations.
- Registers generated charts as ToolResult artifacts.

Supported formats:
- CSV
- TSV
- Parquet
- Excel (.xlsx and .xls)
- JSON records
- JSONL

Files below the 25 MB threshold receive full profiling.

Larger CSV/TSV files receive sampled profiling using a default sample of 1,000 rows.

Sampled results explicitly report partial coverage. Candidate key uniqueness is not asserted for the entire dataset based on a sample.

Generated visualizations:
- `missing_values.png`
- `numeric_distributions.png`

The plots are saved under the approved output directory and referenced through ArtifactRef entries.

### 2. Conservative Cleaning

**File:** `agents/investigator/tools/cleaning.py`

Main function:

`normalize_table(source, context, rules=None)`

Features:
- Preserves original source files.
- Creates a separate normalized Parquet copy.
- Generates a JSON cleaning audit log.
- Uses source-specific JSON dictionaries to validate missing-value markers.
- Skips cleaning rules without matching dictionary evidence.
- Records applied and skipped rules.
- Verifies source preservation using SHA-256 hashes.
- Returns results using the team's ToolResult contract.

Without cleaning rules, the tool performs no value transformations.

The current implementation supports documented missing-marker replacement, not arbitrary imputation, row deletion, or feature engineering.

### Cleaning Dictionary Format

Example:

```json
{
  "source_id": "patients_source",
  "columns": {
    "cholesterol": {
      "missing_values": [0]
    }
  }
}
```

Example rules:

```python
rules = {
    "dictionary_relative_path": "patients_dictionary.json",
    "columns": {
        "cholesterol": {
            "missing_values": [0]
        }
    }
}
```

The dictionary path must be inside the approved dataset root.

The dictionary must match the source ID and explicitly document the requested markers.

A matching JSON dictionary does not independently establish that a medical cleaning rule is clinically valid. The dataset owner must review its provenance.

## Testing

Run all investigator tests:

```powershell
python -m unittest discover -s tests/investigator -p "test_*.py" -v
```

Latest locally verified result:

- 136 tests executed.
- 135 passed.
- 1 Docker integration test skipped.
- 0 failures.

Tabular profiling tests:

```powershell
python -m unittest discover -s tests/investigator -p "test_tables.py" -v
```

Cleaning tests:

```powershell
python -m unittest discover -s tests/investigator -p "test_cleaning.py" -v
```

## Real Cardiovascular Dataset Validation

Run:

```powershell
python validate_real_tables.py
```

Datasets:
- `datasets/original/Cardiovascular_Disease_Dataset.csv`
- `datasets/original/heart_disease.csv`

Verified results:
- Both datasets received full profiling.
- Four PNG charts were generated.
- Two normalized Parquet copies were created.
- Two JSON audit logs were generated.
- Original datasets remained unchanged.
- Normalized output values matched the originals.
- No cleaning transformations were applied without rules.

Generated outputs are located under:

`outputs/real_table_validation/`

These generated data artifacts should not be committed to Git.

## Cholesterol Cleaning Demonstration

Run:

```powershell
python validate_cholesterol_rule_demo.py
```

This demonstration reproduces the existing cardiovascular dataset's cholesterol cleaning decision on a separate copy.

Verified results:
- 1,000 rows preserved.
- 53 zero cholesterol measurements replaced with missing values.
- All other columns and values preserved.
- Original dataset unchanged.
- Cleaning audit verified.

This demonstration verifies implementation behavior, not independent clinical provenance of the cleaning rule.

## Current Limitations

- Full table processing and cleaning are limited to approximately 25 MB per source.
- Large-file reservoir sampling is implemented for CSV and TSV.
- Legacy XLS reader dispatch is tested, but real XLS decoding needs additional integration testing.
- Data dictionary files must be curated and approved externally.
- Cleaning is limited to documented missing-value marker replacement.
- The process execution backend on Windows requires further production-grade process-tree isolation review.
- Full scheduler-to-report integration should be reviewed with the team.

## Integration Notes

Both tools use the investigator's shared SourceRef, Coverage, ArtifactRef, and ToolResult contracts.

The scheduler and reporting components should preserve:
- Full versus sampled coverage.
- Generated artifact references.
- Cleaning audit information.
- Unsupported and failed statuses.
- Limitations associated with partial analysis.

Original data should remain immutable throughout the workflow.
