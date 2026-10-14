# Timeseries 2024 Update: Findings

**Branch:** `eavs-timeseries-2024`
**Original findings:** 2026-09-22 (Claude Code supported session). **Updated:** 2026-10-14, after the column-name change described in section 2.

---

## What changed

### 1. `eavs/assets/manifest.jsonl`
Added the v2.0 entry for the 2024 timeseries release (the v1.0 entry for 2004-2022 is untouched):

    {"year": "timeseries", "version": "2.0", "format": "excel", "url": "https://www.eac.gov/sites/default/files/2026-09/EAVS_Time_Series_2004_2024.xlsx", "sha256sum": "3fec2bbcb03fd32148d7213e04a6bdfc3ff38b0b83236824d4a5c7945451b169"}

### 2. Column names: EAC names throughout
Names are the EAC's, per User Guide v2.1; project rename layer removed.
`eavs/assets/column_mappings/timeseries.yaml` is now a plain list of the 81 required columns (`raw_name`) and their dtypes. Nothing is renamed, so the cleaned file and the state-rate file use the names in the data file and the User Guide.

Columns that `aggregate.py` creates are renamed where the old name contained an item code:
`turnout_rate_a1b` is now `turnout_rate_regist_actv`, and `uses_a1a_fallback` is now `uses_regist_tot_fallback`. `turnout_rate` and the other rate columns keep their names.

Columns summed to state level, with the 2024 instrument item code for reference only:

| Item code | EAC name |
|---|---|
| F1a | `turnout_tot` |
| A1a | `regist_tot` |
| A1b | `regist_actv` |
| A3a | `reg_tot` |
| A3f | `reg_rej` |
| A12a | `remov_tot` |
| C1a | `mail_trans_tot` |
| C1b | `mail_ret` |
| C9a | `mail_rej_tot` |
| E1a | `prov_tot` |
| E1b | `prov_countfull` |
| E1c | `prov_countpart` |
| E1d | `prov_rej` |
| E1e | `prov_oth` |

### 3. `eavs/clean_timeseries.py`
- Version hardcode `"1.0"` changed to `"2.0"`.
- File selection guard: raises `RuntimeError` if more than one non-Appended-Labels spreadsheet exists in the version folder.
- Load-time check: every column listed in the yaml must exist in the file. One `RuntimeError` lists all missing columns (replaces the earlier critical-column check and the non-critical warning).
- No rename step. `FIPSCode` is zero-padded to 5 characters and `Year` is converted to a nullable integer.
- Bare `except: pass` blocks converted to `logger.warning(...)`.
- `load_column_mapping` raises `RuntimeError` if the YAML exists but has no entry for the requested version.
- Numeric dtypes are not enforced at read time (avoids Arrow truncation on fractional historical data); only string dtypes are enforced.
- `load_all_mappings()` fallback removed.
- Schema validation does not run: the code checks for `timeseries_process_schema.yaml`, and that file does not exist.

### 4. `eavs/aggregate.py`
- `YEARS`: `[2020, 2022]` changed to `[2020, 2022, 2024]`.
- Uses `remov_tot` (previously `voters_removed_total_2020_2022`).
- Added `prov_countfull`, `prov_countpart`, `prov_oth` to `SUM_COLS`.
- `provisional_rejection_rate` denominator is now `E1b+E1c+E1d+E1e` per EAC Appendix D, using `fillna(0)` for each component.
- Added a row-count assert after the CVAP merge.

---

## What was verified

### End-to-end run
- `clean_timeseries`: 64,130 rows x 590 columns (57,669 before; +6,461 = 2024 data).
- `aggregate`: 167 state-year rows (56 jurisdictions x 3 years).

### Column-name change (2026-10-14)
Outputs from the previous committed code were saved outside the repo before the change. After the change, with the old names mapped back, `pandas.testing.assert_frame_equal` passed for `timeseries.parquet` (64,130 x 590) and `state_rates.parquet` (167 x 26). No old project names remain in either file.

### Years in the cleaned file
11 survey years, 2004-2024. Rows per year: 2004 6,457; 2006 3,122; 2008 4,624; 2010 4,691; 2012 6,475; 2014 6,464; 2016 6,465; 2018 6,457; 2020 6,457; 2022 6,457; 2024 6,461.

### From the 2026-09-22 run (not re-checked on 2026-10-14)
- All critical columns 100% non-null in 2024 except `prov_oth` (E1e), 44% non-null at jurisdiction level.
- `reg_rej` <= `reg_tot`: zero violations across all 167 state-year rows.
- 2024 national `turnout_tot` total: 158,211,652.
- Turnout plausibility: PA 2024 77.1%, TX 2024 61.7%, CA 2024 62.8%.
- ME: `prov_rej` is null for all three years (ME does not report it). SD 2022 is nullified. SD 2020 shows 84.5% and is not nullified.

---

## Known limits and open questions

### A. CVAP vintage
The 2026-09-22 run found that `State.csv` uses ACS 2018-2022 5-year estimates for all three years. The data folder is named `CVAP_2020-2024_ACS_csv_files`, which suggests a different vintage. **Check which is correct.** The CVAP merge is by state only, so one estimate applies to every year, and `registration_rate` exceeds 1.0 in 30 state-years. Do not publish 2024 registration rates until this is settled.

### B. Provisional denominator fill assumption
`prov_oth` (E1e) is null for about 56% of 2024 jurisdictions and is treated as 0. If jurisdictions omit E1e instead of reporting 0, the denominator is understated and rates overstated. Cross-check high-rate states (AR 79%, DE 93%) against state-reported figures.

### C. Negative `reg_rej` at jurisdiction level (pre-existing)
Jurisdiction-level `reg_rej` has negative values in 2024 for WI (1,851 rows), ME (497), VT (247), CT (169), MT (56), IA (99), MS (82), OR (36), SC (46), UT (28), WY (23) and others. At state level all values are non-negative. Do not display jurisdiction-level rejection rates on dashboards.

### D. `_NULLIFY` list
It covers ME 2020/2022 and SD 2022. Review SD 2020 and any new 2024 anomalies.

### E. No schema validation
`timeseries_process_schema.yaml` does not exist, so no validation runs. If it is created, it must use the EAC column names (for example `remov_tot`).

### F. Sub-channel column definitions
2024 stems such as `regtot_stagncy` and `regtot_nvra` follow the User Guide definitions and may not match 2022 categories (state agency versus disability agency; NVRA versus mandatory/discretionary). They are not used in `aggregate.py`. Check the guide before any sub-channel analysis. `regist_tot` and `regist_actv` are null for North Dakota (no registration system; expected).

### G. Unit of observation: jurisdiction, not county
The file this pipeline reads (`EAVS_Time_Series_2004_2024.xlsx`) is jurisdiction level. In 2008, for example, 4,624 rows share 2,990 distinct `FIPSCode` values. The User Guide describes a separate county-level version in which township data are summed to counties by FIPS code and jurisdictions that cross county lines are split equally. A file named `EAVS_Time_Series_County_Collapse_2004_2024.xlsx` is in `data/raw/timeseries/` but has not been opened or used here. The 2026-09-21 decision to rely on a county rollup is **not verified** for the file this pipeline reads. Which level the dashboard needs is undecided.

### H. Row counts not reconciled with published reports
2008 has 4,624 rows in this file versus 4,527 jurisdictions in the published EAVS report. 2006 has only 3,122 rows. Not yet investigated.

### I. Reason columns
Only `remov_convic` and `remov_novote` are listed in the yaml. Other removal columns (moved, death, and others) and some mail and provisional rejection columns are in the output but are not named or used in aggregation.
