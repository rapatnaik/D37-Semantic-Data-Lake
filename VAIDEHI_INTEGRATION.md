# Vaidehi's D37 document and reporting handoff

## Files
- `agents/investigator/tools/documents.py`: `extract_document(source, context) -> ToolResult`.
- `agents/investigator/reporting.py`: `render_report(run_dir) -> str` and `render_notebook(run_dir) -> str`.
- `agents/investigator/templates/notebook.py.tmpl`: offline marimo notebook template.
- `tests/investigator/test_documents.py`, `test_reporting.py`: focused tests.

## Required dependencies
Add `pypdf`, `python-docx`, and `marimo` to the existing `[project].dependencies` in `pyproject.toml` and regenerate `uv.lock` using `uv lock`. The provided ZIP does **not** overwrite your teammates' `pyproject.toml` or `uv.lock`. PDF and DOCX imports are lazy; TXT/MD extraction and reporting work without those two parsers. marimo is needed to *run* generated notebooks, not to generate their source.

## Measurement contract
`measurements.documents[source_id]` includes format, source_path, units_examined, units_total, character_count, word_count, empty_content, possible_scanned_document, references, role, role_note, and text_artifact when extracted. Markdown includes headings. TXT/MD references are line numbers; PDF references are pages; DOCX references are paragraph and table/row locations (not physical page numbers). PDF scanned-content detection is heuristic and does not perform OCR.

`coverage` indicates full/sample/none and the number of units examined. Extraction uses a strict source-size bound, text character bound, and page limit (for PDF). Text is saved as UTF-8 to a private artifact path. No original source is modified.

## Integration
The existing scheduler already imports these functions by their module paths. It creates report revisions and writes the strings returned by the two reporting functions. No changes to teammates' files are required for basic integration. Report content uses validated saved results, metadata and semantics; it does not recompute measurements or call a model. Notebook code embeds a saved snapshot, displays recorded measurements and stored PNGs, and does not execute custom generated code.

## Testing
From the repository root:

```bash
python -m unittest discover -s tests/investigator -p 'test_documents.py' -v
python -m unittest discover -s tests/investigator -p 'test_reporting.py' -v
```

### Limitations / follow-up
- Reproducing *numeric plot generation* requires source-specific plotting functions and approved local inputs; this notebook displays existing saved PNGs rather than rerunning analysis code. Do not run generated analysis code in marimo; delegate it to Victor's isolated worker.
- The report/notebook may contain sensitive measured fields or model interpretations. Review artifacts before sharing. Neither output intentionally includes environment credentials; the report does not load configuration secrets.
- `pypdf` cannot OCR scanned PDFs. Image-only pages are flagged when no text is extractable.
- Report generation does not render new PNG plots; it references saved plots from upstream tools.
