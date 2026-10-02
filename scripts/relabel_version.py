"""Relabel a framework version: move every row keyed (country_iso3, hazard, version) from
one version label to another, across the tables this repo owns, in one audited transaction.

Why: a version's label is its endorsement date (the 2025-08-11 precedent), but a version
entered before its document was endorsed carries a placeholder — NGA flood 2026-06-18 was a
design-session date; the ERC endorsed it on 2026-07-27. The label is part of the key in
several tables, and entries files (scripts/apply_entries.py) can only upsert, so a relabel
needs a database route: the Databricks job, or a laptop through the SSH tunnel.

Also moves `supersedes` pointers at the old label (same pair) and a `valid_from` that was
only the old label padded to a date. Never touches the KB-owned or zz_legacy_ tables.
Refuses when a table holds rows at BOTH labels (merging is a human decision). Each moved
table is audited to aa.entry_audit (field = the column, old -> new label).

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

from ds_aa_tracking import schema  # noqa: E402

OWNED = [*schema.TABLES, *schema.DURABLE_TABLES]


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
                "SELECT table_name, column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'aa'"
            )
        ):
            cols.setdefault(t, {})[c] = d
        targets = [
            t
            for t in OWNED
            if cols.get(t, {}).get("country_iso3") == "text"
            and {"hazard", "version"} <= set(cols[t])
        ]

        def count(t, col, label):
            return conn.execute(
                sa.text(
                    f"SELECT count(*) FROM aa.{t} WHERE country_iso3 = :c AND hazard = :h "
                    f"AND {col} = :v"
                ),
                {**pair, "v": label},
            ).scalar()

        plan = []
        for t in targets:
            n_old, n_new = count(t, "version", old), count(t, "version", new)
            if n_old and n_new:
                sys.exit(
                    f"aa.{t} has rows at both {old} ({n_old}) and {new} ({n_new}) — merge by hand"
                )
            if n_old:
                plan.append((t, "version", n_old))
            if "supersedes" in cols[t] and (n := count(t, "supersedes", old)):
                plan.append((t, "supersedes", n))
        n_vf = conn.execute(
            sa.text(
                "SELECT count(*) FROM aa.framework_version WHERE country_iso3 = :c "
                "AND hazard = :h AND version = :old AND valid_from::text = :old"
            ),
            pair,
        ).scalar()
        if n_vf:  # first: it matches on the old label, which the version move changes
            plan.insert(0, ("framework_version", "valid_from", n_vf))
        if not plan:
            sys.exit(f"nothing labelled {args.key}")
        for t, col, n in plan:
            print(f"  aa.{t}.{col}: {n} row(s) {old} -> {new}")
        if not args.write:
            print("dry run — nothing changed (--write to apply)")
            return

        for t, col, n in plan:
            sets = (
                f"{col} = CAST(:new AS {cols[t][col]})" if col == "valid_from" else f"{col} = :new"
            )
            if "updated_at" in cols[t]:
                sets += ", updated_at = now()"
            where = (
                "version = :old AND valid_from::text = :old"
                if col == "valid_from"
                else f"{col} = :old"
            )
            moved = conn.execute(
                sa.text(
                    f"UPDATE aa.{t} SET {sets} WHERE country_iso3 = :c AND hazard = :h AND {where}"
                ),
                pair,
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
                    "k": f"{iso3}/{hazard}/{old} ({n} row(s))",
                    "f": col,
                    "old": old,
                    "new": new,
                },
            )
        print(f"relabelled {args.key} -> {new}")


if __name__ == "__main__":
    main()
