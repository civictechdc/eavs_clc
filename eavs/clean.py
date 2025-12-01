import yaml
import re
from pathlib import Path
from loguru import logger as log
from typing import Dict, Any, List

import pandas as pd
import pandera as pa
from pandera.typing import DataFrame, Series

# -----------------
# 1. Configuration
# -----------------
PROJ_ROOT = Path(__file__).resolve().parent.parent

CONFIG_PATH = PROJ_ROOT / 'eavs' / 'assets' / 'column_mappings'

def load_config(year: int) -> Dict[str, Any]:
    """
    Dynamically loads the year-specific config file (e.g., 2022.yaml).
    If the file is not found, it logs a warning and returns a safe empty dictionary.
    """
    config_file = CONFIG_PATH / f'{year}.yaml'
    if not config_file.exists():
        log.warning(f"Config file not found for year {year}: {config_file}. Cleaning will proceed without specific variable handling.")
        return {} 
    
    try:
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        log.error(f"Error loading config file {config_file}: {e}")
        return {}

# -----------------
# 2. Schema Definition
# -----------------

class CleanedEAVSSchema(pa.DataFrameModel):
    # FIPS codes must be 5-digit strings
    fips_code: Series[str] = pa.Field(str_matches=r'^\d{5}$')
    
    # Year of the EAVS data (e.g., 2022)
    year: Series[int] = pa.Field(ge=2000, le=2030)
    
    class Config:
        # Set strict=False to allow all EAVS variable columns (like D8)
        # to exist in the DataFrame without being explicitly listed in the Schema.
        strict = False 
        coerce = True
        
schema = CleanedEAVSSchema

# -----------------
# 3. Cleaning Functions
# -----------------

def clean_data(year: int, config: Dict[str, Any]) -> pd.DataFrame:
    """
    Loads raw EAVS data for a given year, applies renaming and type conversion 
    based on the loaded configuration, and ensures robust column selection.
    """
    # Look inside the raw/{year} folder
    raw_data_dir = PROJ_ROOT / 'data' / 'raw' / str(year)
    
    # Use rglob to recursively search the version folders for any Excel file
    excel_files = list(raw_data_dir.rglob('*.xls*')) 
    
    if not excel_files:
        log.warning(f"Raw EAVS file not found for year {year} within {raw_data_dir}")
        return pd.DataFrame()
        
    # Assume the first found file is the correct one
    data_path = excel_files[0]

    log.info(f"Cleaning data for {year} using file: {data_path.name}")

    # Prepare column renaming map from config (list of dicts)
    # The config is a list of dictionaries, where each dict has 'raw_name' and 'name'
    mapping = {col['raw_name']: col['name'] for col in config}
    
    # Prepare dtypes for efficient loading (optional, but good practice)
    dtypes = {col['raw_name']: str for col in config} 

    # Load raw data
    try:
        # We only load the columns specified in the config for speed and memory efficiency
        df = pd.read_excel(data_path, sheet_name=0, engine='openpyxl', dtype=dtypes)
    except Exception as e:
        log.error(f"Error loading {data_path}: {e}")
        return pd.DataFrame()

    # Standardize column names
    fips_col = next((col for col in df.columns if 'FIPS' in str(col).upper()), None)
    if fips_col:
        df = df.rename(columns={fips_col: 'fips_code'})
    else:
        log.error(f"FIPS code column not found in {year} data.")
        # If FIPS is missing, we can't proceed with cleaning
        return pd.DataFrame() 

    # Add year column
    df['year'] = year

    # --- FIX: Normalize FIPS codes ---
    # Convert to string, pad with leading zeros if needed, and truncate 10-digit codes to first 5 digits
    df['fips_code'] = df['fips_code'].astype(str).str.zfill(5).str[:5]
    # --- END FIX ---

    # --- START INTEGRATION: Apply YAML renaming & Robust Filtering (KeyError Fix) ---
    
    # 1. Determine which columns specified in the mapping actually exist in the DataFrame
    # This prevents the KeyError when selecting a non-existent column.
    mapping_keys = mapping.keys()
    existing_keys = [k for k in mapping_keys if k in df.columns]
    
    # We must also ensure we keep the 'fips_code' and 'year' columns
    cols_to_select = existing_keys + ['fips_code', 'year']
    
    # 2. Filter the DataFrame to keep only the necessary columns (and FIPS/year)
    df = df.filter(items=cols_to_select, axis=1)

    # 3. Apply the renaming *only* to the existing keys
    # We create a mapping subset for renaming based on the existing keys
    renaming_map = {k: mapping[k] for k in existing_keys}
    df = df.rename(columns=renaming_map)
    
    # 4. Convert numerical columns to Int64Dtype (allows NaN)
    # EAVS variables are typically uppercase letter followed by numbers (like A1, B1, etc.)
    for col in df.columns:
        # Check if the renamed column matches the EAVS variable pattern (e.g., 'A1', 'C8')
        if re.match(r'^[A-Z]\d+$', str(col)):
            try:
                df[col] = pd.to_numeric(df[col], errors='coerce').astype(pd.Int64Dtype())
            except Exception:
                log.warning(f"Could not convert column {col} to integer type.")
                df[col] = pd.NA

    # --- END INTEGRATION ---

    return df

def combine_data(cleaned_dfs: List[pd.DataFrame]) -> pd.DataFrame:
    """Combines cleaned dataframes from multiple years."""
    log.info(f"Combining {len(cleaned_dfs)} years of cleaned data.")
    combined_df = pd.concat(cleaned_dfs, ignore_index=True)
    return combined_df

# -----------------
# 4. Main Execution
# -----------------

def main():
    """Main function to clean and combine EAVS data."""
    # These years are now pulled from the combined history of the first two rebases
    years = [2022, 2024] 
    
    cleaned_dataframes = []
    for year in years:
        # Dynamically load configuration for the year
        year_config = load_config(year) 
        
        # Check if config is loaded and non-empty
        if not year_config:
            log.warning(f"Skipping cleaning for year {year} due to missing or empty config.")
            continue

        df = clean_data(year, year_config)
        if not df.empty:
            cleaned_dataframes.append(df)
            
    if not cleaned_dataframes:
        log.error("No valid dataframes were cleaned. Exiting.")
        return

    combined_df = combine_data(cleaned_dataframes)
    cleaned_df = combined_df.copy()

    # --- PANDERA FIX: ensure fips_code is string before schema validation ---
    cleaned_df['fips_code'] = cleaned_df['fips_code'].astype(str)
    # --- END FIX ---
    
    try:
        log.info(f"Validating combined data with {len(cleaned_df)} rows...")
        schema.validate(cleaned_df)
        log.success("Data validation successful!")
        
        # Save the cleaned and validated file
        output_path = PROJ_ROOT / 'data' / 'eavs_combined_cleaned.parquet'
        cleaned_df.to_parquet(output_path, index=False)
        log.info(f"Cleaned data saved to {output_path}")

    except pa.errors.SchemaError as e:
        log.error(f"Data validation failed: {e}")
        return
        
    log.info("Finished EAVS Cleaning Pipeline.")

if __name__ == '__main__':
    main()