from pathlib import Path

from loguru import logger
import pandas as pd
from pandera.io import from_yaml
import pyarrow as pa
from yaml import safe_load

from eavs.config import CLEANED_DATA_DIR, RAW_DATA_DIR

COLUMN_METADATA_DIR = Path(__file__).parent / "assets" / "column_mappings"

def load_column_mapping(year: int, version: str) -> dict:
    with (COLUMN_METADATA_DIR / f"{year}.yaml").open("r") as f:
        data = safe_load(f)
    for dataset in data:
        if dataset["version"] == version:
            return dataset["columns"]



PROCESSING_FNS: dict[int, callable] = {}


def register_cleaning_function(year):
    def decorator(func):
        PROCESSING_FNS[year] = func
        return func

    return decorator

@register_cleaning_function(2024)
def clean_2024():
    metadata = load_column_mapping(2024, "1.0")

    # Prepare data types for PyArrow backend
    dtypes = {col["raw_name"]: f"{col['dtype']}[pyarrow]" for col in metadata}

    # Prepare column renaming map and read data
    mapping = {col["raw_name"]: col["name"] for col in metadata}

    df = pd.read_excel(
        RAW_DATA_DIR / "2024" / "1.0" / "2024_EAVS_for_Public_Release_V1_xlsx.xlsx",
        engine="calamine",
        dtype_backend="pyarrow",
        dtype=dtypes,
        na_values=["Does not apply", "Data not available", "Valid skip"],
    )

    ## Temporary hack for weird bug in pandas
    # https://github.com/pandas-dev/pandas/issues/61496
    for col in dtypes:
        if dtypes[col] == "string[pyarrow]":
            df[col] = df[col].astype(pd.ArrowDtype(pa.string()))
    ##

    # Select only the mapped columns and rename them
    df_out = df.loc[:, mapping.keys()].rename(columns=mapping)
    return df_out

@register_cleaning_function(2022)
def clean_2022():
    metadata = load_column_mapping(2022, "1.1")
    # Use mapping file dtypes, not forced float64
    dtypes = {col["raw_name"]: f"{col['dtype']}[pyarrow]" for col in metadata}

    mapping = {col["raw_name"]: col["name"] for col in metadata}

    df = pd.read_excel(
        RAW_DATA_DIR / "2022" / "1.1" / "2022_EAVS_for_Public_Release_V1.1.xlsx",
        engine="calamine",
        dtype_backend="pyarrow",
        dtype=dtypes,
        na_values=["Does not apply", "Data not available", "Valid skip"],
    )

    ## Temporary hack for weird bug in pandas
    # https://github.com/pandas-dev/pandas/issues/61496
    for col in dtypes:
        if dtypes[col] == "string[pyarrow]":
            df[col] = df[col].astype(pd.ArrowDtype(pa.string()))
    ##
    df_out = df.loc[:, mapping.keys()].rename(columns=mapping)
    return df_out


@register_cleaning_function(2020)
def clean_2020():
    metadata = load_column_mapping(2020, "1.2")
    # Rename columns
    dtypes = {col["raw_name"]: f"{col['dtype']}[pyarrow]" for col in metadata}
    mapping = {col["raw_name"]: col["name"] for col in metadata}
    df = pd.read_excel(
        RAW_DATA_DIR / "2020" / "1.2" / "2020_EAVS_for_Public_Release_V1.2.xlsx",
        engine="calamine",
        dtype_backend="pyarrow",
        dtype=dtypes,
        na_values=["Does not apply", "Data not available", "Valid skip"],
    )
    ## Temporary hack for weird bug in pandas
    # https://github.com/pandas-dev/pandas/issues/61496
    for col in dtypes:
        if dtypes[col] == "string[pyarrow]" and col in df.columns:  # Add existence check
            df[col] = df[col].astype(pd.ArrowDtype(pa.string()))
    ##
    
    # Filter mapping to only include columns that exist in the DataFrame
    existing_keys = [k for k in mapping.keys() if k in df.columns]
    df_out = df.loc[:, existing_keys].rename(columns=mapping)
    return df_out

def main():
    schema = from_yaml(Path(__file__).parent / "assets" / "processed_schema.yaml")
    # timeseries has its own processing schema
    timeseries_schema_path = Path(__file__).parent / "assets" / "timeseries_process_schema.yaml"
    timeseries_schema = None
    if timeseries_schema_path.exists():
        timeseries_schema = from_yaml(timeseries_schema_path)

    out = {}
    for year, fn in PROCESSING_FNS.items():
        logger.info(f"Cleaning data for {year}")
        cleaned_df = fn()
        # Validate using the timeseries-specific schema when appropriate
        if year == "timeseries" and timeseries_schema is not None:
            timeseries_schema.validate(cleaned_df)
        else:
            schema.validate(cleaned_df)

        # Write out intermediate for every dataset
        interim_output_path_base = CLEANED_DATA_DIR / f"{year}"
        cleaned_df.to_csv(interim_output_path_base.with_suffix(".csv"), index=False)
        cleaned_df.to_parquet(interim_output_path_base.with_suffix(".parquet"), index=False)

        # Only include numeric-year datasets in the combined concatenation
        # (timeseries is registered under the string key "timeseries" and
        # should be validated/written but not concatenated with year index)
        if isinstance(year, int):
            out[year] = cleaned_df
        else:
            logger.info(f"Skipping concatenation for non-year dataset '{year}'")

    if out:
        # concat using the numeric year keys only
        concat_df = pd.concat(out, keys=out.keys(), names=("year", "")).droplevel(1)
        combined_output_path_base = CLEANED_DATA_DIR / "combined"
        concat_df.to_csv(combined_output_path_base.with_suffix(".csv"), index=True)
        concat_df.to_parquet(combined_output_path_base.with_suffix(".parquet"), index=True)

if __name__ == "__main__":
    main()
