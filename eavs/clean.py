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
    Loads raw EAVS data for a given year by searching the nested raw data directory.
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
    
    # Load raw data
    try:
        df = pd.read_excel(data_path, sheet_name=0, engine='openpyxl')
    except Exception as e:
        log.error(f"Error loading {data_path}: {e}")
        return pd.DataFrame()

    # Standardize column names
    fips_col = next((col for col in df.columns if 'FIPS' in str(col).upper()), None)
    if fips_col:
        df = df.rename(columns={fips_col: 'fips_code'})
    else:
        log.error(f"FIPS code column not found in {year} data.")
        return pd.DataFrame()

    # Add year column
    df['year'] = year

    # --- FIX: Normalize FIPS codes ---
    # Convert to string, pad with leading zeros if needed, and truncate 10-digit codes to first 5 digits
    df['fips_code'] = df['fips_code'].astype(str).str.zfill(5).str[:5]
    # --- END FIX ---
    
    # Select only the columns needed for cleaning (fips_code, year, and A-columns)
    cols_to_keep = ['fips_code', 'year'] + [col for col in df.columns if re.match(r'^[A-Z]\d+$', str(col))]
    df = df.filter(items=cols_to_keep, axis=1)

    # Convert all EAVS numerical columns (A1, B1, etc.) to Int64Dtype (allows NaN)
    for col in df.columns:
        if col not in ['fips_code', 'year']:
            try:
                df[col] = pd.to_numeric(df[col], errors='coerce').astype(pd.Int64Dtype())
            except Exception:
                log.warning(f"Could not convert column {col} to integer type.")
                df[col] = pd.NA

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
    years = [2022, 2024]  
    
    cleaned_dataframes = []
    for year in years:
        # Dynamically load configuration for the year
        year_config = load_config(year) 
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

