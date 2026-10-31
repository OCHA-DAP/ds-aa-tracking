"""Interactive dashboards + per-framework pages for the review site.

Built to answer the CERF "AA Datasets" key-data-points list (Oct 2025 deck, updated
Aug 2026) — see questions.html for the item-by-item coverage map. Charts are Chart.js
(inlined local asset, no CDN) over row-level JSON embedded in each page, so every
chart is client-side filterable (hazard / region / fund / year). Chart styling
follows the team dataviz method: fixed categorical order (validated palette), one
axis, thin rounded marks, recessive grids, tooltips everywhere.

Canonical values: where sources disagree, dashboards use one canonical row per fact
(source-priority pick, latest CERF sheet first) — the disagreements themselves stay
on the reconciliation pages.
"""

import json
import re

import site_i18n as i18n  # noqa: E402  (EN / FR / ES, the team mechanism: scripts/site_i18n.py)
from site_i18n import ATTR, ATTRC, OPT, T, TB, TBC, TBF, TC, TD, TF  # noqa: E402

import pandas as pd

# validated reference palette (light mode), fixed assignment order
PAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
FUND_COLORS = {"cerf": "#2a78d6", "cbpf": "#eb6834", "regional_fund": "#1baf7a"}
# a fund type in words (chart legends): the type is a code, never shown
FUND_TYPE_LABEL = {"cerf": "CERF", "cbpf": "Country funds", "regional_fund": "Regional funds"}
HAZARDS = ["drought", "flood", "storm", "cholera"]  # fixed order; rest -> Other

# ---------------------------------------------------------------- codes as words
# No code is shown on the public site (owner, 2026-10-27: no table or column names, no raw
# status / hazard / event codes): each vocabulary has its words here. code_words() gives the
# words of a code, or None for a code with none — left out of the page (never shown as it is)
# and named in the build log so words get added. build_site's identifier guard stops a build
# whose public pages show one anyway.
EVENT_TYPE_LABEL = {"framework_aa": "framework activation", "adhoc_aa": "non-framework allocation",
                    "early_action": "early-action allocation"}
# the external reports a framework counts toward (aa.report_channel_inclusion.channel)
REPORT_CHANNEL_LABEL = {
    "anticipation_hub": "Anticipation Hub", "cerf_annual_report": "CERF annual report",
    "ocha_annual_report": "OCHA annual report", "ocha_sf_kpi": "OCHA SF KPI",
    "sg_natural_disasters": "SG report on natural disasters", "sg_report": "SG report",
    "uk_baseline": "UK baseline", "uk_joint_humanitarian_bc": "UK joint humanitarian business case",
    "uk_cerf_bc": "UK CERF business case", "cpc": "CPC"}
# where a version record came from (aa.framework_version.source); 'aa-team-<date>' = the team's
# own records of that day
VERSION_SOURCE_LABEL = {"entered": "data entry", "ocha-web": "OCHA AA web page",
                        "pa-monorepo": "team analysis repository", "aa-team": "AA team records"}
# a partner's role in a framework document, when it is a code (the documents' own words are
# shown as written)
PARTNER_ROLE_LABEL = {"implementing": "implementing", "technical": "technical",
                      "coordination": "coordination", "funding": "funding",
                      "government_counterpart": "government counterpart", "sub_grantee": "sub-grantee"}
# a hazard as a word inside a sentence or a name ('Niger — drought')
HAZARD_WORD = {"drought": "drought", "flood": "flood", "storm": "storm", "cholera": "cholera",
               "plague": "plague", "locusts": "locusts", "food_insecurity": "food insecurity",
               "other": "other hazard"}
_UNLABELLED = set()


def code_words(vocab, code, what="code"):
    """The words of a code from one of the vocabularies above; None (and a build-log line,
    once) for a code with none."""
    if code is None or (not isinstance(code, str) and pd.isna(code)):
        return None
    if code in vocab:
        return vocab[code]
    if (what, code) not in _UNLABELLED:
        _UNLABELLED.add((what, code))
        print(f"  ! {what} without words (left out of the page): {code}")
    return None


def fund_label(fc):
    """A fund as the pages name it ('CERF', 'CBPF AFG', 'RHPF ESA UGA'; the map's form), never its
    code; a financier recorded in words (an agency's co-financing) is shown as written."""
    if not isinstance(fc, str) or not fc:
        return ""
    if fc == "cerf":
        return "CERF"
    if fc == "cbpf-unspecified":
        return "CBPF"
    if re.fullmatch(r"(cbpf|rhpf)(-[a-z]+)+", fc):
        return fc.upper().replace("-", " ")
    return fc


def hazard_word(h):
    """A hazard as a word ('food insecurity'); an unlabelled one is 'other hazard', never its code."""
    return code_words(HAZARD_WORD, h, "hazard") or "other hazard"

def current_source(s):
    """A source label as the database names it after D168 (julia-* -> aa-workbook-*, yakubu-*
    -> cerf-workbook-*, kb-frontmatter -> aa-team). A snapshot taken before the one-off
    scripts/drop_leftovers.py run still carries the old labels; drop this with the KB renames."""
    if not isinstance(s, str):
        return s
    if s == "kb-frontmatter":
        return "aa-team"
    return re.sub(r"^yakubu-", "cerf-workbook-", re.sub(r"^julia-", "aa-workbook-", s))


SOURCE_PRIORITY = [
    "cerf-workbook-prearranged-jun2026", "cerf-workbook-cofinancing-jun2026",
    "aa-workbook-planning-2026", "aa-workbook-reporting-2025", "cerf-workbook-insurance-2026",
    "aa-workbook-gho-2026", "cerf-workbook-new-extended-2025",
]


# Early-action (EA) allocations are kept in the database but never shown or counted on the
# site (decision 2026-09-30, a colleague's review: EA "opens a Pandora's box"). One place:
# every activation query filters on this. Remove the value to bring EA back.
EXCLUDED_EVENT_TYPES = ("early_action",)
_EXCL_SQL = ", ".join(f"'{t}'" for t in EXCLUDED_EVENT_TYPES)
# The CERF AA allocations the site counts: the ones the activation record draws on (framework
# and ad hoc; early action excluded), as the Financing page counts them — not the mirror's
# title keyword (aa_keyword), which also flags early-action allocations and misses ad hoc AA
# with a plain title (2026-10-02 meeting: released by agency and by sector did not match the
# curated figures). An activation whose CERF allocation code is not recorded yet cannot be
# split; the Delivery page lists those.
_CERF_AA_CODES_SQL = ("SELECT DISTINCT allocation_code FROM aa.activation_funding "
                      "WHERE fund_code = 'cerf' AND allocation_code IS NOT NULL "
                      "AND event_type NOT IN (" + _EXCL_SQL + ")")
# ... of which the framework activations' (ad hoc allocations left out): the Plan page's set, and
# the map's by default (2026-10-14: the headline figures are framework-based)
CERF_FW_CODES_SQL = _CERF_AA_CODES_SQL + " AND event_type <> 'adhoc_aa'"
# A post on X/Twitter is not a learning document (two crossed over from the compendium; they
# belong on the media page): every query of aa.learning_document the site renders adds this,
# the Learning page's and the map's per-country lists alike (2026-10-23)
NOT_SOCIAL_SQL = r"coalesce(url, '') !~* '^https?://([a-z]+\.)?(x|twitter)\.com/|^https?://t\.co/'"


def canonical(df, keys):
    """One row per key-combo by source priority (dashboard view; conflicts live on
    the admin page)."""
    df = df.copy()
    df["_p"] = df["source"].map(current_source).map(
        {s: i for i, s in enumerate(SOURCE_PRIORITY)}).fillna(99)
    return (df.sort_values("_p").drop_duplicates(subset=keys, keep="first")
            .drop(columns="_p"))


DASH_CSS = """
td.na { background:#eef1f5; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr)); gap:16px; }   /* min(): never wider than a phone */
/* a phone: the money flow keeps a readable size and scrolls sideways in its box; the activations table too */
@media (max-width:760px){ #flow { overflow-x:auto; } #flow svg.sk { min-width:1000px; } }
table.data.acts { min-width:560px; } table.data.acts td:first-child { white-space:nowrap; }
.panel { background:#fff; border:1px solid #e0e0e0; border-radius:6px; padding:14px 16px; min-width:0; overflow:hidden; }
.panel h3 { margin:2px 0 10px; font-size:14.5px; }
.panel .note { color:#666; font-size:11.5px; margin-top:6px; }
/* tiles in even rows, as on the Map (owner, 2026-10-28): as many equal columns as fit */
.tiles { display:grid; grid-template-columns:repeat(auto-fit, minmax(210px, 1fr)); gap:14px; margin:12px 0; }
.tile { background:#fff; border:1px solid #e0e0e0; border-radius:6px; padding:12px 18px; min-width:0; }
@media (max-width:759px) { .tiles { grid-template-columns:repeat(2, minmax(0, 1fr)); gap:8px; } .tile { padding:10px 12px; } }
.tile .v { font-size:22px; font-weight:700; }
.tile .l { font-size:12px; color:#666; }
.tile .l ul.tb { margin:4px 0 0; padding:0 0 0 15px; } .tile .l ul.tb li { margin:0; }   /* a tile's breakdown, as on the Map */
.fbar { display:flex; gap:10px; flex-wrap:wrap; align-items:center; background:#fff;
        border:1px solid #e0e0e0; border-radius:6px; padding:10px 14px; margin:12px 0;
        position:sticky; top:0; z-index:5; }
.fbar label { font-size:12px; color:#555; }
/* the Financing filter bar stands out (2026-10-16 review: people skip over it) */
.fbar.hi { background:#eef4fb; border:2px solid #1f69b3; box-shadow:0 2px 6px rgba(31,105,179,.15); }
.fbar.hi .fbar-t { font-weight:700; font-size:13px; color:#1f69b3; margin-right:4px; }
.fbar.hi label { font-size:13px; color:#222; }
.fbar select { padding:4px 8px; border:1px solid #bbb; border-radius:4px; font-size:12.5px; }
/* the framework picker (Financing): a list that drops from the filter bar (the bar is sticky,
   so the list anchors to it and stays in view) */
.fwpick > summary { cursor:pointer; list-style:none; font-size:12.5px; padding:4px 9px; border:1px solid #bbb;
                    border-radius:4px; white-space:nowrap; }
.fwpick > summary::-webkit-details-marker { display:none; }
.fwpick.on > summary { border-color:var(--accent); background:#eaf4ff; color:#0b4f8a; font-weight:600; }
.fwpanel { position:absolute; left:10px; top:calc(100% + 4px); width:min(620px, calc(100vw - 40px));
           max-height:60vh; display:flex; flex-direction:column; background:#fff;
           border:1px solid #cbd5e1; border-radius:8px; box-shadow:0 8px 24px rgba(0,0,0,.18); z-index:20; }
.fwhead { display:flex; gap:8px; align-items:center; padding:10px 12px; border-bottom:1px solid #e6e9ee; }
.fwhead input { flex:1; min-width:0; padding:5px 8px; border:1px solid #bbb; border-radius:4px; font-size:12.5px; }
.fbar .freset { margin-left:auto; padding:4px 10px; border:1px solid #1f69b3; border-radius:4px; background:#fff;
                 color:#1f69b3; font-size:12.5px; font-weight:600; cursor:pointer; white-space:nowrap; }
.fbar .freset:hover { background:#1f69b3; color:#fff; }
.fwhead button, .fwnote button { padding:4px 9px; border:1px solid #bbb; border-radius:4px; background:#f7f8fa;
                                 font-size:12px; cursor:pointer; white-space:nowrap; }
.fwlist { overflow-y:auto; padding:4px 12px 8px; }
.fwlist label { display:flex; gap:8px; align-items:baseline; padding:2px 0; font-size:12.5px; color:#1a1a1a; cursor:pointer; }
.fwlist label.grp { font-weight:600; margin-top:8px; padding-bottom:3px; border-bottom:1px solid #eef0f3; }
.fwlist label.off { opacity:.45; }
.fwlist .nm { flex:1; min-width:0; } .fwlist .st { color:#667; font-size:11.5px; white-space:nowrap; }
.fwlist .amt { min-width:92px; text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
.fwlist .cap { text-align:right; font-size:11px; color:#5f6470; padding-top:5px; }
.fwsum { padding:9px 12px; border-top:1px solid #e6e9ee; font-size:12.5px; background:#f7f9fc; border-radius:0 0 8px 8px; }
.fwnote { font-size:12.5px; color:#0b4f8a; background:#eaf4ff; border:1px solid #c5def5; border-radius:6px;
          padding:7px 12px; margin:0 0 8px; }
canvas { max-height:300px; }
.cal { border-collapse:collapse; font-size:11px; }
.cal td, .cal th { border:1px solid #eee; padding:2px 5px; text-align:center; }
.cal td.on, table.data tr:hover td.on { background:#1baf7a; }   /* the row hover must not wipe the months */
.covered { color:#1c6b31; font-weight:600; } .partial { color:#8a5c0a; font-weight:600; }
.missing { color:#a11; font-weight:600; }
.doctag { display:inline-block; padding:0 7px; border-radius:9px; font-size:10.5px; font-weight:600;
          background:#e8e8f8; color:#3b3b8f; margin-left:4px; white-space:nowrap; }
.warn-tag { display:inline-block; padding:0 7px; border-radius:9px; font-size:10.5px; font-weight:600;
            background:#fde3e3; color:#a11; margin-left:6px; }
ul.doclist { list-style:none; padding:0; margin:6px 0; }
ul.doclist li { padding:5px 0; border-bottom:1px solid #f0f0f0; font-size:13px; overflow-wrap:anywhere; }   /* long code references */
ul.doclist li:last-child { border-bottom:0; }
ul.doclist .ks { display:block; color:#555; font-size:11.5px; margin-top:2px; }
ul.doclist .who { color:#666; font-size:12px; }
.headline { background:#f3f8ff; border-left:3px solid #2a78d6; padding:8px 12px 8px 26px; margin:6px 0 10px;
            border-radius:4px; }
.headline li { font-size:13px; margin:3px 0; }
.headline li .src { color:#666; font-size:11.5px; }
.dot { display:inline-block; width:12px; height:12px; border-radius:50%; vertical-align:middle; margin:0 2px; }
.dot.real { background:#e3322d; box-shadow:0 0 0 2px #fff, 0 0 0 3.5px #e3322d; margin:0 4px; }
.dot.old { background:#fff; border:2px solid #e3322d; width:10px; height:10px; }
table.data.hist { width:auto; table-layout:auto; }   /* compact: year | wt1 | wt2, not spread over the panel */
table.hist td, table.hist th { text-align:center; padding:3px 10px; white-space:nowrap; min-width:44px; }
table.hist thead th { white-space:normal; max-width:140px; }   /* long window names wrap, never widen the grid */
table.hist td.yr, table.hist th:first-child { text-align:left; }
table.hist tbody tr:nth-child(even) { background:#fafbfc; }
table.hist td.use, table.data tr:hover td.use { background:#fbf6ee; }
.usetag { display:inline-block; padding:0 6px; border-radius:8px; font-size:10px; font-weight:600;
          background:#f6ead3; color:#7a5a17; margin-left:4px; vertical-align:1px; }
.sw.use, p.legend .sw.use { display:inline-block; width:14px; height:12px; background:#fbf6ee; border:1px solid #eadcc0;
          vertical-align:middle; margin:0 2px; }
p.legend { font-size:12px; color:#555; margin:6px 0 0; }
table.acts { width:100%; table-layout:fixed; }
table.acts td { white-space:normal; overflow-wrap:anywhere; vertical-align:top; font-size:12.5px; }
.vchg { background:#fff; border:1px solid #e0e0e0; border-radius:6px; padding:8px 14px; margin:8px 0; }
.vchg h4 { margin:2px 0 4px; font-size:13px; } .vchg ul { margin:4px 0; padding-left:20px; }
.vchg li { font-size:13px; margin:2px 0; } .vnote { font-size:12px; color:#555; margin:4px 0; }
.empty { color:#666; font-size:13px; font-style:italic; padding:8px 0; }
.blk { margin-top:30px; } .blk > h2 { margin-top:0; padding-bottom:6px; border-bottom:2px solid #e3e8ef; }
.blk h3.sub { font-size:14px; margin:18px 0 6px; color:#334; }
.partners { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px; }
.partners .pg { background:#fff; border:1px solid #e0e0e0; border-radius:6px; padding:10px 14px; }
.partners .pg h4 { margin:0 0 6px; font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:#5f6470; }
.partners .pg li { font-size:12.5px; margin:2px 0; }
"""

DASH_JS = """
const PAL = %s, FUND_COLORS = %s, FUND_TYPE_LABEL = %s;
// a fund's type from the registry (window.REGIONAL_FUNDS, written by the page from aa.fund):
// the Asia-Pacific and ESA regional funds' country windows carry cbpf-* codes
function fundType(fc){ return fc==='cerf' ? 'cerf'
  : ((fc||'').startsWith('rhpf') || (window.REGIONAL_FUNDS||[]).includes(fc)) ? 'regional_fund' : 'cbpf'; }
// a fund as the pages name it ('CERF', 'CBPF AFG'; fund_label in dashboards.py), never its code
function fundName(x){ return x === 'cerf' ? 'CERF' : x === 'cbpf-unspecified' ? 'CBPF'
  : /^(cbpf|rhpf)(-[a-z]+)+$/.test(x || '') ? x.toUpperCase().replace(/-/g, ' ') : x; }
Chart.defaults.font.family = "-apple-system,'Segoe UI',Roboto,sans-serif";
Chart.defaults.color = '#52514e';
Chart.defaults.borderColor = '#ececec';
Chart.defaults.plugins.legend.labels.boxWidth = 12;
if(matchMedia('(prefers-reduced-motion: reduce)').matches) Chart.defaults.animation = false;   // charts draw at once for readers who asked for less motion
function money(v){ if(v==null) return '';
  return v>=1e9 ? '$'+(v/1e9).toFixed(1)+'B' : v>=1e6 ? '$'+(v/1e6).toFixed(1)+'M'
       : v>=1e3 ? '$'+(v/1e3).toFixed(0)+'k' : '$'+Math.round(v); }
// stack totals: the sum of the visible datasets drawn above each bar (opts.totals);
// a small inline plugin, no external dependency
const stackTotals = { id:'stackTotals', afterDatasetsDraw(chart, args, o){
  if(!o || !o.fmt) return;
  const {ctx, scales:{x, y}} = chart, horiz = o.horiz, n = chart.data.labels.length;
  ctx.save(); ctx.font = '600 10.5px ' + Chart.defaults.font.family; ctx.fillStyle = '#52514e';
  for(let i=0;i<n;i++){ let tot = 0;
    chart.data.datasets.forEach((d,di)=>{ if(chart.isDatasetVisible(di)) tot += (+d.data[i]||0); });
    if(!tot) continue;
    if(horiz){ ctx.textAlign='left'; ctx.textBaseline='middle';
      ctx.fillText(o.fmt(tot), x.getPixelForValue(tot)+4, y.getPixelForValue(i)); }
    else { ctx.textAlign='center'; ctx.textBaseline='bottom';
      ctx.fillText(o.fmt(tot), x.getPixelForValue(i), y.getPixelForValue(tot)-3); } }
  ctx.restore(); } };
// a chart whose selection holds no money (a hazard in a region with nothing recorded) says so,
// instead of drawing empty axes with $0 / $1 ticks
const emptyNote = { id:'emptyNote', afterDraw(chart){
  const {ctx, chartArea:a} = chart; if(!a) return;
  ctx.save(); ctx.font = '13px ' + Chart.defaults.font.family; ctx.fillStyle = '#64748b';
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(tr8('No data in this selection'), (a.left+a.right)/2, (a.top+a.bottom)/2); ctx.restore(); } };
function mkChart(id, type, labels, datasets, opts={}){
  // what a chart shows is translated here (tr8: the page's language, site_i18n), the keys
  // the page filters on are not; pages redraw on the 'aalang' event
  labels = labels.map(x=>typeof x==='string' ? tr8(x) : x);
  datasets.forEach((d,i)=>{ if(typeof d.label==='string') d.label = tr8(d.label); d.backgroundColor ??= PAL[i%%PAL.length];
    d.borderColor ??= (type==='line'? d.backgroundColor : '#fcfcfb');
    if(type==='bar'){ d.borderWidth=1; d.borderRadius=3; d.maxBarThickness=34; }
    if(type==='line'){ d.borderWidth=2; d.pointRadius=2; d.pointHoverRadius=5; d.tension=0.15; }});
  const el = document.getElementById(id);
  if(el._chart) el._chart.destroy();
  const horiz = opts.extra && opts.extra.indexAxis === 'y';
  const empty = !datasets.some(d=>(d.data||[]).some(v=>v!=null && (typeof v==='object' ? (v.y||v.x) : v)));
  const fmt = v=>opts.count?v:money(v);
  const valAxis = {stacked:!!opts.stacked, ticks:{callback:fmt}, grid:{color:'#f0f0f0'},
    ...(opts.totals ? {grace:'10%%'} : {})};
  const catAxis = {stacked:!!opts.stacked, grid:{display:false}, ticks:{autoSkip:!opts.allLabels}};
  const cb = {label:c=>{const v=horiz?c.parsed.x:(c.parsed.y??c.parsed);return ` ${c.dataset.label??''}: ${fmt(v)}`;}};
  if(opts.totals && datasets.length>1) cb.footer = items=>tr8('total: {0}', fmt(items.reduce((s,c)=>s+((horiz?c.parsed.x:c.parsed.y)||0),0)));
  el._chart = new Chart(el, { type, data:{labels, datasets},
    plugins: [...(opts.totals ? [stackTotals] : []), ...(empty ? [emptyNote] : [])],
    options:{
    // a horizontal chart's tooltip follows the row under the pointer (the value axis is x)
    responsive:true, maintainAspectRatio:false, interaction:{mode:'index',intersect:false,axis:horiz?'y':'x'},
    scales: opts.noscale ? {} : empty ? {x:{display:false}, y:{display:false}} : (horiz ? {x:valAxis, y:catAxis} : {x:catAxis, y:valAxis}),
    plugins:{ legend:{display:datasets.length>1 && !empty},
      tooltip:{callbacks:cb},
      ...(opts.totals ? {stackTotals:{fmt, horiz}} : {}),
      ...(opts.plugins||{}) },
    ...(opts.extra||{}) }});
  return el._chart; }
function groupSum(rows, keyFn, valFn){ const m={};
  rows.forEach(r=>{ const k=keyFn(r); m[k]=(m[k]||0)+(valFn(r)||0); }); return m; }
function uniqSorted(rows, f){ return [...new Set(rows.map(f).filter(x=>x!=null))].sort(); }
function cumulate(arr){ let s=0; return arr.map(v=>s+=(v||0)); }
""" % (json.dumps(PAL), json.dumps(FUND_COLORS), json.dumps(FUND_TYPE_LABEL))


def clean_org_name(s):
    """An organisation's name as CERF's sub-grant reports give it, fit to print: HTML entities
    decoded, however many times the name was escaped ("D&#233;veloppement", "&amp;amp;")."""
    import html as _html
    if not isinstance(s, str):
        return s
    t = s.strip()
    for _ in range(3):
        u = _html.unescape(t)
        if u == t:
            break
        t = u
    return t


def clean_org_names(df, col="partner_name"):
    """Decode the names, and drop a numbering suffix where the same name also appears without
    it ("World Vision 1" next to "World Vision"). A number that is part of the name stays:
    DRC's numbered education offices ("Ituri 1", "Ituri 3") are different partners."""
    import re as _re
    names = df[col].map(clean_org_name)
    stems = set(names.dropna())
    def unnumber(n):
        if isinstance(n, str):
            stem = _re.sub(r"\s+\d$", "", n)
            if stem != n and stem in stems:
                return stem
        return n
    df[col] = names.map(unnumber)
    return df


def haz(h):
    return h if h in HAZARDS else "other"


def _backfill_years(pre, e, first_year=2020):
    """Framework-years with no dated pre-arranged row get the version that was valid AT ANY TIME
    DURING THE YEAR (the latest of them; 2026-10-05 rule: a version whose validity ended during
    a year still counts for that year) and its envelope from aa.v_version_funding — so the
    annual series covers 2020→ from the framework record itself (source='version-inferred').
    Sheet / entered rows for a framework-year always win; the official year-end reports,
    once loaded, will replace the inferred rows year by year."""
    import datetime as dt

    # endorsed versions from their start; a version also counts while it was IN DEVELOPMENT,
    # from development_since (recorded since 2026-10-05; earlier development dates are lost)
    has_dev = "development_since" in set(pd.read_sql(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'aa' "
        "AND table_name = 'framework_version'", e)["column_name"])
    dev = "development_since" if has_dev else "NULL::date"
    ver = pd.read_sql(
        f"""SELECT country_iso3, hazard, version, kb_framework, kb_status,
                   least(valid_from, {dev}) AS valid_from, valid_until, prearranged_usd_doc
            FROM aa.framework_version
            WHERE (kb_status = 'endorsed' AND valid_from IS NOT NULL)
               OR (kb_status IN ('development', 'pre-development') AND {dev} IS NOT NULL)""", e)
    env = pd.read_sql(
        """SELECT country_iso3, hazard, version, fund_code, total_usd
           FROM aa.v_version_funding WHERE kind = 'prearranged' AND fund_code IS NOT NULL""", e)
    # the imported page metadata (funding_by_source / prearranged_funding_usd) for versions
    # that never got envelope rows — older versions, mostly
    pages = pd.read_sql(
        """SELECT kb_framework, version, frontmatter -> 'funding_by_source' AS by_source,
                  (frontmatter ->> 'prearranged_funding_usd')::numeric AS pre_doc,
                  frontmatter -> 'extra' -> 'shared_pool' ->> 'with' AS shared_with
           FROM aa.version_page""", e)
    page_by = {(r.kb_framework, str(r.version)): (r.by_source, r.pre_doc)
               for r in pages.itertuples()}
    # a version whose envelope sits inside ANOTHER framework's pool (Bangladesh cyclones 2023
    # with floods, Niger floods 2024 under the drought cap) is counted there, once
    shared = {(r.kb_framework, str(r.version)) for r in pages.itertuples() if isinstance(r.shared_with, str)}
    fw_slug = dict(zip(zip(ver["country_iso3"], ver["hazard"]), ver["kb_framework"]))
    # a retired framework is inferred only up to the last year a status report still had it
    # live (no retirement date is recorded)
    ret = pd.read_sql(
        """SELECT r.country_iso3, r.hazard,
                  max(extract(year FROM s.as_of))::int AS last_live
           FROM aa.country_hazard r
           LEFT JOIN aa.framework_status s ON s.country_iso3 = r.country_iso3
                AND s.hazard = r.hazard AND s.status NOT IN ('dormant', 'retired', 'expired')
           WHERE r.retired GROUP BY 1, 2""", e)
    last_live = {(r.country_iso3, r.hazard): r.last_live for r in ret.itertuples()}
    fund_of = {"cerf": "cerf", "cbpf": "cbpf-unspecified", "rhpf": "rhpf"}
    # frontmatter names pooled funds by acronym (AHF, NHF, YHF; FHRAOC = the West & Central
    # Africa regional fund): resolve to the country's fund in aa.fund
    reg = pd.read_sql("SELECT fund_code, fund_type, country_iso3 FROM aa.fund", e)
    cbpf_by_c = {r.country_iso3: r.fund_code for r in reg.itertuples() if r.fund_type == "cbpf" and r.country_iso3}
    rhpf_by_c = {r.country_iso3: r.fund_code for r in reg.itertuples() if r.fund_type == "regional_fund" and r.country_iso3}

    def resolve(key, c):
        k = str(key).strip().lower()
        if k in fund_of:
            return fund_of[k]
        if k in ("fhraoc", "rhpf-wca", "rhpf") or k.startswith(("rhpf", "fhr")):
            return rhpf_by_c.get(c, "rhpf")
        if k.endswith("hf") or "cbpf" in k:
            return cbpf_by_c.get(c, "cbpf-unspecified")
        return k
    have = set(zip(pre["country_iso3"], pre["hazard"], pre["year"].astype(int)))
    today = dt.date.today()
    rows = []
    for (c, h), vs in ver.groupby(["country_iso3", "hazard"]):
        vs = vs.assign(valid_from=pd.to_datetime(vs["valid_from"]),
                       valid_until=pd.to_datetime(vs["valid_until"]))
        cap = last_live.get((c, h), None)
        if (c, h) not in last_live:
            last_year = today.year
        else:   # retired: to the last year a status report had it live, or its validity ran
            ends = [int(x) for x in (cap, vs["valid_until"].max().year if vs["valid_until"].notna().any() else None)
                    if x is not None and not pd.isna(x)]
            last_year = max(ends) if ends else int(vs["valid_from"].min().year)
        for y in range(first_year, int(last_year) + 1):
            if (c, h, y) in have:
                continue
            at = pd.Timestamp(min(dt.date(y, 12, 31), today))
            # valid at any time in the year; the current year: still valid today
            since = at if y == today.year else pd.Timestamp(dt.date(y, 1, 1))
            inforce = vs[(vs["valid_from"] <= at)
                         & (vs["valid_until"].isna() | (vs["valid_until"] >= since))]
            if inforce.empty:
                continue
            v = inforce.sort_values("valid_from").iloc[-1]
            if (fw_slug.get((c, h)), str(v["version"])) in shared:
                continue
            e_v = env[(env["country_iso3"] == c) & (env["hazard"] == h)
                      & (env["version"] == v["version"])]
            by_source, pre_doc = page_by.get((fw_slug.get((c, h)), str(v["version"])), (None, None))
            amounts = []
            if len(e_v):
                # an 'all' total only where no per-fund split exists (as prearranged_now)
                if (e_v["fund_code"] != "all").any():
                    e_v = e_v[e_v["fund_code"] != "all"]
                amounts = [(x.fund_code, float(x.total_usd)) for x in e_v.itertuples()]
            elif isinstance(by_source, dict) and by_source:
                amounts = [(resolve(k, c), float(a))
                           for k, a in by_source.items() if a is not None]
            elif pd.notna(v["prearranged_usd_doc"]):
                amounts = [("cerf", float(v["prearranged_usd_doc"]))]
            elif pre_doc is not None and pd.notna(pre_doc):
                amounts = [("cerf", float(pre_doc))]
            for fc, usd in amounts:
                rows.append({"country_iso3": c, "hazard": h, "year": y, "kind": "prearranged",
                             "fund_code": fc, "financier": None, "amount_usd": usd,
                             "source": "version-inferred", "version": str(v["version"])})
    if not rows:
        return pre
    return pd.concat([pre, pd.DataFrame(rows)[pre.columns]], ignore_index=True)


def old_versions(ver):
    """{(country, hazard, version)} of the versions OUTSIDE their pair's current line — the
    rule of aa.v_framework_lifecycle (schema.py), kept here in step with it so the pages need
    nothing a snapshot taken before the view changed may lack. The current line: the latest
    version (valid_from DESC NULLS LAST, version DESC, as the view's `latest`) and every
    version reached back through `supersedes`. A version outside it belongs to an earlier
    framework that a distinct new one replaced (Somalia drought: the 2019 / 2020-06-23
    food-security framework vs the 2026 one, which supersedes nothing — 2026-10-27 ruling:
    the 2020 activation is the old framework's, not the one in development): its activations
    and money are a RETIRED framework's, never the current framework's. A supersedes naming
    no version of the pair breaks the chain (Mozambique storm 2026-01-09 -> '2025-05-23'):
    the line can't be traced, so nothing on that pair is old."""
    old = set()
    if ver is None or not len(ver) or "supersedes" not in ver:
        return old
    v = ver.assign(version=ver["version"].astype(str),
                   vf=pd.to_datetime(ver["valid_from"].astype(str), errors="coerce"))
    for (c, h), g in v.groupby(["country_iso3", "hazard"]):
        sup = {r.version: (str(r.supersedes) if pd.notna(r.supersedes) else None) for r in g.itertuples()}
        latest = max(g.itertuples(), key=lambda r: (pd.notna(r.vf), r.vf if pd.notna(r.vf) else pd.Timestamp.min,
                                                    r.version)).version
        line, x = set(), latest
        while x is not None and x not in line:
            line.add(x)
            x = sup.get(x)
        if not line <= set(sup):          # a dangling supersedes: the whole pair is one line
            continue
        old |= {(c, h, s) for s in sup if s not in line}
    return old


def activation_factors(e):
    """{(country, hazard, version): n} of the versions whose document allows n > 1 activations a
    year (aa.framework_version.activations_per_year, 2026-10-28: some tropical-cyclone frameworks
    allow two). Their pre-arranged envelope is REPORTED multiplied by n (prearranged_now,
    funding_series), with a note: the budget per activation is the envelope as recorded. Empty
    when the database has no such column yet (a snapshot taken before the migration): then
    nothing changes."""
    has = not pd.read_sql(
        """SELECT 1 FROM information_schema.columns WHERE table_schema = 'aa'
             AND table_name = 'framework_version' AND column_name = 'activations_per_year'""", e).empty
    if not has:
        return {}
    f = pd.read_sql("""SELECT country_iso3, hazard, version, activations_per_year AS n
                       FROM aa.framework_version WHERE activations_per_year > 1""", e)
    return {(r.country_iso3, r.hazard, str(r.version)): int(r.n) for r in f.itertuples()}


def prearranged_now(e):
    """THE definition of pre-arranged money now, from the framework records (2026-09-29):
    for every live framework (active, being updated, in development — in-development ones
    count once the ERC approved the pre-arrangement), the envelope of its MOST RECENT
    VERSION THAT HAS ONE (a framework being updated keeps its last envelope), per fund, from
    aa.v_version_funding; an 'all' total only where no per-fund split exists. Every page
    that shows pre-arranged money now uses this: the Funding tile, the map tiles, and the
    current year of the annual series (so the donor page and the flow chart agree).
    Live frameworks with no envelope in any version are NOT filled from the sheets: they
    are listed as gaps (see envelope_gaps). Only versions of the framework's current line
    count (old_versions): a new framework never inherits the envelope of the one it replaced.
    A Country or Regional Fund envelope that an activation of the version drew on is left out
    (pooled_spent): released, no longer committed — unlike CERF's, which stays committed after
    an activation until the framework is retired: the framework is revised and re-approved for
    the next season (owner, 2026-10-30; D163).
    A version that allows two activations a year (activation_factors) counts its envelope
    twice: total_usd is the envelope × activations_per_year (a column of the result, 1 for
    every other version) — every page reading this gets the multiplied figure and must not
    multiply again; activations_per_year > 1 is what marks the figure (the asterisk note)."""
    env = pd.read_sql(
        """WITH env AS (
               SELECT vf.country_iso3, vf.hazard, vf.version, vf.fund_code, vf.total_usd,
                      fv.valid_from
               FROM aa.v_version_funding vf
               JOIN aa.framework_version fv USING (country_iso3, hazard, version)
               WHERE vf.kind = 'prearranged' AND vf.total_usd > 0),
           env2 AS (
               SELECT * FROM env x
               WHERE NOT (x.fund_code = 'all' AND EXISTS (
                   SELECT 1 FROM env y WHERE y.country_iso3 = x.country_iso3
                     AND y.hazard = x.hazard AND y.version = x.version AND y.fund_code <> 'all')))
           SELECT x.country_iso3, x.hazard, x.version, x.fund_code, x.total_usd, x.valid_from,
                  l.lifecycle, l.latest_version
           FROM env2 x
           JOIN aa.v_framework_lifecycle l USING (country_iso3, hazard)
           WHERE l.lifecycle IN ('active', 'updating', 'development')""", e)
    old = old_versions(pd.read_sql(
        "SELECT country_iso3, hazard, version, valid_from, supersedes FROM aa.framework_version", e))
    env = env.loc[[(c, h, str(v)) not in old
               for c, h, v in zip(env["country_iso3"], env["hazard"], env["version"])]]
    # per framework, the most recent version with an envelope (valid_from DESC NULLS LAST,
    # version DESC — the lifecycle view's order)
    pick = (env.assign(vf=pd.to_datetime(env["valid_from"].astype(str), errors="coerce"))
            .sort_values(["country_iso3", "hazard", "vf", "version"],
                         ascending=[True, True, False, False], na_position="last")
            .drop_duplicates(["country_iso3", "hazard"])[["country_iso3", "hazard", "version"]])
    now = (env.merge(pick, on=["country_iso3", "hazard", "version"])
           .drop(columns="valid_from").sort_values(["country_iso3", "hazard", "fund_code"])
           .reset_index(drop=True))
    reg = pd.read_sql("SELECT fund_code, fund_type, country_iso3 FROM aa.fund WHERE country_iso3 IS NOT NULL", e)
    out = envelope_by_fund(now, reg)
    # two activations a year: the CERF envelope counted twice (activation_factors). The documents
    # state CERF's envelope per activation; a Country or Regional Fund envelope is one allocation
    # (Haiti 2026: the LAC regional fund's $1M next to CERF's $4M per activation; owner, 2026-10-28)
    fac = activation_factors(e)
    out["activations_per_year"] = [fac.get((c, h, str(v)), 1) if f == "cerf" else 1
                                   for c, h, v, f in zip(out["country_iso3"], out["hazard"], out["version"],
                                                         out["fund_code"])]
    out["total_usd"] = out["total_usd"].astype(float) * out["activations_per_year"]
    # a Country or Regional Fund envelope an activation has drawn on is released, no longer
    # committed (pooled_spent); CERF's stays until the framework is retired (D163)
    spent = pooled_spent(e)
    pooled = out["fund_code"].astype(str).str.startswith(("cbpf", "rhpf"))
    out = out[~(pooled & pd.Series([(c, h, str(v)) in spent for c, h, v in
                                    zip(out["country_iso3"], out["hazard"], out["version"])], index=out.index))]
    return out.reset_index(drop=True)


def envelope_by_fund(rows, reg):
    """A version's pre-arranged envelope by fund, by the one rule (prearranged_now; the framework
    pages' version envelope and the map's per-version envelope use it too, 2026-10-28): an 'all'
    total only where the version has no per-fund row; an envelope recorded as "CBPF, fund not
    named" belongs to the country's own pooled fund, or its regional fund where it has no country
    fund (Burkina Faso -> RhPF-WCA); a version with both an unnamed-CBPF row and its fund's own row
    states the same money twice (Nigeria 2026: a sheet's "CBPF" $1M and the NHF's $1M): the larger,
    not the sum. Only positive amounts count, and a row with no fund is not a per-fund row (as the
    SQL of prearranged_now). Two rows of one fund (two financiers) also give the larger: no version
    has them today. rows: v_version_funding rows (country_iso3, hazard, version, fund_code,
    total_usd, any other columns kept as keys); reg: aa.fund rows (fund_code, fund_type, country_iso3)."""
    rows = rows[pd.to_numeric(rows["total_usd"], errors="coerce") > 0]
    if not len(rows):
        return rows.copy()
    keys = ["country_iso3", "hazard", "version"]
    comp = set(map(tuple, rows.loc[rows["fund_code"].notna() & (rows["fund_code"] != "all"), keys].astype(str).values))
    dup = pd.Series([tuple(k) in comp for k in rows[keys].astype(str).values], index=rows.index, dtype=bool)
    rows = rows[~((rows["fund_code"] == "all") & dup)].copy()
    reg = reg[reg["country_iso3"].notna()]
    own = {r.country_iso3: r.fund_code for r in reg.itertuples() if r.fund_type == "cbpf"}
    regional = {r.country_iso3: r.fund_code for r in reg.itertuples() if r.fund_type == "regional_fund"}
    un = rows["fund_code"] == "cbpf-unspecified"
    rows.loc[un, "fund_code"] = [own.get(c) or regional.get(c) or "cbpf-unspecified"
                                 for c in rows.loc[un, "country_iso3"]]
    return (rows.groupby([c for c in rows.columns if c != "total_usd"], as_index=False, dropna=False)
            ["total_usd"].max())


def funding_sql(e):
    """aa.activation_funding as every page reads released money (2026-10-30): amount_usd NET of
    the money the activation refunded (aa.activation_refund, owner: "the money goes out, but the
    activation gets paused or stopped, so the money is refunded back to CERF"), refund_usd beside
    it, and provisional = an amount entered before OneGMS recorded the allocation
    (scripts/resolve_provisional.py). A refund names its allocation, or (NULL) the activation's
    allocation from that fund. A FROM-clause source with the table's own columns; on a database
    without the refund table yet (before the schema run), no refunds."""
    has = pd.read_sql("SELECT to_regclass('aa.activation_refund') AS r", e)["r"].iloc[0] is not None
    if not has:
        return ("(SELECT f.*, NULL::numeric AS refund_usd, (f.match_method = 'provisional') AS provisional "
                "FROM aa.activation_funding f)")
    k = ("country_iso3", "hazard", "event_date", "event_label", "event_type", "fund_code")
    return ("(SELECT f.country_iso3, f.hazard, f.event_date, f.window_name, f.event_label, f.event_type,"
            " f.fund_code, f.allocation_code, f.amount_usd - coalesce(r.usd, 0) AS amount_usd,"
            " r.usd AS refund_usd, f.people_targeted, f.reported_to_ahub, f.match_method, f.source,"
            " f.updated_at, (f.match_method = 'provisional') AS provisional"
            " FROM aa.activation_funding f LEFT JOIN LATERAL ("
            "  SELECT sum(x.amount_usd) AS usd FROM aa.activation_refund x WHERE "
            + " AND ".join(f"x.{c} = f.{c}" for c in k)
            + " AND x.window_name IS NOT DISTINCT FROM f.window_name"
              " AND (x.allocation_code IS NULL OR x.allocation_code = f.allocation_code)) r ON true)")


def refund_problems(e):
    """Refund rows that match no funding row, or (no allocation named) more than one: the build
    warns, since a refund would then be lost or counted twice."""
    if pd.read_sql("SELECT to_regclass('aa.activation_refund') AS r", e)["r"].iloc[0] is None:
        return []
    r = pd.read_sql(
        """SELECT x.country_iso3, x.hazard, x.event_date, x.window_name, x.event_label, x.event_type,
                  x.fund_code, x.allocation_code, count(f.fund_code) AS n
           FROM aa.activation_refund x LEFT JOIN aa.activation_funding f
             ON f.country_iso3 = x.country_iso3 AND f.hazard = x.hazard AND f.event_date = x.event_date
            AND f.event_label = x.event_label AND f.event_type = x.event_type AND f.fund_code = x.fund_code
            AND f.window_name IS NOT DISTINCT FROM x.window_name
            AND (x.allocation_code IS NULL OR x.allocation_code = f.allocation_code)
           GROUP BY 1, 2, 3, 4, 5, 6, 7, 8 HAVING count(f.fund_code) <> 1""", e)
    return [f"{x.country_iso3}/{x.hazard}/{x.event_date}/{x.window_name or ''}/{x.fund_code}"
            f"{'/' + x.allocation_code if isinstance(x.allocation_code, str) else ''}: "
            f"{'no funding row' if not x.n else f'{x.n} funding rows'}" for x in r.itertuples()]


def pooled_spent(e):
    """(country, hazard, version) whose Country or Regional Fund envelope an activation of that
    version has drawn on (owner, 2026-10-28): a framework being updated after an activation keeps its
    CERF envelope committed, but a pooled fund's allocation is released money from then on, not
    committed — Burkina Faso floods' regional-fund $1M after the September 2025 activation."""
    r = pd.read_sql(
        """SELECT DISTINCT f.country_iso3, f.hazard, a.version
           FROM """ + funding_sql(e) + """ f   -- net of refunds: money sent back is not spent
           JOIN aa.activation a ON a.country_iso3 = f.country_iso3 AND a.hazard = f.hazard
            AND a.event_date = f.event_date AND a.event_type = f.event_type
            AND a.window_name IS NOT DISTINCT FROM f.window_name
            AND coalesce(a.event_label, '') = coalesce(f.event_label, '')
           WHERE f.event_type = 'framework_aa' AND f.amount_usd > 0 AND a.version IS NOT NULL
             AND left(f.fund_code, 4) IN ('cbpf', 'rhpf')""", e)   # no '%': the driver reads it as a parameter
    return {(c, h, str(v)) for c, h, v in r.itertuples(index=False)}


def envelope_gaps(d):
    """Live frameworks with no pre-arranged envelope in any version (listed, never filled)."""
    cur = d["current"]
    live = cur[cur["lifecycle"].isin(["active", "updating", "development"])]
    have = set(zip(d["vfund"]["country_iso3"], d["vfund"]["hazard"]))
    released = {(c, h) for c, h, _ in d.get("pool_spent") or set()}
    return [(r.country_name or r.country_iso3, r.hazard, r.lifecycle) for r in live.itertuples()
            if (r.country_iso3, r.hazard) not in have and (r.country_iso3, r.hazard) not in released]


def envelope_released(d):
    """Live frameworks whose pre-arranged money now is nothing because their only envelope, a
    Country or Regional Fund one, was released by an activation (pooled_spent)."""
    cur = d["current"]
    live = cur[cur["lifecycle"].isin(["active", "updating", "development"])]
    have = set(zip(d["vfund"]["country_iso3"], d["vfund"]["hazard"]))
    released = {(c, h) for c, h, _ in d.get("pool_spent") or set()}
    return [(r.country_name or r.country_iso3, r.hazard, r.lifecycle) for r in live.itertuples()
            if (r.country_iso3, r.hazard) in released and (r.country_iso3, r.hazard) not in have]


def _fetch(e):
    """All row-level frames the dashboards embed."""
    d = {}
    d["current"] = pd.read_sql(
        """SELECT c.*, r.region FROM aa.v_trk_framework_current c
           LEFT JOIN aa.country_hazard r USING (country_iso3, hazard)""", e)
    d["current"] = d["current"].loc[:, ~d["current"].columns.duplicated()]
    pre = pd.read_sql(
        """SELECT country_iso3, hazard, year, kind, fund_code, financier,
                  amount_usd, source, version FROM aa.prearranged_funding
           WHERE amount_usd IS NOT NULL AND year IS NOT NULL""", e)   # annual series: dated rows only
    pre = canonical(pre, ["country_iso3", "hazard", "year", "kind", "fund_code",
                          "financier"])
    # drop 'all' totals when component rows exist for the same framework-year
    comp = set(map(tuple, pre.loc[pre["fund_code"].isin(["cerf", "cbpf-unspecified"]),
                                  ["country_iso3", "hazard", "year"]].values))
    pre = pre[~((pre["fund_code"] == "all")
                & pre.apply(lambda r: (r["country_iso3"], r["hazard"], r["year"])
                            in comp, axis=1))]
    d["prearranged"] = _backfill_years(pre, e)
    d["activation"] = pd.read_sql(
        """SELECT a.country_iso3, a.hazard, a.event_type, a.event_date,
                  a.window_name, a.version, a.people_targeted, a.kb_event_date,
                  f.fund_code, f.allocation_code, f.amount_usd, f.refund_usd, f.provisional,
                  r.region
           FROM """ + funding_sql(e) + """ f   -- released money net of refunds
           -- null-safe: non-framework rows have no window, and a plain USING join silently
           -- dropped them (until 2026-09-30 only framework activations came through)
           JOIN aa.activation a
             ON a.country_iso3 = f.country_iso3 AND a.hazard = f.hazard
            AND a.event_date = f.event_date AND a.event_type = f.event_type
            AND a.window_name IS NOT DISTINCT FROM f.window_name
            AND coalesce(a.event_label, '') = coalesce(f.event_label, '')
           LEFT JOIN aa.country_hazard r
             ON r.country_iso3 = a.country_iso3 AND r.hazard = a.hazard
           WHERE a.event_type NOT IN (""" + _EXCL_SQL + ")", e)
    for p in refund_problems(e):   # a refund that matches no funding row (lost) or two (counted twice)
        print(f"::warning::refund {p}: a refund must match exactly one funding row of its activation")
    d["versions"] = pd.read_sql(
        """SELECT country_iso3, hazard, version, kb_status, valid_from, source,
                  doc_url, analysis_ref, prearranged_usd_doc, supersedes
           FROM aa.framework_version ORDER BY country_iso3, hazard, valid_from""", e)
    # versions of an earlier framework a distinct new one replaced: their activations and
    # money are a retired framework's (old_versions; _layer_of)
    d["old"] = old_versions(d["versions"])
    d["alloc"] = pd.read_sql(
        """SELECT v.fund_type, v.fund_name, v.allocation_code,
                  COALESCE(v.country_iso3, fu.country_iso3) AS country_iso3,
                  v.year, v.amount_usd, v.is_aa, left(v.title, 140) AS title
           FROM aa.v_allocation v
           LEFT JOIN aa.fund fu
             ON fu.pf_id = (CASE WHEN v.fund_type <> 'cerf'
                                  AND split_part(v.allocation_code, '-', 2) ~ '^[0-9]+$'
                            THEN split_part(v.allocation_code, '-', 2)::int END)
           WHERE v.year >= 2006""", e)
    d["subgrant"] = clean_org_names(pd.read_sql(
        """SELECT year, country_iso3, emergency_type, partner_type, localization,
                  partner_name, subgrant_usd, is_aa
           FROM aa.cerf_subgrant WHERE subgrant_usd IS NOT NULL""", e))
    d["cbpf_proj"] = pd.read_sql(
        """SELECT p.allocation_year AS year, p.org_type, p.org_name, p.budget,
                  a.aa_keyword, f.country_code_iso2
           FROM aa.cbpf_project p
           LEFT JOIN aa.cbpf_allocation a
             ON a.pooled_fund_id = p.pooled_fund_id
            AND a.allocation_type_id = p.allocation_type_id
           LEFT JOIN aa.cbpf_fund f ON f.pf_id = p.pooled_fund_id
           WHERE p.budget IS NOT NULL""", e)
    d["sector"] = pd.read_sql(
        """SELECT c.year, c.country_iso3, s.cerf_sector_name AS sector,
                  s.sector_amount
           FROM aa.cerf_project_sector s
           JOIN aa.cerf_project p USING (project_code)
           JOIN aa.cerf_allocation c ON c.application_code = p.application_code
           WHERE c.application_code IN (""" + _CERF_AA_CODES_SQL + """)
             AND s.sector_amount IS NOT NULL""", e)
    d["agency"] = pd.read_sql(
        """SELECT c.year, c.country_iso3, p.agency_short_name AS agency,
                  p.amount_approved, p.application_code
           FROM aa.cerf_project p
           JOIN aa.cerf_allocation c ON c.application_code = p.application_code
           WHERE c.application_code IN (""" + _CERF_AA_CODES_SQL + ")", e)
    d["cva"] = pd.read_sql(
        """SELECT year, country_iso3, agency, emergency_type, cva_usd,
                  people_receiving_cash FROM aa.cerf_cva_history
           WHERE cva_usd IS NOT NULL""", e)
    d["reached"] = pd.read_sql(
        """SELECT p.application_code, c.year, c.country_iso3, p.grp, p.value
           FROM aa.cerf_application_people p
           JOIN aa.cerf_allocation c ON c.application_code = p.application_code
           WHERE p.phase = 'reached' AND p.disaggregation = 'sex_age'
             AND c.application_code IN (""" + _CERF_AA_CODES_SQL + ")", e)
    d["covered"] = pd.read_sql(
        """SELECT DISTINCT ON (country_iso3, hazard) country_iso3, hazard,
                  people_covered
           FROM aa.people_covered WHERE people_covered IS NOT NULL
           ORDER BY country_iso3, hazard, as_of DESC""", e)
    d["gho"] = pd.read_sql(
        """SELECT DISTINCT ON (country_iso3, year) country_iso3, year, in_gho
           FROM aa.plan_inclusion WHERE in_gho IS NOT NULL
           ORDER BY country_iso3, year, source""", e)
    # monitoring months IN ANY YEAR: the current version's own record (version_page
    # monitoring_period.months); the tracking sheets' calendar only where the version has
    # none. (2026-10-01: the sheet is a current-year planner — Niger drought showed only
    # August, the one month left in 2026.)
    d["calendar"] = pd.read_sql(
        """WITH cur AS (
               SELECT l.country_iso3, l.hazard, fv.kb_framework, l.latest_version AS version
               FROM aa.v_framework_lifecycle l
               JOIN aa.framework_version fv ON fv.country_iso3 = l.country_iso3
                AND fv.hazard = l.hazard AND fv.version = l.latest_version),
           ver AS (
               SELECT c.country_iso3, c.hazard, (m.value)::int AS month
               FROM cur c JOIN aa.version_page p ON p.kb_framework = c.kb_framework AND p.version = c.version
               CROSS JOIN LATERAL jsonb_array_elements_text(
                   CASE WHEN jsonb_typeof(p.frontmatter -> 'monitoring_period' -> 'months') = 'array'
                        THEN p.frontmatter -> 'monitoring_period' -> 'months' ELSE '[]'::jsonb END) m
               WHERE m.value ~ '^[0-9]+$'),
           sheet AS (
               SELECT DISTINCT country_iso3, hazard, month FROM aa.framework_calendar
               WHERE phase = 'trigger_window')
           SELECT DISTINCT country_iso3, hazard, month FROM ver WHERE month BETWEEN 1 AND 12
           UNION
           SELECT s.country_iso3, s.hazard, s.month FROM sheet s
           WHERE NOT EXISTS (SELECT 1 FROM ver v WHERE v.country_iso3 = s.country_iso3 AND v.hazard = s.hazard)
           ORDER BY 1, 2, 3""", e)
    d["timeliness"] = pd.read_sql(
        """SELECT application_code, country_iso3, year,
                  erc_endorsement_date, first_project_approved_date,
                  (first_project_approved_date - erc_endorsement_date) AS days
           FROM aa.cerf_allocation
           WHERE aa_keyword AND erc_endorsement_date IS NOT NULL
             AND first_project_approved_date IS NOT NULL""", e)
    d["focal"] = pd.read_sql(
        "SELECT country_iso3, hazard, role, person FROM aa.framework_focal_point", e)
    d["report"] = pd.read_sql(
        """SELECT country_iso3, hazard, report_year, channel, counted
           FROM aa.report_channel_inclusion WHERE counted""", e)
    # AA-tagged CBPF / regional-fund allocations from the OneGMS mirror (tagged by a title
    # keyword heuristic, not by hand). The CBPF modality allocates up front: an allocation
    # behind a framework is PRE-ARRANGED money until an activation draws on it (= a row in
    # activation_funding, entered by hand). Which activations use it (framework / ad hoc or
    # early action) and what was approved decide whether it counts (funding_series).
    d["cbpf_aa"] = pd.read_sql(
        """SELECT v.allocation_code, v.fund_type, v.fund_name, v.year, v.amount_usd,
                  fu.country_iso3, fu.fund_code, (af.allocation_code IS NOT NULL) AS linked,
                  coalesce(af.by_framework, false) AS by_framework,
                  coalesce(af.by_other, false) AS by_other, ca.approved_budget,
                  left(v.title, 120) AS title
           FROM aa.v_allocation v
           LEFT JOIN aa.fund fu
             ON fu.pf_id = (CASE WHEN split_part(v.allocation_code, '-', 2) ~ '^[0-9]+$'
                            THEN split_part(v.allocation_code, '-', 2)::int END)
           LEFT JOIN (SELECT allocation_code,
                             bool_or(event_type = 'framework_aa') AS by_framework,
                             bool_or(event_type <> 'framework_aa') AS by_other
                      FROM aa.activation_funding GROUP BY 1) af
             ON af.allocation_code = v.allocation_code
           LEFT JOIN aa.cbpf_allocation ca
             ON 'cbpf-' || ca.pooled_fund_id || '-' || ca.allocation_type_id = v.allocation_code
           WHERE v.is_aa AND v.fund_type <> 'cerf'""", e)
    d["vfund"] = prearranged_now(e)
    d["pool_spent"] = pooled_spent(e)   # pooled envelopes released by an activation (prearranged_now leaves them out)
    # versions that allow two activations a year: their envelope is reported doubled
    # (prearranged_now above, funding_series and the Financing page's split by agency / sector)
    d["act_factors"] = activation_factors(e)
    d["windows"] = pd.read_sql(
        """SELECT w.country_iso3, r.country_name, w.hazard, w.version, w.window_name,
                  w.basis, w.all_in, w.allocation_usd,
                  p.return_period, p.activation_prob, p.n_activations, p.analysis_years,
                  p.analysis_start, p.analysis_end, s.triggered, s.triggered_on, l.lifecycle,
                  (l.latest_version = w.version) AS is_latest
           FROM aa.window w
           JOIN aa.country_hazard r ON r.country_iso3 = w.country_iso3 AND r.hazard = w.hazard
           LEFT JOIN aa.v_window_performance p
             ON p.country_iso3 = w.country_iso3 AND p.hazard = w.hazard
            AND p.version = w.version AND p.window_name = w.window_name
           LEFT JOIN aa.window_status s
             ON s.country_iso3 = w.country_iso3 AND s.hazard = w.hazard
            AND s.version = w.version AND s.window_name = w.window_name
           LEFT JOIN aa.v_framework_lifecycle l
             ON l.country_iso3 = w.country_iso3 AND l.hazard = w.hazard""", e)
    d["plan_rows"] = pd.read_sql(
        """SELECT f.country_iso3, r.country_name, f.hazard, f.version, f.agency, f.sector,
                  f.amount_usd, f.fund_code, l.lifecycle
           FROM aa.v_window_funding_split f
           JOIN aa.v_framework_lifecycle l
             ON l.country_iso3 = f.country_iso3 AND l.hazard = f.hazard
            AND l.latest_version = f.version
           JOIN aa.country_hazard r ON r.country_iso3 = f.country_iso3 AND r.hazard = f.hazard
           WHERE f.amount_usd IS NOT NULL AND (f.agency IS NOT NULL OR f.sector IS NOT NULL)
             AND f.kind = 'prearranged'
             AND l.lifecycle IN ('active', 'updating', 'development')""", e)
    # the co-financing lines of the live frameworks' latest versions: the undated rows a
    # framework document states, naming who co-finances (with an agency or not, so not in
    # aa.prearranged_funding alone) — the Financing page splits each framework's co-financing
    # now in their proportions
    d["cof_lines"] = pd.read_sql(
        """SELECT f.country_iso3, f.hazard, f.version, f.financier, f.agency, f.amount_usd,
                  f.source, f.updated_at
           FROM aa.window_funding f
           JOIN aa.v_framework_lifecycle l
             ON l.country_iso3 = f.country_iso3 AND l.hazard = f.hazard
            AND l.latest_version = f.version
           WHERE f.kind = 'cofinancing' AND f.year IS NULL AND f.amount_usd IS NOT NULL
             AND l.lifecycle IN ('active', 'updating', 'development')""", e)
    d["act_all"] = pd.read_sql(
        """SELECT a.*, r.country_name FROM aa.activation a
           LEFT JOIN aa.country_hazard r ON r.country_iso3 = a.country_iso3 AND r.hazard = a.hazard
           WHERE a.event_type NOT IN (""" + _EXCL_SQL + """)
           ORDER BY a.event_date DESC""", e)
    d["act_url"] = pd.read_sql(
        """SELECT country_iso3, hazard, event_date, window_name, url
           FROM aa.window_activation WHERE url IS NOT NULL""", e)
    # donor contributions to the funds (OneGMS mirrors, ds-cerf-supplement) and donor
    # earmarks to the OCHA AA project (hand-entered) — the donor-shares page. Tolerant of
    # a snapshot taken before the mirror existed: the page then says so.
    try:
        d["contrib"] = pd.read_sql(
            """SELECT v.fund_type, v.fund_name, v.donor, v.donor_type, v.year,
                      v.paid_usd, v.pledged_usd,
                      CASE WHEN v.fund_type = 'cerf' THEN 'cerf' ELSE fu.fund_code END
                          AS fund_code
               FROM aa.v_contribution v
               LEFT JOIN aa.fund fu ON fu.pf_id = v.pooled_fund_id
               WHERE v.year >= 2020""", e)
        d["build"] = pd.read_sql(
            "SELECT donor, year, amount_usd, purpose, source FROM aa.build_contribution", e)
    except Exception as exc:  # missing view/table in an older snapshot
        print(f"  donor shares: contribution tables unavailable ({exc.__class__.__name__})")
        d["contrib"] = pd.DataFrame(columns=["fund_type", "fund_name", "donor", "donor_type",
                                             "year", "paid_usd", "pledged_usd", "fund_code"])
        d["build"] = pd.DataFrame(columns=["donor", "year", "amount_usd", "purpose", "source"])
    # CERF AA sub-grants with the receiving agency (the partner view on the Funding page
    # and the "funded sub-grantees" block of the framework pages)
    # dated by the allocation's year, as the agency totals are (the sub-grant sheet's own year
    # runs a year early for some: CERF-HTI-24-RR-1399, a 2025 allocation, was dated 2024)
    # The AA sub-grants are those of the AA allocations the site counts (_CERF_AA_CODES_SQL), as
    # the Activities page reads them — not the sheet's is_aa flag, which misses four of them
    # (NER 2022, NPL 2021, MDG 2023, TLS 2024: $4.0M; 2026-10-28)
    d["subgrant_aa"] = clean_org_names(pd.read_sql(
        """SELECT g.project_code, g.application_code, g.agency, coalesce(c.year, g.year) AS year,
                  g.country_iso3, g.partner_name, g.partner_acronym, g.partner_type, g.localization,
                  g.subgrant_usd
           FROM aa.cerf_subgrant g
           LEFT JOIN aa.cerf_allocation c ON c.application_code = g.application_code
           WHERE g.application_code IN (""" + _CERF_AA_CODES_SQL + """)
             AND g.subgrant_usd IS NOT NULL""", e))
    # the agency × sector split of EVERY version (the framework pages show the current
    # version's split next to its envelope; plan_rows above keeps only the live ones)
    d["split_all"] = pd.read_sql(
        """SELECT country_iso3, hazard, version, window_name, agency, sector, fund_code,
                  amount_usd
           FROM aa.v_window_funding_split
           WHERE kind = 'prearranged' AND amount_usd IS NOT NULL
             AND (agency IS NOT NULL OR sector IS NOT NULL)""", e)
    d["env_all"] = pd.read_sql(
        """SELECT country_iso3, hazard, version, fund_code, total_usd
           FROM aa.v_version_funding WHERE kind = 'prearranged' AND fund_code IS NOT NULL""", e)
    # learning documents and framework partners: filled by a parallel import, possibly
    # empty (or absent in an older snapshot) — every consumer degrades to "none yet".
    # Internal documents are NEVER rendered: filtered out here, at the source. Neither are
    # posts on X/Twitter (NOT_SOCIAL_SQL).
    try:
        # the publication month (2026-10-23) is NULL until ensure_schema has added the column
        # on dev and a snapshot carries it: the page shows the year alone meanwhile
        has_month = not pd.read_sql(
            """SELECT 1 FROM information_schema.columns WHERE table_schema = 'aa'
                 AND table_name = 'learning_document' AND column_name = 'month'""", e).empty
        month = "month" if has_month else "NULL::smallint AS month"
        d["learning"] = pd.read_sql(
            f"""SELECT id, title, url, publisher, year, {month}, doc_type, scope, country_iso3,
                      hazard, premises, key_stat, summary, section, source
               FROM aa.learning_document WHERE NOT internal AND {NOT_SOCIAL_SQL}
               ORDER BY year DESC NULLS LAST, {"month DESC NULLS LAST, " if has_month else ""}title""", e)
        d["n_internal_docs"] = int(pd.read_sql(
            "SELECT count(*) AS n FROM aa.learning_document WHERE internal", e)["n"].iloc[0])
    except Exception as exc:
        print(f"  learning: aa.learning_document unavailable ({exc.__class__.__name__})")
        d["learning"] = pd.DataFrame(columns=["id", "title", "url", "publisher", "year", "month",
                                              "doc_type", "scope", "country_iso3", "hazard",
                                              "premises", "key_stat", "summary", "section",
                                              "source"])
        d["n_internal_docs"] = 0
    try:
        d["partners"] = pd.read_sql(
            """SELECT country_iso3, hazard, version, name, acronym, org_type, roles,
                      agency_parent, amount_usd, evidence, source
               FROM aa.framework_partner ORDER BY org_type, name""", e)
    except Exception as exc:
        print(f"  partners: aa.framework_partner unavailable ({exc.__class__.__name__})")
        d["partners"] = pd.DataFrame(columns=["country_iso3", "hazard", "version", "name",
                                              "acronym", "org_type", "roles", "agency_parent",
                                              "amount_usd", "evidence", "source"])
    # ---- framework pages: version metadata (for the version diff), the backtest, the
    # activation links; funding page: the flow Sankey. Each tolerant of an older snapshot.
    def _opt(key, sql, cols):
        try:
            d[key] = pd.read_sql(sql, e)
        except Exception as exc:
            print(f"  {key}: unavailable ({exc.__class__.__name__})")
            d[key] = pd.DataFrame(columns=cols)
    _opt("vpage", """SELECT kb_framework, version::text AS version, frontmatter, triggers
                     FROM aa.version_page""", ["kb_framework", "version", "frontmatter", "triggers"])
    _opt("fv_meta", """SELECT country_iso3, hazard, version::text AS version, kb_framework,
                              valid_from, valid_until, note, analysis_ref, doc_url, doc_title
                       FROM aa.framework_version ORDER BY country_iso3, hazard, valid_from""",
         ["country_iso3", "hazard", "version", "kb_framework", "valid_from", "valid_until", "note",
          "analysis_ref", "doc_url", "doc_title"])
    try:   # with the dated columns when the DB has them (event_date, event_time, …)
        d["sim"] = read_simulated(e)
    except Exception as exc:
        print(f"  sim: unavailable ({exc.__class__.__name__})")
        d["sim"] = pd.DataFrame(columns=["country_iso3", "hazard", "version", "window_name",
                                         "event_year", "event_label", *SIM_DATED])
    _opt("wact", """SELECT country_iso3, hazard, event_date::text AS event_date, window_name,
                           full_activation FROM aa.window_activation""",
         ["country_iso3", "hazard", "event_date", "window_name", "full_activation"])
    _opt("actual_url", """SELECT kb_framework, event_date::text AS event_date, window_name, url
                          FROM aa.actual_activation WHERE url IS NOT NULL""",
         ["kb_framework", "event_date", "window_name", "url"])
    _opt("cerf_year", "SELECT application_code, year FROM aa.cerf_allocation",
         ["application_code", "year"])
    _opt("cbpf_org", """SELECT p.allocation_year AS year, fu.fund_code, p.org_type,
                               sum(p.budget) AS usd
                        FROM aa.cbpf_project p
                        JOIN aa.cbpf_allocation a ON a.pooled_fund_id = p.pooled_fund_id
                         AND a.allocation_type_id = p.allocation_type_id
                        LEFT JOIN aa.fund fu ON fu.pf_id = p.pooled_fund_id
                        WHERE a.aa_keyword AND p.budget IS NOT NULL GROUP BY 1, 2, 3""",
         ["year", "fund_code", "org_type", "usd"])
    d["fund_names"] = pd.read_sql("SELECT fund_code, fund_type, name, country_iso3 FROM aa.fund", e)
    REGIONAL_FUNDS.clear()
    REGIONAL_FUNDS.update(d["fund_names"].loc[d["fund_names"]["fund_type"] == "regional_fund", "fund_code"])
    # Financing money flows: CBPF AA project budgets by grantee organisation (named grantees;
    # cbpf_org above keeps the type-only split for an older snapshot)
    _opt("cbpf_org_name", """SELECT p.allocation_year AS year, fu.fund_code,
                                    coalesce(p.org_name, 'organisation not recorded') AS org_name, p.org_type,
                                    sum(p.budget) AS usd
                             FROM aa.cbpf_project p
                             JOIN aa.cbpf_allocation a ON a.pooled_fund_id = p.pooled_fund_id
                              AND a.allocation_type_id = p.allocation_type_id
                             LEFT JOIN aa.fund fu ON fu.pf_id = p.pooled_fund_id
                             WHERE a.aa_keyword AND p.budget IS NOT NULL
                             GROUP BY 1, 2, 3, 4""",
         ["year", "fund_code", "org_name", "org_type", "usd"])
    _resolve_pooled_fund(d)
    _merge_labels(d)
    return d


# the same agency under two names (PAHO is WHO's regional office for the Americas)
AGENCY_ALIAS = {"WHO": "WHO (incl. PAHO)", "PAHO": "WHO (incl. PAHO)", "WHO/PAHO": "WHO (incl. PAHO)",
                "OPS": "WHO (incl. PAHO)", "OPS/OMS": "WHO (incl. PAHO)", "OMS": "WHO (incl. PAHO)"}
# co-financers under one name (the Financing page's chart by co-financer): the agencies as above,
# and the Red Cross emergency fund by its owner's name
COF_ALIAS = {**AGENCY_ALIAS, "PAHO/WHO": "WHO (incl. PAHO)", "DREF": "IFRC DREF"}
# a co-financing line that names a group, not an organisation: a total in words
# ('partners will contribute up to USD 3.7 million'), never one co-financer's share
COF_GROUP = {"partners", "other partners"}


def _cof_base(financier):
    """A financier without its trailing parenthetical (the kind of money or the channel:
    'FAO (preparedness co-financing)', 'DFAT (via Nepal Multi-Partner Trust Fund)')."""
    fin = financier.strip() if isinstance(financier, str) else ""
    return re.sub(r"\s*\([^()]*\)\s*$", "", fin).strip()


def cof_who(financier, agency):
    """The co-financer a co-financing line names, one name per organisation (2026-10-28 owner
    comment): the financier without its parenthetical; an agency's own money ('Agency
    co-financing (GFFO)', 'WFP HQ Trust Fund…') under the agency. None for a line that names
    no one, or only a group (COF_GROUP)."""
    base, ag = _cof_base(financier), agency.strip() if isinstance(agency, str) else ""
    if ag and (not base or base.lower().startswith("agency co-financ")
               or re.match(re.escape(ag) + r"\b", base)):
        base = ag
    return None if not base or base.lower() in COF_GROUP else COF_ALIAS.get(base, base)


def _merge_labels(d):
    """One name per agency and per sector in the money charts (2026-10-16 LAC review: PAHO
    and WHO, food security and food assistance, were shown apart). Sectors go to the Plan
    page's IASC buckets where a label maps to exactly one; a combined label ('WASH &
    Nutrition') keeps its own name, since its money can't be split."""
    from page_plan import OTHER_SECTOR, _buckets
    def sector(x):
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return x
        b = _buckets(x)
        return b[0] if len(b) == 1 and b[0] != OTHER_SECTOR else x
    for k in ("agency", "plan_rows", "split_all"):
        if k in d and "agency" in d[k]:
            d[k]["agency"] = d[k]["agency"].map(lambda x: AGENCY_ALIAS.get(x, x) if isinstance(x, str) else x)
    for k in ("sector", "plan_rows", "split_all"):
        if k in d and "sector" in d[k]:
            d[k]["sector"] = d[k]["sector"].map(sector)


def _resolve_pooled_fund(d):
    """'cbpf-unspecified' (a sheet row that named no pooled fund) -> the country's own pooled
    fund, where the registry knows exactly one for that country (a CBPF, or a regional fund's
    country window). 2026-10-02 meeting: the 2023 non-framework allocations of Somalia, South Sudan
    and Yemen sat in one 'CBPF (fund not recorded)' node with no donors, so Yemen looked
    missing. A country with no registered fund, or several, keeps 'cbpf-unspecified'."""
    reg = d["fund_names"]
    pf = reg[(reg["fund_type"] != "cerf") & reg["country_iso3"].notna()]
    one = {c: g.iloc[0] for c, g in pf.groupby("country_iso3")["fund_code"] if len(g) == 1}
    for k in ("prearranged", "activation"):
        df = d[k]
        m = (df["fund_code"] == "cbpf-unspecified") & df["country_iso3"].isin(one)
        df.loc[m, "fund_code"] = df.loc[m, "country_iso3"].map(one)
    # a resolved row can now meet a row that named the fund: one per key, by source priority
    d["prearranged"] = canonical(d["prearranged"], ["country_iso3", "hazard", "year", "kind",
                                                    "fund_code", "financier"])


def _dash_page(page, name, title, intro, panels_html, data_json, js_body):
    body = f"""
<div class='card'>{intro}</div>
{panels_html}
<script src="chart.umd.js"></script>
<script>window.D = {data_json}; window.REGIONAL_FUNDS = {json.dumps(sorted(REGIONAL_FUNDS))};</script>
<script>{DASH_JS}\n{js_body}</script>
<style>{DASH_CSS}</style>"""
    page(name, title, body)


def _records(df, cols=None):
    df = df if cols is None else df[cols]
    return json.dumps(json.loads(df.to_json(orient="records")), default=str)


def funding_series(d, released="framework"):
    """The annual series the Funding page charts — and the donor-shares page attributes.
    pre: pre-arranged rows per framework-year (sheets/KB/entries, canonical) plus
    AA-tagged CBPF/RhPF allocations from the OneGMS mirror (specific fund_code where
    aa.fund knows the pooled fund). act: allocation drawn per activation × fund."""
    pre = d["prearranged"].copy()
    pre["hz"] = pre["hazard"].map(haz)
    cur = d["current"]
    reg_map = dict(zip(zip(d["current"]["country_iso3"], d["current"]["hazard"]),
                       d["current"]["region"]))
    pre["region"] = [reg_map.get((c, h)) or "?" for c, h in
                     zip(pre["country_iso3"], pre["hazard"])]
    act = d["activation"].copy()
    # released money: framework activations by default (what every total showed until
    # 2026-09-30 and what matches the digest); released="all" adds ad hoc AA allocations,
    # for pages with an ad hoc toggle. Early action never comes through (EXCLUDED_EVENT_TYPES).
    if released == "framework":
        act = act[act["event_type"] == "framework_aa"]
    act["hz"] = act["hazard"].map(haz)
    gho = d["gho"]
    gho_set = set(map(tuple, gho.loc[gho["in_gho"], ["country_iso3", "year"]].values))
    pre["in_gho"] = [
        (c, y) in gho_set for c, y in zip(pre["country_iso3"], pre["year"])]
    act["year"] = act["event_date"].str[:4].astype(int)
    act["in_gho"] = [
        (c, y) in gho_set for c, y in zip(act["country_iso3"], act["year"])]

    # CBPF / regional-fund pre-arranged money comes from the OneGMS mirror (AA-tagged
    # allocations, allocated up front); sheet-era CBPF rows are kept only for country-years
    # the mirror does not cover, so the same money is never counted twice.
    # 2026-10-02: only where a framework stood behind the allocation — one drawn by a
    # framework activation, or one drawn by no activation, approved, in a country with a
    # framework version in force that year. One drawn by an ad hoc or early-action
    # allocation is released money (or none), never a stock; one with no framework behind
    # it (Sudan's) is not pre-arranged; one never approved did not happen.
    import datetime as _dt
    cb = d["cbpf_aa"].copy()
    fvm = d["fv_meta"]
    vf_y = pd.to_datetime(fvm["valid_from"].astype(str), errors="coerce").dt.year
    vu_y = (pd.to_datetime(fvm["valid_until"].astype(str), errors="coerce").dt.year
            if "valid_until" in fvm.columns else pd.Series(float("nan"), index=fvm.index))
    in_force = {(c, int(y)) for c, a, b in zip(fvm["country_iso3"], vf_y, vu_y) if pd.notna(a)
                for y in range(int(a), (int(b) if pd.notna(b) else _dt.date.today().year) + 1)}
    by_fw = cb["by_framework"].fillna(False).astype(bool) if "by_framework" in cb else cb["linked"].astype(bool)
    by_other = cb["by_other"].fillna(False).astype(bool) if "by_other" in cb else pd.Series(False, index=cb.index)
    approved = (pd.to_numeric(cb["approved_budget"], errors="coerce").fillna(1) > 0
                if "approved_budget" in cb else pd.Series(True, index=cb.index))
    standing = pd.Series([(c, int(y)) in in_force for c, y in zip(cb["country_iso3"], cb["year"])],
                         index=cb.index)
    cb = cb[by_fw | (~by_other & approved & standing)]
    live = cur[cur["lifecycle"].isin(["active", "updating", "development"])]
    hz_by_c = live.groupby("country_iso3")["hazard"].agg(
        lambda x: x.iloc[0] if x.nunique() == 1 else "multi")
    cb["hazard"] = cb["country_iso3"].map(hz_by_c).fillna("?")
    cb["hz"] = cb["hazard"].map(haz)
    cb["region"] = cb["country_iso3"].map(
        dict(zip(cur["country_iso3"], cur["region"]))).fillna("?")
    cb["kind"] = "prearranged"
    cb["fund_code"] = cb["fund_code"].fillna(
        cb["fund_type"].map({"regional_fund": "rhpf"}).fillna("cbpf"))
    cb["financier"] = cb["fund_name"]
    cb["source"] = "onegms-mirror"
    cb["version"] = None            # a country-level allocation: no framework version
    cb["in_gho"] = [(c, y) in gho_set for c, y in zip(cb["country_iso3"], cb["year"])]
    mirror_cy = set(zip(cb["country_iso3"], cb["year"]))
    pre = pre[~(pre["fund_code"].str.startswith(("cbpf", "rhpf"))
                & pd.Series([(c, y) in mirror_cy for c, y in
                             zip(pre["country_iso3"], pre["year"])], index=pre.index))]
    pre = pd.concat([pre, cb[pre.columns]], ignore_index=True)
    # a version that allows two activations a year (activation_factors): its pre-arranged rows
    # count twice, as prearranged_now does for the current year (whose rows, already multiplied,
    # replace this year's below — never multiplied twice): the CERF rows only, as there.
    # Co-financing is left as recorded.
    fac = d.get("act_factors") or {}
    if fac:
        n = pd.Series([fac.get((c, h, str(v)), 1) if k == "prearranged" and f == "cerf" else 1
                       for c, h, v, k, f in zip(pre["country_iso3"], pre["hazard"], pre["version"], pre["kind"],
                                                pre["fund_code"])],
                      index=pre.index, dtype=float)
        pre["amount_usd"] = pre["amount_usd"].astype(float) * n
    # the current year is pre-arranged money NOW (prearranged_now: the framework records), not
    # the sheets or the mirror — one figure on every page. Past years keep the reported series
    # until the official year-end reports are loaded.
    import datetime as _dt
    yr = _dt.date.today().year
    now = d["vfund"].rename(columns={"total_usd": "amount_usd"}).copy()
    now = now.assign(year=yr, kind="prearranged", financier=None, source="framework-record",
                     hz=now["hazard"].map(haz),
                     region=[reg_map.get((c, h)) or "?" for c, h in zip(now["country_iso3"], now["hazard"])],
                     in_gho=[(c, yr) in gho_set for c in now["country_iso3"]])
    pre = pd.concat([pre[~((pre["kind"] == "prearranged") & (pre["year"] == yr))], now[pre.columns]],
                    ignore_index=True)
    return pre, act


def cofinancing_now(d, cof, cy):
    """Each framework's co-financing NOW, by co-financer (2026-10-28 owner comment: the sheets'
    yearly totals name no one; the framework documents do) — the Financing page's charts and the
    map's current year count it. cof: the dated co-financing rows (funding_series, kind
    'cofinancing'). A framework's figure is its current-year total (the sheet totals are
    authoritative for amounts), split in the proportions of the lines its latest version states
    (d["cof_lines"]) when the lines make the total within 5% (the document's own figures), or
    exceed a total reported for the same version (scaled down to it); lines short of the total
    keep their stated figures and leave the rest 'not recorded'; an earlier version's smaller total
    gives way to the lines; the lines themselves where no yearly total is recorded; the total under its own financier ("not
    recorded" when it names none) where no line does. A line naming only a group ('partners',
    COF_GROUP) is a total in words, not a line. One source per version (the most recently
    entered), so a document read twice is not counted twice — but a later entry of other lines
    for the same version under a new source would hide the earlier set: enter a version's lines
    together, under one source. A dated row that also carries an agency is in neither the
    totals (aa.prearranged_funding) nor the lines (undated): none is recorded today. Rows:
    country_iso3, hazard, version, who, detail (the line as recorded), amount_usd."""
    ln = d["cof_lines"].copy()
    ln = ln[[not (_cof_base(f).lower() in COF_GROUP and not isinstance(a, str))
             for f, a in zip(ln["financier"], ln["agency"])]]
    if len(ln):
        last = ln.sort_values("updated_at").groupby(["country_iso3", "hazard"])["source"].last()
        ln = ln[[last.get((c, h)) == s for c, h, s in zip(ln["country_iso3"], ln["hazard"], ln["source"])]]
    tot = cof[(cof["kind"] == "cofinancing") & (cof["year"] == cy) & cof["amount_usd"].notna()]
    out = []
    for c, h in sorted(set(zip(tot["country_iso3"], tot["hazard"])) | set(zip(ln["country_iso3"], ln["hazard"]))):
        t = tot[(tot["country_iso3"] == c) & (tot["hazard"] == h)]
        lk = ln[(ln["country_iso3"] == c) & (ln["hazard"] == h)]
        if len(lk) and lk["amount_usd"].sum() > 0:
            lsum, tsum = float(lk["amount_usd"].sum()), float(t["amount_usd"].sum()) if len(t) else None
            # the total split in the lines' proportions only when both belong to the same version (or
            # nearly agree): another version's lines would put figures on organisations that no
            # document states (review of PR #58: Cuba's 2025 total over the 2026 lines gave WFP $2.3M,
            # the document $218k). Otherwise the lines count as stated and whatever the total holds
            # beyond them stays unattributed ('not recorded'); a later document stating more than an
            # older version's total counts its lines.
            # proportional only where the lines nearly make the total, or (same version) exceed it and
            # the total binds; lines short of the total keep their stated figures and the shortfall
            # stays 'not recorded' (Niger floods: FAO's $100k stated, WFP's amount still to confirm)
            same_v = tsum is not None and set(t["version"].astype(str)) == set(lk["version"].astype(str))
            same = tsum is not None and (abs(lsum - tsum) <= 0.05 * tsum or (same_v and lsum > tsum))
            f = tsum / lsum if same else 1.0
            rest = round(tsum - lsum, 2) if tsum is not None and not same and tsum > lsum else 0.0
            parts = [(r.version, r.financier, r.agency, round(float(r.amount_usd * f), 2)) for r in lk.itertuples()]
            # cents: the parts add up to the framework's figure exactly
            fig = round(tsum if same else lsum, 2)
            v, fin, ag, usd = parts[-1]
            parts[-1] = (v, fin, ag, round(usd + fig - sum(x[3] for x in parts), 2))
            if rest:
                parts.append((t["version"].iloc[-1], None, None, rest))
        else:
            parts = [(r.version, r.financier, None, float(r.amount_usd)) for r in t.itertuples()]
        for v, fin, ag, usd in parts:
            fin = fin if isinstance(fin, str) else ""
            ag = ag if isinstance(ag, str) else ""
            out.append({"country_iso3": c, "hazard": h, "version": v,
                        "who": cof_who(fin, ag) or "not recorded", "amount_usd": usd,
                        "detail": " — ".join(x for x in (fin, ag if ag not in fin else "") if x)})
    return pd.DataFrame(out, columns=["country_iso3", "hazard", "version", "who", "detail", "amount_usd"])

# Recipient categories of the money-flow Sankey: the colour of every recipient node, at every
# level (agencies / grantees, and the final column). Keys are carried in the node ids; the
# labels, plurals and colours live in FLOW_JS (CAT_*). Plural only for the fallback nodes.
RECIPIENT_PLURAL = {"un": "UN agencies", "ingo": "international NGOs", "nngo": "national / local NGOs",
                    "gov": "government partners", "rc": "Red Cross / Red Crescent", "oth": "other partners",
                    "nr": "type not recorded"}


def _recipient_cat(t):
    """A CERF sub-grant partner type (INGO, NNGO, GOV, RedC, TBD) or a CBPF org type
    (International NGO, National NGO, UN Agency, Red Cross/Red Crescent Organization, Others)
    -> a recipient category key: un, ingo, nngo, gov, rc, oth, nr (not recorded)."""
    u = " ".join(str(t or "").split()).upper()
    if not u or u in ("NAN", "NONE", "TBD"):
        return "nr"
    if u == "INGO" or "INTERNATIONAL" in u:
        return "ingo"
    if u in ("NNGO", "LNGO") or "NATIONAL" in u or "LOCAL" in u:
        return "nngo"
    if u.startswith("GOV"):
        return "gov"
    if u.startswith("REDC") or "RED CROSS" in u or "RED CRESCENT" in u:
        return "rc"
    if u in ("UN", "UN AGENCY", "UN AGENCIES"):
        return "un"
    return "oth"


def _agency_node(name):
    """A CERF / framework-split agency -> its node key 'cat|name': UN (CERF funds UN agencies
    only; the framework splits name UN agencies), not recorded for a placeholder."""
    import re as _re
    n = str(name)
    return ("nr|" if _re.search(r"to be determined|not recorded", n, _re.IGNORECASE) else "un|") + n


def _layer_of(d):
    """(country, hazard[, version]) -> the map layer its money belongs to: 'r' a retired
    framework, 'c' any other (current frameworks, and the odd AA-tagged CBPF allocation in a
    country whose only framework is still in the pipeline, e.g. Sudan). A row that carries its
    version (activations, pre-arranged rows) is 'r' when that version is outside the pair's current
    line (old_versions: Somalia drought 2019 / 2020-06-23), whatever the pair's status. CBPF
    mirror rows are country-level (hazard 'multi' or '?'): 'r' only when the country has
    retired frameworks and no live one. Non-framework allocations are their own layer ('a'), set by
    the caller from event_type."""
    cur = d["current"]
    pair = dict(zip(zip(cur["country_iso3"], cur["hazard"]), cur["lifecycle"]))
    ret_c = set(cur.loc[cur["lifecycle"] == "retired", "country_iso3"])
    live_c = set(cur.loc[cur["lifecycle"].isin(["active", "updating", "development"]), "country_iso3"])
    old = d.get("old") or set()

    def layer(c, h, version=None):
        if version is not None and (c, h, str(version)) in old:
            return "r"      # an earlier framework, replaced by a distinct new one
        lc = pair.get((c, h))
        if lc is not None:
            return "r" if lc == "retired" else "c"
        return "r" if (c in ret_c and c not in live_c) else "c"
    return layer


# fund codes the registry (aa.fund) types as a regional fund: filled by _fetch. Some regional
# fund windows carry cbpf-* codes (Vanuatu, Fiji, Bangladesh under the AP-RhPF; Kenya, Uganda
# under the ESAHF), so the type comes from the registry, the rhpf- prefix only as a fallback
REGIONAL_FUNDS = set()


def _ft(fc):
    """'cerf', 'regional_fund' or 'cbpf' for a fund code."""
    return ("cerf" if fc == "cerf" else
            "regional_fund" if (fc in REGIONAL_FUNDS or str(fc).startswith("rhpf")) else "cbpf")


def _fu(fc):
    """Fund type letter carried by the flow rows: c CERF, r regional fund, p country CBPF."""
    return {"cerf": "c", "regional_fund": "r"}.get(_ft(fc), "p")


def country_en(c, cname):
    """A country's English name: the site's own (aa.country_hazard, cname), else pycountry's
    common name — never the ISO3 code where a name exists."""
    if isinstance(cname.get(c), str):
        return cname[c]
    try:
        import pycountry
        x = pycountry.countries.get(alpha_3=c)
        return getattr(x, "common_name", None) or x.name
    except Exception:
        return c


def _by_key(s, n):
    """A Series on a MultiIndex -> {its first n levels (a tuple): the Series of the other levels}."""
    if not len(s):
        return {}
    lv = list(range(n))
    return {k: g.droplevel(lv) for k, g in s.groupby(level=lv)}


def _money_flows(d, pre, act):
    """Link rows {m, y, lv, s, t, v, g, fu} for the two 'Where the money flows' Sankeys
    (the Financing page, and the donor-flows view of the donor-shares page).

    The two are kept apart on purpose (never summed): pre-arranged money is a STOCK — the
    envelopes in place at a date — while released money is a FLOW, per year. Released money
    is drawn from the pre-arranged envelopes, so adding the two double-counts it.

    m 'p' pre-arranged, as at the end of year y (the current year: today). One row per
      framework × fund (the Financing page's canonical series); fund -> agency from the agency
      split of the version in force that year (v_window_funding_split, scaled to the
      envelope); CBPF / RhPF allocations by grantee organisation. No final column: who a UN
      agency sub-grants to is only known once money is released. Years are never added up.
    m 'r' released in year y: activation funding; CERF -> agency from the AA projects
      approved that year (scaled to the released total); agency -> the named partners of the
      CERF AA sub-grants, and the rest -> a final node with the agency's own name (what it
      implements itself); CBPF / RhPF -> grantee organisation (AA-keyword project budgets),
      each running on to the same organisation in the final column (grantees implement
      directly). Every band reaches the last column. Years add up.
    lv: 'd' donor -> fund (donor share of the fund's paid income that year × the amount),
        'f' fund -> agency / grantee, 'a' agency / grantee -> final recipient.
    c (the 'f' rows only): the country the money went to — the framework's country (pre-arranged),
      the activation's (released); '' where no single country is recorded (a regional fund's
      allocation with no country): FLOW_JS's optional countries column (2026-10-28) splits each
      'f' link at it, fund -> country -> agency. CERF's released money reaches the agencies by the
      country's own AA projects approved that year and the agencies' sub-grants in that country
      (the region's, where the country has none that year).
    Recipient node ids carry their category (_recipient_cat): 'a:<cat>|<agency>' and
    'p:<cat>|<agency>' (always named), 'a:<cat>~<organisation>' and 'p:<cat>~<organisation>'
    (a partner / grantee: FLOW_JS names the top ones of the view and groups the rest per
    category). One spelling and one category per organisation across CERF and the CBPFs.
    g: the map layer of the money, for the page toggles — 'c' current frameworks, 'r' retired
       frameworks, 'a' non-framework allocations (released only; pass act from
       funding_series(d, released="all") to have them). fu: fund type, 'c' CERF, 'p' CBPF,
       'r' regional fund. Every split is linear in the amount, so the per-layer rows add up
       to the same totals as one pass over all the money. Rows with the same keys are summed.
    names: fund code -> fund name, and 'c:<ISO3>' -> the country's English name."""
    import datetime as _dt
    import re as _re
    today = _dt.date.today()
    C = d["contrib"].copy()
    C = C[C["paid_usd"].fillna(0) > 0]
    C["fund_code"] = C["fund_code"].fillna("cbpf:" + C["fund_name"].astype(str))
    C = C.groupby(["fund_code", "year", "donor"], as_index=False)["paid_usd"].sum()
    # the region of each country, so the Financing page's region filter reaches the chart
    # (2026-10-16 LAC review: the flows stayed global): every row carries 'rg', and CERF's
    # agency and sub-grant splits are taken within the region, so the regions add up to the world
    cur_ = d["current"]
    rg_of = dict(zip(cur_["country_iso3"], cur_["region"].fillna("?")))
    AG = d["agency"].assign(rg=d["agency"]["country_iso3"].map(rg_of).fillna("?"))
    ag = AG.groupby(["year", "rg", "agency"])["amount_approved"].sum()
    # recipient organisations: CERF AA sub-grant partners and CBPF AA grantees, one node per
    # organisation (case / spacing folded), named as most of its money spells it and in the
    # category most of its money carries
    sg = d["subgrant_aa"].copy()
    sg["cat"] = sg["partner_type"].map(_recipient_cat)
    con = d.get("cbpf_org_name")
    named = con is not None and len(con) > 0
    if named:
        co = con.copy()
        co["cat"] = co["org_type"].map(_recipient_cat)
    else:   # older snapshot: grantee types only, one node per category
        co = d["cbpf_org"].copy()
        co["cat"] = co["org_type"].map(_recipient_cat)
        co["org_name"] = co["cat"].map(lambda c: "Country and Regional Fund grantees — " + RECIPIENT_PLURAL[c])
    import html as _html
    import re as _re
    placeholder = _re.compile(r"\b(tbd|to be determined|partner to be determined|not recorded)\b", _re.I)

    def fold(s):   # one key per organisation: entities decoded, case, spaces and punctuation ignored
        return _re.sub(r"[^0-9a-z]+", "", _html.unescape(str(s)).casefold())
    sg["partner_name"] = sg["partner_name"].astype(str).map(_html.unescape)
    co["org_name"] = co["org_name"].astype(str).map(_html.unescape)
    # a national society typed only 'Others' (the CBPF org type of the Nigerian and Vanuatu Red
    # Cross Societies) is still Red Cross / Red Crescent
    rc_name = r"red cross|red crescent|croix[- ]rouge|cruz roja|croissant[- ]rouge"
    for f_, ncol in ((sg, "partner_name"), (co, "org_name")):
        f_.loc[f_["cat"].isin(["oth", "nr"]) & f_[ncol].astype(str).str.contains(rc_name, case=False), "cat"] = "rc"
    reg = pd.concat([sg[["partner_name", "cat", "subgrant_usd"]].set_axis(["name", "cat", "usd"], axis=1),
                     co[["org_name", "cat", "usd"]].set_axis(["name", "cat", "usd"], axis=1)])
    reg["k"] = reg["name"].map(fold)
    spell = reg.groupby(["k", "name"])["usd"].sum().reset_index().sort_values("usd").groupby("k")["name"].last()
    kcat = reg.groupby(["k", "cat"])["usd"].sum().reset_index().sort_values("usd").groupby("k")["cat"].last()
    sep = "~" if named else "|"     # fallback category nodes are not organisations: never grouped
    org_node = {k: f"{kcat[k]}{sep}{spell[k]}" for k in spell.index}
    # placeholder names ("TBD", "Partner to be determined") are not organisations: one node,
    # category not recorded, '|' so the browser never ranks or groups it as a named partner
    for k in spell.index:
        if placeholder.search(str(spell[k])) or kcat[k] == "nr":
            org_node[k] = "nr|partner not recorded"
    sg["node"] = sg["partner_name"].map(fold).map(org_node)
    co["node"] = co["org_name"].map(fold).map(org_node)
    sg["rg"] = sg["country_iso3"].map(rg_of).fillna("?")
    sgm = sg.groupby(["year", "rg", "agency", "node"])["subgrant_usd"].sum()
    co = co.groupby(["fund_code", "year", "node"])["usd"].sum()
    split = d["split_all"].copy()
    split["version"] = split["version"].astype(str)
    fvm = d["fv_meta"].copy()
    fvm["vf"] = pd.to_datetime(fvm["valid_from"], errors="coerce")
    layer = _layer_of(d)
    rows = []

    def add(m, y, lv, s_, t, v, g, fc, rg, c=None):
        if v and v > 0.5:
            r = {"m": m, "y": int(y), "lv": lv, "s": s_, "t": t, "v": float(v), "g": g, "fu": _fu(fc), "rg": rg}
            if lv == "f":       # the country column's key ('' = no single country)
                r["c"] = c if isinstance(c, str) else ""
            rows.append(r)

    def donors(m, y, fc, amount, g, rg):
        cy = C[(C["fund_code"] == fc) & (C["year"] == y)]
        inc = cy["paid_usd"].sum()
        if inc > 0:
            for r in cy.itertuples():
                add(m, y, "d", "d:" + r.donor, "f:" + fc, r.paid_usd / inc * amount, g, fc, rg)
        else:
            add(m, y, "d", "d:(donors not recorded)", "f:" + fc, amount, g, fc, rg)

    def grantees(m, y, fc, amount, g, rg, c):
        # released money: a CBPF / RhPF grantee implements directly (no sub-grant level), so
        # its band runs on, same amount, to the same organisation in the final column — every
        # band then reaches the last column and each grantee node stays balanced (in = out)
        def on(node, v, final):
            add(m, y, "f", "f:" + fc, "a:" + node, v, g, fc, rg, c)
            if m == "r":
                add(m, y, "a", "a:" + node, "p:" + final, v, g, fc, rg)
        o = co[(co.index.get_level_values(0) == fc) & (co.index.get_level_values(1) == y)] if len(co) else co
        osum = float(o.sum()) if len(o) else 0.0
        if osum <= 0:
            on("nr|Country and Regional Fund grantees not recorded", amount, "nr|grantee not recorded")
            return
        for (_f, _a, node), v in o.items():
            cat = node.split(sep)[0]
            final = node if named else f"{cat}|{RECIPIENT_PLURAL[cat]}"
            on(node, v / osum * amount, final)

    # ---------------- pre-arranged, as at the end of each year (never summed over years)
    P = pre[(pre["kind"] == "prearranged") & (pre["fund_code"] != "all") & (pre["year"] <= today.year)]
    P = P.assign(g=[layer(c, h, v) for c, h, v in zip(P["country_iso3"], P["hazard"], P["version"])],
                 rg=P["country_iso3"].map(rg_of).fillna("?"))
    for y, py in P.groupby("year"):
        y = int(y)
        at = pd.Timestamp(min(_dt.date(y, 12, 31), today))
        for (fc, g, rg), amount in py.groupby(["fund_code", "g", "rg"])["amount_usd"].sum().items():
            donors("p", y, fc, amount, g, rg)
        for r in py.itertuples():
            fc, amount, g, rg, c = r.fund_code, float(r.amount_usd), r.g, r.rg, r.country_iso3
            if amount <= 0:
                continue
            if fc != "cerf" and r.source == "onegms-mirror":
                grantees("p", y, fc, amount, g, rg, c)
                continue
            # the agency split of the version in force at that date (latest one with a split)
            vs = fvm[(fvm["country_iso3"] == r.country_iso3) & (fvm["hazard"] == r.hazard)
                     & (fvm["vf"].isna() | (fvm["vf"] <= at))].sort_values("vf")
            sp = None
            for v in reversed(list(vs["version"].astype(str))):
                cand = split[(split["country_iso3"] == r.country_iso3) & (split["hazard"] == r.hazard)
                             & (split["version"] == v) & split["agency"].notna()]
                if len(cand):
                    if fc == "cerf":
                        own = cand[cand["fund_code"].isin(["cerf"]) | cand["fund_code"].isna()]
                    else:   # a pooled fund's money never borrows CERF's agency split
                        own = cand[cand["fund_code"].isin([fc, "cbpf-unspecified", "cbpf", "rhpf"])]
                    sp = own if len(own) else None
                    break
            if (sp is None or sp["amount_usd"].sum() <= 0) and fc != "cerf":
                grantees("p", y, fc, amount, g, rg, c)   # pooled funds: grantee types, as allocated
                continue
            if sp is None or sp["amount_usd"].sum() <= 0:
                add("p", y, "f", "f:" + fc, "a:nr|agencies not recorded", amount, g, fc, rg, c)
                continue
            shares = sp.groupby("agency")["amount_usd"].sum()
            for agency, v in shares.items():
                add("p", y, "f", "f:" + fc, "a:" + _agency_node(agency), v / shares.sum() * amount, g, fc, rg, c)

    # ---------------- released, in the year it went out (years add up); one pass per layer
    R = act[act["amount_usd"].fillna(0) > 0]
    R = R.assign(g=["a" if et == "adhoc_aa" else layer(c, h, v)     # v: an old version -> retired
                    for et, c, h, v in zip(R["event_type"], R["country_iso3"], R["hazard"], R["version"])],
                 rg=R["country_iso3"].map(rg_of).fillna("?"), c=R["country_iso3"].fillna(""))
    for (fc, y, g, rg), amount in R.groupby(["fund_code", "year", "g", "rg"])["amount_usd"].sum().items():
        donors("r", int(y), fc, amount, g, rg)
    # CERF -> agency -> partner, per country (the countries column shows the country's own
    # agencies): the AA projects approved that year in the country and the agencies' sub-grants
    # there; the region's (its countries together) where the country has no project that year
    ag_c = _by_key(AG.groupby(["year", "country_iso3", "agency"])["amount_approved"].sum(), 2)
    ag_r = _by_key(ag, 2)
    sg_c = _by_key(sg.groupby(["year", "country_iso3", "agency", "node"])["subgrant_usd"].sum(), 3)
    sg_r = _by_key(sgm, 3)
    for (fc, y, g, rg, c), amount in R.groupby(["fund_code", "year", "g", "rg", "c"])["amount_usd"].sum().items():
        y = int(y)
        if fc != "cerf":
            grantees("r", y, fc, amount, g, rg, c)
            continue
        key, a_, subs = (y, c), ag_c.get((y, c)), sg_c
        if a_ is None or float(a_.sum()) <= 0:
            key, a_, subs = (y, rg), ag_r.get((y, rg)), sg_r
        asum = float(a_.sum()) if a_ is not None else 0.0
        if asum <= 0:
            add("r", y, "f", "f:cerf", "a:nr|agencies not recorded", amount, g, fc, rg, c)
            add("r", y, "a", "a:nr|agencies not recorded", "p:nr|recipient not recorded", amount, g, fc, rg)
            continue
        k = amount / asum
        for agency, v in a_.items():
            node = _agency_node(agency)
            add("r", y, "f", "f:cerf", "a:" + node, v * k, g, fc, rg, c)
            s_ = subs.get(key + (agency,))
            tot_s = float(s_.sum()) if s_ is not None else 0.0
            parts = min(tot_s, float(v)) * k
            kept = 0.0      # partner rows too small to keep stay with the agency: in = out
            for pnode, sv in (s_.items() if tot_s else ()):
                pv = round(sv / tot_s * parts, 2)
                if pv > 0.5:
                    add("r", y, "a", "a:" + node, "p:" + pnode, pv, g, fc, rg)
                    kept += pv
            # what the agency implements itself: a final node with its own name
            add("r", y, "a", "a:" + node, "p:" + node, v * k - kept, g, fc, rg)

    # one row per link and keys (the per-country split writes the same link many times)
    agg = {}
    for r in rows:
        k_ = (r["m"], r["y"], r["lv"], r["s"], r["t"], r["g"], r["fu"], r["rg"], r.get("c"))
        agg[k_] = agg.get(k_, 0.0) + r["v"]
    rows = []
    for (m, y, lv, s_, t, g, fu, rg, c), v in agg.items():
        r = {"m": m, "y": y, "lv": lv, "s": s_, "t": t, "v": round(v, 2), "g": g, "fu": fu, "rg": rg}
        if c is not None:
            r["c"] = c
        rows.append(r)

    # ---------------- fund labels from the registry, one RhPF spelling
    names = {"cerf": "CERF", "cbpf-unspecified": "CBPF (fund not recorded)", "cbpf": "CBPF (not in registry)",
             "rhpf": "Regional fund (not in registry)"}
    cb = d["cbpf_aa"]
    names.update({fc: (fn if "hpf" in fn.lower() else f"{fn} CBPF")
                  for fc, fn in zip(cb["fund_code"], cb["fund_name"]) if isinstance(fc, str) and isinstance(fn, str)})
    reg = d.get("fund_names")
    for fc in {r["s"][2:] for r in rows if r["s"].startswith("f:")} | {r["t"][2:] for r in rows if r["t"].startswith("f:")}:
        if fc in names:
            continue
        hit = reg[reg["fund_code"] == fc] if reg is not None else None
        if hit is not None and len(hit):
            nm = str(hit["name"].iloc[0])
            names[fc] = nm if hit["fund_type"].iloc[0] != "cbpf" or "hpf" in nm.lower() else f"{nm} CBPF"
        elif str(fc).startswith("rhpf-"):
            names[fc] = "Regional fund " + str(fc)[5:].upper()
        else:
            names[fc] = str(fc).upper()
    names = {k: _re.sub(r"rhpf", "RhPF", v, flags=_re.I) for k, v in names.items()}
    # the countries column's labels (FLOW_JS translates them with tr8, as every country name)
    cname = dict(zip(cur_["country_iso3"], cur_["country_name"])) if "country_name" in cur_ else {}
    names.update({"c:" + c: country_en(c, cname) for c in {r["c"] for r in rows if r.get("c")}})
    years = {m: sorted({r["y"] for r in rows if r["m"] == m}) for m in ("p", "r")}
    # both views open on the last complete year (2026-10-20 call: 2025, not 2026, whose
    # donor shares raise the question of why the US is so represented)
    def _last_done(ys):
        done = [y for y in ys if y <= today.year - 1]
        return done[-1] if done else (ys[-1] if ys else None)
    default = {"p": _last_done(years["p"]), "r": _last_done(years["r"])}
    return rows, years, default, names


# ------------------------------------------------- where the money flows (shared Sankey)
FLOW_TOP_ORGS = 15   # partner / grantee organisations named in a view; the rest grouped per category
FLOW_TOP_COUNTRIES = 15   # the countries column: the countries receiving the most in a view; the rest grouped
FLOW_NOTE = " ".join(TB(x) for x in (
    "<b>Pre-arranged</b>: the envelopes in place in the chosen year (a framework counts for a year "
    "if it was valid at any time in it; the current year: today), one per framework and fund — the "
    "Financing page's annual series. Never summed over years: a two-year envelope would count twice. "
    "Fund → agency uses the agency split of the version in force at that date, scaled to the "
    "envelope; Country and Regional Fund allocations go to their grantee organisations (AA-keyword "
    "project budgets). There is no final column: who an agency sub-grants to is only known once "
    "money is released.",
    "<b>Released</b>: money that went out on activations in the chosen year (all years add up). "
    "CERF → agency uses the AA projects approved that year in the same country (in the same region "
    "where the country has none that year), scaled to the released total; agency → partner uses the "
    "CERF AA sub-grants in that country, and the rest goes to a final node with the agency's own "
    "name — what it implements itself. Country and Regional Funds go to their grantee organisations "
    "from the AA-keyword project budgets; a grantee implements directly, so its band runs on, same "
    "amount, to the same organisation in the final column.",
    f"<b>Countries</b> (tick <i>countries</i>): a column between the funds and the agencies — the "
    f"country of the framework (pre-arranged) or of the activation (released). The {FLOW_TOP_COUNTRIES} "
    "countries receiving the most in the view are named, the rest grouped as <i>other countries</i>; "
    "a regional fund allocation that names no single country is <i>multi-country / regional</i>. "
    "The grantees of a regional fund carry no country: a country's band from a regional fund reaches "
    "that fund's grantees of the year in all its countries. "
    "Country boxes are grey: a band leaving one takes the colour of the box it reaches.",
    f"<b>Recipients</b>: the {FLOW_TOP_ORGS} partner and grantee organisations receiving the most in "
    "the view are named, the rest grouped per category (\"other national / local NGOs\"…). Every "
    "recipient node carries its category colour — UN agency, international NGO, national / local "
    "NGO, government, Red Cross / Red Crescent, other, not recorded — from the sub-grant partner "
    "type or the organisation type recorded by the Country and Regional Funds; a band takes the "
    "colour of the node it leaves.",
    "<b>Recipient types</b>: the far-right column groups every band by the category of the "
    "organisation it reaches — UN agencies, international NGOs, national / local NGOs, Red Cross / "
    "Red Crescent, government, other (untick <i>recipient types</i> to hide it).",
    "<b>Donors → fund</b>: each donor's paid contributions to the fund that year ÷ the fund's total "
    "paid income that year, × the amount — attributed pro rata, since contributions fund the whole "
    "pool. Top 12 donors, the rest grouped."))


def _flow_panel(donors_on, donor_toggle=True, extra=""):
    """The 'Where the money flows' panel: pre-arranged / released switch, year, levels
    (FLOW_JS mounts it). Used by the Financing page (donors off) and the donor-shares page
    (donors on, no toggle: the donor-flows view). extra: HTML appended to the method note."""
    chk = " checked" if donors_on else ""
    dctl = (f"<label><input type='checkbox' id='flD'{chk}> {T('donors')}</label>" if donor_toggle
            else f"<input type='checkbox' id='flD'{chk} hidden>")
    return f"""<div class='panel'>
 <div style='display:flex;gap:16px;flex-wrap:wrap;align-items:center;font-size:12.5px;margin-bottom:8px'>
  <span role='radiogroup' {ATTR('aria-label', 'which money')} style='display:inline-flex;border:1px solid #cbd5e1;border-radius:6px;overflow:hidden'>
   <label style='padding:3px 10px;cursor:pointer'><input type='radio' name='flM' value='p'> {T('pre-arranged')}</label>
   <label style='padding:3px 10px;cursor:pointer;border-left:1px solid #cbd5e1'><input type='radio' name='flM' value='r' checked> {T('released')}</label></span>
  <label><span id='flYl'>{T('Released in')}</span> <select id='flY'></select></label>
  {dctl}
  <label {ATTR('title', 'a column of the countries between the funds and the agencies: the ones receiving the most named, the rest grouped')}><input type='checkbox' id='flC'> {T('countries')}</label>
  <label {ATTR('title', 'a last column that groups the recipients by type (UN agencies, NGOs, Red Cross / Red Crescent, government, other)')}><input type='checkbox' id='flK' checked> {T('recipient types')}</label>
  <label id='flPw'><input type='checkbox' id='flP' checked> {T('final recipients')}</label>
  <label>{T('Find')} <input type='search' id='flS' list='flSL' {ATTR('placeholder', 'a donor, country or organisation')} {ATTR('aria-label', 'Find a donor, country or organisation in the flows')} style='width:230px;max-width:100%;font-size:12.5px;padding:3px 6px'></label><datalist id='flSL'></datalist>
  <span id='flTot' class='muted'></span>
 </div>
 <div id='flow'></div><div id='flLeg' class='note' style='display:flex;flex-wrap:wrap;gap:4px 14px;align-items:center'></div><script src="sankey.js"></script>
 <details class='note'><summary style='cursor:pointer'>{T('How the flows are counted')}</summary>{FLOW_NOTE}{extra}</details>
</div>"""


FLOW_JS = """
// ---- where the money flows: [donors ->] funds -> agencies / grantees [-> final recipients] [-> recipient types].
// Shared by the Financing page and the donor-flows view of the donor-shares page; rows from
// _money_flows. Recipient node ids carry their category: 'a:un|WFP' (an agency: always named),
// 'p:ingo~ActionAid' (an organisation: the top ones of the view named, the rest grouped).
const FLOW_TOP_ORGS = """ + str(FLOW_TOP_ORGS) + """, FLOW_TOP_COUNTRIES = """ + str(FLOW_TOP_COUNTRIES) + """;
const CAT_ORDER = ['un','ingo','nngo','gov','rc','oth','nr'];
// (labels in English: tr8() translates them where they are shown, so a language switch redraws them)
const CAT_LABEL = {un:'UN agency', ingo:'international NGO', nngo:'national / local NGO', gov:'government',
  rc:'Red Cross / Red Crescent', oth:'other', nr:'not recorded'};
const CAT_OTHER = {un:'other UN agencies', ingo:'other international NGOs', nngo:'other national / local NGOs',
  gov:'other government partners', rc:'other Red Cross / Red Crescent', oth:'other partners', nr:'other, type not recorded'};
// one colour per category on every level, apart from the fund colours (CERF blue, CBPF orange,
// RhPF green); the five hues validated as a set (all pairs: CVD dE >= 13.5, normal >= 19.6) and
// against the fund colours (normal >= 15.6); the two greys are the neutral categories
const CAT_COLOR = {un:'#65389f', ingo:'#70b6e7', nngo:'#ceaa3e', gov:'#8a4f0e', rc:'#c3518d', oth:'#3a3f47', nr:'#d6dae0'};
// the recipient-type column: one node per category, the far-right column
const CAT_GROUP = {un:'UN agencies', ingo:'International NGOs', nngo:'National / local NGOs', gov:'Government',
  rc:'Red Cross / Red Crescent', oth:'Other', nr:'Type not recorded'};
function flowNode(id){ const m = /^([apk]):([a-z]+)([|~])(.*)$/.exec(id);
  return m ? {p:m[1], cat:m[2], org:m[3]==='~', name:m[4]} : null; }
function flowRegroup(L, f){ const g = {};
  L.forEach(l=>{ const s = f(l.s, l), t = f(l.t, l), k = l.lv+'\\u0001'+s+'\\u0001'+t;
    if(g[k]) g[k].v += l.v; else g[k] = {lv:l.lv, s, t, v:l.v}; });
  return Object.values(g); }
// pick (2026-10-28): a donor ('d:…'), country ('c:…') or organisation name the search box chose,
// kept out of the 'other' boxes so it has a box of its own to focus
function buildFlow(rows, mode, year, showD, showP, names, topN, keep, topOrgs, showK, showC, pick){
  let R = rows.filter(r=>r.m===mode && (year==='all' || r.y===+year) && keep(r));
  // countries (2026-10-28): each fund -> agency / grantee link split at the country its row carries
  // (c; '' none recorded: 'c:*', multi-country / regional) — fund -> country ('f', so the total is
  // unchanged) and country -> agency ('c'). Every fund link passes through the column.
  if(showC) R = R.flatMap(r=>r.lv==='f' ? [{...r, t:'c:'+(r.c||'*')}, {...r, lv:'c', s:'c:'+(r.c||'*')}] : [r]);
  let L = flowRegroup(R, x=>x);
  // the countries receiving the most in this view named, the rest one 'other countries' box
  // (never a box for a single country)
  if(showC){ const ct = {}; L.forEach(l=>{ if(l.lv==='f' && l.t!=='c:*') ct[l.t] = (ct[l.t]||0) + l.v; });
    const ids = Object.keys(ct).sort((a,b)=>ct[b]-ct[a]);
    const topC = new Set(ids.length > FLOW_TOP_COUNTRIES + 1 ? ids.slice(0, FLOW_TOP_COUNTRIES) : ids);
    if(pick && pick.startsWith('c:')) topC.add(pick);
    L = flowRegroup(L, x=>x.startsWith('c:') && x!=='c:*' && !topC.has(x) ? 'c:+' : x); }
  // top donors; the rest grouped
  const dt = {}; L.filter(l=>l.lv==='d').forEach(l=>dt[l.s]=(dt[l.s]||0)+l.v);
  const top = new Set(Object.keys(dt).filter(k=>k!=='d:(donors not recorded)').sort((a,b)=>dt[b]-dt[a]).slice(0,topN||12));
  top.add('d:(donors not recorded)');
  if(pick && pick.startsWith('d:')) top.add(pick);
  L = flowRegroup(L, (x, l)=>l.lv==='d' && x===l.s && !top.has(x) ? 'd:Other donors' : x);
  // organisations: the top ones of THIS view named, by what they receive (sub-grants and CBPF
  // grants; a grantee's own pass-through to the final column not counted twice), the rest
  // grouped per category, in the middle and the final column alike
  const recv = {};
  L.forEach(l=>{ const t = flowNode(l.t), s = flowNode(l.s); if(!t || !t.org || t.cat==='nr' || (s && s.org && s.name===t.name)) return;
    recv[t.name] = (recv[t.name]||0) + l.v; });
  const named = new Set(Object.keys(recv).sort((a,b)=>recv[b]-recv[a]).slice(0, topOrgs||FLOW_TOP_ORGS));
  if(pick && pick.startsWith('o:')) named.add(pick.slice(2));
  L = flowRegroup(L, x=>{ const n = flowNode(x); return n && n.org && !named.has(n.name) ? `${n.p}:${n.cat}|${CAT_OTHER[n.cat]}` : x; });
  if(!showD) L = L.filter(l=>l.lv!=='d');
  if(!showP) L = L.filter(l=>l.lv!=='a');
  // recipient types (2026-10-02 meeting): the far-right column (2026-10-19: the final bucket,
  // not a stage before the named organisations) — every band reaching the named column runs
  // on to its category: UN agencies, international / national NGOs, Red Cross / Red Crescent,
  // government, other. After the naming above; the 'f' links (the total) are unchanged.
  if(showK){
    const last = showP ? 'p:' : 'a:', lv = showP ? 'a' : showC ? 'c' : 'f', S = [];
    L.forEach(l=>{ S.push(l); const n = l.lv===lv && l.t.startsWith(last) ? flowNode(l.t) : null;
      if(n) S.push({lv:'k', s:l.t, t:`k:${n.cat}|${CAT_GROUP[n.cat]}`, v:l.v}); });
    L = flowRegroup(S, x=>x);
  }
  const lab = id => { const [p, ...rest] = id.split(':'); const n = rest.join(':');
    if(p==='f') return tr8(names[n]||n);
    if(p==='c') return n==='*' ? tr8('multi-country / regional') : n==='+' ? tr8('other countries') : tr8(names[id]||n);
    const r = flowNode(id); return tr8(r ? r.name : n); };
  const cols = [];
  const col = pre => { const ids = new Set(); L.forEach(l=>{ [l.s,l.t].forEach(x=>{ if(x.startsWith(pre)) ids.add(x); }); });
    return [...ids].map(id=>({id, label:lab(id)})); };
  if(showD) cols.push(col('d:'));
  cols.push(col('f:'));
  if(showC) cols.push(col('c:'));
  cols.push(col('a:'));
  if(showP) cols.push(col('p:'));
  if(showK) cols.push(col('k:'));
  const seen = new Set(); cols.forEach(c=>c.forEach(n=>{ const r = flowNode(n.id); if(r) seen.add(r.cat); }));
  const total = L.filter(l=>l.lv==='f').reduce((s,l)=>s+l.v,0);
  return {columns:cols, links:L.map(l=>({s:l.s,t:l.t,v:l.v})), total, cats:CAT_ORDER.filter(c=>seen.has(c))};
}
// wire the panel _flow_panel() wrote; cfg.keep(row) filters the rows (the page's toggles);
// cfg.yLab(year) labels a year (Financing: the current year as '2026*', indicative), cfg.cy the
// current year (the build's; else the viewer's clock). Returns the redraw function, for the page
// to call when its own filters change.
// cfg.noYear: a year the chart never shows, in any view, 'all years' included — the Financing
// page's current year, until the donors' contributions for it are final (owner, 2026-10-30; the
// rows stay in the page data, and the page says nothing about it)
function mountFlow(cfg){
  if(!window.sankeySVG) return ()=>{};
  const noY = cfg.noYear == null ? null : +cfg.noYear, keep0 = cfg.keep || (()=>true);
  const keep = noY == null ? keep0 : (r => +r.y !== noY && keep0(r));
  const yLab = cfg.yLab || (y=>String(y)), cy = cfg.cy || new Date().getFullYear();
  const modeOf = () => document.querySelector("input[name='flM']:checked").value;
  // the search box (owner, 2026-10-28): every donor, country and organisation of the view, so a
  // small one grouped under 'other' can be picked, named and focused like a large one
  let pick = '', choices = new Map();
  function fillChoices(mode){
    choices = new Map();
    D.flow.filter(r=>r.m===mode && (flY.value==='all' || r.y===+flY.value) && keep(r)).forEach(r=>{
      // each name says what it is: a donor and a country can share one ('Zimbabwe')
      if(r.lv==='d' && r.s!=='d:(donors not recorded)') choices.set(`${tr8(r.s.slice(2))} (${tr8('donor')})`, r.s);
      if(r.lv==='f' && r.c) choices.set(`${tr8(D.fundNames['c:'+r.c] || r.c)} (${tr8('country')})`, 'c:'+r.c);
      [r.s, r.t].forEach(x=>{ const n = flowNode(x); if(n && n.org) choices.set(`${n.name} (${tr8(CAT_LABEL[n.cat])})`, 'o:'+n.name); });
    });
    document.getElementById('flSL').innerHTML = [...choices.keys()].sort((a,b)=>a.localeCompare(b)).map(k=>`<option value="${k.replace(/"/g,'&quot;')}">`).join('');
  }
  function drawFlow(){
    const mode = modeOf();
    fillChoices(mode);
    // the pick is kept by its id, so a language switch (labels re-translated) or a year with
    // other names keeps it: the box shows its label again, or empties if it is not in this view
    if(pick){ const hit = [...choices].find(([, v])=>v===pick);
      document.getElementById('flS').value = hit ? hit[0] : ''; if(!hit) pick = ''; }
    if(pick.startsWith('c:') && !flC.checked) flC.checked = true;     // a country needs the country column
    if(pick.startsWith('d:') && !flD.checked) flD.checked = true;     // a donor, the donor column
    const F = buildFlow(D.flow, mode, flY.value, flD.checked, mode==='r' && flP.checked, D.fundNames, 12, keep, cfg.topOrgs, flK.checked, flC.checked, pick);
    const el = document.getElementById('flow'), leg = document.getElementById('flLeg');
    if(!F.links.length){ el.innerHTML = "<p class='empty'>" + tr8('no AA money in this selection for this year') + "</p>"; flTot.textContent=''; if(leg) leg.innerHTML=''; return; }
    const n = Math.max(...F.columns.map(c=>c.length));
    // five columns (donors … recipient types) leave ~170px between them at 1100: wider, shorter labels;
    // six (with the countries) wider again
    const nc = F.columns.length, wide = nc >= 5;
    el.innerHTML = sankeySVG({columns:F.columns, links:F.links, width:nc >= 6 ? 1400 : wide ? 1300 : 1100, height:Math.max(260, n*24),
      fmt:money, labelW:200, labelMax:nc >= 6 ? 22 : wide ? 26 : 34, label:tr8(cfg.label || 'AA money through funds and agencies'),
      nodeColor: nd => { const r = flowNode(nd.id); return r ? CAT_COLOR[r.cat] : null; }});
    el.insertAdjacentHTML('beforeend', "<div class='note'>" + tr8('Hover a band or a box to follow the money; click a box to keep it in focus, click again to clear. Funds in their own colour (CERF blue, pooled funds orange, regional funds green); every agency, grantee and recipient in the colour of its category; a band takes the colour of the box it leaves.') + "</div>");
    if(leg) leg.innerHTML = '<b>' + tr8('Recipients') + '</b>' + F.cats.map(c=>`<span style='display:inline-flex;align-items:center;gap:5px'><span style='width:11px;height:11px;border-radius:2px;background:${CAT_COLOR[c]};display:inline-block${c==='nr' ? ';box-shadow:inset 0 0 0 1px #aab2bd' : ''}'></span>${tr8(CAT_LABEL[c])}</span>`).join('');
    if(pick){ const nd = [...el.querySelectorAll('.sk-n')].find(n=>{ const r = flowNode(n.dataset.id);
        return pick.startsWith('o:') ? r && r.name===pick.slice(2) : n.dataset.id===pick; });
      if(nd) nd.dispatchEvent(new MouseEvent('click', {bubbles:true})); }
    flTot.textContent = mode==='p' ? (+flY.value===cy ? tr8('Pre-arranged, in place in {0}: {1} (today)', yLab(flY.value), money(F.total)) : tr8('Pre-arranged, in place in {0}: {1}', yLab(flY.value), money(F.total)))
                                    : flY.value==='all' ? (noY != null ? tr8('Released in all years to {0}: {1}', noY - 1, money(F.total)) : tr8('Released in all years: {0}', money(F.total)))
                                    : tr8('Released in {0}: {1}', yLab(flY.value), money(F.total));
  }
  // the year list depends on the view: pre-arranged is one year's stock (no 'all years')
  function fillYears(){
    const mode = modeOf(), keepY = flY.value;
    flY.innerHTML = '';
    const ys = D.flowYears[mode].filter(y => +y !== noY);
    ys.slice().reverse().forEach(y=>flY.add(new Option(yLab(y), y)));
    if(mode==='r') flY.add(new Option(noY != null ? tr8('all years, to {0}', noY - 1) : tr8('all years'), 'all'));
    // the default year, unless it is the one left out: then the latest shown
    const def = +D.flowDefault[mode] === noY ? Math.max(...ys) : D.flowDefault[mode];
    flY.value = [...flY.options].some(o=>o.value===keepY) && keepY!=='' ? keepY : String(def);
    document.getElementById('flYl').textContent = mode==='p' ? tr8('In place in') : tr8('Released in');
    document.getElementById('flPw').style.display = mode==='r' ? '' : 'none';
  }
  document.querySelectorAll("input[name='flM']").forEach(el=>el.addEventListener('change', ()=>{ fillYears(); drawFlow(); }));
  fillYears();
  [flY, flD, flP, flK, flC].forEach(el=>el.addEventListener('change', drawFlow));
  document.getElementById('flS').addEventListener('change', ev=>{ pick = choices.get(ev.target.value.trim()) || ''; drawFlow(); });
  document.addEventListener('aalang', ()=>{ fillYears(); drawFlow(); });
  drawFlow();
  return drawFlow;
}
"""


# ---------------------------------------------------------------- financing
# the Financing page's method note, one translatable paragraph each (site_i18n TB)
FUND_NOTE_0 = "<b>Layers</b>, as on the map: <b>current frameworks</b> (active, being updated, in development) and <b>retired</b> frameworks. <b>Money stays counted</b>: what a framework since retired pre-arranged in the years it was in place, and what it released, counts while either framework layer is ticked, whatever its status today, so the past years are complete on the page's opening view (the released tile says how much comes from retired frameworks). The retired layer adds the retired frameworks to the framework count and the by-status chart; on its own it shows their money only. An AA-tagged country or regional fund allocation in a country with no retired framework counts as current. <b>Non-framework allocations</b> add the AA money allocated without a framework: released money only, nothing is pre-arranged for it. The <b>fund</b> switch applies to every figure but co-financing; framework counts, people covered and versions then keep the frameworks with money recorded on that fund. There is no technical-support layer here: technical support carries no money. The tiles and the charts follow the layers, the fund, the framework selection and the hazard and region filters (the GHO filter: the annual series and co-financing); the money-flow chart and the sections further down say what they follow."
# a replaced framework (dashboards.old_versions) is on the retired layer: said under the layers note
FUND_NOTE_REPLACED = "A framework that a distinct new one replaced, rather than revised, counts as <b>retired</b>, its activations and money with it, even though the new one has the same country and hazard (Somalia drought: the 2019–2021 food security framework, replaced by the 2026 one)."
FUND_NOTE_1 = '<b>Frameworks</b> (in the filter bar) lists every current and retired framework with its pre-arranged money now: tick the ones to count — a sub-region, a few countries, any subset — and the tiles and the charts count only those, within the other filters. Money that belongs to no framework (a non-framework allocation, a country-level allocation of a country or regional fund) follows its country: it counts while at least one line of that country is ticked, and the countries whose only AA money is of that kind have a line of their own at the end of the list. A subset changes which frameworks are counted, not how: its pre-arranged money is still a stock, in place today or in a given year, never added over years. The selection is kept in the page address, so a subset can be bookmarked or shared. The money-flow chart and the UN agencies and partners section do not follow it.'
FUND_NOTE_PRE_A = '<b>Pre-arranged now</b> comes from the framework records: for every active, being-updated or in-development framework, the envelope of its most recent version that has one. The same figure is the current year in the annual chart and on the map.'
FUND_NOTE_PRE_B = "CERF money stays pre-arranged until a framework is <b>retired</b>: a framework being updated after an activation keeps its most recent version's CERF envelope. Country and Regional Fund money does not: an envelope or AA-tagged allocation counts as pre-arranged until an activation draws on it, and from then on it is released money, no longer committed. Pre-arranged money is a stock (in place on a date) and released money a flow (per year): the two are never added together."
FUND_NOTE_3 = '<b>People covered now</b> is the latest figure recorded for each current framework — the people its pre-arranged plan covers, not the people reached once it activated (those come from the final reports, on the Activities page). Retired frameworks cover no one now and are left out, as on the map. A framework still in development usually has no figure until its projects are planned; an early estimate can be recorded until then.'
# two activations a year (aa.framework_version.activations_per_year; activation_factors): the
# owner's footnote (2026-10-28) under the tiles, and the sentence the charts' notes add. Both are
# written on every build and shown by the page's script only when a framework is counted so.
TWO_ACT_NOTE = "* allows two activations a year: its CERF envelope is counted twice; the CERF budget per activation is half of it."
TWO_ACT_HOW = ("Frameworks marked * allow two activations a year: their CERF envelope is counted twice here, "
               "and the CERF budget per activation is half of it. Country and Regional Fund envelopes count once.")
FUND_NOTE_4 = "<b>Donors</b> (the <i>donors</i> tick on the money-flow chart): each donor's share of a fund's income that year, applied to the fund's AA money that year — donors give to the pooled funds as a whole, not to anticipatory action. Donors report their AA funding annually under the <a href='https://interagencystandingcommittee.org/grand-bargain' target='_blank' rel='noopener'>Grand Bargain</a>."

# the two co-financing charts' notes (2026-10-28 owner comment: split the chart by agency into a
# time series and a chart per co-financer)
COF_YEAR_HOW = ("Pre-arranged co-financing only: money from outside CERF and the Country and Regional Funds "
                "recorded against a framework; how much of it was disbursed is not recorded. A stock, as at "
                "the end of each year — the years are never added up. A past year counts the co-financing "
                "totals reported for that year. The current year is today: each framework's total for the "
                "year or, where none is reported, the co-financing its latest framework document states — the "
                "figure the chart by co-financer splits, so the two charts agree. Follows the framework layers "
                "and the hazard, region and GHO filters. Does not apply: the fund switch (the money is outside "
                "the pooled funds), the non-framework layer (non-framework allocations carry no co-financing) "
                "and cumulative (a stock).")
COF_WHO_HOW = ("Today's pre-arranged co-financing — the current year of the chart by year — by who co-finances "
               "it. The yearly totals mostly name no co-financer; the framework documents do. So each "
               "framework's co-financing is shown by the lines its latest framework document states: where "
               "those lines make up the year's total, the bars show the document's own figures; where they fall "
               "short of it, the lines count as the document states them and the rest of the total is <i>not "
               "recorded</i>; where the document states lines but no total is reported for the year, the lines "
               "themselves count. A framework whose co-financing names no one is in the <i>not recorded</i> "
               "bar, shown last. One bar per organisation: the kind of money (an agency's own funds, a trust "
               "fund, preparedness or implementation co-financing) and each framework's share are in the "
               "tooltip. A line naming several organisations together stays one bar, as recorded. Follows the "
               "same filters as the chart by year.")


def build_funding(page, d):
    """The Financing page (dash-funding.html: the file name predates the rename, links keep it).
    Every tile and chart follows the map's layer toggles (current frameworks, retired, non-framework
    allocations) and a fund switch; the defaults show everything released (current + retired
    + non-framework, both funds; since 2026-10-02 — before, framework activations only)."""
    import datetime as _dt
    import html as _html
    # the current year, as of the build: its figures move daily until it closes, so wherever the
    # page labels it (the annual charts, the year selectors, the released tile's years) it reads
    # '2026*', with one footnote under the tiles (2026-10-09 meeting: "asterisk on 2026, marked
    # indicative and updated daily")
    cy = _dt.date.today().year
    pre, act = funding_series(d, released="all")   # non-framework rows ride along, toggled client-side
    cur = d["current"]
    layer = _layer_of(d)
    region_of = dict(zip(zip(cur["country_iso3"], cur["hazard"]), cur["region"]))
    pre["g"] = [layer(c, h, v) for c, h, v in zip(pre["country_iso3"], pre["hazard"], pre["version"])]
    # an activation of an earlier framework's version (Somalia drought 2020, 2021) is a retired
    # framework's, whatever the pair's status today (old_versions)
    act["g"] = ["a" if et == "adhoc_aa" else layer(c, h, v)
                for et, c, h, v in zip(act["event_type"], act["country_iso3"], act["hazard"], act["version"])]

    def pair_key(df):
        """k: 'ISO3|hazard', the framework a row belongs to — what the framework picker ticks."""
        return df["country_iso3"].astype(str) + "|" + df["hazard"].astype(str)
    pre["k"], act["k"] = pair_key(pre), pair_key(act)

    # pre-arranged NOW under the convention: every non-retired framework keeps its latest
    # version's envelope ('all' totals dropped where the fund split exists)
    vf = d["vfund"].copy()
    has_comp = set(map(tuple, vf.loc[vf["fund_code"] != "all",
                                     ["country_iso3", "hazard", "version"]].values))
    vf = vf[~((vf["fund_code"] == "all")
              & vf.apply(lambda r: (r["country_iso3"], r["hazard"], r["version"]) in has_comp,
                         axis=1))]
    vf["ft"] = vf["fund_code"].map(_ft)
    vf = vf.merge(cur[["country_iso3", "hazard", "region"]], on=["country_iso3", "hazard"],
                  how="left")
    vf["hz"] = vf["hazard"].map(haz)
    vf["g"] = [layer(c, h, v) for c, h, v in zip(vf["country_iso3"], vf["hazard"], vf["version"])]
    vf["k"] = pair_key(vf)
    # x: activations a year counted (prearranged_now has multiplied total_usd already)
    vf["x"] = vf["activations_per_year"].fillna(1).astype(int) if "activations_per_year" in vf else 1
    now_cerf = vf.loc[vf["ft"] == "cerf", "total_usd"].sum()
    now_cbpf = vf.loc[vf["ft"] != "cerf", "total_usd"].sum()
    gaps, released = envelope_gaps(d), envelope_released(d)
    # kept visible, one compact line under the tiles: what pre-arranged now leaves out — no envelope
    # recorded, or a Country or Regional Fund envelope released by an activation (pooled_spent)
    def _fw_list(xs):
        return ", ".join(f"{T(str(n))} {T(str(h))} ({T(LIFE_LABEL.get(str(lc), str(lc)))})" for n, h, lc in xs)
    gaps_html = ("" if not (gaps or released) else
                 "<p class='note' style='margin:-4px 0 6px;font-size:12px;color:#555'>"
                 + ((TBF("Not in pre-arranged now — <b>{n} current frameworks with no envelope recorded</b>:", n=len(gaps))
                     if len(gaps) > 1 else TB("Not in pre-arranged now — <b>1 current framework with no envelope recorded</b>:"))
                    + " " + _fw_list(gaps) + "." if gaps else "")
                 + ((" " if gaps else "")
                    + TB("<b>Released, no longer committed</b> — the Country or Regional Fund envelope an activation drew on:")
                    + " " + _fw_list(released) + "." if released else "")
                 + "</p>")
    stale = vf[vf["version"].astype(str) != vf["latest_version"].astype(str)][["country_iso3", "hazard", "version"]].drop_duplicates()
    stale_html = ("" if not len(stale) else
                  " " + (TF("{n} frameworks count the envelope of an earlier version because the latest one has none yet:", n=len(stale))
                         if len(stale) > 1 else T("1 framework counts the envelope of an earlier version because the latest one has none yet:"))
                  + " " + ", ".join(f"{r.country_iso3} {T(str(r.hazard))} ({_html.escape(str(r.version))})" for r in stale.itertuples()) + ".")

    # which funds each framework has money on (any year, pre-arranged or released on a
    # framework activation): the fund switch keeps the frameworks with money on that fund
    # in the counts, people covered and versions. The money of an earlier framework that a
    # distinct new one replaced (old_versions) is that framework's, not the pair's current one's
    # (Somalia drought 2026 does not count "with CERF money" for the 2020 and 2021 activations)
    old = d.get("old") or set()
    pair_funds, old_funds = {}, {}
    cols = ["country_iso3", "hazard", "fund_code", "version"]
    money_rows = [pre.loc[(pre["kind"] == "prearranged") & (pre["fund_code"] != "all"), cols],
                  act.loc[act["g"] != "a", cols],
                  vf.loc[vf["fund_code"] != "all", cols]]
    for r in pd.concat(money_rows).itertuples():
        to = old_funds if (r.country_iso3, r.hazard, str(r.version)) in old else pair_funds
        to.setdefault((r.country_iso3, r.hazard), set()).add("c" if r.fund_code == "cerf" else "p")

    def frame_rows(df):
        df = df.copy()
        df["hz"] = df["hazard"].map(haz)
        df["region"] = [region_of.get((c, h)) or "?" for c, h in zip(df["country_iso3"], df["hazard"])]
        vs = df["version"] if "version" in df else [None] * len(df)   # versions: an old one is retired
        df["g"] = [layer(c, h, v) for c, h, v in zip(df["country_iso3"], df["hazard"], vs)]
        # a version of a replaced framework carries that framework's funds, not the new one's
        df["funds"] = ["".join(sorted((old_funds if (c, h, str(v)) in old else pair_funds).get((c, h), ())))
                       for c, h, v in zip(df["country_iso3"], df["hazard"], vs)]
        df["k"] = pair_key(df)
        return df

    fw = frame_rows(cur[["country_iso3", "hazard", "lifecycle", "technical_support"]])
    fw["technical_support"] = fw["technical_support"].fillna(False).astype(bool)
    # an earlier framework that a distinct new one replaced (old_versions: Somalia drought's
    # 2019 / 2020-06-23 food security framework, replaced by the 2026 one) is a retired framework
    # of its own, as on the map (landing: a pair hosting one is on the retired layer too): one
    # more retired row, on the pair's line in the picker, with the funds of its own money. A pair
    # that is itself retired already counts once, as on the map.
    old_pairs = {(c, h) for c, h, _ in old}
    replaced = fw[[(c, h) in old_pairs and lc != "retired"
              for c, h, lc in zip(fw["country_iso3"], fw["hazard"], fw["lifecycle"])]]
    if len(replaced):
        fw = pd.concat([fw, replaced.assign(
            lifecycle="retired", g="r", technical_support=False,
            funds=["".join(sorted(old_funds.get((c, h), ())))
                   for c, h in zip(replaced["country_iso3"], replaced["hazard"])])], ignore_index=True)
    # people covered is a NOW figure, like pre-arranged now: the current frameworks' latest
    # figures only (a retired framework covers no one) — the map's figure (2026-10-02 meeting:
    # Financing showed 10.5M with the retired ones, the map 5.4M). k: the pair, so the tile can
    # say how many current frameworks have no figure yet (in development, mostly)
    live_lc = ("active", "updating", "development")
    cov = d["covered"].merge(cur[["country_iso3", "hazard", "lifecycle"]], on=["country_iso3", "hazard"])
    cov = frame_rows(cov[cov["lifecycle"].isin(live_lc)])
    ver = frame_rows(d["versions"])
    ver["year"] = pd.to_datetime(ver["valid_from"]).dt.year

    n_active = int((cur["lifecycle"] == "active").sum())
    n_upd = int((cur["lifecycle"] == "updating").sum())
    n_dev = int((cur["lifecycle"] == "development").sum())
    n_ret = int((fw["lifecycle"] == "retired").sum())   # with the replaced frameworks, as the map
    n_tech = int(fw["technical_support"].sum())
    fw_act = act[act["g"] != "a"]
    total_rel = fw_act["amount_usd"].sum()

    def ylab(y):
        """A year as the page labels it: the current year marked indicative ('2026*')."""
        return f"{int(y)}*" if int(y) == cy else str(int(y))
    rel_years = f"{ylab(fw_act['year'].min())}–{ylab(fw_act['year'].max())}" if len(fw_act) else ""
    covered = cov["people_covered"].sum()
    n_live = int(fw["lifecycle"].isin(live_lc).sum())
    n_cov = int(cov["k"].nunique())

    # agency × sector split of the live frameworks' latest versions (one source per version)
    pr = d["plan_rows"].merge(cur[["country_iso3", "hazard", "region"]],
                              on=["country_iso3", "hazard"], how="left")
    pr["hz"] = pr["hazard"].map(haz)
    pr["ft"] = pr["fund_code"].map(_ft)
    pr["g"] = [layer(c, h) for c, h in zip(pr["country_iso3"], pr["hazard"])]
    pr["k"] = pair_key(pr)
    # a version that allows two activations a year: its CERF budget lines count twice, as its
    # CERF envelope (prearranged_now)
    fac = d.get("act_factors") or {}
    if fac and len(pr):
        pr["amount_usd"] = pr["amount_usd"].astype(float) * [
            fac.get((c, h, str(v)), 1) if f == "cerf" else 1
            for c, h, v, f in zip(pr["country_iso3"], pr["hazard"], pr["version"], pr["fund_code"])]

    # UN agencies vs partners (owner, 2026-10-28: the chart's 2026 $43.7M did not match the map's
    # CERF $38M): CERF's RELEASED money — the CERF rows of 'AA released by year, by fund' (c2), by
    # the activation's year, every filter of the page — split per allocation by the share its
    # agencies sub-granted of its project budgets (at most all of it), by partner-type group and by
    # localisation; the rest is direct UN spend. Project budgets can exceed the money released
    # (COD-26-RR-1554: $1.5M of projects on $1.0M), so the share carries over, never the budget, and
    # a sub-grant counts in the year its allocation's money does. An allocation with no project
    # records (or a row with no allocation code) has no split: 'split not known' (drawUN).
    sg = d["subgrant_aa"].copy()
    PT_GROUP = {"INGO": "INGO", "NNGO": "NNGO / local", "GOV": "government",
                "RedC": "Red Cross / Red Crescent", "REDC": "Red Cross / Red Crescent"}
    sg["grp"] = sg["partner_type"].map(PT_GROUP).fillna("other")
    # the local / national part: sub-grants typed Local; international NGOs and partners not yet
    # typed (TBD, blank) make up the rest
    sg["lk"] = sg["localization"].fillna("").str.lower().map({"local": "local", "ingo": "intl"}).fillna("untyped")
    proj = d["agency"].groupby("application_code")["amount_approved"].sum()
    pid = {n: i for i, n in enumerate(sorted(sg["partner_name"].dropna().astype(str).unique()))}
    un_split = {}     # allocation code -> {g: share by group, l: share by localisation, p: partner ids}
    for ac in act.loc[act["fund_code"] == "cerf", "allocation_code"].dropna().unique():
        b = float(proj.get(ac, 0) or 0)
        if b <= 0:
            continue
        x = sg[sg["application_code"] == ac]
        k = 1 / max(b, float(x["subgrant_usd"].sum()))
        un_split[ac] = {"g": {g: v * k for g, v in x.groupby("grp")["subgrant_usd"].sum().items() if v > 0},
                        "l": {g: v * k for g, v in x.groupby("lk")["subgrant_usd"].sum().items() if v > 0},
                        "p": sorted({pid[n] for n in x["partner_name"].dropna().astype(str)})}
    # the tiles as the page opens (current frameworks, both funds: D142); drawUN repaints them
    # for every filter. Shares of the money whose split is known.
    cr = act[(act["fund_code"] == "cerf") & act["g"].isin(["c", "r"])]   # released: retired ones too (relOK)
    sp = [(float(v), un_split[ac]) for ac, v in zip(cr["allocation_code"], cr["amount_usd"].fillna(0)) if ac in un_split]
    known = sum(v for v, _ in sp)
    sub_total = sum(v * sum(x["g"].values()) for v, x in sp)
    local_usd = sum(v * x["l"].get("local", 0) for v, x in sp)
    sub_share = (sub_total / known * 100) if known else 0
    local_share = (local_usd / sub_total * 100) if sub_total else 0
    n_un_partners = len({i for v, x in sp if v > 0 for i in x["p"]})

    flow_rows, flow_years, flow_default, fund_names = _money_flows(d, pre, act)

    # co-financing PRE-ARRANGED, by year: the yearly totals (window_funding kind='cofinancing'
    # with a year and no agency / sector line, i.e. aa.prearranged_funding — an agency breakdown
    # of a total would count it twice), a stock per year end. Disbursed co-financing is not
    # known. The non_aa_mobilised amount is not co-financing: kept out, labelled on its own.
    cof = pre[pre["kind"] == "cofinancing"].copy()
    # ... and NOW, by co-financer: each framework's figure now (cofinancing_now), which both
    # charts count — the by-year chart as its current year, so the two agree
    gho_cy = set(d["gho"].loc[d["gho"]["in_gho"] & (d["gho"]["year"] == cy), "country_iso3"])
    cof_now = cofinancing_now(d, cof, cy)
    cof_now["k"] = pair_key(cof_now)
    cof_now["hz"] = cof_now["hazard"].map(haz)
    cof_now["region"] = [region_of.get((c, h)) or "?" for c, h in zip(cof_now["country_iso3"], cof_now["hazard"])]
    cof_now["g"] = [layer(c, h, v) for c, h, v in zip(cof_now["country_iso3"], cof_now["hazard"], cof_now["version"])]
    cof_now["in_gho"] = cof_now["country_iso3"].isin(gho_cy)
    cname = dict(zip(cur["country_iso3"], cur["country_name"]))
    nonaa = pre[pre["kind"] == "non_aa_mobilised"]
    nonaa_html = ("" if not len(nonaa) else
                  TB("Not in this chart — <b>emergency funds mobilised on the forecast, outside the "
                     "anticipatory action framework</b>:") + " " + "; ".join(
                      f"{T(str(cname.get(r.country_iso3) or r.country_iso3))} "
                      f"{T(str(r.hazard))} {int(r.year)}, ${r.amount_usd / 1e6:,.1f}M"
                      for r in nonaa.itertuples()) + ".")

    # the framework picker (2026-10-06, a colleague could not total the pre-arranged money of a
    # sub-regional set of frameworks): every framework with a status on this page — current
    # and retired; a pipeline pair is not a framework yet and carries no figure here — and,
    # after them, the countries whose AA money belongs to no listed framework (ad hoc
    # allocations), so that every row of money on the page can be ticked in or out
    def country_name(c):
        return country_en(c, cname)
    listed = cur[cur["lifecycle"].isin(live_lc + ("retired",))]
    # g2: the retired layer too, for a pair hosting a replaced framework (its line ticks both)
    fw_list = [{"k": f"{r.country_iso3}|{r.hazard}", "name": country_name(r.country_iso3),
                "hazard": hazard_word(r.hazard), "hz": haz(r.hazard),
                "region": r.region if isinstance(r.region, str) else "?", "lc": r.lifecycle,
                "g": layer(r.country_iso3, r.hazard),
                "g2": "r" if (r.country_iso3, r.hazard) in old_pairs and r.lifecycle != "retired" else None}
               for r in listed.itertuples()]
    fw_list.sort(key=lambda f: (f["region"], f["name"], f["hazard"]))
    money_c = (set(pre["country_iso3"]) | set(act["country_iso3"])) - set(listed["country_iso3"])
    fw_list += [{"k": f"{c}|*", "name": country_name(c), "hazard": None, "hz": None,
                 "region": None, "lc": None, "g": None, "g2": None} for c in sorted(money_c, key=country_name)]

    # the two-activation sentence: on the page always (so its translations are checked on every
    # build), shown by the script when a framework is counted twice (.twoOnly)
    two_how = f"<span class='twoOnly' style='display:none'> {TB(TWO_ACT_HOW)}</span>"

    def how(body, title="How this is counted", two=False):
        """A per-chart method note, collapsed under the chart (both in every language)."""
        return (f"<details class='note'><summary style='cursor:pointer'>{T(title)}</summary>{TB(body)}"
                f"{two_how if two else ''}</details>")

    fund_sel = (f"<label>{T('Fund')} <select id='fFund'>{OPT('', 'CERF and Country and Regional Funds')}"
                f"{OPT('cerf', 'CERF')}{OPT('pooled', 'Country and Regional Funds')}</select></label>")
    panels = f"""
<div class='fbar hi'>
 <span class='fbar-t'>{T("Filter every figure on this page:")}</span>
 <span style='display:inline-flex;gap:10px;align-items:center;padding-right:10px;border-right:1px solid #9db2c9'>
  <label {ATTR("title", "frameworks active, being updated or in development: their money in every year")}><input type='checkbox' id='fCur' checked> {T("Current frameworks")}</label>
  <label {ATTR("title", "frameworks since retired: adds them to the framework count and the by-status chart; their money (pre-arranged in the years they were live, and released) counts with current frameworks too")}><input type='checkbox' id='fRet'> {T("Retired")}</label>
  <label {ATTR("title", "AA money allocated without a framework: released money only")}><input type='checkbox' id='fAdh'> {T("Non-framework allocations")}</label></span>
 <details class='fwpick' id='fwPick'><summary id='fwLab' {ATTR("title", "the full list of frameworks: tick the ones to count")}>{T("Frameworks: all ▾")}</summary>
  <div class='fwpanel'>
   <div class='fwhead'><input type='search' id='fwQ' {ATTR("placeholder", "find a country, hazard, region or status…")} {ATTR("aria-label", "find frameworks in the list")}>
    <button type='button' id='fwAll'>{T("tick all")}</button><button type='button' id='fwNone'>{T("untick all")}</button></div>
   <div class='fwlist' id='fwRows'></div>
   <div class='fwsum' id='fwSum'></div>
  </div></details>
 {fund_sel}
 <label>{T("Hazard")} <select id='fHaz'>{OPT("", "all")}</select></label>
 <label>{T("Region")} <select id='fReg'>{OPT("", "all")}</select></label>
 <label>{T("GHO")} <select id='fGho'>{OPT("", "all")}{OPT("1", "GHO contexts only")}</select></label>
 <label {ATTR("title", "released money only: pre-arranged money is a stock, in place on a date, so it never accumulates")}><input type='checkbox' id='fCum'> {T("cumulative (released)")}</label>
 <button type='button' id='fReset' class='freset' {ATTR("title", "put every filter in this bar back to how the page opens: current frameworks only, both funds, every hazard, region and framework")}>{T("Reset all filters")}</button>
</div>
<div class='tiles'>
 <div class='tile'><div class='v' id='tFw'>{n_active + n_upd + n_dev}</div><div class='l' id='tFwl'>{TF("frameworks — {a} active · {u} being updated · {d} in development", a=n_active, u=n_upd, d=n_dev)}</div></div>
 <div class='tile'><div class='v' id='tPre'>${(now_cerf + now_cbpf)/1e6:,.0f}M</div><div class='l' id='tPrel'>{TF("pre-arranged now — CERF {c} · Country and Regional Funds {p}", c=f"${now_cerf/1e6:,.0f}M", p=f"${now_cbpf/1e6:,.0f}M")}</div></div>
 <div class='tile'><div class='v' id='tRel'>${total_rel/1e6:,.0f}M</div><div class='l' id='tRell'>{TF("AA released {years} — framework activations, CERF and Country and Regional Funds", years=rel_years)}</div></div>
 <div class='tile'><div class='v' id='tCov'>{covered/1e6:,.1f}M</div><div class='l' id='tCovl'>{TF("people covered now — current frameworks, latest figure each ({n} of {m} have one) · not people reached", n=n_cov, m=n_live)}</div></div>
</div>
<p class='fwnote' id='fwNote' style='display:none'></p>
<p class='note' style='margin:-4px 0 6px;font-size:12px;color:#555'>{TF("* {y} is indicative: the figures update daily until the year closes.", y=cy)}</p>
<p class='note' id='twoNote' style='display:none;margin:-4px 0 6px;font-size:12px;color:#555'>{TB(TWO_ACT_NOTE)}</p>
{gaps_html}
<details class='note' style='margin:0 0 14px;font-size:12px;color:#555'><summary style='cursor:pointer;font-size:12.5px'>{T("How these figures are counted")}</summary>
<p>{TB(FUND_NOTE_0)} {TB(FUND_NOTE_REPLACED)}</p>
<p>{TB(FUND_NOTE_1)}</p>
<p>{TB(FUND_NOTE_PRE_A)}{stale_html}{two_how} {TB(FUND_NOTE_PRE_B)}</p>
<p>{TB(FUND_NOTE_3)}</p>
<p>{TB(FUND_NOTE_4)}</p>
<p>{TB("The terms used on this page are defined on the <a href='definitions.html'>Definitions</a> page.")}</p>
</details>
<h2>{T("Where the money flows")}</h2>
<p class='meta'>{TB("Funds → agencies and grantees → the organisations that implement, <b>pre-arranged</b> (the envelopes in place on a date) or <b>released</b> (what went out in a year) — two views never added together. Follows the layers and the fund switch. It opens on the money released in the last complete year, from each fund's donors; untick <i>donors</i> to start at the funds.")}</p>
<p class='fwnote' id='fwFlowNote' style='display:none'>{T("This chart shows every framework of the layers above: it does not follow the framework selection (nor the hazard and region filters).")}</p>
{_flow_panel(donors_on=True, extra=two_how)}
<h2>{T("Co-financing")}</h2>
<p class='meta'>{T("Money from outside CERF and the Country and Regional Funds — agencies' own funds, donors, governments — pre-arranged for the frameworks. Not in the chart above, which follows the OCHA-managed funds.")}</p>
<div class='grid'>
 <div class='panel'><h3>{T("Co-financing pre-arranged, by year")}</h3><canvas id='cofYear' height='260'></canvas><p class='empty' id='cofYearX' style='display:none'></p>
   {f"<div class='note'>{nonaa_html}</div>" if nonaa_html else ""}
   {how(COF_YEAR_HOW)}</div>
 <div class='panel'><h3>{T("Co-financing pre-arranged now, by co-financer")}</h3><div id='cofWhoBox' style='position:relative;height:300px'><canvas id='cofWho' style='max-height:none'></canvas></div><p class='empty' id='cofWhoX' style='display:none'></p>
   {how(COF_WHO_HOW)}</div>
</div>
<h2>{T("Frameworks and money by year, hazard and region")}</h2>
<div class='grid'>
 <div class='panel'><h3>{T("Frameworks each year, by status")}</h3><canvas id='c0' height='260'></canvas>
   {how("Each framework's status at the end of the year: active while an endorsed version was valid at any time in the year; being updated when none was and its next version is in development or its last one had expired; in development before its first endorsed version; retired from the first full year after its retirement date. The current year is today's status, the Map's figure. Follows the layers, the framework selection and the hazard and region filters; the GHO filter applies year by year; the fund switch does not apply (a count, not money).")}</div>
 <div class='panel'><h3>{T("Pre-arranged funding in place each year, by fund")}</h3><canvas id='c1' height='260'></canvas>
   {how("A stock: what was committed in each year (a framework counts for a year if it was valid at any time in it), so the bars are not added up (the cumulative switch applies to released money only). CERF: the framework envelopes per year (sheets, framework pages, entries; 'all'-totals excluded where the fund split exists); the current year is pre-arranged now. Country and Regional Funds: AA-tagged allocations in the OneGMS mirror, in the year allocated. Co-financing is shown separately. A framework since retired counts in the years it was in place, whatever its status today.", two=True)}</div>
 <div class='panel'><h3>{T("AA released by year, by fund")}</h3><canvas id='c2' height='260'></canvas>
   {how("Allocations drawn by a framework activation, all pooled funds — plus the non-framework AA allocations when that layer is on. A country or regional fund allocation moves here only once an activation is recorded against it.")}</div>
 <div class='panel'><h3>{T("Pre-arranged now, by hazard")}</h3><canvas id='c3' height='260'></canvas>
   {how("Latest envelope of every framework that is active, being updated or in development.", two=True)}</div>
 <div class='panel'><h3>{T("Pre-arranged now, by region")}</h3><canvas id='c4' height='260'></canvas>
   {how("The same envelopes as by hazard, by the framework's region.", two=True)}</div>
</div>
<h2>{T("Where the pre-arranged money goes")}</h2>
<p class='meta'>{T("The latest version of every current framework, split by agency and sector as the framework documents state it, stacked by fund.")}</p>
<div class='grid'>
 <div class='panel'><h3>{T("Pre-arranged by agency")}</h3><canvas id='c7' height='320'></canvas>
   {how("Envelope shares per implementing agency (the agency lines of the framework budgets; top 18). Money with no agency split recorded (most Country and Regional Fund envelopes) is not in this chart. Follows the current-frameworks layer (retired frameworks have no pre-arranged money now), the fund switch and the hazard and region filters; the GHO filter does not apply.", two=True)}</div>
 <div class='panel'><h3>{T("Pre-arranged by sector")}</h3><canvas id='c8' height='320'></canvas>
   {how("Sector lines of the same budgets; a line with an agency but no sector is not shown here. Money with no sector split recorded (most Country and Regional Fund envelopes) is not in this chart. Follows the same toggles as by agency.", two=True)}</div>
</div>
<h2>{T("UN agencies and partners")}</h2>
<p class='meta'>{T("Once CERF releases AA money, the agencies partially spend it directly (in large part on procurement) and partially sub-grant it to implementing partners.")}</p>
<p class='empty' id='unNone' style='display:none'>{T("The sub-grant reports are CERF's: select CERF, or both funds, to see them.")}</p>
<div id='unBox'>
<div class='tiles'>
 <div class='tile'><div class='v' id='uS'>{sub_share:.0f}%</div><div class='l' id='uSl'>{T("of the CERF AA money released, sub-granted to partners")}</div></div>
 <div class='tile'><div class='v' id='uL'>{local_share:.0f}%</div><div class='l'>{T("localisation share — of all the money passed to partners (partners not yet typed included), the part to local / national actors (NNGO, government, Red Cross / Red Crescent)")}</div></div>
 <div class='tile'><div class='v' id='uT'>${sub_total/1e6:,.1f}M</div><div class='l' id='uTl'>{TF("sub-granted in total · {n} partners", n=n_un_partners)}</div></div>
</div>
<div class='grid'>
 <div class='panel'><h3>{T("CERF AA allocations by year — direct UN spend vs sub-granted to partners")}</h3><canvas id='c9' height='280'></canvas>
   {how("The CERF part of <i>AA released by year, by fund</i>, split in two: each bar is the CERF money released that year, the same figure as the CERF bar of that chart and the map's CERF figure for the same layers and year, and follows the same filters. Each allocation's money is split by the share its agencies passed on to partners: the sub-grants CERF's records report for the allocation, divided by the allocation's project budgets (at most all of it). Project budgets can be larger than the money released, so the share carries over, not the budget. A sub-grant counts in the year the allocation's money is counted, whatever year its record carries. The rest is direct UN spend, which includes sub-grants not reported yet, so recent years show more direct spend. <i>Split not known</i>: money whose CERF allocation is not recorded, or has no project budgets; it is left out of the share sub-granted. Partner groups from the sub-grant partner type; 'other' includes partners not yet typed. 2023 looks low because the only framework activations that year were DRC cholera ($1.5M): the CERF early-action allocations reported to the Anticipation Hub for 2023 are not counted as anticipatory action here, following the definition the Grand Bargain adopted at the end of 2024.")}</div>
 <div class='panel'><h3>{T("Share of CERF AA sub-grants to local and national actors, by year")}</h3><canvas id='c10' height='280'></canvas>
   {how("Each bar is the part of one year's CERF money released that went to partners, the partner part of the chart on the left (100%): to local and national actors (national / local NGOs, government, national Red Cross / Red Crescent societies), to international NGOs, and to partners not yet typed in the reports. The label is the local and national share; the recent years fill in as partners are typed. Follows the same filters as the chart on the left.")}</div>
</div>
</div>"""

    data = {
        "pre": json.loads(_records(pre, ["k", "country_iso3", "hz", "region", "year",
                                         "kind", "fund_code", "amount_usd",
                                         "in_gho", "g"])),
        "act": json.loads(_records(act, ["k", "country_iso3", "hz", "region", "year",
                                         "fund_code", "amount_usd", "event_type",
                                         "in_gho", "g", "allocation_code"])),
        "ver": json.loads(_records(ver, ["k", "year", "kb_status", "hz", "region", "g", "funds"])),
        "now": json.loads(_records(vf, ["k", "country_iso3", "hz", "region", "ft", "total_usd", "g", "x"])),
        "fw": json.loads(_records(fw, ["k", "hz", "region", "lifecycle", "technical_support", "g", "funds"])),
        "cov": json.loads(_records(cov, ["k", "hz", "region", "people_covered", "g", "funds"])),
        "split": json.loads(_records(pr, ["k", "hz", "region", "agency", "sector", "ft",
                                          "amount_usd", "g"])),
        "cof": json.loads(_records(cof, ["k", "hz", "region", "year", "in_gho", "g", "amount_usd"])),
        "cofNow": json.loads(_records(cof_now, ["k", "hz", "region", "g", "in_gho", "who", "amount_usd", "detail"])),
        "fwList": fw_list,
        "fwy": d.get("fwy") or [],
        "unSplit": un_split,
        "flow": flow_rows, "flowYears": flow_years, "flowDefault": flow_default,
        "fundNames": fund_names, "cy": cy,
    }
    js = FLOW_JS + """
// two fund groups on this page's charts: CERF, and the Country and Regional Funds together, as
// the fund switch, the tiles and the notes name them (2026-10-28 owner comment: the agency chart
// said 'Country funds' and 'Regional funds'). The money-flow chart keeps each fund apart.
const FG = [['cerf','CERF',FUND_COLORS.cerf], ['pooled','Country and Regional Funds',FUND_COLORS.cbpf]];
// the Map's status colours; 'being updated' hatched in the two blues of its split pin
const FWC = (()=>{ const c = document.createElement('canvas'); c.width = c.height = 8; const x = c.getContext('2d');
  x.fillStyle = '#2171b5'; x.fillRect(0, 0, 8, 8); x.fillStyle = '#9ecae1';
  x.beginPath(); x.moveTo(8, 0); x.lineTo(8, 8); x.lineTo(0, 8); x.closePath(); x.fill();
  return {active:'#2171b5', updating:x.createPattern(c, 'repeat'), development:'#9ecae1', retired:'#9e9e9e'}; })();
const fgOf = ft => ft==='cerf' ? 'cerf' : 'pooled';
// the current year as of the build: its figures update daily until it closes, so it is labelled
// '2026*' (indicative; the footnote under the tiles) on every chart axis, selector and tile
const CY = D.cy, yLab = y => +y===CY ? y+'*' : String(y);
// whole millions, with one decimal under $100M so a regional total isn't rounded away
// (LAC released $22.5M, shown as $23M before 2026-10-16)
const M0 = v => { const m = v/1e6, r = Math.abs(m) < 100 ? Math.round(m*10)/10 : Math.round(m);
  return '$'+r.toLocaleString('en-US', {maximumFractionDigits: 1})+'M'; };
// the toggles: layers as on the map (g: c current framework, r retired, a ad hoc) and the fund
function sel(){ return {hz:fHaz.value, rg:fReg.value, gho:fGho.value, cum:fCum.checked,
  cur:fCur.checked, ret:fRet.checked, adh:fAdh.checked, fund:fFund.value,
  fws:fwSel, fwC:fwSel && new Set([...fwSel].map(cOf))}; }
const layerOK = (g, s) => g==='a' ? s.adh : g==='r' ? s.ret : s.cur;
// Money stays counted (owner, 2026-10-30: "the retired frameworks disbursed funding should STILL
// show up in the total disbursed to date"; "if the money was prearranged, it was prearranged,
// regardless of whether the framework has since been retired"): a retired framework's money —
// released, and pre-arranged in the years it was in place — counts while either framework layer
// is ticked (the map's flowActs(); the map's past years already count a framework by its status
// then). The framework counts and the figures of today (pre-arranged now, people covered, the
// agency split) keep layerOK: a retired framework has none of those now.
const relOK = (g, s) => g==='a' ? s.adh : g==='r' ? (s.ret || s.cur) : s.cur;
// ---- the framework picker: any subset of frameworks, for every tile and chart that follows the
// hazard and region filters. D.fwList: the frameworks (lc: lifecycle), then the countries whose AA
// money belongs to no framework (lc null, k 'ISO3|*'). fwSel: null = every line ticked (no
// filter), else the ticked keys; kept in the page address (#fw=ISO3.hazard,…) so a subset can be
// bookmarked.
const FWL = D.fwList, FWBY = Object.fromEntries(FWL.map(f=>[f.k, f]));
const FWK = new Set(FWL.filter(f=>f.lc).map(f=>f.k)), N_FW = FWK.size;
const cOf = k => k.slice(0, k.indexOf('|'));
let fwSel = null;
// frameworks whose pre-arranged money counts two activations a year (x: activations_per_year):
// marked * wherever their figure is (the picker, the tile; the note under the tiles)
const TWO = new Set(D.now.filter(r=>r.x>1).map(r=>r.k));
const twoName = k => { const f = FWBY[k]; return f ? tr8(f.name) + (f.hazard ? ' ' + tr8(f.hazard) : '') : k; };
if(TWO.size) document.querySelectorAll('.twoOnly').forEach(el=>{ el.style.display = ''; });
// framework money follows its framework's tick; money that belongs to no listed framework (an ad
// hoc allocation, a country-level pooled fund allocation, a pipeline pair) follows its country:
// kept while any line of that country is ticked
const fwOK = (r, s) => !s.fws || (r.g!=='a' && FWK.has(r.k) ? s.fws.has(r.k) : s.fwC.has(cOf(r.k)));
const escH = t => String(t).replace(/[&<>"']/g, c=>'&#'+c.charCodeAt(0)+';');
const M2 = v => '$'+(v/1e6).toFixed(2)+'M';
const LCL0 = {active:'active', updating:'being updated', development:'in development', retired:'retired'};
const LCL = new Proxy(LCL0, {get:(o, k)=>o[k] && tr8(o[k])});   // the statuses, in the page's language
const fwLines = () => [...fwRows.querySelectorAll('label.fw')];
const fwOn = l => l.querySelector('input').checked, fwShown = l => l.style.display!=='none';
function fwBuild(){
  const groups = [...new Set(FWL.filter(f=>f.lc).map(f=>f.region))].map(g=>[g, FWL.filter(f=>f.lc && f.region===g)]);
  const rest = FWL.filter(f=>!f.lc);
  if(rest.length) groups.push(['Non-framework allocations in countries with no framework in place', rest]);
  // the search reads the English and the shown language alike (data-t)
  const words = f => [f.name, tr8(f.name), f.hazard||'non-framework', tr8(f.hazard||'non-framework'), f.region||'', tr8(f.region||''),
                      LCL0[f.lc]||'no framework', LCL[f.lc]||tr8('no framework')].join(' ').toLowerCase();
  fwRows.innerHTML = `<div class='cap'>${tr8('pre-arranged now (in place today)')}</div>` + groups.map(([g, rows], i)=>
    `<label class='grp' data-g='${i}'><input type='checkbox' checked><span class='nm'>${escH(tr8(g))}</span><span class='amt'></span></label>`
    + rows.map(f=>`<label class='fw' data-g='${i}' data-k="${escH(f.k)}" data-t="${escH(words(f))}">`
      + `<input type='checkbox' checked><span class='nm'>${escH(tr8(f.name))}${f.hazard ? ' — '+escH(tr8(f.hazard)) : ''}</span>`
      + `<span class='st'>${f.lc ? LCL[f.lc] : tr8('non-framework allocations only')}</span><span class='amt'></span></label>`).join('')).join('');
}
function fwToDom(){ fwLines().forEach(l=>{ l.querySelector('input').checked = !fwSel || fwSel.has(l.dataset.k); }); }
function fwCommit(){ const on = fwLines().filter(fwOn).map(l=>l.dataset.k);
  fwSel = on.length===FWL.length ? null : new Set(on);
  history.replaceState(null, '', fwSel ? '#fw=' + on.map(k=>encodeURIComponent(k.replace('|','.'))).join(',') : location.pathname + location.search);
  draw(); }
function fwFromHash(){ const m = /[#&]fw=([^&]*)/.exec(location.hash); if(!m) return null;
  const on = new Set();
  m[1].split(',').forEach(x=>{ let k = ''; try { k = decodeURIComponent(x).replace('.','|'); } catch(e){}
    if(Object.hasOwn(FWBY, k)) on.add(k); });
  return on.size===FWL.length ? null : on; }
// the list follows the page: each line's pre-arranged money now (the fund switch applies), lines
// the layers or the hazard / region filter leave out dimmed, and the total — the tile's figure
function fwPaint(s, N){
  const amt = groupSum(D.now.filter(r=>ftOK(r.ft, s)), r=>r.k, r=>r.total_usd);
  const inView = f => f.lc ? (!s.hz||f.hz===s.hz) && (!s.rg||f.region===s.rg) && ((f.g==='r' ? relOK : layerOK)(f.g, s) || (!!f.g2 && relOK(f.g2, s))) : !s.rg && s.adh;
  const ticked = f => !s.fws || s.fws.has(f.k), gsum = {};
  fwLines().forEach(l=>{ const f = FWBY[l.dataset.k], a = amt[f.k], v = inView(f);
    l.classList.toggle('off', !v); l.title = v ? '' : tr8('left out by the layers or the hazard / region filter');
    l.querySelector('.amt').textContent = !f.lc ? '' : f.lc==='retired' ? '–' : a ? M2(a) + (TWO.has(f.k) ? '*' : '') : tr8('no envelope');
    if(v && s.cur && ticked(f) && a) gsum[l.dataset.g] = (gsum[l.dataset.g]||0) + a; });
  fwRows.querySelectorAll('label.grp').forEach(gl=>{ const rows = fwLines().filter(l=>l.dataset.g===gl.dataset.g);
    const n = rows.filter(fwOn).length, b = gl.querySelector('input');
    b.checked = n===rows.length; b.indeterminate = n>0 && n<rows.length;
    gl.querySelector('.amt').textContent = gsum[gl.dataset.g] ? M2(gsum[gl.dataset.g]) : ''; });
  const fws = FWL.filter(f=>f.lc), rest = FWL.filter(f=>!f.lc), nOn = fws.filter(ticked).length, xOn = rest.filter(ticked).length;
  const count = tr8('{0} of {1} frameworks ticked', nOn, N_FW) + (xOn<rest.length ? ' · ' + tr8('{0} of {1} countries with non-framework allocations only', xOn, rest.length) : '');
  const tot = sumOf(N, r=>r.total_usd), nc = sumOf(N.filter(r=>r.ft==='cerf'), r=>r.total_usd);
  fwSum.innerHTML = `<b>${count}</b> · ` + (!s.cur ? tr8('pre-arranged now: tick <i>Current frameworks</i> in the bar')
    : tr8('pre-arranged now <b>{0}</b>', M2(tot)) + (s.fund==='cerf' ? tr8(', CERF only') : s.fund==='pooled' ? tr8(', Country and Regional Funds only')
        : tr8(' (CERF {0} · Country and Regional Funds {1})', M2(nc), M2(tot-nc))) + (s.hz||s.rg ? tr8(', within the hazard / region filter') : ''));
  fwLab.textContent = s.fws ? tr8('Frameworks: {0} of {1} ▾', nOn, N_FW) : tr8('Frameworks: all ▾');
  fwPick.classList.toggle('on', !!s.fws);
  fwNote.style.display = fwFlowNote.style.display = s.fws ? '' : 'none';
  if(s.fws){ const nm = f => tr8(f.name) + (f.hazard ? ' '+tr8(f.hazard) : ' ' + tr8('(non-framework)'));
    const inn = FWL.filter(ticked).map(nm), out = FWL.filter(f=>!ticked(f)).map(nm);
    const list = a => escH(a.slice(0,14).join(', ')) + (a.length>14 ? ' ' + tr8('and {0} more', a.length-14) : '');
    fwNote.innerHTML = `<b>${count}</b> — ` + (!inn.length ? tr8('nothing is counted')
      : out.length < inn.length ? tr8('everything but {0}', list(out)) : list(inn))
      + '. ' + tr8('The tiles and the charts count only these.') + ` <button type='button'>${tr8('show all frameworks')}</button>`; }
}
const ftOK = (ft, s) => !s.fund || (s.fund==='cerf') === (ft==='cerf');
const fundOK = (fc, s) => ftOK(fundType(fc), s);
const pairFundOK = (funds, s) => !s.fund || (funds||'').includes(s.fund==='cerf' ? 'c' : 'p');
const sumOf = (rows, f) => rows.reduce((t,r)=>t+(f(r)||0), 0);
function stackedBy(id, rows, keyFn, valFn, opts){
  const keys = opts && opts.keys ? opts.keys : uniqSorted(rows, keyFn);
  mkChart(id,'bar',keys,FG.map(([g,lab,col])=>({label:lab, backgroundColor:col,
    data:keys.map(k=>groupSum(rows.filter(r=>fgOf(r.ft)===g&&keyFn(r)===k),()=>0,valFn)[0]||0)})).filter(d=>d.data.some(v=>v)),
    {stacked:true, totals:true, ...(opts||{})});
}
function topKeys(rows, keyFn, valFn, n){ const g = groupSum(rows.filter(r=>keyFn(r)!=null), keyFn, valFn);
  return Object.keys(g).sort((a,b)=>g[b]-g[a]).slice(0,n); }
function tiles(s, geo, A, N){
  if(s.fws && !s.fws.size){
    [[tFw,tFwl,'frameworks'],[tPre,tPrel,'pre-arranged now'],[tRel,tRell,'AA released'],[tCov,tCovl,'people covered now']].forEach(([v,l,w])=>{
      v.textContent = '–'; l.textContent = tr8('{0}: nothing ticked — tick at least one line in Frameworks', tr8(w)); });
    twoNote.style.display = 'none';
    return; }
  const selTxt = s.fws ? tr8(' · ticked frameworks only') : '';
  const fundTxt = s.fund==='cerf' ? tr8(' with CERF money') : s.fund==='pooled' ? tr8(' with Country and Regional Fund money') : '';
  const F = D.fw.filter(r=>geo(r) && layerOK(r.g,s) && pairFundOK(r.funds,s));
  // the fat number is every current framework, the line below breaks it down (2026-10-16
  // review); technical-support-only pairs are not counted here (the map still shows them)
  const n = lc => F.filter(r=>r.lifecycle===lc).length;
  if(s.cur){ tFw.textContent = n('active') + n('updating') + n('development');
    tFwl.textContent = tr8('frameworks{0} — {1} active · {2} being updated · {3} in development', fundTxt, n('active'), n('updating'), n('development'))
      + (s.ret ? tr8(' · {0} retired', n('retired')) : '') + selTxt; }
  else if(s.ret){ tFw.textContent = n('retired'); tFwl.textContent = tr8('retired frameworks{0}', fundTxt) + selTxt; }
  else { tFw.textContent = '–'; tFwl.textContent = tr8('frameworks: no framework layer selected'); }
  const nc = sumOf(N.filter(r=>r.ft==='cerf'), r=>r.total_usd), np = sumOf(N.filter(r=>r.ft!=='cerf'), r=>r.total_usd);
  if(!s.cur){ tPre.textContent = '–'; tPrel.textContent = tr8('pre-arranged now: select current frameworks (retired frameworks and non-framework allocations have none)'); }
  else { tPre.textContent = M0(nc+np);
    const two = [...new Set(N.filter(r=>r.x>1 && r.total_usd>0).map(r=>r.k))];
    tPrel.textContent = tr8('pre-arranged now — {0}', s.fund==='cerf' ? 'CERF' : s.fund==='pooled' ? tr8('Country and Regional Funds') : tr8('CERF {0} · Country and Regional Funds {1}', M0(nc), M0(np)))
      + (two.length ? tr8(' · counts {0} twice', two.map(k=>twoName(k)+'*').join(', ')) : '') + selTxt; }
  twoNote.style.display = s.cur && N.some(r=>r.x>1 && r.total_usd>0) ? '' : 'none';
  const ys = uniqSorted(A, r=>r.year);
  const what = [(s.cur||s.ret) ? tr8('framework activations') : null, s.adh ? tr8('non-framework allocations') : null].filter(Boolean).join(' + ');
  tRel.textContent = M0(sumOf(A, r=>r.amount_usd));
  tRell.textContent = tr8('AA released {0} — {1}, ', ys.length ? yLab(ys[0])+(ys.length>1 ? '–'+yLab(ys[ys.length-1]) : '') : tr8('(none in this selection)'), what || tr8('no layer selected'))
    + (s.fund==='cerf' ? 'CERF' : s.fund==='pooled' ? tr8('Country and Regional Funds') : tr8('CERF and Country and Regional Funds')) + (s.gho ? tr8(', GHO contexts') : '')
    + (s.fws ? (s.adh ? tr8(' · ticked frameworks, and the non-framework allocations of their countries') : selTxt) : '')
    + (() => { const r = s.ret ? 0 : sumOf(A.filter(x=>x.g==='r'), x=>x.amount_usd);
               return r >= 5e4 ? tr8(' · includes {0} released by frameworks since retired', M0(r)) : ''; })();
  // people covered: a now figure, current frameworks only (as pre-arranged now and the map)
  if(!s.cur){ tCov.textContent = '–'; tCovl.textContent = tr8('people covered now: select current frameworks (a retired framework covers no one now)'); }
  else { const C = D.cov.filter(r=>geo(r) && pairFundOK(r.funds,s));
    const live = F.filter(r=>['active','updating','development'].includes(r.lifecycle)).length;
    tCov.textContent = (sumOf(C, r=>r.people_covered)/1e6).toFixed(1)+'M';
    tCovl.textContent = tr8('people covered now — current frameworks{0}, latest figure each ({1} of {2} have one) · not people reached', fundTxt, new Set(C.map(r=>r.k)).size, live) + selTxt; }
}
function draw(){
  const s = sel(), gho = s.gho;
  const geo = r => (!s.hz||r.hz===s.hz) && (!s.rg||r.region===s.rg) && fwOK(r, s);
  const P = D.pre.filter(r=>r.kind==='prearranged' && r.fund_code!=='all' && geo(r) && (!gho||r.in_gho)
      && relOK(r.g,s) && fundOK(r.fund_code,s));
  const A = D.act.filter(r=>geo(r) && (!gho||r.in_gho) && relOK(r.g,s) && fundOK(r.fund_code,s));
  const years = uniqSorted(P.concat(A), r=>r.year);
  for(const [id, rows] of [['c1',P],['c2',A]]){
    const ds = FG.map(([g,lab,col])=>{
      let vals = years.map(y=>sumOf(rows.filter(r=>fgOf(fundType(r.fund_code))===g&&r.year===y), r=>r.amount_usd));
      if(s.cum && id==='c2') vals = cumulate(vals);   // pre-arranged is a stock: never cumulated
      return {label:lab, data:vals, backgroundColor:col};}).filter(d=>d.data.some(v=>v));
    mkChart(id,'bar',years.map(yLab),ds,{stacked:true, totals:true});
  }
  // frameworks each year, by status (D.fwy: each framework's status at year end, the current
  // year as the tiles count it): the current frameworks' statuses while that layer is on, the
  // retired ones while theirs is. Not the fund switch: a count. 'Being updated' is hatched in
  // the two blues of the Map's split pin
  { const W = D.fwy.filter(r=>(!s.hz||r.hz===s.hz) && (!s.rg||r.region===s.rg) && fwOK(r, s));
    const ys = [...new Set(years.map(String).concat(W.flatMap(r=>Object.keys(r.y))))].sort();
    const ST = [['active','Active',FWC.active], ['updating','Being updated',FWC.updating],
                ['development','In development',FWC.development], ['retired','Retired',FWC.retired]];
    const ds = ST.filter(([k])=>k==='retired' ? s.ret : s.cur).map(([k,lab,col])=>({label:lab,
      data:ys.map(y=>W.filter(r=>r.y[y]===k && (!gho||r.gho[y])).length), backgroundColor:col})).filter(d=>d.data.some(v=>v));
    mkChart('c0','bar',ys.map(yLab),ds,{stacked:true, totals:true, count:true}); }
  const N = D.now.filter(r=>geo(r) && layerOK(r.g,s) && ftOK(r.ft,s));
  stackedBy('c3', N, r=>r.hz, r=>r.total_usd); stackedBy('c4', N, r=>r.region, r=>r.total_usd);
  // co-financing PRE-ARRANGED: money from outside the pooled funds, so the fund switch cannot
  // split it; ad hoc allocations carry none. By year, a stock at each year end (never added up),
  // the current year being D.cofNow: each framework's figure now, which the second chart splits
  // by co-financer — the two agree on the current year by construction.
  {
    const keep = r => geo(r) && (!gho||r.in_gho) && relOK(r.g,s);   // co-financing pre-arranged: a retired framework's too
    const Y = D.cof.filter(r=>+r.year!==CY && keep(r)), W = D.cofNow.filter(keep);
    const why = s.fund ? tr8('Co-financing is money from outside CERF and the Country and Regional Funds: the fund switch does not apply to it — select both funds to see it.')
      : !(s.cur||s.ret) ? tr8('Co-financing belongs to frameworks: select current or retired frameworks (non-framework allocations carry none).')
      : !(Y.length||W.length) ? tr8('No pre-arranged co-financing recorded in this selection.') : '';
    cofYear.style.display = cofWhoBox.style.display = why ? 'none' : '';
    [cofYearX, cofWhoX].forEach(el=>{ el.style.display = why ? '' : 'none'; el.textContent = why; });
    if(!why){
      const yrs = [...new Set(Y.map(r=>+r.year).concat(W.length ? [CY] : []))].sort((a,b)=>a-b);
      mkChart('cofYear','bar',yrs.map(yLab),[{label:'Co-financing', backgroundColor:PAL[3],
        data:yrs.map(y=>sumOf(y===CY ? W : Y.filter(r=>+r.year===y), r=>r.amount_usd))}], {stacked:true, totals:true});
      // now, by co-financer: one bar per organisation, sorted by amount, 'not recorded' last; the
      // box grows with the bars so each name stays readable
      const g = groupSum(W, r=>r.who, r=>r.amount_usd);
      const keys = Object.keys(g).filter(k=>k!=='not recorded').sort((a,b)=>g[b]-g[a]);
      if(g['not recorded']) keys.push('not recorded');
      cofWhoBox.style.height = Math.max(120, 40 + 17*keys.length) + 'px';
      if(!keys.length){ cofWhoBox.style.display = 'none'; cofWhoX.style.display = '';
        cofWhoX.textContent = tr8('No pre-arranged co-financing in place today in this selection.'); }
      else {
        const ch = mkChart('cofWho','bar',keys,[{label:tr8('in place today ({0})', yLab(CY)), data:keys.map(k=>g[k]),
          backgroundColor:keys.map(k=>k==='not recorded' ? '#b9c3cf' : PAL[3])}],
          {allLabels:true, totals:true, extra:{indexAxis:'y'}});
        // the frameworks behind a bar, and what each line says (the kind of money, the channel)
        ch.options.plugins.tooltip.callbacks.afterBody = items=>{ const w = keys[items[0].dataIndex];
          const R = W.filter(r=>r.who===w), by = groupSum(R, r=>r.k, r=>r.amount_usd);
          const fws = Object.keys(by).sort((a,b)=>by[b]-by[a]);
          return fws.slice(0,10).map(k=>{ const det = [...new Set(R.filter(r=>r.k===k).map(r=>r.detail))].filter(x=>x && x!==w);
            return `${twoName(k)}: ${money(by[k])}` + (det.length ? ` (${det.join('; ')})` : ''); })
            .concat(fws.length>10 ? [tr8('and {0} more', fws.length-10)] : []); };
        ch.options.scales.y.ticks.callback = function(v){ const l = this.getLabelForValue(v);
          return l.length>32 ? l.slice(0,31)+'…' : l; };
        ch.update(); }
    }
  }
  const S = D.split.filter(r=>geo(r) && layerOK(r.g,s) && ftOK(r.ft,s));
  const SA = S.filter(r=>r.agency), SS = S.filter(r=>r.sector);
  stackedBy('c7', SA, r=>r.agency, r=>r.amount_usd, {keys:topKeys(SA,r=>r.agency,r=>r.amount_usd,18), extra:{indexAxis:'y'}});
  stackedBy('c8', SS, r=>r.sector, r=>r.amount_usd, {keys:topKeys(SS,r=>r.sector,r=>r.amount_usd,18), allLabels:true, extra:{indexAxis:'y'}});
  tiles(s, geo, A, N);
  fwPaint(s, N);
  // UN agencies and partners: the CERF part of c2 (A), split by the sub-grant reports
  const un = s.fund!=='pooled';
  unBox.style.display = un ? '' : 'none'; unNone.style.display = un ? 'none' : '';
  if(un) drawUN(s, A);
  if(window._flowDraw) _flowDraw();
}
// UN vs partners (hidden when only the Country and Regional Funds are selected): the CERF rows of
// c2 (A: every filter applied, by the activation's year), each allocation's money split by the
// share its agencies sub-granted of its project budgets (D.unSplit: g by partner group, l by
// localisation, p the partners); no split recorded: 'split not known'. So c9 = c2's CERF bars.
const UG = ['direct UN spend','INGO','NNGO / local','Red Cross / Red Crescent','government','other','split not known'];
function drawUN(s, A){
  const C = A.filter(r=>r.fund_code==='cerf'), uy = uniqSorted(C, r=>r.year);
  const by = {}, lby = {}, pids = new Set();
  let known = 0, sub = 0;
  C.forEach(r=>{ const v = r.amount_usd||0, x = D.unSplit[r.allocation_code], o = by[r.year] ??= {};
    const add = (g, u) => { o[g] = (o[g]||0) + u; };
    if(!x){ add('split not known', v); return; }
    const l = lby[r.year] ??= {year:r.year, local:0, intl:0, untyped:0};
    let s_ = 0;
    Object.entries(x.g).forEach(([g, sh])=>{ add(g, v*sh); s_ += v*sh; });
    add('direct UN spend', v - s_); known += v; sub += s_;
    Object.entries(x.l).forEach(([k, sh])=>{ l[k] += v*sh; });
    if(v > 0) x.p.forEach(i=>pids.add(i)); });
  const ds = UG.map((g,i)=>({label:g, backgroundColor: g==='split not known' ? '#c8ccd2' : PAL[i],
    data:uy.map(y=>(by[y]||{})[g]||0)})).filter(d=>d.data.some(v=>v));
  if(s.cum) ds.forEach(d=>{ d.data = cumulate(d.data); });   // as c2
  mkChart('c9','bar',uy.map(yLab),ds,{stacked:true, totals:true});
  // local and national share of the money passed to partners, per year (100% bars, local share labelled)
  const L = Object.values(lby).filter(r=>r.local+r.intl+r.untyped > 0.5).sort((a,b)=>a.year-b.year), yl = L.map(r=>r.year);
  const lt = sumOf(L, r=>r.local), st = sumOf(L, r=>r.local+r.intl+r.untyped);
  uS.textContent = known ? Math.round(100*sub/known)+'%' : '–';
  uSl.textContent = tr8('of the CERF AA money released, sub-granted to partners') + (uy.length ? ` (${uy[0]}→)` : '') + (s.rg ? ` · ${tr8(s.rg)}` : '');
  uL.textContent = st ? Math.round(100*lt/st)+'%' : '–';
  uT.textContent = '$'+(sub/1e6).toLocaleString('en-US', {minimumFractionDigits:1, maximumFractionDigits:1})+'M';
  uTl.textContent = tr8('sub-granted in total · {0} partners', pids.size) + (s.rg ? ` · ${tr8(s.rg)}` : '');
  const tot = r => r.local + r.intl + r.untyped, pc = (r, k) => tot(r) ? 100*r[k]/tot(r) : 0;
  const parts = [['local','local and national actors','#1baf7a'], ['intl','international NGOs','#9aa3c7'], ['untyped','partner not yet typed','#d9d9d6']];
  const ch = mkChart('c10','bar',yl.map(yLab), parts.map(([k,lab,col])=>({label:lab, backgroundColor:col, data:L.map(r=>pc(r,k))})), {stacked:true});
  const localLabel = { id:'localLabel', afterDatasetsDraw(c){ const {ctx, scales:{x, y}} = c;
    if(!c.isDatasetVisible(0)) return;
    ctx.save(); ctx.font = '600 11px ' + Chart.defaults.font.family; ctx.fillStyle = '#fff'; ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
    L.forEach((r,i)=>{ const v = pc(r,'local'); if(v >= 8) ctx.fillText(Math.round(v)+'%', x.getPixelForValue(i), y.getPixelForValue(v)+15); });
    ctx.restore(); } };
  ch.config.plugins.push(localLabel);
  ch.options.scales.y.max = 100; ch.options.scales.y.ticks.callback = v=>v+'%';
  ch.options.plugins.tooltip.callbacks.label = c=>{ const r = L[c.dataIndex], k = parts[c.datasetIndex][0];
    return ' ' + tr8('{0}: {1}% ({2} of {3} sub-granted)', c.dataset.label, Math.round(c.parsed.y), money(r[k]), money(tot(r))); };
  ch.update();
}
uniqSorted(D.pre,r=>r.hz).forEach(h=>fHaz.add(new Option(tr8(h),h)));
uniqSorted(D.pre,r=>r.region).forEach(r=>fReg.add(new Option(tr8(r),r)));
[fHaz,fReg,fGho,fCum,fCur,fRet,fAdh,fFund].forEach(el=>el.addEventListener('change',draw));
// a language switch (site_i18n): the options built here, the framework list and every figure
document.addEventListener('aalang', ()=>{
  [fHaz, fReg].forEach(el=>[...el.options].forEach(o=>{ if(o.value) o.text = tr8(o.value); }));
  fwBuild(); fwToDom(); draw(); });
// the flow chart: the layers and the fund switch filter its rows (donors off: it starts at the funds)
window._flowDraw = mountFlow({label:'AA money through funds and agencies to partners', yLab, cy:CY, noYear:CY,
  keep: r=>{ const s = sel(); return relOK(r.g, s) && (!s.fund || (s.fund==='cerf') === (r.fu==='c'))
                                && (!s.rg || r.rg===s.rg); }});
// the framework picker: a group line ticks its lines; with a search typed, the buttons and the
// group lines act on the lines shown
fwBuild(); fwSel = fwFromHash(); fwToDom();
fwRows.addEventListener('change', ev=>{ const l = ev.target.closest('label');
  if(l.classList.contains('grp')) fwLines().filter(x=>x.dataset.g===l.dataset.g && fwShown(x)).forEach(x=>{ x.querySelector('input').checked = ev.target.checked; });
  fwCommit(); });
function fwSetShown(v){ fwLines().filter(fwShown).forEach(l=>{ l.querySelector('input').checked = v; }); fwCommit(); }
fwAll.addEventListener('click', ()=>fwSetShown(true)); fwNone.addEventListener('click', ()=>fwSetShown(false));
fwQ.addEventListener('input', ()=>{ const q = fwQ.value.toLowerCase().split(' ').filter(Boolean);
  fwLines().forEach(l=>{ l.style.display = q.every(w=>l.dataset.t.includes(w)) ? '' : 'none'; });
  fwRows.querySelectorAll('label.grp').forEach(gl=>{ gl.style.display = fwLines().some(l=>l.dataset.g===gl.dataset.g && fwShown(l)) ? '' : 'none'; });
  fwAll.textContent = q.length ? tr8('tick shown') : tr8('tick all'); fwNone.textContent = q.length ? tr8('untick shown') : tr8('untick all'); });
fwNote.addEventListener('click', ev=>{ if(ev.target.tagName==='BUTTON'){ fwSel = null; fwToDom(); fwCommit(); } });
// 'Reset all filters' (2026-10-09 meeting): every control of the bar back to how the page opens —
// the layers and cumulative as the page writes them (defaultChecked: current frameworks on;
// non-framework, retired and cumulative off), the fund, hazard, region and GHO selects on their first
// option ('' = all), every framework ticked with the list's search cleared, and no #fw= in the
// address (fwCommit). The money-flow chart's own controls are views of that chart, not filters.
fReset.addEventListener('click', ()=>{
  [fCur, fRet, fAdh, fCum].forEach(el=>{ el.checked = el.defaultChecked; });
  [fFund, fHaz, fReg, fGho].forEach(el=>{ el.value = ([...el.options].find(o=>o.defaultSelected) || el.options[0]).value; });
  if(fwQ.value){ fwQ.value = ''; fwQ.dispatchEvent(new Event('input')); }
  fwPick.open = false; fwSel = null; fwToDom(); fwCommit(); });
// the list never runs below the window, so its total stays in view wherever the bar sits
function fwFit(){ if(!fwPick.open) return; const p = fwPick.querySelector('.fwpanel');
  p.style.maxHeight = Math.max(220, innerHeight - p.getBoundingClientRect().top - 12) + 'px';
  p.style.left = ''; const over = p.getBoundingClientRect().right - (document.documentElement.clientWidth - 8);
  if(over > 0) p.style.left = (10 - over) + 'px'; }
fwPick.addEventListener('toggle', ()=>{   // little room under the bar: bring the bar to the top of the window first
  const bar = fwPick.closest('.fbar');
  if(fwPick.open && innerHeight - bar.getBoundingClientRect().bottom < 360) bar.scrollIntoView();
  fwFit(); });
addEventListener('scroll', fwFit, {passive:true}); addEventListener('resize', fwFit);
document.addEventListener('click', ev=>{ if(fwPick.open && !fwPick.contains(ev.target)) fwPick.open = false; });
document.addEventListener('keydown', ev=>{ if(ev.key==='Escape') fwPick.open = false; });
window.addEventListener('hashchange', ()=>{ fwSel = fwFromHash(); fwToDom(); draw(); });
draw();"""
    import figure_check
    figure_check.KEY["financing"] = data     # the cross-page figure check (build_site)
    _dash_page(page, "dash-funding.html", "Financing",
               TB("<b>The money of anticipatory action</b>: pre-arranged and released across CERF, "
                  "Country and Regional Funds, with the map's layers and a fund, hazard, region and "
                  "GHO filter. <b>Frameworks</b> in the filter bar lists every framework: tick any "
                  "subset (a sub-region, a few countries) to total it. The money-flow chart can start from "
                  "the donors of each fund."),
               panels, json.dumps(data, default=str), js)


# --------------------------------------------------------- model (triggers)
LIFE_LABEL = {"active": "active", "updating": "being updated", "development": "in development"}


def build_model(page, d):
    import page_model
    return page_model.build_model(page, d)


# -------------------------------------------------------------- plan (people)
def build_plan(page, d):
    import page_plan
    return page_plan.build_plan(page, d)


# ---------------------------------------------------------------- learning
PREMISES = [("speed", "Speed"), ("cost_effectiveness", "Cost effectiveness"),
            ("lives_livelihoods", "Saving lives and livelihoods"),
            ("development_gains", "Protecting development gains"), ("dignity", "Dignity"),
            ("long_term", "Long-term effects")]
DOC_TYPE_LABEL = {"aar": "after-action review", "evaluation": "evaluation",
                  "impact_evaluation": "impact evaluation", "monitoring_report": "monitoring report",
                  "activation_report": "activation report", "case_study": "case study",
                  "story": "story", "research": "research", "guidance": "guidance",
                  "trigger_analysis": "trigger analysis", "other": "other"}


def _aslist(v):
    """text[] columns arrive as lists (psycopg2) — or None / a '{a,b}' string in a snapshot."""
    if v is None or (not isinstance(v, (list, tuple)) and pd.isna(v)):
        return []
    if isinstance(v, str):
        return [x for x in v.strip("{}").split(",") if x]
    return list(v)


def _doc_li(r):
    """One learning document as a list item: title link · publisher · year · type tag."""
    import html as _h
    title = _h.escape(str(r.title))
    t = (f"<a href='{_h.escape(str(r.url))}' target='_blank' rel='noopener'>{title}</a>"
         if isinstance(r.url, str) and r.url else title)
    who = " · ".join(str(x) for x in [r.publisher if isinstance(r.publisher, str) else None,
                                      int(r.year) if pd.notna(r.year) else None] if x)
    tag = f"<span class='doctag'>{T(code_words(DOC_TYPE_LABEL, r.doc_type, 'document type') or 'document')}</span>"
    ks = (f"<span class='ks'>{_h.escape(str(r.key_stat))}</span>"
          if isinstance(r.key_stat, str) and r.key_stat else "")
    return f"<li>{t}{(' <span class=' + chr(39) + 'who' + chr(39) + '>· ' + who + '</span>') if who else ''}{tag}{ks}</li>"


def _fw_docs(docs, c, h):
    """Country-scope documents of a framework: the ISO3 in country_iso3, hazard null or equal."""
    if not len(docs):
        return docs
    m = [(r.scope == "country") and (c in _aslist(r.country_iso3))
         and (not isinstance(r.hazard, str) or not r.hazard or r.hazard == h)
         for r in docs.itertuples()]
    return docs[m]


def build_learning(page, d):
    import page_learning
    return page_learning.build_learning(page, d)


# ------------------------------------------------------------------ hub + frameworks
MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]


def _cal_strip(cal, c, h):
    on = set(cal.loc[(cal["country_iso3"] == c) & (cal["hazard"] == h), "month"])
    # month initials in each language (Spanish: E for enero)
    cells = "".join(f"<td class='{'on' if m in on else ''}'>{T(MONTHS[m-1], MONTHS[m-1], 'EFMAMJJASOND'[m-1])}</td>"
                    for m in range(1, 13))
    return f"<table class='cal'><tr>{cells}</tr></table>"


ORG_GROUPS = [("government", "Government"), ("un", "UN"), ("ingo", "International NGOs"),
              ("nngo", "National NGOs"), ("rcrc", "Red Cross / Red Crescent"), ("other", "Other")]


def _partners_block(pt, sg, c, h, version):
    """The Partners sub-block of a framework page: aa.framework_partner rows of the version,
    grouped by org type, then the CERF AA sub-grantees of the country by agency."""
    import html as _h
    p = pt[(pt["country_iso3"] == c) & (pt["hazard"] == h)]
    note = ""
    pv = p[p["version"].astype(str) == str(version)] if version else p.iloc[0:0]
    if not len(pv) and len(p):
        alt = sorted(p["version"].astype(str).unique())[-1]
        pv = p[p["version"].astype(str) == alt]
        note = f" <span class='muted' style='font-size:11px'>{TF('(from version {v})', v=alt)}</span>"
    groups = ""
    for key, label in ORG_GROUPS:
        g = pv[pv["org_type"] == key] if key != "other" else pv[
            ~pv["org_type"].isin([k for k, _g in ORG_GROUPS if k != "other"])]
        if not len(g):
            continue
        items = "".join(
            f"<li>{_h.escape(str(r.name))}"
            f"{(' (' + _h.escape(str(r.acronym)) + ')') if isinstance(r.acronym, str) and r.acronym else ''}"
            # a role is a code (translated) or the document's own words (as written)
            f"{(' <span class=' + chr(39) + 'muted' + chr(39) + '>' + ', '.join(TD(_role_words(x)) for x in _aslist(r.roles) if _role_words(x)) + '</span>') if any(map(_role_words, _aslist(r.roles))) else ''}"
            f"{(' <span class=' + chr(39) + 'muted' + chr(39) + '>' + TF('under {p}', p=str(r.agency_parent)) + '</span>') if isinstance(r.agency_parent, str) and r.agency_parent else ''}"
            f"{(' · ' + _fmt_usd(r.amount_usd)) if pd.notna(r.amount_usd) else ''}</li>"
            for r in g.itertuples())
        groups += f"<div class='pg'><h4>{T(label)} · {len(g)}</h4><ul style='margin:0;padding-left:16px'>{items}</ul></div>"
    head = (f"<b>{TF('{n} partners', n=pv['name'].nunique())}</b>{note}" if len(pv)
            else f"<span class='empty'>{T('no partners recorded for this version yet')}</span>")
    s = sg[sg["country_iso3"] == c]
    sub = ""
    if len(s):
        for ag, g in s.groupby("agency", sort=True):
            names = (g.groupby("partner_name")
                     .agg(usd=("subgrant_usd", "sum"), typ=("partner_type", "first"))
                     .sort_values("usd", ascending=False))
            items = "".join(
                f"<li>{_h.escape(str(n))} <span class='muted'>{str(r.typ) if pd.notna(r.typ) else ''}</span>"
                f" · {_fmt_usd(r.usd)}</li>" for n, r in names.iterrows())
            sub += (f"<div class='pg'><h4>{_h.escape(str(ag))} · "
                    f"{TF('{usd} to {n}', usd=_fmt_usd(g['subgrant_usd'].sum()), n=len(names))}"
                    f"</h4><ul style='margin:0;padding-left:16px'>{items}</ul></div>")
        sub = (f"<h3 class='sub'>{T('Funded sub-grantees')} <span class='muted' style='font-weight:400'>"
               f"{TF('— CERF AA sub-grants in {c}, all activations, by agency', c=c)}</span></h3>"
               f"<div class='partners'>{sub}</div>")
    return (f"<h3 class='sub'>{T('Partners')}</h3><p style='margin:4px 0 8px'>{head}</p>"
            + (f"<div class='partners'>{groups}</div>" if groups else "") + sub)


# Drive folder with the trigger-validation material (rendered only when set)
TRIGGER_VALIDATION_URL = ""
MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
ACT_RED = "#e3322d"


def _m(v):
    """$15M / $5.7M / $650k — compact money for the change sentences."""
    v = float(v)
    if v >= 1e6:
        s = f"{v/1e6:.2f}".rstrip("0").rstrip(".")
        return f"${s}M"
    return f"${v/1e3:,.0f}k" if v >= 1e3 else f"${v:,.0f}"


def _has(v):
    """A frontmatter value that is actually recorded (None / '' / [] / {} are not)."""
    if v is None:
        return False
    if isinstance(v, (list, tuple, dict, str)):
        return len(v) > 0
    return not (isinstance(v, float) and pd.isna(v))


def _words(s):
    import re
    return set(re.findall(r"[a-z0-9]+", str(s).lower())) - {"of", "the", "in", "and", "a"}


def _match_triggers(old, new):
    """Greedy pairing of trigger-window rows across two versions by basis + indicator word
    overlap; returns (pairs, dropped old rows, added new rows)."""
    cand = []
    for i, o in enumerate(old):
        for j, n in enumerate(new):
            wo, wn = _words(o.get("indicator", "")), _words(n.get("indicator", ""))
            sim = len(wo & wn) / max(len(wo | wn), 1)
            if o.get("basis") == n.get("basis"):
                sim += 0.2
            cand.append((sim, i, j))
    used_o, used_n, pairs = set(), set(), []
    for sim, i, j in sorted(cand, key=lambda x: (-x[0], x[1], x[2])):
        if sim < 0.3 or i in used_o or j in used_n:
            continue
        used_o.add(i); used_n.add(j); pairs.append((i, j))
    return (pairs, [o for i, o in enumerate(old) if i not in used_o],
            [n for j, n in enumerate(new) if j not in used_n])


_TROW_STD = {"basis", "lead time", "return period", "releases", "releases (usd)", "releases (planned)",
             "monitored by"}


def _trow(t):
    """A trigger-window row with `window` and `indicator` filled in where the page used its own
    column names (Haiti 2024-08-23: 'window (pdf → code)', and the conditions as 'wind' and
    '2-day rain' columns instead of one indicator)."""
    t = dict(t)
    if not _has(t.get("window")):
        k = next((k for k in t if str(k).startswith("window")), None)
        if k is not None and _has(t[k]):
            t["window"] = str(t[k]).split("→")[0].strip()
    if not _has(t.get("indicator")):
        conds = [f"{k} {v}" for k, v in t.items()
                 if k not in _TROW_STD and k not in ("window", "threshold")
                 and not str(k).startswith("window") and _has(v)]
        if conds:
            t["indicator"] = " AND ".join(conds)
    return t


def _version_diff(fo, fn, to, tn, w=lambda x: x):
    """Qualitative change sentences between two versions' structured metadata (frontmatter
    fo -> fn, trigger-window rows to -> tn). Only fields recorded on both sides. w: the
    sentences' words in one language (the recorded values inside them stay as recorded)."""
    import html as _h
    fo, fn = fo or {}, fn or {}
    to = [_trow(t) for t in (to or []) if isinstance(t, dict)]
    tn = [_trow(t) for t in (tn or []) if isinstance(t, dict)]
    out = []
    both = lambda k: _has(fo.get(k)) and _has(fn.get(k))   # noqa: E731
    esc = lambda s: _h.escape(str(s))                        # noqa: E731
    unit = {0: "zones", 1: "admin-1 areas", 2: "admin-2 areas", 3: "admin-3 areas"}
    unit1 = {0: "zone", 1: "admin-1 area", 2: "admin-2 area", 3: "admin-3 area"}
    # geographic scope (with the admin level as the unit where known)
    _sl = lambda x: [str(x)] if isinstance(x, str) else [str(y) for y in (x or [])]   # noqa: E731
    if both("geographic_scope") and sorted(_sl(fo["geographic_scope"])) != sorted(_sl(fn["geographic_scope"])):
        lo, ln = fo.get("admin_level"), fn.get("admin_level")
        go, gn = _sl(fo["geographic_scope"]), _sl(fn["geographic_scope"])
        verb = "changed"
        if isinstance(lo, (int, float)) and isinstance(ln, (int, float)) and ln != lo:
            verb = "narrowed" if ln > lo else "widened"
        elif lo == ln:
            if set(gn) < set(go):
                verb = "narrowed"
            elif set(go) < set(gn):
                verb = "widened"
        def _g(g, lvl):
            u = ((unit1 if len(g) == 1 else unit).get(lvl, "area" if len(g) == 1 else "areas")
                 if isinstance(lvl, (int, float)) else "area" if len(g) == 1 else "areas")
            return f"{len(g)} {w(u)} ({', '.join(esc(x) for x in g)})"
        out.append(w(f"Geographic scope {verb} from {{a}} to {{b}}").format(a=_g(go, lo), b=_g(gn, ln)))
    if both("admin_level") and fo["admin_level"] != fn["admin_level"]:
        out.append(w("Admin level {a} → {b}").format(a=fo["admin_level"], b=fn["admin_level"]))
    # trigger windows
    no = len(to) or (fo.get("trigger_facets") or {}).get("n_windows")
    nn = len(tn) or (fn.get("trigger_facets") or {}).get("n_windows")
    if to and tn:
        pairs, dropped, added = _match_triggers(to, tn)
        bits = ([w("dropped {x}").format(x=f"{esc(t.get('window', '?'))} — {esc(t.get('indicator', ''))}") for t in dropped]
                + [w("added {x}").format(x=f"{esc(t.get('window', '?'))} — {esc(t.get('indicator', ''))}") for t in added])
        if len(to) != len(tn) or bits:
            out.append(w("Trigger windows: {a} → {b}").format(a=len(to), b=len(tn)) + (f" ({'; '.join(bits)})" if bits else ""))
        cut = lambda x: (str(x)[:110] + '…') if len(str(x)) > 111 else str(x)   # noqa: E731
        thr = [f"{esc(to[i].get('window', ''))}: {esc(cut(to[i].get('threshold')))} → {esc(cut(tn[j].get('threshold')))}"
               for i, j in pairs if _has(to[i].get("threshold")) and _has(tn[j].get("threshold"))
               and str(to[i]["threshold"]).strip() != str(tn[j]["threshold"]).strip()]
        if thr:
            out.append(w("Thresholds changed — {x}").format(x="; ".join(thr)))
    elif no and nn and no != nn:
        out.append(w("Trigger windows: {a} → {b}").format(a=no, b=nn))
    # trigger facets: indicators, basis, calibration
    tfo, tfn = fo.get("trigger_facets") or {}, fn.get("trigger_facets") or {}
    io, inn = tfo.get("indicators") or [], tfn.get("indicators") or []
    if io and inn and set(io) != set(inn):
        gone, new = [x for x in io if x not in inn], [x for x in inn if x not in io]
        kept = [x for x in io if x in inn]
        swaps = []
        for g in list(gone):   # same family (text before the first '-') -> "a → b"
            fam = str(g).split("-")[0].lower()
            m = next((n for n in new if str(n).split("-")[0].lower() == fam), None)
            if m is not None:
                swaps.append(f"{esc(g)} → {esc(m)}"); gone.remove(g); new.remove(m)
        bits = (swaps + [w("dropped {x}").format(x=esc(x)) for x in gone]
                + [w("added {x}").format(x=esc(x)) for x in new])
        if kept:
            bits.append(w("{x} kept").format(x=", ".join(esc(x) for x in kept)))
        out.append(w("Indicators: {x}").format(x="; ".join(bits)))
    for k, lab in [("basis", "Trigger basis: {a} → {b}"), ("calibration", "Calibration: {a} → {b}")]:
        if _has(tfo.get(k)) and _has(tfn.get(k)) and tfo[k] != tfn[k]:
            out.append(w(lab).format(a=esc(tfo[k]), b=esc(tfn[k])))
    # monitoring months
    mo = (fo.get("monitoring_period") or {}).get("months") if isinstance(fo.get("monitoring_period"), dict) else None
    mn = (fn.get("monitoring_period") or {}).get("months") if isinstance(fn.get("monitoring_period"), dict) else None
    _mi = lambda ms: sorted({int(x) for x in (ms or []) if isinstance(x, int) and 1 <= x <= 12})  # noqa: E731
    mo, mn = _mi(mo) if _has(mo) else None, _mi(mn) if _has(mn) else None
    if mo and mn and mo != mn:
        nm = lambda ms: ", ".join(w(MONTH_ABBR[x - 1]) for x in ms)  # noqa: E731
        out.append(w("Monitoring months: {a} → {b}").format(a=nm(mo), b=nm(mn)))
    # money
    for k, lab in [("prearranged_funding_usd", "Pre-arranged: {a} → {b}"), ("cofinancing_usd", "Co-financing: {a} → {b}")]:
        if both(k):
            try:
                a, b = float(fo[k]), float(fn[k])
            except (TypeError, ValueError):
                continue
            if abs(a - b) > 0.5:
                out.append(w(lab).format(a=_m(a), b=_m(b)))
    for k, lab in [("funding_by_source", "Funding by source: {x}"), ("funding_by_sector", "Sectors: {x}"),
                   ("funding_by_agency", "Agency budgets: {x}")]:
        if not both(k) or not isinstance(fo[k], dict) or not isinstance(fn[k], dict):
            continue
        def _num_d(dct):
            out_d = {}
            for kk, vv in dct.items():
                try:
                    out_d[kk] = None if vv is None else float(vv)
                except (TypeError, ValueError):
                    continue
            return out_d
        a, b = _num_d(fo[k]), _num_d(fn[k])
        if k == "funding_by_source" and set(a) == set(b) and len(a) == 1:
            continue   # a single source says the same as the pre-arranged line
        bits = []
        for x in sorted(set(a) | set(b), key=lambda s: (-float(b.get(s) or a.get(s) or 0), str(s))):
            va, vb = a.get(x), b.get(x)
            if va is not None and vb is not None:
                if abs(float(va) - float(vb)) > 0.5:
                    bits.append(f"{esc(x)} {_m(va)} → {_m(vb)}")
            elif va is None and vb is not None:
                bits.append(w("{x} added ({v})").format(x=esc(x), v=_m(vb)))
            elif va is not None:
                bits.append(w("{x} dropped (was {v})").format(x=esc(x), v=_m(va)))
        if bits:
            out.append(w(lab).format(x="; ".join(bits)))
    # agencies (the list, else the budget dict's keys)
    ao = fo.get("implementing_agencies") if _has(fo.get("implementing_agencies")) else list((fo.get("funding_by_agency") or {}).keys())
    an = fn.get("implementing_agencies") if _has(fn.get("implementing_agencies")) else list((fn.get("funding_by_agency") or {}).keys())
    if ao and an and set(ao) != set(an):
        add, rem = sorted(set(an) - set(ao)), sorted(set(ao) - set(an))
        out.append(w("Agencies: {x}").format(x="; ".join(
            ([w("added {x}").format(x=", ".join(esc(x) for x in add))] if add else [])
            + ([w("removed {x}").format(x=", ".join(esc(x) for x in rem))] if rem else []))))
    if both("target_people") and fo["target_people"] != fn["target_people"]:
        try:
            out.append(w("Target people {a} → {b}").format(a=f"{int(fo['target_people']):,}",
                                                            b=f"{int(fn['target_people']):,}"))
        except (TypeError, ValueError):
            pass
    if both("data_sources") and set(map(str, fo["data_sources"])) != set(map(str, fn["data_sources"])):
        add = sorted(set(map(str, fn["data_sources"])) - set(map(str, fo["data_sources"])))
        rem = sorted(set(map(str, fo["data_sources"])) - set(map(str, fn["data_sources"])))
        out.append(w("Data sources: {x}").format(x="; ".join(
            ([w("added {x}").format(x=", ".join(esc(x) for x in add))] if add else [])
            + ([w("removed {x}").format(x=", ".join(esc(x) for x in rem))] if rem else []))))
    if fo.get("all_in") is not None and fn.get("all_in") is not None and fo["all_in"] != fn["all_in"]:
        out.append(w("Funding model: split by window → all-in" if fn["all_in"] else "Funding model: all-in → split by window"))
    return out


# the version record's own fields, as a curator's note names them, in words (a note is shown as
# written otherwise; the fix at the source is to reword the note)
_NOTE_FIELDS = {"valid_from": "the start date", "valid_until": "the end date",
                "valid_until_source": "the end date's source",
                "development_since": "the development start date", "kb_status": "the version status",
                "kb_framework": "the framework's page", "endorsed_by": "the endorser",
                "prearranged_usd_doc": "the pre-arranged amount in the document",
                "doc_title": "the document title", "doc_url": "the document link",
                "analysis_ref": "the analysis link", "window_rollup": "how the windows' money adds up",
                "activations_per_year": "the activations a year"}
_NOTE_FIELD_RX = re.compile(r"\b(" + "|".join(map(re.escape, _NOTE_FIELDS)) + r")\b")


def _plain_note(note):
    """A version note for a public page: the record's field names in words."""
    return _NOTE_FIELD_RX.sub(lambda m: _NOTE_FIELDS[m.group(1)], str(note))


def _changes_block(fvm, vpage, c, h):
    """'What changed between versions': newest pair first."""
    import html as _h
    v = fvm[(fvm["country_iso3"] == c) & (fvm["hazard"] == h)].copy()
    if len(v) < 2:
        return (f"<div class='blk'><h2>{T('What changed between versions')}</h2>"
                f"<p class='empty'>{T('Only one version is registered — nothing to compare yet.')}</p></div>")
    v["_vf"] = version_start(v)
    v = v.sort_values(["_vf", "version"])
    pg = {(r.kb_framework, str(r.version)): (r.frontmatter, r.triggers) for r in vpage.itertuples()}
    items = ""
    rows = list(v.itertuples())
    for old, new in reversed(list(zip(rows[:-1], rows[1:]))):
        fo, to = pg.get((old.kb_framework, str(old.version)), (None, None))
        fn, tn = pg.get((new.kb_framework, str(new.version)), (None, None))
        # each sentence in every language (the recorded values inside them as they are)
        diff = ({l: _version_diff(fo, fn, to, tn, (lambda x: x) if l == "en" else (lambda x, l=l: i18n.tr(l, x)))
                 for l in ("en",) + i18n.LANGS} if (fo or to) and (fn or tn) else {})
        body = ("<ul>" + "".join("<li>" + "".join(f'<span class="lv lv-{l}">{diff[l][i]}</span>' for l in diff)
                                 + "</li>" for i in range(len(diff["en"]))) + "</ul>" if diff and diff["en"]
                else f"<p class='empty' style='padding:2px 0'>{T('no structured change recorded')}</p>")
        note = (f"<p class='vnote'><b>{T('Note:')}</b> {_h.escape(_plain_note(new.note))}</p>"
                if isinstance(new.note, str) and new.note.strip() else "")
        items += (f"<div class='vchg'><h4>{_h.escape(str(old.version))} → {_h.escape(str(new.version))}"
                  f"</h4>{body}{note}</div>")
    return (f"<div class='blk'><h2>{T('What changed between versions')}</h2>"
            "<p class='meta'>" + TB("Derived from the recorded framework metadata (scope, trigger windows, "
            "indicators, monitoring months, budgets) — only fields recorded for both versions are "
            "compared. Narrative notes on each change can be added to the version record and will "
            "appear under the pair.") + "</p>" + items + "</div>")


def _norm(s):
    import re
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _loose(a, b):
    """Loose window-name match: lower-case alphanumerics, substring either way."""
    na, nb = _norm(a), _norm(b)
    return bool(na) and bool(nb) and (na in nb or nb in na)


def _cerf_page(code, cy):
    y = cy.get(code)
    return (f"https://cerf.un.org/what-we-do/allocation/{int(y)}/summary/{code}"
            if isinstance(code, str) and code and y is not None and pd.notna(y) else None)


def _event_links(d, c, h, kb_fw, umap, ed, window_name, event_type):
    """The funding rows and recorded pages of one real activation: its announcement
    (aa.window_activation url), CERF allocations [(code, page)] and other recorded pages
    (aa.actual_activation, same month and window)."""
    wn = window_name if isinstance(window_name, str) else ""
    fund = d["activation"]
    f = fund[(fund["country_iso3"] == c) & (fund["hazard"] == h)
             & (fund["event_date"].astype(str) == ed) & (fund["event_type"] == event_type)
             & (fund["window_name"].fillna("") == wn)]
    ann = umap.get((c, h, ed, wn or window_name))
    au = d["actual_url"][d["actual_url"]["kb_framework"] == kb_fw] if kb_fw else d["actual_url"].iloc[0:0]
    other = [u for u in au.loc[[str(x)[:7] == ed[:7] and (_loose(w, wn) or not wn)
                                for x, w in zip(au["event_date"], au["window_name"])], "url"]
             if isinstance(u, str) and u and u != ann]
    cy = dict(zip(d["cerf_year"]["application_code"], d["cerf_year"]["year"]))
    cerf = [(x.allocation_code, _cerf_page(x.allocation_code, cy)) for x in f.itertuples()
            if x.fund_code == "cerf" and isinstance(x.allocation_code, str)]
    return dict(fund=f, ann=ann if isinstance(ann, str) and ann else None, other=other, cerf=cerf)


def _event_href(lk):
    """The most relevant page for one real activation, as the activation tables link it:
    the announcement, else the CERF allocation page, else another recorded page.
    (url, what it is) — (None, None) when nothing is recorded."""
    if lk["ann"]:
        return lk["ann"], "the activation announcement"
    u = next((u for _c, u in lk["cerf"] if u), None)
    if u:
        return u, "the CERF allocation page"
    if lk["other"]:
        return lk["other"][0], "the recorded activation page"
    return None, None


# ---------------- simulated activations (the backtest)
# Dated columns added 2026-10-02 (schema.ADDITIVE_MIGRATIONS): the day — for storms the
# hour — the trigger would have activated. Read when present, else event_year.
SIM_DATED = ("event_date", "event_time", "time_precision", "source_note")


def read_simulated(e):
    """aa.simulated_activation with the dated columns, NULL on a DB that does not have them
    yet (a missing column must never turn into an empty backtest)."""
    have = set(pd.read_sql(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'aa' AND table_name = 'simulated_activation'", e)["column_name"])
    fmt = {"event_date": "event_date::text",
           "event_time": "to_char(event_time AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI')",
           "time_precision": "time_precision::text", "source_note": "source_note::text"}
    extra = ", ".join(f"{fmt[c] if c in have else 'NULL::text'} AS {c}" for c in SIM_DATED)
    return pd.read_sql(
        f"""SELECT country_iso3, hazard, version::text AS version, window_name, event_year,
                   event_label, {extra}
            FROM aa.simulated_activation ORDER BY event_year DESC""", e)


def _sim_val(r, k):
    v = r.get(k) if isinstance(r, dict) else getattr(r, k, None)
    return v if isinstance(v, str) and v.strip() and v not in ("NaT", "None", "nan") else None


def sim_year(r):
    """The year a simulated activation counts in: of event_time, else event_date, else event_year."""
    for k in ("event_time", "event_date"):
        v = _sim_val(r, k)
        if v and v[:4].isdigit():
            return int(v[:4])
    return int(r["event_year"] if isinstance(r, dict) else r.event_year)


def sim_when(r):
    """When a simulated activation would have happened, as precisely as recorded: '2019',
    '2019-08', '2019-08-12' or '2019-08-12 06:00 UTC' (time_precision, else inferred)."""
    t, dt = _sim_val(r, "event_time"), _sim_val(r, "event_date")
    p = (_sim_val(r, "time_precision") or ("hour" if t else "day" if dt else "year")).lower()
    base = t or dt
    if base and p == "hour" and t:
        return t[:16] + " UTC"
    if base and p in ("day", "hour"):
        return base[:10]
    if base and p == "month":
        return base[:7]
    return str(sim_year(r))


def _sim_tip(window, r):
    """'<window>: would have activated in 2019 (simulation)', in every language (ATTRC)."""
    when = sim_when(r)
    return ATTRC("title", lambda w: f"{window}: " + w(
        "would have activated on {0} (simulation)" if len(when) > 7
        else "would have activated in {0} (simulation)").replace("{0}", when))


def sim_before_start(ss, valid_from):
    """(rows kept, n rows dropped, start year) for one version's simulated rows. A version's
    backtest is fixed before it is endorsed and real activations can only come after, so only
    rows dated strictly before the year the version took effect (valid_from) count as
    simulation; the years from then on show real activations only. Kept rows get `sim_year`."""
    s = valid_from if isinstance(valid_from, pd.Series) else pd.Series([valid_from])
    yrs = pd.to_datetime(s.astype(str), errors="coerce").dt.year.dropna()
    vf_y = int(yrs.max()) if len(yrs) else None
    if not len(ss):
        return ss.assign(sim_year=pd.Series(dtype="int64")), 0, vf_y
    ss = ss.assign(sim_year=[sim_year(r) for r in ss.itertuples()])
    if vf_y is None:
        return ss, 0, None
    keep = ss["sim_year"] < vf_y
    return ss[keep], int((~keep).sum()), vf_y


def version_start(df):
    """Each version's start, for ordering: valid_from, else the date its label gives ('2022' ->
    2022-01-01), so an undated version sits where its label says instead of first or last."""
    lab = df["version"].astype(str).str.extract(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?")
    lab = pd.to_datetime(lab[0] + "-" + lab[1].fillna("01") + "-" + lab[2].fillna("01"), errors="coerce")
    return pd.to_datetime(df["valid_from"].astype(str), errors="coerce").fillna(lab)


def backtest_span(ss, wv, vf_y):
    """(first, last, n or None) years a version's backtest analysed. The windows' analysis_start ..
    analysis_end when recorded, the end capped at the year before the version took effect
    (from then on only real activations count); else N analysed years (analysis_years)
    ending at the later of the last simulated year and the year before the version took
    effect; else the simulated years themselves. Always spans every simulated year kept.
    `ss` is sim_before_start's output (has sim_year); `wv` the version's d["windows"] rows."""
    def num(col):
        return (pd.to_numeric(wv[col], errors="coerce").dropna()
                if len(wv) and col in wv.columns else pd.Series(dtype=float))
    a0, a1, ny = num("analysis_start"), num("analysis_end"), num("analysis_years")
    smin = int(ss["sim_year"].min()) if len(ss) else None
    smax = int(ss["sim_year"].max()) if len(ss) else None
    if len(a1):
        y1 = int(a1.max()) if not vf_y else min(int(a1.max()), vf_y - 1)
    else:
        y1 = int(max(smax or 0, (vf_y - 1) if vf_y else 0))
    y0 = (int(a0.min()) if len(a0) else int(y1 - ny.max() + 1) if len(ny)
          else smin if smin is not None else y1)
    if smin is not None:
        y0, y1 = min(y0, smin), max(y1, smax)
    recorded = len(a0) or len(a1) or len(ny)   # n only when the analysis says how long it ran
    return y0, y1, (y1 - y0 + 1) if recorded else None


def sim_after_note(n, vf_y):
    """The small note under a backtest when rows dated after the version's start were left out."""
    return (f"{n} simulated row{'' if n == 1 else 's'} dated after the version's start ({vf_y} or later) "
            f"{'is' if n == 1 else 'are'} not shown: a version's backtest is fixed before it is endorsed, "
            f"and from then on only real activations count.") if n else ""


def _register_after_note(n, vf_y):
    """sim_after_note's sentence, registered in every language (looked up by tr / tr8)."""
    tmpl = ("{n} simulated row dated after the version's start ({y} or later) is not shown: a version's "
            "backtest is fixed before it is endorsed, and from then on only real activations count."
            if n == 1 else
            "{n} simulated rows dated after the version's start ({y} or later) are not shown: a version's "
            "backtest is fixed before it is endorsed, and from then on only real activations count.")
    def same(x):
        return {l: str(x) for l in ("en",) + i18n.LANGS}
    return i18n.add(sim_after_note(n, vf_y), tmpl, n=same(n), y=same(vf_y))


def _activation_blocks(d, c, h, kb_fw, version, umap):
    """(Historical activations grid, Actual activations table) for one framework."""
    import html as _h
    esc = lambda s: _h.escape(str(s))   # noqa: E731
    col = PAL[HAZARDS.index(h)] if h in HAZARDS else "#64748b"
    sim = d["sim"][(d["sim"]["country_iso3"] == c) & (d["sim"]["hazard"] == h)].copy()
    sim["version"] = sim["version"].astype(str)
    fvm = d["fv_meta"][(d["fv_meta"]["country_iso3"] == c) & (d["fv_meta"]["hazard"] == h)]
    order = list(fvm.assign(_vf=pd.to_datetime(fvm["valid_from"], errors="coerce"))
                 .sort_values("_vf")["version"].astype(str))
    # the version whose backtest is shown: the current one, else the latest with a backtest
    _vm = lambda a, b: a == b or a.startswith(b) or b.startswith(a)   # noqa: E731 — 'YYYY' label vs dated page
    shown = next((sv for sv in set(sim["version"]) if version is not None and _vm(sv, str(version))), None)
    if shown is None and len(sim):
        vs = [v for v in order if v in set(sim["version"])] or sorted(set(sim["version"]))
        shown = vs[-1]
    ss = sim[sim["version"] == shown] if shown else sim.iloc[0:0]
    # only rows dated before the year the version took effect are simulation; from then on
    # the version is in use and only real activations count (sim_before_start)
    vf = fvm.loc[fvm["version"].astype(str) == str(shown), "valid_from"] if shown else fvm["valid_from"].iloc[0:0]
    ss, n_after, vf_y = sim_before_start(ss, vf)
    vf_txt = str(vf.dropna().astype(str).max())[:10] if len(vf.dropna()) else str(vf_y)
    win = d["windows"]
    wv = win[(win["country_iso3"] == c) & (win["hazard"] == h) & (win["version"].astype(str) == str(shown))]
    wins = sorted(set(ss["window_name"].dropna()) | set(wv["window_name"].dropna()))
    # backtest range: N analysed years ending at the later of the last simulated year and
    # the year before the version took effect
    n_years = None
    rows = {}   # (year, label) -> {'cell': [...], window: [...]}
    sim_years = set()   # years the historical simulation covers; others are greyed out
    use_years = set()   # from the version's start year: real activations only
    if len(ss) or n_after:
        y0, y1, n_years = backtest_span(ss, wv, vf_y)
        labelled = ss[ss["event_label"].fillna("").astype(str) != ""]
        sim_years = set(range(y0, y1 + 1))
        if vf_y:
            use_years = set(range(vf_y, max(vf_y, pd.Timestamp.now().year) + 1))
        for y in sorted(sim_years | use_years):
            if not (labelled["sim_year"] == y).any():
                rows[(y, "")] = {}
        for r in ss.itertuples():
            key = (int(r.sim_year), str(r.event_label) if isinstance(r.event_label, str) else "")
            rows.setdefault(key, {}).setdefault(r.window_name, []).append(
                f"<span class='dot sim' style='background:{col}' {_sim_tip(r.window_name, r)}></span>")
    # real activations, one entry per event with its funding rows
    act = d["act_all"][(d["act_all"]["country_iso3"] == c) & (d["act_all"]["hazard"] == h)].copy()
    wa = d["wact"][(d["wact"]["country_iso3"] == c) & (d["wact"]["hazard"] == h)]
    full = {(str(r.event_date), r.window_name): r.full_activation for r in wa.itertuples()}
    events = []
    for r in act.sort_values("event_date", ascending=False).itertuples():
        ed, wn = str(r.event_date), r.window_name
        wn = wn if isinstance(wn, str) else ""
        lk = _event_links(d, c, h, kb_fw, umap, ed, r.window_name, r.event_type)
        events.append(dict(date=ed, win=wn, typ=str(r.event_type),
                           label=r.event_label if isinstance(r.event_label, str) else "",
                           version=str(r.version) if pd.notna(r.version) else "", fund=lk["fund"],
                           ann=lk["ann"], other=lk["other"], cerf=lk["cerf"],
                           partial=full.get((ed, wn)) is False))
    for ev in events:
        amt = "; ".join(f"{fund_label(x.fund_code)} {_m(x.amount_usd)}" for x in ev["fund"].itertuples()
                        if pd.notna(x.amount_usd))
        href, goes = _event_href(ev)
        vv = "" if ev["version"] is None or str(ev["version"]) in ("nan", "None", "NaT", "<NA>") else str(ev["version"])
        # no version = an ad hoc allocation: neither this version nor an earlier one
        ref = shown if shown is not None else (str(version) if version is not None else None)
        same = (not vv) or (ref is not None and _vm(vv, ref))   # no backtest: compare with the current version
        def tip(w, ev=ev, amt=amt, vv=vv, same=same, href=href, goes=goes):
            return (f"{ev['date']} · {ev['win'] or w(code_words(EVENT_TYPE_LABEL, ev['typ'], 'event type') or 'activation')} · {amt or w('amount not recorded')}"
                    + (" · " + w("non-framework allocation (no framework version)") if not vv else ""
                       if same else " · " + w("under version {0}").replace("{0}", vv))
                    + (" · " + w("partial activation") if ev["partial"] else "")
                    + (" · " + w("opens {0}").replace("{0}", w(goes)) if href else ""))
        mk = (f"<span class='dot {'real' if same else 'old'}'></span>")
        mk = (f"<a href='{esc(href)}' target='_blank' rel='noopener' {ATTRC('title', tip)}>{mk}</a>"
              if href else f"<span {ATTRC('title', tip)}>{mk}</span>")
        y = int(ev["date"][:4]) if ev["date"][:4].isdigit() else None
        if y is None:
            continue
        keys = [k for k in rows if k[0] == y]
        key = next((k for k in keys if ev["label"] and _loose(k[1], ev["label"])), None) \
            or next((k for k in keys if k[1] == ""), None)
        if key is None:
            key = (y, ev["label"] or ("activation" if keys else ""))   # 'activation': translated where shown
            rows.setdefault(key, {})
        wmatch = next((w for w in wins if _loose(w, ev["win"])), None)
        rows[key].setdefault(wmatch or "__cell", []).append(mk)
    # ---- the grid
    if not rows:
        hist = f"<p class='empty'>{T('No backtest and no activation recorded for this framework.')}</p>"
    else:
        head = "".join(f"<th>{esc(w)}</th>" for w in wins)
        use_tip = ("version {v} took effect {d}: from {y} on, real activations only "
                   "(its simulation covers the years before)") if use_years else ""

        def _use(y):   # the 'in use' tooltip of a year, in every language
            return ATTRC("title", lambda w: f"{y}: " + w(use_tip).format(v=shown, d=vf_txt, y=vf_y))
        body = ""
        for (y, lab) in sorted(rows, key=lambda k: (-k[0], k[1])):
            cells = rows[(y, lab)]
            inner = lambda w: "".join(cells.get(w, []))   # noqa: E731
            if y in use_years:
                tds = "".join(f"<td class='use' {_use(y)}>{inner(w)}</td>" for w in wins)
            elif y in sim_years or not sim_years:
                tds = "".join(f"<td>{inner(w)}</td>" for w in wins)
            else:
                tds = "".join(f"<td class='na' {ATTR('title', '{y} is not covered by the historical simulation', y=y)}>{inner(w)}</td>"
                              for w in wins)
            lab_html = T(lab) if lab == "activation" else esc(lab)
            body += (f"<tr><td class='yr'>{y}{(' <span class=' + chr(39) + 'muted' + chr(39) + '>' + lab_html + '</span>') if lab else ''}"
                     + (f" <span class='usetag' {ATTRC('title', lambda w: w(use_tip).format(v=shown, d=vf_txt, y=vf_y))}>{T('in use')}</span>"
                        if y in use_years and not lab else "")
                     + f"{' ' + ''.join(cells.get('__cell', [])) if cells.get('__cell') else ''}</td>"
                     + tds + "</tr>")
        def vnote(w):
            if shown is None:
                return w("No backtest recorded for this framework — real activations only.") + " "
            return (w("Backtest of version {v}").format(v=f"<code>{esc(shown)}</code>")
                    + ("" if str(shown) == str(version) else " " + w("(the current version has no recorded backtest)"))
                    + (", " + w("{n} years analysed").format(n=int(n_years)) if n_years and pd.notna(n_years) else "")
                    + ("; " + w("the version took effect {d}, so from {y} on the rows show real activations only")
                       .format(d=esc(vf_txt), y=vf_y) if use_years else "") + ". "
                    + (esc(w(sim_after_note(n_after, vf_y))) + " " if n_after else ""))
        if n_after:   # the note, registered in every language (it is looked up above)
            _register_after_note(n_after, vf_y)
        hist = (f"<p class='meta'>{TBC(vnote)}"
                + TB("One row per year, newest first; a real activation whose window does not match a "
                     "column sits in the year cell. Markers link to the announcement or the CERF allocation.") + "</p>"
                f"<div class='xscroll'><table class='data hist'><thead><tr><th>{T('year')}</th>{head}</tr></thead><tbody>{body}</tbody></table></div>"
                f"<p class='legend'><span class='dot sim' style='background:{col}'></span> {T('would have activated (simulation)')} · "
                f"<span class='dot real'></span> {T('activated, money released')} · "
                f"<span class='dot old'></span> "
                + T("activated under an earlier version" if str(shown) == str(version) else "activated under a different version (hover for which)")
                + (f" · <span class='sw use'></span> {T('version in use: real activations only')}" if use_years else "")
                + "</p>")
    # ---- actual activations table
    if not events:
        actual = f"<p class='empty'>{T('No activation recorded.')}</p>"
    else:
        tr = ""
        for ev in events:
            fl = "<br>".join(
                f"{esc(fund_label(x.fund_code))}: {'' if pd.isna(x.amount_usd) else '$' + format(x.amount_usd, ',.0f')}"
                for x in ev["fund"].itertuples()) or f"<span class='muted'>{T('not recorded')}</span>"
            links = [f"<a href='{esc(u)}' target='_blank' rel='noopener'>CERF {esc(code)} ↗</a>"
                     for code, u in ev["cerf"] if u]
            links += [f"<span class='muted'>{esc(code)}</span>" for code, u in ev["cerf"] if not u]
            if ev["ann"]:
                links.append(f"<a href='{esc(ev['ann'])}' target='_blank' rel='noopener'>{T('announcement ↗')}</a>")
            links += [f"<a href='{esc(u)}' target='_blank' rel='noopener'>{T('other ↗')}</a>" for u in ev["other"]]
            vtag = ("" if (not ev["version"] or str(ev["version"]) == str(version))
                    else f" <span class='doctag' {ATTR('title', 'This activation happened under version {v}, an earlier version of the framework than the current one ({c}); its triggers and budget may differ.', v=ev['version'], c=version)}>{T('earlier version')}</span>")
            tr += (f"<tr><td>{esc(ev['date'])}</td><td>{esc(ev['version'])}{vtag}</td>"
                   f"<td>{esc(ev['win'])}{(' · ' + esc(ev['label'])) if ev['label'] else ''}"
                   f"{'' if ev['typ'] == 'framework_aa' or not code_words(EVENT_TYPE_LABEL, ev['typ'], 'event type') else ' <span class=' + chr(39) + 'muted' + chr(39) + '>(' + T(code_words(EVENT_TYPE_LABEL, ev['typ'], 'event type')) + ')</span>'}"
                   f"{' <span class=' + chr(39) + 'warn-tag' + chr(39) + '>' + T('partial') + '</span>' if ev['partial'] else ''}</td>"
                   f"<td>{fl}</td><td>{' · '.join(links)}</td></tr>")
        actual = ("<div class='xscroll'><table class='data acts'><colgroup><col style='width:10%'><col style='width:17%'>"
                  "<col style='width:28%'><col style='width:17%'><col style='width:28%'></colgroup>"
                  "<thead><tr>" + "".join(f"<th>{T(x)}</th>" for x in ("date", "version", "window", "funding", "links"))
                  + f"</tr></thead><tbody>{tr}</tbody></table></div>")
    return hist, actual


def _gh_url(ref):
    """'repo@branch:path' -> https://github.com/OCHA-DAP/<repo>/tree/<branch>/<path>."""
    import re
    m = re.match(r"^\s*([\w.\-/]+)@([^:]+):(.*)$", str(ref or ""))
    if not m:
        return None
    repo = m.group(1).split("/")[-1]
    return f"https://github.com/OCHA-DAP/{repo}/tree/{m.group(2).strip()}/{m.group(3).strip().lstrip('/')}"


def _validation_block(fvm, c, h, version):
    """Trigger validation & technical work: analysis_ref, framework doc, Drive folder."""
    import html as _h
    esc = lambda s: _h.escape(str(s))   # noqa: E731
    v = fvm[(fvm["country_iso3"] == c) & (fvm["hazard"] == h)].copy()
    v["_vf"] = pd.to_datetime(v["valid_from"], errors="coerce")
    v = v.sort_values("_vf")
    items = []
    cur = v[v["version"].astype(str) == str(version)]
    def _pick(col):
        x = cur[cur[col].notna() & (cur[col].astype(str).str.strip() != "")]
        if len(x):
            return x.iloc[-1], True
        x = v[v[col].notna() & (v[col].astype(str).str.strip() != "")]
        return (x.iloc[-1], False) if len(x) else (None, False)
    r, is_cur = _pick("analysis_ref")
    if r is not None:
        for ref in str(r["analysis_ref"]).split(";"):
            u = _gh_url(ref)
            lab = f"{T('Trigger analysis code')} — <code>{esc(ref.strip())}</code>"
            items.append((f"<a href='{esc(u)}' target='_blank' rel='noopener'>{lab} ↗</a>" if u else lab)
                         + ("" if is_cur else f" <span class='muted'>{TF('(version {v})', v=r['version'])}</span>"))
    r, is_cur = _pick("doc_url")
    if r is not None:
        t = (esc(r["doc_title"]) if isinstance(r["doc_title"], str) and r["doc_title"]
             else T("Framework document"))   # a document's own title stays as written
        items.append(f"<a href='{esc(r['doc_url'])}' target='_blank' rel='noopener'>{t} ↗</a>"
                     + ("" if is_cur else f" <span class='muted'>{TF('(version {v})', v=r['version'])}</span>"))
    if TRIGGER_VALIDATION_URL:
        items.append(f"<a href='{esc(TRIGGER_VALIDATION_URL)}' target='_blank' rel='noopener'>"
                     f"{T('Trigger validation folder (Drive) ↗')}</a>")
    body = ("<ul class='doclist'>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>" if items
            else f"<p class='empty'>{T('Technical documentation not yet linked.')}</p>")
    return (f"<h3 class='sub'>{T('Trigger validation & technical work')}</h3>" + body
            + f"<p class='meta'>{T('The full trigger validation will be published on this page in future.')}</p>")


def _status_words(st):
    """A framework's status (the tracking sheets' code, or the lifecycle when there is none) in
    words; None for one with no words (the badge is then left out, never the code)."""
    from landing import SHEET_STATUS_LABEL
    words = {**LIFE_LABEL, "retired": "retired", "pipeline": "no framework version yet",
             "no framework": "no framework", "no status": "no status", **SHEET_STATUS_LABEL}
    return code_words(words, st, "framework status")


def _role_words(x):
    """A partner role: a code in words, the document's own words as written."""
    x = str(x)
    is_code = x in PARTNER_ROLE_LABEL or re.fullmatch(r"[a-z]+(_[a-z]+)+", x)
    return code_words(PARTNER_ROLE_LABEL, x, "partner role") if is_code else x


def _source_words(src):
    """Where a version record came from, in words ('' for a source with none)."""
    src = current_source(src)
    if isinstance(src, str) and re.fullmatch(r"aa-team-\d{4}-\d{2}-\d{2}", src):
        src = "aa-team"
    w = code_words(VERSION_SOURCE_LABEL, src, "version source")
    return T(w) if w else ""


def _report_list(r):
    """'Anticipation Hub (2024, 2025), CPC (2025)': the reports a framework counts toward, in
    words (a report with none is left out)."""
    yrs = {}
    for x in r.itertuples():
        w = code_words(REPORT_CHANNEL_LABEL, x.channel, "report channel")
        if w:
            yrs.setdefault(w, set()).add(str(x.report_year))
    return ", ".join(f"{T(w)} ({', '.join(sorted(ys))})" for w, ys in sorted(yrs.items()))


def _no_framework_body(d, fw, c, h, umap, docs):
    """(kind, body) of the page of a pair with NO framework version (owner, 2026-10-30: "the
    'framework' pages for non-framework allocations are a bit weird … the page shouldn't just be
    the same format as a framework page"). No model, monitoring window, versions, backtest or
    pre-arranged chart: those belong to a framework. kind: 'allocations' (it received money
    without a framework: the allocations are listed), 'tech' (OCHA technical support only), or
    'none' (a pair the records hold with neither, Madagascar plague)."""
    import html as _h
    esc = lambda x: _h.escape(str(x))   # noqa: E731
    a = d["act_all"][(d["act_all"]["country_iso3"] == c) & (d["act_all"]["hazard"] == h)]
    tech = bool(fw.get("technical_support")) if pd.notna(fw.get("technical_support")) else False
    kind = "allocations" if len(a) else "tech" if tech else "none"
    name = T(i18n.add(f"{fw['country_name']} — {hazard_word(h)}", "{country} — {hazard}",
                      country=i18n.country(c, fw["country_name"]), hazard=hazard_word(h)))
    badge = {"allocations": "non-framework allocations", "tech": "technical support",
             "none": "no framework version recorded"}[kind]
    st = _status_words(fw.get("status")) if _has(fw.get("status")) else ""
    lead = {
        "allocations": T("Anticipatory-action money allocated for this hazard without a framework: no pre-agreed "
                         "trigger, plan or pre-arranged envelope stands behind it, so this page has no model, "
                         "monitoring window or versions. These allocations count on the Map and the Financing page "
                         "under the non-framework allocations layer."),
        "tech": T("OCHA supports a framework here technically, without a funding commitment from CERF or the "
                  "Country and Regional Funds. No framework version is recorded yet, and no money has been "
                  "allocated for this hazard."),
        "none": T("No framework version and no allocation are recorded for this hazard."),
    }[kind]
    extra = []
    if kind == "allocations" and tech:
        extra.append(T("OCHA also supports a framework here technically, without a funding commitment."))
    if kind != "allocations" and st:
        extra.append(TC(lambda w: w("Status in the tracking sheets: {s}.").format(s=w(st))))
    # the allocations, newest first: what, the money by fund, people targeted, links
    rows, total, years = "", 0.0, set()
    for r in a.sort_values("event_date", ascending=False).itertuples():
        ed = str(r.event_date)
        lk = _event_links(d, c, h, None, umap, ed, r.window_name, r.event_type)
        fl = "<br>".join(f"{esc(fund_label(x.fund_code))}: {'' if pd.isna(x.amount_usd) else '$' + format(x.amount_usd, ',.0f')}"
                         for x in lk["fund"].itertuples()) or f"<span class='muted'>{T('not recorded')}</span>"
        total += float(lk["fund"]["amount_usd"].fillna(0).sum())
        if ed[:4].isdigit():
            years.add(int(ed[:4]))
        links = [f"<a href='{esc(u)}' target='_blank' rel='noopener'>CERF {esc(code)} ↗</a>" for code, u in lk["cerf"] if u]
        links += [f"<span class='muted'>{esc(code)}</span>" for code, u in lk["cerf"] if not u]
        if lk["ann"]:
            links.append(f"<a href='{esc(lk['ann'])}' target='_blank' rel='noopener'>{T('announcement ↗')}</a>")
        links += [f"<a href='{esc(u)}' target='_blank' rel='noopener'>{T('other ↗')}</a>" for u in lk["other"]]
        what = code_words(EVENT_TYPE_LABEL, r.event_type, "event type") or "non-framework allocation"
        lab = r.event_label if isinstance(r.event_label, str) and r.event_label else ""
        ppl = getattr(r, "people_targeted", None)
        if ppl is None or pd.isna(ppl):   # the allocation rows' figure, as the Map counts it
            fp = lk["fund"]["people_targeted"].dropna() if "people_targeted" in lk["fund"] else []
            ppl = float(fp.sum()) if len(fp) else None
        rows += (f"<tr><td>{esc(ed)}</td><td>{esc(lab) + ' ' if lab else ''}<span class='muted'>({T(what)})</span></td>"
                 f"<td>{fl}</td><td class='num'>{f'{int(ppl):,}' if ppl is not None and pd.notna(ppl) else '—'}</td>"
                 f"<td>{' · '.join(links)}</td></tr>")
    span = (f"{min(years)}–{max(years)}" if len(years) > 1 else str(min(years))) if years else "—"
    body = (f"<div class='card'><b>{name}</b> · <span class='badge b-new'>{T(badge)}</span>"
            f"<p style='margin:8px 0 0'>{lead}{''.join(' ' + x for x in extra)}</p></div>")
    if kind == "allocations":
        n = len(a)
        body += (f"<div class='tiles'>"
                 f"<div class='tile'><div class='v'>{n}</div><div class='l'>{T('allocation' if n == 1 else 'allocations')}</div></div>"
                 f"<div class='tile'><div class='v'>{_m(total) if total else '—'}</div><div class='l'>{T('allocated in total')}</div></div>"
                 f"<div class='tile'><div class='v'>{span}</div><div class='l'>{T('year' if len(years) == 1 else 'years')}</div></div></div>"
                 f"<div class='blk'><h2>{T('Allocations')}</h2>"
                 "<div class='xscroll'><table class='data acts'><thead><tr>"
                 + "".join(f"<th>{T(x)}</th>" for x in ("date", "allocation", "funding", "people targeted", "links"))
                 + f"</tr></thead><tbody>{rows}</tbody></table></div></div>")
    fd = _fw_docs(docs, c, h)
    if len(fd):
        body += (f"<div class='blk'><h2>{T('Documents')}</h2>"
                 f"<ul class='doclist'>{''.join(_doc_li(x) for x in fd.itertuples())}</ul></div>")
    body += (f"<p class='meta'><a href='index.html#{esc(c)}'>{T('See it on the Map →')}</a>"
             + (f" · <a href='dash-funding.html'>{T('Financing →')}</a>" if kind == "allocations" else "")
             + f"</p><style>{DASH_CSS}</style>")
    return kind, body


def build_framework_pages(page, tbl, d, e=None):
    cur, ver, act = d["current"], d["versions"], d["activation"]
    # the pre-arranged series of the Financing page (funding_series): the current year is
    # pre-arranged now (prearranged_now, two activations a year counted twice), past years as
    # reported — the sheets' June figure showed Cuba's 2026 as $4M against the map's $9M (2026-10-28).
    # A country with two live frameworks gets its Country and Regional Fund mirror allocations on a
    # 'multi' row, which no framework page shows (none today; the Financing page counts them by country)
    pre, cov = funding_series(d)[0], d["covered"]
    import figure_check
    rep, cal = d["report"], d["calendar"]
    split, env, win = d["split_all"], d["env_all"], d["windows"]
    docs, pt, sg = d["learning"], d["partners"], d["subgrant_aa"]
    urls = d["act_url"]
    umap = {(r.country_iso3, r.hazard, str(r.event_date), r.window_name): r.url
            for r in urls.itertuples()}
    try:
        trig = _kb_trigger_info(e, parts=True) if e is not None else {}
    except Exception as exc:
        print(f"  framework pages: KB trigger info unavailable ({exc.__class__.__name__})")
        trig = {}
    links = []
    for _i, fw in cur.sort_values("country_name").iterrows():
        c, h = fw["country_iso3"], fw["hazard"]
        slug = f"fw-{c.lower()}-{h}"
        # a pair with no framework version (Uganda flood, Zimbabwe drought…) gets a page of its own
        # kind (_no_framework_body): its allocations, or technical support, never a framework shell
        no_fw = ver[(ver["country_iso3"] == c) & (ver["hazard"] == h)].empty
        status = ("no framework" if no_fw else
                  next((x for x in (fw.get("lifecycle"), fw.get("status")) if _has(x)), "no status"))
        cur_v = fw["current_version"] if _has(fw.get("current_version")) else "—"
        links.append((fw["country_name"], h, status, slug, c))
        if no_fw:   # no framework: a page of its own kind, not a framework page's empty shell
            kind, body = _no_framework_body(d, fw, c, h, umap, docs)
            tmpl = "{country} {hazard} — " + {"allocations": "non-framework allocations", "tech": "technical support",
                                              "none": "no framework version recorded"}[kind]
            page(f"{slug}.html", i18n.add(tmpl.format(country=fw["country_name"], hazard=hazard_word(h)), tmpl,
                                          country=i18n.country(c, fw["country_name"]), hazard=hazard_word(h)), body)
            continue
        version = (fw["latest_version"] if pd.notna(fw.get("latest_version"))
                   else fw["current_version"] if pd.notna(fw.get("current_version")) else None)
        kb_fw = fw["kb_framework"] if pd.notna(fw.get("kb_framework")) else None
        v = ver[(ver["country_iso3"] == c) & (ver["hazard"] == h)]
        a = act[(act["country_iso3"] == c) & (act["hazard"] == h)]
        p = pre[(pre["country_iso3"] == c) & (pre["hazard"] == h)
                & (pre["kind"] == "prearranged") & (pre["fund_code"] != "all")]
        r = rep[(rep["country_iso3"] == c) & (rep["hazard"] == h)]
        pc = cov[(cov["country_iso3"] == c) & (cov["hazard"] == h)]
        years = sorted(p["year"].unique())
        chart_data = {
            "years": [int(y) for y in years],
            "series": {
                fc: [float(p.loc[(p["year"] == y) & (p["fund_code"] == fc),
                                 "amount_usd"].sum()) for y in years]
                for fc in p["fund_code"].unique()
            },
        }
        # ---- Model: trigger line, windows / backtests of the current version, activations
        trig_line = trig.get((kb_fw, str(version))) if kb_fw and version else None
        w = win[(win["country_iso3"] == c) & (win["hazard"] == h)]
        wv = w[w["version"].astype(str) == str(version)] if version else w.iloc[0:0]
        wrows = "".join(
            f"<tr><td>{x.window_name}</td><td>{TD(x.basis) if pd.notna(x.basis) else ''}"
            f"{' · ' + T('all-in') if x.all_in is True else ''}</td>"
            f"<td>{T('triggered') + (f' ({x.triggered_on})' if pd.notna(x.triggered_on) else '') if x.triggered else T('not triggered')}</td>"
            f"<td class='num'>{_fmt_usd(x.allocation_usd)}</td>"
            f"<td class='num'>{TF('1-in-{n} yr', n=f'{x.return_period:.1f}') if pd.notna(x.return_period) else ''}</td>"
            f"<td class='num'>{f'{x.activation_prob*100:.0f}%' if pd.notna(x.activation_prob) else ''}</td>"
            f"<td class='num'>{TF('{n} in {y} yrs', n=int(x.n_activations), y=int(x.analysis_years)) if pd.notna(x.n_activations) and pd.notna(x.analysis_years) else ''}</td></tr>"
            for x in wv.sort_values("window_name").itertuples())
        hist_html, actual_html = _activation_blocks(d, c, h, kb_fw, version, umap)
        changes_html = _changes_block(d["fv_meta"], d["vpage"], c, h)
        valid_html = _validation_block(d["fv_meta"], c, h, version)
        # ---- Plan: people covered, agencies, the split vs the version envelope, partners
        s = split[(split["country_iso3"] == c) & (split["hazard"] == h)]
        sv = s[s["version"].astype(str) == str(version)] if version else s.iloc[0:0]
        split_note = ""
        split_version = version
        if not len(sv) and len(s):
            split_version = sorted(s["version"].astype(str).unique())[-1]
            sv = s[s["version"].astype(str) == split_version]
            split_note = (" <span class='muted' style='font-size:11px'>"
                          + TF("(split and envelope from version {v} — the current version has no split yet)", v=split_version)
                          + "</span>")
        # the envelope of the SAME version as the split, so the comparison is like for like
        ev = (env[(env["country_iso3"] == c) & (env["hazard"] == h)
                  & (env["version"].astype(str) == str(split_version))]
              if split_version else env.iloc[0:0])
        # by the one envelope rule (envelope_by_fund): Nigeria's 2026 "CBPF" and NHF rows are one $1M
        ebf = envelope_by_fund(ev, d["fund_names"])
        envelope = float(ebf["total_usd"].sum())
        envelope_cerf = float(ebf.loc[ebf["fund_code"] == "cerf", "total_usd"].sum())   # the part that counts N times
        # the Country or Regional Fund part an activation of this version released (pooled_spent):
        # in the version's envelope, no longer in pre-arranged now
        released_pool = (float(ebf.loc[ebf["fund_code"].astype(str).str.startswith(("cbpf", "rhpf")), "total_usd"].sum())
                         if (c, h, str(split_version)) in (d.get("pool_spent") or set()) else 0.0)
        n_apy = (d.get("act_factors") or {}).get((c, h, str(split_version)), 1)
        # the split is an earlier version's while the current one allows N activations a year: the
        # chart's current-year bar counts the current envelope N times (review of PR #58: Cuba)
        cur_apy = (d.get("act_factors") or {}).get((c, h, str(version)), 1)
        if split_note and cur_apy > 1:
            split_note += (" <span class='muted' style='font-size:11px'>"
                           + TF("The current version ({v}) allows {n} activations a year: the chart, the map and the Financing page count its CERF envelope {n} times.", v=version, n=cur_apy)
                           + "</span>")
        cy_ = pd.Timestamp.now().year     # the cross-page figure check (build_site): this page's pre-arranged figures
        figure_check.KEY.setdefault("fw", {})[f"{c}|{h}"] = dict(
            chart_cy=(sum(v[chart_data["years"].index(cy_)] for v in chart_data["series"].values())
                      if cy_ in chart_data["years"] else 0),
            envelope=envelope, envelope_cerf=envelope_cerf, envelope_released=released_pool,
            envelope_version=split_version, apy=n_apy)
        split_total = float(sv["amount_usd"].sum())
        over = envelope > 0 and split_total > envelope * 1.01
        agencies = sorted(set(sv.loc[sv["agency"].notna(), "agency"]))
        srows = "".join(
            f"<tr><td>{x.window_name or ''}</td><td>{x.agency if pd.notna(x.agency) else ''}</td>"
            f"<td>{x.sector if pd.notna(x.sector) else ''}</td><td>{fund_label(x.fund_code)}</td>"
            f"<td class='num'>${x.amount_usd:,.0f}</td></tr>" for x in sv.itertuples())
        split_foot = (
            f"<tr><th colspan=4>{T('split total')}</th><th class='num'>${split_total:,.0f}</th></tr>"
            f"<tr><th colspan=4>{T('version envelope (pre-arranged)')}</th><th class='num'>"
            f"{f'${envelope:,.0f}' if envelope else '—'}"
            f"{'<span class=' + chr(39) + 'warn-tag' + chr(39) + '>' + TF('split exceeds envelope by {p}%', p=f'{(split_total/envelope - 1)*100:.0f}') + '</span>' if over else ''}"
            # a version that allows two activations a year: the map and the Financing page count it twice
            f"{' <span class=' + chr(39) + 'muted' + chr(39) + ' style=' + chr(39) + 'font-weight:400;font-size:11px' + chr(39) + '>' + TF('the CERF budget of one activation: this version allows {n} activations a year, so the map and the Financing page count its CERF envelope {n} times', n=n_apy) + '</span>' if envelope and n_apy > 1 else ''}"
            # a Country or Regional Fund envelope an activation released: in the envelope, no longer committed
            f"{' <span class=' + chr(39) + 'muted' + chr(39) + ' style=' + chr(39) + 'font-weight:400;font-size:11px' + chr(39) + '>' + TF('of which {x} from a Country or Regional Fund, released by an activation: no longer counted as pre-arranged now', x=f'${released_pool:,.0f}') + '</span>' if released_pool else ''}</th></tr>")
        # budget by agency / by sector (bars) and agency -> sector (Sankey), same split rows
        split_js = [{"a": x.agency if isinstance(x.agency, str) and x.agency else "(agency not stated)",
                     "s": x.sector if isinstance(x.sector, str) and x.sector else "(sector not stated)",
                     "v": float(x.amount_usd)} for x in sv.itertuples() if pd.notna(x.amount_usd)]
        plan_charts = ("<div class='grid' style='margin-top:12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr))'>"
                       f"<div class='panel'><h3>{T('Budget by agency')}</h3><div id='pAg'></div></div>"
                       f"<div class='panel'><h3>{T('Budget by sector')}</h3><div id='pSe'></div></div>"
                       f"<div class='panel' style='grid-column:1/-1'><h3>{T('Agency → sector')}</h3><div id='pSk'></div>"
                       "<div class='note'>" + TBF("From the split rows above (version {v}); a window-level split that repeats "
                       "the same money across alternative windows is summed as recorded — compare the split total with "
                       "the envelope.", v=split_version or "—") + "</div></div></div>") if split_js else ""
        vrows = "".join(
            f"<tr><td>{x.version}</td><td>{TD(x.kb_status) if pd.notna(x.kb_status) else ''}</td><td>{_source_words(x.source)}</td>"
            f"<td>{f'<a href={x.doc_url!r}>' + T('doc') + '</a>' if pd.notna(x.doc_url) else ''}</td>"
            f"<td style='max-width:340px'>{x.analysis_ref if pd.notna(x.analysis_ref) else ''}</td></tr>"
            for x in v.itertuples())
        rrows = _report_list(r)
        covered_txt = (f"{int(pc['people_covered'].iloc[0]):,}"
                       if not pc.empty else "—")
        # ---- Learning: the framework's documents
        fd = _fw_docs(docs, c, h)
        fd_html = (f"<ul class='doclist'>{''.join(_doc_li(x) for x in fd.itertuples())}</ul>"
                   if len(fd) else f"<div class='empty'>{T('no documents yet')}</div>")
        obs = fw.get("observed_status")
        derived_note = (
            " <span class='muted' style='font-size:11px'>"
            + TC(lambda w: w("(derived from the endorsed {v} version — sheets last said “{s}”)").format(
                 v=cur_v, s=w(_status_words(obs)))) + "</span>"
            if (pd.notna(obs) and obs != fw["status"] and not no_fw and _status_words(obs)
                and _has(fw.get("current_version"))) else "")
        fw_name = T(i18n.add(f"{fw['country_name']} — {hazard_word(h)}", "{country} — {hazard}",
                             country=i18n.country(c, fw["country_name"]), hazard=hazard_word(h)))
        st_raw = fw['status'] if _has(fw.get('status')) and not no_fw else status
        body = f"""
<div class='card'><b>{fw_name}</b> ·
{f"<span class='badge b-new'>{T(_status_words(st_raw))}</span>" if _status_words(st_raw) else ''}{derived_note}
{T('current version:')} <code>{cur_v}</code>
· {T('people covered:')} <b>{covered_txt}</b><br>
{T('Monitoring window:')} {_cal_strip(cal, c, h)}</div>
{changes_html}
<div class='blk'><h2>{T('Model')}</h2>
<p class='meta'>{(T('Trigger:') + ' ' + TC(lambda w: _trigger_line(trig_line, w))) if trig_line else T('No structured trigger info in the KB for this version.')}</p>
<h3 class='sub'>{TF('Windows and backtests (version {v})', v=version or '—')}</h3>
<section><div class='scroll' style='max-height:260px'><table class='data'><thead>
<tr>{''.join(f'<th>{T(x)}</th>' for x in ('window', 'basis', 'state', 'budget', 'return period', 'annual prob.', 'backtest'))}</tr></thead>
<tbody>{wrows or '<tr><td colspan=7 class="empty">' + T('no windows registered for this version') + '</td></tr>'}</tbody></table></div></section>
<h3 class='sub'>{T('Actual activations')}</h3>
<section>{actual_html}</section>
<h3 class='sub'>{T('Historical activations')}</h3>
<section>{hist_html}</section>
{valid_html}</div>
<div class='blk'><h2>{T('Activities')}</h2>
<div class='tiles'>
 <div class='tile'><div class='v'>{covered_txt}</div><div class='l'>{T('people covered (latest figure)')}</div></div>
 <div class='tile'><div class='v'>{len(agencies) or '—'}</div><div class='l'>{TF('agencies with a budget line: {list}', list=', '.join(agencies)) if agencies else T('agencies with a budget line')}</div></div>
</div>
<h3 class='sub'>{T('Agency × sector split')}{split_note}</h3>
<section><div class='scroll' style='max-height:360px'><table class='data'><thead>
<tr>{''.join(f'<th>{T(x)}</th>' for x in ('window', 'agency', 'sector', 'fund', 'USD'))}</tr></thead>
<tbody>{srows or '<tr><td colspan=5 class="empty">' + T('no split recorded') + '</td></tr>'}</tbody>
<tfoot>{split_foot}</tfoot></table></div></section>
{plan_charts}
{_partners_block(pt, sg, c, h, version)}</div>
<div class='blk'><h2>{T('Financing')}</h2>
<div class='grid'>
<div class='panel'><h3>{T('Pre-arranged funding in place, by year × fund')}</h3><div class='note'>{T('The envelope in place each year — a stock, so the bars are not added up.')}</div><canvas id='pf' height='230'></canvas></div>
<div class='panel'><h3>{T('Versions (endorsed documents)')}</h3>
<div class='scroll' style='max-height:230px'><table class='data'><thead>
<tr>{''.join(f'<th>{T(x)}</th>' for x in ('version', 'KB status', 'source', 'doc', 'analysis'))}</tr></thead>
<tbody>{vrows or '<tr><td colspan=5>' + T('none registered') + '</td></tr>'}</tbody></table></div></div>
</div>
<p class='meta'>{T('Counted in reports:')} {rrows or '—'}</p></div>
<div class='blk'><h2>{TF('Learning · {n} document', n=len(fd)) if len(fd) == 1 else TF('Learning · {n} documents', n=len(fd))}</h2>
{fd_html}</div>
<script src="chart.umd.js"></script>
<script src="sankey.js"></script>
<script>window.FD = {json.dumps(chart_data)}; window.SPLIT = {json.dumps(split_js)}; window.REGIONAL_FUNDS = {json.dumps(sorted(REGIONAL_FUNDS))};</script>
<script>{DASH_JS}
const ds = Object.entries(FD.series).map(([fc,vals],i)=>({{label:fundName(fc),data:vals,
  backgroundColor:FUND_COLORS[fundType(fc)]||PAL[i]}}));
if(FD.years.length) mkChart('pf','bar',FD.years,ds,{{stacked:true, totals:true}});
else document.getElementById('pf').outerHTML='<p class="meta">' + {json.dumps(T("no funding rows"))} + '</p>';
function drawSplit(){{   // again on a language switch (the two placeholders, the charts' labels)
  if(!(SPLIT.length && window.sankeySVG)) return;
  // the records' agency and sector labels as recorded; our two placeholders translated
  const lab = x => (x === '(agency not stated)' || x === '(sector not stated)') ? tr8(x) : x;
  const bars = k => {{ const g = groupSum(SPLIT, r=>r[k], r=>r.v);
    return Object.keys(g).sort((a,b)=>g[b]-g[a]).map(x=>({{label:lab(x), v:g[x]}})); }};
  const AG = bars('a'), SE = bars('s');
  document.getElementById('pAg').innerHTML = hbarsSVG(AG, {{width:460, fmt:money, labelW:130, colorBy:'a', label:tr8('budget by agency')}});
  document.getElementById('pSe').innerHTML = hbarsSVG(SE, {{width:460, fmt:money, labelW:130, color:'#64748b', label:tr8('budget by sector')}});
  const L = {{}}; SPLIT.forEach(r=>{{ const k='a:'+lab(r.a)+'|s:'+lab(r.s); L[k]=(L[k]||0)+r.v; }});
  document.getElementById('pSk').innerHTML = sankeySVG({{
    columns:[AG.map(x=>({{id:'a:'+x.label,label:x.label}})), SE.map(x=>({{id:'s:'+x.label,label:x.label}}))],
    links:Object.entries(L).map(([k,v])=>{{ const [s,t]=k.split('|'); return {{s,t,v}}; }}),
    width:900, height:Math.max(110, Math.max(AG.length,SE.length)*26), fmt:money, labelW:150,
    label:tr8('pre-arranged budget from agency to sector')}});
}}
drawSplit();
document.addEventListener('aalang', drawSplit);
</script>
<style>{DASH_CSS}</style>"""
        tmpl = "{country} {hazard} — framework"
        title = i18n.add(tmpl.format(country=fw["country_name"], hazard=hazard_word(h)), tmpl,
                         country=i18n.country(fw["country_iso3"], fw["country_name"]), hazard=hazard_word(h))
        page(f"{slug}.html", title, body)
    return links


def _fmt_usd(v):
    """$2.3M, $800k, $500: halves round up, as the Map's money() does in the page (Python's own
    formatting rounds 2.25 to 2.2, the page's to 2.3)."""
    if v is None or pd.isna(v):
        return ""
    from decimal import ROUND_HALF_UP, Decimal
    v = float(v)
    def r(x, q):   # the float's exact binary value, as toFixed() reads it: 1.15 -> 1.1, 2.25 -> 2.3
        return Decimal(x).quantize(Decimal(q), ROUND_HALF_UP)
    return f"${r(v / 1e6, '0.1')}M" if v >= 1e6 else f"${r(v / 1e3, '1')}k" if v >= 1e3 else f"${r(v, '1')}"


def _st(status, kind="fw"):
    if status is None or pd.isna(status):
        return ""
    cls = ("st-on" if status in ("active", "activated_implementing", "endorsed")
           else "st-dev" if ("development" in status or "conversation" in status
                            or status == "under_revision")
           else "st-off")
    return f"<span class='st {cls}'>{status.replace('_', ' ')}</span>"


def _kb_trigger_info(e, parts=False):
    """Structured trigger info per (kb_framework, version) from aa.version_page: the English
    line, or (parts=True) its parts — basis, indicators, months — for _trigger_line()."""
    from ds_aa_tracking.kb_pages import load_version_pages

    out = {}
    for (fw, ver), pg in load_version_pages(e).items():
        fm = pg["fm"]
        tf = fm.get("trigger_facets") or {}
        mp = fm.get("monitoring_period") or {}
        months = [m for m in (mp.get("months") or []) if isinstance(m, int) and 1 <= m <= 12]
        x = (str(tf["basis"]) if tf.get("basis") else None,
             ", ".join(map(str, tf["indicators"])) if tf.get("indicators") else None, months)
        if any(x):
            out[(fw, ver)] = x if parts else _trigger_line(x)
    return out


def _trigger_line(x, w=lambda s: s):
    """'forecast · SEAS5-precip · monitored MAMJAS' (w: the words in one language; the
    indicators as recorded; the month initials of that language)."""
    basis, ind, months = x
    names = w("JFMAMJJASOND")
    bits = [w(basis) if basis else None, ind,
            w("monitored {m}").format(m="".join(names[m - 1] for m in months)) if months else None]
    return " · ".join(b for b in bits if b)


# ------------------------------------------------------------------ entry form
FORM_CSS = """
.form-card { background:#fff; border:1px solid #dfe4ea; border-radius:8px;
  padding:16px 20px; margin:14px 0; }
.form-card h3 { margin:0 0 4px; font-size:14.5px; }
.form-card .hint { color:#667; font-size:11.5px; margin:0 0 10px; }
.frow { display:flex; gap:12px; flex-wrap:wrap; margin:8px 0; }
.frow label { display:flex; flex-direction:column; gap:3px; font-size:11.5px;
  color:#556; font-weight:600; }
.frow input, .frow select, .frow textarea { padding:6px 9px; border:1px solid #bbb;
  border-radius:5px; font-size:13px; font-family:inherit; min-width:160px; }
.frow textarea { min-width:420px; min-height:52px; }
.months { display:flex; gap:4px; }
.months span { width:26px; height:26px; display:grid; place-items:center;
  border:1px solid #ccc; border-radius:5px; font-size:11px; cursor:pointer;
  user-select:none; }
.months span.on { background:#1baf7a; color:#fff; border-color:#1baf7a; }
.rep { border-left:3px solid #e3e8ef; padding:2px 0 2px 12px; margin:8px 0; }
button.small { padding:4px 10px; border:1px solid #bbb; border-radius:5px;
  background:#fff; cursor:pointer; font-size:12px; }
button.primary { padding:8px 18px; border:0; border-radius:6px; background:#1f2a44;
  color:#fff; font-size:14px; cursor:pointer; }
#payload { background:#0f1520; color:#c7e3d4; padding:14px; border-radius:8px;
  font-size:11.5px; overflow-x:auto; display:none; }
.dummy-banner { background:#fdf1dc; border:1px solid #eeddb0; color:#6b4b06;
  border-radius:6px; padding:9px 14px; font-size:12.5px; margin:10px 0; }
"""


def build_entry(page, d, e):
    """Unified data entry (entry.html): optional PDF upload -> Claude extraction
    via the chd-ds-aa-extract proxy (spinner) -> full prefilled form (version
    fields, per-fund totals, windows with triggers and per-window per-fund
    funding) -> live per-field diff against the DB -> Save writes straight to
    aa.entered_* through the proxy, with every field change audited. The ingest
    merges entered values into aa.framework_version (entered wins). Replaces the
    old ingest-doc demo + dummy form; heuristic pdf.js detection remains the
    no-proxy fallback."""
    import os as _os
    from pathlib import Path as _P

    token_file = _P(__file__).parents[1] / ".extract_token"
    extract_token = _os.environ.get("EXTRACT_TOKEN", "").strip() or (
        token_file.read_text().strip() if token_file.exists() else "")
    if not extract_token:
        print("  WARNING: no .extract_token / EXTRACT_TOKEN — proxy calls will 401")

    cur = d["current"].sort_values("country_name")
    ver = d["versions"]
    funds = pd.read_sql("SELECT fund_code, name FROM aa.fund ORDER BY fund_code", e)
    fw = [{"iso3": r.country_iso3, "hazard": r.hazard,
           "label": f"{r.country_name} — {r.hazard}",
           "names": [r.country_name],
           "kb": r.kb_framework if pd.notna(r.kb_framework) else None,
           "versions": sorted(ver.loc[(ver.country_iso3 == r.country_iso3)
                                      & (ver.hazard == r.hazard), "version"].tolist())}
          for r in cur.itertuples()]
    data = {"frameworks": fw, "funds": funds.to_dict("records")}
    body = r"""
<div class='card'><b>Framework data entry</b> — the one place frameworks are entered
or corrected. Drop an endorsed framework PDF and Claude fills the form (country,
version, validity, per-fund totals, every window with its trigger statement and
funding); or fill it by hand. If the version already exists, the page shows a
<b>field-by-field diff against the database</b> — overwrite what the document
corrects, keep what the database already has right. <b>Save writes straight to the
DB</b> (<code>aa.entered_*</code>, every change audited with who/when/old/new);
entered values win over what the registry held.
Status updates are rows of the <a href='admin.html#framework_status'>framework status table</a>.</div>

<div class='form-card' id='drop' style='border:2px dashed #9db2c9; text-align:center;
     padding:34px; cursor:pointer'>
 <div style='font-size:15px; font-weight:600'>Drop a framework PDF here, or click to choose — or skip and fill the form manually</div>
 <div class='hint' style='margin-top:6px'>sent only to the team extraction service · max 32&nbsp;MB / 100 pages</div>
 <input type='file' id='file' accept='application/pdf' style='display:none'>
</div>

<div id='progress' class='muted' style='margin:8px 0'></div>
<div id='spin' style='display:none; margin:14px 0; align-items:center; gap:12px'>
 <div class='spinner'></div><div id='spintext' class='muted'>Claude is reading the document…</div>
</div>

<div class='form-card' id='entry'>
 <h3>Framework version <span class='hint' id='exmeta'></span></h3>
 <div class='frow'>
  <label>Country <select id='dc'></select></label>
  <label id='dcNew' style='display:none'>ISO3 <input id='dcIso' size='4' maxlength='3' style='text-transform:uppercase'></label>
  <label>Hazard <select id='dh'></select></label>
  <label>Version / endorsement date <input type='date' id='dd'></label>
  <label>Endorsed by <select id='de'>
    <option value=''>— unknown —</option>
    <option value='erc'>ERC (major version)</option>
    <option value='cerf_secretariat'>CERF secretariat (minor revision)</option>
  </select></label>
 </div>
 <div class='frow'>
  <label>Title <input id='dt' style='min-width:420px'></label>
  <label>Document URL <input id='du' style='min-width:360px' placeholder='ReliefWeb / UNOCHA link'></label>
 </div>
 <div class='frow'>
  <label>Valid until <input type='date' id='dv'></label>
  <label>Validity source <select id='dvs'>
    <option value=''>—</option><option>doc-stated</option>
    <option>convention</option><option>inherited</option>
  </select></label>
  <label>Window rollup <select id='dr'>
    <option value=''>— unknown —</option>
    <option value='additive'>additive — every window can activate; total = sum</option>
    <option value='exclusive'>exclusive — either/or; each can draw the pot</option>
    <option value='capped'>capped — windows sum past the envelope</option>
  </select></label>
  <label>Supersedes <input id='ds' size='12' placeholder='YYYY[-MM[-DD]]'></label>
 </div>
 <div class='frow'><label style='flex:1'>Note <input id='dn' style='min-width:420px'></label></div>

 <h3 style='margin-top:14px'>Pre-arranged totals per fund
   <button onclick='addVFund()' style='margin-left:10px'>+ add fund</button></h3>
 <div class='hint'>The explicit stated total per fund — entered, never derived from windows.</div>
 <div id='vfund'></div>

 <h3 style='margin-top:14px'>Windows &amp; triggers
   <button onclick='addWindow()' style='margin-left:10px'>+ add window</button></h3>
 <div id='windows'></div>

 <div id='diffpane'></div>

 <div class='frow' style='margin-top:14px; align-items:center'>
  <label>Entered by <input id='by' size='16' placeholder='your name' required></label>
  <button class='primary' onclick='save()'>Save to database</button>
  <a class='btn-sec' href='#' onclick='downloadJson(); return false'>Download JSON</a>
 </div>
 <div id='result'></div>
</div>

<script src="pdf.min.js"></script>
<script>window.G = __DATA__;
window.PROXY = '__PROXY__'; window.SITE_TOKEN = '__TOKEN__';</script>
<script>
pdfjsLib.GlobalWorkerOptions.workerSrc = 'pdf.worker.min.js';
const HAZ = {
  drought: ['drought','sécheresse','secheresse','sequia','sequía','dry spell'],
  flood: ['flood','inondation','monsoon','riverine','crue'],
  storm: ['cyclone','typhoon','hurricane','tropical storm','tempête','ouragan'],
  cholera: ['cholera','choléra'],
};
const HAZARDS = ['drought','flood','storm','cholera','plague','locusts','other'];
const VFIELDS = {doc_title:'dt', doc_url:'du', endorsed_by:'de', valid_until:'dv',
  valid_until_source:'dvs', window_rollup:'dr', supersedes:'ds', note:'dn'};
const WFIELDS = ['basis','trigger_statement','monitoring_period'];
let cur = null;        // GET /framework response for the selected framework
let matched = null;    // version label in the DB this entry matches
let curHash = null;
let fileHashHits = JSON.parse(localStorage.getItem('ingestHashes')||'{}');
document.getElementById('by').value = localStorage.getItem('enteredBy') || '';

const drop = document.getElementById('drop'), fileEl = document.getElementById('file');
drop.onclick = () => fileEl.click();
drop.ondragover = e => { e.preventDefault(); drop.style.background='#eef4fc'; };
drop.ondragleave = () => drop.style.background='';
drop.ondrop = e => { e.preventDefault(); drop.style.background='';
  if(e.dataTransfer.files[0]) handle(e.dataTransfer.files[0]); };
fileEl.onchange = () => fileEl.files[0] && handle(fileEl.files[0]);

async function api(path, opts){
  const hdrs = () => {
    const h = {...(opts && opts.headers || {}), 'x-site-token': SITE_TOKEN};
    const et = localStorage.getItem('editorToken');
    if(et) h['x-editor-token'] = et;
    return h;
  };
  let r = await fetch(PROXY + path, {...opts, headers: hdrs()});
  if(r.status === 401){
    const et = prompt('Editor token required (ask Tristan) — saved in this browser:');
    if(et){ localStorage.setItem('editorToken', et.trim());
            r = await fetch(PROXY + path, {...opts, headers: hdrs()}); }
  }
  return r;
}
function showSpin(on, txt){
  document.getElementById('spin').style.display = on ? 'flex' : 'none';
  if(txt) document.getElementById('spintext').textContent = txt;
}
function fundDatalist(){
  const dl = document.createElement('datalist'); dl.id = 'fundlist';
  G.funds.forEach(f=>{ const o = document.createElement('option');
    o.value = f.fund_code; o.label = f.name || f.fund_code; dl.appendChild(o); });
  ['cofinancing','other'].forEach(v=>{ const o = document.createElement('option');
    o.value = v; dl.appendChild(o); });
  document.body.appendChild(dl);
}
function initSelects(){
  const dsel = document.getElementById('dc'), hsel = document.getElementById('dh');
  if(dsel.options.length) return;
  [...new Map(G.frameworks.map(f=>[f.iso3, f.names[0]])).entries()]
    .sort((a,b)=>a[1].localeCompare(b[1]))
    .forEach(([iso,nm])=>dsel.appendChild(new Option(`${nm} (${iso})`, iso)));
  dsel.appendChild(new Option('— other / new country —', 'NEW'));
  HAZARDS.forEach(h=>hsel.appendChild(new Option(h,h)));
  dsel.onchange = () => {
    document.getElementById('dcNew').style.display = dsel.value==='NEW' ? '' : 'none';
    refreshCurrent();
  };
  hsel.onchange = refreshCurrent;
  document.getElementById('dd').onchange = refreshCurrent;
  fundDatalist();
  addVFund(); addWindow();
}
initSelects();

function isoNow(){
  const v = document.getElementById('dc').value;
  return v==='NEW' ? document.getElementById('dcIso').value.toUpperCase() : v;
}

// ------------------------------------------------------------- dynamic rows
function fundRow(container, f, withAmountLabel){
  const div = document.createElement('div');
  div.className = 'frow fundrow';
  div.innerHTML = `
   <label>Fund <input class='ff' list='fundlist' size='12'></label>
   <label>Financier <input class='fi' size='14' placeholder='if cofinancing'></label>
   <label>${withAmountLabel} USD <input class='fa' size='12'></label>
   <button class='fdel'>remove</button>`;
  div.querySelector('.ff').value = (f && f.fund_code) || '';
  div.querySelector('.fi').value = (f && f.financier) || '';
  div.querySelector('.fa').value = (f && f.amount != null) ? f.amount : '';
  div.querySelector('.fdel').onclick = () => div.remove();
  container.appendChild(div);
}
function addVFund(f){ fundRow(document.getElementById('vfund'),
  f && f.fund_code !== undefined ? f : null, 'Total'); }
function addWindow(w){
  w = w && w.window_name !== undefined ? w : {};
  const div = document.createElement('div');
  div.className = 'wrow';
  div.innerHTML = `
   <div class='frow'>
    <label>Window <input class='wn' size='18'></label>
    <label>Basis <select class='wb'><option value=''>—</option>
      <option>observational</option><option>forecast</option><option>mixed</option></select></label>
    <label>Monitoring period <input class='wm' size='16'></label>
    <button class='wdel' style='align-self:flex-end'>remove window</button>
   </div>
   <label style='display:block'>Trigger statement
    <textarea class='wt' rows='2' style='width:100%; box-sizing:border-box'></textarea></label>
   <div class='hint' style='margin-top:6px'>Window funding per fund
    <button class='wfadd small'>+ add</button></div>
   <div class='wfund'></div>`;
  div.querySelector('.wn').value = w.window_name || '';
  div.querySelector('.wb').value = w.basis || '';
  div.querySelector('.wm').value = w.monitoring_period || '';
  div.querySelector('.wt').value = w.trigger_statement || '';
  div.querySelector('.wdel').onclick = () => div.remove();
  const wf = div.querySelector('.wfund');
  div.querySelector('.wfadd').onclick = () => fundRow(wf, null, 'Amount');
  (w.funding || []).forEach(f => fundRow(wf, f, 'Amount'));
  document.getElementById('windows').appendChild(div);
}

// ------------------------------------------------------------- extraction
function mapFund(f, iso){
  const code = (f.fund || '').toLowerCase();
  if(code === 'cbpf'){
    const c = 'cbpf-' + iso.toLowerCase();
    if(G.funds.some(x=>x.fund_code===c)) return c;
  }
  if(code === 'rhpf'){
    const hit = G.funds.find(x=>x.fund_code.startsWith('rhpf') &&
      x.fund_code.endsWith(iso.toLowerCase()));
    if(hit) return hit.fund_code;
  }
  return code;
}

async function handle(f){
  const prog = document.getElementById('progress');
  document.getElementById('result').innerHTML = '';
  if(f.size > 32*1024*1024){ prog.textContent = 'file exceeds 32 MB — extraction service cap'; return; }
  const buf = await f.arrayBuffer();
  curHash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', buf))]
    .map(b=>b.toString(16).padStart(2,'0')).join('');
  prog.textContent = `${f.name} · ${(f.size/1e6).toFixed(1)} MB · sha256 ${curHash.slice(0,12)}…` +
    (fileHashHits[curHash] ? ` · previously processed as ${fileHashHits[curHash]}` : '');
  const t0 = Date.now();
  showSpin(true, 'Claude is reading the document…');
  try {
    const b64 = await new Promise((res, rej) => {
      const r = new FileReader();
      r.onload = () => res(r.result.split(',')[1]);
      r.onerror = rej;
      r.readAsDataURL(f);
    });
    const resp = await api('/extract', {
      method: 'POST',
      headers: {'content-type':'application/json'},
      body: JSON.stringify({pdf_base64: b64, model: 'claude-opus-5'}),
    });
    const out = await resp.json();
    if(!resp.ok || !out.ok) throw new Error(out.error || `service returned ${resp.status}`);
    showSpin(false);
    document.getElementById('exmeta').textContent =
      `— extracted by ${out.model} in ${((Date.now()-t0)/1000).toFixed(0)}s; correct anything that's wrong`;
    fillForm(out.data);
  } catch(err) {
    showSpin(false);
    prog.textContent += ` · AI extraction unavailable (${err.message}) — heuristic detection instead`;
    await heuristic(buf, f.name);
  }
  refreshCurrent();
}

function setVal(id, v){ document.getElementById(id).value = v == null ? '' : v; }
function fillForm(x){
  const dsel = document.getElementById('dc');
  const iso = (x.country_iso3||'').toUpperCase();
  if([...dsel.options].some(o=>o.value===iso)) dsel.value = iso;
  else { dsel.value = 'NEW'; document.getElementById('dcNew').style.display='';
         setVal('dcIso', iso); }
  setVal('dh', x.hazard || 'other');
  setVal('dd', (x.version_date||'').slice(0,10));
  setVal('dt', x.doc_title); setVal('du', x.doc_url);
  setVal('de', (x.endorsed_by==='unknown'?'':x.endorsed_by));
  setVal('dv', (x.valid_until||'').slice(0,10));
  setVal('dvs', (x.valid_until_source==='unknown'?'':x.valid_until_source));
  setVal('dr', (x.window_rollup==='unknown'?'':x.window_rollup));
  setVal('ds', x.supersedes); setVal('dn', x.note);
  document.getElementById('vfund').innerHTML = '';
  (x.version_funding || []).forEach(f => addVFund(
    {fund_code: mapFund(f, iso), financier: f.financier, amount: f.total_usd}));
  if(!(x.version_funding||[]).length) addVFund();
  document.getElementById('windows').innerHTML = '';
  (x.windows && x.windows.length ? x.windows : [{}]).forEach(w => addWindow({
    ...w, funding: (w.funding||[]).map(f =>
      ({fund_code: mapFund(f, iso), financier: f.financier, amount: f.amount_usd}))}));
}

async function heuristic(buf, fname){
  let text = '';
  try {
    const pdf = await pdfjsLib.getDocument({data: buf.slice(0)}).promise;
    const n = Math.min(pdf.numPages, 8);
    for(let i=1;i<=n;i++){
      const pg = await pdf.getPage(i);
      const tc = await pg.getTextContent();
      text += tc.items.map(x=>x.str).join(' ') + '\n';
    }
  } catch(err) { /* fill manually */ }
  const t = (text + ' ' + fname).toLowerCase();
  let best = null, bestN = 0;
  G.frameworks.forEach(f => f.names.forEach(nm => {
    const n = t.split(nm.toLowerCase()).length - 1;
    if(n > bestN) { best = f.iso3; bestN = n; }
  }));
  let bh = null, bhN = 0;
  for(const [h, kws] of Object.entries(HAZ)){
    const n = kws.reduce((a,k)=>a + (t.split(k).length - 1), 0);
    if(n > bhN) { bh = h; bhN = n; }
  }
  fillForm({country_iso3: best || '', hazard: bh || 'other',
    doc_title: (text.split('\n')[0]||'').trim().slice(0,120) || fname.replace(/\.pdf$/i,''),
    windows: []});
}

// ------------------------------------------------------------- live diff
async function refreshCurrent(){
  const iso = isoNow(), hz = document.getElementById('dh').value;
  const pane = document.getElementById('diffpane');
  if(!/^[A-Z]{3}$/.test(iso) || !hz){ pane.innerHTML=''; return; }
  try {
    const r = await api(`/framework?iso3=${iso}&hazard=${hz}`);
    cur = await r.json();
    if(!r.ok || !cur.ok) throw new Error(cur.error || r.status);
  } catch(err) {
    pane.innerHTML = `<div class='dummy-banner'>live DB check unavailable (${err.message}) — you can still save; the diff just can't be shown</div>`;
    cur = null; matched = null; return;
  }
  renderDiff();
}

function matchVersion(){
  const vd = document.getElementById('dd').value;
  if(!cur || !vd) return null;
  const exact = cur.versions.find(v=>v.version===vd);
  if(exact) return vd;
  let best = null, bestD = 46*864e5;
  cur.versions.forEach(v=>{
    if(!v.valid_from) return;
    const dd = Math.abs(new Date(v.valid_from) - new Date(vd));
    if(dd < bestD){ best = v.version; bestD = dd; }
  });
  return best;
}

function esc(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;'); }
function formVal(id){ return document.getElementById(id).value.trim() || null; }

function renderDiff(){
  const pane = document.getElementById('diffpane');
  matched = matchVersion();
  const iso = isoNow(), hz = document.getElementById('dh').value,
        vd = document.getElementById('dd').value;
  const fwKnown = G.frameworks.some(f=>f.iso3===iso && f.hazard===hz) ||
                  (cur && cur.versions.length);
  if(!matched){
    pane.innerHTML = vd ? `<div class='card' style='margin:12px 0'>${
      fwKnown ? `<b>New version</b> of ${iso}/${hz} — nothing to diff; saving creates version <code>${esc(vd)}</code>.`
              : `<b>Brand-new framework</b> ${iso}/${hz} — saving registers it with version <code>${esc(vd)}</code>.`}</div>` : '';
    return;
  }
  const vrow = cur.versions.find(v=>v.version===matched) || {};
  const erow = (cur.entered_versions||[]).find(v=>v.version===matched) || {};
  const dbv = f => erow[f] != null && String(erow[f]).trim() !== '' ? erow[f] : vrow[f];
  let rows = '';
  for(const [f, id] of Object.entries(VFIELDS)){
    let curV = dbv(f); if(f==='valid_until' && curV) curV = String(curV).slice(0,10);
    const newV = formVal(id);
    if(String(curV??'') === String(newV??'')) continue;
    rows += `<tr><td>${f}</td><td class='cv'>${esc(curV)??''}</td><td class='nv'>${esc(newV)}</td>
      <td><button class='small' onclick="setVal('${id}', ${JSON.stringify(curV==null?'':String(curV))}); renderDiff()">keep current</button></td></tr>`;
  }
  const dbWin = (cur.windows||[]).filter(w=>w.version===matched);
  const dbWinBy = Object.fromEntries(dbWin.map(w=>[w.window_name, w]));
  const formWins = collect().windows;
  const formNames = new Set(formWins.map(w=>w.window_name));
  formWins.forEach(w=>{
    const o = dbWinBy[w.window_name];
    if(!o){ rows += `<tr><td>window “${esc(w.window_name)}”</td><td class='cv'>— not in DB —</td><td class='nv'>added</td><td></td></tr>`; return; }
    WFIELDS.forEach(f=>{
      if(String(o[f]??'') !== String(w[f]??''))
        rows += `<tr><td>“${esc(w.window_name)}” · ${f}</td><td class='cv'>${esc(o[f])}</td><td class='nv'>${esc(w[f])}</td><td></td></tr>`;
    });
  });
  dbWin.forEach(o=>{ if(!formNames.has(o.window_name))
    rows += `<tr><td>window “${esc(o.window_name)}”</td><td class='cv'>${esc(o.trigger_statement||'').slice(0,60)}…</td><td class='nv'>— removed on save —</td><td></td></tr>`; });
  const dbVF = (cur.version_funding||[]).filter(f=>f.version===matched);
  const formVF = collect().version_funding;
  const vfBy = Object.fromEntries(dbVF.map(f=>[f.fund_code, f.total_usd]));
  formVF.forEach(f=>{
    if(String(vfBy[f.fund_code]??'') !== String(f.total_usd??''))
      rows += `<tr><td>total · ${esc(f.fund_code)}</td><td class='cv'>${esc(vfBy[f.fund_code])}</td><td class='nv'>${esc(f.total_usd)}</td><td></td></tr>`;
  });
  dbVF.forEach(f=>{ if(!formVF.some(x=>x.fund_code===f.fund_code))
    rows += `<tr><td>total · ${esc(f.fund_code)}</td><td class='cv'>${esc(f.total_usd)}</td><td class='nv'>— removed on save —</td><td></td></tr>`; });
  const head = `<div class='card' style='margin:12px 0'><b>Version <code>${esc(matched)}</code> exists in the DB</b>
    ${matched!==vd ? ` (matched from your date <code>${esc(vd)}</code> — same version within 45 days; change the date if this is genuinely a new version)` : ''}
    — the table shows exactly what saving would change. <button class='small' onclick='loadCurrent()'>Load ALL current values into the form</button></div>`;
  pane.innerHTML = head + (rows
    ? `<table class='difftable'><tr><th>field</th><th>current (DB)</th><th>new (form)</th><th></th></tr>${rows}</table>`
    : `<div class='hint'>No differences — the form matches the database.</div>`);
}

function loadCurrent(){
  if(!matched || !cur) return;
  const vrow = cur.versions.find(v=>v.version===matched) || {};
  const erow = (cur.entered_versions||[]).find(v=>v.version===matched) || {};
  const dbv = f => erow[f] != null && String(erow[f]).trim() !== '' ? erow[f] : vrow[f];
  for(const [f, id] of Object.entries(VFIELDS)){
    let v = dbv(f); if(f==='valid_until' && v) v = String(v).slice(0,10);
    setVal(id, v);
  }
  document.getElementById('dd').value = /^\d{4}-\d{2}-\d{2}$/.test(matched) ? matched
    : document.getElementById('dd').value;
  document.getElementById('windows').innerHTML = '';
  const wf = cur.window_funding || [];
  const dbWin = (cur.windows||[]).filter(w=>w.version===matched);
  (dbWin.length ? dbWin : [{}]).forEach(w => addWindow({...w,
    funding: wf.filter(f=>f.version===matched && f.window_name===w.window_name)
      .map(f=>({fund_code: f.fund_code, financier: f.financier, amount: f.amount_usd}))}));
  document.getElementById('vfund').innerHTML = '';
  const dbVF = (cur.version_funding||[]).filter(f=>f.version===matched);
  (dbVF.length ? dbVF : [null]).forEach(f => addVFund(f
    ? {fund_code: f.fund_code, financier: f.financier, amount: f.total_usd} : undefined));
  renderDiff();
}

// ------------------------------------------------------------- collect/save
function collectFunding(container){
  return [...container.querySelectorAll('.fundrow')].map(div => ({
    fund_code: div.querySelector('.ff').value.trim().toLowerCase(),
    financier: div.querySelector('.fi').value.trim() || null,
    amount_usd: parseFloat(div.querySelector('.fa').value) || null,
  })).filter(f => f.fund_code && f.amount_usd != null);
}
function collect(){
  const windows = [...document.querySelectorAll('#windows .wrow')].map(div => ({
    window_name: div.querySelector('.wn').value.trim(),
    basis: div.querySelector('.wb').value || null,
    trigger_statement: div.querySelector('.wt').value.trim() || null,
    monitoring_period: div.querySelector('.wm').value.trim() || null,
    funding: collectFunding(div.querySelector('.wfund')),
  })).filter(w => w.window_name);
  return {
    country_iso3: isoNow(),
    hazard: document.getElementById('dh').value,
    version: document.getElementById('dd').value,
    entered_by: document.getElementById('by').value.trim(),
    version_fields: Object.fromEntries(
      Object.entries(VFIELDS).map(([f, id]) => [f, formVal(id)])),
    windows: windows.map(({funding, ...w}) => w),
    window_funding: windows.flatMap(w => w.funding.map(f => ({...f, window_name: w.window_name}))),
    version_funding: collectFunding(document.getElementById('vfund'))
      .map(({amount_usd, ...f}) => ({...f, total_usd: amount_usd})),
  };
}

async function save(){
  const p = collect();
  const out = document.getElementById('result');
  if(!/^[A-Z]{3}$/.test(p.country_iso3) || !p.version){
    out.innerHTML = `<div class='dummy-banner'>need a 3-letter country code and a version date</div>`; return;
  }
  if(!p.entered_by){
    out.innerHTML = `<div class='dummy-banner'>fill “Entered by” — every change is audited</div>`; return;
  }
  localStorage.setItem('enteredBy', p.entered_by);
  if(curHash){ fileHashHits[curHash] = `${p.country_iso3}/${p.hazard}/${p.version}`;
    localStorage.setItem('ingestHashes', JSON.stringify(fileHashHits)); }
  out.innerHTML = `<div class='hint'>saving…</div>`;
  try {
    const r = await api('/entry', {method:'POST',
      headers:{'content-type':'application/json'}, body: JSON.stringify(p)});
    const res = await r.json();
    if(!r.ok || !res.ok) throw new Error(res.error || r.status);
    out.innerHTML = `<div class='card' style='border-color:#1c6b31; background:#eef7f0'>
      <b>Saved.</b> ${res.changes} field change(s) written to <code>aa.entered_*</code>
      (${res.saved.windows} window(s), ${res.saved.window_funding} window-funding,
      ${res.saved.version_funding} fund-total row(s)), all audited as
      “${esc(p.entered_by)}”. Entered values merge into the registry
      (<code>aa.framework_version</code>) — entered wins; this site's static pages
      show it after the next publish.</div>`;
    refreshCurrent();
  } catch(err) {
    out.innerHTML = `<div class='dummy-banner'>save failed: ${esc(err.message)}</div>`;
  }
}

function downloadJson(){
  const p = collect();
  const blob = new Blob([JSON.stringify(p, null, 2)], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `framework-entry-${p.country_iso3||'XXX'}-${p.hazard}-${p.version||'undated'}.json`;
  a.click();
}
</script>
<style>__DASH_CSS____FORM_CSS__
.spinner { width:26px; height:26px; border:4px solid #d8dee6; border-top-color:#2a78d6;
  border-radius:50%; animation:spin .8s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }
#spin { display:none; }
.wrow { border:1px solid #d8dee6; border-radius:8px; padding:10px 12px; margin:8px 0; }
.fundrow { margin:4px 0; }
.btn-sec { display:inline-block; padding:8px 14px; border-radius:6px; border:1.5px solid #1f2a44;
  color:#1f2a44; text-decoration:none; }
.difftable { border-collapse:collapse; margin:8px 0; font-size:12.5px; }
.difftable th, .difftable td { border:1px solid #d8dee6; padding:5px 10px; text-align:left;
  max-width:340px; overflow-wrap:break-word; }
.difftable .cv { background:#fdf6ec; }
.difftable .nv { background:#eef7f0; }
</style>"""
    body = (body
            .replace("__DATA__", json.dumps(data))
            .replace("__PROXY__", "https://chd-ds-aa-extract.azurewebsites.net")
            .replace("__TOKEN__", extract_token)
            .replace("__DASH_CSS__", DASH_CSS)
            .replace("__FORM_CSS__", FORM_CSS))
    page("entry.html", "Framework data entry", body)



# ------------------------------------------------------------------ landing
# The landing page (zoomable map -> country -> framework -> version) lives in
# scripts/landing.py; it reuses the frames fetched here.


def build_all(e, page, tbl):
    d = _fetch(e)
    i18n.register_countries(zip(d["current"]["country_iso3"], d["current"]["country_name"]))
    import landing
    d["fwy"] = landing.framework_status_by_year(d, e)   # the Financing chart of frameworks by year
    build_funding(page, d)
    build_model(page, d)
    build_plan(page, d)
    build_learning(page, d)
    import page_definitions
    page_definitions.build_definitions(page, d)
    import page_history
    page_history.build_history(page, d)
    build_framework_pages(page, tbl, d, e)
    import page_media
    page_media.build_media(page)
    build_entry(page, d, e)
    import landing
    landing.build_landing(page, d, e)
