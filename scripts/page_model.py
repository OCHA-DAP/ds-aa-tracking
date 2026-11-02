"""The Model page (pillar-model.html) — split out of dashboards.py on 2026-09-30
so the page can be reworked on its own. Shared helpers still live in dashboards.

What the page covers: the current (= latest recorded) version of every current framework
(active, being updated, in development); non-framework allocations have no trigger and are left
out. Trigger windows come from the framework records (aa.version_page.triggers, one row per window of the framework's "Trigger windows" table),
enriched with the older backtest windows (aa.window / aa.v_window_performance) where one
matches. Activations come from aa.window_activation + aa.window_status.

The page: the lead-time timelines per hazard, the trigger variables, and one sortable, filterable
table of the frameworks (owner, 2026-10-28) whose first columns are the Map's (landing.py: the
same status labels, monitoring months and return period), then the trigger sources, thresholds,
windows, activations and documents that the bar charts and the two tables below them showed."""

import functools
import html
import json
import re
import unicodedata

import landing
import pandas as pd
import site_i18n as i18n
from dashboards import (
    _dash_page,
    _gh_url,
    _loose,
    _words,
    haz,
    hazard_word,
)
from site_i18n import ATTR, ATTRC, TB, TBF, TD, TF, T

LIVE = ["active", "updating", "development"]
# the Map's status badges (landing.py .badge: green active, two-tone blue being updated, amber in
# development) and its order for sorting (LANDING_JS ST_ORDER)
BADGE = {"active": "endorsed", "updating": "updating", "development": "development"}
NOT_RECORDED = "window not recorded"
# a framework record's overall basis (trigger_facets.basis, _basis) in the frameworks table
BASIS_LABEL = {"forecast": "forecast", "observational": "observed", "mixed": "forecast and observed"}

# ------------------------------------------------ what the triggers measure (shown on the page)
# A trigger is assigned to every variable whose keyword appears in its text (whole words,
# case- and accent-insensitive; 'seas5' matches 'SEAS5-MAM-precip', 'kt' matches '64kt').
MEASURE = [
    ("rainfall", ["rainfall", "rain", "precipitation", "precip", "SPI", "SEAS5", "CHIRPS", "IMERG",
                  "tercile", "ENACTS", "IRI", "Maproom", "INSIVUMEH"]),
    ("wind speed & track", ["wind", "windspeed", "kt", "cyclone", "hurricane", "storm", "track",
                            "landfall", "distance to coast"]),
    ("river flow & level", ["GloFAS", "discharge", "water level", "river", "gauge", "FFWC", "ABN",
                            "DHM"]),
    ("vegetation", ["NDVI", "biomass", "biomasse", "ASAP", "VHI", "ASI", "fAPAR", "vegetation",
                    "WRSI"]),
    ("soil moisture & snow", ["soil moisture", "snow"]),
    ("food-security projections", ["IPC", "cadre harmonisé", "food", "FSNAU", "FEWSNET",
                                   "FEWS NET"]),
    ("disease cases", ["cases", "cholera", "AWD", "surveillance", "IDSR", "PNECHOL"]),
    ("flood extent", ["FloodScan", "flood extent", "flooded area"]),
    ("temperature & heat", ["temperature", "heat", "heatwave", "Tmax"]),
]
UNCLASSIFIED, NO_TRIGGER = "unclassified", "no trigger recorded yet"

# data / model providers: aliases folded before counting (regex on the lower-cased name)
PROVIDER_ALIAS = [
    (r"^seas5", "SEAS5 (ECMWF)"), (r"^era5", "ERA5 / ERA5-Land (ECMWF)"),
    (r"^ecmwf", "ECMWF forecasts"), (r"^glofas", "GloFAS"), (r"^imerg", "IMERG (NASA)"),
    (r"^chirps", "CHIRPS / CHIRPS-GEFS"), (r"^asap", "ASAP (JRC)"),
    (r"^(fao-)?asi$", "ASI (FAO)"), (r"^(fao-)?vhi$", "VHI (FAO)"),
    (r"(^|-)iri(-|$)", "IRI seasonal forecast / Maproom"), (r"^floodscan", "FloodScan"),
    (r"^worldpop", "WorldPop"), (r"^em-?dat", "EM-DAT"), (r"^rsmc-la-r", "RSMC La Réunion"),
    (r"^fewsnet", "FEWS NET"), (r"^enacts", "ENACTS"), (r"^leap", "LEAP / WRSI"),
    (r"awd", "WHO AWD surveillance"), (r"^fms", "Fiji Meteorological Service"),
    (r"^m.t.o-madagascar", "Météo-Madagascar"), (r"^river-gauge-dgre", "DGRE river gauges"),
    (r"^abn", "ABN river gauges (Niger Basin Authority)"), (r"^conasur", "CONASUR alerts"),
    (r"^biomasse-acf", "Biomasse (ACF)"), (r"^ds-storms", "CHD storms pipeline"),
]

_GENERIC = {"window", "windows", "trigger", "stage", "scenario", "path", "de", "la", "le", "des",
            "du", "or", "ou", "et"}
_CODE = re.compile(r"^w[a-z]?\d*$")          # coded backtest window names: wt1, wg2, ws


def _esc(s):
    return html.escape(_nofire(s))


def _tri(build, cut=None):
    """i18n.TC() with the display vocabulary (never 'fired') applied in every language."""
    return i18n.TC(lambda w: _nofire(build(w)), cut)


def _fw(f):
    """A framework's name ('Niger — drought') in every language: the country's exonym, the hazard."""
    hz = hazard_word(f["hazard"])
    return T(i18n.add(f["name"], "{country} — {hazard}",
                      country=i18n.country(f["country_iso3"], f["country_name"]), hazard=hz))


def _nofire(s):
    """Display vocabulary: triggers are 'activated', never 'fired' (also inside source text)."""
    s = "" if s is None or (isinstance(s, float) and pd.isna(s)) else str(s)
    s = re.sub(r"\bfiring\b", "activating", s, flags=re.IGNORECASE)
    return re.sub(r"\bfire(d|s)?\b", lambda m: "activate" + (m.group(1) or ""), s, flags=re.IGNORECASE)


def _toks(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " " + " ".join(re.findall(r"[a-z]+|[0-9]+", s)) + " "


_KW = [(cat, [_toks(k) for k in kws]) for cat, kws in MEASURE]


def measures(text):
    t = _toks(text)
    return [cat for cat, kws in _KW if any(k in t for k in kws)]


def provider(name):
    n = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower().strip()
    return next((lab for rx, lab in PROVIDER_ALIAS if re.search(rx, n)), str(name).strip())


def _basis(b):
    b = str(b or "").lower()
    if "mixed" in b or ("forecast" in b and "obs" in b):
        return "mixed"
    return "forecast" if "forecast" in b else "observational" if "observ" in b else "not recorded"


def _stage(t):
    n = (str(t.get("window") or "") + " " + str(t.get("trigger") or "")).lower()
    if re.search(r"readiness|mobili[sz]ation|pre-activation", n):
        return "readiness"
    return "action" if re.search(r"\baction\b", n) else "other"


def _lead(t, w=lambda x: x):
    """The lead time as the record states it (w: the words around it, in one language)."""
    if t.get("lead time"):
        return t["lead time"]
    if t.get("lead time / months"):
        return w("{n} (months)").format(n=t["lead time / months"])
    if t.get("issued month"):
        return (w("issued {m}").format(m=t["issued month"])
                + (w(", valid {p}").format(p=t["valid period"]) if t.get("valid period") else ""))
    return ""


def _state(ad, w=lambda x: x):
    """'activated 2024-05, 2025-06 (partial)' / 'not activated' (w: one language's words)."""
    if not ad:
        return w("not activated")
    return w("activated {list}").format(list=", ".join(
        k + (" (" + w("partial") + ")" if _flag(ad[k]) is False else "") for k in sorted(ad)))


def _bt(p, w=lambda x: x):
    """The backtest in short: '3 in 40 yrs · 8%/yr' (w: one language's words)."""
    if p is None or not (pd.notna(p.n_activations) and pd.notna(p.analysis_years)):
        return ""
    out = w("{n} in {y} yrs").format(n=int(p.n_activations), y=int(p.analysis_years))
    return out + (w(" · {p}%/yr").format(p=f"{p.activation_prob * 100:.0f}") if pd.notna(p.activation_prob) else "")


def _rp_num(s):
    """'~1-in-6 year', 'RP5', '~3.0 yr', '8.7 yr (12%)' -> years; None when not stated plainly."""
    s = str(s or "")
    m = (re.search(r"1-in-(\d+(?:\.\d+)?)", s) or re.search(r"\bRP\s?(\d+(?:\.\d+)?)", s)
         or re.match(r"^\s*~?\s*(\d+(?:\.\d+)?)\s*(?:yr|year)", s))
    return float(m.group(1)) if m else None


def _jd(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return None
    return v


def _match(name, rows):
    """Indices of the framework-record trigger rows a recorded window name refers to: loose
    name match on window / trigger, else the best distinctive-word overlap; [] if none."""
    if not rows or _CODE.match(str(name).strip().lower()):
        return []
    hit = [i for i, t in enumerate(rows)
           if _loose(name, t.get("window")) or _loose(name, t.get("trigger"))]
    if hit:
        return hit
    wn = _words(name) - _GENERIC
    sc = [len(wn & (_words(" ".join(str(t.get(k) or "") for k in ("window", "trigger", "indicator")))
                    - _GENERIC)) for t in rows]
    best = max(sc, default=0)
    return [i for i, s in enumerate(sc) if s == best] if best else []


def _match_codes(names, rows):
    """Coded backtest windows (wt1, wt2 …) pair with the trigger rows by position, and only when
    the counts agree; returns {name: [row index]}."""
    codes = sorted(n for n in names if _CODE.match(str(n).strip().lower()))
    digits = [re.findall(r"\d+", c) for c in codes]
    if not codes or len(codes) != len(rows) or not all(digits):
        return {}
    return {c: [int(dg[0]) - 1] for c, dg in zip(codes, digits) if 0 < int(dg[0]) <= len(rows)}


@functools.lru_cache(maxsize=1)
def _window_state():
    """aa.window_status and aa.window_activation WITH their version (d carries window status only
    for aa.window rows and activations without version)."""
    try:
        import ocha_stratus as stratus
        e = stratus.get_engine(stage="dev")
        ws = pd.read_sql("""SELECT country_iso3, hazard, version::text AS version, window_name,
                                   triggered, triggered_on::text AS triggered_on
                            FROM aa.window_status""", e)
        wa = pd.read_sql("""SELECT country_iso3, hazard, version::text AS version, window_name,
                                   event_date::text AS event_date, full_activation
                            FROM aa.window_activation""", e)
        return ws, wa
    except Exception as exc:   # noqa: BLE001 — page still builds from d alone
        print(f"  model page: window status/activation by version unavailable ({exc.__class__.__name__})")
        return None, None


TL_COLS = ["country_iso3", "hazard", "version", "leg", "seq", "stage", "lead_from", "lead_to", "unit",
           "months", "season_start", "season_len", "label", "stated", "indicator", "threshold", "note"]


@functools.lru_cache(maxsize=1)
def _timeline_rows():
    """aa.trigger_timeline (hand-entered, one row per bar or set of month marks); empty when the
    snapshot predates the table — every framework then shows 'trigger windows not recorded yet'."""
    try:
        import ocha_stratus as stratus
        e = stratus.get_engine(stage="dev")
        if pd.read_sql("SELECT to_regclass('aa.trigger_timeline') AS r", e)["r"].iloc[0] is None:
            print("  model page: aa.trigger_timeline is not in the snapshot yet (run the nightly with --ensure-schema)")
            return pd.DataFrame(columns=TL_COLS)
        return pd.read_sql(f"SELECT {', '.join(TL_COLS)} FROM aa.trigger_timeline", e)
    except Exception as exc:   # noqa: BLE001 — the page still builds, with no timelines
        print(f"  model page: trigger timelines unavailable ({exc.__class__.__name__})")
        return pd.DataFrame(columns=TL_COLS)


@functools.lru_cache(maxsize=1)
def _rp_frames():
    """The overall return period per version, both figures (landing.RP_SQL: the backtest's and
    the one the document states), so the frameworks table shows the Map's; empty when unavailable."""
    cols, out = ["country_iso3", "hazard", "version", "rp"], {}
    for k, sql in landing.RP_SQL.items():   # one at a time, as landing's _try: a missing table costs only its figure
        try:
            import ocha_stratus as stratus
            out[k] = pd.read_sql(sql, stratus.get_engine(stage="dev"))
        except Exception as exc:   # noqa: BLE001 — that figure then shows '—'
            print(f"  model page: {k} return periods unavailable ({exc.__class__.__name__})")
            out[k] = pd.DataFrame(columns=cols)
    return out


# one panel per hazard, each on its own clock: (hazard, title, unit, axis from, to, step); a bar
# beyond the axis widens it. Drought marks are months placed against the season start: a month
# within the season, or within `to` months of its start, counts after it, any other before it
# (TL_JS draws them the same way, _season_offset), and a longer season widens the axis.
TL_PANELS = [("storm", "Tropical cyclones", "h", -168, 72, 24),
             ("flood", "Floods", "d", -30, 5, 5),
             ("drought", "Drought", "mo", -7, 5, 1)]


def _num(v):
    return None if v is None or pd.isna(v) else float(v)


def _int(v):
    return None if v is None or pd.isna(v) else int(v)


def _leg_order(kv):
    """Legs in the order of their first row (season start, then name, on a tie)."""
    leg, g = kv
    return (g["seq"].min(), _int(g["season_start"].min()) or 0, str(leg))


def _season_offset(m, start, length, after):
    """A checked month's offset from the season start: in the season (or within `after` months
    of its start) it comes after the start, otherwise it leads the season."""
    o = (m - start) % 12
    return o if o < max(length or 0, after) else o - 12


def _first(g, col):
    return _int(g[col].dropna().iloc[0]) if g[col].notna().any() else None


def timelines(fws, rows=None):
    """The trigger-timeline panels: per hazard, each current framework (its latest version) with its
    legs (a river, a season) and their rows; frameworks with rows first, then those without.
    Returns ({hazard: panel data for the page script}, {hazard: [(framework, note)]})."""
    rows = _timeline_rows() if rows is None else rows
    rows = rows.assign(version=rows["version"].astype(str))
    panels, notes = {}, {}
    for h, title, unit, lo, hi, step in TL_PANELS:
        out, after = [], hi
        for f in (f for f in fws if haz(f["hazard"]) == h):
            r = rows[(rows["country_iso3"] == f["country_iso3"]) & (rows["hazard"] == f["hazard"])
                     & (rows["version"] == f["version"])]
            off = r[r["unit"] != unit]
            if len(off):
                print(f"  model page: {f['name']} v{f['version']}: {len(off)} timeline row(s) in "
                      f"{sorted(off['unit'].unique())}, not {unit} — left out")
            r = r[r["unit"] == unit]
            legs = []
            for leg, g in sorted(r.groupby("leg"), key=_leg_order):
                g = g.sort_values("seq")
                legs.append({"leg": str(leg), "start": _first(g, "season_start"), "len": _first(g, "season_len"),
                             "wins": [{"st": w.stage, "a": _num(w.lead_from), "b": _num(w.lead_to),
                                       "m": sorted({int(x) for x in w.months}) if isinstance(w.months, (list, tuple)) else None,
                                       "lab": _nofire(w.label), "stated": _nofire(w.stated),
                                       "ind": _nofire(w.indicator), "thr": _nofire(w.threshold)}
                                      for w in g.itertuples()]})
                if unit != "mo":
                    lo = min(lo, step * (float(g["lead_from"].astype(float).min()) // step))
                    hi = max(hi, -step * (-float(g["lead_to"].astype(float).max()) // step))
                elif legs[-1]["start"]:
                    lg = legs[-1]
                    offs = [_season_offset(m, lg["start"], lg["len"], after)
                            for w in lg["wins"] for m in (w["m"] or [])]
                    lo, hi = min([lo, *offs]), max([hi, lg["len"] or 0, *(o + 1 for o in offs)])
            for nt in dict.fromkeys(_nofire(x).strip() for x in r.sort_values("seq")["note"] if _nofire(x).strip()):
                notes.setdefault(h, []).append((f, nt))
            out.append({"name": i18n.country(f["country_iso3"], f["country_name"]), "status": f["lifecycle"],
                        "legs": legs or [{"leg": "", "start": None, "len": None, "wins": []}]})
        out.sort(key=lambda x: (not any(lg["wins"] for lg in x["legs"]), x["name"]["en"]))
        if out:
            panels[h] = {"key": h, "title": title, "unit": unit, "min": lo, "max": hi, "step": step,
                         "after": after, "fws": out}
    return panels, notes


def _frameworks(d):
    """One row per current framework: current version + its framework record (frontmatter, triggers)."""
    cur = d["current"]
    live = cur[cur["lifecycle"].isin(LIVE)].copy()
    live["version"] = live["latest_version"].astype(str)
    fvm = d.get("fv_meta", pd.DataFrame(columns=["country_iso3", "hazard", "version", "kb_framework",
                                                  "valid_from", "analysis_ref", "doc_url"]))
    fvm = fvm.assign(version=fvm["version"].astype(str))
    vp = d.get("vpage", pd.DataFrame(columns=["kb_framework", "version", "frontmatter", "triggers"]))
    vpd = {(r.kb_framework, str(r.version)): r for r in vp.itertuples()}
    rows = []
    for r in live.itertuples():
        m = fvm[(fvm["country_iso3"] == r.country_iso3) & (fvm["hazard"] == r.hazard)]
        mv = m[m["version"] == r.version]
        kb = (mv["kb_framework"].dropna().iloc[0] if mv["kb_framework"].notna().any()
              else r.kb_framework if isinstance(r.kb_framework, str) else None)
        page = vpd.get((kb, r.version))
        fm = (_jd(page.frontmatter) or {}) if page is not None else {}
        trig = [t for t in ((_jd(page.triggers) or []) if page is not None else []) if isinstance(t, dict)]
        # model documentation: this version's analysis ref, else the latest earlier one
        m = m.assign(_vf=pd.to_datetime(m["valid_from"], errors="coerce")).sort_values("_vf")
        refs = m[m["analysis_ref"].notna()]
        ref = refs[refs["version"] == r.version]
        ref = ref if len(ref) else refs.tail(1)
        rows.append(dict(
            country_iso3=r.country_iso3, hazard=r.hazard, lifecycle=r.lifecycle, version=r.version,
            version_status=r.latest_status, name=f"{r.country_name} — {hazard_word(r.hazard)}",
            country_name=r.country_name, kb=kb, fm=fm, trig=trig,
            doc_url=(mv["doc_url"].dropna().iloc[0] if mv["doc_url"].notna().any() else None),
            ref=(ref["analysis_ref"].iloc[0] if len(ref) else None),
            ref_version=(ref["version"].iloc[0] if len(ref) else None)))
    return sorted(rows, key=lambda f: (f["country_name"], f["hazard"]))


def _life(lc):
    """A status as the Map's badge (landing.KB_LABEL; LANDING_JS badge())."""
    return f"<span class='badge b-{BADGE.get(lc, 'development')}'>{T(landing.KB_LABEL.get(lc, lc))}</span>"


# ------------------------------------------------ the frameworks table's cells
_SAME = {"same", "same as above", "idem"}   # a timeline row that repeats the row before it


def _attr_l(name, vals):
    """An attribute in every language from values already in each ({'en', 'fr', 'es'}): the
    shape ATTR() writes, which the language switch swaps."""
    v = {l: html.escape(str(x), quote=True) for l, x in vals.items()}
    return f'{name}="{v["en"]}" ' + " ".join(f'data-{name}-{l}="{x}"' for l, x in v.items())


def _mstrip(months):
    """The monitoring months as the Map's strip (LANDING_JS monthStrip: month initials, the
    months monitored filled), named in words for a screen reader and on hover."""
    months = [m for m in months if 1 <= m <= 12]
    if not months:
        return "<span class='muted'>—</span>"
    langs = ("en",) + i18n.LANGS
    ini = {l: (i18n.tr(l, "JFMAMJJASOND") if l != "en" else "JFMAMJJASOND") for l in langs}
    names = {"en": MONTHS_EN, **{l: i18n.MONTH_ABBR[l][1:] for l in i18n.LANGS}}
    say = {l: (i18n.tr(l, "Monitored: {0}") if l != "en" else "Monitored: {0}").format(
               ", ".join(names[l][m - 1] for m in months)) for l in langs}
    cells = "".join(f"<span class='mm{' on' if m in months else ''}'>{T(*(ini[l][m - 1] for l in langs))}</span>"
                    for m in range(1, 13))
    return f"<span class='mstrip' role='img' {_attr_l('aria-label', say)} {_attr_l('title', say)}>{cells}</span>"


def _thresholds(f, tl):
    """The framework's trigger thresholds in short, [(label html, text)], one per trigger window:
    the hand-entered timeline rows (indicator: threshold), else the framework record's windows.
    The label tells the rows apart: the leg and the stage where the framework has several, else
    the row's own label; a record window's name."""
    def join(ind, thr):
        return f"{ind}: {thr}" if ind and thr else ind or thr
    r = tl[(tl["country_iso3"] == f["country_iso3"]) & (tl["hazard"] == f["hazard"])
           & (tl["version"] == f["version"])].sort_values("seq")
    out, prev = [], ""
    legs = [_nofire(x).strip() for x in r["leg"]]
    many_legs, many_st = len(set(legs)) > 1, r["stage"].nunique() > 1
    for w, leg in zip(r.itertuples(), legs):
        ind = _nofire(w.indicator).strip()
        ind = prev if ind.lower() in _SAME else ind
        prev = ind
        lab = [x for x in (_esc(leg) if many_legs and leg else "",
                           T(w.stage) if many_st and w.stage in ("readiness", "action", "observational") else "") if x]
        if not lab and len(r) > 1:
            lab = [_esc(w.label)]
        out.append((" · ".join(lab), join(ind, _nofire(w.threshold).strip())))
    if not len(r):
        for t in f["trig"]:
            txt = join(_nofire(t.get("indicator")).strip(), _nofire(t.get("threshold")).strip()) \
                or _nofire(t.get("trigger")).strip()
            if txt:
                out.append((_esc(t.get("window") or ""), txt))
    return [x for x in dict.fromkeys(out) if x[1]]


def _thr_cell(lines, cut=70, show=2):
    """The thresholds, each cut at `cut` characters; when one is cut or there are more than
    `show`, the cell opens (a <details>) on the full text."""
    if not lines:
        return "<span class='muted'>—</span>"

    def ln(lab, txt, n=None):
        t = txt if n is None or len(txt) <= n else txt[:n].rstrip() + "…"
        tp = "<span class='tp'>" + lab + "</span> " if lab else ""
        return f"<span class='ln'>{tp}{html.escape(t)}</span>"
    full = "".join(ln(lab, t) for lab, t in lines)
    if len(lines) <= show and all(len(t) <= cut for _, t in lines):
        return full
    more = len(lines) - show
    short = "".join(ln(lab, t, cut) for lab, t in lines[:show])
    tg = TF("{n} more", n=more) if more > 0 else T("full text")
    return (f"<details class='thr'><summary><span class='sh'>{short}<span class='tg'>{tg}</span></span>"
            f"<span class='tg op'>{T('show less')}</span></summary>{full}</details>")


def _win_names(f, tl):
    """The trigger windows' names: the framework record's, else the timeline rows' labels (with
    the leg where there are several)."""
    names = [x for x in (_nofire(t.get("window") or t.get("trigger")).strip() for t in f["trig"]) if x]
    if names:
        return names
    r = tl[(tl["country_iso3"] == f["country_iso3"]) & (tl["hazard"] == f["hazard"])
           & (tl["version"] == f["version"])].sort_values("seq")
    legs = [_nofire(x).strip() for x in r["leg"]]
    many = len(set(legs)) > 1
    return [x for x in (" · ".join(y for y in (leg if many else "", _nofire(w.label).strip()) if y)
                        for w, leg in zip(r.itertuples(), legs)) if x]


def model_windows(d):
    """The current frameworks and their trigger-window rows, with what each window watches,
    its basis, lead time, return period and activations."""
    fws = _frameworks(d)
    ws, wa = _window_state()
    if ws is None:   # fallback: status joined to aa.window rows, activations without version
        ws = d["windows"][["country_iso3", "hazard", "version", "window_name", "triggered",
                           "triggered_on"]].astype({"triggered_on": str})
        wa = d.get("wact", pd.DataFrame(columns=["country_iso3", "hazard", "event_date",
                                                  "window_name", "full_activation"])).assign(version=None)
    ws = ws.assign(version=ws["version"].astype(str))
    wa = wa.assign(version=wa["version"].astype(str))
    w = d["windows"].copy()
    w["version"] = w["version"].astype(str)

    # ------------------------------------------------ window rows + per-framework facts
    win, unmatched, loose_acts, cat_fw, cat_win = [], [], [], {}, {}
    for f in fws:
        c, h, v, trig = f["country_iso3"], f["hazard"], f["version"], f["trig"]
        fm, tf = f["fm"], (f["fm"].get("trigger_facets") or {})
        f["basis"] = _basis(tf.get("basis")) if tf else "not recorded"
        # what the triggers measure: trigger indicators first, data sources only as fallback
        cats = set(measures(" ; ".join(map(str, tf.get("indicators") or []))))
        for t in trig:
            cats |= set(measures(" ".join(str(t.get(k) or "") for k in ("window", "trigger", "indicator"))))
        if not cats and fm.get("data_sources"):
            cats = set(measures(" ; ".join(map(str, fm["data_sources"]))))
        has_rec = bool(trig or tf.get("indicators"))
        f["cats"] = sorted(cats) if cats else [UNCLASSIFIED if has_rec else NO_TRIGGER]
        for k in f["cats"]:
            cat_fw.setdefault(k, []).append(f)
        # structure
        stages = {_stage(t) for t in trig}
        n = len(trig) or int(tf.get("n_windows") or 0)
        f["structure"] = ("not recorded" if n == 0 else "single window" if n == 1
                          else "staged: readiness → action" if {"readiness", "action"} <= stages
                          else "several, not staged")
        # geographic level
        scope = " ".join(map(str, fm.get("geographic_scope") or [])).lower()
        al = fm.get("admin_level")
        f["geo"] = ("river basin" if re.search(r"\bbasin|bassin", scope)
                    else "health zone" if re.search(r"health zone|zone de sant", scope)
                    else "not recorded" if al is None or str(al).strip() == ""
                    else "national (admin 0)" if str(al) == "0" else f"admin {al}")
        # backtest windows (aa.window) and status / activations on this version -> trigger rows
        bw = w[(w["country_iso3"] == c) & (w["hazard"] == h) & (w["version"] == v)]
        codes = _match_codes(bw["window_name"].tolist(), trig)
        perf = {}
        for b in bw.itertuples():
            idx = codes.get(b.window_name) or _match(b.window_name, trig)
            if not idx:
                unmatched.append(f"{f['name']}: {b.window_name}" + (
                    f" (1-in-{b.return_period:.1f} yr; {int(b.n_activations)} in {int(b.analysis_years)} yrs)"
                    if pd.notna(b.return_period) and pd.notna(b.n_activations)
                    and pd.notna(b.analysis_years) else ""))
            for i in idx:
                perf.setdefault(i, b)
        sv = ws[(ws["country_iso3"] == c) & (ws["hazard"] == h) & (ws["version"] == v)]
        scodes = _match_codes(sv["window_name"].tolist(), trig)
        acts = {}
        for s in sv[sv["triggered"].fillna(False).astype(bool)].itertuples():
            for i in scodes.get(s.window_name) or _match(s.window_name, trig):
                acts.setdefault(i, {})[str(s.triggered_on)[:7]] = None
        for a in wa[(wa["country_iso3"] == c) & (wa["hazard"] == h) & (wa["version"] == v)].itertuples():
            idx = [] if _unrec(a.window_name) else _match(a.window_name, trig)
            if not idx:
                loose_acts.append(f"{f['name']} {str(a.event_date)[:7]}"
                                  + (" (partial)" if _flag(a.full_activation) is False else ""))
            for i in idx:
                acts.setdefault(i, {})[str(a.event_date)[:7]] = a.full_activation
        for i, t in enumerate(trig):
            ind = t.get("indicator") or ""
            tcats = measures(" ".join(str(t.get(k) or "") for k in ("window", "trigger", "indicator"))) \
                or [UNCLASSIFIED]
            for k in tcats:
                cat_win.setdefault(k, []).append(f"{f['name']}: {t.get('window') or ''} — {ind}")
            p = perf.get(i)
            rp_txt = t.get("return period") or ""
            rp_bt = (p.return_period if p is not None and pd.notna(p.return_period) else None)
            ad = acts.get(i, {})
            # English strings (the draft page reads them) and their parts (the Model page
            # assembles them in every language: t, p, ad)
            win.append(dict(f=f, window=t.get("window") or t.get("trigger") or "", basis=_basis(t.get("basis")),
                            cats=tcats, indicator=ind, lead=_lead(t), rp_txt=rp_txt,
                            rp=rp_bt if rp_bt is not None else _rp_num(rp_txt),
                            rp_src="backtest" if rp_bt is not None else "stated",
                            bt=_bt(p), state=_state(ad), activated=bool(ad), t=t, p=p, ad=ad))
        if not trig:
            win.append(dict(f=f, window=None))
    return {"fws": fws, "win": win, "ws": ws, "wa": wa, "unmatched": unmatched,
            "loose_acts": loose_acts, "cat_fw": cat_fw, "cat_win": cat_win}


def build_model(page, d):
    m = model_windows(d)
    fws, ws, wa = m["fws"], m["ws"], m["wa"]
    cat_fw, cat_win = m["cat_fw"], m["cat_win"]

    # ------------------------------------------------ activation record per framework (all versions
    # of its current line: an earlier framework a distinct new one replaced — dashboards.old_versions,
    # Somalia drought 2019 / 2020-06-23 — activated as a retired framework, not as this one)
    old = d.get("old") or set()
    for f in fws:
        c, h = f["country_iso3"], f["hazard"]
        a = wa[(wa["country_iso3"] == c) & (wa["hazard"] == h)]
        a = a.loc[[(c, h, str(v)) not in old for v in a["version"]]]
        s = ws[(ws["country_iso3"] == c) & (ws["hazard"] == h) & ws["triggered"].fillna(False).astype(bool)]
        s = s.loc[[(c, h, str(v)) not in old for v in s["version"]]]
        s = s[~s["version"].isin(a["version"])]      # status-only activations (none expected)
        f["acts"] = [(str(r.event_date)[:7], r.window_name, r.full_activation, r.version)
                     for r in a.sort_values("event_date").itertuples()]
        f["acts"] += [(str(r.triggered_on)[:7], r.window_name, None, r.version) for r in s.itertuples()]
        full = [x for x in f["acts"] if _flag(x[2]) is True]
        f["record"] = ("activated fully (at least once)" if full
                       else "activated partially only" if any(_flag(x[2]) is False for x in f["acts"])
                       else "activated (extent not recorded)" if f["acts"] else "never activated")

    # ------------------------------------------------ trigger variables: the frameworks with a trigger
    # recorded (one with none — NO_TRIGGER, which the draft page still counts — has no row)
    cat_order = [c for c, _ in MEASURE if c in cat_fw]
    cat_order.sort(key=lambda c: -len(cat_fw[c]))
    cat_order += [c for c in (UNCLASSIFIED,) if c in cat_fw]
    n_cat = len({(f["country_iso3"], f["hazard"]) for k in cat_order for f in cat_fw[k]})

    def fw_list(fl):
        return ", ".join(_fw(f) for f in fl)

    cat_rows = "".join(
        f"<tr><td>{T(k)}</td><td class='num'>{len(cat_fw[k])}</td>"
        f"<td class='num'>{len(cat_win.get(k, [])) or ''}</td><td class='small'>{fw_list(cat_fw[k])}</td></tr>"
        for k in cat_order)
    map_rows = "".join(f"<tr><td>{T(c)}</td><td class='small'>{_esc(', '.join(k))}</td></tr>"
                       for c, k in MEASURE)
    uncl = cat_win.get(UNCLASSIFIED, [])
    uncl_html = ("<p class='small'>" + TBF("<b>Windows no keyword matched</b> (counted as unclassified): {list}",
                                         list="; ".join(_esc(u) for u in uncl)) + "</p>") if uncl else ""
    cat_note = (TBF("A framework counts under every variable its triggers use, so the counts add up to more than {n}.",
                    n=n_cat) if sum(len(cat_fw[k]) for k in cat_order) > n_cat else "")
    assign_note = TB(
        "Each trigger window's indicator, window and trigger text (and the framework's list of trigger "
        "indicators) is matched against the keywords below — whole words, ignoring case and accents. A window "
        "can match several variables. The framework's data sources are used only when its trigger text matches "
        "nothing (they list validation data too, e.g. FloodScan for a river-gauge trigger). \"Unclassified\" = "
        "trigger recorded but no keyword matched.")

    # ------------------------------------------------ the frameworks table: one row per current
    # framework. Its first columns are the Map's (landing.py, the table under the map): the same
    # labels, months (landing.monitoring_months) and return period (landing.rp_of, _rp_fields)
    rpf, tl = _rp_frames(), _timeline_rows()
    tl = tl.assign(version=tl["version"].astype(str))

    def act_cell(f):
        rec = T(f["record"])
        if not f["acts"]:
            return f"<span class='rec muted'>{rec}</span>"
        out = []
        for dte, wn, full, ver in f["acts"]:
            wlab = f"<i>{T(NOT_RECORDED)}</i>" if _unrec(wn) else _esc(wn)
            ext = {False: f" ({T('partial')})", None: f" ({T('extent not recorded')})"}.get(_flag(full), "")
            out.append(f"<span class='ln'><b>{_esc(dte)}</b> {wlab}{ext} <span class='muted'>v{_esc(ver)}</span></span>")
        return f"<span class='rec'>{rec}</span>" + "".join(out)

    def doc_cell(f):
        links = []
        if f["doc_url"]:
            links.append(f"<a href='{html.escape(f['doc_url'], quote=True)}'>{T('framework document')}</a>")
        if f["fm"].get("model_report"):
            links.append(f"<a href='{html.escape(f['fm']['model_report'], quote=True)}'>{T('model report')}</a>")
        for s in (f["fm"].get("surfaces") or [])[:4]:
            if isinstance(s, dict) and s.get("url"):
                links.append(f"<a href='{html.escape(s['url'], quote=True)}' "
                             f"title='{html.escape(_nofire(s.get('title') or ''), quote=True)}'>"
                             f"{TD(_nofire(s.get('kind') or 'link'))}</a>")
        return " · ".join(links)

    def code_cell(f):
        links = []
        u = _gh_url(f["ref"]) if f["ref"] else None
        if u:   # the repository as the link, the path in its title (a long path squeezed the column)
            repo, path = str(f["ref"]).split("@")[0], str(f["ref"]).split(":", 1)[-1]
            note = "" if f["ref_version"] == f["version"] else f" <span class='muted'>{TF('(for v{v})', v=f['ref_version'])}</span>"
            links.append(f"<a class='cd' href='{html.escape(u, quote=True)}' title='{_esc(repo + ':' + path)}'>{_esc(repo)}</a>{note}")
        for repo in dict.fromkeys(re.findall(r"ocha-dap/([\w.\-]+)", str(f["fm"].get("source_repo") or ""),
                                             flags=re.IGNORECASE)):
            if not (u and repo in u):
                links.append(f"<a class='cd' href='https://github.com/OCHA-DAP/{repo}'>{_esc(repo)}</a>")
        return "<br>".join(links)

    def rp_cell(rp):
        if rp["rp"] is None:
            return "<span class='muted'>—</span>"

        def tip(w):   # LANDING_JS rpTitle(): both figures behind the one shown
            out = []
            for k, lab in (("rp_bt", "historical simulation: {0}"), ("rp_st", "stated in the framework: {0}")):
                if rp[k] is not None:
                    out.append(w(lab).format(w("1-in-{0} yr").format(landing._tofixed(rp[k], 1))))
            return " · ".join(out)
        return f"<span {ATTRC('title', tip)}>{TF('1-in-{n} yr', n=landing._tofixed(rp['rp'], 1))}</span>"

    rows, gaps = [], {"sources": [], "thresholds": [], "windows": []}
    for f in fws:
        c, h, v = f["country_iso3"], f["hazard"], f["version"]
        months, _ = landing.monitoring_months(f["fm"], d["calendar"], c, h)
        rp = landing._rp_fields(landing.rp_of(rpf["backtest"], c, h, v), landing.rp_of(rpf["stated"], c, h, v))
        ds = f["fm"].get("data_sources") or []
        srcs = list(dict.fromkeys(provider(x) for x in ([ds] if isinstance(ds, str) else ds) if str(x).strip()))
        bl = BASIS_LABEL.get(f["basis"])
        src = ((f"<span class='bs'>{T(bl)}</span>" if bl else "")
               + (f"<span class='ln'>{_esc(', '.join(srcs))}</span>" if srcs else ""))
        thr = _thresholds(f, tl)
        names = [x for x in _win_names(f, tl) if x]
        nw = (f["fm"].get("trigger_facets") or {}).get("n_windows")
        n_win = len(names) or (nw if isinstance(nw, int) else 0)
        win = f"<b>{n_win}</b>" + "".join(f"<span class='ln'>{_esc(x)}</span>" for x in names)
        docs = "<br>".join(x for x in (doc_cell(f), code_cell(f)) if x)
        for k, have in (("sources", srcs), ("thresholds", thr), ("windows", n_win)):
            if not have:
                gaps[k].append(f["name"])
        dash = "<span class='muted'>—</span>"
        name = T(*i18n.country(c, f["country_name"]).values())
        rows.append(
            f"<tr data-life='{f['lifecycle']}'>"
            f"<td data-k='country' class='nw'><a href='fw-{c.lower()}-{h}.html'>{name}</a></td>"
            f"<td data-k='hazard'>{T(landing._haz_label(h))}</td>"
            f"<td data-k='status' data-v='{LIVE.index(f['lifecycle'])}'>{_life(f['lifecycle'])}</td>"
            f"<td class='nq nw'>{_mstrip(months)}</td>"
            f"<td data-k='rp' data-v='{'' if rp['rp'] is None else rp['rp']}' class='num nw'>{rp_cell(rp)}</td>"
            f"<td>{src or dash}</td><td class='thc'>{_thr_cell(thr)}</td>"
            f"<td data-k='windows' data-v='{n_win or ''}'>{win if n_win else dash}</td>"
            f"<td data-k='acts' data-v='{len(f['acts'])}'>{act_cell(f)}</td>"
            f"<td class='dc'>{docs or dash}</td></tr>")
    for k, names in gaps.items():
        if names:
            print(f"  model page: no {k} recorded for {len(names)} framework(s): {', '.join(names)}")

    # the headings: the sortable ones a button each (LANDING_JS fwSort's columns; Monitoring and the
    # text columns are not sorted); FWM_JS keeps aria-sort and the arrow on the sorted one
    cols = [("country", "Country"), ("hazard", "Hazard"), ("status", "Status"), (None, "Monitoring"),
            ("rp", "Return period"), (None, "Trigger sources"), (None, "Basic thresholds"),
            ("windows", "Windows"), ("acts", "Activations"), (None, "Documents & code")]

    def th(k, lab):
        if not k:
            return f"<th>{T(lab)}</th>"
        on = k == "country"                     # the rows come sorted by country, as FWM_JS starts
        sort = " aria-sort='ascending'" if on else ""
        cls = " class='num'" if k == "rp" else ""
        return (f"<th data-k='{k}'{sort}{cls}><button type='button'>{T(lab)}"
                f"<span class='ar' aria-hidden='true'>{'▲' if on else ''}</span></button></th>")
    head = "".join(th(k, lab) for k, lab in cols)
    n_life = {lc: sum(f["lifecycle"] == lc for f in fws) for lc in LIVE}
    life_boxes = "".join(f"<label><input type='checkbox' value='{lc}' checked> {_life(lc)} ({n_life[lc]})</label>"
                         for lc in LIVE if n_life[lc])
    unrec = any(_unrec(x[1]) for f in fws for x in f["acts"])
    fw_notes = "".join(f"<p class='note2'>{x}</p>" for x in [
        TB("<b>Return period</b>: as stated in the framework document, else from the historical simulation "
           "(hover over it for both)."),
        TB("<b>Trigger sources</b>: whether the triggers use forecast or observed data, or both (windows of both "
           "kinds, or one window that combines the two), then the data and models the framework record lists."),
        f"<b>{T('Activations')}</b>: " + TB("Any version of the framework. Partially = only part of the allocation "
                                            "or only the readiness window was released.")
        + (f" <i>{T(NOT_RECORDED)}</i> {T('= the activation is on record but which window activated is not — a curation item.')}"
           if unrec else "")])

    tl_data, tl_notes = timelines(fws)
    data = {"tl": {"panels": [tl_data[h] for h, *_ in TL_PANELS if h in tl_data],
                   "mon": {"en": MONTHS_EN, **{l: i18n.MONTH_ABBR[l][1:] for l in i18n.LANGS}}}}
    tl_html = _timeline_html(fws, tl_data, tl_notes)

    panels = f"""
<style>
td.small, .small {{ font-size:11.5px; }} .muted {{ color:#666; }} .nw {{ white-space:nowrap; }}
details.map {{ margin-top:8px; font-size:12px; }} details.map summary {{ cursor:pointer; color:#1d5aa8; }}
details.map table.data {{ margin:6px 0; }}
p.note2 {{ font-size:12px; color:#555; margin:6px 0; }}
{FWM_CSS}
{TL_CSS}
</style>
<h2>{T("Trigger design per hazard")}</h2>
{tl_html}
<section><h2>{T("Trigger variables")}</h2>
 <div class='scroll'><table class='data'><thead><tr><th>{T('variable')}</th><th>{T('frameworks')}</th><th>{T('windows')}</th><th>{T('frameworks')}</th></tr></thead><tbody>{cat_rows}</tbody></table></div>
 {f"<p class='note2'>{cat_note}</p>" if cat_note else ""}
 <details class='map'><summary>{T("How a trigger is assigned to a variable")}</summary>
 <p>{assign_note}</p>
 <table class='data'><thead><tr><th>{T('variable')}</th><th>{T('keywords')}</th></tr></thead><tbody>{map_rows}</tbody></table>
 {uncl_html}</details></section>
<section><h2>{T("Frameworks and their triggers")}</h2>
 <div class='lfbar' id='fwmst'><input class='filter' id='fwmq' type='search' {ATTR("placeholder", "filter frameworks…")} {ATTR("aria-label", "Filter the frameworks")}>{life_boxes}<span id='fwmn' class='fwmn' aria-live='polite'></span></div>
 <div class='scroll'><table class='data fwm' id='fwm'><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>
 {fw_notes}</section>"""
    _dash_page(page, "pillar-model.html", "Model",
               TB("<b>The model block of anticipatory action</b> — the triggers: what they measure, "
                  "where and when they are monitored, on what basis, how often they are designed to "
                  "activate, and what has activated. Covers every current framework (active, being "
                  "updated or in development), as set out in its latest version. <b>Non-framework allocations "
                  "are not included</b>: they have no trigger."),
               panels, json.dumps(data, default=str).replace("</", "<\\/"), TL_JS + FWM_JS)   # free text: never close the script


MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _tl_head(h, title):
    """A hazard's heading: a button that opens and closes its panel, all open at first (TL_JS)."""
    return (f"<h3><button type='button' class='tl-tog' aria-expanded='true' aria-controls='tl-b-{h}'>"
            f"{T(title)}</button></h3>")


def _timeline_html(fws, panels, notes):
    """The 'How much warning' section: legend, one panel per hazard (drawn by TL_JS from the page
    data), the frameworks' own notes under each, and cholera in words (no lead time to draw)."""
    clocks = {"storm": T("hours before (−) / after (+) landfall or closest approach"),
              "flood": T("days before (−) / after (+) the flood peak"),
              "drought": (f"<span data-cal='0'>{T('months before (−) / after (+) the start of the rainy season')}</span>"
                          f"<span data-cal='1' hidden>{T('calendar months, January to December')}</span>")}
    general = {"drought": TB(
        "On the season view, rows are aligned on the start of the rainy season each trigger protects, so a "
        "Sahel Jul–Sep season and an Ethiopian Mar–May season line up at 0; the calendar view puts every mark "
        "at its own month. The shaded band is the season itself. Each mark is a month in which the trigger is "
        "checked (a forecast issue, or the month an observation is read); where a framework allows either of "
        "two issues, both months are marked. Labels use the frameworks’ own window numbers where the "
        "documents number them; the hover gives each window’s description.")}
    out = []
    for h, *_ in TL_PANELS:
        if h not in panels:
            continue
        seg = ""
        if h == "drought":
            seg = (f"<div class='tl-seg' role='group' {ATTR('aria-label', 'Drought axis')}>"
                   f"<button type='button' data-cal='0' aria-pressed='true'>{T('Aligned on the season')}</button>"
                   f"<button type='button' data-cal='1' aria-pressed='false'>{T('Calendar, Jan–Dec')}</button></div>")
        fw_notes = "".join(
            f"<div class='note'><b>{T(*i18n.country(f['country_iso3'], f['country_name']).values())}</b>: "
            f"{html.escape(nt)}</div>" for f, nt in notes.get(h, []))
        gen = f"<div class='note'>{general[h]}</div>" if h in general else ""
        out.append(f"<section class='panel tl-panel' id='tl-{h}'><div class='tl-ph'>{_tl_head(h, panels[h]['title'])}"
                   f"<span class='tl-clock'>{clocks[h]}</span>{seg}</div>"
                   f"<div class='tl-b' id='tl-b-{h}'><div class='tl-x' data-tl='{h}'></div>{fw_notes}{gen}</div></section>")
    chol = [f for f in fws if haz(f["hazard"]) == "cholera"]
    if chol:
        names = ", ".join(T(*i18n.country(f["country_iso3"], f["country_name"]).values()) for f in chol)
        out.append(f"<section class='panel tl-panel' id='tl-cholera'><div class='tl-ph'>{_tl_head('cholera', 'Cholera')}"
                   f"<span class='tl-clock'>{T('no forecast lead time')}</span></div>"
                   f"<div class='tl-b' id='tl-b-cholera'><div class='note'>"
                   + TBF("{list}: the triggers use weekly surveillance data — a framework activates when reported "
                         "cases cross the agreed thresholds, so there is no forecast lead time to draw.", list=names)
                   + "</div></div></section>")
    legend = "".join(f"<span><i class='tl-sw' style='background:var(--s-{k})'></i>{T(s)}</span>"
                     for k, s in (("ready", "readiness"), ("action", "action"), ("obs", "observational")))
    legend += f"<span><i class='tl-sw tl-ev'></i>{T('the event (landfall, flood peak, season start)')}</span>"
    return ("<p class='meta'>" + TB(
        "One panel per hazard, each on its own clock: hours before landfall for tropical cyclones, days before "
        "the flood peak for floods, months from the start of the rainy season for drought. Each row is one "
        "trigger window of a current framework (its latest version): the bar shows when the trigger can "
        "activate, and for drought each mark is a month in which the trigger is checked. Hover a bar for the "
        "trigger as the framework document states it. The ranges are read from each framework document by "
        "hand.") + f"</p><div class='tlx'><div class='tl-legend'>{legend}</div>{''.join(out)}</div>")


# the stage colours (validated categorical set) and the Map's status chips (landing.py .badge:
# green active, two-tone blue being updated, amber in development). The site has no dark theme.
TL_CSS = """
.tlx { --s-ready:#2a78d6; --s-action:#eb6834; --s-obs:#1baf7a; --tl-season:#e6eef6; --tl-season-ink:#3d5a78;
       --tl-ink:#1a1a1a; --tl-muted:#666; --tl-faint:#8a929d; --tl-line:#e0e0e0; --tl-grid:#eef1f3; }
.tl-legend { display:flex; flex-wrap:wrap; gap:6px 16px; font-size:12.5px; color:#555; margin:8px 0 4px; }
.tl-legend > span { display:inline-flex; align-items:center; gap:6px; }
.tl-sw { width:18px; height:10px; border-radius:2px; display:inline-block; }
.tl-sw.tl-ev { width:2px; height:14px; background:var(--tl-ink); border-radius:0; }
.tl-panel { margin:12px 0; }
.tl-ph { display:flex; flex-wrap:wrap; justify-content:space-between; gap:4px 16px; align-items:baseline;
         max-width:1150px; }   /* the plot's own width */
.tl-panel .tl-ph h3 { margin:2px 0 4px; font-size:18px; }   /* over DASH_CSS .panel h3, written after */
/* the heading opens and closes the panel (owner, 2026-10-28): a chevron, pointing down when open */
.tl-tog { font:inherit; font-weight:700; color:inherit; background:none; border:0; padding:2px 4px 2px 0;
          cursor:pointer; display:inline-flex; align-items:center; gap:10px; text-align:left; }
.tl-tog::before { content:''; width:7px; height:7px; border-right:2px solid currentColor; border-bottom:2px solid currentColor;
                  transform:translateY(-2px) rotate(45deg); }
.tl-tog[aria-expanded="false"]::before { transform:rotate(-45deg); }
.tl-tog:hover { color:#1d5aa8; }
.tl-tog:focus-visible { outline:2px solid var(--s-ready); outline-offset:2px; border-radius:3px; }
.tl-panel.shut .tl-clock, .tl-panel.shut .tl-seg { display:none; }   /* they belong to the closed chart */
.tl-clock { font-size:12px; color:var(--tl-muted); }
.tl-seg { display:inline-flex; border:1px solid #c9d3de; border-radius:6px; overflow:hidden; background:#fff; }
.tl-seg button { font:inherit; font-size:12.5px; border:0; background:transparent; color:var(--tl-ink);
                 padding:4px 10px; cursor:pointer; }
.tl-seg button[aria-pressed="true"] { background:#1f2a44; color:#fff; font-weight:600; }
.tl-seg button:focus-visible { outline:2px solid var(--s-ready); outline-offset:-2px; }
.tl-x { overflow-x:auto; margin-top:6px; }
svg.tl { display:block; width:100%; min-width:680px; max-width:1150px; height:auto; }
svg.tl text { fill:var(--tl-ink); font-family:inherit; }
svg.tl .muted { fill:var(--tl-muted); } svg.tl .faint { fill:var(--tl-faint); }
svg.tl text.lab { paint-order:stroke; stroke:#fff; stroke-width:3px; stroke-linejoin:round; }   /* readable across the event line */
svg.tl g[tabindex]:focus { outline:none; } svg.tl g[tabindex]:focus-visible rect.hit { stroke:var(--s-ready); stroke-width:1.5; }
svg.tl .st-active rect { fill:#e2f3e6; } svg.tl .st-active text { fill:#1e7a37; }
svg.tl .st-dev rect { fill:#fdf0d5; } svg.tl .st-dev text { fill:#9a6d0a; }
svg.tl .st-upd rect { stroke:#9ecae1; } svg.tl .st-upd text { fill:#1a5fa0; }
.tl-tip { position:fixed; z-index:30; pointer-events:none; max-width:340px; background:#1f2a44; color:#fff;
          font-size:12.5px; line-height:1.35; border-radius:6px; padding:8px 10px; box-shadow:0 6px 20px rgba(0,0,0,.18); }
.tl-tip b { display:block; margin-bottom:2px; } .tl-tip .k { opacity:.7; }
"""

# The panels, drawn from D.tl (one SVG per hazard; again on a language switch). Ported from the
# reviewed mock-up: rows grouped by framework (name + status chip, legs beneath), bars from
# lead_from to lead_to, drought rows as one mark per month checked, aligned on the season start
# or on the calendar. Labels sit beside the bars in text ink, never on them.
TL_JS = r"""
(function(){
  // a hazard's heading opens and closes its panel (all open at first); a chart is drawn again on
  // opening, as text measured while hidden has no width
  let onToggle = () => {};
  document.querySelectorAll('.tl-tog').forEach(b => b.addEventListener('click', () => {
    const open = b.getAttribute('aria-expanded') !== 'true', sec = b.closest('.tl-panel');
    b.setAttribute('aria-expanded', String(open)); sec.classList.toggle('shut', !open);
    document.getElementById(b.getAttribute('aria-controls')).hidden = !open;
    onToggle(sec, open);
  }));
  const TL = window.D && D.tl; if (!TL || !TL.panels.length) return;
  const NS = 'http://www.w3.org/2000/svg';
  const mk = (t, a, txt) => { const e = document.createElementNS(NS, t); for (const k in (a || {})) e.setAttribute(k, a[k]);
    if (txt != null) e.textContent = txt; return e; };
  const escH = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const COL = {readiness:'var(--s-ready)', action:'var(--s-action)', observational:'var(--s-obs)'};
  const stageName = s => s === 'readiness' ? tr8('readiness') : s === 'action' ? tr8('action') : tr8('observational');
  const CHIP = {active:'st-active', updating:'st-upd', development:'st-dev'};
  const statusName = s => s === 'active' ? tr8('Active') : s === 'updating' ? tr8('Being updated') : tr8('In development');
  const evName = k => k === 'storm' ? tr8('landfall') : k === 'flood' ? tr8('flood peak') : tr8('season starts');
  const sgn = t => t > 0 ? '+' + t : t < 0 ? '−' + (-t) : '0';
  const tick = (u, t) => u === 'h' ? tr8('{0} h', sgn(t)) : u === 'd' ? tr8('{0} d', sgn(t)) : sgn(t);
  const nm = n => n[aaLang()] || n.en;
  // as page_model._season_offset: in the season (or within `after` months of its start) after it, else before
  const seasonOffset = (m, start, len, after) => { const o = ((m - start) % 12 + 12) % 12; return o < Math.max(len || 0, after) ? o : o - 12; };
  const mon = m => (TL.mon[aaLang()] || TL.mon.en)[m - 1];
  const tip = document.createElement('div'); tip.className = 'tl-tip'; tip.hidden = true; document.body.appendChild(tip);
  function moveTip(ev){ const w = tip.offsetWidth, h = tip.offsetHeight; let x = ev.clientX + 14, y = ev.clientY + 14;
    if (x + w > innerWidth - 8) x = Math.max(8, ev.clientX - w - 14); if (y + h > innerHeight - 8) y = Math.max(8, ev.clientY - h - 14);
    tip.style.left = x + 'px'; tip.style.top = y + 'px'; }
  function showTip(ev, html){ tip.innerHTML = html; tip.hidden = false; moveTip(ev); }
  function chip(svg, status, cx, cy, gid){
    const g = mk('g', {class: CHIP[status] || ''}), lab = statusName(status);
    const r = mk('rect', {x: cx, y: cy, height: 15, rx: 7.5}), t = mk('text', {y: cy + 11, 'font-size': 10.5, 'font-weight': 600, 'text-anchor': 'middle'}, lab);
    if (status === 'updating') r.setAttribute('fill', `url(#${gid})`);
    g.append(r, t); svg.appendChild(g);
    const w = (t.getComputedTextLength() || lab.length * 6.1) + 14;
    r.setAttribute('width', w); t.setAttribute('x', cx + w / 2);
  }
  function draw(p, host, cal){
    const W = 1000, L = 230, R = 18, rowH = 17, headH = 18, gH = 8, top = 28;   // compact rows (owner, 2026-10-28)
    const min = cal ? 0 : p.min, max = cal ? 12 : p.max, ticks = [];
    for (let t = min; t <= max; t += cal ? 1 : p.step) ticks.push(t);
    let n = 0; p.fws.forEach(f => f.legs.forEach(l => { n += Math.max(1, l.wins.length); }));
    const H = top + p.fws.length * (headH + gH) + n * rowH + 26;
    const x = v => L + (v - min) / (max - min) * (W - L - R);
    const svg = mk('svg', {viewBox: `0 0 ${W} ${H}`, class: 'tl', role: 'group',
                           'aria-label': tr8('{0}: trigger windows by framework', tr8(p.title))});
    host.replaceChildren(svg);
    const gid = 'tl-upd-' + p.key, gr = mk('linearGradient', {id: gid, x1: 0, y1: 0, x2: 1, y2: 1});
    [['0', '#dbeafe'], ['0.5', '#dbeafe'], ['0.5', '#eef4fa'], ['1', '#eef4fa']].forEach(([o, c]) => gr.appendChild(mk('stop', {offset: o, 'stop-color': c})));
    const defs = mk('defs'); defs.appendChild(gr); svg.appendChild(defs);
    // grid + axis labels (month names between the gridlines on the calendar view)
    ticks.forEach(t => { svg.appendChild(mk('line', {x1: x(t), x2: x(t), y1: top - 6, y2: H - 22, stroke: 'var(--tl-grid)', 'stroke-width': 1}));
      if (cal) { if (t < 12) svg.appendChild(mk('text', {x: (x(t) + x(t + 1)) / 2, y: top - 12, 'text-anchor': 'middle', 'font-size': 11, class: 'muted'}, mon(t + 1))); }
      else svg.appendChild(mk('text', {x: x(t), y: top - 12, 'text-anchor': 'middle', 'font-size': 11, class: 'muted'}, tick(p.unit, t))); });
    const nGrid = svg.children.length;   // season bands go straight after the grid, under everything else
    const bands = [];
    let y = top;
    p.fws.forEach(f => {
      const name = nm(f.name), hd = mk('text', {x: 0, y: y + 13, 'font-size': 13.5, 'font-weight': 600}, name);
      svg.appendChild(hd);
      chip(svg, f.status, (hd.getComputedTextLength() || name.length * 7.4) + 10, y + 2, gid);
      y += headH;
      f.legs.forEach(leg => {
        const k = Math.max(1, leg.wins.length), y0 = y;
        if (leg.len && leg.start) bands.push([y0, y0 + k * rowH, leg.len, leg.start]);
        if (leg.leg) svg.appendChild(mk('text', {x: 12, y: y0 + 12, 'font-size': 12, class: 'muted'}, leg.leg));
        if (!leg.wins.length) svg.appendChild(mk('text', {x: x(min) + 6, y: y0 + 12, 'font-size': 12, class: 'faint'}, tr8('trigger windows not recorded yet')));
        leg.wins.forEach((w, i) => {
          const yy = y0 + i * rowH + 2.5, full = name + (leg.leg ? ' · ' + leg.leg : ''), st = stageName(w.st);
          const g = mk('g', {tabindex: 0, 'aria-label': `${full}: ${st}, ${w.lab}`});
          svg.appendChild(g);
          let x0, x1;
          if (w.m) {          // one mark per month checked: at its offset from the season start, or at its own month
            const offs = w.m.map(m => [m, cal ? m - 1 : seasonOffset(m, leg.start || 1, leg.len, p.after)]);
            x0 = Math.min(...offs.map(([, o]) => x(o))); x1 = Math.max(...offs.map(([, o]) => x(o + 1)));
            g.appendChild(mk('rect', {class: 'hit', x: x0 - 3, y: yy - 2.5, width: x1 - x0 + 6, height: rowH, fill: 'transparent'}));
            offs.forEach(([m, o]) => {
              g.appendChild(mk('rect', {x: x(o) + 1.5, y: yy, width: x(o + 1) - x(o) - 3, height: 12, rx: 3, fill: COL[w.st]}));
              g.appendChild(mk('text', {x: (x(o) + x(o + 1)) / 2, y: yy + 9.5, 'font-size': 10, 'text-anchor': 'middle', style: 'fill:#10151c;font-weight:600'}, mon(m)));
            });
          } else {
            x0 = x(w.a); x1 = Math.max(x(w.b), x0 + 4);
            g.appendChild(mk('rect', {class: 'hit', x: x0 - 3, y: yy - 2.5, width: x1 - x0 + 6, height: rowH, fill: 'transparent'}));   // larger hit target
            g.appendChild(mk('rect', {x: x0, y: yy, width: x1 - x0, height: 12, rx: 3, fill: COL[w.st]}));
          }
          // the label in text ink beside the bar; left of it when the right side would run out of the chart
          const lt = mk('text', {class: 'lab', x: x1 + 6, y: yy + 10, 'font-size': 11}, w.lab);
          g.appendChild(lt);
          if (x1 + 6 + (lt.getComputedTextLength() || w.lab.length * 6.2) > W) { lt.setAttribute('x', x0 - 6); lt.setAttribute('text-anchor', 'end'); }
          const row = (key, v) => v ? `<br><span class="k">${escH(key)}</span> ${escH(v)}` : '';
          const html = `<b>${escH(full)} · ${escH(st)}</b>${escH(w.lab)}` + row(tr8('As stated:'), w.stated)
                     + row(tr8('Indicator:'), w.ind) + row(tr8('Threshold:'), w.thr);
          g.addEventListener('mouseenter', e => showTip(e, html)); g.addEventListener('mousemove', moveTip);
          g.addEventListener('mouseleave', () => { tip.hidden = true; });
          g.addEventListener('focus', () => { const r = g.getBoundingClientRect(); showTip({clientX: r.right, clientY: r.top}, html); });
          g.addEventListener('blur', () => { tip.hidden = true; });
        });
        y += k * rowH;
      });
      y += gH;
      svg.appendChild(mk('line', {x1: 0, x2: W, y1: y - gH / 2, y2: y - gH / 2, stroke: 'var(--tl-line)', 'stroke-width': 1}));
    });
    // season bands (drought): from the season start on the aligned view, over the season's own months on the calendar
    let under = nGrid;
    bands.forEach(([a, b, len, start]) => {
      const spans = !cal ? [[0, Math.min(len, max)]]
        : (start - 1 + len <= 12 ? [[start - 1, start - 1 + len]] : [[start - 1, 12], [0, start - 1 + len - 12]]);
      spans.forEach(([s0, s1]) => { svg.insertBefore(mk('rect', {x: x(s0), y: a + 1, width: x(s1) - x(s0), height: b - a - 2, fill: 'var(--tl-season)', rx: 2}), svg.children[nGrid]); under++; });
    });
    if (bands.length) {   // name the band once, above the first one
      const [a, , , start] = bands[0], s0 = cal ? start - 1 : 0;
      svg.appendChild(mk('text', {x: x(s0) + 4, y: a - 4, 'font-size': 10.5, style: 'fill:var(--tl-season-ink);font-style:italic'}, tr8('rainy season')));
    }
    if (!cal) {
      // the event line over the bands, under the bars and their labels
      svg.insertBefore(mk('line', {x1: x(0), x2: x(0), y1: top - 6, y2: H - 22, stroke: 'var(--tl-ink)', 'stroke-width': 2}), svg.children[under]);
      svg.appendChild(mk('text', {x: x(0), y: H - 6, 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 600}, evName(p.key)));
    }
  }
  let droughtCal = false;
  function drawAll(){
    tip.hidden = true;
    TL.panels.forEach(p => { const host = document.querySelector(`.tl-x[data-tl="${p.key}"]`);
      if (host) draw(p, host, p.key === 'drought' && droughtCal); });
  }
  const dsec = document.getElementById('tl-drought');
  if (dsec) dsec.querySelectorAll('.tl-seg button').forEach(b => b.addEventListener('click', () => {
    droughtCal = b.dataset.cal === '1';
    dsec.querySelectorAll('.tl-seg button').forEach(o => o.setAttribute('aria-pressed', String(o === b)));
    dsec.querySelectorAll('.tl-clock [data-cal]').forEach(s => { s.hidden = (s.dataset.cal === '1') !== droughtCal; });
    const p = TL.panels.find(q => q.key === 'drought');
    draw(p, dsec.querySelector('.tl-x'), droughtCal);
  }));
  onToggle = (sec, open) => { tip.hidden = true;
    const p = open && TL.panels.find(q => 'tl-' + q.key === sec.id);
    if (p) draw(p, sec.querySelector('.tl-x'), p.key === 'drought' && droughtCal); };
  drawAll();
  document.addEventListener('aalang', drawAll);
})();
"""

# The frameworks table (the Map's first columns, then the triggers): a heading's button sorts it,
# with the Map's rules (LANDING_JS fwSort: names, status and return period ascending at the first
# click, counts descending; a row without the figure last either way; ties by country, then
# hazard; names compared in the language shown, again on a switch), and the text box and the
# status boxes filter it. The months strip is left out of the text search (its initials would
# match 'jas' everywhere).
FWM_CSS = """
table.fwm { min-width:1180px; font-size:12px; }
table.fwm th { vertical-align:bottom; z-index:1; }
table.fwm th button { font:inherit; font-weight:700; color:inherit; background:none; border:0; padding:0;
                      cursor:pointer; text-align:inherit; }
table.fwm th button:hover { color:#1d5aa8; }
table.fwm th button:focus-visible { outline:2px solid #1d5aa8; outline-offset:2px; border-radius:2px; }
table.fwm th .ar { color:#5b6472; font-size:10px; margin-left:3px; }
table.fwm td { line-height:1.35; }
table.fwm td.num { text-align:right; }
table.fwm .ln, table.fwm .bs, table.fwm .rec { display:block; }
table.fwm .ln + .ln { margin-top:2px; }
table.fwm .bs { font-weight:600; }
table.fwm .bs::first-letter, table.fwm .rec::first-letter { text-transform:uppercase; }
table.fwm .tp { color:#555; font-weight:600; }
table.fwm td a { overflow-wrap:anywhere; }
table.fwm td.dc { line-height:24px; }   /* links a line apart: 24 px targets (WCAG 2.5.8) */
table.fwm td.dc a { white-space:nowrap; } table.fwm td.dc a.cd { white-space:normal; }   /* a repository name may break */
table.fwm td.thc { min-width:220px; }
/* the Map's status badges and months strip (landing.py: .badge, .b-*, table.fwtab .mm) */
.fwm .badge, .lfbar .badge { padding:1px 7px; border-radius:9px; font-size:11px; font-weight:600; margin:0;
                             white-space:nowrap; }
.b-endorsed { background:#e2f3e6; color:#1e7a37; } .b-development { background:#fdf0d5; color:#8a5c0a; }
.b-updating { background:linear-gradient(135deg,#dbeafe 0 50%,#eef4fa 50% 100%); color:#1a5fa0; border:1px solid #9ecae1; }
.fwm .mstrip { display:inline-flex; gap:1px; }
.fwm .mm { display:inline-grid; place-items:center; width:14px; height:15px; font-size:8.5px; border-radius:3px;
           background:#f0f2f5; color:#5b6472; }
.fwm .mm.on { background:#2171b5; color:#fff; }
/* a long threshold: cut, the cell opens on the full text */
details.thr > summary { cursor:pointer; list-style:none; }
details.thr > summary::-webkit-details-marker { display:none; }
details.thr .tg { display:block; color:#1d5aa8; margin-top:2px; }
details.thr > summary:hover .tg { text-decoration:underline; }
details.thr > summary:focus-visible { outline:2px solid #1d5aa8; outline-offset:2px; border-radius:2px; }
details.thr[open] > summary .sh, details.thr:not([open]) > summary .op { display:none; }
.lfbar { display:flex; gap:8px 14px; flex-wrap:wrap; align-items:center; margin:10px 0; font-size:12.5px; }
.lfbar input.filter { margin:0; max-width:100%; }
.lfbar label { display:inline-flex; align-items:center; gap:5px; cursor:pointer; }
.fwmn { color:#555; font-size:12px; }
"""

FWM_JS = r"""
(function(){
  const tab = document.getElementById('fwm'); if (!tab) return;
  const tb = tab.tBodies[0], rows = [...tb.rows], S = {k: 'country', dir: 1};
  const UP = ['country', 'hazard', 'status', 'rp'];
  const cell = (r, k) => r.querySelector(`td[data-k='${k}']`), txt = (r, k) => cell(r, k).textContent.trim();
  const val = (r, k) => { const v = cell(r, k).dataset.v; return v === undefined ? txt(r, k) : v === '' ? null : +v; };
  const cmpT = (a, b, k) => txt(a, k).localeCompare(txt(b, k), aaLang());
  function sort(){
    const {k, dir} = S;
    rows.sort((a, b) => { const x = val(a, k), y = val(b, k);
      const c = typeof x === 'string' ? dir * x.localeCompare(y, aaLang())
              : x == null || y == null ? (x == null) - (y == null) : dir * (x - y);
      return c || cmpT(a, b, 'country') || cmpT(a, b, 'hazard'); });
    tb.append(...rows);
    tab.querySelectorAll('th[data-k]').forEach(th => { const on = th.dataset.k === k;
      if (on) th.setAttribute('aria-sort', dir > 0 ? 'ascending' : 'descending'); else th.removeAttribute('aria-sort');
      th.querySelector('.ar').textContent = on ? (dir > 0 ? '▲' : '▼') : ''; });
  }
  tab.querySelectorAll('th[data-k] button').forEach(b => b.addEventListener('click', () => {
    const k = b.parentNode.dataset.k;
    S.dir = S.k === k ? -S.dir : (UP.includes(k) ? 1 : -1); S.k = k; sort(); }));
  const q = document.getElementById('fwmq'), shown = document.getElementById('fwmn');
  const boxes = [...document.querySelectorAll('#fwmst input[type=checkbox]')];
  const hay = r => [...r.cells].map(c => c.classList.contains('nq') ? '' : c.textContent).join(' ').toLowerCase();
  function filter(){
    const s = q.value.trim().toLowerCase(), on = new Set(boxes.filter(b => b.checked).map(b => b.value));
    let n = 0;
    rows.forEach(r => { const show = on.has(r.dataset.life) && (!s || hay(r).includes(s)); r.hidden = !show; n += show; });
    shown.textContent = tr8('{0} of {1} frameworks shown', n, rows.length);
  }
  q.addEventListener('input', filter); boxes.forEach(b => b.addEventListener('change', filter));
  document.addEventListener('aalang', () => { sort(); filter(); });
  sort(); filter();
})();
"""


def _flag(v):
    """full_activation as True / False / None (numpy bools and NaN / NA included)."""
    return None if v is None or v is pd.NA or (isinstance(v, float) and pd.isna(v)) else bool(v)


def _unrec(name):
    """'unspecified' / 'unknown — …' window names: the activation is recorded, its window is not."""
    n = str(name or "").strip().lower()
    return n in ("", "none", "nan", "unspecified") or n.startswith("unknown")
