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


# Early-action (EA) allocations are kept in the database but never shown or counted on the
# site (decision 2026-09-30, a colleague's review: EA "opens a Pandora's box"). One place:
# every activation query filters on this. Remove the value to bring EA back.
EXCLUDED_EVENT_TYPES = ("early_action",)
_EXCL_SQL = ", ".join(f"'{t}'" for t in EXCLUDED_EVENT_TYPES)
# The CERF AA allocations the site counts: the ones the activation record draws on (framework
# and ad hoc; early action excluded), as the Financing page and the Plan page count them — not
# the mirror's title keyword (aa_keyword), which also flags early-action allocations and misses
# ad hoc AA with a plain title (2026-10-02 meeting: released by agency and by sector did not
# match the curated figures). An activation whose CERF allocation code is not recorded yet
# cannot be split; the Delivery page lists those.
_CERF_AA_CODES_SQL = ("SELECT DISTINCT allocation_code FROM aa.activation_funding "
                      "WHERE fund_code = 'cerf' AND allocation_code IS NOT NULL "
                      "AND event_type NOT IN (" + _EXCL_SQL + ")")


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
.fwhead button, .fwnote button { padding:4px 9px; border:1px solid #bbb; border-radius:4px; background:#f7f8fa;
                                 font-size:12px; cursor:pointer; white-space:nowrap; }
.fwlist { overflow-y:auto; padding:4px 12px 8px; }
.fwlist label { display:flex; gap:8px; align-items:baseline; padding:2px 0; font-size:12.5px; color:#1a1a1a; cursor:pointer; }
.fwlist label.grp { font-weight:600; margin-top:8px; padding-bottom:3px; border-bottom:1px solid #eef0f3; }
.fwlist label.off { opacity:.45; }
.fwlist .nm { flex:1; min-width:0; } .fwlist .st { color:#667; font-size:11.5px; white-space:nowrap; }
.fwlist .amt { min-width:92px; text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
.fwlist .cap { text-align:right; font-size:11px; color:#778; padding-top:5px; }
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
                             "source": "version-inferred"})
    if not rows:
        return pre
    return pd.concat([pre, pd.DataFrame(rows)[pre.columns]], ignore_index=True)


def prearranged_now(e):
    """THE definition of pre-arranged money now, from the framework records (2026-09-29):
    for every live framework (active, being updated, in development — in-development ones
    count once the ERC approved the pre-arrangement), the envelope of its MOST RECENT
    VERSION THAT HAS ONE (a framework being updated keeps its last envelope), per fund, from
    aa.v_version_funding; an 'all' total only where no per-fund split exists. Every page
    that shows pre-arranged money now uses this: the Funding tile, the map tiles, and the
    current year of the annual series (so the donor page and the flow chart agree).
    Live frameworks with no envelope in any version are NOT filled from the sheets: they
    are listed as gaps (see envelope_gaps)."""
    now = pd.read_sql(
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
                     AND y.hazard = x.hazard AND y.version = x.version AND y.fund_code <> 'all'))),
           pick AS (
               SELECT DISTINCT ON (country_iso3, hazard) country_iso3, hazard, version
               FROM env2 ORDER BY country_iso3, hazard, valid_from DESC NULLS LAST, version DESC)
           SELECT x.country_iso3, x.hazard, x.version, x.fund_code, x.total_usd,
                  l.lifecycle, l.latest_version
           FROM env2 x
           JOIN pick USING (country_iso3, hazard, version)
           JOIN aa.v_framework_lifecycle l USING (country_iso3, hazard)
           WHERE l.lifecycle IN ('active', 'updating', 'development')
           ORDER BY 1, 2, 4""", e)
    # an envelope recorded as "CBPF, fund not named" belongs to the country's own pooled fund,
    # or its regional fund where it has no country fund (Burkina Faso -> RhPF-WCA)
    reg = pd.read_sql("SELECT fund_code, fund_type, country_iso3 FROM aa.fund WHERE country_iso3 IS NOT NULL", e)
    own = {r.country_iso3: r.fund_code for r in reg.itertuples() if r.fund_type == "cbpf"}
    regional = {r.country_iso3: r.fund_code for r in reg.itertuples() if r.fund_type == "regional_fund"}
    un = now["fund_code"] == "cbpf-unspecified"
    now.loc[un, "fund_code"] = [own.get(c) or regional.get(c) or "cbpf-unspecified"
                                for c in now.loc[un, "country_iso3"]]
    return (now.groupby(["country_iso3", "hazard", "version", "fund_code", "lifecycle", "latest_version"],
                        as_index=False, dropna=False)["total_usd"].sum())


def envelope_gaps(d):
    """Live frameworks with no pre-arranged envelope in any version (listed, never filled)."""
    cur = d["current"]
    live = cur[cur["lifecycle"].isin(["active", "updating", "development"])]
    have = set(zip(d["vfund"]["country_iso3"], d["vfund"]["hazard"]))
    return [(r.country_name or r.country_iso3, r.hazard, r.lifecycle) for r in live.itertuples()
            if (r.country_iso3, r.hazard) not in have]


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
           -- null-safe: ad hoc rows have no window, and a plain USING join silently
           -- dropped them (until 2026-09-30 only framework activations came through)
           JOIN aa.activation a
             ON a.country_iso3 = f.country_iso3 AND a.hazard = f.hazard
            AND a.event_date = f.event_date AND a.event_type = f.event_type
            AND a.window_name IS NOT DISTINCT FROM f.window_name
            AND coalesce(a.event_label, '') = coalesce(f.event_label, '')
           LEFT JOIN aa.country_hazard r
             ON r.country_iso3 = a.country_iso3 AND r.hazard = a.hazard
           WHERE a.event_type NOT IN (""" + _EXCL_SQL + ")", e)
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
           WHERE c.application_code IN (""" + _CERF_AA_CODES_SQL + """)
             AND s.sector_amount IS NOT NULL""", e)
    d["agency"] = pd.read_sql(
        """SELECT c.year, c.country_iso3, p.agency_short_name AS agency,
                  p.amount_approved
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
    return d


def _resolve_pooled_fund(d):
    """'cbpf-unspecified' (a sheet row that named no pooled fund) -> the country's own pooled
    fund, where the registry knows exactly one for that country (a CBPF, or a regional fund's
    country window). 2026-10-02 meeting: the 2023 ad hoc allocations of Somalia, South Sudan
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
<script>window.D = {data_json};</script>
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
    cb["in_gho"] = [(c, y) in gho_set for c, y in zip(cb["country_iso3"], cb["year"])]
    mirror_cy = set(zip(cb["country_iso3"], cb["year"]))
    pre = pre[~(pre["fund_code"].str.startswith(("cbpf", "rhpf"))
                & pd.Series([(c, y) in mirror_cy for c, y in
                             zip(pre["country_iso3"], pre["year"])], index=pre.index))]
    pre = pd.concat([pre, cb[pre.columns]], ignore_index=True)
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
    """(country, hazard) -> the map layer its money belongs to: 'r' a retired framework, 'c' any
    other (current frameworks, and the odd AA-tagged CBPF allocation in a country whose only
    framework is still in the pipeline, e.g. Sudan). CBPF mirror rows are country-level (hazard
    'multi' or '?'): 'r' only when the country has retired frameworks and no live one. Ad hoc
    allocations are their own layer ('a'), set by the caller from event_type."""
    cur = d["current"]
    pair = dict(zip(zip(cur["country_iso3"], cur["hazard"]), cur["lifecycle"]))
    ret_c = set(cur.loc[cur["lifecycle"] == "retired", "country_iso3"])
    live_c = set(cur.loc[cur["lifecycle"].isin(["active", "updating", "development"]), "country_iso3"])

    def layer(c, h):
        lc = pair.get((c, h))
        if lc is not None:
            return "r" if lc == "retired" else "c"
        return "r" if (c in ret_c and c not in live_c) else "c"
    return layer


def _fu(fc):
    """Fund type letter carried by the flow rows: c CERF, r regional fund, p country CBPF."""
    return "c" if fc == "cerf" else "r" if str(fc).startswith("rhpf") else "p"


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
    Recipient node ids carry their category (_recipient_cat): 'a:<cat>|<agency>' and
    'p:<cat>|<agency>' (always named), 'a:<cat>~<organisation>' and 'p:<cat>~<organisation>'
    (a partner / grantee: FLOW_JS names the top ones of the view and groups the rest per
    category). One spelling and one category per organisation across CERF and the CBPFs.
    g: the map layer of the money, for the page toggles — 'c' current frameworks, 'r' retired
       frameworks, 'a' ad hoc allocations (released only; pass act from
       funding_series(d, released="all") to have them). fu: fund type, 'c' CERF, 'p' CBPF,
       'r' regional fund. Every split is linear in the amount, so the per-layer rows add up
       to the same totals as one pass over all the money."""
    import datetime as _dt
    import re as _re
    today = _dt.date.today()
    C = d["contrib"].copy()
    C = C[C["paid_usd"].fillna(0) > 0]
    C["fund_code"] = C["fund_code"].fillna("cbpf:" + C["fund_name"].astype(str))
    C = C.groupby(["fund_code", "year", "donor"], as_index=False)["paid_usd"].sum()
    ag = d["agency"].groupby(["year", "agency"])["amount_approved"].sum()
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
        co["org_name"] = co["cat"].map(lambda c: "country and regional fund grantees — " + RECIPIENT_PLURAL[c])
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
    sgm = sg.groupby(["year", "agency", "node"])["subgrant_usd"].sum()
    co = co.groupby(["fund_code", "year", "node"])["usd"].sum()
    split = d["split_all"].copy()
    split["version"] = split["version"].astype(str)
    fvm = d["fv_meta"].copy()
    fvm["vf"] = pd.to_datetime(fvm["valid_from"], errors="coerce")
    layer = _layer_of(d)
    rows = []

    def add(m, y, lv, s_, t, v, g, fc):
        if v and v > 0.5:
            rows.append({"m": m, "y": int(y), "lv": lv, "s": s_, "t": t, "v": round(float(v), 2),
                         "g": g, "fu": _fu(fc)})

    def donors(m, y, fc, amount, g):
        cy = C[(C["fund_code"] == fc) & (C["year"] == y)]
        inc = cy["paid_usd"].sum()
        if inc > 0:
            for r in cy.itertuples():
                add(m, y, "d", "d:" + r.donor, "f:" + fc, r.paid_usd / inc * amount, g, fc)
        else:
            add(m, y, "d", "d:(donors not recorded)", "f:" + fc, amount, g, fc)

    def grantees(m, y, fc, amount, g):
        # released money: a CBPF / RhPF grantee implements directly (no sub-grant level), so
        # its band runs on, same amount, to the same organisation in the final column — every
        # band then reaches the last column and each grantee node stays balanced (in = out)
        def on(node, v, final):
            add(m, y, "f", "f:" + fc, "a:" + node, v, g, fc)
            if m == "r":
                add(m, y, "a", "a:" + node, "p:" + final, v, g, fc)
        o = co[(co.index.get_level_values(0) == fc) & (co.index.get_level_values(1) == y)] if len(co) else co
        osum = float(o.sum()) if len(o) else 0.0
        if osum <= 0:
            on("nr|country and regional fund grantees not recorded", amount, "nr|grantee not recorded")
            return
        for (_, _, node), v in o.items():
            cat = node.split(sep)[0]
            final = node if named else f"{cat}|{RECIPIENT_PLURAL[cat]}"
            on(node, v / osum * amount, final)

    # ---------------- pre-arranged, as at the end of each year (never summed over years)
    P = pre[(pre["kind"] == "prearranged") & (pre["fund_code"] != "all") & (pre["year"] <= today.year)]
    P = P.assign(g=[layer(c, h) for c, h in zip(P["country_iso3"], P["hazard"])])
    for y, py in P.groupby("year"):
        y = int(y)
        at = pd.Timestamp(min(_dt.date(y, 12, 31), today))
        for (fc, g), amount in py.groupby(["fund_code", "g"])["amount_usd"].sum().items():
            donors("p", y, fc, amount, g)
        for r in py.itertuples():
            fc, amount, g = r.fund_code, float(r.amount_usd), r.g
            if amount <= 0:
                continue
            if fc != "cerf" and r.source == "onegms-mirror":
                grantees("p", y, fc, amount, g)
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
                grantees("p", y, fc, amount, g)      # pooled funds: grantee types, as allocated
                continue
            if sp is None or sp["amount_usd"].sum() <= 0:
                add("p", y, "f", "f:" + fc, "a:nr|agencies not recorded", amount, g, fc)
                continue
            shares = sp.groupby("agency")["amount_usd"].sum()
            for agency, v in shares.items():
                add("p", y, "f", "f:" + fc, "a:" + _agency_node(agency), v / shares.sum() * amount, g, fc)

    # ---------------- released, in the year it went out (years add up); one pass per layer
    R = act[act["amount_usd"].fillna(0) > 0]
    R = R.assign(g=["a" if et == "adhoc_aa" else layer(c, h)
                    for et, c, h in zip(R["event_type"], R["country_iso3"], R["hazard"])])
    for (fc, y, g), amount in R.groupby(["fund_code", "year", "g"])["amount_usd"].sum().items():
        y = int(y)
        donors("r", y, fc, amount, g)
        if fc != "cerf":
            grantees("r", y, fc, amount, g)
            continue
        a_ = ag[ag.index.get_level_values(0) == y] if len(ag) else ag
        asum = float(a_.sum()) if len(a_) else 0.0
        if asum <= 0:
            add("r", y, "f", "f:cerf", "a:nr|agencies not recorded", amount, g, fc)
            add("r", y, "a", "a:nr|agencies not recorded", "p:nr|recipient not recorded", amount, g, fc)
            continue
        k = amount / asum
        for (_, agency), v in a_.items():
            node = _agency_node(agency)
            add("r", y, "f", "f:cerf", "a:" + node, v * k, g, fc)
            s_ = sgm[(sgm.index.get_level_values(0) == y) & (sgm.index.get_level_values(1) == agency)]
            tot_s = float(s_.sum())
            parts = min(tot_s, float(v)) * k
            kept = 0.0      # partner rows too small to keep stay with the agency: in = out
            for (_, _, pnode), sv in s_.items():
                pv = round(sv / tot_s * parts, 2) if tot_s else 0.0
                if pv > 0.5:
                    add("r", y, "a", "a:" + node, "p:" + pnode, pv, g, fc)
                    kept += pv
            # what the agency implements itself: a final node with its own name
            add("r", y, "a", "a:" + node, "p:" + node, v * k - kept, g, fc)

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


# ------------------------------------------------- where the money flows (shared Sankey)
FLOW_TOP_ORGS = 15   # partner / grantee organisations named in a view; the rest grouped per category
FLOW_NOTE = (
    "<b>Pre-arranged</b>: the envelopes in place in the chosen year (a framework counts for a year "
    "if it was valid at any time in it; the current year: today), one per framework and fund — the Financing page's annual series. Never summed over "
    "years: a two-year envelope would count twice. Fund → agency uses the agency split of the "
    "version in force at that date, scaled to the envelope; country and regional fund allocations go to their "
    "grantee organisations (AA-keyword project budgets). There is no final column: who an agency "
    "sub-grants to is only known once money is released. "
    "<b>Released</b>: money that went out on activations in the chosen year (all years add up). "
    "CERF → agency uses the AA projects approved that year, scaled to the released total; "
    "agency → partner uses the CERF AA sub-grants, and the rest goes to a final node with the "
    "agency's own name — what it implements itself. Country and regional funds go to their grantee organisations "
    "from the AA-keyword project budgets; a grantee implements directly, so its band runs on, same "
    "amount, to the same organisation in the final column. "
    f"<b>Recipients</b>: the {FLOW_TOP_ORGS} partner and grantee organisations receiving the most in the "
    "view are named, the rest grouped per category (\"other national / local NGOs\"…). Every "
    "recipient node carries its category colour — UN agency, international NGO, national / local "
    "NGO, government, Red Cross / Red Crescent, other, not recorded — from the sub-grant partner "
    "type or the organisation type recorded by the country and regional funds; a band takes the colour of the node it leaves. "
    "<b>Recipient types</b>: a stage just before the last column groups every band by the category "
    "of the organisation it reaches — UN agencies, international NGOs, national / local NGOs, Red "
    "Cross / Red Crescent, government, other — so one pathway shows the groups and the last column "
    "the named organisations (untick <i>recipient types</i> to hide it). "
    "<b>Donors → fund</b>: each donor's paid contributions to the fund that year ÷ the fund's "
    "total paid income that year, × the amount — attributed pro rata, since contributions fund "
    "the whole pool. Top 12 donors, the rest grouped.")


def _flow_panel(donors_on, donor_toggle=True):
    """The 'Where the money flows' panel: pre-arranged / released switch, year, levels
    (FLOW_JS mounts it). Used by the Financing page (donors off) and the donor-shares page
    (donors on, no toggle: the donor-flows view)."""
    chk = " checked" if donors_on else ""
    dctl = (f"<label><input type='checkbox' id='flD'{chk}> donors</label>" if donor_toggle
            else f"<input type='checkbox' id='flD'{chk} hidden>")
    return f"""<div class='panel'>
 <div style='display:flex;gap:16px;flex-wrap:wrap;align-items:center;font-size:12.5px;margin-bottom:8px'>
  <span role='radiogroup' aria-label='which money' style='display:inline-flex;border:1px solid #cbd5e1;border-radius:6px;overflow:hidden'>
   <label style='padding:3px 10px;cursor:pointer'><input type='radio' name='flM' value='p' checked> pre-arranged</label>
   <label style='padding:3px 10px;cursor:pointer;border-left:1px solid #cbd5e1'><input type='radio' name='flM' value='r'> released</label></span>
  <label><span id='flYl'>In place in</span> <select id='flY'></select></label>
  {dctl}
  <label title='a stage that groups the recipients by type (UN agencies, NGOs, Red Cross / Red Crescent, government, other) before the named ones'><input type='checkbox' id='flK' checked> recipient types</label>
  <label id='flPw'><input type='checkbox' id='flP' checked> final recipients</label>
  <span id='flTot' class='muted'></span>
 </div>
 <div id='flow'></div><div id='flLeg' class='note' style='display:flex;flex-wrap:wrap;gap:4px 14px;align-items:center'></div><script src="sankey.js"></script>
 <details class='note'><summary style='cursor:pointer'>How the flows are counted</summary>{FLOW_NOTE}</details>
</div>"""


FLOW_JS = """
// ---- where the money flows: [donors ->] funds -> agencies / grantees [-> final recipients].
// Shared by the Financing page and the donor-flows view of the donor-shares page; rows from
// _money_flows. Recipient node ids carry their category: 'a:un|WFP' (an agency: always named),
// 'p:ingo~ActionAid' (an organisation: the top ones of the view named, the rest grouped).
const FLOW_TOP_ORGS = """ + str(FLOW_TOP_ORGS) + """;
const CAT_ORDER = ['un','ingo','nngo','gov','rc','oth','nr'];
const CAT_LABEL = {un:'UN agency', ingo:'international NGO', nngo:'national / local NGO', gov:'government',
  rc:'Red Cross / Red Crescent', oth:'other', nr:'not recorded'};
const CAT_OTHER = {un:'other UN agencies', ingo:'other international NGOs', nngo:'other national / local NGOs',
  gov:'other government partners', rc:'other Red Cross / Red Crescent', oth:'other partners', nr:'other, type not recorded'};
// one colour per category on every level, apart from the fund colours (CERF blue, CBPF orange,
// RhPF green); the five hues validated as a set (all pairs: CVD dE >= 13.5, normal >= 19.6) and
// against the fund colours (normal >= 15.6); the two greys are the neutral categories
const CAT_COLOR = {un:'#65389f', ingo:'#70b6e7', nngo:'#ceaa3e', gov:'#8a4f0e', rc:'#c3518d', oth:'#3a3f47', nr:'#d6dae0'};
// the recipient-type stage: one node per category, just before the last column
const CAT_GROUP = {un:'UN agencies', ingo:'International NGOs', nngo:'National / local NGOs', gov:'Government',
  rc:'Red Cross / Red Crescent', oth:'Other', nr:'Type not recorded'};
function flowNode(id){ const m = /^([apk]):([a-z]+)([|~])(.*)$/.exec(id);
  return m ? {p:m[1], cat:m[2], org:m[3]==='~', name:m[4]} : null; }
function flowRegroup(L, f){ const g = {};
  L.forEach(l=>{ const s = f(l.s, l), t = f(l.t, l), k = l.lv+'\\u0001'+s+'\\u0001'+t;
    if(g[k]) g[k].v += l.v; else g[k] = {lv:l.lv, s, t, v:l.v}; });
  return Object.values(g); }
function buildFlow(rows, mode, year, showD, showP, names, topN, keep, topOrgs, showK){
  const R = rows.filter(r=>r.m===mode && (year==='all' || r.y===+year) && keep(r));
  let L = flowRegroup(R, x=>x);
  // top donors; the rest grouped
  const dt = {}; L.filter(l=>l.lv==='d').forEach(l=>dt[l.s]=(dt[l.s]||0)+l.v);
  const top = new Set(Object.keys(dt).filter(k=>k!=='d:(donors not recorded)').sort((a,b)=>dt[b]-dt[a]).slice(0,topN||12));
  top.add('d:(donors not recorded)');
  L = flowRegroup(L, (x, l)=>l.lv==='d' && x===l.s && !top.has(x) ? 'd:Other donors' : x);
  // organisations: the top ones of THIS view named, by what they receive (sub-grants and CBPF
  // grants; a grantee's own pass-through to the final column not counted twice), the rest
  // grouped per category, in the middle and the final column alike
  const recv = {};
  L.forEach(l=>{ const t = flowNode(l.t), s = flowNode(l.s); if(!t || !t.org || t.cat==='nr' || (s && s.org && s.name===t.name)) return;
    recv[t.name] = (recv[t.name]||0) + l.v; });
  const named = new Set(Object.keys(recv).sort((a,b)=>recv[b]-recv[a]).slice(0, topOrgs||FLOW_TOP_ORGS));
  L = flowRegroup(L, x=>{ const n = flowNode(x); return n && n.org && !named.has(n.name) ? `${n.p}:${n.cat}|${CAT_OTHER[n.cat]}` : x; });
  if(!showD) L = L.filter(l=>l.lv!=='d');
  if(!showP) L = L.filter(l=>l.lv!=='a');
  // recipient types (2026-10-02 meeting): every band into the last column passes through its
  // category first — UN agencies, international / national NGOs, Red Cross / Red Crescent,
  // government, other — so one pathway shows the groups and the last column the named ones.
  // After the naming above (the ranking reads agency -> organisation links), and the first
  // half keeps its level so the total (the 'f' links) is unchanged.
  if(showK){
    const last = showP ? 'p:' : 'a:', lv = showP ? 'a' : 'f', S = [];
    L.forEach(l=>{ const n = l.lv===lv && l.t.startsWith(last) ? flowNode(l.t) : null;
      if(!n){ S.push(l); return; }
      const k = `k:${n.cat}|${CAT_GROUP[n.cat]}`;
      S.push({lv, s:l.s, t:k, v:l.v}, {lv:'k', s:k, t:l.t, v:l.v}); });
    L = flowRegroup(S, x=>x);
  }
  const lab = id => { const [p, ...rest] = id.split(':'); const n = rest.join(':');
    if(p==='f') return names[n]||n; const r = flowNode(id); return r ? r.name : n; };
  const cols = [];
  const col = pre => { const ids = new Set(); L.forEach(l=>{ [l.s,l.t].forEach(x=>{ if(x.startsWith(pre)) ids.add(x); }); });
    return [...ids].map(id=>({id, label:lab(id)})); };
  if(showD) cols.push(col('d:'));
  cols.push(col('f:'));
  if(showK && !showP) cols.push(col('k:'));
  cols.push(col('a:'));
  if(showK && showP) cols.push(col('k:'));
  if(showP) cols.push(col('p:'));
  const seen = new Set(); cols.forEach(c=>c.forEach(n=>{ const r = flowNode(n.id); if(r) seen.add(r.cat); }));
  const total = L.filter(l=>l.lv==='f').reduce((s,l)=>s+l.v,0);
  return {columns:cols, links:L.map(l=>({s:l.s,t:l.t,v:l.v})), total, cats:CAT_ORDER.filter(c=>seen.has(c))};
}
// wire the panel _flow_panel() wrote; cfg.keep(row) filters the rows (the page's toggles).
// Returns the redraw function, for the page to call when its own filters change.
function mountFlow(cfg){
  if(!window.sankeySVG) return ()=>{};
  const keep = cfg.keep || (()=>true);
  const modeOf = () => document.querySelector("input[name='flM']:checked").value;
  function drawFlow(){
    const mode = modeOf();
    const F = buildFlow(D.flow, mode, flY.value, flD.checked, mode==='r' && flP.checked, D.fundNames, 12, keep, cfg.topOrgs, flK.checked);
    const el = document.getElementById('flow'), leg = document.getElementById('flLeg');
    if(!F.links.length){ el.innerHTML = "<p class='empty'>no AA money in this selection for this year</p>"; flTot.textContent=''; if(leg) leg.innerHTML=''; return; }
    const n = Math.max(...F.columns.map(c=>c.length));
    el.innerHTML = sankeySVG({columns:F.columns, links:F.links, width:1100, height:Math.max(260, n*24),
      fmt:money, labelW:200, labelMax:34, label:cfg.label || 'AA money through funds and agencies',
      nodeColor: nd => { const r = flowNode(nd.id); return r ? CAT_COLOR[r.cat] : null; }});
    el.insertAdjacentHTML('beforeend', "<div class='note'>Hover a band or a box to follow the money; click a box to keep it in focus, click again to clear. Funds in their own colour (CERF blue, pooled funds orange, regional funds green); every agency, grantee and recipient in the colour of its category; a band takes the colour of the box it leaves.</div>");
    if(leg) leg.innerHTML = '<b>Recipients</b>' + F.cats.map(c=>`<span style='display:inline-flex;align-items:center;gap:5px'><span style='width:11px;height:11px;border-radius:2px;background:${CAT_COLOR[c]};display:inline-block${c==='nr' ? ';box-shadow:inset 0 0 0 1px #aab2bd' : ''}'></span>${CAT_LABEL[c]}</span>`).join('');
    flTot.textContent = mode==='p' ? `Pre-arranged, in place in ${flY.value}: ${money(F.total)}` + (+flY.value===new Date().getFullYear() ? ' (today)' : '')
                                    : `Released ${flY.value==='all' ? 'in all years' : 'in ' + flY.value}: ${money(F.total)}`;
  }
  // the year list depends on the view: pre-arranged is one year's stock (no 'all years')
  function fillYears(){
    const mode = modeOf(), keepY = flY.value;
    flY.innerHTML = '';
    D.flowYears[mode].slice().reverse().forEach(y=>flY.add(new Option(y, y)));
    if(mode==='r') flY.add(new Option('all years', 'all'));
    flY.value = [...flY.options].some(o=>o.value===keepY) && keepY!=='' ? keepY : String(D.flowDefault[mode]);
    document.getElementById('flYl').textContent = mode==='p' ? 'In place in' : 'Released in';
    document.getElementById('flPw').style.display = mode==='r' ? '' : 'none';
  }
  document.querySelectorAll("input[name='flM']").forEach(el=>el.addEventListener('change', ()=>{ fillYears(); drawFlow(); }));
  fillYears();
  [flY, flD, flP, flK].forEach(el=>el.addEventListener('change', drawFlow));
  drawFlow();
  return drawFlow;
}
"""


# ---------------------------------------------------------------- financing
def build_funding(page, d):
    """The Financing page (dash-funding.html: the file name predates the rename, links keep it).
    Every tile and chart follows the map's layer toggles (current frameworks, retired, ad hoc
    allocations) and a fund switch; the defaults show everything released (current + retired
    + ad hoc, both funds; since 2026-10-02 — before, framework activations only)."""
    import html as _html
    pre, act = funding_series(d, released="all")   # ad hoc rows ride along, toggled client-side
    cur = d["current"]
    layer = _layer_of(d)
    region_of = dict(zip(zip(cur["country_iso3"], cur["hazard"]), cur["region"]))
    pre["g"] = [layer(c, h) for c, h in zip(pre["country_iso3"], pre["hazard"])]
    act["g"] = ["a" if et == "adhoc_aa" else layer(c, h)
                for et, c, h in zip(act["event_type"], act["country_iso3"], act["hazard"])]

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
    vf["ft"] = vf["fund_code"].map(lambda f: "cerf" if f == "cerf" else
                                   "regional_fund" if str(f).startswith("rhpf") else "cbpf")
    vf = vf.merge(cur[["country_iso3", "hazard", "region"]], on=["country_iso3", "hazard"],
                  how="left")
    vf["hz"] = vf["hazard"].map(haz)
    vf["g"] = [layer(c, h) for c, h in zip(vf["country_iso3"], vf["hazard"])]
    vf["k"] = pair_key(vf)
    now_cerf = vf.loc[vf["ft"] == "cerf", "total_usd"].sum()
    now_cbpf = vf.loc[vf["ft"] != "cerf", "total_usd"].sum()
    gaps = envelope_gaps(d)
    # kept visible, one compact line under the tiles: what pre-arranged now leaves out
    gaps_html = ("" if not gaps else
                 "<p class='note' style='margin:-4px 0 6px;font-size:12px;color:#555'>"
                 f"Not in pre-arranged now — <b>{len(gaps)} current framework{'s' if len(gaps) > 1 else ''} with no envelope recorded</b>: "
                 + ", ".join(f"{_html.escape(str(n))} {_html.escape(str(h))} ({_html.escape(str(lc))})" for n, h, lc in gaps) + ".</p>")
    stale = vf[vf["version"].astype(str) != vf["latest_version"].astype(str)][["country_iso3", "hazard", "version"]].drop_duplicates()
    stale_html = ("" if not len(stale) else
                  (f" {len(stale)} frameworks count the envelope of an earlier version because the latest one has none yet: " if len(stale) > 1 else " 1 framework counts the envelope of an earlier version because the latest one has none yet: ")
                  + ", ".join(f"{r.country_iso3} {r.hazard} ({_html.escape(str(r.version))})" for r in stale.itertuples()) + ".")

    # which funds each framework has money on (any year, pre-arranged or released on a
    # framework activation): the fund switch keeps the frameworks with money on that fund
    # in the counts, people covered and versions
    pair_funds = {}
    money_rows = [pre.loc[(pre["kind"] == "prearranged") & (pre["fund_code"] != "all"),
                          ["country_iso3", "hazard", "fund_code"]],
                  act.loc[act["g"] != "a", ["country_iso3", "hazard", "fund_code"]],
                  vf.loc[vf["fund_code"] != "all", ["country_iso3", "hazard", "fund_code"]]]
    for r in pd.concat(money_rows).itertuples():
        pair_funds.setdefault((r.country_iso3, r.hazard), set()).add(
            "c" if r.fund_code == "cerf" else "p")

    def frame_rows(df):
        df = df.copy()
        df["hz"] = df["hazard"].map(haz)
        df["region"] = [region_of.get((c, h)) or "?" for c, h in zip(df["country_iso3"], df["hazard"])]
        df["g"] = [layer(c, h) for c, h in zip(df["country_iso3"], df["hazard"])]
        df["funds"] = ["".join(sorted(pair_funds.get((c, h), ()))) for c, h in
                       zip(df["country_iso3"], df["hazard"])]
        df["k"] = pair_key(df)
        return df

    fw = frame_rows(cur[["country_iso3", "hazard", "lifecycle", "technical_support"]])
    fw["technical_support"] = fw["technical_support"].fillna(False).astype(bool)
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
    n_ret = int((cur["lifecycle"] == "retired").sum())
    n_tech = int(fw["technical_support"].sum())
    fw_act = act[act["g"] != "a"]
    total_rel = fw_act["amount_usd"].sum()
    rel_years = f"{int(fw_act['year'].min())}–{int(fw_act['year'].max())}" if len(fw_act) else ""
    covered = cov["people_covered"].sum()
    n_live = int(fw["lifecycle"].isin(live_lc).sum())
    n_cov = int(cov["k"].nunique())

    # agency × sector split of the live frameworks' latest versions (one source per version)
    pr = d["plan_rows"].merge(cur[["country_iso3", "hazard", "region"]],
                              on=["country_iso3", "hazard"], how="left")
    pr["hz"] = pr["hazard"].map(haz)
    pr["ft"] = pr["fund_code"].map(lambda f: "cerf" if f == "cerf" else
                                   "regional_fund" if str(f).startswith("rhpf") else "cbpf")
    pr["g"] = [layer(c, h) for c, h in zip(pr["country_iso3"], pr["hazard"])]
    pr["k"] = pair_key(pr)

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
    loc = sg["localization"].fillna("").str.lower()
    local_usd = float(sg.loc[loc == "local", "subgrant_usd"].sum())
    local_share = (local_usd / sub_total * 100) if sub_total else 0
    un_total = float(ag_year[ag_year.index >= 2020].sum())
    sub_share = (sub_total / un_total * 100) if un_total else 0
    # the local / national share per year: sub-grants typed Local ÷ all AA sub-grants that year;
    # international NGOs and partners not yet typed (TBD, blank) make up the rest
    sg["lk"] = loc.map({"local": "local", "ingo": "intl"}).fillna("untyped")
    local_rows = [{"year": int(y), "local": float(g.loc[g["lk"] == "local", "subgrant_usd"].sum()),
                   "intl": float(g.loc[g["lk"] == "intl", "subgrant_usd"].sum()),
                   "untyped": float(g.loc[g["lk"] == "untyped", "subgrant_usd"].sum())}
                  for y, g in sg.groupby("year") if y >= 2020]

    flow_rows, flow_years, flow_default, fund_names = _money_flows(d, pre, act)

    # co-financing PRE-ARRANGED: window_funding kind='cofinancing' (the rows with no agency /
    # sector line, i.e. aa.prearranged_funding — an agency breakdown of a total would count it
    # twice). A stock per year end, grouped by who finances it: the financier as recorded, else
    # "not recorded" (agency-level co-financing lines are not in this series). Disbursed co-financing is not
    # known. The non_aa_mobilised amount is not co-financing: kept out, labelled on its own.
    cof = pre[pre["kind"] == "cofinancing"].copy()
    fin = cof["financier"].where(cof["financier"].notna()
                                 & (cof["financier"].astype(str).str.strip() != ""))
    if "agency" in cof:
        fin = fin.fillna(cof["agency"])
    cof["who"] = fin.fillna("not recorded")
    cname = dict(zip(cur["country_iso3"], cur["country_name"]))
    nonaa = pre[pre["kind"] == "non_aa_mobilised"]
    nonaa_html = ("" if not len(nonaa) else
                  "Not in this chart — <b>Non-AA emergency funds mobilised on the forecast (to confirm "
                  "with the source)</b>: " + "; ".join(
                      f"{_html.escape(str(cname.get(r.country_iso3) or r.country_iso3))} "
                      f"{_html.escape(str(r.hazard))} {int(r.year)}, ${r.amount_usd / 1e6:,.1f}M"
                      for r in nonaa.itertuples()) + ".")

    # the framework picker (2026-10-06, a colleague could not total the pre-arranged money of a
    # sub-regional set of frameworks): every framework with a status on this page — current
    # and retired; a pipeline pair is not a framework yet and carries no figure here — and,
    # after them, the countries whose AA money belongs to no listed framework (ad hoc
    # allocations), so that every row of money on the page can be ticked in or out
    def country_name(c):
        if isinstance(cname.get(c), str):
            return cname[c]
        try:
            import pycountry
            return pycountry.countries.get(alpha_3=c).name
        except Exception:
            return c
    listed = cur[cur["lifecycle"].isin(live_lc + ("retired",))]
    fw_list = [{"k": f"{r.country_iso3}|{r.hazard}", "name": country_name(r.country_iso3),
                "hazard": str(r.hazard).replace("_", " "), "hz": haz(r.hazard),
                "region": r.region if isinstance(r.region, str) else "?", "lc": r.lifecycle,
                "g": layer(r.country_iso3, r.hazard)}
               for r in listed.itertuples()]
    fw_list.sort(key=lambda f: (f["region"], f["name"], f["hazard"]))
    money_c = (set(pre["country_iso3"]) | set(act["country_iso3"])) - set(listed["country_iso3"])
    fw_list += [{"k": f"{c}|*", "name": country_name(c), "hazard": None, "hz": None,
                 "region": None, "lc": None, "g": None} for c in sorted(money_c, key=country_name)]

    def how(body, title="How this is counted"):
        """A per-chart method note, collapsed under the chart."""
        return f"<details class='note'><summary style='cursor:pointer'>{title}</summary>{body}</details>"

    fund_sel =("<label>Fund <select id='fFund'><option value=''>CERF and country and regional funds</option>"
                "<option value='cerf'>CERF</option>"
                "<option value='pooled'>country and regional funds</option></select></label>")
    panels = f"""
<div class='fbar'>
 <span style='display:inline-flex;gap:10px;align-items:center;padding-right:10px;border-right:1px solid #e0e0e0'>
  <label title='frameworks active, being updated or in development: their money in every year'><input type='checkbox' id='fCur' checked> Current frameworks</label>
  <label title='frameworks since retired: their money in the years they were live'><input type='checkbox' id='fRet' checked> Retired</label>
  <label title='AA money allocated without a framework: released money only'><input type='checkbox' id='fAdh' checked> Ad hoc allocations</label></span>
 <details class='fwpick' id='fwPick'><summary id='fwLab' title='the full list of frameworks: tick the ones to count'>Frameworks: all ▾</summary>
  <div class='fwpanel'>
   <div class='fwhead'><input type='search' id='fwQ' placeholder='find a country, hazard, region or status…' aria-label='find frameworks in the list'>
    <button type='button' id='fwAll'>tick all</button><button type='button' id='fwNone'>untick all</button></div>
   <div class='fwlist' id='fwRows'></div>
   <div class='fwsum' id='fwSum'></div>
  </div></details>
 {fund_sel}
 <label>Hazard <select id='fHaz'><option value=''>all</option></select></label>
 <label>Region <select id='fReg'><option value=''>all</option></select></label>
 <label>GHO <select id='fGho'><option value=''>all</option><option value='1'>GHO contexts only</option></select></label>
 <label title='released money only: pre-arranged money is a stock, in place on a date, so it never accumulates'><input type='checkbox' id='fCum'> cumulative (released)</label>
</div>
<div class='tiles'>
 <div class='tile'><div class='v' id='tFw'>{n_active}</div><div class='l' id='tFwl'>active frameworks · {n_upd} being updated · {n_dev} in development{f' · {n_tech} technical support only' if n_tech else ''} · {n_ret} retired</div></div>
 <div class='tile'><div class='v' id='tPre'>${(now_cerf + now_cbpf)/1e6:,.0f}M</div><div class='l' id='tPrel'>pre-arranged now — CERF ${now_cerf/1e6:,.0f}M · country and regional funds ${now_cbpf/1e6:,.0f}M</div></div>
 <div class='tile'><div class='v' id='tRel'>${total_rel/1e6:,.0f}M</div><div class='l' id='tRell'>AA released {rel_years} — framework activations, CERF and country and regional funds</div></div>
 <div class='tile'><div class='v' id='tCov'>{covered/1e6:,.1f}M</div><div class='l' id='tCovl'>people covered now — current frameworks, latest figure each ({n_cov} of {n_live} have one) · not people reached</div></div>
</div>
<p class='fwnote' id='fwNote' style='display:none'></p>
{gaps_html}
<details class='note' style='margin:0 0 14px;font-size:12px;color:#555'><summary style='cursor:pointer;font-size:12.5px'>How these figures are counted</summary>
<p><b>Layers</b>, as on the map: <b>current frameworks</b> (active, being updated, in development) and <b>retired</b> frameworks bring their pre-arranged and released money in every year — a framework's layer is its status today, so the past years need the retired ones to be complete (an AA-tagged country or regional fund allocation in a country with no retired framework counts as current). <b>Ad hoc allocations</b> add the AA money allocated without a framework: released money only, nothing is pre-arranged for it. The <b>fund</b> switch applies to every figure but co-financing; framework counts, people covered and versions then keep the frameworks with money recorded on that fund. There is no technical-support layer here: technical support carries no money. The tiles and the charts follow the layers, the fund, the framework selection and the hazard and region filters (the GHO filter: the annual series and co-financing); the money-flow chart and the sections further down say what they follow.</p>
<p><b>Frameworks</b> (in the filter bar) lists every current and retired framework with its pre-arranged money now: tick the ones to count — a sub-region, a few countries, any subset — and the tiles and the charts count only those, within the other filters. Money that belongs to no framework (an ad hoc allocation, a country-level allocation of a country or regional fund) follows its country: it counts while at least one line of that country is ticked, and the countries whose only AA money is of that kind have a line of their own at the end of the list. A subset changes which frameworks are counted, not how: its pre-arranged money is still a stock, in place today or in a given year, never added over years. The selection is kept in the page address, so a subset can be bookmarked or shared. The money-flow chart and the UN agencies and partners section do not follow it.</p>
<p><b>Pre-arranged now</b> comes from the framework records: for every active, being-updated or in-development framework, the envelope of its most recent version that has one. The same figure is the current year in the annual chart, on the map and on the donor page.{stale_html} Pre-arranged money stays pre-arranged until a framework is <b>retired</b>: a framework being updated keeps its most recent version's envelope. Country and regional fund allocations are made up front, so an AA-tagged allocation counts as pre-arranged until an activation draws on it (then it counts as released as well). Pre-arranged money is a stock (in place on a date) and released money a flow (per year): the two are never added together.</p>
<p><b>People covered now</b> is the latest figure recorded for each current framework — the people its pre-arranged plan covers, not the people reached once it activated (those come from the final reports, on the Plan page). Retired frameworks cover no one now and are left out, as on the map. A framework still in development usually has no figure until its projects are planned; an early estimate can be recorded until then.</p>
<p>Donors report their AA funding annually under the <a href='https://interagencystandingcommittee.org/grand-bargain' target='_blank' rel='noopener'>Grand Bargain</a>; the <a href='dash-donors.html'>donor-shares page</a> attributes this money to the donors of each fund.</p>
</details>
<h2>Where the money flows</h2>
<p class='meta'>Funds → agencies and grantees → the organisations that implement, <b>pre-arranged</b> (the envelopes in place on a date) or <b>released</b> (what went out in a year) — two views never added together. Follows the layers and the fund switch; tick <i>donors</i> to start from each fund's donors.</p>
<p class='fwnote' id='fwFlowNote' style='display:none'>This chart shows every framework of the layers above: it does not follow the framework selection (nor the hazard and region filters).</p>
{_flow_panel(donors_on=False)}
<div class='grid' style='margin-top:16px'>
 <div class='panel'><h3>Pre-arranged funding in place each year, by fund</h3><canvas id='c1' height='260'></canvas>
   {how("A stock: what was committed in each year (a framework counts for a year if it was valid at any time in it), so the bars are not added up (the cumulative switch applies to released money only). CERF: the framework envelopes per year (sheets, framework pages, entries; 'all'-totals excluded where the fund split exists); the current year is pre-arranged now. Country and regional funds: AA-tagged allocations in the OneGMS mirror, in the year allocated. Co-financing is shown separately.")}</div>
 <div class='panel'><h3>AA released by year, by fund</h3><canvas id='c2' height='260'></canvas>
   {how("Allocations drawn by a framework activation, all pooled funds — plus the ad hoc AA allocations when that layer is on. A country or regional fund allocation moves here only once an activation is recorded against it.")}</div>
 <div class='panel'><h3>Pre-arranged now, by hazard</h3><canvas id='c3' height='260'></canvas>
   {how("Latest envelope of every framework that is active, being updated or in development.")}</div>
 <div class='panel'><h3>Pre-arranged now, by region</h3><canvas id='c4' height='260'></canvas>
   {how("The same envelopes as by hazard, by the framework's region.")}</div>
 <div class='panel'><h3>Framework versions endorsed/revised per year</h3><canvas id='c5' height='260'></canvas>
   {how("One bar segment per version registered that year (endorsed docs; a version = an endorsed document).")}</div>
 <div class='panel'><h3>Co-financing pre-arranged, by agency</h3><canvas id='c6' height='260'></canvas><p class='empty' id='c6x' style='display:none'></p>
   {f"<div class='note'>{nonaa_html}</div>" if nonaa_html else ""}
   {how("Pre-arranged co-financing only: money from outside CERF and the country and regional funds recorded against a framework (window funding of kind co-financing); how much of it was disbursed is not recorded. A stock, as at the end of each year (the current year: today) — the years sit side by side and are never added up. Grouped by the financier as recorded (most co-financing rows do not record one yet); rows with neither are the <i>not recorded</i> bar. Follows the framework layers and the hazard, region and GHO filters. Does not apply: the fund switch (the money is outside the pooled funds), the ad hoc layer (ad hoc allocations carry no co-financing) and cumulative (a stock).")}</div>
</div>
<h2>Where the pre-arranged money goes</h2>
<p class='meta'>The latest version of every current framework, split by agency and sector as the framework documents state it, stacked by fund.</p>
<div class='grid'>
 <div class='panel'><h3>Pre-arranged by agency</h3><canvas id='c7' height='320'></canvas>
   {how("Envelope shares per implementing agency (the agency lines of the framework budgets; top 18). Follows the current-frameworks layer (retired frameworks have no pre-arranged money now), the fund switch and the hazard and region filters; the GHO filter does not apply.")}</div>
 <div class='panel'><h3>Pre-arranged by sector</h3><canvas id='c8' height='320'></canvas>
   {how("Sector lines of the same budgets; a line with an agency but no sector is not shown here. Follows the same toggles as by agency.")}</div>
</div>
<h2>UN agencies and partners</h2>
<p class='meta'>Once CERF releases AA money, the agencies keep part of it as direct spend and sub-grant the rest to implementing partners — where partners appear in the money trail.</p>
<p class='empty' id='unNone' style='display:none'>The sub-grant reports are CERF's: select CERF, or both funds, to see them.</p>
<div id='unBox'>
<div class='tiles'>
 <div class='tile'><div class='v'>{sub_share:.0f}%</div><div class='l'>of CERF AA project money sub-granted to partners (2020→)</div></div>
 <div class='tile'><div class='v'>{local_share:.0f}%</div><div class='l'>localisation share — sub-grants to local / national actors (NNGO, government, Red Cross / Red Crescent)</div></div>
 <div class='tile'><div class='v'>${sub_total/1e6:,.1f}M</div><div class='l'>sub-granted in total · {sg['partner_name'].nunique()} partners</div></div>
</div>
<div class='grid'>
 <div class='panel'><h3>CERF AA allocations by year — direct UN spend vs sub-granted to partners</h3><canvas id='c9' height='280'></canvas>
   {how("Direct UN spend = CERF AA project budgets (OneGMS mirror; the allocations the activation record draws on, framework and ad hoc) minus the sub-grants reported for the same year (aa.cerf_subgrant, curated AA set). Partner groups from the sub-grant partner type; 'other' includes partners not yet typed. CERF's sub-grant reports cover framework and ad hoc allocations together and carry no hazard: this section follows the fund switch only.")}</div>
 <div class='panel'><h3>Share of CERF AA sub-grants to local and national actors, by year</h3><canvas id='c10' height='280'></canvas>
   {how("Each bar is one year's CERF AA sub-grants (100%): to local and national actors (national / local NGOs, government, national Red Cross / Red Crescent societies), to international NGOs, and to partners not yet typed in the reports. The label is the local and national share; the recent years fill in as partners are typed. Follows the fund switch only.")}</div>
</div>
</div>"""

    data = {
        "pre": json.loads(_records(pre, ["k", "country_iso3", "hz", "region", "year",
                                         "kind", "fund_code", "amount_usd",
                                         "in_gho", "g"])),
        "act": json.loads(_records(act, ["k", "country_iso3", "hz", "region", "year",
                                         "fund_code", "amount_usd", "event_type",
                                         "in_gho", "g"])),
        "ver": json.loads(_records(ver, ["k", "year", "kb_status", "hz", "region", "g", "funds"])),
        "now": json.loads(_records(vf, ["k", "country_iso3", "hz", "region", "ft", "total_usd", "g"])),
        "fw": json.loads(_records(fw, ["k", "hz", "region", "lifecycle", "technical_support", "g", "funds"])),
        "cov": json.loads(_records(cov, ["k", "hz", "region", "people_covered", "g", "funds"])),
        "split": json.loads(_records(pr, ["k", "hz", "region", "agency", "sector", "ft",
                                          "amount_usd", "g"])),
        "cof": json.loads(_records(cof, ["k", "hz", "region", "year", "in_gho", "g", "who", "amount_usd"])),
        "fwList": fw_list,
        "un": un_rows, "local": local_rows,
        "flow": flow_rows, "flowYears": flow_years, "flowDefault": flow_default,
        "fundNames": fund_names,
    }
    js = FLOW_JS + """
function fundType(fc){ return fc==='cerf'?'cerf':(fc||'').startsWith('rhpf')?'regional_fund':'cbpf'; }
const FT = ['cerf','cbpf','regional_fund'];
const M0 = v => '$'+Math.round(v/1e6).toLocaleString('en-US')+'M';
// the toggles: layers as on the map (g: c current framework, r retired, a ad hoc) and the fund
function sel(){ return {hz:fHaz.value, rg:fReg.value, gho:fGho.value, cum:fCum.checked,
  cur:fCur.checked, ret:fRet.checked, adh:fAdh.checked, fund:fFund.value,
  fws:fwSel, fwC:fwSel && new Set([...fwSel].map(cOf))}; }
const layerOK = (g, s) => g==='a' ? s.adh : g==='r' ? s.ret : s.cur;
// ---- the framework picker: any subset of frameworks, for every tile and chart that follows the
// hazard and region filters. D.fwList: the frameworks (lc: lifecycle), then the countries whose AA
// money belongs to no framework (lc null, k 'ISO3|*'). fwSel: null = every line ticked (no
// filter), else the ticked keys; kept in the page address (#fw=ISO3.hazard,…) so a subset can be
// bookmarked.
const FWL = D.fwList, FWBY = Object.fromEntries(FWL.map(f=>[f.k, f]));
const FWK = new Set(FWL.filter(f=>f.lc).map(f=>f.k)), N_FW = FWK.size;
const cOf = k => k.slice(0, k.indexOf('|'));
let fwSel = null;
// framework money follows its framework's tick; money that belongs to no listed framework (an ad
// hoc allocation, a country-level pooled fund allocation, a pipeline pair) follows its country:
// kept while any line of that country is ticked
const fwOK = (r, s) => !s.fws || (r.g!=='a' && FWK.has(r.k) ? s.fws.has(r.k) : s.fwC.has(cOf(r.k)));
const escH = t => String(t).replace(/[&<>"']/g, c=>'&#'+c.charCodeAt(0)+';');
const M2 = v => '$'+(v/1e6).toFixed(2)+'M';
const LCL = {active:'active', updating:'being updated', development:'in development', retired:'retired'};
const fwLines = () => [...fwRows.querySelectorAll('label.fw')];
const fwOn = l => l.querySelector('input').checked, fwShown = l => l.style.display!=='none';
function fwBuild(){
  const groups = [...new Set(FWL.filter(f=>f.lc).map(f=>f.region))].map(g=>[g, FWL.filter(f=>f.lc && f.region===g)]);
  const rest = FWL.filter(f=>!f.lc);
  if(rest.length) groups.push(['Ad hoc allocations in countries with no framework in place', rest]);
  fwRows.innerHTML = `<div class='cap'>pre-arranged now (in place today)</div>` + groups.map(([g, rows], i)=>
    `<label class='grp' data-g='${i}'><input type='checkbox' checked><span class='nm'>${escH(g)}</span><span class='amt'></span></label>`
    + rows.map(f=>`<label class='fw' data-g='${i}' data-k="${escH(f.k)}" data-t="${escH([f.name, f.hazard||'ad hoc', f.region||'', LCL[f.lc]||'no framework'].join(' ').toLowerCase())}">`
      + `<input type='checkbox' checked><span class='nm'>${escH(f.name)}${f.hazard ? ' — '+escH(f.hazard) : ''}</span>`
      + `<span class='st'>${f.lc ? LCL[f.lc] : 'ad hoc allocations only'}</span><span class='amt'></span></label>`).join('')).join('');
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
  const inView = f => f.lc ? (!s.hz||f.hz===s.hz) && (!s.rg||f.region===s.rg) && layerOK(f.g, s) : !s.rg && s.adh;
  const ticked = f => !s.fws || s.fws.has(f.k), gsum = {};
  fwLines().forEach(l=>{ const f = FWBY[l.dataset.k], a = amt[f.k], v = inView(f);
    l.classList.toggle('off', !v); l.title = v ? '' : 'left out by the layers or the hazard / region filter';
    l.querySelector('.amt').textContent = !f.lc ? '' : f.lc==='retired' ? '–' : a ? M2(a) : 'no envelope';
    if(v && s.cur && ticked(f) && a) gsum[l.dataset.g] = (gsum[l.dataset.g]||0) + a; });
  fwRows.querySelectorAll('label.grp').forEach(gl=>{ const rows = fwLines().filter(l=>l.dataset.g===gl.dataset.g);
    const n = rows.filter(fwOn).length, b = gl.querySelector('input');
    b.checked = n===rows.length; b.indeterminate = n>0 && n<rows.length;
    gl.querySelector('.amt').textContent = gsum[gl.dataset.g] ? M2(gsum[gl.dataset.g]) : ''; });
  const fws = FWL.filter(f=>f.lc), rest = FWL.filter(f=>!f.lc), nOn = fws.filter(ticked).length, xOn = rest.filter(ticked).length;
  const count = `${nOn} of ${N_FW} frameworks ticked` + (xOn<rest.length ? ` · ${xOn} of ${rest.length} countries with ad hoc allocations only` : '');
  const tot = sumOf(N, r=>r.total_usd), nc = sumOf(N.filter(r=>r.ft==='cerf'), r=>r.total_usd);
  fwSum.innerHTML = `<b>${count}</b> · ` + (!s.cur ? 'pre-arranged now: tick <i>Current frameworks</i> in the bar'
    : `pre-arranged now <b>${M2(tot)}</b>` + (s.fund==='cerf' ? ', CERF only' : s.fund==='pooled' ? ', country and regional funds only'
        : ` (CERF ${M2(nc)} · country and regional funds ${M2(tot-nc)})`) + (s.hz||s.rg ? ', within the hazard / region filter' : ''));
  fwLab.textContent = s.fws ? `Frameworks: ${nOn} of ${N_FW} ▾` : 'Frameworks: all ▾';
  fwPick.classList.toggle('on', !!s.fws);
  fwNote.style.display = fwFlowNote.style.display = s.fws ? '' : 'none';
  if(s.fws){ const nm = f => f.name + (f.hazard ? ' '+f.hazard : ' (ad hoc)');
    const inn = FWL.filter(ticked).map(nm), out = FWL.filter(f=>!ticked(f)).map(nm);
    const list = a => escH(a.slice(0,14).join(', ')) + (a.length>14 ? ` and ${a.length-14} more` : '');
    fwNote.innerHTML = `<b>${count}</b> — ` + (!inn.length ? 'nothing is counted'
      : out.length < inn.length ? 'everything but ' + list(out) : list(inn))
      + `. The tiles and the charts count only these. <button type='button'>show all frameworks</button>`; }
}
const ftOK = (ft, s) => !s.fund || (s.fund==='cerf') === (ft==='cerf');
const fundOK = (fc, s) => ftOK(fundType(fc), s);
const pairFundOK = (funds, s) => !s.fund || (funds||'').includes(s.fund==='cerf' ? 'c' : 'p');
const sumOf = (rows, f) => rows.reduce((t,r)=>t+(f(r)||0), 0);
function stackedBy(id, rows, keyFn, valFn, opts){
  const keys = opts && opts.keys ? opts.keys : uniqSorted(rows, keyFn);
  mkChart(id,'bar',keys,FT.map(ft=>({label:ft, backgroundColor:FUND_COLORS[ft],
    data:keys.map(k=>groupSum(rows.filter(r=>r.ft===ft&&keyFn(r)===k),()=>0,valFn)[0]||0)})).filter(d=>d.data.some(v=>v)),
    {stacked:true, totals:true, ...(opts||{})});
}
function topKeys(rows, keyFn, valFn, n){ const g = groupSum(rows.filter(r=>keyFn(r)!=null), keyFn, valFn);
  return Object.keys(g).sort((a,b)=>g[b]-g[a]).slice(0,n); }
function tiles(s, geo, A, N){
  if(s.fws && !s.fws.size){
    [[tFw,tFwl,'frameworks'],[tPre,tPrel,'pre-arranged now'],[tRel,tRell,'AA released'],[tCov,tCovl,'people covered now']].forEach(([v,l,w])=>{
      v.textContent = '–'; l.textContent = w + ': nothing ticked — tick at least one line in Frameworks'; });
    return; }
  const selTxt = s.fws ? ' · ticked frameworks only' : '';
  const fundTxt = s.fund==='cerf' ? ' with CERF money' : s.fund==='pooled' ? ' with country and regional fund money' : '';
  const F = D.fw.filter(r=>geo(r) && layerOK(r.g,s) && pairFundOK(r.funds,s));
  const n = lc => F.filter(r=>r.lifecycle===lc).length, nT = F.filter(r=>r.technical_support).length;
  if(s.cur){ tFw.textContent = n('active');
    tFwl.textContent = `active frameworks${fundTxt} · ${n('updating')} being updated · ${n('development')} in development`
      + (nT ? ` · ${nT} technical support only` : '') + (s.ret ? ` · ${n('retired')} retired` : '') + selTxt; }
  else if(s.ret){ tFw.textContent = n('retired'); tFwl.textContent = `retired frameworks${fundTxt}` + selTxt; }
  else { tFw.textContent = '–'; tFwl.textContent = 'frameworks: no framework layer selected'; }
  const nc = sumOf(N.filter(r=>r.ft==='cerf'), r=>r.total_usd), np = sumOf(N.filter(r=>r.ft!=='cerf'), r=>r.total_usd);
  if(!s.cur){ tPre.textContent = '–'; tPrel.textContent = 'pre-arranged now: select current frameworks (retired frameworks and ad hoc allocations have none)'; }
  else { tPre.textContent = M0(nc+np);
    tPrel.textContent = 'pre-arranged now — ' + (s.fund==='cerf' ? 'CERF' : s.fund==='pooled' ? 'country and regional funds' : `CERF ${M0(nc)} · country and regional funds ${M0(np)}`) + selTxt; }
  const ys = uniqSorted(A, r=>r.year);
  const what = [(s.cur||s.ret) ? 'framework activations' : null, s.adh ? 'ad hoc allocations' : null].filter(Boolean).join(' + ');
  tRel.textContent = M0(sumOf(A, r=>r.amount_usd));
  tRell.textContent = `AA released ${ys.length ? ys[0]+(ys.length>1 ? '–'+ys[ys.length-1] : '') : '(none in this selection)'} — ${what || 'no layer selected'}, `
    + (s.fund==='cerf' ? 'CERF' : s.fund==='pooled' ? 'country and regional funds' : 'CERF and country and regional funds') + (s.gho ? ', GHO contexts' : '')
    + (s.fws ? (s.adh ? ' · ticked frameworks, and the ad hoc allocations of their countries' : selTxt) : '');
  // people covered: a now figure, current frameworks only (as pre-arranged now and the map)
  if(!s.cur){ tCov.textContent = '–'; tCovl.textContent = 'people covered now: select current frameworks (a retired framework covers no one now)'; }
  else { const C = D.cov.filter(r=>geo(r) && pairFundOK(r.funds,s));
    const live = F.filter(r=>['active','updating','development'].includes(r.lifecycle)).length;
    tCov.textContent = (sumOf(C, r=>r.people_covered)/1e6).toFixed(1)+'M';
    tCovl.textContent = `people covered now — current frameworks${fundTxt}, latest figure each (${new Set(C.map(r=>r.k)).size} of ${live} have one) · not people reached` + selTxt; }
}
function draw(){
  const s = sel(), gho = s.gho;
  const geo = r => (!s.hz||r.hz===s.hz) && (!s.rg||r.region===s.rg) && fwOK(r, s);
  const P = D.pre.filter(r=>r.kind==='prearranged' && r.fund_code!=='all' && geo(r) && (!gho||r.in_gho)
      && layerOK(r.g,s) && fundOK(r.fund_code,s));
  const A = D.act.filter(r=>geo(r) && (!gho||r.in_gho) && layerOK(r.g,s) && fundOK(r.fund_code,s));
  const years = uniqSorted(P.concat(A), r=>r.year);
  for(const [id, rows] of [['c1',P],['c2',A]]){
    const ds = FT.map(ft=>{
      let vals = years.map(y=>sumOf(rows.filter(r=>fundType(r.fund_code)===ft&&r.year===y), r=>r.amount_usd));
      if(s.cum && id==='c2') vals = cumulate(vals);   // pre-arranged is a stock: never cumulated
      return {label:ft, data:vals, backgroundColor:FUND_COLORS[ft]};}).filter(d=>d.data.some(v=>v));
    mkChart(id,'bar',years,ds,{stacked:true, totals:true});
  }
  const N = D.now.filter(r=>geo(r) && layerOK(r.g,s) && ftOK(r.ft,s));
  stackedBy('c3', N, r=>r.hz, r=>r.total_usd); stackedBy('c4', N, r=>r.region, r=>r.total_usd);
  const V = D.ver.filter(r=>r.year && geo(r) && layerOK(r.g,s) && pairFundOK(r.funds,s));
  const vy = uniqSorted(V, r=>r.year);
  mkChart('c5','bar',vy,[{label:'versions',data:vy.map(y=>V.filter(r=>r.year===y).length),backgroundColor:PAL[2]}],{count:true});
  // co-financing PRE-ARRANGED, by who finances it: a stock at each year end, the years side by
  // side (never stacked or added up). Money from outside the pooled funds: the fund switch
  // cannot split it; ad hoc allocations carry none.
  {
    const C = D.cof.filter(r=>geo(r) && (!gho||r.in_gho) && layerOK(r.g,s));
    const why = s.fund ? 'Co-financing is money from outside CERF and the country and regional funds: the fund switch does not apply to it — select both funds to see it.'
      : !(s.cur||s.ret) ? 'Co-financing belongs to frameworks: select current or retired frameworks (ad hoc allocations carry none).'
      : !C.length ? 'No pre-arranged co-financing recorded in this selection.' : '';
    c6.style.display = why ? 'none' : ''; c6x.style.display = why ? '' : 'none'; c6x.textContent = why;
    if(!why){
      const g = groupSum(C, r=>r.who, r=>r.amount_usd);
      const keys = Object.keys(g).filter(k=>k!=='not recorded').sort((a,b)=>g[b]-g[a]);
      if(g['not recorded']) keys.push('not recorded');
      const cy = uniqSorted(C, r=>r.year), yr = new Date().getFullYear();
      mkChart('c6','bar',keys, cy.map((y,i)=>({
        label: +y===yr ? `in place today (${y})` : `in place at end of ${y}`,
        backgroundColor: i===cy.length-1 ? PAL[3] : '#b9c3cf',
        data: keys.map(k=>sumOf(C.filter(r=>r.who===k && r.year===y), r=>r.amount_usd))})),
        {allLabels:true, extra:{indexAxis:'y'}});
    }
  }
  const S = D.split.filter(r=>geo(r) && layerOK(r.g,s) && ftOK(r.ft,s));
  const SA = S.filter(r=>r.agency), SS = S.filter(r=>r.sector);
  stackedBy('c7', SA, r=>r.agency, r=>r.amount_usd, {keys:topKeys(SA,r=>r.agency,r=>r.amount_usd,18), extra:{indexAxis:'y'}});
  stackedBy('c8', SS, r=>r.sector, r=>r.amount_usd, {keys:topKeys(SS,r=>r.sector,r=>r.amount_usd,18), extra:{indexAxis:'y'}});
  tiles(s, geo, A, N);
  fwPaint(s, N);
  // UN agencies and partners: CERF sub-grant reports, the fund switch only
  const un = s.fund!=='pooled';
  unBox.style.display = un ? '' : 'none'; unNone.style.display = un ? 'none' : '';
  if(window._flowDraw) _flowDraw();
}
// UN vs partners: drawn once (CERF data; hidden when only the country and regional funds are selected)
const UG = ['direct UN spend','INGO','NNGO / local','Red Cross / Red Crescent','government','other'];
const uy = uniqSorted(D.un, r=>r.year);
mkChart('c9','bar',uy,UG.map((g,i)=>({label:g, backgroundColor:PAL[i],
  data:uy.map(y=>groupSum(D.un.filter(r=>r.grp===g&&r.year===y),()=>0,r=>r.usd)[0]||0)})).filter(d=>d.data.some(v=>v)),
  {stacked:true, totals:true});
// local and national share of the CERF AA sub-grants, per year (100% bars, local share labelled)
(function(){
  const L = D.local.slice().sort((a,b)=>a.year-b.year), yl = L.map(r=>r.year);
  const tot = r => r.local + r.intl + r.untyped, pc = (r, k) => tot(r) ? 100*r[k]/tot(r) : 0;
  const parts = [['local','local and national actors','#1baf7a'], ['intl','international NGOs','#9aa3c7'], ['untyped','partner not yet typed','#d9d9d6']];
  const ch = mkChart('c10','bar',yl, parts.map(([k,lab,col])=>({label:lab, backgroundColor:col, data:L.map(r=>pc(r,k))})), {stacked:true});
  const localLabel = { id:'localLabel', afterDatasetsDraw(c){ const {ctx, scales:{x, y}} = c;
    if(!c.isDatasetVisible(0)) return;
    ctx.save(); ctx.font = '600 11px ' + Chart.defaults.font.family; ctx.fillStyle = '#fff'; ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
    L.forEach((r,i)=>{ const v = pc(r,'local'); if(v >= 8) ctx.fillText(Math.round(v)+'%', x.getPixelForValue(i), y.getPixelForValue(v)+15); });
    ctx.restore(); } };
  ch.config.plugins.push(localLabel);
  ch.options.scales.y.max = 100; ch.options.scales.y.ticks.callback = v=>v+'%';
  ch.options.plugins.tooltip.callbacks.label = c=>{ const r = L[c.dataIndex], k = parts[c.datasetIndex][0];
    return ` ${c.dataset.label}: ${Math.round(c.parsed.y)}% (${money(r[k])} of ${money(tot(r))} sub-granted)`; };
  ch.update();
})();
uniqSorted(D.pre,r=>r.hz).forEach(h=>fHaz.add(new Option(h,h)));
uniqSorted(D.pre,r=>r.region).forEach(r=>fReg.add(new Option(r,r)));
[fHaz,fReg,fGho,fCum,fCur,fRet,fAdh,fFund].forEach(el=>el.addEventListener('change',draw));
// the flow chart: the layers and the fund switch filter its rows (donors off: it starts at the funds)
window._flowDraw = mountFlow({label:'AA money through funds and agencies to partners',
  keep: r=>{ const s = sel(); return layerOK(r.g, s) && (!s.fund || (s.fund==='cerf') === (r.fu==='c')); }});
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
  fwAll.textContent = q.length ? 'tick shown' : 'tick all'; fwNone.textContent = q.length ? 'untick shown' : 'untick all'; });
fwNote.addEventListener('click', ev=>{ if(ev.target.tagName==='BUTTON'){ fwSel = null; fwToDom(); fwCommit(); } });
// the list never runs below the window, so its total stays in view wherever the bar sits
function fwFit(){ if(!fwPick.open) return; const p = fwPick.querySelector('.fwpanel');
  p.style.maxHeight = Math.max(220, innerHeight - p.getBoundingClientRect().top - 12) + 'px'; }
fwPick.addEventListener('toggle', ()=>{   // little room under the bar: bring the bar to the top of the window first
  const bar = fwPick.closest('.fbar');
  if(fwPick.open && innerHeight - bar.getBoundingClientRect().bottom < 360) bar.scrollIntoView();
  fwFit(); });
addEventListener('scroll', fwFit, {passive:true}); addEventListener('resize', fwFit);
document.addEventListener('click', ev=>{ if(fwPick.open && !fwPick.contains(ev.target)) fwPick.open = false; });
document.addEventListener('keydown', ev=>{ if(ev.key==='Escape') fwPick.open = false; });
window.addEventListener('hashchange', ()=>{ fwSel = fwFromHash(); fwToDom(); draw(); });
draw();"""
    _dash_page(page, "dash-funding.html", "Financing",
               "<b>The money of anticipatory action</b>: pre-arranged and released across CERF, "
               "country and regional funds, with the map's layers and a fund, hazard, region and "
               "GHO filter. <b>Frameworks</b> in the filter bar lists every framework: tick any "
               "subset (a sub-region, a few countries) to total it. See also <a href='dash-donors.html'>donor shares and donor flows</a>.",
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
    tag = f"<span class='doctag'>{DOC_TYPE_LABEL.get(r.doc_type, str(r.doc_type))}</span>"
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
 <div class='panel' style='grid-column:1/-1'><h3>CERF ↔ country and regional funds complementarity (AA activations)</h3><canvas id='a3' height='240'></canvas>
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
     {label:'country and regional funds',data:both.map(x=>x[1].pooled),backgroundColor:FUND_COLORS.cbpf}]);
  const adhoc = D.act.filter(r=>r.event_type!=='framework_aa');
  const byA = Object.entries(groupSum(adhoc,r=>r.country_iso3,r=>r.amount_usd)).sort((a,b)=>b[1]-a[1]);
  mkChart('a4','bar',byA.map(x=>x[0]),[{label:'ad hoc AA USD',data:byA.map(x=>x[1]),backgroundColor:PAL[3]}]);
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
               "application (2006→) and every country and regional fund allocation envelope — with "
               "the AA lens on by default. Complementarity and non-framework AA "
               "views come from the activation record.",
               panels, json.dumps(data, default=str), js)


# ------------------------------------------------------------------ delivery
def build_delivery(page, d):
    sg = d["subgrant"]
    cb = d["cbpf_proj"]
    sec = d["sector"]
    ag = d["agency"]
    # pre-arranged splits: the latest version of every current framework, as on the Financing
    # page (2026-10-02: every version's split was summed here, and lines with a sector but no
    # agency showed as a 'null' bar)
    ps = d["plan_rows"].copy()
    ps["agency"] = ps["agency"].fillna("not stated in the budget")
    ps["sector"] = ps["sector"].fillna("not stated in the budget")
    cva = d["cva"]
    rc = d["reached"]
    # CERF activations whose allocation code is not recorded: their money cannot be split by
    # agency or sector until it is
    import html as _html
    act = d["activation"]
    nolink = act[(act["fund_code"] == "cerf") & act["allocation_code"].isna()
                 & (act["amount_usd"].fillna(0) > 0)]
    nolink_html = ("" if not len(nolink) else
                   f"<p class='note' style='font-size:12px;color:#555'>Not in the released charts yet — "
                   f"<b>{len(nolink)} CERF activation{'s' if len(nolink) > 1 else ''} "
                   f"(${nolink['amount_usd'].sum()/1e6:,.1f}M) with no CERF allocation code recorded</b>: "
                   + "; ".join(f"{_html.escape(str(r.country_iso3))} {_html.escape(str(r.hazard))} "
                               f"{_html.escape(str(r.event_date))} (${r.amount_usd/1e6:,.1f}M)"
                               for r in nolink.sort_values("event_date").itertuples()) + ".</p>")

    panels = nolink_html + """
<div class='grid'>
 <div class='panel'><h3>CERF AA subgrants by partner type × year</h3><canvas id='d1' height='250'></canvas>
   <div class='note'>Yakubu's curated AA subgrant set; local = NNGO+GOV+RedC per his localization tagging.</div></div>
 <div class='panel'><h3>Country and regional fund AA projects: direct funding by org type</h3><canvas id='d2' height='250'></canvas>
   <div class='note'>Country and regional funds pay partners directly — this is the localization view CERF can't show. AA-keyword allocations only.</div></div>
 <div class='panel'><h3>Released by agency (CERF AA projects)</h3><canvas id='d3' height='250'></canvas>
   <div class='note'>CERF AA project budgets, all years: the allocations the activation record draws on (framework and ad hoc), as on the Financing page.</div></div>
 <div class='panel'><h3>Released by sector (CERF AA projects)</h3><canvas id='d4' height='250'></canvas>
   <div class='note'>The sector split of the same projects (CERF sector names).</div></div>
 <div class='panel'><h3>Pre-arranged by agency (framework budgets)</h3><canvas id='d5' height='250'></canvas>
   <div class='note'>The budget lines of the latest version of every current framework, as on the Financing page.</div></div>
 <div class='panel'><h3>Pre-arranged by sector (framework budgets)</h3><canvas id='d6' height='250'></canvas>
   <div class='note'>Sector lines of the same budgets.</div></div>
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
               "localization (CERF AA), direct partner funding (country and regional fund AA), agency "
               "and sector splits (released vs pre-arranged), CVA, and people "
               "reached by gender.",
               panels, json.dumps(data, default=str), js)


# ------------------------------------------------------------------ questions
COVERAGE = [
    ("Pre-arranged funding by year, cumulative", "covered", "dash-funding.html", "canonical per framework-year; cumulative toggle"),
    ("Pre-arranged by hazard / region", "covered", "dash-funding.html", ""),
    ("AA amount released by year, cumulative", "covered", "dash-funding.html", "all pooled funds via activation_funding"),
    ("Subgrants by partner type / local partners", "covered", "dash-delivery.html", "CERF AA subgrants + country and regional fund direct org-type funding"),
    ("Released funds by agency", "covered", "dash-delivery.html", "CERF AA projects"),
    ("Released funds by sector", "covered", "dash-delivery.html", "CERF AA project sector splits"),
    ("Pre-arranged funds by agency / sector", "covered", "dash-delivery.html", "budget lines of the latest version of every current framework (v_window_funding_split)"),
    ("Agency participation across the portfolio", "covered", "dash-delivery.html", "agency axis of pre-arranged budgets"),
    ("AA delivered as CVA", "partial", "dash-delivery.html", "totals by year 2020–2026; MPC-vs-sector split only for 2024+ projects (cerf_project_supplement)"),
    ("People covered", "partial", "dash-funding.html", "per framework (latest); by CATEGORY of people not tracked anywhere"),
    ("People reached by gender, by year", "covered", "dash-delivery.html", "CERF AA final reports; ~9-month lag"),
    ("Co-funding amount and source", "partial", "dash-funding.html", "amounts yes; financier mostly uncurated free text"),
    ("Calendar of monitoring windows", "covered", "dashboards.html#calendar", "trigger-window months per framework (from planning-sheet colors)"),
    ("Filter by hazard", "covered", "dash-funding.html", "all dashboards filter by hazard"),
    ("Frameworks started/revised/endorsed per year", "covered", "dash-funding.html", "endorsed-document versions per year"),
    ("Non-framework AA allocations", "covered", "dash-allocations.html", "explicit ad hoc AA category (ad hoc layer on the Financing page)"),
    ("CERF + Country/Regional Funds complementarity", "covered", "dash-allocations.html", "multi-fund activations from activation_funding"),
    ("AA funding to GHO contexts", "covered", "dash-funding.html", "GHO filter (plan_inclusion)"),
    ("CERF AA growth (released, people, countries…)", "covered", "dash-funding.html", "cumulative toggles + tiles"),
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
    v["_vf"] = version_start(v)
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
    u = next((u for _, u in lk["cerf"] if u), None)
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


def sim_at(r):
    """'in 2019' / 'in 2019-08' / 'on 2019-08-12' / 'on 2019-08-12 06:00 UTC'."""
    w = sim_when(r)
    return ("on " if len(w) > 7 else "in ") + w


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
                f"<span class='dot sim' style='background:{col}' title='{esc(r.window_name)}: would have activated "
                f"{esc(sim_at(r))} (simulation)'></span>")
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
        amt = "; ".join(f"{x.fund_code} {_m(x.amount_usd)}" for x in ev["fund"].itertuples()
                        if pd.notna(x.amount_usd)) or "amount not recorded"
        href, goes = _event_href(ev)
        vv = "" if ev["version"] is None or str(ev["version"]) in ("nan", "None", "NaT", "<NA>") else str(ev["version"])
        # no version = an ad hoc allocation: neither this version nor an earlier one
        ref = shown if shown is not None else (str(version) if version is not None else None)
        same = (not vv) or (ref is not None and _vm(vv, ref))   # no backtest: compare with the current version
        tip = (f"{ev['date']} · {ev['win'] or ev['typ'].replace('_', ' ')} · {amt}"
               + (" · ad hoc allocation (no framework version)" if not vv else "" if same else f" · under version {vv}")
               + (" · partial activation" if ev["partial"] else "")
               + (f" · opens {goes}" if href else ""))
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
        use_tip = (f"version {shown} took effect {vf_txt}: from {vf_y} on, real activations only "
                   "(its simulation covers the years before)") if use_years else ""
        body = ""
        for (y, lab) in sorted(rows, key=lambda k: (-k[0], k[1])):
            cells = rows[(y, lab)]
            inner = lambda w: "".join(cells.get(w, []))   # noqa: E731
            if y in use_years:
                tds = "".join(f"<td class='use' title='{esc(f'{y}: ' + use_tip)}'>{inner(w)}</td>" for w in wins)
            elif y in sim_years or not sim_years:
                tds = "".join(f"<td>{inner(w)}</td>" for w in wins)
            else:
                tds = "".join(f"<td class='na' title='{y} is not covered by the historical simulation'>{inner(w)}</td>"
                              for w in wins)
            body += (f"<tr><td class='yr'>{y}{(' <span class=' + chr(39) + 'muted' + chr(39) + '>' + esc(lab) + '</span>') if lab else ''}"
                     + (f" <span class='usetag' title='{esc(use_tip)}'>in use</span>" if y in use_years and not lab else "")
                     + f"{' ' + ''.join(cells.get('__cell', [])) if cells.get('__cell') else ''}</td>"
                     + tds + "</tr>")
        vnote = ("" if shown is None else
                 f"Backtest of version <code>{esc(shown)}</code>"
                 + ("" if str(shown) == str(version) else " (the current version has no recorded backtest)")
                 + (f", {int(n_years)} years analysed" if n_years and pd.notna(n_years) else "")
                 + (f"; the version took effect {esc(vf_txt)}, so from {vf_y} on the rows show real "
                    "activations only" if use_years else "") + ". "
                 + (esc(sim_after_note(n_after, vf_y)) + " " if n_after else ""))
        hist = (f"<p class='meta'>{vnote or 'No backtest recorded for this framework — real activations only. '}"
                "One row per year, newest first; a real activation whose window does not match a "
                "column sits in the year cell. Markers link to the announcement or the CERF allocation.</p>"
                f"<table class='data hist'><thead><tr><th>year</th>{head}</tr></thead><tbody>{body}</tbody></table>"
                f"<p class='legend'><span class='dot sim' style='background:{col}'></span> would have activated (simulation) · "
                f"<span class='dot real'></span> activated, money released · "
                f"<span class='dot old'></span> activated under "
                + ("an earlier version" if str(shown) == str(version) else "a different version (hover for which)")
                + (" · <span class='sw use'></span> version in use: real activations only" if use_years else "")
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
                    else f" <span class='doctag' title='This activation happened under version {esc(ev['version'])}, an earlier version of the framework than the current one ({esc(version)}); its triggers and budget may differ.'>earlier version</span>")
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
        version = (fw["latest_version"] if pd.notna(fw.get("latest_version"))
                   else fw["current_version"] if pd.notna(fw.get("current_version")) else None)
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
<div class='tile'><a href='dash-funding.html'><b>Financing</b></a><div class='l'>pre-arranged & released, by year/hazard/region/fund, GHO, cumulative; any subset of frameworks (tick them in the list); current / retired frameworks and ad hoc allocations as on the map; money flows; localisation</div></div>
<div class='tile'><a href='dash-donors.html'><b>Donor shares</b></a><div class='l'>each donor's share of AA released / pre-arranged, via their contributions to CERF and the country and regional funds; donor flows; build earmarks</div></div>
<div class='tile'><a href='dash-allocations.html'><b>Allocation explorer</b></a><div class='l'>query every CERF, country and regional fund allocation 2006→; complementarity; timeliness</div></div>
<div class='tile'><a href='dash-delivery.html'><b>Delivery & people</b></a><div class='l'>subgrants, localization, agencies, sectors, CVA, people reached</div></div>
<div class='tile'><a href='pillar-learning.html'><b>Learning</b></a><div class='l'>headline findings on the map, and every learning document by country and hazard</div></div>
<div class='tile'><a href='media.html'><b>Media & visuals</b></a><div class='l'>photos by country and social posts on AA, from the shared AA Visuals folder (a first collection, not curated yet)</div></div>
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
            f"<td>{f'{int(w.sim_activations)} in {int(w.analysis_years)} yrs' if pd.notna(w.sim_activations) and pd.notna(w.analysis_years) else ''}</td></tr>"
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
    import page_history
    page_history.build_history(page, d)
    import page_model_draft          # mock-ups of alternative visuals, internal (for comparison)
    page_model_draft.build_model_draft(page, d)
    build_allocations(page, d)
    build_delivery(page, d)
    import donors
    donors.build_donors(page, d)
    build_questions(page)
    links = build_framework_pages(page, tbl, d, e)
    build_hub(page, d, links)
    import page_media
    page_media.build_media(page)
    build_hierarchy(page, d, e)
    build_entry(page, d, e)
    build_status_form(page, d)
    import landing
    landing.build_landing(page, d, e)
