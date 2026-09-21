"""Window-first migration (2026-09-21): idempotent, non-destructive.

Hierarchy after this migration:
  country_hazard -> framework_version -> window -> window_activation / simulated_activation
                                                 / window_funding
  country_hazard -> adhoc_activation   (ad hoc AA and early-action allocations)

What it does, and only once (every step checks the current state first):
  1. renames framework_registry -> country_hazard (same columns, same key);
  2. renames the retired tables to zz_legacy_<name> (kept read-only for history):
     activation, prearranged_funding, prearranged_sector_budget, entered_version_funding;
  3. after ensure_schema created the new tables, seeds them from the legacy tables —
     window_activation + adhoc_activation from activation; window_funding from
     prearranged_funding, prearranged_sector_budget, the KB funding_breakdown,
     entered_window_funding and entered_version_funding — attributing version-level
     rows to the version's window when it has exactly one ('single' when it has none
     named), and to the 'unattributed' sentinel when it has several.
Compatibility views named framework_registry / activation / prearranged_funding are
(re)created by ensure_schema so nothing outside this repo breaks at once.
"""

import sqlalchemy as sa

LEGACY_RENAMES = ["activation", "prearranged_funding", "prearranged_sector_budget",
                  "entered_version_funding"]


def _relkind(conn, name):
    return conn.execute(sa.text(
        "SELECT c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'aa' AND c.relname = :n"), {"n": name}).scalar()


def _count(conn, name):
    return conn.execute(sa.text(f"SELECT count(*) FROM aa.{name}")).scalar()


def rename_legacy(conn):
    """Step 1 + 2: run BEFORE the CREATE TABLE pass."""
    done = []
    if _relkind(conn, "framework_registry") == "r" and _relkind(conn, "country_hazard") is None:
        conn.execute(sa.text("ALTER TABLE aa.framework_registry RENAME TO country_hazard"))
        done.append("framework_registry -> country_hazard")
    for t in LEGACY_RENAMES:
        if _relkind(conn, t) == "r":
            conn.execute(sa.text(f"ALTER TABLE aa.{t} RENAME TO zz_legacy_{t}"))
            done.append(f"{t} -> zz_legacy_{t}")
    # migration-era health view over the retired tables
    conn.execute(sa.text("DROP VIEW IF EXISTS aa.v_trk_version_attribution"))
    return done


def _window_rule(conn):
    """(country, hazard, version) -> window to attribute version-level rows to."""
    rows = conn.execute(sa.text("""
        SELECT country_iso3, hazard, version, string_agg(DISTINCT window_name, '|') AS names,
               count(DISTINCT window_name) AS n
        FROM (SELECT country_iso3, hazard, version, window_name FROM aa.window
              UNION SELECT country_iso3, hazard, version, window_name FROM aa.entered_window) x
        GROUP BY 1, 2, 3""")).fetchall()
    rule = {}
    for c, h, v, names, n in rows:
        rule[(c, h, v)] = names if n == 1 else "unattributed"
    return lambda c, h, v: rule.get((c, h, v), "single")


def seed_from_legacy(conn):
    """Step 3: run AFTER the CREATE TABLE pass. Seeds only empty targets."""
    done = []
    # ---- activations
    if _relkind(conn, "zz_legacy_activation") == "r" and _count(conn, "window_activation") == 0:
        n = conn.execute(sa.text("""
            INSERT INTO aa.window_activation (country_iso3, hazard, version, window_name,
                event_date, event_label, full_activation, people_targeted, url,
                reported_to_ahub, kb_event_date, comments, source)
            SELECT a.country_iso3, a.hazard, a.version, coalesce(a.window_name, 'unspecified'),
                   a.event_date, coalesce(a.event_label, ''), k.full_activation,
                   a.people_targeted, k.url, a.reported_to_ahub, a.kb_event_date,
                   a.comments, a.source
            FROM aa.zz_legacy_activation a
            LEFT JOIN LATERAL (
                SELECT full_activation, url FROM aa.actual_activation x
                WHERE x.kb_framework = a.kb_framework AND x.event_date = a.kb_event_date
                ORDER BY (x.country_iso3 = a.country_iso3) DESC LIMIT 1) k ON true
            WHERE a.event_type = 'framework_aa' AND a.version IS NOT NULL
            ON CONFLICT DO NOTHING""")).rowcount
        done.append(f"window_activation: {n} rows")
    if _relkind(conn, "zz_legacy_activation") == "r" and _count(conn, "adhoc_activation") == 0:
        n = conn.execute(sa.text("""
            INSERT INTO aa.adhoc_activation (country_iso3, hazard, event_type, event_date,
                event_label, people_targeted, reported_to_ahub, comments, source)
            SELECT country_iso3, hazard, event_type, event_date, coalesce(event_label, ''),
                   people_targeted, reported_to_ahub, comments, source
            FROM aa.zz_legacy_activation
            WHERE event_type IN ('adhoc_aa', 'early_action')
            ON CONFLICT DO NOTHING""")).rowcount
        done.append(f"adhoc_activation: {n} rows")
    # ---- funding
    if _count(conn, "window_funding") == 0:
        win = _window_rule(conn)
        funds = {r[0] for r in conn.execute(sa.text("SELECT fund_code FROM aa.fund"))}
        ins = sa.text("""
            INSERT INTO aa.window_funding (country_iso3, hazard, version, window_name, kind,
                fund_code, financier, agency, sector, amount_usd, year, provenance, source, note)
            VALUES (:c, :h, :v, :w, :kind, :fund, :fin, :agency, :sector, :amt, :year,
                    :prov, :src, :note)
            ON CONFLICT DO NOTHING""")
        total = 0

        def add(c, h, v, w, kind, fund, fin, agency, sector, amt, year, prov, src, note):
            nonlocal total
            if fund is not None and kind in ("cofinancing", "non_aa_mobilised"):
                fund = None
            if fund is None and kind == "prearranged":
                kind = "cofinancing"
            total += conn.execute(ins, dict(c=c, h=h, v=v, w=w, kind=kind, fund=fund, fin=fin,
                                            agency=agency, sector=sector, amt=amt, year=year,
                                            prov=prov, src=src, note=note)).rowcount

        if _relkind(conn, "zz_legacy_prearranged_funding") == "r":
            for r in conn.execute(sa.text(
                    "SELECT * FROM aa.zz_legacy_prearranged_funding WHERE version IS NOT NULL")).mappings():
                w = win(r["country_iso3"], r["hazard"], r["version"])
                add(r["country_iso3"], r["hazard"], r["version"], w, r["kind"], r["fund_code"],
                    r["financier"], None, None, r["amount_usd"], r["year"],
                    "window-unattributed" if w == "unattributed" else "sheet", r["source"],
                    r["remarks"])
        if _relkind(conn, "zz_legacy_prearranged_sector_budget") == "r":
            for r in conn.execute(sa.text(
                    "SELECT * FROM aa.zz_legacy_prearranged_sector_budget WHERE version IS NOT NULL")).mappings():
                w = r["window_name"] or win(r["country_iso3"], r["hazard"], r["version"])
                yr = int(r["year_label"]) if r["year_label"] and str(r["year_label"]).isdigit() else None
                add(r["country_iso3"], r["hazard"], r["version"], w, "prearranged", "cerf", None,
                    r["agency"], r["sector"], r["amount_usd"], yr,
                    "window-unattributed" if w == "unattributed" else "sheet", r["source"],
                    r["status"])
        # KB structural split (agency x sector per window)
        srcmap = {"CERF": ("prearranged", "cerf"), "NHF": ("prearranged", "cbpf-nga"),
                  "AHF": ("prearranged", "cbpf-afg")}
        for r in conn.execute(sa.text(
                "SELECT * FROM aa.funding_breakdown WHERE amount_usd IS NOT NULL")).mappings():
            fs = r["fund_source"]
            # no fund source on the KB page = the CERF envelope split (the template's default)
            kind, fund = srcmap.get(fs or "CERF", ("cofinancing", None))
            if fund and fund not in funds:
                fund = "cbpf-unspecified" if "cbpf-unspecified" in funds else None
            fin = None if fund else (fs or "unspecified")
            w = r["window_name"] or win(r["country_iso3"], r["hazard"], r["version"])
            add(r["country_iso3"], r["hazard"], r["version"], w, kind, fund, fin,
                r["agency"], r["sector"], r["amount_usd"], None,
                "window-unattributed" if w == "unattributed" else "kb",
                "kb-funding-breakdown",
                (r["provenance"] or "") + ("" if fs else " (fund source unspecified on the KB page)"))
        for r in conn.execute(sa.text("SELECT * FROM aa.entered_window_funding")).mappings():
            kind = "cofinancing" if r["fund_code"] in ("cofinancing", "other") else "prearranged"
            fund = None if kind == "cofinancing" else r["fund_code"]
            add(r["country_iso3"], r["hazard"], r["version"], r["window_name"], kind, fund,
                r["financier"], None, None, r["amount_usd"], None, "entered",
                f"entered:{r['entered_by']}", None)
        if _relkind(conn, "zz_legacy_entered_version_funding") == "r":
            for r in conn.execute(sa.text("SELECT * FROM aa.zz_legacy_entered_version_funding")).mappings():
                kind = "cofinancing" if r["fund_code"] in ("cofinancing", "other") else "prearranged"
                fund = None if kind == "cofinancing" else r["fund_code"]
                w = win(r["country_iso3"], r["hazard"], r["version"])
                add(r["country_iso3"], r["hazard"], r["version"], w, kind, fund,
                    r["financier"], None, None, r["total_usd"], None,
                    "window-unattributed" if w == "unattributed" else "entered",
                    f"entered:{r['entered_by']}", None)
        done.append(f"window_funding: {total} rows")
    return done
