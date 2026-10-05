"""The Model page (pillar-model.html) — split out of dashboards.py on 2026-09-30
so the page can be reworked on its own. Shared helpers still live in dashboards.

What the page covers: the current (= latest recorded) version of every current framework
(active, being updated, in development); ad hoc allocations have no trigger and are left
out. Trigger windows come from the framework records (aa.version_page.triggers, one row per window of the framework's "Trigger windows" table),
enriched with the older backtest windows (aa.window / aa.v_window_performance) where one
matches. Activations come from aa.window_activation + aa.window_status."""

import functools
import html
import json
import re
import unicodedata

import pandas as pd
from dashboards import (
    LIFE_LABEL,
    _cal_strip,
    _dash_page,
    _gh_url,
    _loose,
    _records,
    _words,
    haz,
)

LIVE = ["active", "updating", "development"]
LIFE_COLOR = {"active": "#2171b5", "updating": "#6baed6", "development": "#a9cce3"}   # the map's blues
NOT_RECORDED = "window not recorded"

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


def _lead(t):
    if t.get("lead time"):
        return t["lead time"]
    if t.get("lead time / months"):
        return f"{t['lead time / months']} (months)"
    if t.get("issued month"):
        return f"issued {t['issued month']}" + (f", valid {t['valid period']}" if t.get("valid period") else "")
    return ""


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
            version_status=r.latest_status, name=f"{r.country_name} — {r.hazard.replace('_', ' ')}",
            country_name=r.country_name, kb=kb, fm=fm, trig=trig,
            doc_url=(mv["doc_url"].dropna().iloc[0] if mv["doc_url"].notna().any() else None),
            ref=(ref["analysis_ref"].iloc[0] if len(ref) else None),
            ref_version=(ref["version"].iloc[0] if len(ref) else None)))
    return sorted(rows, key=lambda f: (f["country_name"], f["hazard"]))


def _life(lc):
    return f"<span class='lf lf-{lc}'>{LIFE_LABEL.get(lc, lc)}</span>"


def model_windows(d):
    """The current frameworks and their trigger-window rows, with what each window watches,
    its basis, lead time, return period and activations (also used by page_model_draft)."""
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
            bt = ""
            if p is not None and pd.notna(p.n_activations) and pd.notna(p.analysis_years):
                bt = f"{int(p.n_activations)} in {int(p.analysis_years)} yrs"
                if pd.notna(p.activation_prob):
                    bt += f" · {p.activation_prob * 100:.0f}%/yr"
            ad = acts.get(i, {})
            state = ("activated " + ", ".join(k + (" (partial)" if _flag(ad[k]) is False else "") for k in sorted(ad))
                     if ad else "not activated")
            win.append(dict(f=f, window=t.get("window") or t.get("trigger") or "", basis=_basis(t.get("basis")),
                            cats=tcats, indicator=ind, lead=_lead(t), rp_txt=rp_txt,
                            rp=rp_bt if rp_bt is not None else _rp_num(rp_txt),
                            rp_src="backtest" if rp_bt is not None else "stated",
                            bt=bt, state=state, activated=bool(ad)))
        if not trig:
            win.append(dict(f=f, window=None))
    return {"fws": fws, "win": win, "ws": ws, "wa": wa, "unmatched": unmatched,
            "loose_acts": loose_acts, "cat_fw": cat_fw, "cat_win": cat_win}


def build_model(page, d):
    m = model_windows(d)
    fws, win, ws, wa = m["fws"], m["win"], m["ws"], m["wa"]
    unmatched, loose_acts, cat_fw, cat_win = m["unmatched"], m["loose_acts"], m["cat_fw"], m["cat_win"]
    wrows = [x for x in win if x["window"] is not None]
    no_trig = [f for f in fws if not f["trig"]]
    n_life = {lc: sum(f["lifecycle"] == lc for f in fws) for lc in LIVE}

    # ------------------------------------------------ activation record per framework (all versions)
    for f in fws:
        a = wa[(wa["country_iso3"] == f["country_iso3"]) & (wa["hazard"] == f["hazard"])]
        s = ws[(ws["country_iso3"] == f["country_iso3"]) & (ws["hazard"] == f["hazard"])
               & ws["triggered"].fillna(False).astype(bool)]
        s = s[~s["version"].isin(a["version"])]      # status-only activations (none expected)
        f["acts"] = [(str(r.event_date)[:7], r.window_name, r.full_activation, r.version)
                     for r in a.sort_values("event_date").itertuples()]
        f["acts"] += [(str(r.triggered_on)[:7], r.window_name, None, r.version) for r in s.itertuples()]
        full = [x for x in f["acts"] if _flag(x[2]) is True]
        f["record"] = ("activated fully (at least once)" if full
                       else "activated partially only" if any(_flag(x[2]) is False for x in f["acts"])
                       else "activated (extent not recorded)" if f["acts"] else "never activated")
    records = ["activated fully (at least once)", "activated partially only",
               "activated (extent not recorded)", "never activated"]
    records = [r for r in records if any(f["record"] == r for f in fws)]

    # ------------------------------------------------ providers (counted by framework)
    prov = {}
    for f in fws:
        for p in {provider(x) for x in (f["fm"].get("data_sources") or [])}:
            prov.setdefault(p, []).append(f["name"])
    prov_multi = sorted([(p, n) for p, n in prov.items() if len(n) > 1], key=lambda x: (-len(x[1]), x[0]))
    prov_single = sorted(p for p, n in prov.items() if len(n) == 1)
    n_with_src = sum(bool(f["fm"].get("data_sources")) for f in fws)

    # ------------------------------------------------ chart data
    def by_life(keys, keyf):
        return {"labels": keys, "sets": [{"label": LIFE_LABEL[lc], "color": LIFE_COLOR[lc],
                                          "data": [sum(1 for f in fws if f["lifecycle"] == lc and keyf(f, k))
                                                   for k in keys]} for lc in LIVE]}
    cat_order = [c for c, _ in MEASURE if c in cat_fw]
    cat_order.sort(key=lambda c: -len(cat_fw[c]))
    cat_order += [c for c in (UNCLASSIFIED, NO_TRIGGER) if c in cat_fw]
    hz = [h for h in ["drought", "flood", "storm", "cholera", "other"] if any(haz(f["hazard"]) == h for f in fws)]
    bases = ["forecast", "observational", "mixed", "not recorded"]
    n_wb = {}
    for x in wrows:
        k = (haz(x["f"]["hazard"]), x["basis"])
        n_wb[k] = n_wb.get(k, 0) + 1
    w_bases = [b for b in bases if any(k[1] == b for k in n_wb)]
    n_wmix = sum(n for (_, b), n in n_wb.items() if b == "mixed")
    n_fwb = {b: sum(f["basis"] == b for f in fws) for b in bases}
    mix_note = (f" Mixed = a single window that combines forecast and observed data "
                f"({n_wmix} window{'s' if n_wmix != 1 else ''})."
                if n_wmix else "")
    structs = ["single window", "staged: readiness → action",
               "several, not staged", "not recorded"]
    structs = [s for s in structs if any(f["structure"] == s for f in fws)]
    geos = sorted({f["geo"] for f in fws}, key=lambda g: (g == "not recorded", g))
    act = d["act_all"].copy()
    act["year"] = act["event_date"].astype(str).str[:4]
    act = act[act["year"].str.match(r"^\d{4}$")].copy()
    act["year"] = act["year"].astype(int)
    act["kind"] = act["event_type"].map(
        lambda t: "framework triggers" if t == "framework_aa" else "ad hoc allocations")
    data = {
        "cat": by_life(cat_order, lambda f, k: k in f["cats"]),
        # trigger WINDOWS of the current versions (the windows table's rows), not frameworks:
        # most frameworks mix forecast and observational windows, which a framework count hides
        "basis": {"labels": hz, "sets": [{"label": b, "data": [n_wb.get((h, b), 0) for h in hz]}
                                         for b in w_bases]},
        "struct": by_life(structs, lambda f, k: f["structure"] == k),
        "geo": by_life(geos, lambda f, k: f["geo"] == k),
        "rec": by_life(records, lambda f, k: f["record"] == k),
        "prov": {"labels": [p for p, _ in prov_multi], "data": [len(n) for _, n in prov_multi]},
        "rp": [x["rp"] for x in wrows if x["rp"] is not None],
        "act": json.loads(_records(
            act.drop_duplicates(["country_iso3", "hazard", "event_date", "event_type"]), ["year", "kind"])),
    }

    # ------------------------------------------------ HTML pieces
    def fw_list(fl):
        return ", ".join(_esc(f["name"]) for f in fl)

    cat_rows = "".join(
        f"<tr><td>{_esc(k)}</td><td class='num'>{len(cat_fw[k])}</td>"
        f"<td class='num'>{len(cat_win.get(k, [])) or ''}</td><td class='small'>{fw_list(cat_fw[k])}</td></tr>"
        for k in cat_order)
    map_rows = "".join(f"<tr><td>{_esc(c)}</td><td class='small'>{_esc(', '.join(k))}</td></tr>"
                       for c, k in MEASURE)
    uncl = cat_win.get(UNCLASSIFIED, [])
    uncl_html = ("<p class='small'><b>Windows no keyword matched</b> (counted as unclassified): "
                 + "; ".join(_esc(u) for u in uncl) + "</p>") if uncl else ""
    alias_rows = "".join(f"<tr><td><code>{_esc(rx)}</code></td><td>{_esc(lab)}</td></tr>"
                         for rx, lab in PROVIDER_ALIAS)

    def _state_cell(x):
        return (f"<span class='act'>{_esc(x['state'])}</span>" if x["activated"]
                else f"<span class='muted'>{_esc(x['state'])}</span>")

    def _trunc(s, n):
        s = _nofire(s)
        return (f"<span title='{html.escape(s, quote=True)}'>{html.escape(s[:n].rstrip())}…</span>"
                if len(s) > n else html.escape(s))

    def _ver(f):
        tag = " <span class='muted'>(draft)</span>" if f["version_status"] == "development" else ""
        return f"{_esc(f['version'])}{tag}"

    tr = []
    for x in win:
        f = x["f"]
        head = (f"<tr data-life='{f['lifecycle']}'><td>{_esc(f['name'])}</td><td>{_life(f['lifecycle'])}</td>"
                f"<td class='nw'>{_ver(f)}</td>")
        if x["window"] is None:
            tr.append(head + "<td colspan='8' class='muted'>no structured trigger recorded yet for this "
                             "version</td></tr>")
            continue
        rp = _trunc(x["rp_txt"], 60) if x["rp_txt"] else (f"1-in-{x['rp']:.1f} yr" if x["rp"] else "")
        tr.append(head + f"<td>{_esc(x['window'])}</td><td>{_esc(x['basis'])}</td>"
                  f"<td class='small'>{_esc(', '.join(x['cats']))}</td><td class='small'>{_trunc(x['indicator'], 110)}</td>"
                  f"<td class='small'>{_trunc(x['lead'], 70)}</td><td class='small'>{rp}</td>"
                  f"<td class='small nw'>{_esc(x['bt'])}</td><td class='small'>{_state_cell(x)}</td></tr>")
    life_boxes = "".join(
        f"<label><input type='checkbox' value='{lc}' checked onchange='mfilt()'> "
        f"<span class='sw' style='background:{LIFE_COLOR[lc]}'></span>{LIFE_LABEL[lc]} ({n_life[lc]})</label>"
        for lc in LIVE)
    no_trig_html = ", ".join(f"{_esc(f['name'])} ({_esc(f['version'])})" for f in no_trig)
    loose_html = ("<p class='note2'><b>Activations on current versions with the window not recorded:</b> "
                  + "; ".join(_esc(a) for a in loose_acts)
                  + ". These are curation items: the activation is on record, which window activated is "
                    "not.</p>") if loose_acts else ""
    unm_html = ("<p class='note2'>Backtest windows that do not map one-to-one onto a window of the framework "
                "record (not in the table or the return-period chart): "
                + "; ".join(_esc(u) for u in unmatched) + ".</p>") if unmatched else ""

    def act_cell(f):
        if not f["acts"]:
            return "<span class='muted'>—</span>"
        out = []
        for dte, wn, full, ver in f["acts"]:
            wlab = f"<i>{NOT_RECORDED}</i>" if _unrec(wn) else _esc(wn)
            ext = {False: " (partial)", None: " (extent not recorded)"}.get(_flag(full), "")
            out.append(f"<b>{_esc(dte)}</b> {wlab}{ext} <span class='muted'>v{_esc(ver)}</span>")
        return "<br>".join(out)
    rec_rows = "".join(
        f"<tr data-life='{f['lifecycle']}'><td>{_esc(f['name'])}</td><td>{_life(f['lifecycle'])}</td>"
        f"<td>{_esc(f['record'])}</td><td class='small'>{act_cell(f)}</td></tr>" for f in fws)
    n_act = sum(f["record"] != "never activated" for f in fws)

    lead_panels = []
    for h in hz:
        items = []
        for f in (f for f in fws if haz(f["hazard"]) == h):
            lt = [(t.get("window") or t.get("trigger") or "", _lead(t)) for t in f["trig"]]
            lt = [(a, b) for a, b in lt if b]
            if lt:
                items.append(f"<li><b>{_esc(f['country_name'])}</b> — "
                             + "; ".join(f"{_esc(a)}: {_esc(b)}" for a, b in lt) + "</li>")
            elif f["trig"]:
                items.append(f"<li><b>{_esc(f['country_name'])}</b> — <span class='muted'>no lead time "
                             f"stated</span></li>")
        if items:
            lead_panels.append(f"<div class='panel'><h3>{h}</h3><ul class='lead'>{''.join(items)}</ul></div>")

    def doc_cell(f):
        links = []
        if f["doc_url"]:
            links.append(f"<a href='{html.escape(f['doc_url'], quote=True)}'>framework document</a>")
        if f["fm"].get("model_report"):
            links.append(f"<a href='{html.escape(f['fm']['model_report'], quote=True)}'>model report</a>")
        for s in (f["fm"].get("surfaces") or [])[:4]:
            if isinstance(s, dict) and s.get("url"):
                links.append(f"<a href='{html.escape(s['url'], quote=True)}' "
                             f"title='{html.escape(_nofire(s.get('title') or ''), quote=True)}'>"
                             f"{_esc(s.get('kind') or 'link')}</a>")
        return " · ".join(links) or "<span class='muted'>—</span>"

    def code_cell(f):
        links = []
        u = _gh_url(f["ref"]) if f["ref"] else None
        if u:
            lab = str(f["ref"]).split("@")[0] + ":" + str(f["ref"]).split(":", 1)[-1]
            note = "" if f["ref_version"] == f["version"] else f" <span class='muted'>(for v{_esc(f['ref_version'])})</span>"
            links.append(f"<a href='{html.escape(u, quote=True)}'>{_esc(lab)}</a>{note}")
        for repo in dict.fromkeys(re.findall(r"ocha-dap/([\w.\-]+)", str(f["fm"].get("source_repo") or ""),
                                             flags=re.IGNORECASE)):
            if not (u and repo in u):
                links.append(f"<a href='https://github.com/OCHA-DAP/{repo}'>{_esc(repo)}</a>")
        return "<br>".join(links) or "<span class='muted'>—</span>"
    doc_rows = "".join(
        f"<tr data-life='{f['lifecycle']}'><td>{_esc(f['name'])}</td><td>{_life(f['lifecycle'])}</td>"
        f"<td class='nw'>{_ver(f)}</td><td class='small'>{doc_cell(f)}</td><td class='small'>{code_cell(f)}</td></tr>"
        for f in fws)

    cal = d["calendar"]
    cal_rows = "".join(
        f"<tr><td>{_esc(f['name'])}</td><td>{_life(f['lifecycle'])}</td>"
        f"<td>{_cal_strip(cal, f['country_iso3'], f['hazard'])}</td></tr>" for f in fws)

    n_bt = sum(1 for x in wrows if x["rp_src"] == "backtest" and x["rp"] is not None)
    n_st = sum(1 for x in wrows if x["rp_src"] == "stated" and x["rp"] is not None)
    panels = f"""
<style>
.lf {{ display:inline-block; padding:0 8px; border-radius:9px; font-size:11px; font-weight:600; white-space:nowrap; }}
.lf-active {{ background:#dbe9f6; color:#17548a; }} .lf-updating {{ background:#e6f1f8; color:#2b6d99; }}
.lf-development {{ background:#fdf1dc; color:#8a5c0a; }}
td.small, .small {{ font-size:11.5px; }} .muted {{ color:#888; }} .nw {{ white-space:nowrap; }}
span.act {{ color:#b3261e; font-weight:600; }}
.lfbar {{ display:flex; gap:14px; flex-wrap:wrap; align-items:center; margin:10px 0; font-size:12.5px; }}
.lfbar .sw {{ display:inline-block; width:11px; height:11px; border-radius:2px; margin:0 4px 0 2px; vertical-align:-1px; }}
.lfbar input.filter {{ margin:0; }}
details.map {{ margin-top:8px; font-size:12px; }} details.map summary {{ cursor:pointer; color:#1d5aa8; }}
details.map table.data {{ margin:6px 0; }}
p.note2 {{ font-size:12px; color:#555; margin:6px 0; }}
.span2 {{ grid-column:span 2; }} @media (max-width:900px) {{ .span2 {{ grid-column:auto; }} }}
ul.lead {{ margin:0; padding-left:16px; }} ul.lead li {{ font-size:12.5px; margin:4px 0; }}
</style>
<div class='tiles'>
 <div class='tile'><div class='v'>{len(fws)}</div><div class='l'>current frameworks · {n_life['active']} active · {n_life['updating']} being updated · {n_life['development']} in development</div></div>
 <div class='tile'><div class='v'>{len(fws) - len(no_trig)}</div><div class='l'>with their trigger windows recorded (current version)</div></div>
 <div class='tile'><div class='v'>{len(wrows)}</div><div class='l'>trigger windows on the current versions</div></div>
 <div class='tile'><div class='v'>{n_act}</div><div class='l'>current frameworks activated at least once (any version)</div></div>
</div>
<h2>What do the triggers watch?</h2>
<div class='grid'>
 <div class='panel'><h3>Current frameworks, by what their triggers watch</h3><canvas id='m1' height='300'></canvas>
   <div class='note'>A framework counts once under every variable its triggers use (a cyclone framework
   with a wind window and a rainfall window counts under both), so the bars add up to more than {len(fws)}.</div></div>
 <div class='panel'><h3>Which frameworks, and how many windows</h3>
   <div class='scroll' style='max-height:360px'><table class='data'><thead><tr><th>variable</th><th>frameworks</th><th>windows</th><th>frameworks</th></tr></thead><tbody>{cat_rows}</tbody></table></div>
   <details class='map'><summary>How a trigger is assigned to a variable</summary>
   <p>Each trigger window's indicator, window and trigger text (and the framework's list of trigger
   indicators) is matched against the keywords below — whole words, ignoring case and accents. A window
   can match several variables. The framework's data sources are used only when its trigger text matches
   nothing (they list validation data too, e.g. FloodScan for a river-gauge trigger). "Unclassified" =
   trigger recorded but no keyword matched; "{NO_TRIGGER}" = no structured trigger on the current version.</p>
   <table class='data'><thead><tr><th>variable</th><th>keywords</th></tr></thead><tbody>{map_rows}</tbody></table>
   {uncl_html}</details></div>
</div>
<h2>How are the triggers built?</h2>
<div class='grid'>
 <div class='panel'><h3>Forecast or observed data? Trigger windows by hazard</h3><canvas id='m2' height='260'></canvas>
   <div class='note'>Counts the {len(wrows)} trigger windows of the current versions (the rows of the windows
   table below), by the basis each window records.{mix_note}
   Counted by framework instead, from each framework record's overall basis: {n_fwb['forecast']} forecast,
   {n_fwb['observational']} observational, {n_fwb['mixed']} mixed (forecast and observational windows),
   {n_fwb['not recorded']} not recorded. A framework count hides the observational windows inside the
   mixed frameworks, so the chart counts windows.</div></div>
 <div class='panel'><h3>One window or several?</h3><canvas id='m3' height='260'></canvas>
   <div class='note'>Staged = a readiness window followed by an action window on the same event.
   Several, not staged = windows split by season, lead time, area or data source.</div></div>
 <div class='panel'><h3>At what geographic level?</h3><canvas id='m4' height='260'></canvas>
   <div class='note'>Administrative level at which the trigger is evaluated, from the framework record
   (admin 4 = union level in Bangladesh).</div></div>
 <div class='panel'><h3>How often would each trigger activate?</h3><canvas id='m5' height='260'></canvas>
   <div class='note'>Designed return period of each window, 1-in-N years. From the backtest where one is recorded ({n_bt} windows), otherwise the
   return period the framework states ({n_st} windows); ranges and qualitative statements are left out.</div></div>
 <div class='panel span2'><h3>Which data and models do they use?</h3><canvas id='m6' height='320'></canvas>
   <div class='note'>Number of current frameworks listing each source ({n_with_src} of {len(fws)} list their
   sources).
   Used by one framework only: {_esc(', '.join(prov_single))}.</div>
   <details class='map'><summary>Name variants folded together</summary>
   <table class='data'><thead><tr><th>source name matches</th><th>counted as</th></tr></thead><tbody>{alias_rows}</tbody></table></details></div>
</div>
<h2>Have the triggers activated?</h2>
<div class='grid'>
 <div class='panel'><h3>Current frameworks, by activation record</h3><canvas id='m7' height='260'></canvas>
   <div class='note'>Any version of the framework. Partially = only part of the allocation or only the
   readiness window was released.</div></div>
 <div class='panel'><h3>Activations per year — framework triggers vs ad hoc allocations</h3><canvas id='m8' height='260'></canvas></div>
</div>
<section><div class='scroll' style='max-height:420px'><table class='data'><thead><tr><th>framework</th><th>status</th><th>record</th><th>activations (month · window · version)</th></tr></thead><tbody>{rec_rows}</tbody></table></div>
<p class='note2'><i>{NOT_RECORDED}</i> = the activation is on record but which window activated is not — a curation item.</p></section>
<h2>Every trigger window, framework by framework</h2>
<p class='meta'>One row per window of the latest version of each current framework, from its framework
record. No structured trigger recorded yet for {len(no_trig)}: {no_trig_html}.</p>
<section><div class='lfbar'><input class='filter' id='wq' placeholder='filter windows…' oninput='mfilt()'>{life_boxes}</div>
<div class='scroll'><table class='data' id='wtab'><thead><tr><th>framework</th><th>status</th><th>version</th><th>window</th><th>basis</th><th>measures</th><th>indicator</th><th>lead time</th><th>return period</th><th>backtest</th><th>activated on this version</th></tr></thead><tbody>{''.join(tr)}</tbody></table></div>
{loose_html}{unm_html}</section>
<h2>How much warning do the triggers give?</h2>
<p class='meta'>Lead times are written in hours, days, months or relative to landfall, so they are listed
as stated rather than averaged.</p>
<div class='grid'>{''.join(lead_panels)}</div>
<h2>When are the triggers monitored?</h2>
<p class='meta'>Green cells = the months each framework is monitored in a typical year, from its current
version's record (the planning sheet where the record lists none). Not this year's schedule.</p>
<section><div class='scroll'><table class='data'><thead><tr><th>framework</th><th>status</th><th>months monitored (typical year)</th></tr></thead><tbody>{cal_rows}</tbody></table></div></section>
<h2>Where are the models documented?</h2>
<p class='meta'>Framework document, model report and published analyses, and the analysis code
(an analysis reference from an earlier version is marked with that version).</p>
<section><div class='scroll'><table class='data'><thead><tr><th>framework</th><th>status</th><th>version</th><th>documents &amp; analyses</th><th>analysis code</th></tr></thead><tbody>{doc_rows}</tbody></table></div></section>"""
    js = """
const BASIS_COL = {'forecast':PAL[0],'observational':PAL[1],'mixed':PAL[2],'not recorded':'#bdbdbd'};
function lifeSets(o){ return o.sets.map(s=>({label:s.label, data:s.data, backgroundColor:s.color})); }
const H = {extra:{indexAxis:'y'}};
mkChart('m1','bar',D.cat.labels,lifeSets(D.cat),{stacked:true,count:true,totals:true,allLabels:true,...H});
mkChart('m2','bar',D.basis.labels,D.basis.sets.map(s=>({label:s.label,data:s.data,backgroundColor:BASIS_COL[s.label]})),{stacked:true,count:true,totals:true});
mkChart('m3','bar',D.struct.labels,lifeSets(D.struct),{stacked:true,count:true,totals:true,allLabels:true,...H});
mkChart('m4','bar',D.geo.labels,lifeSets(D.geo),{stacked:true,count:true,totals:true,allLabels:true});
const bins = [['≤ 1-in-3',0,3],['1-in-3 to 5',3,5],['1-in-5 to 10',5,10],['> 1-in-10',10,1e9]];
mkChart('m5','bar',bins.map(b=>b[0]),[{label:'windows',data:bins.map(b=>D.rp.filter(v=>v>b[1]&&v<=b[2]).length)}],{count:true});
mkChart('m6','bar',D.prov.labels,[{label:'frameworks',data:D.prov.data}],{count:true,allLabels:true,...H});
mkChart('m7','bar',D.rec.labels,lifeSets(D.rec),{stacked:true,count:true,totals:true,allLabels:true,...H});
const yrs = uniqSorted(D.act, r=>r.year), kinds = ['framework triggers','ad hoc allocations'];
mkChart('m8','bar',yrs,kinds.map(k=>({label:k, data:yrs.map(y=>D.act.filter(r=>r.year===y&&r.kind===k).length)})),{stacked:true,count:true});
function mfilt(){
  const q = document.getElementById('wq').value.toLowerCase();
  const on = new Set([...document.querySelectorAll('.lfbar input[type=checkbox]:checked')].map(b=>b.value));
  document.querySelectorAll('#wtab tbody tr').forEach(r=>{
    r.style.display = (on.has(r.dataset.life) && r.textContent.toLowerCase().includes(q)) ? '' : 'none'; }); }"""
    _dash_page(page, "pillar-model.html", "Model",
               "<b>The model block of anticipatory action</b> — the triggers: what they measure, "
               "where and when they are monitored, on what basis, how often they are designed to "
               "activate, and what has activated. Covers every current framework (active, being "
               "updated or in development), as set out in its latest version. <b>Ad hoc allocations "
               "are not included</b>: they have no trigger (they appear only as a comparison in the "
               "activations-per-year chart).",
               panels, json.dumps(data, default=str), js)


def _flag(v):
    """full_activation as True / False / None (numpy bools and NaN / NA included)."""
    return None if v is None or v is pd.NA or (isinstance(v, float) and pd.isna(v)) else bool(v)


def _unrec(name):
    """'unspecified' / 'unknown — …' window names: the activation is recorded, its window is not."""
    n = str(name or "").strip().lower()
    return n in ("", "none", "nan", "unspecified") or n.startswith("unknown")
