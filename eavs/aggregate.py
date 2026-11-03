import re

import numpy as np
import pandas as pd
from loguru import logger

from eavs.config import CLEANED_DATA_DIR, EXTERNAL_DATA_DIR, PROCESSED_DATA_DIR

# CVAP: U.S. Census Bureau, "Citizen Voting Age Population by Race and Ethnicity",
# special tabulation from the 2020-2024 ACS 5-year estimates (State file; only the
# 'Total' row is used). Source and documentation:
# https://www.census.gov/programs-surveys/decennial-census/about/voting-rights/cvap/2020-2024-CVAP.html
# Not fetched by download.py: unzip into data/external/CVAP_2020-2024_ACS_csv_files/.

CVAP_PATH = EXTERNAL_DATA_DIR / "CVAP_2020-2024_ACS_csv_files" / "State.csv"
TIMESERIES_PATH = CLEANED_DATA_DIR / "timeseries.parquet"
OUTPUT_PATH = PROCESSED_DATA_DIR / "state_rates.parquet"

YEARS = [2020, 2022, 2024]

# Columns summed to state level before computing rates.
# Column names are EAC stem names (User Guide v2.1); EAVS item codes in comments.
# Variable definitions: EAVS Time Series User Guide v2.1.
SUM_COLS = [
    "turnout_tot",    # F1a  — total ballots cast & counted, all modes
    "regist_tot",     # A1a  — total registered (active + inactive)
    "regist_actv",    # A1b  — EAC-preferred registration denominator
    "reg_tot",        # A3a  — registration transaction denominator
    "reg_rej",        # A3f  — registration rejection numerator
    "remov_tot",      # A12a — purge numerator (all years)
    "mail_trans_tot", # C1a
    "mail_ret",       # C1b  — mail rejection denominator
    "mail_rej_tot",   # C9a  — mail rejection numerator
    "prov_tot",       # E1a  — total provisional cast
    "prov_rej",       # E1d  — use E1d not E3 sum (stable across years)
    "prov_countfull", # E1b  — fully counted provisionals
    "prov_countpart", # E1c  — partially counted provisionals
    "prov_oth",       # E1e  — other disposition (neither counted nor rejected)
]

# Known anomalous state-year-metric combinations to null after rate computation.
# See notes/timeseries_2024_update.md, section D.
_NULLIFY = [
    ("ME", 2020, "provisional_rejection_rate"),
    ("ME", 2022, "provisional_rejection_rate"),
    ("SD", 2022, "provisional_rejection_rate"),
]


def _title_fix(s: str) -> str:
    return re.sub(r"\b(Of|And)\b", lambda m: m.group().lower(), s.title())


def _safe_rate(numer: pd.Series, denom: pd.Series) -> pd.Series:
    mask = numer.notna() & denom.notna() & (denom > 0)
    return pd.Series(
        np.where(mask, numer / denom.where(denom > 0, 1), np.nan),
        index=numer.index,
    )


def load_timeseries() -> pd.DataFrame:
    if not TIMESERIES_PATH.exists():
        logger.error(f"Timeseries parquet not found: {TIMESERIES_PATH}")
        return pd.DataFrame()
    logger.info(f"Loading timeseries: {TIMESERIES_PATH}")
    return pd.read_parquet(TIMESERIES_PATH)


def load_cvap() -> pd.DataFrame:
    if not CVAP_PATH.exists():
        logger.error(f"CVAP file not found: {CVAP_PATH}")
        return pd.DataFrame()
    logger.info(f"Loading CVAP: {CVAP_PATH}")
    cvap = pd.read_csv(CVAP_PATH, encoding="latin1")
    cvap = cvap[cvap["lntitle"] == "Total"][["geoname", "cvap_est"]].copy()
    return cvap.rename(columns={"geoname": "state_join"})


def aggregate_state_rates() -> pd.DataFrame:
    ts = load_timeseries()
    if ts.empty:
        return pd.DataFrame()

    cvap = load_cvap()
    if cvap.empty:
        return pd.DataFrame()

    ts = ts[ts["Year"].isin(YEARS)].copy()

    # Sentinel cleanup before aggregation: negative codes (-99, -88, -77, -66) mean missing (User Guide v2.1).
    # pd.to_numeric coerces any remaining string sentinels; .where(>= 0) nulls
    # numeric sentinels (-88, -99, etc.) that survived the cleaning pipeline.
    present = [c for c in SUM_COLS if c in ts.columns]
    for col in present:
        ts[col] = pd.to_numeric(ts[col], errors="coerce")
        ts[col] = ts[col].where(ts[col] >= 0)

    state_df = (
        ts.groupby(["State_Full", "State_Abbr", "Year"])[present]
        .sum(min_count=1)
        .reset_index()
    )

    state_df["state_join"] = state_df["State_Full"].apply(_title_fix)
    merged = state_df.merge(cvap, on="state_join", how="left").drop(columns="state_join")
    assert len(merged) == len(state_df), f"CVAP merge changed row count: {len(state_df)} → {len(merged)}"

    # Compute rates — counts first, rates after.
    merged["registration_rate"] = _safe_rate(merged["regist_tot"], merged["cvap_est"])

    # Two turnout denominators.
    # regist_tot: total registered (active + inactive) — current pipeline default.
    # regist_actv: active voters only — EAC-preferred methodology.
    # Fallback: when regist_actv is null or equals regist_tot the state does not
    # distinguish active/inactive voters; use regist_tot for both and set
    # uses_regist_tot_fallback = True.
    merged["turnout_rate"] = _safe_rate(merged["turnout_tot"], merged["regist_tot"])

    _actv = merged["regist_actv"].copy()
    _fallback = _actv.isna() | (_actv == merged["regist_tot"])
    merged["turnout_rate_regist_actv"]   = _safe_rate(merged["turnout_tot"], _actv.where(~_fallback, merged["regist_tot"]))
    merged["uses_regist_tot_fallback"] = _fallback
    merged["reg_rejection_rate"]  = _safe_rate(merged["reg_rej"],          merged["reg_tot"])
    merged["purge_rate"]          = _safe_rate(merged["remov_tot"],            merged["regist_tot"])
    merged["mail_rejection_rate"] = _safe_rate(merged["mail_rej_tot"],     merged["mail_ret"])

    # EAC Appendix D denominator: E1b+E1c+E1d+E1e (counted full + counted partial + rejected + other).
    # Old denominator was E1a (total cast), which overstates the pool and understates the rate.
    _prov_denom = (
        merged["prov_countfull"].fillna(0)
        + merged["prov_countpart"].fillna(0)
        + merged["prov_rej"].fillna(0)
        + merged["prov_oth"].fillna(0)
    )
    merged["provisional_rejection_rate"] = _safe_rate(merged["prov_rej"], _prov_denom)

    # Null out known anomalous values (see notes/timeseries_2024_update.md, section D).
    for abbr, yr, col in _NULLIFY:
        mask = (merged["State_Abbr"] == abbr) & (merged["Year"] == yr)
        merged.loc[mask, col] = np.nan

    logger.info(
        f"Aggregated {len(merged)} state-year rows "
        f"({merged['State_Abbr'].nunique()} states, years={YEARS})"
    )
    return merged


def main():
    logger.info("Starting state-level aggregation")
    df = aggregate_state_rates()
    if df.empty:
        logger.warning("Aggregation produced no output — skipping write.")
        return

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUTPUT_PATH, index=False)
    logger.info(f"Saved: {OUTPUT_PATH}")

    over_one = df[df["registration_rate"] > 1.0][["State_Abbr", "Year", "registration_rate"]]
    if not over_one.empty:
        logger.warning(f"States with registration_rate > 1.0:\n{over_one.to_string(index=False)}")
    else:
        logger.info("No states with registration_rate > 1.0")


if __name__ == "__main__":
    main()
