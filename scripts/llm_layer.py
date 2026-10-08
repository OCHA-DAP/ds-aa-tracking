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
                          stamps; the CSV is the same rows)
- robots.txt, sitemap.xml

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
  framework records (source `framework-record`); past years keep the reported series.
- Released money is what activations drew: the `funding` rows of aa-activations. The
  Financing page's released series counts framework activations (`event_type` =
  `framework_aa`) only; ad hoc AA allocations (`adhoc_aa`) are listed but shown separately.
  Early action allocations are not anticipatory action and are not in these files.
- CBPF and regional-fund pre-arranged money comes from the OneGMS allocation mirror
  (source `onegms-mirror`); hand-tracked CBPF rows are kept only for country-years the
  mirror does not cover, so the same money is never counted twice.
- A framework is one (country, hazard) pair. Regional frameworks do not exist: the Central
  America Dry Corridor is four national frameworks (El Salvador, Guatemala, Honduras and the
  retired Nicaragua) that share a document.
- A framework version is an endorsed document; `lifecycle` says whether the framework is
  active, being updated, in development, dormant or expired today.
- Return periods and activation probabilities are per trigger window of one version, from
  the historical simulation (backtest) of that version's trigger.
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
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else "; ".join(map(str, v))
    return "" if v is None else v


def _m(v):
    """USD for prose: $1.2M / $450k / $0."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    v = float(v)
    if abs(v) >= 1e6:
        return f"${v / 1e6:,.2f}M".replace(".00M", "M")
    if abs(v) >= 1e3:
        return f"${v / 1e3:,.0f}k"
    return f"${v:,.0f}"


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
    texts, doc_links = _pdf_texts(e, out, stamp)            # sha -> file; (c, h, v) -> [{...}]
    written.update(reads.values())
    written.update(texts.values())

    # ---- frameworks: every pair the registry tracks (the map shows the pipeline ones as points)
    fw_rows = []
    for r in cur.itertuples():
        page = pages.get((r.country_iso3, r.hazard))
        fw_rows.append({
            "country_iso3": r.country_iso3, "country_name": r.country_name, "region": _cell(r.region),
            "hazard": r.hazard, "lifecycle": _cell(r.lifecycle), "status": _cell(r.status),
            "retired": bool(r.retired), "technical_support": bool(r.technical_support),
            "latest_version": _cell(r.latest_version), "latest_version_status": _cell(r.latest_status),
            "current_version": _cell(r.current_version), "valid_until": _cell(r.valid_until),
            "n_windows": _cell(r.n_windows), "n_windows_triggered": _cell(r.n_triggered),
            "fully_triggered": bool(r.fully_triggered) if pd.notna(r.fully_triggered) else None,
            "cerf_prearranged_usd": _cell(r.cerf_prearranged_usd),
            "prearranged_year": _cell(r.prearranged_year),
            "people_covered": _cell(r.people_covered),
            "page_html": SITE_URL + page if page else None,
            "page_markdown": SITE_URL + f"fw-{r.country_iso3.lower()}-{r.hazard}.md",
        })
    write_table("frameworks", fw_rows,
                "The framework registry: one row per (country, hazard) pair the portfolio tracks, "
                "with its lifecycle, latest version, pre-arranged CERF envelope and people covered, "
                "and the link to its Markdown page (an HTML page exists only where the map opens one).")

    # ---- versions: the registry rows + the page fields + the document links
    v_rows, trig_rows = [], []
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
        for t in trig:
            if isinstance(t, dict):
                trig_rows.append({"country_iso3": r.country_iso3, "hazard": r.hazard,
                                  "version": str(r.version), **{str(k): v for k, v in t.items()}})
    write_table("versions", v_rows,
                "Every registered version (an endorsed framework document): validity, the document "
                "(its official page, its structured read `document_read`, its full text "
                "`document_text`), and the version's scope, trigger basis, indicators, data sources, "
                "monitoring months and implementing agencies.")
    write_table("trigger-windows", trig_rows,
                "The trigger windows as the framework document states them, per version: window, "
                "indicator, threshold, lead time, return period and what the window releases. Columns "
                "vary by framework (they are the document's own table).")

    # ---- windows and backtests
    w = d["windows"]
    w_rows = _records(w.sort_values(["country_iso3", "hazard", "version", "window_name"]),
                      ["country_iso3", "country_name", "hazard", "version", "is_latest", "window_name",
                       "basis", "all_in", "allocation_usd", "return_period", "activation_prob",
                       "n_activations", "analysis_years", "analysis_start", "analysis_end",
                       "triggered", "triggered_on"])
    write_table("windows", w_rows,
                "Trigger windows per version with their allocation and backtest: return period "
                "(years), annual activation probability, activations in the analysed years, and "
                "whether the window has triggered under the version in force.")

    # ---- simulated (historical) activations
    s = d["sim"]
    s_rows = _records(s.sort_values(["country_iso3", "hazard", "version", "event_year"]),
                      ["country_iso3", "hazard", "version", "window_name", "event_year",
                       "event_label", "event_date", "event_time", "time_precision"])
    write_table("simulated-activations", s_rows,
                "The historical simulation of each version's trigger: the years (and dates where "
                "known) in which a window would have activated. Rows from the year a version took "
                "effect onwards are not simulation: from then on only real activations count.")

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

    # ---- funding: the annual series the Financing page charts
    pre, act = dashboards.funding_series(d)
    pre = pre[pre["kind"] == "prearranged"].copy()
    pre["source"] = [x if x in ("framework-record", "onegms-mirror", "version-inferred") else "tracking-sheets"
                     for x in pre["source"].astype(str)]
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
                  ["country_iso3", "country_name", "hazard", "version", "fund_code", "agency", "sector", "amount_usd"])
    write_table("plan-split", pl,
                "The pre-arranged budget of each live framework's current version split by implementing "
                "agency and sector (the Plan page). A framework's rows sum to its envelope.")

    # ---- partners
    pt = d["partners"].copy()
    pt["roles"] = [[x for x in (r if isinstance(r, list) else []) if re.fullmatch(r"[a-z_]+", str(x))] or None
                   for r in pt["roles"]]
    pt_rows = _records(pt.sort_values(["country_iso3", "hazard", "org_type", "name"]),
                       ["country_iso3", "hazard", "version", "name", "acronym", "org_type", "roles",
                        "agency_parent", "amount_usd"])
    write_table("partners", pt_rows,
                "Organisations named in the endorsed framework documents (lead and implementing "
                "agencies, government bodies, NGOs), with their role and budget where the document "
                "states one.")

    # ---- learning documents (public ones only: internal rows never leave the DB)
    ld = _records(d["learning"], ["id", "title", "url", "publisher", "year", "doc_type", "scope",
                                  "country_iso3", "hazard", "premises", "key_stat", "summary", "section"])
    write_table("learning", ld,
                "Learning products: after-action reviews, evaluations, activation reports, research "
                "and guidance, per framework or global, with a one-line summary and key statistic.")

    # ---- Markdown pages
    md_pages = []
    for r in cur.itertuples():
        page = pages.get((r.country_iso3, r.hazard))
        name = f"fw-{r.country_iso3.lower()}-{r.hazard}.md"
        text = _framework_md(d, r, page, v_rows, trig_rows, w_rows, s_rows, a_rows, p_rows, pl,
                             pt_rows, ld, snapshot_at, stamp)
        (out / name).write_text(text)
        written.add(name)
        md_pages.append((name, f"{r.country_name} {r.hazard.replace('_', ' ')}",
                         f"{_cell(r.lifecycle) or ''}" + (f", version {r.latest_version}" if pd.notna(r.latest_version) else "")))
    portfolio = _portfolio_md(fw_rows, y_rows, md_pages, snapshot_at, stamp)
    (out / "aa-portfolio.md").write_text(portfolio)
    written.add("aa-portfolio.md")

    # ---- llms.txt, llms-full.txt, robots.txt, sitemap.xml
    stamp_line = f"Data snapshot {snapshot_at} UTC; files generated {stamp}." if snapshot_at else f"Files generated {stamp}."
    idx = [f"# OCHA anticipatory action — portfolio tracking\n",
           f"> The authoritative record of OCHA's anticipatory action (AA) portfolio: every framework "
           f"(a country and a hazard), its versions, triggers and trigger windows, pre-arranged "
           f"funding, activations and the money they released, implementing partners and learning "
           f"documents. Maintained by the data science team of OCHA's Centre for Humanitarian Data. {stamp_line}\n",
           f"**Caveat.** {CAVEAT}\n",
           f"The HTML pages at {SITE_URL} may require a password; the Markdown pages and data files "
           f"listed here are the open interface and carry the same figures. Every file is regenerated "
           f"from the database with each nightly publish.\n",
           RULES,
           "## Portfolio\n",
           f"- [Portfolio overview]({SITE_URL}aa-portfolio.md): every framework with its lifecycle, "
           f"latest version and envelope; the annual pre-arranged and released series.",
           f"- [Everything in one file]({SITE_URL}llms-full.txt): the portfolio page and every "
           f"framework page concatenated.\n",
           "## Framework pages (one per framework, Markdown)\n"]
    for name, title, sub in md_pages:
        idx.append(f"- [{title}]({SITE_URL}{name}): {sub}")
    idx.append("\n## Framework documents\n")
    idx.append("Each version of a framework is an endorsed document (published on ReliefWeb or "
               "unocha.org; `document_url` in aa-versions). Two renderings here, per version:\n")
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
    idx.append("\n## Data files (JSON: one object with `rows`, `columns` and the stamps; CSV: the same rows)\n")
    for name, desc, cols in files:
        idx.append(f"- [aa-{name}.json]({SITE_URL}aa-{name}.json) · [CSV]({SITE_URL}aa-{name}.csv): {desc} "
                   f"Columns: {', '.join(cols)}.")
    idx.append("\n## Vocabulary\n")
    idx.append("- `country_iso3`: ISO 3166-1 alpha-3. `hazard`: drought, flood, storm, cholera, plague, "
               "food_insecurity.\n"
               "- `lifecycle` (aa-frameworks): `active` a version in force; `updating` a successor in "
               "development while one is in force; `development` a first version in development, none in "
               "force yet; `pipeline` early or advanced conversations, nothing in development yet; "
               "`retired` no longer pursued. `status` is the finer observed status behind it "
               "(early_conversations, advanced_conversations, under_development, active, under_revision, "
               "activated_implementing, dormant, retired).\n"
               "- version `status` (aa-versions): `endorsed`, `development` (not yet endorsed), `retired`.\n"
               "- `fund_code`: `cerf` the Central Emergency Response Fund; `cbpf-<iso3>` a country-based "
               "pooled fund; `rhpf-<region>-<iso3>` a regional humanitarian pooled fund's envelope for a "
               "country; `all` a pre-arranged total the source did not break down by fund; "
               "`cbpf-unspecified` a pooled fund the source did not name.\n"
               "- `event_type`: `framework_aa` an activation of a framework's trigger; `adhoc_aa` an "
               "anticipatory allocation outside a framework.\n"
               "- window `basis`: `forecast`, `observational` or `mixed` (what the trigger reads); "
               "`all_in`: one trigger releases the whole envelope.\n"
               "- Amounts are US dollars. Dates are ISO 8601; a month-grain date is the first of the month.\n")
    idx.append(f"\n## Related\n\n- Code and schema (public repository): https://github.com/OCHA-DAP/ds-aa-tracking\n"
               f"- OCHA anticipatory action: https://www.unocha.org/anticipatory-action\n"
               f"- CERF: https://cerf.un.org/\n")
    (out / "llms.txt").write_text("\n".join(idx))
    full = ([portfolio] + [(out / n).read_text() for n, _, _ in md_pages]
            + [(out / fn).read_text() for _, fn in sorted(reads.items())])
    (out / "llms-full.txt").write_text("\n\n---\n\n".join(full))
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}sitemap.xml\n")
    urls = ([SITE_URL + n for n in sorted(public)] + [SITE_URL + "llms.txt", SITE_URL + "aa-portfolio.md"]
            + [SITE_URL + n for n, _, _ in md_pages] + [SITE_URL + fn for _, fn in sorted(reads.items())]
            + [SITE_URL + fn for _, fn in sorted(texts.items())])
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


def _framework_md(d, r, page, v_rows, trig_rows, w_rows, s_rows, a_rows, p_rows, pl, pt_rows, ld,
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
             + (f" (status: {r.status})" if pd.notna(r.status) and r.status != r.lifecycle else "")
             + (" · retired" if r.retired else "") + (" · technical support only" if r.technical_support else "")]
    if version:
        facts.append(f"**Latest version:** {version} ({_cell(r.latest_status) or 'status not recorded'})"
                     + (f", valid until {_cell(r.valid_until)}" if pd.notna(r.valid_until) else ""))
    if pd.notna(r.cerf_prearranged_usd):
        facts.append(f"**Pre-arranged CERF funding:** {_m(r.cerf_prearranged_usd)}"
                     + (f" (as at {int(r.prearranged_year)})" if pd.notna(r.prearranged_year) else ""))
    if pd.notna(r.people_covered):
        facts.append(f"**People covered:** {int(r.people_covered):,}")
    if pd.notna(r.n_windows) and r.n_windows:
        facts.append(f"**Trigger windows (version in force):** {int(r.n_windows)}, "
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
    out.append(_md_table(wv, ["window_name", "basis", "all_in", "allocation_usd", "return_period",
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
    sv = mine(s_rows)
    if sv:
        out.append("## Historical simulation (years the trigger would have activated)\n")
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
        out.append(f"## Plan: pre-arranged budget by agency and sector (version {pv[0]['version']})\n")
        out.append(_md_table(sorted(pv, key=lambda x: -(x["amount_usd"] or 0)),
                             ["agency", "sector", "fund_code", "amount_usd"], {"amount_usd": _m}))
    pall = mine(pt_rows)
    ptv = [x for x in pall if version and str(x["version"]) == version]
    p_label = version
    if not ptv and pall:
        p_label = sorted({str(x["version"]) for x in pall})[-1]
        ptv = [x for x in pall if str(x["version"]) == p_label]
    if ptv:
        out.append(f"## Partners named in the framework document (version {p_label})\n")
        out.append(_md_table(ptv, ["name", "acronym", "org_type", "roles", "agency_parent", "amount_usd"], {"amount_usd": _m}))

    # funding by year × fund
    pf = mine(p_rows)
    if pf:
        out.append("## Pre-arranged funding in place, by year and fund\n\nA stock: the envelope standing each year, not added up across years.\n")
        out.append(_md_table(pf, ["year", "fund_code", "financier", "amount_usd", "source"], {"amount_usd": _m}))

    # versions
    out.append("## Versions (endorsed documents)\n\n`read`: the structured read of the document; `text`: its full text.\n")
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


def _portfolio_md(fw_rows, y_rows, md_pages, snapshot_at, stamp):
    out = [_head("OCHA anticipatory action — the portfolio", snapshot_at, stamp)]
    live = [r for r in fw_rows if r["lifecycle"] in ("active", "updating", "development")]
    out.append(f"{len(fw_rows)} framework (country, hazard) pairs tracked; "
               f"{sum(r['lifecycle'] == 'active' for r in fw_rows)} active, "
               f"{sum(r['lifecycle'] == 'updating' for r in fw_rows)} being updated, "
               f"{sum(r['lifecycle'] == 'development' for r in fw_rows)} in development "
               f"({len(live)} live). Pre-arranged CERF funding in place across the live frameworks: "
               f"{_m(sum(r['cerf_prearranged_usd'] or 0 for r in live))}.\n")
    out.append(RULES)
    out.append("## Frameworks\n")
    out.append(_md_table(fw_rows, ["country_name", "country_iso3", "hazard", "region", "lifecycle", "latest_version",
                                   "latest_version_status", "valid_until", "cerf_prearranged_usd", "people_covered",
                                   "page_markdown"],
                         {"cerf_prearranged_usd": _m,
                          "people_covered": lambda v: f"{int(v):,}" if v is not None else "",
                          "hazard": lambda v: (v or "").replace("_", " ")}))
    out.append("## Pre-arranged and released funding by year and fund\n\n"
               "Pre-arranged is the stock standing that year; released is what framework activations drew. "
               "They are not added together.\n")
    years = sorted({r["year"] for r in y_rows})
    funds = sorted({r["fund_code"] for r in y_rows}, key=lambda f: (f != "cerf", f))
    tot = []
    for y in years:
        rows = [r for r in y_rows if r["year"] == y]
        tot.append({"year": y,
                    "prearranged_usd": sum(r["prearranged_usd"] or 0 for r in rows),
                    "released_usd": sum(r["released_usd"] or 0 for r in rows),
                    "by_fund": "; ".join(f"{f}: {_m(sum(r['prearranged_usd'] or 0 for r in rows if r['fund_code'] == f))} pre-arranged, "
                                         f"{_m(sum(r['released_usd'] or 0 for r in rows if r['fund_code'] == f))} released"
                                         for f in funds if any(r["fund_code"] == f for r in rows))})
    out.append(_md_table(tot, ["year", "prearranged_usd", "released_usd", "by_fund"],
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
    files = {}
    for r in pages.itertuples():
        body = _strip_sections(r.body_md)
        if not body.strip():
            continue
        fn = f"doc-{r.kb_framework}-{r.version}.md"
        countries = ", ".join(r.country_iso3) if isinstance(r.country_iso3, (list, tuple)) else str(r.country_iso3 or "")
        head = (f"> {CAVEAT}\n>\n> A structured read of the framework document by the OCHA data science team: "
                f"the figures carry the document's own page numbers as evidence. Framework {r.kb_framework} "
                f"({countries}, {r.hazard or ''}), version {r.version}."
                + (f" Official document: {r.doc_url}" if isinstance(r.doc_url, str) and r.doc_url else "")
                + (f"\n>\n> Data snapshot {snapshot_at} UTC · generated {stamp}" if snapshot_at else f"\n>\n> Generated {stamp}")
                + f" · framework page: {SITE_URL}fw-{(r.country_iso3[0] if isinstance(r.country_iso3, (list, tuple)) and r.country_iso3 else '').lower()}-{r.hazard}.md"
                + f" · index: {SITE_URL}llms.txt\n\n")
        # the body starts with its own H1; keep it first
        m = re.match(r"\s*(# .*?\n)", body)
        text = (m.group(1) + "\n" + head + body[m.end():].lstrip("\n")) if m else head + body
        (out / fn).write_text(text)
        files[(r.kb_framework, r.version)] = fn
    return files


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


def _pdf_texts(e, out, stamp):
    """pdf-<sha256>.txt for every current, public, registered framework document: the archived
    PDF's text page by page (pypdf), from the blob archive, cached under PDF_CACHE by content
    hash (a file never changes). Returns (sha -> file name, (iso3, hazard, version) -> [doc])."""
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
                + f" Content hash (sha256): {sha}. Generated {stamp}. Index: {SITE_URL}llms.txt\n\n")
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
