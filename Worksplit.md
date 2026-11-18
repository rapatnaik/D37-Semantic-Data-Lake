# D37 Data Analysis Agent

- **Goal:** run `d37-agent` in an unfamiliar data directory to produce EDA, metadata, semantic profiles, and follow-up analyses.
- **Local:** file reading, statistics, plots, and analysis execution. **Cloud:** NRP model reasoning using bounded evidence and selected samples.
- **Approach:** write and test tools for routine analysis; have llm generate Python for additional questions, executed only in an isolated worker.
- **Outputs:** structured results, Markdown report, and reproducible marimo notebook.
- **Rules:** preserve original data, label sampling and uncertainty, record unsupported inputs, and keep credentials out of outputs.
- **Build order:** existing starter → Part 1 tools/reporting → Part 2 metadata/reasoning/integration, roughly in the order below. Report scaffolding can use example results until upstream tools are ready.

## Part 1 — EDA Tools & Reporting

Paths below are relative to `agents/investigator/`; tests live under `tests/investigator/`.

### 1. Manasa — Tables & Conservative Cleaning

- Read CSV/TSV, Parquet, Excel, and JSON/JSONL.
- Profile types, missingness, distributions, duplicates, and candidate keys; provide sampling and plotting functions.
- Write separate normalized copies. Change values only when supported by an explicit data dictionary; log changes and skip lossy conversions.
- **Handoff:** structured measurements to Rakshan; plotting/reproduction functions to Vaidehi. Document sampling and cleaning rules.

| Files | Deliverables |
| --- | --- |
| `tools/tables.py` | `profile_table(source, context) -> ToolResult` |
| `tools/cleaning.py` | Normalized Parquet copies, JSON change logs; PNG plots |
| `test_tables.py`, `test_cleaning.py` | Parsing, sampling, missingness, value preservation |

### 2. Deepal — Image EDA

- Inspect PNG, JPEG, and TIFF: dimensions, channels, data types, intensity distributions, unreadable files.
- Provide bounded readers, sampling, previews, and collection plots; keep pixel arrays local.
- Preserve original pixels and record preview transformations. Treat possible file/sample matches as hypotheses.
- **Scope:** no native microscopy decoding or OCR.
- **Handoff:** image measurements, reusable plotting functions, and documented limitations.

| Files | Deliverables |
| --- | --- |
| `tools/images.py` | `inspect_image(source, context)` and `profile_image_collection(sources, context)` → `ToolResult`; PNG previews/plots |
| `test_images.py` | Corrupt files, multipage TIFFs, sampling, memory limits |

### 3. Vaidehi — Documents/Text & Reports

- Extract/profile TXT, Markdown, PDF, and DOCX; record empty content, errors, and page/section references.
- Distinguish supporting documentation from text datasets; flag scanned documents needing OCR (image-to-text extraction).
- Build Markdown reports and marimo notebooks from saved results and reusable analysis functions.
- Reproduce plots and load saved model interpretations without new cloud calls. Generated code must run through the isolated worker.
- **Handoff:** document evidence and report/notebook templates; document-analysis and reproducibility sections.

| Files | Deliverables |
| --- | --- |
| `tools/documents.py` | `extract_document(source, context) -> ToolResult`; UTF-8 text artifacts |
| `reporting.py`, `templates/` | `render_report(run_dir)`, `render_notebook(run_dir)` → `report.md`, `notebook.py`, PNG plots |
| `test_documents.py`, `test_reporting.py` | Extraction, report contents, notebook execution on fixtures |

## Part 2 — Metadata, Agent Reasoning & Integration

### 4. Rakshan — Discovery & Metadata

- Extend the existing contracts/discovery starter; exclude credentials and generated outputs, avoid outside-root links, and never execute discovered code.
- Assemble metadata from tool results without repeating their computations; retain sources, coverage, assumptions, and code references.
- Validate candidate keys, file/sample matches, and documentation associations without automatically joining data.
- Preserve existing CSV metadata compatibility.
- **Handoff:** validated metadata and relationship evidence for Jacob; document discovery and metadata behavior.

| Files | Deliverables |
| --- | --- |
| `contracts.py`, `discovery.py` | Shared validated dataclasses; `discover(root) -> Inventory` (starter exists) |
| `metadata.py` | `build_metadata(component_id, results)` → metadata JSON |
| `relationships.py` | Evidence-backed relationship checks |
| `test_contracts.py`, `test_discovery.py`, `test_metadata.py`, `test_relationships.py` | Contracts, discovery, assembly, relationship validation |

### 5. Jacob — Investigation & Semantic Extraction

- Build the NRP reasoning loop: examine evidence, choose a tested tool, or propose custom Python.
- Send custom analysis to Victor's worker; allow at most two repair attempts within the run budget. Use mocked execution until the worker is ready.
- Generate semantic descriptions that separate measured facts, documented claims, and hypotheses.
- Support follow-up questions and optional web research using generic queries; bound model inputs and retain evidence references.
- **Handoff:** validated action requests to Victor; evidence-linked descriptions to Vaidehi. Document tool selection and uncertainty.

| Files | Deliverables |
| --- | --- |
| `models.py` | Replaceable model interface and NRP adapter |
| `investigation.py` | `choose_next_action(context)` → tool call, `AnalysisRequest`, or completion |
| `semantics.py` | Metadata/evidence → semantic profile JSON |
| `research.py`, `prompts/` | Optional search adapter and versioned prompts |
| `test_models.py`, `test_investigation.py`, `test_semantics.py` | Mocked model responses, action selection, evidence handling |

### 6. Victor — CLI, Execution & Integration

- Build `d37-agent`, progress display, follow-up sessions, checkpoints, and resume support.
- Schedule dependencies and independent jobs; invalidate affected results when sources change.
- Isolate generated code: selected read-only inputs, dedicated outputs, no network/credentials, enforced resource limits.
- Validate artifacts; retain code, environment versions, logs, failures, and report revisions.
- **Defaults:** 15 minutes/run; four local workers, including at most one custom-code worker; two concurrent model requests; 30 model requests/run.
- **Handoff:** integrated workflow and architecture/validation documentation; preserve the existing assignment pipeline.

| Files | Deliverables |
| --- | --- |
| `cli.py`, `config.py` | CLI; TOML settings and environment-based credentials |
| `scheduler.py`, `state.py` | Scheduling, JSON checkpoints, JSONL events |
| `execution.py`, `worker.py` | `execute_analysis(request, context)` → validated execution result |
| `containers/investigator/Dockerfile` (repo root), `pyproject.toml`, `uv.lock` | Worker environment, dependencies, CLI packaging |
| `test_execution.py`, `test_scheduler.py`, `test_resume.py`, `test_cli.py` | Isolation, scheduling, recovery, end-to-end integration |

## Shared Code Shape & Output Formats — One Example

**Input:** `patients.csv`, containing ten synthetic rows and two blank ages. IDs below are shortened for readability; discovery generates stable IDs from relative paths and source/selector combinations.

### 1. Discovery identifies the file and table

```python
inventory = discover(dataset_root)  # Inventory
source = inventory.sources[0]      # SourceRef for patients.csv
component = inventory.components[0]  # ComponentRef for its table
```

| Object | Example values | Purpose |
| --- | --- | --- |
| `SourceRef` | `source_id="s_patients"`, `relative_path="patients.csv"`, `format="csv"`, plus `size_bytes`, `mtime_ns`, optional `sha256` | Physical file and change-detection metadata |
| `ComponentRef` | `component_id="c_patients"`, `kind="table"`, `source_ids=["s_patients"]`, `selector={}` | Logical unit to analyze; a future Excel reader can use a sheet selector |
| `Inventory` | `sources=[source]`, `components=[component]`, `limitations=[]`, `schema_version="1.0"` | Files/components available to tools |

- Start with one component per table/image/document file; group only with supporting evidence.
- Unknown inputs remain `kind="unknown"` with limitations. Discovery labels candidates; it does not prove file contents are valid.
- Paths are relative to the dataset root. Size/mtime support change detection; hash inputs used in finalized analyses.

### 2. A tool receives the source and local execution context

Production interface (planned):

```python
def profile_table(source: SourceRef, context: ToolContext) -> ToolResult:
    path = context.resolve_source(source)
    # Read approved input, measure rows/columns, return the result below.
```

| `ToolContext` field/method | Use in this example |
| --- | --- |
| `dataset_root`, `resolve_source(source)` | Resolve `patients.csv` and enforce containment inside the approved root |
| `output_dir` | Private directory for any plots/derived files |
| `seed`, `limits` | Reproducible sampling and resource bounds |
| `component_id`, `result_id` | IDs supplied by the scheduler, reused by the tool |

- Victor implements `ToolContext`; it stays local and is not sent to the model.
- Collection tools receive a list of sources.
- The current disposable example reads the synthetic fixture directly; it does not implement this context or the production profiler.

### 3. The tool returns measurements with coverage and references

```json
{
  "schema_version": "1.0",
  "result_id": "r_counts",
  "component_id": "c_patients",
  "status": "complete",
  "inputs": ["s_patients"],
  "method": "example_csv_counts",
  "parameters": {"missing_age_definition": "empty or whitespace-only age"},
  "coverage": {
    "mode": "full", "unit": "rows", "examined": 10, "total": 10,
    "selection": "all data rows, excluding header", "seed": null
  },
  "measurements": {"row_count": 10, "columns": {"age": {"null_count": 2}}},
  "artifacts": [],
  "limitations": ["Example counts only; no type inference or production profiling."]
}
```

```python
result.validate_references(inventory)  # IDs must refer to the inventory
saved_json = result.to_json()          # Validates before serialization
restored = ToolResult.from_json(saved_json)
```

| Contract/rule | Example meaning |
| --- | --- |
| `Coverage` | All 10 rows examined. A sample must say `mode="sample"`, explain selection, and retain its seed when used. |
| `ArtifactRef` | A future plot could use `artifact_id="a_age"`, `relative_path="artifacts/age.png"`, `media_type="image/png"`. |
| Artifact publishing | Tools return paths relative to their private output directory; Victor validates/relocates them to run-relative paths. |
| Status | `complete`, `partial`, `unsupported`, `failed`, or `deferred`; incomplete results require limitations. A completed sample is still sampled. |
| Measurements | Tables: `columns`; images: `images`/`collection`; documents: `documents`/`collection`. Owners define detailed keys. |
| Validation | Reject unsafe paths, duplicate IDs, unknown references, and non-JSON values. Return measurements/references rather than DataFrames or pixel arrays. |

### 4. Metadata and reasoning consume the same result (planned)

- **Rakshan:** `build_metadata("c_patients", [result])` retains the measured count, coverage, and source references.
- **Jacob:** can state “2 of 10 ages are blank.” Why they are blank remains unknown unless supported by documentation or further analysis.
- **Follow-up:** “Are blank ages concentrated in one group?” becomes an `AnalysisRequest`:

| Field | Example |
| --- | --- |
| `question` | `"Are blank ages concentrated in one group?"` |
| `code` | Python source that counts rows and blank ages per group |
| `input_ids` | `["s_patients"]` |
| `parameters` | `{"group_column": "group", "value_column": "age"}` |
| `expected_outputs` | `["application/json"]` |

- **Victor:** resolves approved inputs, runs the request in isolation, validates outputs, and retains code/logs. An `AnalysisRequest` grants no execution permissions by itself.
- **Vaidehi:** renders measured counts, coverage, evidence, and limitations in the report/notebook. Verify findings; successful execution alone does not establish correctness.

### 5. Save the investigation (planned)

Under `.d37-agent/runs/<run-id>/`:

| Location | Contents |
| --- | --- |
| `manifest.json`, `inventory.json`, `events.jsonl` | Configuration, input inventory, checkpoints/history |
| `results/`, `metadata/`, `semantics/` | Versioned tool results and profiles |
| `analyses/<job-id>/` | Generated code, request/result JSON, logs |
| `artifacts/` | PNG plots, extracted text, normalized Parquet, JSON change logs |
| `reports/revision-001/` | `report.md`, marimo `notebook.py` |

- Retain seeds, input fingerprints, and environment versions for reproduction.
- Keep originals unchanged; never save credentials or rerun generated code outside the isolated worker.

## Runnable Starter — Available on `analysis_agent`

- **Implemented:** contracts, basic discovery, synthetic CSV, disposable counting example, 11 passing tests.
- **Expected result:** 10 rows, 2 blank ages, full coverage, validated source/component references.
- **Limits:** prefix-based format detection; no Excel-sheet/pixel analysis, model calls, or execution sandbox. Skips hidden entries, common credential names, caches, and all symlinks; filename filtering cannot detect arbitrary secret contents.
- **Requirements:** Python 3.11+, standard library only. More detail: [examples/README.md](examples/README.md).

From the repository root:

```sh
python3 -m examples.investigator_starter
python3 -m unittest discover -s tests/investigator -p 'test_*.py' -v
```

| Tests | Checks |
| --- | --- |
| `test_contracts.py` — 5 tests | All seven JSON round trips; invalid fields/JSON/coverage; validation after mutation; source/component references |
| `test_discovery.py` — 6 tests | Stable IDs/order; exclusions and symlinks; candidate formats; unreadable files; invalid roots; correct fixture counts/coverage with unchanged bytes and modification times |

## Branch & Implementation Order

- **Current working branch:** `analysis_agent`; continue the starter and subsequent work here.
- **Order:** Manasa's table tools → Deepal's image tools → Vaidehi's documents/reporting → Rakshan's metadata → Jacob's reasoning → Victor's runtime/integration, with overlap where dependencies allow.
- **Use the starter throughout:** develop against the contracts, synthetic fixtures, and example results; use mocks for unfinished dependencies.
- **At each handoff:** add focused tests, document measurement keys/limitations, and verify compatibility with earlier components.
- **Final integration:** mixed-format inputs, custom analysis isolation, reports/notebook reproduction, interruption/resume, and existing pipeline compatibility.
- **Before merging to `main`:** team review and passing integration checks. Preserve `semantic_agent` and unrelated work; exclude credentials, private datasets, and generated runs.
