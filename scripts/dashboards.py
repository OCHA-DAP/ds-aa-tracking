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
td.na { background:#eef1f5; }
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
.doctag { display:inline-block; padding:0 7px; border-radius:9px; font-size:10.5px; font-weight:600;
          background:#e8e8f8; color:#3b3b8f; margin-left:4px; white-space:nowrap; }
.warn-tag { display:inline-block; padding:0 7px; border-radius:9px; font-size:10.5px; font-weight:600;
            background:#fde3e3; color:#a11; margin-left:6px; }
ul.doclist { list-style:none; padding:0; margin:6px 0; }
ul.doclist li { padding:5px 0; border-bottom:1px solid #f0f0f0; font-size:13px; }
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
table.hist { width:100%; table-layout:fixed; }
table.hist td, table.hist th { text-align:center; padding:3px 6px; word-wrap:break-word; }
table.hist td.yr, table.hist th:first-child { text-align:left; width:150px; }
table.hist tbody tr:nth-child(even) { background:#fafbfc; }
p.legend { font-size:12px; color:#555; margin:6px 0 0; }
table.acts { width:100%; table-layout:fixed; }
table.acts td { white-space:normal; overflow-wrap:anywhere; vertical-align:top; font-size:12.5px; }
.vchg { background:#fff; border:1px solid #e0e0e0; border-radius:6px; padding:8px 14px; margin:8px 0; }
.vchg h4 { margin:2px 0 4px; font-size:13px; } .vchg ul { margin:4px 0; padding-left:20px; }
.vchg li { font-size:13px; margin:2px 0; } .vnote { font-size:12px; color:#555; margin:4px 0; }
ul.claims { list-style:none; padding:0; margin:4px 0 8px; }
ul.claims li { font-size:13px; padding:6px 0 6px 10px; border-left:3px solid #2a78d6; background:#f3f8ff;
               margin:0 0 6px; border-radius:0 4px 4px 0; }
ul.claims .claim { color:#1a1a1a; }
ul.claims .src { color:#666; font-size:11.5px; }
.morehd { font-size:11px; text-transform:uppercase; letter-spacing:.04em; color:#889; margin:8px 0 2px; }
ul.doclist.compact li { padding:3px 0; font-size:12px; }
.empty { color:#777; font-size:13px; font-style:italic; padding:8px 0; }
.blk { margin-top:30px; } .blk > h2 { margin-top:0; padding-bottom:6px; border-bottom:2px solid #e3e8ef; }
.blk h3.sub { font-size:14px; margin:18px 0 6px; color:#334; }
.partners { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px; }
.partners .pg { background:#fff; border:1px solid #e0e0e0; border-radius:6px; padding:10px 14px; }
.partners .pg h4 { margin:0 0 6px; font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:#778; }
.partners .pg li { font-size:12.5px; margin:2px 0; }
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
function mkChart(id, type, labels, datasets, opts={}){
  datasets.forEach((d,i)=>{ d.backgroundColor ??= PAL[i%%PAL.length];
    d.borderColor ??= (type==='line'? d.backgroundColor : '#fcfcfb');
    if(type==='bar'){ d.borderWidth=1; d.borderRadius=3; d.maxBarThickness=34; }
    if(type==='line'){ d.borderWidth=2; d.pointRadius=2; d.pointHoverRadius=5; d.tension=0.15; }});
  const el = document.getElementById(id);
  if(el._chart) el._chart.destroy();
  const horiz = opts.extra && opts.extra.indexAxis === 'y';
  const fmt = v=>opts.count?v:money(v);
  const valAxis = {stacked:!!opts.stacked, ticks:{callback:fmt}, grid:{color:'#f0f0f0'},
    ...(opts.totals ? {grace:'10%%'} : {})};
  const catAxis = {stacked:!!opts.stacked, grid:{display:false}, ticks:{autoSkip:!opts.allLabels}};
  const cb = {label:c=>{const v=horiz?c.parsed.x:(c.parsed.y??c.parsed);return ` ${c.dataset.label??''}: ${fmt(v)}`;}};
  if(opts.totals) cb.footer = items=>'total: '+fmt(items.reduce((s,c)=>s+((horiz?c.parsed.x:c.parsed.y)||0),0));
  el._chart = new Chart(el, { type, data:{labels, datasets},
    plugins: opts.totals ? [stackTotals] : [],
    options:{
    responsive:true, maintainAspectRatio:false, interaction:{mode:'index',intersect:false},
    scales: opts.noscale?{}:(horiz ? {x:valAxis, y:catAxis} : {x:catAxis, y:valAxis}),
    plugins:{ legend:{display:datasets.length>1},
      tooltip:{callbacks:cb},
      ...(opts.totals ? {stackTotals:{fmt, horiz}} : {}),
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


def _backfill_years(pre, e, first_year=2020):
    """Framework-years with no dated pre-arranged row get the version in force at 31 December
    (or today, for the current year) and its envelope from aa.v_version_funding — so the
    annual series covers 2020→ from the framework record itself (source='version-inferred').
    Sheet / entered rows for a framework-year always win; the official year-end reports,
    once loaded, will replace the inferred rows year by year."""
    import datetime as dt

    ver = pd.read_sql(
        """SELECT country_iso3, hazard, version, kb_framework, kb_status, valid_from,
                  valid_until, prearranged_usd_doc FROM aa.framework_version
           WHERE kb_status = 'endorsed' AND valid_from IS NOT NULL""", e)
    env = pd.read_sql(
        """SELECT country_iso3, hazard, version, fund_code, total_usd
           FROM aa.v_version_funding WHERE kind = 'prearranged' AND fund_code IS NOT NULL""", e)
    # the imported page metadata (funding_by_source / prearranged_funding_usd) for versions
    # that never got envelope rows — older versions, mostly
    pages = pd.read_sql(
        """SELECT kb_framework, version, frontmatter -> 'funding_by_source' AS by_source,
                  (frontmatter ->> 'prearranged_funding_usd')::numeric AS pre_doc
           FROM aa.version_page""", e)
    page_by = {(r.kb_framework, str(r.version)): (r.by_source, r.pre_doc)
               for r in pages.itertuples()}
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
        last_year = today.year if (c, h) not in last_live else (
            cap if cap is not None and not pd.isna(cap)
            else int(vs["valid_from"].min().year))
        for y in range(first_year, int(last_year) + 1):
            if (c, h, y) in have:
                continue
            at = pd.Timestamp(min(dt.date(y, 12, 31), today))
            inforce = vs[(vs["valid_from"] <= at)
                         & (vs["valid_until"].isna() | (vs["valid_until"] >= at))]
            if inforce.empty:
                continue
            v = inforce.sort_values("valid_from").iloc[-1]
            e_v = env[(env["country_iso3"] == c) & (env["hazard"] == h)
                      & (env["version"] == v["version"])]
            by_source, pre_doc = page_by.get((fw_slug.get((c, h)), str(v["version"])), (None, None))
            amounts = []
            if len(e_v):
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
                             "source": "version-inferred"})
    if not rows:
        return pre
    return pd.concat([pre, pd.DataFrame(rows)[pre.columns]], ignore_index=True)


def _fetch(e):
    """All row-level frames the dashboards embed."""
    d = {}
    d["current"] = pd.read_sql(
        """SELECT c.*, r.region FROM aa.v_trk_framework_current c
           LEFT JOIN aa.country_hazard r USING (country_iso3, hazard)""", e)
    d["current"] = d["current"].loc[:, ~d["current"].columns.duplicated()]
    pre = pd.read_sql(
        """SELECT country_iso3, hazard, year, kind, fund_code, financier,
                  amount_usd, source FROM aa.prearranged_funding
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
                  f.fund_code, f.allocation_code, f.amount_usd,
                  r.region
           FROM aa.activation_funding f
           JOIN aa.activation a USING (country_iso3, hazard, event_date,
                                       window_name, event_label, event_type)
           LEFT JOIN aa.country_hazard r USING (country_iso3, hazard)""", e)
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
                  coalesce(year::text, 'Prearranged') AS year_label
           FROM aa.v_window_funding_split
           WHERE amount_usd IS NOT NULL AND (agency IS NOT NULL OR sector IS NOT NULL)""", e)
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
    # AA-tagged CBPF / regional-fund allocations from the OneGMS mirror. The CBPF modality
    # allocates up front: an AA-tagged allocation is PRE-ARRANGED money until an activation
    # draws on it (= a row in activation_funding, entered by hand), then it is disbursed.
    d["cbpf_aa"] = pd.read_sql(
        """SELECT v.allocation_code, v.fund_type, v.fund_name, v.year, v.amount_usd,
                  fu.country_iso3, fu.fund_code, (af.allocation_code IS NOT NULL) AS linked,
                  left(v.title, 120) AS title
           FROM aa.v_allocation v
           LEFT JOIN aa.fund fu
             ON fu.pf_id = (CASE WHEN split_part(v.allocation_code, '-', 2) ~ '^[0-9]+$'
                            THEN split_part(v.allocation_code, '-', 2)::int END)
           LEFT JOIN (SELECT DISTINCT allocation_code FROM aa.activation_funding) af
             ON af.allocation_code = v.allocation_code
           WHERE v.is_aa AND v.fund_type <> 'cerf'""", e)
    # pre-arranged money NOW: the latest version's envelope of every framework that is not
    # retired (a framework being updated keeps its most recent version's figures)
    d["vfund"] = pd.read_sql(
        """SELECT vf.country_iso3, vf.hazard, vf.version, vf.fund_code, vf.total_usd,
                  l.lifecycle
           FROM aa.v_version_funding vf
           JOIN aa.v_framework_lifecycle l
             ON l.country_iso3 = vf.country_iso3 AND l.hazard = vf.hazard
            AND l.latest_version = vf.version
           WHERE vf.kind = 'prearranged'
             AND l.lifecycle IN ('active', 'updating', 'development')""", e)   # pre-arranged 'now' (2026-09-28: in-development frameworks count — the money is pre-arranged once the ERC approved it)
    d["windows"] = pd.read_sql(
        """SELECT w.country_iso3, r.country_name, w.hazard, w.version, w.window_name,
                  w.basis, w.all_in, w.allocation_usd,
                  p.return_period, p.activation_prob, p.n_activations, p.analysis_years,
                  s.triggered, s.triggered_on, l.lifecycle,
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
    d["act_all"] = pd.read_sql(
        """SELECT a.*, r.country_name FROM aa.activation a
           LEFT JOIN aa.country_hazard r ON r.country_iso3 = a.country_iso3 AND r.hazard = a.hazard
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
    d["subgrant_aa"] = pd.read_sql(
        """SELECT project_code, application_code, agency, year, country_iso3, partner_name,
                  partner_type, localization, subgrant_usd
           FROM aa.cerf_subgrant WHERE is_aa AND subgrant_usd IS NOT NULL""", e)
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
    # Internal documents are NEVER rendered: filtered out here, at the source.
    try:
        d["learning"] = pd.read_sql(
            """SELECT id, title, url, publisher, year, doc_type, scope, country_iso3, hazard,
                      premises, key_stat, summary, section, source
               FROM aa.learning_document WHERE NOT internal
               ORDER BY year DESC NULLS LAST, title""", e)
        d["n_internal_docs"] = int(pd.read_sql(
            "SELECT count(*) AS n FROM aa.learning_document WHERE internal", e)["n"].iloc[0])
    except Exception as exc:
        print(f"  learning: aa.learning_document unavailable ({exc.__class__.__name__})")
        d["learning"] = pd.DataFrame(columns=["id", "title", "url", "publisher", "year",
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
                              valid_from, note, analysis_ref, doc_url, doc_title
                       FROM aa.framework_version ORDER BY country_iso3, hazard, valid_from""",
         ["country_iso3", "hazard", "version", "kb_framework", "valid_from", "note",
          "analysis_ref", "doc_url", "doc_title"])
    _opt("sim", """SELECT country_iso3, hazard, version::text AS version, window_name,
                          event_year, event_label FROM aa.simulated_activation""",
         ["country_iso3", "hazard", "version", "window_name", "event_year", "event_label"])
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
    d["fund_names"] = pd.read_sql("SELECT fund_code, fund_type, name FROM aa.fund", e)
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


def funding_series(d):
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
    # the mirror does not cover, so the same money is never counted twice
    cb = d["cbpf_aa"].copy()
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
    cb["in_gho"] = [(c, y) in gho_set for c, y in zip(cb["country_iso3"], cb["year"])]
    mirror_cy = set(zip(cb["country_iso3"], cb["year"]))
    pre = pre[~(pre["fund_code"].str.startswith(("cbpf", "rhpf"))
                & pd.Series([(c, y) in mirror_cy for c, y in
                             zip(pre["country_iso3"], pre["year"])], index=pre.index))]
    pre = pd.concat([pre, cb[pre.columns]], ignore_index=True)
    return pre, act


PARTNER_TYPE = {"INGO": "INGO", "NNGO": "national / local NGO", "GOV": "government",
                "RedC": "Red Cross / Red Crescent", "REDC": "Red Cross / Red Crescent",
                "TBD": "other partners"}
CBPF_ORG = {"International NGO": "INGO", "National NGO": "national / local NGO",
            "UN Agency": "UN agencies", "Red Cross/Red Crescent Organization": "Red Cross / Red Crescent",
            "Others": "other"}


def _money_flows(d, pre, act):
    """Link rows {m, y, lv, s, t, v} for the two 'Where the money flows' Sankeys.

    The two are kept apart on purpose (never summed): pre-arranged money is a STOCK — the
    envelopes in place at a date — while released money is a FLOW, per year. Released money
    is drawn from the pre-arranged envelopes, so adding the two double-counts it.

    m 'p' pre-arranged, as at the end of year y (the current year: today). One row per
      framework × fund (the Funding page's canonical series); fund -> agency from the agency
      split of the version in force that year (v_window_funding_split, scaled to the
      envelope); CBPF / RhPF allocations by grantee type. No partner level: who a UN agency
      sub-grants to is only known once money is released. Years are never added up.
    m 'r' released in year y: activation funding; CERF -> agency from the AA projects
      approved that year (scaled to the released total); agency -> partner type from the
      CERF AA sub-grants; CBPF / RhPF by grantee type. Years add up.
    lv: 'd' donor -> fund (donor share of the fund's paid income that year × the amount),
        'f' fund -> agency, 'a' agency -> partner type."""
    import datetime as _dt
    import re as _re
    today = _dt.date.today()
    C = d["contrib"].copy()
    C = C[C["paid_usd"].fillna(0) > 0]
    C["fund_code"] = C["fund_code"].fillna("cbpf:" + C["fund_name"].astype(str))
    C = C.groupby(["fund_code", "year", "donor"], as_index=False)["paid_usd"].sum()
    co = d["cbpf_org"].copy()
    co["grp"] = co["org_type"].map(CBPF_ORG).fillna("other")
    co = co.groupby(["fund_code", "year", "grp"])["usd"].sum()
    ag = d["agency"].groupby(["year", "agency"])["amount_approved"].sum()
    sg = d["subgrant_aa"].copy()
    sg["grp"] = sg["partner_type"].map(PARTNER_TYPE).fillna("other partners")
    sgm = sg.groupby(["year", "agency", "grp"])["subgrant_usd"].sum()
    split = d["split_all"].copy()
    split["version"] = split["version"].astype(str)
    fvm = d["fv_meta"].copy()
    fvm["vf"] = pd.to_datetime(fvm["valid_from"], errors="coerce")
    rows = []

    def add(m, y, lv, s_, t, v):
        if v and v > 0.5:
            rows.append({"m": m, "y": int(y), "lv": lv, "s": s_, "t": t, "v": round(float(v), 2)})

    def donors(m, y, fc, amount):
        cy = C[(C["fund_code"] == fc) & (C["year"] == y)]
        inc = cy["paid_usd"].sum()
        if inc > 0:
            for r in cy.itertuples():
                add(m, y, "d", "d:" + r.donor, "f:" + fc, r.paid_usd / inc * amount)
        else:
            add(m, y, "d", "d:(donors not recorded)", "f:" + fc, amount)

    def grantees(m, y, fc, amount):
        o = co[(co.index.get_level_values(0) == fc) & (co.index.get_level_values(1) == y)] if len(co) else co
        osum = float(o.sum()) if len(o) else 0.0
        if osum <= 0:
            add(m, y, "f", "f:" + fc, "a:partners (CBPF)", amount)
            return
        for (_, _, grp), v in o.items():
            add(m, y, "f", "f:" + fc, "a:CBPF grantees: " + grp, v / osum * amount)

    # ---------------- pre-arranged, as at the end of each year (never summed over years)
    P = pre[(pre["kind"] == "prearranged") & (pre["fund_code"] != "all") & (pre["year"] <= today.year)]
    for y, py in P.groupby("year"):
        y = int(y)
        at = pd.Timestamp(min(_dt.date(y, 12, 31), today))
        for fc, amount in py.groupby("fund_code")["amount_usd"].sum().items():
            donors("p", y, fc, amount)
        for r in py.itertuples():
            fc, amount = r.fund_code, float(r.amount_usd)
            if amount <= 0:
                continue
            if fc != "cerf" and r.source == "onegms-mirror":
                grantees("p", y, fc, amount)
                continue
            # the agency split of the version in force at that date (latest one with a split)
            vs = fvm[(fvm["country_iso3"] == r.country_iso3) & (fvm["hazard"] == r.hazard)
                     & (fvm["vf"].isna() | (fvm["vf"] <= at))].sort_values("vf")
            sp = None
            for v in reversed(list(vs["version"].astype(str))):
                cand = split[(split["country_iso3"] == r.country_iso3) & (split["hazard"] == r.hazard)
                             & (split["version"] == v) & split["agency"].notna()]
                if len(cand):
                    own = cand[cand["fund_code"] == fc]
                    sp = own if len(own) else cand
                    break
            if sp is None or sp["amount_usd"].sum() <= 0:
                add("p", y, "f", "f:" + fc, "a:agencies not recorded", amount)
                continue
            shares = sp.groupby("agency")["amount_usd"].sum()
            for agency, v in shares.items():
                add("p", y, "f", "f:" + fc, "a:" + agency, v / shares.sum() * amount)

    # ---------------- released, in the year it went out (years add up)
    R = act[act["amount_usd"].fillna(0) > 0]
    for (fc, y), amount in R.groupby(["fund_code", "year"])["amount_usd"].sum().items():
        y = int(y)
        donors("r", y, fc, amount)
        if fc != "cerf":
            grantees("r", y, fc, amount)
            continue
        a_ = ag[ag.index.get_level_values(0) == y] if len(ag) else ag
        asum = float(a_.sum()) if len(a_) else 0.0
        if asum <= 0:
            add("r", y, "f", "f:cerf", "a:agencies not recorded", amount)
            continue
        k = amount / asum
        for (_, agency), v in a_.items():
            add("r", y, "f", "f:cerf", "a:" + agency, v * k)
            s_ = sgm[(sgm.index.get_level_values(0) == y) & (sgm.index.get_level_values(1) == agency)]
            tot_s = float(s_.sum())
            parts = min(tot_s, float(v)) * k
            for (_, _, grp), sv in s_.items():
                add("r", y, "a", "a:" + agency, "p:" + grp, sv / tot_s * parts if tot_s else 0)
            add("r", y, "a", "a:" + agency, "p:retained by agency", v * k - parts)

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
    years = {m: sorted({r["y"] for r in rows if r["m"] == m}) for m in ("p", "r")}
    done = [y for y in years["r"] if y <= today.year - 1]
    default = {"p": today.year if today.year in years["p"] else (years["p"][-1] if years["p"] else None),
               "r": done[-1] if done else (years["r"][-1] if years["r"] else None)}
    return rows, years, default, names


# ------------------------------------------------------------------ funding
def build_funding(page, d):
    pre, act = funding_series(d)
    cur = d["current"]
    ver = d["versions"].copy()
    ver["year"] = pd.to_datetime(ver["valid_from"]).dt.year

    # pre-arranged NOW under the convention: every non-retired framework keeps its latest
    # version's envelope ('all' totals dropped where the fund split exists)
    vf = d["vfund"].copy()
    has_comp = set(map(tuple, vf.loc[vf["fund_code"] != "all",
                                     ["country_iso3", "hazard", "version"]].values))
    vf = vf[~((vf["fund_code"] == "all")
              & vf.apply(lambda r: (r["country_iso3"], r["hazard"], r["version"]) in has_comp,
                         axis=1))]
    vf["ft"] = vf["fund_code"].map(lambda f: "cerf" if f == "cerf" else
                                   "regional_fund" if str(f).startswith("rhpf") else "cbpf")
    vf = vf.merge(cur[["country_iso3", "hazard", "region"]], on=["country_iso3", "hazard"],
                  how="left")
    vf["hz"] = vf["hazard"].map(haz)
    now_cerf = vf.loc[vf["ft"] == "cerf", "total_usd"].sum()
    now_cbpf = vf.loc[vf["ft"] != "cerf", "total_usd"].sum()

    n_active = int((cur["lifecycle"] == "active").sum())
    n_upd = int((cur["lifecycle"] == "updating").sum())
    n_tech = int(cur["technical_support"].fillna(False).astype(bool).sum())
    total_disb = act["amount_usd"].sum()
    covered = d["covered"]["people_covered"].sum()

    # agency × sector split of the live frameworks' latest versions (one source per version)
    pr = d["plan_rows"].merge(cur[["country_iso3", "hazard", "region"]],
                              on=["country_iso3", "hazard"], how="left")
    pr["hz"] = pr["hazard"].map(haz)
    pr["ft"] = pr["fund_code"].map(lambda f: "cerf" if f == "cerf" else
                                   "regional_fund" if str(f).startswith("rhpf") else "cbpf")

    # UN agencies vs partners: CERF AA project money per year (direct UN spend) against
    # what the agencies sub-granted (cerf_subgrant, is_aa) by partner-type group
    sg = d["subgrant_aa"].copy()
    PT_GROUP = {"INGO": "INGO", "NNGO": "NNGO / local", "GOV": "government",
                "RedC": "Red Cross / Red Crescent", "REDC": "Red Cross / Red Crescent"}
    sg["grp"] = sg["partner_type"].map(PT_GROUP).fillna("other")
    ag_year = d["agency"].groupby("year")["amount_approved"].sum()
    sg_year = sg.groupby("year")["subgrant_usd"].sum()
    un_rows = [{"year": int(y), "grp": "direct UN spend",
                "usd": float(max(ag_year.get(y, 0) - sg_year.get(y, 0), 0))}
               for y in sorted(set(ag_year.index) | set(sg_year.index)) if y >= 2020]
    un_rows += [{"year": int(r.year), "grp": r.grp, "usd": float(r.subgrant_usd)}
                for r in sg.groupby(["year", "grp"])["subgrant_usd"].sum().reset_index()
                .itertuples() if r.year >= 2020]
    sub_total = float(sg["subgrant_usd"].sum())
    local_usd = float(sg.loc[sg["localization"].fillna("").str.lower() == "local",
                             "subgrant_usd"].sum())
    local_share = (local_usd / sub_total * 100) if sub_total else 0
    un_total = float(ag_year[ag_year.index >= 2020].sum())
    sub_share = (sub_total / un_total * 100) if un_total else 0

    # donors of the funds that pre-arrange AA money (CERF + every CBPF / RhPF with a
    # pre-arranged row), paid contributions in the latest year on record
    import datetime as _dt
    aa_funds = set(pre.loc[pre["kind"] == "prearranged", "fund_code"].dropna()) | {"cerf"}
    co = d["contrib"]
    co = co[co["fund_code"].isin(aa_funds) & (co["paid_usd"].fillna(0) > 0)].copy()
    donor_year = None
    if len(co):
        yrs = sorted(int(y) for y in co["year"].dropna().unique() if y <= _dt.date.today().year)
        donor_year = yrs[-1] if yrs else int(co["year"].max())
        co = co[co["year"] == donor_year]
    co["ft"] = co["fund_type"].map(lambda t: "cerf" if t == "cerf" else
                                   "regional_fund" if t == "regional_fund" else "cbpf")
    top_donors = (co.groupby("donor")["paid_usd"].sum().sort_values(ascending=False)
                  .head(10).index.tolist())
    donor_rows = (co[co["donor"].isin(top_donors)].groupby(["donor", "ft"])["paid_usd"].sum()
                  .reset_index().rename(columns={"paid_usd": "usd"}))
    donor_note = (f"Paid contributions in {donor_year}"
                  + (" (year to date)" if donor_year == _dt.date.today().year else "")
                  + f" to the {len(aa_funds)} pooled funds holding pre-arranged AA money "
                  "(CERF and the CBPFs / regional funds with an AA-tagged allocation). "
                  "Contributions fund the whole pool, not AA alone."
                  if donor_year else "No contribution rows in this snapshot.")
    flow_rows, flow_years, flow_default, fund_names = _money_flows(d, pre, act)

    panels = f"""
<div class='tiles'>
 <div class='tile'><div class='v'>{n_active}</div><div class='l'>active frameworks · {n_upd} being updated{f' · {n_tech} technical support only' if n_tech else ''}</div></div>
 <div class='tile'><div class='v'>${(now_cerf + now_cbpf)/1e6:,.0f}M</div><div class='l'>pre-arranged now — CERF ${now_cerf/1e6:,.0f}M · CBPF/RhPF ${now_cbpf/1e6:,.0f}M</div></div>
 <div class='tile'><div class='v'>${total_disb/1e6:,.0f}M</div><div class='l'>AA/EA disbursed 2020–2026 (all funds)</div></div>
 <div class='tile'><div class='v'>{covered/1e6:,.1f}M</div><div class='l'>people covered (latest per framework)</div></div>
</div>
<div class='note' style='margin:-6px 0 10px'>Pre-arranged money stays pre-arranged until a framework is <b>retired</b>: a framework being updated keeps its most recent version's envelope. CBPF and regional-fund allocations are made up front, so an AA-tagged allocation counts as pre-arranged until an activation draws on it (then it is disbursed as well).</div>
<div class='fbar'>
 <label>Hazard <select id='fHaz'><option value=''>all</option></select></label>
 <label>Region <select id='fReg'><option value=''>all</option></select></label>
 <label>GHO <select id='fGho'><option value=''>all</option><option value='1'>GHO contexts only</option></select></label>
 <label title='released money only: pre-arranged money is a stock, in place on a date, so it never accumulates'><input type='checkbox' id='fCum'> cumulative (released)</label>
</div>
<div class='grid'>
 <div class='panel'><h3>Pre-arranged funding in place at year end — CERF, CBPF and RhPF</h3><canvas id='c1' height='260'></canvas>
   <div class='note'>A stock: what was committed at each year end, so the bars are not added up (the cumulative switch applies to released money only). CERF: the framework envelopes per year (sheets, KB pages, entries; 'all'-totals excluded where the fund split exists). CBPF / regional funds: AA-tagged allocations in the OneGMS mirror, in the year allocated. Co-financing shown separately below.</div></div>
 <div class='panel'><h3>AA/EA disbursed by year — CERF, CBPF and RhPF</h3><canvas id='c2' height='260'></canvas>
   <div class='note'>Allocations drawn by an activation (framework + ad-hoc + EA), all pooled funds. A CBPF allocation moves here only once an activation is recorded against it.</div></div>
 <div class='panel'><h3>Pre-arranged now, by hazard — CERF, CBPF and RhPF</h3><canvas id='c3' height='260'></canvas>
   <div class='note'>Latest version of every framework that is active or being updated.</div></div>
 <div class='panel'><h3>Pre-arranged now, by region — CERF, CBPF and RhPF</h3><canvas id='c4' height='260'></canvas></div>
 <div class='panel'><h3>Framework versions endorsed/revised per year</h3><canvas id='c5' height='260'></canvas>
   <div class='note'>One bar segment per version registered that year (endorsed docs; a version = an endorsed document).</div></div>
 <div class='panel'><h3>Co-financing & non-OCHA money</h3><canvas id='c6' height='260'></canvas>
   <div class='note'>kind = cofinancing / non_aa_mobilised; financier mostly uncurated — amounts only.</div></div>
</div>
<h2>Where the money flows</h2>
<p class='meta'>Donors → funds → agencies (→ partner types). Two views that are never added together: <b>pre-arranged</b> money is a stock, the envelopes in place on a date; <b>released</b> money is a flow, what went out in a year, drawn from those envelopes. Not affected by the filter bar above.</p>
<div class='panel'>
 <div style='display:flex;gap:16px;flex-wrap:wrap;align-items:center;font-size:12.5px;margin-bottom:8px'>
  <span role='radiogroup' aria-label='which money' style='display:inline-flex;border:1px solid #cbd5e1;border-radius:6px;overflow:hidden'>
   <label style='padding:3px 10px;cursor:pointer'><input type='radio' name='flM' value='p' checked> pre-arranged</label>
   <label style='padding:3px 10px;cursor:pointer;border-left:1px solid #cbd5e1'><input type='radio' name='flM' value='r'> released</label></span>
  <label><span id='flYl'>As at end of</span> <select id='flY'></select></label>
  <label><input type='checkbox' id='flD' checked> donors</label>
  <label id='flPw'><input type='checkbox' id='flP' checked> partner types (sub-granting)</label>
  <span id='flTot' class='muted'></span>
 </div>
 <div id='flow'></div><script src="sankey.js"></script>
 <div class='note'><b>Pre-arranged</b>: the envelopes in place at the end of the chosen year (the current year: today), one per framework and fund — the Funding page's annual series. Never summed over years: a two-year envelope would count twice. Fund → agency uses the agency split of the version in force at that date, scaled to the envelope; CBPF / RhPF allocations go to their grantee types. There is no partner level: who an agency sub-grants to is only known once money is released.
 <b>Released</b>: money that went out on activations in the chosen year (all years add up). CERF → agency uses the AA projects approved that year, scaled to the released total; agency → partner type uses the CERF AA sub-grants, the rest "retained by agency"; CBPF / RhPF go to grantee types from their AA-keyword project budgets.
 <b>Donors → fund</b> (both views): each donor's paid contributions to the fund that year ÷ the fund's total paid income that year, × the amount — attributed pro rata, since contributions fund the whole pool. Top 12 donors, the rest grouped.</div>
</div>
<h2>Who holds the pre-arranged money</h2>
<p class='meta'>The latest version of every live framework (active, being updated, in development), split by agency and sector as the framework documents state it, stacked by fund. Hazard and region filters apply; the GHO filter does not.</p>
<div class='grid'>
 <div class='panel'><h3>Pre-arranged by agency</h3><canvas id='c7' height='320'></canvas>
   <div class='note'>Envelope shares per implementing agency (the agency lines of the framework budgets; top 18).</div></div>
 <div class='panel'><h3>Pre-arranged by sector</h3><canvas id='c8' height='320'></canvas>
   <div class='note'>Sector lines of the same budgets; a line with an agency but no sector is not shown here.</div></div>
</div>
<h2>UN agencies and partners</h2>
<p class='meta'>Pre-arranged money is committed to UN agencies at the framework level. Once CERF disburses, the agencies keep part of it as direct spend and sub-grant the rest to implementing partners — this is where partners appear in the money trail. Not affected by the filters.</p>
<div class='tiles'>
 <div class='tile'><div class='v'>{sub_share:.0f}%</div><div class='l'>of CERF AA project money sub-granted to partners (2020→)</div></div>
 <div class='tile'><div class='v'>{local_share:.0f}%</div><div class='l'>localization share — sub-grants to local / national actors (NNGO, government, Red Cross / Red Crescent)</div></div>
 <div class='tile'><div class='v'>${sub_total/1e6:,.1f}M</div><div class='l'>sub-granted in total · {sg['partner_name'].nunique()} partners</div></div>
</div>
<div class='grid'>
 <div class='panel' style='grid-column:1/-1'><h3>CERF AA allocations by year — direct UN spend vs sub-granted to partners</h3><canvas id='c9' height='280'></canvas>
   <div class='note'>Direct UN spend = CERF AA project budgets (OneGMS mirror, AA-flagged allocations) minus the sub-grants reported for the same year (aa.cerf_subgrant, curated AA set). Partner groups from the sub-grant partner type; 'other' includes partners not yet typed.</div></div>
</div>
<h2>Donors</h2>
<p class='meta'>{donor_note} <a href='dash-donors.html'>full donor shares →</a></p>
<div class='grid'>
 <div class='panel' style='grid-column:1/-1'><h3>Top 10 donors of the funds that pre-arrange AA money{f' — {donor_year}' if donor_year else ''}</h3><canvas id='c10' height='320'></canvas>
   <div class='note'>Paid contributions (cash basis, pledges excluded), stacked by fund type. The <a href='dash-donors.html'>donor shares</a> page turns these into each donor's share of the AA money released and pre-arranged.</div></div>
</div>"""

    data = {
        "pre": json.loads(_records(pre, ["country_iso3", "hz", "region", "year",
                                         "kind", "fund_code", "amount_usd",
                                         "in_gho"])),
        "act": json.loads(_records(act, ["country_iso3", "hz", "region", "year",
                                         "fund_code", "amount_usd", "event_type",
                                         "in_gho"])),
        "ver": json.loads(_records(ver, ["year", "kb_status"])),
        "now": json.loads(_records(vf, ["country_iso3", "hz", "region", "ft", "total_usd"])),
        "split": json.loads(_records(pr, ["hz", "region", "agency", "sector", "ft",
                                          "amount_usd"])),
        "un": un_rows,
        "donors": json.loads(_records(donor_rows)),
        "flow": flow_rows, "flowYears": flow_years, "flowDefault": flow_default,
        "fundNames": fund_names,
    }
    js = """
function fundType(fc){ return fc==='cerf'?'cerf':(fc||'').startsWith('rhpf')?'regional_fund':'cbpf'; }
const FT = ['cerf','cbpf','regional_fund'];
function stackedBy(id, rows, keyFn, valFn, opts){
  const keys = opts && opts.keys ? opts.keys : uniqSorted(rows, keyFn);
  mkChart(id,'bar',keys,FT.map(ft=>({label:ft, backgroundColor:FUND_COLORS[ft],
    data:keys.map(k=>groupSum(rows.filter(r=>r.ft===ft&&keyFn(r)===k),()=>0,valFn)[0]||0)})).filter(d=>d.data.some(v=>v)),
    {stacked:true, totals:true, ...(opts||{})});
}
function topKeys(rows, keyFn, valFn, n){ const g = groupSum(rows.filter(r=>keyFn(r)!=null), keyFn, valFn);
  return Object.keys(g).sort((a,b)=>g[b]-g[a]).slice(0,n); }
function draw(){
  const hz=fHaz.value, rg=fReg.value, gho=fGho.value, cum=fCum.checked;
  const P = D.pre.filter(r=>r.kind==='prearranged' && r.fund_code!=='all'
      && (!hz||r.hz===hz) && (!rg||r.region===rg) && (!gho||r.in_gho));
  const A = D.act.filter(r=>(!hz||r.hz===hz)&&(!rg||r.region===rg)&&(!gho||r.in_gho));
  const years = uniqSorted(P.concat(A), r=>r.year);
  for(const [id, rows, kf] of [['c1',P,r=>fundType(r.fund_code)],['c2',A,r=>fundType(r.fund_code)]]){
    const ds = FT.map(ft=>{
      let vals = years.map(y=>groupSum(rows.filter(r=>kf(r)===ft&&r.year===y),()=>0,r=>r.amount_usd)[0]||0);
      if(cum && id==='c2') vals = cumulate(vals);   // pre-arranged is a stock: never cumulated
      return {label:ft, data:vals, backgroundColor:FUND_COLORS[ft]};});
    mkChart(id,'bar',years,ds,{stacked:true, totals:true});
  }
  const N = D.now.filter(r=>(!hz||r.hz===hz)&&(!rg||r.region===rg));
  stackedBy('c3', N, r=>r.hz, r=>r.total_usd); stackedBy('c4', N, r=>r.region, r=>r.total_usd);
  const vy = uniqSorted(D.ver.filter(r=>r.year), r=>r.year);
  mkChart('c5','bar',vy,[{label:'versions',data:vy.map(y=>D.ver.filter(r=>r.year===y).length),backgroundColor:PAL[2]}],{count:true});
  const C = D.pre.filter(r=>r.kind!=='prearranged'&&(!hz||r.hz===hz)&&(!rg||r.region===rg));
  const cy = uniqSorted(C, r=>r.year);
  mkChart('c6','bar',cy,['cofinancing','non_aa_mobilised'].map((k,i)=>({label:k,
    data:cy.map(y=>groupSum(C.filter(r=>r.kind===k&&r.year===y),()=>0,r=>r.amount_usd)[0]||0),
    backgroundColor:PAL[i+3]})),{stacked:true, totals:true});
  const S = D.split.filter(r=>(!hz||r.hz===hz)&&(!rg||r.region===rg));
  const SA = S.filter(r=>r.agency), SS = S.filter(r=>r.sector);
  stackedBy('c7', SA, r=>r.agency, r=>r.amount_usd, {keys:topKeys(SA,r=>r.agency,r=>r.amount_usd,18), extra:{indexAxis:'y'}});
  stackedBy('c8', SS, r=>r.sector, r=>r.amount_usd, {keys:topKeys(SS,r=>r.sector,r=>r.amount_usd,18), extra:{indexAxis:'y'}});
}
// UN vs partners and donors: fixed panels (not filtered)
const UG = ['direct UN spend','INGO','NNGO / local','Red Cross / Red Crescent','government','other'];
const uy = uniqSorted(D.un, r=>r.year);
mkChart('c9','bar',uy,UG.map((g,i)=>({label:g, backgroundColor:PAL[i],
  data:uy.map(y=>groupSum(D.un.filter(r=>r.grp===g&&r.year===y),()=>0,r=>r.usd)[0]||0)})).filter(d=>d.data.some(v=>v)),
  {stacked:true, totals:true});
const dk = topKeys(D.donors, r=>r.donor, r=>r.usd, 10);
if(dk.length) stackedBy('c10', D.donors, r=>r.donor, r=>r.usd, {keys:dk, extra:{indexAxis:'y'}});
else document.getElementById('c10').outerHTML = "<p class='meta'>no contribution rows in this snapshot</p>";
uniqSorted(D.pre,r=>r.hz).forEach(h=>fHaz.add(new Option(h,h)));
uniqSorted(D.pre,r=>r.region).forEach(r=>fReg.add(new Option(r,r)));
[fHaz,fReg,fGho,fCum].forEach(el=>el.addEventListener('change',draw));
draw();
// ---- where the money flows: donors -> funds -> agencies -> partner types
function buildFlow(rows, mode, year, showD, showP, names, topN){
  const R = rows.filter(r=>r.m===mode && (year==='all' || r.y===+year));
  const agg = {}; R.forEach(r=>{ const k=r.lv+'\\u0001'+r.s+'\\u0001'+r.t; agg[k]=(agg[k]||0)+r.v; });
  let L = Object.entries(agg).map(([k,v])=>{ const [lv,s,t]=k.split('\\u0001'); return {lv,s,t,v}; });
  // top donors; the rest grouped
  const dt = {}; L.filter(l=>l.lv==='d').forEach(l=>dt[l.s]=(dt[l.s]||0)+l.v);
  const top = new Set(Object.keys(dt).filter(k=>k!=='d:(donors not recorded)').sort((a,b)=>dt[b]-dt[a]).slice(0,topN||12));
  top.add('d:(donors not recorded)');
  const g = {}; L.forEach(l=>{ if(l.lv==='d' && !top.has(l.s)) l.s='d:Other donors';
    const k=l.lv+'\\u0001'+l.s+'\\u0001'+l.t; g[k]=g[k]?(g[k].v+=l.v,g[k]):{...l}; });
  L = Object.values(g);
  if(!showD) L = L.filter(l=>l.lv!=='d');
  if(!showP) L = L.filter(l=>l.lv!=='a');
  const lab = id => { const [p, ...rest] = id.split(':'); const n = rest.join(':');
    return p==='f' ? (names[n]||n) : n; };
  const cols = []; const seen = {};
  const col = pre => { const ids = new Set(); L.forEach(l=>{ [l.s,l.t].forEach(x=>{ if(x.startsWith(pre)) ids.add(x); }); });
    return [...ids].map(id=>({id, label:lab(id)})); };
  if(showD) cols.push(col('d:'));
  cols.push(col('f:')); cols.push(col('a:'));
  if(showP) cols.push(col('p:'));
  const total = L.filter(l=>l.lv==='f').reduce((s,l)=>s+l.v,0);
  return {columns:cols, links:L.map(l=>({s:l.s,t:l.t,v:l.v})), total};
}
function drawFlow(){
  const mode = document.querySelector("input[name='flM']:checked").value;
  const F = buildFlow(D.flow, mode, flY.value, flD.checked, mode==='r' && flP.checked, D.fundNames, 12);
  const el = document.getElementById('flow');
  if(!F.links.length){ el.innerHTML = "<p class='empty'>no AA money recorded for this year</p>"; flTot.textContent=''; return; }
  const n = Math.max(...F.columns.map(c=>c.length));
  el.innerHTML = sankeySVG({columns:F.columns, links:F.links, width:1100, height:Math.max(260, n*24),
    fmt:money, labelW:170, label:'AA money from donors through funds and agencies to partners'});
  el.insertAdjacentHTML('beforeend', "<div class='note'>Hover a band or a box to follow the money; click a box to keep it in focus, click again to clear. Colours: one per fund (CERF blue, pooled funds orange, regional funds green) and one per agency.</div>");
  flTot.textContent = mode==='p' ? `Pre-arranged, in place at the end of ${flY.value}: ${money(F.total)}` + (+flY.value===new Date().getFullYear() ? ' (today)' : '')
                                  : `Released ${flY.value==='all' ? 'in all years' : 'in ' + flY.value}: ${money(F.total)}`;
}
if(window.sankeySVG){
  // the year list depends on the view: pre-arranged is one year's stock (no 'all years')
  function fillYears(){
    const mode = document.querySelector("input[name='flM']:checked").value, keep = flY.value;
    flY.innerHTML = '';
    D.flowYears[mode].slice().reverse().forEach(y=>flY.add(new Option(y, y)));
    if(mode==='r') flY.add(new Option('all years', 'all'));
    flY.value = [...flY.options].some(o=>o.value===keep) && keep!=='' ? keep : String(D.flowDefault[mode]);
    document.getElementById('flYl').textContent = mode==='p' ? 'As at end of' : 'Released in';
    document.getElementById('flPw').style.display = mode==='r' ? '' : 'none';
  }
  document.querySelectorAll("input[name='flM']").forEach(el=>el.addEventListener('change', ()=>{ fillYears(); drawFlow(); }));
  fillYears();
  [flY, flD, flP].forEach(el=>el.addEventListener('change', drawFlow));
  drawFlow();
}"""
    _dash_page(page, "dash-funding.html", "Funding",
               "<b>The funding block of anticipatory action.</b> Pre-arranged and "
               "disbursed AA money across CERF, CBPFs and regional funds — filter by "
               "hazard, region, GHO context; toggle cumulative. "
               "<a href='dash-donors.html'>Donor shares</a> attribute this money to the "
               "donors of each fund. Donors report their AA funding annually under the "
               "<a href='https://interagencystandingcommittee.org/grand-bargain' "
               "target='_blank' rel='noopener'>Grand Bargain</a>. Internal: "
               "<a href='dash-allocations.html'>allocation explorer</a> · "
               "<a href='questions.html'>coverage of the CERF key data points</a>.",
               panels, json.dumps(data, default=str), js)


# --------------------------------------------------------- model (triggers)
LIFE_LABEL = {"active": "active", "updating": "being updated", "development": "in development"}


def build_model(page, d):
    w = d["windows"].copy()
    cur = d["current"]
    live = cur[cur["lifecycle"].isin(["active", "updating", "development"])]
    wl = w[w["is_latest"].fillna(False).astype(bool)
           & w["lifecycle"].isin(["active", "updating", "development"])].copy()
    wl["hz"] = wl["hazard"].map(haz)
    wl["basis"] = wl["basis"].fillna("unspecified")
    n_trig = int(wl["triggered"].fillna(False).astype(bool).sum())
    fc_share = (wl["basis"].str.contains("forecast", case=False).mean() * 100) if len(wl) else 0
    act = d["act_all"].copy()
    act["year"] = act["event_date"].astype(str).str[:4]
    act = act[act["year"].str.match(r"^\d{4}$")].copy()
    act["year"] = act["year"].astype(int)
    act["kind"] = act["event_type"].map(
        lambda t: "framework" if t == "framework_aa" else "ad hoc / early action")
    cal = d["calendar"]
    cal_rows = "".join(
        f"<tr><td>{r.country_name} — {r.hazard.replace('_', ' ')}</td>"
        f"<td>{_st(LIFE_LABEL.get(r.lifecycle, r.lifecycle))}</td>"
        f"<td>{_cal_strip(cal, r.country_iso3, r.hazard)}</td></tr>"
        for r in live.sort_values("country_name").itertuples())

    def _state(r):
        if r.triggered:
            return "triggered" + (f" ({r.triggered_on})" if pd.notna(r.triggered_on) else "")
        return "not triggered"
    win_rows = "".join(
        f"<tr><td>{r.country_name} — {r.hazard.replace('_', ' ')}</td><td>{r.version}</td>"
        f"<td>{r.window_name}</td><td>{r.basis}</td><td>{_state(r)}</td>"
        f"<td class='num'>{f'1-in-{r.return_period:.1f} yr' if pd.notna(r.return_period) else ''}</td>"
        f"<td class='num'>{f'{r.activation_prob*100:.0f}%' if pd.notna(r.activation_prob) else ''}</td>"
        f"<td class='num'>{f'{int(r.n_activations)} in {int(r.analysis_years)} yrs' if pd.notna(r.n_activations) and pd.notna(r.analysis_years) else ''}</td></tr>"
        for r in wl.sort_values(["country_name", "hazard", "window_name"]).itertuples())
    panels = f"""
<div class='tiles'>
 <div class='tile'><div class='v'>{len(live)}</div><div class='l'>frameworks with a model (active, being updated, in development)</div></div>
 <div class='tile'><div class='v'>{len(wl)}</div><div class='l'>trigger windows on the latest versions</div></div>
 <div class='tile'><div class='v'>{n_trig}</div><div class='l'>windows triggered on the latest versions</div></div>
 <div class='tile'><div class='v'>{fc_share:.0f}%</div><div class='l'>of windows are forecast-based</div></div>
</div>
<div class='grid'>
 <div class='panel'><h3>Trigger windows by hazard × basis</h3><canvas id='m1' height='250'></canvas>
   <div class='note'>Latest version of every live framework; basis from the KB trigger registry.</div></div>
 <div class='panel'><h3>Designed return period of the windows</h3><canvas id='m2' height='250'></canvas>
   <div class='note'>From the backtests (1-in-N years); windows without a backtest are not shown.</div></div>
 <div class='panel' style='grid-column:1/-1'><h3>Activations per year — framework triggers vs ad hoc / early action</h3><canvas id='m3' height='250'></canvas></div>
</div>
<h2>Monitoring calendar</h2>
<p class='meta'>Green cells = months the framework is monitored (trigger-window months).</p>
<section><div class='scroll'><table class='data'><thead><tr><th>framework</th><th>status</th><th>monitoring window</th></tr></thead><tbody>{cal_rows}</tbody></table></div></section>
<h2>Trigger windows (latest versions)</h2>
<section><input class='filter' placeholder='filter windows…' oninput='filt(this)'>
<div class='scroll'><table class='data'><thead><tr><th>framework</th><th>version</th><th>window</th><th>basis</th><th>state</th><th>return period</th><th>annual prob.</th><th>backtest</th></tr></thead><tbody>{win_rows}</tbody></table></div></section>"""
    data = {
        "win": json.loads(_records(wl, ["hz", "basis", "return_period", "triggered"])),
        "act": json.loads(_records(
            act.drop_duplicates(["country_iso3", "hazard", "event_date", "event_type"]),
            ["year", "kind"])),
    }
    js = """
const hz = uniqSorted(D.win, r=>r.hz), bases = uniqSorted(D.win, r=>r.basis);
mkChart('m1','bar',hz,bases.map((b,i)=>({label:b, data:hz.map(h=>D.win.filter(r=>r.hz===h&&r.basis===b).length)})),{stacked:true,count:true});
const bins = [['≤ 1-in-3',0,3],['1-in-3 to 5',3,5],['1-in-5 to 10',5,10],['> 1-in-10',10,1e9]];
mkChart('m2','bar',bins.map(b=>b[0]),[{label:'windows',data:bins.map(b=>D.win.filter(r=>r.return_period!=null&&r.return_period>b[1]&&r.return_period<=b[2]).length)}],{count:true});
const yrs = uniqSorted(D.act, r=>r.year), kinds = ['framework','ad hoc / early action'];
mkChart('m3','bar',yrs,kinds.map((k,i)=>({label:k, data:yrs.map(y=>D.act.filter(r=>r.year===y&&r.kind===k).length)})),{stacked:true,count:true});"""
    _dash_page(page, "pillar-model.html", "Model",
               "<b>The model block of anticipatory action</b> — the triggers: what is "
               "monitored, when, on what basis, how often it is designed to fire, and what "
               "actually fired. One row per trigger window of the latest framework versions.",
               panels, json.dumps(data, default=str), js)


# -------------------------------------------------------------- plan (people)
def build_plan(page, d):
    pr = d["plan_rows"].copy()
    cur = d["current"]
    live = cur[cur["lifecycle"].isin(["active", "updating"])]
    ag = pr[pr["agency"].notna()]
    n_ag = ag["agency"].nunique()
    cov = d["covered"].merge(cur[["country_iso3", "hazard", "country_name", "lifecycle"]],
                             on=["country_iso3", "hazard"], how="left")
    cov = cov[cov["lifecycle"].isin(["active", "updating"])]
    covered = cov["people_covered"].sum()
    fw_ag = (ag.groupby("agency")[["country_iso3", "hazard"]]
             .apply(lambda x: len(x.drop_duplicates())).sort_values(ascending=False))

    def _agencies(c, h):
        return ", ".join(sorted(set(ag.loc[(ag["country_iso3"] == c) & (ag["hazard"] == h), "agency"])))

    def _budget(c, h):
        v = pr.loc[(pr["country_iso3"] == c) & (pr["hazard"] == h) & pr["agency"].notna(), "amount_usd"].sum()
        return _fmt_usd(v) if v else ""

    def _covered(c, h):
        v = cov.loc[(cov["country_iso3"] == c) & (cov["hazard"] == h), "people_covered"].sum()
        return f"{int(v):,}" if v else ""
    fw_rows = "".join(
        f"<tr><td>{r.country_name} — {r.hazard.replace('_', ' ')}</td>"
        f"<td>{_st(LIFE_LABEL.get(r.lifecycle, r.lifecycle))}</td>"
        f"<td>{_agencies(r.country_iso3, r.hazard)}</td>"
        f"<td class='num'>{_budget(r.country_iso3, r.hazard)}</td>"
        f"<td class='num'>{_covered(r.country_iso3, r.hazard)}</td></tr>"
        for r in live.sort_values("country_name").itertuples())
    panels = f"""
<div class='tiles'>
 <div class='tile'><div class='v'>{len(live)}</div><div class='l'>frameworks with a plan (active or being updated)</div></div>
 <div class='tile'><div class='v'>{n_ag}</div><div class='l'>implementing agencies with a pre-arranged budget line</div></div>
 <div class='tile'><div class='v'>{covered/1e6:,.1f}M</div><div class='l'>people covered by the plans (latest figure per framework)</div></div>
</div>
<div class='grid'>
 <div class='panel'><h3>Pre-arranged budget by agency</h3><canvas id='p1' height='300'></canvas>
   <div class='note'>Latest version of every framework that is active or being updated; from the framework documents' agency split. The sector view is on the <a href='dash-funding.html'>Funding</a> page.</div></div>
 <div class='panel'><h3>Frameworks per agency</h3><canvas id='p3' height='300'></canvas></div>
</div>
<h2>Plans by framework</h2>
<section><input class='filter' placeholder='filter…' oninput='filt(this)'>
<div class='scroll'><table class='data'><thead><tr><th>framework</th><th>status</th><th>agencies</th><th>agency budget</th><th>people covered</th></tr></thead><tbody>{fw_rows}</tbody></table></div></section>
<p class='meta'>Delivery detail (CERF projects, sub-grants, localization, cash, people reached) is on the internal <a href='dash-delivery.html'>delivery dashboard</a>.</p>"""
    data = {
        "ag": json.loads(_records(ag, ["agency", "amount_usd"])),
        "fwag": [{"agency": k, "n": int(v)} for k, v in fw_ag.items()],
    }
    js = """
const byA = groupSum(D.ag, r=>r.agency, r=>r.amount_usd), aKeys = Object.keys(byA).sort((a,b)=>byA[b]-byA[a]).slice(0,18);
mkChart('p1','bar',aKeys,[{label:'pre-arranged',data:aKeys.map(k=>byA[k])}],{extra:{indexAxis:'y'}});
const fa = D.fwag.slice(0,20);
mkChart('p3','bar',fa.map(r=>r.agency),[{label:'frameworks',data:fa.map(r=>r.n),backgroundColor:PAL[2]}],{count:true});"""
    _dash_page(page, "pillar-plan.html", "Plan",
               "<b>The plan block of anticipatory action</b> — who acts and for whom: the "
               "agencies with a pre-arranged budget line, the sectors, and the people the "
               "plans cover. Figures follow the latest version of each framework that is "
               "active or being updated.",
               panels, json.dumps(data, default=str), js)


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


def _doc_li(r, key_stat=True):
    """One learning document as a list item: title link · publisher · year · type tag."""
    import html as _h
    title = _h.escape(str(r.title))
    t = (f"<a href='{_h.escape(str(r.url))}' target='_blank' rel='noopener'>{title}</a>"
         if isinstance(r.url, str) and r.url else title)
    who = " · ".join(str(x) for x in [r.publisher if isinstance(r.publisher, str) else None,
                                      int(r.year) if pd.notna(r.year) else None] if x)
    tag = f"<span class='doctag'>{DOC_TYPE_LABEL.get(r.doc_type, str(r.doc_type))}</span>"
    ks = (f"<span class='ks'>{_h.escape(str(r.key_stat))}</span>"
          if key_stat and isinstance(r.key_stat, str) and r.key_stat else "")
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
    import html as _h
    docs = d["learning"].copy()   # internal rows are excluded at the source (_fetch)
    cur = d["current"]
    act = d["act_all"].copy()
    urls = d["act_url"]
    umap = {(r.country_iso3, r.hazard, str(r.event_date), r.window_name): r.url
            for r in urls.itertuples()}
    act["url"] = [umap.get((c, h, str(e), w)) for c, h, e, w in
                  zip(act["country_iso3"], act["hazard"], act["event_date"], act["window_name"])]
    act["year"] = act["event_date"].astype(str).str[:4]
    act = act[act["year"].str.match(r"^\d{4}$")].copy()
    act["kind"] = act["event_type"].map(
        lambda t: "framework" if t == "framework_aa" else str(t).replace("_", " "))
    n_fw = int((act["kind"] == "framework").sum())

    # per-framework document counts (a hazard-less country document counts for every
    # framework of that country)
    fw_docs = {(r.country_iso3, r.hazard): _fw_docs(docs, r.country_iso3, r.hazard)
               for r in cur.itertuples()}
    fw_with = {k for k, v in fw_docs.items() if len(v)}
    n_eval = int(docs["doc_type"].isin(["evaluation", "impact_evaluation"]).sum()) if len(docs) else 0

    def _link(u):
        return f"<a href='{u}' target='_blank' rel='noopener'>record ↗</a>" if isinstance(u, str) and u else ""
    rows = "".join(
        f"<tr><td>{r.event_date}</td><td>{r.country_name or r.country_iso3} — {str(r.hazard).replace('_', ' ')}</td>"
        f"<td>{r.kind}</td><td>{r.version or ''}</td>"
        f"<td>{r.window_name or ''}{(' · ' + r.event_label) if isinstance(r.event_label, str) and r.event_label else ''}</td>"
        f"<td class='num'>{int(r.people_targeted) if pd.notna(r.people_targeted) else ''}</td>"
        f"<td>{_link(r.url)}</td></tr>"
        for r in act.itertuples())

    # (b) what the evidence says — one panel per premise: each claim sits right next to
    # the document it comes from (key_stat — title · publisher · year), documents with a
    # headline figure first, the rest as a compact "more evidence" list
    def _claim_li(r):
        title = _h.escape(str(r.title))
        t = (f"<a href='{_h.escape(str(r.url))}' target='_blank' rel='noopener'>{title}</a>"
             if isinstance(r.url, str) and r.url else title)
        who = " · ".join(str(x) for x in [
            _h.escape(r.publisher) if isinstance(r.publisher, str) else None,
            int(r.year) if pd.notna(r.year) else None] if x)
        return (f"<li><span class='claim'>{_h.escape(str(r.key_stat))}</span> "
                f"<span class='src'>— {t}{(' · ' + who) if who else ''}</span></li>")
    prem_panels = ""
    for key, label in PREMISES:
        sub = docs[[key in _aslist(p) for p in docs["premises"]]] if len(docs) else docs
        has_ks = [isinstance(k, str) and bool(k.strip()) for k in sub["key_stat"]] if len(sub) else []
        with_ks = sub[has_ks] if len(sub) else sub
        rest = sub[[not x for x in has_ks]] if len(sub) else sub
        claims = "".join(_claim_li(r) for r in with_ks.itertuples())
        more = "".join(_doc_li(r, key_stat=False) for r in rest.itertuples())
        body = ((f"<ul class='claims'>{claims}</ul>" if claims else "")
                + (f"<div class='morehd'>{'More evidence' if claims else 'Documents'}</div>"
                   f"<ul class='doclist compact'>{more}</ul>" if more else "")
                + ("" if len(sub) else "<div class='empty'>no documents tagged yet</div>"))
        prem_panels += f"<div class='panel'><h3>{label} <span class='doctag'>{len(sub)}</span></h3>{body}</div>"

    # (c) global learning by document type
    glob = docs[docs["scope"] == "global"] if len(docs) else docs
    glob_html = ""
    for dt in DOC_TYPE_LABEL:
        g = glob[glob["doc_type"] == dt] if len(glob) else glob
        if len(g):
            glob_html += (f"<h3 class='sub'>{DOC_TYPE_LABEL[dt].capitalize()} · {len(g)}</h3>"
                          f"<ul class='doclist'>{''.join(_doc_li(r) for r in g.itertuples())}</ul>")
    if len(glob):
        other = glob[~glob["doc_type"].isin(DOC_TYPE_LABEL)]
        if len(other):
            glob_html += (f"<h3 class='sub'>Untyped · {len(other)}</h3>"
                          f"<ul class='doclist'>{''.join(_doc_li(r) for r in other.itertuples())}</ul>")
    if not glob_html:
        glob_html = "<div class='empty'>no global documents yet</div>"

    # (d) by framework
    fw_rows = ""
    for r in cur.sort_values("country_name").itertuples():
        v = fw_docs[(r.country_iso3, r.hazard)]
        if not len(v):
            continue
        latest = int(v["year"].max()) if v["year"].notna().any() else ""
        fw_rows += (f"<tr><td><a href='fw-{r.country_iso3.lower()}-{r.hazard}.html'>{r.country_name}</a></td>"
                    f"<td>{str(r.hazard).replace('_', ' ')}</td><td class='num'>{len(v)}</td>"
                    f"<td class='num'>{latest}</td></tr>")

    panels = f"""
<div class='tiles'>
 <div class='tile'><div class='v'>{len(docs)}</div><div class='l'>learning documents</div></div>
 <div class='tile'><div class='v'>{n_eval}</div><div class='l'>evaluations and impact evaluations</div></div>
 <div class='tile'><div class='v'>{len(fw_with)}</div><div class='l'>frameworks with at least one document</div></div>
 <div class='tile'><div class='v'>{len(act)}</div><div class='l'>activations recorded — {n_fw} framework triggers, {len(act) - n_fw} ad hoc / early action</div></div>
</div>
<div class='card'><b>What lives here.</b> The evidence on anticipatory action, curated: what the evaluations, after-action reviews and studies say about each of the premises of acting ahead of a shock, the global learning products by type, and the documents per framework. Every activation is a learning event, so the activation records are listed at the bottom.
<span class='note' style='display:block;margin-top:6px'>Internal documents ({d.get('n_internal_docs', 0)} in the database) are held in the database but not shown here.</span></div>
<div class='blk'><h2>What the evidence says</h2>
<p class='meta'>One panel per premise; each headline figure is the document's own key statistic, followed by its source.</p>
<div class='grid'>{prem_panels}</div></div>
<div class='blk'><h2>Global learning</h2>
<p class='meta'>Documents with a global scope, by type.</p>
<section>{glob_html}</section></div>
<div class='blk'><h2>By framework</h2>
<section><div class='scroll' style='max-height:60vh'><table class='data'><thead><tr><th>country</th><th>hazard</th><th>documents</th><th>latest year</th></tr></thead>
<tbody>{fw_rows or '<tr><td colspan=4 class="empty">no framework has a document yet</td></tr>'}</tbody></table></div></section></div>
<div class='blk'><h2>Activation records</h2>
<div class='grid'><div class='panel' style='grid-column:1/-1'><h3>Activations per year</h3><canvas id='l1' height='240'></canvas></div></div>
<section><input class='filter' placeholder='filter…' oninput='filt(this)'>
<div class='scroll'><table class='data'><thead><tr><th>date</th><th>framework</th><th>kind</th><th>version</th><th>window</th><th>people targeted</th><th>record</th></tr></thead><tbody>{rows}</tbody></table></div></section></div>"""
    data = {"act": json.loads(_records(act, ["year", "kind"]))}
    js = """
const yrs = uniqSorted(D.act, r=>r.year), kinds = uniqSorted(D.act, r=>r.kind);
mkChart('l1','bar',yrs,kinds.map(k=>({label:k, data:yrs.map(y=>D.act.filter(r=>r.year===y&&r.kind===k).length)})),{stacked:true,count:true,totals:true});"""
    _dash_page(page, "pillar-learning.html", "Learning",
               "<b>The learning block of anticipatory action</b> — what the evidence "
               "says, premise by premise; the global learning products; the documents "
               "per framework; and the activation records.",
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
        note = f" <span class='muted' style='font-size:11px'>(from version {alt})</span>"
    groups = ""
    for key, label in ORG_GROUPS:
        g = pv[pv["org_type"] == key] if key != "other" else pv[
            ~pv["org_type"].isin([k for k, _ in ORG_GROUPS if k != "other"])]
        if not len(g):
            continue
        items = "".join(
            f"<li>{_h.escape(str(r.name))}"
            f"{(' (' + _h.escape(str(r.acronym)) + ')') if isinstance(r.acronym, str) and r.acronym else ''}"
            f"{(' <span class=' + chr(39) + 'muted' + chr(39) + '>' + ', '.join(str(x).replace('_', ' ') for x in _aslist(r.roles)) + '</span>') if _aslist(r.roles) else ''}"
            f"{(' <span class=' + chr(39) + 'muted' + chr(39) + '>under ' + _h.escape(str(r.agency_parent)) + '</span>') if isinstance(r.agency_parent, str) and r.agency_parent else ''}"
            f"{(' · ' + _fmt_usd(r.amount_usd)) if pd.notna(r.amount_usd) else ''}</li>"
            for r in g.itertuples())
        groups += f"<div class='pg'><h4>{label} · {len(g)}</h4><ul style='margin:0;padding-left:16px'>{items}</ul></div>"
    head = (f"<b>{pv['name'].nunique()} partners</b>{note}" if len(pv)
            else "<span class='empty'>no partners recorded for this version yet</span>")
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
            sub += (f"<div class='pg'><h4>{_h.escape(str(ag))} · {_fmt_usd(g['subgrant_usd'].sum())}"
                    f" to {len(names)}</h4><ul style='margin:0;padding-left:16px'>{items}</ul></div>")
        sub = (f"<h3 class='sub'>Funded sub-grantees <span class='muted' style='font-weight:400'>"
               f"— CERF AA sub-grants in {c}, all activations, by agency</span></h3>"
               f"<div class='partners'>{sub}</div>")
    return (f"<h3 class='sub'>Partners</h3><p style='margin:4px 0 8px'>{head}</p>"
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


def _version_diff(fo, fn, to, tn):
    """Qualitative change sentences between two versions' structured metadata (frontmatter
    fo -> fn, trigger-window rows to -> tn). Only fields recorded on both sides."""
    import html as _h
    fo, fn = fo or {}, fn or {}
    to = [t for t in (to or []) if isinstance(t, dict)]
    tn = [t for t in (tn or []) if isinstance(t, dict)]
    out = []
    both = lambda k: _has(fo.get(k)) and _has(fn.get(k))   # noqa: E731
    esc = lambda s: _h.escape(str(s))                        # noqa: E731
    unit = {0: "zones", 1: "admin-1 areas", 2: "admin-2 areas", 3: "admin-3 areas"}
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
            u = unit.get(lvl, "areas") if isinstance(lvl, (int, float)) else "areas"
            u = u[:-1] if len(g) == 1 else u
            return f"{len(g)} {u} ({', '.join(esc(x) for x in g)})"
        out.append(f"Geographic scope {verb} from {_g(go, lo)} to {_g(gn, ln)}")
    if both("admin_level") and fo["admin_level"] != fn["admin_level"]:
        out.append(f"Admin level {fo['admin_level']} → {fn['admin_level']}")
    # trigger windows
    no = len(to) or (fo.get("trigger_facets") or {}).get("n_windows")
    nn = len(tn) or (fn.get("trigger_facets") or {}).get("n_windows")
    if to and tn:
        pairs, dropped, added = _match_triggers(to, tn)
        bits = ([f"dropped {esc(t.get('window', '?'))} — {esc(t.get('indicator', ''))}" for t in dropped]
                + [f"added {esc(t.get('window', '?'))} — {esc(t.get('indicator', ''))}" for t in added])
        if len(to) != len(tn) or bits:
            out.append(f"Trigger windows: {len(to)} → {len(tn)}" + (f" ({'; '.join(bits)})" if bits else ""))
        cut = lambda x: (str(x)[:110] + '…') if len(str(x)) > 111 else str(x)   # noqa: E731
        thr = [f"{esc(to[i].get('window', ''))}: {esc(cut(to[i].get('threshold')))} → {esc(cut(tn[j].get('threshold')))}"
               for i, j in pairs if _has(to[i].get("threshold")) and _has(tn[j].get("threshold"))
               and str(to[i]["threshold"]).strip() != str(tn[j]["threshold"]).strip()]
        if thr:
            out.append("Thresholds changed — " + "; ".join(thr))
    elif no and nn and no != nn:
        out.append(f"Trigger windows: {no} → {nn}")
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
        bits = swaps + [f"dropped {esc(x)}" for x in gone] + [f"added {esc(x)}" for x in new]
        if kept:
            bits.append(f"{', '.join(esc(x) for x in kept)} kept")
        out.append("Indicators: " + "; ".join(bits))
    for k, lab in [("basis", "Trigger basis"), ("calibration", "Calibration")]:
        if _has(tfo.get(k)) and _has(tfn.get(k)) and tfo[k] != tfn[k]:
            out.append(f"{lab}: {esc(tfo[k])} → {esc(tfn[k])}")
    # monitoring months
    mo = (fo.get("monitoring_period") or {}).get("months") if isinstance(fo.get("monitoring_period"), dict) else None
    mn = (fn.get("monitoring_period") or {}).get("months") if isinstance(fn.get("monitoring_period"), dict) else None
    _mi = lambda ms: sorted({int(x) for x in (ms or []) if isinstance(x, int) and 1 <= x <= 12})  # noqa: E731
    mo, mn = _mi(mo) if _has(mo) else None, _mi(mn) if _has(mn) else None
    if mo and mn and mo != mn:
        nm = lambda ms: ", ".join(MONTH_ABBR[x - 1] for x in ms)  # noqa: E731
        out.append(f"Monitoring months: {nm(mo)} → {nm(mn)}")
    # money
    for k, lab in [("prearranged_funding_usd", "Pre-arranged"), ("cofinancing_usd", "Co-financing")]:
        if both(k):
            try:
                a, b = float(fo[k]), float(fn[k])
            except (TypeError, ValueError):
                continue
            if abs(a - b) > 0.5:
                out.append(f"{lab}: {_m(a)} → {_m(b)}")
    for k, lab in [("funding_by_source", "Funding by source"), ("funding_by_sector", "Sectors"),
                   ("funding_by_agency", "Agency budgets")]:
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
        for x in sorted(set(a) | set(b), key=lambda s: -float(b.get(s) or a.get(s) or 0)):
            va, vb = a.get(x), b.get(x)
            if va is not None and vb is not None:
                if abs(float(va) - float(vb)) > 0.5:
                    bits.append(f"{esc(x)} {_m(va)} → {_m(vb)}")
            elif va is None and vb is not None:
                bits.append(f"{esc(x)} added ({_m(vb)})")
            elif va is not None:
                bits.append(f"{esc(x)} dropped (was {_m(va)})")
        if bits:
            out.append(f"{lab}: " + "; ".join(bits))
    # agencies (the list, else the budget dict's keys)
    ao = fo.get("implementing_agencies") if _has(fo.get("implementing_agencies")) else list((fo.get("funding_by_agency") or {}).keys())
    an = fn.get("implementing_agencies") if _has(fn.get("implementing_agencies")) else list((fn.get("funding_by_agency") or {}).keys())
    if ao and an and set(ao) != set(an):
        add, rem = sorted(set(an) - set(ao)), sorted(set(ao) - set(an))
        out.append("Agencies: " + "; ".join(
            ([f"added {', '.join(esc(x) for x in add)}"] if add else [])
            + ([f"removed {', '.join(esc(x) for x in rem)}"] if rem else [])))
    if both("target_people") and fo["target_people"] != fn["target_people"]:
        try:
            out.append(f"Target people {int(fo['target_people']):,} → {int(fn['target_people']):,}")
        except (TypeError, ValueError):
            pass
    if both("data_sources") and set(map(str, fo["data_sources"])) != set(map(str, fn["data_sources"])):
        add = sorted(set(map(str, fn["data_sources"])) - set(map(str, fo["data_sources"])))
        rem = sorted(set(map(str, fo["data_sources"])) - set(map(str, fn["data_sources"])))
        out.append("Data sources: " + "; ".join(
            ([f"added {', '.join(esc(x) for x in add)}"] if add else [])
            + ([f"removed {', '.join(esc(x) for x in rem)}"] if rem else [])))
    if fo.get("all_in") is not None and fn.get("all_in") is not None and fo["all_in"] != fn["all_in"]:
        out.append("Funding model: " + ("split by window → all-in" if fn["all_in"] else "all-in → split by window"))
    return out


def _changes_block(fvm, vpage, c, h):
    """'What changed between versions': newest pair first."""
    import html as _h
    v = fvm[(fvm["country_iso3"] == c) & (fvm["hazard"] == h)].copy()
    if len(v) < 2:
        return ("<div class='blk'><h2>What changed between versions</h2>"
                "<p class='empty'>Only one version is registered — nothing to compare yet.</p></div>")
    v["_vf"] = pd.to_datetime(v["valid_from"], errors="coerce")
    v = v.sort_values(["_vf", "version"])
    pg = {(r.kb_framework, str(r.version)): (r.frontmatter, r.triggers) for r in vpage.itertuples()}
    items = ""
    rows = list(v.itertuples())
    for old, new in reversed(list(zip(rows[:-1], rows[1:]))):
        fo, to = pg.get((old.kb_framework, str(old.version)), (None, None))
        fn, tn = pg.get((new.kb_framework, str(new.version)), (None, None))
        diff = _version_diff(fo, fn, to, tn) if (fo or to) and (fn or tn) else []
        body = ("<ul>" + "".join(f"<li>{x}</li>" for x in diff) + "</ul>" if diff
                else "<p class='empty' style='padding:2px 0'>no structured change recorded</p>")
        note = (f"<p class='vnote'><b>Note:</b> {_h.escape(str(new.note))}</p>"
                if isinstance(new.note, str) and new.note.strip() else "")
        items += (f"<div class='vchg'><h4>{_h.escape(str(old.version))} → {_h.escape(str(new.version))}"
                  f"</h4>{body}{note}</div>")
    return ("<div class='blk'><h2>What changed between versions</h2>"
            "<p class='meta'>Derived from the recorded framework metadata (scope, trigger windows, "
            "indicators, monitoring months, budgets) — only fields recorded for both versions are "
            "compared. Narrative notes on each change can be added to the version record and will "
            "appear under the pair.</p>" + items + "</div>")


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
    win = d["windows"]
    wv = win[(win["country_iso3"] == c) & (win["hazard"] == h) & (win["version"].astype(str) == str(shown))]
    wins = sorted(set(ss["window_name"].dropna()) | set(wv["window_name"].dropna()))
    # backtest range: N analysed years ending at the later of the last simulated year and
    # the year before the version took effect
    n_years = pd.to_numeric(wv["analysis_years"], errors="coerce").max() if len(wv) else None
    rows = {}   # (year, label) -> {'cell': [...], window: [...]}
    sim_years = set()   # years the historical simulation covers; others are greyed out
    if len(ss):
        vf = fvm.loc[fvm["version"].astype(str) == shown, "valid_from"]
        vf_y = pd.to_datetime(vf, errors="coerce").dt.year.max() if len(vf) else None
        y1 = int(max(ss["event_year"].max(), (vf_y - 1) if vf_y and pd.notna(vf_y) else 0))
        y0 = int(y1 - n_years + 1) if n_years and pd.notna(n_years) else int(ss["event_year"].min())
        y0 = min(y0, int(ss["event_year"].min()))
        labelled = ss[ss["event_label"].fillna("").astype(str) != ""]
        sim_years = set(range(y0, y1 + 1))
        for y in range(y0, y1 + 1):
            if not (labelled["event_year"] == y).any():
                rows[(y, "")] = {}
        for r in ss.itertuples():
            key = (int(r.event_year), str(r.event_label) if isinstance(r.event_label, str) else "")
            rows.setdefault(key, {}).setdefault(r.window_name, []).append(
                f"<span class='dot sim' style='background:{col}' title='{esc(r.window_name)}: would have fired in {int(r.event_year)} (simulation)'></span>")
    # real activations, one entry per event with its funding rows
    act = d["act_all"][(d["act_all"]["country_iso3"] == c) & (d["act_all"]["hazard"] == h)].copy()
    fund = d["activation"][(d["activation"]["country_iso3"] == c) & (d["activation"]["hazard"] == h)]
    cy = dict(zip(d["cerf_year"]["application_code"], d["cerf_year"]["year"]))
    wa = d["wact"][(d["wact"]["country_iso3"] == c) & (d["wact"]["hazard"] == h)]
    full = {(str(r.event_date), r.window_name): r.full_activation for r in wa.itertuples()}
    au = d["actual_url"][d["actual_url"]["kb_framework"] == kb_fw] if kb_fw else d["actual_url"].iloc[0:0]
    events = []
    for r in act.sort_values("event_date", ascending=False).itertuples():
        ed, wn = str(r.event_date), r.window_name
        wn = wn if isinstance(wn, str) else ""
        f = fund[(fund["event_date"].astype(str) == ed) & (fund["event_type"] == r.event_type)
                 & (fund["window_name"].fillna("") == wn)]
        ann = umap.get((c, h, ed, wn or r.window_name))
        other = [u for u in au.loc[[str(x)[:7] == ed[:7] and (_loose(w, wn) or not wn)
                                    for x, w in zip(au["event_date"], au["window_name"])], "url"]
                 if isinstance(u, str) and u and u != ann]
        cerf = [(x.allocation_code, _cerf_page(x.allocation_code, cy)) for x in f.itertuples()
                if x.fund_code == "cerf" and isinstance(x.allocation_code, str)]
        events.append(dict(date=ed, win=wn if isinstance(wn, str) else "", typ=str(r.event_type),
                           label=r.event_label if isinstance(r.event_label, str) else "",
                           version=str(r.version) if pd.notna(r.version) else "", fund=f,
                           ann=ann if isinstance(ann, str) and ann else None, other=other,
                           cerf=cerf, partial=full.get((ed, wn)) is False))
    for ev in events:
        amt = "; ".join(f"{x.fund_code} {_m(x.amount_usd)}" for x in ev["fund"].itertuples()
                        if pd.notna(x.amount_usd)) or "amount not recorded"
        href = ev["ann"] or next((u for _, u in ev["cerf"] if u), None) or (ev["other"][0] if ev["other"] else None)
        vv = "" if ev["version"] is None or str(ev["version"]) in ("nan", "None", "NaT", "<NA>") else str(ev["version"])
        # no version = an ad hoc allocation: neither this version nor an earlier one
        same = (not vv) or (shown is not None and (vv == shown or vv.startswith(shown) or shown.startswith(vv)))
        tip = (f"{ev['date']} · {ev['win'] or ev['typ'].replace('_', ' ')} · {amt}"
               + (" · ad hoc allocation (no framework version)" if not vv else "" if same else f" · under version {vv}")
               + (" · partial activation" if ev["partial"] else ""))
        mk = (f"<span class='dot {'real' if same else 'old'}'></span>")
        mk = (f"<a href='{esc(href)}' target='_blank' rel='noopener' title='{esc(tip)}'>{mk}</a>"
              if href else f"<span title='{esc(tip)}'>{mk}</span>")
        y = int(ev["date"][:4]) if ev["date"][:4].isdigit() else None
        if y is None:
            continue
        keys = [k for k in rows if k[0] == y]
        key = next((k for k in keys if ev["label"] and _loose(k[1], ev["label"])), None) \
            or next((k for k in keys if k[1] == ""), None)
        if key is None:
            key = (y, ev["label"] or ("activation" if keys else ""))
            rows.setdefault(key, {})
        wmatch = next((w for w in wins if _loose(w, ev["win"])), None)
        rows[key].setdefault(wmatch or "__cell", []).append(mk)
    # ---- the grid
    if not rows:
        hist = "<p class='empty'>No backtest and no activation recorded for this framework.</p>"
    else:
        head = "".join(f"<th>{esc(w)}</th>" for w in wins)
        body = ""
        for (y, lab) in sorted(rows, key=lambda k: (-k[0], k[1])):
            cells = rows[(y, lab)]
            body += (f"<tr><td class='yr'>{y}{(' <span class=' + chr(39) + 'muted' + chr(39) + '>' + esc(lab) + '</span>') if lab else ''}"
                     f"{' ' + ''.join(cells.get('__cell', [])) if cells.get('__cell') else ''}</td>"
                     + "".join((f"<td>{''.join(cells.get(w, []))}</td>" if y in sim_years or not sim_years else
                                f"<td class='na' title='{y} is not covered by the historical simulation'>{''.join(cells.get(w, []))}</td>")
                               for w in wins) + "</tr>")
        vnote = ("" if shown is None else
                 f"Backtest of version <code>{esc(shown)}</code>"
                 + ("" if str(shown) == str(version) else " (the current version has no recorded backtest)")
                 + (f", {int(n_years)} years analysed" if n_years and pd.notna(n_years) else "") + ". ")
        hist = (f"<p class='meta'>{vnote or 'No backtest recorded for this framework — real activations only. '}"
                "One row per year, newest first; a real activation whose window does not match a "
                "column sits in the year cell. Markers link to the announcement or the CERF allocation.</p>"
                f"<table class='data hist'><thead><tr><th>year</th>{head}</tr></thead><tbody>{body}</tbody></table>"
                f"<p class='legend'><span class='dot sim' style='background:{col}'></span> would have fired (simulation) · "
                f"<span class='dot real'></span> activated, money released · "
                f"<span class='dot old'></span> activated under "
                + ("an earlier version" if str(shown) == str(version) else "a different version (hover for which)")
                + "</p>")
    # ---- actual activations table
    if not events:
        actual = "<p class='empty'>No activation recorded.</p>"
    else:
        tr = ""
        for ev in events:
            fl = "<br>".join(
                f"{esc(x.fund_code)}: {'' if pd.isna(x.amount_usd) else '$' + format(x.amount_usd, ',.0f')}"
                for x in ev["fund"].itertuples()) or "<span class='muted'>not recorded</span>"
            links = [f"<a href='{esc(u)}' target='_blank' rel='noopener'>CERF {esc(code)} ↗</a>"
                     for code, u in ev["cerf"] if u]
            links += [f"<span class='muted'>{esc(code)}</span>" for code, u in ev["cerf"] if not u]
            if ev["ann"]:
                links.append(f"<a href='{esc(ev['ann'])}' target='_blank' rel='noopener'>announcement ↗</a>")
            links += [f"<a href='{esc(u)}' target='_blank' rel='noopener'>other ↗</a>" for u in ev["other"]]
            vtag = ("" if (not ev["version"] or str(ev["version"]) == str(version))
                    else f" <span class='doctag' title='This activation fired under version {esc(ev['version'])}, an earlier version of the framework than the current one ({esc(version)}); its triggers and budget may differ.'>earlier version</span>")
            tr += (f"<tr><td>{esc(ev['date'])}</td><td>{esc(ev['version'])}{vtag}</td>"
                   f"<td>{esc(ev['win'])}{(' · ' + esc(ev['label'])) if ev['label'] else ''}"
                   f"{'' if ev['typ'] == 'framework_aa' else ' <span class=' + chr(39) + 'muted' + chr(39) + '>(' + esc(ev['typ'].replace('_', ' ')) + ')</span>'}"
                   f"{' <span class=' + chr(39) + 'warn-tag' + chr(39) + '>partial</span>' if ev['partial'] else ''}</td>"
                   f"<td>{fl}</td><td>{' · '.join(links)}</td></tr>")
        actual = ("<table class='data acts'><colgroup><col style='width:10%'><col style='width:17%'>"
                  "<col style='width:28%'><col style='width:17%'><col style='width:28%'></colgroup>"
                  "<thead><tr><th>date</th><th>version</th><th>window</th><th>funding</th><th>links</th>"
                  f"</tr></thead><tbody>{tr}</tbody></table>")
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
            lab = f"Trigger analysis code — <code>{esc(ref.strip())}</code>"
            items.append((f"<a href='{esc(u)}' target='_blank' rel='noopener'>{lab} ↗</a>" if u else lab)
                         + ("" if is_cur else f" <span class='muted'>(version {esc(r['version'])})</span>"))
    r, is_cur = _pick("doc_url")
    if r is not None:
        t = r["doc_title"] if isinstance(r["doc_title"], str) and r["doc_title"] else "Framework document"
        items.append(f"<a href='{esc(r['doc_url'])}' target='_blank' rel='noopener'>{esc(t)} ↗</a>"
                     + ("" if is_cur else f" <span class='muted'>(version {esc(r['version'])})</span>"))
    if TRIGGER_VALIDATION_URL:
        items.append(f"<a href='{esc(TRIGGER_VALIDATION_URL)}' target='_blank' rel='noopener'>"
                     "Trigger validation folder (Drive) ↗</a>")
    body = ("<ul class='doclist'>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>" if items
            else "<p class='empty'>Technical documentation not yet linked.</p>")
    return ("<h3 class='sub'>Trigger validation &amp; technical work</h3>" + body
            + "<p class='meta'>The full trigger validation will be published on this page in future.</p>")


def build_framework_pages(page, tbl, d, e=None):
    cur, ver, act = d["current"], d["versions"], d["activation"]
    pre, cov, foc = d["prearranged"], d["covered"], d["focal"]
    rep, cal = d["report"], d["calendar"]
    split, env, win = d["split_all"], d["env_all"], d["windows"]
    docs, pt, sg = d["learning"], d["partners"], d["subgrant_aa"]
    urls = d["act_url"]
    umap = {(r.country_iso3, r.hazard, str(r.event_date), r.window_name): r.url
            for r in urls.itertuples()}
    try:
        trig = _kb_trigger_info(e) if e is not None else {}
    except Exception as exc:
        print(f"  framework pages: KB trigger info unavailable ({exc.__class__.__name__})")
        trig = {}
    links = []
    for _, fw in cur.sort_values("country_name").iterrows():
        c, h = fw["country_iso3"], fw["hazard"]
        slug = f"fw-{c.lower()}-{h}"
        links.append((fw["country_name"], h, fw.get("lifecycle") or fw["status"], slug, c))
        version = fw["current_version"] if pd.notna(fw.get("current_version")) else None
        kb_fw = fw["kb_framework"] if pd.notna(fw.get("kb_framework")) else None
        v = ver[(ver["country_iso3"] == c) & (ver["hazard"] == h)]
        a = act[(act["country_iso3"] == c) & (act["hazard"] == h)]
        p = pre[(pre["country_iso3"] == c) & (pre["hazard"] == h)
                & (pre["kind"] == "prearranged") & (pre["fund_code"] != "all")]
        f = foc[(foc["country_iso3"] == c) & (foc["hazard"] == h)]
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
            f"<tr><td>{x.window_name}</td><td>{x.basis if pd.notna(x.basis) else ''}"
            f"{' · all-in' if x.all_in is True else ''}</td>"
            f"<td>{'triggered' + (f' ({x.triggered_on})' if pd.notna(x.triggered_on) else '') if x.triggered else 'not triggered'}</td>"
            f"<td class='num'>{_fmt_usd(x.allocation_usd)}</td>"
            f"<td class='num'>{f'1-in-{x.return_period:.1f} yr' if pd.notna(x.return_period) else ''}</td>"
            f"<td class='num'>{f'{x.activation_prob*100:.0f}%' if pd.notna(x.activation_prob) else ''}</td>"
            f"<td class='num'>{f'{int(x.n_activations)} in {int(x.analysis_years)} yrs' if pd.notna(x.n_activations) and pd.notna(x.analysis_years) else ''}</td></tr>"
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
            split_note = (f" <span class='muted' style='font-size:11px'>(split and envelope from "
                          f"version {split_version} — the current version has no split yet)</span>")
        # the envelope of the SAME version as the split, so the comparison is like for like
        ev = (env[(env["country_iso3"] == c) & (env["hazard"] == h)
                  & (env["version"].astype(str) == str(split_version))]
              if split_version else env.iloc[0:0])
        comp = ev[ev["fund_code"] != "all"]
        envelope = float(comp["total_usd"].sum()) if len(comp) else float(ev["total_usd"].sum())
        split_total = float(sv["amount_usd"].sum())
        over = envelope > 0 and split_total > envelope * 1.01
        agencies = sorted(set(sv.loc[sv["agency"].notna(), "agency"]))
        srows = "".join(
            f"<tr><td>{x.window_name or ''}</td><td>{x.agency if pd.notna(x.agency) else ''}</td>"
            f"<td>{x.sector if pd.notna(x.sector) else ''}</td><td>{x.fund_code if pd.notna(x.fund_code) else ''}</td>"
            f"<td class='num'>${x.amount_usd:,.0f}</td></tr>" for x in sv.itertuples())
        split_foot = (
            f"<tr><th colspan=4>split total</th><th class='num'>${split_total:,.0f}</th></tr>"
            f"<tr><th colspan=4>version envelope (pre-arranged)</th><th class='num'>"
            f"{f'${envelope:,.0f}' if envelope else '—'}"
            f"{'<span class=' + chr(39) + 'warn-tag' + chr(39) + '>split exceeds envelope by ' + f'{(split_total/envelope - 1)*100:.0f}' + '%</span>' if over else ''}</th></tr>")
        # budget by agency / by sector (bars) and agency -> sector (Sankey), same split rows
        split_js = [{"a": x.agency if isinstance(x.agency, str) and x.agency else "(agency not stated)",
                     "s": x.sector if isinstance(x.sector, str) and x.sector else "(sector not stated)",
                     "v": float(x.amount_usd)} for x in sv.itertuples() if pd.notna(x.amount_usd)]
        plan_charts = ("<div class='grid' style='margin-top:12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr))'>"
                       "<div class='panel'><h3>Budget by agency</h3><div id='pAg'></div></div>"
                       "<div class='panel'><h3>Budget by sector</h3><div id='pSe'></div></div>"
                       "<div class='panel' style='grid-column:1/-1'><h3>Agency → sector</h3><div id='pSk'></div>"
                       "<div class='note'>From the split rows above (version "
                       f"{split_version or '—'}); a window-level split that repeats the same money "
                       "across alternative windows is summed as recorded — compare the split total with "
                       "the envelope.</div></div></div>") if split_js else ""
        vrows = "".join(
            f"<tr><td>{x.version}</td><td>{x.kb_status if pd.notna(x.kb_status) else ''}</td><td>{x.source}</td>"
            f"<td>{f'<a href={x.doc_url!r}>doc</a>' if pd.notna(x.doc_url) else ''}</td>"
            f"<td style='max-width:340px'>{x.analysis_ref if pd.notna(x.analysis_ref) else ''}</td></tr>"
            for x in v.itertuples())
        frows = "".join(f"<span class='badge b-kb'>{x.role}: {x.person}</span>"
                        for x in f.itertuples())
        rrows = ", ".join(sorted({f"{x.channel} ({x.report_year})"
                                  for x in r.itertuples()}))
        covered_txt = (f"{int(pc['people_covered'].iloc[0]):,}"
                       if not pc.empty else "—")
        # ---- Learning: the framework's documents
        fd = _fw_docs(docs, c, h)
        fd_html = (f"<ul class='doclist'>{''.join(_doc_li(x) for x in fd.itertuples())}</ul>"
                   if len(fd) else "<div class='empty'>no documents yet</div>")
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
{changes_html}
<div class='blk'><h2>Model</h2>
<p class='meta'>{('Trigger: ' + trig_line) if trig_line else 'No structured trigger info in the KB for this version.'}</p>
<h3 class='sub'>Windows and backtests (version {version or '—'})</h3>
<section><div class='scroll' style='max-height:260px'><table class='data'><thead>
<tr><th>window</th><th>basis</th><th>state</th><th>budget</th><th>return period</th><th>annual prob.</th><th>backtest</th></tr></thead>
<tbody>{wrows or '<tr><td colspan=7 class="empty">no windows registered for this version</td></tr>'}</tbody></table></div></section>
<h3 class='sub'>Actual activations</h3>
<section>{actual_html}</section>
<h3 class='sub'>Historical activations</h3>
<section>{hist_html}</section>
{valid_html}</div>
<div class='blk'><h2>Plan</h2>
<div class='tiles'>
 <div class='tile'><div class='v'>{covered_txt}</div><div class='l'>people covered (latest figure)</div></div>
 <div class='tile'><div class='v'>{len(agencies) or '—'}</div><div class='l'>agencies with a budget line{(': ' + ', '.join(agencies)) if agencies else ''}</div></div>
</div>
<h3 class='sub'>Agency × sector split{split_note}</h3>
<section><div class='scroll' style='max-height:360px'><table class='data'><thead>
<tr><th>window</th><th>agency</th><th>sector</th><th>fund</th><th>USD</th></tr></thead>
<tbody>{srows or '<tr><td colspan=5 class="empty">no split recorded</td></tr>'}</tbody>
<tfoot>{split_foot}</tfoot></table></div></section>
{plan_charts}
{_partners_block(pt, sg, c, h, version)}</div>
<div class='blk'><h2>Funding</h2>
<div class='grid'>
<div class='panel'><h3>Pre-arranged funding in place, by year × fund</h3><div class='note'>The envelope in place each year — a stock, so the bars are not added up.</div><canvas id='pf' height='230'></canvas></div>
<div class='panel'><h3>Versions (endorsed documents)</h3>
<div class='scroll' style='max-height:230px'><table class='data'><thead>
<tr><th>version</th><th>KB status</th><th>source</th><th>doc</th><th>analysis</th></tr></thead>
<tbody>{vrows or '<tr><td colspan=5>none registered</td></tr>'}</tbody></table></div></div>
</div>
<p class='meta'>Counted in reports: {rrows or '—'}</p></div>
<div class='blk'><h2>Learning · {len(fd)} document{'' if len(fd) == 1 else 's'}</h2>
{fd_html}</div>
<script src="chart.umd.js"></script>
<script src="sankey.js"></script>
<script>window.FD = {json.dumps(chart_data)}; window.SPLIT = {json.dumps(split_js)};</script>
<script>{DASH_JS}
const ds = Object.entries(FD.series).map(([fc,vals],i)=>({{label:fc,data:vals,
  backgroundColor:FUND_COLORS[fc==='cerf'?'cerf':(fc.startsWith('rhpf')?'regional_fund':'cbpf')]||PAL[i]}}));
if(FD.years.length) mkChart('pf','bar',FD.years,ds,{{stacked:true, totals:true}});
else document.getElementById('pf').outerHTML='<p class="meta">no funding rows</p>';
if(SPLIT.length && window.sankeySVG){{
  const bars = k => {{ const g = groupSum(SPLIT, r=>r[k], r=>r.v);
    return Object.keys(g).sort((a,b)=>g[b]-g[a]).map(x=>({{label:x, v:g[x]}})); }};
  const AG = bars('a'), SE = bars('s');
  document.getElementById('pAg').innerHTML = hbarsSVG(AG, {{width:460, fmt:money, labelW:130, colorBy:'a', label:'budget by agency'}});
  document.getElementById('pSe').innerHTML = hbarsSVG(SE, {{width:460, fmt:money, labelW:130, color:'#64748b', label:'budget by sector'}});
  const L = {{}}; SPLIT.forEach(r=>{{ const k='a:'+r.a+'|s:'+r.s; L[k]=(L[k]||0)+r.v; }});
  document.getElementById('pSk').innerHTML = sankeySVG({{
    columns:[AG.map(x=>({{id:'a:'+x.label,label:x.label}})), SE.map(x=>({{id:'s:'+x.label,label:x.label}}))],
    links:Object.entries(L).map(([k,v])=>{{ const [s,t]=k.split('|'); return {{s,t,v}}; }}),
    width:900, height:Math.max(110, Math.max(AG.length,SE.length)*26), fmt:money, labelW:150,
    label:'pre-arranged budget from agency to sector'}});
}}
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
<div class='tile'><a href='dash-donors.html'><b>Donor shares</b></a><div class='l'>each donor's share of AA released / pre-arranged, via their contributions to CERF and the CBPFs; build earmarks</div></div>
<div class='tile'><a href='dash-allocations.html'><b>Allocation explorer</b></a><div class='l'>query every CERF + CBPF allocation 2006→; complementarity; timeliness</div></div>
<div class='tile'><a href='dash-delivery.html'><b>Delivery & people</b></a><div class='l'>subgrants, localization, agencies, sectors, CVA, people reached</div></div>
<div class='tile'><a href='pillar-learning.html'><b>Learning</b></a><div class='l'>the evidence by premise, global learning products, documents per framework, activation records</div></div>
<div class='tile'><a href='media.html'><b>Media & visuals</b></a><div class='l'>videos, photos, social posts and press releases on AA (collection starting)</div></div>
</div></div>
<h2 id='frameworks'>Per-framework pages</h2>
<p class='meta' id='calendar'>Green cells = trigger-window months (monitoring calendar).</p>
<section><input class='filter' placeholder='filter frameworks…' oninput='filt(this)'>
<div class='scroll'><table class='data'><thead><tr><th>framework</th><th>status</th><th>monitoring window</th></tr></thead>
<tbody>{fw_items}</tbody></table></div></section>
<style>{DASH_CSS}</style>"""
    page("dashboards.html", "Dashboards", body)


def build_media(page):
    """media.html — the public 'Media & visuals' page: a simple card page with an empty
    state until the collection (videos, photos, social posts, press releases) exists."""
    body = f"""
<div class='card'><b>Media &amp; visuals of anticipatory action.</b> This page will collect
the best material on AA — videos, photos, social posts and press releases from the
activations and the frameworks — so that every activation's story is one click away
from its record. Nothing is sourced yet: the collection starts with the learning
documents now being imported, and each item will link back to the framework it
belongs to.</div>
<div class='card' style='text-align:center;padding:40px 20px'>
<div style='font-size:34px;line-height:1'>▶</div>
<div class='empty' style='margin-top:10px'>No media collected yet.</div>
<p class='meta' style='margin:8px 0 0'>Meanwhile: <a href='pillar-learning.html'>Learning</a> lists the evaluations,
after-action reviews and stories on record, and each framework page links its documents.</p>
</div>
<style>{DASH_CSS}</style>"""
    page("media.html", "Media & visuals", body)




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


def _kb_trigger_info(e):
    """Structured trigger info per (kb_framework, version) from aa.version_page."""
    from ds_aa_tracking.kb_pages import load_version_pages

    out = {}
    for (fw, ver), pg in load_version_pages(e).items():
        fm = pg["fm"]
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
            out[(fw, ver)] = " · ".join(bits)
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
                      FROM aa.window_funding
                      WHERE agency IS NULL AND sector IS NULL AND kind = 'prearranged'
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
    trig = _kb_trigger_info(e)
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
    build_model(page, d)
    build_plan(page, d)
    build_learning(page, d)
    build_allocations(page, d)
    build_delivery(page, d)
    import donors
    donors.build_donors(page, d)
    build_questions(page)
    links = build_framework_pages(page, tbl, d, e)
    build_hub(page, d, links)
    build_media(page)
    build_hierarchy(page, d, e)
    build_entry(page, d, e)
    build_status_form(page, d)
    import landing
    landing.build_landing(page, d, e)
