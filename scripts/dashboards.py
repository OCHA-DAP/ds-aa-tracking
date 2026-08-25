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
                  a.window_name, a.version, a.people_targeted,
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
<section><input class='filter' placeholder='filter rows…' oninput='filt(this)'>
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
        arows = "".join(
            f"<tr><td>{x.event_date}</td><td>{x.event_type}</td>"
            f"<td>{x.window_name if pd.notna(x.window_name) else ''}</td><td>{x.fund_code}</td>"
            f"<td>{x.allocation_code if pd.notna(x.allocation_code) else ''}</td>"
            f"<td>{'' if pd.isna(x.amount_usd) else f'${x.amount_usd:,.0f}'}</td>"
            f"<td>{'' if pd.isna(x.people_targeted) else f'{int(x.people_targeted):,}'}</td></tr>"
            for x in a.sort_values("event_date").itertuples())
        frows = "".join(f"<span class='badge b-kb'>{x.role}: {x.person}</span>"
                        for x in f.itertuples())
        srows = "".join(
            f"<tr><td>{x.window_name or ''}</td><td>{x.agency}</td><td>{x.sector}</td>"
            f"<td>${x.amount_usd:,.0f}</td></tr>" for x in s.itertuples())
        rrows = ", ".join(sorted({f"{x.channel} ({x.report_year})"
                                  for x in r.itertuples()}))
        covered_txt = (f"{int(pc['people_covered'].iloc[0]):,}"
                       if not pc.empty else "—")
        body = f"""
<div class='card'><b>{fw['country_name']} — {h}</b> ·
<span class='badge b-new'>{fw['status'] or 'no status'}</span>
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
<tr><th>date</th><th>type</th><th>window</th><th>fund</th><th>allocation</th><th>USD</th><th>targeted</th></tr>
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


def build_all(e, page, tbl):
    d = _fetch(e)
    build_funding(page, d)
    build_allocations(page, d)
    build_delivery(page, d)
    build_questions(page)
    links = build_framework_pages(page, tbl, d)
    build_hub(page, d, links)
