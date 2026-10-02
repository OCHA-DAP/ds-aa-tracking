"""The historical trigger explorer (pillar-history.html), written 2026-10-01.

For every current framework (active, being updated, in development; retired ones left out):
would its trigger have activated in each past year (the backtest — aa.simulated_activation),
and when did it activate for real (aa.activation, framework_aa rows; the money from
aa.activation_funding). The same material the team sends the insurance broker as snapshots,
kept up to date from the tracking DB.

At the top, an interactive timeline (TL_JS, inline SVG, no library): every framework's real
activations by month (by day when recorded), then one framework version by version, with each
version's simulated activations drawn only before it took effect, at the precision the backtest
gives (year today; day or hour once aa.simulated_activation.event_date / event_time are filled).

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
                        _event_links, _fmt_usd, _loose, haz, sim_before_start, sim_when)

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


def _frameworks(d, lifecycles=LIVE):
    cur = d["current"]
    live = cur[cur["lifecycle"].isin(lifecycles)].sort_values(["country_name", "hazard"])
    out = []
    for r in live.itertuples():
        version = (r.latest_version if pd.notna(r.latest_version)          # latest version, as the map and Model page
                   else r.current_version if pd.notna(r.current_version) else None)
        kb_fw = r.kb_framework if pd.notna(r.kb_framework) else None
        out.append(dict(c=r.country_iso3, h=r.hazard, name=f"{r.country_name} — {r.hazard}",
                        life=r.lifecycle, version=None if version is None else str(version),
                        kb_fw=kb_fw, slug=f"fw-{r.country_iso3.lower()}-{r.hazard}.html"))
    return out


def _events(d, c, h, ref, kb_fw=None, umap=None, slug=None, adhoc=False):
    """Real framework activations of one framework, with the money released and the page
    each one links to (as the activation tables: announcement, else CERF allocation, else
    another recorded page — else the framework page `slug`). adhoc=True: its ad hoc
    allocations instead (money released without a pre-agreed trigger)."""
    act = d["act_all"]
    act = act[(act["country_iso3"] == c) & (act["hazard"] == h)
              & ((act["event_type"] != "framework_aa") if adhoc
                 else (act["event_type"] == "framework_aa"))]
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


# ---------------- the interactive timeline (top of the page), data for its JS
TL_START = 2020            # the portfolio timeline opens here (first activation on record)
TL_RETIRED = ["retired"]


def _tl_versions(d, c, h):
    """One framework's versions as bands: start = valid_from; end = its own valid_until
    (fv_meta), else the next version's start, else open."""
    v = d["versions"]
    v = v[(v["country_iso3"] == c) & (v["hazard"] == h)].copy()
    v["vf_dt"] = pd.to_datetime(v["valid_from"].astype(str), errors="coerce")
    v = v.sort_values("vf_dt", na_position="last")
    vu = {}
    fvm = d["fv_meta"]
    if "valid_until" in fvm.columns:
        for r in fvm[(fvm["country_iso3"] == c) & (fvm["hazard"] == h)].itertuples():
            if _str(r.valid_until):
                vu[str(r.version)] = _str(r.valid_until)[:10]
    cr = d["current"][(d["current"]["country_iso3"] == c) & (d["current"]["hazard"] == h)]
    if len(cr) and _str(cr.iloc[0]["current_version"]) and _str(cr.iloc[0]["valid_until"]):
        vu.setdefault(str(cr.iloc[0]["current_version"]), _str(cr.iloc[0]["valid_until"])[:10])
    starts = sorted(x for x in v["vf_dt"] if pd.notna(x))
    out = []
    for r in v.itertuples():
        st = r.vf_dt.strftime("%Y-%m-%d") if pd.notna(r.vf_dt) else None
        nxt = next((x for x in starts if st and x > r.vf_dt), None)
        end, why = vu.get(str(r.version)), "valid until (as recorded)"
        if nxt is not None and (end is None or nxt.strftime("%Y-%m-%d") < end):
            end, why = nxt.strftime("%Y-%m-%d"), "replaced by the next version"
        out.append(dict(v=str(r.version), st=_str(r.kb_status), start=st, end=end,
                        why=why if end else "no end recorded"))
    return out


def _tl_match(labels, v):
    """The version label among `labels` that version string `v` means: exact, else _vm."""
    return (v if v in labels else next((x for x in labels if _vm(x, v)), None)) if v else None


def _tl_ev(ev, adhoc=False):
    return dict(d=ev["date"], w=_nofire(ev["win"]), v=ev["version"], lab=_nofire(ev["label"]),
                a=ev["amount"], fu=ev["funds"], href=ev["href"] or "", goes=ev["goes"] or "",
                ah=1 if adhoc else 0)


def _tl_detail(d, f):
    """The framework view of one framework: per version, its band and one lane per window,
    with its simulated activations (only those dated before the version took effect —
    sim_before_start) and the real activations under it."""
    c, h = f["c"], f["h"]
    groups = {g["v"]: dict(g, lanes={}, cover=None, n_after=0, vf_y=None, bt=False)
              for g in _tl_versions(d, c, h)}
    sim = d["sim"][(d["sim"]["country_iso3"] == c) & (d["sim"]["hazard"] == h)].copy()
    sim["version"] = sim["version"].astype(str)
    fvm = d["fv_meta"][(d["fv_meta"]["country_iso3"] == c) & (d["fv_meta"]["hazard"] == h)]
    win = d["windows"][(d["windows"]["country_iso3"] == c) & (d["windows"]["hazard"] == h)]
    fv_lab = [str(x) for x in fvm["version"]]

    def lane(g, w):
        return g["lanes"].setdefault(w, dict(w=w, sims=[], reals=[]))

    for sv in sorted(set(sim["version"])):
        key = _tl_match(list(groups), sv)
        if key is None:
            key = sv
            groups[sv] = dict(v=sv, st="", start=None, end=None, why="version not on record",
                              lanes={}, cover=None, n_after=0, vf_y=None, bt=False)
        g = groups[key]
        fk = _tl_match(fv_lab, sv)
        vf = fvm.loc[fvm["version"].astype(str) == fk, "valid_from"] if fk else fvm["valid_from"].iloc[0:0]
        ss, n_after, vf_y = sim_before_start(sim[sim["version"] == sv], vf)
        wv = win[win["version"].astype(str) == sv]
        if not len(wv):
            wv = win[[_vm(str(x), sv) for x in win["version"]]]
        n_years = pd.to_numeric(wv["analysis_years"], errors="coerce").max() if len(wv) else None
        if len(ss) or n_after:   # the analysed span, as _backtest
            y1 = int(max(ss["sim_year"].max() if len(ss) else 0, (vf_y - 1) if vf_y else 0))
            y0 = (int(y1 - n_years + 1) if n_years and pd.notna(n_years)
                  else int(ss["sim_year"].min()) if len(ss) else y1)
            y0 = min(y0, int(ss["sim_year"].min())) if len(ss) else y0
            g["cover"] = [y0, y1]
        g.update(bt=True, n_after=g["n_after"] + n_after, vf_y=vf_y, sv=sv)
        for w in sorted({_str(x) for x in wv["window_name"]} - {""}):
            lane(g, _nofire(w))
        for r in ss.sort_values("sim_year").itertuples():
            lane(g, _nofire(_str(r.window_name)) or "window not recorded")["sims"].append(
                dict(t=sim_when(r), lab=_nofire(_str(r.event_label)), note=_nofire(_str(r.source_note))))
    for ev in f["events"]:
        key = _tl_match(list(groups), ev["version"])
        if key is None:
            key = "?"
            groups.setdefault("?", dict(v="", st="", start=None, end=None,
                                        why="version not recorded", lanes={}, cover=None,
                                        n_after=0, vf_y=None, bt=False))
        g = groups[key]
        w = _nofire(ev["win"]) or "window not recorded"
        w = w if w in g["lanes"] else next((x for x in g["lanes"] if _loose(x, w)), w)
        lane(g, w)["reals"].append(_tl_ev(ev))
    out = []
    for g in sorted(groups.values(), key=lambda g: (g["start"] is None, g["start"] or "", g["v"])):
        out.append(dict(g, lanes=list(g["lanes"].values())))
    return out


# The timeline's script: inline SVG, no library. Dates are parsed by hand into UTC ms ('YYYY',
# 'YYYY-MM', 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM UTC'); a mark sits at the centre of the span its
# date is known to (at the hour itself when an hour is given), drawn faintly behind it.
TL_JS = r"""
const TL = D.tl, DAY = 864e5, HOUR = 36e5, AX = 24;
const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const tlq = id => document.getElementById(id);
const tlEsc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
  c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
function tlParse(s){   // -> [start, end, precision]
  const m = /^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?(?:[ T](\d{2}):(\d{2}))?/.exec(String(s || ''));
  if(!m) return null;
  const y = +m[1], mo = m[2] ? +m[2] - 1 : null, d = m[3] ? +m[3] : null;
  if(m[4] != null && d != null){ const t = Date.UTC(y, mo, d, +m[4], +m[5]); return [t, t + HOUR, 'hour']; }
  if(d != null){ const t = Date.UTC(y, mo, d); return [t, t + DAY, 'day']; }
  if(mo != null) return [Date.UTC(y, mo, 1), Date.UTC(y, mo + 1, 1), 'month'];
  return [Date.UTC(y, 0, 1), Date.UTC(y + 1, 0, 1), 'year'];
}
const tlMid = p => p[2] === 'hour' ? p[0] : (p[0] + p[1]) / 2;
const p2 = n => String(n).padStart(2, '0');
function tlFmt(s, plainYear){
  const p = tlParse(s); if(!p) return String(s || '');
  const t = new Date(p[0]), y = t.getUTCFullYear(), m = MON[t.getUTCMonth()], d = t.getUTCDate();
  return p[2] === 'year' ? (plainYear ? String(y) : y + ' (month not recorded)')
       : p[2] === 'month' ? m + ' ' + y : p[2] === 'day' ? d + ' ' + m + ' ' + y
       : d + ' ' + m + ' ' + y + ', ' + p2(t.getUTCHours()) + ':' + p2(t.getUTCMinutes()) + ' UTC';
}
const tlIso = t => new Date(t).toISOString().slice(0, 10);
const tlToday = tlParse(TL.today)[0];
const tlEnd = (() => { const t = new Date(tlToday); return Date.UTC(t.getUTCFullYear(), t.getUTCMonth() + 1, 1); })();
const tlCol = h => TL.hz[h] || TL.other;
let tlMaxA = 1; TL.rows.forEach(r => r.ev.forEach(e => { if(e.a > tlMaxA) tlMaxA = e.a; }));
const tlR = a => a ? 3.5 + 8.5 * Math.sqrt(a / tlMaxA) : 4.5;

function tlTicks(a, b, W){   // [t, label, major] at a step that leaves room for the labels
  const ppd = W / ((b - a) / DAY);
  const steps = [['y',10,3652],['y',5,1826],['y',2,730],['y',1,365],['m',6,182],['m',3,91],['m',1,30.4],
                 ['d',7,7],['d',1,1],['h',6,.25],['h',1,1/24]];
  let st = steps[0]; for(const s of steps){ if(s[2] * ppd >= 62) st = s; else break; }
  const [u, n] = st, out = [], d0 = new Date(a);
  let y = d0.getUTCFullYear(), mo = d0.getUTCMonth(), dd = d0.getUTCDate();
  if(u === 'y'){ y = Math.floor(y / n) * n;
    for(;; y += n){ const t = Date.UTC(y, 0, 1); if(t > b) break; if(t >= a) out.push([t, String(y), true]); } }
  else if(u === 'm'){ mo = Math.floor(mo / n) * n;
    for(;; mo += n){ const t = Date.UTC(y, mo, 1); if(t > b) break; if(t < a) continue;
      const m = new Date(t).getUTCMonth();
      out.push([t, m === 0 || !out.length ? MON[m] + ' ' + new Date(t).getUTCFullYear() : MON[m], m === 0]); } }
  else if(u === 'd'){
    for(let k = 0;; k++){ const t = Date.UTC(y, mo, dd + k); if(t > b) break; if(t < a) continue;
      const x = new Date(t), day = x.getUTCDate();
      if(n === 7 && [1, 8, 15, 22].indexOf(day) < 0) continue;
      out.push([t, day + ' ' + MON[x.getUTCMonth()] + (!out.length || (day === 1 && x.getUTCMonth() === 0) ? ' ' + x.getUTCFullYear() : ''), day === 1]); } }
  else { const h0 = Math.floor(d0.getUTCHours() / n) * n;
    for(let k = 0;; k += n){ const t = Date.UTC(y, mo, dd, h0 + k); if(t > b) break; if(t < a) continue;
      const x = new Date(t), H = x.getUTCHours();
      out.push([t, (H === 0 || !out.length ? x.getUTCDate() + ' ' + MON[x.getUTCMonth()] + ' ' : '') + p2(H) + ':00', H === 0]); } }
  return out;
}

function tlEvMark(e, r, inFw){   // a real activation (circle) or an ad hoc allocation (diamond)
  const p = tlParse(e.d); if(!p) return null;
  const lines = [r.name,
    (e.ah ? 'ad hoc allocation (no pre-agreed trigger; not a framework activation): ' : 'activated ') + tlFmt(e.d)
      + (e.w ? ' · ' + e.w : ''),
    (e.a ? money(e.a) + ' released' : 'amount not recorded') + (e.fu ? ' (' + e.fu + ')' : '')];
  if(e.v) lines.push('version ' + e.v);
  if(e.lab) lines.push(e.lab);
  lines.push(e.href ? 'click: opens ' + (e.goes || 'its page') : 'no page recorded');
  return {t0: p[0], t1: p[1], tc: tlMid(p), r: tlR(e.a), shape: e.ah ? 'd' : 'c', hollow: !e.a,
          fill: inFw ? TL.red : tlCol(r.h), href: e.href, tip: lines.join('\n'), txt: e.a ? money(e.a) : '',
          kind: e.ah ? 'adhoc' : 'real', prec: p[2]};
}
function tlSimMark(s, g, l, r){   // a simulated activation: a block for its year, a square on its day / hour
  const p = tlParse(s.t); if(!p) return null;
  const lines = [r.name + ' · version ' + g.v, l.w,
    'would have activated ' + (p[2] === 'year' || p[2] === 'month' ? 'in ' : 'on ') + tlFmt(s.t, true)
      + ' (backtest, fixed before the version took effect)'];
  if(s.lab) lines.push(s.lab);
  if(s.note) lines.push(s.note);
  return {t0: p[0], t1: p[1], tc: tlMid(p), r: 5, shape: p[2] === 'year' ? 'blk' : 's', fill: TL.sim,
          tip: lines.join('\n'), kind: 'sim', prec: p[2]};
}

function tlRowSvg(r, y0, X, a, b, W, labels){
  let s = ''; const mid = y0 + r.h / 2, cl = x => Math.max(-4, Math.min(W + 4, x));
  (r.spans || []).forEach(p => {
    if(p.t1 < a || p.t0 > b) return;
    const x0 = cl(X(p.t0)), x1 = cl(X(p.t1));
    s += `<rect x='${x0.toFixed(1)}' y='${y0 + p.y}' width='${Math.max(1, x1 - x0).toFixed(1)}' height='${p.hh}' class='${p.cls}'`
       + (p.tip ? ` data-tip='${tlEsc(p.tip)}'` : '') + '/>';
    if(p.txt && x1 - x0 > p.txt.length * 5.6 + 12)
      s += `<text x='${(Math.max(x0, 0) + 5).toFixed(1)}' y='${y0 + p.y + p.hh / 2 + 3.5}' class='tlbt'>${tlEsc(p.txt)}</text>`;
  });
  (r.lines || []).forEach(t => { if(t >= a && t <= b){ const x = X(t).toFixed(1);
    s += `<line x1='${x}' x2='${x}' y1='${y0}' y2='${y0 + r.h}' class='tlvs'/>`; } });
  const ms = (r.marks || []).filter(m => m && m.t1 >= a && m.t0 <= b)
    .map(m => Object.assign({x: X(m.tc)}, m)).sort((p, q) => p.x - q.x);
  const placed = [], SL = [0, -7, 7, -12, 12];
  let labEnd = -1e9;
  ms.forEach(m => {
    let dy = 0;
    if(m.shape !== 'blk'){
      dy = SL.find(o => !placed.some(p => p.o === o && Math.abs(p.x - m.x) < p.r + m.r + 1));
      if(dy === undefined) dy = 0;
      placed.push({x: m.x, r: m.r, o: dy});
    }
    const yy = mid + dy, e0 = X(m.t0), e1 = X(m.t1);
    if(m.shape !== 'blk' && e1 - e0 > 2 * m.r + 2)
      s += `<rect x='${cl(e0).toFixed(1)}' y='${mid - 3}' width='${(cl(e1) - cl(e0)).toFixed(1)}' height='6' rx='3' fill='${m.fill}' class='tlext'/>`;
    let g;
    if(m.shape === 'blk'){ const w = Math.max(6, e1 - e0 - Math.min(8, Math.max(2, (e1 - e0) * .2)));
      g = `<rect class='mk' x='${((e0 + e1) / 2 - w / 2).toFixed(1)}' y='${mid - 6}' width='${w.toFixed(1)}' height='12' rx='2' fill='${m.fill}'/>`; }
    else if(m.shape === 's')
      g = `<rect class='mk' x='${(m.x - 4.5).toFixed(1)}' y='${yy - 4.5}' width='9' height='9' rx='1.5' fill='${m.fill}' stroke='#fff' stroke-width='1'/>`;
    else if(m.shape === 'd'){ const q = m.r + 1.5;
      g = `<path class='mk' d='M${m.x.toFixed(1)} ${yy - q}l${q} ${q}l${-q} ${q}l${-q} ${-q}z' fill='${m.hollow ? '#fff' : m.fill}' stroke='${m.hollow ? m.fill : '#fff'}' stroke-width='1.5'/>`; }
    else
      g = `<circle class='mk' cx='${m.x.toFixed(1)}' cy='${yy}' r='${m.r.toFixed(1)}' fill='${m.hollow ? '#fff' : m.fill}' stroke='${m.hollow ? m.fill : '#fff'}' stroke-width='1.5'/>`;
    const tip = tlEsc(m.tip), ext = m.href && !(/\.html$/.test(m.href) && m.href.indexOf('://') < 0);
    s += m.href
      ? `<a class='tlm' data-kind='${m.kind}' data-prec='${m.prec}' href='${tlEsc(m.href)}'${ext ? " target='_blank' rel='noopener'" : ''} data-tip='${tip}' aria-label='${tip}'>${g}</a>`
      : `<g class='tlm' data-kind='${m.kind}' data-prec='${m.prec}' tabindex='0' role='img' data-tip='${tip}' aria-label='${tip}'>${g}</g>`;
    if(labels && m.txt && m.x + m.r + 3 > labEnd){
      s += `<text x='${(m.x + m.r + 3).toFixed(1)}' y='${yy + 3.5}' class='tlamt'>${tlEsc(m.txt)}</text>`;
      labEnd = m.x + m.r + 3 + m.txt.length * 6 + 6; }
  });
  return s;
}

function tlRender(v){
  if(!v.rows) return;
  const W = Math.max(v.sc.clientWidth || 0, 620), rows = v.rows, a = v.a, b = v.b;
  const H = 2 * AX + rows.reduce((s, r) => s + r.h, 0), k = W / (b - a), X = t => (t - a) * k;
  const labels = 30.4 * DAY * k >= 44;   // amounts written out once a month is wide enough
  v.W = W;
  let s = '', y = AX; const ys = [];
  rows.forEach(r => { ys.push(y); if(r.bg) s += `<rect x='0' y='${y}' width='${W}' height='${r.h}' fill='${r.bg}'/>`; y += r.h; });
  tlTicks(a, b, W).forEach(([t, txt, maj]) => { const x = X(t);
    s += `<line x1='${x.toFixed(1)}' x2='${x.toFixed(1)}' y1='${AX}' y2='${H - AX}' class='tlg${maj ? ' maj' : ''}'/>`
       + `<text x='${(x + 3).toFixed(1)}' y='${AX - 8}' class='tlt'>${txt}</text>`
       + `<text x='${(x + 3).toFixed(1)}' y='${H - 8}' class='tlt'>${txt}</text>`; });
  rows.forEach((r, i) => { s += tlRowSvg(r, ys[i], X, a, b, W, labels); });
  if(tlToday >= a && tlToday <= b){ const x = X(tlToday).toFixed(1);
    s += `<line x1='${x}' x2='${x}' y1='${AX - 4}' y2='${H - AX + 4}' class='tltoday'/>`; }
  s += `<rect class='tlbr' x='0' y='0' width='${W}' height='${AX}'><title>drag to zoom</title></rect>`
     + `<rect class='tlbr' x='0' y='${H - AX}' width='${W}' height='${AX}'><title>drag to zoom</title></rect>`
     + `<rect class='tlsel' x='0' y='0' width='0' height='${H}'/>`;
  v.svg.setAttribute('width', W); v.svg.setAttribute('height', H); v.svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  v.svg.innerHTML = s;
  v.lab.innerHTML = `<div style='height:${AX}px'></div>`
    + rows.map(r => `<div class='tlrow ${r.lcls || ''}' style='height:${r.h}px'>${r.lab}</div>`).join('')
    + `<div style='height:${AX}px'></div>`;
  v.ra.value = tlIso(a); v.rb.value = tlIso(b - 1);
  const y0 = new Date(a).getUTCFullYear();
  v.ry.value = a === Date.UTC(y0, 0, 1) && b === Date.UTC(y0 + 1, 0, 1) ? String(y0) : '';
}
function tlZoom(v, a, b){
  a = Math.max(v.full[0], a); b = Math.min(v.full[1], b);
  if(!(b > a)) return tlRender(v);
  if(b - a < 2 * HOUR){ b = Math.min(v.full[1], a + 2 * HOUR); a = b - 2 * HOUR; }
  v.a = a; v.b = b; tlRender(v);
}
function tlSetFull(v, a, b){
  v.full = [a, b]; v.a = a; v.b = b;
  const y0 = new Date(a).getUTCFullYear(), y1 = new Date(b - 1).getUTCFullYear();
  v.ry.innerHTML = "<option value=''>zoom to a year…</option>"
    + Array.from({length: y1 - y0 + 1}, (_, i) => y1 - i).map(y => `<option>${y}</option>`).join('');
  v.ra.min = v.rb.min = tlIso(a); v.ra.max = v.rb.max = tlIso(b - 1);
}

const tlTip = document.createElement('div'); tlTip.id = 'tltip'; tlTip.setAttribute('role', 'tooltip');
document.body.appendChild(tlTip);
function tlShow(el, x, y){
  tlTip.textContent = el.dataset.tip; tlTip.style.display = 'block';
  const w = tlTip.offsetWidth, h = tlTip.offsetHeight;
  let L = x + 14, T = y + 14;
  if(L + w > innerWidth - 8) L = Math.max(8, x - w - 14);
  if(T + h > innerHeight - 8) T = Math.max(8, y - h - 14);
  tlTip.style.left = L + 'px'; tlTip.style.top = T + 'px';
}
function tlHide(){ tlTip.style.display = 'none'; }
document.addEventListener('keydown', ev => { if(ev.key === 'Escape') tlHide(); });

const tlV = {p: {id: 'tl-p'}, f: {id: 'tl-f'}};
function tlInitView(v){
  v.el = tlq(v.id); v.sc = v.el.querySelector('.tlsc'); v.svg = v.sc.querySelector('svg'); v.lab = v.el.querySelector('.tll');
  const box = tlq(v.id + '-r');
  box.innerHTML = "<label>from <input type='date' class='ra'></label><label>to <input type='date' class='rb'></label>"
    + "<select class='ry' aria-label='zoom to one year'></select>"
    + "<button type='button' class='rall'>whole period</button><span class='rhint'>or drag along the dates</span>";
  v.ra = box.querySelector('.ra'); v.rb = box.querySelector('.rb'); v.ry = box.querySelector('.ry');
  v.ra.addEventListener('change', () => { const p = tlParse(v.ra.value); if(p) tlZoom(v, p[0], v.b); });
  v.rb.addEventListener('change', () => { const p = tlParse(v.rb.value); if(p) tlZoom(v, v.a, p[1]); });
  v.ry.addEventListener('change', () => { const y = +v.ry.value; if(y) tlZoom(v, Date.UTC(y, 0, 1), Date.UTC(y + 1, 0, 1)); });
  box.querySelector('.rall').addEventListener('click', () => tlZoom(v, v.full[0], v.full[1]));
  const px = ev => ev.clientX - v.svg.getBoundingClientRect().left;
  v.svg.addEventListener('pointerdown', ev => {
    if(!ev.target.classList.contains('tlbr')) return;
    v.drag = px(ev); ev.preventDefault();
    try { v.svg.setPointerCapture(ev.pointerId); } catch(e) {} });
  v.svg.addEventListener('pointermove', ev => {
    if(v.drag != null){ const x = px(ev), sel = v.svg.querySelector('.tlsel');
      sel.setAttribute('x', Math.min(x, v.drag)); sel.setAttribute('width', Math.abs(x - v.drag)); return; }
    const m = ev.target.closest && ev.target.closest('[data-tip]');
    if(m) tlShow(m, ev.clientX, ev.clientY); else tlHide(); });
  v.svg.addEventListener('pointerup', ev => {
    if(v.drag == null) return;
    const x = px(ev), x0 = Math.min(x, v.drag), x1 = Math.max(x, v.drag); v.drag = null;
    if(x1 - x0 > 5){ const inv = q => v.a + q / v.W * (v.b - v.a); tlZoom(v, inv(x0), inv(x1)); } else tlRender(v); });
  v.svg.addEventListener('pointerleave', tlHide);
  v.svg.addEventListener('focusin', ev => { const m = ev.target.closest('[data-tip]');
    if(m){ const r = m.getBoundingClientRect(); tlShow(m, r.right, r.bottom); } });
  v.svg.addEventListener('focusout', tlHide);
}

function tlPRows(){   // the portfolio rows the filters let through
  const {on, hz} = hstate(), ret = tlq('tlret').checked, adh = tlq('tladh').checked;
  return TL.rows.filter(r => (!hz || r.h === hz) && (r.life === '' ? adh : r.life === 'retired' ? ret : on.has(r.life)))
    .map((r, i) => {
      const lab = (TL.fw[r.k]
          ? `<button type='button' class='tlb' data-k='${r.k}' title='${tlEsc(r.name)}: see it version by version'>${tlEsc(r.name)}</button>`
          : `<span class='tln' title='${tlEsc(r.name)}'>${tlEsc(r.name)}</span>`)
        + (r.life ? `<span class='lf lf-${r.life}'>${tlEsc(TL.life[r.life] || r.life)}</span>` : "<span class='lf lf-ah'>ad hoc only</span>");
      return {h: 28, lab, bg: i % 2 ? '#fafbfc' : '',
              marks: r.ev.filter(e => adh || !e.ah).map(e => tlEvMark(e, r, false))};
    });
}
function tlDraw(){
  const v = tlV.p; if(!v.el) return;
  v.rows = tlPRows(); tlRender(v);
  const ms = v.rows.flatMap(r => r.marks.filter(Boolean)), nr = ms.filter(m => m.kind === 'real').length;
  const na = ms.length - nr;
  tlq('tl-p-n').textContent = v.rows.length + ' row' + (v.rows.length === 1 ? '' : 's') + ' · ' + nr + ' real activation'
    + (nr === 1 ? '' : 's') + (na ? ' · ' + na + ' ad hoc allocation' + (na === 1 ? '' : 's') : '');
}

function tlFRows(k){   // the framework view: per version a band row, then one lane per window
  const r = TL.rows.find(x => x.k === k), out = [];
  (TL.fw[k] || []).forEach(g => {
    const st = g.start ? tlParse(g.start)[0] : null, en = g.end ? tlParse(g.end)[0] : tlEnd;
    const dev = /development/.test(g.st || '');
    const vl = g.v ? 'version ' + g.v : 'version not recorded';
    const stat = g.st === 'endorsed' ? 'endorsed' : dev ? g.st.replace('development', 'in development').replace('pre-in ', 'pre-') : (g.st || '');
    const tip = [r.name + ' · ' + vl + (stat ? ' (' + stat + ')' : ''),
      g.start ? 'took effect ' + tlFmt(g.start) : 'start date not recorded',
      g.end ? 'until ' + tlFmt(g.end) + ' (' + g.why + ')' : 'no end recorded',
      g.bt ? 'backtest' + (g.cover ? ' over ' + g.cover[0] + '–' + g.cover[1] : '') + ', simulated activations shown before ' + (g.vf_y || 'its start')
           : 'no backtest recorded',
      g.n_after ? g.n_after + ' simulated row(s) dated after the start are not shown' : ''].filter(Boolean).join('\n');
    out.push({h: 26, lcls: 'tlver', bg: '#f6f8fb',
      lab: `<span class='tln' title='${tlEsc(tip)}'><b>${tlEsc(vl)}</b> <span class='tlst${dev ? ' dev' : ''}'>${tlEsc(stat)}</span></span>`,
      spans: st != null ? [{t0: st, t1: Math.max(en, st + DAY), y: 5, hh: 16, tip,
        cls: 'tlband' + (dev ? ' dev' : '') + (g.end ? '' : ' open'),
        txt: tlFmt(g.start) + ' → ' + (g.end ? tlFmt(g.end) : 'no end recorded')}] : []});
    const cov = g.cover ? {t0: Date.UTC(g.cover[0], 0, 1), t1: Date.UTC(g.cover[1] + 1, 0, 1), y: 3, hh: 20, cls: 'tlcov',
      tip: vl + ': years its backtest analysed, ' + g.cover[0] + '–' + g.cover[1] + ' (no mark: would not have activated)'} : null;
    if(!g.lanes.length)
      out.push({h: 22, lab: `<span class='tlw muted'>${g.bt ? 'no window recorded' : 'no backtest and no real activation recorded'}</span>`,
                lines: st != null ? [st] : []});
    g.lanes.forEach(l => out.push({h: 26, lab: `<span class='tlw' title='${tlEsc(l.w)}'>${tlEsc(l.w)}</span>`,
      spans: cov ? [cov] : [], lines: st != null ? [st] : [],
      marks: l.sims.map(s => tlSimMark(s, g, l, r)).concat(l.reals.map(e => tlEvMark(e, r, true)))}));
  });
  if(!out.length) out.push({h: 26, lab: "<span class='tlw muted'>no version, backtest or real activation recorded</span>"});
  return out;
}
function tlFRange(k){
  let lo = Infinity, hi = tlEnd;
  (TL.fw[k] || []).forEach(g => {
    if(g.cover) lo = Math.min(lo, Date.UTC(g.cover[0], 0, 1));
    if(g.start) lo = Math.min(lo, tlParse(g.start)[0]);
    if(g.end) hi = Math.max(hi, tlParse(g.end)[0]);
    g.lanes.forEach(l => l.sims.concat(l.reals).forEach(x => { const p = tlParse(x.t || x.d); if(p) lo = Math.min(lo, p[0]); }));
  });
  if(!isFinite(lo)) lo = Date.UTC(TL.start, 0, 1);
  const y0 = new Date(lo).getUTCFullYear(), y1 = new Date(Math.min(hi, tlEnd + 3 * 366 * DAY) - 1).getUTCFullYear();
  return [Date.UTC(y0, 0, 1), Date.UTC(y1 + 1, 0, 1)];
}
function tlFw(k, scroll, init){
  const v = tlV.f; if(!TL.fw[k]) return;
  v.k = k; tlq('tlfw').value = k; v.rows = tlFRows(k);
  const [a, b] = tlFRange(k); tlSetFull(v, a, b); tlRender(v);
  const r = TL.rows.find(x => x.k === k), gs = TL.fw[k];
  const nr = r.ev.filter(e => !e.ah).length, nb = gs.filter(g => g.bt).length;
  const ns = gs.reduce((s, g) => s + g.lanes.reduce((t, l) => t + l.sims.length, 0), 0);
  const na = gs.reduce((s, g) => s + (g.n_after || 0), 0);
  tlq('tl-f-head').innerHTML = `<a href='${tlEsc(r.slug)}'><b>${tlEsc(r.name)}</b></a> · ${tlEsc(TL.life[r.life] || r.life)} · `
    + `${gs.filter(g => g.v).length} version(s), ${nb} with a backtest (${ns} simulated activation(s) shown) · `
    + `${nr} real activation(s)` + (na ? ` · ${na} simulated row(s) dated after their version's start not shown` : '');
  if(!init) try { history.replaceState(null, '', '#fw=' + k); } catch(e) {}
  if(scroll) tlq('tl-f-sec').scrollIntoView({block: 'start',
    behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
}
function tlInit(){
  tlInitView(tlV.p); tlInitView(tlV.f);
  let lo = Date.UTC(TL.start, 0, 1);
  TL.rows.forEach(r => r.ev.forEach(e => { const p = tlParse(e.d); if(p && p[0] < lo) lo = Date.UTC(new Date(p[0]).getUTCFullYear(), 0, 1); }));
  tlSetFull(tlV.p, lo, tlEnd);
  tlV.p.lab.addEventListener('click', ev => { const bt = ev.target.closest('.tlb'); if(bt) tlFw(bt.dataset.k, true); });
  const sel = tlq('tlfw'), by = {};
  TL.rows.filter(r => TL.fw[r.k]).forEach(r => (by[r.life] = by[r.life] || []).push(r));
  sel.innerHTML = ['active', 'updating', 'development', 'retired'].filter(l => by[l])
    .map(l => `<optgroup label='${tlEsc(TL.life[l] || l)}'>`
      + by[l].map(r => `<option value='${r.k}'>${tlEsc(r.name)}</option>`).join('') + '</optgroup>').join('');
  sel.addEventListener('change', () => tlFw(sel.value));
  const hk = (location.hash.match(/fw=([A-Z]{3}-[a-z_]+)/) || [])[1];
  const score = k => TL.fw[k].some(g => g.bt) * 1000 + TL.rows.find(r => r.k === k).ev.filter(e => !e.ah).length;
  const def = hk && TL.fw[hk] ? hk : Object.keys(TL.fw).sort((p, q) => score(q) - score(p))[0];
  tlDraw(); if(def) tlFw(def, false, true);
  let rt; addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => { tlRender(tlV.p); tlRender(tlV.f); }, 150); });
}
tlInit();
"""


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

    # ---- the timeline's data: one portfolio row per framework (current, then retired), each
    # with its real activations and ad hoc allocations; rows for the ad hoc allocations of
    # country-hazards with no such framework; and per framework the versions / window lanes
    ret = _frameworks(d, TL_RETIRED)
    for f in ret:
        f["events"] = _events(d, f["c"], f["h"], f["version"], f["kb_fw"], umap, f["slug"])
    tl_rows, tl_fw = [], {}
    for f in fws + ret:
        k = f"{f['c']}-{f['h']}"
        ah = _events(d, f["c"], f["h"], None, f["kb_fw"], umap, f["slug"], adhoc=True)
        tl_rows.append(dict(k=k, name=f["name"], h=f["h"], life=f["life"], slug=f["slug"],
                            ev=[_tl_ev(ev) for ev in f["events"]] + [_tl_ev(ev, True) for ev in ah]))
        tl_fw[k] = _tl_detail(d, f)
    cur = d["current"]
    on_row = {(f["c"], f["h"]) for f in fws + ret}
    ah_rows = []
    for (c, h), g in act_all[act_all["event_type"] != "framework_aa"].groupby(["country_iso3", "hazard"]):
        if (c, h) in on_row:
            continue
        cr = cur[(cur["country_iso3"] == c) & (cur["hazard"] == h)]
        slug = f"fw-{c.lower()}-{h}.html" if len(cr) else None   # a framework page exists for every d['current'] row
        kb = cr["kb_framework"].iloc[0] if len(cr) and pd.notna(cr["kb_framework"].iloc[0]) else None
        cn = next((x for x in list(g["country_name"]) + list(cur.loc[cur["country_iso3"] == c, "country_name"])
                   if isinstance(x, str) and x), c)
        ah = _events(d, c, h, None, kb, umap, slug, adhoc=True)
        ah_rows.append(dict(k=f"{c}-{h}", name=f"{cn} — {h.replace('_', ' ')}", h=h, life="", slug=slug or "",
                          ev=[_tl_ev(ev, True) for ev in ah]))
    tl_rows += sorted(ah_rows, key=lambda r: r["name"])
    tl = dict(rows=tl_rows, fw=tl_fw, today=date.today().isoformat(), start=TL_START,
              hz={h: PAL[HAZARDS.index(h)] for h in HAZARDS}, other="#64748b", sim=SIM_COL,
              red=ACT_RED, life=dict(LIFE_LABEL, retired="retired"))

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
    # ---- the timeline (portfolio view, then the framework view); drawn by TL_JS from D.tl
    hz_on = sorted({r["h"] for r in tl_rows}, key=lambda h: (haz(h) == "other", h))
    hz_key = " ".join(f"<span class='tlk' style='background:{tl['hz'].get(h, tl['other'])}'></span>{_esc(h)}"
                      for h in hz_on if h in HAZARDS) + (f" <span class='tlk' style='background:{tl['other']}'></span>other"
                                                        if any(h not in HAZARDS for h in hz_on) else "")
    n_ret = len(ret)
    n_ah = sum(e["ah"] for r in tl_rows for e in r["ev"])
    tl_html = f"""
<h2 id='tl-p-sec'>When the frameworks activated</h2>
<p class='meta'>Each mark is a real activation (the trigger was met and the pre-arranged money released), placed at
its month, or its day when recorded, sized by the money released and coloured by hazard; hover or tab to a mark for
the details, click it for its announcement (else its CERF allocation page, else the framework page), and click a
framework's name to see it version by version below.</p>
<div class='tlbar'>
 <label><input type='checkbox' id='tlret' onchange='tlDraw()'> retired frameworks ({n_ret})</label>
 <label title='money released without a pre-agreed trigger'><input type='checkbox' id='tladh' onchange='tlDraw()'>
  ad hoc allocations ({n_ah}), which are not framework activations</label>
 <span class='tlr' id='tl-p-r'></span><span class='cnt' id='tl-p-n'></span></div>
<div class='tl' id='tl-p'><div class='tll'></div><div class='tlsc'><svg role='group'
 aria-label='Real activations by date, one row per framework'></svg></div></div>
<p class='legend'>{hz_key} · size: money released (<span class='tlk ring'></span> amount not recorded) ·
<span class='tlk dia' style='background:#8a93a0'></span> ad hoc allocation · faint bar behind a mark: the month,
or the whole year, its date is known to · dashed red line: today. Drag along the dates (top or bottom) to zoom.</p>
<h2 id='tl-f-sec'>One framework, version by version</h2>
<p class='meta'>Each version is a band from the day it took effect, with one lane per window under it:
<span class='tlk sq' style='background:{SIM_COL}'></span> the years its trigger would have activated in its
backtest, which is fixed before the version is endorsed and so drawn only before the version's start (dotted line),
and <span class='tlk' style='background:{ACT_RED}'></span> its real activations, which can only come after; the
backtests give years today, and the day (for storms the hour) appears as the trigger analyses provide it.</p>
<div class='tlbar'><label>framework <select id='tlfw'></select></label><span class='tlr' id='tl-f-r'></span></div>
<p class='meta' id='tl-f-head'></p>
<div class='tl' id='tl-f'><div class='tll'></div><div class='tlsc'><svg role='group'
 aria-label='One framework: its versions, simulated and real activations by date'></svg></div></div>
<p class='legend'><span class='tlk sq' style='background:#dbe9f6;box-shadow:inset 0 0 0 1px #8fb2d6'></span> version
endorsed · <span class='tlk sq' style='background:#fdf1dc;box-shadow:inset 0 0 0 1px #e0b766'></span> version in
development · <span class='tlk sq' style='background:#eaf0f6'></span> years its backtest analysed (no mark: would not
have activated) · <span class='tlk sq' style='background:{SIM_COL}'></span> would have activated: a block for the
year, a square on the day or hour · <span class='tlk' style='background:{ACT_RED}'></span> real activation, sized by
the money released.</p>"""
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
/* the interactive timeline */
#tl-p-sec, #tl-f-sec {{ scroll-margin-top:84px; }}   /* clear of the sticky filter bar */
.tl {{ display:flex; background:#fff; border:1px solid #e0e0e0; border-radius:6px; margin:6px 0 4px; }}
.tl .tll {{ flex:0 0 250px; width:250px; border-right:1px solid #dde3ea; font-size:12px; min-width:0; }}
.tl .tlrow {{ display:flex; align-items:center; gap:6px; padding:0 8px; overflow:hidden; white-space:nowrap; box-sizing:border-box; }}
.tl .tlb, .tl .tln, .tl .tlw {{ overflow:hidden; text-overflow:ellipsis; min-width:0; flex:1 1 auto; text-align:left; }}
.tl .tlb {{ background:none; border:0; padding:0; font:inherit; font-weight:600; color:#17548a; cursor:pointer; }}
.tl .tlb:hover {{ text-decoration:underline; }}
.tl .tlb:focus-visible, .tlbar button:focus-visible {{ outline:2px solid #17548a; outline-offset:1px; }}
.tl .lf {{ flex:0 0 auto; font-size:10px; padding:0 6px; }}
.lf-retired {{ background:#eceff3; color:#555; }} .lf-ah {{ background:#f4eefa; color:#5b3d80; }}
.tl .tlrow.tlver {{ background:#f6f8fb; }} .tl .tlw {{ padding-left:14px; color:#334; }}
.tl .tlst {{ font-size:10.5px; color:#17548a; }} .tl .tlst.dev {{ color:#8a5c0a; }}
.tl .tlsc {{ flex:1 1 auto; min-width:0; overflow-x:auto; overflow-y:hidden; }}
.tl svg {{ display:block; font-family:inherit; }}
.tl .tlg {{ stroke:#eef0f3; }} .tl .tlg.maj {{ stroke:#d3dbe4; }}
.tl .tlt {{ font-size:10.5px; fill:#556; }}
.tl .tltoday {{ stroke:{ACT_RED}; stroke-dasharray:3 3; opacity:.55; }}
.tl .tlbr {{ fill:#000; fill-opacity:0; cursor:col-resize; touch-action:none; }}
.tl .tlbr:hover {{ fill:#2a78d6; fill-opacity:.06; }}
.tl .tlsel {{ fill:#2a78d6; fill-opacity:.12; pointer-events:none; }}
.tl .tlext {{ opacity:.22; pointer-events:none; }}
.tl .tlamt, .tl .tlbt {{ font-size:10px; fill:#334; pointer-events:none; }}
.tl .tlband {{ fill:#dbe9f6; stroke:#8fb2d6; }} .tl .tlband.open {{ fill-opacity:.55; }}
.tl .tlband.dev {{ fill:#fdf1dc; stroke:#e0b766; stroke-dasharray:4 3; }}
.tl .tlcov {{ fill:#eaf0f6; }}
.tl .tlvs {{ stroke:#7d8b99; stroke-dasharray:2 3; }}
.tl .tlm {{ cursor:pointer; outline:none; }} .tl g.tlm {{ cursor:default; }}
.tl .tlm .mk {{ transform-box:fill-box; transform-origin:center; }}
.tl .tlm:hover .mk, .tl .tlm:focus .mk {{ transform:scale(1.35); }}
.tl .tlm:focus-visible .mk {{ stroke:#111; stroke-width:2; }}
@media (prefers-reduced-motion: no-preference) {{ .tl .tlm .mk {{ transition:transform .12s ease-out; }} }}
.tlbar {{ display:flex; gap:8px 14px; flex-wrap:wrap; align-items:center; font-size:12.5px; margin:6px 0; }}
.tlbar .tlr {{ display:flex; gap:6px 10px; flex-wrap:wrap; align-items:center; }}
.tlbar input[type=date], .tlbar select, .tlbar button {{ font:inherit; font-size:12px; }}
.tlbar .rhint {{ color:#888; font-size:11.5px; }} .tlbar .cnt {{ font-size:12px; color:#666; margin-left:auto; }}
.tlk {{ display:inline-block; width:10px; height:10px; border-radius:50%; vertical-align:-1px; margin:0 2px; }}
.tlk.sq {{ border-radius:2px; }} .tlk.dia {{ transform:rotate(45deg) scale(.85); border-radius:1px; }}
.tlk.ring {{ background:#fff !important; box-shadow:inset 0 0 0 1.5px #667; }}
#tltip {{ position:fixed; z-index:60; display:none; max-width:340px; background:#1f2733; color:#fff; font-size:12px;
  line-height:1.45; padding:7px 10px; border-radius:5px; white-space:pre-line; pointer-events:none;
  box-shadow:0 2px 8px rgba(0,0,0,.2); }}
@media (max-width:700px) {{ .tl .tll {{ flex-basis:128px; width:128px; font-size:11px; }} .tl .lf {{ display:none; }}
  .tlbar .rhint {{ display:none; }} }}
</style>
<div class='fbar' id='hbar'>{life_boxes}
 <label>hazard <select id='hhaz' onchange='hfilt()'><option value=''>all</option>{hz_opts}</select></label>
 <button class='dl' onclick='histCsv()' title='the simulated and real activations of the frameworks shown'>⬇ CSV</button>
 <span class='cnt' id='hn'></span></div>
{tl_html}
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
    js = TL_JS + """
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
  if(typeof tlDraw === 'function') tlDraw();   // the timeline follows the same filters
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
               json.dumps({"rows": rows, "tl": tl}, default=str).replace("</", "<\\/"), js)
