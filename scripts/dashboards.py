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

import pandas as pd

# validated reference palette (light mode), fixed assignment order
PAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
FUND_COLORS = {"cerf": "#2a78d6", "cbpf": "#eb6834", "regional_fund": "#1baf7a"}
HAZARDS = ["drought", "flood", "storm", "cholera"]  # fixed order; rest -> Other

SOURCE_PRIORITY = [
    "yakubu-prearranged-jun2026", "yakubu-cofinancing-jun2026", "julia-planning-2026",
    "julia-reporting-2025", "yakubu-insurance-2026", "julia-gho-2026",
    "yakubu-new-extended-2025",
]


def canonical(df, keys):
    """One row per key-combo by source priority (dashboard view; conflicts live on
    the reconciliation pages)."""
    df = df.copy()
    df["_p"] = df["source"].map(
        {s: i for i, s in enumerate(SOURCE_PRIORITY)}).fillna(99)
    return (df.sort_values("_p").drop_duplicates(subset=keys, keep="first")
            .drop(columns="_p"))


DASH_CSS = """
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(420px,1fr)); gap:16px; }
.panel { background:#fff; border:1px solid #e0e0e0; border-radius:6px; padding:14px 16px; min-width:0; overflow:hidden; }
.panel h3 { margin:2px 0 10px; font-size:14.5px; }
.panel .note { color:#666; font-size:11.5px; margin-top:6px; }
.tiles { display:flex; gap:14px; flex-wrap:wrap; margin:12px 0; }
.tile { background:#fff; border:1px solid #e0e0e0; border-radius:6px; padding:12px 18px; min-width:150px; }
.tile .v { font-size:22px; font-weight:700; }
.tile .l { font-size:12px; color:#666; }
.fbar { display:flex; gap:10px; flex-wrap:wrap; align-items:center; background:#fff;
        border:1px solid #e0e0e0; border-radius:6px; padding:10px 14px; margin:12px 0;
        position:sticky; top:0; z-index:5; }
.fbar label { font-size:12px; color:#555; }
.fbar select { padding:4px 8px; border:1px solid #bbb; border-radius:4px; font-size:12.5px; }
canvas { max-height:300px; }
.cal { border-collapse:collapse; font-size:11px; }
.cal td, .cal th { border:1px solid #eee; padding:2px 5px; text-align:center; }
.cal td.on { background:#1baf7a; }
.covered { color:#1c6b31; font-weight:600; } .partial { color:#8a5c0a; font-weight:600; }
.missing { color:#a11; font-weight:600; }
"""

DASH_JS = """
const PAL = %s, FUND_COLORS = %s;
Chart.defaults.font.family = "-apple-system,'Segoe UI',Roboto,sans-serif";
Chart.defaults.color = '#52514e';
Chart.defaults.borderColor = '#ececec';
Chart.defaults.plugins.legend.labels.boxWidth = 12;
function money(v){ if(v==null) return '';
  return v>=1e9 ? '$'+(v/1e9).toFixed(1)+'B' : v>=1e6 ? '$'+(v/1e6).toFixed(1)+'M'
       : v>=1e3 ? '$'+(v/1e3).toFixed(0)+'k' : '$'+Math.round(v); }
function mkChart(id, type, labels, datasets, opts={}){
  datasets.forEach((d,i)=>{ d.backgroundColor ??= PAL[i%%PAL.length];
    d.borderColor ??= (type==='line'? d.backgroundColor : '#fcfcfb');
    if(type==='bar'){ d.borderWidth=1; d.borderRadius=3; d.maxBarThickness=34; }
    if(type==='line'){ d.borderWidth=2; d.pointRadius=2; d.pointHoverRadius=5; d.tension=0.15; }});
  const el = document.getElementById(id);
  if(el._chart) el._chart.destroy();
  const horiz = opts.extra && opts.extra.indexAxis === 'y';
  const valAxis = {stacked:!!opts.stacked, ticks:{callback:v=>opts.count?v:money(v)}, grid:{color:'#f0f0f0'}};
  const catAxis = {stacked:!!opts.stacked, grid:{display:false}};
  el._chart = new Chart(el, { type, data:{labels, datasets}, options:{
    responsive:true, maintainAspectRatio:false, interaction:{mode:'index',intersect:false},
    scales: opts.noscale?{}:(horiz ? {x:valAxis, y:catAxis} : {x:catAxis, y:valAxis}),
    plugins:{ legend:{display:datasets.length>1},
      tooltip:{callbacks:{label:c=>{const v=horiz?c.parsed.x:(c.parsed.y??c.parsed);return ` ${c.dataset.label??''}: ${opts.count?v:money(v)}`;}}},
      ...(opts.plugins||{}) },
    ...(opts.extra||{}) }});
  return el._chart; }
function groupSum(rows, keyFn, valFn){ const m={};
  rows.forEach(r=>{ const k=keyFn(r); m[k]=(m[k]||0)+(valFn(r)||0); }); return m; }
function uniqSorted(rows, f){ return [...new Set(rows.map(f).filter(x=>x!=null))].sort(); }
function cumulate(arr){ let s=0; return arr.map(v=>s+=(v||0)); }
""" % (json.dumps(PAL), json.dumps(FUND_COLORS))


def haz(h):
    return h if h in HAZARDS else "other"


def _fetch(e):
    """All row-level frames the dashboards embed."""
    d = {}
    d["current"] = pd.read_sql(
        """SELECT c.*, r.region FROM aa.v_trk_framework_current c
           LEFT JOIN aa.framework_registry r USING (country_iso3, hazard)""", e)
    d["current"] = d["current"].loc[:, ~d["current"].columns.duplicated()]
    pre = pd.read_sql(
        """SELECT country_iso3, hazard, year, kind, fund_code, financier,
                  amount_usd, source FROM aa.prearranged_funding
           WHERE amount_usd IS NOT NULL""", e)
    pre = canonical(pre, ["country_iso3", "hazard", "year", "kind", "fund_code",
                          "financier"])
    # drop 'all' totals when component rows exist for the same framework-year
    comp = set(map(tuple, pre.loc[pre["fund_code"].isin(["cerf", "cbpf-unspecified"]),
                                  ["country_iso3", "hazard", "year"]].values))
    pre = pre[~((pre["fund_code"] == "all")
                & pre.apply(lambda r: (r["country_iso3"], r["hazard"], r["year"])
                            in comp, axis=1))]
    d["prearranged"] = pre
    d["activation"] = pd.read_sql(
        """SELECT a.country_iso3, a.hazard, a.event_type, a.event_date,
                  a.window_name, a.version, a.people_targeted, a.kb_event_date,
                  f.fund_code, f.allocation_code, f.amount_usd,
                  r.region
           FROM aa.activation_funding f
           JOIN aa.activation a USING (country_iso3, hazard, event_date,
                                       window_name, event_label, event_type)
           LEFT JOIN aa.framework_registry r USING (country_iso3, hazard)""", e)
    d["versions"] = pd.read_sql(
        """SELECT country_iso3, hazard, version, kb_status, valid_from, source,
                  doc_url, analysis_ref, prearranged_usd_doc
           FROM aa.framework_version ORDER BY country_iso3, hazard, valid_from""", e)
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
    d["subgrant"] = pd.read_sql(
        """SELECT year, country_iso3, emergency_type, partner_type, localization,
                  partner_name, subgrant_usd, is_aa
           FROM aa.cerf_subgrant WHERE subgrant_usd IS NOT NULL""", e)
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
           WHERE c.aa_keyword AND s.sector_amount IS NOT NULL""", e)
    d["agency"] = pd.read_sql(
        """SELECT c.year, c.country_iso3, p.agency_short_name AS agency,
                  p.amount_approved
           FROM aa.cerf_project p
           JOIN aa.cerf_allocation c ON c.application_code = p.application_code
           WHERE c.aa_keyword""", e)
    d["pre_sector"] = pd.read_sql(
        """SELECT country_iso3, hazard, window_name, agency, sector, amount_usd,
                  year_label FROM aa.prearranged_sector_budget
           WHERE amount_usd IS NOT NULL""", e)
    d["cva"] = pd.read_sql(
        """SELECT year, country_iso3, agency, emergency_type, cva_usd,
                  people_receiving_cash FROM aa.cerf_cva_history
           WHERE cva_usd IS NOT NULL""", e)
    d["reached"] = pd.read_sql(
        """SELECT p.application_code, c.year, c.country_iso3, p.grp, p.value
           FROM aa.cerf_application_people p
           JOIN aa.cerf_allocation c ON c.application_code = p.application_code
           WHERE p.phase = 'reached' AND p.disaggregation = 'sex_age'
             AND c.aa_keyword""", e)
    d["covered"] = pd.read_sql(
        """SELECT DISTINCT ON (country_iso3, hazard) country_iso3, hazard,
                  people_covered
           FROM aa.people_covered WHERE people_covered IS NOT NULL
           ORDER BY country_iso3, hazard, as_of DESC""", e)
    d["gho"] = pd.read_sql(
        """SELECT DISTINCT ON (country_iso3, year) country_iso3, year, in_gho
           FROM aa.plan_inclusion WHERE in_gho IS NOT NULL
           ORDER BY country_iso3, year, source""", e)
    d["calendar"] = pd.read_sql(
        """SELECT country_iso3, hazard, month FROM aa.framework_calendar
           WHERE phase = 'trigger_window' ORDER BY country_iso3, hazard, month""", e)
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
    return d


def _dash_page(page, name, title, intro, panels_html, data_json, js_body):
    body = f"""
<div class='card'>{intro}</div>
{panels_html}
<script src="chart.umd.js"></script>
<script>window.D = {data_json};</script>
<script>{DASH_JS}\n{js_body}</script>
<style>{DASH_CSS}</style>"""
    page(name, title, body)


def _records(df, cols=None):
    df = df if cols is None else df[cols]
    return json.dumps(json.loads(df.to_json(orient="records")), default=str)


# ------------------------------------------------------------------ funding
def build_funding(page, d):
    pre = d["prearranged"].copy()
    pre["hz"] = pre["hazard"].map(haz)
    cur = d["current"]
    reg_map = dict(zip(zip(d["current"]["country_iso3"], d["current"]["hazard"]),
                       d["current"]["region"]))
    pre["region"] = [reg_map.get((c, h)) or "?" for c, h in
                     zip(pre["country_iso3"], pre["hazard"])]
    act = d["activation"].copy()
    act["hz"] = act["hazard"].map(haz)
    ver = d["versions"].copy()
    ver["year"] = pd.to_datetime(ver["valid_from"]).dt.year
    gho = d["gho"]
    gho_set = set(map(tuple, gho.loc[gho["in_gho"], ["country_iso3", "year"]].values))
    pre["in_gho"] = [
        (c, y) in gho_set for c, y in zip(pre["country_iso3"], pre["year"])]
    act["year"] = act["event_date"].str[:4].astype(int)
    act["in_gho"] = [
        (c, y) in gho_set for c, y in zip(act["country_iso3"], act["year"])]

    n_active = int((cur["status"].isin(["active", "activated_implementing"])).sum())
    total_pre = pre.loc[(pre["kind"] == "prearranged") & (pre["year"] == 2026)
                        & (pre["fund_code"] != "all"), "amount_usd"].sum()
    total_disb = act["amount_usd"].sum()
    covered = d["covered"]["people_covered"].sum()

    panels = f"""
<div class='tiles'>
 <div class='tile'><div class='v'>{n_active}</div><div class='l'>active frameworks (of {len(cur)} tracked)</div></div>
 <div class='tile'><div class='v'>${total_pre/1e6:,.0f}M</div><div class='l'>pre-arranged 2026 (canonical)</div></div>
 <div class='tile'><div class='v'>${total_disb/1e6:,.0f}M</div><div class='l'>AA/EA disbursed 2020–2026 (all funds)</div></div>
 <div class='tile'><div class='v'>{covered/1e6:,.1f}M</div><div class='l'>people covered (latest per framework)</div></div>
</div>
<div class='fbar'>
 <label>Hazard <select id='fHaz'><option value=''>all</option></select></label>
 <label>Region <select id='fReg'><option value=''>all</option></select></label>
 <label>GHO <select id='fGho'><option value=''>all</option><option value='1'>GHO contexts only</option></select></label>
 <label><input type='checkbox' id='fCum'> cumulative</label>
</div>
<div class='grid'>
 <div class='panel'><h3>Pre-arranged funding by year × fund</h3><canvas id='c1' height='260'></canvas>
   <div class='note'>Canonical source per framework-year (latest CERF sheet wins); 'all'-totals excluded where components exist. Co-financing shown separately below.</div></div>
 <div class='panel'><h3>AA/EA disbursed by year × fund</h3><canvas id='c2' height='260'></canvas>
   <div class='note'>Activation funding rows (framework + ad-hoc + EA), all pooled funds.</div></div>
 <div class='panel'><h3>Pre-arranged by hazard (2026)</h3><canvas id='c3' height='260'></canvas></div>
 <div class='panel'><h3>Pre-arranged by region (2026)</h3><canvas id='c4' height='260'></canvas></div>
 <div class='panel'><h3>Framework versions endorsed/revised per year</h3><canvas id='c5' height='260'></canvas>
   <div class='note'>One bar segment per version registered that year (endorsed docs; a version = an endorsed document).</div></div>
 <div class='panel'><h3>Co-financing & non-OCHA money</h3><canvas id='c6' height='260'></canvas>
   <div class='note'>kind = cofinancing / non_aa_mobilised; financier mostly uncurated — amounts only.</div></div>
</div>"""

    data = {
        "pre": json.loads(_records(pre, ["country_iso3", "hz", "region", "year",
                                         "kind", "fund_code", "amount_usd",
                                         "in_gho"])),
        "act": json.loads(_records(act, ["country_iso3", "hz", "region", "year",
                                         "fund_code", "amount_usd", "event_type",
                                         "in_gho"])),
        "ver": json.loads(_records(ver, ["year", "kb_status"])),
    }
    js = """
function fundType(fc){ return fc==='cerf'?'cerf':(fc||'').startsWith('rhpf')?'regional_fund':'cbpf'; }
function draw(){
  const hz=fHaz.value, rg=fReg.value, gho=fGho.value, cum=fCum.checked;
  const P = D.pre.filter(r=>r.kind==='prearranged' && r.fund_code!=='all'
      && (!hz||r.hz===hz) && (!rg||r.region===rg) && (!gho||r.in_gho));
  const A = D.act.filter(r=>(!hz||r.hz===hz)&&(!rg||r.region===rg)&&(!gho||r.in_gho));
  const years = uniqSorted(P.concat(A), r=>r.year);
  for(const [id, rows, kf] of [['c1',P,r=>fundType(r.fund_code)],['c2',A,r=>fundType(r.fund_code)]]){
    const ds = ['cerf','cbpf','regional_fund'].map(ft=>{
      let vals = years.map(y=>groupSum(rows.filter(r=>kf(r)===ft&&r.year===y),()=>0,r=>r.amount_usd)[0]||0);
      if(cum) vals = cumulate(vals);
      return {label:ft, data:vals, backgroundColor:FUND_COLORS[ft]};});
    mkChart(id,'bar',years,ds,{stacked:true});
  }
  const p26 = P.filter(r=>r.year===2026);
  const byH = groupSum(p26, r=>r.hz, r=>r.amount_usd);
  mkChart('c3','bar',Object.keys(byH),[{label:'pre-arranged',data:Object.values(byH),backgroundColor:PAL[0]}]);
  const byR = groupSum(p26, r=>r.region, r=>r.amount_usd);
  mkChart('c4','bar',Object.keys(byR),[{label:'pre-arranged',data:Object.values(byR),backgroundColor:PAL[0]}]);
  const vy = uniqSorted(D.ver.filter(r=>r.year), r=>r.year);
  mkChart('c5','bar',vy,[{label:'versions',data:vy.map(y=>D.ver.filter(r=>r.year===y).length),backgroundColor:PAL[2]}],{count:true});
  const C = D.pre.filter(r=>r.kind!=='prearranged'&&(!hz||r.hz===hz)&&(!rg||r.region===rg));
  const cy = uniqSorted(C, r=>r.year);
  mkChart('c6','bar',cy,['cofinancing','non_aa_mobilised'].map((k,i)=>({label:k,
    data:cy.map(y=>groupSum(C.filter(r=>r.kind===k&&r.year===y),()=>0,r=>r.amount_usd)[0]||0),
    backgroundColor:PAL[i+3]})),{stacked:true});
}
uniqSorted(D.pre,r=>r.hz).forEach(h=>fHaz.add(new Option(h,h)));
uniqSorted(D.pre,r=>r.region).forEach(r=>fReg.add(new Option(r,r)));
[fHaz,fReg,fGho,fCum].forEach(el=>el.addEventListener('change',draw));
draw();"""
    _dash_page(page, "dash-funding.html", "Funding dashboard",
               "Pre-arranged and disbursed AA funding across CERF, CBPFs and "
               "regional funds — filter by hazard, region, GHO context; toggle "
               "cumulative. Answers the funding rows of the CERF key-data-points "
               "list (see <a href='questions.html'>coverage</a>).",
               panels, json.dumps(data, default=str), js)


# ------------------------------------------------------------- allocations
def build_allocations(page, d):
    al = d["alloc"].copy()
    act = d["activation"].copy()
    act["year"] = act["event_date"].str[:4].astype(int)
    tim = d["timeliness"]

    panels = f"""
<div class='fbar'>
 <label>Fund <select id='fFund'><option value=''>all</option></select></label>
 <label>Country <select id='fC'><option value=''>all</option></select></label>
 <label>Year ≥ <select id='fY1'></select></label>
 <label>Year ≤ <select id='fY2'></select></label>
 <label>AA <select id='fAA'><option value='1' selected>AA only</option><option value=''>all allocations</option></select></label>
 <label>Search <input id='fQ' class='filter' style='width:200px;margin:0' placeholder='title…'></label>
</div>
<div class='tiles'><div class='tile'><div class='v' id='tN'>–</div><div class='l'>allocations</div></div>
 <div class='tile'><div class='v' id='tUsd'>–</div><div class='l'>total USD</div></div></div>
<div class='grid'>
 <div class='panel'><h3>Allocations by year × fund type</h3><canvas id='a1' height='240'></canvas></div>
 <div class='panel'><h3>Top countries</h3><canvas id='a2' height='240'></canvas></div>
 <div class='panel' style='grid-column:1/-1'><h3>CERF ↔ CBPF/RhPF complementarity (AA activations)</h3><canvas id='a3' height='240'></canvas>
   <div class='note'>Per activation event: countries funded by more than one pooled fund at once appear in both series (from aa.activation_funding).</div></div>
 <div class='panel'><h3>Non-framework AA (ad-hoc) by country</h3><canvas id='a4' height='240'></canvas></div>
 <div class='panel'><h3>Timeliness: ERC endorsement → first project approved (AA, days)</h3><canvas id='a5' height='240'></canvas>
   <div class='note'>From the CERF mirror; activation→endorsement lag needs curated activation datetimes (sheet-era dates are month-grain).</div></div>
</div>
<h2>Allocation table</h2>
<section><div style='display:flex;gap:10px;align-items:center'>
<input class='filter' placeholder='filter rows…' oninput='filt(this)'>
<button class='dl' onclick='dlFiltered()'>⬇ CSV (current filter)</button></div>
<div class='scroll'><table class='data' id='tbl'><thead><tr>
<th>fund</th><th>code</th><th>country</th><th>year</th><th>USD</th><th>AA</th><th>title</th>
</tr></thead><tbody></tbody></table></div></section>"""

    data = {
        "al": json.loads(_records(al)),
        "act": json.loads(_records(act, ["country_iso3", "hazard", "event_type",
                                         "year", "fund_code", "amount_usd"])),
        "tim": json.loads(_records(tim, ["year", "days"])),
    }
    js = """
function fundType(fc){ return fc==='cerf'?'cerf':(fc||'').startsWith('rhpf')?'regional_fund':'cbpf'; }
const YEARS = uniqSorted(D.al, r=>r.year);
YEARS.forEach(y=>{fY1.add(new Option(y,y)); fY2.add(new Option(y,y));});
fY1.value = 2020; fY2.value = YEARS[YEARS.length-1];
uniqSorted(D.al, r=>r.fund_type).forEach(f=>fFund.add(new Option(f,f)));
uniqSorted(D.al, r=>r.country_iso3).forEach(c=>fC.add(new Option(c,c)));
function rows(){ const q = fQ.value.toLowerCase();
  return D.al.filter(r=> (!fFund.value||r.fund_type===fFund.value)
    && (!fC.value||r.country_iso3===fC.value)
    && r.year>=+fY1.value && r.year<=+fY2.value
    && (!fAA.value||r.is_aa)
    && (!q||(r.title||'').toLowerCase().includes(q))); }
function draw(){ const R = rows();
  tN.textContent = R.length.toLocaleString();
  tUsd.textContent = money(R.reduce((s,r)=>s+(r.amount_usd||0),0));
  const ys = uniqSorted(R, r=>r.year);
  mkChart('a1','bar',ys,['cerf','cbpf','regional_fund'].map(ft=>({label:ft,
    data:ys.map(y=>R.filter(r=>r.fund_type===ft&&r.year===y).reduce((s,r)=>s+(r.amount_usd||0),0)),
    backgroundColor:FUND_COLORS[ft]})),{stacked:true});
  const byC = Object.entries(groupSum(R,r=>r.country_iso3||r.fund_name,r=>r.amount_usd))
    .sort((a,b)=>b[1]-a[1]).slice(0,15);
  mkChart('a2','bar',byC.map(x=>x[0]),[{label:'USD',data:byC.map(x=>x[1]),backgroundColor:PAL[0]}],
    {extra:{indexAxis:'y'}});
  const multi = {};
  D.act.forEach(r=>{ const k=r.country_iso3; (multi[k]??={cerf:0,pooled:0});
    multi[k][fundType(r.fund_code)==='cerf'?'cerf':'pooled'] += r.amount_usd||0; });
  const both = Object.entries(multi).filter(([,v])=>v.cerf&&v.pooled)
    .sort((a,b)=>(b[1].cerf+b[1].pooled)-(a[1].cerf+a[1].pooled));
  mkChart('a3','bar',both.map(x=>x[0]),
    [{label:'CERF',data:both.map(x=>x[1].cerf),backgroundColor:FUND_COLORS.cerf},
     {label:'CBPF/RhPF',data:both.map(x=>x[1].pooled),backgroundColor:FUND_COLORS.cbpf}]);
  const adhoc = D.act.filter(r=>r.event_type!=='framework_aa');
  const byA = Object.entries(groupSum(adhoc,r=>r.country_iso3,r=>r.amount_usd)).sort((a,b)=>b[1]-a[1]);
  mkChart('a4','bar',byA.map(x=>x[0]),[{label:'ad-hoc AA + EA USD',data:byA.map(x=>x[1]),backgroundColor:PAL[3]}]);
  const ty = uniqSorted(D.tim,r=>r.year);
  mkChart('a5','line',ty,[{label:'median days',data:ty.map(y=>{
    const v=D.tim.filter(r=>r.year===y).map(r=>r.days).sort((a,b)=>a-b);
    return v.length?v[Math.floor(v.length/2)]:null;}),backgroundColor:PAL[0]}],{count:true});
  const tb = document.querySelector('#tbl tbody');
  tb.innerHTML = R.slice(0,600).map(r=>`<tr><td>${r.fund_type}</td><td>${r.allocation_code}</td>
    <td>${r.country_iso3??r.fund_name??''}</td><td>${r.year??''}</td><td>${money(r.amount_usd)}</td>
    <td>${r.is_aa?'✓':''}</td><td>${r.title??''}</td></tr>`).join('');
}
function dlFiltered(){ const R = rows();
  const cols = ['fund_type','fund_name','allocation_code','country_iso3','year','amount_usd','is_aa','title'];
  const esc = v => v==null ? '' : /[",\\n]/.test(String(v)) ? '"'+String(v).replace(/"/g,'""')+'"' : String(v);
  const csv = [cols.join(',')].concat(R.map(r=>cols.map(c=>esc(r[c])).join(','))).join('\\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv],{type:'text/csv'}));
  a.download = 'allocations_filtered.csv'; a.click(); URL.revokeObjectURL(a.href); }
[fFund,fC,fY1,fY2,fAA].forEach(el=>el.addEventListener('change',draw));
fQ.addEventListener('input',draw);
draw();"""
    _dash_page(page, "dash-allocations.html", "Allocation explorer",
               "Query the full historical allocation universe — every CERF "
               "application (2006→) and every CBPF/RhPF allocation envelope — with "
               "the AA lens on by default. Complementarity and non-framework AA "
               "views come from the activation record.",
               panels, json.dumps(data, default=str), js)


# ------------------------------------------------------------------ delivery
def build_delivery(page, d):
    sg = d["subgrant"]
    cb = d["cbpf_proj"]
    sec = d["sector"]
    ag = d["agency"]
    ps = d["pre_sector"]
    cva = d["cva"]
    rc = d["reached"]

    panels = """
<div class='grid'>
 <div class='panel'><h3>CERF AA subgrants by partner type × year</h3><canvas id='d1' height='250'></canvas>
   <div class='note'>Yakubu's curated AA subgrant set; local = NNGO+GOV+RedC per his localization tagging.</div></div>
 <div class='panel'><h3>CBPF AA projects: direct funding by org type</h3><canvas id='d2' height='250'></canvas>
   <div class='note'>CBPF pays partners directly — this is the localization view CERF can't show. AA-keyword allocations only.</div></div>
 <div class='panel'><h3>Disbursed by agency (CERF AA projects)</h3><canvas id='d3' height='250'></canvas></div>
 <div class='panel'><h3>Disbursed by sector (CERF AA projects)</h3><canvas id='d4' height='250'></canvas></div>
 <div class='panel'><h3>Pre-arranged by agency (framework budgets)</h3><canvas id='d5' height='250'></canvas>
   <div class='note'>From the Jun-2026 pre-arranged sector budgets (framework docs).</div></div>
 <div class='panel'><h3>Pre-arranged by sector (framework budgets)</h3><canvas id='d6' height='250'></canvas></div>
 <div class='panel'><h3>AA delivered as CVA by year</h3><canvas id='d7' height='250'></canvas>
   <div class='note'>cerf_cva_history (2020–2026 CERF AA); project-level markers exist for 2024+ in cerf_project_supplement.</div></div>
 <div class='panel'><h3>People reached by gender × year (CERF AA)</h3><canvas id='d8' height='250'></canvas>
   <div class='note'>Reached figures lag ~9 months (final reports); recent years undercount.</div></div>
</div>"""

    data = {
        "sg": json.loads(_records(sg[sg["is_aa"]],
                                  ["year", "partner_type", "localization",
                                   "subgrant_usd"])),
        "cb": json.loads(_records(cb[cb["aa_keyword"] == True],  # noqa: E712
                                  ["year", "org_type", "budget"])),
        "sec": json.loads(_records(sec)),
        "ag": json.loads(_records(ag)),
        "ps": json.loads(_records(ps, ["agency", "sector", "amount_usd"])),
        "cva": json.loads(_records(cva, ["year", "cva_usd"])),
        "rc": json.loads(_records(rc, ["year", "grp", "value"])),
    }
    js = """
const PT = ['NNGO','INGO','GOV','RedC'];
const sgY = uniqSorted(D.sg, r=>r.year);
mkChart('d1','bar',sgY,PT.map((t,i)=>({label:t,
  data:sgY.map(y=>groupSum(D.sg.filter(r=>r.partner_type===t&&r.year===y),()=>0,r=>r.subgrant_usd)[0]||0),
  backgroundColor:PAL[i]})),{stacked:true});
const cbY = uniqSorted(D.cb, r=>r.year);
const OT = ['National NGO','International NGO','UN Agency','Others'];
mkChart('d2','bar',cbY,OT.map((t,i)=>({label:t,
  data:cbY.map(y=>groupSum(D.cb.filter(r=>r.org_type===t&&r.year===y),()=>0,r=>r.budget)[0]||0),
  backgroundColor:PAL[i]})),{stacked:true});
for(const [id, rows, kf, vf] of [
   ['d3', D.ag, r=>r.agency, r=>r.amount_approved],
   ['d4', D.sec, r=>r.sector, r=>r.sector_amount],
   ['d5', D.ps, r=>r.agency, r=>r.amount_usd],
   ['d6', D.ps, r=>r.sector, r=>r.amount_usd]]){
  const g = Object.entries(groupSum(rows,kf,vf)).sort((a,b)=>b[1]-a[1]).slice(0,14);
  mkChart(id,'bar',g.map(x=>x[0]),[{label:'USD',data:g.map(x=>x[1]),backgroundColor:PAL[0]}],
    {extra:{indexAxis:'y'}});
}
const cvY = uniqSorted(D.cva,r=>r.year);
mkChart('d7','bar',cvY,[{label:'CVA USD',data:cvY.map(y=>groupSum(D.cva.filter(r=>r.year===y),()=>0,r=>r.cva_usd)[0]||0),backgroundColor:PAL[4]}]);
const rcY = uniqSorted(D.rc,r=>r.year);
mkChart('d8','bar',rcY,[['women',0],['men',1],['girls',2],['boys',3]].map(([g,i])=>({label:g,
  data:rcY.map(y=>groupSum(D.rc.filter(r=>r.grp===g&&r.year===y),()=>0,r=>r.value)[0]||0),
  backgroundColor:PAL[i]})),{stacked:true,count:true});"""
    _dash_page(page, "dash-delivery.html", "Delivery, partners & people",
               "Who the money flows through and who it reaches: subgrants and "
               "localization (CERF AA), direct partner funding (CBPF AA), agency "
               "and sector splits (disbursed vs pre-arranged), CVA, and people "
               "reached by gender.",
               panels, json.dumps(data, default=str), js)


# ------------------------------------------------------------------ questions
COVERAGE = [
    ("Pre-arranged funding by year, cumulative", "covered", "dash-funding.html", "canonical per framework-year; cumulative toggle"),
    ("Pre-arranged by hazard / region", "covered", "dash-funding.html", ""),
    ("AA amount disbursed by year, cumulative", "covered", "dash-funding.html", "all pooled funds via activation_funding"),
    ("Subgrants by partner type / local partners", "covered", "dash-delivery.html", "CERF AA subgrants + CBPF direct org-type funding"),
    ("Disbursed funds by agency", "covered", "dash-delivery.html", "CERF AA projects"),
    ("Disbursed funds by sector", "covered", "dash-delivery.html", "CERF AA project sector splits"),
    ("Pre-arranged funds by agency / sector", "covered", "dash-delivery.html", "Jun-2026 framework budgets; KB funding_breakdown adds per-version detail"),
    ("Agency participation across the portfolio", "covered", "dash-delivery.html", "agency axis of pre-arranged budgets"),
    ("AA delivered as CVA", "partial", "dash-delivery.html", "totals by year 2020–2026; MPC-vs-sector split only for 2024+ projects (cerf_project_supplement)"),
    ("People covered", "partial", "dash-funding.html", "per framework (latest); by CATEGORY of people not tracked anywhere"),
    ("People reached by gender, by year", "covered", "dash-delivery.html", "CERF AA final reports; ~9-month lag"),
    ("Co-funding amount and source", "partial", "dash-funding.html", "amounts yes; financier mostly uncurated free text"),
    ("Calendar of monitoring windows", "covered", "dashboards.html#calendar", "trigger-window months per framework (from planning-sheet colors)"),
    ("Filter by hazard", "covered", "dash-funding.html", "all dashboards filter by hazard"),
    ("Frameworks started/revised/endorsed per year", "covered", "dash-funding.html", "endorsed-document versions per year"),
    ("Non-framework AA allocations", "covered", "dash-allocations.html", "explicit adhoc_aa / early_action categories"),
    ("CERF + Country/Regional Funds complementarity", "covered", "dash-allocations.html", "multi-fund activations from activation_funding"),
    ("AA funding to GHO contexts", "covered", "dash-funding.html", "GHO filter (plan_inclusion)"),
    ("CERF AA growth (disbursed, people, countries…)", "covered", "dash-funding.html", "cumulative toggles + tiles"),
    ("Timeliness (activation → approval letters)", "partial", "dash-allocations.html", "ERC endorsement → first project approved works; trigger-date lag needs curated activation datetimes"),
    ("Partner participation beyond CERF (Start, RCRC, WB…)", "missing", "", "only Start Fund alert counts (start_network); no systematic non-OCHA partner data"),
    ("Activities repository", "missing", "", "not tracked anywhere yet — would need framework-doc activity extraction"),
    ("Endorsement and activation dates", "covered", "dashboards.html#frameworks", "framework_version + activation (dates as precise as known)"),
    ("Framework versions", "covered", "table-framework_version.html", "65+ versions incl. the historical sweep, with doc links"),
]


def build_questions(page):
    rows = "\n".join(
        f"<tr><td>{q}</td><td class='{cls}'>{cls.upper()}</td>"
        f"<td>{f'<a href={link!r}>{link.split(chr(46))[0]}</a>' if link else '—'}</td>"
        f"<td>{note}</td></tr>"
        for q, cls, link, note in COVERAGE)
    n_cov = sum(1 for _, c, _, _ in COVERAGE if c == "covered")
    n_par = sum(1 for _, c, _, _ in COVERAGE if c == "partial")
    body = f"""
<div class='card'>Item-by-item coverage of the CERF <b>"AA Datasets — key data
points"</b> deck (Oct 2025, updated Aug 2026): {n_cov} covered · {n_par} partial ·
{len(COVERAGE) - n_cov - n_par} missing. The deck's own diagnosis — Excel doesn't
scale and the Power BI view mistags allocations — is what this system replaces.</div>
<section><div class='scroll'><table class='data'><thead>
<tr><th>Key data point (deck)</th><th>status</th><th>where</th><th>notes</th></tr>
</thead><tbody>{rows}</tbody></table></div></section>
<style>{DASH_CSS}</style>"""
    page("questions.html", "CERF key-data-points coverage", body)


# ------------------------------------------------------------------ hub + frameworks
MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]


def _cal_strip(cal, c, h):
    on = set(cal.loc[(cal["country_iso3"] == c) & (cal["hazard"] == h), "month"])
    cells = "".join(f"<td class='{'on' if m in on else ''}'>{MONTHS[m-1]}</td>"
                    for m in range(1, 13))
    return f"<table class='cal'><tr>{cells}</tr></table>"


def build_framework_pages(page, tbl, d):
    cur, ver, act = d["current"], d["versions"], d["activation"]
    pre, cov, foc = d["prearranged"], d["covered"], d["focal"]
    ps, rep, cal = d["pre_sector"], d["report"], d["calendar"]
    links = []
    for _, fw in cur.sort_values("country_name").iterrows():
        c, h = fw["country_iso3"], fw["hazard"]
        slug = f"fw-{c.lower()}-{h}"
        links.append((fw["country_name"], h, fw["status"], slug, c))
        v = ver[(ver["country_iso3"] == c) & (ver["hazard"] == h)]
        a = act[(act["country_iso3"] == c) & (act["hazard"] == h)]
        p = pre[(pre["country_iso3"] == c) & (pre["hazard"] == h)
                & (pre["kind"] == "prearranged") & (pre["fund_code"] != "all")]
        f = foc[(foc["country_iso3"] == c) & (foc["hazard"] == h)]
        s = ps[(ps["country_iso3"] == c) & (ps["hazard"] == h)]
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
        vrows = "".join(
            f"<tr><td>{x.version}</td><td>{x.kb_status if pd.notna(x.kb_status) else ''}</td><td>{x.source}</td>"
            f"<td>{f'<a href={x.doc_url!r}>doc</a>' if pd.notna(x.doc_url) else ''}</td>"
            f"<td style='max-width:340px'>{x.analysis_ref if pd.notna(x.analysis_ref) else ''}</td></tr>"
            for x in v.itertuples())
        # one line per ACTIVATION; multi-fund events combine their funding rows
        arows = ""
        for (ed, et), g in a.sort_values("event_date").groupby(
                ["event_date", "event_type"], sort=True):
            first = g.iloc[0]
            funding = "<br>".join(
                f"{x.fund_code}: "
                + ("" if pd.isna(x.amount_usd) else f"${x.amount_usd:,.0f}")
                + (f" ({x.allocation_code})" if pd.notna(x.allocation_code) else "")
                for x in g.itertuples())
            total = g["amount_usd"].sum()
            pt = g["people_targeted"].max()
            arows += (
                f"<tr><td>{ed}</td><td>{et}</td>"
                f"<td>{first['window_name'] if pd.notna(first['window_name']) else ''}</td>"
                f"<td>{funding}</td>"
                f"<td>{'' if not total else f'${total:,.0f}'}</td>"
                f"<td>{'' if pd.isna(pt) else f'{int(pt):,}'}</td></tr>")
        frows = "".join(f"<span class='badge b-kb'>{x.role}: {x.person}</span>"
                        for x in f.itertuples())
        srows = "".join(
            f"<tr><td>{x.window_name or ''}</td><td>{x.agency}</td><td>{x.sector}</td>"
            f"<td>${x.amount_usd:,.0f}</td></tr>" for x in s.itertuples())
        rrows = ", ".join(sorted({f"{x.channel} ({x.report_year})"
                                  for x in r.itertuples()}))
        covered_txt = (f"{int(pc['people_covered'].iloc[0]):,}"
                       if not pc.empty else "—")
        obs = fw.get("observed_status")
        derived_note = (
            f" <span class='muted' style='font-size:11px'>(derived from the endorsed "
            f"{fw['current_version']} version — sheets last said “{str(obs).replace('_', ' ')}”)</span>"
            if pd.notna(obs) and obs != fw["status"] else "")
        body = f"""
<div class='card'><b>{fw['country_name']} — {h}</b> ·
<span class='badge b-new'>{fw['status'] or 'no status'}</span>{derived_note}
current version: <code>{fw['current_version'] or '—'}</code>
{('· KB: <code>' + fw['kb_framework'] + '</code>') if pd.notna(fw['kb_framework']) else '· not in KB'}
· people covered: <b>{covered_txt}</b><br>
Monitoring window: {_cal_strip(cal, c, h)}
<div style='margin-top:6px'>{frows}</div></div>
<div class='grid'>
<div class='panel'><h3>Pre-arranged funding by year × fund</h3><canvas id='pf' height='230'></canvas></div>
<div class='panel'><h3>Versions (endorsed documents)</h3>
<div class='scroll' style='max-height:230px'><table class='data'><thead>
<tr><th>version</th><th>KB status</th><th>source</th><th>doc</th><th>analysis</th></tr></thead>
<tbody>{vrows or '<tr><td colspan=5>none registered</td></tr>'}</tbody></table></div></div>
</div>
<h2>Activations</h2>
<section><div class='scroll'><table class='data'><thead>
<tr><th>date</th><th>type</th><th>window</th><th>funding (fund: USD, allocation)</th><th>total USD</th><th>targeted</th></tr>
</thead><tbody>{arows or '<tr><td colspan=7>none recorded</td></tr>'}</tbody></table></div></section>
<h2>Pre-arranged sector budgets</h2>
<section><div class='scroll' style='max-height:320px'><table class='data'><thead>
<tr><th>window</th><th>agency</th><th>sector</th><th>USD</th></tr></thead>
<tbody>{srows or '<tr><td colspan=4>none</td></tr>'}</tbody></table></div></section>
<p class='meta'>Counted in reports: {rrows or '—'}</p>
<script src="chart.umd.js"></script>
<script>window.FD = {json.dumps(chart_data)};</script>
<script>{DASH_JS}
const ds = Object.entries(FD.series).map(([fc,vals],i)=>({{label:fc,data:vals,
  backgroundColor:FUND_COLORS[fc==='cerf'?'cerf':(fc.startsWith('rhpf')?'regional_fund':'cbpf')]||PAL[i]}}));
if(FD.years.length) mkChart('pf','bar',FD.years,ds,{{stacked:true}});
else document.getElementById('pf').outerHTML='<p class="meta">no funding rows</p>';
</script>
<style>{DASH_CSS}</style>"""
        page(f"{slug}.html", f"{fw['country_name']} {h} — framework", body)
    return links


def build_hub(page, d, fw_links):
    cal = d["calendar"]
    fw_items = "".join(
        f"<tr><td><a href='{slug}.html'>{name} — {hz}</a></td><td>{status or ''}</td>"
        f"<td>{_cal_strip(cal, iso3, hz)}</td></tr>"
        for name, hz, status, slug, iso3 in fw_links)
    body = f"""
<div class='card'><b>Dashboards</b> — interactive views over the tracking DB,
built to the CERF key-data-points list (<a href='questions.html'>coverage map</a>).
<div class='tiles'>
<div class='tile'><a href='dash-funding.html'><b>Funding</b></a><div class='l'>pre-arranged & disbursed, by year/hazard/region/fund, GHO, cumulative</div></div>
<div class='tile'><a href='dash-allocations.html'><b>Allocation explorer</b></a><div class='l'>query every CERF + CBPF allocation 2006→; complementarity; timeliness</div></div>
<div class='tile'><a href='dash-delivery.html'><b>Delivery & people</b></a><div class='l'>subgrants, localization, agencies, sectors, CVA, people reached</div></div>
</div></div>
<h2 id='frameworks'>Per-framework pages</h2>
<p class='meta' id='calendar'>Green cells = trigger-window months (monitoring calendar).</p>
<section><input class='filter' placeholder='filter frameworks…' oninput='filt(this)'>
<div class='scroll'><table class='data'><thead><tr><th>framework</th><th>status</th><th>monitoring window</th></tr></thead>
<tbody>{fw_items}</tbody></table></div></section>
<style>{DASH_CSS}</style>"""
    page("dashboards.html", "Dashboards", body)




# ------------------------------------------------------------------ hierarchy
HIER_CSS = """
.tree details.fw { background:#fff; border:1px solid #dfe4ea; border-radius:8px;
  padding:6px 16px 10px; margin:10px 0; }
.tree details.ver { border-left:3px solid #e3e8ef; padding-left:14px; margin:8px 0 8px 8px; }
.tree summary { cursor:pointer; padding:6px 2px; list-style:none; }
.tree summary::before { content:'▸'; color:#8a97a8; font-size:12px; margin-right:8px;
  display:inline-block; transition:transform .12s; }
.tree details[open] > summary::before { transform:rotate(90deg); }
.tree summary:hover { background:#f4f7fa; border-radius:5px; }
.fw-line { display:inline-grid; grid-template-columns:300px 150px 110px 130px 110px;
  gap:8px; align-items:baseline; width:calc(100% - 30px); }
.fw-line .nm { font-weight:700; font-size:14px; }
.ver-line { display:inline-grid; grid-template-columns:150px 110px 130px auto;
  gap:8px; align-items:baseline; width:calc(100% - 30px); }
.ver-line .nm { font-weight:650; font-size:13px; font-family:ui-monospace,monospace; }
.muted { color:#667; font-size:12px; } .num { font-size:12.5px; color:#334; }
.st { display:inline-block; padding:0 8px; border-radius:9px; font-size:11px;
  font-weight:600; }
.st-on { background:#e3f1e6; color:#1c6b31; } .st-off { background:#ededed; color:#777; }
.st-dev { background:#fdf1dc; color:#8a5c0a; }
table.mini { border-collapse:collapse; font-size:12px; margin:6px 0 10px; background:#fff; }
table.mini th { text-align:left; font-weight:600; color:#556; background:#f4f6f9;
  padding:3px 10px; border:1px solid #e6eaef; white-space:nowrap; }
table.mini td { padding:3px 10px; border:1px solid #e6eaef; vertical-align:top; }
table.mini td.lbl { color:#667; white-space:nowrap; width:110px; background:#fafbfc; }
table.mini a { color:#1d5aa8; }
.hier-tools { display:flex; gap:10px; margin:12px 0; align-items:center; }
.hier-tools button { padding:5px 12px; border:1px solid #bbb; border-radius:5px;
  background:#fff; cursor:pointer; font-size:12.5px; }
h4.sect { font-size:11.5px; text-transform:uppercase; letter-spacing:.04em;
  color:#778; margin:10px 0 2px; }
"""


def _fmt_usd(v):
    if v is None or pd.isna(v):
        return ""
    v = float(v)
    return f"${v/1e6:.1f}M" if v >= 1e6 else f"${v/1e3:.0f}k" if v >= 1e3 else f"${v:.0f}"


def _st(status, kind="fw"):
    if status is None or pd.isna(status):
        return ""
    cls = ("st-on" if status in ("active", "activated_implementing", "endorsed")
           else "st-dev" if ("development" in status or "conversation" in status
                            or status == "under_revision")
           else "st-off")
    return f"<span class='st {cls}'>{status.replace('_', ' ')}</span>"


def _kb_trigger_info():
    """Structured trigger info per (kb_framework, version) from KB page frontmatter."""
    import re

    import yaml

    from ds_aa_tracking.versions import KB_DIR

    out = {}
    for pg in KB_DIR.glob("frameworks/*/[0-9]*.md"):
        m = re.match(r"^---\n(.*?)\n---", pg.read_text(), re.DOTALL)
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1))
        except yaml.YAMLError:
            continue
        tf = fm.get("trigger_facets") or {}
        mp = fm.get("monitoring_period") or {}
        bits = []
        if tf.get("basis"):
            bits.append(str(tf["basis"]))
        if tf.get("indicators"):
            bits.append(", ".join(map(str, tf["indicators"])))
        months = mp.get("months") or []
        if months:
            names = "JFMAMJJASOND"
            bits.append("monitored " + "".join(names[m - 1] for m in months
                                               if isinstance(m, int) and 1 <= m <= 12))
        if bits:
            out[(fm.get("framework"), str(fm.get("version")))] = " · ".join(bits)
    return out


def build_hierarchy(page, d, e):
    cur = d["current"]
    ver = pd.read_sql(
        """SELECT * FROM aa.framework_version
           ORDER BY country_iso3, hazard, valid_from NULLS LAST""", e)
    win = pd.read_sql(
        """SELECT w.country_iso3, w.hazard, w.version, w.window_name,
                  w.all_in, w.basis, w.allocation_usd,
                  p.n_activations AS sim_activations, p.analysis_years,
                  p.return_period, p.activation_prob
           FROM aa.window w
           LEFT JOIN aa.v_window_performance p
             USING (country_iso3, hazard, version, window_name)""", e)
    # browser-entered windows (entry.html → aa.entered_window): trigger statements,
    # basis and per-window funding; they enrich KB windows and add missing ones
    ew = pd.read_sql(
        """SELECT w.country_iso3, w.hazard, w.version, w.window_name,
                  w.basis AS basis_entered, w.trigger_statement,
                  f.amount_usd AS entered_usd
           FROM aa.entered_window w
           LEFT JOIN (SELECT country_iso3, hazard, version, window_name,
                             sum(amount_usd) AS amount_usd
                      FROM aa.entered_window_funding
                      GROUP BY country_iso3, hazard, version, window_name) f
             USING (country_iso3, hazard, version, window_name)""", e)
    if len(ew):
        win = win.merge(ew, on=["country_iso3", "hazard", "version", "window_name"],
                        how="outer")
        win["basis"] = win["basis"].where(win["basis"].notna(), win["basis_entered"])
        win["allocation_usd"] = win["allocation_usd"].where(
            win["allocation_usd"].notna(), win["entered_usd"])
    else:
        win["trigger_statement"] = None
    act = d["activation"]
    urls = pd.read_sql(
        "SELECT kb_framework, event_date, url FROM aa.actual_activation "
        "WHERE url IS NOT NULL", e)
    url_map = {(r["kb_framework"], r["event_date"]): r["url"]
               for _, r in urls.iterrows()}
    trig = _kb_trigger_info()
    focal = d["focal"]

    def windows_table(wins_v):
        if not len(wins_v):
            return ""
        rows = "".join(
            f"<tr><td>{w.window_name}</td>"
            f"<td>{w.basis if pd.notna(w.basis) else ''}"
            f"{' · all-in' if w.all_in is True else ''}</td>"
            f"<td>{_fmt_usd(w.allocation_usd)}</td>"
            f"<td>{f'{w.return_period:.1f} yr' if pd.notna(w.return_period) else ''}</td>"
            f"<td>{f'{w.activation_prob:.0%}' if pd.notna(w.activation_prob) else ''}</td>"
            f"<td>{f'{int(w.sim_activations)} in {int(w.analysis_years)} yrs' if pd.notna(w.sim_activations) else ''}</td></tr>"
            for w in wins_v.itertuples())
        trig_rows = "".join(
            f"<div class='hint' style='margin:2px 0'><b>{w.window_name}:</b> "
            f"{w.trigger_statement}</div>"
            for w in wins_v.itertuples()
            if pd.notna(getattr(w, "trigger_statement", None)))
        return ("<h4 class='sect'>Windows</h4>"
                "<table class='mini'><thead><tr><th>window</th><th>basis</th>"
                "<th>budget</th><th>return period</th><th>annual prob</th>"
                "<th>backtest</th></tr></thead><tbody>" + rows + "</tbody></table>"
                + trig_rows)

    def activations_table(acts_v, kb_fw):
        if not len(acts_v):
            return ""
        rows = []
        for ed, g in acts_v.groupby("event_date", sort=True):
            first = g.iloc[0]
            funding = "<br>".join(
                f"{r.fund_code}: {_fmt_usd(r.amount_usd) or '?'}"
                + (f" <span class='muted'>({r.allocation_code})</span>"
                   if pd.notna(r.allocation_code) else "")
                for r in g.itertuples())
            url = url_map.get((kb_fw, first.get("kb_event_date")))
            link = f"<a href='{url}'>announcement</a>" if url else ""
            targeted = (f"{int(first['people_targeted']):,}"
                        if pd.notna(first.get("people_targeted")) else "")
            wname = first.get("window_name")
            rows.append(
                f"<tr><td>{ed}</td><td>{first['event_type'].replace('_', ' ')}</td>"
                f"<td>{wname if pd.notna(wname) and wname != 'unspecified' else ''}</td>"
                f"<td>{funding}</td><td>{targeted}</td><td>{link}</td></tr>")
        return ("<h4 class='sect'>Activations</h4>"
                "<table class='mini'><thead><tr><th>date</th><th>type</th>"
                "<th>window</th><th>funding</th><th>people targeted</th><th>link</th>"
                "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")

    def ver_block(v, wins_v, acts_v, kb_fw):
        n_act = acts_v["event_date"].nunique() if len(acts_v) else 0
        head = (f"<span class='ver-line'><span class='nm'>{v.version}</span>"
                f"<span>{_st(v.kb_status)}</span>"
                f"<span class='num'>{_fmt_usd(v.prearranged_usd_doc)}</span>"
                f"<span class='muted'>"
                f"{f'{len(wins_v)} windows · ' if len(wins_v) else ''}"
                f"{f'{n_act} activation(s)' if n_act else ''}</span></span>")
        meta = []
        rng = " → ".join(str(x) for x in [v.valid_from, v.valid_until]
                         if x is not None and str(x) != "None")
        if rng:
            meta.append(("Valid", rng))
        if pd.notna(v.doc_url):
            meta.append(("Document", f"<a href='{v.doc_url}'>"
                         f"{v.doc_title if pd.notna(v.doc_title) else 'framework document'}</a>"))
        t = trig.get((kb_fw, v.version))
        if t:
            meta.append(("Trigger", t))
        if pd.notna(v.analysis_ref):
            meta.append(("Analysis", f"<code>{v.analysis_ref}</code>"))
        if pd.notna(v.endorsed_by):
            meta.append(("Endorsed by", v.endorsed_by))
        if pd.notna(v.supersedes) and str(v.supersedes) not in ("None", "null"):
            meta.append(("Supersedes", str(v.supersedes)))
        meta.append(("Source", v.source))
        meta_tbl = ("<table class='mini'>" + "".join(
            f"<tr><td class='lbl'>{k}</td><td>{val}</td></tr>" for k, val in meta)
            + "</table>")
        return (f"<details class='ver'><summary>{head}</summary>"
                f"{meta_tbl}{windows_table(wins_v)}{activations_table(acts_v, kb_fw)}"
                "</details>")

    blocks = []
    for _, fw in cur.sort_values("country_name").iterrows():
        c, h = fw["country_iso3"], fw["hazard"]
        kb_fw = fw.get("kb_framework") if pd.notna(fw.get("kb_framework")) else None
        vs = ver[(ver["country_iso3"] == c) & (ver["hazard"] == h)]
        acts_f = act[(act["country_iso3"] == c) & (act["hazard"] == h)]
        n_act = acts_f["event_date"].nunique()
        head = (f"<span class='fw-line'><span class='nm'>{fw['country_name']} — {h}</span>"
                f"<span>{_st(fw['status'])}</span>"
                f"<span class='num'>{_fmt_usd(fw.get('cerf_prearranged_usd'))}</span>"
                f"<span class='muted'>"
                f"{f'{int(fw.people_covered):,} covered' if pd.notna(fw.get('people_covered')) else ''}</span>"
                f"<span class='muted'>{f'{n_act} activation(s)' if n_act else ''}</span>"
                "</span>")
        meta = []
        if kb_fw:
            meta.append(("KB", f"<code>{kb_fw}</code>"))
        if pd.notna(fw.get("region")):
            meta.append(("Region", fw["region"]))
        fps = focal[(focal["country_iso3"] == c) & (focal["hazard"] == h)]
        if len(fps):
            meta.append(("Focal points", ", ".join(
                f"{r.person} <span class='muted'>({r.role.replace('_', ' ')})</span>"
                for r in fps.itertuples())))
        meta.append(("More", f"<a href='fw-{c.lower()}-{h}.html'>framework page</a>"))
        meta_tbl = ("<table class='mini'>" + "".join(
            f"<tr><td class='lbl'>{k}</td><td>{val}</td></tr>" for k, val in meta)
            + "</table>")
        inner = ""
        for v in vs.itertuples():
            wins_v = win[(win["country_iso3"] == c) & (win["hazard"] == h)
                         & (win["version"] == v.version)]
            acts_v = acts_f[acts_f["version"] == v.version]
            inner += ver_block(v, wins_v, acts_v, kb_fw)
        stray_f = acts_f[~acts_f["version"].isin(set(vs["version"]))]
        if len(stray_f):
            inner += ("<h4 class='sect'>Activations not attributed to a version</h4>"
                      + activations_table(stray_f, kb_fw))
        if not len(vs):
            inner += "<p class='muted'>No endorsed version anywhere yet — pipeline framework.</p>"
        blocks.append(
            f"<details class='fw' data-name='{fw['country_name'].lower()} {h}'>"
            f"<summary>{head}</summary>{meta_tbl}{inner}</details>")

    body = f"""
<div class='card'>The portfolio as a collapsible tree — <b>framework → version →
window → activation</b> — with everything the DB knows at each level: status and
funding, framework documents per version, structured trigger info (basis, indicators,
monitored months — from the KB pages; plain-text trigger statements land with the
window registry), per-window budgets and backtested return periods, and each
activation's fund-by-fund allocations with announcement links.</div>
<div class='hier-tools'>
 <input class='filter' placeholder='filter frameworks…' oninput='hfilter(this.value)'>
 <button onclick='setAll(true)'>expand all</button>
 <button onclick='setAll(false)'>collapse all</button>
</div>
<div class='tree'>{''.join(blocks)}</div>
<script>
function setAll(open){{ document.querySelectorAll('.tree details').forEach(d=>d.open=open); }}
function hfilter(q){{ q=q.toLowerCase();
  document.querySelectorAll('.tree > details').forEach(d=>{{
    d.style.display = d.dataset.name.includes(q) ? '' : 'none'; }}); }}
</script>
<style>{DASH_CSS}{HIER_CSS}</style>"""
    page("hierarchy.html", "Portfolio explorer — framework › version › window › activation", body)




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
the ingest merges entered values into the registry, and entered values win.
<a href='status.html'>Status updates</a> stay on their own page.</div>

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
    <option value='additive'>additive — all windows can fire; total = sum</option>
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
  <a class='btn-sec' id='kbbtn' href='#' target='_blank' style='display:none'>Draft KB page →</a>
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
    const kb = G.frameworks.find(f=>f.iso3===p.country_iso3 && f.hazard===p.hazard);
    out.innerHTML = `<div class='card' style='border-color:#1c6b31; background:#eef7f0'>
      <b>Saved.</b> ${res.changes} field change(s) written to <code>aa.entered_*</code>
      (${res.saved.windows} window(s), ${res.saved.window_funding} window-funding,
      ${res.saved.version_funding} fund-total row(s)), all audited as
      “${esc(p.entered_by)}”. Entered values merge into the registry
      (<code>aa.framework_version</code>) — entered wins; this site's static pages
      show it after the next publish.</div>`;
    const KBHAZ = {storm:'tropical-cyclone', flood:'flood', drought:'drought',
                   cholera:'cholera', plague:'plague', locusts:'locusts'};
    const kbBody = [`country: ${p.country_iso3}`, `hazard: ${KBHAZ[p.hazard]||p.hazard}`,
      `version: ${p.version}`, `doc: ${p.version_fields.doc_url||''}`,
      kb && kb.kb ? `slug: ${kb.kb}` : 'slug:', '', `title: ${p.version_fields.doc_title||''}`].join('\n');
    const kbbtn = document.getElementById('kbbtn');
    kbbtn.style.display = '';
    kbbtn.href = 'https://github.com/OCHA-DAP/ds-knowledge-base/issues/new?title=' +
      encodeURIComponent(`[ingest-doc] ${p.country_iso3}/${p.hazard} ${p.version}`) +
      '&body=' + encodeURIComponent(kbBody);
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
    redirect = ("<meta http-equiv='refresh' content='0; url=entry.html'>"
                "<p>Moved to <a href='entry.html'>entry.html</a>.</p>")
    page("ingest-doc.html", "Moved — framework data entry", redirect)
    page("form.html", "Moved — framework data entry", redirect)



# ------------------------------------------------------------------ status entry
STATUS_CARDS = [
    ("endorsed_live", "Endorsed — live & monitoring",
     "The framework document is endorsed, funds pre-arranged, triggers monitored. Not currently activated.", "active"),
    ("triggered", "Triggered — activation underway",
     "A trigger has been reached; the activation/allocation process is in motion.", "activated_implementing"),
    ("implementing", "Activated — implementing",
     "Funds released; agencies implementing anticipatory activities.", "activated_implementing"),
    ("post_activation", "Previously activated — back to monitoring",
     "Implementation finished; the framework returns to live monitoring (or awaits revision/refill).", "active"),
    ("under_revision", "Under revision",
     "An endorsed framework being revised/renewed; monitoring may pause.", "under_revision"),
    ("dormant", "Dormant / expired",
     "No current activity or validity lapsed with no successor.", "dormant"),
]


def build_status_form(page, d):
    cur = d["current"].sort_values("country_name")
    fw = [{"key": f"{r.country_iso3}|{r.hazard}",
           "label": f"{r.country_name} — {r.hazard}",
           "status": r.status if pd.notna(r.status) else None,
           "version": r.current_version if pd.notna(r.current_version) else None}
          for r in cur.itertuples()]
    cards = "".join(
        f"""<label class='scard'><input type='radio' name='st' value='{val}' data-key='{key}'>
        <div><b>{title}</b><div class='hint'>{desc}</div></div></label>"""
        for key, title, desc, val in STATUS_CARDS)
    body = f"""
<div class='card'><b>Framework status update (demo)</b> — the quick way to record
where a framework is in its lifecycle. One click per state; “Save” previews the
<code>aa.framework_status</code> row (nothing is written). Activation events
themselves are entered via the <a href='entry.html'>data entry page</a> — this page only moves the status.</div>
<div class='form-card'>
 <div class='frow'>
  <label>Framework <select id='fw' onchange='fwSel()'></select></label>
  <label>As of <input type='date' id='asof'></label>
 </div>
 <div id='cur' class='hint'></div>
 <div class='scards'>{cards}</div>
 <div class='frow'><label>Note <input id='note' style='min-width:420px'
   placeholder='e.g. Window 1 trigger reached 30 Apr; CERF letter pending'></label></div>
 <div class='frow'><button class='primary' onclick='save()'>Save (preview row)</button></div>
</div>
<pre id='payload' style='display:none'></pre>
<script>window.S = {json.dumps(fw)};</script>
<script>
S.forEach(f=>document.getElementById('fw').appendChild(new Option(f.label, f.key)));
document.getElementById('asof').valueAsDate = new Date();
function fwSel(){{
  const f = S.find(x=>x.key===document.getElementById('fw').value);
  document.getElementById('cur').innerHTML =
    `current status: <b>${{f.status||'—'}}</b> · current version: <code>${{f.version||'—'}}</code>`;
}}
function save(){{
  const f = S.find(x=>x.key===document.getElementById('fw').value);
  const sel = document.querySelector('input[name=st]:checked');
  const p = document.getElementById('payload');
  if(!sel){{ p.style.display='block'; p.textContent='pick a state first'; return; }}
  const [iso, hz] = f.key.split('|');
  p.style.display = 'block';
  p.textContent = JSON.stringify({{
    _dummy: 'no data written — row preview',
    'aa.framework_status (insert)': {{
      country_iso3: iso, hazard: hz,
      as_of: document.getElementById('asof').value,
      status: sel.value, status_raw: sel.closest('.scard').querySelector('b').textContent,
      version: f.version, version_match: 'entered',
      comments: document.getElementById('note').value || null,
      source: 'status-form' }},
    _previous_status: f.status,
  }}, null, 2);
}}
fwSel();
</script>
<style>{{DASH_CSS}}{{FORM_CSS}}
.scards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:10px; margin:12px 0; }}
.scard {{ display:flex; gap:10px; align-items:flex-start; border:1.5px solid #d8dee6;
  border-radius:8px; padding:12px 14px; cursor:pointer; }}
.scard:hover {{ border-color:#2a78d6; background:#f4f8fd; }}
.scard:has(input:checked) {{ border-color:#1c6b31; background:#eef7f0; }}
.scard input {{ margin-top:3px; }}
</style>"""
    body = body.replace("{DASH_CSS}", DASH_CSS).replace("{FORM_CSS}", FORM_CSS)
    page("status.html", "Framework status update (demo)", body)





# ------------------------------------------------------------------ landing
# The landing page (zoomable map -> country -> framework -> version) lives in
# scripts/landing.py; it reuses the frames fetched here.


def build_all(e, page, tbl):
    d = _fetch(e)
    build_funding(page, d)
    build_allocations(page, d)
    build_delivery(page, d)
    build_questions(page)
    links = build_framework_pages(page, tbl, d)
    build_hub(page, d, links)
    build_hierarchy(page, d, e)
    build_entry(page, d, e)
    build_status_form(page, d)
    import landing
    landing.build_landing(page, d, e)
