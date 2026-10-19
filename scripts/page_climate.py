"""Climate adaptation in CERF projects (climate-adaptation.html): an UNLISTED public page.

CERF projects coded by hand against climate-adaptation indicators, filterable by indicator.
The page sits behind the public site's password like the tabs, but no tab and no other page
links to it (build_site.UNLISTED_TABS): it is reached only by its link while the coding grows.

The codes are aa.cerf_climate_coding (one row per project x indicator x coder, loaded from
the coding workbooks by scripts/import_climate_coding.py); everything else about a project
(year, country, agency, emergency, title, amount) is the CERF mirror, aa.cerf_project.
Nothing from the proposals themselves is shown: the coder read them, the page only says
what was coded.

INDICATORS is the coding sheet's framework, worded for reading: one gate question (does
the proposal mention current climate risk or future impacts?) and the activity indicators
in seven areas. The keys are the ones the coding table stores."""

import html
import json

import pandas as pd

from dashboards import DASH_CSS

PAGE = "climate-adaptation.html"
TITLE = "Climate adaptation in CERF projects"

GATE = "climate_risk_mentioned"
THEMES = [
    ("water", "Water", "reducing climate-induced water scarcity; resilient water supply and sanitation"),
    ("food", "Food and agriculture", "climate-resilient food and agriculture, and food for all"),
    ("health", "Health", "resilient health services; less climate-related illness and death"),
    ("ecosystems", "Ecosystems", "nature-based solutions or ecosystem restoration"),
    ("infrastructure", "Infrastructure and settlements", "resilient infrastructure; fewer impacts on settlements"),
    ("poverty", "Poverty and livelihoods", "reducing climate impacts on poverty and livelihoods"),
    ("ews", "Early warning", "updated risk assessment and multi-hazard early warning"),
]
# (key, theme, label); the 'other' indicators carry the coder's list of activities as a note
INDICATORS = [
    (GATE, "gate", "Current climate risk or future climate impacts are mentioned"),
    ("water_sanitation", "water", "Increases or extends sanitation"),
    ("water_stress", "water", "Reduces water stress"),
    ("water_efficiency", "water", "Increases water efficiency"),
    ("water_relocation", "water", "Supports planned relocation in response to a water hazard"),
    ("water_other", "water", "Other relevant activities"),
    ("food_extension", "food", "Extension services or knowledge transfer"),
    ("food_adaptation_tech", "food", "Agriculture that uses adaptation technology"),
    ("food_access", "food", "More people with equitable access to food and nutrition"),
    ("food_yield", "food", "Increases yield"),
    ("food_other", "food", "Other climate-relevant activities"),
    ("health_infectious_disease", "health", "Less climate-related infectious disease"),
    ("health_mortality_morbidity", "health", "Less mortality or morbidity from climate-related impacts"),
    ("health_mental_health", "health", "More people vulnerable to climate change with access to mental health services"),
    ("health_services_capacity", "health", "Health services stay at full capacity during climate-related events"),
    ("health_facilities_resilient", "health", "Health facilities resilient to climate hazards"),
    ("health_other", "health", "Other relevant health activities"),
    ("ecosystems_activities", "ecosystems", "Includes relevant activities"),
    ("infra_relocation", "infrastructure", "Infrastructure or settlements relocated to (climate-)safer locations"),
    ("infra_settlement_upgrade", "infrastructure", "Settlement upgrade that includes adaptation"),
    ("infra_other", "infrastructure", "Other relevant activities"),
    ("poverty_social_protection_access", "poverty", "More access to social protection"),
    ("poverty_social_protection_climate", "poverty", "Social protection that considers climate risk"),
    ("poverty_reduced", "poverty", "Fewer people living in poverty"),
    ("ews_multi_hazard", "ews", "Helps establish multi-hazard early warning systems"),
    ("ews_warning_access", "ews", "More people with access to warnings from government"),
    ("ews_monitoring_forecasts", "ews", "Hazard monitoring and forecasts"),
    ("ews_evacuation", "ews", "More people evacuated as a result of a warning"),
    ("ews_climate_information", "ews", "Climate information services or climate-related data collection"),
]
KEYS = {k for k, _, _ in INDICATORS}

SQL = """
SELECT c.project_code, c.indicator, c.coded_by, c.value, c.uncertain, c.note,
       p.year, p.country_iso3, p.country_name, p.window_name, p.agency_short_name,
       p.emergency_type, p.title, p.amount_approved
FROM aa.cerf_climate_coding c
LEFT JOIN aa.cerf_project p USING (project_code)
ORDER BY c.project_code, c.coded_by"""


def _e(s):
    return html.escape("" if s is None else str(s))


def _s(v):
    """A text field, None when missing (a project absent from the CERF mirror has no facts)."""
    return None if v is None or pd.isna(v) else str(v)


def _rows(df):
    """One record per (project, coder): the project's facts, its Y/N codes, the answers marked
    uncertain and the coder's notes."""
    out = []
    for (code, coder), g in df.groupby(["project_code", "coded_by"], sort=True):
        p = g.iloc[0]
        codes = {r.indicator: r.value for r in g.itertuples() if r.value in ("Y", "N")}
        out.append({
            "code": code, "coder": coder,
            "year": None if pd.isna(p.year) else int(p.year),
            "iso3": _s(p.country_iso3), "country": _s(p.country_name),
            "window": _s(p.window_name), "agency": _s(p.agency_short_name),
            "emergency": _s(p.emergency_type), "title": _s(p.title),
            "amount": None if pd.isna(p.amount_approved) else round(float(p.amount_approved)),
            "codes": codes,
            "unc": sorted(r.indicator for r in g.itertuples() if r.uncertain),
            "notes": {r.indicator: r.note for r in g.itertuples() if isinstance(r.note, str) and r.note},
            "mirror": not pd.isna(p.year),
        })
    return out


def build(e, page):
    exists = pd.read_sql("SELECT to_regclass('aa.cerf_climate_coding') AS r", e)["r"].iloc[0]
    df = pd.read_sql(SQL, e) if exists is not None else pd.DataFrame()
    if df.empty:
        page(PAGE, TITLE, f"<style>{DASH_CSS}</style><div class='card'>No coded projects loaded yet: "
             "the codes arrive through a data-entry file (scripts/import_climate_coding.py).</div>")
        return
    unknown = sorted(set(df["indicator"]) - KEYS)
    if unknown:
        print(f"::warning::{PAGE}: indicator keys not in page_climate.INDICATORS ignored: {', '.join(unknown)}")
        df = df[df["indicator"].isin(KEYS)]
    if df.empty:
        page(PAGE, TITLE, f"<style>{DASH_CSS}</style><div class='card'>No coded projects loaded yet.</div>")
        return
    rows = _rows(df)
    coders = sorted({r["coder"] for r in rows}, key=lambda c: (c.startswith("model-"), c))
    data = {
        "themes": [{"key": k, "name": n, "desc": d} for k, n, d in THEMES],
        "indicators": [{"key": k, "theme": t, "label": lab} for k, t, lab in INDICATORS],
        "gate": GATE, "rows": rows, "coders": coders,
    }
    # every '<' escaped: no text in the data can end the script element or open a comment in it
    payload = json.dumps(data, ensure_ascii=False, default=str, allow_nan=False).replace("<", "\\u003c")

    coder_pick = ("<label>Coder <select id='cc-coder'>"
                  + "".join(f"<option>{_e(c)}</option>" for c in coders) + "</select></label>"
                  if len(coders) > 1 else "")
    body = f"""
<div class='card'><b>Unlisted page, work in progress.</b> CERF projects coded against climate-adaptation
indicators: one question on whether the proposal mentions current climate risk or future climate impacts,
and activity indicators in seven areas, each project coded from its proposal's project summary. More are
being coded. Tick indicators below to list the projects coded <i>yes</i> on them; the counts follow the other
filters. Project facts (year, agency, emergency, amount) are from the CERF project data.
<div class='tiles' id='cc-tiles'></div><div class='meta' id='cc-blank'></div></div>

<div class='fbar'>
 {coder_pick}
 <label>Year <select id='cc-year'><option value=''>all</option></select></label>
 <label>Window <select id='cc-window'><option value=''>all</option></select></label>
 <label>Agency <select id='cc-agency'><option value=''>all</option></select></label>
 <label>Emergency <select id='cc-emergency'><option value=''>all</option></select></label>
 <input id='cc-q' type='search' placeholder='search code, country, title…' aria-label='Search projects'>
 <span class='cc-mode'>Ticked indicators: <label><input type='radio' name='cc-mode' value='any' checked> any</label>
 <label><input type='radio' name='cc-mode' value='all'> all</label></span>
 <button type='button' id='cc-reset' class='dl'>Clear filters</button>
</div>

<h2>Indicators</h2>
<div class='cc-gate' id='cc-gate'></div>
<div class='cc-themes' id='cc-themes'></div>

<h2 id='cc-h'>Projects</h2>
<div class='cc-head'><span id='cc-count' class='meta'></span>
 <button type='button' class='dl' id='cc-csv'>Download CSV</button></div>
<div class='scroll'><table class='data cc-table'><thead><tr>
 <th>Project</th><th>Year</th><th>Country</th><th>Agency</th><th>Emergency</th><th>Title</th>
 <th style='text-align:right'>Approved (US$)</th><th>Coded yes</th></tr></thead>
 <tbody id='cc-body'></tbody></table></div>
<p class='meta'>A tag is an area with at least one indicator coded yes (×n: how many); hover it for the
indicators. (?) = the coder was unsure of one of them. The coder's notes are under the tags.</p>

<script type='application/json' id='cc-data'>{payload}</script>
<style>{DASH_CSS}{CC_CSS}</style><script>{CC_JS}</script>"""
    page(PAGE, TITLE, body)


CC_CSS = """
.cc-mode { font-size:12px; color:#555; }
.cc-themes { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:12px; }
.cc-th { background:#fff; border:1px solid #e0e0e0; border-radius:6px; padding:10px 12px 8px; min-width:0; }
.cc-th h3 { margin:0; font-size:14px; display:flex; gap:8px; align-items:baseline; }
.cc-th h3 .n { margin-left:auto; color:var(--muted); font-weight:400; font-size:12px; white-space:nowrap; }
.cc-th .d { color:var(--muted); font-size:11.5px; margin:2px 0 6px; }
.cc-gate .cc-th { max-width:600px; margin-bottom:12px; }
.cc-i { display:grid; grid-template-columns:auto 1fr 56px 42px; gap:6px; align-items:center; font-size:12.5px;
        padding:3px 0; cursor:pointer; }
.cc-i.zero { color:#999; }
.cc-i .bar { display:block; height:8px; background:#eef1f5; border-radius:4px; position:relative; overflow:hidden; }
.cc-i .bar i { position:absolute; left:0; top:0; bottom:0; background:var(--accent); }
.cc-i .cnt { font-size:11.5px; color:#333; text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }
.fbar select { max-width:200px; }
.cc-head { display:flex; gap:12px; align-items:center; justify-content:space-between; margin:6px 0; }
.cc-table td.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
.cc-tag { display:inline-block; font-size:11px; padding:1px 7px; margin:1px 3px 1px 0; border-radius:9px;
          background:#eaf4ff; color:#0b4f8a; white-space:nowrap; cursor:help; }
.cc-tag.gate { background:#fff4d6; color:#7a5200; }
.cc-note { color:#555; font-size:11.5px; margin-top:3px; }
.cc-none { color:#999; font-size:12px; }
"""

CC_JS = r"""
document.addEventListener('DOMContentLoaded', () => {
  const D = JSON.parse(document.getElementById('cc-data').textContent);
  const $ = id => document.getElementById(id);
  const IND = Object.fromEntries(D.indicators.map(i => [i.key, i]));
  const THEME = Object.fromEntries(D.themes.map(t => [t.key, t]));
  const ticked = new Set();
  const fmt = n => n == null ? '' : n.toLocaleString('en-US');
  const el = (tag, cls, text) => { const x = document.createElement(tag); if (cls) x.className = cls;
    if (text != null) x.textContent = text; return x; };
  const SEL = {year: 'year', window: 'window', agency: 'agency', emergency: 'emergency'};

  function coderRows() { const c = $('cc-coder') ? $('cc-coder').value : D.coders[0];
    return D.rows.filter(r => r.coder === c); }
  // the select filters' options, from the rows of the chosen coder
  function fillSelects() {
    const rows = coderRows();
    for (const [id, f] of Object.entries(SEL)) {
      const s = $('cc-' + id), keep = s.value;
      const vals = [...new Set(rows.map(r => r[f]).filter(v => v != null))].sort();
      s.length = 1;
      vals.forEach(v => s.add(new Option(v, v)));
      s.value = vals.map(String).includes(keep) ? keep : '';
    }
  }
  function base() {
    const q = $('cc-q').value.trim().toLowerCase();
    return coderRows().filter(r => Object.entries(SEL).every(([id, f]) => !$('cc-' + id).value
        || String(r[f]) === $('cc-' + id).value)
      && (!q || [r.code, r.country, r.iso3, r.title, r.agency].some(v => v && v.toLowerCase().includes(q))));
  }
  const mode = () => document.querySelector('input[name=cc-mode]:checked').value;
  function matches(r) {
    if (!ticked.size) return true;
    const ys = [...ticked].map(k => r.codes[k] === 'Y');
    return mode() === 'all' ? ys.every(Boolean) : ys.some(Boolean);
  }

  function indicatorRow(i, rows) {
    const coded = rows.filter(r => r.codes[i.key] != null).length;
    const n = rows.filter(r => r.codes[i.key] === 'Y').length;
    const lab = el('label', 'cc-i' + (n ? '' : ' zero'));
    const cb = el('input'); cb.type = 'checkbox'; cb.checked = ticked.has(i.key);
    cb.addEventListener('change', () => { cb.checked ? ticked.add(i.key) : ticked.delete(i.key); render(); });
    const bar = el('span', 'bar'), fill = el('i');
    fill.style.width = coded ? (100 * n / coded) + '%' : '0';
    bar.append(fill);
    lab.title = `${n} of ${coded} coded projects: yes`;
    lab.append(cb, el('span', null, i.label), bar, el('span', 'cnt', `${n} of ${coded}`));
    return lab;
  }
  function panels(rows) {
    const g = $('cc-gate'); g.textContent = '';
    const gp = el('div', 'cc-th'); gp.append(el('h3', null, 'Climate risk'));
    gp.append(indicatorRow(IND[D.gate], rows)); g.append(gp);
    const box = $('cc-themes'); box.textContent = '';
    for (const t of D.themes) {
      const p = el('div', 'cc-th'), h = el('h3', null, t.name);
      const anyY = rows.filter(r => D.indicators.some(i => i.theme === t.key && r.codes[i.key] === 'Y')).length;
      h.append(el('span', 'n', `${anyY} with any`));
      p.append(h, el('div', 'd', t.desc));
      D.indicators.filter(i => i.theme === t.key).forEach(i => p.append(indicatorRow(i, rows)));
      box.append(p);
    }
  }
  function tiles(rows) {
    const coded = rows.filter(r => Object.keys(r.codes).length);
    const anyAct = coded.filter(r => D.indicators.some(i => i.key !== D.gate && r.codes[i.key] === 'Y'));
    const gate = coded.filter(r => r.codes[D.gate] === 'Y');
    const t = $('cc-tiles'); t.textContent = '';
    const blank = rows.filter(r => !Object.keys(r.codes).length).map(r => r.code);
    $('cc-blank').textContent = blank.length ? `Listed but not coded: ${blank.join(', ')}.` : '';
    [[coded.length, 'projects coded'], [anyAct.length, 'with at least one indicator coded yes'],
     [gate.length, 'mention climate risk or impacts']].forEach(([v, l]) => {
      const d = el('div', 'tile'); d.append(el('div', 'v', fmt(v)), el('div', 'l', l)); t.append(d); });
  }
  function table(rows) {
    const tb = $('cc-body'); tb.textContent = '';
    for (const r of rows) {
      const tr = el('tr');
      [r.code, r.year, r.country || (r.mirror ? '' : 'not in the CERF data'), r.agency, r.emergency, r.title]
        .forEach(v => tr.append(el('td', null, v == null ? '' : v)));
      tr.append(el('td', 'num', fmt(r.amount)));
      const td = el('td');
      const ys = D.indicators.filter(i => r.codes[i.key] === 'Y');
      if (!Object.keys(r.codes).length) td.append(el('span', 'cc-none', 'not coded'));
      else if (!ys.length) td.append(el('span', 'cc-none', 'none'));
      // one tag per area: its name, how many of its indicators are coded yes, the list on hover
      const byTheme = new Map();
      ys.forEach(i => byTheme.set(i.theme, (byTheme.get(i.theme) || []).concat(i)));
      byTheme.forEach((is, t) => {
        const unsure = is.some(i => r.unc.includes(i.key));
        const tag = el('span', 'cc-tag' + (t === 'gate' ? ' gate' : ''),
          (t === 'gate' ? 'climate risk' : THEME[t].name) + (is.length > 1 ? ` ×${is.length}` : '') + (unsure ? ' (?)' : ''));
        tag.title = is.map(i => i.label + (r.unc.includes(i.key) ? ' (unsure)' : '')).join('\n'); td.append(tag);
      });
      Object.entries(r.notes).forEach(([k, v]) => td.append(el('div', 'cc-note', `${IND[k] ? IND[k].label : k}: ${v}`)));
      tr.append(td); tb.append(tr);
    }
  }
  let shown = [];
  function render() {
    const b = base();
    shown = b.filter(r => matches(r) && (!ticked.size || Object.keys(r.codes).length));
    tiles(b); panels(b); table(shown);
    const amt = shown.reduce((s, r) => s + (r.amount || 0), 0);
    $('cc-count').textContent = `${shown.length} of ${b.length} projects · US$ ${fmt(amt)} approved`
      + (ticked.size ? ` · coded yes on ${mode() === 'all' ? 'all' : 'any'} of ${ticked.size} ticked indicator${ticked.size > 1 ? 's' : ''}` : '');
  }
  $('cc-csv').addEventListener('click', () => {
    const cols = ['code', 'coder', 'year', 'iso3', 'country', 'window', 'agency', 'emergency', 'title', 'amount'];
    const q = v => { const s = v == null ? '' : String(v); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
    const lines = [cols.concat(D.indicators.map(i => i.key), ['uncertain', 'notes']).join(',')];
    shown.forEach(r => lines.push(cols.map(c => q(r[c])).concat(D.indicators.map(i => q(r.codes[i.key])),
      [q(r.unc.join(' ')), q(Object.entries(r.notes).map(([k, v]) => k + ': ' + v).join(' | '))]).join(',')));
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([lines.join('\n')], {type: 'text/csv;charset=utf-8'}));
    a.download = 'cerf_climate_coding.csv'; a.click(); URL.revokeObjectURL(a.href);
  });
  ['cc-year', 'cc-window', 'cc-agency', 'cc-emergency'].forEach(id => $(id).addEventListener('change', render));
  $('cc-q').addEventListener('input', render);
  document.querySelectorAll('input[name=cc-mode]').forEach(x => x.addEventListener('change', render));
  if ($('cc-coder')) $('cc-coder').addEventListener('change', () => { fillSelects(); render(); });
  $('cc-reset').addEventListener('click', () => {
    ticked.clear(); $('cc-q').value = '';
    Object.keys(SEL).forEach(id => { $('cc-' + id).value = ''; });
    document.querySelector('input[name=cc-mode][value=any]').checked = true; render();
  });
  fillSelects(); render();
});
"""
