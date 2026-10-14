from pathlib import Path

from loguru import logger
import pandas as pd
from pandera.io import from_yaml
import pyarrow as pa
from yaml import safe_load

from eavs.config import CLEANED_DATA_DIR, RAW_DATA_DIR

COLUMN_METADATA_DIR = Path(__file__).parent / "assets" / "column_mappings"


def load_column_mapping(year: str, version: str) -> list:
    """Load column mapping for `year` at `version` from the corresponding YAML.

    Returns a list of dicts with `raw_name` and `dtype` keys.
    Raises RuntimeError if the file exists but no entry matches the requested version.
    Returns an empty list only if the file does not exist at all.
    """
    config_file = COLUMN_METADATA_DIR / f"{year}.yaml"
    if not config_file.exists():
        logger.warning(f"Mapping file not found: {config_file}")
        return []
    with config_file.open("r") as f:
        data = safe_load(f)
    if isinstance(data, dict) and "columns" in data:
        if data.get("version") == version:
            return data.get("columns", [])
    if isinstance(data, list):
        for dataset in data:
            if dataset.get("version") == version:
                return dataset.get("columns", [])
    raise RuntimeError(
        f"Mapping file {config_file} exists but contains no entry for version '{version}'. "
        "Check that the YAML has a matching `version:` key."
    )


def clean_timeseries() -> pd.DataFrame:
    """Clean the EAVS timeseries dataset (version 2.0, covering 2004–2024).

    Reads column mappings from `eavs/assets/column_mappings/timeseries.yaml`,
    checks that all expected EAC column names are present in the raw file, and
    writes `data/cleaned/timeseries.parquet`. Columns are kept as EAC stem names;
    no renaming is done.

    Pandera schema validation runs if `eavs/assets/timeseries_process_schema.yaml`
    exists (currently absent); failures are logged but do not abort the write.
    """
    year = "timeseries"
    version = "2.0"

    metadata = load_column_mapping(year, version)
    if not metadata:
        raise RuntimeError(
            f"No column mapping entries found in timeseries.yaml for version '{version}'. "
            "The mapping file must exist and contain at least one column entry."
        )

    # Only enforce strindg dtype at read time; numeric columns are cast after loading
    # to avoid ArrowInvalid truncation errors on older survey-year rows that stored
    # fractional aggregates.
    string_raw_names = {
        col["raw_name"]
        for col in metadata
        if col.get("dtype", "").startswith("str")
    }
    read_dtypes = {raw: "string[pyarrow]" for raw in string_raw_names}

    # Find raw file — exactly one spreadsheet must be present in the version folder.
    raw_ts_dir = RAW_DATA_DIR / "timeseries" / version
    # Exclude _Appended_Labels variants — same data, different column-naming convention,
    # not used by this pipeline.
    files = (
        [
            f for f in raw_ts_dir.glob("*")
            if f.suffix.lower() in (".csv", ".xls", ".xlsx")
            and "_Appended_Labels" not in f.name
        ]
        if raw_ts_dir.exists()
        else []
    )
    if not files:
        raise RuntimeError(f"No timeseries raw file found in {raw_ts_dir}")
    if len(files) > 1:
        raise RuntimeError(
            f"Multiple raw files found in {raw_ts_dir}: {[f.name for f in files]}. "
            "Remove all but the canonical file to avoid silently loading the wrong one."
        )

    data_path = files[0]
    logger.info(f"Loading timeseries raw file: {data_path}")

    try:
        if data_path.suffix.lower() == ".csv":
            df = pd.read_csv(data_path, dtype=read_dtypes or None)
        else:
            df = pd.read_excel(
                data_path,
                engine="calamine",
                dtype_backend="pyarrow",
                dtype=read_dtypes or None,
                na_values=["Does not apply", "Data not available", "Valid skip"],
            )
    except Exception as e:
        raise RuntimeError(f"Failed to load timeseries file {data_path}") from e

    # Post-load type enforcement for string columns (Arrow compatibility fix).
    for raw_col in string_raw_names:
        if raw_col in df.columns:
            try:
                df[raw_col] = df[raw_col].astype(pd.ArrowDtype(pa.string()))
            except Exception as e:
                logger.warning(f"Arrow string cast failed for column '{raw_col}': {e}")

    # Load-time check: every column listed in the YAML must exist in the file.
    all_raw_names = [col["raw_name"] for col in metadata]
    missing = [raw for raw in all_raw_names if raw not in df.columns]
    if missing:
        raise RuntimeError(
            f"{len(missing)} expected column(s) are absent from the raw file: "
            f"{sorted(missing)}. "
            "Check that the timeseries.yaml raw_name values match the actual file columns."
        )

    # Normalize FIPS to 5-digit string.
    if "FIPSCode" in df.columns:
        try:
            df["FIPSCode"] = df["FIPSCode"].astype(str).str.zfill(5).str[:5]
        except Exception as e:
            logger.warning(f"FIPS normalization failed: {e}")

    # Normalize year to nullable int.
    if "Year" in df.columns:
        try:
            df["Year"] = pd.to_numeric(df["Year"], errors="coerce").astype(pd.Int64Dtype())
        except Exception as e:
            logger.warning(f"Year normalization failed: {e}")

    # Pandera schema validation — failures are logged, write still proceeds.
    schema_path = Path(__file__).parent / "assets" / "timeseries_process_schema.yaml"
    if schema_path.exists():
        try:
            ts_schema = from_yaml(schema_path)
            ts_schema.validate(df)
            logger.info("Timeseries schema validation passed.")
        except Exception as e:
            logger.error(f"Timeseries schema validation failed (data will still be written): {e}")

    CLEANED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CLEANED_DATA_DIR / "timeseries.parquet"
    df.to_parquet(out_path, index=False)
    logger.info(f"Saved timeseries parquet: {out_path}")

    return df


def main():
    logger.info("Starting timeseries cleaning")
    df = clean_timeseries()
    logger.info(f"Timeseries cleaned: {len(df)} rows, {len(df.columns)} cols")


if __name__ == "__main__":
    main()
