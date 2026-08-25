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
from ds_aa_tracking.versions import (  # noqa: E402
    attribute_versions,
    build_framework_version,
    historical_activation_events,
)

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
        """SELECT a.kb_framework, a.event_date, a.country_iso3, a.kb_version,
                  a.released_usd, l.application_code
           FROM aa.actual_activation a
           LEFT JOIN aa.activation_allocation l
             ON l.kb_framework = a.kb_framework AND l.event_date = a.event_date""",
        engine,
    )
    ev = tables["activation_event"]
    kb_framework, kb_event_date, app_code, method, act_version = [], [], [], [], []
    for _, e in ev.iterrows():
        slug = kb_map.get((e["country_iso3"], e["hazard"]))
        matched = (None, None, None, None, None)
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
                               exact.iloc[0]["application_code"], "auto-year-month",
                               exact.iloc[0]["kb_version"])
                elif len(cand) == 1:
                    matched = (slug, cand.iloc[0]["event_date"],
                               cand.iloc[0]["application_code"], "auto-year",
                               cand.iloc[0]["kb_version"])
            elif len(cand) == 1:
                matched = (slug, cand.iloc[0]["event_date"],
                           cand.iloc[0]["application_code"], "auto-year",
                           cand.iloc[0]["kb_version"])
            elif len(cand) > 1:
                matched = (None, None, None, "ambiguous", None)
        kb_framework.append(matched[0])
        kb_event_date.append(matched[1])
        app_code.append(matched[2])
        method.append(matched[3])
        act_version.append(matched[4])
    ev["kb_framework"] = kb_framework
    ev["kb_event_date"] = kb_event_date
    ev["application_code"] = app_code
    ev["match_method"] = method
    ev["kb_activation_version"] = act_version


ENVELOPE_RE = __import__("re").compile(r"\((?:AP-)?(?:RHPF|RhPF)-?(\w+)\)|Regional Envelope \((?:RHPF|RhPF)-(\w+)\)", 2)


def seed_fund(engine, tables):
    """aa.fund: CERF + every pooled fund in the CBPF mirror (OCHA pooled funds only —
    agency co-financing is deliberately NOT a fund)."""
    import re

    import pycountry

    funds = pd.read_sql(
        "SELECT pf_id, name, country_code_iso2, parent_pf_id FROM aa.cbpf_fund", engine
    )

    def iso3_of(iso2):
        try:
            return pycountry.countries.get(alpha_2=iso2).alpha_3
        except AttributeError:
            return None

    rows = [{"fund_code": "cerf", "fund_type": "cerf",
             "name": "Central Emergency Response Fund", "country_iso3": None,
             "pf_id": None}]
    for _, f in funds.iterrows():
        iso3 = iso3_of(f["country_code_iso2"])
        m = re.search(r"R[Hh]PF-?(\w+)", str(f["name"]))
        if m:  # regional envelope or a per-country child of one
            env = m.group(1).lower()
            is_envelope = "envelope" in str(f["name"]).lower()
            code = f"rhpf-{env}" if is_envelope else f"rhpf-{env}-{(iso3 or f['pf_id'])}".lower()
            ftype = "regional_fund"
        else:
            code = f"cbpf-{(iso3 or f['pf_id'])}".lower()
            ftype = "cbpf"
        rows.append({"fund_code": code, "fund_type": ftype, "name": f["name"],
                     "country_iso3": iso3, "pf_id": int(f["pf_id"])})
    df = pd.DataFrame(rows).drop_duplicates(subset=["fund_code"])
    tables["fund"] = df
    return dict(zip(df["pf_id"], df["fund_code"]))


def split_activations(tables, pf_to_fund, engine):
    """Allocation-grain sheet rows -> aa.activation + aa.activation_funding.

    One activation per (country, hazard, year, month, event_type); its fund rows
    become activation_funding. event_date is partial ISO at the sheet's precision.
    Framework activations get window_name from the matched KB activation, else
    'unspecified' (curation queue) — every framework activation has a window."""
    ev = tables.pop("activation_event")
    win = pd.read_sql(
        "SELECT kb_framework, event_date, window_name FROM aa.actual_activation", engine
    )
    win_map = {(r["kb_framework"], r["event_date"]): r["window_name"]
               for _, r in win.iterrows()}
    cbpf = pd.read_sql(
        "SELECT pooled_fund_id, allocation_type_id FROM aa.cbpf_allocation", engine
    )
    cbpf_fund_of = {f"cbpf-{r['pooled_fund_id']}-{r['allocation_type_id']}":
                    pf_to_fund.get(r["pooled_fund_id"])
                    for _, r in cbpf.iterrows()}

    def event_date(r):
        if pd.notna(r.get("month")):
            return f"{int(r['year'])}-{int(r['month']):02d}"
        return str(int(r["year"]))

    def fund_code(r):
        if r["fund_source"] == "cerf":
            return "cerf"
        code = r.get("cbpf_allocation_code")
        if code is not None and pd.notna(code) and cbpf_fund_of.get(code):
            return cbpf_fund_of[code]
        return ("rhpf-unspecified" if r["fund_source"] == "regional_fund"
                else "cbpf-unspecified")

    acts, funding = {}, []
    for _, r in ev.iterrows():
        ed = event_date(r)
        key = (r["country_iso3"], r["hazard"], ed, r["event_type"])
        if key not in acts:
            wname = None
            if r["event_type"] == "framework_aa":
                wname = win_map.get((r.get("kb_framework"), r.get("kb_event_date"))) \
                        or "unspecified"
            acts[key] = {
                "country_iso3": r["country_iso3"], "hazard": r["hazard"],
                "event_type": r["event_type"], "event_date": ed,
                "window_name": wname, "event_label": "",
                "kb_framework": r.get("kb_framework"),
                "kb_event_date": r.get("kb_event_date"),
                "kb_activation_version": r.get("kb_activation_version"),
                "people_targeted": r.get("people_targeted"),
                "reported_to_ahub": r.get("reported_to_ahub"),
                "comments": r.get("comments"), "source": r["source"],
            }
        else:
            a = acts[key]
            for col in ("kb_framework", "kb_event_date", "kb_activation_version"):
                if a.get(col) is None and pd.notna(r.get(col)):
                    a[col] = r[col]
            pt = r.get("people_targeted")
            if pd.notna(pt) and (pd.isna(a["people_targeted"]) or
                                 a["people_targeted"] is None or pt > a["people_targeted"]):
                a["people_targeted"] = pt
        a = acts[key]
        # allocation code must match the funding row's fund: CERF codes only on
        # CERF rows (a merged multi-fund event matches one KB activation whose
        # CERF application_code must not leak onto the CBPF row)
        if r["fund_source"] == "cerf":
            alloc = r.get("application_code")
        else:
            alloc = r.get("cbpf_allocation_code")
        funding.append({
            "country_iso3": r["country_iso3"], "hazard": r["hazard"],
            "event_date": ed, "window_name": a["window_name"], "event_label": "",
            "event_type": r["event_type"], "fund_code": fund_code(r),
            "allocation_code": alloc if pd.notna(alloc) else None,
            "amount_usd": r.get("amount_usd"),
            "people_targeted": r.get("people_targeted"),
            "reported_to_ahub": r.get("reported_to_ahub"),
            "match_method": r.get("match_method"), "source": r["source"],
        })
    tables["activation"] = pd.DataFrame(acts.values())
    tables["activation_funding"] = pd.DataFrame(funding)
    print(f"  split: {len(ev)} allocation-grain rows -> "
          f"{len(acts)} activations + {len(funding)} funding rows")


def cbpf_match(engine, tables):
    """Match country/regional-fund activation events to CBPF allocations.

    Auto-links only when exactly one AA-keyword allocation exists for the event's
    country and year in the mirror; everything else stays null for review."""
    import pycountry

    cbpf = pd.read_sql(
        """SELECT a.pooled_fund_id, a.allocation_type_id, a.year, a.aa_keyword,
                  f.country_code_iso2
           FROM aa.cbpf_allocation a
           LEFT JOIN aa.cbpf_fund f ON f.pf_id = a.pooled_fund_id
           WHERE a.aa_keyword""",
        engine,
    )

    def iso3_of(iso2):
        try:
            return pycountry.countries.get(alpha_2=iso2).alpha_3
        except AttributeError:
            return None

    cbpf["country_iso3"] = cbpf["country_code_iso2"].map(iso3_of)
    ev = tables["activation_event"]
    codes = []
    for _, e in ev.iterrows():
        code = None
        if e["fund_source"] in ("country_fund", "regional_fund"):
            cand = cbpf[
                (cbpf["country_iso3"] == e["country_iso3"])
                & (cbpf["year"] == e["year"])
            ]
            if len(cand) == 1:
                r = cand.iloc[0]
                code = f"cbpf-{r['pooled_fund_id']}-{r['allocation_type_id']}"
        codes.append(code)
    ev["cbpf_allocation_code"] = codes
    n = sum(c is not None for c in codes)
    print(f"  CBPF matches: {n} of "
          f"{(ev['fund_source'].isin(('country_fund', 'regional_fund'))).sum()} "
          "country/regional-fund events")


LEGACY_OBJECTS = [
    "TABLE aa.activation_event",   # split into aa.activation + aa.activation_funding
]


def load(engine, tables):
    with engine.begin() as conn:
        for name, ddl in schema.VIEWS.items():
            conn.execute(sa.text(f"DROP VIEW IF EXISTS aa.{name} CASCADE"))
        for obj in LEGACY_OBJECTS:
            conn.execute(sa.text(f"DROP {obj} CASCADE".replace("DROP TABLE", "DROP TABLE IF EXISTS")))
        for name in schema.TABLES:
            # full-refresh incl. structure: our views are recreated below; nothing
            # outside this repo depends on these tables
            conn.execute(sa.text(f"DROP TABLE IF EXISTS aa.{name} CASCADE"))
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
    hist_ev = historical_activation_events(tables["activation_event"])
    if not hist_ev.empty:
        print(f"  + {len(hist_ev)} historical activation events (reference CSV)")
        tables["activation_event"] = pd.concat(
            [tables["activation_event"], hist_ev], ignore_index=True
        )
    ev = tables["activation_event"]
    ev["event_type"] = [
        "early_action" if str(r["aa_or_ea"]).upper() == "EA"
        else ("adhoc_aa" if r["mechanism"] == "adhoc" else "framework_aa")
        for _, r in ev.iterrows()
    ]
    tables["framework_registry"] = complete_registry(tables)
    engine = stratus.get_engine(stage="dev", write=True)
    print("Crosswalking to KB…")
    kb_crosswalk(engine, tables)
    cbpf_match(engine, tables)
    pf_to_fund = seed_fund(engine, tables)
    split_activations(tables, pf_to_fund, engine)
    print("Building framework versions + attributing facts…")
    fv = build_framework_version(tables)
    tables["framework_version"] = fv
    attribute_versions(tables, fv)
    print("Loading dev DB…")
    load(engine, tables)
    print("Done.")


if __name__ == "__main__":
    main()
