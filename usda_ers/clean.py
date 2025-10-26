from pathlib import Path

from loguru import logger
import pandas as pd
from pandera.io import from_yaml
import pyarrow as pa
from yaml import safe_load

from usda_ers.config import (
    RAW_DATA_DIR, 
    PROC_DATA_DIR, 
    PROJ_CLEANED_DATA_DIR,
    PROJ_ENRICHED_DATA_DIR
)

COLUMN_METADATA_DIR = Path(__file__).parent / "assets" / "column_mappings"

def load_column_mapping(measure: str, year: int, version: str) -> dict:
    with (COLUMN_METADATA_DIR / measure / f"{year}.yaml").open("r") as f:
        data = safe_load(f)
    for dataset in data:
        if dataset["version"] == version:
            return dataset["columns"]

def find_file(measure: str, year: int, version: str, ext: str) -> Path:    
    data_dir = RAW_DATA_DIR / measure / str(year) / version
    data_file = list(data_dir.glob(ext))
    assert len(data_file) == 1, (
        f'Expected only 1 file with extension "{ext}" in "{data_dir}" '
        f'but found:\n{data_file}'
    )
    data_file = data_file[0]
    return data_file
    
PROCESSING_FNS: dict[(str,int), callable] = {}


def register_cleaning_function(measure, year):
    def decorator(func):
        PROCESSING_FNS[(measure, year)] = func
        return func

    return decorator


@register_cleaning_function("RUCC", 2023)
def clean_rucc_2023():
    # Load metadata
    data_measure = 'RUCC'
    data_year = 2023
    data_ver = "2024-01-22"
    data_ext = '*.xls*' 
    
    metadata = load_column_mapping(data_measure, data_year, data_ver)    
    
    # Preprocess metadata columns
    dtypes = {col["raw_name"]: f"{col['dtype']}[pyarrow]" for col in metadata}
    mapping = {col["raw_name"]: col["name"] for col in metadata}

    # Load file and rename columns    
    data_file = find_file(data_measure, data_year, data_ver, data_ext)
    df = pd.read_excel(
        data_file,
        engine="calamine",
        dtype_backend="pyarrow",
        dtype=dtypes,
        na_values=["Does not apply", "Data not available", "Valid skip"],
    )
    
    for col in dtypes:
        if dtypes[col] == "string[pyarrow]":
            df[col] = df[col].astype(pd.ArrowDtype(pa.string()))

    df = df.loc[:, mapping.keys()].rename(columns=mapping)

    # Proces specific columbs
    df['is_in_metro_2023'] = df['rural_urban_continuum_desc_2023'].str.startswith('Metro')
    df['jurisdiction_name'] = df['jurisdiction_name'].str.strip().str.upper()
    
    return df


@register_cleaning_function("UIC", 2024)
def clean_uic_2024():
    # Load metadata
    data_measure = 'UIC'
    data_year = 2024
    data_ver = "2024-12-13"
    data_ext = '*.xls*' 
    
    metadata = load_column_mapping(data_measure, data_year, data_ver)    
    
    # Preprocess metadata columns
    dtypes = {col["raw_name"]: f"{col['dtype']}[pyarrow]" for col in metadata}
    mapping = {col["raw_name"]: col["name"] for col in metadata}

    # Load file and rename columns    
    data_file = find_file(data_measure, data_year, data_ver, data_ext)
    df = pd.read_excel(
        data_file,
        engine="calamine",
        dtype_backend="pyarrow",
        dtype=dtypes,
        na_values=["Does not apply", "Data not available", "Valid skip"],
    )
    
    for col in dtypes:
        if dtypes[col] == "string[pyarrow]":
            df[col] = df[col].astype(pd.ArrowDtype(pa.string()))

    df = df.loc[:, mapping.keys()].rename(columns=mapping)

    # Proces specific columbs
    df['jurisdiction_name'] = df['jurisdiction_name'].str.strip().str.upper()
    
    return df


def merge_ERS_to_EAVS(ers_df: pd.DataFrame, eavs_df: pd.DataFrame):    
    # Find out ID data frames for each source based on jurisdiction and state abbr
    # Note: this is because of mismatch of the type of FIPS code used
    #       e.g. in EAVS ~ varying length (2, 5, 10) & some 0-padded, while ERS const=5 number      
    eavs_idf = (
        eavs_df.reset_index()
        .filter(['fips_code','jurisdiction_name','state_abbr'])
        .drop_duplicates(ignore_index=True)
    )

    ers_idf = (
        ers_df.filter(['ers_fips_code','jurisdiction_name','state_abbr'])
        .drop_duplicates(ignore_index=True)    
    )

    # Merge ID dataframes to find/check common counties
    merged_idf = eavs_idf.merge(ers_idf, how='left')

    assert (
        merged_idf.query('not ers_fips_code.isna()')
        ['fips_code'].str.endswith("00000").all()
    ), 'Expected the FIPS codes from EVAS of common counties to end with "00000"'

    merged_idf = (
        merged_idf
        .query('not ers_fips_code.isna()')
        .query('fips_code.str.replace(r"00000$","",regex=True) == ers_fips_code', engine='python')
        .reset_index(drop=True)
    )

    # Finalize ERS
    ers_df = (
        ers_df
        .merge(merged_idf,how='right')
        .drop(columns='ers_fips_code')
    )

    # Finalize EAVS
    eavs_df = (
        eavs_df
        .reset_index()
        .merge(ers_df, how='left')
        .set_index('year')
    )
    
    return eavs_df

def main():
    ers_df = None
    for (measure, year), fn in PROCESSING_FNS.items():
        logger.info(f"Cleaning {measure} data for {year}")
        cleaned_df = fn()
        
        # Write out intermediate
        interim_output_dir = PROC_DATA_DIR / measure        
        interim_output_dir.mkdir(parents=True, exist_ok=True)
        interim_output_path_base = interim_output_dir / f"{year}"
        
        cleaned_df.to_csv(interim_output_path_base.with_suffix(".csv"), index=False)
        cleaned_df.to_parquet(interim_output_path_base.with_suffix(".parquet"), index=False)

        # Save to `ers_df`
        if ers_df is None:
            ers_df = cleaned_df
        else:
            ers_df = ers_df.merge(cleaned_df, how='inner')

    # Maximize number of counties with valid values across all ERS sources 
    ers_df = ers_df.dropna(how='any')
    
    # Load combined EAVS data
    eavs_df = pd.read_parquet(PROJ_CLEANED_DATA_DIR / 'combined.parquet')
    eavs_df['jurisdiction_name'] = eavs_df['jurisdiction_name'].str.strip().str.upper()

    # Merge data
    eavs_df = merge_ERS_to_EAVS(ers_df, eavs_df)

    # Save data
    PROJ_ENRICHED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path_base = PROJ_ENRICHED_DATA_DIR / "enr_eavs"
    
    eavs_df.to_csv(out_path_base.with_suffix(".csv"), index=True)
    eavs_df.to_parquet(out_path_base.with_suffix(".parquet"), index=True)
    
if __name__ == "__main__":
    main()
