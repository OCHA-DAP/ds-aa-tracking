"""The open, machine-readable layer of the site: what an LLM (or any fetch-based tool) reads
beside the pages, as Markdown and tables.

Written by write_site() at the top of site_build/, never encrypted, regenerated on every build (so
the nightly publish keeps it current). It carries ONLY the data of the pages the open site serves
without a password (build_site.OPEN_PAGES, passed in as `live`): every file has a home page (HOME),
and a file whose home is not open is not written at all (owner, 2026-11-02: "only configure it to
put the data live for the one page that is actually going live ... the map one. we will put the
other data live later"). Opening a page (adding it to OPEN_PAGES) puts its data live with it.

The map (index.html), open since 2026-11-01:
- llms.txt                the index: what the site is, the caveat, the counting rules, every file,
                          the dictionary of the map's data, and the result of the figure check
- aa-map.md               the map in text: its headline figures as it opens, each with the map's own
                          note on it (quoted, so a change to a note follows), its frameworks
- aa-map-data.json        the open map's own data, as its page embeds it (without the drawing):
                          whatever the map shows is in it, without this module knowing of it
- aa-<name>.json / .csv   frameworks, versions, activations, prearranged-funding, cofinancing,
                          funds: the frameworks the open map shows, with its figures. Every row
                          carries every column; the money rows carry the map's layer (current /
                          retired / non-framework, dashboards._layer_of)
- robots.txt, sitemap.xml (the open files and the open pages)
The figures come from the open map's own data (landing.OPEN_MAP): its tiles, its people reached or
targeted, and its withholding (a people-covered figure from an unpublished framework document is
left out, landing.withheld_on_open_map; the build stops if a live file still carries one).

Held until their pages open (the code stays, nothing is written): aa-portfolio.md and
aa-funding-annual (Financing), aa-plan-split and aa-partners (Activities), aa-learning (Learning),
aa-trigger-timelines, aa-trigger-windows and aa-windows (Model), aa-simulated-activations
(historical activations), and with the framework pages fw-<iso3>-<hazard>.md, the structured reads
of the framework documents doc-<kb_framework>-<version>.md, their full texts pdf-<sha256>.txt and
llms-full.txt.

Kept in step with the map, as the data and the site change (owner, 2026-11-02: "make sure the
LLM stuff is always up to date as I make edits to the site, but even more importantly that it
stays up to date as the data itself is updated"): the files are written in the same build as the
map, from the map's own data, on every publish (nightly, on each push to main, from the admin's
Publish changes); figure_check.open_layer() recomputes every headline figure and each framework's
figures from the files as written and compares them with the open map's (a mismatch is a warning
in the publish run, and llms.txt says so); _map_field_alarm() warns when the map's data gains a
field open_map_fields.py does not describe, or the map a tile aa-map.md does not state; and the
build warns when a page is opened whose data no file carries.

A reader that knows nothing about the site has to be able to use it (tested 2026-10-09 with
readers given only the URL): the figures agree across files to the dollar, a coded window name
carries the document's name for it, and no link is dead (the build stops on a link or a file name
that this build did not write).

Never published, whatever is open: focal points (people), the version pages' working notes
(frontmatter `extra`, raw extracts, QA notes, the sources and open-questions sections of the page
body), the version records' provenance notes, activation comments, partner evidence, documents
registered as private, internal learning documents (already filtered at the source).
"""

import json
import os
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

SITE_URL = os.environ.get("SITE_URL", "https://ocha-dap.github.io/ds-aa-tracking/").rstrip("/") + "/"

CAVEAT = ("OCHA internal product under development, subject to change without warning. "
          "The figures may be incorrect and should not be used.")

# the version-page fields the public framework page shows (the rest of the frontmatter is
# working material and never leaves the database)
FM_KEYS = ("geographic_scope", "admin_level", "trigger_facets", "data_sources",
           "implementing_agencies", "target_people", "all_in", "framework_doc",
           "framework_doc_date", "prearranged_funding_usd", "cofinancing_usd",
           "cofinancing_sources")

# the page-body sections that are working material (what was read, what is unresolved)
DROP_SECTIONS = ("Sources & repo completeness", "Open questions / known issues", "Open questions")
PDF_CACHE = Path(os.environ.get("FRAMEWORK_DOC_CACHE", Path(__file__).parents[1] / "data" / "framework_documents"))

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

def _rules(on):
    """The counting rules, naming only the files written (`on`: HOME key -> written)."""
    funding_annual = " and aa-funding-annual" if on("funding-annual") else ""
    sums = [x for x in ("its sum over the frameworks on the map's current-frameworks layer is the map's "
                        "Pre-arranged tile (aa-map.md)" if on("map") else "",
                        "its sum is the portfolio page's headline (aa-portfolio.md)" if on("portfolio") else "") if x]
    rp_windows = (" A trigger window has two return periods and they can differ: the one its document states "
                  "(aa-trigger-windows, free text) and the one from the historical simulation (backtest) of the "
                  "trigger (aa-windows, `return_period` in years, with the activation probability)."
                  if on("trigger-windows") and on("windows") else "")
    return f"""\
Counting rules (an LLM summing these files without them gets wrong totals):

- Pre-arranged funding is a STOCK: the envelope in place for a framework in a given year.
  Never add it across years, and never add it to released money. "Pre-arranged in 2026" is
  the sum over frameworks of the 2026 rows only (aa-prearranged-funding{funding_annual}). The
  current year's figure comes from the framework records (source `framework-record`): for each
  live framework, the envelope of its most recent version that has one, all funds.
  `prearranged_usd` in aa-frameworks is that same figure per framework{"; " + "; ".join(sums) if sums else ""}.
  Past years keep the reported series. It is not reduced by what activations released during the year.
- Two activations a year: a framework version whose document allows the trigger to activate
  twice in one season (`activations_per_year` = 2, some tropical-cyclone frameworks) has its
  CERF envelope COUNTED TWICE in every pre-arranged figure here, as on the pages. The amounts
  are already multiplied: never multiply again.
- Released money is what activations drew: the `funding` rows of aa-activations, net of any
  money refunded after an activation stopped (`refund_usd`). Two kinds: framework activations
  (`event_type` `framework_aa`) and non-framework allocations (`adhoc_aa`: anticipatory money
  allocated without a framework; they have no version and no window, and nothing is
  pre-arranged for them). Early action allocations are not anticipatory action and are not in
  these files.
- Layers, as on the site: every money row carries `layer` = `current` (a framework that is
  active, being updated or in development today), `retired` (a retired framework, in the
  years it was live) or `non_framework`. The map opens with the current-frameworks layer on
  and the current year: its stock figures (frameworks, pre-arranged, co-financing, people
  covered) count the frameworks on that layer (`map_layers` contains `framework` in
  aa-frameworks); its flow figures (activations, money released, people reached or targeted)
  count the year's framework activations of the frameworks on that layer; those of frameworks
  since retired count when the retired layer is on (the map's "All years, to today" switches it
  on), and non-framework allocations only when that layer is on. Add up the layers the question
  needs, and say which.
- A framework is one (country, hazard) pair. Regional frameworks do not exist: the Central
  America Dry Corridor is four national frameworks (El Salvador, Guatemala, Honduras and the
  retired Nicaragua), even where a document title calls it regional or one document serves
  several of them. One exception: a pair can also hold an EARLIER framework that a distinct
  new one replaced rather than revised (Somalia drought: the 2019-2021 food security
  framework, replaced by the 2026 one). Its versions, activations and money carry
  `replaced_framework` = true and the `retired` layer: they are a retired framework's, never
  the current framework's.
- Money comes from CERF and the Country and Regional Funds (the country-based pooled funds
  and the regional humanitarian funds), together the OCHA-managed funds. Pooled-fund
  pre-arranged money comes from the OneGMS allocation mirror (source `onegms-mirror`);
  hand-tracked rows are kept only for country-years the mirror does not cover, so the same
  money is never counted twice. Co-financing (money from outside the OCHA-managed funds,
  aa-cofinancing) is a separate stock: never add it to the pre-arranged figures.
- A framework version is one framework document: `endorsed`, or `development` while it is
  still being written. `lifecycle` says where the framework stands today: active, updating
  (being updated), development, pipeline or retired (defined under Vocabulary). Count
  frameworks by `lifecycle`, not by `status`.
- Return periods.{rp_windows} For a whole framework version, `return_period_years` (aa-frameworks,
  aa-versions) is the figure the map's table shows: the one the document states where there is
  one, otherwise the backtest's (`return_period_basis` says which; both figures are given).
- People reached or targeted (the map's tile), per allocation of aa-activations' `funding` rows,
  each allocation once (`allocation_shared` marks a row whose allocation is counted on an earlier
  activation): a CERF allocation counts the people CERF reports reached (`people_reached`), or,
  while there is no report, the people it plans to reach or the activation targets
  (`people_planned`); a Country or Regional Fund allocation counts the people it targets
  (`people_planned`: its results are not available yet). It is not people covered (what the
  frameworks cover now).
- People covered (`people_covered`): a figure taken from a framework document that is not
  published is left out of these files, as it is of the open map.
"""

# the map layer a money row belongs to (dashboards._layer_of), in words
LAYER = {"c": "current", "r": "retired", "a": "non_framework"}

# the page whose data each file is (build_site page names; "fw": the framework pages). A file is
# written only while one of its pages is open (build_site.OPEN_PAGES): the data of a page goes live
# with the page
MAP = "index.html"
HOME = {
    "map": (MAP,),                                         # aa-map.md
    "map-data": (MAP,),                                    # aa-map-data.json: the map's own data
    "frameworks": (MAP, "fw"), "versions": (MAP, "fw"), "activations": (MAP, "fw"),
    "prearranged-funding": (MAP, "dash-funding.html"), "cofinancing": (MAP, "dash-funding.html"),
    "funds": (MAP, "dash-funding.html"),
    "portfolio": ("dash-funding.html",), "funding-annual": ("dash-funding.html",),
    "plan-split": ("pillar-plan.html",), "partners": ("fw", "pillar-plan.html"),
    "learning": ("pillar-learning.html",),
    "trigger-timelines": ("pillar-model.html",),
    "trigger-windows": ("fw", "pillar-model.html"), "windows": ("fw", "pillar-model.html"),
    "simulated-activations": ("pillar-history.html",),
    "documents": ("fw",),             # fw-*.md, doc-*.md, pdf-*.txt, llms-full.txt
}


def _live(name, live):
    """Is file `name` (a HOME key) written, with the pages of `live` open?"""
    return any(h in live or (h == "fw" and any(n.startswith("fw-") for n in live)) for h in HOME[name])


# ---------------------------------------------------------------------- helpers
def _slug_pairs(public):
    """(ISO3, hazard) of every public framework page."""
    out = {}
    for n in public:
        m = re.match(r"fw-([a-z]{3})-(.+)\.html$", n)
        if m:
            out[(m.group(1).upper(), m.group(2))] = n
    return out


def _cell(v):
    """A JSON-safe cell: NaN/NaT -> None, dates -> ISO text, numpy -> python."""
    if v is None:
        return None
    if isinstance(v, (list, dict)):
        return v
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.isoformat() if (v.hour or v.minute) else v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if hasattr(v, "item"):          # numpy scalar
        v = v.item()
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def _records(df, cols=None):
    df = df if cols is None else df[[c for c in cols if c in df.columns]]
    return [{k: _cell(v) for k, v in r.items()} for r in df.to_dict(orient="records")]


def _csv_cell(v):
    """A CSV cell: a nested value as JSON (never a Python repr), a plain list joined with '; '."""
    if isinstance(v, dict) or (isinstance(v, list) and any(isinstance(x, (dict, list)) for x in v)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return "; ".join(map(str, v))
    return "" if v is None else v


def _m(v):
    """USD to the dollar ($6,002,640): a reader that quotes a page must get the table's figure."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return f"${float(v):,.0f}"


def _md_table(rows, cols, fmt=None):
    """A Markdown table from dict rows; `fmt` maps a column to a formatter."""
    if not rows:
        return "_none recorded_\n"
    fmt = fmt or {}
    def esc(v):
        if isinstance(v, list):
            v = ", ".join(map(str, v))
        return str(v).replace("|", "\\|").replace("\n", " ")
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(
            esc(fmt[c](r.get(c)) if c in fmt else ("" if r.get(c) is None else r.get(c)))
            for c in cols) + " |")
    return "\n".join(out) + "\n"


def _version_facts(vpage, kb_fw, version):
    """The public fields of one version page, flattened for a row or a Markdown block."""
    if not kb_fw or version is None:
        return {}, []
    hit = vpage[(vpage["kb_framework"] == kb_fw) & (vpage["version"].astype(str) == str(version))]
    if not len(hit):
        return {}, []
    fm = hit.iloc[0]["frontmatter"] or {}
    out = {k: fm.get(k) for k in FM_KEYS if fm.get(k) not in (None, "", [], {})}
    tf = out.pop("trigger_facets", None) or {}
    if tf.get("basis"):
        out["trigger_basis"] = tf["basis"]
    if tf.get("indicators"):
        out["trigger_indicators"] = list(map(str, tf["indicators"]))
    mp = fm.get("monitoring_period") or {}
    months = [m for m in (mp.get("months") or []) if isinstance(m, int) and 1 <= m <= 12]
    if months:
        out["monitoring_months"] = months
    trig = hit.iloc[0]["triggers"] or []
    return out, trig


# the documents' trigger tables name the same things differently: one name per column here,
# anything else a document's table carries goes to `other`
TRIG_KEYS = {"basis": "basis", "window": "window", "window (pdf → code)": "window",
             "indicator": "indicator", "threshold": "threshold",
             "lead time": "lead_time", "lead time / months": "lead_time",
             "return period": "return_period",
             "releases": "releases", "releases (planned)": "releases", "releases (usd)": "releases_usd"}
TRIG_COLS = ("window", "basis", "indicator", "threshold", "lead_time", "return_period", "releases", "releases_usd")


def _trigger_row(t):
    row = dict.fromkeys(TRIG_COLS)
    other = {}
    for k, v in t.items():
        if v in (None, ""):
            continue
        col = TRIG_KEYS.get(str(k).strip().lower())
        if col and row[col] is None:
            row[col] = v
        else:
            other[str(k)] = v
    row["other"] = other or None
    return row


def _window_label(t):
    return str(t.get("window") or t.get("window (pdf → code)") or t.get("trigger") or "").strip()


def _document_windows(name, trig, idx):
    """The document's window label(s) a recorded window stands for, from the page model's
    pairing `idx` — kept only where it is safe to state as a fact: the same name, a single
    row, or several rows that are that window's own sub-rows ("Window 2" -> "Window 2
    (forecast path)", "Window 2 (obs path)"). A loose match that also catches a neighbour
    ("Déclencheur I" ~ "Déclencheur II") gives nothing."""
    norm = lambda x: re.sub(r"\s+", " ", str(x or "")).strip().lower()      # noqa: E731
    labels = [_window_label(t) for t in trig]
    n = norm(name)
    same = [lab for lab in labels if lab and norm(lab) == n]
    if same:
        return same[:1]
    got = list(dict.fromkeys(labels[i] for i in idx if labels[i]))
    if len(got) <= 1:
        return got
    sub = all(norm(lab).startswith(n) and not norm(lab)[len(n):len(n) + 1].isalnum() for lab in got)
    return got if sub else []


def _read(e, sql, cols):
    """A table that may not exist in an older snapshot: an empty frame, never a crash."""
    try:
        return pd.read_sql(sql, e)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::open layer: {exc.__class__.__name__} reading {sql.split('FROM')[1].split()[0]}")
        return pd.DataFrame(columns=cols)


RP_NONE = {"return_period_years": None, "return_period_basis": None,
           "return_period_stated_years": None, "return_period_backtest_years": None}


def _return_periods(e):
    """(country, hazard, version) -> a version's OVERALL return period (any window activating in a
    year) as the map's table shows it (landing._rp_fields, in its order RP_PREFER: the figure the
    document states, else the backtest's), with both figures. A version label that is a prefix of
    the other ('2026' / '2026-04-17') matches when it is the only one, as landing.rp_of does."""
    import landing

    cols = ["country_iso3", "hazard", "version", "rp"]
    bt = _read(e, "SELECT country_iso3, hazard, version::text AS version, overall_return_period AS rp "
                  "FROM aa.v_framework_performance WHERE overall_return_period IS NOT NULL", cols)
    st = _read(e, "SELECT country_iso3, hazard, version::text AS version, overall_rp_reported AS rp "
                  "FROM aa.version_performance_reported WHERE overall_rp_reported IS NOT NULL", cols)
    def of(df, c, h, v):
        x = df[(df["country_iso3"] == c) & (df["hazard"] == h)]
        y = x[x["version"] == v]
        if not len(y):
            y = x[[a.startswith(v) or v.startswith(a) for a in x["version"]]]
            if len(y) != 1:
                return None
        return float(y["rp"].iloc[0]) if len(y) else None
    r2 = lambda x: None if x is None else round(x, 2)      # noqa: E731
    words = {"stated": "stated in the framework", "backtest": "historical simulation"}
    out = {}
    ver = pd.read_sql("SELECT country_iso3, hazard, version::text AS version FROM aa.framework_version", e)
    for c, h, v in set(zip(ver["country_iso3"], ver["hazard"], ver["version"])):
        f = landing._rp_fields(of(bt, c, h, v), of(st, c, h, v))
        if f["rp"] is not None:
            out[(c, h, v)] = {"return_period_years": r2(f["rp"]), "return_period_basis": words[f["rp_src"]],
                              "return_period_stated_years": r2(f["rp_st"]),
                              "return_period_backtest_years": r2(f["rp_bt"])}
    return out


# ---------------------------------------------------------------------- the build
def build(d, e, live, out, snapshot_at):
    """Write the layer into `out`: the files whose page is in `live` (the pages the open site
    serves, build_site.OPEN_PAGES), nothing else. Return the set of file names written."""
    import dashboards
    import landing

    stamp = date.today().isoformat()
    on = lambda name: _live(name, live)          # noqa: E731
    pages = _slug_pairs(live)                   # (iso3, hazard) -> fw-xxx.html, the open framework pages
    written = set()
    files = []                                   # (name, description, columns) for llms.txt

    # the open map's own data (landing.build_landing): its frameworks, its funding rows with people
    # reached or targeted, its headline figures, and the figures it withholds
    om = landing.OPEN_MAP
    if on("map") and not om.get("countries"):
        raise SystemExit("FATAL: the open layer needs the open map's data (landing.OPEN_MAP is empty)")
    # a people-covered figure taken from an unpublished framework document stays off the open
    # files as it stays off the open map (fail-closed: withheld_on_open_map stops the build if it
    # cannot tell)
    withheld = om["withheld"] if "withheld" in om else landing.withheld_on_open_map(e)
    gone_v = {pair: {v for _, v in xs} for pair, xs in withheld.items()}
    def gone(c, h, v):
        return v is not None and pd.notna(v) and int(v) in gone_v.get((c, h), set())
    map_fw = {(iso, f["hazard"]): f for iso, cd in (om.get("countries") or {}).items() for f in cd["fws"]}
    in_scope = lambda c, h: (c, h) in map_fw or (c, h) in pages      # noqa: E731
    # countries whose money rows go out: the open map's, until the Financing page opens
    scope_ctry = None if "dash-funding.html" in live else {c for c, _ in map_fw} | {c for c, _ in pages}
    map_fund = {}       # the map's funding rows, by activation and allocation
    for (iso, h), f in map_fw.items():
        for a in f["activations"]:
            for x in a["funding"]:
                map_fund.setdefault((iso, h, str(a["date"]), a["type"], a["window"] or "", x["fund"],
                                     x["code"] or ""), []).append(x)

    def write_table(name, rows, desc):
        if not on(name):
            return rows
        cols = []
        for r in rows:
            for k in r:
                if k not in cols:
                    cols.append(k)
        rows = [{c: r.get(c) for c in cols} for r in rows]      # every row carries every column
        obj = {"title": name, "description": desc, "generated": stamp,
               "snapshot_at": snapshot_at or None, "caveat": CAVEAT, "site": SITE_URL,
               "n": len(rows), "columns": cols, "rows": rows}
        (out / f"aa-{name}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=None, default=str))
        pd.DataFrame([{c: _csv_cell(r.get(c)) for c in cols} for r in rows], columns=cols) \
            .to_csv(out / f"aa-{name}.csv", index=False)
        written.update({f"aa-{name}.json", f"aa-{name}.csv"})
        files.append((name, desc, cols))
        return rows

    cur = d["current"].sort_values(["country_name", "hazard"])
    fvm = d["fv_meta"]
    vpage = d["vpage"]
    layer_of = dashboards._layer_of(d)          # the map's layers: c current, r retired
    old = d.get("old") or set()                 # versions of a framework a new one replaced
    fac = d.get("act_factors") or {}            # versions allowing two activations a year
    rp = _return_periods(e)                     # (c, h, version) -> the map table's figures
    name_of = dict(zip(cur["country_iso3"], cur["country_name"]))

    # ---- the documents: structured reads (version pages) and the archived PDFs' text
    # (held until the framework pages open: not read, not written)
    reads, texts, doc_links = {}, {}, {}
    if on("documents"):
        reads = _doc_reads(e, out, snapshot_at, stamp)      # (kb_framework, version) -> file
        texts, doc_links = _pdf_texts(e, out)               # sha -> file; (c, h, v) -> [{...}]
    written.update(reads.values())
    written.update(texts.values())

    # ---- funding: the annual series the Financing page charts. Its current-year rows are
    # pre-arranged money NOW (dashboards.prearranged_now, the one definition every page uses);
    # the registry rows below carry the same figure, so every file agrees to the dollar.
    # released="all": the non-framework allocations ride along on their own layer, as on the
    # Financing page (its layer toggles); co-financing is kept apart from the pre-arranged money
    pre, act = dashboards.funding_series(d, released="all")
    cof = pre[pre["kind"] == "cofinancing"].copy()
    pre = pre[pre["kind"] == "prearranged"].copy()
    for df in (pre, cof):
        df["source"] = [x if x in ("framework-record", "onegms-mirror", "version-inferred") else "tracking-sheets"
                        for x in df["source"].astype(str)]
        df["version"] = [None if pd.isna(v) else str(v) for v in df["version"]]
        df["layer"] = [LAYER[layer_of(c, h, v)] for c, h, v in zip(df["country_iso3"], df["hazard"], df["version"])]
        df["replaced_framework"] = [(c, h, v) in old for c, h, v in zip(df["country_iso3"], df["hazard"], df["version"])]
    # funding_series has already multiplied these rows (activation_factors): the factor says so
    pre["activations_per_year"] = [fac.get((c, h, v), 1) for c, h, v in zip(pre["country_iso3"], pre["hazard"], pre["version"])]
    if scope_ctry is not None:
        pre, cof = pre[pre["country_iso3"].isin(scope_ctry)], cof[cof["country_iso3"].isin(scope_ctry)]
    act = act.copy()
    act["layer"] = ["non_framework" if t == "adhoc_aa" else LAYER[layer_of(c, h, v)]
                    for t, c, h, v in zip(act["event_type"], act["country_iso3"], act["hazard"], act["version"])]
    now_year = date.today().year
    now = pre[(pre["year"] == now_year) & (pre["source"] == "framework-record")]
    now_all = now.groupby(["country_iso3", "hazard"])["amount_usd"].sum().to_dict()
    now_cerf = now[now["fund_code"] == "cerf"].groupby(["country_iso3", "hazard"])["amount_usd"].sum().to_dict()
    now_ver = {(x.country_iso3, x.hazard): str(x.version) for x in d["vfund"].itertuples()}
    # co-financing as reported for the year, per framework: the map table's column
    # co-financing now, as the map and the Financing page count it (dashboards.cofinancing_now): the
    # framework's yearly total, split by co-financer as its latest document states, or the document's
    # lines where no total is recorded; the past years keep the yearly totals as reported
    cof = cof[cof["amount_usd"].notna() & cof["year"].notna()]
    cn = dashboards.cofinancing_now(d, cof, now_year)
    if scope_ctry is not None:
        cn = cn[cn["country_iso3"].isin(scope_ctry)]
    cn = cn.assign(year=now_year, version=[None if pd.isna(v) else str(v) for v in cn["version"]],
                   financier=cn["who"], source="co-financing-now")
    cn["layer"] = [LAYER[layer_of(c, h, v)] for c, h, v in zip(cn["country_iso3"], cn["hazard"], cn["version"])]
    cn["replaced_framework"] = [(c, h, v) in old for c, h, v in zip(cn["country_iso3"], cn["hazard"], cn["version"])]
    gho = cof.drop_duplicates(["country_iso3", "year"]).set_index(["country_iso3", "year"])["in_gho"].to_dict() \
        if "in_gho" in cof.columns else {}
    cn["in_gho"] = [gho.get((c, now_year)) for c in cn["country_iso3"]]
    cof = pd.concat([cof[cof["year"] != now_year], cn], ignore_index=True)
    cof_now = cn.groupby(["country_iso3", "hazard"])["amount_usd"].sum().to_dict()

    # ---- frameworks: the pairs the open map shows (and any framework page that is open)
    fw_rows = []
    for r in cur.itertuples():
        page = pages.get((r.country_iso3, r.hazard))
        pair = (r.country_iso3, r.hazard)
        if not in_scope(*pair):
            continue
        mf = map_fw.get(pair) or {}
        latest = (r.country_iso3, r.hazard, str(r.latest_version)) if pd.notna(r.latest_version) else None
        apy = fac.get((*pair, now_ver[pair]), 1) if pair in now_all else fac.get(latest, 1)
        fw_rows.append({
            "country_iso3": r.country_iso3, "country_name": r.country_name, "region": _cell(r.region),
            "hazard": r.hazard, "lifecycle": _cell(r.lifecycle), "status": _cell(r.status),
            "retired": bool(r.retired), "technical_support": bool(r.technical_support),
            "latest_version": _cell(r.latest_version), "latest_version_status": _cell(r.latest_status),
            "current_version": _cell(r.current_version), "valid_until": _cell(r.valid_until),
            "n_windows": _cell(r.n_windows), "n_windows_triggered": _cell(r.n_triggered),
            "fully_triggered": bool(r.fully_triggered) if pd.notna(r.fully_triggered) else None,
            **rp.get(latest, RP_NONE),
            "prearranged_usd": _cell(now_all.get(pair)),
            "prearranged_cerf_usd": _cell(now_cerf.get(pair)) if pair in now_all else None,
            "prearranged_year": now_year if pair in now_all else None,
            "prearranged_version": now_ver.get(pair) if pair in now_all else None,
            "activations_per_year": apy,
            "cofinancing_usd": _cell(landing.cof_of(mf) if mf else cof_now.get(pair)),
            # the open map's figure (its copy leaves out one taken from an unpublished document)
            "people_covered": (_cell(mf.get("covered")) if mf
                               else None if gone(*pair, r.people_covered) else _cell(r.people_covered)),
            "monitoring_months": ((mf.get("versions") or [{}])[-1].get("months") or None) if mf else None,
            "map_layers": mf.get("layers") or None,
            **({"page_html": SITE_URL + page if page else None,
                "page_markdown": SITE_URL + f"fw-{r.country_iso3.lower()}-{r.hazard}.md" if page else None}
               if on("documents") else {}),
        })
    # the pairs the map draws only for a non-framework allocation have no registry row: one each,
    # so the table lists every pair on the map
    have = {(x["country_iso3"], x["hazard"]) for x in fw_rows}
    for (c, h), f in sorted(map_fw.items()):
        if (c, h) not in have:
            cd = om["countries"][c]
            fw_rows.append({"country_iso3": c, "country_name": cd.get("name"), "region": cd.get("region"),
                            "hazard": h, "people_covered": _cell(f.get("covered")),
                            "cofinancing_usd": _cell(landing.cof_of(f)), "map_layers": f.get("layers") or None})
    fw_rows.sort(key=lambda x: (x["country_name"] or "", x["hazard"]))
    write_table("frameworks", fw_rows,
                "The frameworks on the map: one row per (country, hazard) pair the open map shows (a pair "
                "drawn only for a non-framework allocation has no framework: its lifecycle and versions are "
                "blank), "
                "with its lifecycle, latest version, the return period of that version as the map's table "
                "shows it, the pre-arranged funding in place now (`prearranged_usd`, all funds; "
                "`prearranged_cerf_usd` its CERF part; the envelope of `prearranged_version`, counted "
                "twice where `activations_per_year` is 2; these sum to the current-year rows of "
                f"aa-prearranged-funding{' and aa-funding-annual' if on('funding-annual') else ''}), this "
                "year's co-financing (outside the OCHA-managed funds, never added to pre-arranged), people "
                "covered (blank where the figure comes from a framework document that is not published, as "
                "on the open map), the months its latest version is monitored, and `map_layers`: the map's "
                "layers the pair is drawn on (framework: current frameworks; retired; adhoc: non-framework "
                "allocations; tech: technical support only)"
                + (", and the links to its page and its Markdown" if on("documents") else "") + ".")

    # ---- versions: the registry rows + the page fields + the document links
    v_rows, trig_rows, trig_table, trig_of = [], [], [], {}   # trig_rows: the document's own keys (pages)
    vv = fvm.copy()
    vv["_vf"] = pd.to_datetime(vv["valid_from"].astype(str), errors="coerce")
    kbs = d["versions"].set_index(["country_iso3", "hazard", d["versions"]["version"].astype(str)])
    for r in vv.sort_values(["country_iso3", "hazard", "_vf"]).itertuples():
        key = (r.country_iso3, r.hazard, str(r.version))
        if not in_scope(r.country_iso3, r.hazard):
            continue
        kb_status = _cell(kbs.loc[key, "kb_status"]) if key in kbs.index else None
        facts, trig = _version_facts(vpage, r.kb_framework, r.version)
        row = {"country_iso3": r.country_iso3, "hazard": r.hazard, "version": str(r.version),
               "status": kb_status, "replaced_framework": key in old,
               "valid_from": _cell(r.valid_from), "valid_until": _cell(r.valid_until),
               "activations_per_year": fac.get(key, 1), **rp.get(key, RP_NONE),
               "document_title": _cell(r.doc_title), "document_url": _cell(r.doc_url),
               "analysis_ref": _cell(r.analysis_ref)}
        if on("documents"):
            row.update({"document_read": (SITE_URL + reads[(r.kb_framework, str(r.version))]
                                          if (r.kb_framework, str(r.version)) in reads else None),
                        "document_text": [SITE_URL + texts[x["sha256"]] for x in doc_links.get(key, [])
                                          if x["sha256"] in texts] or None})
        if gone(r.country_iso3, r.hazard, facts.get("target_people")):
            facts["target_people"] = None       # as the open map leaves it out
        row.update(facts)
        v_rows.append(row)
        trig = [t for t in trig if isinstance(t, dict)]
        trig_of[key] = trig
        for i, t in enumerate(trig):
            trig_rows.append({"country_iso3": r.country_iso3, "hazard": r.hazard,
                              "version": str(r.version), **{str(k): v for k, v in t.items()}})
            trig_table.append({"country_iso3": r.country_iso3, "hazard": r.hazard,
                               "version": str(r.version), "row": i + 1, **_trigger_row(t)})
    write_table("versions", v_rows,
                "Every registered version of the frameworks on the map (`status`: an endorsed document, one "
                "still in development, or a retired one; `replaced_framework`: a version of an earlier "
                "framework that a distinct new one replaced): validity, the activations a year it allows, its "
                "overall return period, the document ("
                + ("its official page, its structured read `document_read`, its full text `document_text`"
                   if on("documents") else "`document_title`, `document_url` its official page")
                + "), and the version's scope, trigger basis, indicators, data sources, monitoring months, "
                "implementing agencies and the people its document targets (`target_people`, blank where the "
                "document is not published and the figure is the framework's people covered, as on the open map).")
    write_table("trigger-windows", trig_table,
                "The trigger windows as the framework document states them, per version, in the "
                "document's order (`row`): window, basis, indicator, threshold, lead time, the return "
                "period THE DOCUMENT states (free text; the backtest's is in aa-windows) and what the "
                "window releases (`releases` as the document words it, `releases_usd` where it gives an "
                "amount). `other` holds any further column of that document's own table.")

    # ---- windows and backtests
    w = d["windows"]
    w_rows = _records(w.sort_values(["country_iso3", "hazard", "version", "window_name"]),
                      ["country_iso3", "country_name", "hazard", "version", "is_latest", "window_name",
                       "basis", "all_in", "allocation_usd", "return_period", "activation_prob",
                       "n_activations", "analysis_years", "analysis_start", "analysis_end",
                       "triggered", "triggered_on"])
    # the recorded window names are not always the document's ("wt1", "ws" are the backtest's
    # codes): pair them the way the framework pages do (page_model), blank where no pairing holds
    import page_model
    by_ver = {}
    for x in w_rows:
        by_ver.setdefault((x["country_iso3"], x["hazard"], str(x["version"])), []).append(x)
    for key, rows in by_ver.items():
        trig = trig_of.get(key) or []
        codes = page_model._match_codes([x["window_name"] for x in rows], trig) if trig else {}
        for x in rows:
            idx = (codes.get(x["window_name"]) or page_model._match(x["window_name"], trig)) if trig else []
            x["document_window"] = "; ".join(_document_windows(x["window_name"], trig, idx)) or None
    w_rows = [{k: x.get(k) for k in ("country_iso3", "country_name", "hazard", "version", "is_latest",
                                     "window_name", "document_window", "basis", "all_in", "allocation_usd",
                                     "return_period", "activation_prob", "n_activations", "analysis_years",
                                     "analysis_start", "analysis_end", "triggered", "triggered_on")}
              for x in w_rows]
    write_table("windows", w_rows,
                "Trigger windows per version as the tracking database records them, with their "
                "allocation and BACKTEST: `return_period` (years, from the historical simulation of the "
                "trigger; the document's own stated figure is in aa-trigger-windows and can differ), "
                "annual activation probability, activations in the analysed years, and whether the "
                "window has triggered under this version. `window_name` is the recorded name (short "
                "codes such as wt1, wg2, ws are the backtest's labels); `document_window` is the window "
                "of the document's table (aa-trigger-windows) it corresponds to, blank where no "
                "one-to-one pairing is recorded.")

    # ---- simulated (historical) activations
    s = d["sim"].copy()
    s["version"] = s["version"].astype(str)
    s["in_backtest"] = True
    for (c_, h_, v_), g in s.groupby(["country_iso3", "hazard", "version"]):
        vf = fvm.loc[(fvm["country_iso3"] == c_) & (fvm["hazard"] == h_)
                     & (fvm["version"].astype(str) == v_), "valid_from"]
        kept, _, _ = dashboards.sim_before_start(g, vf)
        s.loc[g.index.difference(kept.index), "in_backtest"] = False
    s_rows = _records(s.sort_values(["country_iso3", "hazard", "version", "event_year"]),
                      ["country_iso3", "hazard", "version", "window_name", "event_year",
                       "event_label", "event_date", "event_time", "time_precision", "in_backtest"])
    write_table("simulated-activations", s_rows,
                "The historical simulation of each version's trigger: the years (and dates where "
                "known) in which a window would have activated. `in_backtest` is false for a row dated "
                "in or after the year its version took effect: from then on only real activations "
                "(aa-activations) count, and the site does not show that row.")

    # ---- real activations (framework and non-framework): one row per event, funding nested.
    # People reached or targeted are the open map's own (its funding rows, landing._reach_fields):
    # the same figures its tile adds up
    fund = d["activation"]
    a_rows, off_map, unmatched = [], 0, 0
    for r in d["act_all"].sort_values("event_date", ascending=False).itertuples():
        if not in_scope(r.country_iso3, r.hazard):
            off_map += 1
            continue
        wn = r.window_name if isinstance(r.window_name, str) else None
        lab = r.event_label if isinstance(r.event_label, str) else ""
        f = fund[(fund["country_iso3"] == r.country_iso3) & (fund["hazard"] == r.hazard)
                 & (fund["event_date"].astype(str) == str(r.event_date))
                 & (fund["event_type"] == r.event_type)
                 & (fund["window_name"].fillna("") == (wn or ""))]
        rows = []
        for x in f.itertuples():
            code = _cell(x.allocation_code)
            k = (r.country_iso3, r.hazard, str(r.event_date), r.event_type, wn or "")
            # a pooled fund the record did not name: the Financing page names the country's own
            # (dashboards._resolve_pooled_fund), the map keeps it unnamed
            got = map_fund.get((*k, x.fund_code, code or "")) or map_fund.get((*k, "cbpf-unspecified", code or ""))
            m = got.pop(0) if got else None
            if m is None and map_fw:
                unmatched += 1
            m = m or {}
            # every funding row carries every key, as every table row does (null: no figure)
            rows.append({"fund_code": x.fund_code, "allocation_code": code,
                         "amount_usd": _cell(x.amount_usd),
                         "refund_usd": _cell(x.refund_usd) if pd.notna(x.refund_usd) and x.refund_usd else None,
                         "provisional": bool(x.provisional) if pd.notna(x.provisional) else False,
                         "people_reached": _cell(m.get("reached")),
                         "people_reached_interim": bool(m.get("interim")) if m.get("reached") is not None else None,
                         "people_planned": _cell(m.get("planned")),
                         "allocation_shared": bool(m.get("shared"))})
        version = _cell(r.version)
        a_rows.append({"country_iso3": r.country_iso3, "country_name": name_of.get(r.country_iso3),
                       "hazard": r.hazard, "event_type": r.event_type, "event_date": _cell(r.event_date),
                       "window_name": wn, "event_label": lab or None,
                       "version": version,
                       "layer": ("non_framework" if r.event_type == "adhoc_aa"
                                 else LAYER[layer_of(r.country_iso3, r.hazard, version)]),
                       "replaced_framework": (r.country_iso3, r.hazard, str(version)) in old,
                       "people_targeted": _cell(r.people_targeted),
                       "amount_usd": sum(x["amount_usd"] or 0 for x in rows) if rows else None,
                       "fund_codes": "; ".join(sorted({x["fund_code"] for x in rows})) or None,
                       "funding": rows})
    if off_map or unmatched:
        print(f"::warning::open layer: {off_map} activation(s) on no pair of the open map left out; "
              f"{unmatched} funding row(s) not found in the map's data (no people figure)")
    write_table("activations", a_rows,
                "Every real activation since 2020 on the map: framework activations (event_type "
                "framework_aa) and non-framework allocations (adhoc_aa: anticipatory money allocated "
                "without a framework), with the money each drew per fund (`funding`; `amount_usd` is their "
                "sum, net of any money refunded after the activation stopped, `refund_usd`; `provisional`: "
                "an amount entered before OCHA's grant management system recorded the allocation) and the "
                "people the map counts for it: `people_reached` CERF's figure (`people_reached_interim`: "
                "summed from its projects' reports, no final report yet); `people_planned` where there is no "
                "report, the people a CERF allocation plans to reach or the activation targets, and for a "
                "Country or Regional Fund allocation the people it targets. `allocation_shared`: the "
                "allocation serves several activations and its figures sit on the earliest one. `layer` and "
                "`replaced_framework` as in the counting rules. Early action is not included.")

    # ---- funding tables (the series computed above)
    p_rows = _records(pre.sort_values(["year", "country_iso3", "hazard", "fund_code"]),
                      ["country_iso3", "hazard", "year", "version", "fund_code", "financier", "amount_usd",
                       "activations_per_year", "source", "layer", "replaced_framework", "in_gho"])
    write_table("prearranged-funding", p_rows,
                "Pre-arranged funding in place per framework, year and fund: a STOCK (the envelope "
                "standing that year), never summed across years. `version`: the version the envelope "
                "belongs to (blank for a pooled-fund allocation made at country level; hazard `multi` or "
                "`?` there means the country has several or no live framework). `activations_per_year` 2: "
                "the amount is already the envelope counted twice. `source`: framework-record (the current "
                "envelope), onegms-mirror (pooled-fund allocations), tracking-sheets (the team's "
                "reported series), version-inferred (carried from the version in force). `in_gho`: "
                "the country was in that year's Global Humanitarian Overview.")
    c_rows = _records(cof.sort_values(["year", "country_iso3", "hazard"]),
                      ["country_iso3", "hazard", "year", "version", "financier", "amount_usd", "source",
                       "layer", "replaced_framework", "in_gho"])
    write_table("cofinancing", c_rows,
                "Co-financing pre-arranged for a framework: money from outside CERF and the Country and "
                "Regional Funds, recorded with the pre-arranged figures (the map's Co-financing tile and "
                "table column). A stock per year, never summed across years and never added to the "
                "OCHA-managed pre-arranged money. Past years: the yearly totals as reported for the year. "
                "The current year (`source` co-financing-now): each framework's co-financing now, as the map "
                "counts it: its yearly total, split by co-financer in the proportions its latest framework "
                "document states, or the document's own lines where no total is recorded; a framework whose "
                "pre-arranged money was all released by an activation has none now (its co-financing stays "
                "with its version in the database). `financier`: who "
                "provides it (`not recorded` where no one is named). How much of it was disbursed is not "
                "recorded.")
    yr_pre = pre.groupby(["year", "fund_code", "layer"])["amount_usd"].sum()
    yr_rel = act.groupby(["year", "fund_code", "layer"])["amount_usd"].sum()
    keys = sorted(set(yr_pre.index) | set(yr_rel.index))
    y_rows = [{"year": int(y), "fund_code": fc, "layer": lay,
               "prearranged_usd": _cell(yr_pre.get((y, fc, lay))), "released_usd": _cell(yr_rel.get((y, fc, lay)))}
              for y, fc, lay in keys]
    write_table("funding-annual", y_rows,
                "The Financing page's series: per year, fund and layer, the pre-arranged stock in place and "
                "the money released (framework activations on the current and retired layers, "
                "non-framework allocations on their own). The page opens with the current and "
                "non-framework layers on and the retired layer off. `fund_code` all: a pre-arranged total the "
                "source did not split by fund, which the page's annual chart (stacked by fund) leaves out. Do "
                "not add a year's pre-arranged to its released, nor pre-arranged across years.")

    # ---- plan: agency × sector split of the live frameworks' current version
    pl = _records(d["plan_rows"].sort_values(["country_iso3", "hazard", "agency", "sector"]),
                  ["country_iso3", "country_name", "hazard", "version", "fund_code", "window_name",
                   "agency", "sector", "amount_usd"])
    for x in pl:
        if x.get("window_name") in ("single", "unattributed"):      # the split is not per window
            x["window_name"] = None
    write_table("plan-split", pl,
                "The pre-arranged budget of each live framework's latest version split by implementing "
                "agency and sector (the Activities page), per trigger window where the budget is per window "
                "(`window_name`; blank: the split is for the whole framework). OCHA-managed money only "
                "(`fund_code`), never an agency's own co-financing. A framework's rows add up to its "
                "budgeted split, which can differ by rounding from the envelope its document states "
                "(aa-prearranged-funding).")

    # ---- funds: what each fund_code used above is
    used = (({x["fund_code"] for x in p_rows} if on("prearranged-funding") else set())
            | ({x["fund_code"] for x in pl} if on("plan-split") else set())
            | {f["fund_code"] for a in a_rows for f in a["funding"]})
    try:
        fd = pd.read_sql("SELECT fund_code, fund_type, name, country_iso3 FROM aa.fund ORDER BY fund_code", e)
        write_table("funds", _records(fd[fd["fund_code"].isin(used)]),
                    "The funds behind every `fund_code` in these files: CERF and the Country and Regional "
                    "Funds, that is the country-based pooled funds and the regional humanitarian pooled "
                    "funds' country envelopes (`fund_type` "
                    "cerf, cbpf or regional_fund; a name ending in a regional fund's acronym, such as "
                    "AP-RHPF, marks a country envelope of that regional fund).")
    except Exception as exc:
        print(f"::warning::open layer: fund register unavailable ({exc.__class__.__name__}); no aa-funds")

    # ---- partners
    pt = d["partners"].copy()
    pt["roles"] = [[x for x in (r if isinstance(r, list) else []) if re.fullmatch(r"[a-z_]+", str(x))] or None
                   for r in pt["roles"]]
    pt_rows = _records(pt.sort_values(["country_iso3", "hazard", "org_type", "name"]),
                       ["country_iso3", "hazard", "version", "name", "acronym", "org_type", "roles",
                        "agency_parent", "amount_usd"])
    write_table("partners", pt_rows,
                "Organisations named in the framework documents (lead and implementing agencies, "
                "government bodies, NGOs), per version, with their role tags. `amount_usd` is the budget "
                "the document attaches to the organisation, which can include its own co-financing on "
                "top of OCHA-managed money: for the CERF or pooled-fund share per agency use "
                "aa-plan-split. `agency_parent`: the UN agency a sub-grantee works under.")

    # ---- learning documents (public ones only: internal rows never leave the DB)
    ld = _records(d["learning"], ["id", "title", "url", "publisher", "year", "month", "doc_type", "scope",
                                  "country_iso3", "hazard", "premises", "key_stat", "summary", "section"])
    write_table("learning", ld,
                "Learning products (the Learning page): after-action reviews, evaluations, activation "
                "reports, research and guidance, per framework or global, with a one-line summary and key "
                "statistic. `year` and `month` date the publication, not the event it reports on.")

    # ---- trigger timelines (the Model page): when each window can act, on its hazard's clock
    import page_model
    tl = page_model._timeline_rows()
    latest_of = {(r.country_iso3, r.hazard): str(r.latest_version) for r in cur.itertuples()
                 if pd.notna(r.latest_version)}
    tl = tl.assign(version=tl["version"].astype(str))
    tl["latest_version"] = [latest_of.get((c, h)) == v for c, h, v in zip(tl["country_iso3"], tl["hazard"], tl["version"])]
    write_table("trigger-timelines", _records(
        tl.sort_values(["hazard", "country_iso3", "version", "leg", "seq"], na_position="first"),
        ["country_iso3", "hazard", "version", "latest_version", "leg", "seq", "stage", "lead_from", "lead_to",
         "unit", "months", "season_start", "season_len", "label", "stated", "indicator", "threshold", "note"]),
        "When each trigger window of a framework version can act, read by hand from the framework "
        "document (the Model page's trigger timelines, which draw the latest version: "
        "`latest_version`). Storms in hours (`unit` h) and floods in days (d) before (negative) or "
        "after (positive) landfall or the flood peak, as a bar from `lead_from` to `lead_to`; drought "
        "(`unit` mo) as the calendar `months` a trigger is checked, against the rainy season "
        "(`season_start` month, `season_len` months). `stage`: readiness, action or observational "
        "(acting on the observed event); `leg`: a river or a season, with `seq` ordering its rows; "
        "`label`: the window's name; `stated`: the document's own wording of the timing; `note`: what "
        "the document adds.")

    # ---- Markdown pages
    md_pages = []
    fw_of = {(x["country_iso3"], x["hazard"]): x for x in fw_rows}
    for r in cur.itertuples():
        page = pages.get((r.country_iso3, r.hazard))
        if not (page and on("documents")):
            continue
        name = f"fw-{r.country_iso3.lower()}-{r.hazard}.md"
        text = _framework_md(d, r, fw_of[(r.country_iso3, r.hazard)], page, v_rows, trig_rows, w_rows,
                             s_rows, a_rows, p_rows, c_rows, pl, pt_rows, ld, snapshot_at, stamp)
        (out / name).write_text(text)
        written.add(name)
        md_pages.append((name, f"{r.country_name} {r.hazard.replace('_', ' ')}",
                         f"{_cell(r.lifecycle) or ''}" + (f", version {r.latest_version}" if pd.notna(r.latest_version) else "")))
    # what this build wrote (a table can be missing: the fund register, if it cannot be read)
    has = lambda n: on(n) if n in ("documents", "map", "portfolio") else f"aa-{n}.json" in written  # noqa: E731
    rules = _rules(has)
    portfolio = None
    if on("portfolio"):
        unsplit = [(x["year"], f"{name_of.get(x['country_iso3'], x['country_iso3'])} {x['hazard'].replace('_', ' ')}",
                    x["amount_usd"]) for x in p_rows if x["fund_code"] == "all" and x["amount_usd"]]
        portfolio = _portfolio_md(fw_rows, y_rows, md_pages, snapshot_at, stamp,
                                  [f"{n} {h.replace('_', ' ')}" for n, h, _ in dashboards.envelope_gaps(d)], unsplit,
                                  rules)
        (out / "aa-portfolio.md").write_text(portfolio)
        written.add("aa-portfolio.md")
    if on("map"):
        (out / "aa-map.md").write_text(_map_md(om, fw_rows, a_rows, snapshot_at, stamp))
        written.add("aa-map.md")
    if on("map-data"):
        (out / "aa-map-data.json").write_text(_map_data(om, snapshot_at, stamp))
        written.add("aa-map-data.json")
    if on("map") or on("map-data"):
        _map_field_alarm(om)

    # ---- the withheld figures: none may be left in a live file (the build stops). The map's data
    # file is the open copy, which open_map_countries already cleared: checked all the same
    leak = [f"{c} {h}" for (c, h), f in map_fw.items()
            if gone(c, h, f.get("covered"))
            or any(gone(c, h, v.get("target_people")) for v in f.get("versions") or [])
            or any(gone(c, h, x[1]) for x in (f.get("hist") or {}).get("cov") or [])]
    if leak and on("map-data"):
        raise SystemExit(f"FATAL: open layer: the map's data carries a people figure from an unpublished "
                         f"framework document ({', '.join(leak)})")

    # ---- the withheld figures: none may be left in a live file (the build stops)
    for rows, cols in ((fw_rows, ("people_covered",)), (v_rows, ("target_people",))):
        for x in rows:
            if any(gone(x["country_iso3"], x["hazard"], x.get(c)) for c in cols):
                raise SystemExit(f"FATAL: open layer: {x['country_iso3']} {x['hazard']} carries a people figure "
                                 "from an unpublished framework document")

    # ---- the figure check: the files as written against the open map's own figures (figure_check;
    # a mismatch is a warning in the publish run, and llms.txt says so)
    n_cmp, bad = 0, []
    if on("map"):
        import figure_check
        n_cmp, bad = figure_check.open_layer(out, om)
    # an open page whose data no file carries (a page opened before its data was given a file)
    for pg in sorted(live - WORDS_ONLY):
        if not any(pg in h for h in HOME.values()) and not pg.startswith("fw-"):
            print(f"::warning::open layer: {pg} is served without a password, but no file of the open layer "
                  f"carries its data (llm_layer.HOME)")

    # ---- llms.txt, llms-full.txt, robots.txt, sitemap.xml
    stamp_line = f"Data snapshot {snapshot_at} UTC; files generated {stamp}." if snapshot_at else f"Files generated {stamp}."
    idx = ["# OCHA anticipatory action — portfolio tracking\n",
           f"> The tracking record of OCHA's anticipatory action (AA) portfolio, as the open pages of {SITE_URL} "
           f"show it: every framework on the map (a country and a hazard), its versions, pre-arranged funding and "
           f"co-financing, activations and the money they released, and the people reached or targeted. Maintained "
           f"by the data science team of OCHA's Centre for Humanitarian Data. {stamp_line}\n",
           f"**Caveat.** {CAVEAT}\n",
           f"The map at {SITE_URL} is open, with no password. The site's other pages are not public yet: at "
           f"their addresses a \"Coming soon\" page links to the development version of the site, behind a "
           f"password. These files carry the data of the open pages, and only theirs (today: the map's); the "
           f"data of the other pages will be added as those pages open. They are published openly on purpose: "
           f"they are the interface for programs and AI assistants and need no password. Every file is "
           f"regenerated from the database with each publish (nightly, and whenever the site or its data "
           f"changes), in the same build as the map. The pages read in English, French and Spanish; these "
           f"files are in English.\n",
           (f"**Checked against the map.** At this build, every figure here was compared with the map's own "
            f"({n_cmp} comparisons: each headline figure recomputed from the tables, each framework's figures, "
            f"the figures aa-map.md states): all agree.\n" if on("map") and not bad else
            f"**Checked against the map: {len(bad)} of {n_cmp} figures disagree at this build.** The map's "
            f"own figures are those of aa-map.md and aa-map-data.json; the tables below may be off for: "
            + "; ".join(bad[:10]) + (" (and more)" if len(bad) > 10 else "") + ".\n" if on("map") else ""),
           rules]
    idx.append("## The map\n")
    if on("map"):
        idx.append(f"- [The map in text]({SITE_URL}aa-map.md): its headline figures as it opens (pre-arranged "
                   f"money, co-financing, people covered, this year's activations and the people reached or "
                   f"targeted), with the map's own notes on them, its frameworks and this year's activations.")
    if on("map-data"):
        idx.append(f"- [The map's own data]({SITE_URL}aa-map-data.json) (JSON, large): exactly what the map's "
                   f"page carries, without the drawing: every country, framework, version and activation, the "
                   f"country panels (trigger tables and windows, backtests, budget splits, partners, learning "
                   f"documents, sub-grantees) and the year selector's past years, with the headline figures "
                   f"(`headline`, `headline_non_framework`). Every field is described under \"The map's data\" "
                   f"below. The tables are easier to read; this file has everything the map shows.")
    if portfolio:
        idx.append(f"- [Portfolio overview]({SITE_URL}aa-portfolio.md): every framework with its lifecycle, "
                   f"latest version and envelope; the annual pre-arranged and released series.")
    if on("documents"):
        idx.append(f"- [Everything in one file]({SITE_URL}llms-full.txt): every Markdown page and every "
                   f"structured read of a framework document, concatenated (large).")
    idx.append("")
    if md_pages:
        idx.append("## Framework pages (one per framework, Markdown)\n")
        for name, title, sub in md_pages:
            idx.append(f"- [{title}]({SITE_URL}{name}): {sub}")
        idx.append("")
    if reads or texts:
        idx.append("## Framework documents\n")
        idx.append("Each endorsed version of a framework is a published document (on ReliefWeb or "
                   "unocha.org; `document_url` in aa-versions). Two renderings here, per version. A version "
                   "still in development has no document yet: its file below is the team's working record "
                   "and says so in its first lines.\n")
        idx.append("- **Structured reads** (`doc-<framework>-<version>.md`): a full read of the document by "
                   "the OCHA data science team — summary, method, trigger logic, trigger windows, "
                   "monitoring, key decisions, changes from the previous version, historical activations — "
                   "with the document's own page numbers as evidence. Linked from each framework page and "
                   "from `document_read` in aa-versions. All of them are in "
                   f"[llms-full.txt]({SITE_URL}llms-full.txt).")
        idx.append("- **Full text** (`pdf-<sha256>.txt`): the text of the archived PDF, page by page, as "
                   "extracted (tables and figures come out flattened; the structured read is the better "
                   "source for figures). Linked from `document_text` in aa-versions.\n")
        for (kb, ver), fn in sorted(reads.items()):
            idx.append(f"- [{kb} {ver}]({SITE_URL}{fn})")
        idx.append("")
    idx.append("## Data files\n\nJSON: one object with `rows`, `columns`, a `description` and the stamps; "
               "every row carries every column (null where empty). CSV: the same rows; a nested value is "
               "JSON in its cell, a plain list is joined with `; `.\n")
    for name, desc, cols in files:
        idx.append(f"- [aa-{name}.json]({SITE_URL}aa-{name}.json) · [CSV]({SITE_URL}aa-{name}.csv): {desc} "
                   f"Columns: {', '.join(cols)}.")
    if on("map-data"):
        idx.append("\n## The map's data (aa-map-data.json)\n")
        idx.append(_map_dictionary(om))
    idx.append("\n## Vocabulary\n")
    idx.append(_vocabulary(has))
    idx.append("\n## Related\n\n- Code and schema (public repository): https://github.com/OCHA-DAP/ds-aa-tracking\n"
               "- OCHA anticipatory action: https://www.unocha.org/anticipatory-action\n"
               "- CERF: https://cerf.un.org/\n")
    (out / "llms.txt").write_text("\n".join(idx))
    written.add("llms.txt")
    if on("documents"):
        full = ([portfolio] if portfolio else []) + [(out / n).read_text() for n, _, _ in md_pages] \
            + [(out / fn).read_text() for _, fn in sorted(reads.items())]
        (out / "llms-full.txt").write_text("\n\n---\n\n".join(full))
        written.add("llms-full.txt")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}sitemap.xml\n")
    # the open files first (what a program reads), then the open pages
    urls = ([SITE_URL + "llms.txt"] + [SITE_URL + n for n in ("aa-map.md", "aa-portfolio.md", "llms-full.txt") if n in written]
            + [SITE_URL + n for n, _, _ in md_pages]
            + [SITE_URL + f"aa-{n}.{ext}" for n, _, _ in files for ext in ("json", "csv")]
            + [SITE_URL + fn for _, fn in sorted(reads.items())]
            + [SITE_URL + fn for _, fn in sorted(texts.items())]
            + [SITE_URL + ("" if n == MAP else n) for n in sorted(live, key=lambda n: (n != MAP, n))])
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc><lastmod>{stamp}</lastmod></url>\n" for u in urls) + "</urlset>\n")
    written.update({"robots.txt", "sitemap.xml"})
    _check_refs(out, written, live)
    print(f"  open layer ({', '.join(sorted(live))}): {len(files)} tables · "
          + ("aa-map.md · " if "aa-map.md" in written else "")
          + f"{len(md_pages)} framework pages · {len(reads)} document reads · {len(texts)} document texts · llms.txt")
    return written


_FILE_REF = re.compile(r"\b(?:aa-(?:" + "|".join(sorted((k for k in HOME if k != "documents"), key=len, reverse=True))
                       + r")\b(?:\.(?:json|csv|md))?|fw-[a-z]{3}-[a-z_]+\.md|doc-[\w.-]+?\.md|pdf-[0-9a-f]{8,}\.txt"
                       r"|llms-full\.txt)")


def _check_refs(out, written, live):
    """Every file a written file names, by link or by name, is written too (or is an open page):
    a reader must never be sent to a file of a page that is not open yet. Stops the build."""
    bad = {}
    for n in sorted(written):
        text = (out / n).read_text()
        for u in re.findall(re.escape(SITE_URL) + r"([^\s)\]<>\"'|]*)", text):
            u = u.split("#")[0].rstrip(".,;")
            if u and u not in written and u not in live:
                bad.setdefault(n, set()).add(u)
        for m in _FILE_REF.findall(text):
            f = m if "." in m else (f"{m}.md" if m in ("aa-map", "aa-portfolio") else f"{m}.json")
            if f not in written:
                bad.setdefault(n, set()).add(m)
    if bad:
        msg = ("open layer: files named that this build does not write (their page is not open):\n"
               + "\n".join(f"  {n}: {', '.join(sorted(v))}" for n, v in sorted(bad.items())))
        if os.environ.get("AA_SITE_GUARD", "").strip().lower() == "strict":
            raise SystemExit("FATAL: " + msg)
        print("::warning::" + msg)


def _vocabulary(on):
    """The vocabulary of llms.txt, naming only the files written."""
    w = lambda name, text: text if on(name) else ""       # noqa: E731
    return (
        "- `country_iso3`: ISO 3166-1 alpha-3. `hazard`: drought, flood, storm, cholera, plague, "
        "food_insecurity for frameworks; non-framework allocations in aa-activations also carry other "
        "hazards (locusts, for one) and countries without a framework.\n"
        "- `lifecycle` (aa-frameworks), the one rule every page counts by: `active` the latest "
        "version is endorsed, within its validity and not fully triggered; `updating` (being "
        "updated) an endorsed framework whose latest version is in development, or whose latest "
        "version has fully triggered or passed its end of validity and awaits renewal; "
        "`development` no endorsed version yet; `pipeline` conversations only, nothing in "
        "development; `retired` no longer pursued. `status` is a different thing: the operational "
        "status the team reports for the framework (early_conversations, advanced_conversations, "
        "under_development, project_finalization, active, under_revision, activated_implementing, "
        "monitoring, dormant, expired, retired). It is observed separately and can lag `lifecycle`.\n"
        "- Versions (aa-frameworks): `latest_version` the most recent version of any status; "
        "`current_version` the most recent one that is not in development, with `valid_until` its "
        "end of validity (which can be in the past; blank: none recorded). `n_windows` and "
        "`n_windows_triggered` count the windows recorded for the latest version; "
        "`fully_triggered`: that version has nothing left to release (any window for an all-in "
        "framework, every window otherwise; where no windows are recorded, a full activation "
        "under it). `technical_support`: OCHA supported the framework "
        "technically, with no funding. `retired`: flagged as retired by hand. `map_layers`: the map's "
        "layers the pair is drawn on (`framework` the current frameworks, `retired`, `adhoc` "
        "non-framework allocations, `tech` technical support).\n"
        "- `replaced_framework` (aa-versions, aa-activations, aa-prearranged-funding, aa-cofinancing): "
        "the row belongs to an earlier framework on the same (country, hazard) pair that a distinct new "
        "framework replaced rather than revised; it counts as a retired framework's. `layer`: "
        "`current`, `retired` or `non_framework`, the site's layer toggles (see the counting rules).\n"
        "- `activations_per_year` (aa-frameworks, aa-versions, aa-prearranged-funding): how many "
        "activations a year the version's document allows (1 for most). Where it is 2 the "
        "pre-arranged amounts already count the CERF envelope twice.\n"
        "- Return periods: `return_period_years` the version's overall return period in years (any of "
        "its windows activating in a year), `return_period_basis` where that figure comes from (`stated "
        "in the framework` or `historical simulation`), with both figures in "
        "`return_period_stated_years` and `return_period_backtest_years`."
        + w("windows", " A window's own backtest return period is `return_period` in aa-windows.") + "\n"
        "- version `status` (aa-versions): `endorsed`, `development` (not yet endorsed), `retired`. "
        + w("documents", "`document_text` is a list of URLs (a version can have several archived documents, "
                         "such as language editions). ")
        + "`analysis_ref`: where the trigger analysis lives, as repository@branch:path in the OCHA-DAP "
        "GitHub organisation. `monitoring_months` (aa-frameworks, aa-versions): the months (1-12) a "
        "version's trigger is monitored.\n"
        "- People: `people_covered` (aa-frameworks) the people the framework covers, as last "
        "reported by the team (blank where the figure comes from a framework document that is not "
        "published); `target_people` (aa-versions) the people the version's document targets; "
        "`people_targeted` (aa-activations) the people one activation targeted; in the funding rows of "
        "aa-activations, `people_reached` the people a CERF allocation reached, from CERF's report "
        "(`people_reached_interim` true: summed from its projects' reports while there is no final one), "
        "and `people_planned` the people counted where there is no report (a CERF allocation's planned "
        "figure, else the people the activation targets; a Country or Regional Fund allocation's "
        "targeted figure). The map's tile adds, over the year's allocations, each once, the reported "
        "figure where there is one and the planned one otherwise. They are different figures: do not "
        "add people covered to people reached.\n"
        "- `fund_code`" + w("funds", " (names in aa-funds)") + ": `cerf` the Central Emergency Response Fund; "
        "`cbpf-<iso3>` a country-based pooled fund, or a regional fund's envelope for that country"
        + w("funds", " where aa-funds says so") + "; `rhpf-<region>-<iso3>` a regional humanitarian pooled fund's "
        "envelope for a country (`wca` West and Central Africa, `esa` Eastern and Southern "
        "Africa); `all` a pre-arranged total the source did not break down by fund; "
        "`cbpf-unspecified` a pooled fund the source did not name. `allocation_code`: the fund's "
        "own code for the allocation, as recorded (formats differ by fund and year; one allocation "
        "can serve several frameworks). `financier`: the fund's name where the source gave one.\n"
        "- `event_type`: `framework_aa` an activation of a framework's trigger; `adhoc_aa` a "
        "non-framework allocation, anticipatory money allocated outside a framework.\n"
        "- `window_name` (aa-activations"
        + w("windows", ", aa-windows") + w("simulated-activations", ", aa-simulated-activations")
        + "): the trigger window as the tracking database records it, which can be a short code of the "
        "backtest (wt1, wg2, ws)"
        + w("windows", "; `document_window` in aa-windows gives the document's name for it where a one-to-one "
                       "pairing is recorded. `basis` is `forecast`, `observational` or `mixed` (what the "
                       "trigger reads); `all_in`: one trigger releases the whole envelope") + ".\n"
        "- Amounts are US dollars, to the dollar. Dates are ISO 8601. `event_date` keeps the "
        "precision recorded (YYYY, YYYY-MM or YYYY-MM-DD); "
        + ("`triggered_on`, " if on("windows") else "")
        + "`valid_from` and `valid_until` are full dates, so one known only to the month is written as "
        "its first day.\n")


# ---------------------------------------------------------------------- Markdown pages
def _head(title, snapshot_at, stamp, html_page=None):
    """A Markdown file's head. html_page: the open page it is the data of (only open pages have
    files here, so the link needs no password)."""
    s = f"Data snapshot {snapshot_at} UTC · generated {stamp}" if snapshot_at else f"Generated {stamp}"
    link = f" · HTML page: {SITE_URL}{'' if html_page == MAP else html_page}" if html_page else ""
    return (f"# {title}\n\n> {CAVEAT}\n>\n> {s} · index: {SITE_URL}llms.txt{link}\n\n")


def _map_md(om, fw_rows, a_rows, snapshot_at, stamp):
    """aa-map.md: the open map in text — its headline figures as it opens (the open map's own tiles,
    landing.tile_figures over its open copy: current-frameworks layer, this year, as of today), its
    frameworks and this year's activations."""
    t, ad, y = om["tiles"], om.get("adhoc") or {}, om["year"]
    n = lambda v: f"{int(v):,}"          # noqa: E731
    out = [_head("The map: OCHA's anticipatory action frameworks", snapshot_at, stamp, MAP)]
    out.append(f"The map at {SITE_URL} (open, no password) shows the anticipatory action frameworks OCHA "
               f"supports, with headline figures, a frameworks table and a panel per country. This file is "
               f"its data in text: the headline figures as the map opens (the current-frameworks layer, "
               f"{y} as of today), the frameworks it shows and this year's activations. Other years and "
               f"layers can be worked out from the data files listed in {SITE_URL}llms.txt (pre-arranged "
               f"money per year in aa-prearranged-funding, every activation in aa-activations), with the "
               f"counting rules given there.\n")
    out.append(f"## Headline figures ({y}, as of today)\n\nEach figure as the map's tile shows it, to the "
               "dollar, followed by the map's own note on it (the text its tile shows on hover).\n")
    notes = om.get("notes") or {}
    note = lambda tid: f"\n  - *The map's note:* {notes[tid]}" if notes.get(tid) else ""      # noqa: E731
    funds = lambda cerf, pooled, other=0: "; ".join(x for x in (     # noqa: E731
        cerf and f"CERF {_m(cerf)}", pooled and f"Country and Regional Funds {_m(pooled)}",
        other and f"not split by fund {_m(other)}") if x)
    lines = [f"- **Frameworks: {t['n_fw']}** in {t['n_ctry']} countries on the map today: {t['n_active']} "
             f"active, {t['n_upd']} being updated, {t['n_dev']} in development." + note("t-fw")]
    if t["n_fw"]:
        twice = sorted({f"{name} {'tropical cyclone' if hz == 'storm' else hz.replace('_', ' ')}"
                        for _, name, hz, _ in t["apy"]})
        lines.append(f"- **Pre-arranged now: {_m(t['pre'])}** ({funds(t['pre_cerf'], t['pre_pooled'], t['pre_all'])})"
                     + (f"; the CERF envelope counted once per activation for {', '.join(twice)}" if twice else "")
                     + "." + note("t-pre"))
        lines.append(f"- **Co-financing pre-arranged now: {_m(t['cofin']) if t['n_cofin'] else 'none recorded'}**"
                     + (f", recorded for {t['n_cofin']} of the {t['n_fw']} frameworks shown" if t["n_cofin"] else "")
                     + "." + note("t-cof"))
        lines.append(f"- **People covered now: {n(t['covered'])}**, figures for {t['n_cov']} of the {t['n_fw']} "
                     f"frameworks shown." + note("t-cov"))
    if t["n_act"]:
        extra = [x for x in (t["refund"] and f"{_m(t['refund'])} returned after activations stopped, deducted",
                             t["prov"] and f"{_m(t['prov'])} of it estimated, not yet in OCHA's grant management system",
                             t["n_nousd"] and f"{t['n_nousd']} of the {t['n_act']} with no amount recorded") if x]
        lines.append(f"- **Activations in {y}: {_m(t['released'])} released in {t['n_act']} framework "
                     f"activation{'s' if t['n_act'] != 1 else ''}** "
                     f"({funds(t['released_cerf'], t['released'] - t['released_cerf'])})"
                     + (f"; {'; '.join(extra)}" if extra else "") + "." + note("t-act"))
    else:
        lines.append(f"- **Activations in {y}: none** on the current-frameworks layer." + note("t-act"))
    est = t["reached"] + t["targeted"] + t["ptargeted"]
    if t["n_rep"] or t["n_tgt"] or t["n_ptgt"]:
        parts = [x for x in (t["n_rep"] and f"{n(t['reached'])} reported reached by CERF for {t['n_rep']} "
                                            f"allocation{'s' if t['n_rep'] != 1 else ''}"
                                            + (f" ({t['n_interim']} from interim reports)" if t["n_interim"] else ""),
                             t["n_tgt"] and f"{n(t['targeted'])} planned or targeted for {t['n_tgt']} CERF "
                                            f"allocation{'s' if t['n_tgt'] != 1 else ''} awaiting reports",
                             t["n_ptgt"] and f"{n(t['ptargeted'])} targeted by {t['n_ptgt']} Country and Regional "
                                             f"Fund allocation{'s' if t['n_ptgt'] != 1 else ''}") if x]
        lines.append(f"- **Reached or targeted by the {y} releases: {'about ' if t['n_tgt'] or t['n_ptgt'] else ''}"
                     f"{n(est)} people**: {'; '.join(parts)}." + note("t-reach"))
    else:
        lines.append(f"- **Reached or targeted by the {y} releases: no figure yet.**" + note("t-reach"))
    if ad.get("n_act"):
        a_est = ad["reached"] + ad["targeted"] + ad["ptargeted"]
        lines.append(f"- Not counted above (the non-framework layer is off when the map opens): {ad['n_act']} "
                     f"non-framework allocation{'s' if ad['n_act'] != 1 else ''} in {y}, {_m(ad['released'])}"
                     + (f", about {n(a_est)} people reached or targeted" if a_est else "") + ".")
    out.append("\n".join(lines) + "\n")

    cols = ["country_name", "hazard", "lifecycle", "latest_version", "prearranged_usd", "prearranged_cerf_usd",
            "activations_per_year", "cofinancing_usd", "people_covered", "return_period_years",
            "return_period_basis", "monitoring_months"]
    fmt = {"prearranged_usd": _m, "prearranged_cerf_usd": _m, "cofinancing_usd": _m,
           "people_covered": lambda v: n(v) if v is not None else "",
           "hazard": lambda v: (v or "").replace("_", " "),
           "monitoring_months": lambda v: ", ".join(MONTHS[m - 1] for m in v) if v else ""}
    on_fw = [x for x in fw_rows if "framework" in (x["map_layers"] or [])]
    other = [x for x in fw_rows if "framework" not in (x["map_layers"] or [])]
    out.append(f"## Frameworks on the current-frameworks layer ({len(on_fw)})\n\nThe frameworks the headline figures "
               "count. `prearranged_usd`: pre-arranged now, all funds (`activations_per_year` 2: the CERF envelope "
               "counted twice); `people_covered` blank: no figure, or one from a framework document that is not "
               "published.\n")
    out.append(_md_table(on_fw, cols, fmt))
    if other:
        out.append(f"## On the map's other layers ({len(other)})\n\nRetired frameworks, pairs with non-framework "
                   "allocations only, and technical support (`map_layers`). Not counted in the headline figures.\n")
        out.append(_md_table(other, ["country_name", "hazard", "lifecycle", "map_layers", "latest_version"], fmt))
    yr = [a for a in a_rows if str(a["event_date"] or "")[:4] == str(y)]
    out.append(f"## Activations in {y} ({len(yr)})\n\n`kind`: a framework activation (counted in the headline "
               "figures) or a non-framework allocation (counted only with that layer on). `amount_usd`: released, "
               "net of `returned_usd` (sent back after the activation stopped). `people` is the map's count for "
               "it: reported reached, else planned or targeted.\n")
    for a in yr:
        a["kind"] = "non-framework allocation" if a["event_type"] == "adhoc_aa" else "framework activation"
        a["people"] = sum((x["people_reached"] if x["people_reached"] is not None else x["people_planned"] or 0)
                          for x in a["funding"] if not x["allocation_shared"]) or None
        a["returned_usd"] = sum(x["refund_usd"] or 0 for x in a["funding"]) or None
    out.append(_md_table(yr, ["event_date", "country_name", "hazard", "kind", "window_name", "amount_usd",
                              "returned_usd", "fund_codes", "people"],
                         {"amount_usd": _m, "returned_usd": _m, "people": lambda v: n(v) if v else "",
                          "hazard": lambda v: (v or "").replace("_", " ")}))
    for a in yr:
        a.pop("kind", None), a.pop("people", None), a.pop("returned_usd", None)
    return "\n".join(out)


def _framework_md(d, r, fw, page, v_rows, trig_rows, w_rows, s_rows, a_rows, p_rows, c_rows, pl, pt_rows, ld,
                  snapshot_at, stamp):
    c, h = r.country_iso3, r.hazard
    mine = lambda rows: [x for x in rows if x["country_iso3"] == c and x["hazard"] == h]   # noqa: E731
    version = (str(r.latest_version) if pd.notna(r.latest_version)
               else str(r.current_version) if pd.notna(r.current_version) else None)
    hz = h.replace("_", " ")
    out = [_head(f"{r.country_name} {hz} — anticipatory action framework", snapshot_at, stamp, page)]
    facts = [f"**Country:** {r.country_name} ({c}), {_cell(r.region) or 'region not recorded'}",
             f"**Hazard:** {hz}",
             f"**Lifecycle:** {_cell(r.lifecycle) or 'not recorded'}"
             + (f" (operational status reported by the team: {r.status})"
                if pd.notna(r.status) and r.status != r.lifecycle else "")
             + (" · technical support only" if r.technical_support else "")]
    if version:
        facts.append(f"**Latest version:** {version} ({_cell(r.latest_status) or 'status not recorded'})")
    if pd.notna(r.current_version):
        facts.append(f"**Current version (the latest one not in development):** {r.current_version}"
                     + (f", valid until {_cell(r.valid_until)}" if pd.notna(r.valid_until) else ", no end date recorded"))
    if fw.get("prearranged_usd"):
        mine_now = [x for x in p_rows if x["country_iso3"] == c and x["hazard"] == h
                    and x["year"] == fw["prearranged_year"] and x["source"] == "framework-record"]
        apy = fw.get("activations_per_year") or 1
        facts.append(f"**Pre-arranged funding in place ({fw['prearranged_year']}):** {_m(fw['prearranged_usd'])} ("
                     + "; ".join(f"{x['fund_code']} {_m(x['amount_usd'])}" for x in mine_now)
                     + f"), the envelope of version {fw['prearranged_version']}"
                     + (f", counted {'twice' if apy == 2 else f'{apy} times'}: the version allows {apy} "
                        f"activations a year, so the budget per activation is {_m(fw['prearranged_usd'] / apy)}"
                        if apy > 1 else ""))
    if fw.get("cofinancing_usd"):
        facts.append(f"**Co-financing reported for {date.today().year}** (outside the OCHA-managed funds, not "
                     f"part of the pre-arranged figure): {_m(fw['cofinancing_usd'])}")
    if fw.get("return_period_years"):
        other = (fw["return_period_backtest_years"] if fw["return_period_basis"] == "stated in the framework"
                 else fw["return_period_stated_years"])
        facts.append(f"**Return period of the latest version** (any window activating in a year): "
                     f"1-in-{fw['return_period_years']:g} yr, {fw['return_period_basis']}"
                     + (f" (the historical simulation gives 1-in-{other:g} yr)" if other and fw["return_period_basis"] == "stated in the framework"
                        else f" (the framework states 1-in-{other:g} yr)" if other else ""))
    if pd.notna(r.people_covered):
        facts.append(f"**People covered:** {int(r.people_covered):,}")
    if any(v["replaced_framework"] for v in mine(v_rows)):
        facts.append("**Replaced framework on this pair:** an earlier framework, replaced by a distinct new one "
                     "rather than revised, shares this country and hazard. Its versions and activations are "
                     "marked below; they count as a retired framework's, not this one's.")
    if pd.notna(r.n_windows) and r.n_windows:
        facts.append(f"**Trigger windows recorded for the latest version:** {int(r.n_windows)}, "
                     f"{int(r.n_triggered or 0)} triggered" + (" · fully triggered" if r.fully_triggered else ""))
    out.append("\n".join(f"- {x}" for x in facts) + "\n")

    # scope and trigger of the latest version
    vs = [{**v, "read": v.get("document_read"), "text": v.get("document_text")} for v in mine(v_rows)]
    cur_v = next((v for v in vs if version and v["version"] == version), vs[-1] if vs else None)
    if cur_v:
        out.append(f"## Scope and trigger (version {cur_v['version']})\n")
        bits = []
        if cur_v.get("geographic_scope"):
            sc = cur_v["geographic_scope"]
            bits.append("**Geographic scope:** " + (", ".join(map(str, sc)) if isinstance(sc, list) else str(sc)))
        if cur_v.get("admin_level") is not None:
            bits.append(f"**Admin level:** {cur_v['admin_level']}")
        if cur_v.get("monitoring_months"):
            bits.append("**Monitoring months:** " + ", ".join(MONTHS[m - 1] for m in cur_v["monitoring_months"]))
        if cur_v.get("trigger_basis"):
            bits.append(f"**Trigger basis:** {cur_v['trigger_basis']}")
        if cur_v.get("trigger_indicators"):
            bits.append("**Indicators:** " + ", ".join(cur_v["trigger_indicators"]))
        if cur_v.get("data_sources"):
            ds = cur_v["data_sources"]
            bits.append("**Data sources:** " + (", ".join(map(str, ds)) if isinstance(ds, list) else str(ds)))
        if cur_v.get("implementing_agencies"):
            ag = cur_v["implementing_agencies"]
            bits.append("**Implementing agencies:** " + (", ".join(map(str, ag)) if isinstance(ag, list) else str(ag)))
        if cur_v.get("target_people"):
            bits.append(f"**People targeted:** {cur_v['target_people']}")
        if cur_v.get("all_in") is not None:
            bits.append("**All-in trigger:** " + ("yes (one trigger releases the whole envelope)" if cur_v["all_in"] else "no (each window releases its own package)"))
        if cur_v.get("prearranged_funding_usd"):
            bits.append(f"**Pre-arranged funding stated in the document:** {_m(cur_v['prearranged_funding_usd'])}")
        if cur_v.get("cofinancing_usd"):
            bits.append(f"**Co-financing:** {_m(cur_v['cofinancing_usd'])}"
                        + (f" from {', '.join(map(str, cur_v['cofinancing_sources']))}" if isinstance(cur_v.get("cofinancing_sources"), list) else ""))
        if cur_v.get("document_url"):
            bits.append(f"**Framework document:** {cur_v['document_url']}"
                        + (f" ({cur_v['framework_doc_date']})" if cur_v.get("framework_doc_date") else ""))
        out.append("\n".join(f"- {b}" for b in bits) + "\n" if bits else "_no structured description recorded_\n")
        tw = [t for t in mine(trig_rows) if t["version"] == cur_v["version"]]
        if tw:
            cols = [k for k in tw[0] if k not in ("country_iso3", "hazard", "version")]
            for t in tw[1:]:
                cols += [k for k in t if k not in cols and k not in ("country_iso3", "hazard", "version")]
            out.append(f"### Trigger windows as the framework document states them\n\n{_md_table(tw, cols)}")

    # windows and backtests
    wall = mine(w_rows)
    wv = [x for x in wall if version and str(x["version"]) == version]
    w_label = version
    if not wv and wall:
        w_label = sorted({str(x["version"]) for x in wall})[-1]
        wv = [x for x in wall if str(x["version"]) == w_label]
    gone = {v["version"] for v in mine(v_rows) if v["replaced_framework"]}
    out.append("## Trigger windows and backtest" + (f" (version {w_label})" if w_label else "")
               + (" — the earlier, replaced framework's: this framework has none recorded yet" if w_label in gone
                  else " — the latest version with a recorded backtest" if w_label != version else "") + "\n")
    if wv:
        out.append("The windows as the tracking database records them. `return_period` and "
                   "`activation_prob` come from the backtest (the historical simulation of the trigger), "
                   "so they can differ from the return period the document itself states (table above). "
                   "`document_window`: the window of the document's table this row corresponds to, blank "
                   "where no one-to-one pairing is recorded.\n")
    out.append(_md_table(wv, ["window_name", "document_window", "basis", "all_in", "allocation_usd", "return_period",
                              "activation_prob", "n_activations", "analysis_years", "triggered", "triggered_on"],
                         {"allocation_usd": _m,
                          "return_period": lambda v: f"1-in-{v:.1f} yr" if v is not None else "",
                          "activation_prob": lambda v: f"{v * 100:.0f}%" if v is not None else "",
                          "all_in": lambda v: "all-in" if v else "",
                          "triggered": lambda v: "triggered" if v else "not triggered"}))

    # real activations
    av = [{**x, "kind": ("non-framework allocation" if x["event_type"] == "adhoc_aa" else
                         "activation of the earlier, replaced framework" if x["replaced_framework"] else
                         "framework activation"),
           "people_reached": sum(f.get("people_reached") or 0 for f in x["funding"]) or None}
          for x in mine(a_rows)]
    out.append("## Activations\n")
    if av:
        out.append("Framework activations and non-framework allocations (anticipatory money allocated "
                   "without a framework). `people_reached`: CERF's figure for the allocation, where "
                   "reported (an allocation shared by several activations is counted on the earliest).\n")
    out.append(_md_table(av, ["event_date", "kind", "window_name", "version", "people_targeted", "people_reached",
                              "fund_codes", "amount_usd"],
                         {"amount_usd": _m, "people_targeted": lambda v: f"{int(v):,}" if v is not None else "",
                          "people_reached": lambda v: f"{int(v):,}" if v is not None else ""}))

    # simulated
    sv = [x for x in mine(s_rows) if x.get("in_backtest")]
    if sv:
        out.append("## Historical simulation (years the trigger would have activated)\n\n"
                   "Years before each version took effect; from then on only real activations count.\n")
        by_v = {}
        for x in sv:
            by_v.setdefault(x["version"], []).append(x)
        for v, rows in sorted(by_v.items()):
            items = sorted({(x["event_year"], x["window_name"] or "", x["event_label"] or "") for x in rows})
            out.append(f"- version {v}" + (" (the earlier, replaced framework)" if v in gone else "") + ": " + "; ".join(
                f"{y} {w}" + (f" ({lab})" if lab else "") for y, w, lab in items))
        out.append("")

    # plan
    pv = mine(pl)
    if pv:
        out.append(f"## Activities: pre-arranged budget by agency and sector (version {pv[0]['version']})\n\n"
                   f"OCHA-managed money only; total {_m(sum(x['amount_usd'] or 0 for x in pv))}.\n")
        pcols = ["agency", "sector", "fund_code", "amount_usd"]
        if any(x.get("window_name") for x in pv):
            pcols.insert(0, "window_name")
        out.append(_md_table(sorted(pv, key=lambda x: (x.get("agency") or "", -(x["amount_usd"] or 0))),
                             pcols, {"amount_usd": _m}))
    pall = mine(pt_rows)
    ptv = [x for x in pall if version and str(x["version"]) == version]
    p_label = version
    if not ptv and pall:
        p_label = sorted({str(x["version"]) for x in pall})[-1]
        ptv = [x for x in pall if str(x["version"]) == p_label]
    if ptv:
        out.append(f"## Partners named in the framework document (version {p_label}"
                   + (", the earlier, replaced framework's" if p_label in gone else "") + ")\n\n"
                   "`amount_usd` is the budget the document attaches to the organisation and can include "
                   "its own co-financing; the activities table above is the OCHA-managed share.\n")
        out.append(_md_table(ptv, ["name", "acronym", "org_type", "roles", "agency_parent", "amount_usd"], {"amount_usd": _m}))

    # funding by year × fund
    pf = mine(p_rows)
    if pf:
        out.append("## Pre-arranged funding in place, by year and fund\n\nA stock: the envelope standing each year, "
                   "not added up across years. `layer` retired: the money of an earlier, replaced framework.\n")
        out.append(_md_table(pf, ["year", "version", "fund_code", "financier", "amount_usd", "source", "layer"],
                             {"amount_usd": _m}))
    cf = mine(c_rows)
    if cf:
        out.append("## Co-financing, by year\n\nOutside the OCHA-managed funds; a stock as reported for each year, "
                   "never added to the pre-arranged money.\n")
        out.append(_md_table(cf, ["year", "version", "financier", "amount_usd", "source"], {"amount_usd": _m}))

    # versions
    out.append("## Versions\n\n`status`: endorsed, development (not yet endorsed) or retired. `return_period`: "
               "the version's overall return period (stated in the framework where it states one, otherwise "
               "from the historical simulation). `read`: the structured read of the version's document; "
               "`text`: the document's full text.\n")
    vs = [{**v, "status": (v["status"] or "") + (" (earlier framework, replaced)" if v["replaced_framework"] else ""),
           "return_period": (f"1-in-{v['return_period_years']:g} yr" if v.get("return_period_years") else "")
                            + (" (stated)" if v.get("return_period_basis") == "stated in the framework"
                               else " (simulation)" if v.get("return_period_basis") else "")}
          for v in vs]
    out.append(_md_table(vs, ["version", "status", "valid_from", "valid_until", "return_period", "document_title",
                              "document_url", "read", "text"],
                         {"read": lambda v: v or "", "text": lambda v: ", ".join(v) if v else ""}))

    # learning
    docs = [x for x in ld if x.get("country_iso3") == c and (x.get("hazard") in (None, h))]
    if docs:
        out.append(f"## Learning documents ({len(docs)})\n")
        for x in docs:
            line = f"- **{x['title']}**" + (f" ({x['publisher']}, {x['year']})" if x.get("publisher") else (f" ({x['year']})" if x.get("year") else ""))
            if x.get("url"):
                line += f" — {x['url']}"
            if x.get("summary"):
                line += f"\n  {x['summary']}"
            if x.get("key_stat"):
                line += f"\n  Key statistic: {x['key_stat']}"
            out.append(line)
        out.append("")
    return "\n".join(out)


# the tiles aa-map.md states (a tile the map gains is warned about: _map_field_alarm)
MAP_TILES = ("t-fw", "t-pre", "t-cof", "t-cov", "t-act", "t-reach")
# open pages that hold words only, no figures: no data file to give them
WORDS_ONLY = {"definitions.html", "accessibility.html", "privacy.html"}


def _map_keys(om):
    """The fields the open map's data carries, by level (open_map_fields.MAP_FIELDS's levels)."""
    seen = {"country": set(), "fw": set(), "hist": set(), "version": set(), "activation": set(), "funding": set()}
    for cd in om["countries"].values():
        seen["country"] |= set(cd)
        for f in cd["fws"]:
            seen["fw"] |= set(f)
            seen["hist"] |= set(f.get("hist") or {})
            for v in f.get("versions") or []:
                seen["version"] |= set(v)
            for a in f.get("activations") or []:
                seen["activation"] |= set(a)
                for x in a.get("funding") or []:
                    seen["funding"] |= set(x)
    return seen


def _map_field_alarm(om):
    """Warn when the open map shows something the open layer does not describe: a field of its data
    with no line in open_map_fields (aa-map-data.json carries it already, llms.txt cannot explain it),
    a headline figure, or a tile that aa-map.md does not state. The way a change to the map reaches
    the open layer: the warning names what to add."""
    import open_map_fields as F
    seen = _map_keys(om)
    new = [f"{lv}.{k}" for lv, ks in seen.items() for k in sorted(ks)
           if k not in F.MAP_FIELDS[lv] and k not in F.OMIT.get(lv, set())]
    new += [f"headline.{k}" for k in sorted(set(om.get("tiles") or {}) - set(F.TILE_FIELDS))]
    if new:
        print(f"::warning::open layer: the map's data has field(s) llms.txt does not describe yet: {', '.join(new)} "
              "— add a line for each to scripts/open_map_fields.py (aa-map-data.json carries them already)")
    tiles = sorted(set(om.get("notes") or {}) - set(MAP_TILES))
    if tiles:
        print(f"::warning::open layer: the map has tile(s) aa-map.md does not state: {', '.join(tiles)} "
              "— add them to llm_layer._map_md and MAP_TILES")


def _clean(v):
    """Strict JSON: NaN and infinities become null (the page's script accepts them, JSON does not)."""
    if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
        return None
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    return v


def _map_data(om, snapshot_at, stamp):
    """aa-map-data.json: the open map's own data (landing.OPEN_MAP: the copy the open page embeds,
    without the figures it withholds), minus the fields that only draw the map, with its headline
    figures. Whatever the map shows is here, without the open layer having to know of it."""
    import open_map_fields as F
    countries = {}
    for iso, cd in sorted(om["countries"].items()):
        c = {k: v for k, v in cd.items() if k not in F.OMIT["country"]}
        c["fws"] = [{k: v for k, v in f.items() if k not in F.OMIT["fw"]} for f in cd["fws"]]
        countries[iso] = c
    obj = {"title": "The open map's data",
           "description": "Exactly what the map's page carries (without the drawing): every country, framework, "
                          "version and activation, the country panels, the year selector's past years and the "
                          "headline figures as the map opens. Every field is described in llms.txt, under "
                          "\"The map's data\".",
           "generated": stamp, "snapshot_at": snapshot_at or None, "caveat": CAVEAT, "site": SITE_URL,
           "dictionary": SITE_URL + "llms.txt", "year": om["year"],
           "headline": om["tiles"], "headline_non_framework": om.get("adhoc"), "countries": countries}
    return json.dumps(_clean(obj), ensure_ascii=False, default=str, allow_nan=False)


def _map_dictionary(om):
    """The dictionary of aa-map-data.json, for llms.txt: the fields the map's data carries today."""
    import open_map_fields as F
    seen = _map_keys(om)
    out = ["One JSON object: `year`; `headline` (the headline figures as the map opens, for the current year, "
           "on the current-frameworks layer) and `headline_non_framework` (the same figures for the non-framework "
           "allocations of the year); `countries` {ISO3: country}. Amounts in US dollars as recorded (not "
           "rounded). Fields by level:\n"]
    for lv, path in (("country", "countries.ISO3"), ("fw", "countries.ISO3.fws[] (one per pair)"),
                     ("hist", "fws[].hist"), ("version", "fws[].versions[]"), ("activation", "fws[].activations[]"),
                     ("funding", "fws[].activations[].funding[]")):
        out.append(f"**{path}**\n")
        out += [f"- `{k}`: {d}" for k, d in F.MAP_FIELDS[lv].items() if k in seen[lv]]
        out.append("")
    out.append("**headline**\n")
    out += [f"- `{k}`: {d}" for k, d in F.TILE_FIELDS.items() if k in (om.get("tiles") or {})]
    return "\n".join(out) + "\n"


def _portfolio_md(fw_rows, y_rows, md_pages, snapshot_at, stamp, gaps=(), unsplit=(), rules=""):
    out = [_head("OCHA anticipatory action — the portfolio", snapshot_at, stamp)]
    live = [r for r in fw_rows if r["lifecycle"] in ("active", "updating", "development")]
    out.append(f"{len(fw_rows)} framework (country, hazard) pairs tracked; "
               f"{sum(r['lifecycle'] == 'active' for r in fw_rows)} active, "
               f"{sum(r['lifecycle'] == 'updating' for r in fw_rows)} being updated, "
               f"{sum(r['lifecycle'] == 'development' for r in fw_rows)} in development "
               f"({len(live)} live); the rest are in the pipeline (conversations only) or retired.\n")
    env = [r for r in fw_rows if r.get("prearranged_usd")]
    if env:
        year = env[0]["prearranged_year"]
        total = sum(r["prearranged_usd"] for r in env)
        cerf = sum(r["prearranged_cerf_usd"] or 0 for r in env)
        dev = sum(r["prearranged_usd"] for r in env if r["lifecycle"] == "development")
        out.append(f"**Pre-arranged funding in place in {year}: {_m(total)}** across {len(env)} live "
                   f"frameworks (CERF {_m(cerf)}; Country and Regional Funds {_m(total - cerf)})."
                   f" This is the one headline figure: the sum of `prearranged_usd` below, of the {year} rows "
                   f"of aa-prearranged-funding and of the {year} row of the annual table. It is the envelope "
                   f"standing for the year (for each live framework, that of its most recent version that "
                   f"has one), not what remains after this year's activations"
                   + (f", and it includes {_m(dev)} for frameworks still in development" if dev else "") + "."
                   + (" It counts twice the envelopes of " + ", ".join(
                       f"{r['country_name']} {r['hazard'].replace('_', ' ')}" for r in env if (r.get("activations_per_year") or 1) > 1)
                      + ", whose versions allow two activations a year (the budget per activation is half)."
                      if any((r.get("activations_per_year") or 1) > 1 for r in env) else "")
                   + (f" Live frameworks with no recorded envelope: {', '.join(gaps)}." if gaps else "") + "\n")
    out.append(rules)
    out.append("## Frameworks\n\n`current_version`: the latest version not in development; `valid_until` is its "
               "end of validity. `prearranged_usd`: pre-arranged funding in place now, all funds.\n")
    out.append(_md_table(fw_rows, ["country_name", "country_iso3", "hazard", "region", "lifecycle", "latest_version",
                                   "latest_version_status", "current_version", "valid_until", "return_period_years",
                                   "prearranged_usd", "prearranged_cerf_usd", "activations_per_year",
                                   "cofinancing_usd", "people_covered", "page_markdown"],
                         {"prearranged_usd": _m, "prearranged_cerf_usd": _m, "cofinancing_usd": _m,
                          "people_covered": lambda v: f"{int(v):,}" if v is not None else "",
                          "hazard": lambda v: (v or "").replace("_", " ")}))
    out.append("## Pre-arranged and released funding by year\n\n"
               "Pre-arranged is the stock standing that year (current and retired frameworks); released is "
               "what framework activations drew, and, in its own column, the non-framework allocations. They "
               "are not added together, and pre-arranged is not added across years. `retired_part`: how much "
               "of the two framework figures belongs to retired frameworks (the Financing page opens with "
               "that layer off). `framework_money_by_fund` breaks the two framework figures down by fund: "
               "its amounts are parts of those figures, not additions to them.\n")
    years = sorted({r["year"] for r in y_rows})
    funds = sorted({r["fund_code"] for r in y_rows}, key=lambda f: (f != "cerf", f))
    s_ = lambda rows, col: sum(r[col] or 0 for r in rows)      # noqa: E731
    tot = []
    for y in years:
        rows = [r for r in y_rows if r["year"] == y]
        fwr = [r for r in rows if r["layer"] != "non_framework"]
        ret = [r for r in rows if r["layer"] == "retired"]
        tot.append({"year": y,
                    "prearranged_usd": s_(fwr, "prearranged_usd"),
                    "released_framework_usd": s_(fwr, "released_usd"),
                    "released_non_framework_usd": s_([r for r in rows if r["layer"] == "non_framework"], "released_usd"),
                    "retired_part": (f"{_m(s_(ret, 'prearranged_usd'))} pre-arranged, {_m(s_(ret, 'released_usd'))} released"
                                     if ret else ""),
                    "framework_money_by_fund": "; ".join(
                        f"{f}: {_m(s_([r for r in fwr if r['fund_code'] == f], 'prearranged_usd'))} pre-arranged, "
                        f"{_m(s_([r for r in fwr if r['fund_code'] == f], 'released_usd'))} released"
                        for f in funds if any(r["fund_code"] == f for r in fwr))})
    out.append(_md_table(tot, ["year", "prearranged_usd", "released_framework_usd", "released_non_framework_usd",
                               "retired_part", "framework_money_by_fund"],
                         {"prearranged_usd": _m, "released_framework_usd": _m, "released_non_framework_usd": _m}))
    rel = lambda keep: sum(r["released_usd"] or 0 for r in y_rows if r["layer"] in keep)      # noqa: E731
    ry = sorted({r["year"] for r in y_rows if r["released_usd"]})
    if ry:
        span = f"{ry[0]}–{ry[-1]}"
        out.append(f"Released {span}, by the Financing page's layers: {_m(rel(('current', 'non_framework')))} as the "
                   f"page opens (current frameworks and non-framework allocations); "
                   f"{_m(rel(('current', 'retired', 'non_framework')))} with the retired layer too; "
                   f"{_m(rel(('current', 'retired')))} framework activations only.\n")
    if unsplit:
        out.append("The Financing page's annual chart stacks pre-arranged money by fund and so leaves out what "
                   "was recorded with no fund split (`fund_code` all), which the figures above include: "
                   + "; ".join(f"{_m(a)} for {lab} in {y}" for y, lab, a in sorted(unsplit)) + ".\n")
    out.append("## Framework pages\n")
    for name, title, sub in md_pages:
        out.append(f"- [{title}]({SITE_URL}{name}): {sub}")
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------- the documents
def _doc_reads(e, out, snapshot_at, stamp):
    """doc-<kb_framework>-<version>.md: the page body of every version page, minus the working
    sections. Returns (kb_framework, version) -> file name."""
    try:
        pages = pd.read_sql(
            """SELECT p.kb_framework, p.version::text AS version, p.body_md, p.country_iso3, p.hazard,
                      fm.doc_url, fm.doc_title
               FROM aa.version_page p
               LEFT JOIN LATERAL (
                   SELECT doc_url, doc_title FROM aa.framework_version f
                   WHERE f.kb_framework = p.kb_framework AND f.version::text = p.version::text
                   LIMIT 1) fm ON true
               WHERE p.body_md IS NOT NULL AND length(p.body_md) > 0""", e)
    except Exception as exc:
        print(f"::warning::open layer: version pages unavailable ({exc.__class__.__name__}); no document reads")
        return {}
    bodies = {(r.kb_framework, r.version): _strip_sections(r.body_md) for r in pages.itertuples()}
    files = {k: f"doc-{k[0]}-{k[1]}.md" for k, b in bodies.items() if b.strip()}
    for r in pages.itertuples():
        fn = files.get((r.kb_framework, r.version))
        if not fn:
            continue
        body = _relink(bodies[(r.kb_framework, r.version)], r.kb_framework, files)
        countries = ", ".join(r.country_iso3) if isinstance(r.country_iso3, (list, tuple)) else str(r.country_iso3 or "")
        has_doc = isinstance(r.doc_url, str) and bool(r.doc_url)
        what = (("A structured read of the framework document by the OCHA data science team: the figures "
                 "carry the document's own page numbers as evidence.") if has_doc else
                ("This version has no published framework document yet: what follows is the OCHA data "
                 "science team's working record of the framework as it stands (its analysis, trigger "
                 "design and status), not a read of an endorsed document."))
        head = (f"> {CAVEAT}\n>\n> {what} Framework {r.kb_framework} "
                f"({countries}, {r.hazard or ''}), version {r.version}."
                + (f" Official document: {r.doc_url}" if has_doc else "")
                + (f"\n>\n> Data snapshot {snapshot_at} UTC · generated {stamp}" if snapshot_at else f"\n>\n> Generated {stamp}")
                + f" · framework page: {SITE_URL}fw-{(r.country_iso3[0] if isinstance(r.country_iso3, (list, tuple)) and r.country_iso3 else '').lower()}-{r.hazard}.md"
                + f" · index: {SITE_URL}llms.txt\n\n")
        # the body starts with its own H1; keep it first
        m = re.match(r"\s*(# .*?\n)", body)
        text = (m.group(1) + "\n" + head + body[m.end():].lstrip("\n")) if m else head + body
        (out / fn).write_text(text)
    return files


_REL_LINK = re.compile(r"\[([^\]]*)\]\((?!https?:|#|mailto:)([^)\s]+)\)")


def _relink(body, kb_fw, files):
    """A version page's relative links point into the knowledge base it was written in. Here a
    link to another version's page becomes that version's document read; any other relative
    link keeps its text and loses its target, so the open layer carries no dead links."""
    def sub(m):
        text, target = m.group(1), m.group(2).split("#")[0]
        s = re.fullmatch(r"(?:\./)?(?:\.\./([a-z0-9-]+)/)?([^/]+)\.md", target)
        fn = files.get((s.group(1) or kb_fw, s.group(2))) if s else None
        return f"[{text}]({SITE_URL}{fn})" if fn else text
    return _REL_LINK.sub(sub, body)


def _strip_sections(body):
    """The page body without its working sections (DROP_SECTIONS) and section markers."""
    parts = re.split(r"(?m)^(?=## )", body)
    keep = []
    for part in parts:
        m = re.match(r"## +(.+?)\s*$", part, re.M)
        title = m.group(1).strip() if m else ""
        if title in DROP_SECTIONS or title.startswith("--- section"):
            continue
        keep.append(part)
    text = re.sub(r"(?m)^#+ +--- section.*$\n?", "", "".join(keep))
    # the body points into the frontmatter's working notes (`extra.*`), which stay in the
    # database: an aside "(see `extra.x`)" goes, any other mention says what it was
    text = re.sub(r"\s*\((?:see|captured in)\s+`extra\.[\w.*]+`\)", "", text)
    text = re.sub(r",\s*see\s+`extra\.[\w.*]+`(?=\))", "", text)
    return re.sub(r"`extra\.[\w.*]+`", "a working note (not published)", text)


def _pdf_texts(e, out):
    """pdf-<sha256>.txt for every current, public, registered framework document: the archived
    PDF's text page by page (pypdf), from the blob archive, cached under PDF_CACHE by content
    hash (a file never changes, so the file carries no date and the published site sees no churn).
    Returns (sha -> file name, (iso3, hazard, version) -> [doc])."""
    try:
        docs = pd.read_sql(
            """SELECT v.country_iso3, v.hazard, v.version::text AS version, v.role, v.official_url,
                      d.sha256, d.blob_path, d.title, d.language, d.bytes
               FROM aa.version_document v
               JOIN aa.framework_document d USING (sha256)
               WHERE d.is_public AND v.superseded_by IS NULL
               ORDER BY v.country_iso3, v.hazard, v.version""", e)
    except Exception as exc:
        print(f"::warning::open layer: document registry unavailable ({exc.__class__.__name__}); no document texts")
        return {}, {}
    links = {}
    for r in docs.itertuples():
        links.setdefault((r.country_iso3, r.hazard, r.version), []).append(
            {"sha256": r.sha256, "role": r.role, "title": _cell(r.title), "language": _cell(r.language),
             "official_url": _cell(r.official_url)})
    if os.environ.get("OPEN_LAYER_NO_PDF"):
        print("  open layer: document texts skipped (OPEN_LAYER_NO_PDF)")
        return {}, links
    PDF_CACHE.mkdir(parents=True, exist_ok=True)
    files, failed = {}, []
    for sha, grp in docs.groupby("sha256", sort=False):
        cache = PDF_CACHE / f"{sha}.txt"
        if not cache.exists():
            try:
                text = _extract_pdf(grp.iloc[0]["blob_path"])
            except Exception as exc:
                failed.append(f"{sha[:12]} ({grp.iloc[0]['country_iso3']} {grp.iloc[0]['hazard']}): {exc.__class__.__name__}")
                continue
            cache.write_text(text)
        serves = "; ".join(f"{x.country_iso3} {x.hazard} version {x.version} ({x.role})" for x in grp.itertuples())
        urls = sorted({u for u in grp["official_url"] if isinstance(u, str) and u})
        title = next((t for t in grp["title"] if isinstance(t, str) and t), None)
        lang = next((t for t in grp["language"] if isinstance(t, str) and t), None)
        head = (f"{title or 'Anticipatory action framework document'}\n"
                f"{'=' * len(title or 'Anticipatory action framework document')}\n\n"
                f"{CAVEAT}\n\n"
                f"Full text of the framework document, page by page, as extracted from the PDF (tables and "
                f"figures come out flattened; the structured read is the better source for figures). "
                f"Serves: {serves}." + (f" Language: {lang}." if lang else "")
                + (" Official page(s): " + ", ".join(urls) + "." if urls else "")
                + f" Content hash (sha256): {sha}. Index: {SITE_URL}llms.txt\n\n")
        fn = f"pdf-{sha}.txt"
        (out / fn).write_text(head + cache.read_text())
        files[sha] = fn
    if failed:
        print("::warning::open layer: document text not extracted for " + "; ".join(failed))
    return files, links


def _extract_pdf(blob_path):
    import io

    import ocha_stratus as stratus
    from pypdf import PdfReader

    data = stratus.load_blob_data(blob_path, stage="dev", container_name="projects")
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for i, page in enumerate(reader.pages, 1):
        t = (page.extract_text() or "").strip()
        pages.append(f"--- page {i} ---\n{t}\n")
    return "\n".join(pages)
