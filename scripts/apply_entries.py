"""Apply pending data entries (JSON files on the dev blob) to the dev `aa` schema.

Why: since 2026-09-30 the dev database no longer accepts connections from laptops; only
the Databricks job (and the admin page's proxy) reach it. Entries prepared elsewhere are
uploaded as JSON to the PRIVATE dev blob (never git: this repo is public) under
`projects/ds-aa-tracking/entries/`, and the nightly job applies each new file once, before
it takes the snapshot the site is built from.

File format:
    {"entered_by": "who / from what", "note": "...",
     "rows": [{"table": "window_funding", "row": {...column: value...}}, ...]}

Each row is matched on its table's primary key or first unique constraint (looked up in
the catalog, NULLs equal): an existing row is updated with just the fields given (plus
updated_at), a new one inserted; every row is audited to aa.entry_audit with entered_by =
the file name. Two more item kinds, for records that are re-entered as a whole (a backtest
re-run while its framework version is in development):
    {"op": "delete", "table": T, "row": {...key columns...}}
        removes that one row (already absent = nothing to do);
    {"op": "replace", "table": T, "scope": {"country_iso3": …, "hazard": …, "version": …},
     "rows": [{...}, ...]}
        the given rows BECOME the scope's rows in T: everything in the scope is deleted, then
        the rows are inserted (each must sit inside the scope). E.g. a version's
        simulated_activation after a new backtest run — years that dropped out go too.
A sealed backtest (framework_version.backtest_sealed_at) refuses all three: the database
trigger fails the file; corrections to sealed backtests are errata (backtests/README.md).
A file is
applied ONCE: aa.applied_entries records its name and content hash, so a later edit made
in the admin page is never overwritten by a re-run. Changing a file's content makes it
pending again (deliberately).

Usage:
    uv run python scripts/apply_entries.py                 # pending files from the blob
    uv run python scripts/apply_entries.py --dir DIR       # local files instead (testing)
    uv run python scripts/apply_entries.py --upload FILE   # put a file on the blob
    ... [--dry-run]
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
os.environ.setdefault("PGSSLMODE", "require")

import ocha_stratus as stratus  # noqa: E402

CONTAINER, PREFIX = "projects", "ds-aa-tracking/entries"
TRACK_DDL = """
    CREATE TABLE IF NOT EXISTS aa.applied_entries (
        name text PRIMARY KEY,
        sha256 text NOT NULL,
        n_rows integer NOT NULL,
        entered_by text,
        applied_at timestamptz NOT NULL DEFAULT now()
    )"""


def _key_cols(conn, table):
    """Primary key, else the first unique constraint, of aa.<table>."""
    rows = conn.execute(sa.text("""
        SELECT c.contype, array_agg(a.attname ORDER BY k.ord) AS cols
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord)
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
        WHERE n.nspname = 'aa' AND t.relname = :t AND c.contype IN ('p', 'u')
        GROUP BY c.oid, c.contype ORDER BY (c.contype = 'p') DESC, c.oid"""), {"t": table}).fetchall()
    if not rows:
        raise SystemExit(f"aa.{table} has no primary key or unique constraint to upsert on")
    return list(rows[0].cols)


def _col_types(conn, table):
    return dict(conn.execute(sa.text(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'aa' AND table_name = :t"), {"t": table}).fetchall())


def _audit(conn, by, table, row_key, new_value, old_value=None):
    conn.execute(sa.text(
        "INSERT INTO aa.entry_audit (entered_by, table_name, row_key, field, old_value, new_value) "
        "VALUES (:by, :t, :k, '(row)', :o, :v)"),
        {"by": by, "t": table, "k": row_key, "o": old_value, "v": new_value})


def _delete_where(conn, name, table, match, types, dry, by):
    """Delete the rows of aa.<table> matching `match` (column -> value, NULLs equal)."""
    unknown = set(match) - set(types)
    if unknown:
        raise SystemExit(f"{name}: aa.{table} has no column(s) {sorted(unknown)}")
    where = " AND ".join(f'"{k}" IS NOT DISTINCT FROM :{k}' for k in match)
    gone = conn.execute(sa.text(f'SELECT * FROM aa."{table}" WHERE {where}'), match).mappings().all()
    if not dry and gone:
        conn.execute(sa.text(f'DELETE FROM aa."{table}" WHERE {where}'), match)
        for g in gone:
            _audit(conn, by, table, "/".join(str(match[k]) for k in match), "deleted",
                   json.dumps(dict(g), default=str)[:4000])
    return len(gone)


def apply_file(conn, name, payload, dry=False):
    by = f"entries:{name}" + (f" ({payload['entered_by']})" if payload.get("entered_by") else "")
    n = 0
    for item in payload["rows"]:
        table, op = item["table"], item.get("op", "upsert")
        types = _col_types(conn, table)
        if op == "delete":
            keys = _key_cols(conn, table)
            key = {k: item["row"].get(k) for k in keys}
            k = _delete_where(conn, name, table, key, types, dry, by)
            print(f"  {'(dry) ' if dry else ''}{table}: {'/'.join(str(v) for v in key.values())}"
                  f"  [delete{'' if k else ', already absent'}]")
            n += 1
            continue
        if op == "replace":
            scope = item.get("scope") or {}
            if not {"country_iso3", "hazard", "version"} <= set(scope):
                raise SystemExit(f"{name}: replace on aa.{table} needs a scope with at least "
                                 "country_iso3, hazard and version")
            for r in item.get("rows") or []:
                off = {c: r.get(c) for c in scope if r.get(c) != scope[c]}
                if off:
                    raise SystemExit(f"{name}: replace on aa.{table}: row {r} is outside the scope {off}")
            k = _delete_where(conn, name, table, scope, types, dry, by)
            print(f"  {'(dry) ' if dry else ''}{table}: {'/'.join(str(v) for v in scope.values())}"
                  f"  [replace: {k} out, {len(item.get('rows') or [])} in]")
            for r in item.get("rows") or []:
                n += apply_file(conn, name, {"entered_by": payload.get("entered_by"),
                                             "rows": [{"table": table, "row": r}]}, dry)
            continue
        if op != "upsert":
            raise SystemExit(f"{name}: unknown op {op!r} (upsert | delete | replace)")
        row = dict(item["row"])
        unknown = set(row) - set(types)
        if unknown:
            raise SystemExit(f"{name}: aa.{table} has no column(s) {sorted(unknown)}")
        keys = _key_cols(conn, table)
        cols = list(row)
        vals = []
        for c in cols:
            if types[c] in ("jsonb", "json") and not isinstance(row[c], str) and row[c] is not None:
                row[c] = json.dumps(row[c])
                vals.append(f"CAST(:{c} AS {types[c]})")
            else:
                vals.append(f":{c}")
        for k in keys:                     # a key column left out means NULL (as an insert would)
            row.setdefault(k, None)
        # an existing row is UPDATEd with just the fields given (an INSERT … ON CONFLICT would
        # trip NOT NULL columns the entry leaves out, e.g. source, before seeing the conflict)
        where = " AND ".join(f"{k} IS NOT DISTINCT FROM :{k}" for k in keys)
        exists = conn.execute(sa.text(f"SELECT 1 FROM aa.{table} WHERE {where}"), row).first()
        upd = [(c, v) for c, v in zip(cols, vals) if c not in keys]
        if exists:
            sets = [f"{c} = {v}" for c, v in upd]
            if "updated_at" in types and "updated_at" not in row:
                sets.append("updated_at = now()")
            sql = f"UPDATE aa.{table} SET {', '.join(sets)} WHERE {where}" if upd else None
        else:
            sql = f"INSERT INTO aa.{table} ({', '.join(cols)}) VALUES ({', '.join(vals)})"
        row_key = "/".join(str(row.get(k)) for k in keys)
        print(f"  {'(dry) ' if dry else ''}{table}: {row_key}"
              f"  [{'update' if exists else 'insert'}{'' if sql else ', unchanged'}]")
        if not dry and sql:
            conn.execute(sa.text(sql), row)
            conn.execute(sa.text(
                "INSERT INTO aa.entry_audit (entered_by, table_name, row_key, field, old_value, new_value) "
                "VALUES (:by, :t, :k, '(row)', NULL, :v)"),
                {"by": by, "t": table, "k": row_key, "v": json.dumps(item["row"], default=str)})
        n += 1
    return n


def _blob_files():
    names = stratus.list_container_blobs(name_starts_with=f"{PREFIX}/", stage="dev",
                                         container_name=CONTAINER)
    for nm in sorted(x for x in names if x.endswith(".json")):
        yield nm.rsplit("/", 1)[-1], stratus.load_blob_data(nm, stage="dev", container_name=CONTAINER)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", help="apply local *.json files from DIR instead of the blob")
    ap.add_argument("--upload", help="upload a local JSON file to the blob entries folder")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.upload:
        p = Path(a.upload)
        json.loads(p.read_text())          # must parse before it goes anywhere
        stratus.upload_blob_data(p.read_bytes(), f"{PREFIX}/{p.name}", stage="dev",
                                 container_name=CONTAINER)
        print(f"uploaded -> {CONTAINER}/{PREFIX}/{p.name}")
        return
    files = ([(p.name, p.read_bytes()) for p in sorted(Path(a.dir).glob("*.json"))]
             if a.dir else list(_blob_files()))
    engine = stratus.get_engine(stage="dev", write=True)
    with engine.begin() as conn:
        conn.execute(sa.text(TRACK_DDL))
        done = dict(conn.execute(sa.text("SELECT name, sha256 FROM aa.applied_entries")).fetchall())
    applied = failed = 0
    for name, raw in files:
        sha = hashlib.sha256(raw).hexdigest()
        if done.get(name) == sha:
            continue
        payload = json.loads(raw)
        print(f"{name}: {len(payload['rows'])} item(s)")
        try:
            with engine.begin() as conn:   # one transaction per file: all or nothing
                n = apply_file(conn, name, payload, dry=a.dry_run)
                conn.execute(sa.text("SET CONSTRAINTS ALL IMMEDIATE"))  # deferred checks now
                if not a.dry_run:
                    conn.execute(sa.text(
                        "INSERT INTO aa.applied_entries (name, sha256, n_rows, entered_by) "
                        "VALUES (:n, :s, :r, :b) ON CONFLICT (name) DO UPDATE SET "
                        "sha256 = EXCLUDED.sha256, n_rows = EXCLUDED.n_rows, "
                        "entered_by = EXCLUDED.entered_by, applied_at = now()"),
                        {"n": name, "s": sha, "r": n, "b": payload.get("entered_by")})
        except (Exception, SystemExit) as ex:   # one bad file never blocks the others
            print(f"!! {name}: not applied — {str(ex).splitlines()[0] if str(ex) else ex!r}")
            failed += 1
            continue
        applied += 1
    print(f"{applied} entries file(s) applied" + (" (dry run)" if a.dry_run else ""))
    if failed:
        sys.exit(f"{failed} entries file(s) failed (they stay pending)")


if __name__ == "__main__":
    main()
