"""Idempotent, NON-destructive schema pass for the ds-aa-tracking aa tables.

DB-first era (2026-09-10): the dev DB is the single source of truth — this
script never DROPs or TRUNCATEs a table. It:
  1. CREATE TABLE IF NOT EXISTS for every owned table (regular + durable),
  2. applies schema.ADDITIVE_MIGRATIONS (append-only ALTERs),
  3. creates indexes,
  4. rebuilds the v_trk_* views (views are derived — DROP+CREATE is safe).

Usage: uv run python scripts/ensure_schema.py
"""

import os
import sys
from pathlib import Path

import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

os.environ.setdefault("PGSSLMODE", "require")

import ocha_stratus as stratus  # noqa: E402

from ds_aa_tracking import schema  # noqa: E402


def ensure_schema(engine):
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE SCHEMA IF NOT EXISTS aa"))
        for name, ddl in {**schema.TABLES, **schema.DURABLE_TABLES}.items():
            conn.execute(sa.text(ddl))
        for stmt in schema.ADDITIVE_MIGRATIONS:
            conn.execute(sa.text(stmt))
        for idx in schema.INDEXES:
            conn.execute(sa.text(idx))
        for name in schema.VIEWS:
            conn.execute(sa.text(f"DROP VIEW IF EXISTS aa.{name} CASCADE"))
        for name, ddl in schema.VIEWS.items():
            conn.execute(sa.text(ddl))
    print(f"ensured {len(schema.TABLES) + len(schema.DURABLE_TABLES)} tables, "
          f"{len(schema.ADDITIVE_MIGRATIONS)} migrations, {len(schema.VIEWS)} views")


if __name__ == "__main__":
    ensure_schema(stratus.get_engine(stage="dev", write=True))
