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

        metadata["columns"][column] = {
            "datatype": str(column_data.dtype),
            "null_count": int(column_data.isna().sum()),
            "null_percentage": round(column_data.isna().mean() * 100, 2),
            "all_missing": bool(column_data.isna().all())
        }
    
    return metadata

