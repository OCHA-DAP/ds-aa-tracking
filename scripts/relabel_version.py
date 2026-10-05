"""Relabel a framework version: move every row keyed (country_iso3, hazard, version) from
one version label to another, across the schema's base tables, in one audited transaction.

Why: a version's label is its endorsement date (the 2025-08-11 precedent), but a version
entered before its document was endorsed carries a placeholder — NGA flood 2026-06-18 was a
design-session date; the ERC endorsed it on 2026-07-27. The label is part of the key in
several tables, and entries files (scripts/apply_entries.py) can only add or update rows, so
a relabel needs a database route: the Databricks job (nightly.py --relabel), or a laptop
through the SSH tunnel.

Covers every BASE table with a text country_iso3 + hazard + version — the backtest tables
(window, simulated_activation, version_performance_reported) and the frozen KB-era record
too (left behind they would dangle, and the backtest tables' foreign keys to the version
would fail the transaction) — but never the zz_legacy_ history, and never a view. A version
whose backtest is SEALED can't be relabelled: the database refuses it outside an erratum,
so relabel to the endorsement date before sealing. aa.version_page is keyed by the KB slug instead: its row moves with the
version unless another country still uses the same slug at the old label (a shared regional
page stays). Also moves `supersedes` pointers at the old label (same pair) and a
`valid_from` that was only the old label padded to a date. Refuses when a table holds rows
at BOTH labels (merging is a human decision). Each move is audited to aa.entry_audit.

Usage:
  uv run python scripts/relabel_version.py NGA/flood/2026-06-18 2026-07-27          # dry run
  uv run python scripts/relabel_version.py NGA/flood/2026-06-18 2026-07-27 --write --note "…"
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
os.environ.setdefault("PGSSLMODE", "require")

import ocha_stratus as stratus  # noqa: E402

PAIR = "country_iso3 = :c AND hazard = :h"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("key", help="ISO3/hazard/old-version")
    ap.add_argument("new", help="new version label")
    ap.add_argument("--write", action="store_true", help="apply (default: dry run)")
    ap.add_argument("--by", default=getpass.getuser())
    ap.add_argument("--note", default="", help="why — recorded in the audit")
    args = ap.parse_args()
    iso3, hazard, old = args.key.split("/", 2)
    new = args.new
    pair = {"c": iso3, "h": hazard, "old": old, "new": new}

    engine = stratus.get_engine(stage="dev", write=True)
    with engine.begin() as conn:
        cols = {}
        for t, c, d in conn.execute(
            sa.text(
                "SELECT c.table_name, c.column_name, c.data_type "
                "FROM information_schema.columns c JOIN information_schema.tables t "
                "ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
                "WHERE c.table_schema = 'aa' AND t.table_type = 'BASE TABLE'"
            )
        ):
            cols.setdefault(t, {})[c] = d
        targets = sorted(
            t
            for t in cols
            if not t.startswith("zz_legacy_")
            and cols[t].get("country_iso3") == "text"
            and {"hazard", "version"} <= set(cols[t])
        )

        def scalar(sql, **kw):
            return conn.execute(sa.text(sql), {**pair, **kw}).scalar()

        # each step: (table, column, rows expected, WHERE, extra params); run in this order
        plan = []
        n_vf = scalar(
            f"SELECT count(*) FROM aa.framework_version WHERE {PAIR} "
            "AND version = :old AND valid_from::text = :old"
        )
        if n_vf:  # first: it matches on the old label, which the version move changes
            plan.append(
                (
                    "framework_version",
                    "valid_from",
                    n_vf,
                    f"{PAIR} AND version = :old AND valid_from::text = :old",
                    {},
                )
            )
        for t in targets:
            n_old = scalar(f"SELECT count(*) FROM aa.{t} WHERE {PAIR} AND version = :old")
            n_new = scalar(f"SELECT count(*) FROM aa.{t} WHERE {PAIR} AND version = :new")
            if n_old and n_new:
                sys.exit(
                    f"aa.{t} has rows at both {old} ({n_old}) and {new} ({n_new}) — merge by hand"
                )
            if n_old:
                plan.append((t, "version", n_old, f"{PAIR} AND version = :old", {}))
            if "supersedes" in cols[t]:
                if n := scalar(f"SELECT count(*) FROM aa.{t} WHERE {PAIR} AND supersedes = :old"):
                    plan.append((t, "supersedes", n, f"{PAIR} AND supersedes = :old", {}))
        if "version_page" in cols:
            slugs = [
                r[0]
                for r in conn.execute(
                    sa.text(
                        f"SELECT DISTINCT kb_framework FROM aa.framework_version WHERE {PAIR} "
                        "AND version = :old AND kb_framework IS NOT NULL"
                    ),
                    pair,
                )
            ]
            for slug in slugs:
                others = scalar(
                    "SELECT count(*) FROM aa.framework_version WHERE kb_framework = :s "
                    "AND version = :old AND NOT (country_iso3 = :c AND hazard = :h)",
                    s=slug,
                )
                where = "kb_framework = :s AND version = :old"
                n_old = scalar(f"SELECT count(*) FROM aa.version_page WHERE {where}", s=slug)
                n_new = scalar(
                    "SELECT count(*) FROM aa.version_page WHERE kb_framework = :s "
                    "AND version = :new",
                    s=slug,
                )
                if not n_old:
                    continue
                if others:
                    print(
                        f"  aa.version_page {slug}/{old}: shared with {others} other "
                        "version row(s) — left in place"
                    )
                elif n_new:
                    sys.exit(
                        f"aa.version_page {slug} has rows at both {old} and {new} — merge by hand"
                    )
                else:
                    plan.append(("version_page", "version", n_old, where, {"s": slug}))
        if not plan:
            sys.exit(f"nothing labelled {args.key}")
        for t, col, n, _, extra in plan:
            print(
                f"  aa.{t}.{col}: {n} row(s) {old} -> {new}"
                + (f"  ({extra['s']})" if extra else "")
            )
        if not args.write:
            print("dry run — nothing changed (--write to apply)")
            return

        for t, col, n, where, extra in plan:
            sets = (
                f"{col} = CAST(:new AS {cols[t][col]})" if col == "valid_from" else f"{col} = :new"
            )
            if "updated_at" in cols[t]:
                sets += ", updated_at = now()"
            moved = conn.execute(
                sa.text(f"UPDATE aa.{t} SET {sets} WHERE {where}"), {**pair, **extra}
            ).rowcount
            if moved != n:  # raising rolls the whole relabel back
                raise SystemExit(f"aa.{t}.{col}: expected {n} row(s), moved {moved}")
            conn.execute(
                sa.text(
                    "INSERT INTO aa.entry_audit (entered_by, table_name, row_key, field, "
                    "old_value, new_value) VALUES (:by, :t, :k, :f, :old, :new)"
                ),
                {
                    "by": f"relabel_version.py ({args.by})"
                    + (f": {args.note}" if args.note else ""),
                    "t": t,
                    "k": f"{extra.get('s') or f'{iso3}/{hazard}'}/{old} ({n} row(s))",
                    "f": col,
                    "old": old,
                    "new": new,
                },
            )
        print(f"relabelled {args.key} -> {new}")


if __name__ == "__main__":
    main()
