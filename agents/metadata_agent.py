import pandas as pd
import duckdb
import json
from pathlib import Path

#Metadata extraction. Agents extract the structure of both sources.
def extract_metadata(path):
    df = pd.read_csv(path)

    #extracting metadata of dataset
    metadata = {
        "dataset": path,
        "row_count": df.shape[0],
        "column_count": df.shape[1],
        "columns": {}
    }

    #extracting metadata for every column
    for column in df.columns:
        column_data = df[column]
        no_nulls = column_data.dropna()

        metadata["columns"][column] = {
            "datatype": str(column_data.dtype),
            "null_count": int(column_data.isna().sum()),
            "null_percentage": float(round(column_data.isna().mean() * 100, 2)),
            "all_missing": bool(column_data.isna().all()),
            "distinct_count": int(column_data.nunique()),
            "column_sample": no_nulls.head().tolist()
        }

        #summary statistics for numerical type columns
        #includes numerically-encoded categorical columns like 'sex'
        if pd.api.types.is_numeric_dtype(column_data):
            metadata["columns"][column]["statistics"] = {
                "min": float(no_nulls.min()) if not no_nulls.empty else None,
                "max": float(no_nulls.max()) if not no_nulls.empty else None,
                "mean": float(no_nulls.mean()) if not no_nulls.empty else None,
                "median": float(no_nulls.median()) if not no_nulls.empty else None
            }

        # summary statistics for categorical type columns
        else:
            metadata["columns"][column]["frequent_values"] = {
                str(value): int(count)
                for value, count in column_data.value_counts().head().items()
            }

    #data profiling using SQL
    sql_stats = sql_profile(df)

    #merging SQL statistics with existing metadata
    for column in df.columns:
        metadata["columns"][column]["sql_profile"] = sql_stats[column]

    #finding potential primary keys
    metadata["potential_keys"] = primary_keys(df)

    return metadata

#Data profiling: Agents compute column statistics with SQL.
#computing same statistics as above, just using SQL not pandas.

def sql_profile(df):
    #duckdb = sqlite for analytics workloads
    con = duckdb.connect()
    con.register("dataset", df)

    sql_metadata = {}

    #summary statistics for every column
    for column in df.columns:
        #fixing formatting for SQL
        col = '"' + column.replace('"', '""') + '"'

        query = f"""
            SELECT
                COUNT(*) - COUNT({col}) AS null_count,
                COUNT(DISTINCT {col}) AS distinct_count
            FROM dataset
        """

        #runs query, returns one row per column, and puts into Python-retrievable result (tuple)
        output = con.execute(query).fetchone()

        sql_metadata[column] = {
            "null_count": output[0],
            "distinct_count": output[1]
        }

        #additional statistics for numerical type columns
        if pd.api.types.is_numeric_dtype(df[column]):
            query = f"""
                SELECT
                    MIN({col}),
                    MAX({col}),
                    AVG({col}),
                    MEDIAN({col})
                FROM dataset
            """

            #run query
            output = con.execute(query).fetchone()

            sql_metadata[column]["statistics"] = {
                "min": output[0],
                "max": output[1],
                "mean": output[2],
                "median": output[3]
            }

    con.close()
    return sql_metadata

#identifying primary keys
def primary_keys(df):
    #possible primary keys
    keys = []

    for column in df.columns:
        is_unique = df[column].is_unique
        has_no_nulls = df[column].notna().all()
        
        #if all values are unique and no nulls within that column
        if is_unique and has_no_nulls:
            keys.append(column)
    
    return keys


#detecting possible relationships 
#only looks at columns with SAME NAME
def possible_relationships(df1, df2):
    relationships = {}

    #shared columns between the two
    shared_columns = set(df1.columns) & set(df2.columns)

    for column in shared_columns:
        #get unique non-null values in both
        vals1 = set(df1[column].dropna().unique())
        vals2 = set(df2[column].dropna().unique())\
        
        #find overlapping values
        overlap = vals1 & vals2

        relationships[column] = {
            "shared_values": len(overlap),
            "dataset1_distinct": len(vals1),
            "dataset2_distinct": len(vals2)
        }

    return relationships

#exporting metadata into a JSON file for downstream agents
def export_metadata(metadata, output_path):
    #output folder
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    #saves metadata as JSON
    with open(output_path, "w") as file:
        json.dump(metadata, file, indent=4)

    print(f"Metadata exported to {output_path}")




