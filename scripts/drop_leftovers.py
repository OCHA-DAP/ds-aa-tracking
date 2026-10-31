"""One-off (D168): retire what was left from building the tracker, after copying it to the
archive on the private dev blob.

What goes:
- the pre-window tables, renamed zz_legacy_* on 2026-09-21 and read by nothing since;
- version_match on framework_status, framework_focal_point, framework_calendar,
  people_covered and report_channel_inclusion: how a version was guessed when the rows were
  seeded from the team's workbooks;
- version_page.frontmatter_text (the knowledge-base page's raw YAML at import) and
  version_performance_reported.gsheet_tab (the backtest spreadsheet's tab);
- the views framework_registry and framework_version_map (old names kept for one release)
  and the sheets-versus-KB queues v_trk_activation_kb_only / v_trk_activation_reconciliation.

What is renamed: source labels that name the colleagues whose workbooks seeded the tables
(julia-* -> aa-workbook-*, yakubu-* -> cerf-workbook-*), and the version source
kb-frontmatter -> aa-team (a version first recorded from the team's knowledge-base page).

Archive first: every table losing a column or going whole, as parquet, plus the label map,
under projects/ds-aa-tracking/archive/2026-10-30-leftovers/ on the dev blob. Then ONE
transaction: drops, relabels, and the schema's views rebuilt as scripts/ensure_schema.py
does. Refuses if a view outside this repo's schema.py depends on what goes, or if a new
label already exists. Safe to re-run: what is already gone is skipped.

  uv run python scripts/drop_leftovers.py            # dry run: what would be archived and changed
  uv run python scripts/drop_leftovers.py --write    # the nightly job runs this with --drop-leftovers
  uv run python scripts/drop_leftovers.py --write --archive-to DIR   # a local test DB: archive to DIR
"""

import argparse
import io
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
os.environ.setdefault("PGSSLMODE", "require")

import ocha_stratus as stratus  # noqa: E402

from ds_aa_tracking import schema  # noqa: E402

ARCHIVE = "ds-aa-tracking/archive/2026-10-30-leftovers"
TABLES = ["zz_legacy_activation", "zz_legacy_prearranged_funding",
          "zz_legacy_prearranged_sector_budget", "zz_legacy_entered_version_funding"]
COLUMNS = [("framework_status", "version_match"), ("framework_focal_point", "version_match"),
           ("framework_calendar", "version_match"), ("people_covered", "version_match"),
           ("report_channel_inclusion", "version_match"), ("version_page", "frontmatter_text"),
           ("version_performance_reported", "gsheet_tab")]
VIEWS = ["framework_registry", "framework_version_map", "v_trk_activation_kb_only",
         "v_trk_activation_reconciliation"]
RELABEL = [("^julia-", "aa-workbook-"), ("^yakubu-", "cerf-workbook-")]


def present(conn):
    """What of the list is still in the database."""
    rel = {r[0]: r[1] for r in conn.execute(sa.text(
        "SELECT c.relname, c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'aa' AND c.relkind IN ('r', 'v')"))}
    cols = {(r[0], r[1]) for r in conn.execute(sa.text(
        "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'aa'"))}
    return ([t for t in TABLES if rel.get(t) == "r"], [tc for tc in COLUMNS if tc in cols],
            [v for v in VIEWS if rel.get(v) == "v"])


def dependents(conn, tables, columns):
    """Views that read a table going, or a column going (CASCADE would drop them)."""
    q = sa.text("""
        SELECT DISTINCT v.relname FROM pg_depend d
        JOIN pg_rewrite rw ON rw.oid = d.objid
        JOIN pg_class v ON v.oid = rw.ev_class
        JOIN pg_class t ON t.oid = d.refobjid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        LEFT JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
        WHERE n.nspname = 'aa' AND v.relname <> t.relname
          AND (t.relname = ANY(:tables) OR (t.relname || '.' || a.attname) = ANY(:cols))""")
    return sorted(r[0] for r in conn.execute(q, {"tables": tables,
                                                 "cols": [f"{t}.{c}" for t, c in columns]}))


def relabels(conn):
    """(table, old, new, rows) for every source label to rename."""
    out = []
    tables = [r[0] for r in conn.execute(sa.text(
        "SELECT c.table_name FROM information_schema.columns c JOIN information_schema.tables t "
        "USING (table_schema, table_name) WHERE c.table_schema = 'aa' AND t.table_type = 'BASE TABLE' "
        "AND c.column_name = 'source' AND c.data_type = 'text' ORDER BY 1"))
              if r[0] not in TABLES]       # the tables going are archived as they are
    for t in tables:
        for old, n in conn.execute(sa.text(
                f"SELECT source, count(*) FROM aa.{t} WHERE source ~ '^(julia|yakubu)-' "
                "OR (:fv AND source = 'kb-frontmatter') GROUP BY 1 ORDER BY 1"), {"fv": t == "framework_version"}):
            new = "aa-team" if old == "kb-frontmatter" else old
            for pat, rep in RELABEL:
                new = re.sub(pat, rep, new)
            out.append((t, old, new, n))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true", help="archive, then drop and relabel (default: dry run)")
    ap.add_argument("--archive-to", type=Path, help="write the archive to this folder, not the blob (local tests)")
    args = ap.parse_args()
    engine = stratus.get_engine(stage="dev", write=True)

    with engine.connect() as conn:
        tables, columns, views = present(conn)
        labels = relabels(conn)
        deps = dependents(conn, tables, columns)
    ours = set(schema.VIEWS) | set(VIEWS)
    if foreign := [v for v in deps if v not in ours]:
        sys.exit(f"refused: views outside schema.py read what would go: {foreign}")
    for t in tables:
        print(f"  drop table aa.{t}")
    for t, c in columns:
        print(f"  drop column aa.{t}.{c}")
    for v in views:
        print(f"  drop view aa.{v}")
    for t, old, new, n in labels:
        print(f"  aa.{t}.source: {old} -> {new} ({n} rows)")
    print(f"  views rebuilt afterwards: {len(schema.VIEWS)} (dropped with them: {deps or 'none'})")
    if not (tables or columns or views or labels):
        print("nothing left to do")
        return
    if not args.write:
        print("dry run — nothing changed (--write to apply)")
        return

    # archive first: every table touched, whole, and the label map
    def keep(data, name):
        if args.archive_to:
            args.archive_to.mkdir(parents=True, exist_ok=True)
            (args.archive_to / name).write_bytes(data)
        else:
            stratus.upload_blob_data(data, f"{ARCHIVE}/{name}", stage="dev", container_name="projects")
    with engine.connect() as conn:
        for t in sorted(set(tables) | {t for t, _ in columns} | {t for t, *_ in labels}):
            df = pd.read_sql(sa.text(f"SELECT * FROM aa.{t}"), conn)
            for c in df.columns:     # json / jsonb columns go as their text
                df[c] = df[c].map(lambda v: json.dumps(v, default=str) if isinstance(v, (dict, list)) else v)
            buf = io.BytesIO()
            df.to_parquet(buf, index=False)
            keep(buf.getvalue(), f"{t}.parquet")
    keep(json.dumps({"tables": tables, "columns": columns, "views": views,
                     "relabels": [dict(zip(("table", "old", "new", "rows"), x)) for x in labels]},
                    indent=1).encode(), "manifest.json")
    print(f"archived to {args.archive_to or 'projects/' + ARCHIVE}/")

    with engine.begin() as conn:
        for t, old, new, n in labels:
            if conn.execute(sa.text(f"SELECT count(*) FROM aa.{t} WHERE source = :n"), {"n": new}).scalar():
                raise SystemExit(f"refused: aa.{t} already has source {new!r}")
            done = conn.execute(sa.text(f"UPDATE aa.{t} SET source = :new WHERE source = :old"),
                                {"old": old, "new": new}).rowcount
            if done != n:   # raising rolls everything back
                raise SystemExit(f"aa.{t}: expected {n} rows labelled {old}, changed {done}")
        for name in [*VIEWS, *schema.VIEWS]:      # the schema's views come back below
            conn.execute(sa.text(f"DROP VIEW IF EXISTS aa.{name} CASCADE"))
        for t, c in columns:
            conn.execute(sa.text(f"ALTER TABLE aa.{t} DROP COLUMN {c}"))
        for t in tables:
            conn.execute(sa.text(f"DROP TABLE aa.{t}"))
        for ddl in schema.VIEWS.values():
            conn.execute(sa.text(ddl))
    print("done: dropped, relabelled, views rebuilt")


if __name__ == "__main__":
    main()
