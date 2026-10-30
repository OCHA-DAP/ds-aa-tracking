"""Swap provisional CERF amounts for OneGMS's once the allocation is recorded there.

A CERF allocation reaches OneGMS (and so the mirror, aa.cerf_allocation) days or weeks after
the money goes out. Meanwhile the amount is entered by hand as an aa.activation_funding row
with match_method = 'provisional' and no allocation_code (owner, 2026-10-30: "we need to be
able to add disbursed amounts from CERF before they show up in OneGMS; once they show up
there, they need to be auto-replaced by the OneGMS version"). The nightly job runs this
after the entries files: a provisional row whose allocation has appeared gets OneGMS's
allocation code, approved amount (and planned people, when the row has none), and
match_method 'onegms-auto'. Every change is audited (aa.entry_audit).

The allocation of a provisional row: a CERF allocation of the same country, tagged
anticipatory action, not yet linked to any activation, whose title names no other hazard,
and dated near the activation by any of its dates: ERC endorsement from 90 days before the
activation to 120 days after it, the month in its title ("… Sep 2026 (Anticipatory Action -
Floods)") within two months of it, or its first project approval from 30 days before to 240
days after (the endorsement date is often blank in OneGMS, and the first approval can come
months later: Mozambique cholera "Mar 2026" was first approved on 27 July). Exactly one such
allocation is taken; none leaves the row provisional (with a warning once it is 120 days
old); two or more are listed and left for a person to choose (enter the code by hand).
Country and Regional Fund rows stay as entered: their allocations carry no
anticipatory-action flag to match on.

Usage: uv run python scripts/resolve_provisional.py [--dry-run]
"""

import calendar
import datetime as dt
import json
import os
import re
import sys

import sqlalchemy as sa

os.environ.setdefault("PGSSLMODE", "require")

import ocha_stratus as stratus  # noqa: E402

D = dt.timedelta
# (date, days before the activation, days after it) a candidate's date may fall in
WINDOWS = {"erc": (90, 120), "title": (60, 60), "first": (30, 240)}
STALE = D(days=120)          # a provisional amount this old with no allocation found: warn
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                      "nov", "dec"), 1)}
# words a CERF allocation title uses for each hazard (titles read "… (Anticipatory Action - Floods)")
HAZARD_WORDS = {
    "flood": ("flood",),
    "storm": ("storm", "cyclone", "typhoon", "hurricane"),
    "drought": ("drought", "dry spell", "el niño", "el nino"),
    "cholera": ("cholera",),
}
KEY = ("country_iso3", "hazard", "event_date", "window_name", "event_label", "event_type", "fund_code")
# aa.activation_funding's unique key, as apply_entries writes it to the audit
AUDIT_KEY = KEY + ("allocation_code",)


def span(event_date):
    """The days an activation's partial ISO date ('2026', '2026-10', '2026-10-05') covers;
    None when it is not a date."""
    p = [int(x) for x in re.findall(r"\d+", str(event_date))[:3]]
    if not p:
        return None
    y, m, d = (p + [None, None])[:3]
    try:
        if m is None:
            return dt.date(y, 1, 1), dt.date(y, 12, 31)
        if d is None:
            return dt.date(y, m, 1), dt.date(y, m, calendar.monthrange(y, m)[1])
        return dt.date(y, m, d), dt.date(y, m, d)
    except ValueError:                                  # '2026-13': not a date
        return None


def title_month(title):
    """The first day of the month a CERF allocation's title names ('… Somalia Sep 2026 (…)')."""
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? ((?:19|20)\d\d)\b",
                  (title or "").lower())
    return dt.date(int(m.group(2)), MONTHS[m.group(1)], 1) if m else None


def near(c, sp):
    """A candidate allocation dated near the activation by any of its dates (WINDOWS)."""
    dates = {"erc": c["erc"], "title": title_month(c["title"]), "first": c["first"]}
    return any(v is not None and sp[0] - D(days=WINDOWS[k][0]) <= v <= sp[1] + D(days=WINDOWS[k][1])
               for k, v in dates.items())


def other_hazard(title, hazard):
    """The title names a hazard and none of them is this one."""
    t = (title or "").lower()
    named = {h for h, ws in HAZARD_WORDS.items() if any(w in t for w in ws)}
    return bool(named) and hazard not in named


def main():
    dry = "--dry-run" in sys.argv
    engine = stratus.get_engine(stage="dev", write=not dry)
    with engine.begin() as conn:
        rows = conn.execute(sa.text(
            "SELECT * FROM aa.activation_funding WHERE match_method = 'provisional' "
            "AND fund_code = 'cerf' AND allocation_code IS NULL")).mappings().fetchall()
        if not rows:
            print("provisional CERF amounts: none")
            return
        cand = conn.execute(sa.text(
            """SELECT c.application_code AS code, c.country_iso3, c.title, c.amount_approved,
                      c.individuals_planned, c.erc_endorsement_date AS erc,
                      c.first_project_approved_date AS first
               FROM aa.cerf_allocation c
               JOIN aa.v_allocation v ON v.allocation_code = c.application_code AND v.fund_type = 'cerf'
               WHERE v.is_aa AND c.amount_approved > 0
                 AND c.application_code NOT IN (SELECT allocation_code FROM aa.activation_funding
                                                WHERE allocation_code IS NOT NULL)""")).mappings().fetchall()
        picks = {}                                      # the row's full key -> (row, allocation)
        today = dt.date.today()
        for r in rows:
            sp = span(r["event_date"])
            k = tuple(r[c] for c in KEY)
            lab = "/".join("" if r[c] is None else str(r[c]) for c in KEY)
            if sp is None:
                print(f"::warning::provisional CERF amount {lab}: its date is not a date; left provisional")
                continue
            hits = [c for c in cand if c["country_iso3"] == r["country_iso3"] and near(c, sp)
                    and not other_hazard(c["title"], r["hazard"])]
            if len(hits) == 1:
                picks[k] = (r, hits[0], lab)
            elif hits:
                print(f"::warning::provisional CERF amount {lab}: {len(hits)} OneGMS allocations could be it "
                      f"({', '.join(c['code'] for c in hits)}): enter its allocation_code by hand")
            elif today - sp[1] > STALE:
                print(f"::warning::provisional CERF amount {lab}: no OneGMS allocation found {(today - sp[1]).days} "
                      f"days on; check it and enter the allocation_code by hand")
            else:
                print(f"  {lab}: not in OneGMS yet; stays provisional (${float(r['amount_usd'] or 0):,.0f})")
        # one allocation claimed by two provisional rows (two windows of one activation): a person decides
        claimed = {}
        for r, c, lab in picks.values():
            claimed.setdefault(c["code"], []).append(lab)
        n = 0
        for r, c, lab in picks.values():
            if len(claimed[c["code"]]) > 1:
                print(f"::warning::OneGMS allocation {c['code']} fits {len(claimed[c['code']])} provisional "
                      f"amounts ({'; '.join(claimed[c['code']])}): enter its allocation_code by hand")
                continue
            new = {"allocation_code": c["code"], "amount_usd": c["amount_approved"],
                   "match_method": "onegms-auto"}
            if r["people_targeted"] is None and c["individuals_planned"]:
                new["people_targeted"] = int(c["individuals_planned"])
            print(f"  {'(dry) ' if dry else ''}{lab}: provisional ${float(r['amount_usd'] or 0):,.0f} -> "
                  f"OneGMS {c['code']} ${float(c['amount_approved']):,.0f}")
            if dry:
                continue
            where = " AND ".join(f"{k} IS NOT DISTINCT FROM :k_{k}" for k in KEY) + " AND allocation_code IS NULL"
            conn.execute(sa.text(
                "UPDATE aa.activation_funding SET " + ", ".join(f"{k} = :{k}" for k in new)
                + ", updated_at = now() WHERE " + where),
                {**new, **{f"k_{k}": r[k] for k in KEY}})
            # audited under the row's new key, in apply_entries' format (every key column)
            rk = "/".join(str({**r, **new}.get(c)) for c in AUDIT_KEY)
            for f, v in new.items():
                conn.execute(sa.text(
                    "INSERT INTO aa.entry_audit (entered_by, table_name, row_key, field, old_value, new_value) "
                    "VALUES ('nightly resolve_provisional', 'activation_funding', :rk, :f, :o, :v)"),
                    {"rk": rk, "f": f, "o": json.dumps(r[f], default=str), "v": json.dumps(v, default=str)})
            n += 1
        print(f"provisional CERF amounts: {len(rows)}, replaced by OneGMS's: {n}" + (" (dry run)" if dry else ""))


if __name__ == "__main__":
    main()
