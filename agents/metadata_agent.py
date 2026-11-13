import pandas as pd
import numpy as np
import duckdb
import json
from pathlib import Path
import re
import tifffile

#Metadata extraction. Agents extract the structure of both sources.
def extract_metadata_csv(path):
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


#---- for imaging data ----
#used AI tools for help with Path functions (as_posix) and image metadata details

#to standardize _Mask & _overview .lif and .txt files under one
def normalize_samples(filename):
    name = Path(filename).stem
    match = re.match(r"^(\d{6}_\d+)", name)

    if not match:
        return None
    
    return match.group(1) + "_overview"

#structural metadata about each file
def file_metadata(path):
    path = Path(path)

    return {
        "filename": path.name,
        "path": path.as_posix(),
        "extension": path.suffix.lower(),
        "filesize": path.stat().st_size #bytes
    }

#extract metadata of imaging samples, spread across datasets
def extract_metadata_img(path):
    root = Path(path)
    samples = {} #record of all 22 samples

    #to access or initialize a sample's record
    def get_sample(id):
        if id not in samples:
            samples[id] = {
                "sample_id": id,
                "files": {},
                "quality_flags": []
            }
        return samples[id]
    
    # 1. extract ROI values
    roi_directory = root / "ROIvalues"

    for roi_path in sorted(roi_directory.glob("*.txt")):
        id = normalize_samples(roi_path.name)

        if id is None:
            continue

        #putting into 'samples' record
        sample = get_sample(id)
        sample["files"]["roi"] = file_metadata(roi_path)

        #reading the coordinates - used AI for try-except format to avoid error full stop
        try:
            coordinates = np.loadtxt(roi_path, dtype=float)
            if coordinates.shape != (4,2):
                raise ValueError(
                    f"The ROI shape should be 4x2. This one is: "
                    f"{coordinates.shape}"
                )
            
            if not np.isfinite(coordinates).all():
                raise ValueError(
                    f"This ROI contains non-finite number(s)"
                )
            
            #getting x and y coordinates
            x = coordinates[:, 0]
            y = coordinates[:, 1]

            sample["roi"] = {
                "coordinates": coordinates.tolist(),
                "point_count": 4,
                "x_min": float(x.min()),
                "x_max": float(x.max()),
                "y_min": float(y.min()),
                "y_max": float(y.max()),
                "width_px": float(x.max() - x.min()),
                "height_px": float(y.max() - y.min()),
                "coordinate_frame": (
                    "native_transformed_image_unverified"
                )
            }
        
        except (ValueError, OSError) as error:
            sample["quality_flags"].append(
                f"roi_read_error: {error}"
            )

    # 2. extract orientation metadata
    orientation_path = root / "orientationStack.txt"

    if orientation_path.exists():
        orientation_df = pd.read_csv(
            orientation_path,
            sep=r"\s+",
            engine="python"
        )

        for _, row in orientation_df.iterrows():
            id = normalize_samples(str(row["filename"]))
            if id is None:
                continue
                
            sample = get_sample(id)
            sample["files"]["orientation"] = (file_metadata(orientation_path))

            sample["orientation"] = {
                "rotation_angle": float(row["angle"])
            }


    # 3. extract masks TIFF

    mask_directory = root / "Masks"

    for mask_path in sorted(mask_directory.glob("*")):
        #only process tif files
        if mask_path.suffix.lower() not in (".tif", ".tiff"):
            continue

        id = normalize_samples(mask_path.name)
        if id is None:
            continue

        sample = get_sample(id) #groups with same id files
        sample["files"]["mask"] = file_metadata(mask_path)

        #reads mask
        img = tifffile.imread(mask_path)
        values, counts = np.unique(img, return_counts=True)
        #number of nonzero pixels
        nonzero_pixels = int(np.count_nonzero(img))

        #mask metadata - used AI for what metadata to extract from mask
        sample["mask"] = {
            "shape": list(img.shape),
            "dtype": str(img.dtype),
            "unique_values": [float(v) for v in values],
            "unique_value_counts": {
                str(v): int(c)
                for v, c in zip(values, counts)
            },
            "total_pixels": int(img.size),
            "nonzero_pixels": nonzero_pixels,
            "nonzero_percentage": round(
                100 * nonzero_pixels / img.size,
                2
            ) if img.size else None,
            "is_binary": bool(len(values) <= 2),
            "native_alignment_verified": False
        }

        #in eda, we discovered that 2 masks use {0, 255} instead of {0, 1}
        #need to flag
        if set(values.tolist()) == {0, 255}:
            sample["quality_flags"].append(
                "mask_uses_0_255_encoding"
            )
        
        #checking mask dimensions against ROI coords
        if "roi" in sample and img.ndim == 2:
            roi_height = int(sample["roi"]["height_px"])
            roi_width = int(sample["roi"]["width_px"])

            #are they the same
            sample["mask"]["roi_dimension_match"] = (
                img.shape == (roi_height, roi_width)
            )

            #if not, quality flag
            if not sample["mask"]["roi_dimension_match"]:
                sample["quality_flags"].append(
                    "mask_roi_dimension_mismatch"
                )


    # 4. inventory native microscopy images
    image_directory = root / "Images"

    for image_path in sorted(image_directory.glob("*.lif")):
        id = normalize_samples(image_path.name)
        if id is None:
            continue
        
        #adding to 'samples' record
        sample = get_sample(id)
        sample["files"]["microscopy_image"] = (file_metadata(image_path))

        sample["image"] = {
            "format": "LIF",
            "native_file_present": True,
            "channels_extracted": False,
            "dimensions_extracted": False
        }

    # 5. importing validation results from 
    repo_root = root.resolve().parents[1]

    validation_path = (repo_root / "Person2_ROI_Orientation" / "data" / "processed" / "roi_validation.csv")

    if validation_path.exists():
        validation_df = pd.read_csv(validation_path)

        for _, row in validation_df.iterrows():
            id = str(row["sample_id"])
            sample = get_sample(id)

            sample["included_in_study"] = bool(row["included_in_study"])

            #using roi identified in eda/preprocessing for val
            sample["roi_validation"] = {
                "valid_preliminary": bool(row["roi_valid"]),
                "issue": str(row["validation_issue"]),
                "status": str(row["transform_validation_status"])
            }

            if not sample["roi_validation"]["valid_preliminary"]:
                sample["quality_flags"].append("roi_preliminary_validation_failed")

    # 6. finalized sample relationships across files
    for sample in samples.values():
        files = sample["files"]

        #checking each sample accessed each respective file
        sample["relationships"] = {
            "has_roi": "roi" in files,
            "has_orientation": "orientation" in files,
            "has_mask": "mask" in files,
            "has_native_image": ("microscopy_image" in files)
        }

    #final output
    #counts - how many sample records have a ____
    return {
        "dataset": "ventricular_tissue_imaging",
        "source_path": root.as_posix(),
        "modality": "microscopy_imaging",
        "sample_count": len(samples),
        "roi_count": sum(
            "roi" in s["files"]
            for s in samples.values()
        ),
        "orientation_count": sum(
            "orientation" in s["files"]
            for s in samples.values()
        ),
        "mask_count": sum(
            "mask" in s["files"]
            for s in samples.values()
        ),
        "native_image_count": sum(
            "microscopy_image" in s["files"]
            for s in samples.values()
        ),
        "samples": dict(sorted(samples.items()))
    }


def extract_metadata(path):
    #to select the right metadata extractor as per the data input type
    path = Path(path)

    if path.is_file() and path.suffix.lower() == ".csv":
        return extract_metadata_csv(str(path))

    if path.is_dir():
        return extract_metadata_img(path)

    #if run into error
    raise ValueError(
        f"Unsupported dataset or missing path: {path}"
    )


        









            
            


    








