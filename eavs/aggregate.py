import re

import numpy as np
import pandas as pd
from loguru import logger

from eavs.config import CLEANED_DATA_DIR, EXTERNAL_DATA_DIR, PROCESSED_DATA_DIR

CVAP_PATH = EXTERNAL_DATA_DIR / "CVAP_2020-2024_ACS_csv_files" / "State.csv"
TIMESERIES_PATH = CLEANED_DATA_DIR / "timeseries.parquet"
OUTPUT_PATH = PROCESSED_DATA_DIR / "state_rates.parquet"

YEARS = [2020, 2022, 2024]

# Columns summed to state level before computing rates.
# Column names are snake_case as in timeseries.parquet; EAVS item codes in comments.
# See EAVS_DATA_REFERENCE.md for full definitions and value ranges.
SUM_COLS = [
    "F1a",                               # F1a/turnout_tot — total ballots cast & counted, all modes
    "registered_eligible_voters",         # A1a/regist_tot  — total registered (active + inactive)
    "active_voters",                      # A1b/regist_actv — EAC-preferred registration denominator
    "total_registrations_received",       # A3a/reg_tot     — registration transaction denominator
    "rejected_registrations",             # A3f/reg_rej     — registration rejection numerator
    "voters_removed_total",               # A12a/remov_tot  — purge numerator (all years)
    "mail_transmitted_total",             # C1a/mail_trans_tot
    "mail_returned_by_voters",            # C1b/mail_ret    — mail rejection denominator
    "mail_ballots_rejected_total",        # C9a/mail_rej_tot — mail rejection numerator
    "provisional_ballots_cast_total",     # E1a/prov_tot    — total provisional cast
    "provisional_ballots_rejected_total", # E1d/prov_rej    — use E1d not E3 sum (stable across years)
    "prov_countfull",                     # E1b/prov_countfull — fully counted provisionals
    "prov_countpart",                     # E1c/prov_countpart — partially counted provisionals
    "prov_oth",                           # E1e/prov_oth    — other disposition (neither counted nor rejected)
]

# Known anomalous state-year-metric combinations to null after rate computation.
# See EAVS_DATA_REFERENCE.md §9.
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

    ts = ts[ts["year"].isin(YEARS)].copy()

    # Sentinel cleanup before aggregation (EAVS_DATA_REFERENCE.md §6).
    # pd.to_numeric coerces any remaining string sentinels; .where(>= 0) nulls
    # numeric sentinels (-88, -99, etc.) that survived the cleaning pipeline.
    present = [c for c in SUM_COLS if c in ts.columns]
    for col in present:
        ts[col] = pd.to_numeric(ts[col], errors="coerce")
        ts[col] = ts[col].where(ts[col] >= 0)

    state_df = (
        ts.groupby(["state", "state_abbr", "year"])[present]
        .sum(min_count=1)
        .reset_index()
    )

    state_df["state_join"] = state_df["state"].apply(_title_fix)
    merged = state_df.merge(cvap, on="state_join", how="left").drop(columns="state_join")

    # Compute rates — counts first, rates after (EAVS_DATA_REFERENCE.md §7).
    merged["registration_rate"] = _safe_rate(merged["registered_eligible_voters"], merged["cvap_est"])

    # Two turnout denominators (EAVS_DATA_REFERENCE.md §7).
    # A1a: total registered (active + inactive) — current pipeline default.
    # A1b: active voters only — EAC-preferred methodology.
    # Fallback: when A1b is null or equals A1a the state does not distinguish
    # active/inactive voters; use A1a for both and set uses_a1a_fallback = True.
    merged["turnout_rate"] = _safe_rate(merged["F1a"], merged["registered_eligible_voters"])

    _a1b = merged["active_voters"].copy()
    _fallback = _a1b.isna() | (_a1b == merged["registered_eligible_voters"])
    merged["turnout_rate_a1b"]  = _safe_rate(merged["F1a"], _a1b.where(~_fallback, merged["registered_eligible_voters"]))
    merged["uses_a1a_fallback"] = _fallback
    merged["reg_rejection_rate"]  = _safe_rate(merged["rejected_registrations"],          merged["total_registrations_received"])
    merged["purge_rate"]          = _safe_rate(merged["voters_removed_total"],            merged["registered_eligible_voters"])
    merged["mail_rejection_rate"] = _safe_rate(merged["mail_ballots_rejected_total"],     merged["mail_returned_by_voters"])

    # EAC Appendix D denominator: E1b+E1c+E1d+E1e (counted full + counted partial + rejected + other).
    # Old denominator was E1a (total cast), which overstates the pool and understates the rate.
    _prov_denom = (
        merged["prov_countfull"].fillna(0)
        + merged["prov_countpart"].fillna(0)
        + merged["provisional_ballots_rejected_total"].fillna(0)
        + merged["prov_oth"].fillna(0)
    )
    merged["provisional_rejection_rate"] = _safe_rate(merged["provisional_ballots_rejected_total"], _prov_denom)

    # Null out known anomalous values (EAVS_DATA_REFERENCE.md §9).
    for abbr, yr, col in _NULLIFY:
        mask = (merged["state_abbr"] == abbr) & (merged["year"] == yr)
        merged.loc[mask, col] = np.nan

    logger.info(
        f"Aggregated {len(merged)} state-year rows "
        f"({merged['state_abbr'].nunique()} states, years={YEARS})"
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

    over_one = df[df["registration_rate"] > 1.0][["state_abbr", "year", "registration_rate"]]
    if not over_one.empty:
        logger.warning(f"States with registration_rate > 1.0:\n{over_one.to_string(index=False)}")
    else:
        logger.info("No states with registration_rate > 1.0")


if __name__ == "__main__":
    main()
