# Investigator starter

From the repository root, using Python 3.11 or newer (standard library only):

```sh
python3 -m examples.investigator_starter
python3 -m unittest discover -s tests/investigator -p 'test_*.py' -v
```

The example prints a `ToolResult` JSON with `status: "complete"`,
`measurements.row_count: 10`, `measurements.columns.age.null_count: 2`, and
coverage `{mode: "full", unit: "rows", examined: 10, total: 10, ...}`.
Source/component IDs are checked against the discovered inventory before printing.

Discovery returns relative file paths, size/mtime metadata, stable path-derived
IDs, and one candidate component per file. It reads at most 4096 prefix bytes
per file, recognizes common image/PDF signatures and CSV/TSV/text candidates,
and retains unsupported files as unknown components with limitations. Excel
sheets and image contents are not analyzed. All symlinks, hidden entries
(including `.d37-agent`), common credential filenames, and cache directories
are skipped. Filename exclusions cannot identify secrets in arbitrary files;
select a data directory. Discovery is not a concurrent-filesystem sandbox.

The example then reads only the synthetic CSV, measures all ten rows, and
packages two counts with their source IDs and coverage. This shows the handoff
from discovery to a tool to a structured result. It is a disposable example,
not Manasa's production profiler. It makes no model calls, writes no files,
and implements no CLI, execution worker, or metadata assembly.
