# Timeseries 2024 Update — Findings

**Branch:** `eavs-timeseries-2024`
**Date:** 2026-09-22
**Reviewer:** Claude (session overnight)

---

## What changed

### 1. `eavs/assets/manifest.jsonl`
Added the v2.0 entry for the 2024 timeseries release:
```
{"year": "timeseries", "version": "2.0", "format": "excel",
 "url": "https://www.eac.gov/sites/default/files/2026-09/EAVS_Time_Series_2004_2024.xlsx",
 "sha256sum": "3fec2bbcb03fd32148d7213e04a6bdfc3ff38b0b83236824d4a5c7945451b169"}
```
The v1.0 entry (old 2004–2022 dataset) is untouched.

### 2. `eavs/assets/column_mappings/timeseries.yaml`
**Replaced** the old pandera-schema-format content (which was dead code — never matched any version string) with a proper column mapping for v2.0. Maps 2024 "stem" column names (e.g. `regist_tot`, `remov_tot`, `turnout_tot`) to pipeline-canonical names.

Key renames vs the 2022 convention:
| 2022 item code | 2024 stem | Canonical name |
|---|---|---|
| F1a | `turnout_tot` | `F1a` (preserved) |
| A1a | `regist_tot` | `registered_eligible_voters` |
| A9a | `remov_tot` | `voters_removed_total` (renamed from `voters_removed_total_2020_2022`) |
| A3e | `reg_rej` | `rejected_registrations` (note: A3e→A3f renumbering; crosswalk corrects guide typo) |
| C1a | `mail_trans_tot` | `mail_transmitted_total` |
| E1a | `prov_tot` | `provisional_ballots_cast_total` |
| E1b | `prov_countfull` | `prov_countfull` (new) |
| E1c | `prov_countpart` | `prov_countpart` (new) |
| E1d | `prov_rej` | `provisional_ballots_rejected_total` |
| E1e | `prov_oth` | `prov_oth` (new) |

### 3. `eavs/clean_timeseries.py`
- Version hardcode: `"1.0"` → `"2.0"`
- File selection guard: raises `RuntimeError` if more than one non-Appended-Labels spreadsheet exists in the version folder (can't silently grab wrong file)
- Silent no-op on column mismatch converted to `RuntimeError` for critical columns; non-critical mismatches logged as warnings
- All bare `except: pass` converted to `logger.warning(...)` calls
- `load_column_mapping` raises `RuntimeError` if the YAML exists but contains no entry matching the requested version (was returning `[]` silently, masking misconfiguration)
- Numeric dtypes not enforced at read time (avoid Arrow truncation on fractional historical data); type inference left to pyarrow
- `load_all_mappings()` fallback removed — v2.0 mapping is explicit and complete; no fallback needed

### 4. `eavs/aggregate.py`
- `YEARS`: `[2020, 2022]` → `[2020, 2022, 2024]`
- `voters_removed_total_2020_2022` → `voters_removed_total` throughout (SUM_COLS and `purge_rate` computation)
- Added `prov_countfull` (E1b), `prov_countpart` (E1c), `prov_oth` (E1e) to `SUM_COLS`
- `provisional_rejection_rate` denominator: was E1a (total cast); now `E1b+E1c+E1d+E1e` per EAC Appendix D. Uses `fillna(0)` for each component before summing.

---

## What was verified

### End-to-end run
```
clean_timeseries: 64,130 rows × 590 cols  (was 57,669; +6,461 = 2024 data)
aggregate:        167 state-year rows (56 jurisdictions × 3 years)
```

### Critical column population (2024 rows)
All columns 100% non-null in 2024 except:
- `prov_oth` (E1e): 44% non-null at jurisdiction level. States that don't report this category implicitly have 0, which is handled correctly by `fillna(0)` in the provisional denominator.

### reg_rej ≤ reg_tot sanity check
**Zero violations** across all 167 state-year rows. ✓

### 2024 national F1a total
**158,211,652** — consistent with public reports of ~155–160M votes cast in the 2024 presidential election. ✓

### Turnout plausibility
- PA 2024: 77.1% (vs 77.2% in 2020 — consistent for a presidential election)
- TX 2024: 61.7% (vs 46.1% in 2022 midterm — expected presidential-year increase)
- CA 2024: 62.8% (vs 41.4% in 2022 — expected)

### ME/SD provisional anomaly status
- **ME**: `provisional_ballots_rejected_total` is still null for all three years — ME does not report this field. `_NULLIFY` entries for ME 2020/2022 are now redundant (rate is NaN regardless) but harmless.
- **SD 2022**: Correctly nullified (NaN). SD 2024 shows 50.5% — no anomaly.
- **SD 2020**: 84.5% rejection rate — not nullified, worth reviewing.

---

## What is still uncertain / needs human review

### A. CVAP vintage mismatch for 2024
`State.csv` uses ACS 2018–2022 5-year estimates for all three years (2020, 2022, 2024). For the 2024 election, ACS 2020–2024 estimates would be more appropriate. This affects `registration_rate` for 2024 only. The 2024 CVAP file may not yet be published. **Flag for follow-up before publishing 2024 registration rates.**

### B. Provisional denominator fill assumption
`prov_oth` (E1e) is null for ~56% of 2024 jurisdictions. These are treated as 0 when computing the provisional rejection rate denominator. If jurisdictions are actually omitting E1e rather than reporting 0, the denominator is understated and rates are overstated. The effect is likely small for most states (E1e is a minor category), but some high-rejection-rate states (AR at 79%, DE at 93%) should be cross-checked against state-reported figures.

### C. Negative rejected_registrations at jurisdiction level (pre-existing)
Jurisdiction-level `rejected_registrations` has negative values in 2024 for: WI (1,851 rows), ME (497), VT (247), CT (169), MT (56), IA (99), MS (82), OR (36), SC (46), UT (28), WY (23), and others. This is a pre-existing timeseries artifact (correction/amendment rows net-negative). At the **state level, all values are non-negative** (0 violations in reg_rej ≤ reg_tot check). Do not display jurisdiction-level rejection rates on dashboards.

### D. `_NULLIFY` list review for 2024
The current `_NULLIFY` in `aggregate.py` covers ME 2020/2022 and SD 2022. Recommend reviewing whether any 2024 state-year combinations need similar treatment, particularly SD 2020 (84.5% provisional rejection rate) and any states with new anomalies.

### E. `voters_removed_total` renamed from `voters_removed_total_2020_2022`
The `timeseries_process_schema.yaml` (pandera validation schema) does not exist, so validation doesn't run. If/when it is created, it will need to use `voters_removed_total` not the old name. The old `timeseries.yaml` that was in column_mappings (which contained the pandera schema) has been replaced by the column mapping; the schema content should be moved to `eavs/assets/timeseries_process_schema.yaml` and updated before enabling validation.

### F. Survey category mapping changes (Section A, per-channel)
The 2024 timeseries uses new sub-category names for registration-by-channel (e.g. `regtot_stagncy` for "state agency" where 2022 used "disability agency", `regtot_nvra` for NVRA vs split mandatory/discretionary). The canonical names like `total_forms_disability_agency` and `total_forms_mandatory_nvra` may no longer accurately describe the 2024 data. These columns are not used in aggregate.py or the dashboard, but the naming should be reviewed before any sub-channel analysis.
