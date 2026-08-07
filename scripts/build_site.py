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
  <a href="reconciliation.html">Reconciliation</a>
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
<span class='badge b-new'>ds-aa-tracking (this repo, 19 tables + 5 views)</span>
framework_registry · framework_status · framework_focal_point · framework_calendar ·
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
