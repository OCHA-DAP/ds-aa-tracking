"""Set the publication month of learning documents (aa.learning_document.month, 2026-10-23).

1. adds aa.learning_document.month (the same ALTER as schema.ADDITIVE_MIGRATIONS, so a later
   ensure_schema is a no-op for it);
2. sets the month and year of the public documents listed (each with its evidence): `year` is
   the publication year, `year_now` the year recorded before (null when none was). A row is
   touched only when its id AND title match, its year is still `year_now` and it has no month
   yet, so a re-run changes nothing. Add rows to the "set" list of
   reference/learning_publication_months.json to date more documents.

One transaction: all of it or none. Prints what it changed. Run against whatever
DSCI_AZ_DB_DEV_HOST points at (the tunnel: 127.0.0.1:15432).
Usage: uv run python scripts/set_learning_months.py reference/learning_publication_months.json [--dry-run]
"""

import json
import os
import sys
from pathlib import Path

import sqlalchemy as sa

REPO = Path(__file__).parents[1]
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("PGSSLMODE", "require")

import ocha_stratus as stratus  # noqa: E402

ALTER = ("ALTER TABLE IF EXISTS aa.learning_document ADD COLUMN IF NOT EXISTS month smallint "
         "CHECK (month BETWEEN 1 AND 12)")
UPDATE = sa.text("""UPDATE aa.learning_document
    SET month = :month, year = :year, updated_at = now()
    WHERE id = :id AND title = :title AND month IS NULL AND year IS NOT DISTINCT FROM :year_now
      AND NOT internal""")


def main():
    path = next(a for a in sys.argv[1:] if not a.startswith("--"))
    dry = "--dry-run" in sys.argv
    rows = json.loads(Path(path).read_text())["set"]
    print(f"host {os.environ.get('DSCI_AZ_DB_DEV_HOST')} · {len(rows)} months to set"
          + (" · DRY RUN, rolled back" if dry else ""))
    engine = stratus.get_engine(stage="dev", write=True)
    conn = engine.connect()
    tx = conn.begin()
    try:
        conn.execute(sa.text(ALTER))
        done, dated, moved, missed = 0, 0, [], []
        for r in rows:
            n = conn.execute(UPDATE, {k: r[k] for k in ("id", "title", "month", "year", "year_now")}).rowcount
            done += n
            if n:
                continue
            had = conn.execute(sa.text("SELECT month, year FROM aa.learning_document WHERE id = :id AND title = :title"),
                               {"id": r["id"], "title": r["title"]}).first()
            if had is not None and had.month is not None:
                dated += 1
            elif had is not None and had.year != r["year_now"]:
                moved.append(f"{r['id']} (year {had.year}, not {r['year_now']})")
            else:
                missed.append(r["id"])
        print(f"  month set on {done} documents; {dated} had one already"
              + (f"; year changed since, left alone: {moved}" if moved else "")
              + (f"; not found under that id and title (renamed or gone): {missed}" if missed else ""))
        print("  " + ", ".join(f"{m}:{n}" for m, n in conn.execute(sa.text(
            "SELECT coalesce(month::text, '-') AS m, count(*) AS n FROM aa.learning_document "
            "WHERE NOT internal GROUP BY 1 ORDER BY 1")).all()))
        (tx.rollback if dry else tx.commit)()
    except Exception:
        tx.rollback()
        raise
    finally:
        conn.close()
    print("rolled back (dry run)" if dry else "committed ✓")


if __name__ == "__main__":
    main()
