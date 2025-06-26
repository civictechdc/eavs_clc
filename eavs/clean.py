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


@register_cleaning_function(2022)
def clean_2022():
    metadata = load_column_mapping(2022, "1.1")
    # Rename columns
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
        if dtypes[col] == "string[pyarrow]":
            df[col] = df[col].astype(pd.ArrowDtype(pa.string()))
    ##

    df_out = df.loc[:, mapping.keys()].rename(columns=mapping)
    return df_out


def main():
    schema = from_yaml(Path(__file__).parent / "assets" / "processed_schema.yaml")

    out = {}
    for year, fn in PROCESSING_FNS.items():
        logger.info(f"Cleaning data for {year}")
        cleaned_df = fn()
        schema.validate(cleaned_df)

        # Write out intermediate
        interim_output_path_base = CLEANED_DATA_DIR / f"{year}"
        cleaned_df.to_csv(interim_output_path_base.with_suffix(".csv"), index=False)
        cleaned_df.to_parquet(interim_output_path_base.with_suffix(".parquet"), index=False)
        out[year] = cleaned_df

    concat_df = pd.concat(out, keys=out.keys()).droplevel(1)
    combined_output_path_base = CLEANED_DATA_DIR / "combined"
    concat_df.to_csv(combined_output_path_base.with_suffix(".csv"), index=False)
    concat_df.to_parquet(combined_output_path_base.with_suffix(".parquet"), index=False)


if __name__ == "__main__":
    main()
