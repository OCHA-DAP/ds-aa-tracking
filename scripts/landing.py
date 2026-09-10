"""Landing page: zoomable world map → country → framework → version.

Click a country: the map zooms to it and draws the subnational areas in scope of the
current version of each framework there (KB `geographic_scope` names matched to CODAB
admin boundaries from the team blob cache). The sidebar lists the country's frameworks;
selecting one shows the chosen version's monitoring months, triggers (KB "Trigger
windows" table + backtested windows), budget by agency/fund, and every recorded
activation across ALL versions (flagged when it fired under a different version), with
the authoritative framework document linked per version.

Geometry is emitted as one small `adm-<ISO3>.json` per country in site_build (fetched
lazily by the page); CODAB layers are cached under data/codab/ (gitignored).
"""

import difflib
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd
import yaml

from ds_aa_tracking.versions import KB_DIR

ROOT = Path(__file__).parents[1]
OUT = ROOT / "site_build"
CACHE = ROOT / "data" / "codab"

W, H = 980, 460
LAT_TOP, LAT_BOT = 75.0, -58.0

STATUS_RANK = {"activated_implementing": 5, "active": 4, "under_revision": 3,
               "under_development": 2, "advanced_conversations": 1,
               "early_conversations": 1, "monitoring": 4, "project_finalization": 3}
STATUS_FILL = {5: "#0e7a52", 4: "#1baf7a", 3: "#eda100", 2: "#f2c14e", 1: "#9db2c9"}
HAZ_COLOR = {"flood": "#2a78d6", "drought": "#eb6834", "storm": "#8e5bd9",
             "cholera": "#1baf7a", "plague": "#b8860b"}

# scope-name aliases the generic matcher cannot resolve (normalized KB name -> one or
# more normalized CODAB names). Burkina Faso's 2025 region reform is not in CODAB yet:
# the new regions are mapped to the pre-reform provinces they were carved from
# (approximate — review when CODAB ships the 17-region layer).
ALIASES = {
    "south ethiopia region": ["snnp"],           # carved out of SNNP in 2023; CODAB predates it
    "bahr el gazal": ["barh el gazel"],
    "sar e pul": ["sar e pol"],
    "liptako": ["oudalan", "seno", "yagha"],
    "yaadga": ["loroum", "passore", "yatenga", "zondoma"],
    "koulse": ["bam", "namentenga", "sanmatenga"], "kuilse": ["bam", "namentenga", "sanmatenga"],
    "bankui": ["bale", "banwa", "mouhoun"],
    "sourou": ["kossi", "nayala", "sourou"],
    "djoro": ["bougouriba", "ioba", "noumbiel", "poni"],
}
DESCRIPTORS = ("region", "province", "district", "state", "governorate", "department",
               "departamento", "region de", "région", "province de", "county", "zone",
               "division", "prefecture", "municipality", "palika")


# ---------------------------------------------------------------- projection
def pt(lon, lat):
    return (lon + 180.0) / 360.0 * W, (LAT_TOP - lat) / (LAT_TOP - LAT_BOT) * H


def _ring_d(r):
    return "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in (pt(a, b) for a, b in r)) + "Z"


def svg_world(status_by_iso, country_names):
    gj = json.loads((ROOT / "site_src" / "countries.geo.json").read_text())
    paths, bboxes = [], {}
    for f in gj["features"]:
        iso = f.get("id")
        if iso == "ATA":
            continue
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        d = "".join(_ring_d(r[::2] or r) for poly in polys for r in poly)
        rank = status_by_iso.get(iso)
        fill = STATUS_FILL.get(rank, "#e6eaef")
        cls = "cty on" if rank else "cty"
        nm = country_names.get(iso, f["properties"].get("name", iso))
        paths.append(f"<path class='{cls}' data-iso='{iso}' data-name='{nm}' d='{d}' fill='{fill}'/>")
        # bbox of the largest polygon (avoids antimeridian blow-ups for FJI etc.)
        big = max(polys, key=lambda p: len(p[0]))
        xs = [c[0] for c in big[0]]; ys = [c[1] for c in big[0]]
        bboxes[iso] = [min(xs), min(ys), max(xs), max(ys)]
    svg = (f"<svg id='map' viewBox='0 0 {W} {H}' preserveAspectRatio='xMidYMid meet'>"
           f"<rect id='sea' x='0' y='0' width='{W}' height='{H}' fill='transparent'/>"
           f"<g id='world'>{''.join(paths)}<g id='adm'></g></g></svg>")
    return svg, bboxes


# ---------------------------------------------------------------- KB pages
def _kb_pages():
    """(kb_framework, version) -> {frontmatter, triggers[list of dict]}."""
    out = {}
    for pg in sorted(KB_DIR.glob("frameworks/*/[0-9]*.md")):
        txt = pg.read_text()
        m = re.match(r"^---\n(.*?)\n---", txt, re.DOTALL)
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            continue
        trig = []
        t = re.search(r"^## Trigger windows\n(.*?)(?=^## |\Z)", txt, re.M | re.S)
        if t:
            rows = [ln for ln in t.group(1).splitlines() if ln.strip().startswith("|")]
            if len(rows) >= 3:
                hdr = [h.strip().lower() for h in rows[0].strip().strip("|").split("|")]
                for ln in rows[2:]:
                    cells = [c.strip() for c in ln.strip().strip("|").split("|")]
                    if len(cells) != len(hdr) or all(not c or c.startswith("e.g.") for c in cells):
                        continue
                    trig.append({h: re.sub(r"\*\*(.*?)\*\*", r"\1", c) for h, c in zip(hdr, cells)})
        out[(fm.get("framework"), str(fm.get("version")))] = {"fm": fm, "triggers": trig}
    return out


# ---------------------------------------------------------------- CODAB + scope matching
def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _strip_desc(s):
    words = [w for w in s.split() if w not in DESCRIPTORS and w not in ("de", "of", "the")]
    return " ".join(words) or s


def load_codab(iso, level):
    """CODAB layer from the blob cache (cached locally as a pickle)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{iso}_adm{level}.pkl"
    if f.exists():
        return pd.read_pickle(f)
    from ocha_stratus import codab
    gdf = codab.load_codab_from_blob(iso, admin_level=level, stage="dev")
    if gdf is None:
        gdf = False
    pd.to_pickle(gdf, f)
    return gdf


class Matcher:
    """Match KB geographic_scope names to CODAB features at admin levels 1..3."""

    def __init__(self, iso, max_level):
        self.iso = iso
        self.layers = {}
        for lv in range(1, max(1, min(max_level, 3)) + 1):
            g = load_codab(iso, lv)
            if g is False or g is None or not len(g):
                continue
            pcol = f"ADM{lv}_PCODE"
            # name columns are language-specific (ADM1_EN / _FR / _ES / _PT ...)
            ncols = [c for c in g.columns if re.fullmatch(rf"ADM{lv}_[A-Z]{{2}}", c)]
            ncols.sort(key=lambda c: (not c.endswith("_EN"), c))
            if not ncols or pcol not in g.columns:
                continue
            ncol = ncols[0]
            g = g.copy()
            g["_names"] = g[ncols].astype(str).agg(list, axis=1)
            g["_n"] = g["_names"].map(lambda xs: [_norm(x) for x in xs])
            g["_ns"] = g["_n"].map(lambda xs: [_strip_desc(x) for x in xs])
            self.layers[lv] = (g, ncol, pcol)
        self.used = {}   # pcode -> feature record

    def _record(self, lv, row):
        g, ncol, pcol = self.layers[lv]
        pc = row[pcol]
        if pc not in self.used:
            self.used[pc] = {"pcode": pc, "name": row[ncol], "level": lv,
                             "geometry": row["geometry"]}
        return pc

    def _find(self, name, levels):
        n = _norm(name)
        if n in ALIASES:
            out = []
            for alias in ALIASES[n]:
                out += self._find_one(alias, levels)
            return out
        return self._find_one(n, levels)

    def _find_one(self, n, levels):
        ns = _strip_desc(n)
        for lv in levels:
            if lv not in self.layers:
                continue
            g, ncol, pcol = self.layers[lv]
            if n.upper() in set(g[pcol]):                        # pcode given directly
                return [self._record(lv, r) for _, r in g[g[pcol] == n.upper()].iterrows()]
            hit = g[g["_n"].map(lambda xs: n in xs) | g["_ns"].map(lambda xs: ns in xs)]
            if len(hit):
                return [self._record(lv, r) for _, r in hit.iterrows()]
        if len(ns) >= 4:                                          # unique word-bounded containment
            for lv in levels:                                     # ('bicol' in 'region v bicol region')
                if lv not in self.layers:
                    continue
                g, ncol, pcol = self.layers[lv]
                pat = re.compile(rf"\b{re.escape(ns)}\b")
                hit = g[g["_ns"].map(lambda xs: any(pat.search(x) for x in xs))]
                if len(hit) == 1:
                    return [self._record(lv, r) for _, r in hit.iterrows()]
        for lv in levels:                                         # fuzzy fallback
            if lv not in self.layers:
                continue
            g, ncol, pcol = self.layers[lv]
            pool = {x: i for i, xs in zip(g.index, g["_ns"]) for x in xs}
            cands = difflib.get_close_matches(ns, list(pool), n=1, cutoff=0.86)
            if cands:
                return [self._record(lv, g.loc[pool[cands[0]]])]
        return []

    def match(self, items, admin_level, country_name):
        """-> (pcodes, unmatched_names, national_flag)."""
        pcodes, unmatched, national = [], [], False
        top = max(1, min(admin_level or 3, 3))
        levels = list(range(top, 0, -1))
        for raw in items or []:
            s = str(raw).strip()
            if not s:
                continue
            if re.match(r"^[A-Z]{3}:\s", s):                       # 'GTM: a, b' (multi-country)
                if not s.startswith(self.iso + ":"):
                    continue
                s = s.split(":", 1)[1].strip()
            if s.startswith(self.iso + "/"):                       # 'NPL/Koshi Province/Sunsari district (…)'
                s = s.split("/")[-1].strip()
            # 'Eastern Visayas (R8) — Samar…' -> drop dash suffixes (outside parentheses only)
            s = re.split(r"\s+[—–-]{1,2}\s+(?![^()]*\))", s)[0].strip()
            low = _norm(s)
            if (low in ("national", "nationwide", "all", _norm(country_name), self.iso.lower())
                    or low.startswith("national") or "all other" in low):
                national = True
                continue
            groups = re.findall(r"[^,;()]+\([^()]*\)", s)     # 'A (a1, a2), B (b1)' -> per group
            if len(groups) > 1:
                for grp in groups:
                    pc, um, _ = self.match([grp.strip(" ,;")], admin_level, country_name)
                    pcodes += pc
                    unmatched += um
                continue
            parts = re.match(r"^(.*?)\s*\((.*)\)\s*$", s)
            names = [s]
            if parts:
                outer, inner = parts.group(1).strip(), parts.group(2).strip()
                inner = inner.split(":", 1)[1] if ":" in inner else inner
                children = [c.strip() for c in re.split(r"[,;/]| and ", inner) if c.strip()]
                names = [outer] + children
            if "," in s and not parts:
                names = [c.strip() for c in s.split(",") if c.strip()]
            got = []
            # prefer the children (deeper level) when they all resolve; else the outer name
            if parts and len(names) > 1:
                kids = [self._find(c, levels) for c in names[1:]]
                if kids and all(kids):
                    got = [p for k in kids for p in k]
                else:
                    got = self._find(names[0], levels) or self._find(parts.group(2), levels)
            else:
                for nm in names:
                    got += self._find(nm, levels)
            if got:
                pcodes += got
            else:
                unmatched.append(s)
        return sorted(set(pcodes)), unmatched, national


def _rings(geom, tol):
    """Simplified geometry -> list of rings [[lon,lat],...] with 3-decimal coords."""
    from shapely.geometry import MultiPolygon, Polygon
    g = geom.simplify(tol, preserve_topology=True)
    polys = list(g.geoms) if isinstance(g, MultiPolygon) else [g] if isinstance(g, Polygon) else []
    if not polys:
        return []
    amax = max(p.area for p in polys)
    rings = []
    for p in polys:
        if p.area < amax * 0.002:
            continue
        rings.append([[round(x, 3), round(y, 3)] for x, y in p.exterior.coords])
        for hole in p.interiors:
            rings.append([[round(x, 3), round(y, 3)] for x, y in hole.coords])
    return rings


def write_country_geo(iso, matcher, adm0):
    """adm-<ISO>.json: country outline, ADM1 mesh, and the matched scope areas."""
    b = adm0.total_bounds if adm0 is not None else None
    diag = ((b[2] - b[0]) ** 2 + (b[3] - b[1]) ** 2) ** 0.5 if b is not None else 10
    tol1, tol2 = diag / 700, diag / 1100
    out = {"adm0": [], "adm1": [], "areas": {}}
    if adm0 is not None and len(adm0):
        out["adm0"] = _rings(adm0.geometry.union_all() if hasattr(adm0.geometry, "union_all")
                             else adm0.geometry.unary_union, tol1)
    if 1 in matcher.layers:
        g, ncol, pcol = matcher.layers[1]
        out["adm1"] = [{"n": r[ncol], "p": r[pcol], "r": _rings(r["geometry"], tol1)}
                       for _, r in g.iterrows()]
    for pc, rec in matcher.used.items():
        out["areas"][pc] = {"n": rec["name"], "l": rec["level"],
                            "r": _rings(rec["geometry"], tol2 if rec["level"] > 1 else tol1)}
    (OUT / f"adm-{iso}.json").write_text(json.dumps(out, separators=(",", ":")))
    return b


# ---------------------------------------------------------------- data assembly
def _f(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) or str(v) in ("None", "NaT", "nan") else v


def _num(v):
    v = _f(v)
    return None if v is None else float(v)


def _s(v):
    v = _f(v)
    return None if v is None else str(v)


def assemble(d, e):
    cur = d["current"].sort_values("country_name")
    ver = pd.read_sql("SELECT * FROM aa.framework_version", e)
    win = pd.read_sql(
        """SELECT w.kb_framework, w.kb_version, w.country_iso3, w.window_name, w.all_in,
                  w.basis, w.allocation_usd, p.n_activations AS sim_activations,
                  p.analysis_years, p.return_period, p.activation_prob
           FROM aa.window w LEFT JOIN aa.v_window_performance p
             USING (kb_framework, kb_version, country_iso3, window_name)""", e)
    fb = pd.read_sql("SELECT * FROM aa.funding_breakdown WHERE amount_usd IS NOT NULL", e)
    psb = pd.read_sql(
        """SELECT country_iso3, hazard, version, window_name, agency, sector, amount_usd
           FROM aa.prearranged_sector_budget WHERE amount_usd IS NOT NULL""", e)
    acts = pd.read_sql(
        """SELECT a.country_iso3, a.hazard, a.event_type, a.event_date, a.window_name,
                  a.event_label, a.version, a.kb_framework, a.kb_event_date,
                  a.people_targeted, a.comments
           FROM aa.activation a ORDER BY a.event_date DESC""", e)
    actf = pd.read_sql(
        """SELECT country_iso3, hazard, event_date, window_name, event_label, event_type,
                  fund_code, allocation_code, amount_usd FROM aa.activation_funding""", e)
    aurl = pd.read_sql(
        """SELECT kb_framework, event_date, country_iso3, url, released_usd, full_activation, note
           FROM aa.actual_activation""", e)
    cal = d["calendar"]
    kb = _kb_pages()

    def kb_page(kb_fw, version):
        if not kb_fw:
            return None
        p = kb.get((kb_fw, version))
        if p:
            return p
        for (f, v), pg in kb.items():          # 'YYYY' registry label vs dated page
            if f == kb_fw and (v.startswith(version) or version.startswith(v)):
                return pg
        return None

    def kb_key_match(series, version):
        return series.map(lambda v: v == version or str(v).startswith(version)
                          or version.startswith(str(v)))

    countries = {}
    for _, r in cur.iterrows():
        c, h = r["country_iso3"], r["hazard"]
        kb_fw = _s(r.get("kb_framework"))
        countries.setdefault(c, {"name": r["country_name"], "region": _s(r.get("region")),
                                 "fws": []})
        vs = ver[(ver["country_iso3"] == c) & (ver["hazard"] == h)].copy()
        vs = vs.sort_values("valid_from", na_position="first")
        a_f = acts[(acts["country_iso3"] == c) & (acts["hazard"] == h)]

        versions = []
        for v in vs.itertuples():
            pg = kb_page(kb_fw, v.version)
            fm = pg["fm"] if pg else {}
            mp = fm.get("monitoring_period") or {}
            tf = fm.get("trigger_facets") or {}
            months = [int(m) for m in (mp.get("months") or []) if isinstance(m, int)]
            if not months:
                months = sorted(int(m) for m in cal.loc[(cal["country_iso3"] == c)
                                                        & (cal["hazard"] == h), "month"].unique())
                months_src = "calendar sheet" if months else None
            else:
                months_src = mp.get("source")
            # backtested windows for this version
            w_v = win[(win["country_iso3"] == c) & (win["kb_framework"] == (kb_fw or "—"))
                      & kb_key_match(win["kb_version"], v.version)]
            windows = [{"name": w.window_name, "basis": _s(w.basis), "all_in": _f(w.all_in),
                        "budget": _num(w.allocation_usd), "rp": _num(w.return_period),
                        "prob": _num(w.activation_prob), "sim": _num(w.sim_activations),
                        "years": _num(w.analysis_years)} for w in w_v.itertuples()]
            # budget breakdown: KB funding_breakdown for this version, else sheet sector budget
            f_v = fb[(fb["country_iso3"] == c) & (fb["kb_framework"] == (kb_fw or "—"))
                     & (fb["kb_version"] == v.version)]
            fund_src = "kb"
            if not len(f_v):
                p_v = psb[(psb["country_iso3"] == c) & (psb["hazard"] == h)
                          & (psb["version"] == v.version)]
                f_v = p_v.assign(fund_source="CERF (sheet)", provenance="sheet")
                fund_src = "sheet" if len(p_v) else None
            by_agency = (f_v.dropna(subset=["agency"])
                         .groupby(["agency", "fund_source"], dropna=False)["amount_usd"].sum()
                         .reset_index()) if len(f_v) else pd.DataFrame()
            by_sector = (f_v.dropna(subset=["sector"])
                         .groupby(["sector", "fund_source"], dropna=False)["amount_usd"].sum()
                         .reset_index()) if len(f_v) else pd.DataFrame()
            by_fund = (f_v.groupby("fund_source", dropna=False)["amount_usd"].sum()
                       .reset_index()) if len(f_v) else pd.DataFrame()
            scope_raw = fm.get("geographic_scope") or []
            if isinstance(scope_raw, str):
                scope_raw = [scope_raw]
            regional = isinstance(fm.get("country_iso3"), list) and len(fm["country_iso3"]) > 1
            if regional:   # 'GTM: a, b' entries belong to one country each
                scope_raw = [x for x in scope_raw
                             if not re.match(r"^[A-Z]{3}[:/]", str(x)) or str(x).startswith(c)]
            versions.append({
                "v": v.version, "status": _s(v.kb_status), "valid_from": _s(v.valid_from),
                "valid_until": _s(v.valid_until), "valid_until_source": _s(v.valid_until_source),
                "endorsed_by": _s(v.endorsed_by), "supersedes": _s(v.supersedes),
                "doc_url": _s(v.doc_url), "doc_title": _s(v.doc_title),
                "doc_date": _s(fm.get("framework_doc_date")),
                "prearranged_doc": _num(v.prearranged_usd_doc)
                                   or _num(fm.get("prearranged_funding_usd")),
                "regional": regional,
                "cofin": _num(fm.get("cofinancing_usd")),
                "cofin_sources": fm.get("cofinancing_sources") or [],
                "agencies": fm.get("implementing_agencies") or [],
                "target_people": _num(fm.get("target_people")),
                "all_in": fm.get("all_in", None),
                "months": months, "months_src": months_src, "months_note": _s(mp.get("note")),
                "basis": _s(tf.get("basis")), "calibration": _s(tf.get("calibration")),
                "indicators": tf.get("indicators") or [],
                "data_sources": fm.get("data_sources") or [],
                "triggers": pg["triggers"] if pg else [],
                "windows": windows,
                "funding": {
                    "src": fund_src,
                    "agency": [{"agency": _s(x.agency), "fund": _s(x.fund_source) or "unspecified",
                                "usd": float(x.amount_usd)} for x in by_agency.itertuples()],
                    "sector": [{"sector": _s(x.sector), "fund": _s(x.fund_source) or "unspecified",
                                "usd": float(x.amount_usd)} for x in by_sector.itertuples()],
                    "fund": [{"fund": _s(x.fund_source) or "unspecified", "usd": float(x.amount_usd)}
                             for x in by_fund.itertuples()],
                },
                "admin_level": fm.get("admin_level") if isinstance(fm.get("admin_level"), int) else None,
                "scope_raw": [str(x) for x in scope_raw],
                "scope": None,      # filled by the geo pass
                "kb_page": bool(pg), "source": _s(v.source), "note": _s(v.note),
            })

        activations = []
        for a in a_f.itertuples():
            fr = actf[(actf["country_iso3"] == c) & (actf["hazard"] == h)
                      & (actf["event_date"] == a.event_date)
                      & (actf["event_type"] == a.event_type)
                      & (actf["event_label"].fillna("") == (a.event_label or ""))
                      & (actf["window_name"].fillna("") == (a.window_name or ""))]
            u = aurl[(aurl["kb_framework"] == (kb_fw or "—"))
                     & (aurl["event_date"] == (a.kb_event_date or "—"))]
            if len(u) > 1 and "country_iso3" in u.columns:
                u2 = u[u["country_iso3"] == c]
                u = u2 if len(u2) else u
            u = u.iloc[0] if len(u) else None
            activations.append({
                "date": a.event_date, "kb_date": _s(a.kb_event_date),
                "type": a.event_type, "window": _s(a.window_name), "version": _s(a.version),
                "people": _num(a.people_targeted),
                "url": _s(u["url"]) if u is not None else None,
                "released": _num(u["released_usd"]) if u is not None else None,
                "full": _f(u["full_activation"]) if u is not None else None,
                "funding": [{"fund": x.fund_code, "code": _s(x.allocation_code),
                             "usd": _num(x.amount_usd)} for x in fr.itertuples()],
            })

        cur_v = _s(r.get("current_version"))
        if cur_v not in {x["v"] for x in versions} and versions:
            cur_v = versions[-1]["v"]
        countries[c]["fws"].append({
            "hazard": h, "status": _s(r.get("status")), "kb": kb_fw,
            "page": f"fw-{c.lower()}-{h}.html",
            "prearranged": _num(r.get("cerf_prearranged_usd")),
            "prearranged_year": _num(r.get("prearranged_year")),
            "covered": _num(r.get("people_covered")),
            "current": cur_v, "versions": versions, "activations": activations,
        })
    return countries


def geo_pass(countries, bboxes):
    """Match every version's scope to CODAB and write one geometry file per country."""
    for iso, cd in countries.items():
        levels = [v["admin_level"] for f in cd["fws"] for v in f["versions"]
                  if v["admin_level"]]
        has_scope = any(v["scope_raw"] for f in cd["fws"] for v in f["versions"])
        deeper = any("(" in x for f in cd["fws"] for v in f["versions"] for x in v["scope_raw"])
        max_level = (min(max(levels) if levels else 1, 3) + (1 if deeper else 0)) if has_scope else 1
        max_level = min(max_level, 3)
        try:
            m = Matcher(iso, max_level)
            adm0 = load_codab(iso, 0)
            adm0 = None if adm0 is False else adm0
        except Exception as ex:  # noqa: BLE001 — a missing CODAB must not break the build
            print(f"  ! CODAB unavailable for {iso}: {ex}")
            m, adm0 = None, None
        for f in cd["fws"]:
            for v in f["versions"]:
                if m is None:
                    v["scope"] = {"pcodes": [], "unmatched": v["scope_raw"], "national": False}
                    continue
                pcodes, unmatched, national = m.match(v["scope_raw"], v["admin_level"], cd["name"])
                if not v["scope_raw"] and v["admin_level"] == 0:
                    national = True
                v["scope"] = {"pcodes": pcodes, "unmatched": unmatched, "national": national}
                if unmatched:
                    print(f"  ? {iso} {f['hazard']} {v['v']}: unmatched scope {unmatched}")
        if m is not None:
            b = write_country_geo(iso, m, adm0)
            if b is not None:
                bboxes[iso] = [float(x) for x in b]
        cd["bbox"] = bboxes.get(iso)
        cd["has_geo"] = m is not None


# ---------------------------------------------------------------- page
def build_landing(page, d, e):
    cur = d["current"]
    status_by_iso = {}
    for _, r in cur.iterrows():
        rank = STATUS_RANK.get(r["status"] or "", 0)
        if rank and rank > status_by_iso.get(r["country_iso3"], 0):
            status_by_iso[r["country_iso3"]] = rank
    names = dict(zip(cur["country_iso3"], cur["country_name"]))
    svg, bboxes = svg_world(status_by_iso, names)

    countries = assemble(d, e)
    geo_pass(countries, bboxes)

    act = d["activation"]
    n_active = int(cur["status"].isin(["active", "activated_implementing"]).sum())
    pre = d["prearranged"]
    total_pre = pre.loc[(pre["kind"] == "prearranged") & (pre["year"] == 2026)
                        & (pre["fund_code"] != "all"), "amount_usd"].sum()
    n_act_all = act["event_date"].nunique()
    covered = d["covered"]["people_covered"].sum()

    body = f"""
<div class='hero'>
 <p>The single source for the AA portfolio: every framework, endorsed version, trigger
 window, activation and dollar — across CERF, country-based and regional pooled funds.
 <b>Click a country</b> to zoom in and see the areas each framework covers.</p>
 <div class='tiles'>
  <div class='tile'><div class='v'>{n_active}</div><div class='l'>active frameworks (of {len(cur)} tracked)</div></div>
  <div class='tile'><div class='v'>${total_pre/1e6:,.0f}M</div><div class='l'>pre-arranged (2026)</div></div>
  <div class='tile'><div class='v'>{n_act_all}</div><div class='l'>activations since 2020</div></div>
  <div class='tile'><div class='v'>{covered/1e6:,.1f}M</div><div class='l'>people covered</div></div>
 </div>
</div>
<div class='maprow'>
 <div class='mapbox'>
  <button id='back' class='backbtn' hidden>← world</button>
  <div id='tip' class='tip' hidden></div>
  {svg}
  <div class='legend' id='legend'>
   <span><i style='background:#0e7a52'></i>activated &amp; implementing</span>
   <span><i style='background:#1baf7a'></i>active</span>
   <span><i style='background:#eda100'></i>revision / development</span>
   <span><i style='background:#9db2c9'></i>early conversations</span>
  </div>
 </div>
 <div class='side' id='side'>
  <div class='muted' style='padding:20px 6px'>Select a country on the map to see its
  frameworks — status, funding, monitoring window, triggers, versions and activations.</div>
 </div>
</div>
<div class='tiles' style='margin-top:18px'>
 <div class='tile'><a href='dashboards.html'><b>Dashboards</b></a><div class='l'>funding · allocations · delivery</div></div>
 <div class='tile'><a href='hierarchy.html'><b>Portfolio explorer</b></a><div class='l'>framework › version › window › activation</div></div>
 <div class='tile'><a href='ingest-doc.html'><b>Ingest a document</b></a><div class='l'>upload an endorsed framework PDF</div></div>
 <div class='tile'><a href='overview.html'><b>Data &amp; schema review</b></a><div class='l'>tables · reconciliation · roadmap</div></div>
</div>
<script>window.L = {json.dumps(countries, default=str)};
window.HAZ = {json.dumps(HAZ_COLOR)}; window.MAPW={W}; window.MAPH={H}; window.LATT={LAT_TOP}; window.LATB={LAT_BOT};</script>
<script>{LANDING_JS}</script>
<style>{LANDING_CSS}</style>"""
    page("index.html", "OCHA Anticipatory Action — portfolio", body)


LANDING_CSS = r"""
.hero { text-align:left; padding:6px 0 2px; }
.hero p { color:#556; max-width:800px; }
.tiles { display:flex; gap:14px; flex-wrap:wrap; margin:12px 0; }
.tile { background:#fff; border:1px solid #e0e0e0; border-radius:6px; padding:12px 18px; min-width:150px; }
.tile .v { font-size:22px; font-weight:700; } .tile .l { font-size:12px; color:#666; }
.maprow { display:grid; grid-template-columns: minmax(0,1fr) 420px; gap:16px; align-items:start; }
@media (max-width: 1000px) { .maprow { grid-template-columns: 1fr; } }
.mapbox { background:#fff; border:1px solid #dfe4ea; border-radius:10px; padding:10px; position:relative; overflow:hidden; }
#map { width:100%; height:auto; display:block; background:#f7f9fc; border-radius:6px; }
.cty { stroke:#fff; stroke-width:.5; vector-effect:non-scaling-stroke; transition: opacity .5s, fill .5s; }
.cty.on { cursor:pointer; }
.cty.on:hover { filter:brightness(.9); }
#map.zoomed .cty { opacity:.14; } #map.zoomed .cty.sel { opacity:0; }
.a0 { fill:#fff; stroke:#2f3d59; stroke-width:1.5; vector-effect:non-scaling-stroke; }
.a1 { fill:#eef1f5; stroke:#aab5c4; stroke-width:.8; vector-effect:non-scaling-stroke; }
.a1:hover { fill:#e2e7ee; }
.sc { stroke:#fff; stroke-width:.8; vector-effect:non-scaling-stroke; fill-opacity:.78; cursor:pointer; transition: fill-opacity .3s; }
.sc:hover { fill-opacity:1; }
.sc.dim { fill-opacity:.25; }
.nat { fill-opacity:.35; pointer-events:none; }
#adm { opacity:0; transition: opacity .5s ease .35s; } #adm.show { opacity:1; }
.backbtn { position:absolute; top:18px; left:18px; z-index:3; padding:5px 12px; border:1px solid #bbb;
  border-radius:16px; background:#fff; cursor:pointer; font-size:12.5px; box-shadow:0 1px 3px rgba(0,0,0,.1); }
.tip { position:absolute; z-index:4; background:#1f2a44; color:#fff; font-size:12px; padding:4px 9px;
  border-radius:5px; pointer-events:none; white-space:nowrap; transform:translate(-50%,-130%); }
.legend { display:flex; gap:16px; flex-wrap:wrap; padding:8px 6px 2px; font-size:12px; color:#556; }
.legend i { display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:5px; vertical-align:-1px; }
.side { background:#fff; border:1px solid #dfe4ea; border-radius:10px; padding:12px 16px 16px;
  max-height:640px; overflow-y:auto; font-size:13px; }
.side h3 { margin:2px 0 4px; font-size:18px; } .side h4 { margin:14px 0 4px; font-size:11.5px;
  text-transform:uppercase; letter-spacing:.05em; color:#778; }
.crumb { font-size:12px; color:#667; margin-bottom:8px; } .crumb a { color:#1d5aa8; cursor:pointer; text-decoration:none; }
.crumb a:hover { text-decoration:underline; }
.fwlist .fcardx { border:1px solid #e6eaef; border-radius:8px; padding:10px 12px; margin:8px 0; cursor:pointer;
  border-left:4px solid var(--hz,#999); transition: background .15s; }
.fwlist .fcardx:hover { background:#f6f8fb; }
.fhead { display:flex; justify-content:space-between; align-items:center; gap:8px; }
.fhead b { text-transform:capitalize; font-size:14px; }
.st { display:inline-block; padding:0 8px; border-radius:9px; font-size:11px; font-weight:600; white-space:nowrap; }
.st-on { background:#e3f1e6; color:#1c6b31; } .st-off { background:#ededed; color:#777; }
.st-dev { background:#fdf1dc; color:#8a5c0a; } .st-past { background:#eceff5; color:#4a5670; }
table.mini { border-collapse:collapse; font-size:12px; width:100%; }
table.mini td, table.mini th { padding:3px 6px; border-bottom:1px solid #eef1f5; vertical-align:top; text-align:left; }
table.mini th { font-weight:600; color:#556; background:#f4f6f9; white-space:nowrap; }
table.mini td.lbl { color:#667; width:118px; white-space:nowrap; }
table.mini td.num { text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }
.mm { display:inline-grid; place-items:center; width:17px; height:17px; font-size:9px;
  border-radius:3px; background:#f0f2f5; color:#99a; margin-right:1px; }
.mm.on { background:#1baf7a; color:#fff; }
.muted { color:#667; font-size:12px; }
.small { font-size:11.5px; color:#556; }
.verbar { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin:8px 0 4px; }
.verbar select { padding:4px 8px; border:1px solid #bbb; border-radius:5px; font-size:12.5px; background:#fff; }
.docbtn { display:inline-block; padding:5px 11px; border-radius:5px; background:#1d5aa8; color:#fff !important;
  text-decoration:none; font-size:12.5px; font-weight:600; }
.docbtn.ghost { background:#fff; color:#1d5aa8 !important; border:1px solid #9bb8dd; }
.warnbox { background:#fdf6e7; border:1px solid #f1d9a5; color:#7a5410; border-radius:6px; padding:6px 10px; font-size:12px; margin:8px 0; }
.trig { border:1px solid #e6eaef; border-radius:6px; padding:7px 10px; margin:6px 0; background:#fbfcfd; }
.trig .tn { font-weight:650; } .trig .tt { margin-top:2px; }
.trig .tm { color:#667; font-size:11.5px; margin-top:3px; }
.actrow { border-bottom:1px solid #eef1f5; padding:6px 0; }
.actrow .ah { display:flex; justify-content:space-between; gap:8px; align-items:baseline; }
.actrow .ad { font-weight:650; white-space:nowrap; }
.vtag { display:inline-block; font-size:10.5px; padding:0 6px; border-radius:8px; background:#eceff5; color:#4a5670; margin-left:6px; font-family:ui-monospace,monospace; }
.vtag.other { background:#fdf1dc; color:#8a5c0a; }
.chips span { display:inline-block; background:#f0f2f5; border-radius:9px; padding:0 7px; font-size:11px; margin:2px 3px 2px 0; }
.scopelist { font-size:12px; color:#334; line-height:1.5; }
.hzdot { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:5px; vertical-align:0; }
"""

LANDING_JS = r"""
const MONL = 'JFMAMJJASOND';
const svg = document.getElementById('map'), world = document.getElementById('world'),
      adm = document.getElementById('adm'), side = document.getElementById('side'),
      back = document.getElementById('back'), tip = document.getElementById('tip'),
      legend = document.getElementById('legend');
const GEO = {};   // iso -> fetched adm-XXX.json
let state = { iso:null, hz:null, ver:null };
const LEGEND_WORLD = legend.innerHTML;

function money(v){ return v==null ? '—' : v>=1e6 ? '$'+(v/1e6).toFixed(v>=1e7?0:1)+'M' : v>=1e3 ? '$'+Math.round(v/1e3)+'k' : '$'+Math.round(v); }
function num(v){ return v==null ? '—' : Math.round(v).toLocaleString(); }
function esc(s){ return s==null ? '' : String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function stCls(s){ s=s||''; return ['active','activated_implementing','endorsed'].includes(s) ? 'st-on'
  : (s.includes('dev')||s.includes('revision')||s.includes('conversation')) ? 'st-dev' : s==='superseded' ? 'st-past' : 'st-off'; }
function stTxt(s){ return s ? s.replace(/_/g,' ') : 'no status'; }
function hzColor(h){ return HAZ[h] || '#7a8699'; }
function pt(lon, lat){ return [(lon+180)/360*MAPW, (LATT-lat)/(LATT-LATB)*MAPH]; }
function ringsD(rings){ return rings.map(r=>'M'+r.map(([x,y])=>{const p=pt(x,y);return p[0].toFixed(2)+','+p[1].toFixed(2);}).join('L')+'Z').join(''); }

// ---------- map: zoom (SVG transform attribute animated in user units — CSS px transforms
// on <g> do not map to the viewBox reliably)
let T = {tx:0, ty:0, sx:1, sy:1}, animId = null, animSeq = 0;
function applyT(t){ world.setAttribute('transform', `translate(${t.tx} ${t.ty}) scale(${t.sx} ${t.sy})`); }
function animateTo(target, ms=800){
  if(animId) cancelAnimationFrame(animId);
  if(document.hidden){ T = {...target}; applyT(T); return; }   // rAF is paused in hidden tabs
  const seq = ++animSeq;                                        // guarantee the final state
  setTimeout(()=>{ if(seq===animSeq){ T = {...target}; applyT(T); animId=null; } }, ms+80);
  const from = {...T}, t0 = performance.now();
  const ease = x => 1 - Math.pow(1 - x, 3);
  function step(now){
    const k = Math.min(1, (now - t0)/ms), e = ease(k);
    T = { tx: from.tx + (target.tx-from.tx)*e, ty: from.ty + (target.ty-from.ty)*e,
          sx: from.sx + (target.sx-from.sx)*e, sy: from.sy + (target.sy-from.sy)*e };
    applyT(T);
    if(k < 1) animId = requestAnimationFrame(step); else animId = null;
  }
  animId = requestAnimationFrame(step);
}
function zoomTo(bbox){
  const [x0,y0] = pt(bbox[0], bbox[3]), [x1,y1] = pt(bbox[2], bbox[1]);
  const lat0 = (bbox[1]+bbox[3])/2, cosf = Math.max(.35, Math.cos(lat0*Math.PI/180));
  const bw = Math.max(x1-x0, 2), bh = Math.max(y1-y0, 2), pad = 1.3;
  let s = Math.min(MAPW/(bw*cosf*pad), MAPH/(bh*pad));
  s = Math.min(s, 60);
  const cx = (x0+x1)/2, cy = (y0+y1)/2;
  animateTo({ tx: MAPW/2 - cx*s*cosf, ty: MAPH/2 - cy*s, sx: s*cosf, sy: s });
}
function resetZoom(){ animateTo({tx:0, ty:0, sx:1, sy:1}, 650); }

// ---------- map: admin layers
async function loadGeo(iso){
  if(GEO[iso] !== undefined) return GEO[iso];
  try { const r = await fetch(`adm-${iso}.json`); GEO[iso] = r.ok ? await r.json() : null; }
  catch(e){ GEO[iso] = null; }
  return GEO[iso];
}
function drawAdmin(iso, fade){
  const g = GEO[iso]; adm.innerHTML=''; if(fade) adm.classList.remove('show');
  if(!g) return;
  const c = L[iso];
  let html = '';
  if(g.adm0.length) html += `<path class='a0' d='${ringsD(g.adm0)}'/>`;
  g.adm1.forEach(a => html += `<path class='a1' data-n='${esc(a.n)}' d='${ringsD(a.r)}'/>`);
  // which areas to paint: selected framework+version, else the current version of every framework
  const paint = {};  // pcode -> [{hz}]
  let national = [];
  const targets = state.hz ? c.fws.filter(f=>f.hazard===state.hz) : c.fws;
  targets.forEach(f => {
    const v = f.versions.find(x => x.v === (state.hz && state.ver ? state.ver : f.current));
    if(!v || !v.scope) return;
    if(v.scope.national) national.push(f.hazard);
    v.scope.pcodes.forEach(p => { (paint[p] ??= []).push(f.hazard); });
  });
  national.forEach(h => { if(g.adm0.length) html += `<path class='nat' fill='${hzColor(h)}' d='${ringsD(g.adm0)}'/>`; });
  Object.entries(paint).forEach(([p, hzs]) => {
    const a = g.areas[p]; if(!a) return;
    html += `<path class='sc' fill='${hzColor(hzs[0])}' data-n='${esc(a.n)}' data-hz='${esc(hzs.join(', '))}' d='${ringsD(a.r)}'/>`;
  });
  adm.innerHTML = html;
  if(fade) void adm.getBoundingClientRect();   // force a style flush so the opacity transition runs
  adm.classList.add('show');
  // legend: hazards in view
  const hzs = [...new Set(targets.map(f=>f.hazard))];
  legend.innerHTML = hzs.map(h=>`<span><i style='background:${hzColor(h)}'></i>${h} framework scope</span>`).join('')
    + `<span><i style='background:#f3f5f8;border:1px solid #c9d1dc'></i>admin-1 boundaries</span>`
    + (national.length ? `<span class='small'>shaded whole country = national trigger</span>` : '');
}

// ---------- tooltips
svg.addEventListener('mousemove', ev => {
  const t = ev.target, box = svg.getBoundingClientRect();
  let txt = null;
  if(t.classList.contains('cty') && t.classList.contains('on') && !state.iso){
    const c = L[t.dataset.iso]; txt = `${c.name} · ${c.fws.length} framework${c.fws.length>1?'s':''}`;
  } else if(t.classList.contains('sc')) txt = `${t.dataset.n} · ${t.dataset.hz}`;
  else if(t.classList.contains('a1')) txt = t.dataset.n;
  if(txt){ tip.textContent = txt; tip.hidden = false;
    tip.style.left = (ev.clientX-box.left)+'px'; tip.style.top = (ev.clientY-box.top)+'px'; }
  else tip.hidden = true;
});
svg.addEventListener('mouseleave', ()=> tip.hidden = true);

// ---------- selection
svg.addEventListener('click', ev => {
  const t = ev.target;
  if(t.classList.contains('cty') && t.classList.contains('on')) selectCountry(t.dataset.iso);
  else if(t.id === 'sea' && state.iso) goWorld();
});
back.addEventListener('click', goWorld);

function goWorld(){
  state = { iso:null, hz:null, ver:null };
  document.querySelectorAll('.cty.sel').forEach(x=>x.classList.remove('sel'));
  svg.classList.remove('zoomed'); adm.innerHTML=''; adm.classList.remove('show');
  resetZoom(); back.hidden = true; legend.innerHTML = LEGEND_WORLD;
  side.innerHTML = `<div class='muted' style='padding:20px 6px'>Select a country on the map.</div>`;
  history.replaceState(null, '', location.pathname);
}

async function selectCountry(iso, hz, ver){
  const c = L[iso]; if(!c) return;
  const changed = state.iso !== iso;
  state = { iso, hz: hz || (c.fws.length===1 ? c.fws[0].hazard : null), ver: ver || null };
  document.querySelectorAll('.cty.sel').forEach(x=>x.classList.remove('sel'));
  const el = svg.querySelector(`.cty[data-iso='${iso}']`); if(el) el.classList.add('sel');
  svg.classList.add('zoomed'); back.hidden = false;
  if(changed){ adm.innerHTML=''; adm.classList.remove('show'); if(c.bbox) zoomTo(c.bbox); }
  renderSide();
  await loadGeo(iso);
  if(state.iso === iso) drawAdmin(iso, changed);
  location.hash = [iso, state.hz, state.ver].filter(Boolean).join('/');
}
function selectFramework(hz){ selectCountry(state.iso, hz, null); }
function selectVersion(v){ state.ver = v; renderSide(); drawAdmin(state.iso, false);
  location.hash = [state.iso, state.hz, v].join('/'); }

// ---------- sidebar
function renderSide(){
  const c = L[state.iso];
  const crumb = `<div class='crumb'><a onclick='goWorld()'>World</a> › ` +
    (state.hz ? `<a onclick='selectCountry("${state.iso}", null)'>${esc(c.name)}</a> › <span style='text-transform:capitalize'>${esc(state.hz)}</span>` : `<b>${esc(c.name)}</b>`) + `</div>`;
  if(!state.hz){
    side.innerHTML = crumb + `<h3>${esc(c.name)}</h3><div class='muted'>${esc(c.region||'')} · ${c.fws.length} framework${c.fws.length>1?'s':''} — select one</div>` +
      `<div class='fwlist'>` + c.fws.map(f => {
        const v = f.versions.find(x=>x.v===f.current);
        const nAct = f.activations.length;
        return `<div class='fcardx' style='--hz:${hzColor(f.hazard)}' onclick='selectFramework("${f.hazard}")'>
          <div class='fhead'><b>${esc(f.hazard)}</b><span class='st ${stCls(f.status)}'>${stTxt(f.status)}</span></div>
          <table class='mini'>
           <tr><td class='lbl'>Current version</td><td>${f.current ? `<code>${f.current}</code> <span class='muted'>(${f.versions.length} total)</span>` : '<span class="muted">none endorsed yet</span>'}</td></tr>
           <tr><td class='lbl'>Pre-arranged</td><td>${money(f.prearranged)}${f.prearranged_year?` <span class='muted'>(${f.prearranged_year})</span>`:''}</td></tr>
           <tr><td class='lbl'>People covered</td><td>${num(f.covered)}</td></tr>
           <tr><td class='lbl'>Activations</td><td>${nAct||'—'}</td></tr>
           <tr><td class='lbl'>Monitoring</td><td>${monthStrip(v ? v.months : [])}</td></tr>
          </table></div>`; }).join('') + `</div>`;
    return;
  }
  const f = c.fws.find(x=>x.hazard===state.hz); if(!f){ state.hz=null; return renderSide(); }
  if(!f.versions.length){
    side.innerHTML = crumb + fwHeader(c, f) + `<p class='muted'>No endorsed version anywhere yet — a pipeline framework. Status comes from colleagues' tracking sheets.</p>` +
      activationsBlock(f, null) + `<p><a href='${f.page}'>framework page →</a></p>`;
    return;
  }
  const ver = state.ver || f.current; state.ver = ver;
  const v = f.versions.find(x=>x.v===ver) || f.versions[f.versions.length-1];
  const isCur = v.v === f.current;
  side.innerHTML = crumb + fwHeader(c, f) + versionBar(f, v, isCur) +
    (isCur ? '' : `<div class='warnbox'>Viewing a <b>${esc(v.status||'past')}</b> version. The map shows this version's scope. Current version: <a onclick='selectVersion("${f.current}")' style='cursor:pointer;color:#1d5aa8'>${f.current}</a>.</div>`) +
    factsBlock(f, v) + triggersBlock(v) + fundingBlock(v) + activationsBlock(f, v) + scopeBlock(v) +
    `<p class='small' style='margin-top:12px'><a href='${f.page}'>full framework page →</a> · <a href='hierarchy.html'>explorer</a></p>`;
}
function fwHeader(c, f){
  return `<h3><span class='hzdot' style='background:${hzColor(f.hazard)}'></span>${esc(c.name)} — <span style='text-transform:capitalize'>${esc(f.hazard)}</span></h3>
   <div><span class='st ${stCls(f.status)}'>${stTxt(f.status)}</span> <span class='muted'>${f.kb?`· KB <code>${f.kb}</code>`:''}</span></div>`;
}
function versionBar(f, v, isCur){
  const opts = [...f.versions].reverse().map(x=>`<option value='${x.v}' ${x.v===v.v?'selected':''}>${x.v}${x.v===f.current?' (in force)':''} — ${stTxt(x.status)}</option>`).join('');
  return `<div class='verbar'><label class='small'>Version</label><select onchange='selectVersion(this.value)'>${opts}</select>
    ${v.doc_url ? `<a class='docbtn' href='${esc(v.doc_url)}' target='_blank' rel='noopener' title='${esc(v.doc_title||'')}'>Framework document ↗</a>` : `<span class='st st-off'>no document link</span>`}</div>`;
}
function monthStrip(months){ months = months||[]; return [...MONL].map((m,i)=>`<span class='mm ${months.includes(i+1)?'on':''}'>${m}</span>`).join(''); }
function factsBlock(f, v){
  const rows = [];
  rows.push(['Status', `<span class='st ${stCls(v.status)}'>${stTxt(v.status)}</span>${v.endorsed_by?` <span class='muted'>endorsed by ${esc(v.endorsed_by)}</span>`:''}`]);
  rows.push(['Valid', `${v.valid_from||'?'} → ${v.valid_until||'<span class="muted">open</span>'}${v.valid_until_source?` <span class='muted'>(${esc(v.valid_until_source)})</span>`:''}`]);
  if(v.doc_title) rows.push(['Document', `${esc(v.doc_title)}${v.doc_date?` <span class='muted'>(${v.doc_date})</span>`:''}`]);
  rows.push(['Pre-arranged', `${money(v.prearranged_doc)}${v.regional?` <span class='muted'>· regional document total (all countries)</span>`:''}${v.all_in===false?` <span class='muted'>· split budget per window</span>`:v.all_in===true?` <span class='muted'>· all-in</span>`:''}`]);
  if(v.cofin) rows.push(['Co-financing', `${money(v.cofin)}${v.cofin_sources.length?` <span class='muted'>${esc(v.cofin_sources.join(', '))}</span>`:''}`]);
  if(v.target_people) rows.push(['People targeted', num(v.target_people)]);
  if(f.covered && f.current===v.v) rows.push(['People covered', `${num(f.covered)} <span class='muted'>(tracking sheet)</span>`]);
  rows.push(['Monitored', `${monthStrip(v.months)}${v.months_src?` <span class='muted'>${esc(v.months_src)}</span>`:''}${v.months_note?`<div class='small' style='margin-top:3px'>${esc(v.months_note)}</div>`:''}`]);
  if(v.basis||v.indicators.length) rows.push(['Trigger basis', `${esc(v.basis||'')}${v.calibration?` · ${esc(v.calibration)}`:''}${v.indicators.length?`<div class='chips'>${v.indicators.map(i=>`<span>${esc(i)}</span>`).join('')}</div>`:''}`]);
  if(v.agencies.length) rows.push(['Agencies', esc(v.agencies.join(', '))]);
  if(v.supersedes) rows.push(['Supersedes', `<a onclick='selectVersion("${esc(v.supersedes)}")' style='cursor:pointer;color:#1d5aa8'>${esc(v.supersedes)}</a>`]);
  return `<table class='mini' style='margin-top:6px'>${rows.map(([k,val])=>`<tr><td class='lbl'>${k}</td><td>${val}</td></tr>`).join('')}</table>`;
}
function triggersBlock(v){
  let html = '';
  if(v.triggers.length){
    html += `<h4>Triggers (${v.triggers.length} window${v.triggers.length>1?'s':''})</h4>`;
    v.triggers.forEach(t => {
      const name = t.window || t.trigger || t.component || Object.values(t)[0];
      const sub = [t.basin, t.basis, t.country].filter(Boolean).join(' · ');
      const ind = t.indicator || t.indicators || '';
      const thr = t.threshold || t.condition || '';
      const meta = [t['lead time'] ? `lead ${t['lead time']}` : null, t['return period'] ? `RP ${t['return period']}` : null,
                    t.releases ? `releases: ${t.releases}` : null].filter(Boolean);
      const fired = v.windows.find(w => sameWin(w.name, name));
      html += `<div class='trig'><div class='tn'>${esc(name)}${sub?` <span class='muted'>· ${esc(sub)}</span>`:''}</div>
        <div class='tt'>${esc(ind)}${ind&&thr?' — ':''}<b>${esc(thr)}</b></div>
        ${meta.length?`<div class='tm'>${esc(meta.join(' · '))}</div>`:''}
        ${fired?`<div class='tm'>backtest: ${fired.rp?`1-in-${fired.rp.toFixed(1)} yr`:''}${fired.prob?` · ${(fired.prob*100).toFixed(0)}%/yr`:''}${fired.sim!=null?` · ${fired.sim} in ${fired.years} yrs`:''}${fired.budget?` · budget ${money(fired.budget)}`:''}</div>`:''}
      </div>`;
    });
  }
  const extra = v.windows.filter(w => !v.triggers.some(t => sameWin(w.name, t.window || t.trigger || Object.values(t)[0])));
  if(extra.length){
    html += `<h4>${v.triggers.length?'Other backtested windows':'Windows (backtest registry)'}</h4><table class='mini'><tr><th>window</th><th>basis</th><th>budget</th><th>return period</th><th>annual prob</th></tr>` +
      extra.map(w=>`<tr><td>${esc(w.name)}</td><td>${esc(w.basis||'')}${w.all_in===true?' · all-in':''}</td><td class='num'>${money(w.budget)}</td><td class='num'>${w.rp?w.rp.toFixed(1)+' yr':''}</td><td class='num'>${w.prob?(w.prob*100).toFixed(0)+'%':''}</td></tr>`).join('') + `</table>`;
  }
  if(!html) html = `<h4>Triggers</h4><div class='muted'>No structured trigger information for this version yet — see the framework document.</div>`;
  return html;
}
function sameWin(a, b){ if(!a||!b) return false; a=String(a).toLowerCase().replace(/[^a-z0-9]+/g,' ').trim(); b=String(b).toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
  return a===b || a.includes(b) || b.includes(a); }
function fundingBlock(v){
  const F = v.funding; if(!F.agency.length && !F.sector.length && !F.fund.length) return '';
  const funds = [...new Set(F.fund.map(x=>x.fund))];
  let html = `<h4>Budget by agency ${F.src==='sheet'?'<span class="muted" style="text-transform:none">(tracking sheet)</span>':''}</h4>`;
  if(F.agency.length){
    const ags = [...new Set(F.agency.map(x=>x.agency))];
    const cell = (a,fd) => F.agency.filter(x=>x.agency===a&&x.fund===fd).reduce((s,x)=>s+x.usd,0);
    const tot = a => F.agency.filter(x=>x.agency===a).reduce((s,x)=>s+x.usd,0);
    ags.sort((a,b)=>tot(b)-tot(a));
    html += `<table class='mini'><tr><th>agency</th>${funds.length>1?funds.map(fd=>`<th class='num'>${esc(fd)}</th>`).join(''):''}<th class='num'>total</th></tr>` +
      ags.map(a=>`<tr><td>${esc(a)}</td>${funds.length>1?funds.map(fd=>`<td class='num'>${cell(a,fd)?money(cell(a,fd)):''}</td>`).join(''):''}<td class='num'><b>${money(tot(a))}</b></td></tr>`).join('') +
      `<tr><td class='lbl'>total</td>${funds.length>1?funds.map(fd=>`<td class='num'>${money(F.fund.find(x=>x.fund===fd)?.usd)}</td>`).join(''):''}<td class='num'><b>${money(F.agency.reduce((s,x)=>s+x.usd,0))}</b></td></tr></table>`;
    const noAgency = F.fund.reduce((s,x)=>s+x.usd,0) - F.agency.reduce((s,x)=>s+x.usd,0);
    if(noAgency > 1000) html += `<div class='small'>+ ${money(noAgency)} not attributed to an agency (${F.fund.filter(fd=>!F.agency.some(a=>a.fund===fd.fund)).map(fd=>esc(fd.fund)).join(', ')||'see sectors'})</div>`;
  } else if(F.fund.length){
    html += `<table class='mini'>${F.fund.map(x=>`<tr><td>${esc(x.fund)}</td><td class='num'>${money(x.usd)}</td></tr>`).join('')}</table>`;
  }
  if(F.sector.length){
    const secs = {}; F.sector.forEach(x=>secs[x.sector]=(secs[x.sector]||0)+x.usd);
    html += `<details style='margin-top:6px'><summary class='small' style='cursor:pointer'>by sector</summary><table class='mini'>` +
      Object.entries(secs).sort((a,b)=>b[1]-a[1]).map(([s,u])=>`<tr><td>${esc(s)}</td><td class='num'>${money(u)}</td></tr>`).join('') + `</table></details>`;
  }
  return html;
}
function activationsBlock(f, v){
  const A = f.activations;
  let html = `<h4>Activations — all versions (${A.length})</h4>`;
  if(!A.length) return html + `<div class='muted'>Never activated.</div>`;
  const byWin = {};
  A.forEach(a => { const k = a.version && v && a.version===v.v ? (a.window||'unspecified window') : null; if(k) (byWin[k] ??= []).push(a); });
  if(v && Object.keys(byWin).length){
    html += `<div class='small' style='margin-bottom:4px'>Under this version, by trigger: ` +
      Object.entries(byWin).map(([w,as])=>`<b>${esc(w)}</b> ×${as.length}`).join(' · ') + `</div>`;
  }
  html += A.map(a => {
    const other = v ? (a.version !== v.v) : false;
    const funding = a.funding.filter(x=>x.usd!=null||x.code).map(x=>`${esc(x.fund)}: ${money(x.usd)}${x.code?` <span class='muted'>(${esc(x.code)})</span>`:''}`).join('<br>');
    return `<div class='actrow' ${other?"style='opacity:.85'":''}>
      <div class='ah'><span class='ad'>${a.date}${a.type!=='framework_aa'?` <span class='st st-off'>${esc(a.type.replace(/_/g,' '))}</span>`:''}${a.full===false?` <span class='st st-dev'>partial</span>`:''}</span>
        ${a.version ? `<span class='vtag ${other?'other':''}' title='${other?'fired under a different version than the one displayed':'fired under the displayed version'}'>${other?'under ':''}${a.version}</span>` : `<span class='vtag other'>no version</span>`}</div>
      <div class='small'>${a.window?esc(a.window):'<span class="muted">window not recorded</span>'}</div>
      <div class='small'>${funding||(a.released?`released ${money(a.released)}`:'<span class="muted">funding not recorded</span>')}${a.people?` · ${num(a.people)} people targeted`:''}${a.url?` · <a href='${esc(a.url)}' target='_blank' rel='noopener'>source ↗</a>`:''}</div>
    </div>`; }).join('');
  return html;
}
function scopeBlock(v){
  const s = v.scope; if(!s) return '';
  let html = `<h4>Geographic scope${v.admin_level!=null?` <span class='muted' style='text-transform:none'>(trigger at admin ${v.admin_level})</span>`:''}</h4>`;
  if(s.national) html += `<div class='scopelist'>National trigger — whole country shaded.</div>`;
  if(v.scope_raw.length) html += `<div class='scopelist'>${v.scope_raw.map(x=>esc(x)).join(' · ')}</div>`;
  if(!s.national && !v.scope_raw.length) html += `<div class='muted'>Scope not extracted for this version yet.</div>`;
  if(s.unmatched.length) html += `<div class='small' style='margin-top:4px;color:#8a5c0a'>Not on the map (no boundary match): ${s.unmatched.map(esc).join('; ')}</div>`;
  return html;
}

// deep link  #ISO/hazard/version
(function(){ const h = location.hash.replace('#','').split('/'); if(h[0] && L[h[0]]) selectCountry(h[0], h[1]||null, h[2]||null); })();
"""
