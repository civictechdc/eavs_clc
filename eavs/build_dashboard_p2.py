import json
import re

import numpy as np
import pandas as pd
from loguru import logger

from eavs.config import CLEANED_DATA_DIR, PROCESSED_DATA_DIR, PROJ_ROOT

TIMESERIES_PATH = CLEANED_DATA_DIR / "timeseries.parquet"
DASHBOARDS_DIR  = PROJ_ROOT / "dashboards"
OUTPUT_PATH     = DASHBOARDS_DIR / "eavs_dashboard_page2.html"

SENTINEL_COLS = [
    "total_registrations_received",
    "rejected_registrations",
    "registered_eligible_voters",
    "voters_removed_total_2020_2022",
    "mail_returned_by_voters",
    "mail_ballots_rejected_total",
    "provisional_ballots_cast_total",
    "provisional_ballots_rejected_total",
]

RATE_DEFS = {
    "reg_rejection_rate":         ("rejected_registrations",            "total_registrations_received"),
    "purge_rate":                 ("voters_removed_total_2020_2022",    "registered_eligible_voters"),
    "mail_rejection_rate":        ("mail_ballots_rejected_total",       "mail_returned_by_voters"),
    "provisional_rejection_rate": ("provisional_ballots_rejected_total","provisional_ballots_cast_total"),
}

CLASS_KEYS = {
    "reg_rejection_rate":         "reg_class",
    "purge_rate":                 "purge_class",
    "mail_rejection_rate":        "mail_class",
    "provisional_rejection_rate": "prov_class",
}


def _to_float(val):
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    v = float(val)
    return None if np.isnan(v) else v


def _normalize_state(raw: str) -> str:
    if not raw or raw.upper() in ("US", "UNITED STATES"):
        return "United States"
    return re.sub(r"\b(Of|And)\b", lambda m: m.group().lower(), raw.title())


def _classify(rate, avg) -> str:
    if rate is None or avg is None:
        return "Not reported"
    if rate < avg:
        return "Low"
    if rate < 2 * avg:
        return "Moderate"
    if rate < 4 * avg:
        return "High"
    return "Very high"


def _prepare():
    df = pd.read_parquet(TIMESERIES_PATH)
    df = df[df["year"].isin([2020, 2022])].copy()

    for col in SENTINEL_COLS:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce")
            df[col] = s.where(s >= 0)

    num_cols = [c for c in SENTINEL_COLS if c in df.columns]
    state_df = (
        df.groupby(["state", "state_abbr", "year"])[num_cols]
        .sum(min_count=1)
        .reset_index()
    )

    for rate_key, (numer, denom) in RATE_DEFS.items():
        n = pd.to_numeric(state_df[numer], errors="coerce")
        d = pd.to_numeric(state_df[denom], errors="coerce")
        mask = n.notna() & d.notna() & (d > 0)
        state_df[rate_key] = np.where(mask, n / d.where(d > 0, 1), np.nan)

    # Null out known anomalous values (EAVS_DATA_REFERENCE.md §9).
    for abbr, yr, col in [
        ("ME", 2020, "provisional_rejection_rate"),
        ("ME", 2022, "provisional_rejection_rate"),
        ("SD", 2022, "provisional_rejection_rate"),
    ]:
        mask = (state_df["state_abbr"] == abbr) & (state_df["year"] == yr)
        state_df.loc[mask, col] = np.nan

    avgs = {}
    for yr in [2020, 2022]:
        sub = state_df[state_df["year"] == yr]
        avgs[yr] = {}
        for rate_key in RATE_DEFS:
            vals = pd.to_numeric(sub[rate_key], errors="coerce").dropna()
            avgs[yr][rate_key] = float(vals.mean()) if len(vals) else None

    for rate_key, cls_key in CLASS_KEYS.items():
        def _cls(row, rk=rate_key):
            return _classify(_to_float(row[rk]), avgs[int(row["year"])][rk])
        state_df[cls_key] = state_df.apply(_cls, axis=1)

    records = []
    for _, row in state_df.iterrows():
        yr = int(row["year"])
        rec = {
            "state": _normalize_state(str(row["state"])),
            "abbr":  str(row["state_abbr"]),
            "year":  yr,
        }
        for rate_key in RATE_DEFS:
            rec[rate_key] = _to_float(row[rate_key])
        for cls_key in CLASS_KEYS.values():
            rec[cls_key] = str(row[cls_key])
        records.append(rec)

    avgs_out = {
        str(yr): {k: v for k, v in yr_d.items()}
        for yr, yr_d in avgs.items()
    }

    logger.info(
        f"Prepared {len(records)} state-year records, "
        f"{sum(1 for r in records if r['reg_rejection_rate'] is not None)} with reg rate"
    )
    return records, avgs_out


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>EAVS Voter Process Integrity — Page 2</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg:      #0f1117;
      --surf:    #1a1d2e;
      --surf-hi: #21263a;
      --bdr:     #2d3154;
      --txt:     #dde1ee;
      --mut:     #8892b0;
      --blue:    #4f8ef7;
      --red:     #f76c5e;
      --green:   #56d364;
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: var(--bg); color: var(--txt); font-family: 'Inter', system-ui, sans-serif; min-height: 100vh; font-size: 14px; }

    /* ── Header ── */
    .hdr { padding: 18px 24px 14px; border-bottom: 1px solid var(--bdr); }
    .hdr h1 { font-size: 18px; font-weight: 700; letter-spacing: -.01em; }
    .hdr p  { font-size: 12px; color: var(--mut); margin-top: 3px; }

    /* ── About / methodology ── */
    .about-data { border-top: 1px solid var(--bdr); margin-top: 4px; }
    .about-hdr  { padding: 9px 24px; font-size: 12px; color: var(--mut); cursor: pointer;
                  font-weight: 600; user-select: none; }
    .about-hdr:hover { color: var(--txt); }
    .about-body { padding: 2px 24px 16px; }
    .about-section { margin-bottom: 12px; font-size: 11px; color: var(--mut); line-height: 1.75; }
    .about-section strong { color: var(--txt); font-weight: 600; }
    .about-tag { display: inline-block; background: var(--surf-hi); border: 1px solid var(--bdr);
                 border-radius: 3px; padding: 0 5px; font-size: 10px; margin-right: 4px; }
    .crossnote { font-size: 11px; color: var(--mut); font-style: italic;
                 border-top: 1px solid var(--bdr); padding-top: 10px; margin-top: 4px;
                 line-height: 1.7; }

    /* ── Controls ── */
    .ctrl { padding: 10px 24px; display: flex; gap: 20px; align-items: center;
            flex-wrap: wrap; border-bottom: 1px solid var(--bdr); background: var(--surf); }
    .tg  { display: flex; align-items: center; gap: 4px; }
    .tg-lbl { font-size: 11px; color: var(--mut); text-transform: uppercase;
              letter-spacing: .07em; margin-right: 2px; white-space: nowrap; }
    button.tb { background: transparent; border: 1px solid var(--bdr); color: var(--mut);
                border-radius: 5px; padding: 4px 11px; font-size: 12px; font-family: inherit;
                cursor: pointer; transition: all .12s; line-height: 1.5; white-space: nowrap; }
    button.tb:hover { border-color: var(--blue); color: var(--txt); }
    button.tb.on  { background: var(--blue); border-color: var(--blue); color: #fff; font-weight: 600; }

    /* ── Legend ── */
    .lgnd { padding: 8px 24px; display: flex; gap: 14px; flex-wrap: wrap;
            border-bottom: 1px solid var(--bdr); }
    .li { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--mut); }
    .sw { width: 14px; height: 10px; border-radius: 2px; flex-shrink: 0; }

    /* ── Heatmap grid ── */
    .grid-wrap { padding: 14px 24px 6px; }
    #state-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(68px, 1fr)); gap: 6px; }
    .tile { border-radius: 6px; padding: 8px 4px 6px; cursor: pointer; text-align: center;
            transition: filter .1s; user-select: none; }
    .tile:hover { filter: brightness(1.2); }
    .tile-abbr { font-size: 14px; font-weight: 700; color: #fff; line-height: 1.2; }
    .tile-val  { font-size: 11px; color: rgba(255,255,255,0.85); margin-top: 1px; }

    /* ── Detail panel ── */
    #detail { display: none; border-top: 1px solid var(--bdr); padding: 16px 24px 20px;
              background: var(--surf); }
    .det-hdr { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 14px; }
    .det-title { font-size: 16px; font-weight: 700; }
    .det-close { background: none; border: 1px solid var(--bdr); color: var(--mut); border-radius: 4px;
                 padding: 2px 8px; font-size: 12px; font-family: inherit; cursor: pointer; }
    .det-close:hover { border-color: var(--red); color: var(--red); }
    .det-body { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
    @media (max-width: 820px) { .det-body { grid-template-columns: 1fr; } }
    .det-lbl { font-size: 10px; color: var(--mut); text-transform: uppercase;
               letter-spacing: .07em; margin-bottom: 8px; }
    .dtbl { width: 100%; border-collapse: collapse; font-size: 13px; }
    .dtbl th { text-align: left; color: var(--mut); font-size: 10px; font-weight: 500;
               text-transform: uppercase; letter-spacing: .06em;
               border-bottom: 1px solid var(--bdr); padding: 4px 8px 6px; }
    .dtbl td { padding: 7px 8px; border-bottom: 1px solid var(--bdr); vertical-align: middle; }
    #det-bars svg { display: block; width: 100%; height: auto; }

    /* ── Footnote ── */
    .footnote { padding: 10px 24px 20px; font-size: 11px; color: var(--mut);
                border-top: 1px solid var(--bdr); line-height: 1.6; }
  </style>
</head>
<body>

<div class="hdr">
  <h1>Voter Process Integrity Dashboard — Page 2</h1>
  <p>Administrative data reported by election officials to the EAC · Source: EAC Election Administration and Voting Survey (EAVS)</p>
</div>

<div class="ctrl">
  <div class="tg">
    <span class="tg-lbl">Metric</span>
    <button class="tb on" id="mb-reg_rejection_rate"         onclick="setMetric('reg_rejection_rate')">Reg. Rejection</button>
    <button class="tb"    id="mb-purge_rate"                 onclick="setMetric('purge_rate')">Purge Rate</button>
    <button class="tb"    id="mb-mail_rejection_rate"        onclick="setMetric('mail_rejection_rate')">Mail Ballot Rejection</button>
    <button class="tb"    id="mb-provisional_rejection_rate" onclick="setMetric('provisional_rejection_rate')">Provisional Rejection</button>
  </div>
  <div class="tg">
    <span class="tg-lbl">Year</span>
    <button class="tb on" id="yb-2022" onclick="setYear(2022)">2022</button>
    <button class="tb"    id="yb-2020" onclick="setYear(2020)">2020</button>
  </div>
</div>

<div class="lgnd">
  <div class="li"><div class="sw" style="background:#2dc4b2"></div>Low (below avg)</div>
  <div class="li"><div class="sw" style="background:#f0a500"></div>Moderate (up to 2× avg)</div>
  <div class="li"><div class="sw" style="background:#e07040"></div>High (2–4× avg)</div>
  <div class="li"><div class="sw" style="background:#cc3333"></div>Very high (&gt;4× avg)</div>
  <div class="li"><div class="sw" style="background:#2d3154;border:1px solid #3d4268"></div>Not reported</div>
</div>

<div class="grid-wrap">
  <div id="state-grid"></div>
</div>

<div id="detail">
  <div class="det-hdr">
    <div class="det-title" id="det-title"></div>
    <button class="det-close" onclick="closeDetail()">✕ close</button>
  </div>
  <div class="det-body">
    <div>
      <div class="det-lbl">Rates vs. National Average</div>
      <div id="det-table"></div>
    </div>
    <div>
      <div class="det-lbl">2020 → 2022 Change</div>
      <div id="det-bars"></div>
    </div>
  </div>
</div>

<div class="footnote">
  <strong>Source:</strong> EAC Election Administration and Voting Survey (EAVS), aggregated from jurisdiction level to state level.
  Sentinel values (−88 does not apply, −99 data not available) reported by jurisdictions were treated as "not reported" and excluded from rate calculations.
  States where all jurisdictions reported sentinels show no rate.
  Pennsylvania and several other states show elevated registration rejection rates because DMV automatic voter registration systems may count incomplete or duplicate form submissions as rejections.
  Maine 2020/2022 and South Dakota 2022 provisional rejection rates are suppressed due to known data anomalies.
</div>

<div class="about-data">
  <div class="about-hdr" onclick="const b=document.getElementById('about-body');b.style.display=b.style.display==='none'?'block':'none'">
    ▾ About the data &amp; methodology
  </div>
  <div class="about-body" id="about-body" style="display:none">
    <div class="about-section">
      <strong>Election Administration and Voting Survey (EAVS)</strong><br>
      <span class="about-tag">EAC</span> Biennial (federal election years) · Reported by: state and local election administrators<br>
      Measures: Administrative counts — ballots cast, voter registrations, rejections, purges, mail ballot activity.<br>
      Limitation: Self-reported by election officials; anomalies reflect administrative practices, not necessarily voter behaviour.<br>
      Coverage: All 50 states + DC + territories · Years in this dashboard: 2020, 2022
    </div>
    <div class="about-section">
      <strong>Metric formulas (source columns from EAVS codebook)</strong><br>
      Registration Rejection Rate: Rejected applications (A3e) ÷ Total applications received (A3a)<br>
      Purge Rate: Voters removed (A9a) ÷ Total registered voters (A1a)<br>
      Mail Ballot Rejection Rate: Mail ballots rejected (C9a) ÷ Mail ballots returned (C1b)<br>
      Provisional Rejection Rate: Provisional ballots rejected (E1d) ÷ Provisional ballots cast (E1a)
    </div>
    <div class="about-section">
      <strong>Classification thresholds:</strong>
      Low = below national average · Moderate = up to 2× average · High = 2–4× average · Very high = &gt;4× average.
      National average computed per year from states with reported data only.
    </div>
    <div class="about-section">
      <strong>Current Population Survey (CPS) Voting Supplement — Table 4b</strong><br>
      <span class="about-tag">Census Bureau</span> Not used on this page. Race-disaggregated self-reported participation rates appear on Page 3.
    </div>
    <div class="about-section">
      <strong>American Community Survey (ACS) — CVAP Special Tabulation</strong><br>
      <span class="about-tag">Census Bureau</span> Not used on this page. CVAP denominators appear on Page 1.
    </div>
    <div class="crossnote">
      EAVS rates shown here are for the total population — EAVS does not collect race-disaggregated administrative data.
      These administrative barrier rates cannot be directly compared to the race-disaggregated participation rates on Page 3,
      which use different denominators and a different data source (CPS).
    </div>
  </div>
</div>

<script>
const DATA = __DATA__;
const AVGS = __AVGS__;

const METRICS = [
  {key:'reg_rejection_rate',        cls:'reg_class',  label:'Reg. Rejection',       full:'Registration Rejection Rate',
   formula:'Rejected applications (A3e) ÷ Total applications received (A3a)'},
  {key:'purge_rate',                cls:'purge_class', label:'Purge Rate',            full:'Voter Purge / Removal Rate',
   formula:'Voters removed (A9a) ÷ Total registered voters (A1a)'},
  {key:'mail_rejection_rate',       cls:'mail_class',  label:'Mail Ballot Rejection', full:'Mail Ballot Rejection Rate',
   formula:'Mail ballots rejected (C9a) ÷ Mail ballots returned (C1b)'},
  {key:'provisional_rejection_rate',cls:'prov_class',  label:'Provisional Rejection', full:'Provisional Ballot Rejection Rate',
   formula:'Provisional ballots rejected (E1d) ÷ Provisional ballots cast (E1a)'},
];

const COLORS = {
  'Low':          '#2dc4b2',
  'Moderate':     '#f0a500',
  'High':         '#e07040',
  'Very high':    '#cc3333',
  'Not reported': '#2d3154',
};

const MAX_VALS = {};
for (const m of METRICS) {
  const vs = DATA.filter(d => d[m.key] !== null).map(d => d[m.key]);
  MAX_VALS[m.key] = vs.length ? Math.max(...vs) : 0.01;
}

let metric = 'reg_rejection_rate';
let year   = 2022;
let selected = null;

function setMetric(m) {
  metric = m;
  METRICS.forEach(mi =>
    document.getElementById('mb-' + mi.key).classList.toggle('on', mi.key === m)
  );
  renderGrid();
  if (selected) renderDetail(selected);
}

function setYear(y) {
  year = y;
  [2022, 2020].forEach(yr =>
    document.getElementById('yb-' + yr).classList.toggle('on', yr === y)
  );
  renderGrid();
  if (selected) renderDetail(selected);
}

function selectTile(abbr) {
  selected = abbr;
  renderGrid();
  renderDetail(abbr);
  document.getElementById('detail').style.display = 'block';
  setTimeout(() => document.getElementById('detail').scrollIntoView({behavior:'smooth', block:'nearest'}), 60);
}

function closeDetail() {
  selected = null;
  document.getElementById('detail').style.display = 'none';
  renderGrid();
}

function getRow(abbr, yr) {
  return DATA.find(d => d.abbr === abbr && d.year === yr) || null;
}

function pct(v, digits=1) {
  return (v === null || v === undefined) ? 'n/a' : (v * 100).toFixed(digits) + '%';
}

function renderGrid() {
  const rows = DATA.filter(d => d.year === year);
  const mobj = METRICS.find(m => m.key === metric);

  rows.sort((a, b) => {
    const av = a[metric], bv = b[metric];
    if (av === null && bv === null) return a.abbr < b.abbr ? -1 : 1;
    if (av === null) return 1;
    if (bv === null) return -1;
    return bv - av;
  });

  document.getElementById('state-grid').innerHTML = rows.map(d => {
    const cls = d[mobj.cls] || 'Not reported';
    const col = COLORS[cls];
    const isSel = d.abbr === selected;
    const bdr = isSel ? '2px solid rgba(255,255,255,0.9)' : '2px solid transparent';
    const flt = isSel ? 'filter:brightness(1.3)' : '';
    return `<div class="tile" style="background:${col};border:${bdr};${flt}" onclick="selectTile('${d.abbr}')">
      <div class="tile-abbr">${d.abbr}</div>
      <div class="tile-val">${pct(d[metric])}</div>
    </div>`;
  }).join('');
}

function renderDetail(abbr) {
  const r20  = getRow(abbr, 2020);
  const r22  = getRow(abbr, 2022);
  const rAct = year === 2022 ? r22 : r20;
  if (!rAct) return;

  document.getElementById('det-title').textContent = rAct.state + ' — ' + year;

  const av = AVGS[String(year)] || {};
  let tbl = `<table class="dtbl"><thead><tr>
    <th>Metric</th><th>Value</th><th>Nat'l Avg</th><th>Class</th>
  </tr></thead><tbody>`;
  for (const m of METRICS) {
    const v   = rAct[m.key];
    const a   = av[m.key];
    const cls = rAct[m.cls] || 'Not reported';
    const col = COLORS[cls];
    tbl += `<tr>
      <td>
        <div style="font-weight:500">${m.full}</div>
        <div style="font-size:10px;color:var(--mut);margin-top:2px;font-family:monospace">${m.formula}</div>
      </td>
      <td>${pct(v)}</td>
      <td style="color:var(--mut)">${pct(a)}</td>
      <td><span style="color:${col};font-weight:600">${cls}</span></td>
    </tr>`;
  }
  tbl += '</tbody></table>';
  document.getElementById('det-table').innerHTML = tbl;
  document.getElementById('det-bars').innerHTML = buildChangeBars(r20, r22);
}

function buildChangeBars(r20, r22) {
  if (!r20 && !r22) {
    return '<p style="color:var(--mut);font-size:12px;padding-top:8px">No data for either year.</p>';
  }

  const W=580, ML=188, MR=78, MT=8, RH=54, BH=12;
  const cw  = W - ML - MR;
  const H   = MT + METRICS.length * RH + 6;
  const MUT = '#8892b0', TXT = '#dde1ee', GRD = '#1e2236',
        GRN = '#56d364', RED = '#f76c5e';

  let s = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;

  for (let i = 0; i < METRICS.length; i++) {
    const m  = METRICS[i];
    const y0 = MT + i * RH;
    const v20 = r20 ? r20[m.key] : null;
    const v22 = r22 ? r22[m.key] : null;
    const mx  = MAX_VALS[m.key];

    if (i > 0) {
      s += `<line x1="0" y1="${y0}" x2="${W}" y2="${y0}" stroke="${GRD}" stroke-width="1"/>`;
    }

    // Metric label (short, right-aligned into left margin)
    s += `<text x="${ML-8}" y="${y0+13}" text-anchor="end" font-family="Inter,sans-serif" font-size="11" fill="${TXT}">${m.label}</text>`;

    // 2020 row
    s += `<text x="${ML-8}" y="${y0+28}" text-anchor="end" font-family="Inter,sans-serif" font-size="9" fill="${MUT}">2020</text>`;
    if (v20 !== null) {
      const w = Math.max((v20 / mx) * cw, 2);
      s += `<rect x="${ML}" y="${y0+18}" width="${w}" height="${BH}" rx="2" fill="#4f8ef7" fill-opacity="0.6"/>`;
      s += `<text x="${ML+w+4}" y="${y0+28}" font-family="Inter,sans-serif" font-size="10" fill="${MUT}">${pct(v20)}</text>`;
    } else {
      s += `<text x="${ML+4}" y="${y0+28}" font-family="Inter,sans-serif" font-size="10" font-style="italic" fill="${MUT}">n/a</text>`;
    }

    // 2022 row
    s += `<text x="${ML-8}" y="${y0+44}" text-anchor="end" font-family="Inter,sans-serif" font-size="9" fill="${MUT}">2022</text>`;
    if (v22 !== null) {
      const cls22 = r22 ? (r22[m.cls] || 'Not reported') : 'Not reported';
      const col22 = COLORS[cls22];
      const w = Math.max((v22 / mx) * cw, 2);
      s += `<rect x="${ML}" y="${y0+34}" width="${w}" height="${BH}" rx="2" fill="${col22}"/>`;
      s += `<text x="${ML+w+4}" y="${y0+44}" font-family="Inter,sans-serif" font-size="10" fill="${MUT}">${pct(v22)}</text>`;
    } else {
      s += `<text x="${ML+4}" y="${y0+44}" font-family="Inter,sans-serif" font-size="10" font-style="italic" fill="${MUT}">n/a</text>`;
    }

    // Delta label (right side)
    if (v20 !== null && v22 !== null) {
      const delta = v22 - v20;
      const sign  = delta >= 0 ? '+' : '';
      const col   = Math.abs(delta) < 0.001 ? MUT : (delta > 0 ? RED : GRN);
      const arrow = Math.abs(delta) < 0.001 ? '–' : (delta > 0 ? '▲' : '▼');
      s += `<text x="${W-MR+6}" y="${y0+28}" font-family="Inter,sans-serif" font-size="10" font-weight="600" fill="${col}">${sign}${(delta*100).toFixed(1)}pp</text>`;
      s += `<text x="${W-MR+6}" y="${y0+44}" font-family="Inter,sans-serif" font-size="11" fill="${col}">${arrow}</text>`;
    }
  }

  s += '</svg>';
  return s;
}

window.addEventListener('DOMContentLoaded', renderGrid);
</script>
</body>
</html>"""


def _html(records, avgs) -> str:
    return (
        HTML_TEMPLATE
        .replace("__DATA__", json.dumps(records, separators=(",", ":")))
        .replace("__AVGS__", json.dumps(avgs, separators=(",", ":")))
    )


def main():
    logger.info("Starting Page 2 dashboard build")
    if not TIMESERIES_PATH.exists():
        logger.error(f"Input not found: {TIMESERIES_PATH}")
        return
    records, avgs = _prepare()
    html = _html(records, avgs)
    DASHBOARDS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    size = OUTPUT_PATH.stat().st_size
    logger.info(f"Saved: {OUTPUT_PATH}  ({size:,} bytes, {len(records)} records)")


if __name__ == "__main__":
    main()
