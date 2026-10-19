"""Two UNLISTED public pages on CERF projects coded against climate-adaptation indicators.

- climate-adaptation.html: the projects coded by hand (by people), filterable by indicator.
- climate-coding-accuracy.html: how closely automated passes (coders named model-*)
  reproduce the hand coding, run by run and project by project.

Both sit behind the public site's password like the tabs, but no tab and no other page links
to them (build_site.UNLISTED_TABS); they link only to each other.

The codes are aa.cerf_climate_coding (one row per project x indicator x coder, loaded from
the coding workbooks by scripts/import_climate_coding.py, and from the model runs' outputs);
everything else about a project (year, country, agency, emergency, title, amount) is the
CERF mirror, aa.cerf_project. The hand-coding page shows only what was coded and the
coders' own notes; the accuracy page also shows each model's evidence, a short quote from
the proposal for every yes.

INDICATORS is the coding sheet's framework, worded for reading: one gate question (does
the proposal mention current climate risk or future impacts?) and the activity indicators
in seven areas. The keys are the ones the coding table stores."""

import html
import json

import pandas as pd

from dashboards import DASH_CSS

PAGE = "climate-adaptation.html"
TITLE = "Climate adaptation in CERF projects"
ACC_PAGE = "climate-coding-accuracy.html"
ACC_TITLE = "Climate coding: can a model reproduce it?"

# the hand coder the accuracy page scores the models against; if absent, the human coder
# with the most answers (with a warning)
REF_CODER = "Nico"
# the automated passes the accuracy page knows, in the order it shows them: coded_by, name,
# what the model was given. A model-* coder not listed here is shown last, under its key.
RUNS = [
    ("model-blind-summary", "Blind, from the summaries",
     "Only the indicator wording and each project's summary (the text the hand coder read). "
     "It never saw the hand coder's answers."),
    ("model-blind-full-proposal", "Blind, from the full proposals",
     "As above, but reading the whole proposal instead of the summary."),
    ("model-held-out", "Learned from the other half",
     "The coded projects were split into two halves. From one half's summaries and the hand "
     "coder's answers the model wrote down the coder's rules, then coded the other half with those "
     "rules without seeing the answers there; then the halves swapped. The fair estimate for "
     "projects not yet coded."),
    ("model-in-sample", "Learned from all (in-sample)",
     "Rules written from all the coded projects, applied back to the same projects: how closely the "
     "rules can reproduce the hand coding at best. It overstates accuracy on new projects."),
]

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
    """Both pages (each says so when it has nothing to show)."""
    exists = pd.read_sql("SELECT to_regclass('aa.cerf_climate_coding') AS r", e)["r"].iloc[0]
    df = pd.read_sql(SQL, e) if exists is not None else pd.DataFrame()
    if df.empty:
        page(PAGE, TITLE, f"<style>{DASH_CSS}</style><div class='card'>No coded projects loaded yet: "
             "the codes arrive through a data-entry file (scripts/import_climate_coding.py).</div>")
        build_accuracy(df, page)
        return
    unknown = sorted(set(df["indicator"]) - KEYS)
    if unknown:
        print(f"::warning::{PAGE}: indicator keys not in page_climate.INDICATORS ignored: {', '.join(unknown)}")
        df = df[df["indicator"].isin(KEYS)]
    if df.empty:
        page(PAGE, TITLE, f"<style>{DASH_CSS}</style><div class='card'>No coded projects loaded yet.</div>")
        build_accuracy(df, page)
        return
    build_accuracy(df, page)
    df = df[~df["coded_by"].str.startswith("model-")]    # this page: the hand coding only
    if df.empty:
        page(PAGE, TITLE, f"<style>{DASH_CSS}</style><div class='card'>No hand-coded projects loaded yet. "
             f"The model runs are on <a href='{ACC_PAGE}'>their own page</a>.</div>")
        return
    rows = _rows(df)
    coders = sorted({r["coder"] for r in rows})
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
How closely a model reproduces this coding: <a href='{ACC_PAGE}'>model accuracy</a>.
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


# ------------------------------------------------------------------ accuracy page
def _kappa(pairs):
    """Cohen's kappa over (reference, model) Y/N pairs; None when chance agreement is total."""
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    pe = sum(sum(a == v for a, _ in pairs) * sum(b == v for _, b in pairs) for v in ("Y", "N")) / n / n
    return None if pe == 1 else (po - pe) / (1 - pe)


def _score(ref, run):
    """Every answer the reference coder gave, against the run's answer for the same cell."""
    pairs, gate, anyp = [], [], []
    for code, rc in ref.items():
        mc = run.get(code)
        if not mc:
            continue
        pairs += [(rc[k], mc[k]) for k in rc if k in mc]
        if GATE in rc and GATE in mc:
            gate.append((rc[GATE], mc[GATE]))
        anyp.append((any(v == "Y" for k, v in rc.items() if k != GATE),
                     any(v == "Y" for k, v in mc.items() if k != GATE and k in rc)))
    both = sum(a == b == "Y" for a, b in pairs)
    ref_y, run_y = sum(a == "Y" for a, _ in pairs), sum(b == "Y" for _, b in pairs)
    return {"projects": len(anyp), "cells": len(pairs), "agree": sum(a == b for a, b in pairs),
            "kappa": _kappa(pairs), "ref_y": ref_y, "run_y": run_y, "both": both,
            "precision": both / run_y if run_y else None, "recall": both / ref_y if ref_y else None,
            "gate_kappa": _kappa(gate), "gate_agree": sum(a == b for a, b in gate), "gate_n": len(gate),
            "any_agree": sum(a == b for a, b in anyp)}


def _pct(v):
    return "—" if v is None else f"{v:.0%}"


def _k(v):
    return "—" if v is None else f"{v:.2f}"


def build_accuracy(df, page):
    """climate-coding-accuracy.html: each model-* coder against the hand coder."""
    coders = sorted(set(df["coded_by"])) if not df.empty else []
    humans = [c for c in coders if not c.startswith("model-")]
    models = [c for c in coders if c.startswith("model-")]
    if not humans or not models:
        missing = "No model runs" if humans else "No hand coding to compare with" if models else "No coding"
        page(ACC_PAGE, ACC_TITLE, f"<style>{DASH_CSS}</style><div class='card'>{missing} loaded yet. "
             f"The hand coding is on <a href='{PAGE}'>its own page</a>.</div>")
        return
    if REF_CODER in humans:
        ref_coder = REF_CODER
    else:
        ref_coder = max(humans, key=lambda c: int(((df["coded_by"] == c) & df["value"].notna()).sum()))
        print(f"::warning::{ACC_PAGE}: reference coder {REF_CODER!r} not found; scoring against {ref_coder!r}")
    known = [k for k, _, _ in RUNS]
    runs = [(k, n, d) for k, n, d in RUNS if k in models] + [(m, m, "") for m in models if m not in known]
    rows = _rows(df)
    by = {(r["code"], r["coder"]): r for r in rows}
    ref = {r["code"]: r["codes"] for r in rows if r["coder"] == ref_coder and r["codes"]}
    run_codes = {k: {r["code"]: r["codes"] for r in rows if r["coder"] == k and r["codes"]} for k, _, _ in runs}
    scores = {k: _score(ref, run_codes[k]) for k, _, _ in runs}

    head = "".join(f"<th>{_e(n)}</th>" for _, n, _ in runs)
    score_rows = "".join(
        f"<tr><td><b>{_e(n)}</b><div class='acc-d'>{_e(d)}</div></td>"
        f"<td class='num'>{s['projects']}</td><td class='num'><b>{_k(s['kappa'])}</b></td>"
        f"<td class='num'>{_pct(s['precision'])}</td><td class='num'>{_pct(s['recall'])}</td>"
        f"<td class='num'>{s['run_y']} / {s['both']}</td>"
        f"<td class='num'>{_pct(s['agree'] / s['cells'] if s['cells'] else None)}</td>"
        f"<td class='num'>{_k(s['gate_kappa'])} ({s['gate_agree']} of {s['gate_n']})</td>"
        f"<td class='num'>{s['any_agree']} of {s['projects']}</td></tr>"
        for (k, n, d), s in ((r, scores[r[0]]) for r in runs))
    any_ref = sum(any(v == "Y" for kk, v in c.items() if kk != GATE) for c in ref.values())
    n_ref_y = sum(v == "Y" for c in ref.values() for v in c.values())
    n_ref = sum(len(c) for c in ref.values())

    theme_name = {k: n for k, n, _ in THEMES} | {"gate": "Climate risk"}
    ind_rows = []
    for key, theme, label in INDICATORS:
        ry = sum(c.get(key) == "Y" for c in ref.values())
        answered = [c for c in ref if key in ref[c]]       # cells the hand coder answered
        counts = [(sum(run_codes[k].get(c, {}).get(key) == "Y" for c in answered),
                   sum(ref[c][key] == "Y" and run_codes[k].get(c, {}).get(key) == "Y" for c in answered))
                  for k, _, _ in runs]
        zero = " class='zero'" if not ry and not any(my for my, _ in counts) else ""
        ind_rows.append(f"<tr{zero}><td>{_e(theme_name[theme])}</td><td>{_e(label)}</td>"
                        f"<td class='num'><b>{ry}</b></td>"
                        + "".join(f"<td class='num'>{my} / {both}</td>" for my, both in counts) + "</tr>")

    projects = []
    for code in sorted({r["code"] for r in rows}):
        r0 = by.get((code, ref_coder)) or next(r for r in rows if r["code"] == code)
        projects.append({
            "code": code, "year": r0["year"], "country": r0["country"], "agency": r0["agency"],
            "emergency": r0["emergency"], "title": r0["title"],
            "ref": ref.get(code, {}), "ref_notes": (by.get((code, ref_coder)) or {}).get("notes", {}),
            "runs": {k: {"codes": by[(code, k)]["codes"], "notes": by[(code, k)]["notes"]}
                     for k, _, _ in runs if (code, k) in by},
        })
    data = {"indicators": [{"key": k, "theme": theme_name[t], "label": lab} for k, t, lab in INDICATORS],
            "runs": [{"key": k, "name": n} for k, n, _ in runs], "ref": ref_coder, "projects": projects}
    payload = json.dumps(data, ensure_ascii=False, default=str, allow_nan=False).replace("<", "\\u003c")
    default = "model-held-out" if "model-held-out" in run_codes else runs[0][0]
    opts = "".join(f"<option value='{_e(k)}'{' selected' if k == default else ''}>{_e(n)}</option>"
                   for k, n, _ in runs)

    body = f"""
<div class='card'><b>Unlisted page, work in progress.</b> Can a model code CERF proposals the way
{_e(ref_coder)} did? The model (Claude) coded the same projects in {len(runs)} ways, and every answer is compared with
{_e(ref_coder)}'s: {len(ref)} hand-coded projects, {n_ref_y} answers <i>yes</i> out of
{n_ref:,}. The hand coding itself, with its filters, is on <a href='{PAGE}'>its own page</a>.
<p class='meta' style='margin:8px 0 0'>Under {_e(ref_coder)}'s reading, {any_ref} of the {len(ref)} projects have at
least one activity indicator coded yes: most indicators are read as broad humanitarian categories (any disease
work, any psychosocial support, any food or cash), not only climate-related activity.</p></div>

<h2>Run by run</h2>
<p class='meta'><b>Kappa</b>: agreement with {_e(ref_coder)} beyond what chance would give (1 = the same answers,
0 = no better than chance); the number to read, since most answers are <i>no</i> for everyone and plain agreement
is high whatever happens. <b>Precision</b>: of the model's yes answers, the share {_e(ref_coder)} also gave.
<b>Recall</b>: of {_e(ref_coder)}'s yes answers, the share the model found.</p>
<div class='scroll' style='max-height:none'><table class='data acc-runs'><thead><tr>
 <th>Run</th><th>Projects</th><th>Kappa</th><th>Precision</th><th>Recall</th><th>Model yes / both yes</th>
 <th>Answers agreeing</th><th>Climate-risk question: kappa (agree)</th><th>"At least one yes" agrees</th>
</tr></thead><tbody>{score_rows}</tbody></table></div>

<h2>Indicator by indicator</h2>
<p class='meta'>How many projects each coder said <i>yes</i> on: {_e(ref_coder)}, then for each run the model's
yes answers / those {_e(ref_coder)} also gave (counted where {_e(ref_coder)} answered). Indicators with only a few yes answers cannot be learned or scored
from this sample.</p>
<div class='scroll'><table class='data acc-ind'><thead><tr><th>Area</th><th>Indicator</th>
 <th>{_e(ref_coder)}</th>{head}</tr></thead><tbody>{''.join(ind_rows)}</tbody></table></div>

<h2 id='acc-h'>Project by project</h2>
<div class='fbar'>
 <label>Run <select id='acc-run'>{opts}</select></label>
 <label><input type='checkbox' id='acc-diff'> only projects where this run disagrees</label>
 <input id='acc-q' type='search' placeholder='search code, country, title…' aria-label='Search projects'>
 <span id='acc-count' class='meta'></span>
</div>
<p class='meta'>Click a project to see every answer side by side, and why the model said yes: its evidence,
quoted from the proposal. <span class='acc-key extra'>extra</span> the model said yes, {_e(ref_coder)} no.
<span class='acc-key miss'>missed</span> {_e(ref_coder)} said yes, the model no.</p>
<div class='scroll'><table class='data acc-proj'><thead><tr><th>Project</th><th>Country</th><th>Emergency</th>
 <th>Title</th><th>{_e(ref_coder)}: yes</th>{"".join(f"<th>{_e(n)}: differs</th>" for _, n, _ in runs)}</tr></thead>
 <tbody id='acc-body'></tbody></table></div>

<script type='application/json' id='acc-data'>{payload}</script>
<style>{DASH_CSS}{ACC_CSS}</style><script>{ACC_JS}</script>"""
    page(ACC_PAGE, ACC_TITLE, body)


ACC_CSS = """
.acc-runs td, .acc-ind td { vertical-align:top; }
.acc-d { color:var(--muted); font-size:11.5px; max-width:460px; margin-top:2px; }
td.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
.acc-ind tr.zero td { color:#aaa; }
.acc-proj tr.p { cursor:pointer; }
.acc-proj tr.p.open td { background:#eef4fb; }
.acc-proj td.sel { font-weight:700; }
.acc-proj td.bad { color:#a11; }
.acc-key { display:inline-block; padding:0 6px; border-radius:4px; font-size:11.5px; }
.extra { background:#fff1cc; } .miss { background:#fde3e3; }
.acc-det { padding:8px 4px 12px; }
.acc-mx { border-collapse:collapse; font-size:12px; margin:4px 0 10px; }
.acc-mx th, .acc-mx td { border:1px solid #e3e7ec; padding:3px 8px; text-align:center; }
.acc-mx th { background:#f4f6f9; font-weight:600; }
.acc-mx td.lab { text-align:left; max-width:340px; }
.acc-mx td.lab .a { color:var(--muted); font-size:11px; }
.acc-mx th.sel, .acc-mx td.sel { outline:2px solid var(--accent); outline-offset:-2px; }
.acc-ev { font-size:12px; margin:2px 0 0; padding-left:18px; }
.acc-ev li { margin:3px 0; }
"""

ACC_JS = r"""
document.addEventListener('DOMContentLoaded', () => {
  const D = JSON.parse(document.getElementById('acc-data').textContent);
  const $ = id => document.getElementById(id);
  const IND = Object.fromEntries(D.indicators.map(i => [i.key, i]));
  const el = (tag, cls, text) => { const x = document.createElement(tag); if (cls) x.className = cls;
    if (text != null) x.textContent = text; return x; };
  const open = new Set();
  const codes = (p, k) => (p.runs[k] || {}).codes || {};
  // indicators where the run and the hand coder both answered and differ
  const diffs = (p, k) => { const r = codes(p, k);
    return D.indicators.filter(i => p.ref[i.key] && r[i.key] && p.ref[i.key] !== r[i.key]); };
  const yes = c => D.indicators.filter(i => c[i.key] === 'Y').length;

  function detail(p, run) {
    const box = el('div', 'acc-det');
    const shown = D.indicators.filter(i => p.ref[i.key] === 'Y'
      || D.runs.some(r => codes(p, r.key)[i.key] === 'Y'));
    if (!shown.length) { box.append(el('div', 'meta', 'Every coder answered no on every indicator.')); return box; }
    const t = el('table', 'acc-mx'), hr = el('tr');
    hr.append(el('th', null, 'Indicator'), el('th', null, D.ref));
    D.runs.forEach(r => hr.append(el('th', r.key === run ? 'sel' : null, r.name)));
    t.append(hr);
    for (const i of shown) {
      const tr = el('tr'), lab = el('td', 'lab');
      lab.append(el('div', 'a', i.theme), el('div', null, i.label)); tr.append(lab);
      tr.append(el('td', null, p.ref[i.key] || '–'));
      D.runs.forEach(r => {
        const v = codes(p, r.key)[i.key], ref = p.ref[i.key];
        const cls = [r.key === run ? 'sel' : '', ref && v && v !== ref ? (v === 'Y' ? 'extra' : 'miss') : ''].join(' ').trim();
        const td = el('td', cls || null, v || '–');
        const ev = ((p.runs[r.key] || {}).notes || {})[i.key];
        if (ev) td.title = ev;
        tr.append(td);
      });
      t.append(tr);
    }
    box.append(t);
    const notes = Object.entries(p.ref_notes || {});
    if (notes.length) {
      box.append(el('div', 'meta', `${D.ref}'s notes:`));
      const ul = el('ul', 'acc-ev');
      notes.forEach(([k, v]) => { const li = el('li'); li.append(el('b', null, (IND[k] || {label: k}).label + ': '), el('span', null, v)); ul.append(li); });
      box.append(ul);
    }
    // the model's note on a yes is its evidence
    const ev = Object.entries(((p.runs[run] || {}).notes) || {}).filter(([k]) => codes(p, run)[k] === 'Y');
    const rn = (D.runs.find(r => r.key === run) || {}).name;
    box.append(el('div', 'meta', ev.length ? `Why the model said yes (${rn}), quoted from the proposal:` : `No evidence recorded for ${rn}.`));
    const ul = el('ul', 'acc-ev');
    ev.forEach(([k, v]) => { const li = el('li'); li.append(el('b', null, (IND[k] || {label: k}).label + ': '), el('span', null, v)); ul.append(li); });
    box.append(ul);
    return box;
  }

  function render() {
    const run = $('acc-run').value, only = $('acc-diff').checked, q = $('acc-q').value.trim().toLowerCase();
    const list = D.projects.filter(p => (!only || diffs(p, run).length)
      && (!q || [p.code, p.country, p.title, p.agency].some(v => v && v.toLowerCase().includes(q))));
    const tb = $('acc-body'); tb.textContent = '';
    for (const p of list) {
      const tr = el('tr', 'p' + (open.has(p.code) ? ' open' : ''));
      [p.code, p.country, p.emergency, p.title].forEach(v => tr.append(el('td', null, v || '')));
      tr.append(el('td', 'num', Object.keys(p.ref).length ? String(yes(p.ref)) : 'not coded'));
      D.runs.forEach(r => {
        const has = p.runs[r.key] && Object.keys(p.ref).length, n = has ? diffs(p, r.key).length : null;
        tr.append(el('td', 'num' + (r.key === run ? ' sel' : '') + (n ? ' bad' : ''), n == null ? '–' : String(n)));
      });
      tr.addEventListener('click', () => { open.has(p.code) ? open.delete(p.code) : open.add(p.code); render(); });
      tb.append(tr);
      if (open.has(p.code)) {
        const dr = el('tr'), td = el('td'); td.colSpan = 5 + D.runs.length;
        td.append(detail(p, run)); dr.append(td); tb.append(dr);
      }
    }
    $('acc-count').textContent = `${list.length} of ${D.projects.length} projects`;
  }
  $('acc-run').addEventListener('change', render);
  $('acc-diff').addEventListener('change', render);
  $('acc-q').addEventListener('input', render);
  render();
});
"""
