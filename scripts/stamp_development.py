"""Stamp aa.framework_version.development_since on development versions that lack it.

In-development frameworks count toward pre-arranged money, in the yearly figures too, from
the day they went into development. Nobody has to remember to enter that date: the nightly
job runs this before the snapshot, so a development version gets today's date the first night
it exists (an explicit date entered with the version is never overwritten). Does nothing on a
database that does not have the column yet.

Usage: uv run python scripts/stamp_development.py [--dry-run]
"""

import os
import sys

import sqlalchemy as sa

os.environ.setdefault("PGSSLMODE", "require")

import ocha_stratus as stratus  # noqa: E402


def main():
    dry = "--dry-run" in sys.argv
    engine = stratus.get_engine(stage="dev", write=not dry)
    with engine.begin() as conn:
        has = conn.execute(sa.text(
            "SELECT 1 FROM information_schema.columns WHERE table_schema = 'aa' "
            "AND table_name = 'framework_version' AND column_name = 'development_since'")).first()
        if not has:
            print("development_since: column not there yet (run the schema migration); nothing done")
            return
        rows = conn.execute(sa.text(
            "SELECT country_iso3, hazard, version FROM aa.framework_version "
            "WHERE kb_status IN ('development', 'pre-development') AND development_since IS NULL")).fetchall()
        for r in rows:
            print(f"  {'(dry) ' if dry else ''}development_since = today: {r.country_iso3}/{r.hazard}/{r.version}")
        if rows and not dry:
            conn.execute(sa.text(
                "UPDATE aa.framework_version SET development_since = CURRENT_DATE "
                "WHERE kb_status IN ('development', 'pre-development') AND development_since IS NULL"))
        print(f"{len(rows)} development version(s) stamped" + (" (dry run)" if dry else ""))


if __name__ == "__main__":
    main()
