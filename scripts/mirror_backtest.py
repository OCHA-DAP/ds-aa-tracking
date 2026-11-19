"""Regenerate aa.simulated_activation and aa.backtest_event from aa.window_event (D252).

Since D252 the window's event record (aa.window_event) is what is entered and edited. The two
tables it replaces stay while code on the open site, or the pages, still read them (D203): every
night this step makes them say what the record says, so the open site keeps showing current
backtests. They go once the pages read the record and that code has been promoted.

Changes only what differs, so an unchanged record changes nothing:
- simulated_activation: one row per window and year with a met event the return periods count
  (inside the window's analysis span and not a gap year; any year when the span is not
  recorded). A year that is no longer met goes; a new one comes in, labelled with its events'
  names ("Dennis, Wilma"). An existing row keeps its label while it names the same events (in any
  order). A year with one event takes that event's date, time and precision (a cleared date is
  cleared), and, for a window whose record is not per tested event, its note.
- backtest_event: for the windows whose record lists tested events one by one, every named
  event of the record with whether it was met and its value. A window counts as one only when
  every met event in its record is named (a storm), and it is already in the table or its
  record has an event that was not met or not assessed: a year-only record with one named storm
  added stays out, so aa.v_trigger_event (the CERF app's view) keeps reading its simulated years.
Only windows with a code are touched, and never a window whose record has no event at all
(its rows stay, with a warning: emptying a window's record does not empty them). Nothing
happens before the one-off backfill (scripts/backfill_window_events.py) has committed: the
sign is its rows in aa.entry_audit, not rows in aa.window_event, which an editor could have
entered first.

Every change is audited to aa.entry_audit (entered_by 'nightly mirror_backtest').

Usage: uv run python scripts/mirror_backtest.py [--dry-run]
    --dry-run makes the changes in one transaction, runs a second pass (which must find
    nothing), and rolls back.
"""

import argparse
import json
import os
import sys

import sqlalchemy as sa

os.environ.setdefault("PGSSLMODE", "require")

import ocha_stratus as stratus

BY = "nightly mirror_backtest"
BACKFILL_BY = "backfill_window_events"     # entry_audit.entered_by of the one-off backfill
WKEY = ("country_iso3", "hazard", "version", "window_code")


def _audit(conn, table, row_key, field, old, new):
    conn.execute(sa.text(
        "INSERT INTO aa.entry_audit (entered_by, table_name, row_key, field, old_value, new_value) "
        "VALUES (:by, :t, :k, :f, :o, :v)"),
        {"by": BY, "t": table, "k": row_key, "f": field,
         "o": None if old is None else json.dumps(old, default=str),
         "v": None if new is None else json.dumps(new, default=str)})


def _names(label):
    """The event names a label carries, in any order: 'Dennis, Wilma' -> {'Dennis', 'Wilma'}."""
    return frozenset(x.strip() for x in (label or "").split(",") if x.strip())


def _rows(conn, sql):
    return [dict(r) for r in conn.execute(sa.text(sql)).mappings()]


def record_live(conn):
    """True once the one-off backfill has committed (its audit rows exist), so aa.window_event
    holds every window's record. Rows in aa.window_event alone prove nothing: an editor or an
    entries file could have entered one before the backfill."""
    if conn.execute(sa.text("SELECT to_regclass('aa.window_event')")).scalar() is None:
        return False
    return bool(conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM aa.entry_audit WHERE entered_by = :by AND table_name = 'window_event')"),
        {"by": BACKFILL_BY}).scalar())


def _same(a, b):
    """Equal, with NaN equal to NaN (numeric NaN would otherwise rewrite a row every night)."""
    nan = lambda x: x is not None and x != x  # noqa: E731  (float and Decimal NaN)
    return a == b or (nan(a) and nan(b))


def _counted(w, year):
    """A met event of this year counts toward the return period (as aa.v_window_event.counted):
    inside the window's analysis years and not a gap year, or any year when the window's
    analysis years are not recorded."""
    a, b = w["analysis_start"], w["analysis_end"]
    if a is None or b is None:
        return True
    return a <= year <= b and year not in (w["analysis_gap_years"] or [])


def _order(e):
    return (e["event_date"] is None, e["event_date"] or 0, e["event_label"])


def mirror(conn, verbose=True):
    """One pass. Returns the number of changes (rows inserted or deleted, fields updated)."""
    say = print if verbose else (lambda *a, **k: None)
    if not record_live(conn):
        say("window events: the one-off backfill has not run yet; nothing mirrored")
        return 0
    wins = {tuple(w[k] for k in WKEY): w for w in _rows(conn, """
        SELECT country_iso3, hazard, version, window_code, window_name, kb_framework,
               analysis_start, analysis_end, analysis_gap_years
        FROM aa.window WHERE window_code IS NOT NULL""")}
    events = {}
    for e in _rows(conn, "SELECT * FROM aa.window_event"):
        events.setdefault(tuple(e[k] for k in WKEY), []).append(e)
    changed = 0
    bt = {}
    for b in _rows(conn, "SELECT * FROM aa.backtest_event WHERE window_code IS NOT NULL"):
        bt[(tuple(b[k] for k in WKEY), b["event_year"], b["event_label"])] = b
    # windows whose record lists tested events one by one (see the docstring)
    in_bt = {k[0] for k in bt}
    tested = {wk for wk, evs in events.items()
              if all(e["event_label"] for e in evs if e["met"])
              and (wk in in_bt or any(e["met"] is not True for e in evs))}
    empty_warned = set()

    def empty(wk, table):
        """A coded window with rows here and no event in its record: left as it is, warned once."""
        if wk in events:
            return False
        if (wk, table) not in empty_warned:
            empty_warned.add((wk, table))
            say(f"::warning::{'/'.join(map(str, wk))}: no event in aa.window_event but rows in aa.{table}; "
                "left as they are (delete them by hand if the record was emptied on purpose)")
        return True

    # ---- simulated_activation: the met years of the reference span
    sim = {}
    for s in _rows(conn, "SELECT * FROM aa.simulated_activation WHERE window_code IS NOT NULL"):
        sim[(tuple(s[k] for k in WKEY), s["event_year"])] = s
    want = {}
    for wk, evs in events.items():
        w = wins.get(wk)
        if w is None:
            continue
        for e in evs:
            if e["met"] and _counted(w, e["event_year"]):
                want.setdefault((wk, e["event_year"]), []).append(e)
    for (wk, y), s in sorted(sim.items(), key=lambda x: (x[0][0], x[0][1])):
        if wk in wins and (wk, y) not in want and not empty(wk, "simulated_activation"):
            lab = "/".join(str(v) for v in (*wk, y))
            conn.execute(sa.text(
                "DELETE FROM aa.simulated_activation WHERE country_iso3 = :country_iso3 AND hazard = :hazard "
                "AND version = :version AND window_name = :window_name AND event_year = :event_year"), s)
            _audit(conn, "simulated_activation", lab, "(delete)", s, None)
            say(f"  simulated_activation {lab}: gone (no met event in the record)")
            changed += 1
    for (wk, y), evs in sorted(want.items(), key=lambda x: (x[0][0], x[0][1])):
        w, evs = wins[wk], sorted(evs, key=_order)
        names = frozenset().union(*(_names(e["event_label"]) for e in evs))
        one = evs[0] if len(evs) == 1 else None
        lab = "/".join(str(v) for v in (*wk, y))
        s = sim.get((wk, y))
        if s is None:
            row = {"country_iso3": wk[0], "hazard": wk[1], "version": wk[2], "window_name": w["window_name"],
                   "window_code": wk[3], "event_year": y, "kb_framework": w["kb_framework"],
                   "event_label": ", ".join(e["event_label"] for e in evs if e["event_label"]) or None,
                   "event_date": one["event_date"] if one else None,
                   "event_time": one["event_time"] if one else None,
                   "time_precision": one["time_precision"] if one else "year",
                   "source_note": "; ".join(dict.fromkeys(e["source_note"] for e in evs if e["source_note"])) or None}
            conn.execute(sa.text(
                "INSERT INTO aa.simulated_activation (" + ", ".join(row) + ") VALUES ("
                + ", ".join(f":{k}" for k in row) + ")"), row)
            _audit(conn, "simulated_activation", lab, "(row)", None, row)
            say(f"  simulated_activation {lab}: new ({row['event_label'] or 'the year'})")
            changed += 1
            continue
        sets = {}
        if _names(s["event_label"]) != names:
            sets["event_label"] = ", ".join(e["event_label"] for e in evs if e["event_label"]) or None
        if one is not None:
            for c in ("event_date", "event_time", "time_precision") + (() if wk in tested else ("source_note",)):
                if not _same(one[c], s[c]):
                    sets[c] = one[c]
        if sets:
            conn.execute(sa.text(
                "UPDATE aa.simulated_activation SET " + ", ".join(f"{c} = :s_{c}" for c in sets)
                + " WHERE country_iso3 = :country_iso3 AND hazard = :hazard AND version = :version "
                "AND window_name = :window_name AND event_year = :event_year"),
                {**{f"s_{c}": v for c, v in sets.items()}, **s})
            for c, v in sets.items():
                _audit(conn, "simulated_activation", lab, c, s[c], v)
            say(f"  simulated_activation {lab}: " + "; ".join(f"{c} {s[c]!r} -> {v!r}" for c, v in sets.items()))
            changed += len(sets)

    # ---- backtest_event: the named events of the windows that list tested events one by one
    want_bt = {(wk, e["event_year"], e["event_label"]): e
               for wk, evs in events.items() if wk in tested and wk in wins
               for e in evs if e["event_label"]}
    for k, b in sorted(bt.items(), key=lambda x: x[0]):
        if k[0] in wins and k not in want_bt and not empty(k[0], "backtest_event"):
            lab = "/".join(str(v) for v in (*k[0], k[1], k[2]))
            conn.execute(sa.text(
                "DELETE FROM aa.backtest_event WHERE country_iso3 = :country_iso3 AND hazard = :hazard "
                "AND version = :version AND window_name = :window_name AND event_year = :event_year "
                "AND event_label = :event_label"), b)
            _audit(conn, "backtest_event", lab, "(delete)", b, None)
            say(f"  backtest_event {lab}: gone (not in the record)")
            changed += 1
    for k, e in sorted(want_bt.items(), key=lambda x: x[0]):
        wk, y, label = k
        w, b = wins[wk], bt.get(k)
        lab = "/".join(str(v) for v in (*wk, y, label))
        if b is None:
            row = {"country_iso3": wk[0], "hazard": wk[1], "version": wk[2], "window_name": w["window_name"],
                   "window_code": wk[3], "event_year": y, "event_label": label, "kb_framework": w["kb_framework"],
                   "met": e["met"], "value": e["value"], "unit": e["unit"], "source_note": e["source_note"]}
            conn.execute(sa.text(
                "INSERT INTO aa.backtest_event (" + ", ".join(row) + ") VALUES ("
                + ", ".join(f":{c}" for c in row) + ")"), row)
            _audit(conn, "backtest_event", lab, "(row)", None, row)
            say(f"  backtest_event {lab}: new")
            changed += 1
            continue
        sets = {c: e[c] for c in ("met", "value", "unit", "source_note") if not _same(e[c], b[c])}
        if sets:
            conn.execute(sa.text(
                "UPDATE aa.backtest_event SET " + ", ".join(f"{c} = :s_{c}" for c in sets)
                + " WHERE country_iso3 = :country_iso3 AND hazard = :hazard AND version = :version "
                "AND window_name = :window_name AND event_year = :event_year AND event_label = :event_label"),
                {**{f"s_{c}": v for c, v in sets.items()}, **b})
            for c, v in sets.items():
                _audit(conn, "backtest_event", lab, c, b[c], v)
            say(f"  backtest_event {lab}: " + "; ".join(f"{c} {b[c]!r} -> {v!r}" for c, v in sets.items()))
            changed += len(sets)
    return changed


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    eng = stratus.get_engine(stage="dev", write=True)
    with eng.connect() as conn:
        tx = conn.begin()
        try:
            n = mirror(conn)
            if a.dry_run:
                again = mirror(conn, verbose=False)
                tx.rollback()
                print(f"backtest tables: {n} change(s) would be made (dry run, rolled back); "
                      f"a second pass found {again}")
                if again:
                    sys.exit("::error::mirror_backtest is not idempotent: the second pass changed something")
            else:
                tx.commit()
                print(f"backtest tables: {n} change(s) from the event record")
        except BaseException:
            if tx.is_active:
                tx.rollback()
            raise


if __name__ == "__main__":
    main()
