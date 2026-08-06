import yaml
import re
from pathlib import Path
from loguru import logger as log
from eavs.clean_timeseries import clean_timeseries as clean_timeseries_module
from eavs.calculated_variables import add_eavs_calculations
from typing import Dict, Any, List
import pandas as pd
import pandera as pa
from pandera.typing import DataFrame, Series, String

# -----------------
# 1. Configuration
# -----------------
# PROJ_ROOT = directory above 'eavs' (ie. /home/user/eavs_clc)
PROJ_ROOT = Path(__file__).resolve().parent.parent

CONFIG_PATH = PROJ_ROOT / 'eavs' / 'assets' / 'column_mappings'

def load_config(year: int) -> List[Dict[str, Any]]:
    """
    Dynamically loads the year-specific config file (e.g., 2022.yaml).
    Handles top-level nesting (e.g., under a 'columns' key) to ensure 
    a clean list of mappings is returned.
    """
    config_file = CONFIG_PATH / f'{year}.yaml'
    if not config_file.exists():
        log.warning(f"Config file not found for year {year}: {config_file}. Cleaning will proceed without specific variable handling.")
        return [] 
    
    try:
        with open(config_file, 'r') as f:
            data = yaml.safe_load(f)
            
            # If the loaded data is a dictionary, extract the list from the 'columns' key.
            if isinstance(data, dict) and 'columns' in data:
                log.debug("Extracted column list from 'columns' key.")
                return data['columns']
                
            # If it's already a list (flat structure), return it directly.
            if isinstance(data, list):
                log.debug("Loaded config as flat list.")
                return data
                
            # Fallback for unexpected structure
            log.warning(f"Config for year {year} is in an unexpected format. Returning empty list.")
            return []
            
    except Exception as e:
        log.error(f"Error loading config file {config_file}: {e}")
        return []

def build_master_schema() -> set:
    """
    Builds a master list of all variables across all yearly YAML files.

    Example:
        2020.yaml
        2022.yaml
        2024.yaml

    are combined into one complete schema.
    """

    master_columns = set()

    yaml_files = [
        f for f in CONFIG_PATH.glob("*.yaml")
        if f.stem != "timeseries"]

    for yaml_file in yaml_files:

        try:
            with open(yaml_file, "r") as f:
                data = yaml.safe_load(f)

            if isinstance(data, dict):
                if "columns" in data:
                    columns = data["columns"]
                else:
                    columns = []
            elif isinstance(data, list):
                columns = data

            else:
                columns = []

            for column in columns:

                if "name" in column:
                    master_columns.add(
                        column["name"]
                    )

        except Exception as e:
            log.error(
                f"Could not read {yaml_file}: {e}"
            )

    log.info(
        f"Master schema created with {len(master_columns)} columns."
    )

    return master_columns

MASTER_COLUMNS = build_master_schema()

def add_missing_columns(
    df: pd.DataFrame,
    master_columns: set) -> pd.DataFrame:
    """
    Adds missing columns from the master schema.

    Missing variables are filled with pd.NA.
    """

    missing_columns = (
        master_columns
        -
        set(df.columns)
    )

    for column in missing_columns:
        df[column] = pd.NA

    if missing_columns:
        log.debug(
            f"Added {len(missing_columns)} missing columns."
        )

    return df    
# -----------------
# 2. Schema Definition
# -----------------

class CleanedEAVSSchema(pa.DataFrameModel):
    # FIPS codes must be 5-digit strings
    fips_code: Series[String] = pa.Field(str_matches=r'^\d{5}$')
    
    # Year of the EAVS data (e.g., 2022)
    year: Series[int] = pa.Field(ge=2000, le=2030)
    
    class Config:
        strict = False 
        coerce = True
        
schema = CleanedEAVSSchema

# -----------------
# 3. Cleaning Functions
# -----------------

def clean_data(year: int, config: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Loads raw EAVS data for a given year, applies renaming and type conversion 
    based on the loaded configuration, and ensures robust column selection.
    
    NOTE: This function relies on raw data being found in:
    <PROJ_ROOT>/data/raw/<year>/<filename>.xlsx
    """
    raw_data_dir = PROJ_ROOT / 'data' / 'raw' / str(year)
    excel_files = list(raw_data_dir.rglob('*.xls*')) 
    
    if not excel_files:
        log.warning(f"Raw EAVS file not found for year {year} within {raw_data_dir}")
        return pd.DataFrame()
        
    data_path = excel_files[0]
    log.info(f"Cleaning data for {year} using file: {data_path.name}")

    # Robustly create mapping, skipping malformed config entries 
    valid_configs = [
        c for c in config 
        if isinstance(c, dict) and 'raw_name' in c and 'name' in c
    ]
    if len(valid_configs) != len(config):
        log.warning(f"Skipped {len(config) - len(valid_configs)} malformed entries in the {year} column mapping file.")

    mapping = {col['raw_name']: col['name'] for col in valid_configs} 

    # Load raw data
    try:
        df = pd.read_excel(data_path, sheet_name=0, engine='openpyxl', dtype=str)
        
        
    except Exception as e:
        log.error(f"Error loading {data_path}: {e}")
        return pd.DataFrame()

     # Normalize missing values 
    df = df.replace({
         "Data not available": pd.NA,
         "Not available": pd.NA,
         "N/A": pd.NA,
         "NA": pd.NA,
         "--": pd.NA,
         "": pd.NA,
         " ": pd.NA
         })

    # Standardize FIPS column name
    fips_col = next((col for col in df.columns if 'FIPS' in str(col).upper()), None)
    if fips_col:
        df = df.rename(columns={fips_col: 'fips_code'})
    else:
        log.error(f"FIPS code column not found in {year} data.")
        return pd.DataFrame() 

    # Add year column and normalize FIPS
    df['year'] = year
    df['fips_code'] = df['fips_code'].astype(str).str.zfill(5).str[:5]

    # Apply YAML renaming & Robust Filtering
    mapping_keys = mapping.keys()
    existing_keys = [k for k in mapping_keys if k in df.columns]
    
    cols_to_select = existing_keys + ['fips_code', 'year']
    
    df = df.filter(items=cols_to_select, axis=1)

    renaming_map = {k: mapping[k] for k in existing_keys}
    df = df.rename(columns=renaming_map)

    # Build dtype map from YAML config
    yaml_dtypes = {
        c["name"]: c["dtype"]
        for c in config
        if isinstance(c, dict) and "name" in c and "dtype" in c
        }
    # Convert numerical columns to Int64Dtype (EAVS variables: A1, B2, etc.)
    exclude = {"fips_code", "year", "jurisdiction_name", "state", "state_abbr"}
    
    for col in df.columns:
        if col in exclude:
            continue

        expected_type = yaml_dtypes.get(col)

        
        if expected_type == "string":
            df[col] = df[col].astype("string")

        elif expected_type == "int64":
            cleaned = (
                df[col]
                .astype("string")
                .str.replace(",", "", regex=False)
                .str.strip()
            )
            df[col] = pd.to_numeric(cleaned, errors="coerce").astype("Int64")

        elif expected_type == "float64":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Float64")
        #fallback 
        else:
            log.warning(f"No dtype for this col{col}. Keep as string")
            df[col] = df[col].astype("string")
    return df

def combine_data(combined_dfs: List[pd.DataFrame]) -> pd.DataFrame:
    """Combines cleaned dataframes from multiple years."""
    log.info(f"Combining {len(combined_dfs)} years of cleaned data.")
    combined_df = pd.concat(combined_dfs, ignore_index=True, copy=False)
    return combined_df

def add_calculated_variables(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds EAVS calculated variables from calculated_variables.py.
    """

    log.info("Adding calculated EAVS variables...")

    try:
        df = add_missing_columns(
            df,
            MASTER_COLUMNS
            )

        df = add_eavs_calculations(df)

        log.success(
            f"Calculated variables added successfully. "
            f"New column count: {len(df.columns)}"
        )

    except KeyError as e:
        log.error(
            f"Missing input variable required for calculation: {e}"
        )
        raise

    except Exception as e:
        log.error(
            f"Error while generating calculated variables: {e}"
        )
        raise

    return df


# -----------------
# 4. New Saving Function (Added to meet requirements)
# -----------------
def save_dataframes(df: pd.DataFrame, filename: str, output_dir: Path):
    """Saves a DataFrame to Parquet, XLSX, and CSV formats."""
    log.info(f"Saving {filename} data to multiple formats in {output_dir.name}/")
    
    # Ensure output directory exists (redundant with main, but safer here)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Parquet
    parquet_path = output_dir / f"{filename}.parquet"
    df.to_parquet(parquet_path, index=False)
    log.info(f"Saved: {parquet_path.name}")

    # 2. Excel (XLSX)
    excel_path = output_dir / f"{filename}.xlsx"
    df.to_excel(excel_path, index=False)
    log.info(f"Saved: {excel_path.name}")

    # 3. CSV
    csv_path = output_dir / f"{filename}.csv"
    df.to_csv(csv_path, index=False)
    log.info(f"Saved: {csv_path.name}")


# -----------------
# 5. Main Execution (Modified to use new function)
# -----------------

def main():
    """Main function to clean and combine EAVS data, saving all formats."""
    years = [2020, 2022, 2024] 
    
    # NEW: Define output directory and ensure it exists
    output_dir = PROJ_ROOT / 'data' / 'cleaned'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    cleaned_dataframes = []
    for year in years:
        year_config = load_config(year) 
        
        if not year_config:
            log.warning(f"Skipping cleaning for year {year} due to missing or empty config.")
            continue

        df = clean_data(year, year_config)
        if not df.empty:
            df = add_calculated_variables(df)

            cleaned_dataframes.append(df)
            
            # **NEW:** Save individual year file in all formats
            save_dataframes(df, f'{year}_cleaned', output_dir)
            
    # Run timeseries cleaning via its own module (saves its own parquet)
    try:
        ts_df = clean_timeseries_module()
        if ts_df is not None and not ts_df.empty:
            log.info(f"Timeseries file processed in separate module: {len(ts_df)} rows")
        else:
            log.info("Timeseries was processed but returned empty or not processed.")
    except Exception as e:
        # Protect the pipeline from timeseries failures
        log.error(f"Error when running timeseries module: {e}")

    if not cleaned_dataframes:
        log.error("No valid dataframes were cleaned. Exiting.")
        return

    combined_df = combine_data(cleaned_dataframes)
    

    # Ensure fips_code is string before schema validation
    combined_df['fips_code'] = combined_df['fips_code'].astype(str)
    
    try:
        log.info(f"Validating combined data with {len(combined_df)} rows...")
        schema.validate(combined_df)
        log.success("Data validation successful!")
        
        # **NEW:** Save combined file in all formats
        save_dataframes(combined_df, 'eavs_combined_cleaned', output_dir)

    except pa.errors.SchemaError as e:
        log.error(f"Data validation failed: {e}")
        return
        
    log.info("Finished EAVS Cleaning Pipeline.")

if __name__ == '__main__':
    main()