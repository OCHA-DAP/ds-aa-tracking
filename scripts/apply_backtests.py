"""Apply backtest errata and seals (backtests/) to the dev `aa` schema — the nightly job's
step after the entries.

A version's backtest (aa.window + aa.simulated_activation + aa.version_performance_reported)
is edited freely while it is unsealed: entries files (op: replace / delete), the admin page.
Once it has been checked against the endorsed document it is SEALED
(framework_version.backtest_sealed_at), and the database's guard_sealed trigger refuses every
change to it — from any writer — except inside an erratum applied by this script.
See backtests/README.md for when to write which file.

  backtests/errata/<id>.json   a correction, reviewed in a pull request, applied once:
      {"kind": "transcription" | "analysis-note",
       "reason": "…", "evidence": "document + page / table …", "requested_by": "…",
       "versions": ["ISO3/hazard/version", …],     # optional for transcription (derived)
       "changes": [                                 # empty for analysis-note
         {"op": "delete", "table": "simulated_activation", "key": {…}, "why": "…"},
         {"op": "update", "table": "window", "key": {…}, "set": {…}, "why": "…"},
         {"op": "insert", "table": "simulated_activation", "row": {…}, "why": "…"}]}
    transcription = the database did not match the endorsed document; analysis-note = the
    endorsed backtest itself is wrong — recorded (and shown), never edited in place: the
    fix is a new version. An erratum for a version whose document is NOT public goes on the
    private dev blob (projects/ds-aa-tracking/errata/<id>.json), never in this public repo.

  backtests/seals/<name>.json  versions verified against their document:
      {"sealed_by": "…", "note": "…",
       "versions": [{"version": "ISO3/hazard/version", "against": "…"}, …]}
    Sealing an unsealed version needs no erratum; a version already sealed is left alone
    (changing a seal is an erratum), and a file seals a version ONCE: if an erratum has
    unsealed it since, it stays unsealed until a new seals file lists it. The database
    checks every seal: the version is endorsed, has windows, each with a span, and no
    simulated year outside it.

After the files, the backtest foreign keys still marked NOT VALID are validated (a backtest
row belongs to a registered version, a simulated year to a window — schema.BACKTEST_FKS).

Each file is one transaction: all of it or none. An erratum is recorded in
aa.backtest_erratum (id = file stem) with the before-values of every row it changed, and
each change is audited to aa.entry_audit (entered_by 'errata:<id>'). An applied erratum is
immutable: the same id with different content is refused — write a new file. A failing file
is reported and the next one still runs; the script exits non-zero if any failed.

Usage:
    uv run python scripts/apply_backtests.py              # pending files (repo + blob)
    uv run python scripts/apply_backtests.py --dry-run    # apply in a transaction, check
                                                          # every constraint, roll back
    uv run python scripts/apply_backtests.py --dir DIR    # errata/ + seals/ under DIR only
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

from ds_aa_tracking import schema  # noqa: E402

ROOT = Path(__file__).parents[1] / "backtests"
CONTAINER, BLOB_PREFIX = "projects", "ds-aa-tracking/errata"
TABLES = {*schema.BACKTEST_TABLES, "framework_version"}
KINDS = {"transcription", "analysis-note"}
KEY = ("country_iso3", "hazard", "version")


def _vkey(row):
    missing = [k for k in KEY if not row.get(k)]
    if missing:
        raise ValueError(f"row {row} lacks {missing}")
    return "/".join(str(row[k]) for k in KEY)


def _pk(conn, table):
    return [r[0] for r in conn.execute(sa.text("""
        SELECT a.attname FROM pg_constraint c
        CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord)
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
        WHERE c.conrelid = CAST(:t AS regclass) AND c.contype = 'p' ORDER BY k.ord"""),
        {"t": f'aa."{table}"'})]


def _check_cols(conn, table, *objs):
    known = {r[0] for r in conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'aa' AND table_name = :t"), {"t": table})}
    bad = sorted({c for o in objs for c in (o or {})} - known)
    if bad:
        raise ValueError(f"aa.{table} has no column(s) {bad}")


def _where(key, prefix="k_"):
    return " AND ".join(f'"{c}" = :{prefix}{c}' for c in key), {f"{prefix}{c}": v for c, v in key.items()}


def _check_key(conn, table, key):
    pk = _pk(conn, table)
    if set(key) != set(pk):
        raise ValueError(f"aa.{table}: key must be exactly the primary key {pk}, got {sorted(key)}")


def apply_erratum(conn, eid, payload, source, sha, dry):
    kind = payload.get("kind")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {sorted(KINDS)}")
    for f in ("reason", "requested_by"):
        if not str(payload.get(f) or "").strip():
            raise ValueError(f"'{f}' is required")
    changes = payload.get("changes") or []
    if kind == "analysis-note" and changes:
        raise ValueError("an analysis-note changes nothing: the fix for a wrong endorsed "
                         "backtest is a new version")
    if kind == "transcription" and not changes:
        raise ValueError("a transcription erratum needs changes")
    versions = set(payload.get("versions") or [])
    for ch in changes:
        if ch.get("table") not in TABLES:
            raise ValueError(f"table {ch.get('table')!r} is not a backtest table ({sorted(TABLES)})")
        versions.add(_vkey(ch.get("key") or ch.get("row") or {}))
        if ch.get("op") == "update" and any(k in (ch.get("set") or {}) for k in KEY):
            versions.add(_vkey({**ch["key"], **ch["set"]}))
    if not versions:
        raise ValueError("no versions named")
    for v in versions:   # a typo check: a registered version, or a label rows sit under
        c, h, ver = v.split("/", 2)
        known = " UNION ALL ".join(
            f'SELECT 1 FROM aa."{t}" WHERE country_iso3 = :c AND hazard = :h AND version = :v'
            for t in ("framework_version", *schema.BACKTEST_TABLES))
        if not conn.execute(sa.text(f"SELECT 1 FROM ({known}) x LIMIT 1"),
                            {"c": c, "h": h, "v": ver}).first():
            raise ValueError(f"{v}: no such version and no backtest rows under that label")

    # the record goes in first: the guard trigger looks it up while the changes are applied
    conn.execute(sa.text("""
        INSERT INTO aa.backtest_erratum (id, kind, versions, reason, evidence, requested_by,
                                         source, sha256, changes)
        VALUES (:id, :kind, :versions, :reason, :evidence, :by, :source, :sha, '[]'::jsonb)"""),
        {"id": eid, "kind": kind, "versions": sorted(versions), "reason": payload["reason"],
         "evidence": payload.get("evidence"), "by": payload["requested_by"], "source": source,
         "sha": sha})
    conn.execute(sa.text("SELECT set_config('aa.erratum_id', :id, true)"), {"id": eid})

    done = []
    for ch in changes:
        op, table = ch.get("op"), ch["table"]
        _check_cols(conn, table, ch.get("key"), ch.get("set"), ch.get("row"))
        if op in ("delete", "update"):
            key = ch.get("key") or {}
            _check_key(conn, table, key)
            where, params = _where(key)
            before = conn.execute(sa.text(f'SELECT * FROM aa."{table}" WHERE {where}'),
                                  params).mappings().all()
            if len(before) != 1:
                raise ValueError(f"{op} aa.{table} {key}: matched {len(before)} rows, expected 1")
            if op == "delete":
                conn.execute(sa.text(f'DELETE FROM aa."{table}" WHERE {where}'), params)
            else:
                sets = ch.get("set") or {}
                if not sets:
                    raise ValueError(f"update aa.{table} {key}: nothing to set")
                setsql = ", ".join(f'"{c}" = :s_{c}' for c in sets)
                conn.execute(sa.text(f'UPDATE aa."{table}" SET {setsql} WHERE {where}'),
                             {**params, **{f"s_{c}": v for c, v in sets.items()}})
            rec = {**ch, "before": json.loads(json.dumps(dict(before[0]), default=str))}
        elif op == "insert":
            row = ch.get("row") or {}
            cols = ", ".join(f'"{c}"' for c in row)
            vals = ", ".join(f":{c}" for c in row)
            conn.execute(sa.text(f'INSERT INTO aa."{table}" ({cols}) VALUES ({vals})'), row)
            key = {c: row.get(c) for c in _pk(conn, table)}
            rec = {**ch, "before": None}
        else:
            raise ValueError(f"unknown op {op!r} (delete | update | insert)")
        done.append(rec)
        row_key = "/".join(str(v) for v in key.values())
        conn.execute(sa.text(
            "INSERT INTO aa.entry_audit (entered_by, table_name, row_key, field, old_value, new_value) "
            "VALUES (:by, :t, :k, :f, :old, :new)"),
            {"by": f"errata:{eid}", "t": table, "k": row_key, "f": f"({op})",
             "old": json.dumps(rec["before"], default=str) if rec["before"] else None,
             "new": json.dumps(ch.get("set") or ch.get("row"), default=str) if op != "delete" else None})
        print(f"  {'(dry) ' if dry else ''}{op} aa.{table} {row_key}"
              + (f" — {ch['why']}" if ch.get("why") else ""))
    conn.execute(sa.text("UPDATE aa.backtest_erratum SET changes = CAST(:c AS jsonb) WHERE id = :id"),
                 {"c": json.dumps(done, default=str), "id": eid})
    conn.execute(sa.text("SET CONSTRAINTS ALL IMMEDIATE"))   # the span check, now, not at commit
    return len(done)


def apply_seals(conn, name, payload, dry):
    by = str(payload.get("sealed_by") or "").strip()
    if not by:
        raise ValueError("'sealed_by' is required")
    n = 0
    for item in payload.get("versions") or []:
        c, h, v = item["version"].split("/", 2)
        against = str(item.get("against") or "").strip()
        if not against:
            raise ValueError(f"{item['version']}: 'against' (what it was verified against) is required")
        p = {"c": c, "h": h, "v": v}
        cur = conn.execute(sa.text(
            "SELECT backtest_sealed_at, backtest_sealed_by, backtest_sealed_against, kb_status "
            "FROM aa.framework_version WHERE country_iso3 = :c AND hazard = :h AND version = :v"),
            p).first()
        if cur is None:
            raise ValueError(f"{item['version']} is not in aa.framework_version")
        if cur.kb_status != "endorsed":
            raise ValueError(f"{item['version']} is {cur.kb_status}: only an endorsed version's "
                             "backtest is sealed")
        if cur.backtest_sealed_at is not None:
            same = (cur.backtest_sealed_by, cur.backtest_sealed_against) == (by, against)
            print(f"  {item['version']}: already sealed"
                  + ("" if same else f" by {cur.backtest_sealed_by!r} against "
                     f"{cur.backtest_sealed_against!r} — left alone (changing a seal is an erratum)"))
            continue
        if conn.execute(sa.text(
                "SELECT 1 FROM aa.entry_audit WHERE entered_by = :by AND table_name = 'framework_version' "
                "AND row_key = :k AND field = 'backtest_sealed_against' LIMIT 1"),
                {"by": f"seals:{name}", "k": item["version"]}).first():
            print(f"  {item['version']}: this file sealed it before and an erratum has unsealed it "
                  "since — left unsealed (to seal it again, list it in a new seals file)")
            continue
        nwin = conn.execute(sa.text('SELECT count(*) FROM aa."window" WHERE country_iso3 = :c '
                                    "AND hazard = :h AND version = :v"), p).scalar()
        if not nwin:
            raise ValueError(f"{item['version']}: no backtest windows to seal")
        bad = conn.execute(sa.text("""
            SELECT count(*) FROM aa.simulated_activation s JOIN aa."window" w
              USING (country_iso3, hazard, version, window_name)
            WHERE s.country_iso3 = :c AND s.hazard = :h AND s.version = :v
              AND (w.analysis_start IS NULL OR w.analysis_end IS NULL
                   OR s.event_year NOT BETWEEN w.analysis_start AND w.analysis_end)"""), p).scalar()
        if bad:
            raise ValueError(f"{item['version']}: {bad} simulated year(s) outside or without an "
                             "analysis span — fix before sealing")
        conn.execute(sa.text(
            "UPDATE aa.framework_version SET backtest_sealed_at = now(), backtest_sealed_by = :by, "
            "backtest_sealed_against = :a WHERE country_iso3 = :c AND hazard = :h AND version = :v"),
            {**p, "by": by, "a": against})
        conn.execute(sa.text(
            "INSERT INTO aa.entry_audit (entered_by, table_name, row_key, field, old_value, new_value) "
            "VALUES (:by, 'framework_version', :k, 'backtest_sealed_against', NULL, :a)"),
            {"by": f"seals:{name}", "k": item["version"], "a": against})
        print(f"  {'(dry) ' if dry else ''}sealed {item['version']} — against {against}")
        n += 1
    return n


def _files(root, use_blob):
    out = []
    for p in sorted((root / "errata").glob("*.json")):
        out.append(("erratum", p.stem, p.read_bytes(), f"backtests/errata/{p.name}"))
    if use_blob:
        names = stratus.list_container_blobs(name_starts_with=f"{BLOB_PREFIX}/", stage="dev",
                                             container_name=CONTAINER)
        for nm in sorted(x for x in names if x.endswith(".json")):
            raw = stratus.load_blob_data(nm, stage="dev", container_name=CONTAINER)
            out.append(("erratum", Path(nm).stem, raw if isinstance(raw, bytes) else raw.encode(),
                        f"blob:{CONTAINER}/{nm}"))
    for p in sorted((root / "seals").glob("*.json")):
        out.append(("seal", p.stem, p.read_bytes(), f"backtests/seals/{p.name}"))
    return out


def validate_fks(engine, dry):
    """Validate the backtest foreign keys that are still NOT VALID (schema.BACKTEST_FKS are
    added that way because rows from before the guards may break them): once the errata have
    cleaned those rows, this makes the rule hold for every row. Idempotent; returns failures."""
    with engine.connect() as conn:
        pending = conn.execute(sa.text(
            "SELECT conrelid::regclass::text AS tbl, conname FROM pg_constraint "
            "WHERE connamespace = 'aa'::regnamespace AND contype = 'f' AND NOT convalidated "
            "AND conname = ANY(:names) ORDER BY conname"),
            {"names": [name for _, name, _ in schema.BACKTEST_FKS]}).fetchall()
    failed = 0
    for tbl, name in pending:
        if dry:
            print(f"{name}: not validated yet (the real run tries)")
            continue
        try:
            with engine.begin() as conn:
                conn.execute(sa.text(f"ALTER TABLE {tbl} VALIDATE CONSTRAINT {name}"))
            print(f"{name}: validated — every row satisfies it now")
        except Exception as ex:  # rows from before still break it: report, try again next run
            print(f"!! {name}: {str(ex).splitlines()[0]} — see the error rows of "
                  "aa.v_trk_backtest_check")
            failed += 1
    return failed


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dir", help="read errata/ and seals/ under DIR (no blob)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    files = _files(Path(a.dir) if a.dir else ROOT, use_blob=not a.dir)
    engine = stratus.get_engine(stage="dev", write=True)
    with engine.connect() as conn:
        if conn.execute(sa.text("SELECT to_regclass('aa.backtest_erratum') IS NULL")).scalar():
            print("the backtest tables and guards are not installed in this database yet "
                  "(scripts/ensure_schema.py — the nightly job's one-off --ensure-schema run): "
                  f"{len(files)} backtest file(s) left pending, nothing applied")
            return
        applied = dict(conn.execute(sa.text("SELECT id, sha256 FROM aa.backtest_erratum")).fetchall())
    failed = 0
    for kind, name, raw, source in files:
        sha = hashlib.sha256(raw).hexdigest()
        if kind == "erratum" and name in applied:
            if applied[name] != sha:
                print(f"!! {source}: erratum {name} was applied with different content — errata "
                      "are immutable; write a new file")
                failed += 1
            continue
        try:
            payload = json.loads(raw)
            print(f"{source}:")
            conn = engine.connect()
            tx = conn.begin()
            try:
                n = (apply_erratum(conn, name, payload, source, sha, a.dry_run) if kind == "erratum"
                     else apply_seals(conn, name, payload, a.dry_run))
                if a.dry_run:
                    tx.rollback()
                    print(f"  {n} change(s) checked, rolled back (dry run)")
                else:
                    tx.commit()
                    print(f"  {n} change(s) applied")
            except Exception:
                tx.rollback()
                raise
            finally:
                conn.close()
        except Exception as ex:  # report, carry on with the next file
            print(f"!! {source}: {str(ex).splitlines()[0]}")
            failed += 1
    failed += validate_fks(engine, a.dry_run)
    if failed:
        sys.exit(f"{failed} backtest step(s) failed")


if __name__ == "__main__":
    main()
