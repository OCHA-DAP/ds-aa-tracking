"""The historical trigger explorer (pillar-history.html), written 2026-10-01.

For every current framework (active, being updated, in development; retired ones left out):
would its trigger have activated in each past year (the backtest — aa.simulated_activation),
and when did it activate for real (aa.activation, framework_aa rows; the money from
aa.activation_funding). The same material the team sends the insurance broker as snapshots,
kept up to date from the tracking DB.

The version simulated per framework follows dashboards._activation_blocks: the current
version, else the latest version with a backtest (the row says which). `_backtest` below
replicates its selection and year-range logic line for line, so the overview grid and the
per-framework grids under it agree — change both together.
"""

import html
import json
import re
from datetime import date

import pandas as pd
from dashboards import (HAZARDS, LIFE_LABEL, PAL, _activation_blocks, _dash_page, _event_href,
                        _event_links, _fmt_usd, haz, sim_before_start, sim_when)

LIVE = ["active", "updating", "development"]
LIFE_ON = {"active": True, "updating": True, "development": False}   # default filter state
SPLIT_YEAR = 2000          # years before this are summarised in one column
SIM_COL = PAL[0]           # one colour for simulated activations across the page
ACT_RED = "#e3322d"        # real activations (as on the framework pages)


def _nofire(s):
    """Display vocabulary: triggers are 'activated', never 'fired' (also inside source text)."""
    s = "" if s is None or (isinstance(s, float) and pd.isna(s)) else str(s)
    s = re.sub(r"\bfiring\b", "activating", s, flags=re.IGNORECASE)
    return re.sub(r"\bfire(d|s)?\b", lambda m: "activate" + (m.group(1) or ""), s,
                  flags=re.IGNORECASE)


def _esc(s):
    return html.escape(_nofire(s))


def _str(v):
    return "" if v is None or (not isinstance(v, str) and pd.isna(v)) else str(v)


def _vm(a, b):
    """Version match as on the framework pages: 'YYYY' label vs a dated version."""
    return a == b or a.startswith(b) or b.startswith(a)


def _backtest(d, c, h, version):
    """(shown version, its simulated rows, first year, last year, years analysed, year the
    version took effect, simulated rows dropped) — the same choice, start-year cut and range as
    dashboards._activation_blocks. Only rows dated before the version's start year are
    simulation (sim_before_start); the kept rows carry `sim_year`."""
    sim = d["sim"][(d["sim"]["country_iso3"] == c) & (d["sim"]["hazard"] == h)].copy()
    sim["version"] = sim["version"].astype(str)
    fvm = d["fv_meta"][(d["fv_meta"]["country_iso3"] == c) & (d["fv_meta"]["hazard"] == h)]
    order = list(fvm.assign(_vf=pd.to_datetime(fvm["valid_from"], errors="coerce"))
                 .sort_values("_vf")["version"].astype(str))
    shown = next((sv for sv in set(sim["version"])
                  if version is not None and _vm(sv, str(version))), None)
    if shown is None and len(sim):
        vs = [v for v in order if v in set(sim["version"])] or sorted(set(sim["version"]))
        shown = vs[-1]
    ss = sim[sim["version"] == shown] if shown else sim.iloc[0:0]
    vf = (fvm.loc[fvm["version"].astype(str) == str(shown), "valid_from"] if shown
          else fvm["valid_from"].iloc[0:0])
    ss, n_after, vf_y = sim_before_start(ss, vf)
    win = d["windows"]
    wv = win[(win["country_iso3"] == c) & (win["hazard"] == h)
             & (win["version"].astype(str) == str(shown))]
    n_years = pd.to_numeric(wv["analysis_years"], errors="coerce").max() if len(wv) else None
    y0 = y1 = None
    if len(ss) or n_after:
        y1 = int(max(ss["sim_year"].max() if len(ss) else 0, (vf_y - 1) if vf_y else 0))
        y0 = (int(y1 - n_years + 1) if n_years and pd.notna(n_years)
              else int(ss["sim_year"].min()) if len(ss) else y1)
        y0 = min(y0, int(ss["sim_year"].min())) if len(ss) else y0
    return shown, ss, y0, y1, n_years, vf_y, n_after


def _frameworks(d):
    cur = d["current"]
    live = cur[cur["lifecycle"].isin(LIVE)].sort_values(["country_name", "hazard"])
    out = []
    for r in live.itertuples():
        version = (r.latest_version if pd.notna(r.latest_version)          # latest version, as the map and Model page
                   else r.current_version if pd.notna(r.current_version) else None)
        kb_fw = r.kb_framework if pd.notna(r.kb_framework) else None
        out.append(dict(c=r.country_iso3, h=r.hazard, name=f"{r.country_name} — {r.hazard}",
                        life=r.lifecycle, version=None if version is None else str(version),
                        kb_fw=kb_fw, slug=f"fw-{r.country_iso3.lower()}-{r.hazard}.html"))
    return out


def _events(d, c, h, ref, kb_fw=None, umap=None, slug=None):
    """Real framework activations of one framework, with the money released and the page
    each one links to (as the activation tables: announcement, else CERF allocation, else
    another recorded page — else the framework page `slug`)."""
    act = d["act_all"]
    act = act[(act["country_iso3"] == c) & (act["hazard"] == h)
              & (act["event_type"] == "framework_aa")]
    evs = []
    for r in act.sort_values("event_date").itertuples():
        ed, wn = _str(r.event_date), _str(r.window_name)
        if not ed[:4].isdigit():
            continue
        lk = _event_links(d, c, h, kb_fw, umap or {}, ed, r.window_name, r.event_type)
        f = lk["fund"]
        href, goes = _event_href(lk)
        if not href and slug:
            href, goes = slug, "the framework page"
        amt = pd.to_numeric(f["amount_usd"], errors="coerce")
        vv = _str(r.version)
        vv = "" if vv in ("nan", "None", "NaT", "<NA>") else vv
        evs.append(dict(date=ed, year=int(ed[:4]), win=wn, label=_str(r.event_label), version=vv,
                        amount=float(amt.sum()) if amt.notna().any() else None,
                        funds="; ".join(f"{x.fund_code} {_fmt_usd(x.amount_usd)}".strip()
                                        for x in f.itertuples() if isinstance(x.fund_code, str)),
                        funds_csv="; ".join(f"{x.fund_code}: {x.amount_usd:.0f}" if pd.notna(x.amount_usd)
                                            else f"{x.fund_code}: not recorded"
                                            for x in f.itertuples() if isinstance(x.fund_code, str)),
                        same=(not vv) or (ref is not None and _vm(vv, str(ref))),
                        href=href, goes=goes))
    return evs


def build_history(page, d):
    fws = _frameworks(d)
    this_year = date.today().year
    umap = {(r.country_iso3, r.hazard, str(r.event_date), r.window_name): r.url
            for r in d["act_url"].itertuples()}
    # the per-framework blocks show framework activations only, like the grid (ad hoc
    # allocations have no trigger to simulate)
    act_all = d["act_all"]
    n_adhoc = int((act_all["event_type"] != "framework_aa").sum())
    dd = dict(d, act_all=act_all[act_all["event_type"] == "framework_aa"])

    for f in fws:
        (f["shown"], f["ss"], f["y0"], f["y1"], f["n_years"], f["vf_y"],
         f["n_after"]) = _backtest(d, f["c"], f["h"], f["version"])
        f["ref"] = f["shown"] or f["version"]
        f["events"] = _events(d, f["c"], f["h"], f["ref"], f["kb_fw"], umap, f["slug"])
        f["hit"] = {}   # year -> windows (and labels, dates) that would have activated
        for r in f["ss"].itertuples():
            lab, when = _str(r.event_label), sim_when(r)
            extra = ", ".join(x for x in (lab, when if when != str(r.sim_year) else "") if x)
            f["hit"].setdefault(int(r.sim_year), []).append(
                _str(r.window_name) + (f" ({extra})" if extra else ""))
        f["n_sim"] = (f["y1"] - f["y0"] + 1) if f["y0"] is not None else 0
        f["n_hit"] = len(f["hit"])
    y_min = min([f["y0"] for f in fws if f["y0"] is not None] or [SPLIT_YEAR])
    old = y_min < SPLIT_YEAR
    years = list(range(SPLIT_YEAR if old else y_min, this_year + 1))

    def rate(f):
        if not f["shown"]:
            return "no backtest recorded"
        s = (f"activated in {f['n_hit']} of {f['n_sim']} simulated years "
             f"({f['y0']}–{f['y1']})")
        if f["version"] is None:
            s += f" · backtest of version {f['shown']}"
        elif str(f["shown"]) != str(f["version"]):
            s += f" · backtest of version {f['shown']} (the current version has none)"
        if f["n_after"]:
            s += (f" · {f['n_after']} simulated row{'' if f['n_after'] == 1 else 's'} dated after "
                  f"the version's start not shown")
        return s

    def n_real(f):
        n = len(f["events"])
        return f"{n} real activation{'' if n == 1 else 's'}" if n else "no real activation"

    def life_tag(lc):
        return f"<span class='lf lf-{lc}'>{LIFE_LABEL.get(lc, lc)}</span>"

    def ev_tip(ev):
        return (f"activated {ev['date']}" + (f" · {ev['win']}" if ev["win"] else "")
                + (f" · {ev['label']}" if ev["label"] else "")
                + f" · {ev['funds'] or 'amount not recorded'}"
                + ("" if ev["same"] else f" · under version {ev['version'] or '?'}"))

    def markers(evs):
        """Real activations as links to their most relevant page (announcement, else CERF
        allocation, else the framework page): solid under the version simulated, hollow under
        another version; activations sharing a page share one marker, with a count."""
        out, groups = "", {}
        for ev in evs:
            groups.setdefault((not ev["same"], ev["href"] or ""), []).append(ev)
        for (other, href), g in sorted(groups.items(), key=lambda kv: kv[0][0]):
            tip = " | ".join(ev_tip(ev) for ev in g) + (f" — opens {g[0]['goes']}" if href else "")
            cnt = f"<sup>{len(g)}</sup>" if len(g) > 1 else ""
            cls = "old" if other else "real"
            ext = "" if href.endswith(".html") and "://" not in href else " target='_blank' rel='noopener'"
            out += (f"<a class='mk' href='{html.escape(href)}'{ext} title='{_esc(tip)}'><span class='dot {cls}'></span>{cnt}</a>"
                    if href else f"<span class='mk' title='{_esc(tip)}'><span class='dot {cls}'></span>{cnt}</span>")
        return out

    # ---- the overview grid
    head = ((f"<th class='old' title='{y_min}–{SPLIT_YEAR - 1}: simulated years summarised'>"
             f"{y_min}–<br>{SPLIT_YEAR - 1}</th>") if old else "")
    head += "".join(f"<th class='y{' dec' if y % 10 == 0 else ''}'>{y}</th>" for y in years)
    trs = []
    for f in fws:
        sim_yrs = set(range(f["y0"], f["y1"] + 1)) if f["y0"] is not None else set()
        cells = ""
        if old:
            pre_ev = [ev for ev in f["events"] if ev["year"] < SPLIT_YEAR]
            if f["y0"] is not None and f["y0"] < SPLIT_YEAR:
                a, b = f["y0"], min(f["y1"], SPLIT_YEAR - 1)
                n_h = sum(1 for y in f["hit"] if y < SPLIT_YEAR)
                tip = f"{a}–{b}: would have activated in {n_h} of {b - a + 1} simulated years"
                cells += (f"<td class='old' title='{_esc(tip)}'><b>{n_h}</b><span class='of'>/{b - a + 1}</span>"
                          f"{markers(pre_ev)}</td>")
            else:
                cells += (f"<td class='old na' title='no simulated years before {SPLIT_YEAR}'>"
                          f"{markers(pre_ev)}</td>")
        for y in years:
            evs = [ev for ev in f["events"] if ev["year"] == y]
            hit = f["hit"].get(y)
            in_use = f["vf_y"] is not None and f["shown"] and y >= f["vf_y"]
            tips = [f"{y}"]
            if in_use:   # never simulation from the version's start year on
                tips.append(f"version {f['shown']} in use (took effect {f['vf_y']}): real activations only"
                            if str(f["shown"]) == str(f["version"]) else
                            f"from {f['vf_y']}, version {f['shown']} (took effect {f['vf_y']}) and later "
                            "versions in use: real activations only")
            elif hit:
                tips.append("simulation: would have activated — " + ", ".join(sorted(set(hit))))
            elif y in sim_yrs:
                tips.append("simulation: would not have activated")
            else:
                tips.append("not covered by the simulation")
            tips += [ev_tip(ev) for ev in evs]
            mk = ("<span class='dot sim'></span>" if hit and not in_use else "") + markers(evs)
            cls = "use" if in_use else "" if y in sim_yrs else "na"
            cells += (f"<td class='{cls}' title='{_esc(' · '.join(tips))}'>{mk}</td>")
        trs.append(
            f"<tr class='hrow' data-life='{f['life']}' data-haz='{_esc(f['h'])}'>"
            f"<th class='fw'><a href='{f['slug']}'>{_esc(f['name'])}</a> {life_tag(f['life'])}"
            f"<span class='rate'>{_esc(rate(f))} · {n_real(f)}</span></th>{cells}</tr>")
    grid = (f"<div class='scroll hscroll'><table class='hgrid'><thead><tr><th class='fw'>framework</th>"
            f"{head}</tr></thead><tbody>{''.join(trs)}</tbody></table></div>")

    # ---- per-framework detail: the framework page's historical grid + activations table
    det = []
    for f in fws:
        hist, actual = _activation_blocks(dd, f["c"], f["h"], f["kb_fw"], f["version"], umap)
        col = PAL[HAZARDS.index(f["h"])] if f["h"] in HAZARDS else "#64748b"   # as there
        hist = _nofire(hist.replace(f"class='dot sim' style='background:{col}'",
                                    f"class='dot sim' style='background:{SIM_COL}'"))
        det.append(
            f"<details class='fwd' data-life='{f['life']}' data-haz='{_esc(f['h'])}'>"
            f"<summary><b>{_esc(f['name'])}</b> {life_tag(f['life'])} "
            f"<span class='rate'>{_esc(rate(f))} · {n_real(f)}</span></summary>"
            f"<div class='fwbody'><h3 class='sub'>Historical activations</h3>{hist}"
            f"<h3 class='sub'>Real activations</h3>{_nofire(actual)}"
            f"<p class='meta'><a href='{f['slug']}'>Framework page →</a></p></div></details>")

    # ---- the rows behind the grid (CSV download, filtered client-side)
    rows = []
    for f in fws:
        base = dict(framework=f["name"], country_iso3=f["c"], hazard=f["h"],
                    status=LIFE_LABEL.get(f["life"], f["life"]), lifecycle=f["life"])
        for r in f["ss"].sort_values(["sim_year", "window_name"]).itertuples():
            when = sim_when(r)   # the day / hour when recorded (event_date, event_time)
            rows.append(dict(base, kind="simulated", version=f["shown"],
                             window=_nofire(r.window_name), year=int(r.sim_year),
                             event_date=when if when != str(r.sim_year) else "",
                             event_label=_str(r.event_label), amount_usd=None, funding="",
                             same_version_as_simulated="", source_note=_str(r.source_note)))
        for ev in f["events"]:
            rows.append(dict(base, kind="real", version=ev["version"], window=_nofire(ev["win"]),
                             year=ev["year"], event_date=ev["date"], event_label=ev["label"],
                             amount_usd=ev["amount"], funding=ev["funds_csv"],
                             # vs the version simulated; vs the current one without a backtest
                             same_version_as_simulated="yes" if ev["same"] else "no",
                             source_note=""))

    no_bt = [f for f in fws if not f["shown"]]
    aft = [f for f in fws if f["n_after"]]
    after_note = (f" {sum(f['n_after'] for f in aft)} simulated rows dated after their version's start are "
                  f"not shown ({_esc(', '.join(f['name'] + ' ' + str(f['shown']) for f in aft))})."
                  if aft else "")
    life_boxes = "".join(
        f"<label><input type='checkbox' value='{lc}'{' checked' if LIFE_ON[lc] else ''} "
        f"onchange='hfilt()'> {LIFE_LABEL[lc]} ({sum(f['life'] == lc for f in fws)})</label>"
        for lc in LIVE)
    hz_opts = "".join(f"<option value='{_esc(h)}'>{_esc(h)}</option>"
                      for h in sorted({f["h"] for f in fws}, key=lambda h: (haz(h) == "other", h)))
    panels = f"""
<style>
.lf {{ display:inline-block; padding:0 8px; border-radius:9px; font-size:11px; font-weight:600; white-space:nowrap; }}
.lf-active {{ background:#dbe9f6; color:#17548a; }} .lf-updating {{ background:#e6f1f8; color:#2b6d99; }}
.lf-development {{ background:#fdf1dc; color:#8a5c0a; }}
.muted {{ color:#888; }}
.fbar input[type=checkbox] {{ vertical-align:-2px; }}
.fbar .cnt {{ font-size:12px; color:#666; margin-left:auto; }}
.hscroll {{ max-height:none; background:#fff; }}
table.hgrid {{ border-collapse:separate; border-spacing:0; font-size:12px; }}
table.hgrid th, table.hgrid td {{ border-bottom:1px solid #eef0f3; }}
table.hgrid thead th {{ background:#eef3f8; font-size:10px; font-weight:600; color:#445; padding:4px 0;
  text-align:center; border-bottom:2px solid #cbd6e2; position:sticky; top:0; z-index:2; }}
table.hgrid thead th.dec {{ color:#111; }}
table.hgrid th.fw {{ position:sticky; left:0; z-index:1; background:#fff; text-align:left; font-weight:400;
  padding:5px 10px; min-width:340px; max-width:360px; border-right:1px solid #dde3ea; }}
table.hgrid thead th.fw {{ background:#eef3f8; z-index:3; font-size:12px; }}
table.hgrid th.fw a {{ font-weight:600; }}
.rate {{ display:block; font-size:11px; color:#666; margin-top:1px; }}
table.hgrid td {{ width:34px; min-width:34px; max-width:34px; height:34px; padding:0; text-align:center; line-height:1.1; }}
table.hgrid td sup {{ font-size:9px; color:#a11; margin-left:-2px; }}
table.hgrid td + td {{ border-left:1px solid #f4f5f7; }}
table.hgrid td.na {{ background:#eef1f5; }}
table.hgrid td.use {{ background:#fbf6ee; }}
table.hgrid a.mk {{ text-decoration:none; }} table.hgrid a.mk:hover .dot {{ transform:scale(1.25); }}
table.hgrid td.old, table.hgrid th.old {{ min-width:52px; width:52px; border-right:2px solid #cbd6e2; font-size:11px; }}
table.hgrid td.old .of {{ color:#888; }}
table.hgrid tr.hrow:hover th.fw, table.hgrid tr.hrow:hover td:not(.na) {{ background:#f2f7fc; }}
table.hgrid .dot {{ margin:0 1px; }}
.dot.sim {{ background:{SIM_COL}; width:11px; height:11px; }}
table.hgrid .dot.real {{ width:10px; height:10px; box-shadow:0 0 0 1.5px #fff, 0 0 0 3px {ACT_RED}; margin:0 3px; }}
table.hgrid .dot.old {{ width:8px; height:8px; margin:0 2px; }}
p.legend .sw {{ display:inline-block; width:14px; height:12px; background:#eef1f5; border:1px solid #dde3ea; vertical-align:middle; margin:0 2px; }}
details.fwd {{ background:#fff; border:1px solid #e0e0e0; border-radius:6px; margin:8px 0; }}
details.fwd > summary {{ cursor:pointer; padding:9px 14px; font-size:13.5px; }}
details.fwd > summary .rate {{ display:inline; margin-left:6px; }}
details.fwd[open] > summary {{ border-bottom:1px solid #eee; }}
details.fwd .fwbody {{ padding:4px 16px 12px; }}
details.fwd h3.sub {{ font-size:14px; margin:16px 0 6px; color:#334; }}
@media (max-width:700px) {{ table.hgrid th.fw {{ min-width:170px; max-width:200px; }}
  details.fwd > summary .rate {{ display:block; margin-left:0; }} }}
</style>
<div class='fbar' id='hbar'>{life_boxes}
 <label>hazard <select id='hhaz' onchange='hfilt()'><option value=''>all</option>{hz_opts}</select></label>
 <button class='dl' onclick='histCsv()' title='the simulated and real activations of the frameworks shown'>⬇ CSV</button>
 <span class='cnt' id='hn'></span></div>
<h2>Every current framework, year by year</h2>
<p class='meta'>One row per framework: its current trigger run over the past years (the backtest), and its
real activations. Years before {SPLIT_YEAR} are summarised in the first column (years the trigger would have
activated / years simulated). Hover a cell for the windows and the money; open a framework below for its
window-by-window grid.</p>
{grid}
<p class='legend'><span class='dot sim'></span> would have activated (simulation, any window) ·
<span class='dot real'></span> activated, money released ·
<span class='dot old'></span> activated under a different version (hover for which) ·
<sup style='color:#a11'>2</sup> several activations that year ·
<span class='sw use'></span> the version in use: real activations only ·
<span class='sw'></span> year not covered by the simulation</p>
<p class='meta'>The version simulated is the current one; where the current version has no recorded backtest,
the latest version that has one, as the row says. A solid red marker is an activation under the version
simulated in that row (under the current version where there is no backtest); a hollow one, under another
version, whose triggers may differ. Each real-activation marker links to its announcement, else its CERF
allocation page, else the framework page (hover for which). A version's backtest is fixed before it is
endorsed, and real activations can only come after: from the year the version took effect, a row shows real
activations only.{after_note} Real activations are framework activations only:
the {n_adhoc} ad hoc allocations on record (money released without a pre-agreed trigger) are left out,
as there is no trigger to simulate them against. No backtest recorded yet for {len(no_bt)} of the
{len(fws)} frameworks: {_esc(', '.join(f['name'] for f in no_bt)) or 'none'}.</p>
<h2>Framework by framework</h2>
<p class='meta'>The same backtest window by window, and each real activation with its funding and links.</p>
{''.join(det)}"""
    js = """
function hstate(){
  const on = new Set([...document.querySelectorAll('#hbar input[type=checkbox]:checked')].map(b=>b.value));
  return {on, hz: document.getElementById('hhaz').value};
}
function hfilt(){
  const {on, hz} = hstate(); let n = 0;
  document.querySelectorAll('tr.hrow, details.fwd').forEach(el=>{
    const ok = on.has(el.dataset.life) && (!hz || el.dataset.haz === hz);
    el.style.display = ok ? '' : 'none';
    if(ok && el.tagName === 'TR') n++; });
  document.getElementById('hn').textContent = n + ' framework' + (n === 1 ? '' : 's') + ' shown';
}
function histCsv(){
  const {on, hz} = hstate();
  const cols = ['framework','country_iso3','hazard','status','kind','version','window','year',
                'event_date','event_label','amount_usd','funding','same_version_as_simulated',
                'source_note'];
  const q = v => { if(v == null) return ''; const s = String(v);
    return /[",\\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
  const rows = D.rows.filter(r => on.has(r.lifecycle) && (!hz || r.hazard === hz));
  const csv = [cols.join(',')].concat(rows.map(r => cols.map(c => q(r[c])).join(','))).join('\\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], {type: 'text/csv;charset=utf-8'}));
  a.download = 'historical-activations.csv'; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
hfilt();"""
    intro = ("A <b>simulated activation</b> means today's trigger would have activated in a past "
             "year, given the historical data for that year. A <b>real activation</b> means the trigger was actually met and the "
             "pre-arranged money was released.")
    _dash_page(page, "pillar-history.html", "Historical activations", intro, panels,
               json.dumps({"rows": rows}, default=str).replace("</", "<\\/"), js)
