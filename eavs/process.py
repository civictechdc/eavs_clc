from pathlib import Path

import pandas as pd
import pyarrow as pa
from pandera.io import from_yaml
from yaml import safe_load

from eavs.config import RAW_DATA_DIR

COLUMN_METADATA_PATH = Path(__file__).parent / "assets" / "columns.yaml"


def load_column_metadata():
    with COLUMN_METADATA_PATH.open("r") as f:
        data = safe_load(f)

    return {(dataset["year"], dataset["version"]): dataset["columns"] for dataset in data}


def process_2022():
    metadata = load_column_metadata()[(2022, "1.1")]
    # Rename columns
    dtypes = {col["raw_name"]: f"{col["dtype"]}[pyarrow]" for col in metadata}

    mapping = {col["raw_name"]: col["name"] for col in metadata}

    df = pd.read_excel(
        RAW_DATA_DIR / "2022" / "1.1" / "2022_EAVS_for_Public_Release_V1.1.xlsx",
        engine="calamine",
        dtype_backend="pyarrow",
        dtype=dtypes,
        na_values=["Does not apply", "Data not available", "Valid skip"]
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
    process_df = process_2022()

    schema = from_yaml(Path(__file__).parent / "assets" / "processed_schema.yaml")
    schema.validate(process_df)


if __name__ == "__main__":
    main()
