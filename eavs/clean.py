import re
import pandas as pd

from pathlib import Path

# NOTE: Assuming 'load_column_mapping' is available from your metadata module
# from eavs.assets.metadata import load_column_mapping, load_process_schema 

# --- PATH CONSTANTS (Adjust these if your project structure is different) ---
RAW_DATA_DIR = Path("./raw_data") 
CLEAN_DATA_DIR = Path("./clean_data")


# Dictionary to hold the cleaning functions, keyed by year
_CLEANING_FUNCTIONS = {}


def register_cleaning_function(year):
    """
    Decorator to register a cleaning function for a specific EAVS year.
    
    Args:
        year (int): The year of the EAVS data this function cleans.
    """
    def decorator(func):
        _CLEANING_FUNCTIONS[year] = func
        return func
    
    return decorator


def clean(year):
    """
    Executes the registered cleaning function for the specified year.
    
    Args:
        year (int): The year to clean (e.g., 2024).
    
    Returns:
        pd.DataFrame: The cleaned and standardized DataFrame.
    """
    if year not in _CLEANING_FUNCTIONS:
        raise ValueError(f"No cleaning function registered for year {year}")
    
    print(f"Starting EAVS data cleaning for {year}...")
    df = _CLEANING_FUNCTIONS[year]()
    print(f"Cleaning complete for {year}. DataFrame shape: {df.shape}")
    return df


def _robust_column_filter(df, mapping):
    """
    Robustly filters and renames columns, preventing KeyError if the raw 
    data is missing columns defined in the YAML mapping.
    
    Args:
        df (pd.DataFrame): The DataFrame read from the raw data.
        mapping (dict): Dictionary mapping raw names (keys) to clean names (values).
        
    Returns:
        pd.DataFrame: DataFrame with only the columns present in both 
                      the raw data and the mapping.
    """
    
    # 1. Identify columns that exist in BOTH the raw data and the mapping
    cols_to_keep = {
        raw_name: clean_name 
        for raw_name, clean_name in mapping.items() 
        if raw_name in df.columns
    }
    
    # 2. Select only the existing columns and rename them
    df = df[list(cols_to_keep.keys())].rename(columns=cols_to_keep)
    
    # 3. Handle missing columns for auditing
    missing_raw_cols = set(mapping.keys()) - set(df.columns)
    if missing_raw_cols:
        print(f"WARNING: The following columns were defined in the mapping but NOT found in the raw data: {missing_raw_cols}")
        
    return df


@register_cleaning_function(2020)
def clean_2020():
    # Placeholder for loading metadata
    # metadata = load_column_mapping(2020, "1.0") 
    metadata = [{"raw_name": "FIPSCode", "name": "fips_code", "dtype": "string"}] 

    dtypes = {col["raw_name"]: f"{col['dtype']}[pyarrow]" for col in metadata}
    mapping = {col["raw_name"]: col["name"] for col in metadata}
    
    # Placeholder for reading data
    # df = pd.DataFrame({"FIPSCode": ["01001"], "EXTRA_COL": [1]})
    df = pd.DataFrame({"FIPSCode": ["01001"], "EXTRA_COL": [1]})


    # --- FIX APPLIED: Robust Column Filtering ---
    df = _robust_column_filter(df, mapping)
    # --- END FIX ---

    # Add the year column for timeseries integration
    df["year"] = 2020

    return df


@register_cleaning_function(2022)
def clean_2022():
    # Placeholder for loading metadata
    # metadata = load_column_mapping(2022, "1.1")
    metadata = [{"raw_name": "FIPSCode", "name": "fips_code", "dtype": "string"}] 
    
    # Prepare data types for PyArrow backend
    dtypes = {col["raw_name"]: f"{col['dtype']}[pyarrow]" for col in metadata}
    
    # Prepare column renaming map and read data
    mapping = {col["raw_name"]: col["name"] for col in metadata}

    # Placeholder for reading data
    # df = pd.DataFrame({"FIPSCode": ["01001"], "EXTRA_COL": [1]})
    df = pd.DataFrame({"FIPSCode": ["01001"], "EXTRA_COL": [1]})


    # --- FIX APPLIED: Robust Column Filtering ---
    df = _robust_column_filter(df, mapping)
    # --- END FIX ---
    
    # Add the year column for timeseries integration
    df["year"] = 2022

    return df


@register_cleaning_function(2024)
def clean_2024():
    # Placeholder for loading metadata
    # metadata = load_column_mapping(2024, "1.0")
    metadata = [{"raw_name": "FIPSCode", "name": "fips_code", "dtype": "string"}] 

    # Prepare data types for PyArrow backend
    dtypes = {col["raw_name"]: f"{col['dtype']}[pyarrow]" for col in metadata}

    # Prepare column renaming map and read data
    mapping = {col["raw_name"]: col["name"] for col in metadata}

    # Placeholder for reading data
    # df = pd.DataFrame({"FIPSCode": ["01001"], "EXTRA_COL": [1]})
    df = pd.DataFrame({"FIPSCode": ["01001"], "EXTRA_COL": [1]})


    # --- FIX APPLIED: Robust Column Filtering ---
    df = _robust_column_filter(df, mapping)
    # --- END FIX ---

    # Add the year column for timeseries integration
    df["year"] = 2024

    return df

# Main execution (example of how to run the cleaning process)
if __name__ == "__main__":
    # Example usage:
    # df_2022 = clean(2022)
    # df_2024 = clean(2024)
    pass