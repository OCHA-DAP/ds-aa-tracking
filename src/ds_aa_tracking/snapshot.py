"""Schema-faithful snapshots of the dev ``aa`` schema, so the site can be built (and the
tables inspected locally) without any network path to the database.

Why this exists (2026-09-24): the dev Postgres server is losing public network access;
only Databricks (via its private endpoint) will reach it. GitHub Actions and laptops
therefore build from a blob snapshot instead of the live DB:

    Databricks nightly job ── export ──▶ dev blob  projects/ds-aa-tracking/snapshot/
                                            ├── latest/          (always the newest)
                                            └── YYYY-MM-DD/      (kept 30 days)
    GitHub Actions / laptop ── restore ──▶ throwaway local Postgres ── build_site.py

A snapshot is one consistent REPEATABLE READ transaction: every base table as parquet
(``aa/<table>.parquet``), plus ``schema.json`` (columns with exact Postgres types,
defaults, sequences, constraints, indexes, view definitions, comments) and
``manifest.json`` (timestamp, row counts). ``restore`` recreates the schema verbatim so
the ~60 ad-hoc queries in the build, and the schema/ERD page, work unchanged against
``localhost``. Nothing is ported to another SQL dialect.

The KB-owned and CERF-mirror tables that live in ``aa`` but are not in ``schema.py`` are
captured the same way (the DDL comes from the catalog, not from this repo).
"""

from __future__ import annotations

import datetime as dt
import io
import json
import re
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

SCHEMA = "aa"
CONTAINER = "projects"
PREFIX = "ds-aa-tracking/snapshot"
KEEP_DAYS = 30
NULL = "\\N"  # COPY null marker: unquoted \N; pandas never quotes it, '' stays ''

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres", "db"}


def q(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


# --------------------------------------------------------------------------- export
_CATALOG = {
    "tables": """
        SELECT c.relname AS name
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = :s AND c.relkind IN ('r', 'p') ORDER BY 1""",
    "columns": """
        SELECT c.relname AS table_name, a.attnum, a.attname AS name,
               format_type(a.atttypid, a.atttypmod) AS type, a.attnotnull AS not_null,
               pg_get_expr(d.adbin, d.adrelid) AS "default"
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
        LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
        WHERE n.nspname = :s AND c.relkind IN ('r', 'p') ORDER BY 1, 2""",
    "sequences": """
        SELECT sequencename AS name, data_type, start_value, increment_by, last_value
        FROM pg_sequences WHERE schemaname = :s ORDER BY 1""",
    "constraints": """
        SELECT c.relname AS table_name, con.conname AS name, con.contype AS type,
               pg_get_constraintdef(con.oid) AS definition
        FROM pg_constraint con
        JOIN pg_class c ON c.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = :s
        ORDER BY CASE con.contype WHEN 'p' THEN 0 WHEN 'u' THEN 1 WHEN 'c' THEN 2
                                  WHEN 'x' THEN 3 ELSE 9 END, 1, 2""",
    "indexes": """
        SELECT i.tablename AS table_name, i.indexname AS name, i.indexdef AS definition
        FROM pg_indexes i
        WHERE i.schemaname = :s
          AND NOT EXISTS (SELECT 1 FROM pg_constraint con
                          JOIN pg_class ic ON ic.oid = con.conindid
                          JOIN pg_namespace n ON n.oid = ic.relnamespace
                          WHERE n.nspname = :s AND ic.relname = i.indexname)
        ORDER BY 1, 2""",
    "views": """
        SELECT c.relname AS name, c.relkind AS kind, pg_get_viewdef(c.oid, true) AS definition
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = :s AND c.relkind IN ('v', 'm') ORDER BY 1""",
    "comments": """
        SELECT c.relname AS table_name, a.attname AS column_name, d.description
        FROM pg_description d
        JOIN pg_class c ON c.oid = d.objoid AND d.classoid = 'pg_class'::regclass
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.objsubid
                                 AND d.objsubid > 0
        WHERE n.nspname = :s ORDER BY 1, 2""",
}


def _records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records", date_format="iso"))


def export(engine, out: Path, source: str = "") -> dict:
    """Write a snapshot of schema ``aa`` into ``out/`` (parquet + schema.json + manifest)."""
    out.mkdir(parents=True, exist_ok=True)
    (out / SCHEMA).mkdir(exist_ok=True)
    started = dt.datetime.now(dt.timezone.utc)
    meta: dict = {}
    counts: dict[str, int] = {}
    # one REPEATABLE READ transaction => every table and the catalog agree
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin():
            for key, sql in _CATALOG.items():
                meta[key] = _records(pd.read_sql(sa.text(sql), conn, params={"s": SCHEMA}))
            for t in [r["name"] for r in meta["tables"]]:
                df = pd.read_sql(
                    sa.text(f"SELECT * FROM {q(SCHEMA)}.{q(t)}"), conn,
                    dtype_backend="numpy_nullable",
                )
                df.to_parquet(out / SCHEMA / f"{t}.parquet", index=False)
                counts[t] = int(len(df))
    manifest = {
        "snapshot_at": started.isoformat(timespec="seconds"),
        "schema": SCHEMA,
        "source": source,
        "n_tables": len(counts),
        "n_views": len(meta["views"]),
        "rows": counts,
        "total_rows": int(sum(counts.values())),
    }
    (out / "schema.json").write_text(json.dumps(meta, indent=1, default=str))
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


# ----------------------------------------------------------------------------- blob
def upload(out: Path, stage: str = "dev", day: dt.date | None = None) -> list[str]:
    """Upload ``out/`` to ``PREFIX/latest/`` and ``PREFIX/<day>/``; return blob prefixes."""
    import ocha_stratus as stratus

    day = day or dt.datetime.now(dt.timezone.utc).date()
    prefixes = [f"{PREFIX}/latest", f"{PREFIX}/{day.isoformat()}"]
    files = sorted(p for p in out.rglob("*") if p.is_file())
    for pfx in prefixes:
        for p in files:
            stratus.upload_blob_data(
                p.read_bytes(), f"{pfx}/{p.relative_to(out).as_posix()}",
                stage=stage, container_name=CONTAINER,
            )
    return prefixes


def prune(stage: str = "dev", keep_days: int = KEEP_DAYS, today: dt.date | None = None) -> list[str]:
    """Delete dated snapshot folders older than ``keep_days``; return the deleted prefixes."""
    import ocha_stratus as stratus

    today = today or dt.datetime.now(dt.timezone.utc).date()
    names = stratus.list_container_blobs(
        name_starts_with=f"{PREFIX}/", stage=stage, container_name=CONTAINER
    )
    old: dict[str, list[str]] = {}
    for n in names:
        m = re.match(rf"^{re.escape(PREFIX)}/(\d{{4}}-\d{{2}}-\d{{2}})/", n)
        if m and (today - dt.date.fromisoformat(m.group(1))).days > keep_days:
            old.setdefault(m.group(1), []).append(n)
    if old:
        cc = stratus.get_container_client(container_name=CONTAINER, stage=stage, write=True)
        for names_ in old.values():
            for n in names_:
                cc.delete_blob(n)
    return sorted(old)


def download(snapshot: str, dest: Path, stage: str = "dev") -> Path:
    """Fetch ``PREFIX/<snapshot>/`` (``latest`` or ``YYYY-MM-DD``) into ``dest/``."""
    import ocha_stratus as stratus

    pfx = f"{PREFIX}/{snapshot}/"
    names = stratus.list_container_blobs(name_starts_with=pfx, stage=stage, container_name=CONTAINER)
    if not names:
        raise SystemExit(f"no snapshot at {CONTAINER}/{pfx} on the {stage} blob")
    # a hierarchical-namespace account lists directory placeholders too: skip them
    dirs = {n.rsplit("/", 1)[0] for n in names if "/" in n}
    for n in names:
        if n in dirs or n.endswith("/"):
            continue
        p = dest / n[len(pfx):]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(stratus.load_blob_data(n, stage=stage, container_name=CONTAINER))
    return dest


# --------------------------------------------------------------------------- restore
def _copy_in(raw_conn, table: str, df: pd.DataFrame):
    cols = ", ".join(q(c) for c in df.columns)
    buf = io.StringIO()
    df.to_csv(buf, index=False, na_rep=NULL)
    buf.seek(0)
    with raw_conn.cursor() as cur:
        cur.copy_expert(
            f"COPY {q(SCHEMA)}.{q(table)} ({cols}) FROM STDIN "
            f"WITH (FORMAT csv, HEADER true, NULL '{NULL}')", buf)


def _exec_all(conn, stmts: list[tuple[str, str]], what: str) -> list[str]:
    """Run each (label, sql) in its own savepoint; return labels that failed."""
    failed = []
    for label, sql in stmts:
        sp = conn.begin_nested()
        try:
            conn.execute(sa.text(sql))
            sp.commit()
        except Exception as exc:  # noqa: BLE001 — report and continue
            sp.rollback()
            failed.append(label)
            print(f"  ! {what} {label}: {str(exc).splitlines()[0][:160]}")
    return failed


def restore(engine, src: Path, allow_remote: bool = False) -> dict:
    """Drop and recreate schema ``aa`` on ``engine`` from a snapshot directory.

    Refuses any non-local host unless ``allow_remote`` — this DROPs the schema.
    """
    host = engine.url.host or ""
    if host not in LOCAL_HOSTS and not allow_remote:
        raise SystemExit(f"refusing to DROP SCHEMA {SCHEMA} on non-local host {host!r} "
                         "(pass --allow-remote if you really mean it)")
    meta = json.loads((src / "schema.json").read_text())
    manifest = json.loads((src / "manifest.json").read_text())
    S = q(SCHEMA)
    problems: list[str] = []

    with engine.begin() as conn:
        conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {S} CASCADE"))
        conn.execute(sa.text(f"CREATE SCHEMA {S}"))
        for s in meta["sequences"]:
            conn.execute(sa.text(
                f"CREATE SEQUENCE {S}.{q(s['name'])} AS {s['data_type']} "
                f"INCREMENT BY {s['increment_by']} START WITH {s['start_value']}"))
        cols_by_table: dict[str, list[dict]] = {}
        for c in meta["columns"]:
            cols_by_table.setdefault(c["table_name"], []).append(c)
        for t in meta["tables"]:
            defs = []
            for c in cols_by_table.get(t["name"], []):
                d = f"{q(c['name'])} {c['type']}"
                if c["not_null"]:
                    d += " NOT NULL"
                if c["default"]:
                    d += f" DEFAULT {c['default']}"
                defs.append(d)
            conn.execute(sa.text(f"CREATE TABLE {S}.{q(t['name'])} ({', '.join(defs)})"))

    # data: COPY per table (fast, and Postgres parses the text, so types are exact)
    raw = engine.raw_connection()
    try:
        for t in meta["tables"]:
            p = src / SCHEMA / f"{t['name']}.parquet"
            if not p.exists():
                problems.append(f"missing parquet {t['name']}")
                continue
            df = pd.read_parquet(p, dtype_backend="numpy_nullable")
            _copy_in(raw, t["name"], df)
        raw.commit()
    finally:
        raw.close()

    with engine.begin() as conn:
        problems += _exec_all(conn, [
            (f"{c['table_name']}.{c['name']}",
             f"ALTER TABLE {S}.{q(c['table_name'])} ADD CONSTRAINT {q(c['name'])} {c['definition']}")
            for c in meta["constraints"]], "constraint")
        problems += _exec_all(conn, [(i["name"], i["definition"]) for i in meta["indexes"]],
                              "index")
        # views may depend on each other: keep passing until nothing more resolves
        pending = list(meta["views"])
        for _ in range(len(pending) + 1):
            if not pending:
                break
            still = []
            for v in pending:
                kind = "MATERIALIZED VIEW" if v["kind"] == "m" else "VIEW"
                sp = conn.begin_nested()
                try:
                    conn.execute(sa.text(f"CREATE {kind} {S}.{q(v['name'])} AS {v['definition']}"))
                    sp.commit()
                except Exception:  # noqa: BLE001
                    sp.rollback()
                    still.append(v)
            if len(still) == len(pending):
                break
            pending = still
        for v in pending:  # report the real error for whatever never resolved
            _exec_all(conn, [(v["name"], f"CREATE VIEW {S}.{q(v['name'])} AS {v['definition']}")],
                      "view")
            problems.append(f"view {v['name']}")
        _exec_all(conn, [
            (c["table_name"],
             "COMMENT ON " + (f"COLUMN {S}.{q(c['table_name'])}.{q(c['column_name'])}"
                              if c["column_name"] else f"TABLE {S}.{q(c['table_name'])}")
             + " IS :d".replace(":d", "'" + c["description"].replace("'", "''") + "'"))
            for c in meta["comments"] if c["description"]], "comment")
        for s in meta["sequences"]:
            if s["last_value"] is not None:
                conn.execute(sa.text(
                    f"SELECT setval('{SCHEMA}.{q(s['name'])}', {int(s['last_value'])}, true)"))

    # verify row counts against the manifest
    with engine.connect() as conn:
        for t, n in manifest["rows"].items():
            got = conn.execute(sa.text(f"SELECT count(*) FROM {S}.{q(t)}")).scalar()
            if got != n:
                problems.append(f"rowcount {t}: {got} != {n}")
    return {"manifest": manifest, "problems": problems}
