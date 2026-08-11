"""Render the review site (static HTML) from the dev DB into site_build/.

Every ds-aa-tracking table gets a page with its full contents, plus:
- index with schema overview, ownership map, and source-sheet decisions
- reconciliation page (sheet vs KB vs CERF-mirror conflicts)
- CERF-mirror page for the new cerf_project* tables not yet fully documented in the KB

The output is then encrypted with staticrypt before publishing (see publish step in
README) — nothing in site_build/ is committed or served unencrypted.
"""

import html
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
os.environ.setdefault("PGSSLMODE", "require")

import ocha_stratus as stratus  # noqa: E402

from ds_aa_tracking import schema as trk_schema  # noqa: E402

OUT = Path(__file__).parents[1] / "site_build"
OUT.mkdir(exist_ok=True)

CSS = """
:root { --accent:#007ce0; --muted:#666; }
* { box-sizing:border-box; }
body { font-family:-apple-system,'Segoe UI',Roboto,sans-serif; margin:0; color:#1a1a1a;
       background:#fafafa; }
header { background:#1f2a44; color:#fff; padding:14px 28px; }
header a { color:#9ec5f0; text-decoration:none; margin-right:18px; }
header .t { font-weight:700; font-size:17px; margin-right:26px; }
main { max-width:1500px; margin:0 auto; padding:22px 28px 80px; }
h1 { font-size:24px; } h2 { font-size:19px; margin-top:34px; }
p.meta { color:var(--muted); font-size:13px; }
table.data { border-collapse:collapse; font-size:12.5px; background:#fff; width:100%; }
table.data th { background:#eef3f8; text-align:left; padding:5px 8px; position:sticky;
                top:0; border-bottom:2px solid #cbd6e2; }
table.data td { padding:4px 8px; border-bottom:1px solid #eee; vertical-align:top;
                max-width:420px; overflow-wrap:break-word; }
table.data tr:hover td { background:#f2f7fc; }
.scroll { overflow-x:auto; max-height:75vh; overflow-y:auto; border:1px solid #ddd; }
input.filter { padding:6px 10px; width:340px; margin:10px 0; border:1px solid #bbb;
               border-radius:4px; font-size:13px; }
.card { background:#fff; border:1px solid #e0e0e0; border-radius:6px; padding:16px 20px;
        margin:14px 0; }
.badge { display:inline-block; padding:1px 8px; border-radius:10px; font-size:11.5px;
         font-weight:600; margin-right:6px; }
.b-new { background:#e3f1e6; color:#1c6b31; } .b-kb { background:#e8e8f8; color:#3b3b8f; }
.b-mirror { background:#fdf1dc; color:#8a5c0a; } .b-warn { background:#fde3e3; color:#a11; }
code { background:#f0f0f0; padding:1px 5px; border-radius:3px; font-size:12px; }
ul.tight li { margin:3px 0; }
"""

FILTER_JS = """
function filt(inp) {
  const q = inp.value.toLowerCase();
  const rows = inp.closest('section').querySelectorAll('table.data tbody tr');
  rows.forEach(r => { r.style.display = r.textContent.toLowerCase().includes(q) ? '' : 'none'; });
}
"""

NAV = """
<header>
  <span class="t">AA tracking — schema &amp; data review</span>
  <a href="index.html">Overview</a>
  <a href="tables.html">Tracking tables</a>
  <a href="schema.html">DB schema</a>
  <a href="reconciliation.html">Reconciliation</a>
  <a href="review-julia.html">Julia</a>
  <a href="review-yakubu.html">Yakubu</a>
  <a href="cerf-mirror.html">CERF mirror</a>
  <a href="decisions.html">Source decisions</a>
</header>
"""


def page(name, title, body):
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style>
<script>{FILTER_JS}</script></head><body>
{NAV}<main><h1>{html.escape(title)}</h1>
<p class="meta">Generated {date.today().isoformat()} from the dev <code>aa</code> schema
· internal review only</p>
{body}</main></body></html>"""
    (OUT / name).write_text(doc)
    print(f"  {name}")


def tbl(df, max_rows=8000):
    n = len(df)
    shown = df.head(max_rows)
    t = shown.to_html(index=False, classes="data", na_rep="", border=0)
    note = f"<p class='meta'>{n:,} rows" + (
        f" (showing first {max_rows:,})" if n > max_rows else ""
    ) + "</p>"
    return (
        f"<section>{note}<input class='filter' placeholder='filter rows…' "
        f"oninput='filt(this)'>\n<div class='scroll'>{t}</div></section>"
    )


# per-table reviewer notes
NOTES = {
    "framework_registry": "One row per (country, hazard) — the framework identity used everywhere, incl. pipeline entries with no KB page yet. <code>kb_framework</code>/<code>in_kb</code> crosswalk to the KB. Attributes (region, language, focal-point context) come from Julia's 2026 planning sheet.",
    "framework_version": "The unit that actually gets approved: one row per framework version, seeded from KB page frontmatter (incl. superseded/retired versions) plus sheet-reported revision dates with no KB page (<code>source='sheet-revision'</code> — a KB completeness gap). Version-specific facts (budgets, sector budgets, coverage, calendar, activations, status) carry a <code>version</code> attribution: direct from the KB for matched activations, otherwise inferred from the version in force at the fact's date (<code>version_match</code>; NULL = no version exists to attribute to). Caveat: figures reported mid-revision may belong to the upcoming version — interval inference can't see that; overrides are a curation pass.",
    "framework_status": "Operational lifecycle snapshots from every source sheet, kept side by side (PK includes <code>source</code>). Canonical <code>status</code> vocabulary; raw spelling preserved. This is deliberately distinct from the KB page-status vocabulary.",
    "framework_focal_point": "Focal points by role from the 2026 planning sheet.",
    "framework_calendar": "Monthly markers recovered from cell <em>colors</em> in the planning sheet: green = trigger window, orange = framework finalization, red = proposal development; 'F' = finalization deadline.",
    "prearranged_funding": "Pre-arranged/co-financing amounts per (framework, year, fund source), one row per source sheet — conflicts intentionally preserved (see Reconciliation).",
    "prearranged_sector_budget": "Pre-arranged budgets per framework × agency × sector (Yakubu, Jun 2026). <code>subunit</code> captures sub-framework splits (Bangladesh Jamuna/Padma, DRC-1/2).",
    "people_covered": "People covered per framework, per source; includes double-activation assessment for cyclone frameworks.",
    "activation_event": "The superset activation record 2020–2026 (Julia): framework + ad-hoc, AA + EA, CERF + country/regional funds. Crosswalked to KB <code>actual_activation</code> where possible (<code>match_method</code>).",
    "report_channel_inclusion": "Which frameworks/countries count toward which external reports per year (A-Hub, UK BCs, SG, CERF/OCHA annual reports, SF KPI, CPC).",
    "plan_inclusion": "GHO/HNRP plan inclusion + AA feasibility flags per country-year, per source.",
    "start_network": "Start Fund anticipation alerts + Start READY membership per country (from the planning sheet).",
    "cirv": "CERF Index for Risk and Vulnerability, 2025 vintage (150 countries).",
    "cerf_subgrant": "Sub-granting to implementing partners: full CERF 2020–2025 + the curated AA set (with localization tagging). Deduplicated on (project, partner, amount).",
    "cerf_application_people": "Application-level beneficiary demographics (long format): planned/reached × sex-age/disability/displacement-category. GMS 2020–2024 + OneGMS planned figures.",
    "cerf_application_report": "RC/HC report metadata + the seven narrative sections per application (GMS 2020–2024 export).",
    "cerf_allocation_extra": "OneGMS fields the mirror lacks: the structured <code>Is AA Allocation</code> flag, onset type, response funding requirements, people affected.",
    "cerf_project_supplement": "Project-level markers + CVA from the Agency HQ Report export: gender/GBV/disability/cash markers, people receiving cash, CVA amount, displacement-category targeting.",
    "cerf_cva_history": "CVA by country × agency × emergency × year, 2020–2026 (aggregated to the sheet's grain).",
    "emergency_type_override": "Yakubu's re-tagged allocations: GMS emergency type vs actual shock (mostly Flood→Storm, with storm name).",
}

TABLE_ORDER = list(NOTES)


def main():
    e = stratus.get_engine(stage="dev")

    # ---------- per-table pages + tables index
    cards = []
    for t in TABLE_ORDER:
        df = pd.read_sql(f"SELECT * FROM aa.{t}", e)
        df = df.drop(columns=[c for c in ("updated_at",) if c in df.columns])
        if t == "cerf_application_people":
            wide = df.pivot_table(
                index=["application_code", "source", "phase"],
                columns=["disaggregation", "grp"], values="value", aggfunc="first",
            )
            wide.columns = [f"{a}:{b}" for a, b in wide.columns]
            wide = wide.reset_index()
            body = (
                f"<div class='card'>{NOTES[t]}</div>"
                + "<h2>Pivoted (one row per application × phase)</h2>"
                + tbl(wide)
            )
        else:
            body = f"<div class='card'>{NOTES[t]}</div>" + tbl(df)
        page(f"table-{t}.html", f"aa.{t}", body)
        cards.append(
            f"<div class='card'><span class='badge b-new'>new</span>"
            f"<a href='table-{t}.html'><b>aa.{t}</b></a>"
            f" — {len(df):,} rows<br><span class='meta'>{NOTES[t]}</span></div>"
        )
    page("tables.html", "Tracking tables (owned by ds-aa-tracking)", "\n".join(cards))

    # ---------- reconciliation page
    sections = []
    rec = pd.read_sql(
        "SELECT * FROM aa.v_trk_activation_reconciliation ORDER BY year DESC, month DESC",
        e,
    )
    counts = rec["reconciliation"].value_counts().to_dict()
    sections.append(
        "<div class='card'><b>Activation events: sheets vs KB.</b> "
        f"{counts.get('OK', 0)} matched · "
        f"<span class='badge b-warn'>{counts.get('AMOUNT_CONFLICT', 0)} amount conflicts</span>"
        f"<span class='badge b-warn'>{counts.get('MISSING_IN_KB', 0)} missing in KB</span>"
        f"{counts.get('OUT_OF_KB_SCOPE', 0)} out of KB scope (ad-hoc / EA / non-CERF fund "
        "— the KB structurally cannot hold these; the new table is their home). "
        "Per your call, no KB pages have been edited — adjudicate here first.</div>"
    )
    sections.append("<h2>Sheet events vs KB</h2>" + tbl(rec))
    kb_only = pd.read_sql("SELECT * FROM aa.v_trk_activation_kb_only", e)
    sections.append(
        "<h2>KB activations with no sheet counterpart</h2>"
        "<p class='meta'>Mostly pre-2020 pilots, partial-window triggers, and "
        "multi-country frameworks recorded differently — worth an explicit pass.</p>"
        + tbl(kb_only)
    )
    flags = pd.read_sql("SELECT * FROM aa.v_trk_aa_flag_reconciliation", e)
    sections.append(
        "<h2>AA flag: OneGMS reported vs mirror keyword heuristic</h2>"
        "<p class='meta'>The mirror derives <code>aa_keyword</code> from titles; OneGMS "
        "now reports a structured flag (in <code>aa.cerf_allocation_extra</code>). "
        "Disagreements below.</p>" + tbl(flags)
    )
    pre = pd.read_sql(
        """SELECT country_iso3, hazard, year, fund_source, source, amount_usd
           FROM aa.prearranged_funding WHERE kind='prearranged'""",
        e,
    )
    piv = pre.pivot_table(
        index=["country_iso3", "hazard", "year", "fund_source"],
        columns="source", values="amount_usd", aggfunc="first",
    ).reset_index()
    src_cols = [c for c in piv.columns if c not in
                ("country_iso3", "hazard", "year", "fund_source")]
    piv["n_distinct_amounts"] = piv[src_cols].apply(
        lambda r: r.dropna().nunique(), axis=1
    )
    piv = piv.sort_values(["n_distinct_amounts", "country_iso3"], ascending=[False, True])
    sections.append(
        "<h2>Pre-arranged funding across sources</h2>"
        "<p class='meta'>One column per source sheet; <code>n_distinct_amounts</code> &gt; 1 "
        "= the sheets disagree (often timing: 2025 vs likely-2026 vs Jun-2026 figures).</p>"
        + tbl(piv)
    )
    attr = pd.read_sql("SELECT * FROM aa.v_trk_version_attribution", e)
    attr["version_match"] = attr["version_match"].fillna("(no version to attribute to)")
    vsum = pd.read_sql("SELECT * FROM aa.v_trk_version_summary", e)
    vgap = pd.read_sql(
        "SELECT * FROM aa.framework_version WHERE source='sheet-revision'", e
    )
    sections.append(
        "<h2>Framework versions: attribution &amp; completeness</h2>"
        "<div class='card'>Version-specific facts (budgets, coverage, calendar, "
        "activations, status) are attributed to the framework <em>version</em> in "
        "force at the fact's date — sheets don't record versions, so this is inferred "
        "(<code>auto-interval</code>), flagged when the fact falls after the version's "
        "stated validity (<code>auto-post-validity</code>), or inherited from the KB "
        "activation record (<code>kb-activation</code>). '(no version to attribute "
        "to)' = pipeline/ad-hoc frameworks with no version anywhere — correct, not an "
        "error. Mid-revision figures may belong to the upcoming version; that needs "
        "manual override in a later pass.</div>"
        + tbl(attr, 100)
    )
    sections.append(
        "<h3>Sheet-reported revisions with no KB version page</h3>" + tbl(vgap, 100)
    )
    sections.append(
        "<h3>Per-version rollup (doc budget vs tracked budget)</h3>"
        "<p class='meta'>From <code>aa.v_trk_version_summary</code> — where "
        "<code>prearranged_usd_doc</code> (KB frontmatter) and "
        "<code>prearranged_usd_tracked</code> (sheets, attributed) disagree, either the "
        "budget genuinely changed with the version or the attribution needs review.</p>"
        + tbl(vsum, 200)
    )
    cov = pd.read_sql("SELECT * FROM aa.people_covered", e)
    cpiv = cov.pivot_table(
        index=["country_iso3", "hazard"], columns="source", values="people_covered",
        aggfunc="first",
    ).reset_index()
    sections.append(
        "<h2>People covered across sources</h2>" + tbl(cpiv)
    )
    page("reconciliation.html", "Reconciliation — sheets vs KB vs mirror",
         "\n".join(sections))

    # ---------- CERF mirror page
    sections = []
    sections.append(
        "<div class='card'><span class='badge b-mirror'>mirror</span>"
        "The OneGMS mirror (<code>ds-cerf-supplement</code>) gained full project-level "
        "tables in Aug 2026 — <code>aa.cerf_project</code>, "
        "<code>aa.cerf_project_sector</code>, <code>aa.cerf_project_country</code> — "
        "which the KB only partially documents (the ERD shows ~7 of 48 project columns; "
        "sector taxonomy columns and lifecycle dates are undocumented). Summary below; "
        "the new tracking tables link to these via "
        "<code>application_code</code>/<code>project_code</code>.</div>"
    )
    for t, q in [
        ("cerf_allocation", "SELECT year, count(*) n_allocations, sum(CASE WHEN aa_keyword THEN 1 ELSE 0 END) n_aa_keyword, sum(amount_approved) amount_approved FROM aa.cerf_allocation GROUP BY year ORDER BY year"),
        ("cerf_project", "SELECT year, count(*) n_projects, count(DISTINCT application_code) n_applications, sum(amount_approved) amount_approved FROM aa.cerf_project GROUP BY year ORDER BY year"),
        ("cerf_project_sector", "SELECT cerf_sector_name, count(*) n, sum(sector_amount) amount FROM aa.cerf_project_sector GROUP BY 1 ORDER BY amount DESC NULLS LAST"),
        ("cerf_project_country", "SELECT count(*) n_rows, count(DISTINCT project_code) n_projects, count(DISTINCT country_iso3) n_countries FROM aa.cerf_project_country"),
    ]:
        df = pd.read_sql(q, e)
        sections.append(f"<h2>aa.{t}</h2>" + tbl(df, max_rows=200))
    cols = pd.read_sql(
        """SELECT table_name, column_name, data_type
           FROM information_schema.columns
           WHERE table_schema='aa' AND table_name IN
                 ('cerf_project','cerf_project_sector','cerf_project_country')
           ORDER BY table_name, ordinal_position""",
        e,
    )
    sections.append(
        "<h2>Full column inventory (not yet in the KB ERD)</h2>" + tbl(cols, 300)
    )
    page("cerf-mirror.html", "CERF OneGMS mirror — new content", "\n".join(sections))

    # ---------- decisions page
    page("decisions.html", "Source workbooks — sheet-by-sheet decisions", DECISIONS)

    # ---------- schema page
    build_schema_page(e)

    # ---------- per-person review pages
    build_person_pages(e)

    # ---------- index
    reg = pd.read_sql("SELECT * FROM aa.v_trk_framework_current ORDER BY country_name", e)
    n_active = (reg["status"] == "active").sum() + (
        reg["status"] == "activated_implementing"
    ).sum()
    idx = f"""
<div class='card'>
<b>What this is.</b> The expanded <code>aa</code> schema in the dev DB now covers all
the tracking done in Julia's and Yakubu's spreadsheets, crosswalked to the existing
KB trigger-performance tables and the CERF OneGMS mirror. This site shows every new
table's full contents plus the conflicts that need your adjudication. Once reviewed,
the DB becomes the single authoritative source and the sheets can be retired.
</div>
<div class='card'>
<b>Ownership map</b> (single writer per table, schema <code>aa</code>):<br>
<span class='badge b-new'>ds-aa-tracking (this repo, 20 tables + 7 views)</span>
framework_registry · framework_version · framework_status · framework_focal_point ·
framework_calendar ·
prearranged_funding · prearranged_sector_budget · people_covered · activation_event ·
report_channel_inclusion · plan_inclusion · start_network · cirv · cerf_subgrant ·
cerf_application_people · cerf_application_report · cerf_allocation_extra ·
cerf_project_supplement · cerf_cva_history · emergency_type_override<br>
<span class='badge b-kb'>ds-knowledge-base</span>
framework_version_map · window · simulated_activation · funding_breakdown ·
actual_activation · activation_allocation<br>
<span class='badge b-mirror'>ds-cerf-supplement</span>
cerf_allocation · cerf_project · cerf_project_sector · cerf_project_country ·
cerf_allocation_storm · cerf_supplement
</div>
<h2>Portfolio at a glance ({n_active} active of {len(reg)} tracked frameworks)</h2>
{tbl(reg)}
"""
    page("index.html", "AA tracking — schema & data review", idx)


def _latest_status_pivot(e, since="2025-12-01"):
    """Latest status per (framework, source) for recent snapshots; conflict-flagged."""
    st = pd.read_sql(
        f"""SELECT DISTINCT ON (country_iso3, hazard, source)
                   country_iso3, hazard, source, status, as_of
            FROM aa.framework_status WHERE as_of >= '{since}'
            ORDER BY country_iso3, hazard, source, as_of DESC""",
        e,
    )
    st["cell"] = st["status"] + " (" + st["as_of"].astype(str) + ")"
    piv = st.pivot_table(index=["country_iso3", "hazard"], columns="source",
                         values="cell", aggfunc="first")
    nuniq = st.groupby(["country_iso3", "hazard"])["status"].nunique()
    piv["n_distinct_statuses"] = nuniq
    return piv.reset_index()


def _prearranged_pivot(e):
    pre = pd.read_sql(
        """SELECT country_iso3, hazard, year, source, amount_usd
           FROM aa.prearranged_funding
           WHERE kind = 'prearranged' AND fund_source = 'cerf'""",
        e,
    )
    piv = pre.pivot_table(index=["country_iso3", "hazard", "year"], columns="source",
                          values="amount_usd", aggfunc="first")
    piv["n_distinct_amounts"] = piv.apply(lambda r: r.dropna().nunique(), axis=1)
    return piv.reset_index()


def _covered_pivot(e):
    cov = pd.read_sql("SELECT * FROM aa.people_covered", e)
    piv = cov.pivot_table(index=["country_iso3", "hazard"], columns="source",
                          values="people_covered", aggfunc="first")
    piv["n_distinct_values"] = piv.apply(lambda r: r.dropna().nunique(), axis=1)
    return piv.reset_index()


def _conflict_rows(piv, person, count_col):
    """Rows where sources disagree and this person's sheets contributed a value."""
    p_cols = [c for c in piv.columns if str(c).startswith(f"{person}-")]
    if not p_cols:
        return piv.iloc[0:0]
    has_p = piv[p_cols].notna().any(axis=1)
    return piv[(piv[count_col] > 1) & has_p]


def _version_issues(e, person):
    """Version-attribution uncertainties on this person's facts."""
    fv = pd.read_sql(
        "SELECT country_iso3, hazard, version, kb_status FROM aa.framework_version", e
    )
    fw_with_versions = set(zip(fv["country_iso3"], fv["hazard"]))
    dev = fv[fv["kb_status"] == "development"]
    dev_versions = set(zip(dev["country_iso3"], dev["hazard"], dev["version"]))
    specs = {
        "framework_status": ("as_of::text AS fact_date", "status AS detail"),
        "framework_calendar": ("as_of::text AS fact_date",
                               "phase || ' m' || month AS detail"),
        "people_covered": ("as_of::text AS fact_date",
                           "people_covered::text AS detail"),
        "prearranged_funding": ("year::text AS fact_date",
                                "kind || ' ' || fund_source || ' $' || COALESCE(amount_usd::text,'?') AS detail"),
        "prearranged_sector_budget": ("year_label AS fact_date",
                                      "agency || ' / ' || sector || ' $' || COALESCE(amount_usd::text,'?') AS detail"),
        "activation_event": ("year::text || COALESCE('-' || month::text,'') AS fact_date",
                             "aa_or_ea || ' ' || mechanism || ' $' || COALESCE(amount_usd::text,'?') AS detail"),
    }
    frames = []
    for t, (datecol, detailcol) in specs.items():
        df = pd.read_sql(
            f"""SELECT '{t}' AS "table", country_iso3, hazard, {datecol}, {detailcol},
                       source, version, version_match
                FROM aa.{t} WHERE source LIKE '{person}-%%'""",
            e,
        )
        frames.append(df)
    facts = pd.concat(frames, ignore_index=True)
    issues = []
    for _, r in facts.iterrows():
        key = (r["country_iso3"], r["hazard"])
        if r["version_match"] == "auto-post-validity":
            issue = ("dated after the attributed version's validity — belongs to a "
                     "newer/upcoming version?")
        elif pd.isna(r["version"]) and key in fw_with_versions:
            issue = "no version covers this date (predates first known version?)"
        elif (pd.notna(r["version"])
              and (r["country_iso3"], r["hazard"], r["version"]) in dev_versions):
            issue = "attributed to an in-development version — confirm"
        else:
            continue
        issues.append({**r, "issue": issue})
    return pd.DataFrame(issues)


def build_person_pages(e):
    people = {
        "julia": "Julia — sheet reconciliation queue",
        "yakubu": "Yakubu — sheet reconciliation queue",
    }
    status_piv = _latest_status_pivot(e)
    pre_piv = _prearranged_pivot(e)
    cov_piv = _covered_pivot(e)

    for person, title in people.items():
        sections = [
            "<div class='card'>Everything on this page traces back to "
            f"<b>{person.title()}'s</b> workbooks: places where they disagree with the "
            "KB, the CERF mirror, the other tracking sheets, or where a fact can't be "
            "confidently attributed to a framework version. Each table is a queue — "
            "the answer is either 'the sheet is right' (we fix the KB/mirror), 'the "
            "other source is right' (we correct at ingestion), or a version override."
        ]
        if person == "julia":
            sections[0] += (
                " Sources: 2026 planning, 2024/2025 AA reporting, 2026 GHO, "
                "activations 2020–2026.</div>"
            )
        else:
            sections[0] += (
                " Sources: CERF AA Data (Jun 2026), subgrant data, displacement/GMS "
                "exports, March 2026 allocation analysis.</div>"
            )

        st = _conflict_rows(status_piv, person, "n_distinct_statuses")
        sections.append(
            "<h2>Framework status: recent snapshots disagree</h2>"
            "<p class='meta'>Latest status per source since Dec 2025. Some differences "
            "are genuine evolution (a framework endorsed between two snapshot dates); "
            "the rest need one answer.</p>" + tbl(st)
        )
        pre = _conflict_rows(pre_piv, person, "n_distinct_amounts")
        sections.append(
            "<h2>Pre-arranged CERF funding: sources disagree</h2>"
            "<p class='meta'>Per framework and year, CERF-only amounts (fund-source "
            "totals are compared separately on the Reconciliation page). Timing "
            "explains some (a top-up between snapshots) — confirm which figure is "
            "authoritative per year.</p>" + tbl(pre)
        )
        cov = _conflict_rows(cov_piv, person, "n_distinct_values")
        sections.append(
            "<h2>People covered: sources disagree</h2>"
            "<p class='meta'>e.g. Afghanistan drought appears as 769,000 (2025 "
            "reporting), 392,816 (Jun 2026 CERF sheet) and 257,996 (2025 baseline) — "
            "which is the number to carry?</p>" + tbl(cov)
        )
        vi = _version_issues(e, person)
        sections.append(
            "<h2>Version attribution to confirm</h2>"
            "<p class='meta'>Facts from these sheets whose framework-version "
            "attribution is uncertain. Key cases: figures reported while a framework "
            "was under revision may describe the <em>upcoming</em> version, not the "
            "one in force.</p>" + tbl(vi)
        )

        if person == "julia":
            rec = pd.read_sql(
                """SELECT * FROM aa.v_trk_activation_reconciliation
                   WHERE reconciliation <> 'OK'
                   ORDER BY reconciliation, year DESC, month DESC""",
                e,
            )
            sections.append(
                "<h2>Activation list vs KB</h2>"
                "<p class='meta'><code>MISSING_IN_KB</code> = framework CERF "
                "activations in your list with no KB record — if real, the KB page "
                "needs an <code>activations:</code> entry (we'll batch these once "
                "confirmed). <code>AMOUNT_CONFLICT</code> = both match but amounts "
                "differ (Nigeria 2025: your CERF/Country-Fund split vs the KB's "
                "single $7M). <code>OUT_OF_KB_SCOPE</code> = ad-hoc/EA/non-CERF — "
                "fine, they live only in the new table; just confirm they're "
                "correct.</p>" + tbl(rec)
            )
            kb_only = pd.read_sql("SELECT * FROM aa.v_trk_activation_kb_only", e)
            sections.append(
                "<h2>KB activations missing from your list</h2>"
                "<p class='meta'>Should any of these be added to the activations "
                "sheet's successor (this DB)? Mostly pre-2020 pilots, partial-window "
                "triggers, and multi-country events.</p>" + tbl(kb_only)
            )
            vgap = pd.read_sql(
                "SELECT * FROM aa.framework_version WHERE source='sheet-revision'", e
            )
            sections.append(
                "<h2>Revisions you reported with no KB version page</h2>"
                "<p class='meta'>Your reporting sheet says these frameworks were "
                "revised, but the KB has no version within 90 days — is there an "
                "endorsed doc we should ingest?</p>" + tbl(vgap)
            )
        else:
            flags = pd.read_sql("SELECT * FROM aa.v_trk_aa_flag_reconciliation", e)
            sections.append(
                "<h2>'Is AA' flag: your OneGMS export vs the mirror heuristic</h2>"
                "<p class='meta'>The mirror flags AA allocations from title keywords; "
                "your export carries OneGMS's structured flag. Which is right for "
                "these?</p>" + tbl(flags)
            )
            retag = pd.read_sql(
                """SELECT o.application_code, o.country_name, o.initial_type,
                          o.actual_type, o.storm_name,
                          c.emergency_type AS mirror_current_type,
                          s.not_tc AS mirror_not_tc
                   FROM aa.emergency_type_override o
                   LEFT JOIN aa.cerf_allocation c USING (application_code)
                   LEFT JOIN aa.cerf_supplement s USING (application_code)
                   ORDER BY o.application_code""",
                e,
            )
            sections.append(
                "<h2>Retagged allocations vs the mirror</h2>"
                "<p class='meta'>Your re-tags next to what the OneGMS mirror "
                "currently says (and the storm-matcher's <code>not_tc</code> where "
                "set). Rows where <code>mirror_current_type</code> still equals the "
                "initial tag are uncorrected upstream; blank mirror columns = "
                "application code not found in the mirror (code format worth "
                "checking).</p>" + tbl(retag)
            )
            sect = pd.read_sql(
                """SELECT * FROM aa.prearranged_sector_budget
                   WHERE year_label IS NULL
                      OR year_label NOT IN ('Prearranged', '2025', '2026')""",
                e,
            )
            sections.append(
                "<h2>Sector budgets with unclear year labels</h2>"
                "<p class='meta'>The 'Year' column in Sector Data - Pre-arranged "
                "includes notes like “Think these are the info from old info” — "
                "which framework version do these rows describe?</p>" + tbl(sect)
            )
            grain = pd.read_sql(
                """SELECT country_name, agency, emergency_type, year, n_source_rows,
                          amount_approved_usd, cva_usd, people_receiving_cash
                   FROM aa.cerf_cva_history WHERE n_source_rows > 1
                   ORDER BY n_source_rows DESC""",
                e,
            )
            sections.append(
                "<h2>CVA data grain check</h2>"
                "<p class='meta'>Your Disbursement+CVA sheet has no project codes, so "
                "rows were aggregated to country × agency × emergency × year. "
                "Rows below collapsed multiple sheet rows (n_source_rows) — confirm "
                "summing was right (e.g. repeat activations in one year).</p>"
                + (tbl(grain) if not grain.empty
                   else "<p class='meta'>none — every combination was already "
                        "unique ✓</p>")
            )
        page(f"review-{person}.html", title, "\n".join(sections))


KB_TABLES = [
    "framework_version_map", "window", "simulated_activation", "funding_breakdown",
    "actual_activation", "activation_allocation",
]
MIRROR_TABLES = [
    "cerf_allocation", "cerf_project", "cerf_project_sector", "cerf_project_country",
    "cerf_allocation_storm", "cerf_supplement",
]
OWNER_BADGE = {
    "ds-aa-tracking": "<span class='badge b-new'>ds-aa-tracking</span>",
    "ds-knowledge-base": "<span class='badge b-kb'>ds-knowledge-base</span>",
    "ds-cerf-supplement": "<span class='badge b-mirror'>ds-cerf-supplement</span>",
    "other": "<span class='badge'>other</span>",
}


ERD_STYLE = {
    "new": ("#e3f1e6", "#1c6b31"),
    "kb": ("#e8e8f8", "#3b3b8f"),
    "mirror": ("#fdf1dc", "#8a5c0a"),
}

# (name, owner, key-line) — key columns only, to keep the diagram readable
ERD_NODES = [
    ("framework_registry", "new", "country_iso3 · hazard"),
    ("framework_version", "new", "+ version (the approved unit)"),
    ("framework_status", "new", "+ as_of · source"),
    ("framework_focal_point", "new", "+ role · person · as_of"),
    ("framework_calendar", "new", "+ month · phase"),
    ("prearranged_funding", "new", "+ year · kind · fund_source · source"),
    ("prearranged_sector_budget", "new", "+ subunit · agency · sector"),
    ("people_covered", "new", "+ as_of · source"),
    ("activation_event", "new", "+ year · month · fund_source"),
    ("report_channel_inclusion", "new", "report_year · channel + …"),
    ("plan_inclusion", "new", "country_iso3 · year · source"),
    ("start_network", "new", "country_iso3 · as_of"),
    ("cirv", "new", "country_iso3 · year"),
    ("cerf_subgrant", "new", "project_code · partner_name"),
    ("cerf_application_people", "new", "application_code · phase · grp"),
    ("cerf_application_report", "new", "application_code"),
    ("cerf_allocation_extra", "new", "application_code"),
    ("cerf_project_supplement", "new", "project_code"),
    ("cerf_cva_history", "new", "country · agency · type · year"),
    ("emergency_type_override", "new", "application_code"),
    ("framework_version_map", "kb", "kb_framework · kb_version · iso3"),
    ("window", "kb", "+ window_name"),
    ("simulated_activation", "kb", "+ window_name · event_year"),
    ("funding_breakdown", "kb", "+ window · fund · agency · sector"),
    ("actual_activation", "kb", "kb_framework · event_date"),
    ("activation_allocation", "kb", "kb_framework+event_date ⇄ app_code"),
    ("cerf_allocation", "mirror", "application_code"),
    ("cerf_project", "mirror", "project_code"),
    ("cerf_project_sector", "mirror", "project_code + sector"),
    ("cerf_project_country", "mirror", "project_code · country_iso3"),
    ("cerf_allocation_storm", "mirror", "application_code · sid"),
    ("cerf_supplement", "mirror", "application_code"),
]

# (from, to, label, dashed) — dashed = join by convention, no declared FK
ERD_EDGES = [
    ("framework_version", "framework_registry", "country+hazard", True),
    ("framework_status", "framework_version", "+ version", True),
    ("framework_focal_point", "framework_registry", "", True),
    ("framework_calendar", "framework_version", "+ version", True),
    ("prearranged_funding", "framework_version", "+ version", True),
    ("prearranged_sector_budget", "framework_version", "+ version", True),
    ("people_covered", "framework_version", "+ version", True),
    ("report_channel_inclusion", "framework_registry", "", True),
    ("activation_event", "framework_version", "+ version", True),
    ("plan_inclusion", "framework_registry", "country_iso3", True),
    ("start_network", "framework_registry", "country_iso3", True),
    ("cirv", "framework_registry", "country_iso3", True),
    ("framework_version", "framework_version_map", "kb_framework · kb_version", True),
    ("window", "framework_version_map", "", True),
    ("simulated_activation", "window", "", True),
    ("funding_breakdown", "framework_version_map", "", True),
    ("actual_activation", "framework_version_map", "kb_framework", True),
    ("activation_event", "actual_activation", "kb_framework+event_date", True),
    ("activation_event", "cerf_allocation", "application_code", True),
    ("activation_allocation", "actual_activation", "FK", False),
    ("activation_allocation", "cerf_allocation", "FK", False),
    ("cerf_project", "cerf_allocation", "application_code", True),
    ("cerf_project_sector", "cerf_project", "project_code", True),
    ("cerf_project_country", "cerf_project", "project_code", True),
    ("cerf_allocation_storm", "cerf_allocation", "", True),
    ("cerf_supplement", "cerf_allocation", "", True),
    ("cerf_allocation_extra", "cerf_allocation", "application_code", True),
    ("cerf_application_people", "cerf_allocation", "application_code", True),
    ("cerf_application_report", "cerf_allocation", "application_code", True),
    ("emergency_type_override", "cerf_allocation", "application_code", True),
    ("cerf_project_supplement", "cerf_project", "project_code", True),
    ("cerf_subgrant", "cerf_project", "project_code", True),
    ("cerf_cva_history", "framework_registry", "country_iso3", True),
]


def build_erd():
    """Render the ERD to SVG with graphviz (brew install graphviz)."""
    import shutil
    import subprocess

    dot_bin = shutil.which("dot") or "/opt/homebrew/bin/dot"
    lines = [
        "digraph aa {",
        '  rankdir=RL; splines=true; concentrate=true;',
        '  graph [fontname="Helvetica", pad="0.3", nodesep=0.25, ranksep=1.1];',
        '  node [shape=none, fontname="Helvetica", fontsize=11];',
        '  edge [fontname="Helvetica", fontsize=8.5, color="#8a97a8",'
        ' fontcolor="#5a6675", arrowsize=0.6];',
    ]
    for name, owner, keys in ERD_NODES:
        bg, fg = ERD_STYLE[owner]
        lines.append(
            f'  {name} [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">'
            f'<tr><td bgcolor="{bg}"><font color="{fg}"><b>{name}</b></font></td></tr>'
            f'<tr><td bgcolor="white"><font point-size="9" color="#444">{keys}</font></td></tr>'
            f"</table>>];"
        )
    for src, dst, label, dashed in ERD_EDGES:
        attrs = [f'label="{label}"'] if label else []
        if dashed:
            attrs.append('style=dashed')
        else:
            attrs.append('style=solid color="#1c6b31" penwidth=1.6')
        lines.append(f"  {src} -> {dst} [{' '.join(attrs)}];")
    lines.append("}")
    svg = subprocess.run(
        [dot_bin, "-Tsvg"], input="\n".join(lines).encode(),
        capture_output=True, check=True,
    ).stdout.decode()
    # strip XML prolog/doctype, make responsive
    svg = svg[svg.index("<svg"):]
    svg = svg.replace("<svg ", "<svg style='max-width:100%;height:auto' ", 1)
    return svg


def build_schema_page(e):
    """Column-level documentation of the whole `aa` schema, grouped by owning repo."""
    cols = pd.read_sql(
        """SELECT c.table_name, c.ordinal_position, c.column_name, c.data_type,
                  c.is_nullable, c.column_default
           FROM information_schema.columns c
           JOIN information_schema.tables t
             ON t.table_schema = c.table_schema AND t.table_name = c.table_name
           WHERE c.table_schema = 'aa' AND t.table_type = 'BASE TABLE'
           ORDER BY c.table_name, c.ordinal_position""",
        e,
    )
    cons = pd.read_sql(
        """SELECT rel.relname AS table_name, con.conname,
                  pg_get_constraintdef(con.oid) AS definition
           FROM pg_constraint con
           JOIN pg_class rel ON rel.oid = con.conrelid
           JOIN pg_namespace ns ON ns.oid = rel.relnamespace
           WHERE ns.nspname = 'aa'
           ORDER BY rel.relname, con.contype DESC""",
        e,
    )
    idx = pd.read_sql(
        """SELECT tablename AS table_name, indexname, indexdef
           FROM pg_indexes WHERE schemaname = 'aa'
           ORDER BY tablename, indexname""",
        e,
    )

    def owner_of(t):
        if t in trk_schema.TABLES:
            return "ds-aa-tracking"
        if t in KB_TABLES:
            return "ds-knowledge-base"
        if t in MIRROR_TABLES:
            return "ds-cerf-supplement"
        return "other"

    sections = [
        "<div class='card'>Live column-level schema, read from the dev DB "
        "(<code>information_schema</code> + <code>pg_catalog</code>), grouped by the "
        "repo that owns (i.e. is the single writer of) each table. Constraints and "
        "indexes are shown as Postgres reports them; row counts are as of generation "
        "time. The <code>v_trk_*</code> view SQL at the bottom is this repo's — the "
        "other repos' view definitions aren't readable by the reader role but are "
        "documented in the KB ERD.</div>"
    ]
    sections.append(
        "<h2>ERD</h2>"
        "<div class='card'><p class='meta'>"
        "<span class='badge b-new'>ds-aa-tracking</span>"
        "<span class='badge b-kb'>ds-knowledge-base</span>"
        "<span class='badge b-mirror'>ds-cerf-supplement</span> · "
        "solid green edges = declared foreign keys (the schema's only two, on "
        "<code>activation_allocation</code>); dashed = joins by convention, checked at "
        "load time. Key columns shown; full column lists below.</p>"
        f"<div class='scroll' style='max-height:none'>{build_erd()}</div></div>"
    )
    tables = sorted(cols["table_name"].unique(), key=lambda t: (owner_of(t) != "ds-aa-tracking", t))
    for owner in ("ds-aa-tracking", "ds-knowledge-base", "ds-cerf-supplement", "other"):
        group = [t for t in tables if owner_of(t) == owner]
        if not group:
            continue
        sections.append(f"<h2 style='border-bottom:2px solid #cbd6e2;padding-bottom:6px'>"
                        f"{OWNER_BADGE[owner]} {len(group)} tables</h2>")
        for t in group:
            n = pd.read_sql(f"SELECT count(*) AS n FROM aa.{t}", e)["n"].iloc[0]
            tc = cols[cols["table_name"] == t][
                ["column_name", "data_type", "is_nullable", "column_default"]
            ].rename(columns={"is_nullable": "nullable", "column_default": "default"})
            tc["default"] = tc["default"].fillna("").str.replace("::.*", "", regex=True)
            note = NOTES.get(t)
            keys = cons[cons["table_name"] == t]
            uniq_idx = idx[
                (idx["table_name"] == t)
                & idx["indexdef"].str.contains("UNIQUE")
                & ~idx["indexname"].str.endswith("_pkey")
            ]
            key_bits = [
                f"<li><code>{html.escape(r['conname'])}</code>: "
                f"<code>{html.escape(r['definition'])}</code></li>"
                for _, r in keys.iterrows()
            ] + [
                f"<li><code>{html.escape(r['indexname'])}</code>: "
                f"<code>{html.escape(r['indexdef'].split(' USING ')[-1])}</code> (unique index)</li>"
                for _, r in uniq_idx.iterrows()
            ]
            keys_html = (
                f"<ul class='tight'>{''.join(key_bits)}</ul>" if key_bits
                else "<p class='meta'>no PK/unique constraint (append-only fact "
                     "table; see notes)</p>"
            )
            link = (
                f" · <a href='table-{t}.html'>data</a>"
                if t in trk_schema.TABLES else ""
            )
            sections.append(
                f"<div class='card'><h3 style='margin:2px 0'>aa.{t}"
                f"<span class='meta' style='font-weight:400'> — {n:,} rows{link}</span></h3>"
                + (f"<p class='meta'>{note}</p>" if note else "")
                + keys_html
                + tbl_plain(tc)
                + "</div>"
            )

    sections.append("<h2>Views owned by ds-aa-tracking (SQL)</h2>")
    for name, ddl in trk_schema.VIEWS.items():
        sql = ddl.split("AS", 1)[1].strip() if "AS" in ddl else ddl
        sections.append(
            f"<div class='card'><h3 style='margin:2px 0'>aa.{name}</h3>"
            f"<pre style='overflow-x:auto;font-size:12px;background:#f6f8fa;"
            f"padding:10px;border-radius:4px'>{html.escape(sql)}</pre></div>"
        )
    other_views = pd.read_sql(
        """SELECT table_name FROM information_schema.views
           WHERE table_schema='aa' ORDER BY table_name""",
        e,
    )
    others = [
        v for v in other_views["table_name"] if v not in trk_schema.VIEWS
    ]
    if others:
        sections.append(
            "<p class='meta'>Other views in the schema (KB-owned, documented in the "
            "KB ERD): " + ", ".join(f"<code>aa.{v}</code>" for v in others) + "</p>"
        )
    page("schema.html", "DB schema — the full aa schema by owner", "\n".join(sections))


def tbl_plain(df):
    return (
        "<div class='scroll' style='max-height:none'>"
        + df.to_html(index=False, classes="data", na_rep="", border=0)
        + "</div>"
    )


DECISIONS = """
<div class='card'>Per workbook: which sheets were ingested as primary data, and which
were skipped as derived pivots/scratch (they recompute from the primary sheets or from
data already in the mirror). Flag anything you disagree with.</div>
<h2>julia/2026 AA planning_USE THIS.xlsx</h2>
<ul class='tight'>
<li><b>Status and planning</b> → registry, status, focal points, calendar (from cell
colors), 2026 pre-arranged, Start Fund/READY. <span class='badge b-warn'>caveat</span>
the coordination-group column appears row-shifted in the source for some countries
(e.g. Chad shows Philippines actors) — ingested as-is, needs a fix upstream.</li>
<li><b>Trends</b> — skipped (derived yearly counts).</li>
<li><b>2025 plan w FAO &amp; WFP</b> — skipped (marked outdated in its own name).</li>
</ul>
<h2>julia/AA reports_counting frameworks and countries.xlsx</h2>
<ul class='tight'>
<li><b>2024 / 2025 AA reporting</b> → framework_status, report_channel_inclusion,
prearranged_funding (2025+2026), people_covered, plan_inclusion.</li>
<li><b>2026 GHO</b> → status, funding, GHO inclusion.</li>
</ul>
<h2>julia/OCHA_AA_activations_2020-2026.xlsb</h2>
<ul class='tight'>
<li><b>Overall activations</b> → activation_event (the superset record).</li>
<li><b>Activations by region</b> — skipped (pivot).</li>
</ul>
<h2>yakubu/26 March 2026 CERF Allocation Analysis for AA.xlsx</h2>
<ul class='tight'>
<li><b>Retagged Allocations</b> → emergency_type_override. <b>CIRV</b> → cirv.
<b>HNRP 2025 countries / HNRP FCDO BC analysis / Summary by country</b> →
plan_inclusion.</li>
<li><b>Cholera/Drought/Flood/Storms + regional summaries</b> — skipped: per-hazard
allocation totals are recomputable from <code>aa.cerf_allocation</code> (mirror), which
is the better source; the retags feed the override table instead.</li>
</ul>
<h2>yakubu/AA Displacement Data - Clean.xlsx</h2>
<ul class='tight'>
<li><b>CERF GMS Data 2020-2024</b> → cerf_application_people (planned+reached ×
sex-age/disability/category) + cerf_application_report (narratives, report metadata).</li>
<li><b>OneGMS Data 2024-2025</b> → cerf_allocation_extra (structured AA flag, onset,
response requirements) + planned demographics.</li>
<li><b>Main AA Data / Sheets 1-6 / pivots / CORRECT VALUES / Totals</b> — skipped
(all derived from the two exports above; verified the curated AA set matches).</li>
</ul>
<h2>yakubu/CERF AA - Clean Subgrant Data 2020 - 2025_AR.xlsx</h2>
<ul class='tight'>
<li><b>Sheet3</b> (full CERF subgrants) + <b>Subgrants - June 2026</b> (from the other
workbook; curated AA set with localization) → cerf_subgrant, deduplicated with the
curated rows winning.</li>
<li>All pivot/top-N sheets — skipped (derived).</li>
</ul>
<h2>yakubu/CERF AA Data as of June 1st 2026.xlsx</h2>
<ul class='tight'>
<li><b>Agency HQ Report</b> → cerf_project_supplement (markers, CVA, targeting).</li>
<li><b>Disbursement Data+CVA</b> → cerf_cva_history (aggregated to its grain — the
sheet has no project codes).</li>
<li><b>People covered / Double activations / Co-financing / Pre-arranged /
New-Extended Frameworks / Sector Data - Pre-arranged / 2026 Portfolio for
Insurance</b> → people_covered, prearranged_funding, framework_status,
prearranged_sector_budget.</li>
<li><b>ProjectSearch / Regular Data / Sector Data Jun 2026</b> — skipped: project-level
sector splits, dates and targeting are already in the mirror
(<code>aa.cerf_project</code>/<code>_sector</code>), which covers 2006→present;
Regular Data additionally has visible column corruption (dates in numeric columns).</li>
<li>All remaining pivot sheets — skipped (derived).</li>
</ul>
<h2>Cross-cutting conventions</h2>
<ul class='tight'>
<li>Framework identity = (country_iso3, canonical hazard); raw spellings kept in
*_raw columns; 'Mauretania', 'Congo DR' etc. normalized.</li>
<li>Sheets that disagree are loaded side by side (source in the key) — reconciliation
is a view, not a silent merge; where a single value is needed the newest sheet wins.</li>
<li>EA (early action) events are in scope, flagged <code>aa_or_ea='EA'</code>.</li>
<li>Sub-frameworks (Bangladesh Jamuna/Padma) live in <code>subunit</code>, matching the
KB's window concept rather than creating duplicate frameworks (KB rule D62).</li>
</ul>
"""


if __name__ == "__main__":
    main()
