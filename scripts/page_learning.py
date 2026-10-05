"""The Learning page (pillar-learning.html): a map of headline findings, then the repository.

Reworked on 2026-10-05 into two things only. (1) A world map with six headline findings
called out of the countries they are about (three on saving lives and livelihoods, three on
cost effectiveness); hovering any shaded country shows that country's own headlines.
(2) The repository: every public learning document, filterable by country and hazard,
sortable by year; a row opens a side panel with the link, the key facts and the summary.

Documents come from aa.learning_document (public rows only: internal ones are excluded in
dashboards._fetch). The headline findings are curated below, each tied to the document
that states it."""

import html
import itertools
import json

import landing
import pandas as pd
from dashboards import DOC_TYPE_LABEL, PREMISES, _aslist
from import_learning import PLACEHOLDER

# ---- headline findings ---------------------------------------------------------------------
# One finding of one learning document about ONE country, under one premise: `big` is the
# figure that jumps out of the map, `text` the sentence around it. Both are the document's
# own statement, tightened to fit a callout: the figures are the document's, nothing is added.
# `src` is the document's url in aa.learning_document (a finding whose document is not there,
# or is internal, is dropped at build time). `featured` = one of the callouts shown by
# default; on hover a country shows its own findings, in this order.
EVIDENCE = ("https://reliefweb.int/report/world/"
            "saving-lives-time-and-money-evidence-anticipatory-action-may-2025")
DRC_STORY = ("https://data.humdata.org/dataset/2048a947-5714-4220-905b-e662cbcd14c8/resource/"
             "9e47fd0e-c0e0-4fa3-ab93-4efa4d740552/download/aa_impact_story_cholera_drc_final.pdf")


def _h(iso, premise, big, text, src=EVIDENCE, featured=False):
    return {"iso": iso, "premise": premise, "big": big, "text": text, "src": src,
            "featured": featured}


HEADLINES = [
    # saving lives and livelihoods
    _h("SOM", "lives_livelihoods", "About 118 deaths, against 2,300",
       "Loss of life in the 2023 El Niño floods, after early warning and anticipatory action, "
       "against a comparable event in 1997.", featured=True),
    _h("COD", "lives_livelihoods", "0.27% case fatality",
       "Fewer than 3 deaths per 1,000 cholera cases in the targeted health zones of North and "
       "South Kivu, February to May 2023.", src=DRC_STORY, featured=True),
    _h("ETH", "lives_livelihoods", "13,000 children stayed in school",
       "Cash assistance ahead of the 2021 drought prevented them from dropping out.",
       featured=True),
    _h("AFG", "lives_livelihoods", "From 6% to over 50%",
       "Families with acceptable food consumption, before and after anticipatory action "
       "ahead of the 2021 La Niña drought."),
    _h("SOM", "lives_livelihoods", "From 22% to 89%",
       "People with access to a functioning water point, after water points were built and "
       "rehabilitated ahead of the 2020–2022 drought."),
    _h("HND", "lives_livelihoods", "40% higher maize yields",
       "Farmers assisted in the anticipatory activation for the 2023–2024 El Niño drought."),
    _h("SDN", "lives_livelihoods", "0.8 litre more milk a day",
       "Per agropastoral household, after livestock vaccination, animal feed and destocking "
       "training ahead of the 2017 drought."),
    _h("LSO", "lives_livelihoods", "12 points more people avoided negative coping",
       "The share who did not have to sell livestock or adopt other negative livelihood "
       "coping mechanisms, with anticipatory assistance."),
    _h("PHL", "lives_livelihoods", "No seed loans at up to 15% interest",
       "Drought-tolerant seeds distributed ahead of the exceptionally dry 2019 season "
       "spared farmers from buying seed on credit."),
    _h("NER", "lives_livelihoods", "Not forced to migrate",
       "Families assisted ahead of the 2022 drought did not have to leave to find income; "
       "cash let them buy food, protect livestock and keep children in school."),
    _h("MDG", "lives_livelihoods", "80% felt better prepared",
       "People supported ahead of the forecast 2023 drought, who also reported improved "
       "mental well-being."),
    # cost effectiveness
    _h("BGD", "cost_effectiveness", "Half the cost",
       "Acting ahead of the 2020 floods reached people for $13 each, against $26 in the "
       "regular rapid response of 2019.", featured=True),
    _h("SSD", "cost_effectiveness", "4 times cheaper",
       "Protecting a road and transporting supplies before the floods, against airlifting "
       "them after.", featured=True),
    _h("NPL", "cost_effectiveness", "$1 could save $35",
       "Modelled over 20 years: each dollar invested in acting ahead of floods could save "
       "about $35 in future emergency response costs.", featured=True),
    _h("KEN", "cost_effectiveness", "$3.50 back for every $1",
       "Animal feed distributed ahead of the 2017 drought peak: the benefit to households "
       "for each dollar invested."),
    *[_h(iso, "cost_effectiveness", "$1 early = $1.30 later",
         "Southern Africa, 2023–2024 El Niño drought: a dollar provided before the drought "
         "had the same impact as $1.30 provided later (conservative estimate).")
      for iso in ("MOZ", "MDG", "LSO")],
    # speed
    _h("BGD", "speed", "16 minutes",
       "CERF allocated $6.2 million within 16 minutes of the 2024 flood alert; some 500,000 "
       "people were assisted within five days, ahead of the peak."),
    _h("NPL", "speed", "6 minutes",
       "From the early-warning trigger for flooding in 2024 to CERF funds released to "
       "agencies."),
    _h("MOZ", "speed", "13 minutes",
       "To provide CERF funding to partners, days ahead of Tropical Cyclone Jude's landfall "
       "in 2025."),
    _h("AFG", "speed", "8 months earlier",
       "Anticipatory actions started eight months before the La Niña drought emergency was "
       "declared in June 2021."),
    _h("MNG", "speed", "4 months earlier",
       "Action against the harsh winter (dzud) of 2017/18 began four months before the "
       "standard emergency response."),
    # dignity
    _h("COL", "dignity", "74% reported better community relations",
       "Households in community production centres set up ahead of the 2018 drought: "
       "nearly double the share among households not assisted."),
]
PER_COUNTRY = 3        # findings a country shows on hover
# premise -> (dot / accent colour, text colour on white); the two premises of the default
# callouts get a colour of their own, the others share a neutral one
PREMISE_COLOR = {"lives_livelihoods": ("#1baf7a", "#0d7a54"),
                 "cost_effectiveness": ("#eda100", "#8a5a00")}
NEUTRAL = ("#7a8699", "#556270")
HAZARD_LABEL = {"drought": "Drought", "flood": "Floods", "storm": "Tropical cyclones",
                "cholera": "Cholera", "other": "Other"}
# a country's own best key statistics, behind its curated findings: evaluations first
TYPE_RANK = {"impact_evaluation": 0, "evaluation": 1, "research": 2, "aar": 3,
             "monitoring_report": 4, "case_study": 5}


def _t(v):
    """A non-empty string, or None (pandas missing values are truthy: never `v or ...`)."""
    return v.strip() if isinstance(v, str) and v.strip() else None


def _url(v):
    """The document's link: http(s) only, and not the compendium's placeholder link."""
    u = _t(v)
    if not u or not u.lower().startswith(("http://", "https://")):
        return None
    return None if any(p in u for p in PLACEHOLDER) else u


def _key(u):
    return (u or "").lower().rstrip("/")


def _world(on):
    """The world base, server-rendered in the landing map's projection and frame.

    Returns (svg paths, {iso: name}, {iso: [x1, y1, x2, y2]} of each country's largest
    polygon, xy) in view-box units; `xy(lon, lat)` projects a point the same way."""
    from shapely.geometry import MultiPolygon
    x0, y0, x1, _ = landing.EE_BBOX
    k, W, H = landing.VB_W / (x1 - x0), landing.VB_W, landing.VB_H

    def xy(lon, lat):
        x, y = landing.equal_earth(lon, lat)
        return (x - x0) * k, (y - y0) * k

    paths, names, boxes = [], {}, {}
    for f in landing.world_simplified().itertuples():
        polys = list(f.geometry.geoms) if isinstance(f.geometry, MultiPolygon) else [f.geometry]
        names[f.iso] = f.NAME
        d = []
        for poly in sorted(polys, key=lambda p: -p.area):
            for i, ring in enumerate([poly.exterior, *poly.interiors]):
                pts = [xy(lon, lat) for lon, lat in ring.coords]
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                # a ring cut by the projection's edge would sweep across the map; one
                # wholly outside the frame is not drawn
                if (any(abs(a - b) > W / 2 for a, b in itertools.pairwise(xs))
                        or max(xs) < 0 or min(xs) > W or max(ys) < 0 or min(ys) > H):
                    continue
                if i == 0 and f.iso not in boxes:
                    boxes[f.iso] = [round(v, 1) for v in (min(xs), min(ys), max(xs), max(ys))]
                seg, last = [], None
                for x, y in pts:
                    p = f"{x:.1f},{y:.1f}"
                    if p != last:
                        seg.append(p)
                        last = p
                if len(seg) > 2:
                    d.append("M" + "L".join(seg) + "Z")
        if d:
            paths.append(f"<path class='cty{' on' if f.iso in on else ''}' data-iso='{f.iso}' "
                         f"d='{''.join(d)}'/>")
    return "".join(paths), names, boxes, xy


def build_learning(page, d):
    docs = d["learning"]          # public documents only (internal rows never leave _fetch)
    cur = d["current"]
    cnames = dict(zip(cur["country_iso3"], cur["country_name"]))
    fw_of = {}                    # iso -> hazards of its frameworks (each has a page)
    for r in cur.itertuples():
        fw_of.setdefault(r.country_iso3, []).append(r.hazard)
    premise_label = dict(PREMISES)

    # ---- documents
    recs, by_url = [], {}
    for r in docs.itertuples():
        isos = [str(x) for x in _aslist(r.country_iso3)]
        hz = _t(r.hazard)
        recs.append({
            "id": int(r.id), "t": str(r.title).strip(), "u": _url(r.url),
            "pub": _t(r.publisher), "y": int(r.year) if pd.notna(r.year) else None,
            "ty": DOC_TYPE_LABEL.get(r.doc_type, str(r.doc_type)).capitalize(),
            "type": r.doc_type, "iso": isos, "hz": hz,
            "pr": [p for p in _aslist(r.premises) if p in premise_label],
            "ks": _t(r.key_stat), "s": _t(r.summary),
            # the framework pages the document belongs to: its hazard's, or (a document
            # with no hazard) every framework of the country
            "fw": [[f"fw-{c.lower()}-{h}.html",
                    f"{cnames.get(c, c)} · {HAZARD_LABEL.get(h, str(h).replace('_', ' '))}"]
                   for c in isos for h in fw_of.get(c, []) if hz in (None, h)],
        })
        if _t(r.url):
            by_url.setdefault(_key(r.url), recs[-1])

    # ---- findings per country: the curated ones, then the country's own key statistics
    heads, featured = {}, []
    for h in HEADLINES:
        doc = by_url.get(_key(h["src"]))
        if doc is None:
            print(f"  learning: headline dropped, its document is not public / not found: "
                  f"{h['iso']} — {h['big']}")
            continue
        item = {"b": h["big"], "t": h["text"], "p": h["premise"], "d": doc["id"]}
        heads.setdefault(h["iso"], []).append(item)
        # the same finding stated for several countries is one key fact of its document
        doc.setdefault("hl", {}).setdefault((h["big"], h["text"]), []).append(h["iso"])
        if h["featured"]:
            featured.append({"iso": h["iso"], **item})
    is_featured = {(f["iso"], f["b"]) for f in featured}
    for c, items in heads.items():      # a country's default callout leads its own list
        items.sort(key=lambda x: (c, x["b"]) not in is_featured)

    def _rank(r):
        strong = any(p in PREMISE_COLOR for p in r["pr"])
        return (not strong, not r["pr"], TYPE_RANK.get(r["type"], 9), -(r["y"] or 0), r["t"])

    n_docs = {}
    for r in recs:
        for c in r["iso"]:
            n_docs[c] = n_docs.get(c, 0) + 1
    for c in n_docs:
        own = heads.setdefault(c, [])
        used = {x["d"] for x in own}
        mine = [r for r in recs if c in r["iso"] and r["id"] not in used]
        for r in sorted((r for r in mine if r["ks"]), key=_rank):
            if len(own) >= PER_COUNTRY:
                break
            own.append({"b": None, "t": r["ks"], "d": r["id"],
                        "p": next((p for p in r["pr"] if p in PREMISE_COLOR),
                                  r["pr"][0] if r["pr"] else None)})
        if not own:               # documents but no figure yet: its newest documents
            newest = sorted(mine, key=lambda r: (-(r["y"] or 0), r["t"]))
            own.extend({"b": None, "t": r["t"], "p": None, "d": r["id"], "doc": True}
                       for r in newest[:PER_COUNTRY])

    # ---- the map
    paths, wnames, boxes, xy = _world(set(heads))

    def name(c):
        return cnames.get(c) or wnames.get(c) or c

    countries = {}
    for c, items in heads.items():
        if c not in boxes:        # not on the map (outside the frame): findings stay in the list
            print(f"  learning: {c} is not on the map, its headlines are not shown")
            continue
        b = boxes[c]
        lat, lon = landing.CENTROID.get(c) or (None, None)
        x, y = xy(lon, lat) if lat is not None else ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
        countries[c] = {"n": name(c), "x": round(x, 1), "y": round(y, 1), "r": b,
                        "dir": landing.DIRECTIONS.get(c, (0.7, -0.7)),
                        "nd": n_docs.get(c, 0), "h": items[:PER_COUNTRY]}
    featured = [f for f in featured if f["iso"] in countries]
    feat_color = {f["iso"]: PREMISE_COLOR.get(f["p"], NEUTRAL)[0] for f in reversed(featured)}

    def dot(c, v):
        if c in feat_color:
            return (f"<circle class='ldot feat' data-iso='{c}' cx='{v['x']}' cy='{v['y']}' "
                    f"r='4.2' style='fill:{feat_color[c]}'/>")
        return f"<circle class='ldot' data-iso='{c}' cx='{v['x']}' cy='{v['y']}' r='2.8'/>"

    # the default callouts' dots are drawn last, on top
    dots = "".join(dot(c, v) for c, v in sorted(countries.items(),
                                                key=lambda kv: kv[0] in feat_color))
    for r in recs:
        r["cn"] = [name(c) for c in r["iso"]]
        r["hl"] = [{"n": ", ".join(name(c) for c in isos), "b": b, "t": t}
                   for (b, t), isos in r.get("hl", {}).items()]
        del r["type"]

    prem = {k: {"l": lab, "c": PREMISE_COLOR.get(k, NEUTRAL)[0],
                "ink": PREMISE_COLOR.get(k, NEUTRAL)[1]} for k, lab in PREMISES}
    legend = "".join(
        f"<span class='lg-i'><span class='lg-d' style='background:{PREMISE_COLOR[k][0]}'></span>"
        f"{html.escape(premise_label[k])}</span>"
        for k in dict.fromkeys(f["p"] for f in featured) if k in PREMISE_COLOR)

    # ---- the repository's filters
    c_opts = "".join(
        f"<option value='{c}'>{html.escape(n)} ({n_docs[c]})</option>"
        for n, c in sorted((name(c), c) for c in n_docs))
    n_global = sum(1 for r in recs if not r["iso"])
    hz_n = {}
    for r in recs:
        hz_n[r["hz"]] = hz_n.get(r["hz"], 0) + 1
    h_opts = "".join(
        f"<option value='{h}'>{html.escape(HAZARD_LABEL.get(h, h))} ({hz_n[h]})</option>"
        for h in [*[h for h in HAZARD_LABEL if h in hz_n],
                  *sorted(h for h in hz_n if h and h not in HAZARD_LABEL)])
    n_int = int(d.get("n_internal_docs", 0))

    data = {"docs": recs, "countries": countries, "featured": featured, "prem": prem,
            "hazard": HAZARD_LABEL, "vb": {"w": landing.VB_W, "h": round(landing.VB_H, 1)}}
    # "</" never appears inside the page's script element, whatever a title holds
    data_js = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    body = f"""<style>{LEARNING_CSS}</style>
<div class='lmapbox' id='lmapbox' style='aspect-ratio:{landing.VB_W:.0f}/{landing.VB_H:.1f}'>
 <svg id='lmap' viewBox='0 0 {landing.VB_W:.1f} {landing.VB_H:.1f}' preserveAspectRatio='xMidYMid meet'
  role='img' aria-label='World map of headline findings on anticipatory action'>
  <g id='lworld'>{paths}</g><g id='ldots'>{dots}</g></svg>
 <div id='lpane' class='lpane'><svg id='leaders' class='leadersvg'></svg></div>
 <div id='hcard' class='hcard' hidden></div>
 <div class='llegend' id='llegend'><b>Headline findings</b>{legend}
  <span class='lg-h'>Hover a shaded country for its own headlines; click it to keep them open.</span></div>
</div>
<div id='hlstack' class='hlstack'></div>
<div class='lrepo' id='lrepo'>
 <h2>Learning documents</h2>
 <div class='lbar'>
  <label>Country <select id='f-c'><option value=''>All countries</option>{
      f"<option value='_global'>Global, not country-specific ({n_global})</option>" if n_global else ""}{c_opts}</select></label>
  <label>Hazard <select id='f-h'><option value=''>All hazards</option>{h_opts}{
      f"<option value='_none'>Not hazard-specific ({hz_n[None]})</option>" if None in hz_n else ""}</select></label>
  <span class='lcount' id='lcount'></span>
  <button type='button' class='lclear' id='lclear' hidden>clear filters</button>
 </div>
 <table class='data ldocs'><thead><tr><th>Document</th><th>Country</th><th>Hazard</th>
  <th class='yr'><button type='button' id='ysort' title='Sort by year'>Year <span id='yarrow'>▼</span></button></th>
  <th>Link</th></tr></thead><tbody id='lrows'></tbody></table>
 {f"<p class='meta'>{n_int} internal document{'' if n_int == 1 else 's'} held in the database {'is' if n_int == 1 else 'are'} not listed here.</p>" if n_int else ""}
</div>
<aside id='ldrawer' class='ldrawer' role='dialog' aria-labelledby='sd-t' tabindex='-1' aria-hidden='true'></aside>
<script>window.LD = {data_js};</script>
<script>{LEARNING_JS}</script>"""
    page("pillar-learning.html", "Learning", body)


LEARNING_CSS = r"""
.lmapbox { position:relative; width:100%; overflow:hidden; border-radius:12px; border:1px solid #e6eaef;
  background:linear-gradient(180deg,#eef3f8 0%,#e9eff5 100%);
  box-shadow:0 1px 2px rgba(16,24,40,.06), 0 8px 24px -12px rgba(16,24,40,.18); }
#lmap { width:100%; height:100%; display:block; }
#lmap .cty { fill:#f7f8fa; stroke:#d3d9df; stroke-width:.45; vector-effect:non-scaling-stroke; transition:fill .2s; }
#lmap .cty.on { fill:#cfe1f3; stroke:#8fb4d9; stroke-width:.7; cursor:pointer; }
#lmap .cty.on:hover, #lmap .cty.on.sel { fill:#a9c9e8; }
#lmap .ldot { fill:#51627a; stroke:#fff; stroke-width:1.2; vector-effect:non-scaling-stroke; cursor:pointer; }
#lmap .ldot.feat { stroke-width:1.8; }
.lpane { position:absolute; inset:0; pointer-events:none; transition:opacity .2s; }
.leadersvg { position:absolute; inset:0; width:100%; height:100%; overflow:visible; }
.leader { stroke:#7c8ba1; stroke-width:1; stroke-linecap:round; }
/* a headline finding: country + premise, the figure, the sentence, the source */
.hl { display:flex; flex-direction:column; align-items:flex-start; gap:2px; text-align:left; font:inherit; color:#1a1a1a;
  background:#fff; border:1px solid #dfe5ec; border-left:4px solid var(--pc,#94a3b8); border-radius:8px; padding:7px 10px 8px;
  cursor:pointer; box-shadow:0 1px 2px rgba(15,23,42,.10), 0 6px 16px -8px rgba(15,23,42,.28); }
.hl:hover, .hl:focus-visible { border-color:#9fb6cf; border-left-color:var(--pc,#94a3b8); outline:none; box-shadow:0 2px 4px rgba(15,23,42,.14), 0 10px 22px -8px rgba(15,23,42,.36); }
.hl-k { display:flex; flex-wrap:wrap; align-items:baseline; gap:0 7px; }
.hl-c { font-size:10px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; color:#0f2540; }
.hl-p { font-size:10px; font-weight:600; letter-spacing:.02em; }
.hl-b { font-size:16.5px; font-weight:750; line-height:1.15; color:#0f2540; }
.hl-t { font-size:11px; line-height:1.32; color:#33435a; }
.hl-s { font-size:9.5px; color:#6b7a8f; }
.callout.hl { position:absolute; width:236px; pointer-events:auto; visibility:hidden; transition:opacity .2s; }
.lmapbox.tight .callout.hl { width:204px; padding:6px 8px 7px; }
.lmapbox.tight .callout .hl-b { font-size:15px; } .lmapbox.tight .callout .hl-t { font-size:10.5px; }
.lmapbox.hovering .callout.hl, .lmapbox.hovering .leader { opacity:.16; }
.lmapbox.hovering .callout.hl { pointer-events:none; }
/* the hovered / pinned country's own headlines */
.hcard { position:absolute; z-index:5; width:290px; background:#fff; border:1px solid #cfd8e3; border-radius:10px; padding:10px 12px;
  pointer-events:none; box-shadow:0 2px 6px rgba(15,23,42,.16), 0 14px 30px -10px rgba(15,23,42,.4); }
.hcard.pinned { pointer-events:auto; }
.hc-h { display:flex; align-items:baseline; gap:8px; margin-bottom:6px; }
.hc-h b { font-size:14px; color:#0f2540; } .hc-h span { font-size:11px; color:#6b7a8f; }
.hc-x { margin-left:auto; border:0; background:none; font-size:18px; line-height:1; color:#6b7a8f; cursor:pointer; padding:0 2px; }
.hc-i { width:100%; margin:0 0 6px; box-shadow:none; }
.hc-i .hl-b { font-size:15px; }
.hc-k { font-size:10px; text-transform:uppercase; letter-spacing:.05em; color:#6b7a8f; margin:0 0 4px; }
.hc-hint { font-size:10.5px; color:#6b7a8f; }
.hc-more, .lclear { border:0; background:none; padding:0; font:inherit; font-size:12px; color:#1d5aa8; cursor:pointer; }
.hc-more:hover, .lclear:hover { text-decoration:underline; }
.llegend { position:absolute; left:12px; bottom:12px; max-width:250px; background:rgba(255,255,255,.93); border:1px solid #e3e8ef;
  border-radius:8px; padding:8px 10px; font-size:11px; color:#33435a; display:flex; flex-direction:column; gap:3px; }
.llegend b { font-size:11px; color:#0f2540; }
.lg-i { display:flex; align-items:center; gap:6px; } .lg-d { width:9px; height:9px; border-radius:50%; flex:none; }
.lg-h { color:#6b7a8f; font-size:10.5px; line-height:1.3; margin-top:2px; }
/* narrow screens: the callouts do not fit on the map, the headlines are listed under it */
.hlstack { display:none; }
.lmapbox.compact .lpane, .lmapbox.compact .hcard, .lmapbox.compact .llegend { display:none; }
.lmapbox.compact + .hlstack { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:8px; margin-top:10px; }
.hlstack .hc-h, .hlstack .hc-f { grid-column:1/-1; margin:0; }
.hlstack .hl { width:auto; box-shadow:none; }
/* the repository */
.lrepo { margin-top:28px; transition:padding-right .25s; }
.lrepo h2 { margin:0 0 6px; }
.lbar { display:flex; flex-wrap:wrap; gap:8px 16px; align-items:center; margin:8px 0 10px; }
.lbar label { font-size:12.5px; color:#445; }
.lbar select { padding:5px 8px; border:1px solid #bbb; border-radius:4px; font-size:13px; max-width:260px; background:#fff; }
.lcount { font-size:12.5px; color:#667; }
table.ldocs { border:1px solid #e3e6ea; }
table.ldocs td { padding:7px 8px; font-size:13px; max-width:none; }
table.ldocs tbody tr { cursor:pointer; }
table.ldocs tbody tr.sel td { background:#e6f0fb; }
table.ldocs tbody tr:focus-visible { outline:2px solid #2a78d6; outline-offset:-2px; }
table.ldocs td.lt { width:58%; } .lt-t { font-weight:600; color:#0f2540; } .lt-p { color:#6b7a8f; font-size:12px; margin-left:8px; }
table.ldocs td.yr, table.ldocs th.yr { text-align:right; white-space:nowrap; }
table.ldocs td.lk { white-space:nowrap; }
table.ldocs td.lk a { color:#1d5aa8; text-decoration:none; } table.ldocs td.lk a:hover { text-decoration:underline; }
#ysort { border:0; background:none; font:inherit; font-weight:700; color:inherit; cursor:pointer; padding:0; }
#ysort:hover { color:#1d5aa8; } #yarrow { font-size:9px; }
.lnone { color:#777; font-style:italic; }
/* the side panel of a document */
.ldrawer { position:fixed; top:0; right:0; z-index:60; width:min(420px,100vw); height:100vh; overflow-y:auto; background:#fff;
  border-left:1px solid #d9e0e8; box-shadow:-10px 0 30px -12px rgba(15,23,42,.35); padding:18px 20px 40px;
  transform:translateX(105%); visibility:hidden; transition:transform .25s ease, visibility 0s .25s; }
.ldrawer.open { transform:none; visibility:visible; transition:transform .25s ease; }
.ldrawer:focus { outline:none; }
.sd-x { position:absolute; top:10px; right:12px; border:0; background:none; font-size:24px; line-height:1; color:#6b7a8f; cursor:pointer; }
.sd-k { font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:.05em; color:#6b7a8f; margin-right:30px; }
.ldrawer h3 { font-size:17px; line-height:1.3; margin:6px 0 4px; color:#0f2540; }
.ldrawer h4 { font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:#6b7a8f; margin:18px 0 6px; }
.ldrawer p { font-size:13.5px; line-height:1.55; margin:0; color:#23364d; }
.sd-pub { font-size:13px; color:#445; }
.sd-tags { display:flex; flex-wrap:wrap; gap:5px; margin-top:8px; }
.sd-tag { font-size:11.5px; padding:2px 9px; border-radius:10px; background:#eef2f7; color:#33435a; }
.sd-open { display:inline-block; margin-top:14px; padding:8px 14px; border-radius:6px; background:#1d5aa8; color:#fff; font-size:13px;
  font-weight:600; text-decoration:none; }
.sd-open:hover { background:#174a8a; }
.sd-nolink { margin-top:14px; font-size:12.5px; color:#777; font-style:italic; }
.sd-facts { list-style:none; margin:0; padding:0; }
.sd-facts li { font-size:13.5px; line-height:1.45; padding:7px 0 7px 12px; border-left:3px solid #2a78d6; background:#f3f8ff; margin:0 0 6px;
  border-radius:0 4px 4px 0; color:#1a1a1a; }
.sd-facts li.lead { border-left-color:#0f2540; background:#e6f0fb; }
.sd-facts li b { color:#0f2540; } .sd-facts li i { font-style:normal; font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:.04em; color:#556270; display:block; }
.sd-fw a { display:block; font-size:13px; color:#1d5aa8; margin:2px 0; }
@media (max-width:759px){ table.ldocs td.lt { width:auto; } .lt-p { display:block; margin:2px 0 0; } }
"""

LEARNING_JS = r"""
const LD = window.LD, C = LD.countries, DOCS = LD.docs, PREM = LD.prem, VB = LD.vb;
const BYID = new Map(DOCS.map(d => [d.id, d]));
const $ = id => document.getElementById(id);
const svg = $('lmap'), mapbox = $('lmapbox'), lpane = $('lpane'), leaders = $('leaders'),
      legend = $('llegend'), hcard = $('hcard'), stack = $('hlstack');
const NS = 'http://www.w3.org/2000/svg';
function esc(s){ return s==null ? '' : String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
const srcOf = d => [d.pub, d.y].filter(Boolean).join(' · ');
const pcol = h => (PREM[h.p] || {}).c || '#94a3b8';
// one finding: [country] [premise] / the figure / the sentence / its source
function hlHTML(h, country){
  const p = PREM[h.p], d = BYID.get(h.d);
  const s = d ? (srcOf(d) || (h.doc ? '' : d.t)) : '';       // h.doc: the sentence IS the document's title
  return (country || p ? `<span class='hl-k'>${country ? `<span class='hl-c'>${esc(country)}</span>` : ''}${p ? `<span class='hl-p' style='color:${p.ink}'>${esc(p.l)}</span>` : ''}</span>` : '')
    + (h.b ? `<span class='hl-b'>${esc(h.b)}</span>` : '')
    + `<span class='hl-t'>${esc(h.t)}</span>`
    + (s ? `<span class='hl-s'>${esc(s)}</span>` : '');
}
function hlButton(h, country, cls){
  return `<button type='button' class='hl ${cls}' data-doc='${h.d}' data-b='${esc(h.b || '')}' style='--pc:${pcol(h)}' title='Open the source document'>${hlHTML(h, country)}</button>`;
}

// ---------- the default callouts: each card takes the free spot nearest its country.
// Candidate spots lie on rays from the country (16 directions from its preferred side, a few
// distances). A spot costs more the more of a shaded country it hides (its own most), the
// longer its leader and the more shaded countries the leader runs over; two cards never
// overlap, and a leader should not run through another card, leader or dot. Cards are placed
// one by one, then each is re-placed against the others for a few sweeps. The order of
// placing matters, so many orders are tried (the same ones every time) and the cheapest
// layout is kept.
const labels = [];
function buildCallouts(){
  LD.featured.forEach(f => {
    const c = C[f.iso], tmp = document.createElement('div');
    tmp.innerHTML = hlButton(f, c.n, 'callout');
    const el = tmp.firstChild; lpane.appendChild(el);
    const ln = document.createElementNS(NS, 'line'); ln.setAttribute('class', 'leader'); leaders.appendChild(ln);
    labels.push({iso:f.iso, dir:c.dir, el, ln, at:null});
  });
}
const rectPx = (c, k) => ({x1:c.r[0]*k, y1:c.r[1]*k, x2:c.r[2]*k, y2:c.r[3]*k});
const area = r => (r.x2-r.x1)*(r.y2-r.y1);
function inter(a, b){ const w = Math.min(a.x2,b.x2)-Math.max(a.x1,b.x1), h = Math.min(a.y2,b.y2)-Math.max(a.y1,b.y1); return w>0 && h>0 ? w*h : 0; }
const grow = (r, p) => ({x1:r.x1-p, y1:r.y1-p, x2:r.x2+p, y2:r.y2+p});
const inside = (r, x, y) => x > r.x1 && x < r.x2 && y > r.y1 && y < r.y2;
// where a card's leader ends: the point of its edge nearest the country
const edgePt = (b, x, y) => [Math.max(b.x1, Math.min(b.x2, x)), Math.max(b.y1, Math.min(b.y2, y))];
function segCross(p1, p2, p3, p4){
  const d = (a,b,c) => (c[0]-a[0])*(b[1]-a[1]) - (b[0]-a[0])*(c[1]-a[1]);
  const d1 = d(p3,p4,p1), d2 = d(p3,p4,p2), d3 = d(p1,p2,p3), d4 = d(p1,p2,p4);
  return ((d1>0&&d2<0)||(d1<0&&d2>0)) && ((d3>0&&d4<0)||(d3<0&&d4>0)); }
function segHitsBox(p, q, b){
  if(inside(b, p[0], p[1]) || inside(b, q[0], q[1])) return true;
  const c = [[b.x1,b.y1],[b.x2,b.y1],[b.x2,b.y2],[b.x1,b.y2]];
  for(let i=0;i<4;i++) if(segCross(p, q, c[i], c[(i+1)%4])) return true;
  return false; }
// every spot a card can take, with the part of its cost that does not depend on the other cards
function spots(Lb, W, H, k, shaded, keepOut){
  const rc = rectPx(C[Lb.iso], k), mx = (rc.x1+rc.x2)/2, my = (rc.y1+rc.y2)/2, hx = (rc.x2-rc.x1)/2, hy = (rc.y2-rc.y1)/2;
  const a0 = Math.atan2(Lb.dir[1], Lb.dir[0]), p = Lb.p, out = [];
  for(let i=0; i<16; i++){
    const a = a0 + i*Math.PI/8, ux = Math.cos(a), uy = Math.sin(a);
    const reach = Math.abs(ux)*hx + Math.abs(uy)*hy + 6 + Math.abs(ux)*Lb.w/2 + Math.abs(uy)*Lb.h/2;
    for(const far of [0, 30, 70, 120, 180, 250]){
      const cx = Math.max(4+Lb.w/2, Math.min(W-4-Lb.w/2, mx + ux*(reach+far))), cy = Math.max(4+Lb.h/2, Math.min(H-4-Lb.h/2, my + uy*(reach+far)));
      const b = {x1:cx-Lb.w/2, y1:cy-Lb.h/2, x2:cx+Lb.w/2, y2:cy+Lb.h/2}, e = edgePt(b, p[0], p[1]);
      let cost = Math.min(i, 16-i) * .08 + Math.hypot(e[0]-p[0], e[1]-p[1]) / 70;     // its preferred side; a short leader
      for(const s of shaded){
        cost += (s.iso === Lb.iso ? 6 : s.feat ? 4 : 2.5) * inter(b, s.r) / area(s.r);
        if(s.feat && inside(b, s.x, s.y)) cost += 10;                               // never on a default callout's dot
        if(s.iso !== Lb.iso && segHitsBox(p, e, s.r)) cost += .8;
      }
      for(const r of keepOut) if(inter(b, r)) cost += 30;
      out.push({b, e, g:grow(b, 8), cost});
    }
  }
  return out;
}
// what a spot of one card costs against another card where it now stands
function pairCost(Lb, c, o){
  const ov = inter(c.g, o.at.b); let cost = ov ? 1000 + ov/50 : 0;
  if(segHitsBox(Lb.p, c.e, o.at.b)) cost += 8;
  if(segHitsBox(o.p, o.at.e, c.b)) cost += 8;
  if(segCross(Lb.p, c.e, o.p, o.at.e)) cost += 6;
  if(segHitsBox(Lb.p, c.e, o.dot)) cost += 3;
  return cost;
}
const costOf = (Lb, c) => labels.reduce((s, o) => o === Lb || !o.at ? s : s + pairCost(Lb, c, o), c.cost);
function seeded(a){ return () => { a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
let compact = false;
function runLayout(){
  const r = svg.getBoundingClientRect(), W = r.width, H = r.height;
  if(!W) return;
  const k = W / VB.w, was = compact;
  compact = W < 1040;                                     // six cards no longer fit on the map: list them under it
  mapbox.classList.toggle('compact', compact); mapbox.classList.toggle('tight', W < 1250);
  if(compact !== was || !stack.dataset.init){ stack.dataset.init = '1'; unpin(); }
  if(compact || !labels.length) return;
  const feat = new Set(labels.map(Lb => Lb.iso));
  const shaded = Object.entries(C).map(([iso, c]) => ({iso, feat:feat.has(iso), r:rectPx(c, k), x:c.x*k, y:c.y*k}));
  const lr = legend.getBoundingClientRect(), mr = mapbox.getBoundingClientRect();
  const keepOut = lr.width ? [{x1:lr.left-mr.left-6, y1:lr.top-mr.top-6, x2:lr.right-mr.left+6, y2:lr.bottom-mr.top+6}] : [];
  labels.forEach(Lb => { const c = C[Lb.iso]; Lb.p = [c.x*k, c.y*k]; Lb.dot = grow({x1:Lb.p[0], y1:Lb.p[1], x2:Lb.p[0], y2:Lb.p[1]}, 7);
    Lb.w = Lb.el.offsetWidth; Lb.h = Lb.el.offsetHeight; });
  labels.forEach(Lb => { Lb.spots = spots(Lb, W, H, k, shaded, keepOut); });
  const rnd = seeded(7); let best = null;
  for(let t=0; t<50; t++){
    const order = labels.slice();
    if(t) for(let i=order.length-1; i>0; i--){ const j = Math.floor(rnd()*(i+1)); [order[i], order[j]] = [order[j], order[i]]; }
    labels.forEach(Lb => { Lb.at = null; });
    for(let sweep=0; sweep<3; sweep++) order.forEach(Lb => {
      let pick = null, low = Infinity;
      for(const c of Lb.spots){ const v = costOf(Lb, c); if(v < low){ low = v; pick = c; } }
      Lb.at = pick; });
    const total = labels.reduce((s, Lb) => s + costOf(Lb, Lb.at), 0);
    if(!best || total < best.total) best = {total, at:labels.map(Lb => Lb.at)};
  }
  labels.forEach((Lb, i) => {
    const {b, e} = Lb.at = best.at[i];
    Lb.el.style.visibility = 'visible'; Lb.el.style.left = b.x1+'px'; Lb.el.style.top = b.y1+'px';
    Lb.ln.setAttribute('x1', Lb.p[0]); Lb.ln.setAttribute('y1', Lb.p[1]); Lb.ln.setAttribute('x2', e[0]); Lb.ln.setAttribute('y2', e[1]);
  });
}

// ---------- a country's own headlines: on hover (a preview), on click (kept open)
let pinned = null;
function countryHTML(iso, pin){
  const c = C[iso], nd = c.nd;
  return `<div class='hc-h'><b>${esc(c.n)}</b><span>${nd ? `${nd} document${nd>1?'s':''}` : 'no country document'}</span>`
    + (pin ? `<button type='button' class='hc-x' aria-label='Close'>×</button>` : '') + `</div>`
    + (c.h[0] && c.h[0].doc ? `<div class='hc-k'>No headline figure yet · newest documents</div>` : '')
    + c.h.map(h => hlButton(h, null, 'hc-i')).join('')
    + `<div class='hc-f'>` + (pin ? (nd ? `<button type='button' class='hc-more' data-iso='${iso}'>Show ${nd>1?`its ${nd} documents`:'its document'} in the list ↓</button>` : '')
                                  : `<span class='hc-hint'>Click the country to keep this open</span>`) + `</div>`;
}
function placeCard(iso){
  const r = svg.getBoundingClientRect(), k = r.width / VB.w, c = C[iso], rc = rectPx(c, k);
  const w = hcard.offsetWidth, h = hcard.offsetHeight, mx = (rc.x1+rc.x2)/2, my = (rc.y1+rc.y2)/2;
  const hx = (rc.x2-rc.x1)/2, hy = (rc.y2-rc.y1)/2, [dx, dy] = c.dir;
  // the country's preferred side first, then the others: the first that leaves the country clear
  let best = null;
  for(const [vx, vy] of [[dx,dy], [-dx,dy], [dx,-dy], [-dx,-dy], [1,0], [-1,0], [0,1], [0,-1]]){
    const dl = Math.hypot(vx, vy) || 1, ux = vx/dl, uy = vy/dl;
    const reach = Math.abs(ux)*hx + Math.abs(uy)*hy + 12 + Math.abs(ux)*w/2 + Math.abs(uy)*h/2;
    const cx = Math.max(6+w/2, Math.min(r.width-6-w/2, mx + ux*reach)), cy = Math.max(6+h/2, Math.min(r.height-6-h/2, my + uy*reach));
    const ox = Math.min(cx+w/2, rc.x2) - Math.max(cx-w/2, rc.x1), oy = Math.min(cy+h/2, rc.y2) - Math.max(cy-h/2, rc.y1);
    const over = ox > 0 && oy > 0 ? ox*oy : 0;
    if(!best || over < best.over) best = {cx, cy, over};
    if(!over) break;
  }
  hcard.style.left = (best.cx-w/2)+'px'; hcard.style.top = (best.cy-h/2)+'px';
}
function mark(iso){ svg.querySelectorAll('.cty.sel').forEach(e => e.classList.remove('sel'));
  if(iso){ const p = svg.querySelector(`.cty[data-iso='${iso}']`); if(p) p.classList.add('sel'); } }
function showCountry(iso, pin){
  if(!C[iso]) return;
  if(compact){ if(!pin) return;
    stack.innerHTML = countryHTML(iso, true) + `<div class='hc-f'><button type='button' class='hc-more' data-back='1'>← The headline findings</button></div>`;
    mark(iso); return; }
  hcard.innerHTML = countryHTML(iso, pin); hcard.classList.toggle('pinned', !!pin); hcard.hidden = false;
  mapbox.classList.add('hovering'); mark(iso); placeCard(iso);
}
function hideCountry(){ hcard.hidden = true; mapbox.classList.remove('hovering'); mark(null); }
function unpin(){ pinned = null; hideCountry();
  stack.innerHTML = LD.featured.map(f => hlButton(f, C[f.iso].n, '')).join(''); }
const isoOf = t => (t && t.dataset && t.dataset.iso && C[t.dataset.iso] && (t.classList.contains('on') || t.classList.contains('ldot'))) ? t.dataset.iso : null;
svg.addEventListener('mouseover', e => { const iso = isoOf(e.target); if(iso && !pinned) showCountry(iso, false); });
svg.addEventListener('mouseout', e => { if(!pinned && isoOf(e.target) && !isoOf(e.relatedTarget)) hideCountry(); });
svg.addEventListener('click', e => { const iso = isoOf(e.target);
  if(iso && iso !== pinned){ pinned = iso; showCountry(iso, true); } else unpin(); });
// a headline opens its source document; the pinned card can also filter the list
function onHeadlineClick(e){
  const b = e.target.closest('button'); if(!b) return;
  if(b.dataset.doc) openDoc(+b.dataset.doc, b.dataset.b);
  else if(b.dataset.iso) filterTo(b.dataset.iso);
  else unpin();
}
[lpane, hcard, stack].forEach(el => el.addEventListener('click', onHeadlineClick));

// ---------- the repository: filter by country and hazard, sort by year, a row opens the panel
const fC = $('f-c'), fH = $('f-h'), rows = $('lrows'), drawer = $('ldrawer'), repo = $('lrepo');
const state = {desc:true, sel:null};
function matches(d){
  const c = fC.value, h = fH.value;
  if(c === '_global' ? d.iso.length : c && !d.iso.includes(c)) return false;
  if(h === '_none' ? d.hz : h && d.hz !== h) return false;
  return true;
}
function renderTable(){
  const list = DOCS.filter(matches).sort((a, b) => (a.y == null) - (b.y == null)       // no year: last, either way
    || (state.desc ? b.y - a.y : a.y - b.y) || a.t.localeCompare(b.t));
  rows.innerHTML = list.map(d => `<tr data-id='${d.id}' tabindex='0'>`
    + `<td class='lt'><span class='lt-t'>${esc(d.t)}</span>${d.pub ? `<span class='lt-p'>${esc(d.pub)}</span>` : ''}</td>`
    + `<td>${d.cn.length ? esc(d.cn.join(', ')) : 'Global'}</td><td>${d.hz ? esc(LD.hazard[d.hz] || d.hz) : '—'}</td>`
    + `<td class='yr'>${d.y == null ? '—' : d.y}</td>`
    + `<td class='lk'>${d.u ? `<a href='${esc(d.u)}' target='_blank' rel='noopener'>open ↗</a>` : `<span class='lnone' title='No public link recorded'>none</span>`}</td></tr>`).join('')
    || `<tr><td colspan='5' class='lnone'>No document matches these filters.</td></tr>`;
  const filtered = !!(fC.value || fH.value);
  $('lcount').textContent = filtered ? `${list.length} of ${DOCS.length} documents` : `${DOCS.length} documents`;
  $('lclear').hidden = !filtered; $('yarrow').textContent = state.desc ? '▼' : '▲';
  markRow();
}
function markRow(){ rows.querySelectorAll('tr.sel').forEach(tr => tr.classList.remove('sel'));
  const tr = state.sel == null ? null : rows.querySelector(`tr[data-id='${state.sel}']`); if(tr) tr.classList.add('sel'); }
function filterTo(iso){ fC.value = iso; fH.value = ''; renderTable(); repo.scrollIntoView({behavior:'smooth', block:'start'}); }
fC.addEventListener('change', renderTable); fH.addEventListener('change', renderTable);
$('lclear').addEventListener('click', () => { fC.value = ''; fH.value = ''; renderTable(); });
$('ysort').addEventListener('click', () => { state.desc = !state.desc; renderTable(); });
rows.addEventListener('click', e => { if(e.target.closest('a')) return; const tr = e.target.closest('tr[data-id]'); if(tr) openDoc(+tr.dataset.id); });
rows.addEventListener('keydown', e => { if(e.key !== 'Enter' && e.key !== ' ') return; const tr = e.target.closest('tr[data-id]');
  if(tr && e.target === tr){ e.preventDefault(); openDoc(+tr.dataset.id); } });

// ---------- the side panel of one document: link, key facts, summary
function facts(d, lead){
  // the finding the panel was opened from comes first
  const out = [...d.hl].sort((a, b) => (b.b === lead) - (a.b === lead))
    .map(h => `<li${h.b === lead ? " class='lead'" : ''}><i>${esc(h.n)}</i><b>${esc(h.b)}.</b> ${esc(h.t)}</li>`);
  // the document's key statistic, one fact per clause
  if(d.ks) d.ks.split(/;\s+/).forEach(s => { s = s.trim().replace(/\.$/, ''); if(s) out.push(`<li>${esc(s.charAt(0).toUpperCase() + s.slice(1))}.</li>`); });
  return out.join('');
}
let opener = null;
// keep the list clear of the panel where the two would overlap (wide panel, narrow window)
function padForDrawer(){
  const open = drawer.classList.contains('open'); repo.style.paddingRight = '';
  if(!open || window.innerWidth < 900) return;
  const over = repo.getBoundingClientRect().right - (window.innerWidth - drawer.offsetWidth) + 14;
  if(over > 0) repo.style.paddingRight = over + 'px';
}
function openDoc(id, lead){
  const d = BYID.get(id); if(!d) return;
  if(!drawer.classList.contains('open')) opener = document.activeElement;
  state.sel = id;
  const f = facts(d, lead), tags = [...(d.cn.length ? d.cn : ['Global']), ...(d.hz ? [LD.hazard[d.hz] || d.hz] : [])];
  drawer.innerHTML = `<button type='button' class='sd-x' aria-label='Close'>×</button>`
    + `<div class='sd-k'>${esc(d.ty)}${d.y ? ' · ' + d.y : ''}</div><h3 id='sd-t'>${esc(d.t)}</h3>`
    + (d.pub ? `<div class='sd-pub'>${esc(d.pub)}</div>` : '')
    + `<div class='sd-tags'>${tags.map(t => `<span class='sd-tag'>${esc(t)}</span>`).join('')}</div>`
    + (d.u ? `<a class='sd-open' href='${esc(d.u)}' target='_blank' rel='noopener'>Open the document ↗</a>` : `<div class='sd-nolink'>No public link is recorded for this document.</div>`)
    + (f ? `<h4>Key facts</h4><ul class='sd-facts'>${f}</ul>` : '')
    + (d.s ? `<h4>Summary</h4><p>${esc(d.s)}</p>` : '')
    + (d.pr.length ? `<h4>Evidence on</h4><div class='sd-tags'>${d.pr.map(p => `<span class='sd-tag'>${esc(PREM[p].l)}</span>`).join('')}</div>` : '')
    + (d.fw.length ? `<h4>Framework</h4><div class='sd-fw'>${d.fw.map(([href, label]) => `<a href='${esc(href)}'>${esc(label)} →</a>`).join('')}</div>` : '');
  drawer.classList.add('open'); drawer.setAttribute('aria-hidden', 'false'); drawer.scrollTop = 0;
  markRow(); padForDrawer(); drawer.focus({preventScroll:true});
}
function closeDoc(){
  if(!drawer.classList.contains('open')) return;
  drawer.classList.remove('open'); drawer.setAttribute('aria-hidden', 'true'); state.sel = null;
  markRow(); padForDrawer();
  if(opener && document.contains(opener)) opener.focus({preventScroll:true}); opener = null;
}
drawer.addEventListener('click', e => { if(e.target.closest('.sd-x')) closeDoc(); });
document.addEventListener('keydown', e => { if(e.key !== 'Escape') return;
  if(drawer.classList.contains('open')) closeDoc(); else if(pinned) unpin(); });

// relayout whenever the map's rendered size changes: the callouts are positioned in CSS px
// (a hidden tab gets no resize observations, hence the two extra listeners)
let rto = null, laidW = 0;
function relayout(){ clearTimeout(rto); rto = setTimeout(() => {
  const w = svg.getBoundingClientRect().width; padForDrawer();
  if(Math.abs(w - laidW) < 1) return;
  laidW = w; runLayout(); if(pinned && !compact) placeCard(pinned); }, 120); }
new ResizeObserver(relayout).observe(svg);
window.addEventListener('resize', relayout);
document.addEventListener('visibilitychange', relayout);
buildCallouts(); renderTable(); runLayout(); laidW = svg.getBoundingClientRect().width;
"""
