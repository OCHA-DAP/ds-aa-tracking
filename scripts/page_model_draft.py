"""Mock-ups of the Model page (pillar-model-draft.html), 2026-10-01, for the team lead to compare
with pillar-model.html. The question: "Are bar charts the best way to show this to a layperson?"

Same data as the Model page (page_model.model_windows), drawn without bar charts: a tile grid,
a shaded count table, lead-time range bars, a return-period strip and a preview of the
historical activations grid. Nothing here replaces the Model page."""

import json
import math
import re

import pandas as pd
from dashboards import LIFE_LABEL, PAL, _dash_page, haz, sim_at, sim_before_start
from page_model import MEASURE, NO_TRIGGER, UNCLASSIFIED, _esc, _lead, model_windows

# the map's status colours (landing.KB_COLOR): 'being updated' = half active, half development
STATUS_BG = {"active": "#2171b5", "development": "#9ecae1",
             "updating": "linear-gradient(135deg,#2171b5 0 50%,#9ecae1 50% 100%)"}
STATUS_ORDER = ["active", "updating", "development"]
# hazard colours as on the map (landing.HAZ_COLOR)
HAZ_COLOR = {"flood": "#2a78d6", "drought": "#eb6834", "storm": "#8e5bd9", "cholera": "#1baf7a",
             "other": "#b8860b"}
HAZ_ORDER = ["drought", "flood", "storm", "cholera", "other"]
HAZ_LABEL = {"drought": "Drought", "flood": "Floods", "storm": "Tropical cyclones",
             "cholera": "Cholera", "other": "Other"}
BASES = ["forecast", "observational", "mixed", "not recorded"]
RAMP = ["#ffffff", "#deebf7", "#c6dbef", "#9ecae1", "#6baed6", "#4292c6", "#2171b5", "#08519c"]
SIM_COL, ACT_RED = PAL[0], "#e3322d"     # as on pillar-history.html
FIRST_YEAR = 2000                        # the history preview starts here (as the full grid)
FONT = "-apple-system,'Segoe UI',Roboto,sans-serif"

# ------------------------------------------------ lead time -> days (only clean statements)
_UNIT = {"h": 1 / 24, "hr": 1 / 24, "hrs": 1 / 24, "hour": 1 / 24, "hours": 1 / 24,
         "day": 1, "days": 1, "week": 7, "weeks": 7, "month": 30, "months": 30}
_LEAD = re.compile(r"^(?:~|≈|about\s+)?(≤|<=|<|up to\s+|maximum\s+|max\.?\s+)?~?\s*"
                   r"(\d+(?:\.\d+)?)\s*(?:(?:–|-|to)\s*(\d+(?:\.\d+)?))?\s*"
                   r"(hours?|hrs?|h|days?|weeks?|months?)\b")
_LEAD_SKIP = re.compile(r"after|lag|post|>", re.IGNORECASE)   # not a warning before the shock
LEAD_TICKS = [(0, "same day"), (1, "1 day"), (3, "3 days"), (7, "1 week"), (14, "2 weeks"),
              (30, "1 month"), (90, "3 months"), (180, "6 months")]
LEAD_MAX = 200


def lead_days(s):
    """(low, high, 'up to'?) in days when the stated lead time starts with a number or range
    in hours / days / weeks / months (a month = 30 days); None otherwise."""
    s = str(s or "").strip()
    if not s or _LEAD_SKIP.search(s):
        return None
    m = _LEAD.match(s.lower())
    if not m:
        return None
    k = _UNIT[m.group(4)]
    a = float(m.group(2)) * k
    b = float(m.group(3)) * k if m.group(3) else a
    return min(a, b), max(a, b), bool(m.group(1))


def _days_txt(v):
    if v < 1:
        return "same day" if v == 0 else f"{v * 24:.0f} hours"
    if v >= 30:
        return f"{v / 30:.0f} month{'s' if round(v / 30) != 1 else ''}"
    return f"{v:.0f} day{'s' if round(v) != 1 else ''}"


def _a(s):
    """Attribute-safe text (data-tip)."""
    return _esc(s).replace("'", "&#x27;")


def _svg(w, h, inner, label):
    # drawn at its own size (never stretched, so the text stays 11px); shrinks on narrow screens
    return (f"<svg viewBox='0 0 {w} {h}' width='{w}' role='img' aria-label='{_a(label)}' "
            f'style="display:block;max-width:100%;height:auto;font:11px {FONT}">{inner}</svg>')


# ------------------------------------------------ 1. tile grid: what the triggers watch
def _tiles(fws, cat_fw):
    order = [c for c, _ in MEASURE if c in cat_fw]
    order.sort(key=lambda c: -len(cat_fw[c]))
    order += [c for c in (UNCLASSIFIED, NO_TRIGGER) if c in cat_fw]
    groups = []
    for c in order:
        tiles = "".join(
            f"<span class='tl tl-{f['lifecycle']}' data-tip='{_a(f['name'])} · "
            f"{_a(LIFE_LABEL.get(f['lifecycle'], f['lifecycle']))} · version {_a(f['version'])}'>"
            f"<b>{_esc(f['country_name'])}</b><i>{_esc(f['hazard'].replace('_', ' '))}</i></span>"
            for f in sorted(cat_fw[c], key=lambda f: (STATUS_ORDER.index(f["lifecycle"]),
                                                     f["country_name"])))
        groups.append(f"<div class='tg'><div class='tgh'>{_esc(c)} <span class='n'>"
                      f"{len(cat_fw[c])}</span></div><div class='tgs'>{tiles}</div></div>")
    n_multi = sum(len(f["cats"]) > 1 for f in fws)
    legend = "".join(f"<span><span class='sw tl-{lc}'></span>{LIFE_LABEL[lc]}</span>" for lc in STATUS_ORDER)
    return (f"<p class='how'>One tile per current framework, under each thing its triggers watch. "
            f"A framework that watches two things (say wind and rainfall) appears in both groups — "
            f"{n_multi} of the {len(fws)} do — so the tiles add up to more than {len(fws)}.</p>"
            f"<div class='lg'>{legend}</div><div class='tgrid'>{''.join(groups)}</div>")


# ------------------------------------------------ 2. shaded count table: forecast or observed
def _basis_table(wrows):
    n = {}
    for x in wrows:
        k = (haz(x["f"]["hazard"]), x["basis"])
        n[k] = n.get(k, 0) + 1
    hz = [h for h in HAZ_ORDER if any(k[0] == h for k in n)]
    cols = [b for b in BASES if any(k[1] == b for k in n)]
    top = max(n.values(), default=1)

    def cell(v):
        i = 0 if not v else max(1, math.ceil(v / top * (len(RAMP) - 1)))
        fg = "#fff" if i >= 5 else "#1a1a1a" if v else "#b8bcc4"
        return f"<td class='sc' style='background:{RAMP[i]};color:{fg}'>{v}</td>"
    head = "".join(f"<th>{_esc(b)}</th>" for b in cols)
    body = "".join(
        f"<tr><th class='rh'>{HAZ_LABEL[h]}</th>{''.join(cell(n.get((h, b), 0)) for b in cols)}"
        f"<td class='tot'>{sum(n.get((h, b), 0) for b in cols)}</td></tr>" for h in hz)
    foot = ("<tr class='tr'><th class='rh'>all hazards</th>"
            + "".join(f"<td class='tot'>{sum(n.get((h, b), 0) for h in hz)}</td>" for b in cols)
            + f"<td class='tot all'>{sum(n.values())}</td></tr>")
    n_mix = sum(v for (_, b), v in n.items() if b == "mixed")
    return (f"<p class='how'>Each number is a count of trigger windows (the current version of every "
            f"current framework); the darker the cell, the more windows. Read across a row for one "
            f"hazard. Mixed = a single window that uses both forecast and observed data ({n_mix}).</p>"
            f"<table class='shade'><thead><tr><th></th>{head}<th class='tot'>total</th></tr></thead>"
            f"<tbody>{body}{foot}</tbody></table>")


# ------------------------------------------------ 3. lead time: range bars on one days axis
def _lead_chart(fws):
    rows, text = [], []
    for f in fws:
        miss = []
        for t in f["trig"]:
            wn, lt = (t.get("window") or t.get("trigger") or ""), _lead(t)
            p = lead_days(lt)
            if p:
                rows.append({"h": haz(f["hazard"]), "f": f, "w": wn, "lt": lt, "lo": p[0], "hi": p[1], "upto": p[2]})
            else:
                miss.append((wn, lt))
        if miss:
            text.append((haz(f["hazard"]), f, miss))
    LW, PW, RH, GH, TOP = 270, 800, 17, 24, 30
    W = LW + PW + 24

    def X(v):
        return LW + PW * math.log1p(v) / math.log1p(LEAD_MAX)
    out, y = [], TOP
    for h in HAZ_ORDER:
        rs = [r for r in rows if r["h"] == h]
        if not rs:
            continue
        out.append(f"<text x='4' y='{y + 16}' font-weight='700' fill='{HAZ_COLOR[h]}'>{HAZ_LABEL[h]}</text>")
        y += GH
        for r in rs:
            cy, col = y + RH / 2, HAZ_COLOR[h]
            lab = f"{r['f']['country_name']} · {r['w']}"
            short = lab if len(lab) <= 44 else lab[:43] + "…"
            tip = (f"{r['f']['name']} · {r['w']}: {r['lt']} → "
                   + (f"up to {_days_txt(r['hi'])}" if r["upto"] else _days_txt(r["lo"])
                      if r["lo"] == r["hi"] else f"{_days_txt(r['lo'])} to {_days_txt(r['hi'])}"))
            out.append(f"<text x='{LW - 8}' y='{cy + 4}' text-anchor='end' fill='#334155'>{_esc(short)}</text>")
            if r["lo"] == r["hi"]:
                out.append(f"<circle cx='{X(r['lo']):.1f}' cy='{cy}' r='5' fill='{col}' data-tip='{_a(tip)}'/>")
            else:
                x0, x1 = X(r["lo"]), X(r["hi"])
                out.append(f"<rect x='{x0:.1f}' y='{cy - 5}' width='{max(x1 - x0, 6):.1f}' height='10' rx='5' "
                           f"fill='{col}' fill-opacity='.85' data-tip='{_a(tip)}'/>")
            y += RH
    grid = "".join(
        f"<line x1='{X(v):.1f}' x2='{X(v):.1f}' y1='{TOP - 6}' y2='{y + 4}' stroke='#e6e8ec'/>"
        f"<text x='{X(v):.1f}' y='{TOP - 10}' text-anchor='middle' fill='#52514e'>{t}</text>"
        f"<text x='{X(v):.1f}' y='{y + 18}' text-anchor='middle' fill='#52514e'>{t}</text>"
        for v, t in LEAD_TICKS)
    svg = _svg(W, y + 26, grid + "".join(out), "lead time of each trigger window, in days")
    lst = "".join(
        f"<li><b>{_esc(f['name'])}</b> — "
        + "; ".join(f"{_esc(w)}: {_esc(lt) if lt else '<span class=muted>not stated</span>'}" for w, lt in miss)
        + "</li>"
        for h in HAZ_ORDER for hh, f, miss in text if hh == h)
    n_txt = sum(len(m) for _, _, m in text)
    return (f"<p class='how'>How long before the shock (landfall, flood peak, the lean season…) each trigger "
            f"window activates. A bar is a stated range, a dot a single figure (\"up to 5 days\" is drawn at 5 "
            f"days). The scale is stretched at the short end so hours and months fit on one line; a month "
            f"counts as 30 days.</p>{svg}"
            f"<p class='how' style='margin-top:10px'><b>Not stated in days</b> ({n_txt} windows: months of the "
            f"year, a lag after the event, or no figure) — as the frameworks put it:</p>"
            f"<ul class='lead'>{lst}</ul>"), len(rows), n_txt


# ------------------------------------------------ 4. return period: one strip, words on the axis
def _rp_strip(fws, wrows):
    RMIN, RMAX, PAD, W, D = 1.2, 22, 36, 1080, 11

    def X(v):
        return PAD + (W - 2 * PAD) * (math.log(v) - math.log(RMIN)) / (math.log(RMAX) - math.log(RMIN))
    pts = sorted(({"x": X(min(max(r["rp"], RMIN), RMAX)), "r": r} for r in wrows if r["rp"] is not None),
                 key=lambda p: (p["x"], HAZ_ORDER.index(haz(p["r"]["f"]["hazard"]))))
    last = []                     # right-most x on each stack level
    for p in pts:
        lv = next((i for i, lx in enumerate(last) if p["x"] - lx >= D), len(last))
        if lv == len(last):
            last.append(p["x"])
        last[lv] = p["x"]
        p["lv"] = lv
    base = 26 + D * max(len(last), 1)
    dots = []
    for p in pts:
        r = p["r"]
        col, cy = HAZ_COLOR[haz(r["f"]["hazard"])], base - D / 2 - p["lv"] * D
        tip = (f"{r['f']['name']} · {r['window']}: about once every {r['rp']:.1f} years"
               + (" (from the backtest)" if r["rp_src"] == "backtest" else f" (as stated: {r['rp_txt']})"))
        fill = col if r["rp_src"] == "backtest" else "#fff"
        dots.append(f"<circle cx='{p['x']:.1f}' cy='{cy:.1f}' r='4.4' fill='{fill}' stroke='{col}' "
                    f"stroke-width='1.6' data-tip='{_a(tip)}'/>")
    ticks = "".join(
        f"<line x1='{X(v):.1f}' x2='{X(v):.1f}' y1='{base}' y2='{base + 5}' stroke='#888'/>"
        f"<text x='{X(v):.1f}' y='{base + 18}' text-anchor='middle' fill='#333' font-size='12'>{v}</text>"
        for v in (2, 3, 5, 10, 20))
    axis = (f"<line x1='{PAD}' x2='{W - PAD}' y1='{base}' y2='{base}' stroke='#888'/>{ticks}"
            f"<text x='{W / 2}' y='{base + 36}' text-anchor='middle' fill='#333' font-size='12.5' "
            f"font-weight='600'>about once every … years</text>"
            f"<text x='{PAD}' y='{base + 36}' fill='#777'>← more often</text>"
            f"<text x='{W - PAD}' y='{base + 36}' text-anchor='end' fill='#777'>less often →</text>")
    svg = _svg(W, base + 46, axis + "".join(dots), "return period of each trigger window")
    no_num = [f for f in fws if f["trig"] and not any(r["rp"] is not None for r in wrows if r["f"] is f)]
    part = sum(1 for r in wrows if r["rp"] is None and r["f"] not in no_num)
    no_trig = [f for f in fws if not f["trig"]]
    hz = sorted({haz(r["f"]["hazard"]) for r in wrows if r["rp"] is not None}, key=HAZ_ORDER.index)
    legend = ("".join(f"<span><span class='sw' style='background:{HAZ_COLOR[h]};border-radius:50%'></span>"
                      f"{HAZ_LABEL[h]}</span>" for h in hz)
              + "<span><span class='sw' style='background:#555;border-radius:50%'></span>from the backtest</span>"
              + "<span><span class='sw' style='border:1.6px solid #555;border-radius:50%'></span>as the framework "
                "states it</span>")
    return (f"<p class='how'>Each dot is one trigger window, placed by how often it is designed to activate: "
            f"a dot at 5 means about once every 5 years. Dots further left activate more often. Hover a dot for "
            f"the framework and the exact figure.</p><div class='lg'>{legend}</div>{svg}"
            f"<p class='how'><b>No number stated</b> for any window of: "
            f"{_esc(', '.join(f['name'] for f in no_num)) or '—'}"
            + (f"; and for {part} more windows of frameworks that state it for their other windows" if part else "")
            + (f". No trigger recorded yet: {_esc(', '.join(f['name'] for f in no_trig))}" if no_trig else "")
            + ".</p>"), len(pts), no_num, part


# ------------------------------------------------ 5. activations: preview of the history grid
def _hist_rows(d, fws):
    """(framework, simulated rows, first, last simulated year, real framework activations,
    year the version took effect) per framework — page_history's selection when it imports,
    else a plain fallback. Either way only simulated rows dated before the version's start
    year count (dashboards.sim_before_start)."""
    cur = d["current"].set_index(["country_iso3", "hazard"])["latest_version"]
    try:
        import page_history as ph
        how = "page_history"
    except Exception:   # noqa: BLE001 — the preview must not take the draft down
        ph, how = None, "fallback"
    act = d["act_all"][d["act_all"]["event_type"] == "framework_aa"]
    out = []
    for f in fws:
        c, h = f["country_iso3"], f["hazard"]
        v = cur.get((c, h))
        v = None if v is None or (not isinstance(v, str) and pd.isna(v)) else str(v)
        if ph is not None:
            try:
                shown, ss, y0, y1, _, vf_y, _ = ph._backtest(d, c, h, v)
                evs = [(e["year"], e["same"], e["date"], e["win"]) for e in ph._events(d, c, h, shown or v)]
                out.append((f, ss, y0, y1, evs, vf_y))
                continue
            except Exception:   # noqa: BLE001
                how = "fallback"
        sim = d["sim"][(d["sim"]["country_iso3"] == c) & (d["sim"]["hazard"] == h)]
        vs = sorted(sim["version"].astype(str).unique())
        shown = v if v in vs else (vs[-1] if vs else None)
        ss = sim[sim["version"].astype(str) == shown] if shown else sim.iloc[0:0]
        fvm = d["fv_meta"]
        vf = fvm.loc[(fvm["country_iso3"] == c) & (fvm["hazard"] == h)
                     & (fvm["version"].astype(str) == str(shown)), "valid_from"]
        ss, _, vf_y = sim_before_start(ss, vf)
        y0 = int(ss["sim_year"].min()) if len(ss) else None
        y1 = int(ss["sim_year"].max()) if len(ss) else None
        a = act[(act["country_iso3"] == c) & (act["hazard"] == h)]
        evs = [(int(str(r.event_date)[:4]), True, str(r.event_date), str(r.window_name or ""))
               for r in a.itertuples() if str(r.event_date)[:4].isdigit()]
        out.append((f, ss, y0, y1, evs, vf_y if shown else None))
    return out, how


def _hist_preview(d, fws):
    rows, how = _hist_rows(d, fws)
    years = list(range(FIRST_YEAR, pd.Timestamp.now(tz="UTC").year + 1))
    LW, CW, RH, TOP = 200, 28, 16, 22
    W = LW + CW * len(years) + 8
    out = []
    for i, y in enumerate(years):
        if y % 5 == 0:
            out.append(f"<text x='{LW + i * CW + CW / 2}' y='{TOP - 8}' text-anchor='middle' fill='#52514e'>{y}</text>")
    n_sim = n_real = 0
    for j, (f, ss, y0, y1, evs, vf_y) in enumerate(rows):
        yy = TOP + j * RH
        name = f"{f['country_name']} — {f['hazard']}"
        out.append(f"<text x='{LW - 8}' y='{yy + 11}' text-anchor='end' fill='#334155'>{_esc(name)}</text>")
        hit = {}
        for r in ss.itertuples():
            w = sim_at(r)
            hit.setdefault(int(r.sim_year), []).append(
                str(r.window_name) + ("" if w == f"in {r.sim_year}" else f" {w}"))
        for i, y in enumerate(years):
            x = LW + i * CW
            use = vf_y is not None and y >= vf_y          # the version in use: real only
            cov = not use and y0 is not None and y0 <= y <= y1
            ev = [e for e in evs if e[0] == y]
            tip = [f"{name} · {y}"]
            if use:
                tip.append(f"version in use (took effect {vf_y}): real activations only")
            elif y in hit:
                tip.append("simulation: would have activated (" + ", ".join(sorted(set(hit[y]))) + ")")
            elif cov:
                tip.append("simulation: would not have activated")
            else:
                tip.append("not covered by the simulation")
            tip += [f"activated for real {e[2]}" + (f" · {e[3]}" if e[3] else "") for e in ev]
            out.append(f"<rect x='{x + 1}' y='{yy + 1}' width='{CW - 2}' height='{RH - 2}' rx='2' "
                       f"fill='{'#fbf6ee' if use else '#ffffff' if cov else '#eef1f5'}' stroke='#eceef2' "
                       f"data-tip='{_a(' · '.join(tip))}'/>")
            cx, cy = x + CW / 2, yy + RH / 2
            if y in hit and not use:
                n_sim += 1
                out.append(f"<circle cx='{cx - (3 if ev else 0)}' cy='{cy}' r='3.6' fill='{SIM_COL}' "
                           f"pointer-events='none'/>")
            if ev:
                n_real += 1
                same = any(e[1] for e in ev)
                out.append(f"<circle cx='{cx + (3 if y in hit else 0)}' cy='{cy}' r='3.8' "
                           f"fill='{ACT_RED if same else '#fff'}' stroke='{ACT_RED}' stroke-width='1.6' "
                           f"pointer-events='none'/>")
    svg = _svg(W, TOP + len(rows) * RH + 6, "".join(out), "simulated and real activations by year")
    legend = (f"<span><span class='sw' style='background:{SIM_COL};border-radius:50%'></span>the trigger would "
              f"have activated (simulation)</span><span><span class='sw' style='background:{ACT_RED};"
              f"border-radius:50%'></span>activated for real</span><span><span class='sw' style='border:1.6px "
              f"solid {ACT_RED};border-radius:50%'></span>for real, under another version</span>"
              f"<span><span class='sw' style='background:#fbf6ee'></span>version in use: real only</span>"
              f"<span><span class='sw' style='background:#eef1f5'></span>year not simulated</span>")
    return (f"<p class='how'>One row per current framework, one column per year since {FIRST_YEAR}. A blue dot: "
            f"today's trigger, run on past data, would have activated that year. A red dot: it activated for "
            f"real. Cream: the version in use since it took effect — real activations only, as its backtest "
            f"was fixed before. Grey: the simulation does not cover that year.</p><div class='lg'>{legend}</div>"
            f"<div class='hscroll'>{svg}</div>"
            f"<p class='how'><a href='pillar-history.html'><b>Historical activations →</b></a> the full grid, "
            f"with the years before {FIRST_YEAR}, the windows and the money released.</p>"), how, n_sim, n_real


# ------------------------------------------------ page
def build_model_draft(page, d):
    m = model_windows(d)
    fws, win, cat_fw = m["fws"], m["win"], m["cat_fw"]
    wrows = [x for x in win if x["window"] is not None]
    tiles = _tiles(fws, cat_fw)
    table = _basis_table(wrows)
    lead, n_lead, n_lead_txt = _lead_chart(fws)
    rp, n_rp, _, _ = _rp_strip(fws, wrows)
    hist, how, _, _ = _hist_preview(d, fws)
    panels = f"""
<style>
.span2 {{ grid-column:1 / -1; }}
p.how {{ font-size:12.5px; color:#444; margin:0 0 10px; }}
.muted {{ color:#888; }}
.lg {{ display:flex; gap:14px; flex-wrap:wrap; font-size:12px; color:#444; margin:0 0 10px; }}
.lg .sw {{ display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:5px; vertical-align:-2px; box-sizing:border-box; }}
.tgrid {{ display:flex; flex-wrap:wrap; gap:16px 30px; align-items:flex-start; }}
.tg {{ flex:0 1 auto; max-width:536px; }}   /* up to five tiles a row */
.tgh {{ font-size:13px; font-weight:700; margin:0 0 6px; color:#223; }} .tgh::first-letter {{ text-transform:uppercase; }}
.tgh .n {{ color:#889; font-weight:600; margin-left:4px; }}
.tgs {{ display:flex; flex-wrap:wrap; gap:4px; }}
.tl {{ display:inline-flex; flex-direction:column; justify-content:center; width:100px; height:36px; padding:0 7px;
       border-radius:4px; box-sizing:border-box; line-height:1.15; cursor:default; }}
.tl b {{ font-size:11.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.tl i {{ font-size:10.5px; font-style:normal; opacity:.9; }}
.tl-active, .lg .tl-active {{ background:{STATUS_BG['active']}; color:#fff; }}
.tl-updating, .lg .tl-updating {{ background:{STATUS_BG['updating']}; color:#fff; text-shadow:0 0 3px rgba(8,48,107,.9); }}
.tl-development, .lg .tl-development {{ background:{STATUS_BG['development']}; color:#0b3a66; }}
table.shade {{ border-collapse:separate; border-spacing:3px; font-size:13px; }}
table.shade th {{ font-weight:600; font-size:12px; color:#445; padding:4px 8px; text-align:center; }}
table.shade th.rh {{ text-align:left; }}
table.shade td {{ width:92px; height:38px; text-align:center; border-radius:4px; font-size:15px; font-weight:600; }}
table.shade td.tot {{ background:#f4f5f7; color:#223; font-weight:700; }}
table.shade td.all {{ background:#e6e8ec; }}
ul.lead {{ margin:0; padding-left:16px; }} ul.lead li {{ font-size:12.5px; margin:4px 0; }}
.hscroll {{ overflow-x:auto; }} .hscroll svg {{ min-width:600px; }}
.dtip {{ position:fixed; z-index:9999; pointer-events:none; background:#0f2540; color:#fff; font:12px {FONT};
         padding:5px 8px; border-radius:5px; max-width:340px; box-shadow:0 4px 14px rgba(0,0,0,.25); }}
.mockbadge {{ display:inline-block; background:#fdf1dc; color:#8a5c0a; font-weight:700; font-size:11px;
              padding:1px 8px; border-radius:9px; margin-right:6px; }}
</style>
<div class='grid'>
 <div class='panel span2'><h3>What do the triggers watch?</h3>{tiles}</div>
 <div class='panel'><h3>Forecast or observed data?</h3>{table}</div>
 <div class='panel span2'><h3>How much warning do the triggers give?</h3>{lead}</div>
 <div class='panel span2'><h3>How often would each trigger activate?</h3>{rp}</div>
 <div class='panel span2'><h3>Have the triggers activated?</h3>{hist}</div>
</div>"""
    js = """
(function(){ const tip = document.createElement('div'); tip.className = 'dtip'; tip.hidden = true;
  document.body.appendChild(tip);
  document.addEventListener('mousemove', e => {
    const el = e.target.closest ? e.target.closest('[data-tip]') : null;
    if(!el){ tip.hidden = true; return; }
    tip.textContent = el.dataset.tip; tip.hidden = false;
    tip.style.left = Math.min(e.clientX + 12, innerWidth - 350) + 'px'; tip.style.top = (e.clientY + 14) + 'px'; });
})();"""
    intro = ("<span class='mockbadge'>MOCK-UP</span><b>The Model page without bar charts</b> — the same data "
             "as the <a href='pillar-model.html'>Model page</a>, drawn as tiles, a shaded table, ranges and dots, "
             "for comparison. Nothing here replaces it. Covers every current framework (active, being updated "
             "or in development), as set out in its latest version. <b>Ad hoc allocations are not included</b>: "
             "they have no trigger.")
    meta = {"windows": len(wrows), "lead_drawn": n_lead, "lead_text": n_lead_txt, "rp_dots": n_rp,
            "history_source": how}
    _dash_page(page, "pillar-model-draft.html", "Model (mock-ups)", intro, panels, json.dumps(meta), js)
