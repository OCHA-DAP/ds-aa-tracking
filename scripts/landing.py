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

from ds_aa_tracking.kb_pages import load_version_pages

ROOT = Path(__file__).parents[1]
OUT = ROOT / "site_build"
CACHE = ROOT / "data" / "fieldmaps"

import datetime as _dt
import math

# ---- projections. World view: Equal Earth (endorsed by UN GA resolution A/80/L.104,
# 4 Sep 2026), centred on 30°E so the portfolio (Americas → Pacific) sits in frame.
# Country view: a local equirectangular fit (cos(lat) corrected) — the page morphs
# between the two. The same constants live in the JS below; keep them in sync.
EE_A1, EE_A2, EE_A3, EE_A4 = 1.340264, -0.081106, 0.000893, 0.003796
EE_LAM0 = 30.0
FRAME = (-112.0, -42.0, 184.0, 52.0)   # lon0, lat0, lon1, lat1 shown in the world view
VB_W = 980.0
S_MAX_DEG = 0.8                         # never zoom tighter than this many degrees across


def equal_earth(lon, lat):
    """Equal Earth forward projection (Šavrič, Patterson & Jenny 2018), y up."""
    lam = math.radians(((lon - EE_LAM0 + 540) % 360) - 180)
    th = math.asin(math.sqrt(3) / 2 * math.sin(math.radians(lat)))
    t2 = th * th
    t6 = t2 * t2 * t2
    x = 2 * math.sqrt(3) * lam * math.cos(th) / (3 * (9 * EE_A4 * t6 * t2 + 7 * EE_A3 * t6
                                                      + 3 * EE_A2 * t2 + EE_A1))
    y = th * (EE_A4 * t6 * t2 * th + EE_A3 * t6 * th + EE_A2 * t2 * th + EE_A1)
    return x, -y


def _frame_bbox():
    pts = []
    lon0, lat0, lon1, lat1 = FRAME
    for i in range(0, 101):
        f = i / 100
        pts.append(equal_earth(lon0 + (lon1 - lon0) * f, lat0))
        pts.append(equal_earth(lon0 + (lon1 - lon0) * f, lat1))
        pts.append(equal_earth(lon0, lat0 + (lat1 - lat0) * f))
        pts.append(equal_earth(lon1, lat0 + (lat1 - lat0) * f))
    xs = [x for x, _ in pts]; ys = [y for _, y in pts]
    return min(xs), min(ys), max(xs), max(ys)


EE_BBOX = _frame_bbox()
VB_H = VB_W * (EE_BBOX[3] - EE_BBOX[1]) / (EE_BBOX[2] - EE_BBOX[0])
VB_X, VB_Y = 0.0, 0.0
W, H = VB_W, VB_H                       # kept for callers; the view box is 0 0 VB_W VB_H

# Lifecycle colours, glyphs, callout directions and centroids mirror the KB public map
# (ds-knowledge-base/scripts/gen_public_site.py) so the two sites read the same.
# framework status (aa.v_framework_lifecycle): 'updating' shares the active colour, hatched
KB_COLOR = {"active": "#2171b5", "updating": "#2171b5", "development": "#9ecae1"}
KB_LABEL = {"active": "Active", "updating": "Being updated", "development": "In development"}
# map layers (index.html toggles). A pair can sit on several layers; the pin takes the
# style of the first ENABLED layer in this order (a framework with ad hoc allocations is
# drawn as a framework while the framework layer is on).
LAYER_ORDER = ("framework", "retired", "adhoc", "tech")
LAYER_COLOR = {"adhoc": "#74c476", "retired": "#9e9e9e", "tech": "#2a9d8f"}
LAYER_LABEL = {"framework": "Current frameworks", "adhoc": "Ad hoc allocations", "retired": "Retired",
               "tech": "Technical support"}
DISP_LABEL = {**KB_LABEL, "retired": "Retired", "pipeline": "No framework version yet",
              "adhoc": "Ad hoc allocations only"}
# year selector: the first year it offers (the annual pre-arranged series starts here —
# dashboards._backfill_years) and the status-report -> lifecycle mapping, the CASE that
# aa.v_framework_lifecycle applies to a framework with no version (anything else: not shown)
YEAR_FIRST = 2020
SHEET_LIFECYCLE = {"active": "active", "activated_implementing": "active", "monitoring": "active",
                   "under_revision": "updating", "expired": "updating",
                   "under_development": "development", "project_finalization": "development",
                   "dormant": "retired", "retired": "retired"}
# trigger-validation Drive folder (rendered in the Model pillar when non-empty)
TRIGGER_VALIDATION_URL = ""
# framework_version.analysis_ref is 'repo@branch:path' in the team's GitHub org
ANALYSIS_REPO_BASE = "https://github.com/OCHA-DAP/"
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


# ---------------------------------------------------------------- world base
WORLD_SRC = ROOT / "data" / "world" / "ne_50m_admin_0_countries.geojson"
WORLD_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
             "geojson/ne_50m_admin_0_countries.geojson")
WORLD_TOL = 0.03      # degrees; one topology for all countries -> borders stay shared


def world_gdf():
    """Natural Earth 1:50m countries, one (multi)polygon per ISO3 (Somaliland folded
    into Somalia), full resolution. Downloaded once into data/world/."""
    import geopandas as gpd
    if not WORLD_SRC.exists():
        import urllib.request
        WORLD_SRC.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(WORLD_URL, WORLD_SRC)
    g = gpd.read_file(WORLD_SRC)[["ISO_A3", "ADM0_A3", "NAME", "geometry"]]
    g["iso"] = [a if a != "-99" else b for a, b in zip(g["ISO_A3"], g["ADM0_A3"])]
    g.loc[g["iso"] == "SOL", "iso"] = "SOM"
    g = g[g["iso"] != "ATA"]
    return g.dissolve("iso", as_index=False, aggfunc={"NAME": "first"})


def world_simplified():
    """The world base simplified as ONE topology so shared borders survive (cached)."""
    import geopandas as gpd
    cache = WORLD_SRC.parent / f"world_topo_{WORLD_TOL}.geojson"
    if cache.exists():
        return gpd.read_file(cache)
    import topojson as tp
    g = world_gdf()
    topo = tp.Topology(g, prequantize=1_000_000, toposimplify=WORLD_TOL,
                       topoquantize=False, shared_coords=True)
    out = topo.to_gdf()
    out = out[["iso", "NAME", "geometry"]]
    out.to_file(cache, driver="GeoJSON")
    return out


def world_data(shown_iso, country_names):
    """World base as lon/lat rings per country (the page projects them); plus the
    largest-polygon bbox per country for framing."""
    from shapely.geometry import MultiPolygon
    g = world_simplified()
    data, bboxes = {}, {}
    for _, f in g.iterrows():
        iso, geom = f["iso"], f["geometry"]
        polys = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
        rings = [[[round(x, 3), round(y, 3)] for x, y in ring.coords]
                 for poly in polys for ring in [poly.exterior, *poly.interiors]]
        data[iso] = {"n": country_names.get(iso, f["NAME"]), "on": iso in shown_iso, "r": rings}
        big = max(polys, key=lambda p: p.area)
        bboxes[iso] = [float(x) for x in big.bounds]
    svg = (f"<svg id='map' viewBox='0 0 {VB_W:.1f} {VB_H:.1f}' preserveAspectRatio='xMidYMid meet'>"
           f"<rect id='sea' x='{-VB_W}' y='{-VB_H}' width='{3*VB_W}' height='{3*VB_H}' fill='transparent'/>"
           f"<g id='world'></g><g id='adm'></g></svg>")
    return svg, bboxes, data


# ---------------------------------------------------------------- framework pages (DB)
def _kb_pages(e):
    """(kb_framework, version) -> {fm, triggers, tiers} — aa.version_page (the KB pages,
    imported once on 2026-09-28 and edited in the DB since; the KB is not a source)."""
    return load_version_pages(e)


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
    """FieldMaps edge-matched COD-AB layer (the team loader's source) for one country,
    read with a predicate filter from the global GeoParquet and cached as a pickle.
    Edge-matched: neighbouring countries and nested admin levels share their edges
    exactly, so a zoomed country fits its neighbours with no slivers."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{iso}_adm{level}.pkl"
    if f.exists():
        return pd.read_pickle(f)
    from ocha_stratus import codab
    try:
        gdf = codab.load_codab_from_fieldmaps(iso, admin_level=level)
    except Exception as ex:  # noqa: BLE001 — network / missing country
        print(f"  ! fieldmaps {iso} adm{level}: {ex}")
        gdf = None
    if gdf is None:
        gdf = False
    pd.to_pickle(gdf, f)
    return gdf


def local_scale(b):
    """Scale (view-box units per degree of latitude) of the local country projection —
    identical to `localProj` in the page."""
    lat0 = (b[1] + b[3]) / 2
    cosf = max(0.35, math.cos(math.radians(lat0)))
    bw = max((b[2] - b[0]) * cosf, 0.01)
    bh = max(b[3] - b[1], 0.01)
    S = VB_H                                # the zoomed view is a square of the world height
    return min(S / (bw * 1.25), S / (bh * 1.25), S / S_MAX_DEG), cosf, lat0


def viewport_box(b):
    """Lon/lat box of what the zoomed viewport shows for a country bbox b, plus a 15 %
    margin so clip edges stay off-screen."""
    from shapely.geometry import box
    sc, cosf, lat0 = local_scale(b)
    vis_lon = VB_H / (sc * cosf) * 1.15
    vis_lat = VB_H / sc * 1.15
    cx = (b[0] + b[2]) / 2
    return box(cx - vis_lon / 2, lat0 - vis_lat / 2, cx + vis_lon / 2, lat0 + vis_lat / 2)


_WORLD = {}


def countries_in_view(iso, view):
    """Every other country whose (world-file) shape intersects the zoomed viewport —
    all drawn from the edge-matched set so no two boundary sources meet on screen."""
    if "g" not in _WORLD:
        _WORLD["g"] = world_gdf()
    g = _WORLD["g"]
    from shapely.affinity import translate
    hit = g[g.intersects(view) | g.intersects(translate(view, xoff=-360))].copy()   # frames past 180°
    hit = hit[hit["iso"] != iso]
    if len(hit) > 40:                          # open ocean views: keep what actually shows
        hit["_a"] = hit.geometry.intersection(view).area
        hit = hit.sort_values("_a", ascending=False).head(40)
    return sorted(hit["iso"])


class Matcher:
    """Match KB geographic_scope names to CODAB features at admin levels 1..3."""

    def __init__(self, iso, max_level):
        self.iso = iso
        self.layers = {}
        for lv in range(1, max(1, min(max_level, 3)) + 1):
            g = load_codab(iso, lv)
            if g is False or g is None or not len(g):
                continue
            pcol = f"adm{lv}_src"                     # source pcode
            ncols = [c for c in (f"adm{lv}_name", f"adm{lv}_name1", f"adm{lv}_name2")
                     if c in g.columns and g[c].notna().any()]
            if not ncols or pcol not in g.columns:
                continue
            ncol = ncols[0]
            g = g.copy()
            g["_names"] = g[ncols].apply(lambda r: [str(x) for x in r if pd.notna(x)], axis=1)
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

    def _exact_levels(self, name):
        """Admin levels at which this name (or pcode) matches exactly."""
        n = _norm(name)
        if n in ALIASES:
            return set()
        ns = _strip_desc(n)
        code = n.upper().replace(" ", "")
        m_pc = re.fullmatch(r"([A-Z]{2,3})(\d+)", code)
        out = set()
        for lv, (g, ncol, pcol) in self.layers.items():
            if m_pc:
                tail = m_pc.group(2)
                if g[pcol].str.upper().str.replace(" ", "").map(
                        lambda pc: bool(re.fullmatch(r"[A-Z]{2,3}" + re.escape(tail), pc))).sum() == 1:
                    out.add(lv)
            elif (g["_n"].map(lambda xs: n in xs) | g["_ns"].map(lambda xs: ns in xs)).any():
                out.add(lv)
        return out

    def _find(self, name, levels):
        n = _norm(name)
        all_levels = sorted(self.layers)
        if n in ALIASES:
            out = []
            for alias in ALIASES[n]:
                out += self._find_one(alias, all_levels)
            return out
        if re.fullmatch(r"[a-z]{2,3}\s?\d+", n):          # a pcode names its level itself
            return self._find_one(n, all_levels)
        return self._find_one(n, levels)

    def _find_one(self, n, levels):
        ns = _strip_desc(n)
        for lv in levels:
            if lv not in self.layers:
                continue
            g, ncol, pcol = self.layers[lv]
            # pcode given directly — accept the ISO2 (TD18, as in HDX CODs) or ISO3 (TCD18,
            # FieldMaps) prefix style: compare the part after the country prefix
            code = n.upper().replace(" ", "")
            m_pc = re.fullmatch(r"([A-Z]{2,3})(\d+)", code)
            if m_pc:
                tail = m_pc.group(2)
                hit = g[g[pcol].str.upper().str.replace(" ", "").map(
                    lambda pc: bool(re.fullmatch(r"[A-Z]{2,3}" + re.escape(tail), pc)))]
                if len(hit) == 1:
                    return [self._record(lv, r) for _, r in hit.iterrows()]
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
        # a name can exist at several levels (Dosso region and Dosso commune; Khulna
        # division and Khulna district): resolve the whole list at the level where MOST of
        # its names match, ties going to the coarser unit
        top = max(1, min(admin_level or 3, 3))
        counts = {}
        for raw in items or []:
            for lv in self._exact_levels(str(raw).split(":", 1)[-1].split("(")[0].strip()):
                counts[lv] = counts.get(lv, 0) + 1
        dominant = min(counts, key=lambda lv: (-counts[lv], lv)) if counts else 1
        levels = [dominant] + [lv for lv in range(1, top + 1) if lv != dominant]
        if dominant > top:
            levels = [dominant] + list(range(1, top + 1))
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


def _rings(geom):
    """Geometry -> list of rings [[lon,lat],...] (4-decimal coords, slivers dropped)."""
    from shapely.geometry import MultiPolygon, Polygon
    polys = (list(geom.geoms) if isinstance(geom, MultiPolygon)
             else [geom] if isinstance(geom, Polygon) else [])
    polys = [p for p in polys if not p.is_empty]
    if not polys:
        return []
    amax = max(p.area for p in polys)
    rings = []
    for p in polys:
        if p.area < amax * 0.001:
            continue
        rings.append([[round(x, 4), round(y, 4)] for x, y in p.exterior.coords])
        for hole in p.interiors:
            rings.append([[round(x, 4), round(y, 4)] for x, y in hole.coords])
    return rings


def _union(gs):
    return gs.union_all() if hasattr(gs, "union_all") else gs.unary_union


def write_country_geo(iso, matcher, adm0):
    """adm-<ISO>.json: country outline, ADM1 mesh, matched scope areas and the
    neighbours' outlines — simplified TOGETHER as one topology (shared arcs), so
    every edge still matches after simplification."""
    import hashlib

    import geopandas as gpd
    import topojson as tp
    from shapely.geometry import box

    if adm0 is None or adm0 is False or not len(adm0):
        return None
    b = adm0.total_bounds
    if b[2] - b[0] > 180:                      # antimeridian (Fiji): a contiguous frame past 180°
        from shapely.geometry import MultiPolygon
        geom0 = _union(adm0.geometry)
        parts = sorted((list(geom0.geoms) if isinstance(geom0, MultiPolygon) else [geom0]),
                       key=lambda g: -g.area)
        tot = sum(g.area for g in parts)
        keep, cum = [], 0.0
        for g in parts:                          # the islands that make up 90 % of the land
            keep.append(g)
            cum += g.area
            if cum >= 0.90 * tot:
                break
        xs, ys = [], []
        for g in keep:
            x0, y0, x1, y1 = g.bounds
            if x1 < 0:                           # western side of the line -> shift past 180
                x0, x1 = x0 + 360, x1 + 360
            xs += [x0, x1]; ys += [y0, y1]
        b = [min(xs), min(ys), max(xs), max(ys)]
    diag = ((b[2] - b[0]) ** 2 + (b[3] - b[1]) ** 2) ** 0.5
    tol = diag / 900
    view = viewport_box(b)
    neighbours = countries_in_view(iso, view)
    pcodes = sorted(matcher.used)
    sig = hashlib.md5(json.dumps([iso, pcodes, neighbours, round(tol, 6),
                                  1 in matcher.layers, "viewclip-v7"]).encode()).hexdigest()[:10]
    cache_f = CACHE / f"topo_{iso}_{sig}.json"
    if cache_f.exists():
        (OUT / f"adm-{iso}.json").write_text(cache_f.read_text())
        return [float(x) for x in b]

    rows = [{"kind": "a0", "n": iso, "p": iso, "l": 0, "geometry": _union(adm0.geometry)}]
    if 1 in matcher.layers:
        g, ncol, pcol = matcher.layers[1]
        rows += [{"kind": "a1", "n": r[ncol], "p": r[pcol], "l": 1, "geometry": r["geometry"]}
                 for _, r in g.iterrows()]
    for pc, rec in matcher.used.items():
        rows.append({"kind": "sc", "n": rec["name"], "p": pc, "l": rec["level"],
                     "geometry": rec["geometry"]})
    # every other country in the viewport: full-resolution outline clipped to the view
    import gc

    from shapely import clip_by_rect, make_valid
    for n in neighbours:
        gn = load_codab(n, 0)
        if gn is False or gn is None or not len(gn):
            continue
        # rectangle-clip each part BEFORE unioning: full OSM outlines (Mexico, China…)
        # run to millions of vertices and a union of the whole thing costs gigabytes
        clipped = [make_valid(clip_by_rect(g, *view.bounds)) for g in gn.geometry]
        clipped = [g for g in clipped if not g.is_empty]
        del gn
        if not clipped:
            continue
        geom = _union(gpd.GeoSeries(clipped, crs=4326))
        if not geom.is_empty:
            rows.append({"kind": "nb", "n": n, "p": n, "l": 0, "geometry": geom})
        del clipped
        gc.collect()
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=4326)
    # snap every input to one grid first: shared borders snap identically on both sides
    # (so they stay shared) while OSM-density coastlines collapse to a fraction of their
    # vertices — the pure-Python topology step below cannot take millions of points
    import shapely
    gdf["geometry"] = shapely.set_precision(gdf.geometry.values, grid_size=tol / 3)
    gdf = gdf[~gdf.geometry.is_empty]
    print(f"    {iso}: {len(gdf)} features, {int(shapely.get_num_coordinates(gdf.geometry.values).sum()):,} vertices after snapping", flush=True)
    try:
        topo = tp.Topology(gdf, prequantize=False, toposimplify=tol,
                           topoquantize=False, shared_coords=True)
        simp = topo.to_gdf()
    except Exception as ex:  # noqa: BLE001 — fall back to per-feature simplification
        print(f"  ! topology {iso}: {ex}; falling back")
        simp = gdf.copy()
        simp["geometry"] = simp.geometry.simplify(tol, preserve_topology=True)
    out = {"adm0": [], "adm1": [], "areas": {}, "nb": [], "neighbours": neighbours}
    for _, r in simp.iterrows():
        rings = _rings(r["geometry"])
        if r["kind"] == "a0":
            out["adm0"] = rings
        elif r["kind"] == "a1":
            out["adm1"].append({"n": r["n"], "p": r["p"], "r": rings})
        elif r["kind"] == "sc":
            out["areas"][r["p"]] = {"n": r["n"], "l": int(r["l"]), "r": rings}
        else:
            out["nb"].append({"iso": r["p"], "r": rings})
    txt = json.dumps(out, separators=(",", ":"))
    cache_f.write_text(txt)
    for old in CACHE.glob(f"topo_{iso}_*.json"):
        if old != cache_f:
            old.unlink()
    (OUT / f"adm-{iso}.json").write_text(txt)
    return [float(x) for x in b]


# ---------------------------------------------------------------- data assembly
def _f(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) or str(v) in ("None", "NaT", "nan") else v


def _num(v):
    v = _f(v)
    return None if v is None else float(v)


def _s(v):
    v = _f(v)
    return None if v is None else str(v)


def _envelopes(vf):
    """(country, hazard, version) -> pre-arranged USD from v_version_funding rows: the
    'all' total only counts where no per-fund split exists (the dashboards' rule)."""
    out = {}
    if vf is None or not len(vf):
        return out
    keys = ["country_iso3", "hazard", "version"]
    has_comp = set(map(tuple, vf.loc[vf["fund_code"] != "all", keys].values))
    for r in vf.itertuples():
        k = (r.country_iso3, r.hazard, r.version)
        if r.fund_code == "all" and k in has_comp:
            continue
        if _num(r.total_usd) is not None:
            out[k] = out.get(k, 0.0) + float(r.total_usd)
    return out


def _analysis_url(ref):
    """'repo@branch:path' -> GitHub tree URL in the team org; anything else stays text."""
    m = re.match(r"^([\w.-]+)@([\w./-]+):(.*)$", str(ref or ""))
    if not m:
        return None
    repo, branch, path = m.groups()
    return f"{ANALYSIS_REPO_BASE}{repo}/tree/{branch}/{path.strip('/')}"


ORG_GROUP = {"government": "Government", "un": "UN", "ingo": "International NGOs",
             "nngo": "National NGOs", "rcrc": "Red Cross / Red Crescent"}


def _partner_rows(df):
    return [{"name": _s(x.name), "acronym": _s(x.acronym),
             "group": ORG_GROUP.get(_s(x.org_type), "Other"),
             "roles": _list(x.roles),
             "parent": _s(x.agency_parent), "usd": _num(x.amount_usd)} for x in df.itertuples()]


def _list(v):
    """A Postgres text[] as read by pandas (list / ndarray / '{a,b}' text / NULL) -> list[str]."""
    if v is None or isinstance(v, float):
        return []
    if isinstance(v, str):
        return [s for s in v.strip("{}").split(",") if s]
    try:
        return [str(s) for s in v]
    except TypeError:
        return []


HZ_EMERGENCY = {"drought": ("drought",), "flood": ("flood",), "storm": ("storm", "cyclone", "hurricane", "typhoon"),
                "cholera": ("cholera",), "locusts": ("insect", "locust"), "plague": ("plague",),
                "food_insecurity": ("food",)}


def _adhoc_cerf(e, acts, actf, _try):
    """(country, hazard) -> [CERF allocation dicts] behind the pair's ad hoc AA allocations.
    The allocation code from activation_funding when recorded; otherwise the CERF allocation
    of that country and year whose emergency type matches the hazard (closest amount wins).
    Each carries agencies, sectors and planned / reached people from the CERF mirror."""
    ad = acts[acts["event_type"] == "adhoc_aa"]
    if ad.empty:
        return {}
    isos = sorted(set(ad["country_iso3"]))
    q = ", ".join(f"'{c}'" for c in isos)
    al = _try(f"""SELECT application_code, year, country_iso3, emergency_type, title, amount_approved,
                         individuals_planned, individuals_reached, aa_keyword
                  FROM aa.cerf_allocation WHERE country_iso3 IN ({q})""",
              ["application_code", "year", "country_iso3", "emergency_type", "title", "amount_approved",
               "individuals_planned", "individuals_reached", "aa_keyword"])
    out = {}
    for (c, h), evs in ad.groupby(["country_iso3", "hazard"]):
        picked = []
        for ev in evs.itertuples():
            y = int(str(ev.event_date)[:4]) if str(ev.event_date)[:4].isdigit() else None
            f = actf[(actf["country_iso3"] == c) & (actf["hazard"] == h)
                     & (actf["event_date"] == ev.event_date) & (actf["event_type"] == "adhoc_aa")
                     & (actf["fund_code"] == "cerf")]                 # CERF rows only
            mine = al[al["country_iso3"] == c]                         # never another country
            codes = [x for x in f["allocation_code"].dropna() if x]
            cand = mine[mine["application_code"].isin(codes)] if codes else mine.iloc[0:0]
            how = "recorded allocation code"
            if cand.empty and y is not None:
                # same country and year, emergency type matching the hazard; AA-tagged
                # allocations first; never the underfunded-emergencies window (-UF-)
                keys = HZ_EMERGENCY.get(h, (h,))
                cand = mine[(mine["year"] == y)
                            & mine["emergency_type"].fillna("").str.lower().map(lambda t: any(k in t for k in keys))
                            & ~mine["application_code"].str.contains("-UF-", na=False)]
                if cand["aa_keyword"].fillna(False).astype(bool).any():
                    cand = cand[cand["aa_keyword"].fillna(False).astype(bool)]
                target = f["amount_usd"].sum()
                if len(cand) > 1:
                    cand = (cand.iloc[[int((cand["amount_approved"] - target).abs().argmin())]]
                            if target > 0 else cand.iloc[0:0])        # ambiguous: show nothing
                how = "matched by country, year and emergency type"
            for a in cand.itertuples():
                if a.application_code not in [p["code"] for p in picked]:
                    picked.append({"code": a.application_code, "year": int(a.year), "emergency": a.emergency_type,
                                   "title": a.title, "usd": _num(a.amount_approved), "how": how,
                                   "event": str(ev.event_date),
                                   "url": f"https://cerf.un.org/what-we-do/allocation/{int(a.year)}/summary/{a.application_code}"})
        if not picked:
            continue
        codes = ", ".join(f"'{p['code']}'" for p in picked)
        pr = _try(f"""SELECT application_code, project_code, agency_short_name AS agency, amount_approved,
                             people_planned, people_reached, sector_name
                      FROM aa.cerf_project WHERE application_code IN ({codes})""",
                  ["application_code", "project_code", "agency", "amount_approved", "people_planned",
                   "people_reached", "sector_name"])
        ps = _try(f"""SELECT p.application_code, s.cerf_sector_name AS sector, s.sector_amount
                      FROM aa.cerf_project_sector s JOIN aa.cerf_project p USING (project_code)
                      WHERE p.application_code IN ({codes})""",
                  ["application_code", "sector", "sector_amount"])
        for p_ in picked:
            x = pr[pr["application_code"] == p_["code"]]
            p_["agencies"] = [{"agency": a, "usd": float(g["amount_approved"].sum())}
                              for a, g in x.groupby("agency")] if len(x) else []
            p_["agencies"].sort(key=lambda z: -z["usd"])
            p_["planned"] = _num(x["people_planned"].sum()) if len(x) else None
            p_["reached"] = _num(x["people_reached"].sum()) if len(x) and x["people_reached"].notna().any() else None
            y_ = ps[ps["application_code"] == p_["code"]]
            p_["sectors"] = sorted(({"sector": k, "usd": float(v)} for k, v in
                                    y_.groupby("sector")["sector_amount"].sum().items()), key=lambda z: -z["usd"])
        out[(c, h)] = picked
    return out


PRE_SERIES = {}   # year -> the whole annual pre-arranged series (assemble fills it; the tile label quotes it)


def _year_history(d, e, excl, _try):
    """What the year selector needs to show a past year AS AT 31 DECEMBER, per (country,
    hazard): the status reports (mapped as aa.v_framework_lifecycle maps them, consecutive
    repeats dropped), the people-covered figures, the years of the ad hoc allocations, the
    pre-arranged stock of each year (dashboards.funding_series: a stock as at year end, never
    summed over years; flagged when inferred from the version record) and, for a framework
    flagged retired today, a DERIVED retirement date (none is recorded): the day after its last
    version's validity ended, else the first status report saying dormant / retired.
    Only past years are kept — the current year is the live record."""
    from dashboards import funding_series
    past = f"{TODAY.year}-01-01"
    pair, country, series = {}, {}, {}

    def slot(c, h):
        return pair.setdefault((c, h), {})
    st = _try("""SELECT country_iso3, hazard, as_of, status FROM aa.framework_status
                 WHERE as_of IS NOT NULL ORDER BY country_iso3, hazard, as_of, updated_at""",
              ["country_iso3", "hazard", "as_of", "status"])
    sh_all = {}
    for (c, h), g in st.groupby(["country_iso3", "hazard"]):
        day = {}                                   # one per day: the last one entered
        for x in g.itertuples():
            day[str(x.as_of)[:10]] = SHEET_LIFECYCLE.get(x.status, "pipeline")
        rows = []
        for a, cat in sorted(day.items()):
            if not rows or rows[-1][1] != cat:
                rows.append([a, cat])
        sh_all[(c, h)] = rows
        if any(a < past for a, _ in rows):
            slot(c, h)["sh"] = [r for r in rows if r[0] < past]
    pc = _try("""SELECT country_iso3, hazard, as_of, source, people_covered FROM aa.people_covered
                 WHERE people_covered IS NOT NULL AND as_of IS NOT NULL""",
              ["country_iso3", "hazard", "as_of", "source", "people_covered"])
    pc = pc[pc["as_of"].astype(str) < past]
    for (c, h, a), g in pc.groupby(["country_iso3", "hazard", "as_of"]):
        rep = g[g["source"].fillna("").str.contains("reporting")]   # the year-end report first
        slot(c, h).setdefault("cov", []).append([str(a)[:10], int((rep if len(rep) else g)["people_covered"].iloc[0])])
    ad = _try(f"SELECT country_iso3, hazard, event_date FROM aa.adhoc_activation "
              f"WHERE event_type NOT IN ({excl})", ["country_iso3", "hazard", "event_date"])
    for x in ad.itertuples():
        if str(x.event_date)[:4].isdigit():
            slot(x.country_iso3, x.hazard).setdefault("adhoc", []).append(int(str(x.event_date)[:4]))
    pre, _ = funding_series(d)
    pre = pre[(pre["kind"] == "prearranged") & pre["amount_usd"].notna()
              & (pre["year"].astype(int) >= YEAR_FIRST) & (pre["year"].astype(int) < TODAY.year)]
    pairs = set(zip(d["current"]["country_iso3"], d["current"]["hazard"]))
    for (c, h, y), g in pre.groupby(["country_iso3", "hazard", "year"]):
        y = str(int(y))
        usd, drv = float(g["amount_usd"].sum()), int((g["source"] == "version-inferred").any())
        series[y] = series.get(y, 0.0) + usd
        # rows of no single framework (a pooled-fund allocation of a country with several
        # hazards): the country's, counted while any of its frameworks is shown
        tgt = slot(c, h).setdefault("pre", {}) if (c, h) in pairs else country.setdefault(c, {})
        old = tgt.get(y, [0.0, 0])
        tgt[y] = [old[0] + usd, old[1] or drv]
    ret = pd.read_sql(
        """SELECT r.country_iso3, r.hazard,
                  (SELECT v.valid_until FROM aa.framework_version v
                   WHERE v.country_iso3 = r.country_iso3 AND v.hazard = r.hazard
                   ORDER BY v.valid_from DESC NULLS LAST, v.version DESC LIMIT 1) AS last_until
           FROM aa.country_hazard r WHERE r.retired""", e)
    for x in ret.itertuples():
        s = slot(x.country_iso3, x.hazard)
        s["retired"] = True
        if _s(x.last_until):
            s["ret_on"] = str(pd.Timestamp(str(x.last_until)).date() + _dt.timedelta(days=1))
            s["ret_note"] = f"last version valid until {str(x.last_until)[:10]}"
        else:
            first = next((a for a, cat in sh_all.get((x.country_iso3, x.hazard), []) if cat == "retired"), None)
            if first:
                s["ret_on"], s["ret_note"] = first, f"first status report saying dormant / retired, {first}"
    return {"pair": pair, "country": country, "series": series}


def assemble(d, e):
    cur = d["current"].sort_values("country_name")
    ver = pd.read_sql("SELECT * FROM aa.framework_version", e)
    win = pd.read_sql(
        """WITH w AS (
             SELECT country_iso3, hazard, version, window_name, all_in, basis, allocation_usd
             FROM aa.window
             UNION ALL
             SELECT e.country_iso3, e.hazard, e.version, e.window_name, NULL, e.basis, NULL
             FROM aa.entered_window e
             WHERE NOT EXISTS (SELECT 1 FROM aa.window k
                               WHERE (k.country_iso3, k.hazard, k.version, k.window_name)
                                   = (e.country_iso3, e.hazard, e.version, e.window_name)))
           SELECT w.*, p.n_activations AS sim_activations,
                  p.analysis_years, p.analysis_start, p.analysis_end,
                  p.return_period, p.activation_prob,
                  s.triggered, s.triggered_on
           FROM w LEFT JOIN aa.v_window_performance p
             USING (country_iso3, hazard, version, window_name)
           LEFT JOIN aa.window_status s
             USING (country_iso3, hazard, version, window_name)""", e)
    # the agency x sector split of each version's funding, per window (KB pages, sheets,
    # entered) — window_funding split rows; fund_source = pooled fund or financier
    fb = pd.read_sql(
        """SELECT country_iso3, hazard, version, window_name,
                  coalesce(fund_code, financier, 'unspecified') AS fund_source,
                  agency, sector, amount_usd, provenance
           FROM aa.v_window_funding_split
           WHERE amount_usd IS NOT NULL AND (agency IS NOT NULL OR sector IS NOT NULL)""", e)
    from dashboards import (EXCLUDED_EVENT_TYPES, read_simulated, sim_after_note,
                            sim_before_start, sim_when)
    sim = read_simulated(e)   # with event_date / event_time when the DB has them
    psb = fb.iloc[0:0]                                    # folded into window_funding
    excl = ", ".join(f"'{t}'" for t in EXCLUDED_EVENT_TYPES)
    acts = pd.read_sql(
        f"""SELECT a.country_iso3, a.hazard, a.event_type, a.event_date, a.window_name,
                  a.event_label, a.version, a.kb_framework, a.kb_event_date,
                  a.people_targeted, a.comments
           FROM aa.activation a WHERE a.event_type NOT IN ({excl}) ORDER BY a.event_date DESC""", e)
    actf = pd.read_sql(
        """SELECT f.country_iso3, f.hazard, f.event_date, f.window_name, f.event_label,
                  f.event_type, f.fund_code, f.allocation_code, f.amount_usd, c.year AS alloc_year
           FROM aa.activation_funding f
           LEFT JOIN (SELECT DISTINCT ON (application_code) application_code, year
                      FROM aa.cerf_allocation ORDER BY application_code, year) c
             ON c.application_code = f.allocation_code
           WHERE f.event_type NOT IN (""" + excl + ")", e)
    aurl = pd.read_sql(
        """SELECT kb_framework, event_date, country_iso3, url, released_usd, full_activation, note
           FROM aa.actual_activation""", e)
    cal = d["calendar"]
    kb = _kb_pages(e)

    def _try(sql, cols):
        """Read a table that may not exist yet on this DB: an empty frame, never a crash."""
        try:
            return pd.read_sql(sql, e)
        except Exception as ex:  # noqa: BLE001
            print(f"  ! {sql.split('FROM')[1].split()[0] if 'FROM' in sql else sql}: {ex}")
            return pd.DataFrame(columns=cols)

    # ad hoc AA allocations sit on the (country, hazard) pair, not on a version
    adhoc = _try(f"SELECT country_iso3, hazard, count(*) AS n FROM aa.adhoc_activation "
                 f"WHERE event_type NOT IN ({excl}) GROUP BY 1, 2",   # all years (a year selector will filter)
                 ["country_iso3", "hazard", "n"])
    adhoc_cerf = _adhoc_cerf(e, acts, actf, _try)
    n_adhoc = {(a.country_iso3, a.hazard): int(a.n) for a in adhoc.itertuples()}
    hist = _year_history(d, e, excl, _try)        # the year selector's dated records, per pair
    learn = _try(
        """SELECT id, title, url, publisher, year, doc_type, country_iso3, hazard, key_stat
           FROM aa.learning_document
           WHERE scope = 'country' AND NOT internal ORDER BY year DESC NULLS LAST, title""",
        ["id", "title", "url", "publisher", "year", "doc_type", "country_iso3", "hazard", "key_stat"])
    partners = _try(
        """SELECT country_iso3, hazard, version, name, acronym, org_type, roles, agency_parent,
                  amount_usd FROM aa.framework_partner ORDER BY org_type, name""",
        ["country_iso3", "hazard", "version", "name", "acronym", "org_type", "roles",
         "agency_parent", "amount_usd"])
    subg = _try(
        """SELECT country_iso3, agency, partner_name, partner_acronym, partner_type,
                  sum(subgrant_usd) AS usd
           FROM aa.cerf_subgrant WHERE is_aa AND country_iso3 IS NOT NULL
           GROUP BY 1, 2, 3, 4, 5 ORDER BY 1, 2, 6 DESC NULLS LAST""",
        ["country_iso3", "agency", "partner_name", "partner_acronym", "partner_type", "usd"])
    # every version's pre-arranged envelope (all funds; an 'all' total is dropped where the
    # per-fund split exists — the dashboards' rule) for the budget sanity check
    vfa = pd.read_sql(
        """SELECT country_iso3, hazard, version, fund_code, total_usd
           FROM aa.v_version_funding WHERE kind = 'prearranged' AND total_usd IS NOT NULL""", e)
    envelope = _envelopes(vfa)
    pre_now = {}                          # pair -> pre-arranged now (the landing tile's rule)
    for (c_, h_, _), usd in _envelopes(d["vfund"]).items():
        pre_now[(c_, h_)] = pre_now.get((c_, h_), 0.0) + usd

    # ad hoc pairs absent from country_hazard (food insecurity, locusts…) still get a pin
    # on the ad hoc layer: synthesise a row with the country's name from any known row
    have = set(zip(cur["country_iso3"], cur["hazard"]))
    iso_name = dict(zip(cur["country_iso3"], cur["country_name"]))
    iso_region = dict(zip(cur["country_iso3"], cur["region"])) if "region" in cur else {}
    extra = [{"country_iso3": c_, "hazard": h_, "country_name": iso_name.get(c_),
              "region": iso_region.get(c_), "lifecycle": None, "technical_support": False,
              "retired": False, "synthetic": True}
             for (c_, h_) in sorted(n_adhoc) if (c_, h_) not in have]
    if extra:
        cur = pd.concat([cur, pd.DataFrame(extra)], ignore_index=True)

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
        countries.setdefault(c, {"name": _s(r["country_name"]), "region": _s(r.get("region")),
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
                        "years": _num(w.analysis_years),
                        "triggered": (None if w.triggered is None or pd.isna(w.triggered)
                                      else bool(w.triggered)),
                        "triggered_on": _s(w.triggered_on)} for w in w_v.itertuples()]
            # backtest: which window would have fired in which year (or storm)
            s_v = sim[(sim["country_iso3"] == c) & (sim["hazard"] == h)
                      & kb_key_match(sim["version"], v.version)]
            # a version's backtest is fixed before it is endorsed and real activations come
            # after: only rows dated before the year it took effect are simulation
            s_v, n_after, vf_y = sim_before_start(s_v, v.valid_from)
            backtest = None
            if len(s_v) or n_after:
                wins_bt = list(dict.fromkeys(w.window_name for w in w_v.itertuples())) or sorted(s_v["window_name"].unique())
                per_event = bool(s_v["event_label"].notna().any())   # numpy bool -> str under default=str
                rows, when = {}, {}
                for sr in s_v.itertuples():
                    key = (int(sr.sim_year), _s(sr.event_label) if per_event else None)
                    rows.setdefault(key, set()).add(sr.window_name)
                    if sim_when(sr) != str(sr.sim_year):   # the day / hour when recorded
                        when.setdefault(key, {})[sr.window_name] = sim_when(sr)
                yrs = [int(x) for x in w_v["analysis_start"].dropna()] + [int(x) for x in w_v["analysis_end"].dropna()]
                y0, y1 = ((min(yrs), max(yrs)) if yrs else
                          (int(s_v["sim_year"].min()), int(s_v["sim_year"].max())) if len(s_v) else
                          (vf_y - 1, vf_y - 1))
                if vf_y:
                    y1 = min(y1, vf_y - 1)
                    y0 = min(y0, y1)
                # the years the version has been in use: real activations only
                vu = pd.to_datetime(str(v.valid_until), errors="coerce") if _s(v.valid_until) else None
                use_end = int(vu.year) if vu is not None and pd.notna(vu) else TODAY.year
                if not per_event:
                    for y in range(y0, y1 + 1):
                        rows.setdefault((y, None), set())
                    if vf_y:
                        for y in range(vf_y, max(vf_y, min(use_end, TODAY.year)) + 1):
                            rows.setdefault((y, None), set())
                backtest = {"windows": wins_bt, "per_event": per_event, "start": y0, "end": y1,
                            "in_use_from": vf_y, "in_use_to": use_end if vu is not None and pd.notna(vu) else None,
                            "n_after": n_after, "after_note": sim_after_note(n_after, vf_y),
                            "rows": [{"year": k[0], "label": k[1], "fired": sorted(ws),
                                      "when": when.get(k, {})}
                                     for k, ws in sorted(rows.items(), key=lambda kv: (-kv[0][0], str(kv[0][1])))]}
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
            by_pair = (f_v.dropna(subset=["agency", "sector"])
                       .groupby(["agency", "sector"])["amount_usd"].sum()
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
                "dev_since": _s(getattr(v, "development_since", None)),
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
                "rollup": _s(v.window_rollup),
                "n_windows": tf.get("n_windows") if isinstance(tf.get("n_windows"), int) else None,
                "months": months, "months_src": months_src, "months_note": _s(mp.get("note")),
                "basis": _s(tf.get("basis")), "calibration": _s(tf.get("calibration")),
                "indicators": tf.get("indicators") or [],
                "data_sources": fm.get("data_sources") or [],
                "triggers": pg["triggers"] if pg else [],
                "learning": [x for x in (fm.get("learning") or fm.get("lessons_learned") or [])
                             if isinstance(x, dict)],
                "windows": windows, "backtest": backtest,
                "funding": {
                    "src": fund_src,
                    "agency": [{"agency": _s(x.agency), "fund": _s(x.fund_source) or "unspecified",
                                "usd": float(x.amount_usd)} for x in by_agency.itertuples()],
                    "sector": [{"sector": _s(x.sector), "fund": _s(x.fund_source) or "unspecified",
                                "usd": float(x.amount_usd)} for x in by_sector.itertuples()],
                    "fund": [{"fund": _s(x.fund_source) or "unspecified", "usd": float(x.amount_usd)}
                             for x in by_fund.itertuples()],
                    "pair": [{"agency": _s(x.agency), "sector": _s(x.sector), "usd": float(x.amount_usd)}
                             for x in by_pair.itertuples()],
                },
                "admin_level": fm.get("admin_level") if isinstance(fm.get("admin_level"), int) else None,
                "scope_raw": [str(x) for x in scope_raw],
                "scope_tiers_raw": (pg["tiers"] if pg else []) if not regional else [],
                "scope": None,      # filled by the geo pass
                "kb_page": bool(pg), "source": _s(v.source), "note": _s(v.note),
                # budget sanity: the version's pre-arranged envelope (v_version_funding, all
                # funds) — the sidebar compares the agency x sector split total against it
                "envelope": envelope.get((c, h, v.version)),
                "analysis_ref": _s(v.analysis_ref), "analysis_url": _analysis_url(_s(v.analysis_ref)),
                "partners": _partner_rows(partners[(partners["country_iso3"] == c)
                                                   & (partners["hazard"] == h)
                                                   & (partners["version"] == v.version)]),
                "partners_from": None,
            })
        # partners: a version without its own list borrows the latest version that has one
        with_p = [x for x in versions if x["partners"]]
        for x in versions:
            if not x["partners"] and with_p:
                src = with_p[-1]
                x["partners"], x["partners_from"] = src["partners"], src["v"]

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
                             "usd": _num(x.amount_usd),
                             # the allocation's public CERF page (year = allocation year)
                             "cerf_url": (f"https://cerf.un.org/what-we-do/allocation/"
                                          f"{int(x.alloc_year)}/summary/{x.allocation_code}"
                                          if x.fund_code == "cerf" and _s(x.allocation_code)
                                          and pd.notna(x.alloc_year) else None)}
                            for x in fr.itertuples()],
            })

        # the map and the sidebar default to the MOST RECENT version (as the KB map does);
        # the tracking view's in-force version is kept for reference
        for i, x in enumerate(versions):          # inferred: a newer endorsed version exists
            x["superseded"] = (x["status"] == "endorsed"
                               and any(y["status"] == "endorsed" for y in versions[i + 1:]))
            x["fully_triggered"] = fully_triggered(x, activations)
        latest = versions[-1]["v"] if versions else None
        in_force = _s(r.get("current_version"))
        if in_force not in {x["v"] for x in versions}:
            in_force = latest
        sheet_status = _s(r.get("status"))
        disp = _s(r.get("lifecycle"))                 # aa.v_framework_lifecycle — the one rule
        tech = bool(_f(r.get("technical_support")) or False)
        synthetic = bool(_f(r.get("synthetic")) or False)
        # map layers (the page filters; LAYER_ORDER decides the pin style)
        layers = []
        if disp in KB_LABEL:
            layers.append("framework")                # active · updating · development
        if disp == "retired":
            layers.append("retired")
        if n_adhoc.get((c, h)):
            layers.append("adhoc")                    # ad hoc AA allocations on the pair
        if tech:
            layers.append("tech")                     # OCHA technical support, whatever the lifecycle
        if not layers:
            continue                                  # conversation stage with nothing to show
        if disp is None or (disp == "pipeline" and not tech):
            disp = "adhoc" if "adhoc" in layers else "pipeline"
        months_now = (versions[-1]["months"] if versions else [])
        ring = "now" if disp == "active" and TODAY.month in months_now else None   # currently monitored
        n_fw_act = sum(1 for a in activations if a["type"] == "framework_aa")
        docs = learn[learn["country_iso3"].map(lambda xs: c in _list(xs))
                     & (learn["hazard"].isna() | (learn["hazard"] == h))] if len(learn) else learn
        countries[c]["fws"].append({
            "hazard": h, "status": sheet_status, "kb": kb_fw,
            "disp": disp, "disp_label": DISP_LABEL.get(disp, disp), "ring": ring, "n_act": n_fw_act,
            "n_act_all": len(activations), "n_adhoc": n_adhoc.get((c, h), 0),
            "adhoc_cerf": adhoc_cerf.get((c, h), []),
            "layers": layers, "layer": next(l for l in LAYER_ORDER if l in layers),
            "tech": tech,
            "hz_label": HAZ_LABEL.get(h, h.replace("_", " ").capitalize()),
            "glyph": HAZ_GLYPH.get(h, "other"),
            "latest": latest, "in_force": in_force,
            "page": None if synthetic else f"fw-{c.lower()}-{h}.html",
            "prearranged": _num(r.get("cerf_prearranged_usd")),
            "prearranged_year": _num(r.get("prearranged_year")),
            "pre_now": pre_now.get((c, h)),           # the landing tile's pre-arranged 'now'
            "covered": _num(r.get("people_covered")),
            "current": latest, "versions": versions, "activations": activations,
            "hist": hist["pair"].get((c, h)) or {},   # the year selector's past-year records
            "learning_docs": [{"id": int(x.id), "title": _s(x.title), "url": _s(x.url),
                               "publisher": _s(x.publisher),
                               "year": int(x.year) if _num(x.year) is not None else None,
                               "type": _s(x.doc_type), "stat": _s(x.key_stat)}
                              for x in docs.itertuples()],
        })
    out = {iso: cd for iso, cd in countries.items() if cd["fws"]}
    for iso, cd in out.items():                   # pre-arranged of no single framework, per year
        if hist["country"].get(iso):
            cd["pre_x"] = hist["country"][iso]
    PRE_SERIES.clear(); PRE_SERIES.update(hist["series"])   # every row of each past year
    # funded sub-grantees (CERF AA allocations) are per country: one list per country
    for iso, cd in out.items():
        s = subg[subg["country_iso3"] == iso] if len(subg) else subg
        groups = {}
        for x in s.itertuples():
            groups.setdefault(_s(x.agency) or "unspecified agency", []).append(
                {"name": _s(x.partner_name), "acronym": _s(x.partner_acronym),
                 "type": _s(x.partner_type), "usd": _num(x.usd)})
        cd["subgrants"] = [{"agency": a, "partners": ps} for a, ps in
                           sorted(groups.items(), key=lambda kv: -sum(p["usd"] or 0 for p in kv[1]))]
    return out


def _expired(valid_until):
    if not valid_until:
        return False
    m = re.match(r"(\d{4})(?:-(\d{1,2}))?", str(valid_until))
    if not m:
        return False
    mo = int(m.group(2)) if m.group(2) and 1 <= int(m.group(2)) <= 12 else 12
    return (int(m.group(1)), mo) < (TODAY.year, TODAY.month)


def fully_triggered(v, activations):
    """Did this version fire in full? Same rule as aa.v_framework_lifecycle (which decides
    the framework status): from the windows' curated trigger state (aa.window_status) — any
    window for an all-in / exclusive framework, every window for independent ones; a version
    with no windows registered falls back to its activations (any not marked partial)."""
    wins = v["windows"]
    if not wins:
        return any(a["version"] == v["v"] and a["type"] == "framework_aa"
                   and a["full"] is not False for a in activations)
    fired = [w["triggered"] is True for w in wins]
    any_mode = v["rollup"] == "exclusive" or any(w["all_in"] is True for w in wins)
    return any(fired) if any_mode else all(fired)


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
                tiers = []
                for t in v.get("scope_tiers_raw") or []:
                    if t["rest"]:
                        tiers.append({"label": t["label"], "pcodes": [], "rest": True})
                        national = True
                    else:
                        pc, um, _ = m.match(t["items"], v["admin_level"], cd["name"])
                        tiers.append({"label": t["label"], "pcodes": pc, "rest": False})
                        unmatched += um
                if tiers:
                    pcodes = sorted({pc for t in tiers for pc in t["pcodes"]})
                    unmatched = sorted(set(unmatched))
                v["scope"] = {"pcodes": pcodes, "unmatched": unmatched, "national": national,
                              "tiers": tiers}
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
                elif not sc["pcodes"]:
                    # zone unknown or not mappable (a zone south of 17°N, communes without
                    # names…): show the whole country rather than nothing, and say so
                    v["scope"] = dict(sc, national=True, approx=True)
        if m is not None:
            cd["area_names"] = {pc: rec["name"] for pc, rec in m.used.items()}
            b = write_country_geo(iso, m, adm0)
            if b is not None:
                bboxes[iso] = [float(x) for x in b]
        cd["bbox"] = bboxes.get(iso)
        cd["has_geo"] = m is not None


def tile_figures(countries, layers):
    """Headline figures for a set of enabled layers — mirrors updateTiles() in LANDING_JS.
    A pair is shown when any of its layers is enabled; framework figures (count, pre-arranged,
    people covered) count pairs shown ON the framework layer; activations count every shown pair."""
    shown = [f for cd in countries.values() for f in cd["fws"] if set(f["layers"]) & set(layers)]
    fw = [f for f in shown if "framework" in layers and "framework" in f["layers"]]
    return {"n_fw": len(fw),
            "n_active": sum(1 for f in fw if f["disp"] == "active"),
            "n_upd": sum(1 for f in fw if f["disp"] == "updating"),
            "n_dev": sum(1 for f in fw if f["disp"] == "development"),
            "pre": sum(f["pre_now"] or 0 for f in fw),
            "n_act": sum(f["n_act_all"] for f in shown),
            "covered": sum(f["covered"] or 0 for f in fw)}


# ---------------------------------------------------------------- page
def build_landing(page, d, e):
    cur = d["current"]
    names = dict(zip(cur["country_iso3"], cur["country_name"]))
    countries = assemble(d, e)
    svg, bboxes, wdata = world_data(set(countries), names)
    for iso, cd in countries.items():
        if not cd.get("name"):                        # ad hoc-only country: Natural Earth name
            cd["name"] = (wdata.get(iso) or {}).get("n") or iso
        cd["lbbox"] = bboxes.get(iso)                 # layout box (world file, largest polygon)
        cd["centroid"] = CENTROID.get(iso) or (
            [(cd["lbbox"][1] + cd["lbbox"][3]) / 2, (cd["lbbox"][0] + cd["lbbox"][2]) / 2]
            if cd["lbbox"] else None)
        cd["dir"] = DIRECTIONS.get(iso, (0.7, -0.7))
    geo_pass(countries, bboxes)

    # headline tiles follow the map: the same rule as the page's updateTiles() (JS), here
    # for the default layer set so the static HTML matches what the page first shows.
    # Status from aa.v_framework_lifecycle; pre-arranged = the latest version's envelope of
    # every framework shown (development ones included — they just have no envelope yet)
    t = tile_figures(countries, {"framework"})
    n_shown = t["n_fw"]

    body = f"""
<div class='hero'>
 <div class='yearbar' id='yearbar' role='group' aria-label='Year shown on the map'><span class='yl'>Year</span>
  <button type='button' data-y='' class='on' aria-pressed='true'>All years, to today</button>{"".join(
      f"<button type='button' data-y='{y}' aria-pressed='false'>{y}{' (today)' if y == TODAY.year else ''}</button>"
      for y in range(TODAY.year, YEAR_FIRST - 1, -1))}
 </div>
 <p class='yearnote' id='yearnote' hidden>Past years are reconstructed from the framework records (version dates and
  status history): a framework counts for a year if a version was valid at any time during it. They will
  be replaced by the official year-end figures once those are loaded.</p>
 <div class='tiles gtiles' id='gtiles'>
  <div class='gcap' id='gcap'>Global portfolio — all layers currently shown on the map</div>
  <div class='tile' id='t-fw'><div class='v'>{t["n_fw"]}</div><div class='l'>frameworks on the map · {t["n_active"]} active · {t["n_upd"]} being updated · {t["n_dev"]} in development</div></div>
  <div class='tile' id='t-pre'><div class='v'>${t["pre"]/1e6:,.0f}M</div><div class='l'>pre-arranged now (CERF and country and regional funds), frameworks shown</div></div>
  <div class='tile' id='t-act'><div class='v'>{t["n_act"]}</div><div class='l'>activations</div></div>
  <div class='tile' id='t-cov'><div class='v'>{t["covered"]/1e6:,.1f}M</div><div class='l'>people covered, frameworks shown</div></div>
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
<p class='maphelp'><b>Reading the map.</b> Published triggers, windows, pre-arranged financing and activations
 across the AA portfolio — CERF, country-based and regional pooled funds. Pin colour = framework status,
 inferred from the most recent version; each red dot = one past activation; an amber ring = in its monitoring
 season this month. <b>Click a country or a pin</b> to zoom in and see the areas each framework covers; the
 <b>layer toggles</b> in the map legend choose what is drawn, and the figures above follow them.</p>
<details id='statushelp' class='statushelp'><summary>How statuses work — version lifecycle and the framework status inferred from it</summary>
 <div class='sh-grid'>
  <svg viewBox='0 0 780 362' class='sh-svg' role='img' aria-label='Status diagram'>
   <defs><linearGradient id='shsplit' x1='0' y1='0' x2='1' y2='1'><stop offset='50%' stop-color='#dbeafe'/><stop offset='50%' stop-color='#e8f1f8'/></linearGradient><marker id='arr' viewBox='0 0 10 10' refX='9' refY='5' markerWidth='7' markerHeight='7' orient='auto-start-reverse'><path d='M0,0 L10,5 L0,10 z' fill='#64748b'/></marker></defs>
   <text x='10' y='22' class='sh-h'>Framework VERSION status (stored: one of three, set in the admin)</text>
   <g class='sh-box'><rect x='10' y='40' width='120' height='40' rx='8'/><text x='70' y='65'>pre-development</text></g>
   <g class='sh-box'><rect x='170' y='40' width='120' height='40' rx='8'/><text x='230' y='65'>in development</text></g>
   <g class='sh-box sh-on'><rect x='330' y='40' width='120' height='40' rx='8'/><text x='390' y='65'>endorsed</text></g>
   <g class='sh-box sh-ev'><rect x='500' y='20' width='130' height='34' rx='8'/><text x='565' y='42'>windows triggered</text></g>
   <g class='sh-box sh-ev'><rect x='500' y='66' width='130' height='34' rx='8'/><text x='565' y='88'>validity ended</text></g>
   <g class='sh-box sh-off'><rect x='670' y='40' width='100' height='40' rx='8'/><text x='720' y='65'>superseded</text></g>
   <line x1='130' y1='60' x2='168' y2='60' class='sh-arr'/><line x1='290' y1='60' x2='328' y2='60' class='sh-arr'/>
   <line x1='450' y1='55' x2='498' y2='40' class='sh-arr'/><line x1='450' y1='65' x2='498' y2='80' class='sh-arr'/>
   <line x1='630' y1='45' x2='668' y2='56' class='sh-arr'/><line x1='630' y1='78' x2='668' y2='66' class='sh-arr'/>
   <text x='500' y='118' class='sh-note'>inferred, not stored: each window is marked triggered / not triggered; the version is</text>
   <text x='500' y='132' class='sh-note'>fully triggered when every window activated (any window if all-in). Superseded = a newer</text>
   <text x='500' y='146' class='sh-note'>endorsed version exists. The next version starts in development.</text>
   <text x='10' y='176' class='sh-h'>FRAMEWORK status (inferred from the most recent version — aa.v_framework_lifecycle)</text>
   <g class='sh-box sh-on'><rect x='10' y='192' width='220' height='34' rx='8'/><text x='120' y='214'>Active</text></g>
   <text x='240' y='206' class='sh-note'>most recent version is endorsed, in validity and has not fully triggered</text>
   <text x='240' y='220' class='sh-note'>(partial triggers of independent windows keep it active) · amber ring = in its monitoring season this month</text>
   <g class='sh-box sh-upd'><rect x='10' y='234' width='220' height='34' rx='8'/><text x='120' y='256'>Being updated</text></g>
   <text x='240' y='248' class='sh-note'>an endorsed framework whose most recent version fully triggered or reached the end of its</text>
   <text x='240' y='262' class='sh-note'>validity, or whose next version is already in development — the framework stands, a new version is coming</text>
   <g class='sh-box sh-dev'><rect x='10' y='276' width='220' height='34' rx='8'/><text x='120' y='298'>In development</text></g>
   <text x='240' y='290' class='sh-note'>no endorsed version yet — the framework is being built for the first time</text>
   <g class='sh-box sh-off'><rect x='10' y='318' width='220' height='34' rx='8'/><text x='120' y='340'>Retired (layer off by default)</text></g>
   <text x='240' y='332' class='sh-note'>a manual flag on the framework (country × hazard) in the admin — overrides everything above</text>
  </svg>
  <div class='sh-layers'>
   <b>Map layers.</b> <span class='dot' style='background:{KB_COLOR["active"]}'></span><b>Current frameworks</b> — every framework whose status is active, being updated or in development (the default view; the headline figures follow whatever is shown).
   <span class='dot' style='background:{LAYER_COLOR["adhoc"]}'></span><b>Ad hoc allocations</b> — countries and hazards that received ad hoc anticipatory-action money without a framework version (light green; a framework that also received ad hoc money stays drawn as a framework).
   <span class='dot' style='background:{LAYER_COLOR["retired"]}'></span><b>Retired</b> — frameworks flagged retired in the admin, drawn in grey so past coverage can be compared with today's.
   <span class='dot dot-hollow' style='border-color:{LAYER_COLOR["tech"]}'></span><b>Technical support</b> — countries where OCHA supported the framework technically without a funding commitment, whatever their status (including pipeline ones like Palau and Tonga), drawn as a hollow teal pin.
  </div>
 </div>
</details>
<div class='tiles' style='margin-top:18px'>
 <div class='tile'><a href='dashboards.html'><b>Dashboards</b></a><div class='l'>funding · allocations · delivery</div></div>
 <div class='tile'><a href='hierarchy.html'><b>Portfolio explorer</b></a><div class='l'>framework › version › window › activation</div></div>
 <div class='tile'><a href='entry.html'><b>Enter / ingest a framework</b></a><div class='l'>upload a PDF or fill the form — writes to the DB</div></div>
 <div class='tile'><a href='overview.html'><b>Data &amp; schema review</b></a><div class='l'>tables · reconciliation · roadmap</div></div>
</div>
<script>window.L = {json.dumps(countries, default=str)};
window.HAZ = {json.dumps(HAZ_COLOR)}; window.COLOR = {json.dumps(KB_COLOR)};
window.KBLABEL = {json.dumps(DISP_LABEL)}; window.GLYPH = {json.dumps(HAZARD_SVG)};
window.LAYER_ORDER = {json.dumps(list(LAYER_ORDER))}; window.LAYER_COLOR = {json.dumps(LAYER_COLOR)};
window.LAYER_LABEL = {json.dumps(LAYER_LABEL)}; window.TRIGGER_VALIDATION_URL = {json.dumps(TRIGGER_VALIDATION_URL)};
window.WORLD = {json.dumps(wdata, separators=(",", ":"))};
window.VB = {{w:{VB_W:.2f}, h:{VB_H:.2f}}}; window.EEBOX = {json.dumps([round(x, 6) for x in EE_BBOX])};
window.EE = {{lam0:{EE_LAM0}, smax:{S_MAX_DEG}}};
window.CURMONTH = {json.dumps(TODAY.strftime("%B %Y"))};
window.YEARS = {json.dumps({"first": YEAR_FIRST, "now": TODAY.year, "today": TODAY.isoformat(),
                            "series": {y: round(v) for y, v in PRE_SERIES.items()}})};</script>
<script src="sankey.js"></script>
<script>{LANDING_JS}</script>
<style>{LANDING_CSS}</style>"""
    page("index.html", "OCHA Anticipatory Action — portfolio", body)


LANDING_CSS = r"""
:root { --ocha:#1a6bb5; --ink:#222; --muted:#777; --line:#e3e6ea; }
.hero { text-align:left; padding:6px 0 2px; }
.statushelp { margin-top:14px; background:#fff; border:1px solid #e6eaef; border-radius:12px; padding:8px 16px; }
.statushelp summary { cursor:pointer; color:var(--ocha); font-size:13px; }
.sh-grid { overflow-x:auto; padding:8px 0 4px; } .sh-svg { width:100%; max-width:820px; height:auto; display:block; font-family:-apple-system,'Segoe UI',Roboto,sans-serif; }
.sh-h { font-size:12px; font-weight:700; fill:#0f2540; } .sh-note { font-size:10.5px; fill:#475569; }
.sh-box rect { fill:#f1f5f9; stroke:#cbd5e1; } .sh-box text { font-size:11px; fill:#1e293b; text-anchor:middle; font-weight:600; }
.sh-box.sh-on rect { fill:#dbeafe; stroke:#2171b5; } .sh-box.sh-dev rect { fill:#e8f1f8; stroke:#9ecae1; }
.sh-box.sh-ev rect { fill:#fef3c7; stroke:#f59e0b; } .sh-box.sh-off rect { fill:#f1f5f9; stroke:#94a3b8; }
.sh-box.sh-upd rect { fill:url(#shsplit); stroke:#2171b5; }
.sh-arr { stroke:#64748b; stroke-width:1.4; marker-end:url(#arr); }
.hero p { color:#556; max-width:860px; font-size:13.5px; }
.tiles { display:flex; gap:14px; flex-wrap:wrap; margin:12px 0; }
.tile { background:#fff; border:1px solid #e6eaef; border-radius:12px; padding:12px 18px; min-width:150px; box-shadow:0 1px 2px rgba(16,24,40,.05); }
.tile .v { font-size:22px; font-weight:700; } .tile .l { font-size:12px; color:var(--muted); }
.tile a { color:var(--ocha); }
/* the sidebar slides in only when a country is selected: the card keeps the world view's
   height (--maph, set by the page), the map goes square and the sidebar takes the rest */
.maprow { --maph: 420px; display:grid; grid-template-columns: minmax(0,1fr) 0px; gap:0; align-items:start;
  transition: grid-template-columns .9s cubic-bezier(.22,.8,.2,1), gap .9s; }
.maprow.open { grid-template-columns: var(--maph) minmax(0,1fr); gap:16px; }
.maprow .side { opacity:0; visibility:hidden; transition: opacity .3s; height:var(--maph); }
.maprow.open .side { opacity:1; visibility:visible; transition: opacity .4s .5s; }
@media (max-width: 760px) {
  .maprow, .maprow.open { grid-template-columns: 1fr; gap:12px; }
  .maprow .side, .maprow.open .side { height:auto; max-height:none; opacity:1; visibility:visible; }
  .mapbox.compact .callout, .mapbox.compact .leader { display:none; }
  .mapbox.compact .cdot { r:2.5; }
  .mapbox.compact .maplegend { display:none; }
  .mapbox.compact #map.zoomed ~ .maplegend { display:block; left:8px; bottom:8px; font-size:10.5px; padding:6px 9px; max-width:70%; }
  .backbtn { top:8px; left:8px; padding:5px 10px; font-size:12px; }
  .hero p { font-size:13px; }
  .wl-pins { display:flex; flex-wrap:wrap; gap:6px 14px; margin-top:6px; }
  .wl-pin { display:inline-flex; align-items:center; gap:5px; }
  .wl-pin .iconbox { width:20px; height:20px; cursor:default; } .wl-pin .iconbox svg.hz { width:13px; height:13px; }
  .tiles { gap:8px; } .tile { min-width:0; flex:1 1 40%; padding:10px 12px; } .tile .v { font-size:18px; }
}
.mapbox { background:linear-gradient(180deg,#eef3f8 0%,#e9eff5 100%); border-radius:12px; box-shadow:0 1px 2px rgba(16,24,40,.06), 0 8px 24px -12px rgba(16,24,40,.18); position:relative; overflow:hidden; border:1px solid #e6eaef; height:var(--maph); }
#map { width:100%; height:100%; display:block; }
.cty { fill:#f7f8fa; stroke:#d3d9df; stroke-width:.45; vector-effect:non-scaling-stroke; transition: opacity .5s, fill .3s; }
.cty.on { fill:#cfe1f3; stroke:#8fb4d9; stroke-width:.7; cursor:pointer; }
.cty.on:hover { fill:#b9d3ec; }
.cty:not(.on):hover { fill:#eef1f5; }
#map.zoomed .cty { opacity:0; pointer-events:none; }
#map.zooming .cty { transition: none; }
#map.zooming .cty.on { fill:#cfe1f3; }
.nb { fill:#f3f5f8; stroke:#c5ccd5; stroke-width:.6; vector-effect:non-scaling-stroke; stroke-linejoin:round; }
.nb:hover { fill:#e9edf2; }
.a0 { fill:#fff; stroke:#2c3a55; stroke-width:1.25; vector-effect:non-scaling-stroke; stroke-linejoin:round; }
.a1 { fill:#f5f8fb; stroke:#b3c2d3; stroke-width:.55; vector-effect:non-scaling-stroke; stroke-linejoin:round; transition: fill .15s; }
.a1:hover { fill:#e6edf5; }
.sc { stroke:#fff; stroke-width:.7; vector-effect:non-scaling-stroke; fill-opacity:.82; cursor:pointer; transition: fill-opacity .2s; stroke-linejoin:round; }
.sc:hover { fill-opacity:1; }
.nat { fill-opacity:.82; pointer-events:none; }
#adm { opacity:0; transition: opacity .5s ease; } #adm.show { opacity:1; }
/* callouts (KB style) */
.labelpane { position:absolute; inset:0; pointer-events:none; transition: opacity .35s; }
.labelpane.hide { opacity:0; }
.leadersvg { position:absolute; inset:0; width:100%; height:100%; overflow:visible; }
.leader { stroke:#94a3b8; stroke-width:1; stroke-linecap:round; }
.cdot { fill:#334155; stroke:#fff; stroke-width:1.6; }
.callout { position:absolute; display:flex; flex-direction:column; align-items:flex-start; pointer-events:auto; visibility:hidden; }
.cname { font-weight:650; font-size:11px; color:#0f2540; white-space:nowrap; line-height:1.15; margin-bottom:1px; cursor:pointer; letter-spacing:.1px; text-shadow:0 0 3px #fff,0 0 3px #fff; }
.cname:hover { text-decoration:underline; }
.hrow { display:flex; align-items:center; gap:4px; margin:1px 0; }
.hlab { font-size:10px; font-weight:450; color:#243b55; white-space:nowrap; line-height:1.15; text-shadow:0 0 3px #fff,0 0 3px #fff; }
.iconbox { position:relative; display:inline-flex; align-items:center; justify-content:center; width:22px; height:22px;
  border-radius:7px; border:1.5px solid #fff; box-shadow:0 1px 2px rgba(15,23,42,.28), 0 2px 6px rgba(15,23,42,.14); cursor:pointer; flex:none; transition: transform .15s; }
.iconbox svg.hz { width:15px; height:15px; display:block; }
/* 'being updated': a diagonal two-tone fill (active on one half, development on the other) */
.iconbox:hover { transform:scale(1.12); filter:brightness(1.06); }
/* in its monitoring season: a calm, static amber ring — no animation (2026-10-01: the pulse
   read as false urgency and is a problem for motion-sensitive readers) */
.iconbox.able-now { box-shadow:0 0 0 2px #fff, 0 0 0 4px #f5a300, 0 1px 3px rgba(0,0,0,.35); }
.iconbox.able-off { box-shadow:0 0 0 2px #f6c95f, 0 1px 3px rgba(0,0,0,.4); }
.actdots { position:absolute; right:-4px; bottom:calc(100% - 5px); width:31px; display:flex; flex-direction:row-reverse; flex-wrap:wrap-reverse; gap:1px; pointer-events:none; }
.rm { display:inline-block; width:9px; height:9px; border-radius:50%; background:#e3322d; box-shadow:0 0 0 1.5px #fff, 0 0 0 2.5px #e3322d; margin:0 3px; vertical-align:-1px; }
.rm.old { background:#fff; box-shadow:none; border:2px solid #e3322d; width:6px; height:6px; }
a.rm:hover { transform:scale(1.3); }
/* the backtest grid keeps its natural width: year | wt1 | wt2, not spread over the sidebar */
table.mini.bt { table-layout:auto; width:auto; } table.bt th.bt-c { font-size:10.5px; line-height:1.2; white-space:normal; min-width:40px; max-width:120px; }
.bt-key { margin:4px 0 8px; color:#64748b; }
td.bt-na { background:#eef1f5; }
table.bt td.bt-use { background:#fbf6ee; }
.bt-usetag { display:inline-block; padding:0 5px; border-radius:8px; font-size:9.5px; font-weight:600; background:#f6ead3; color:#7a5a17; margin-left:3px; vertical-align:1px; }
.bt-sw { display:inline-block; width:13px; height:10px; border:1px solid #eadcc0; vertical-align:-1px; background:#fbf6ee; }
table.acttbl { table-layout:fixed; width:100%; } table.acttbl td, table.acttbl th { overflow-wrap:anywhere; vertical-align:top; }
table.acttbl tr.oldv td { background:#f8fafc; }
.fhead .actdots, .wl-pin .actdots { display:none; }
.actdot { width:7px; height:7px; border-radius:50%; background:#e3322d; border:1.5px solid #fff; display:inline-block; }
.maplegend { position:absolute; left:12px; bottom:12px; font-size:11.5px; line-height:1.55; background:rgba(255,255,255,.86); backdrop-filter:blur(6px); -webkit-backdrop-filter:blur(6px); padding:9px 12px;
  border-radius:10px; box-shadow:0 1px 2px rgba(16,24,40,.08), 0 6px 18px -8px rgba(16,24,40,.25); border:1px solid rgba(226,232,240,.9); z-index:3; color:#334155; transition: opacity .3s; }
.maplegend b { color:#0f2540; }
.maplegend .dot { display:inline-block; width:12px; height:12px; border-radius:50%; margin-right:5px; vertical-align:-1px; }
.maplegend .sq { display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:5px; vertical-align:-1px; }
.backbtn { position:absolute; top:12px; left:12px; z-index:4; padding:6px 13px; border:1px solid #dbe2ea;
  border-radius:18px; background:rgba(255,255,255,.9); backdrop-filter:blur(6px); cursor:pointer; font-size:12.5px; color:#1e293b; box-shadow:0 1px 2px rgba(16,24,40,.08), 0 4px 12px -6px rgba(16,24,40,.25); }
.backbtn:hover { background:#fff; border-color:#b6c2d1; }
.tip { position:absolute; z-index:5; background:rgba(15,37,64,.92); color:#fff; font-size:12px; padding:5px 10px;
  border-radius:6px; pointer-events:none; white-space:nowrap; transform:translate(-50%,-135%); box-shadow:0 4px 12px -4px rgba(0,0,0,.35); }
/* sidebar (KB info-pop styling) */
.side { background:#fff; border:1px solid #e6eaef; border-radius:12px; padding:12px 16px 16px;
  overflow-y:auto; scrollbar-gutter:stable; font-size:12.5px; line-height:1.45; color:var(--ink); box-shadow:0 1px 2px rgba(16,24,40,.06), 0 8px 24px -12px rgba(16,24,40,.18); box-sizing:border-box; }
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
.b-updating { background:linear-gradient(135deg,#dbeafe 0 50%,#eef4fa 50% 100%); color:#1a5fa0; border:1px solid #9ecae1; }
.b-tech { background:#f3e8ff; color:#6b21a8; }
.pillars { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin:12px 0 8px; }
.pillars.four { grid-template-columns:repeat(4,1fr); }
.pillar { border:1px solid #dfe6ee; border-radius:10px; padding:8px 10px; cursor:pointer; background:#fff; transition:border-color .15s, background .15s; }
.pillar:hover { border-color:#9ecae1; } .pillar.on { border-color:var(--ocha); background:#eef5fc; box-shadow:inset 0 -3px 0 var(--ocha); }
.pillar .pk { font-size:10.5px; text-transform:uppercase; letter-spacing:.04em; color:#64748b; }
.pillar .pv { font-size:15px; font-weight:700; color:#0f2540; margin-top:2px; line-height:1.2; }
.pillar .ps { font-size:11px; color:#475569; margin-top:2px; }
@media (max-width:759px){ .pillars, .pillars.four { grid-template-columns:repeat(2,1fr); } }
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
.scopelist { font-size:12px; color:#334; line-height:1.5; margin:3px 0; }
table.bt th { position:sticky; top:0; } table.bt td { padding:2px 6px; } table.bt tr.bt-on td { background:#fbfcfe; }
table.bt .bt-c { text-align:center; min-width:40px; } table.bt td.lbl { width:auto; min-width:44px; }
.bt-dot { display:inline-block; width:9px; height:9px; border-radius:50%; }
/* headline tiles follow the map layers; when a country is open they step back as the GLOBAL
   portfolio (caption + subdued) and the country's own figures sit at the top of the sidebar */
.yearbar { display:flex; flex-wrap:wrap; align-items:center; gap:4px; margin:-4px 0 6px; font-size:12px; }
.yearbar .yl { color:#64748b; font-size:11px; text-transform:uppercase; letter-spacing:.05em; margin-right:4px; }
.yearbar button { font:inherit; padding:2px 9px; border:1px solid #d5dbe3; border-radius:12px; background:#fff; color:#334155; cursor:pointer; }
.yearbar button:hover { border-color:#2171b5; }
.yearbar button.on { background:#2171b5; border-color:#2171b5; color:#fff; font-weight:600; }
.yearnote { margin:0 0 8px; font-size:12px; color:#92400e; background:#fffbeb; border:1px solid #fde68a; border-radius:8px; padding:5px 10px; }
.drv { display:inline-block; margin-left:5px; padding:0 5px; border:1px dashed #b45309; border-radius:6px; font-size:10px; font-weight:600; color:#b45309; vertical-align:1px; cursor:help; }
.gtiles { position:relative; transition: opacity .3s; }
.gtiles .gcap { flex-basis:100%; font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:#64748b; margin:-2px 0 -6px 2px; }
.gtiles.global { opacity:.72; } .gtiles.global .tile { background:#f6f8fa; border-style:dashed; box-shadow:none; }
.gtiles.global .tile .v { font-size:18px; color:#475569; } .gtiles.global .gcap { color:#b45309; font-weight:700; }
.ctiles { display:grid; grid-template-columns:repeat(4,1fr); gap:6px; margin:8px 0 4px; }
.ctiles .ctile { background:#eef5fc; border:1px solid #cfe1f3; border-radius:8px; padding:6px 8px; }
.ctiles .ctile .v { font-size:15px; font-weight:700; color:#0f2540; line-height:1.2; } .ctiles .ctile .l { font-size:10.5px; color:#475569; }
.ctiles .ccap { grid-column:1 / -1; font-size:10.5px; text-transform:uppercase; letter-spacing:.05em; color:#1a5fa0; font-weight:700; margin-bottom:-2px; }
@media (max-width:759px){ .ctiles { grid-template-columns:repeat(2,1fr); } }
/* map layer toggles (world legend) */
.layerctl { display:flex; flex-direction:column; gap:1px; margin:0 0 5px; padding-bottom:5px; border-bottom:1px solid #e2e8f0; }
.maplegend { width:max-content; font-variant-numeric:tabular-nums; }
.maplegend .cnt { color:#64748b; display:inline-block; min-width:1.6em; }
.maplegend .lsub { display:flex; gap:10px; white-space:nowrap; font-size:10.5px; color:#475569; }
.layerctl .lsub { margin:0 0 2px 22px; }
.maplegend .lsub.off { opacity:.35; }
.maplegend .lsub .dot { width:9px; height:9px; margin-right:4px; }
.layerctl label { display:flex; align-items:center; gap:6px; cursor:pointer; white-space:nowrap; }
.layerctl input { margin:0; accent-color:#2171b5; }
.layerctl .cnt { color:#64748b; }
.maplegend .dot-hollow, .sh-layers .dot-hollow { background:#fff !important; border:2.5px solid #2a9d8f; box-sizing:border-box; }
.maphelp { font-size:13px; color:#334155; line-height:1.55; margin:10px 2px 6px; max-width:980px; }
.sh-layers { font-size:12px; color:#334155; line-height:1.6; margin:6px 0 4px; }
.sh-layers .dot { display:inline-block; width:11px; height:11px; border-radius:50%; margin:0 4px 0 6px; vertical-align:-1px; }
/* technical support: a hollow teal pin (the glyph takes the teal too) */
.iconbox.tech { background:#fff !important; border:2px solid #2a9d8f; }
.iconbox.tech svg.hz [fill='#fff'] { fill:#2a9d8f; } .iconbox.tech svg.hz [stroke='#fff'] { stroke:#2a9d8f; }
.b-adhoc { background:#e3f4e1; color:#2a7a2f; } .b-pipeline { background:#f1f5f9; color:#475569; }
/* plain-language help: ⓘ with a hover / focus tooltip (keyboard reachable) */
.info { display:inline-grid; place-items:center; width:13px; height:13px; border-radius:50%; font-size:9.5px; font-weight:700; line-height:1;
  color:#fff; background:#94a3b8; margin-left:3px; cursor:help; position:relative; vertical-align:2px; font-style:normal; user-select:none; text-transform:none; letter-spacing:0; font-family:Georgia,serif; }
.info:hover, .info:focus { background:var(--ocha); outline:none; }
.info::after { content:attr(data-tip); position:absolute; left:50%; bottom:calc(100% + 6px); transform:translateX(-50%); width:max-content; max-width:240px;
  background:rgba(15,37,64,.95); color:#fff; font-size:11.5px; font-weight:400; line-height:1.35; padding:6px 9px; border-radius:6px; text-align:left; white-space:normal;
  box-shadow:0 4px 12px -4px rgba(0,0,0,.35); display:none; z-index:6; text-transform:none; letter-spacing:0; }
.info:hover::after, .info:focus::after, .info:focus-visible::after { display:block; }
.info.left::after { left:auto; right:-4px; transform:none; }
abbr[title] { text-decoration:underline dotted #94a3b8; text-underline-offset:2px; cursor:help; }
/* partners */
.pgrp { margin:6px 0 2px; font-weight:650; color:#16324f; font-size:12px; }
.prow { font-size:12px; padding:2px 0 2px 8px; }
.rtag { display:inline-block; font-size:10px; padding:0 6px; border-radius:8px; background:#eef2f7; color:#4a5670; margin-left:4px; vertical-align:1px; }
.dtag { display:inline-block; font-size:10px; padding:0 6px; border-radius:8px; background:#f3e8ff; color:#6b21a8; margin-left:4px; vertical-align:1px; }
.warntag { display:inline-block; font-size:10.5px; padding:0 7px; border-radius:8px; background:#fde2e1; color:#b3261e; font-weight:600; margin-left:6px; }
.tdoc { font-size:12px; margin:4px 0; }
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
let state = { iso:null, hz:null, ver:null, pillar:'model' };
// ---------- map layers: what the map draws (the legend's toggles); the tiles follow
const LAYERS = { framework:true, adhoc:false, retired:false, tech:false };
// the pin takes the style of the first ENABLED layer of the pair (LAYER_ORDER: framework > retired > ad hoc > tech)
function visLayer(f){ return LAYER_ORDER.find(l => LAYERS[l] && f.layers.includes(l)) || null; }
function vis(c){ return c.fws.filter(f => visLayer(f)); }
function hidden(c){ return c.fws.filter(f => f.layers.length && !visLayer(f)); }   // a pair with no layer did not exist in the year shown
function setLayer(k, on){ LAYERS[k] = !!on; applyLayers(); }
// ---------- year selector: the map AS AT 31 DECEMBER of a year (the current year: today).
// null = all years, to today (the live record: current status, every activation). The
// current year keeps the live status and filters activations / ad hoc allocations to it;
// a past year is RECONSTRUCTED from the version dates and the status reports (f.hist).
let YEAR = null;
const LIVE = new Map();   // f -> its live (all-years) fields, which applyYear() overwrites
const LIVE_KEYS = ['disp','disp_label','layers','layer','n_act','n_act_all','n_adhoc','ring','current','pre_now','prearranged','covered'];
function snapLive(){ Object.values(L).forEach(c => c.fws.forEach(f => { const o = {}; LIVE_KEYS.forEach(k => o[k] = f[k]); LIVE.set(f, o); })); }
const pastY = () => YEAR != null && YEAR < YEARS.now;
const dateY = () => YEAR == null || YEAR >= YEARS.now ? YEARS.today : `${YEAR}-12-31`;
function lastAt(rows, D){ let x = null; for(const r of rows || []){ if(r[0] <= D) x = r; else break; } return x; }
// status of a framework as at D: the latest version dated on or before D decides (an endorsed one
// in validity -> active; expired, or a newer development version -> being updated; development
// only -> in development); no version by then -> the status report as at D; retired once the
// derived retirement date has passed. [status, version shown] — status null = did not exist yet.
function statusAt(f, D){
  const H = f.hist || {}, d10 = s => String(s || '').slice(0, 10);
  // a version exists from its start, or from the day it went into development when recorded;
  // one marked retired was never (or is no longer) a framework version
  const since = v => [v.valid_from, v.dev_since].filter(Boolean).map(d10).sort()[0];
  const dated = f.versions.filter(v => v.status !== 'retired' && since(v) && since(v) <= D);
  const last = dated[dated.length - 1], ver = last ? last.v : null;
  // the yearly view shows a framework as ACTIVE if it was ever active in the year: an endorsed
  // version in force at any time in it (validity that ended during the year still counts)
  const S = D.slice(0, 4) + '-01-01';
  if(H.retired && H.ret_on && H.ret_on <= S) return ['retired', ver];
  if(last){
    const endorsed = dated.filter(v => v.status === 'endorsed' && v.valid_from && d10(v.valid_from) <= D);
    if(endorsed.some(v => !v.valid_until || d10(v.valid_until) >= S)) return ['active', endorsed[endorsed.length - 1].v];
    return [endorsed.length ? 'updating' : 'development', ver];
  }
  const s = lastAt(H.sh, D), sc = s ? s[1] : null;
  if(!sc || sc === 'pipeline' || sc === 'retired') return [null, null];
  return [f.versions.length ? 'development' : sc, null];   // its first version came later: being built
}
function applyYear(){
  const Y = String(YEAR), D = dateY();
  Object.values(L).forEach(c => c.fws.forEach(f => {
    const B = LIVE.get(f); Object.assign(f, B); f.pre_drv = false;
    if(YEAR == null) return;
    const acts = f.activations.filter(a => String(a.date).slice(0, 4) === Y), H = f.hist || {};
    f.n_act = acts.filter(a => a.type === 'framework_aa').length; f.n_act_all = acts.length;
    f.n_adhoc = (H.adhoc || []).filter(y => String(y) === Y).length;
    let layers;
    if(!pastY()){ layers = B.layers.filter(l => l !== 'adhoc' || f.n_adhoc); }
    else {
      const [st, ver] = statusAt(f, D); layers = [];
      if(['active','updating','development'].includes(st)) layers.push('framework');
      if(st === 'retired') layers.push('retired');
      if(f.n_adhoc) layers.push('adhoc');
      if(f.tech && st) layers.push('tech');
      f.disp = st || (f.n_adhoc ? 'adhoc' : 'pipeline'); f.disp_label = KBLABEL[f.disp] || f.disp;
      f.ring = null; f.current = ver; f.prearranged = null;
      const p = (H.pre || {})[Y]; f.pre_now = p ? p[0] : null; f.pre_drv = !!(p && p[1]);
      const cv = lastAt(H.cov, D); f.covered = cv ? cv[1] : null;
    }
    f.layers = layers; f.layer = LAYER_ORDER.find(l => layers.includes(l)) || null;
  }));
}
function hashFor(parts){ const p = parts.filter(Boolean).join('/');
  return p ? p + (YEAR != null ? '|' + YEAR : '') : (YEAR != null ? String(YEAR) : ''); }
function syncYearUI(){
  document.querySelectorAll('#yearbar button').forEach(b => { const on = b.dataset.y === (YEAR == null ? '' : String(YEAR));
    b.classList.toggle('on', on); b.setAttribute('aria-pressed', on ? 'true' : 'false'); });
  const n = document.getElementById('yearnote'); if(n) n.hidden = !pastY();
}
function setYear(y){
  YEAR = (y === '' || y == null) ? null : +y; applyYear(); syncYearUI();
  if(state.iso){ state.ver = null; if(state.hz && !c_has(state.iso, state.hz)) state.hz = null; }
  applyLayers();
  const h = hashFor(state.iso ? [state.iso, state.hz, state.ver] : []);
  history.replaceState(null, '', location.pathname + (h ? '#' + h : ''));
}
function c_has(iso, hz){ const f = L[iso].fws.find(x => x.hazard === hz); return !!(f && f.layers.length); }
document.querySelectorAll('#yearbar button').forEach(b => b.addEventListener('click', () => setYear(b.dataset.y)));
// a status 'as at' a past year is derived: say so wherever it is shown
const DRV = (t) => `<span class='drv' title='${esc(t || 'Reconstructed from the framework records (version dates and status history)')}'>derived</span>`;
function statusNote(f){ if(!pastY()) return '';
  return f.disp === 'retired' ? ` · retired by the end of ${YEAR} (retirement date derived: ${(f.hist||{}).ret_note || 'no date recorded'})`
       : ` · status at the end of ${YEAR} (derived)`; }

function money(v){ return v==null ? '—' : v>=1e6 ? '$'+(v/1e6).toFixed(v>=1e7?0:1)+'M' : v>=1e3 ? '$'+Math.round(v/1e3)+'k' : '$'+Math.round(v); }
function num(v){ return v==null ? '—' : Math.round(v).toLocaleString(); }
function esc(s){ return s==null ? '' : String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
const SPLIT = `linear-gradient(135deg,${'#2171b5'} 0 50%,${'#9ecae1'} 50% 100%)`;   // 'being updated': half active, half development
function bgFor(st){ return st==='updating' ? SPLIT : (COLOR[st] || COLOR.development); }
// pin background for a pair given the layer it is drawn on
function pinStyle(f){ const l = visLayer(f) || f.layer;
  if(l==='framework') return {bg: bgFor(f.disp), cls: f.disp==='updating' ? 'upd' : ''};
  if(l==='tech') return {bg: '#fff', cls: 'tech'};
  return {bg: LAYER_COLOR[l], cls: l}; }
function badge(st, label){ st = st || 'development';
  const cls = st==='active' ? 'endorsed' : st==='updating' ? 'updating' : st==='retired' ? 'retired' : st==='adhoc' ? 'adhoc' : st==='pipeline' ? 'pipeline' : 'development';
  return `<span class='badge b-${cls}'>${esc(label || KBLABEL[st] || st.replace(/_/g,' '))}</span>`; }
function verBadge(st){ st=st||''; const m = {endorsed:'endorsed', superseded:'superseded', development:'development', 'pre-development':'pre-development', retired:'retired'};
  const lbl = {development:'in development', 'pre-development':'pre-development'}[st] || st || '?';
  return `<span class='badge b-${m[st]||'retired'}'>${esc(lbl)}</span>`; }
function hzColor(h){ return HAZ[h] || '#7a8699'; }
function iconHTML(f, extra=''){ const ps = pinStyle(f); return `<span class='iconbox ${f.ring==='now'?'able-now':''} ${ps.cls} ${extra}' style='background:${ps.bg}' data-hz='${f.hazard}'>`
  + `<svg viewBox='0 0 24 24' class='hz'>${GLYPH[f.glyph]||GLYPH.other}</svg>`
  + (f.n_act ? `<span class='actdots' title='${f.n_act} activation${f.n_act>1?'s':''}'>${'<span class="actdot"></span>'.repeat(Math.min(f.n_act,16))}</span>` : '') + `</span>`; }
// ---------- projections
// World: Equal Earth (UN GA A/80/L.104, Sep 2026), centred on EE.lam0, fitted to the view box.
// Country: local equirectangular fit (cos-lat corrected). Zooming MORPHS one into the other.
const EEA = {A1:1.340264, A2:-0.081106, A3:0.000893, A4:0.003796}, SQ3 = Math.sqrt(3), D2R = Math.PI/180;
const EEK = VB.w / (EEBOX[2]-EEBOX[0]);
function eeRaw(lon, lat){
  let lam = ((lon - EE.lam0 + 540) % 360 - 180) * D2R;
  const th = Math.asin(SQ3/2 * Math.sin(lat*D2R)), t2 = th*th, t6 = t2*t2*t2;
  const x = 2*SQ3*lam*Math.cos(th) / (3*(9*EEA.A4*t6*t2 + 7*EEA.A3*t6 + 3*EEA.A2*t2 + EEA.A1));
  const y = th*(EEA.A4*t6*t2*th + EEA.A3*t6*th + EEA.A2*t2*th + EEA.A1);
  return [x, -y];
}
function worldProj(lon, lat){ const [x,y] = eeRaw(lon, lat); return [(x-EEBOX[0])*EEK, (y-EEBOX[1])*EEK]; }
// the zoomed view is a SQUARE of the world view's height (the card keeps its height, the
// sidebar takes the freed width); the local projection fits the country into that square
function localProj(b){
  const S = VB.h, lat0 = (b[1]+b[3])/2, cosf = Math.max(.35, Math.cos(lat0*D2R));
  const bw = Math.max((b[2]-b[0])*cosf, .01), bh = Math.max(b[3]-b[1], .01);
  const s = Math.min(S/(bw*1.25), S/(bh*1.25), S/EE.smax), cx = (b[0]+b[2])/2;
  return (lon, lat) => [S/2 + (((lon-cx+540)%360)-180)*cosf*s, S/2 - (lat-lat0)*s];
}
function setViewW(w){ svg.setAttribute('viewBox', `0 0 ${w.toFixed(1)} ${VB.h}`); }
// the card's height is the world view's height for the current width; it never changes
// while zooming (the map goes square and the sidebar takes the rest)
const isMobile = () => window.matchMedia('(max-width: 760px)').matches;
function fixHeight(){
  const w = maprow.getBoundingClientRect().width;
  // phones: the map is full width — world view at the world aspect, zoomed view square
  if(isMobile()){ maprow.style.setProperty('--maph', Math.round(state.iso ? w : w * VB.h / VB.w) + 'px'); return; }
  if(state.iso) return;
  maprow.style.setProperty('--maph', Math.round(w * VB.h / VB.w) + 'px');
}
// phones: callouts are unusable at 350 px, so the panel lists the countries instead
function renderWorldList(){
  const rows = Object.entries(L).filter(([iso,c]) => vis(c).length).sort((a,b)=>a[1].name.localeCompare(b[1].name)).map(([iso,c]) =>
    `<div class='fcardx wl' style='--hz:${hzColor(vis(c)[0].hazard)}' onclick='selectCountry("${iso}")'>
      <div class='fhead'><b>${esc(c.name)}</b><span class='muted'>${nounCount(vis(c))}</span></div>
      <div class='wl-pins'>${vis(c).map(f=>`<span class='wl-pin'>${iconHTML(f)}<span class='hlab'>${esc(f.hz_label)}</span> ${badge(f.disp)}</span>`).join('')}</div>
    </div>`).join('');
  side.innerHTML = `<div class='muted' style='margin:2px 0 8px'>Tap a country to zoom in.</div><div class='fwlist'>${rows}</div>`;
}
let P = worldProj;                                    // projection the country layers use
function ringsD(rings, proj=P){ let d=''; for(const r of rings){ let first=true; for(const [x,y] of r){ const q=proj(x,y); d += (first?'M':'L') + q[0].toFixed(1) + ',' + q[1].toFixed(1); first=false; } d+='Z'; } return d; }
function kpx(){ return svg.getBoundingClientRect().width / VB.w; }
function toPx(lon, lat){ const [x,y]=worldProj(lon,lat), k=kpx(); return [x*k, y*k]; }

// ---------- world base: rings projected in the browser; precomputed for morphing
const WP = {};   // iso -> {el, w: Float64Array (world coords), n: ring lengths}
function buildWorld(){
  let html = '';
  for(const [iso, c] of Object.entries(WORLD)) html += `<path class='cty${c.on?' on':''}' data-iso='${iso}' data-name='${esc(c.n)}' d='${ringsD(c.r, worldProj)}'/>`;
  world.innerHTML = html;
  for(const [iso, c] of Object.entries(WORLD)){
    const n = c.r.reduce((s,r)=>s+r.length, 0), w = new Float64Array(n*2); let k = 0;
    for(const r of c.r) for(const [lon,lat] of r){ const q = worldProj(lon,lat); w[k++]=q[0]; w[k++]=q[1]; }
    WP[iso] = { el: world.querySelector(`.cty[data-iso='${iso}']`), w, lens: c.r.map(r=>r.length) };
  }
}
function pathFrom(coords, lens){ let d='', k=0; for(const n of lens){ for(let i=0;i<n;i++){ d += (i?'L':'M') + coords[k].toFixed(1) + ',' + coords[k+1].toFixed(1); k+=2; } d+='Z'; } return d; }
// morph the whole base between two projections (t: 0 = from, 1 = to), only for shapes that
// can be on screen in either state — everything else is parked off-canvas
function morphWorld(fromP, toP, t){
  for(const [iso, c] of Object.entries(WORLD)){
    const wp = WP[iso]; if(!wp) continue;
    if(!wp.to){ const n = wp.w.length, a = new Float64Array(n); let k=0; for(const r of c.r) for(const [lon,lat] of r){ const q = toP(lon,lat); a[k++]=q[0]; a[k++]=q[1]; } wp.to = a;
      let minx=1e9,maxx=-1e9,miny=1e9,maxy=-1e9; for(let i=0;i<n;i+=2){ if(a[i]<minx)minx=a[i]; if(a[i]>maxx)maxx=a[i]; if(a[i+1]<miny)miny=a[i+1]; if(a[i+1]>maxy)maxy=a[i+1]; }
      // shapes that end up far away, or blown up to many times the canvas (a continent-sized
      // neighbour at island zoom), would sweep across the view as bands: park them instead
      wp.vis = !(maxx < -VB.w || minx > 2*VB.w || maxy < -VB.h || miny > 2*VB.h)
            && (maxx-minx) < 2.5*VB.w && (maxy-miny) < 2.5*VB.h; }
    if(!wp.vis){ wp.el.style.display = 'none'; continue; }
    wp.el.style.display = '';
    const a = wp.w, b = wp.to, n = a.length, out = new Float64Array(n);
    for(let i=0;i<n;i++) out[i] = a[i] + (b[i]-a[i])*t;
    wp.el.setAttribute('d', pathFrom(out, wp.lens));
  }
}
function resetWorld(){ for(const wp of Object.values(WP)){ wp.el.style.display=''; wp.el.setAttribute('d', pathFrom(wp.w, wp.lens)); wp.to = null; } }

// ---------- zoom: a projection morph (world -> local), eased, hidden-tab safe
let animId = null, animSeq = 0, zoomTarget = null, inflight = null;
function finishInflight(){ if(!inflight) return; const a = inflight; inflight = null; if(animId){ cancelAnimationFrame(animId); animId = null; } a.step(1); a.done && a.done(); }
function animate(ms, step, done){
  finishInflight();                                   // a click mid-animation snaps the old one to its end first
  const seq = ++animSeq, t0 = performance.now(), ease = x => x<.5 ? 4*x*x*x : 1 - Math.pow(-2*x+2, 3)/2;
  inflight = {step, done};
  const end = () => { if(inflight && inflight.step === step){ inflight = null; animId = null; done && done(); } };
  if(document.hidden){ step(1); end(); return; }
  function frame(now){ if(seq !== animSeq) return; const k = Math.min(1, (now-t0)/ms); step(ease(k)); if(k<1) animId = requestAnimationFrame(frame); else end(); }
  animId = requestAnimationFrame(frame);
  setTimeout(()=>{ if(seq===animSeq && animId){ cancelAnimationFrame(animId); animId=null; step(1); end(); } }, ms+120);
}
// the map column and the view box shrink together from the SAME eased value: because the
// card height equals width x VB.h/VB.w, their ratio — the on-screen scale — stays constant
// for the whole animation, so nothing lurches while the sidebar opens
function colAt(t){
  if(isMobile()) return;
  const w0 = maprow._w0, h = parseFloat(getComputedStyle(maprow).getPropertyValue('--maph'));
  maprow.style.transition = 'none';
  maprow.style.gridTemplateColumns = `${(w0 + (h - w0)*t).toFixed(1)}px minmax(0,1fr)`;
  maprow.style.gap = `${(16*t).toFixed(1)}px`;
}
function colDone(){ maprow.style.transition = ''; maprow.style.gridTemplateColumns = ''; maprow.style.gap = ''; }
function zoomTo(bbox, done){
  const to = localProj(bbox); zoomTarget = bbox;
  for(const wp of Object.values(WP)) wp.to = null;
  P = to;
  if(!maprow.classList.contains('open') || !maprow._w0) maprow._w0 = maprow.getBoundingClientRect().width;
  svg.classList.add('zooming');
  animate(1050, t => { morphWorld(worldProj, to, t); world.style.opacity = 1 - 0.75*t; setViewW(VB.w + (VB.h - VB.w)*t); colAt(t); },
          () => { svg.classList.remove('zooming'); svg.classList.add('zoomed'); world.style.opacity = ''; setViewW(VB.h); colDone(); done && done(); });
}
function zoomOut(done){
  const from = P; if(from === worldProj){ done && done(); return; }
  svg.classList.remove('zoomed'); svg.classList.add('zooming');
  // reuse the stored target coords: morph back from local (t=1) to world (t=0)
  animate(850, t => { morphWorld(worldProj, from, 1 - t); world.style.opacity = 0.25 + 0.75*t; setViewW(VB.h + (VB.w - VB.h)*t); colAt(1 - t); },
          () => { resetWorld(); P = worldProj; zoomTarget = null; svg.classList.remove('zooming'); world.style.opacity = ''; setViewW(VB.w); colDone(); maprow.classList.remove('open'); done && done(); });
}

// ---------- admin layers (country view)
async function loadGeo(iso){
  if(GEO[iso] !== undefined) return GEO[iso];
  try { const r = await fetch(`adm-${iso}.json`); GEO[iso] = r.ok ? await r.json() : null; }
  catch(e){ GEO[iso] = null; }
  return GEO[iso];
}
// lighter shades of a hazard colour for the tiers of one framework (t: 0 = full, 1 = lightest)
function shade(hex, t){ const n = parseInt(hex.slice(1),16), r=n>>16, g=(n>>8)&255, b=n&255, k = 0.55*t;
  return '#' + [r,g,b].map(v => Math.round(v + (255-v)*k).toString(16).padStart(2,'0')).join(''); }
// diagonal stripes alternating the colours of the tiers that share an area
function hatchId(cols){
  const id = 'hatch-' + cols.map(c=>c.slice(1)).join('-'); const hzs = cols;
  let defs = svg.querySelector('defs'); if(!defs){ defs = document.createElementNS(NS,'defs'); svg.insertBefore(defs, svg.firstChild); }
  if(!defs.querySelector('#'+id)){
    const n = hzs.length, w = 4.5;
    const pat = document.createElementNS(NS,'pattern');
    pat.setAttribute('id', id); pat.setAttribute('patternUnits','userSpaceOnUse'); pat.setAttribute('width', w*n); pat.setAttribute('height', w*n);
    pat.setAttribute('patternTransform','rotate(45)');
    hzs.forEach((h,i)=>{ const r = document.createElementNS(NS,'rect'); r.setAttribute('x', i*w); r.setAttribute('y', 0); r.setAttribute('width', w); r.setAttribute('height', w*n); r.setAttribute('fill', h); pat.appendChild(r); });
    defs.appendChild(pat);
  }
  return id;
}
function drawAdmin(iso, fade){
  const g = GEO[iso]; adm.innerHTML=''; if(fade) adm.classList.remove('show');
  if(!g) return;
  const c = L[iso];
  let html = '';
  (g.nb||[]).forEach(n => html += `<path class='nb' data-n='${esc(L[n.iso]?.name || WORLD[n.iso]?.n || n.iso)}' d='${ringsD(n.r)}'/>`);
  if(g.adm0.length) html += `<path class='a0' d='${ringsD(g.adm0)}'/>`;
  g.adm1.forEach(a => html += `<path class='a1' data-n='${esc(a.n)}' d='${ringsD(a.r)}'/>`);

  // one entry per framework tier: {hz, label, color, pcodes, rest}
  const targets = state.hz ? c.fws.filter(f=>f.hazard===state.hz) : vis(c);
  const tiers = [];
  targets.forEach(f => {
    const v = f.versions.find(x => x.v === (state.hz && state.ver ? state.ver : f.current));
    if(!v || !v.scope) return;
    const ts = (v.scope.tiers && v.scope.tiers.length) ? v.scope.tiers
             : [{label:null, pcodes:v.scope.pcodes, rest:!!v.scope.national}];
    ts.forEach((t, i) => tiers.push({hz:f.hazard, hzl:f.hz_label, label:t.label, pcodes:t.pcodes||[], rest:!!t.rest,
      color: shade(hzColor(f.hazard), ts.length > 1 ? i/(ts.length-1) : 0)}));
  });
  // country-wide tiers (national trigger, 'all other provinces', unmapped zone): a wash under everything
  const rests = tiers.filter(t => t.rest);
  rests.forEach(t => { if(g.adm0.length) html += `<path class='nat' fill='${t.color}' d='${ringsD(g.adm0)}'/>`; });
  // areas: collect every tier covering each admin area; a national tier covers them all
  const paint = {};
  tiers.filter(t => !t.rest).forEach(t => t.pcodes.forEach(p => (paint[p] ??= []).push(t)));
  let multi = false;
  Object.entries(paint).forEach(([p, ts]) => {
    const a = g.areas[p]; if(!a) return;
    const cover = [...ts, ...rests.filter(r => !ts.some(t => t.hz === r.hz))];   // other hazards' national tiers
    const fill = cover.length > 1 ? `url(#${hatchId(cover.map(t=>t.color))})` : cover[0].color;
    if(cover.length > 1) multi = true;
    html += `<path class='sc' fill='${fill}' data-n='${esc(a.n)}' data-hz='${esc(cover.map(t=>t.hzl + (t.label?` (${t.label})`:'')).join(' + '))}' d='${ringsD(a.r)}'/>`;
  });
  adm.innerHTML = html;
  if(fade) void adm.getBoundingClientRect();
  adm.classList.add('show');
  legend.innerHTML = `<b>${esc(c.name)}</b><br>` + tiers.map(t =>
      `<span class='sq' style='background:${t.color}'></span>${esc(t.hzl)}${t.label?` — ${esc(t.label)}`:''}${t.rest?' (whole country)':''}<br>`).join('');
}

// ---------- world legend (KB style)
function worldLegend(){
  const all = Object.values(L).flatMap(c=>c.fws), shown = all.filter(f=>visLayer(f));
  const onLayer = k => all.filter(f=>f.layers.includes(k));
  const n = k => onLayer('framework').filter(f=>f.disp===k).length;
  const nAct = shown.reduce((s,f)=>s+f.n_act_all,0), nNow = shown.filter(f=>f.ring==='now').length;
  const swatch = { framework: `<span class='dot' style='background:${COLOR.active}'></span>`, adhoc: `<span class='dot' style='background:${LAYER_COLOR.adhoc}'></span>`,
                   retired: `<span class='dot' style='background:${LAYER_COLOR.retired}'></span>`, tech: `<span class='dot dot-hollow'></span>` };
  const lab = k => k === 'framework' && pastY() ? `Frameworks at the end of ${YEAR}` : k === 'adhoc' && YEAR != null ? `Ad hoc allocations in ${YEAR}` : LAYER_LABEL[k];
  const row = k => `<label><input type='checkbox' ${LAYERS[k]?'checked':''} onchange='setLayer("${k}", this.checked)'>${swatch[k]}${lab(k)} <span class='cnt'>${onLayer(k).length}</span></label>`;
  const st = `<div class='lsub${LAYERS.framework?'':' off'}'>`
    + `<span><span class='dot' style='background:${COLOR.active}'></span>Active <span class='cnt'>${n('active')}</span></span>`
    + `<span><span class='dot' style='background:${SPLIT}'></span>Being updated <span class='cnt'>${n('updating')}</span></span>`
    + `<span><span class='dot' style='background:${COLOR.development}'></span>In development <span class='cnt'>${n('development')}</span></span></div>`;
  legend.innerHTML = `<div class='layerctl' role='group' aria-label='Map layers'>` + row('framework') + st + row('adhoc') + row('retired') + row('tech') + `</div>`
    + `<div class='lsub'><span><span class='dot' style='background:#e3322d'></span>Activations${YEAR != null ? ` in ${YEAR}` : ''} <span class='cnt'>${nAct}</span></span>`
    + (pastY() ? '' : `<span><span class='dot' style='background:#fff;border:2.5px solid #f5a300;box-sizing:border-box'></span>In monitoring season <span class='cnt'>${nNow}</span></span>`) + `</div>`;
}
// what a list of map entries is called: frameworks, unless some are ad hoc allocations or technical support
function nounCount(fs){
  const k = {framework:0, retired:0, adhoc:0, tech:0};
  fs.forEach(f => { k[visLayer(f) || f.layer] = (k[visLayer(f) || f.layer] || 0) + 1; });
  const out = [];
  if(k.framework) out.push(`${k.framework} framework${k.framework>1?'s':''}`);
  if(k.retired) out.push(`${k.retired} retired framework${k.retired>1?'s':''}`);
  if(k.adhoc) out.push(`${k.adhoc} with ad hoc allocations`);
  if(k.tech) out.push(`${k.tech} with technical support`);
  return out.join(' · ') || 'nothing shown';
}
// re-draw everything that depends on the layer set: pins, callouts, legend, tiles, sidebar
function syncOn(){ for(const [iso, c] of Object.entries(L)){ const el = WP[iso] && WP[iso].el; if(el) el.classList.toggle('on', vis(c).length > 0); } }
function applyLayers(){
  syncOn(); worldLegend(); updateTiles();
  if(state.iso){ renderSide(); if(GEO[state.iso]) drawAdmin(state.iso, false); }
  else { buildCallouts(); runLayout(); if(isMobile()) renderWorldList(); }
}
// headline tiles: recomputed from the pairs the map currently shows (see tile_figures in Python)
function updateTiles(){
  const shown = Object.values(L).flatMap(c=>c.fws).filter(f=>visLayer(f));
  const fw = shown.filter(f=>LAYERS.framework && f.layers.includes('framework'));
  const n = k => fw.filter(f=>f.disp===k).length;
  // the label is text; `drv` appends the 'derived' marker (past years: reconstructed figures)
  const set = (id, v, l, drv) => { const el = document.getElementById(id); if(!el) return; el.querySelector('.v').textContent = v;
    el.querySelector('.l').innerHTML = esc(l) + (drv ? DRV(drv === true ? null : drv) : ''); };
  const past = pastY(), at = past ? ` at the end of ${YEAR}` : YEAR != null ? ' today' : '';
  set('t-fw', fw.length, `frameworks on the map${at} · ${n('active')} active · ${n('updating')} being updated · ${n('development')} in development`,
      past && 'Which frameworks existed at 31 December, and their status, are reconstructed from the version dates and status history; a framework whose validity ended during the year still counts as active for that year');
  const noEnv = []; Object.values(L).forEach(c => c.fws.forEach(f => { if(fw.includes(f) && !f.pre_now) noEnv.push(`${c.name} ${f.hz_label.toLowerCase()}`); }));
  let pre = fw.reduce((s,f)=>s+(f.pre_now||0),0), preX = 0;
  if(past){   // pooled-fund rows of no single framework count with the country's frameworks shown
    Object.entries(L).forEach(([iso, c]) => { const x = (c.pre_x || {})[String(YEAR)]; if(x && c.fws.some(f => fw.includes(f))) preX += x[0]; }); pre += preX; }
  const ser = (YEARS.series || {})[String(YEAR)];
  set('t-pre', '$' + Math.round(pre/1e6) + 'M', past
      ? `pre-arranged in ${YEAR}, frameworks shown`
        + (noEnv.length ? ` · ${noEnv.length} with no figure for ${YEAR}` : '')
      : 'pre-arranged now (CERF and country and regional funds), all current frameworks incl. in development'
        + (noEnv.length ? ` · ${noEnv.length} without an envelope recorded yet: ${noEnv.join(', ')}` : ''),
      past && fw.some(f => f.pre_drv) && 'Part of this year\'s figure is inferred from the envelope of the version valid during the year (no reported figure for that framework-year)');
  const tp = document.getElementById('t-pre'); if(tp) tp.title = !past ? '' : [
    `A stock for ${YEAR}: each framework valid at any time in the year, counted once; never summed over years.`,
    preX ? `Includes ${money(preX)} of pooled-fund allocations not tied to one hazard.` : '',
    ser != null && Math.abs(ser - pre) >= 5e5 ? `The funding page's ${YEAR} figure (${money(ser)}) also counts AA-tagged pooled-fund allocations in countries without a framework shown here.` : '',
    noEnv.length ? `No figure for ${YEAR}: ${noEnv.join(', ')}.` : ''].filter(Boolean).join(' ');
  set('t-act', shown.reduce((s,f)=>s+f.n_act_all,0), YEAR != null ? `activations in ${YEAR}` : 'activations');
  const cov = fw.reduce((s,f)=>s+(f.covered||0),0);
  set('t-cov', past && !cov ? '—' : (cov/1e6).toFixed(1) + 'M', past
      ? (cov ? `people covered at the end of ${YEAR}, frameworks shown (latest figure reported by then)` : `people covered: no figure recorded by the end of ${YEAR}`)
      : 'people covered, frameworks shown');
  const g = document.getElementById('gtiles'); if(g) g.classList.toggle('global', !!state.iso);
  const cap = document.getElementById('gcap'); if(cap) cap.textContent = (state.iso ? `Global portfolio — not ${L[state.iso].name}: its own figures are in the panel` : 'Global portfolio — all layers currently shown on the map')
    + (past ? ` · as at 31 December ${YEAR}` : YEAR != null ? ` · ${YEAR}, as of today` : '');
}

// ---------- callouts: one per country, laid out clear of every framework country (ported from the KB map)
const NS = 'http://www.w3.org/2000/svg';
let labels = [];
// one callout per country with something on the enabled layers; rebuilt on every layer change
function buildCallouts(){
  lpane.querySelectorAll('.callout').forEach(el => el.remove()); leaders.innerHTML = ''; labels = [];
  Object.entries(L).forEach(([iso, c]) => {
    const fws = vis(c);
    if(!c.centroid || !fws.length) return;
    const el = document.createElement('div'); el.className = 'callout';
    el.innerHTML = `<span class='cname' data-iso='${iso}'>${esc(c.name)}</span>` +
      fws.map(f => { const extra = Math.ceil(Math.min(f.n_act||0,16)/4) - 1;   // stacked activation-dot rows need head room
        return `<span class='hrow'${extra>0?` style='margin-top:${extra*11}px'`:''}>${iconHTML(f)}<span class='hlab'>${esc(f.hz_label)}</span></span>`; }).join('');
    el.querySelector('.cname').onclick = e => { e.stopPropagation(); selectCountry(iso); };
    el.querySelectorAll('.iconbox').forEach(ib => { ib.onclick = e => { e.stopPropagation(); selectCountry(iso, ib.dataset.hz); };
      ib.onmouseenter = ev => { const f = c.fws.find(x=>x.hazard===ib.dataset.hz); const nA = f.n_act_all; showTip(ev, `${c.name} — ${f.hz_label}: ${f.disp_label}${statusNote(f)}${f.tech?' · technical support':''}${nA?` · ${nA} activation${nA>1?'s':''}${YEAR!=null?` in ${YEAR}`:''}`:''}`); };
      ib.onmouseleave = () => tip.hidden = true; });
    lpane.appendChild(el);
    const ln = document.createElementNS(NS, 'line'); ln.setAttribute('class','leader'); leaders.appendChild(ln);
    const dot = document.createElementNS(NS, 'circle'); dot.setAttribute('class','cdot'); dot.setAttribute('r','3.5'); leaders.appendChild(dot);
    labels.push({iso, lat:c.centroid[0], lon:c.centroid[1], dir:c.dir, el, ln, dot, bbox:c.lbbox});
  });
}
let PAD = 8, GAP = 4; let ALLRECTS = [];
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
// leader-line tidy-up: a leader should not cross another leader nor run through another
// label. Swap the positions of two labels whenever that lowers the total count, then let
// the overlap pass settle; stop when a full sweep changes nothing.
function anchorOf(Lb){ return [Lb.cx-Lb.w/2+Lb.iox, Lb.cy-Lb.h/2+Lb.ioy]; }
function segCross(p1, p2, p3, p4){
  const d = (a,b,c) => (c[0]-a[0])*(b[1]-a[1]) - (b[0]-a[0])*(c[1]-a[1]);
  const d1 = d(p3,p4,p1), d2 = d(p3,p4,p2), d3 = d(p1,p2,p3), d4 = d(p1,p2,p4);
  return ((d1>0&&d2<0)||(d1<0&&d2>0)) && ((d3>0&&d4<0)||(d3<0&&d4>0)); }
function segHitsBox(p, q, Lb){
  const x1 = Lb.cx-Lb.w/2, y1 = Lb.cy-Lb.h/2, x2 = x1+Lb.w, y2 = y1+Lb.h;
  if(Math.max(p[0],q[0]) < x1 || Math.min(p[0],q[0]) > x2 || Math.max(p[1],q[1]) < y1 || Math.min(p[1],q[1]) > y2) return false;
  const c = [[x1,y1],[x2,y1],[x2,y2],[x1,y2]];
  for(let i=0;i<4;i++) if(segCross(p, q, c[i], c[(i+1)%4])) return true;
  return false; }
function badness(){
  let n = 0; const A = labels.map(anchorOf);
  for(let i=0;i<labels.length;i++){ const pi = [labels[i].px, labels[i].py];
    for(let j=0;j<labels.length;j++){ if(i===j) continue;
      if(j>i && segCross(pi, A[i], [labels[j].px, labels[j].py], A[j])) n += 2;
      if(segHitsBox(pi, A[i], labels[j])) n += 1; } }
  return n; }
function overlaps(){ let n = 0;
  for(let i=0;i<labels.length;i++) for(let j=i+1;j<labels.length;j++){ const a = labels[i], b = labels[j];
    if(Math.abs(a.cx-b.cx)*2 < a.w+b.w+PAD && Math.abs(a.cy-b.cy)*2 < a.h+b.h+PAD) n++; }
  return n; }
function layoutScore(){ return badness() + 10*overlaps(); }
function uncross(W, H){
  for(let pass=0; pass<6; pass++){
    let changed = false;
    // candidate pairs: leaders that cross, or a leader running through the other label
    const A = labels.map(anchorOf), cands = [];
    for(let i=0;i<labels.length;i++) for(let j=i+1;j<labels.length;j++){
      const a = labels[i], b = labels[j], pa = [a.px,a.py], pb = [b.px,b.py];
      if(segCross(pa, A[i], pb, A[j]) || segHitsBox(pa, A[i], b) || segHitsBox(pb, A[j], a)) cands.push([a, b]); }
    for(const [a, b] of cands){
      const snap = labels.map(l => [l.cx, l.cy]), cur = layoutScore();
      const sa = [a.cx, a.cy]; a.cx = b.cx; a.cy = b.cy; b.cx = sa[0]; b.cy = sa[1];
      separate(300, W, H);
      if(layoutScore() < cur) changed = true;
      else labels.forEach((l, k) => { l.cx = snap[k][0]; l.cy = snap[k][1]; });   // keep only improvements
    }
    if(!changed) break;
  }
}
function runLayout(){
  const r = svg.getBoundingClientRect(), W = r.width, H = r.height;
  if(!W) return;
  const mobile = window.matchMedia('(max-width: 760px)').matches;
  mapbox.classList.toggle('compact', mobile); PAD = mobile ? 3 : 8; GAP = mobile ? 2 : 4;
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
  uncross(W, H);
  labels.forEach(Lb => {
    Lb.el.style.visibility = 'visible'; Lb.el.style.left = (Lb.cx-Lb.w/2)+'px'; Lb.el.style.top = (Lb.cy-Lb.h/2)+'px';
    Lb.ln.setAttribute('x1', Lb.px); Lb.ln.setAttribute('y1', Lb.py);
    Lb.ln.setAttribute('x2', Lb.cx-Lb.w/2+Lb.iox); Lb.ln.setAttribute('y2', Lb.cy-Lb.h/2+Lb.ioy);
    Lb.dot.setAttribute('cx', Lb.px); Lb.dot.setAttribute('cy', Lb.py);
  });
}
// relayout whenever the map's rendered size changes (window resize, sidebar sliding in or
// out) — callouts are positioned in CSS px, so a stale width puts them off the countries
let rto = null;
let lastLayoutW = 0;
function scheduleLayout(){ clearTimeout(rto); rto = setTimeout(() => { if(!state.iso){ fixHeight(); runLayout(); lpane.classList.remove('hide'); if(isMobile()){ maprow.classList.add('open'); if(!side.querySelector('.wl')) renderWorldList(); }
  lastLayoutW = svg.getBoundingClientRect().width;
  // a resize can land while this tab is throttled: re-check once the dust settles
  setTimeout(() => { if(!state.iso && Math.abs(svg.getBoundingClientRect().width - lastLayoutW) > 1) scheduleLayout(); }, 600); } }, 120); }
new ResizeObserver(() => scheduleLayout()).observe(svg);
window.addEventListener('resize', scheduleLayout);

// ---------- tooltips
function showTip(ev, txt){ const box = mapbox.getBoundingClientRect(); tip.textContent = txt; tip.hidden = false;
  tip.style.left = (ev.clientX-box.left)+'px'; tip.style.top = (ev.clientY-box.top)+'px'; }
svg.addEventListener('mousemove', ev => {
  const t = ev.target; let txt = null;
  if(t.classList.contains('cty') && !state.iso){ const c = L[t.dataset.iso], nv = c ? vis(c).length : 0; txt = nv ? `${c.name} · ${nounCount(vis(c))}` : t.dataset.name; }
  else if(t.classList.contains('sc')) txt = `${t.dataset.n} · ${t.dataset.hz}`;
  else if(t.classList.contains('a1') || t.classList.contains('nb')) txt = t.dataset.n;
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
document.addEventListener('keydown', e => { if(e.key === 'Escape' && state.iso) goWorld(); });

function goWorld(){
  state = { iso:null, hz:null, ver:null, pillar: state.pillar };
  document.querySelectorAll('.cty.sel').forEach(x=>x.classList.remove('sel'));
  adm.classList.remove('show'); back.hidden = true; worldLegend(); updateTiles();
  if(isMobile()){ renderWorldList(); fixHeight(); } else { side.innerHTML = `<div class='muted' style='padding:20px 6px'>Select a country or a pin on the map.</div>`; side.style.opacity = '0'; setTimeout(()=>{ side.style.opacity=''; }, 900); }
  setTimeout(()=>{ adm.innerHTML=''; }, 300);
  zoomOut(() => scheduleLayout());
  history.replaceState(null, '', location.pathname + (YEAR != null ? '#' + YEAR : ''));
}
async function selectCountry(iso, hz, ver){
  const c = L[iso]; if(!c) return;
  const changed = state.iso !== iso;
  // a deep link to a pair whose layer is off: switch that layer on so the map and the panel agree
  const want = hz ? c.fws.find(f=>f.hazard===hz) : null;
  if(want && want.layer && !visLayer(want)){ LAYERS[want.layer] = true; syncOn(); }
  const fws = vis(c);
  state = { iso, hz: hz || (fws.length===1 ? fws[0].hazard : null), ver: ver || null, pillar: state.pillar };
  document.querySelectorAll('.cty.sel').forEach(x=>x.classList.remove('sel'));
  svg.querySelectorAll(`.cty[data-iso='${iso}']`).forEach(el => el.classList.add('sel'));
  back.hidden = false; lpane.classList.add('hide'); tip.hidden = true; maprow.classList.add('open');
  renderSide(); updateTiles(); if(want && !changed) worldLegend();
  if(isMobile()){ fixHeight(); setTimeout(() => window.scrollTo({top: side.getBoundingClientRect().top + window.scrollY - 8, behavior:'smooth'}), 1150); }
  location.hash = hashFor([iso, state.hz, state.ver]);
  if(changed){
    adm.classList.remove('show'); adm.innerHTML='';
    const geoP = loadGeo(iso);
    let zoomed = false, geoDone = false;
    const finish = () => { if(zoomed && geoDone && state.iso === iso) drawAdmin(iso, true); };
    if(c.bbox) zoomTo(c.bbox, () => { zoomed = true; finish(); }); else { zoomed = true; }
    await geoP; geoDone = true; finish();
  } else {
    await loadGeo(iso);
    if(state.iso === iso) drawAdmin(iso, false);
  }
}
function selectFramework(hz){ selectCountry(state.iso, hz, null); }
function selectVersion(v){ state.ver = v; renderSide(); drawAdmin(state.iso, false); location.hash = hashFor([state.iso, state.hz, v]); }

// ---------- sidebar
function monthStrip(months){ months = months||[]; return [...MONL].map((m,i)=>`<span class='mm ${months.includes(i+1)?'on':''}'>${m}</span>`).join(''); }
// the country's OWN figures, at the top of the panel — never to be confused with the global tiles
function countryTiles(c){
  const fws = vis(c), fw = fws.filter(f=>visLayer(f)==='framework');
  const pre = fw.reduce((s,f)=>s+(f.pre_now||0),0), cov = fw.reduce((s,f)=>s+(f.covered||0),0), nA = fws.reduce((s,f)=>s+f.n_act_all,0);
  return `<div class='ctiles'><div class='ccap'>${esc(c.name)} only</div>
    <div class='ctile'><div class='v'>${fw.length}</div><div class='l'>framework${fw.length===1?'':'s'}${fws.length>fw.length?` · ${fws.length-fw.length} other`:''}</div></div>
    <div class='ctile'><div class='v'>${pre?money(pre):'—'}</div><div class='l'>pre-arranged ${pastY()?`in ${YEAR}`:'now'}</div></div>
    <div class='ctile'><div class='v'>${nA}</div><div class='l'>activation${nA===1?'':'s'}${YEAR!=null?` in ${YEAR}`:''}</div></div>
    <div class='ctile'><div class='v'>${cov?num(cov):'—'}</div><div class='l'>people covered</div></div></div>`;
}
function hiddenNote(c){
  const h = hidden(c); if(!h.length) return '';
  return `<div class='small' style='margin:6px 0;color:#64748b'>Not drawn by the current layers: ` + h.map(f => `${esc(f.hz_label)} (<a style='cursor:pointer' onclick='setLayer("${f.layer}", true)'>${LAYER_LABEL[f.layer].toLowerCase()}</a>)`).join(', ') + `</div>`;
}
function renderSide(){
  const c = L[state.iso];
  const crumb = `<div class='crumb'><a onclick='goWorld()'>World</a> › ` +
    (state.hz ? `<a onclick='selectCountry("${state.iso}", null)'>${esc(c.name)}</a> › ${esc(c.fws.find(f=>f.hazard===state.hz)?.hz_label||state.hz)}` : `<b>${esc(c.name)}</b>`) + `</div>`;
  if(!state.hz){
    const fws = vis(c);
    side.innerHTML = crumb + `<h3>${esc(c.name)}</h3><div class='muted'>${esc(c.region||'')} · ${nounCount(fws)} — select one</div>` + countryTiles(c) + hiddenNote(c) +
      `<div class='fwlist'>` + fws.map(f => {
        const v = f.versions.find(x=>x.v===f.current);
        return `<div class='fcardx' style='--hz:${hzColor(f.hazard)}' onclick='selectFramework("${f.hazard}")'>
          <div class='fhead'><b>${iconHTML(f)}${esc(f.hz_label)}</b>${badge(f.disp)}${pastY()?DRV(statusNote(f).slice(3)):''}${f.tech?` <span class='badge b-tech'>technical support</span>`:''}</div>
          <table class='mini'>
           <tr><td class='lbl'>${pastY()?`Version, end of ${YEAR}`:'Latest version'}</td><td>${f.current ? `<code>${f.current}</code> <span class='muted'>(${f.versions.length} total)</span>` : '<span class="muted">no framework version</span>'}</td></tr>
           <tr><td class='lbl'>Pre-arranged</td><td>${money(f.pre_now ?? f.prearranged)}${f.pre_now==null && f.prearranged_year?` <span class='muted'>(${f.prearranged_year})</span>`:''}</td></tr>
           <tr><td class='lbl'>People covered</td><td>${num(f.covered)}</td></tr>
           <tr><td class='lbl'>Activations${YEAR!=null?` ${YEAR}`:''}</td><td>${f.n_act_all||'—'}${f.n_adhoc?` <span class='muted'>(${f.n_adhoc} ad hoc)</span>`:''}</td></tr>
           <tr><td class='lbl'>Monitoring</td><td>${monthStrip(v ? v.months : [])}</td></tr>
          </table></div>`; }).join('') + `</div>`;
    annotate(side, side);
    return;
  }
  const f = c.fws.find(x=>x.hazard===state.hz); if(!f){ state.hz=null; return renderSide(); }
  if(!f.versions.length){
    const why = f.layer==='adhoc' ? `Ad hoc anticipatory-action allocations for this hazard — no framework behind them.`
              : f.layer==='tech' ? `OCHA technical support — no framework version in the registry yet${f.status?` (tracking sheets: ${esc(f.status.replace(/_/g,' '))})`:''}.`
              : `No framework version in the registry yet — status comes from the tracking sheets (${esc((f.status||'').replace(/_/g,' '))}).`;
    side.innerHTML = crumb + fwHeader(c, f) + countryTiles(c) + `<p class='muted'>${why}</p>` + adhocBlock(f) +
      learningBlock(f, null) + partnersBlock(c, f, null) + (f.page ? `<p><a href='${f.page}'>framework page →</a></p>` : '');
    annotate(side, side);
    return;
  }
  const ver = state.ver || f.current; state.ver = ver;
  const v = f.versions.find(x=>x.v===ver) || f.versions[f.versions.length-1];
  const isCur = v.v === f.current;
  side.innerHTML = crumb + fwHeader(c, f) + countryTiles(c) + versionBar(f, v, isCur) +
    (isCur ? '' : f.current ? `<div class='warnbox'>Viewing ${pastY()?'another':'an older'} version (${esc(v.superseded?'superseded':(v.status||'past'))}). The map shows this version's scope. ${pastY()?`In force or most recent at the end of ${YEAR}`:'Most recent'}: <a onclick='selectVersion("${f.current}")' style='cursor:pointer'>${f.current}</a>.</div>`
       : `<div class='warnbox'>No dated version by the end of ${YEAR}${f.layers.length?' (in development by the status reports)':''}; showing the latest version.</div>`) +
    factsBlock(f, v) + pillarsBar(f, v) + `<div id='pillarbody'>${pillarBody(f, v)}</div>` +
    `<p class='small' style='margin-top:12px'>${f.page?`<a href='${f.page}'>full framework page →</a> · `:''}<a href='hierarchy.html'>explorer</a></p>`;
  annotate(side, side);
}
// ---------- the building blocks of AA: model · plan · funding · learning (always shown)
const PILLARS = ['model', 'plan', 'funding', 'learning'];
function pillarsBar(f, v){
  const F = v.funding, funds = [...new Set(F.fund.map(x=>x.fund))].filter(x=>x!=='unspecified');
  const nTrig = v.triggers.length || v.windows.length || v.n_windows || 0;
  const nDocs = (f.learning_docs||[]).length + (v.learning||[]).length;
  const Pv = (v.partners||[]).length ? v.partners : (([...f.versions].reverse().find(x => (x.partners||[]).length) || {}).partners || []);
  const nPart = new Set(Pv.map(p => (p.name||'').toLowerCase())).size;
  const nUN = new Set(F.agency.map(x => x.agency)).size || v.agencies.length;
  const boxes = [
    ['model', 'Model', nTrig ? `${nTrig} trigger window${nTrig>1?'s':''}` : (v.basis ? esc(v.basis) : '—'), [v.basis, v.months.length ? `${v.months.length} months monitored` : null, f.activations.length ? `${f.activations.length} activation${f.activations.length>1?'s':''}` : 'never activated'].filter(Boolean).join(' · ')],
    ['plan', 'Plan', nUN ? `${nUN} UN agenc${nUN>1?'ies':'y'} funded` : '—', [v.target_people ? `${num(v.target_people)} people targeted` : (f.covered ? `${num(f.covered)} people covered` : null), nPart ? `${nPart} partner${nPart>1?'s':''} in total` : null].filter(Boolean).join('<br>')],
    ['funding', 'Funding', money(v.prearranged_doc ?? v.envelope), (v.prearranged_doc ?? v.envelope) ? `pre-arranged${funds.length?' · '+funds.map(x=>x.toUpperCase().replace('CBPF-','CBPF ')).join(', '):''}` : (f.tech ? 'technical support only' : 'no figure yet')],
    ['learning', 'Learning', nDocs ? `${nDocs} document${nDocs>1?'s':''}` : 'no documents yet', 'evaluations, reviews, reports'],
  ];
  if(!PILLARS.includes(state.pillar)) state.pillar = 'model';
  return `<div class='pillars four'>` + boxes.map(([k, name, val, sub]) =>
    `<div class='pillar ${state.pillar===k?'on':''}' onclick='selectPillar("${k}")'><div class='pk'>${name}</div><div class='pv'>${val}</div><div class='ps'>${sub||''}</div></div>`).join('') + `</div>`;
}
function selectPillar(k){ state.pillar = k; const c = L[state.iso], f = c.fws.find(x=>x.hazard===state.hz); const v = f.versions.find(x=>x.v===state.ver) || f.versions[f.versions.length-1];
  document.querySelectorAll('.pillar').forEach(el=>el.classList.toggle('on', el.getAttribute('onclick').includes(`"${k}"`)));
  const pb = document.getElementById('pillarbody'); pb.innerHTML = pillarBody(f, v); annotate(pb, side); }
function pillarBody(f, v){
  const rows = [];
  const c = L[state.iso];
  if(state.pillar==='funding'){
    rows.push(['Pre-arranged', `${money(v.prearranged_doc ?? v.envelope)}${v.regional?` <span class='muted'>· regional document total (all countries)</span>`:''}${v.all_in===false?` <span class='muted'>· split budget per window</span>`:v.all_in===true?` <span class='muted'>· all-in</span>`:''}`]);
    if(v.envelope!=null && v.prearranged_doc!=null && Math.abs(v.envelope - v.prearranged_doc) > 0.01*Math.max(v.envelope, v.prearranged_doc)) rows.push(['Envelope (registry)', `${money(v.envelope)} <span class='muted'>from the version's window funding; the document says ${money(v.prearranged_doc)}</span>`]);
    if(v.cofin) rows.push(['Co-financing', `${money(v.cofin)}${v.cofin_sources.length?` <span class='muted'>${esc(v.cofin_sources.join(', '))}</span>`:''}`]);
    if(f.tech) rows.push(['OCHA role', `<span class='badge b-tech'>technical support</span> <span class='muted'>no funding commitment</span>`]);
    return miniTable(rows) + fundingBlock(v);
  }
  if(state.pillar==='model'){
    rows.push(['Monitored', `${monthStrip(v.months)}${v.months_src?` <span class='muted'>${esc(v.months_src)}</span>`:''}${v.months_note?`<div class='small' style='margin-top:3px'>${esc(v.months_note)}</div>`:''}`]);
    if(v.basis||v.indicators.length) rows.push(['Trigger basis', `${esc(v.basis||'')}${v.calibration?` · ${esc(v.calibration)}`:''}${v.indicators.length?`<div class='chips'>${v.indicators.map(i=>`<span>${esc(i)}</span>`).join('')}</div>`:''}`]);
    if(v.data_sources.length) rows.push(['Data sources', esc(v.data_sources.map(d=>typeof d==='string'?d:(d.name||d.source||JSON.stringify(d))).join(', '))]);
    // trigger design, then (at the bottom of the trigger section) the historical activations
    // simulation with the real ones marked in, the table of real activations, scope, docs
    return miniTable(rows) + triggersBlock(v) + actualBlock(f, v) + backtestBlock(f, v) + scopeBlock(v) + techDocsBlock(v);
  }
  if(state.pillar==='plan'){
    if(v.agencies.length) rows.push(['Agencies', esc(v.agencies.join(', '))]);
    if(v.target_people) rows.push(['People targeted', num(v.target_people)]);
    if(f.covered && f.current===v.v) rows.push(['People covered', `${num(f.covered)} <span class='muted'>(tracking sheet)</span>`]);
    return miniTable(rows) + partnersBlock(c, f, v) + sectorBlock(v);
  }
  return learningBlock(f, v);
}
// Learning: curated documents (aa.learning_document, country scope, hazard-matched or
// hazard-less, public only) + the version page's learning links; then the activations
const DOCTYPE = {aar:'AAR', evaluation:'evaluation', impact_evaluation:'impact evaluation', monitoring_report:'monitoring', activation_report:'activation report',
                 case_study:'case study', story:'story', research:'research', guidance:'guidance', trigger_analysis:'trigger analysis', other:'other'};
function learningBlock(f, v){
  const docs = f.learning_docs || [], links = (v && v.learning) || [];
  const n = docs.length + links.length;
  let html = `<h4>Learning · ${n ? `${n} document${n>1?'s':''}` : 'no documents yet'}</h4>`;
  if(!n) return html + `<div class='muted'>No learning documents recorded for this framework yet — after-action reviews, evaluations and activation reports will appear here.</div>`;
  html += `<ul class='small' style='margin:2px 0 6px;padding-left:18px'>`;
  docs.forEach(d => { html += `<li>${d.url?`<a href='${esc(d.url)}' target='_blank' rel='noopener'>${esc(d.title)}</a>`:esc(d.title)}${d.publisher?` · ${esc(d.publisher)}`:''}${d.year?` · ${d.year}`:''}${d.type?` <span class='dtag'>${esc(DOCTYPE[d.type]||d.type.replace(/_/g,' '))}</span>`:''}${d.stat?`<div class='muted'>${esc(d.stat)}</div>`:''}</li>`; });
  links.forEach(d => { html += `<li>${d.url?`<a href='${esc(d.url)}' target='_blank' rel='noopener'>${esc(d.title||d.url)}</a>`:esc(d.title||'')}${d.date?` <span class='muted'>(${esc(d.date)})</span>`:''} <span class='dtag'>framework page</span></li>`; });
  return html + `</ul>`;
}
// Model: technical documentation links (trigger analysis, framework document, validation folder)
function techDocsBlock(v){
  const items = [];
  if(v.analysis_ref) items.push(v.analysis_url ? `<a href='${esc(v.analysis_url)}' target='_blank' rel='noopener'>trigger analysis ↗</a> <span class='muted'>${esc(v.analysis_ref)}</span>` : `trigger analysis: <code>${esc(v.analysis_ref)}</code>`);
  if(v.doc_url) items.push(`<a href='${esc(v.doc_url)}' target='_blank' rel='noopener'>framework document ↗</a>${v.doc_title?` <span class='muted'>${esc(v.doc_title)}</span>`:''}`);
  if(TRIGGER_VALIDATION_URL) items.push(`<a href='${esc(TRIGGER_VALIDATION_URL)}' target='_blank' rel='noopener'>trigger validation (Drive) ↗</a>`);
  if(!items.length) return '';
  return `<h4>Technical documentation</h4>` + items.map(x=>`<div class='tdoc'>${x}</div>`).join('');
}
// Plan: the framework's partner list (aa.framework_partner, this version or the latest that
// has one) and the funded sub-grantees of the country's CERF AA allocations (aa.cerf_subgrant)
const PGROUPS = ['Government', 'UN', 'International NGOs', 'National NGOs', 'Red Cross / Red Crescent', 'Other'];
const ROLE = {implementing:'implementing', sub_grantee:'sub-grantee', technical:'technical', coordination:'coordination', government_counterpart:'counterpart', funding:'funding'};
function partnersBlock(c, f, v){
  const P = (v && v.partners) || [], S = c.subgrants || [];
  let html = `<h4>Partners${P.length?` · ${P.length}`:''}</h4>`;
  if(!P.length && !S.length) return html + `<div class='muted'>No partner list yet.</div>`;
  if(P.length){
    html += `<div class='small'><b>${P.length} partner${P.length>1?'s':''}</b> named in the framework${v && v.partners_from ? ` <span class='muted'>(from version ${esc(v.partners_from)} — none extracted for ${esc(v.v)})</span>` : ''}</div>`;
    PGROUPS.forEach(g => { const rows = P.filter(p=>p.group===g); if(!rows.length) return;
      html += `<div class='pgrp'>${g} <span class='muted' style='font-weight:400'>(${rows.length})</span></div>` + rows.map(p =>
        `<div class='prow'>${esc(p.name)}${p.acronym?` (${esc(p.acronym)})`:''}${p.parent?` <span class='muted'>· under ${esc(p.parent)}</span>`:''}${p.roles.map(r=>`<span class='rtag'>${esc(ROLE[r]||r.replace(/_/g,' '))}</span>`).join('')}${p.usd?` <span class='muted'>· ${money(p.usd)}</span>`:''}</div>`).join(''); });
  } else html += `<div class='muted'>No partner list extracted from the framework document yet.</div>`;
  if(S.length){
    const tot = S.reduce((s,a)=>s+a.partners.reduce((t,p)=>t+(p.usd||0),0),0), nP = S.reduce((s,a)=>s+a.partners.length,0);
    html += `<h4>Funded sub-grantees <span class='muted' style='text-transform:none'>(CERF AA allocations, ${esc(c.name)}, all hazards)</span></h4>
      <div class='small'>${nP} sub-grant${nP>1?'s':''} · ${money(tot)}</div>` + S.map(a =>
      `<div class='pgrp'>${esc(a.agency)} <span class='muted' style='font-weight:400'>· ${money(a.partners.reduce((t,p)=>t+(p.usd||0),0))}</span></div>` +
      a.partners.map(p=>`<div class='prow'>${esc(p.name)}${p.acronym&&p.acronym!==p.name?` (${esc(p.acronym)})`:''}${p.type?`<span class='rtag'>${esc(p.type)}</span>`:''}${p.usd?` <span class='muted'>· ${money(p.usd)}</span>`:''}</div>`).join('')).join('');
  }
  return html;
}
function miniTable(rows){ return rows.length ? `<table class='mini' style='margin-top:4px'>${rows.map(([k,val])=>`<tr><td class='lbl'>${k}</td><td>${val}</td></tr>`).join('')}</table>` : ''; }
function sectorBlock(v){
  const F = v.funding; if(!F.sector.length) return '';
  const tot = groupBy(F.sector, x=>x.sector, x=>x.usd);
  const keys = Object.keys(tot).sort((a,b)=>tot[b]-tot[a]);
  return `<h4>Budget by sector</h4><table class='mini'><tr><th>sector</th><th class='num'>USD</th></tr>` + keys.map(k=>`<tr><td>${esc(k)}</td><td class='num'>${money(tot[k])}</td></tr>`).join('') + `</table>`;
}
// the CERF allocations behind a pair's ad hoc AA allocations: amount, agencies, sectors, people
function adhocBlock(f){
  const A = f.adhoc_cerf || [];
  if(!A.length) return f.n_adhoc ? `<div class='muted small'>No CERF allocation found for these allocations in the CERF data.</div>` : '';
  const CW = Math.max(280, Math.min(560, (side.clientWidth || 420) - 36));
  return `<h4>Ad hoc allocations (${A.length})</h4>` + A.map(a => `<div class='trig'>
      <div class='tn'><a href='${esc(a.url)}' target='_blank' rel='noopener'>CERF ${esc(a.code)} ↗</a> <span class='muted'>· ${esc(a.emergency||'')} · ${a.year}</span></div>
      <div class='tt'><b>${money(a.usd)}</b>${a.planned?` · ${num(a.planned)} people planned`:''}${a.reached?` · ${num(a.reached)} reached`:''}</div>
      ${a.title?`<div class='tm'>${esc(a.title)}</div>`:''}
      ${a.agencies.length?`<div class='small' style='margin-top:4px'><b>Agencies</b></div>` + hbarsSVG(a.agencies.map(x=>({label:x.agency, v:x.usd})), {width:CW, fmt:money, colorBy:'a', label:'CERF allocation by agency'}):''}
      ${a.sectors.length?`<div class='small' style='margin-top:4px'><b>Sectors</b></div>` + hbarsSVG(a.sectors.map(x=>({label:x.sector, v:x.usd})), {width:CW, fmt:money, color:'#64748b', label:'CERF allocation by sector'}):''}
      <div class='tm'>${a.how==='recorded allocation code' ? 'Allocation code recorded with the ad hoc allocation.' : 'Matched to the CERF allocation of the same country, year and emergency type (no code recorded).'}</div>
    </div>`).join('');
}
function groupBy(rows, kf, vf){ const m = {}; rows.forEach(r=>{ const k = kf(r); m[k] = (m[k]||0) + (vf(r)||0); }); return m; }
function fwHeader(c, f){
  return `<h3 style='display:flex;align-items:center;gap:8px'>${iconHTML(f)}<span>${esc(c.name)} — ${esc(f.hz_label)}</span></h3>
   <div>${pastY() && !f.layers.length ? `<span class='badge b-retired'>no framework at the end of ${YEAR}</span>` : badge(f.disp) + (pastY() ? DRV(statusNote(f).slice(3)) : '')}${f.tech?` <span class='badge b-tech'>OCHA technical support</span>`:''} ${f.ring ? `<span class='small' style='color:#c8860a'>&bull; in its monitoring season</span>` : ''}
   ${f.kb?` <span class='muted'>· KB <code>${f.kb}</code></span>`:''}${f.in_force && f.in_force!==f.current ? ` <span class='muted'>· tracking view in force: ${f.in_force}</span>` : ''}</div>`;
}
function versionBar(f, v, isCur){
  const opts = [...f.versions].reverse().map(x=>`<option value='${x.v}' ${x.v===v.v?'selected':''}>${x.v}${x.v===f.current?(pastY()?` (at the end of ${YEAR})`:' (latest)'):''} — ${x.superseded?'superseded':(x.status||'?')}</option>`).join('');
  return `<div class='verbar'><label class='small'>Version</label><select onchange='selectVersion(this.value)'>${opts}</select>
    ${v.doc_url ? `<a class='docbtn' href='${esc(v.doc_url)}' target='_blank' rel='noopener' title='${esc(v.doc_title||'')}'>Framework doc ↗</a>` : `<span class='badge b-retired'>no document link</span>`}</div>`;
}
function factsBlock(f, v){
  const rows = [];
  rows.push(['Status', `${verBadge(v.superseded?'superseded':v.status)}${v.endorsed_by?` <span class='muted'>endorsed by ${esc(v.endorsed_by)}</span>`:''}${v.superseded?` <span class='muted'>· a newer endorsed version exists</span>`:''}`]);
  if(v.windows.length){ const n = v.windows.filter(w=>w.triggered===true).length;
    rows.push(['Triggered', `${n?`<b>${n}</b> of ${v.windows.length} window${v.windows.length>1?'s':''}`:`none of ${v.windows.length} window${v.windows.length>1?'s':''}`}${v.fully_triggered?` <span class='badge b-endorsed'>fully triggered</span>`:''}${n&&!v.fully_triggered?` <span class='muted'>· partial (independent windows)</span>`:''}`]); }
  rows.push(['Valid', `${v.valid_from||'?'} → ${v.valid_until||'<span class="muted">open</span>'}${v.valid_until_source?` <span class='muted'>(${esc(v.valid_until_source)})</span>`:''}`]);
  if(v.doc_title) rows.push(['Document', `${esc(v.doc_title)}${v.doc_date?` <span class='muted'>(${v.doc_date})</span>`:''}`]);
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
        ${bt?`<div class='tm'>${bt.triggered===true?`<b style='color:#b45309'>triggered${bt.triggered_on?' '+bt.triggered_on:''}</b> · `:''}backtest: ${bt.rp?`1-in-${bt.rp.toFixed(1)} yr`:''}${bt.prob?` · ${(bt.prob*100).toFixed(0)}%/yr`:''}${bt.sim!=null?` · ${bt.sim} in ${bt.years} yrs`:''}${bt.budget?` · budget ${money(bt.budget)}`:''}</div>`:''}
      </div>`;
    });
  }
  const extra = v.windows.filter(w => !v.triggers.some(t => sameWin(w.name, t.window || t.trigger || Object.values(t)[0])));
  if(extra.length){
    html += `<h4>${v.triggers.length?'Other backtested windows':'Windows (backtest registry)'}</h4><table class='mini'><tr><th>window</th><th>basis</th><th>state</th><th>budget</th><th>return period</th><th>annual prob</th></tr>` +
      extra.map(w=>`<tr><td>${esc(w.name)}</td><td>${esc(w.basis||'')}${w.all_in===true?' · all-in':''}</td><td>${w.triggered===true?`<b style='color:#b45309'>triggered</b>${w.triggered_on?` <span class='muted'>${w.triggered_on}</span>`:''}`:w.triggered===false?'<span class="muted">not triggered</span>':''}</td><td class='num'>${money(w.budget)}</td><td class='num'>${w.rp?w.rp.toFixed(1)+' yr':''}</td><td class='num'>${w.prob?(w.prob*100).toFixed(0)+'%':''}</td></tr>`).join('') + `</table>`;
  }
  if(!html) html = `<h4>Triggers</h4><div class='muted'>No structured trigger information for this version yet — see the framework document.</div>`;
  return html;
}
function fundingBlock(v){
  const F = v.funding; if(!F.agency.length && !F.sector.length && !F.fund.length) return '';
  // budget sanity: the split rows (one source per version, v_window_funding_split) must not
  // add up to more than the version's envelope — a flag here is a genuine data problem
  const splitTot = F.fund.reduce((s,x)=>s+x.usd,0), env = v.envelope ?? v.prearranged_doc;
  const over = env != null && splitTot > env * 1.01;
  let html = `<div class='small' style='margin:8px 0 4px'>Split total <b>${money(splitTot)}</b>${env!=null?` of a ${money(env)} envelope`:' — no envelope recorded'}${F.src==='sheet'?' <span class="muted">(tracking sheet)</span>':''}${over?`<span class='warntag' title='the agency × sector split adds up to more than the version envelope'>split exceeds envelope</span>`:''}</div>`;
  if(F.fund.length > 1) html += `<div class='small muted'>By fund: ${F.fund.map(x=>`${esc(x.fund)} ${money(x.usd)}`).join(' · ')}</div>`;
  const CW = Math.max(280, Math.min(560, (side.clientWidth || 420) - 36));
  const bars = (rows, label) => { const m = groupBy(rows, x=>x[label], x=>x.usd);
    return hbarsSVG(Object.entries(m).sort((a,b)=>b[1]-a[1]).map(([k,u])=>({label:k, v:u})), {width:CW, fmt:money, label:`budget by ${label}`, colorBy: label==='agency' ? 'a' : null, color:'#64748b'}); };
  if(F.agency.length) html += `<h4>Budget by agency</h4>` + bars(F.agency, 'agency');
  if(F.sector.length) html += `<h4>Budget by sector</h4>` + bars(F.sector, 'sector');
  if((F.pair||[]).length > 1){
    const ag = [...new Set(F.pair.map(x=>x.agency))], se = [...new Set(F.pair.map(x=>x.sector))];
    html += `<h4>Which agency, which sector</h4>` + sankeySVG({columns:[ag.map(a=>({id:'a:'+a, label:a})), se.map(x=>({id:'s:'+x, label:x}))],
      links: F.pair.map(x=>({s:'a:'+x.agency, t:'s:'+x.sector, v:x.usd})), width:CW, fmt:money, labelW:110, label:'agency to sector'});
  }
  return html;
}
function scopeBlock(v){
  const s = v.scope; if(!s) return '';
  const names = (L[state.iso].area_names) || {};
  const nm = pcs => pcs.map(p => names[p] || p).sort((a,b)=>a.localeCompare(b));
  let html = `<h4>Geographic scope${v.admin_level!=null?` <span class='muted' style='text-transform:none'>(trigger at admin ${v.admin_level})</span>`:''}</h4>`;
  if(s.inherited_from) html += `<div class='warnbox'>Scope not yet extracted for this version — the map shows the ${esc(s.inherited_from)} scope.</div>`;
  if(s.approx) html += `<div class='warnbox'>The framework's zone could not be mapped to admin areas${s.unmatched.length?` (${esc(s.unmatched.join('; '))})`:''} — the whole country is shown.</div>`;
  const nt = (s.tiers||[]).length;
  if(nt){
    html += s.tiers.map((t,i)=>`<div class='scopelist'><span class='sq' style='display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px;background:${shade(hzColor(state.hz), nt>1?i/(nt-1):0)}'></span><b>${esc(t.label||'named areas')}</b>${t.rest ? ' — everywhere not named above' : `: ${nm(t.pcodes).map(esc).join(', ')}`}</div>`).join('');
  } else if(s.national && !s.approx) html += `<div class='scopelist'>National trigger — whole country.</div>`;
  else if(s.pcodes.length) html += `<div class='scopelist'>${nm(s.pcodes).map(esc).join(', ')}</div>`;
  if(!s.national && !s.pcodes.length && !s.inherited_from) html += `<div class='muted'>Scope not extracted for this version yet.</div>`;
  if(s.unmatched.length && !s.approx) html += `<div class='small' style='margin-top:4px;color:#8a5c0a'>Not on the map (no boundary match): ${s.unmatched.map(esc).join('; ')}</div>`;
  return html;
}
// the link for a real activation: its announcement, else its CERF allocation page
function actLinks(a){
  const out = [];
  if(a.url) out.push(`<a href='${esc(a.url)}' target='_blank' rel='noopener'>announcement↗</a>`);
  (a.funding||[]).forEach(x => { if(x.cerf_url) out.push(`<a href='${esc(x.cerf_url)}' target='_blank' rel='noopener'>CERF allocation↗</a>`); });
  return [...new Set(out)];
}
function actMoney(a){ return (a.funding||[]).filter(x=>x.usd!=null).map(x=>`${String(x.fund).toUpperCase()} ${money(x.usd)}`).join(' + ') || (a.released ? money(a.released) : ''); }
function realMark(a, v){
  const old = !!(v && a.version && a.version !== v.v && !String(a.version).startsWith(v.v) && !String(v.v).startsWith(a.version));
  const title = `${a.date} · ${a.window||'window not recorded'}${actMoney(a)?' · '+actMoney(a):''}${old?` · under version ${a.version}`:''}${a.full===false?' · partial':''}`;
  const href = a.url || ((a.funding||[]).find(x=>x.cerf_url)||{}).cerf_url;
  return href ? `<a class='rm ${old?'old':''}' href='${esc(href)}' target='_blank' rel='noopener' title='${esc(title)}'></a>`
              : `<span class='rm ${old?'old':''}' title='${esc(title)}'></span>`;
}
// historical activations: the simulation of this version's triggers (one row per year or storm,
// one column per window), with every REAL activation of the framework marked into the grid
function backtestBlock(f, v){
  const bt = v.backtest; if(!bt) return '';
  const trigName = w => { const t = v.triggers.find(t => sameWin(w, t.window || t.trigger || Object.values(t)[0])); const n = t ? (t.window || t.trigger || Object.values(t)[0]) : null; return n && n.toLowerCase() !== w.toLowerCase() ? `${esc(n)}` : esc(w); };
  const rows = bt.rows.map(r => ({...r, real:{}, realYear:[]}));
  f.activations.filter(a => a.type === 'framework_aa').forEach(a => {
    const y = +String(a.date).slice(0,4), col = bt.windows.find(w => sameWin(w, a.window));
    if(!y) return;
    let r = bt.per_event ? null : rows.find(x => x.year === y && !x.label);
    if(!r){ r = {year:y, label: bt.per_event ? 'activation' : null, fired:[], real:{}, realYear:[], extra:true}; rows.push(r); }
    if(col) (r.real[col] ??= []).push(a); else r.realYear.push(a);
  });
  rows.sort((a,b) => b.year - a.year || String(a.label||'').localeCompare(String(b.label||'')));
  // from the year the version took effect: real activations only (its backtest was fixed before)
  const use0 = bt.in_use_from || null, inUse = y => use0 != null && y >= use0;
  const useTip = y => bt.in_use_to && y > bt.in_use_to
    ? `${y}: after version ${v.v} was replaced (${bt.in_use_to}) — real activations only`
    : `${y}: version ${v.v} in use (took effect ${v.valid_from || use0}) — real activations only; its simulation covers the years before`;
  const simYears = new Set(bt.rows.filter(r => !inUse(r.year)).map(r => r.year));
  const dot = (w, r) => `<span class='bt-dot' style='background:${hzColor(f.hazard)}' title='would have activated ${r && r.when && r.when[w] ? 'on '+esc(r.when[w]) : 'in '+(r ? r.year : 'that year')} (simulation)'></span>`;
  const cell = (r, w) => inUse(r.year) ? `<td class='bt-c bt-use' title='${esc(useTip(r.year))}'>`
    : simYears.has(r.year) && !r.extra ? `<td class='bt-c'>`
    : `<td class='bt-c bt-na' title='${r.year} is not covered by the historical simulation'>`;
  let html = `<h4>Historical activations</h4>
    <div class='small' style='margin-bottom:4px'>Simulation ${bt.start}–${bt.end}: would each trigger of this version have activated${bt.per_event?' for each storm':' each year'}?${use0 ? ` From ${use0}, when the version took effect, real activations only.` : ''} Real activations are marked in, linked to their announcement.${bt.after_note ? ` <span class='muted'>${esc(bt.after_note)}</span>` : ''}</div>
    <table class='mini bt'><thead><tr><th>${bt.per_event?'storm':'year'}</th>${bt.windows.map(w=>`<th class='bt-c'>${trigName(w)}</th>`).join('')}</tr></thead><tbody>`;
  html += rows.map(r => `<tr class='${r.fired.length?'bt-on':''}'><td class='lbl'>${r.year}${r.label?` <span class='muted'>${esc(r.label)}</span>`:''}${inUse(r.year) && !r.label && !(bt.in_use_to && r.year > bt.in_use_to) ? ` <span class='bt-usetag' title='${esc(useTip(r.year))}'>in use</span>` : ''}${r.realYear.map(a=>realMark(a, v)).join('')}</td>`
    + bt.windows.map(w => `${cell(r, w)}${r.fired.includes(w) && !inUse(r.year) ? dot(w, r) : ''}${(r.real[w]||[]).map(a=>realMark(a, v)).join('')}</td>`).join('') + `</tr>`).join('');
  return html + `</tbody></table><div class='small bt-key'>${dot()} would have activated (simulation) · <span class='rm'></span> activated, money released · <span class='rm old'></span> activated under an earlier version${use0 ? ` · <span class='bt-sw bt-use'></span> version in use: real activations only` : ''}</div>`;
}
// the real activations of the framework, all versions: when, which window, how much, links
function actualBlock(f, v){
  const A = f.activations;
  let html = `<h4>Actual activations (${A.length})</h4>`;
  if(!A.length) return html + `<div class='muted'>Never activated.</div>`;
  return html + `<table class='mini acttbl'><colgroup><col style='width:22%'><col style='width:30%'><col style='width:22%'><col style='width:26%'></colgroup>
    <tr><th>date</th><th>window</th><th>funding</th><th>links</th></tr>` + A.map(a => {
      const old = !!(v && a.version && a.version !== v.v && !String(a.version).startsWith(v.v) && !String(v.v).startsWith(a.version));
      const tags = (a.type!=='framework_aa'?` <span class='badge b-retired'>${esc(a.type.replace(/_/g,' '))}</span>`:'')
        + (a.full===false?` <span class='badge b-development'>partial</span>`:'')
        + (old?` <span class='vtag other' title='Fired under version ${esc(a.version)}, an earlier version than the one shown (${esc(v.v)}); its triggers and budget may differ.'>v ${esc(a.version)}</span>`:'');
      return `<tr${old?" class='oldv'":''}><td>${esc(a.date)}${tags}</td><td>${a.window?esc(a.window):'<span class="muted">not recorded</span>'}${a.people?`<div class='muted'>${num(a.people)} people</div>`:''}</td><td>${actMoney(a)||'<span class="muted">—</span>'}</td><td>${actLinks(a).join('<br>')||'<span class="muted">—</span>'}</td></tr>`;
    }).join('') + `</table>`;
}

// ---------- plain-language help: ⓘ after the first use of a term, <abbr> around the first
// use of an acronym, applied to the TEXT NODES of a rendered block (never by hand in strings).
// `scope` is the container whose earlier annotations count as "already explained".
const HELP = [
  ['pre-arranged', /\bpre-?arranged\b/i, 'money set aside in advance so it can be released the moment a trigger is met'],
  ['trigger', /\btriggers?\b/i, 'the pre-agreed forecast or observation threshold that releases the money'],
  ['window', /\bwindows?\b/i, 'the period in the year during which a trigger is monitored'],
  ['return period', /\breturn periods?\b/i, 'how rare the trigger threshold is: a 1-in-5-year trigger is expected to be met about once every five years'],
  ['activation probability', /\b(activation probability|annual prob(?:ability)?)\b/i, 'the chance the trigger is met in any given year'],
  ['all-in', /\ball-in\b/i, 'all windows share one envelope: the first window to fire takes it'],
  ['lead time', /\blead time\b/i, 'how far ahead of the shock the money is released'],
  ['readiness', /\b(readiness(?: vs\.? action)?|readiness and action)\b/i, 'readiness money prepares the response before the shock is certain; action money delivers it'],
];
const ABBR = {CERF:'Central Emergency Response Fund', CBPF:'Country-Based Pooled Fund', RhPF:'Regional Humanitarian Pooled Fund', ERC:'Emergency Relief Coordinator',
  AA:'anticipatory action', GHO:'Global Humanitarian Overview', HRP:'Humanitarian Response Plan', IPC:'Integrated Food Security Phase Classification',
  CH:'Cadre Harmonisé', SEAS5:'ECMWF seasonal forecast system', ECMWF:'European Centre for Medium-Range Weather Forecasts', GloFAS:'Global Flood Awareness System',
  ASAP:'Anomaly hot Spots of Agricultural Production', 'FEWS NET':'Famine Early Warning Systems Network', ENSO:'El Niño–Southern Oscillation', NDMO:'National Disaster Management Office',
  UNFPA:'United Nations Population Fund', UNHCR:'UN Refugee Agency', UNICEF:'United Nations Children\'s Fund', WFP:'World Food Programme', FAO:'Food and Agriculture Organization of the United Nations',
  IOM:'International Organization for Migration', WHO:'World Health Organization', IFRC:'International Federation of Red Cross and Red Crescent Societies'};
const ABBR_RE = new RegExp('(?<![\\w-])(' + Object.keys(ABBR).sort((a,b)=>b.length-a.length).join('|') + ')(?![\\w-])');
const SKIP = new Set(['SCRIPT','STYLE','SELECT','OPTION','TEXTAREA','CODE','ABBR','INPUT']);
function annotate(root, scope){
  scope = scope || root;
  const doneHelp = new Set([...scope.querySelectorAll('.info[data-term]')].map(e=>e.dataset.term));
  const doneAbbr = new Set([...scope.querySelectorAll('abbr[data-ab]')].map(e=>e.dataset.ab));
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: n => {
    for(let p = n.parentNode; p && p !== root.parentNode; p = p.parentNode){ if(p.nodeType===1 && (SKIP.has(p.tagName) || p.namespaceURI === NS || (p.classList && p.classList.contains('info')))) return NodeFilter.FILTER_REJECT; }
    return n.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP; } });
  const nodes = []; for(let n; (n = walker.nextNode());) nodes.push(n);
  for(let node of nodes){
    for(;;){
      const txt = node.nodeValue; let best = null;
      for(const [key, re, tip] of HELP){ if(doneHelp.has(key)) continue; const m = re.exec(txt); if(m && (!best || m.index < best.idx)) best = {idx:m.index, len:m[0].length, key, tip, kind:'help'}; }
      const am = ABBR_RE.exec(txt); if(am && !doneAbbr.has(am[1]) && (!best || am.index < best.idx)) best = {idx:am.index, len:am[0].length, key:am[1], tip:ABBR[am[1]], kind:'abbr'};
      if(!best) break;
      const after = node.splitText(best.idx), rest = after.splitText(best.len);   // node | after (the match) | rest
      if(best.kind==='abbr'){ const ab = document.createElement('abbr'); ab.title = best.tip; ab.dataset.ab = best.key; ab.textContent = after.nodeValue; after.replaceWith(ab); doneAbbr.add(best.key); }
      else { const i = document.createElement('span'); i.className = 'info'; i.tabIndex = 0; i.setAttribute('role','note'); i.setAttribute('aria-label', best.tip); i.dataset.term = best.key; i.dataset.tip = best.tip; i.textContent = 'i';
             after.parentNode.insertBefore(i, rest); doneHelp.add(best.key); }
      node = rest;
    }
  }
}

// ---------- boot
// deep links: #ISO/hazard/version, with the year as a '|2024' suffix, or a bare #2024
const HASH0 = (function(){ let [p, y] = decodeURIComponent(location.hash.replace('#','')).split('|');
  if(!y && /^\d{4}$/.test(p || '')){ y = p; p = ''; }
  y = +y; if(!(y >= YEARS.first && y <= YEARS.now)) y = null;
  return {path: (p || '').split('/'), year: y}; })();
snapLive();
if(HASH0.year != null){ YEAR = HASH0.year; applyYear(); syncYearUI(); }
fixHeight(); buildWorld(); syncOn(); worldLegend(); updateTiles(); buildCallouts(); runLayout();
if(isMobile()){ maprow.classList.add('open'); renderWorldList(); }
setTimeout(runLayout, 300);   // once fonts have settled
(function(){ const h = HASH0.path; if(h[0] && L[h[0]]) selectCountry(h[0], h[1]||null, h[2]||null); })();
"""
