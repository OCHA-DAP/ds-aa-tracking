"""One-off (D252): fill aa.window_event from the two backtest tables it replaces, and give each
window the unit of its chance to activate (D253).

Per window with a code and no event yet:
- a window whose backtest tested its events one by one (aa.backtest_event, 14 storm windows on
  2026-11-19): those events, met, not met or not assessed, with their values. A simulated year
  none of its met events falls in (none on 2026-11-19) comes in as a met event under the
  simulated row's label. Where a simulated year has exactly one met event, that event takes the
  simulated row's date and its precision;
- otherwise its simulated years (aa.simulated_activation), each a met event with the label,
  date and note its row carries. A label that names several storms ("Dennis, Wilma") stays one
  event: the record does not split what the document lists together.
Runs once: after it has committed, a second run does nothing. It refuses to start while
aa.window_event has rows it did not write (entered before it ran): their windows would not
match the two tables, so delete them first and enter them again afterwards.
chance_unit (where not set): 'event' for storm windows (one chance per storm), 'year' for the
others (a year or season), for a person to correct where a framework counts otherwise.

Every row written is audited to aa.entry_audit (entered_by 'backfill_window_events'). Then it
checks, in the same transaction, the two things the backfill must not change:
- regenerating the backtest tables from the record (scripts/mirror_backtest.py) changes
  nothing: the round trip;
- the return periods from the record equal the ones the pages show (aa.v_trk_event_check has
  no row about them).
Either failing rolls everything back.

Usage: uv run python scripts/backfill_window_events.py [--write]   (default: dry run, rolled back)
"""

import argparse
import json
import os
import sys
from pathlib import Path

import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("PGSSLMODE", "require")

import ocha_stratus as stratus  # noqa: E402
from mirror_backtest import BACKFILL_BY, mirror, record_live  # noqa: E402

BY = BACKFILL_BY      # its audit rows are the sign, for the nightly step and the entries, that it ran
COLS = ("country_iso3", "hazard", "version", "window_code", "event_year", "event_label", "event_date",
        "event_time", "time_precision", "met", "value", "unit", "source_note")

# the windows to fill: coded, no event yet
TODO = """
    SELECT w.country_iso3, w.hazard, w.version, w.window_code, w.window_name
    FROM aa.window w
    WHERE w.window_code IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM aa.window_event e
                      WHERE (e.country_iso3, e.hazard, e.version, e.window_code)
                          = (w.country_iso3, w.hazard, w.version, w.window_code))"""


def _rows(conn, sql, **p):
    return [dict(r) for r in conn.execute(sa.text(sql), p).mappings()]


def events_for(conn, w):
    """The window's events from the two tables, as aa.window_event rows."""
    k = {c: w[c] for c in ("country_iso3", "hazard", "version")} | {"window_name": w["window_name"]}
    where = "country_iso3 = :country_iso3 AND hazard = :hazard AND version = :version AND window_name = :window_name"
    sims = _rows(conn, f"SELECT * FROM aa.simulated_activation WHERE {where} ORDER BY event_year", **k)
    bts = _rows(conn, f"SELECT * FROM aa.backtest_event WHERE {where} ORDER BY event_year, event_label", **k)
    base = {c: w[c] for c in ("country_iso3", "hazard", "version", "window_code")}
    out = []
    if bts:
        for b in bts:
            out.append({**base, "event_year": b["event_year"], "event_label": b["event_label"],
                        "event_date": None, "event_time": None, "time_precision": None,
                        "met": b["met"], "value": b["value"], "unit": b["unit"], "source_note": b["source_note"]})
        for s in sims:
            met = [e for e in out if e["event_year"] == s["event_year"] and e["met"]]
            if not met:
                out.append({**base, "event_year": s["event_year"], "event_label": s["event_label"] or "",
                            "event_date": s["event_date"], "event_time": s["event_time"],
                            "time_precision": s["time_precision"], "met": True, "value": None, "unit": None,
                            "source_note": s["source_note"]})
            elif len(met) == 1:
                for c in ("event_date", "event_time", "time_precision"):
                    met[0][c] = s[c]
    else:
        for s in sims:
            out.append({**base, "event_year": s["event_year"], "event_label": s["event_label"] or "",
                        "event_date": s["event_date"], "event_time": s["event_time"],
                        "time_precision": s["time_precision"], "met": True, "value": None, "unit": None,
                        "source_note": s["source_note"]})
    return out


def backfill(conn, verbose=True):
    say = print if verbose else (lambda *a, **k: None)
    if record_live(conn):
        say("window events: backfilled already; nothing to do")
        return 0
    early = conn.execute(sa.text("SELECT count(*) FROM aa.window_event")).scalar()
    if early:
        raise SystemExit(f"::error::aa.window_event has {early} row(s) entered before the backfill: delete "
                         "them, run the backfill, then enter them again (the record of their windows would "
                         "not match the backtest tables)")
    n_win = n_ev = 0
    for w in _rows(conn, TODO):
        evs = events_for(conn, w)
        if not evs:
            continue
        for e in evs:
            conn.execute(sa.text(f"INSERT INTO aa.window_event ({', '.join(COLS)}) VALUES "
                                 f"({', '.join(':' + c for c in COLS)})"), e)
            conn.execute(sa.text(
                "INSERT INTO aa.entry_audit (entered_by, table_name, row_key, field, old_value, new_value) "
                "VALUES (:by, 'window_event', :k, '(row)', NULL, :v)"),
                {"by": BY, "k": "/".join(str(e[c]) for c in COLS[:6]), "v": json.dumps(e, default=str)})
        n_win += 1
        n_ev += len(evs)
    say(f"window events: {n_ev} event(s) in {n_win} window(s)")
    units = conn.execute(sa.text(
        "UPDATE aa.window SET chance_unit = CASE WHEN hazard = 'storm' THEN 'event' ELSE 'year' END "
        "WHERE chance_unit IS NULL RETURNING country_iso3, hazard, version, window_name, chance_unit")).fetchall()
    for u in units:
        conn.execute(sa.text(
            "INSERT INTO aa.entry_audit (entered_by, table_name, row_key, field, old_value, new_value) "
            "VALUES (:by, 'window', :k, 'chance_unit', NULL, :v)"),
            {"by": BY, "k": "/".join(str(x) for x in u[:4]), "v": json.dumps(u[4])})
    say(f"chance_unit: set on {len(units)} window(s)")
    return n_ev


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true", help="commit (default: dry run, rolled back)")
    a = ap.parse_args()
    eng = stratus.get_engine(stage="dev", write=True)
    with eng.connect() as conn:
        tx = conn.begin()
        try:
            if record_live(conn):
                tx.rollback()
                print("window events: backfilled already; nothing to do")
                return
            backfill(conn)
            conn.execute(sa.text("SET CONSTRAINTS ALL IMMEDIATE"))     # the window key, now
            # before the round trip, which would make the backtest tables agree by construction:
            # a return period that moves, or a counted year the CERF app's view does not show
            bad = conn.execute(sa.text(
                "SELECT count(*) FROM aa.v_trk_event_check WHERE position('activation year' in problem) > 0 "
                "OR position('v_trigger_event' in problem) > 0")).scalar()
            n = mirror(conn, verbose=True)
            if n or bad:
                tx.rollback()
                sys.exit(f"::error::backfill rolled back: regenerating the backtest tables would change {n} "
                         f"thing(s); {bad} problem(s) in aa.v_trk_event_check (a return period that moves, "
                         "or a year the CERF app's view would show differently)")
            if a.write:
                tx.commit()
                print("window events: committed; the round trip changes nothing and the return periods agree")
            else:
                tx.rollback()
                print("window events: dry run, rolled back; the round trip changes nothing and the return "
                      "periods agree")
        except BaseException:
            if tx.is_active:
                tx.rollback()
            raise


if __name__ == "__main__":
    main()
