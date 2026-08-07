"""Parse all tracking workbooks and load the aa.* tracking tables (dev DB).

Full-refresh: every ds-aa-tracking-owned table is truncated and reloaded in one
transaction. KB-owned and mirror tables are read for crosswalking but never written.

Usage: uv run python scripts/ingest.py
"""

import os
import sys
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

os.environ.setdefault("PGSSLMODE", "require")

import ocha_stratus as stratus  # noqa: E402

from ds_aa_tracking import schema  # noqa: E402
from ds_aa_tracking.parsers import parse_all  # noqa: E402

SLUG_HAZARD = [
    ("dry-corridor", "drought"),
    ("drought", "drought"),
    ("flood", "flood"),
    ("cyclone", "storm"),
    ("storm", "storm"),
    ("hurricane", "storm"),
    ("cholera", "cholera"),
]


def slug_hazard(slug):
    for token, hazard in SLUG_HAZARD:
        if token in slug:
            return hazard
    return None


def complete_registry(tables):
    """Registry = planning-sheet rows + every (country, hazard) other sheets track."""
    reg = tables["framework_registry"].copy()
    seen = set(zip(reg["country_iso3"], reg["hazard"]))
    names = dict(zip(reg["country_iso3"], reg["country_name"]))

    extra_frames = []
    for tbl in ("framework_status", "prearranged_funding", "people_covered",
                "prearranged_sector_budget"):
        if tbl in tables:
            extra_frames.append(tables[tbl][["country_iso3", "hazard"]])
    if "activation_event" in tables:
        ev = tables["activation_event"]
        extra_frames.append(
            ev.loc[ev["mechanism"] == "framework", ["country_iso3", "hazard"]]
        )
    extras = pd.concat(extra_frames, ignore_index=True).drop_duplicates()
    rows = []
    for _, r in extras.iterrows():
        key = (r["country_iso3"], r["hazard"])
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "country_iso3": r["country_iso3"], "hazard": r["hazard"],
            "country_name": names.get(r["country_iso3"], r["country_iso3"]),
        })
    if rows:
        reg = pd.concat([reg, pd.DataFrame(rows)], ignore_index=True)
    return reg.drop_duplicates(subset=["country_iso3", "hazard"])


def kb_crosswalk(engine, tables):
    """Fill registry.kb_framework/in_kb and match activation events to the KB."""
    kb = pd.read_sql(
        "SELECT DISTINCT kb_framework, country_iso3 FROM aa.framework_version_map",
        engine,
    )
    kb["hazard"] = kb["kb_framework"].map(slug_hazard)
    kb_map = {
        (r["country_iso3"], r["hazard"]): r["kb_framework"] for _, r in kb.iterrows()
    }

    reg = tables["framework_registry"]
    reg["kb_framework"] = [
        kb_map.get((c, h)) for c, h in zip(reg["country_iso3"], reg["hazard"])
    ]
    reg["in_kb"] = reg["kb_framework"].notna()

    acts = pd.read_sql(
        """SELECT a.kb_framework, a.event_date, a.country_iso3,
                  a.released_usd, l.application_code
           FROM aa.actual_activation a
           LEFT JOIN aa.activation_allocation l
             ON l.kb_framework = a.kb_framework AND l.event_date = a.event_date""",
        engine,
    )
    ev = tables["activation_event"]
    kb_framework, kb_event_date, app_code, method = [], [], [], []
    for _, e in ev.iterrows():
        slug = kb_map.get((e["country_iso3"], e["hazard"]))
        matched = (None, None, None, None)
        if slug is not None:
            cand = acts[
                (acts["kb_framework"] == slug)
                & (acts["event_date"].str.startswith(str(e["year"])))
            ]
            if e["month"] is not None and not pd.isna(e["month"]):
                ym = f"{e['year']}-{int(e['month']):02d}"
                exact = cand[cand["event_date"].str.startswith(ym)]
                if len(exact) >= 1:
                    matched = (slug, exact.iloc[0]["event_date"],
                               exact.iloc[0]["application_code"], "auto-year-month")
                elif len(cand) == 1:
                    matched = (slug, cand.iloc[0]["event_date"],
                               cand.iloc[0]["application_code"], "auto-year")
            elif len(cand) == 1:
                matched = (slug, cand.iloc[0]["event_date"],
                           cand.iloc[0]["application_code"], "auto-year")
            elif len(cand) > 1:
                matched = (None, None, None, "ambiguous")
        kb_framework.append(matched[0])
        kb_event_date.append(matched[1])
        app_code.append(matched[2])
        method.append(matched[3])
    ev["kb_framework"] = kb_framework
    ev["kb_event_date"] = kb_event_date
    ev["application_code"] = app_code
    ev["match_method"] = method


def load(engine, tables):
    with engine.begin() as conn:
        for name, ddl in schema.TABLES.items():
            conn.execute(sa.text(ddl))
        for idx in schema.INDEXES:
            conn.execute(sa.text(idx))
        for name in schema.TABLES:
            df = tables.get(name)
            conn.execute(sa.text(f"TRUNCATE aa.{name}"))
            if df is None or df.empty:
                print(f"  aa.{name}: 0 rows (no source data)")
                continue
            cols = [
                c for c in df.columns
                if c in _table_columns(conn, name)
            ]
            df[cols].to_sql(name, conn, schema="aa", if_exists="append", index=False)
            print(f"  aa.{name}: {len(df)} rows")
        for name, ddl in schema.VIEWS.items():
            conn.execute(sa.text(ddl))
            print(f"  view aa.{name}")


def _table_columns(conn, table):
    rows = conn.execute(sa.text(
        """SELECT column_name FROM information_schema.columns
           WHERE table_schema = 'aa' AND table_name = :t"""
    ), {"t": table})
    return {r[0] for r in rows}


def main():
    print("Parsing workbooks…")
    tables = parse_all()
    tables["framework_registry"] = complete_registry(tables)
    engine = stratus.get_engine(stage="dev", write=True)
    print("Crosswalking to KB…")
    kb_crosswalk(engine, tables)
    print("Loading dev DB…")
    load(engine, tables)
    print("Done.")


if __name__ == "__main__":
    main()
