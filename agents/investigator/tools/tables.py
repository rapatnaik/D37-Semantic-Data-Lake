
"""
Tabular data profiling for the D37 Investigator Agent.

Reads structured datasets, calculates EDA statistics,
supports reproducible CSV/TSV sampling, and saves PNG plots.

Original source files are never modified.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

import pandas as pd

from ..contracts import ArtifactRef, Coverage, SourceRef, ToolResult



SUPPORTED_FORMATS = {
    ".csv", ".tsv", ".parquet", ".xlsx",
    ".xls", ".json", ".jsonl"
}

MAX_SOURCE_BYTES = 25 * 1024 * 1024
DEFAULT_SAMPLE_SIZE = 1000


# ---------------------------------------------------------
# 1. Read structured data files
# ---------------------------------------------------------

def read_table(path, sheet_name=0):
    """
    Read a supported table into a Pandas DataFrame.

    The source file is not modified.
    """

    path = Path(path)
    extension = path.suffix.lower()

    if extension not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported table format: {extension}"
        )

    if extension == ".csv":
        df = pd.read_csv(path)

    elif extension == ".tsv":
        df = pd.read_csv(path, sep="\t")

    elif extension == ".parquet":
        df = pd.read_parquet(path)

    elif extension in (".xlsx", ".xls"):
        df = pd.read_excel(
            path,
            sheet_name=sheet_name
        )

    elif extension == ".jsonl":
        df = pd.read_json(path, lines=True)

    elif extension == ".json":
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, list):
            raise ValueError(
                "JSON table must contain a list of records."
            )

        if not all(isinstance(row, dict) for row in data):
            raise ValueError(
                "JSON records must be objects."
            )

        df = pd.DataFrame(data)

    return df


# ---------------------------------------------------------
# 2. Reproducible CSV/TSV sampling
# ---------------------------------------------------------

def sample_delimited_table(
    path,
    sample_size=1000,
    seed=42
):
    """
    Select a reproducible reservoir sample from CSV/TSV.

    Reads the file in chunks instead of retaining all rows.
    Returns (sample_dataframe, total_source_rows).
    """

    path = Path(path)

    separator = (
        "\t" if path.suffix.lower() == ".tsv" else ","
    )

    if type(sample_size) is not int or sample_size < 1:
        raise ValueError(
            "sample_size must be a positive integer"
        )

    rng = random.Random(seed)

    sampled_rows = []
    total_rows = 0
    columns = None

    for chunk in pd.read_csv(
        path,
        sep=separator,
        chunksize=1000,
        low_memory=False
    ):
        if columns is None:
            columns = list(chunk.columns)

        for row in chunk.itertuples(
            index=False,
            name=None
        ):
            total_rows += 1

            if len(sampled_rows) < sample_size:
                sampled_rows.append(row)

            else:
                index = rng.randrange(total_rows)

                if index < sample_size:
                    sampled_rows[index] = row

    sampled_df = pd.DataFrame(
        sampled_rows,
        columns=columns
    )

    return sampled_df, total_rows


# ---------------------------------------------------------
# 3. Table statistics
# ---------------------------------------------------------

def calculate_table_statistics(df):
    """
    Calculate factual EDA statistics without changing data.

    Includes row counts, missingness, types, duplicates,
    candidate keys, numerical summaries, and top values.
    """

    if df.columns.has_duplicates:
        raise ValueError(
            "Duplicate column names are not supported."
        )

    columns = {}

    for col in df.columns:
        series = df[col]
        column_name = str(col)

        null_count = int(series.isna().sum())
        distinct_count = int(
            series.nunique(dropna=True)
        )

        info = {
            "dtype": str(series.dtype),
            "null_count": null_count,
            "null_percentage": (
                float(null_count / len(df) * 100)
                if len(df) > 0 else 0.0
            ),
            "distinct_count": distinct_count,
            "candidate_key": bool(
                len(df) > 0
                and series.notna().all()
                and series.is_unique
            )
        }

        # Numerical columns
        if (
            pd.api.types.is_numeric_dtype(series)
            and not pd.api.types.is_bool_dtype(series)
        ):
            numeric = (
                series.replace(
                    [float("inf"), -float("inf")],
                    float("nan")
                )
                .dropna()
            )

            info["min"] = (
                float(numeric.min())
                if len(numeric) else None
            )

            info["max"] = (
                float(numeric.max())
                if len(numeric) else None
            )

            info["mean"] = (
                float(numeric.mean())
                if len(numeric) else None
            )

            info["median"] = (
                float(numeric.median())
                if len(numeric) else None
            )

            info["std"] = (
                float(numeric.std())
                if len(numeric) > 1 else None
            )

        # Categorical and other non-numeric columns
        else:
            counts = series.value_counts(
                dropna=True
            ).head(5)

            info["top_values"] = [
                {
                    "value": str(value),
                    "count": int(count)
                }
                for value, count in counts.items()
            ]

        columns[column_name] = info

    return {
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "duplicate_row_count": int(
            df.duplicated().sum()
        ),
        "columns": columns
    }


# ---------------------------------------------------------
# 4. Agent-facing table profiling
# ---------------------------------------------------------

def profile_table(
    source: SourceRef,
    context: Any
) -> ToolResult:
    """
    Profile a structured table using the team's ToolResult.

    Small files receive full profiling.
    Large CSV/TSV files receive sampled profiling.

    Expected context:
        dataset_root
        resolve_source(source)
        component_id
        result_id
        seed (optional)
    """

    supported = {
        "csv", "tsv", "parquet", "xlsx",
        "xls", "json", "jsonl"
    }

    max_source_bytes = MAX_SOURCE_BYTES

    def make_result(
        status,
        measurements=None,
        limitations=None,
        examined=0
    ):
        return ToolResult(
            result_id=context.result_id,
            component_id=context.component_id,
            status=status,
            inputs=[source.source_id],
            method="table_profile_v1",
            parameters={
                "max_source_bytes": max_source_bytes,
                "format": source.format,
                "sampling": "none"
            },
            coverage=Coverage(
                mode=(
                    "full"
                    if status == "complete"
                    else "none"
                ),
                unit="rows",
                examined=examined,
                total=(
                    examined
                    if status == "complete"
                    else None
                ),
                selection=(
                    "All data rows"
                    if status == "complete"
                    else "No rows examined"
                ),
                seed=None
            ),
            measurements=measurements or {},
            artifacts=[],
            limitations=limitations or []
        )

    # Validate file format.
    if source.format not in supported:
        return make_result(
            "unsupported",
            limitations=[
                f"Unsupported table format: {source.format}"
            ]
        )

    try:
        # Resolve and validate the approved input path.
        root = Path(
            context.dataset_root
        ).resolve(strict=True)

        path = Path(
            context.resolve_source(source)
        ).resolve(strict=True)

        expected = (
            root / source.relative_path
        ).resolve(strict=True)

        if (
            path != expected
            or not path.is_relative_to(root)
            or not path.is_file()
        ):
            raise ValueError(
                "Table source is not an approved regular file."
            )

        file_size = path.stat().st_size
        is_large = file_size > max_source_bytes

        # ---------------------------------------------
        # Case 1: Large CSV/TSV — sampled EDA
        # ---------------------------------------------

        if is_large and source.format in {"csv", "tsv"}:

            sample_size = DEFAULT_SAMPLE_SIZE

            seed = getattr(context, "seed", None)
            if seed is None:
                seed = 42

            df, total_rows = sample_delimited_table(
                path,
                sample_size=sample_size,
                seed=seed
            )

            measurements = calculate_table_statistics(df)

            # Uniqueness in a sample does not prove
            # uniqueness in the entire dataset.
            for info in measurements["columns"].values():
                info["candidate_key"] = None

            measurements["profile_scope"] = "sample"
            measurements["sample_row_count"] = int(len(df))
            measurements["total_source_rows"] = int(
                total_rows
            )

            result = ToolResult(
                result_id=context.result_id,
                component_id=context.component_id,
                status="complete",
                inputs=[source.source_id],
                method="table_profile_v1",
                parameters={
                    "max_source_bytes": max_source_bytes,
                    "sample_size": sample_size,
                    "format": source.format,
                    "sampling": "reservoir"
                },
                coverage=Coverage(
                    mode="sample",
                    unit="rows",
                    examined=len(df),
                    total=total_rows,
                    selection=(
                        "Reservoir sample of CSV/TSV rows"
                    ),
                    seed=seed
                ),
                measurements=measurements,
                artifacts=[],
                limitations=[
                    "Missingness, distributions, duplicates, "
                    "and column statistics describe sampled "
                    "rows only. Candidate keys have not been "
                    "verified against the complete dataset."
                ]
            )
            return attach_table_plots(result, df, source, context)

        # ---------------------------------------------
        # Case 2: Large unsupported sampling format
        # ---------------------------------------------

        if is_large:
            return make_result(
                "unsupported",
                limitations=[
                    "File exceeds the 25 MB full-read limit. "
                    "Sampling is not yet implemented for "
                    f"{source.format} files."
                ]
            )

        # ---------------------------------------------
        # Case 3: Small file — full EDA
        # ---------------------------------------------

        df = read_table(path)

        measurements = calculate_table_statistics(df)
        measurements["profile_scope"] = "full"

        result = make_result(
            "complete",
            measurements=measurements,
            examined=len(df)
        )
        return attach_table_plots(result, df, source, context)

    except Exception as error:
        return make_result(
            "failed",
            limitations=[
                f"Table profiling failed: "
                f"{type(error).__name__}: {error}"
            ]
        )


# ---------------------------------------------------------
# 5. Save reproducible EDA plots
# ---------------------------------------------------------

def plot_table_profile(
    df: pd.DataFrame,
    output_dir: str | Path,
    max_numeric_columns: int = 6
) -> list[Path]:
    """
    Create PNG visualizations for tabular EDA.

    Saves:
        missing_values.png
        numeric_distributions.png (if numeric columns exist)

    Returns paths to generated PNG files.
    The input DataFrame is not modified.

    The caller must supply an approved output directory.
    """

    import matplotlib
    matplotlib.use("Agg")

    import matplotlib.pyplot as plt

    if (
        type(max_numeric_columns) is not int
        or max_numeric_columns < 1
    ):
        raise ValueError(
            "max_numeric_columns must be a positive integer"
        )

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    generated = []

    # ---------------------------------------------
    # Plot 1: Missing-value counts
    # ---------------------------------------------

    missing = df.isna().sum()

    if len(missing) > 0:
        missing = missing.head(30)

        fig, ax = plt.subplots(
            figsize=(9, 5)
        )

        ax.bar(
            [str(column) for column in missing.index],
            missing.values
        )

        ax.set_title("Missing Values by Column")
        ax.set_xlabel("Column")
        ax.set_ylabel("Missing Value Count")

        ax.tick_params(
            axis="x",
            rotation=45
        )

        fig.tight_layout()

        target = output_dir / "missing_values.png"

        fig.savefig(
            target,
            dpi=150
        )

        plt.close(fig)
        generated.append(target)

    # ---------------------------------------------
    # Plot 2: Numeric distributions
    # ---------------------------------------------

    numeric_columns = df.select_dtypes(
        include="number"
    ).columns[:max_numeric_columns]

    if len(numeric_columns) > 0:
        fig, axes = plt.subplots(
            len(numeric_columns),
            1,
            figsize=(
                8,
                3 * len(numeric_columns)
            ),
            squeeze=False
        )

        for i, column in enumerate(numeric_columns):
            ax = axes[i, 0]

            values = pd.to_numeric(
                df[column],
                errors="coerce"
            )

            values = values.replace(
                [float("inf"), -float("inf")],
                float("nan")
            ).dropna()

            if len(values) > 0:
                ax.hist(
                    values,
                    bins=20
                )
            else:
                ax.text(
                    0.5,
                    0.5,
                    "No finite values",
                    ha="center",
                    va="center",
                    transform=ax.transAxes
                )

            ax.set_title(
                f"Distribution: {column}"
            )

            ax.set_xlabel(str(column))
            ax.set_ylabel("Frequency")

        fig.tight_layout()

        target = (
            output_dir / "numeric_distributions.png"
        )

        fig.savefig(
            target,
            dpi=150
        )

        plt.close(fig)
        generated.append(target)

    return generated




def attach_table_plots(
    result: ToolResult,
    df: pd.DataFrame,
    source: SourceRef,
    context: Any
) -> ToolResult:
    """
    Generate EDA plots and register them in the ToolResult.

    The output paths are relative to context.output_dir.
    Original source files are never modified.
    """
    token = hashlib.sha256(
        source.source_id.encode("utf-8")
    ).hexdigest()[:16]

    relative_dir = f"tables/{token}/profile"

    output_root = Path(context.output_dir).resolve()
    plot_dir = (output_root / relative_dir).resolve()

    if not plot_dir.is_relative_to(output_root):
        raise ValueError("Plot path escapes output directory.")

    paths = plot_table_profile(df, plot_dir)

    for index, path in enumerate(paths):
        relative_path = path.relative_to(output_root).as_posix()

        result.artifacts.append(
            ArtifactRef(
                artifact_id=f"table_plot_{token}_{index}",
                relative_path=relative_path,
                media_type="image/png"
            )
        )

    result.validate()
    return result
