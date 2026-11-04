"""CERF's insurance portfolio, as the annex "Anticipatory action frameworks covered by the
insurance" lists it (D198; owner, 2026-11-04, passing on a colleague's request: "Under financing,
let's include the insurance portfolio and monitor against expenditure"; "just include that info").

Only the annex and the owner's two notes are used here (the period it runs, and what a loss
statement is); nothing else about the insurance. The Financing page (dashboards.build_funding)
shows the cover and, beside it, the CERF money released on the covered frameworks' activations
in the period.

A once-a-period annex, so it lives here rather than in a table: when the portfolio is renewed,
replace COVER, PERIOD and UPDATED together (the checks below then fail until the totals match the
new annex's), or move it to a table if it starts to change within a period.
"""

# the annex's iteration of the portfolio: 1 October 2026 to 31 December 2027, as months, the
# grain an activation's event_date is sure to carry ('2026-10' sorts before '2026-10-01')
PERIOD = ("2026-10", "2027-12")
START_TEXT = "1 October 2026"
PERIOD_TEXT = START_TEXT + " to 31 December 2027"
UPDATED = "2026-11-04"   # the date the annex was copied here

# (country ISO3, hazard code, cover limit in US$ million per season, also in UNICEF's policy,
#  can activate up to twice per season: the limit is then the maximum across both activations)
COVER = (
    ("AFG", "drought", 12.0, True, False),
    ("BGD", "flood", 6.0, True, False),
    ("BGD", "storm", 4.0, True, False),
    ("BFA", "drought", 8.0, False, False),
    ("TCD", "drought", 7.9, False, False),
    ("TCD", "flood", 4.0, False, False),
    ("CUB", "storm", 9.0, False, True),
    ("SLV", "drought", 2.5, False, False),
    ("ETH", "drought", 10.0, True, False),
    ("FJI", "storm", 2.4, True, False),
    ("GTM", "drought", 4.0, False, False),
    ("HTI", "storm", 8.0, True, True),
    ("HND", "drought", 4.0, False, False),
    ("KEN", "drought", 5.0, True, False),
    ("MDG", "storm", 6.0, True, True),
    ("MRT", "drought", 2.5, False, False),
    ("MOZ", "storm", 9.0, False, True),
    ("MMR", "storm", 10.0, False, True),
    ("NPL", "flood", 2.8, False, False),
    ("NER", "drought", 8.0, True, False),
    ("NER", "flood", 5.0, False, False),
    ("NGA", "flood", 5.0, False, False),
    ("PHL", "storm", 12.0, True, True),
    ("VUT", "storm", 1.5, False, False),
)

# the annex's own totals: a slip in copying it fails the build rather than going live
_PAIRS = {(c, h) for c, h, *_ in COVER}
assert len(COVER) == len(_PAIRS) == 24, "insurance: the annex lists 24 frameworks"
assert len({c for c, *_ in COVER}) == 21, "insurance: the annex covers 21 countries"
assert round(sum(m for _, _, m, _, _ in COVER), 1) == 148.6, "insurance: the annex's total cover is US$148.6M"
assert sum(u for *_, u, _ in COVER) == 10, "insurance: UNICEF's policy covers 10 frameworks"
assert len({c for c, _, _, u, _ in COVER if u}) == 9, "insurance: UNICEF's policy covers 9 countries"


def in_period(event_date) -> bool:
    """An activation dated within the portfolio's period (event_date is partial ISO: a month or a day)."""
    return PERIOD[0] <= str(event_date)[:7] <= PERIOD[1]


def monitor(activation):
    """[{iso3, hazard, cover (US$), unicef, twice, released (US$), n (loss statements)}] in the
    annex's order: per covered framework, the CERF money released on its framework activations
    dated in the period (net of refunds, as every page counts released money; an amount entered
    before OneGMS records the allocation included) and how many such activations — each one a
    loss statement, CERF's notification that the framework is triggered."""
    a = activation
    a = a[(a["event_type"] == "framework_aa") & (a["fund_code"] == "cerf")
          & a["event_date"].map(in_period)]
    out = []
    for c, h, m, unicef, twice in COVER:
        rows = a[(a["country_iso3"] == c) & (a["hazard"] == h)]
        # one activation = one (event_date, window): a window's CERF money may be in several rows
        n = len(rows[["event_date", "window_name"]].drop_duplicates())
        out.append({"iso3": c, "hazard": h, "cover": m * 1e6, "unicef": unicef, "twice": twice,
                    "released": float(rows["amount_usd"].fillna(0).sum()), "n": n})
    return out
