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
# visible crop of the world (the portfolio spans roughly lon -108..182, lat 50..-40)
VB_X = (-108 + 180) / 360 * W
VB_W = (182 + 108) / 360 * W
VB_Y = (LAT_TOP - 50) / (LAT_TOP - LAT_BOT) * H
VB_H = (50 + 40) / (LAT_TOP - LAT_BOT) * H

import datetime as _dt

# Lifecycle colours, glyphs, callout directions and centroids mirror the KB public map
# (ds-knowledge-base/scripts/gen_public_site.py) so the two sites read the same.
KB_COLOR = {"endorsed": "#2171b5", "recently-triggered": "#e0706a", "expired": "#b2a56e",
            "development": "#9ecae1", "retired": "#b6bcc4"}
KB_LABEL = {"endorsed": "Active", "recently-triggered": "Recently triggered", "expired": "Expired",
            "development": "In development", "retired": "Retired / dormant"}
HAZ_COLOR = {"flood": "#2a78d6", "drought": "#eb6834", "storm": "#8e5bd9",
             "cholera": "#1baf7a", "plague": "#b8860b"}
HAZ_LABEL = {"storm": "Trop. cyclones", "flood": "Floods", "drought": "Drought",
             "cholera": "Cholera", "plague": "Plague"}
HAZ_GLYPH = {"storm": "tropical-cyclone", "flood": "flood", "drought": "drought",
             "cholera": "cholera"}
HAZARD_SVG = {
    "drought": '<circle cx="12" cy="12" r="3.6" fill="#fff"/><g stroke="#fff" stroke-width="1.7" stroke-linecap="round">'
               '<line x1="12" y1="2.5" x2="12" y2="5.5"/><line x1="12" y1="18.5" x2="12" y2="21.5"/>'
               '<line x1="2.5" y1="12" x2="5.5" y2="12"/><line x1="18.5" y1="12" x2="21.5" y2="12"/>'
               '<line x1="5.2" y1="5.2" x2="7.3" y2="7.3"/><line x1="16.7" y1="16.7" x2="18.8" y2="18.8"/>'
               '<line x1="18.8" y1="5.2" x2="16.7" y2="7.3"/><line x1="7.3" y1="16.7" x2="5.2" y2="18.8"/></g>',
    "flood": '<g fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round">'
             '<path d="M2 8.5c2 0 2 2 4 2s2-2 4-2 2 2 4 2 2-2 4-2 2 2 4 2"/>'
             '<path d="M2 13.5c2 0 2 2 4 2s2-2 4-2 2 2 4 2 2-2 4-2 2 2 4 2"/>'
             '<path d="M2 18.5c2 0 2 2 4 2s2-2 4-2 2 2 4 2 2-2 4-2 2 2 4 2"/></g>',
    "tropical-cyclone": '<circle cx="12" cy="12" r="2.2" fill="#fff"/>'
             '<g fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round">'
             '<path d="M12 4.2c4.2 0 7 2.1 7 5 0 2-1.8 3.2-4 3.2"/>'
             '<path d="M12 19.8c-4.2 0-7-2.1-7-5 0-2 1.8-3.2 4-3.2"/></g>',
    "cholera": '<circle cx="12" cy="12" r="3.2" fill="#fff"/>'
             '<g stroke="#fff" stroke-width="1.6" stroke-linecap="round">'
             '<line x1="12" y1="4" x2="12" y2="6.4"/><line x1="12" y1="17.6" x2="12" y2="20"/>'
             '<line x1="4" y1="12" x2="6.4" y2="12"/><line x1="17.6" y1="12" x2="20" y2="12"/>'
             '<line x1="6.3" y1="6.3" x2="8" y2="8"/><line x1="16" y1="16" x2="17.7" y2="17.7"/>'
             '<line x1="17.7" y1="6.3" x2="16" y2="8"/><line x1="8" y1="16" x2="6.3" y2="17.7"/></g>'
             '<g fill="#fff"><circle cx="12" cy="3.6" r="1.1"/><circle cx="12" cy="20.4" r="1.1"/>'
             '<circle cx="3.6" cy="12" r="1.1"/><circle cx="20.4" cy="12" r="1.1"/></g>',
    "other": '<circle cx="12" cy="12" r="3.5" fill="#fff"/>',
}
CENTROID = {   # iso3 -> (lat, lon) for the callout anchor dot
    "AFG": (33.9, 67.7), "BFA": (12.2, -1.6), "BGD": (23.7, 90.4), "COD": (-2.9, 23.6),
    "CUB": (21.7, -79.5), "ETH": (9.1, 40.5), "FJI": (-17.7, 178.0), "GTM": (15.7, -90.2),
    "HND": (15.0, -86.5), "HTI": (19.0, -72.3), "KEN": (0.2, 37.9), "MDG": (-18.8, 46.9),
    "MMR": (21.0, 96.0), "MOZ": (-18.0, 35.5), "MRT": (20.5, -10.9), "MWI": (-13.3, 34.3),
    "NIC": (12.9, -85.2), "NER": (17.6, 9.4), "NGA": (9.1, 8.7), "NPL": (28.2, 84.0),
    "PHL": (12.9, 121.8), "PLW": (7.5, 134.6), "SLV": (13.8, -88.9), "SOM": (5.2, 46.2),
    "SSD": (7.3, 30.3), "TCD": (15.5, 18.7), "VUT": (-16.5, 168.0), "YEM": (15.6, 48.0),
    "CMR": (5.7, 12.4), "MLI": (17.6, -4.0), "PAK": (30.4, 69.3), "SDN": (15.6, 30.2),
    "SYR": (35.0, 38.5), "TON": (-21.2, -175.2), "ZWE": (-19.0, 29.9),
}
DIRECTIONS = {   # preferred callout direction (screen vector, +y down)
    "AFG": (0.2, -1), "BFA": (-1, 0.2), "BGD": (0.7, -0.8), "COD": (-0.6, 1),
    "CUB": (-0.9, -0.4), "ETH": (0.7, -0.5), "FJI": (-0.6, 0.8), "GTM": (-1, -0.3),
    "HND": (0.3, 1), "HTI": (1, 0.3), "KEN": (1, 0.25), "MDG": (1, 0.1),
    "MMR": (0.8, 0.5), "MOZ": (0.6, 0.8), "MRT": (-0.85, -0.5), "MWI": (-0.9, 0.3),
    "NER": (-0.2, -1), "NGA": (-0.6, 0.85), "NIC": (0.9, 0.6), "NPL": (0.1, -1),
    "PHL": (1, -0.1), "SLV": (-0.8, 0.7), "SOM": (1, 0.2), "SSD": (-0.5, -0.8),
    "TCD": (0.5, -1), "VUT": (-0.7, -0.5), "YEM": (1, -0.1), "CMR": (-0.9, 0.6),
    "MLI": (-0.3, -1), "PAK": (-0.6, -0.8), "SDN": (0.3, -1), "SYR": (0.9, -0.5),
}
# tracking-sheet statuses for frameworks without a KB version -> KB lifecycle bucket;
# conversation stages are not frameworks yet and stay off the map
SHEET_BUCKET = {"active": "endorsed", "activated_implementing": "endorsed",
                "monitoring": "endorsed", "under_development": "development",
                "under_revision": "development", "project_finalization": "development",
                "dormant": "retired", "expired": "expired", "retired": "retired"}
TODAY = _dt.date.today()

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


def svg_world(shown_iso, country_names):
    """World SVG in the KB style: framework countries light blue, the rest grey."""
    gj = json.loads((ROOT / "site_src" / "countries.geo.json").read_text())
    paths, bboxes = [], {}
    for f in gj["features"]:
        iso = f.get("id")
        if iso == "ATA":
            continue
        if iso == "-99" and f["properties"].get("name") == "Somaliland":
            iso = "SOM"                                   # fold into Somalia (KB does the same)
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        d = "".join(_ring_d(r[::2] or r) for poly in polys for r in poly)
        on = iso in shown_iso
        nm = country_names.get(iso, f["properties"].get("name", iso))
        paths.append(f"<path class='{'cty on' if on else 'cty'}' data-iso='{iso}' data-name='{nm}' d='{d}'/>")
        big = max(polys, key=lambda p: len(p[0]))
        xs = [c[0] for c in big[0]]; ys = [c[1] for c in big[0]]
        b = [min(xs), min(ys), max(xs), max(ys)]
        if iso in bboxes:                                  # union of folded features
            o = bboxes[iso]
            b = [min(o[0], b[0]), min(o[1], b[1]), max(o[2], b[2]), max(o[3], b[3])]
        bboxes[iso] = b
    svg = (f"<svg id='map' viewBox='{VB_X:.1f} {VB_Y:.1f} {VB_W:.1f} {VB_H:.1f}' preserveAspectRatio='xMidYMid meet'>"
           f"<rect id='sea' x='{VB_X-W}' y='{VB_Y-H}' width='{3*W}' height='{3*H}' fill='transparent'/>"
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
        """SELECT w.country_iso3, w.hazard, w.version, w.window_name, w.all_in,
                  w.basis, w.allocation_usd, p.n_activations AS sim_activations,
                  p.analysis_years, p.return_period, p.activation_prob
           FROM aa.window w LEFT JOIN aa.v_window_performance p
             USING (country_iso3, hazard, version, window_name)""", e)
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
            w_v = win[(win["country_iso3"] == c) & (win["hazard"] == h)
                      & kb_key_match(win["version"], v.version)]
            windows = [{"name": w.window_name, "basis": _s(w.basis), "all_in": _f(w.all_in),
                        "budget": _num(w.allocation_usd), "rp": _num(w.return_period),
                        "prob": _num(w.activation_prob), "sim": _num(w.sim_activations),
                        "years": _num(w.analysis_years)} for w in w_v.itertuples()]
            # budget breakdown: KB funding_breakdown for this version, else sheet sector budget
            f_v = fb[(fb["country_iso3"] == c) & (fb["hazard"] == h)
                     & (fb["version"] == v.version)]
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
                "n_windows": tf.get("n_windows") if isinstance(tf.get("n_windows"), int) else None,
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

        # the map and the sidebar default to the MOST RECENT version (as the KB map does);
        # the tracking view's in-force version is kept for reference
        latest = versions[-1]["v"] if versions else None
        in_force = _s(r.get("current_version"))
        if in_force not in {x["v"] for x in versions}:
            in_force = latest
        sheet_status = _s(r.get("status"))
        disp = lifecycle(versions[-1] if versions else None, sheet_status, activations)
        if disp is None:
            continue                                  # conversation stage: not on the map
        able = able_to_trigger(versions[-1] if versions else None, h, disp)
        months_now = (versions[-1]["months"] if versions else [])
        ring = None
        if able:
            ring = "now" if TODAY.month in months_now else "able"
        n_fw_act = sum(1 for a in activations if a["type"] == "framework_aa")
        countries[c]["fws"].append({
            "hazard": h, "status": sheet_status, "kb": kb_fw,
            "disp": disp, "disp_label": KB_LABEL[disp], "ring": ring, "n_act": n_fw_act,
            "hz_label": HAZ_LABEL.get(h, h.replace("_", " ").capitalize()),
            "glyph": HAZ_GLYPH.get(h, "other"),
            "latest": latest, "in_force": in_force,
            "page": f"fw-{c.lower()}-{h}.html",
            "prearranged": _num(r.get("cerf_prearranged_usd")),
            "prearranged_year": _num(r.get("prearranged_year")),
            "covered": _num(r.get("people_covered")),
            "current": latest, "versions": versions, "activations": activations,
        })
    return {iso: cd for iso, cd in countries.items() if cd["fws"]}


def _expired(valid_until):
    if not valid_until:
        return False
    m = re.match(r"(\d{4})(?:-(\d{1,2}))?", str(valid_until))
    if not m:
        return False
    mo = int(m.group(2)) if m.group(2) and 1 <= int(m.group(2)) <= 12 else 12
    return (int(m.group(1)), mo) < (TODAY.year, TODAY.month)


def lifecycle(latest, sheet_status, activations):
    """KB display status of the most recent version (None = not shown on the map)."""
    if latest is None:
        if sheet_status in (None, "early_conversations", "advanced_conversations"):
            return None
        return SHEET_BUCKET.get(sheet_status, "development")
    st = latest["status"] or ""
    if st in ("development", "pre-development"):
        return "development"
    if st in ("retired", "superseded"):
        return "retired"
    if any(a["version"] == latest["v"] and a["type"] == "framework_aa" for a in activations):
        return "recently-triggered"
    if _expired(latest["valid_until"]):
        return "expired"
    return "endorsed"


def able_to_trigger(latest, hazard, disp):
    if disp not in ("endorsed", "recently-triggered"):
        return False
    if disp == "recently-triggered":
        cholera = hazard == "cholera"
        split = latest is not None and (latest["n_windows"] or 0) > 1 and latest["all_in"] is False
        return cholera or split
    return True


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
        for f in cd["fws"]:
            prev = None
            for v in f["versions"]:
                sc = v["scope"]
                if not sc["pcodes"] and not sc["national"] and prev is not None:
                    v["scope"] = dict(prev, inherited_from=prev["from"])
                elif sc["pcodes"] or sc["national"]:
                    prev = dict(sc, **{"from": v["v"]})
        if m is not None:
            b = write_country_geo(iso, m, adm0)
            if b is not None:
                bboxes[iso] = [float(x) for x in b]
        cd["bbox"] = bboxes.get(iso)
        cd["has_geo"] = m is not None


# ---------------------------------------------------------------- page
def build_landing(page, d, e):
    cur = d["current"]
    names = dict(zip(cur["country_iso3"], cur["country_name"]))
    countries = assemble(d, e)
    svg, bboxes = svg_world(set(countries), names)
    for iso, cd in countries.items():
        cd["lbbox"] = bboxes.get(iso)                 # layout box (world file, largest polygon)
        cd["centroid"] = CENTROID.get(iso) or (
            [(cd["lbbox"][1] + cd["lbbox"][3]) / 2, (cd["lbbox"][0] + cd["lbbox"][2]) / 2]
            if cd["lbbox"] else None)
        cd["dir"] = DIRECTIONS.get(iso, (0.7, -0.7))
    geo_pass(countries, bboxes)

    act = d["activation"]
    n_active = int(cur["status"].isin(["active", "activated_implementing"]).sum())
    pre = d["prearranged"]
    total_pre = pre.loc[(pre["kind"] == "prearranged") & (pre["year"] == 2026)
                        & (pre["fund_code"] != "all"), "amount_usd"].sum()
    n_act_all = act["event_date"].nunique()
    covered = d["covered"]["people_covered"].sum()
    n_shown = sum(len(cd["fws"]) for cd in countries.values())

    body = f"""
<div class='hero'>
 <p>Published triggers, windows, pre-arranged financing and activations across the AA
 portfolio — CERF, country-based and regional pooled funds. Pin colour = lifecycle status of
 the most recent version; each red dot = one past activation. <b>Click a country or a pin</b>
 to zoom in and see the areas each framework covers.</p>
 <div class='tiles'>
  <div class='tile'><div class='v'>{n_active}</div><div class='l'>active frameworks ({n_shown} on the map, {len(cur)} tracked)</div></div>
  <div class='tile'><div class='v'>${total_pre/1e6:,.0f}M</div><div class='l'>pre-arranged (2026)</div></div>
  <div class='tile'><div class='v'>{n_act_all}</div><div class='l'>activations since 2020</div></div>
  <div class='tile'><div class='v'>{covered/1e6:,.1f}M</div><div class='l'>people covered</div></div>
 </div>
</div>
<div class='maprow' id='maprow'>
 <div class='mapbox' id='mapbox'>
  <button id='back' class='backbtn' hidden>← world</button>
  <div id='tip' class='tip' hidden></div>
  {svg}
  <div id='lpane' class='labelpane'><svg id='leaders' class='leadersvg'></svg></div>
  <div class='maplegend' id='legend'></div>
 </div>
 <div class='side' id='side'>
  <div class='muted' style='padding:20px 6px'>Select a country or a pin to see its
  frameworks — status, funding, monitoring window, triggers, versions and activations.</div>
 </div>
</div>
<div class='tiles' style='margin-top:18px'>
 <div class='tile'><a href='dashboards.html'><b>Dashboards</b></a><div class='l'>funding · allocations · delivery</div></div>
 <div class='tile'><a href='hierarchy.html'><b>Portfolio explorer</b></a><div class='l'>framework › version › window › activation</div></div>
 <div class='tile'><a href='entry.html'><b>Enter / ingest a framework</b></a><div class='l'>upload a PDF or fill the form — writes to the DB</div></div>
 <div class='tile'><a href='overview.html'><b>Data &amp; schema review</b></a><div class='l'>tables · reconciliation · roadmap</div></div>
</div>
<script>window.L = {json.dumps(countries, default=str)};
window.HAZ = {json.dumps(HAZ_COLOR)}; window.COLOR = {json.dumps(KB_COLOR)};
window.KBLABEL = {json.dumps(KB_LABEL)}; window.GLYPH = {json.dumps(HAZARD_SVG)};
window.MAPW={W}; window.MAPH={H}; window.LATT={LAT_TOP}; window.LATB={LAT_BOT};
window.VB = {{x:{VB_X:.2f}, y:{VB_Y:.2f}, w:{VB_W:.2f}, h:{VB_H:.2f}}};
window.CURMONTH = {json.dumps(TODAY.strftime("%B %Y"))};</script>
<script>{LANDING_JS}</script>
<style>{LANDING_CSS}</style>"""
    page("index.html", "OCHA Anticipatory Action — portfolio", body)


LANDING_CSS = r"""
:root { --ocha:#1a6bb5; --ink:#222; --muted:#777; --line:#e3e6ea; }
.hero { text-align:left; padding:6px 0 2px; }
.hero p { color:#556; max-width:860px; font-size:13.5px; }
.tiles { display:flex; gap:14px; flex-wrap:wrap; margin:12px 0; }
.tile { background:#fff; border:1px solid var(--line); border-radius:8px; padding:12px 18px; min-width:150px; box-shadow:0 1px 3px rgba(0,0,0,.05); }
.tile .v { font-size:22px; font-weight:700; } .tile .l { font-size:12px; color:var(--muted); }
.tile a { color:var(--ocha); }
/* the sidebar slides in only when a country is selected, so the world view keeps the full width */
.maprow { display:grid; grid-template-columns: minmax(0,1fr) 0px; gap:0; align-items:start;
  transition: grid-template-columns .55s cubic-bezier(.22,.8,.2,1), gap .55s; }
.maprow.open { grid-template-columns: minmax(0,1fr) 380px; gap:16px; }
.maprow .side { opacity:0; visibility:hidden; transition: opacity .3s; }
.maprow.open .side { opacity:1; visibility:visible; transition: opacity .4s .25s; }
@media (max-width: 1000px) { .maprow, .maprow.open { grid-template-columns: 1fr; gap:16px; } }
.mapbox { background:#fff; border-radius:8px; box-shadow:0 1px 3px rgba(0,0,0,.08); position:relative; overflow:hidden; }
#map { width:100%; height:auto; display:block; background:#fff; }
.cty { fill:#ebedf0; stroke:#d3d7dc; stroke-width:.5; vector-effect:non-scaling-stroke; transition: opacity .5s, fill .5s; }
.cty.on { fill:#cfe0f2; stroke:#9cc0e3; stroke-width:.8; cursor:pointer; }
.cty.on:hover { fill:#bcd4ee; }
#map.zoomed .cty { opacity:.35; } #map.zoomed .cty.on { opacity:.55; } #map.zoomed .cty.sel { opacity:0; }
.a0 { fill:#fff; stroke:#39506b; stroke-width:1.4; vector-effect:non-scaling-stroke; }
.a1 { fill:#eef3f9; stroke:#9cc0e3; stroke-width:.8; vector-effect:non-scaling-stroke; }
.a1:hover { fill:#e0eaf6; }
.sc { stroke:#fff; stroke-width:.8; vector-effect:non-scaling-stroke; fill-opacity:.8; cursor:pointer; transition: fill-opacity .3s; }
.sc:hover { fill-opacity:1; }
.nat { fill-opacity:.35; pointer-events:none; }
#adm { opacity:0; transition: opacity .5s ease .35s; } #adm.show { opacity:1; }
/* callouts (KB style) */
.labelpane { position:absolute; inset:0; pointer-events:none; transition: opacity .35s; }
.labelpane.hide { opacity:0; }
.leadersvg { position:absolute; inset:0; width:100%; height:100%; overflow:visible; }
.leader { stroke:#8a99a8; stroke-width:1; }
.cdot { fill:#39506b; stroke:#fff; stroke-width:1.5; }
.callout { position:absolute; display:flex; flex-direction:column; align-items:flex-start; pointer-events:auto; visibility:hidden; }
.cname { font-weight:700; font-size:11px; color:#16324f; white-space:nowrap; line-height:1.15; margin-bottom:1px; cursor:pointer; }
.cname:hover { text-decoration:underline; }
.hrow { display:flex; align-items:center; gap:4px; margin:1px 0; }
.hlab { font-size:10px; font-weight:400; color:#1c3550; white-space:nowrap; line-height:1.15; }
.iconbox { position:relative; display:inline-flex; align-items:center; justify-content:center; width:22px; height:22px;
  border-radius:6px; border:1.5px solid #fff; box-shadow:0 1px 3px rgba(0,0,0,.4); cursor:pointer; flex:none; }
.iconbox svg.hz { width:15px; height:15px; display:block; }
.iconbox:hover { filter:brightness(1.08); }
@keyframes ablepulse {
  0%   { box-shadow: 0 0 0 2px #f5a300, 0 0 0 0 rgba(245,163,0,.85), 0 1px 3px rgba(0,0,0,.4); }
  65%  { box-shadow: 0 0 0 2px #f5a300, 0 0 0 11px rgba(245,163,0,0), 0 1px 3px rgba(0,0,0,.4); }
  100% { box-shadow: 0 0 0 2px #f5a300, 0 0 0 11px rgba(245,163,0,0), 0 1px 3px rgba(0,0,0,.4); } }
.iconbox.able-now { box-shadow:0 0 0 2px #f5a300, 0 1px 3px rgba(0,0,0,.4); animation:ablepulse 1.1s ease-out infinite; }
.iconbox.able-off { box-shadow:0 0 0 2px #f6c95f, 0 1px 3px rgba(0,0,0,.4); }
.actdots { position:absolute; top:-5px; right:-4px; display:flex; flex-direction:row-reverse; gap:1px; }
.actdot { width:7px; height:7px; border-radius:50%; background:#e3322d; border:1.5px solid #fff; display:inline-block; }
.maplegend { position:absolute; left:10px; bottom:10px; font-size:12px; line-height:1.5; background:#fff; padding:7px 9px;
  border-radius:6px; box-shadow:0 1px 4px rgba(0,0,0,.2); z-index:3; transition: opacity .3s; }
.maplegend .dot { display:inline-block; width:12px; height:12px; border-radius:50%; margin-right:5px; vertical-align:-1px; }
.maplegend .sq { display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:5px; vertical-align:-1px; }
.backbtn { position:absolute; top:10px; left:10px; z-index:4; padding:5px 12px; border:1px solid #cfd6de;
  border-radius:16px; background:#fff; cursor:pointer; font-size:12.5px; box-shadow:0 1px 3px rgba(0,0,0,.12); }
.tip { position:absolute; z-index:5; background:#16324f; color:#fff; font-size:12px; padding:4px 9px;
  border-radius:5px; pointer-events:none; white-space:nowrap; transform:translate(-50%,-130%); }
/* sidebar (KB info-pop styling) */
.side { background:#fff; border:1px solid #d4d8de; border-radius:8px; padding:12px 16px 16px;
  max-height:640px; overflow-y:auto; font-size:12.5px; line-height:1.45; color:var(--ink); box-shadow:0 1px 3px rgba(0,0,0,.08); }
.side a { color:var(--ocha); }
.side h3 { margin:2px 0 4px; font-size:17px; color:#16324f; } .side h4 { margin:14px 0 4px; font-size:11.5px;
  text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }
.crumb { font-size:12px; color:var(--muted); margin-bottom:8px; } .crumb a { cursor:pointer; text-decoration:none; }
.crumb a:hover { text-decoration:underline; }
.fwlist .fcardx { border:1px solid var(--line); border-radius:8px; padding:10px 12px; margin:8px 0; cursor:pointer;
  border-left:4px solid var(--hz,#999); transition: background .15s; }
.fwlist .fcardx:hover { background:#f6f9fc; }
.fhead { display:flex; justify-content:space-between; align-items:center; gap:8px; }
.fhead b { font-size:13.5px; display:inline-flex; align-items:center; gap:6px; }
.fhead .iconbox { width:20px; height:20px; cursor:default; } .fhead .iconbox svg.hz { width:13px; height:13px; }
.badge { display:inline-block; padding:1px 7px; border-radius:9px; font-size:11px; font-weight:600; white-space:nowrap; }
.b-endorsed { background:#e2f3e6; color:#1e7a37; } .b-recently-triggered { background:#fce4cd; color:#b5650a; }
.b-expired { background:#f1ead0; color:#7d6b1a; } .b-development { background:#fdf0d5; color:#9a6d0a; }
.b-retired, .b-superseded { background:#e8e8e8; color:#666; } .b-pre-development { background:#e5eefb; color:#15c; }
table.mini { border-collapse:collapse; font-size:12px; width:100%; }
table.mini td, table.mini th { padding:3px 6px; border-bottom:1px solid #eef1f5; vertical-align:top; text-align:left; }
table.mini th { font-weight:600; color:#556; background:#f1f4f7; white-space:nowrap; }
table.mini td.lbl { color:var(--muted); width:118px; white-space:nowrap; }
table.mini td.num { text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }
.mm { display:inline-grid; place-items:center; width:17px; height:17px; font-size:9px;
  border-radius:3px; background:#f0f2f5; color:#99a; margin-right:1px; }
.mm.on { background:#2171b5; color:#fff; }
.muted { color:var(--muted); font-size:12px; }
.small { font-size:11.5px; color:#556; }
.verbar { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin:8px 0 4px; }
.verbar select { padding:4px 8px; border:1px solid #bbb; border-radius:5px; font-size:12.5px; background:#fff; }
.docbtn { display:inline-block; padding:5px 11px; border-radius:5px; background:var(--ocha); color:#fff !important;
  text-decoration:none; font-size:12.5px; font-weight:600; }
.warnbox { background:#fff4d6; border:1px solid #e6cf8f; color:#6b5310; border-radius:6px; padding:6px 10px; font-size:12px; margin:8px 0; }
.trig { border:1px solid var(--line); border-radius:6px; padding:7px 10px; margin:6px 0; background:#f8fafc; }
.trig .tn { font-weight:650; color:var(--ocha); } .trig .tt { margin-top:2px; }
.trig .tm { color:var(--muted); font-size:11.5px; margin-top:3px; }
.actrow { border-bottom:1px solid #eef1f5; padding:6px 0; }
.actrow .ah { display:flex; justify-content:space-between; gap:8px; align-items:baseline; }
.actrow .ad { font-weight:650; white-space:nowrap; color:#b3261e; }
.actrow .ad a { color:#e3322d; }
.vtag { display:inline-block; font-size:10.5px; padding:0 6px; border-radius:8px; background:#eceff5; color:#4a5670; margin-left:6px; font-family:ui-monospace,monospace; }
.vtag.other { background:#fdf1dc; color:#8a5c0a; }
.chips span { display:inline-block; background:#f0f2f5; border-radius:9px; padding:0 7px; font-size:11px; margin:2px 3px 2px 0; }
.scopelist { font-size:12px; color:#334; line-height:1.5; }
"""

LANDING_JS = r"""
const MONL = 'JFMAMJJASOND';
const svg = document.getElementById('map'), world = document.getElementById('world'),
      adm = document.getElementById('adm'), side = document.getElementById('side'),
      back = document.getElementById('back'), tip = document.getElementById('tip'),
      legend = document.getElementById('legend'), lpane = document.getElementById('lpane'),
      leaders = document.getElementById('leaders'), mapbox = document.getElementById('mapbox'),
      maprow = document.getElementById('maprow');
const GEO = {};
let state = { iso:null, hz:null, ver:null };

function money(v){ return v==null ? '—' : v>=1e6 ? '$'+(v/1e6).toFixed(v>=1e7?0:1)+'M' : v>=1e3 ? '$'+Math.round(v/1e3)+'k' : '$'+Math.round(v); }
function num(v){ return v==null ? '—' : Math.round(v).toLocaleString(); }
function esc(s){ return s==null ? '' : String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function badge(st, label){ st = st || 'retired'; return `<span class='badge b-${esc(st)}'>${esc(label || KBLABEL[st] || st.replace(/_/g,' '))}</span>`; }
function verBadge(st){ st=st||''; const m = {endorsed:'endorsed', superseded:'superseded', development:'development', 'pre-development':'pre-development', retired:'retired'};
  return `<span class='badge b-${m[st]||'retired'}'>${esc(st||'?')}</span>`; }
function hzColor(h){ return HAZ[h] || '#7a8699'; }
function iconHTML(f, extra=''){ return `<span class='iconbox ${f.ring==='now'?'able-now':f.ring==='able'?'able-off':''} ${extra}' style='background:${COLOR[f.disp]}' data-hz='${f.hazard}'>`
  + `<svg viewBox='0 0 24 24' class='hz'>${GLYPH[f.glyph]||GLYPH.other}</svg>`
  + (f.n_act ? `<span class='actdots'>${'<span class="actdot"></span>'.repeat(Math.min(f.n_act,6))}</span>` : '') + `</span>`; }
function pt(lon, lat){ return [(lon+180)/360*MAPW, (LATT-lat)/(LATT-LATB)*MAPH]; }
function ringsD(rings){ return rings.map(r=>'M'+r.map(([x,y])=>{const p=pt(x,y);return p[0].toFixed(2)+','+p[1].toFixed(2);}).join('L')+'Z').join(''); }
function kpx(){ return svg.getBoundingClientRect().width / VB.w; }   // CSS px per map unit
function toPx(lon, lat){ const [x,y]=pt(lon,lat), k=kpx(); return [(x-VB.x)*k, (y-VB.y)*k]; }

// ---------- zoom (SVG transform attribute animated in user units)
let T = {tx:0, ty:0, sx:1, sy:1}, animId = null, animSeq = 0;
function applyT(t){ world.setAttribute('transform', `translate(${t.tx} ${t.ty}) scale(${t.sx} ${t.sy})`); }
function animateTo(target, ms=800){
  if(animId) cancelAnimationFrame(animId);
  if(document.hidden){ T = {...target}; applyT(T); return; }
  const seq = ++animSeq;
  setTimeout(()=>{ if(seq===animSeq){ T = {...target}; applyT(T); animId=null; } }, ms+80);
  const from = {...T}, t0 = performance.now(), ease = x => 1 - Math.pow(1 - x, 3);
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
  let s = Math.min(VB.w/(bw*cosf*pad), VB.h/(bh*pad), 60);
  const cx = (x0+x1)/2, cy = (y0+y1)/2;
  animateTo({ tx: VB.x + VB.w/2 - cx*s*cosf, ty: VB.y + VB.h/2 - cy*s, sx: s*cosf, sy: s });
}
function resetZoom(){ animateTo({tx:0, ty:0, sx:1, sy:1}, 650); }

// ---------- admin layers (country view)
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
  const paint = {}; let national = [];
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
    html += `<path class='sc' fill='${hzColor(hzs[0])}' data-n='${esc(a.n)}' data-hz='${esc(hzs.map(h=>L[iso].fws.find(f=>f.hazard===h)?.hz_label||h).join(', '))}' d='${ringsD(a.r)}'/>`;
  });
  adm.innerHTML = html;
  if(fade) void adm.getBoundingClientRect();
  adm.classList.add('show');
  const hzs = [...new Set(targets.map(f=>f.hazard))];
  legend.innerHTML = `<b>${esc(c.name)}</b><br>` + hzs.map(h=>`<span class='sq' style='background:${hzColor(h)}'></span>${esc(targets.find(f=>f.hazard===h).hz_label)} — scope of the displayed version<br>`).join('')
    + `<span class='sq' style='background:#eef3f9;border:1px solid #9cc0e3'></span>admin-1 boundaries`
    + (national.length ? `<br><span class='small'>whole country shaded = national trigger</span>` : '');
}

// ---------- world legend (KB style)
function worldLegend(){
  const fws = Object.values(L).flatMap(c=>c.fws);
  const n = k => fws.filter(f=>f.disp===k).length;
  const nAct = fws.reduce((s,f)=>s+f.n_act,0), nNow = fws.filter(f=>f.ring==='now').length, nOff = fws.filter(f=>f.ring==='able').length;
  legend.innerHTML = `<b>Framework</b><br>`
    + `<span class='dot' style='background:${COLOR.endorsed}'></span>Active (${n('endorsed')})<br>`
    + `<span class='dot' style='background:${COLOR['recently-triggered']}'></span>Recently triggered (${n('recently-triggered')})<br>`
    + `<span class='dot' style='background:${COLOR.expired}'></span>Expired (${n('expired')})<br>`
    + `<span class='dot' style='background:${COLOR.development}'></span>In development (${n('development')})<br>`
    + `<span class='dot' style='background:${COLOR.retired}'></span>Retired / dormant (${n('retired')})<br>`
    + `<span class='dot' style='background:#e3322d;width:11px;height:11px;border:2px solid #fff'></span>Activated — a dot per activation (${nAct})<br>`
    + `<span class='dot' style='background:#fff;width:12px;height:12px;border:2.5px solid #f5a300'></span>Able to trigger now — in season (${CURMONTH}), pulsing (${nNow})<br>`
    + `<span class='dot' style='background:#fff;width:12px;height:12px;border:2.5px solid #f6c95f'></span>Able to trigger — off-season (${nOff})<br>`
    + `<span class='dot' style='background:#fff;width:12px;height:12px;border:2.5px solid #e3e6ea'></span>No ring = cannot trigger (activated &amp; spent, expired, or in development)`;
}

// ---------- callouts: one per country, laid out clear of every framework country (ported from the KB map)
const NS = 'http://www.w3.org/2000/svg';
const labels = [];
function buildCallouts(){
  Object.entries(L).forEach(([iso, c]) => {
    if(!c.centroid) return;
    const el = document.createElement('div'); el.className = 'callout';
    el.innerHTML = `<span class='cname' data-iso='${iso}'>${esc(c.name)}</span>` +
      c.fws.map(f => `<span class='hrow'>${iconHTML(f)}<span class='hlab'>${esc(f.hz_label)}</span></span>`).join('');
    el.querySelector('.cname').onclick = e => { e.stopPropagation(); selectCountry(iso); };
    el.querySelectorAll('.iconbox').forEach(ib => { ib.onclick = e => { e.stopPropagation(); selectCountry(iso, ib.dataset.hz); };
      ib.onmouseenter = ev => { const f = c.fws.find(x=>x.hazard===ib.dataset.hz); showTip(ev, `${c.name} — ${f.hz_label}: ${f.disp_label}${f.n_act?` · ${f.n_act} activation${f.n_act>1?'s':''}`:''}`); };
      ib.onmouseleave = () => tip.hidden = true; });
    lpane.appendChild(el);
    const ln = document.createElementNS(NS, 'line'); ln.setAttribute('class','leader'); leaders.appendChild(ln);
    const dot = document.createElementNS(NS, 'circle'); dot.setAttribute('class','cdot'); dot.setAttribute('r','3.5'); leaders.appendChild(dot);
    labels.push({iso, lat:c.centroid[0], lon:c.centroid[1], dir:c.dir, el, ln, dot, bbox:c.lbbox});
  });
}
const PAD = 8, GAP = 4; let ALLRECTS = [];
function rectOf(bbox){ if(!bbox || bbox[2]-bbox[0] > 170) return null;
  const [x1,y1] = toPx(bbox[0], bbox[3]), [x2,y2] = toPx(bbox[2], bbox[1]);
  return {x1:Math.min(x1,x2), y1:Math.min(y1,y2), x2:Math.max(x1,x2), y2:Math.max(y1,y2)}; }
function clampAll(W, H){ labels.forEach(Lb => {
  if(Lb.cx - Lb.w/2 < 3) Lb.cx = 3 + Lb.w/2; if(Lb.cx + Lb.w/2 > W-3) Lb.cx = W-3-Lb.w/2;
  if(Lb.cy - Lb.h/2 < 3) Lb.cy = 3 + Lb.h/2; if(Lb.cy + Lb.h/2 > H-3) Lb.cy = H-3-Lb.h/2; }); }
function ejectCountries(Lb){
  const bx1 = Lb.cx-Lb.w/2-GAP, by1 = Lb.cy-Lb.h/2-GAP, bx2 = Lb.cx+Lb.w/2+GAP, by2 = Lb.cy+Lb.h/2+GAP;
  let best = null, bestA = 0;
  for(const r of ALLRECTS){ const ox = Math.min(bx2,r.x2)-Math.max(bx1,r.x1), oy = Math.min(by2,r.y2)-Math.max(by1,r.y1);
    if(ox>0 && oy>0){ const a = Math.min(ox,oy); if(a>bestA){ bestA=a; best=r; } } }
  if(!best) return false;
  const pushL = best.x1-bx2, pushR = best.x2-bx1, pushU = best.y1-by2, pushD = best.y2-by1;
  const cands = [[Math.abs(pushL),pushL,0],[Math.abs(pushR),pushR,0],[Math.abs(pushU),0,pushU],[Math.abs(pushD),0,pushD]].sort((a,b)=>a[0]-b[0]);
  const bias = cands.filter(c => (c[1]*Lb.dir[0] + c[2]*Lb.dir[1]) >= 0);
  const pick = (bias[0] && bias[0][0] <= cands[0][0]*1.6) ? bias[0] : cands[0];
  Lb.cx += pick[1]; Lb.cy += pick[2]; return true;
}
function separate(iters, W, H){
  for(let s=0; s<iters; s++){
    let clean = true;
    for(let i=0;i<labels.length;i++) for(let j=i+1;j<labels.length;j++){
      const a = labels[i], b = labels[j];
      const ax = a.cx-a.w/2, ay = a.cy-a.h/2, bx = b.cx-b.w/2, by = b.cy-b.h/2;
      if(ax < bx+b.w+PAD && ax+a.w+PAD > bx && ay < by+b.h+PAD && ay+a.h+PAD > by){
        clean = false;
        const ox = Math.min(ax+a.w, bx+b.w)-Math.max(ax,bx)+PAD, oy = Math.min(ay+a.h, by+b.h)-Math.max(ay,by)+PAD;
        if(ox <= oy){ const hx = ox/2+.5; if(a.cx < b.cx){ a.cx-=hx; b.cx+=hx; } else { a.cx+=hx; b.cx-=hx; } }
        else { const hy = oy/2+.5; if(a.cy < b.cy){ a.cy-=hy; b.cy+=hy; } else { a.cy+=hy; b.cy-=hy; } }
      }
    }
    labels.forEach(Lb => { if(ejectCountries(Lb)) clean = false; });
    clampAll(W, H);
    if(clean) return true;
  }
  return false;
}
function runLayout(){
  const r = svg.getBoundingClientRect(), W = r.width, H = r.height;
  if(!W) return;
  ALLRECTS = labels.map(Lb => rectOf(Lb.bbox)).filter(Boolean);
  const lr = legend.getBoundingClientRect(), mr = mapbox.getBoundingClientRect();
  if(lr.width) ALLRECTS.push({x1:lr.left-mr.left-6, y1:lr.top-mr.top-6, x2:lr.right-mr.left+6, y2:lr.bottom-mr.top+6});
  labels.forEach(Lb => {
    const p = toPx(Lb.lon, Lb.lat); Lb.px = p[0]; Lb.py = p[1];
    Lb.w = Lb.el.offsetWidth; Lb.h = Lb.el.offsetHeight;
    const ib = Lb.el.querySelector('.iconbox');
    Lb.iox = ib ? ib.offsetLeft + ib.offsetWidth/2 : 12; Lb.ioy = ib ? ib.offsetTop + ib.offsetHeight/2 : Lb.h/2;
    const rc = rectOf(Lb.bbox);
    const dl = Math.hypot(Lb.dir[0], Lb.dir[1]) || 1, ux = Lb.dir[0]/dl, uy = Lb.dir[1]/dl;
    const cx0 = rc ? (rc.x1+rc.x2)/2 : Lb.px, cy0 = rc ? (rc.y1+rc.y2)/2 : Lb.py;
    const hx = rc ? (rc.x2-rc.x1)/2 : 0, hy = rc ? (rc.y2-rc.y1)/2 : 0;
    const reach = Math.abs(ux)*hx + Math.abs(uy)*hy + GAP + Math.abs(ux)*Lb.w/2 + Math.abs(uy)*Lb.h/2 + 2;
    Lb.cx = cx0 + ux*reach; Lb.cy = cy0 + uy*reach;
  });
  for(let step=0; step<55; step++){
    labels.forEach(Lb => { Lb.cx += (Lb.px-Lb.cx)*.06; Lb.cy += (Lb.py-Lb.cy)*.06; ejectCountries(Lb); });
    separate(10, W, H);
  }
  separate(700, W, H);
  labels.forEach(Lb => {
    Lb.el.style.visibility = 'visible'; Lb.el.style.left = (Lb.cx-Lb.w/2)+'px'; Lb.el.style.top = (Lb.cy-Lb.h/2)+'px';
    Lb.ln.setAttribute('x1', Lb.px); Lb.ln.setAttribute('y1', Lb.py);
    Lb.ln.setAttribute('x2', Lb.cx-Lb.w/2+Lb.iox); Lb.ln.setAttribute('y2', Lb.cy-Lb.h/2+Lb.ioy);
    Lb.dot.setAttribute('cx', Lb.px); Lb.dot.setAttribute('cy', Lb.py);
  });
}
let rto = null; window.addEventListener('resize', () => { clearTimeout(rto); rto = setTimeout(runLayout, 150); });

// ---------- tooltips
function showTip(ev, txt){ const box = mapbox.getBoundingClientRect(); tip.textContent = txt; tip.hidden = false;
  tip.style.left = (ev.clientX-box.left)+'px'; tip.style.top = (ev.clientY-box.top)+'px'; }
svg.addEventListener('mousemove', ev => {
  const t = ev.target; let txt = null;
  if(t.classList.contains('cty') && t.classList.contains('on') && !state.iso){ const c = L[t.dataset.iso]; if(c) txt = `${c.name} · ${c.fws.length} framework${c.fws.length>1?'s':''}`; }
  else if(t.classList.contains('sc')) txt = `${t.dataset.n} · ${t.dataset.hz}`;
  else if(t.classList.contains('a1')) txt = t.dataset.n;
  if(txt) showTip(ev, txt); else tip.hidden = true;
});
svg.addEventListener('mouseleave', ()=> tip.hidden = true);

// ---------- selection
svg.addEventListener('click', ev => {
  const t = ev.target;
  if(t.classList.contains('cty') && t.classList.contains('on') && L[t.dataset.iso]) selectCountry(t.dataset.iso);
  else if(t.id === 'sea' && state.iso) goWorld();
});
back.addEventListener('click', goWorld);

function goWorld(){
  state = { iso:null, hz:null, ver:null };
  document.querySelectorAll('.cty.sel').forEach(x=>x.classList.remove('sel'));
  svg.classList.remove('zoomed'); adm.innerHTML=''; adm.classList.remove('show');
  resetZoom(); back.hidden = true; worldLegend(); maprow.classList.remove('open');
  setTimeout(()=>{ runLayout(); lpane.classList.remove('hide'); }, 580);   // after the sidebar has closed
  side.innerHTML = `<div class='muted' style='padding:20px 6px'>Select a country or a pin on the map.</div>`;
  history.replaceState(null, '', location.pathname);
}
async function selectCountry(iso, hz, ver){
  const c = L[iso]; if(!c) return;
  const changed = state.iso !== iso;
  state = { iso, hz: hz || (c.fws.length===1 ? c.fws[0].hazard : null), ver: ver || null };
  document.querySelectorAll('.cty.sel').forEach(x=>x.classList.remove('sel'));
  svg.querySelectorAll(`.cty[data-iso='${iso}']`).forEach(el => el.classList.add('sel'));
  svg.classList.add('zoomed'); back.hidden = false; lpane.classList.add('hide'); tip.hidden = true; maprow.classList.add('open');
  if(changed){ adm.innerHTML=''; adm.classList.remove('show'); if(c.bbox) zoomTo(c.bbox); }
  renderSide();
  await loadGeo(iso);
  if(state.iso === iso) drawAdmin(iso, changed);
  location.hash = [iso, state.hz, state.ver].filter(Boolean).join('/');
}
function selectFramework(hz){ selectCountry(state.iso, hz, null); }
function selectVersion(v){ state.ver = v; renderSide(); drawAdmin(state.iso, false); location.hash = [state.iso, state.hz, v].join('/'); }

// ---------- sidebar
function monthStrip(months){ months = months||[]; return [...MONL].map((m,i)=>`<span class='mm ${months.includes(i+1)?'on':''}'>${m}</span>`).join(''); }
function renderSide(){
  const c = L[state.iso];
  const crumb = `<div class='crumb'><a onclick='goWorld()'>World</a> › ` +
    (state.hz ? `<a onclick='selectCountry("${state.iso}", null)'>${esc(c.name)}</a> › ${esc(c.fws.find(f=>f.hazard===state.hz)?.hz_label||state.hz)}` : `<b>${esc(c.name)}</b>`) + `</div>`;
  if(!state.hz){
    side.innerHTML = crumb + `<h3>${esc(c.name)}</h3><div class='muted'>${esc(c.region||'')} · ${c.fws.length} framework${c.fws.length>1?'s':''} — select one</div>` +
      `<div class='fwlist'>` + c.fws.map(f => {
        const v = f.versions.find(x=>x.v===f.current);
        return `<div class='fcardx' style='--hz:${hzColor(f.hazard)}' onclick='selectFramework("${f.hazard}")'>
          <div class='fhead'><b>${iconHTML(f)}${esc(f.hz_label)}</b>${badge(f.disp)}</div>
          <table class='mini'>
           <tr><td class='lbl'>Latest version</td><td>${f.current ? `<code>${f.current}</code> <span class='muted'>(${f.versions.length} total)</span>` : '<span class="muted">none in the KB yet</span>'}</td></tr>
           <tr><td class='lbl'>Pre-arranged</td><td>${money(f.prearranged)}${f.prearranged_year?` <span class='muted'>(${f.prearranged_year})</span>`:''}</td></tr>
           <tr><td class='lbl'>People covered</td><td>${num(f.covered)}</td></tr>
           <tr><td class='lbl'>Activations</td><td>${f.n_act||'—'}</td></tr>
           <tr><td class='lbl'>Monitoring</td><td>${monthStrip(v ? v.months : [])}</td></tr>
          </table></div>`; }).join('') + `</div>`;
    return;
  }
  const f = c.fws.find(x=>x.hazard===state.hz); if(!f){ state.hz=null; return renderSide(); }
  if(!f.versions.length){
    side.innerHTML = crumb + fwHeader(c, f) + `<p class='muted'>No version in the knowledge base yet — status comes from the tracking sheets (${esc((f.status||'').replace(/_/g,' '))}).</p>` +
      activationsBlock(f, null) + `<p><a href='${f.page}'>framework page →</a></p>`;
    return;
  }
  const ver = state.ver || f.current; state.ver = ver;
  const v = f.versions.find(x=>x.v===ver) || f.versions[f.versions.length-1];
  const isCur = v.v === f.current;
  side.innerHTML = crumb + fwHeader(c, f) + versionBar(f, v, isCur) +
    (isCur ? '' : `<div class='warnbox'>Viewing an older version (${esc(v.status||'past')}). The map shows this version's scope. Most recent: <a onclick='selectVersion("${f.current}")' style='cursor:pointer'>${f.current}</a>.</div>`) +
    factsBlock(f, v) + triggersBlock(v) + fundingBlock(v) + activationsBlock(f, v) + scopeBlock(v) +
    `<p class='small' style='margin-top:12px'><a href='${f.page}'>full framework page →</a> · <a href='hierarchy.html'>explorer</a></p>`;
}
function fwHeader(c, f){
  return `<h3 style='display:flex;align-items:center;gap:8px'>${iconHTML(f)}<span>${esc(c.name)} — ${esc(f.hz_label)}</span></h3>
   <div>${badge(f.disp)} ${f.ring ? `<span class='small' style='color:#c8860a'>&bull; able to trigger${f.ring==='now'?' now (in season)':' (off-season)'}</span>` : (f.disp==='recently-triggered' ? `<span class='small' style='color:#999'>&bull; not able to trigger now (spent)</span>` : '')}
   ${f.kb?` <span class='muted'>· KB <code>${f.kb}</code></span>`:''}${f.in_force && f.in_force!==f.current ? ` <span class='muted'>· tracking view in force: ${f.in_force}</span>` : ''}</div>`;
}
function versionBar(f, v, isCur){
  const opts = [...f.versions].reverse().map(x=>`<option value='${x.v}' ${x.v===v.v?'selected':''}>${x.v}${x.v===f.current?' (latest)':''} — ${x.status||'?'}</option>`).join('');
  return `<div class='verbar'><label class='small'>Version</label><select onchange='selectVersion(this.value)'>${opts}</select>
    ${v.doc_url ? `<a class='docbtn' href='${esc(v.doc_url)}' target='_blank' rel='noopener' title='${esc(v.doc_title||'')}'>Framework doc ↗</a>` : `<span class='badge b-retired'>no document link</span>`}</div>`;
}
function factsBlock(f, v){
  const rows = [];
  rows.push(['Status', `${verBadge(v.status)}${v.endorsed_by?` <span class='muted'>endorsed by ${esc(v.endorsed_by)}</span>`:''}`]);
  rows.push(['Valid', `${v.valid_from||'?'} → ${v.valid_until||'<span class="muted">open</span>'}${v.valid_until_source?` <span class='muted'>(${esc(v.valid_until_source)})</span>`:''}`]);
  if(v.doc_title) rows.push(['Document', `${esc(v.doc_title)}${v.doc_date?` <span class='muted'>(${v.doc_date})</span>`:''}`]);
  rows.push(['Pre-arranged', `${money(v.prearranged_doc)}${v.regional?` <span class='muted'>· regional document total (all countries)</span>`:''}${v.all_in===false?` <span class='muted'>· split budget per window</span>`:v.all_in===true?` <span class='muted'>· all-in</span>`:''}`]);
  if(v.cofin) rows.push(['Co-financing', `${money(v.cofin)}${v.cofin_sources.length?` <span class='muted'>${esc(v.cofin_sources.join(', '))}</span>`:''}`]);
  if(v.target_people) rows.push(['People targeted', num(v.target_people)]);
  if(f.covered && f.current===v.v) rows.push(['People covered', `${num(f.covered)} <span class='muted'>(tracking sheet)</span>`]);
  rows.push(['Monitored', `${monthStrip(v.months)}${v.months_src?` <span class='muted'>${esc(v.months_src)}</span>`:''}${v.months_note?`<div class='small' style='margin-top:3px'>${esc(v.months_note)}</div>`:''}`]);
  if(v.basis||v.indicators.length) rows.push(['Trigger basis', `${esc(v.basis||'')}${v.calibration?` · ${esc(v.calibration)}`:''}${v.indicators.length?`<div class='chips'>${v.indicators.map(i=>`<span>${esc(i)}</span>`).join('')}</div>`:''}`]);
  if(v.agencies.length) rows.push(['Agencies', esc(v.agencies.join(', '))]);
  if(v.supersedes) rows.push(['Supersedes', `<a onclick='selectVersion("${esc(v.supersedes)}")' style='cursor:pointer'>${esc(v.supersedes)}</a>`]);
  return `<table class='mini' style='margin-top:6px'>${rows.map(([k,val])=>`<tr><td class='lbl'>${k}</td><td>${val}</td></tr>`).join('')}</table>`;
}
function sameWin(a, b){ if(!a||!b) return false; a=String(a).toLowerCase().replace(/[^a-z0-9]+/g,' ').trim(); b=String(b).toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
  return a===b || a.includes(b) || b.includes(a); }
function triggersBlock(v){
  let html = '';
  if(v.triggers.length){
    html += `<h4>Triggers (${v.triggers.length} window${v.triggers.length>1?'s':''})</h4>`;
    v.triggers.forEach(t => {
      const name = t.window || t.trigger || t.component || Object.values(t)[0];
      const sub = [t.basin, t.basis, t.country].filter(Boolean).join(' · ');
      const ind = t.indicator || t.indicators || '', thr = t.threshold || t.condition || '';
      const meta = [t['lead time'] ? `lead ${t['lead time']}` : null, t['return period'] ? `RP ${t['return period']}` : null,
                    t.releases ? `releases: ${t.releases}` : null].filter(Boolean);
      const bt = v.windows.find(w => sameWin(w.name, name));
      html += `<div class='trig'><div class='tn'>${esc(name)}${sub?` <span class='muted'>· ${esc(sub)}</span>`:''}</div>
        <div class='tt'>${esc(ind)}${ind&&thr?' — ':''}<b>${esc(thr)}</b></div>
        ${meta.length?`<div class='tm'>${esc(meta.join(' · '))}</div>`:''}
        ${bt?`<div class='tm'>backtest: ${bt.rp?`1-in-${bt.rp.toFixed(1)} yr`:''}${bt.prob?` · ${(bt.prob*100).toFixed(0)}%/yr`:''}${bt.sim!=null?` · ${bt.sim} in ${bt.years} yrs`:''}${bt.budget?` · budget ${money(bt.budget)}`:''}</div>`:''}
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
    html += `<details style='margin-top:6px'><summary class='small' style='cursor:pointer;color:var(--ocha)'>by sector</summary><table class='mini'>` +
      Object.entries(secs).sort((a,b)=>b[1]-a[1]).map(([s,u])=>`<tr><td>${esc(s)}</td><td class='num'>${money(u)}</td></tr>`).join('') + `</table></details>`;
  }
  return html;
}
function activationsBlock(f, v){
  const A = f.activations;
  let html = `<h4>Activations — all versions (${A.length})</h4>`;
  if(!A.length) return html + `<div class='muted'>Never activated.</div>`;
  const byWin = {};
  A.forEach(a => { if(v && a.version===v.v) (byWin[a.window||'unspecified window'] ??= []).push(a); });
  if(v && Object.keys(byWin).length){
    html += `<div class='small' style='margin-bottom:4px'>Under this version, by trigger: ` +
      Object.entries(byWin).map(([w,as])=>`<b>${esc(w)}</b> ×${as.length}`).join(' · ') + `</div>`;
  }
  html += A.map(a => {
    const other = v ? (a.version !== v.v) : false;
    const funding = a.funding.filter(x=>x.usd!=null||x.code).map(x=>`${esc(x.fund)}: ${money(x.usd)}${x.code?` <span class='muted'>(${esc(x.code)})</span>`:''}`).join('<br>');
    const dateHtml = a.url ? `<a href='${esc(a.url)}' target='_blank' rel='noopener'>${a.date}↗</a>` : a.date;
    return `<div class='actrow' ${other?"style='opacity:.85'":''}>
      <div class='ah'><span class='ad'>${dateHtml}${a.type!=='framework_aa'?` <span class='badge b-retired'>${esc(a.type.replace(/_/g,' '))}</span>`:''}${a.full===false?` <span class='badge b-development'>partial</span>`:''}</span>
        ${a.version ? `<span class='vtag ${other?'other':''}' title='${other?'fired under a different version than the one displayed':'fired under the displayed version'}'>${other?'under ':''}${a.version}</span>` : `<span class='vtag other'>no version</span>`}</div>
      <div class='small'>${a.window?esc(a.window):'<span class="muted">window not recorded</span>'}</div>
      <div class='small'>${funding||(a.released?`released ${money(a.released)}`:'<span class="muted">funding not recorded</span>')}${a.people?` · ${num(a.people)} people targeted`:''}</div>
    </div>`; }).join('');
  return html;
}
function scopeBlock(v){
  const s = v.scope; if(!s) return '';
  let html = `<h4>Geographic scope${v.admin_level!=null?` <span class='muted' style='text-transform:none'>(trigger at admin ${v.admin_level})</span>`:''}</h4>`;
  if(s.inherited_from) html += `<div class='warnbox'>Scope not yet extracted for this version — the map shows the ${esc(s.inherited_from)} scope.</div>`;
  if(s.national) html += `<div class='scopelist'>National trigger — whole country shaded.</div>`;
  if(v.scope_raw.length) html += `<div class='scopelist'>${v.scope_raw.map(x=>esc(x)).join(' · ')}</div>`;
  if(!s.national && !v.scope_raw.length && !s.inherited_from) html += `<div class='muted'>Scope not extracted for this version yet.</div>`;
  if(s.unmatched.length) html += `<div class='small' style='margin-top:4px;color:#8a5c0a'>Not on the map (no boundary match): ${s.unmatched.map(esc).join('; ')}</div>`;
  return html;
}

// ---------- boot
worldLegend(); buildCallouts(); runLayout();
setTimeout(runLayout, 300);   // once fonts have settled
(function(){ const h = location.hash.replace('#','').split('/'); if(h[0] && L[h[0]]) selectCountry(h[0], h[1]||null, h[2]||null); })();
"""
