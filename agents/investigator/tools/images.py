"""Bounded PNG/JPEG/TIFF image inspection for D37's directory investigator.

Inputs are trusted SourceRef IDs plus a local ToolContext.  The context must
provide resolve_source(source), output_dir, component_id, result_id, and may
provide limits (dict) and seed.  Raw pixels never enter the ToolResult.

This is not a microscopy .lif decoder, an OCR tool, or a security sandbox.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image, UnidentifiedImageError

from ..contracts import ArtifactRef, Coverage, SourceRef, ToolResult

SUPPORTED = {"png", "jpeg", "tiff"}
DEFAULT_LIMITS = {
    "max_decode_pixels": 16_000_000,  # prevent expensive whole-frame decodes
    "max_decode_bytes": 96 * 1024 * 1024,
    "max_sample_pixels": 100_000,
    "preview_max_side": 800,
}


def _limits(context: Any) -> dict[str, int]:
    given = getattr(context, "limits", None) or {}
    if not isinstance(given, dict):
        given = {key: getattr(given, key) for key in DEFAULT_LIMITS if hasattr(given, key)}
    result = DEFAULT_LIMITS.copy()
    for name in result:
        if name in given:
            value = given[name]
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
            result[name] = value
    return result


def _token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _output_path(context: Any, relative: str) -> Path:
    root = Path(context.output_dir).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Output path escapes the output directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _source_path(source: SourceRef, context: Any) -> Path:
    # Victor will supply the production resolver.  Check containment here too.
    root = Path(context.dataset_root).resolve(strict=True)
    path = Path(context.resolve_source(source)).resolve(strict=True)
    expected = (root / source.relative_path).resolve(strict=True)
    if path != expected or not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Image source is not an approved regular file")
    return path


def _result(
    source: SourceRef,
    context: Any,
    *,
    status: str,
    examined: int = 0,
    total: int | None = None,
    measurements: dict[str, Any] | None = None,
    artifacts: list[ArtifactRef] | None = None,
    limitations: list[str] | None = None,
    parameters: dict[str, Any] | None = None,
) -> ToolResult:
    mode = "none" if examined == 0 else ("full" if total == examined else "sample")
    if status != "complete" and not limitations:
        limitations = ["Image analysis is incomplete."]
    return ToolResult(
        result_id=str(context.result_id),
        component_id=str(context.component_id),
        status=status,
        inputs=[source.source_id],
        method="bounded_image_profile_v1",
        parameters=parameters or {},
        coverage=Coverage(
            mode=mode, unit="pixels", examined=examined, total=total,
            selection="first TIFF frame; deterministic spatial grid with recorded stride",
            seed=None,  # grid sampling does not use randomness
        ),
        measurements={"images": {source.source_id: measurements or {}}},
        artifacts=artifacts or [],
        limitations=limitations or [],
    )


def _preview_image(pixels: np.ndarray, max_side: int) -> tuple[Image.Image, str]:
    """Make an inspection-only RGB preview, with explicit scaling recorded."""
    h, w = pixels.shape[:2]
    stride = max(1, math.ceil(max(h, w) / max_side))
    small = pixels[::stride, ::stride]
    if small.ndim == 2:
        small = small[:, :, None]
    channels = small.shape[2]

    if small.dtype == np.uint8:
        display = small[:, :, :3]
        transform = "no intensity scaling (8-bit)"
    else:
        # Non-8-bit data needs visualization scaling; NEVER reuse these pixels
        # for numerical analysis or replace the source file with this image.
        planes = []
        for c in range(min(channels, 3)):
            v = small[:, :, c].astype(np.float64)
            finite = v[np.isfinite(v)]
            if finite.size == 0:
                v8 = np.zeros(v.shape, dtype=np.uint8)
            else:
                lo, hi = np.percentile(finite, [1, 99])
                v8 = (np.clip((v - lo) * 255 / (hi - lo), 0, 255)
                      if hi > lo else np.zeros_like(v))
                v8 = np.nan_to_num(v8, nan=0, posinf=255, neginf=0).astype(np.uint8)
            planes.append(v8)
        display = np.stack(planes, axis=2)
        transform = "per-band 1st–99th percentile scaling to 8-bit"

    if display.shape[2] == 1:
        display = np.repeat(display, 3, axis=2)
    elif display.shape[2] == 2:
        display = np.repeat(display[:, :, :1], 3, axis=2)
    else:
        display = display[:, :, :3]
    note = (
        f"grid-stride={stride}; {transform}; RGB preview uses first 3 bands "
        "(or grayscale if fewer than 3); ignores alpha; no EXIF rotation"
    )
    return Image.fromarray(np.ascontiguousarray(display), mode="RGB"), note


def _plot_histogram(samples: np.ndarray, labels: list[str], target: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 3.5))
    for index in range(samples.shape[2]):
        values = samples[:, :, index].ravel().astype(np.float64)
        values = values[np.isfinite(values)]
        if values.size:
            ax.hist(values, bins=32, density=True, histtype="step", linewidth=1.4,
                    label=labels[index], alpha=0.9)
    ax.set(title="Sampled pixel-intensity distributions", xlabel="Raw pixel value", ylabel="Density")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(target, dpi=130)
    plt.close(fig)


def _inspect(source: SourceRef, context: Any) -> ToolResult:
    limits = _limits(context)
    params = {**limits, "supported_formats": sorted(SUPPORTED)}
    info: dict[str, Any] = {"relative_path": source.relative_path, "source_id": source.source_id}
    if source.format not in SUPPORTED:
        return _result(source, context, status="unsupported", measurements=info,
                       parameters=params, limitations=["File format not supported by image EDA."])
    try:
        path = _source_path(source, context)
        with Image.open(path) as image:
            actual_format = (image.format or "").lower()
            if actual_format == "jpg":
                actual_format = "jpeg"
            if actual_format not in SUPPORTED:
                return _result(source, context, status="unsupported", measurements=info,
                               parameters=params, limitations=["Decoder reports unsupported image format."])
            width, height = image.size
            frames = int(getattr(image, "n_frames", 1))
            mode = image.mode
            bands = list(image.getbands())
            n_channels = len(bands)
            bytes_per_band = 4 if (mode in {"I", "F"}) else 2 if ("16" in mode) else 1
            estimated_bytes = width * height * n_channels * bytes_per_band
            info.update({
                "format": actual_format, "width": int(width), "height": int(height),
                "mode": mode, "channel_count": n_channels, "bands": bands,
                "frame_count": frames, "estimated_decode_bytes": estimated_bytes,
            })
            if width * height > limits["max_decode_pixels"] or estimated_bytes > limits["max_decode_bytes"]:
                return _result(
                    source, context, status="deferred", measurements=info, parameters=params,
                    total=(width * height if frames == 1 else None),
                    limitations=["First frame exceeds configured decode/memory budget; no pixels decoded."],
                )
            image.seek(0)
            # The budget above is checked BEFORE decoding and constructing arrays.
            image.load()
            pixels = np.asarray(image)
            if pixels.ndim == 2:
                pixels = pixels[:, :, None]
            if pixels.ndim != 3 or pixels.shape[2] != n_channels or pixels.dtype.kind not in "uif":
                return _result(source, context, status="unsupported", measurements=info,
                               parameters=params, limitations=["Unsupported image channel layout or pixel dtype."])
            h, w, _ = pixels.shape
            # A square-root stride alone can oversample very skinny images.
            # Increase it until the actual sampled grid fits the pixel budget.
            step = max(1, math.ceil(math.sqrt((w * h) / limits["max_sample_pixels"])))
            step = max(step, math.ceil(max(w, h) / limits["max_sample_pixels"]))
            while math.ceil(w / step) * math.ceil(h / step) > limits["max_sample_pixels"]:
                step += 1
            samples = pixels[::step, ::step, :]
            observed = int(samples.shape[0] * samples.shape[1])
            channel_stats = []
            for i, name in enumerate(bands):
                vec = samples[:, :, i].ravel().astype(np.float64)
                valid = vec[np.isfinite(vec)]
                if valid.size == 0:
                    channel_stats.append({"band": name, "index": i, "valid_sample_count": 0})
                    continue
                channel_stats.append({
                    "band": name, "index": i, "valid_sample_count": int(valid.size),
                    "minimum": float(valid.min()), "maximum": float(valid.max()),
                    "mean": float(valid.mean()), "median": float(np.median(valid)),
                    "std": float(valid.std()),
                    "zero_pct": float(100 * np.mean(valid == 0)),
                    "nonfinite_count": int(vec.size - valid.size),
                })
            info.update({
                "dtype": str(pixels.dtype), "sample_stride": step,
                "sampled_pixels_per_band": observed, "intensity_by_channel": channel_stats,
            })
            warnings: list[str] = []
            if frames > 1:
                warnings.append(f"Only first frame of {frames} frames was inspected; frame shapes may differ.")
            if mode == "P":
                warnings.append("Palette indices are profiled; RGB palette values are not inferred as separate channels.")
            if mode in {"RGBA", "LA"}:
                warnings.append("Alpha was included in statistics but dropped from the RGB preview.")
            preview, transform = _preview_image(pixels, limits["preview_max_side"])
            info["preview_transform"] = transform
            token = _token(source.source_id)
            preview_rel = f"previews/{token}.png"
            hist_rel = f"histograms/{token}.png"
            preview.save(_output_path(context, preview_rel))
            _plot_histogram(samples, bands, _output_path(context, hist_rel))
            info["preview_artifact_id"] = f"preview_{token}"
            artifacts = [ArtifactRef(info["preview_artifact_id"], preview_rel, "image/png"),
                         ArtifactRef(f"histogram_{token}", hist_rel, "image/png")]
            # For multipage images, total pixels over frames may be unknown.
            total = (width * height if frames == 1 else None)
            return _result(source, context, status="partial" if frames > 1 else "complete",
                           examined=observed, total=total, measurements=info, artifacts=artifacts,
                           limitations=warnings + (["Image statistics are spatially sampled; see stride and coverage."]
                                                  if step > 1 else []), parameters=params)
    except (OSError, ValueError, SyntaxError, MemoryError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        # Avoid storing arbitrary external exception messages and absolute paths.
        info["failure_type"] = type(exc).__name__
        return _result(source, context, status="failed", measurements=info, parameters=params,
                       limitations=[f"Image could not be safely inspected ({type(exc).__name__})."])


def inspect_image(source: SourceRef, context: Any) -> ToolResult:
    """Inspect one image and save preview/histogram under context.output_dir."""
    return _inspect(source, context)


def profile_image_collection(sources: Sequence[SourceRef], context: Any) -> ToolResult:
    """Profile a collection, with per-file failures and two overview plots.

    `context.component_id` should reference a collection ComponentRef that lists
    these sources (to be created by the scheduler/metadata integration layer).
    """
    if not sources:
        raise ValueError("Expected at least one image source")
    if len({source.source_id for source in sources}) != len(sources):
        raise ValueError("Duplicate source IDs in image collection")
    analyses = [_inspect(source, context) for source in sources]
    images = {source.source_id: result.measurements["images"][source.source_id]
              for source, result in zip(sources, analyses)}
    statuses = {source.source_id: result.status for source, result in zip(sources, analyses)}
    artifacts = [a for result in analyses for a in result.artifacts]
    good = [(source.source_id, images[source.source_id]) for source, result in zip(sources, analyses)
            if result.status in {"complete", "partial"}]
    mean_levels = []
    labels, widths, heights = [], [], []
    for source_id, item in good:
        labels.append(item["relative_path"].split("/")[-1][:26])
        widths.append(item["width"])
        heights.append(item["height"])
        values = [c["mean"] for c in item["intensity_by_channel"] if "mean" in c]
        mean_levels.append(float(np.mean(values)) if values else 0.0)
    if good:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        token = _token(";".join(source.source_id for source in sources))
        x = np.arange(len(good))
        fig, ax = plt.subplots(figsize=(max(7, len(good) * 0.45), 4))
        ax.plot(x, widths, "o-", label="Width")
        ax.plot(x, heights, "o-", label="Height")
        ax.set(xticks=x, xticklabels=labels, ylabel="Pixels", title="Image dimensions")
        ax.tick_params(axis="x", labelrotation=75)
        ax.legend()
        fig.tight_layout()
        rel = f"figures/{token}_dimensions.png"
        fig.savefig(_output_path(context, rel), dpi=130)
        plt.close(fig)
        artifacts.append(ArtifactRef(f"dimensions_{token}", rel, "image/png"))

        fig, ax = plt.subplots(figsize=(max(7, len(good) * 0.45), 4))
        ax.bar(x, mean_levels)
        ax.set(xticks=x, xticklabels=labels, ylabel="Raw mean intensity",
               title="Mean sampled intensity across bands (not biologically standardized)")
        ax.tick_params(axis="x", labelrotation=75)
        fig.tight_layout()
        rel = f"figures/{token}_intensity.png"
        fig.savefig(_output_path(context, rel), dpi=130)
        plt.close(fig)
        artifacts.append(ArtifactRef(f"intensity_{token}", rel, "image/png"))
    partial_or_failed = sum(result.status != "complete" for result in analyses)
    issues = [f"{source.relative_path}: {result.status} — {result.limitations[0]}"
              for source, result in zip(sources, analyses) if result.status != "complete"]
    return ToolResult(
        result_id=str(context.result_id), component_id=str(context.component_id),
        status="complete" if not partial_or_failed else "partial",
        inputs=[source.source_id for source in sources],
        method="bounded_image_collection_v1",
        parameters=_limits(context),
        coverage=Coverage("full", "files", len(sources), len(sources),
                          "attempted every supplied file once; see per-file pixel sampling"),
        measurements={
            "images": images,
            "collection": {"file_count": len(sources), "success_count": len(good),
                           "statuses": statuses,
                           "per_image_pixel_coverage": {
                               source.source_id: result.coverage.to_dict()
                               for source, result in zip(sources, analyses)},
                           "note": "Do not interpret cross-file intensity differences as biological effects."},
        },
        artifacts=artifacts,
        limitations=issues,
    )
