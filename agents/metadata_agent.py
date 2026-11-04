import pandas as pd

def extract_metadata(path):
    df = pd.read_csv(path)

    # extracting metadata of dataset
    metadata = {
        "dataset": path,
        "row_count": df.shape[0],
        "column_count": df.shape[1],
        "columns": {}
    }

    # extracting metadata for every column
    for column in df.columns:
        column_data = df[column]
        no_nulls = column_data.dropna()

        metadata["columns"][column] = {
            "datatype": str(column_data.dtype),
            "null_count": int(column_data.isna().sum()),
            "null_percentage": round(column_data.isna().mean() * 100, 2),
            "all_missing": bool(column_data.isna().all()),
            "distinct_count": int(column_data.nunique()),
            "column_sample": no_nulls.head().tolist()
        }

        # summary statistics for numerical type categories
        # includes numerically-encoded categorical categories like 'sex'
        if pd.api.types.is_numeric_dtype(column_data):
            metadata["columns"][column]["statistics"] = {
                "min": float(no_nulls.min()) if not no_nulls.empty else None,
                "max": float(no_nulls.max()) if not no_nulls.empty else None,
                "mean": float(no_nulls.mean()) if not no_nulls.empty else None,
                "median": float(no_nulls.median()) if not no_nulls.empty else None
            }

        # summary statistics for categorical type categories
        else:
            metadata["columns"][column]["frequent_values"] = {
                str(value): int(count)
                for value, count in column_data.value_counts().head().items()
            }
        

    return metadata

