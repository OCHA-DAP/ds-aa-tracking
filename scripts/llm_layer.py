"""The open, machine-readable layer of the public site: what an LLM (or any fetch-based
tool) reads, since the HTML pages are encrypted with a password it cannot type.

Written by write_site() next to the encrypted pages, never encrypted, regenerated on every
build (so the nightly publish keeps it current):

- llms.txt            the index: what the site is, the caveat, the counting rules, every file
- llms-full.txt       every Markdown page in one file
- aa-portfolio.md     the portfolio: one row per framework, the annual funding series
- fw-<iso3>-<hazard>.md   one page per PUBLIC framework page (the map's), same slug as the HTML
- fw-<iso3>-<hazard>.md   one page per framework (every pair the registry tracks; the HTML
                          link only where the map opens a page)
- doc-<kb_framework>-<version>.md   the structured read of each version's framework document
                          (aa.version_page body: summary, method, trigger logic and windows,
                          monitoring, decisions, changes, activations — the working sections
                          on sources and open questions stay in the database)
- pdf-<sha256>.txt        the full text of each registered public framework document
                          (aa.framework_document, extracted with pypdf from the blob archive,
                          cached under data/framework_documents/)
- aa-<name>.json / .csv   the tables behind the pages (one JSON object with the rows and the
                          stamps, every row carrying every column; the CSV is the same rows)
- robots.txt, sitemap.xml (the open files first; the encrypted pages last)

A reader that knows nothing about the site has to be able to use it (tested 2026-10-09 with
readers given only the URL): the figures agree across files to the dollar (pre-arranged money
now is dashboards.prearranged_now everywhere), a coded window name carries the document's name
for it, no link is dead, and publish.sh makes the password page point at llms.txt.

Everything the database holds about the portfolio goes in (2026-10-08: "make everything
visible to LLMs that we can"), except people and working material: never focal points, the
version pages' working notes (frontmatter `extra`, raw extracts, QA notes, the sources and
open-questions sections of the page body), the version records' provenance notes, activation
comments, partner evidence, documents registered as private, internal learning documents
(already filtered at the source).
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

RULES = """\
Counting rules (an LLM summing these files without them gets wrong totals):

- Pre-arranged funding is a STOCK: the envelope in place for a framework in a given year.
  Never add it across years, and never add it to released money. "Pre-arranged in 2026" is
  the sum over frameworks of the 2026 rows only. The current year's figure comes from the
  framework records (source `framework-record`): for each live framework, the envelope of its
  most recent version that has one, all funds. `prearranged_usd` in aa-frameworks is that same
  figure per framework, and the portfolio page's headline is its sum. Past years keep the
  reported series. It is not reduced by what activations released during the year.
- Released money is what activations drew: the `funding` rows of aa-activations. The
  Financing page's released series counts framework activations (`event_type` =
  `framework_aa`) only; ad hoc AA allocations (`adhoc_aa`) are listed but shown separately.
  Early action allocations are not anticipatory action and are not in these files.
- CBPF and regional-fund pre-arranged money comes from the OneGMS allocation mirror
  (source `onegms-mirror`); hand-tracked CBPF rows are kept only for country-years the
  mirror does not cover, so the same money is never counted twice.
- A framework is one (country, hazard) pair. Regional frameworks do not exist: the Central
  America Dry Corridor is four national frameworks (El Salvador, Guatemala, Honduras and the
  retired Nicaragua), even where a document title calls it regional or one document serves
  several of them.
- A framework version is one framework document: `endorsed`, or `development` while it is
  still being written. `lifecycle` says where the framework stands today: active, updating,
  development, pipeline or retired (defined under Vocabulary). Count frameworks by
  `lifecycle`, not by `status`.
- A trigger window has two return periods and they can differ: the one its document states
  (aa-trigger-windows, free text) and the one from the historical simulation (backtest) of
  the trigger (aa-windows, `return_period` in years, with the activation probability).
- Activations also include ad hoc anticipatory allocations for hazards and countries that
  have no framework; they have no version and no window.
"""


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


# ---------------------------------------------------------------------- the build
def build(d, e, public, out, snapshot_at):
    """Write the layer into `out`; return the set of file names written."""
    import dashboards

    stamp = date.today().isoformat()
    pages = _slug_pairs(public)                 # (iso3, hazard) -> fw-xxx.html (the map's)
    written = set()
    files = []                                   # (name, description, columns) for llms.txt

    def write_table(name, rows, desc):
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
    kb_of = {(r.country_iso3, r.hazard): r.kb_framework for r in cur.itertuples()
             if isinstance(r.kb_framework, str)}
    name_of = dict(zip(cur["country_iso3"], cur["country_name"]))

    # ---- the documents: structured reads (version pages) and the archived PDFs' text
    reads = _doc_reads(e, out, snapshot_at, stamp)          # (kb_framework, version) -> file
    texts, doc_links = _pdf_texts(e, out)                   # sha -> file; (c, h, v) -> [{...}]
    written.update(reads.values())
    written.update(texts.values())

    # ---- funding: the annual series the Financing page charts. Its current-year rows are
    # pre-arranged money NOW (dashboards.prearranged_now, the one definition every page uses);
    # the registry rows below carry the same figure, so every file agrees to the dollar.
    pre, act = dashboards.funding_series(d)
    pre = pre[pre["kind"] == "prearranged"].copy()
    pre["source"] = [x if x in ("framework-record", "onegms-mirror", "version-inferred") else "tracking-sheets"
                     for x in pre["source"].astype(str)]
    now_year = date.today().year
    now = pre[(pre["year"] == now_year) & (pre["source"] == "framework-record")]
    now_all = now.groupby(["country_iso3", "hazard"])["amount_usd"].sum().to_dict()
    now_cerf = now[now["fund_code"] == "cerf"].groupby(["country_iso3", "hazard"])["amount_usd"].sum().to_dict()
    now_ver = {(x.country_iso3, x.hazard): str(x.version) for x in d["vfund"].itertuples()}

    # ---- frameworks: every pair the registry tracks (the map shows the pipeline ones as points)
    fw_rows = []
    for r in cur.itertuples():
        page = pages.get((r.country_iso3, r.hazard))
        pair = (r.country_iso3, r.hazard)
        fw_rows.append({
            "country_iso3": r.country_iso3, "country_name": r.country_name, "region": _cell(r.region),
            "hazard": r.hazard, "lifecycle": _cell(r.lifecycle), "status": _cell(r.status),
            "retired": bool(r.retired), "technical_support": bool(r.technical_support),
            "latest_version": _cell(r.latest_version), "latest_version_status": _cell(r.latest_status),
            "current_version": _cell(r.current_version), "valid_until": _cell(r.valid_until),
            "n_windows": _cell(r.n_windows), "n_windows_triggered": _cell(r.n_triggered),
            "fully_triggered": bool(r.fully_triggered) if pd.notna(r.fully_triggered) else None,
            "prearranged_usd": _cell(now_all.get(pair)),
            "prearranged_cerf_usd": _cell(now_cerf.get(pair)) if pair in now_all else None,
            "prearranged_year": now_year if pair in now_all else None,
            "prearranged_version": now_ver.get(pair) if pair in now_all else None,
            "people_covered": _cell(r.people_covered),
            "page_html": SITE_URL + page if page else None,
            "page_markdown": SITE_URL + f"fw-{r.country_iso3.lower()}-{r.hazard}.md",
        })
    write_table("frameworks", fw_rows,
                "The framework registry: one row per (country, hazard) pair the portfolio tracks, "
                "with its lifecycle, latest version, the pre-arranged funding in place now "
                "(`prearranged_usd`, all funds; `prearranged_cerf_usd` its CERF part; the envelope of "
                "`prearranged_version`; these sum to the current-year rows of aa-prearranged-funding and "
                "aa-funding-annual) and people covered, and the link to its Markdown page (an HTML page "
                "exists only where the map opens one).")

    # ---- versions: the registry rows + the page fields + the document links
    v_rows, trig_rows, trig_table, trig_of = [], [], [], {}   # trig_rows: the document's own keys (pages)
    vv = fvm.copy()
    vv["_vf"] = pd.to_datetime(vv["valid_from"].astype(str), errors="coerce")
    kbs = d["versions"].set_index(["country_iso3", "hazard", d["versions"]["version"].astype(str)])
    for r in vv.sort_values(["country_iso3", "hazard", "_vf"]).itertuples():
        key = (r.country_iso3, r.hazard, str(r.version))
        kb_status = _cell(kbs.loc[key, "kb_status"]) if key in kbs.index else None
        facts, trig = _version_facts(vpage, r.kb_framework, r.version)
        row = {"country_iso3": r.country_iso3, "hazard": r.hazard, "version": str(r.version),
               "status": kb_status, "valid_from": _cell(r.valid_from), "valid_until": _cell(r.valid_until),
               "document_title": _cell(r.doc_title), "document_url": _cell(r.doc_url),
               "analysis_ref": _cell(r.analysis_ref),
               "document_read": (SITE_URL + reads[(r.kb_framework, str(r.version))]
                                 if (r.kb_framework, str(r.version)) in reads else None),
               "document_text": [SITE_URL + texts[x["sha256"]] for x in doc_links.get(key, []) if x["sha256"] in texts] or None}
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
                "Every registered version of every framework (`status`: an endorsed document, one still "
                "in development, or a retired one): validity, the document "
                "(its official page, its structured read `document_read`, its full text "
                "`document_text`), and the version's scope, trigger basis, indicators, data sources, "
                "monitoring months and implementing agencies.")
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

    # ---- real activations (every framework and ad hoc): one row per event, funding nested
    fund = d["activation"]
    a_rows = []
    for r in d["act_all"].sort_values("event_date", ascending=False).itertuples():
        wn = r.window_name if isinstance(r.window_name, str) else None
        lab = r.event_label if isinstance(r.event_label, str) else ""
        f = fund[(fund["country_iso3"] == r.country_iso3) & (fund["hazard"] == r.hazard)
                 & (fund["event_date"].astype(str) == str(r.event_date))
                 & (fund["event_type"] == r.event_type)
                 & (fund["window_name"].fillna("") == (wn or ""))]
        rows = [{"fund_code": x.fund_code, "allocation_code": _cell(x.allocation_code),
                 "amount_usd": _cell(x.amount_usd)} for x in f.itertuples()]
        a_rows.append({"country_iso3": r.country_iso3, "country_name": name_of.get(r.country_iso3),
                       "hazard": r.hazard, "event_type": r.event_type, "event_date": _cell(r.event_date),
                       "window_name": wn, "event_label": lab or None,
                       "version": _cell(r.version), "people_targeted": _cell(r.people_targeted),
                       "amount_usd": sum(x["amount_usd"] or 0 for x in rows) if rows else None,
                       "fund_codes": "; ".join(sorted({x["fund_code"] for x in rows})) or None,
                       "funding": rows})
    write_table("activations", a_rows,
                "Every real activation since 2020: framework activations (event_type framework_aa) "
                "and ad hoc anticipatory allocations (adhoc_aa), with the money each drew per fund "
                "(`funding`; `amount_usd` is their sum). Early action is not included.")

    # ---- funding tables (the series computed above)
    p_rows = _records(pre.sort_values(["year", "country_iso3", "hazard", "fund_code"]),
                      ["country_iso3", "hazard", "year", "fund_code", "financier", "amount_usd", "source", "in_gho"])
    write_table("prearranged-funding", p_rows,
                "Pre-arranged funding in place per framework, year and fund: a STOCK (the envelope "
                "standing that year), never summed across years. `source`: framework-record (the current "
                "envelope), onegms-mirror (pooled-fund allocations), tracking-sheets (the team's "
                "reported series), version-inferred (carried from the version in force). `in_gho`: "
                "the country was in that year's Global Humanitarian Overview.")
    act = act.copy()
    yr_pre = pre.groupby(["year", "fund_code"])["amount_usd"].sum()
    yr_rel = act.groupby(["year", "fund_code"])["amount_usd"].sum()
    keys = sorted(set(yr_pre.index) | set(yr_rel.index))
    y_rows = [{"year": int(y), "fund_code": fc,
               "prearranged_usd": _cell(yr_pre.get((y, fc))), "released_usd": _cell(yr_rel.get((y, fc)))}
              for y, fc in keys]
    write_table("funding-annual", y_rows,
                "The Financing page's series: per year and fund, the pre-arranged stock in place and "
                "the money released by framework activations. Do not add a year's pre-arranged to its "
                "released.")

    # ---- plan: agency × sector split of the live frameworks' current version
    pl = _records(d["plan_rows"].sort_values(["country_iso3", "hazard", "agency", "sector"]),
                  ["country_iso3", "country_name", "hazard", "version", "fund_code", "window_name",
                   "agency", "sector", "amount_usd"])
    for x in pl:
        if x.get("window_name") in ("single", "unattributed"):      # the split is not per window
            x["window_name"] = None
    write_table("plan-split", pl,
                "The pre-arranged budget of each live framework's latest version split by implementing "
                "agency and sector (the Plan page), per trigger window where the budget is per window "
                "(`window_name`; blank: the split is for the whole framework). OCHA-managed money only "
                "(`fund_code`), never an agency's own co-financing. A framework's rows add up to its "
                "budgeted split, which can differ by rounding from the envelope its document states "
                "(aa-prearranged-funding).")

    # ---- funds: what each fund_code used above is
    used = ({x["fund_code"] for x in p_rows} | {x["fund_code"] for x in pl}
            | {f["fund_code"] for a in a_rows for f in a["funding"]})
    try:
        fd = pd.read_sql("SELECT fund_code, fund_type, name, country_iso3 FROM aa.fund ORDER BY fund_code", e)
        write_table("funds", _records(fd[fd["fund_code"].isin(used)]),
                    "The funds behind every `fund_code` in these files: CERF, the country-based pooled "
                    "funds and the regional humanitarian pooled funds' country envelopes (`fund_type` "
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
    ld = _records(d["learning"], ["id", "title", "url", "publisher", "year", "doc_type", "scope",
                                  "country_iso3", "hazard", "premises", "key_stat", "summary", "section"])
    write_table("learning", ld,
                "Learning products: after-action reviews, evaluations, activation reports, research "
                "and guidance, per framework or global, with a one-line summary and key statistic.")

    # ---- Markdown pages
    md_pages = []
    fw_of = {(x["country_iso3"], x["hazard"]): x for x in fw_rows}
    for r in cur.itertuples():
        page = pages.get((r.country_iso3, r.hazard))
        name = f"fw-{r.country_iso3.lower()}-{r.hazard}.md"
        text = _framework_md(d, r, fw_of[(r.country_iso3, r.hazard)], page, v_rows, trig_rows, w_rows,
                             s_rows, a_rows, p_rows, pl, pt_rows, ld, snapshot_at, stamp)
        (out / name).write_text(text)
        written.add(name)
        md_pages.append((name, f"{r.country_name} {r.hazard.replace('_', ' ')}",
                         f"{_cell(r.lifecycle) or ''}" + (f", version {r.latest_version}" if pd.notna(r.latest_version) else "")))
    portfolio = _portfolio_md(fw_rows, y_rows, md_pages, snapshot_at, stamp,
                              [f"{n} {h.replace('_', ' ')}" for n, h, _ in dashboards.envelope_gaps(d)])
    (out / "aa-portfolio.md").write_text(portfolio)
    written.add("aa-portfolio.md")

    # ---- llms.txt, llms-full.txt, robots.txt, sitemap.xml
    stamp_line = f"Data snapshot {snapshot_at} UTC; files generated {stamp}." if snapshot_at else f"Files generated {stamp}."
    idx = [f"# OCHA anticipatory action — portfolio tracking\n",
           f"> The tracking record of OCHA's anticipatory action (AA) portfolio: every framework "
           f"(a country and a hazard), its versions, triggers and trigger windows, pre-arranged "
           f"funding, activations and the money they released, implementing partners and learning "
           f"documents. Maintained by the data science team of OCHA's Centre for Humanitarian Data. {stamp_line}\n",
           f"**Caveat.** {CAVEAT}\n",
           f"The HTML pages at {SITE_URL} sit behind a password while the site is under review. The "
           f"data itself is public, and the Markdown pages and data files listed here are published "
           f"openly on purpose: they are the interface for programs and AI assistants, need no password "
           f"and carry the same figures as the pages. Every file is regenerated from the database with "
           f"each nightly publish.\n",
           RULES,
           "## Portfolio\n",
           f"- [Portfolio overview]({SITE_URL}aa-portfolio.md): every framework with its lifecycle, "
           f"latest version and envelope; the annual pre-arranged and released series.",
           f"- [Everything in one file]({SITE_URL}llms-full.txt): the portfolio page, every "
           f"framework page and every structured read of a framework document, concatenated (large).\n",
           "## Framework pages (one per framework, Markdown)\n"]
    for name, title, sub in md_pages:
        idx.append(f"- [{title}]({SITE_URL}{name}): {sub}")
    idx.append("\n## Framework documents\n")
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
    idx.append("\n## Data files\n\nJSON: one object with `rows`, `columns`, a `description` and the stamps; "
               "every row carries every column (null where empty). CSV: the same rows; a nested value is "
               "JSON in its cell, a plain list is joined with `; `.\n")
    for name, desc, cols in files:
        idx.append(f"- [aa-{name}.json]({SITE_URL}aa-{name}.json) · [CSV]({SITE_URL}aa-{name}.csv): {desc} "
                   f"Columns: {', '.join(cols)}.")
    idx.append("\n## Vocabulary\n")
    idx.append("- `country_iso3`: ISO 3166-1 alpha-3. `hazard`: drought, flood, storm, cholera, plague, "
               "food_insecurity for frameworks; ad hoc allocations in aa-activations also carry other "
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
               "technically, with no funding. `retired`: flagged as retired by hand.\n"
               "- version `status` (aa-versions): `endorsed`, `development` (not yet endorsed), `retired`. "
               "`document_text` is a list of URLs (a version can have several archived documents, such "
               "as language editions). `analysis_ref`: where the trigger analysis lives, as "
               "repository@branch:path in the OCHA-DAP GitHub organisation.\n"
               "- People: `people_covered` (aa-frameworks) the people the framework covers, as last "
               "reported by the team; `target_people` (aa-versions) the people the version's document "
               "targets; `people_targeted` (aa-activations) the people one activation targeted. They are "
               "three different figures.\n"
               "- `fund_code` (names in aa-funds): `cerf` the Central Emergency Response Fund; "
               "`cbpf-<iso3>` a country-based pooled fund, or a regional fund's envelope for that country "
               "where aa-funds says so; `rhpf-<region>-<iso3>` a regional humanitarian pooled fund's "
               "envelope for a country (`wca` West and Central Africa, `esa` Eastern and Southern "
               "Africa); `all` a pre-arranged total the source did not break down by fund; "
               "`cbpf-unspecified` a pooled fund the source did not name. `allocation_code`: the fund's "
               "own code for the allocation, as recorded (formats differ by fund and year; one allocation "
               "can serve several frameworks). `financier`: the fund's name where the source gave one.\n"
               "- `event_type`: `framework_aa` an activation of a framework's trigger; `adhoc_aa` an "
               "anticipatory allocation outside a framework.\n"
               "- Windows: `basis` is `forecast`, `observational` or `mixed` (what the trigger reads); "
               "`all_in`: one trigger releases the whole envelope. `window_name` in aa-windows, "
               "aa-activations and aa-simulated-activations is the name the tracking database records, "
               "which can be a short code of the backtest (wt1, wg2, ws); `document_window` in aa-windows "
               "gives the document's name for it where a one-to-one pairing is recorded.\n"
               "- Amounts are US dollars, to the dollar. Dates are ISO 8601. `event_date` keeps the "
               "precision recorded (YYYY, YYYY-MM or YYYY-MM-DD); `triggered_on`, `valid_from` and "
               "`valid_until` are full dates, so one known only to the month is written as its first day.\n")
    idx.append(f"\n## Related\n\n- Code and schema (public repository): https://github.com/OCHA-DAP/ds-aa-tracking\n"
               f"- OCHA anticipatory action: https://www.unocha.org/anticipatory-action\n"
               f"- CERF: https://cerf.un.org/\n")
    (out / "llms.txt").write_text("\n".join(idx))
    full = ([portfolio] + [(out / n).read_text() for n, _, _ in md_pages]
            + [(out / fn).read_text() for _, fn in sorted(reads.items())])
    (out / "llms-full.txt").write_text("\n\n---\n\n".join(full))
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}sitemap.xml\n")
    # the open files first (what a reader without the password can use), the pages last
    urls = ([SITE_URL + "llms.txt", SITE_URL + "llms-full.txt", SITE_URL + "aa-portfolio.md"]
            + [SITE_URL + n for n, _, _ in md_pages]
            + [SITE_URL + f"aa-{n}.{ext}" for n, _, _ in files for ext in ("json", "csv")]
            + [SITE_URL + fn for _, fn in sorted(reads.items())]
            + [SITE_URL + fn for _, fn in sorted(texts.items())]
            + [SITE_URL + n for n in sorted(public)])
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc><lastmod>{stamp}</lastmod></url>\n" for u in urls) + "</urlset>\n")
    written.update({"llms.txt", "llms-full.txt", "robots.txt", "sitemap.xml"})
    print(f"  open layer: {len(md_pages)} framework pages · {len(reads)} document reads · "
          f"{len(texts)} document texts · {len(files)} tables · llms.txt")
    return written


# ---------------------------------------------------------------------- Markdown pages
def _head(title, snapshot_at, stamp, html_page=None):
    s = f"Data snapshot {snapshot_at} UTC · generated {stamp}" if snapshot_at else f"Generated {stamp}"
    link = f" · HTML page (may require a password): {SITE_URL}{html_page}" if html_page else ""
    return (f"# {title}\n\n> {CAVEAT}\n>\n> {s} · index: {SITE_URL}llms.txt{link}\n\n")


def _framework_md(d, r, fw, page, v_rows, trig_rows, w_rows, s_rows, a_rows, p_rows, pl, pt_rows, ld,
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
        facts.append(f"**Pre-arranged funding in place ({fw['prearranged_year']}):** {_m(fw['prearranged_usd'])} ("
                     + "; ".join(f"{x['fund_code']} {_m(x['amount_usd'])}" for x in mine_now)
                     + f"), the envelope of version {fw['prearranged_version']}")
    if pd.notna(r.people_covered):
        facts.append(f"**People covered:** {int(r.people_covered):,}")
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
    out.append("## Trigger windows and backtest" + (f" (version {w_label})" if w_label else "")
               + (" — the latest version with a recorded backtest" if w_label != version else "") + "\n")
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
    av = mine(a_rows)
    out.append("## Activations\n")
    out.append(_md_table(av, ["event_date", "event_type", "window_name", "version", "people_targeted", "fund_codes", "amount_usd"],
                         {"amount_usd": _m, "people_targeted": lambda v: f"{int(v):,}" if v is not None else "",
                          "event_type": lambda v: (v or "").replace("_", " ")}))

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
            out.append(f"- version {v}: " + "; ".join(
                f"{y} {w}" + (f" ({lab})" if lab else "") for y, w, lab in items))
        out.append("")

    # plan
    pv = mine(pl)
    if pv:
        out.append(f"## Plan: pre-arranged budget by agency and sector (version {pv[0]['version']})\n\n"
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
        out.append(f"## Partners named in the framework document (version {p_label})\n\n"
                   "`amount_usd` is the budget the document attaches to the organisation and can include "
                   "its own co-financing; the plan table above is the OCHA-managed share.\n")
        out.append(_md_table(ptv, ["name", "acronym", "org_type", "roles", "agency_parent", "amount_usd"], {"amount_usd": _m}))

    # funding by year × fund
    pf = mine(p_rows)
    if pf:
        out.append("## Pre-arranged funding in place, by year and fund\n\nA stock: the envelope standing each year, not added up across years.\n")
        out.append(_md_table(pf, ["year", "fund_code", "financier", "amount_usd", "source"], {"amount_usd": _m}))

    # versions
    out.append("## Versions\n\n`status`: endorsed, development (not yet endorsed) or retired. `read`: the "
               "structured read of the version's document; `text`: the document's full text.\n")
    out.append(_md_table(vs, ["version", "status", "valid_from", "valid_until", "document_title", "document_url", "read", "text"],
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


def _portfolio_md(fw_rows, y_rows, md_pages, snapshot_at, stamp, gaps=()):
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
                   f"frameworks (CERF {_m(cerf)}; country-based and regional pooled funds {_m(total - cerf)})."
                   f" This is the one headline figure: the sum of `prearranged_usd` below, of the {year} rows "
                   f"of aa-prearranged-funding and of the {year} row of the annual table. It is the envelope "
                   f"standing for the year (for each live framework, that of its most recent version that "
                   f"has one), not what remains after this year's activations"
                   + (f", and it includes {_m(dev)} for frameworks still in development" if dev else "") + "."
                   + (f" Live frameworks with no recorded envelope: {', '.join(gaps)}." if gaps else "") + "\n")
    out.append(RULES)
    out.append("## Frameworks\n\n`current_version`: the latest version not in development; `valid_until` is its "
               "end of validity. `prearranged_usd`: pre-arranged funding in place now, all funds.\n")
    out.append(_md_table(fw_rows, ["country_name", "country_iso3", "hazard", "region", "lifecycle", "latest_version",
                                   "latest_version_status", "current_version", "valid_until", "prearranged_usd",
                                   "prearranged_cerf_usd", "people_covered", "page_markdown"],
                         {"prearranged_usd": _m, "prearranged_cerf_usd": _m,
                          "people_covered": lambda v: f"{int(v):,}" if v is not None else "",
                          "hazard": lambda v: (v or "").replace("_", " ")}))
    out.append("## Pre-arranged and released funding by year and fund\n\n"
               "Pre-arranged is the stock standing that year; released is what framework activations drew. "
               "They are not added together. `of_which_by_fund` breaks the two totals of the row down by "
               "fund: its amounts are parts of those totals, not additions to them.\n")
    years = sorted({r["year"] for r in y_rows})
    funds = sorted({r["fund_code"] for r in y_rows}, key=lambda f: (f != "cerf", f))
    tot = []
    for y in years:
        rows = [r for r in y_rows if r["year"] == y]
        tot.append({"year": y,
                    "prearranged_usd": sum(r["prearranged_usd"] or 0 for r in rows),
                    "released_usd": sum(r["released_usd"] or 0 for r in rows),
                    "of_which_by_fund": "; ".join(f"{f}: {_m(sum(r['prearranged_usd'] or 0 for r in rows if r['fund_code'] == f))} pre-arranged, "
                                         f"{_m(sum(r['released_usd'] or 0 for r in rows if r['fund_code'] == f))} released"
                                         for f in funds if any(r["fund_code"] == f for r in rows))})
    out.append(_md_table(tot, ["year", "prearranged_usd", "released_usd", "of_which_by_fund"],
                         {"prearranged_usd": _m, "released_usd": _m}))
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
    text = "".join(keep)
    return re.sub(r"(?m)^#+ +--- section.*$\n?", "", text)


def _pdf_texts(e, out):
    """pdf-<sha256>.txt for every current, public, registered framework document: the archived
    PDF's text page by page (pypdf), from the blob archive, cached under PDF_CACHE by content
    hash (a file never changes, so the file carries no date and gh-pages sees no churn).
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
