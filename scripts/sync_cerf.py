"""Keep the tracker's CERF figures equal to OneGMS's: amounts and people targeted (D232).

Why: the tracker was seeded in September 2026 from the AA activations workbook, whose amounts
and people were typed in by hand ("$5.2M"): the seed matched each activation to its CERF
allocation but kept the workbook's figures, and a hand entry since (admin page, entries file)
does the same. Only a provisional amount was ever replaced by OneGMS's (resolve_provisional.py).
On 2026-11-16, 27 of the 46 CERF funding rows with an allocation code differed from OneGMS's
amount (up to $13,802 on one allocation, Niger drought 2022). Owner, the same day: "let's
replace the manually entered numbers with what's in the CERF mirror automatically. this should
apply to people reached too".

The nightly job runs this after the entries files and resolve_provisional. Where OneGMS (the
mirror, aa.cerf_allocation) gives a figure above zero:

1. A CERF funding row (aa.activation_funding) whose allocation is on no other funding row takes
   the allocation's approved amount (amount_usd) and the people it plans to reach
   (people_targeted <- individuals_planned). OneGMS's approved amount is the sum of the
   allocation's projects funded so far: while a project is still under review it can rise
   (Ethiopia 2020: $13.2M from December, $20.0M from April 2021), and the tracker follows it. It
   stays the gross amount after a refund (Mozambique 2026, Nepal 2021): refunds are their own
   rows.
2. An activation's own people figure (aa.window_activation / aa.adhoc_activation,
   people_targeted) takes the planned people of the CERF allocation that pays for it, whatever
   else pays for it too (owner, 2026-11-16: "if it's the activation, use the CERF number").
3. An allocation on more than one funding row (one allocation over two activations or two
   windows: Ethiopia 2020-12 and 2021-02, Chad 2026 windows 1 and 2): the amounts stay as
   entered (how it splits is a person's call); its planned people go to the first row by date,
   then window, and that row's activation, as the pages give the allocation's reach to that row.
   Warned when the rows' amounts do not add up to the approved amount, or their people to the
   planned people.
4. Left as entered, with a warning in the log:
   - a CERF funding row whose allocation is of another country than the row (a wrong code);
   - a coded CERF row while another CERF row of the same country, hazard and year has no code
     yet (the allocation may be split over both, e.g. two windows), until it is coded;
   - the people figure of an activation with more than one CERF funding row.

People reached is not stored in the tracker: the pages read it from the mirror at every build
(landing._cerf_reached), so it follows OneGMS already.

Every change is audited to aa.entry_audit (entered_by 'nightly sync_cerf'); the row key writes
'' for a NULL, as the admin page's History panel looks it up.

Usage: uv run python scripts/sync_cerf.py [--dry-run]
    --dry-run makes every change in one transaction, runs the pass a second time (which must
    find nothing to change), and rolls back.
"""

import argparse
import json
import os
import sys

import sqlalchemy as sa

os.environ.setdefault("PGSSLMODE", "require")

import ocha_stratus as stratus

BY = "nightly sync_cerf"
# aa.activation_funding's unique key (NULLs equal)
FKEY = ("country_iso3", "hazard", "event_date", "window_name", "event_label", "event_type",
        "fund_code", "allocation_code")
# the activation's key as aa.activation_funding carries it
AKEY = ("country_iso3", "hazard", "event_date", "window_name", "event_label", "event_type")
# the primary keys of the two tables behind the aa.activation view
TKEY = {"window_activation": ("country_iso3", "hazard", "version", "window_name", "event_date", "event_label"),
        "adhoc_activation": ("country_iso3", "hazard", "event_type", "event_date", "event_label")}

FUNDING = """
    SELECT f.*, c.amount_approved, c.individuals_planned, c.country_iso3 AS alloc_country,
           (SELECT count(*) FROM aa.activation_funding g
             WHERE g.allocation_code = f.allocation_code) AS n_alloc_rows,
           (SELECT count(*) FROM aa.activation_funding g
             WHERE g.fund_code = 'cerf'
               AND g.country_iso3 = f.country_iso3 AND g.hazard = f.hazard
               AND g.event_date = f.event_date AND g.window_name IS NOT DISTINCT FROM f.window_name
               AND g.event_label = f.event_label AND g.event_type = f.event_type) AS n_cerf_act_rows,
           (SELECT string_agg(g.event_date || coalesce(' ' || g.window_name, ''), '; ')
              FROM aa.activation_funding g
             WHERE g.fund_code = 'cerf' AND g.allocation_code IS NULL
               AND g.country_iso3 = f.country_iso3 AND g.hazard = f.hazard
               AND left(g.event_date, 4) = left(f.event_date, 4)) AS uncoded_siblings
    FROM aa.activation_funding f
    JOIN aa.cerf_allocation c ON c.application_code = f.allocation_code
    WHERE f.fund_code = 'cerf'
    ORDER BY f.country_iso3, f.hazard, f.event_date, f.window_name, f.event_label"""


def _num(v):
    return None if v is None else float(v)


def _fmt(v):
    return "—" if v is None else f"{float(v):,.0f}"


def _lab(r, keys):
    return "/".join("" if r[k] is None else str(r[k]) for k in keys)


def _audit(conn, table, row_key, field, old, new):
    conn.execute(sa.text(
        "INSERT INTO aa.entry_audit (entered_by, table_name, row_key, field, old_value, new_value) "
        "VALUES (:by, :t, :k, :f, :o, :v)"),
        {"by": BY, "t": table, "k": row_key, "f": field,
         "o": json.dumps(old, default=str), "v": json.dumps(new, default=str)})


def _update(conn, table, keys, row, sets):
    where = " AND ".join(f"{k} IS NOT DISTINCT FROM :k_{k}" for k in keys)
    n = conn.execute(sa.text(
        f"UPDATE aa.{table} SET " + ", ".join(f"{c} = :s_{c}" for c in sets)
        + f", updated_at = now() WHERE {where}"),
        {**{f"s_{c}": v for c, v in sets.items()}, **{f"k_{k}": row[k] for k in keys}}).rowcount
    if n != 1:
        raise SystemExit(f"aa.{table} {_lab(row, keys)}: {n} rows matched its key, expected 1")
    for c, v in sets.items():
        _audit(conn, table, _lab(row, keys), c, row[c], v)


def _activation(conn, r):
    """The one activation row (table, row) a funding row belongs to, or (table, None). The
    funding row names it by AKEY; a window activation's table key adds the version (not on the
    funding row) and has no event type, an ad hoc one has no window."""
    if r["event_type"] == "framework_aa":
        table, cols = "window_activation", ("country_iso3", "hazard", "event_date", "window_name", "event_label")
    else:
        table, cols = "adhoc_activation", ("country_iso3", "hazard", "event_type", "event_date", "event_label")
    where = " AND ".join(f"{k} IS NOT DISTINCT FROM :{k}" for k in cols)
    acts = conn.execute(sa.text(f"SELECT * FROM aa.{table} WHERE {where}"),
                        {k: r[k] for k in cols}).mappings().fetchall()
    return table, (acts[0] if len(acts) == 1 else None), len(acts)


def sync(conn, verbose=True):
    """One pass. Returns the number of fields changed."""
    say = print if verbose else (lambda *a, **k: None)
    rows = conn.execute(sa.text(FUNDING)).mappings().fetchall()
    changed = 0
    shared, synced = {}, []
    for r in rows:
        lab = _lab(r, FKEY)
        if r["alloc_country"] != r["country_iso3"]:
            say(f"::warning::{lab}: allocation {r['allocation_code']} is of {r['alloc_country']}, not "
                f"{r['country_iso3']}: a wrong allocation code? Left as entered")
            continue
        if r["uncoded_siblings"]:
            say(f"::warning::{lab}: another CERF amount of {r['country_iso3']} {r['hazard']} that year has no "
                f"allocation code yet ({r['uncoded_siblings']}); if it draws on {r['allocation_code']} too, "
                "enter the code there. Left as entered until then")
            continue
        if r["n_alloc_rows"] > 1:
            shared.setdefault(r["allocation_code"], []).append(r)
            continue
        synced.append(r)
        sets = {}
        appr, amt = _num(r["amount_approved"]), _num(r["amount_usd"])
        if appr and appr > 0 and (amt is None or round(amt, 2) != round(appr, 2)):
            sets["amount_usd"] = r["amount_approved"]
        planned = r["individuals_planned"]
        if planned and planned > 0 and r["people_targeted"] != int(planned):
            sets["people_targeted"] = int(planned)
        if sets:
            say(f"  {lab}: " + "; ".join(f"{c} {_fmt(r[c])} -> {_fmt(v)}" for c, v in sets.items()))
            _update(conn, "activation_funding", FKEY, r, sets)
            changed += len(sets)
    firsts = []
    for code, rs in shared.items():
        # the split amounts stay as entered; the allocation's people go to its first row (by date,
        # then window: the row the pages give the allocation's reach to, landing's reach_row)
        rs = sorted(rs, key=lambda x: (x["event_date"], x["window_name"] or ""))
        first, planned = rs[0], rs[0]["individuals_planned"] or 0
        firsts.append(first)
        if planned > 0 and first["people_targeted"] != int(planned):
            say(f"  {_lab(first, FKEY)}: people_targeted {_fmt(first['people_targeted'])} -> {_fmt(planned)} "
                f"(first of {len(rs)} rows of {code})")
            _update(conn, "activation_funding", FKEY, first, {"people_targeted": int(planned)})
            changed += 1
        where = "; ".join(_lab(x, AKEY) for x in rs)
        total = sum(_num(x["amount_usd"]) or 0 for x in rs)
        appr = _num(first["amount_approved"]) or 0
        ppl = sum(x["people_targeted"] or 0 for x in rs[1:]) + (int(planned) if planned > 0 else 0)
        off = []
        if appr > 0 and abs(total - appr) > 1:
            off.append(f"amounts add up to ${total:,.0f}, OneGMS approved ${appr:,.0f}")
        if planned > 0 and ppl != planned:
            off.append(f"people add up to {ppl:,}, OneGMS plans {planned:,}")
        if off:
            say(f"::warning::{code} is on {len(rs)} funding rows ({where}): {'; '.join(off)}; "
                "split it by hand")
        else:
            say(f"  {code}: on {len(rs)} funding rows ({where}); they add up to OneGMS's")
    # the activation's own people figure: its CERF allocation's planned people, whatever else pays
    # for it too (owner, 2026-11-16: "if it's the activation, use the CERF number")
    for r in synced + firsts:
        planned = r["individuals_planned"]
        if not planned or planned <= 0:
            continue
        if r["n_cerf_act_rows"] != 1:
            say(f"::warning::{_lab(r, AKEY)}: {r['n_cerf_act_rows']} CERF funding rows; the activation's "
                "people figure is left as entered")
            continue
        table, a, n = _activation(conn, r)
        if a is None:
            say(f"::warning::{_lab(r, AKEY)}: {n} activations in aa.{table} for this funding row; "
                "people figure left as entered")
            continue
        if a["people_targeted"] != int(planned):
            say(f"  {table} {_lab(a, TKEY[table])}: people_targeted {_fmt(a['people_targeted'])} -> {_fmt(planned)}")
            _update(conn, table, TKEY[table], a, {"people_targeted": int(planned)})
            changed += 1
    return changed


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="make the changes, check that a second pass finds none, roll back")
    dry = ap.parse_args().dry_run
    engine = stratus.get_engine(stage="dev", write=True)
    with engine.connect() as conn:
        tx = conn.begin()
        n = sync(conn)
        if dry:
            again = sync(conn, verbose=False)
            tx.rollback()
            print(f"CERF figures: {n} field(s) would change (dry run, rolled back); a second pass found {again}")
            if again:
                sys.exit("the second pass found changes: the sync does not settle")
        else:
            tx.commit()
            print(f"CERF figures: {n} field(s) changed to OneGMS's")


if __name__ == "__main__":
    main()
