# Deepal's Image EDA Tool — Integration Notes

## Scope
- Supports PNG, JPEG and TIFF; no Leica `.lif` decoding or OCR.
- `inspect_image(source, context) -> ToolResult` analyzes one image.
- `profile_image_collection(sources, context) -> ToolResult` profiles many images.
- Reports raw-channel statistics, sampling, failures, multipage limitations and PNG artifacts.
- Does not edit or write the original images.

## Integration contract
The runtime must provide a local context with `dataset_root`, `resolve_source(source)`,
`output_dir`, `component_id`, `result_id`, and optional `limits` and `seed`.
`ToolResult` references the context's component ID. For collection runs, the runtime
should add a collection `ComponentRef(kind='images', source_ids=[...])` to the
inventory, since current discovery creates one component per file.

All preview/histogram/plot paths returned as `ArtifactRef.relative_path` are relative
to `context.output_dir`. Runtime publishing must validate/relocate them to run-relative
paths, following `Worksplit.md`.

## Defaults and limitations
- Maximum decoded first-frame area: 16 million pixels, maximum estimated raw decode:
  96 MiB. Larger images are `deferred`, **not** fully scanned or downsampled.
- Raw intensity statistics use a deterministic spatial grid with at most 100,000
  sample locations per band. `Coverage` records examined pixel locations.
- Multipage TIFFs profile the first frame only and return `partial`.
- 8-bit previews use the first three channels (or grayscale). Non-8-bit previews
  are 8-bit and display-scaled per channel at 1st–99th percentiles. Alpha is not
  rendered in the preview; EXIF orientation isn't applied.
- Pixel arrays stay local; only JSON-compatible stats and artifact refs are returned.
- Intensity comparisons across images are descriptive, not biological conclusions.
- This is a bounded best-effort reader, not a hardened sandbox; the runtime must
  enforce filesystem isolation and OS limits for untrusted code and datasets.

## Install dependencies
From the repository root, prefer:

```sh
uv add pillow matplotlib
```

If not using uv, use your activated environment:

```sh
python3 -m pip install numpy pillow matplotlib
```

## Run tests

```sh
python3 -m unittest discover -s tests/investigator -p 'test_*.py' -v
```

Run with the existing `contracts.py` and `discovery.py` from `analysis_agent`.
The tests create temporary synthetic inputs; no cardiovascular data is required.

## Smoke-test the integrated profiler on an image folder
From the repository root (after copying `examples/image_eda_demo.py`):

```sh
uv run python -m examples.image_eda_demo Images/outputs/previews --output .d37-agent/image-demo
```

The `.d37-agent/image-demo` folder will contain `image_results.json`, individual
previews and histograms, and collection figures. Add `.d37-agent/` to `.gitignore`
so generated results do not accidentally get committed.
