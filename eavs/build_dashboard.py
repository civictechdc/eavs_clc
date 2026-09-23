import json
import re

import pandas as pd
from loguru import logger

from eavs.config import PROCESSED_DATA_DIR, PROJ_ROOT

INPUT_PATH     = PROCESSED_DATA_DIR / "state_rates.parquet"
DASHBOARDS_DIR = PROJ_ROOT / "dashboards"
OUTPUT_PATH    = DASHBOARDS_DIR / "eavs_dashboard_page1.html"


def _title_fix(s: str) -> str:
    return re.sub(r"\b(Of|And)\b", lambda m: m.group().lower(), s.title())


def _to_float(val):
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    return float(val)


def _to_int(val):
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    return int(val)


def _build_records(df: pd.DataFrame) -> list[dict]:
    records = []
    for _, row in df.iterrows():
        abbr = str(row["state_abbr"])
        yr   = int(row["year"])
        reg      = _to_float(row["registration_rate"])
        turn_a1a = _to_float(row["turnout_rate"])          # F1a / A1a (total registered)
        turn_a1b = _to_float(row["turnout_rate_a1b"])      # F1a / A1b (EAC active voters)
        cvap     = _to_float(row["cvap_est"])

        # reg_rejection_rate: null out negative values — timeseries aggregation
        # artifact for WI, CT, AR, OR, SC, MO (EAVS_DATA_REFERENCE.md §9).
        reg_rej = _to_float(row["reg_rejection_rate"])
        if reg_rej is not None and reg_rej < 0:
            reg_rej = None

        # provisional_rejection_rate: ME (both years) and SD 2022 already nulled
        # in aggregate.py; _to_float converts any remaining NaN to None.
        prov_rej = _to_float(row["provisional_rejection_rate"])

        records.append({
            "state":   _title_fix(str(row["state"])),
            "abbr":    abbr,
            "year":    yr,
            # Primary participation rates
            "registration_rate": reg,
            "turnout_rate_a1a":  turn_a1a,
            "turnout_rate_a1b":  turn_a1b,
            "uses_a1a_fallback": bool(row.get("uses_a1a_fallback", False)),
            "cvap_est":          cvap,
            # Process integrity rates
            "reg_rejection_rate":         reg_rej,
            "purge_rate":                 _to_float(row["purge_rate"]),
            "mail_rejection_rate":        _to_float(row["mail_rejection_rate"]),
            "provisional_rejection_rate": prov_rej,
            # Raw counts
            "registered_voters":              _to_int(row["registered_eligible_voters"]),
            "active_voters":                  _to_int(row["active_voters"]),
            "ballots_cast":                   _to_int(row["F1a"]),
            "total_registrations_received":   _to_int(row["total_registrations_received"]),
            "rejected_registrations":         _to_int(row["rejected_registrations"]),
            "voters_removed":                 _to_int(row["voters_removed_total_2020_2022"]),
            "mail_transmitted":               _to_int(row["mail_transmitted_total"]),
            "mail_returned":                  _to_int(row["mail_returned_by_voters"]),
            "mail_rejected":                  _to_int(row["mail_ballots_rejected_total"]),
            "provisional_cast":               _to_int(row["provisional_ballots_cast_total"]),
            "provisional_rejected":           _to_int(row["provisional_ballots_rejected_total"]),
            # Flags
            "is_stale":                reg is not None and reg > 1.0,
            "is_territory":            cvap is None,
            "is_ky_rejection_anomaly": abbr == "KY",
        })
    return records


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>EAVS Voter Participation — Page 1</title>
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
      --gold:    #f0c040;
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

    /* ── Summary chips ── */
    .chips { padding: 10px 24px; display: flex; gap: 10px; flex-wrap: wrap;
             border-bottom: 1px solid var(--bdr); }
    .chip { background: var(--surf); border: 1px solid var(--bdr); border-radius: 8px;
            padding: 9px 16px; min-width: 155px; }
    .chip-lbl { font-size: 10px; color: var(--mut); text-transform: uppercase; letter-spacing: .07em; }
    .chip-val { font-size: 22px; font-weight: 700; margin-top: 3px; line-height: 1; }
    .c-blue { color: var(--blue); }
    .c-red  { color: var(--red);  }
    .c-gold { color: var(--gold); }

    /* ── Charts ── */
    .charts { padding: 14px 24px 0; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    @media (max-width: 820px) { .charts { grid-template-columns: 1fr; } }
    .cp { background: var(--surf); border: 1px solid var(--bdr); border-radius: 10px;
          padding: 10px 8px; overflow-y: auto; max-height: 65vh; min-height: 300px; }
    .cp svg { display: block; width: 100%; height: auto; }

    /* ── Legend ── */
    .legend { padding: 8px 24px 6px; display: flex; gap: 14px; flex-wrap: wrap; }
    .li { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--mut); }
    .sw { width: 12px; height: 9px; border-radius: 2px; flex-shrink: 0; }
    .dl { width: 20px; border-top: 2px dashed var(--gold); flex-shrink: 0; }

    /* ── Footnote ── */
    .footnote { padding: 4px 24px 16px; font-size: 11px; color: var(--mut);
                border-top: 1px solid var(--bdr); line-height: 1.6; margin-top: 6px; }
  </style>
</head>
<body>

<div class="hdr">
  <h1>Voter Participation Dashboard — Page 1</h1>
  <p>Administrative data reported by election officials to the EAC · Election Administration and Voting Survey (EAVS), U.S. Election Assistance Commission</p>
</div>

<div class="ctrl">
  <div class="tg">
    <span class="tg-lbl">Year</span>
    <button class="tb on" id="y2022" onclick="setYear(2022)">2022</button>
    <button class="tb"    id="y2020" onclick="setYear(2020)">2020</button>
  </div>
  <div class="tg">
    <span class="tg-lbl">Sort</span>
    <button class="tb on" id="s-reg"  onclick="setSort('reg')">Registration Rate</button>
    <button class="tb"    id="s-turn" onclick="setSort('turn')">Turnout Rate</button>
    <button class="tb"    id="s-az"   onclick="setSort('az')">A – Z</button>
  </div>
  <div class="tg">
    <span class="tg-lbl">Turnout</span>
    <button class="tb on" id="tm-a1b" onclick="setTurnMethod('a1b')">EAC (active voters)</button>
    <button class="tb"    id="tm-a1a" onclick="setTurnMethod('a1a')">Total registered</button>
  </div>
</div>

<div class="chips">
  <div class="chip">
    <div class="chip-lbl">Avg Registration Rate</div>
    <div class="chip-val c-blue" id="c-reg">—</div>
  </div>
  <div class="chip">
    <div class="chip-lbl">States Below 80% Reg.</div>
    <div class="chip-val c-red" id="c-low">—</div>
  </div>
  <div class="chip">
    <div class="chip-lbl">Avg Turnout Rate</div>
    <div class="chip-val c-gold" id="c-turn">—</div>
  </div>
</div>

<div class="charts">
  <div class="cp" id="reg-panel"></div>
  <div class="cp" id="turn-panel"></div>
</div>

<div class="legend">
  <div class="li"><div class="sw" style="background:#4f8ef7"></div>Normal</div>
  <div class="li"><div class="sw" style="background:#f76c5e"></div>Stale rolls (reg. rate &gt; 100%)</div>
  <div class="li"><div class="sw" style="background:#2d3154"></div>Territory / no CVAP (n/a)</div>
  <div class="li"><div class="dl"></div>National average (excl. territories)</div>
  <div class="li" id="li-fallback" style="display:none"><span style="color:var(--mut);font-size:12px;margin-right:2px">†</span>A1a fallback state</div>
</div>
<div class="footnote" id="turn-footnote" style="display:none">
  <strong>Turnout rate (EAC method):</strong> F1a ÷ active registered voters (A1b).
  6 states (ID, MN, NH, ND, Guam, PR) do not distinguish active/inactive voters — A1a (total registered) used as fallback for those states. Marked †.
  Additional states where active and total registered counts are equal in EAVS data are also shown with †.
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
      <strong>Registration rate denominator:</strong>
      Registered voters (EAVS A1a or A1b) ÷ Citizen Voting-Age Population (ACS CVAP 5-year estimates, U.S. Census Bureau).
      A1a = total registered (active + inactive); A1b = active voters only (EAC-preferred). Toggle above to switch.<br>
      <strong>Turnout rate denominator:</strong>
      Total ballots cast (EAVS F1a, all modes: Election Day in-person, early in-person, mail, counted provisional, UOCAVA)
      ÷ Active registered voters (EAVS A1b); fallback to A1a for states that do not distinguish active/inactive voters (marked †).
    </div>
    <div class="about-section">
      <strong>American Community Survey (ACS) — CVAP Special Tabulation</strong><br>
      <span class="about-tag">Census Bureau</span> Annual (5-year rolling estimates used here)<br>
      Measures: Citizen Voting Age Population (CVAP) — U.S. citizens aged 18+ by race and geography.<br>
      Used for: Registration rate denominator (Registered voters ÷ CVAP).<br>
      Vintage used: ACS 2018–2022 5-year estimates
    </div>
    <div class="about-section">
      <strong>Current Population Survey (CPS) Voting Supplement — Table 4b</strong><br>
      <span class="about-tag">Census Bureau</span> Not used on this page. Race-disaggregated participation rates appear on Page 3.
    </div>
    <div class="crossnote">
      Registration rates above 100% are real — they reflect stale voter rolls where EAVS-reported registrations exceed the ACS CVAP estimate. These are flagged in red and are not suppressed.
    </div>
  </div>
</div>

<script>
const DATA = __DATA__;

let year = 2022, sortBy = 'reg', turnMethod = 'a1b';

function setYear(y) {
  year = y;
  ['2022', '2020'].forEach(k =>
    document.getElementById('y' + k).classList.toggle('on', Number(k) === y)
  );
  render();
}

function setSort(s) {
  sortBy = s;
  ['reg', 'turn', 'az'].forEach(k =>
    document.getElementById('s-' + k).classList.toggle('on', k === s)
  );
  render();
}

function setTurnMethod(m) {
  turnMethod = m;
  ['a1b', 'a1a'].forEach(k =>
    document.getElementById('tm-' + k).classList.toggle('on', k === m)
  );
  render();
}

function sorted(data) {
  const d = [...data];
  if (sortBy === 'reg') {
    d.sort((a, b) => {
      if (a.is_territory !== b.is_territory) return a.is_territory ? 1 : -1;
      return (b.registration_rate ?? -1) - (a.registration_rate ?? -1);
    });
  } else if (sortBy === 'turn') {
    const tf = turnMethod === 'a1b' ? 'turnout_rate_a1b' : 'turnout_rate_a1a';
    d.sort((a, b) => (b[tf] ?? -1) - (a[tf] ?? -1));
  } else {
    d.sort((a, b) => a.abbr < b.abbr ? -1 : 1);
  }
  return d;
}

function mean(data, field) {
  const vs = data
    .filter(d => !d.is_territory && d[field] !== null)
    .map(d => d[field]);
  return vs.length ? vs.reduce((a, b) => a + b, 0) / vs.length : null;
}

function pct(v) {
  return v === null ? 'n/a' : (v * 100).toFixed(1) + '%';
}

function chart(panelId, rows, field, title, subtitle, maxX) {
  const W = 680, ML = 46, MR = 64, MT = 62, MB = 44, RH = 21, BH = 13;
  const cw = W - ML - MR;
  const H  = MT + rows.length * RH + MB;
  const sc = v => Math.max(0, (v / maxX) * cw);
  const a  = mean(rows, field);

  const BLU = '#4f8ef7', RED = '#f76c5e', MUT = '#8892b0',
        GLD = '#f0c040', GRD = '#1e2236', TXT = '#dde1ee';

  let s = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;

  // Title + subtitle (split subtitle on ' · ')
  s += `<text x="${ML}" y="16" font-family="Inter,sans-serif" font-size="13" font-weight="600" fill="${TXT}">${title}</text>`;
  const sub = subtitle.split(' · ');
  s += `<text x="${ML}" y="30" font-family="Inter,sans-serif" font-size="11" fill="${MUT}">${sub[0]}</text>`;
  if (sub[1]) s += `<text x="${ML}" y="45" font-family="Inter,sans-serif" font-size="11" fill="${MUT}">${sub[1]}</text>`;

  // X-axis grid lines
  const ticks = [0, .25, .5, .75, 1.0, ...(maxX > 1 ? [1.25] : [])];
  for (const t of ticks) {
    const x = ML + sc(t);
    s += `<line x1="${x}" y1="${MT}" x2="${x}" y2="${H - MB}" stroke="${GRD}" stroke-width="1"/>`;
    s += `<text x="${x}" y="${H - MB + 16}" text-anchor="middle" font-family="Inter,sans-serif" font-size="10" fill="${MUT}">${Math.round(t * 100)}%</text>`;
  }

  // 100% threshold line on registration chart
  if (maxX > 1) {
    const x1 = ML + sc(1.0);
    s += `<line x1="${x1}" y1="${MT}" x2="${x1}" y2="${H - MB}" stroke="${RED}" stroke-width="1.2" stroke-opacity="0.45"/>`;
  }

  // National average dashed line + label below chart
  if (a !== null) {
    const ax = ML + sc(a);
    s += `<line x1="${ax}" y1="${MT}" x2="${ax}" y2="${H - MB}" stroke="${GLD}" stroke-width="1.5" stroke-dasharray="4,3"/>`;
    s += `<text x="${ax}" y="${H - MB + 30}" text-anchor="middle" font-family="Inter,sans-serif" font-size="10" font-weight="500" fill="${GLD}">avg ${pct(a)}</text>`;
  }

  // Bar rows
  for (let i = 0; i < rows.length; i++) {
    const d  = rows[i];
    const y0 = MT + i * RH;
    const by = y0 + (RH - BH) / 2;
    const v  = d[field];

    if (i % 2 === 0) {
      s += `<rect x="0" y="${y0}" width="${W}" height="${RH}" fill="#ffffff" fill-opacity="0.012"/>`;
    }

    // State abbreviation label
    s += `<text x="${ML - 5}" y="${y0 + RH / 2 + 4}" text-anchor="end" font-family="Inter,sans-serif" font-size="11" fill="${MUT}">${d.abbr}</text>`;

    if (v === null) {
      s += `<text x="${ML + 5}" y="${y0 + RH / 2 + 4}" font-family="Inter,sans-serif" font-size="10" font-style="italic" fill="${MUT}">n/a</text>`;
    } else {
      const bw  = Math.min(sc(v), cw);
      const col = (field === 'registration_rate' && d.is_stale) ? RED : BLU;
      s += `<rect x="${ML}" y="${by}" width="${Math.max(bw, 2)}" height="${BH}" rx="2" fill="${col}"/>`;
      const staleTag    = (field === 'registration_rate' && d.is_stale) ? ' stale' : '';
      const fallbackTag = (field === 'turnout_rate_a1b' && d.uses_a1a_fallback) ? ' †' : '';
      const lbl = pct(v) + staleTag + fallbackTag;
      const lc  = (field === 'registration_rate' && d.is_stale) ? RED : MUT;
      s += `<text x="${ML + bw + 5}" y="${y0 + RH / 2 + 4}" font-family="Inter,sans-serif" font-size="10" fill="${lc}">${lbl}</text>`;
    }
  }

  s += '</svg>';
  document.getElementById(panelId).innerHTML = s;
}

function updateChips(data) {
  const ar  = mean(data, 'registration_rate');
  const turnField = turnMethod === 'a1b' ? 'turnout_rate_a1b' : 'turnout_rate_a1a';
  const at  = mean(data, turnField);
  const low = data.filter(
    d => !d.is_territory && d.registration_rate !== null && d.registration_rate < 0.8
  ).length;
  document.getElementById('c-reg').textContent  = ar !== null ? pct(ar) : '—';
  document.getElementById('c-low').textContent  = low;
  document.getElementById('c-turn').textContent = at !== null ? pct(at) : '—';
}

function render() {
  const rows = sorted(DATA.filter(d => d.year === year));
  const turnField = turnMethod === 'a1b' ? 'turnout_rate_a1b' : 'turnout_rate_a1a';
  const turnSub = turnMethod === 'a1b'
    ? `Numerator: F1a — all ballot modes (EAVS ${year}) · Denominator: Active registered voters (A1b, EAC method) — † = A1a fallback`
    : `Numerator: F1a — all ballot modes (EAVS ${year}) · Denominator: Total registered voters (A1a, incl. inactive)`;

  const hasFallback = turnMethod === 'a1b' && rows.some(d => d.uses_a1a_fallback);
  document.getElementById('li-fallback').style.display   = hasFallback ? '' : 'none';
  document.getElementById('turn-footnote').style.display = turnMethod === 'a1b' ? '' : 'none';

  chart('reg-panel',  rows, 'registration_rate',
    'Voter Registration Rate',
    `Numerator: Registered voters (EAVS ${year} — sum of jurisdiction-level reported totals) · Denominator: Citizen Voting-Age Population (ACS CVAP 2020–2024 5-year estimate, U.S. Census Bureau)`,
    1.5);
  chart('turn-panel', rows, turnField, 'Voter Turnout Rate', turnSub, 1.0);
  updateChips(rows);
}

window.addEventListener('DOMContentLoaded', render);
</script>
</body>
</html>"""


def _html(records: list[dict]) -> str:
    return HTML_TEMPLATE.replace("__DATA__", json.dumps(records, separators=(",", ":")))


def main():
    logger.info("Starting dashboard build")
    if not INPUT_PATH.exists():
        logger.error(f"Input not found: {INPUT_PATH}")
        return
    df = pd.read_parquet(INPUT_PATH)
    records = _build_records(df)
    html = _html(records)
    DASHBOARDS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    size = OUTPUT_PATH.stat().st_size
    logger.info(f"Saved: {OUTPUT_PATH}  ({size:,} bytes, {len(records)} records)")


if __name__ == "__main__":
    main()
