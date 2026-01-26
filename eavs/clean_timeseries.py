from pathlib import Path

from loguru import logger
import pandas as pd
from pandera.io import from_yaml
import pyarrow as pa
from yaml import safe_load

from eavs.config import CLEANED_DATA_DIR, RAW_DATA_DIR

COLUMN_METADATA_DIR = Path(__file__).parent / "assets" / "column_mappings"


def load_column_mapping(year: str, version: str) -> list:
    """Load a specific year mapping file. If not found, return an empty list.

    Note: We intentionally do not fail if a timeseries mapping file is missing. The
    timeseries dataset uses short codes (A1a, A3a, FIPSCode, Year, etc.) and will
    fall back to aggregated mappings from other year files when needed.
    """
    config_file = COLUMN_METADATA_DIR / f"{year}.yaml"
    if not config_file.exists():
        logger.warning(f"Timeseries mapping file not found: {config_file}")
        return []
    with config_file.open("r") as f:
        data = safe_load(f)
    # Support both list and dict that contains 'columns'
    if isinstance(data, dict) and "columns" in data:
        for dataset in [data]:
            if dataset.get("version") == version:
                return dataset.get("columns", [])

    if isinstance(data, list):
        for dataset in data:
            if dataset.get("version") == version:
                return dataset.get("columns", [])
    return []


def load_all_mappings() -> list:
    """Aggregate mappings from all YAML files in `COLUMN_METADATA_DIR`.

    This allows a timeseries processing flow to use mappings defined for other
    yearly datasets (like 2024.yaml) when a dedicated timeseries mapping is not
    provided. The result is a de-duplicated list of column metadata dicts.
    """
    all_columns = []
    for cfg in COLUMN_METADATA_DIR.glob("*.yaml"):
        try:
            with cfg.open("r") as f:
                data = safe_load(f)
        except Exception:
            continue
        if not data:
            continue
        if isinstance(data, dict) and "columns" in data:
            columns = data.get("columns", [])
        elif isinstance(data, list):
            columns = data
        else:
            columns = []
        for c in columns:
            if isinstance(c, dict) and "raw_name" in c and "name" in c:
                all_columns.append(c)

    # De-dup keeping first occurrence
    seen = set()
    unique = []
    for c in all_columns:
        key = c.get("raw_name")
        if key and key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def clean_timeseries() -> pd.DataFrame:
    """Cleans the EAVS timeseries dataset.

    Reads column mappings from `eavs/assets/column_mappings/timeseries.yaml`,
    applies dtypes, renames short raw codes into full names, validates using
    `timeseries_process_schema.yaml` (via pandera.from_yaml), and writes a
    Parquet file to `data/cleaned/timeseries.parquet`.
    """
    # Constants
    year = "timeseries"
    version = "1.0"

    # Load mapping: prefer a dedicated timeseries.yaml, otherwise aggregate from other mappings
    metadata = load_column_mapping(year, version)
    if not metadata:
        logger.warning("No dedicated timeseries mapping found; attempting to use aggregated mappings from year YAMLs.")
        metadata = load_all_mappings()

    # Build dtype mapping and renaming map if metadata present
    dtypes = {col["raw_name"]: f"{col['dtype']}[pyarrow]" for col in metadata} if metadata else {}
    mapping = {col["raw_name"]: col["name"] for col in metadata} if metadata else {}

    # Ensure critical renames exist for schema compatibility
    # Add common defaults if they are not present in the mapping
    defaults = {
        "FIPSCode": "fips_code",
        "Year": "year",
        "Jurisdiction_Name": "jurisdiction_name",
        "State_Full": "state",
        "State_Abbr": "state_abbr",
    }
    for raw, canonical in defaults.items():
        if raw not in mapping:
            mapping[raw] = canonical
            # If no dtype already present, set a conservative type
            if raw not in dtypes:
                if canonical == "year":
                    dtypes[raw] = "int64[pyarrow]"
                else:
                    dtypes[raw] = "string[pyarrow]"

    # Find raw file
    raw_ts_dir = RAW_DATA_DIR / "timeseries" / version
    files = [f for f in raw_ts_dir.glob("*") if f.suffix.lower() in (".csv", ".xls", ".xlsx")] if raw_ts_dir.exists() else []
    if not files:
        logger.error(f"No timeseries raw files found in {raw_ts_dir}")
        return pd.DataFrame()

    data_path = files[0]
    logger.info(f"Loading timeseries raw file: {data_path}")

    try:
        if data_path.suffix.lower() == ".csv":
            # CSV read falls back to pandas inferring types if no dtypes provided
            df = pd.read_csv(data_path, dtype=dtypes or None)
        else:
            df = pd.read_excel(
                data_path,
                engine="calamine",
                dtype_backend="pyarrow",
                dtype=dtypes or None,
                na_values=["Does not apply", "Data not available", "Valid skip"],
            )
    except Exception as e:
        logger.error(f"Error loading timeseries file {data_path}: {e}")
        return pd.DataFrame()

    # Temporary Arrow string dtype fix for Pandas bug
    for col in dtypes:
        if dtypes[col] == "string[pyarrow]" and col in df.columns:
            try:
                df[col] = df[col].astype(pd.ArrowDtype(pa.string()))
            except Exception:
                # Best-effort fallback; ignore if not possible
                pass

    # Apply renaming if mapping present
    if mapping:
        # Build a case-insensitive mapping to handle small variations in raw column names
        df_columns_lower = {str(c).lower().strip(): c for c in df.columns}
        rename_candidates = {}
        for raw, canon in mapping.items():
            # exact match first
            if raw in df.columns:
                rename_candidates[raw] = canon
            else:
                normalized_raw = raw.lower().strip()
                match = df_columns_lower.get(normalized_raw)
                if match:
                    rename_candidates[match] = canon

        if not rename_candidates:
            logger.warning("Mapping found but none of the mapping columns matched raw file column names.")
        else:
            logger.debug(f"Applying column rename mapping: {rename_candidates}")
            # Apply the rename map and keep all other columns unchanged
            df = df.rename(columns=rename_candidates)

    # Post-rename normalization for critical columns
    # Normalize FIPS codes: ensure 5-digit string with leading zeros if necessary
    if "fips_code" in df.columns:
        try:
            df["fips_code"] = df["fips_code"].astype(str).str.zfill(5).str[:5]
        except Exception:
            # best-effort; continue if normalization fails
            pass

    # Normalize year column to ints
    if "year" in df.columns:
        try:
            df["year"] = pd.to_numeric(df["year"], errors="coerce").astype(pd.Int64Dtype())
        except Exception:
            df["year"] = pd.NA

    # Validate against timeseries schema if present
    schema_path = Path(__file__).parent / "assets" / "timeseries_process_schema.yaml"
    if schema_path.exists():
        try:
            ts_schema = from_yaml(schema_path)
            ts_schema.validate(df)
            logger.info("Timeseries validation successful.")
        except Exception as e:
            logger.error(f"Timeseries schema validation failed: {e}")
            # Continue: write the cleaned dataframe even if validation fails

    # Ensure output dir exists
    CLEANED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CLEANED_DATA_DIR / "timeseries.parquet"
    try:
        df.to_parquet(out_path, index=False)
        logger.info(f"Saved timeseries parquet: {out_path}")
    except Exception as e:
        logger.error(f"Failed to save timeseries parquet: {e}")

    return df


def main():
    logger.info("Starting timeseries cleaning")
    df = clean_timeseries()
    if df.empty:
        logger.warning("No timeseries data was cleaned.")
    else:
        logger.info(f"Timeseries cleaned: {len(df)} rows, {len(df.columns)} cols")


if __name__ == "__main__":
    main()
