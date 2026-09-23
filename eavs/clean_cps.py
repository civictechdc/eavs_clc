import re

import pandas as pd
from loguru import logger

from eavs.config import CPS_DATA_DIR, PROCESSED_DATA_DIR

OUTPUT_PATH = PROCESSED_DATA_DIR / "cps_voting_clean.parquet"

# Column indices in the raw xlsx (0-indexed, consistent across all years)
_STATE = 0
_DEMO = 1
_PCT_REG_CIT = 7
_MOE_REG_CIT = 8
_PCT_VOT_CIT = 12
_MOE_VOT_CIT = 13

# Per-year file config: filename and number of header rows to skip
_FILE_CFG = {
    2020: {"filename": "table04b_2020.xlsx", "skip": 6},
    2022: {"filename": "table04b_2022.xlsx", "skip": 5},
    2024: {"filename": "table04b_2024.xlsx", "skip": 5},
}

# Map raw demographic labels → canonical output label
# Hispanic label changed between 2020 and 2022/2024; both map to "Hispanic"
_DEMO_MAP = {
    "Total":                    "Total",
    "White non-Hispanic alone": "White non-Hispanic",
    "Black alone":              "Black",
    "Hispanic (of any race)":   "Hispanic",
    "Hispanic (any race)":      "Hispanic",
    "Asian alone":              "Asian",
}


def _normalize_state(raw) -> str | None:
    if pd.isna(raw):
        return None
    s = str(raw).strip()
    if s.upper() in ("US", "UNITED STATES"):
        return "United States"
    # Title-case then lowercase small connectors
    return re.sub(r"\b(Of|And)\b", lambda m: m.group().lower(), s.title())


def _parse_one(year: int, cfg: dict) -> pd.DataFrame:
    path = CPS_DATA_DIR / cfg["filename"]
    if not path.exists():
        logger.error(f"CPS file not found: {path}")
        return pd.DataFrame()

    xl = pd.ExcelFile(path)
    df = xl.parse(xl.sheet_names[0], header=None)

    # Drop header/metadata rows
    df = df.iloc[cfg["skip"]:].reset_index(drop=True)

    # Forward-fill state column (2020 only has state on the first row of each group)
    df[_STATE] = df[_STATE].ffill()

    # Keep only target demographic groups
    df = df[df[_DEMO].isin(_DEMO_MAP)].copy()

    result = pd.DataFrame({
        "state":          df[_STATE].apply(_normalize_state),
        "demo_group":     df[_DEMO].map(_DEMO_MAP),
        "pct_registered": pd.to_numeric(df[_PCT_REG_CIT], errors="coerce") / 100,
        "moe_registered": pd.to_numeric(df[_MOE_REG_CIT], errors="coerce") / 100,
        "pct_voted":      pd.to_numeric(df[_PCT_VOT_CIT], errors="coerce") / 100,
        "moe_voted":      pd.to_numeric(df[_MOE_VOT_CIT], errors="coerce") / 100,
        "year":           year,
    })

    result["unreliable"] = (result["moe_registered"] > 0.10) | (result["moe_voted"] > 0.10)

    logger.info(f"Parsed {year}: {len(result)} rows")
    return result


def clean_cps() -> pd.DataFrame:
    frames = []
    for year, cfg in _FILE_CFG.items():
        df = _parse_one(year, cfg)
        if not df.empty:
            frames.append(df)

    if not frames:
        logger.error("No CPS data parsed.")
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    logger.info(f"Combined: {len(combined)} rows across years {sorted(combined['year'].unique())}")
    return combined


def main():
    logger.info("Starting CPS voting clean")
    df = clean_cps()
    if df.empty:
        logger.warning("No output produced — skipping write.")
        return

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUTPUT_PATH, index=False)
    logger.info(f"Saved: {OUTPUT_PATH}  ({OUTPUT_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
