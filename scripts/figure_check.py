"""The figures that appear on more than one page agree — a build-time check (2026-10-28).

The owner's comment on the Financing page: "why does this $43.7M not match the $38M from CERF on
the first page — we need to make sure the numbers are consistent across the pages". Each page
builder hands this module the data its page embeds (KEY: the map's countries, the Financing page's
D, the History timeline, the Activities tiles, the framework pages' pre-arranged figures);
check() recomputes each shared figure from every page's data, under the same settings, and prints
one ::warning:: line per mismatch (the identifier guard's and the i18n check's way: the build goes
on, the publish run's summary shows it).

Compared like with like (both pages open on current frameworks, D80 and D142; the comparisons
name their layers explicitly either way):
  * frameworks by status, retired frameworks: Map ↔ Financing ↔ History (↔ Activities' count)
  * pre-arranged now — total, CERF, Country and Regional Funds — and per framework: Map ↔
    Financing ↔ the framework page (its chart's current-year bar; its version envelope when it is
    the version the figure comes from, times the activations a year it allows)
  * people covered now, and co-financing pre-arranged now: Map ↔ Financing
  * released this year by fund (current frameworks): Map ↔ Financing
  * released to date, framework activations and non-framework allocations, and the number of
    each: Map ↔ Financing ↔ History; and the current frameworks' own (the Map's released follows
    the Retired box, D185; the Financing page counts a retired framework's with either layer, D150)
  * people reached, CERF allocations of framework activations to date: Map ↔ Activities
  * the open layer (scripts/llm_layer.py, the files as written) ↔ the OPEN map (its own copy, its
    tiles as it opens): every headline figure recomputed from the files' rows, each framework's
    pre-arranged, people-covered and co-financing figure, and the figures aa-map.md states
    (open_layer(); llm_layer runs it while it writes the files, and says the result in llms.txt)
Deliberate differences are not checked here — they are labelled on the pages: a past year on the
map shows the frameworks as they stood then (Financing classifies pre-arranged money by today's
status, and with the current-frameworks layer off a past year's releases differ too: labelled on the
Map's tile); the
Activities page's localisation share leaves partners not yet typed out of the whole, the
Financing page's counts them in; a framework page's version envelope is the budget of one
activation, or that of an earlier version where the current one has no split.
"""
from __future__ import annotations

import datetime as _dt
import math

KEY: dict = {}      # page -> the data it embeds (filled by the builders)


def _fmt(v, kind):
    if v is None:
        return "—"
    return f"${v:,.0f}" if kind == "usd" else f"{v:,.0f}"


def open_layer(out, om) -> tuple[int, list[str]]:
    """The open layer's files (`out`: the directory they were written to) against the open map's own
    figures (`om`: landing.OPEN_MAP). Recomputes every headline tile from the files' rows by the
    map's rule (landing.tile_figures, _flow_acts), compares each framework's figures, and checks that
    aa-map.md states the headline figures. Returns (comparisons, mismatch lines); KEY["open"] keeps
    them for check()."""
    import json
    from pathlib import Path
    out = Path(out)
    T = {}
    for n in ("frameworks", "activations", "prearranged-funding", "cofinancing"):
        f = out / f"aa-{n}.json"
        T[n] = json.loads(f.read_text())["rows"] if f.exists() else None
    t, ad, y = om["tiles"], om.get("adhoc") or {}, str(om["year"])
    bad, n = [], [0]

    def cmp(figure, a, b, kind="usd"):
        n[0] += 1
        a0, b0 = (0.0 if x is None else float(x) for x in (a, b))
        if math.isnan(a0) or math.isnan(b0) or abs(a0 - b0) > (1.0 if kind == "usd" else 0.5):
            bad.append(f"{figure} — open files {_fmt(a, kind)}, open map {_fmt(b, kind)}")

    missing = [k for k, v in T.items() if v is None]
    if missing:
        bad.append(f"open layer: no {', '.join('aa-' + k for k in missing)} to compare")
        return n[0], bad
    fw = T["frameworks"]
    layers = {(r["country_iso3"], r["hazard"]): set(r["map_layers"] or []) for r in fw}
    on = [r for r in fw if "framework" in layers[(r["country_iso3"], r["hazard"])]]
    pairs = {(r["country_iso3"], r["hazard"]) for r in on}
    s_ = lambda rows, k: sum(r[k] or 0 for r in rows)      # noqa: E731
    # stock tiles
    cmp("frameworks", len(on), t["n_fw"], "n")
    cmp("their countries", len({c for c, _ in pairs}), t["n_ctry"], "n")
    for k, lc in (("n_active", "active"), ("n_upd", "updating"), ("n_dev", "development")):
        cmp(f"frameworks {lc}", sum(r["lifecycle"] == lc for r in on), t[k], "n")
    cmp("pre-arranged now", s_(on, "prearranged_usd"), t["pre"])
    cmp("pre-arranged now, CERF", s_(on, "prearranged_cerf_usd"), t["pre_cerf"])
    cmp("pre-arranged now, other than CERF", s_(on, "prearranged_usd") - s_(on, "prearranged_cerf_usd"),
        t["pre_pooled"] + t["pre_all"])
    cmp("pre-arranged now, aa-prearranged-funding's current-year rows",
        sum(r["amount_usd"] or 0 for r in T["prearranged-funding"] if str(r["year"]) == y
            and r["source"] == "framework-record" and (r["country_iso3"], r["hazard"]) in pairs), t["pre"])
    cmp("co-financing now", s_(on, "cofinancing_usd"), t["cofin"])
    cmp("frameworks with co-financing", sum(r["cofinancing_usd"] is not None for r in on), t["n_cofin"], "n")
    cmp("co-financing now, aa-cofinancing's current-year rows",
        sum(r["amount_usd"] or 0 for r in T["cofinancing"] if str(r["year"]) == y
            and (r["country_iso3"], r["hazard"]) in pairs), t["cofin"])
    cmp("people covered now", s_(on, "people_covered"), t["covered"], "n")
    cmp("frameworks with people covered", sum(bool(r["people_covered"]) for r in on), t["n_cov"], "n")
    # each framework, against the map's own record of it
    mf = {(iso, f["hazard"]): f for iso, cd in om["countries"].items() for f in cd["fws"]}
    import landing
    for r in fw:
        f = mf.get((r["country_iso3"], r["hazard"]))
        lab = f"{r['country_iso3']} {r['hazard']}"
        if f is None:
            bad.append(f"{lab} — in aa-frameworks, not on the open map")
            continue
        cmp(f"{lab} pre-arranged now", r["prearranged_usd"], f.get("pre_now") if "framework" in f["layers"]
            else r["prearranged_usd"])
        cmp(f"{lab} people covered", r["people_covered"], f.get("covered"), "n")
        cmp(f"{lab} co-financing now", r["cofinancing_usd"], landing.cof_of(f))
    if len(mf) != len(fw):
        bad.append(f"pairs — {len(fw)} in aa-frameworks, {len(mf)} on the open map")

    # flow tiles: the year's activations, by the map's rule (_flow_acts) for the open map's layer
    # (current frameworks): a retired or replaced framework's need the Retired layer (D185)
    def flows(kind):
        acts = []
        for a in T["activations"]:
            if str(a["event_date"] or "")[:4] != y or a["event_type"] != kind:
                continue
            L = layers.get((a["country_iso3"], a["hazard"]), set())
            own = "framework" if "framework" in L else "retired" if "retired" in L else None
            if kind == "adhoc_aa" or (not a["replaced_framework"] and own == "framework"):
                acts.append(a)
        rows = [x for a in acts for x in a["funding"]]
        cerf = [x for x in rows if x["fund_code"] == "cerf" and not x["allocation_shared"]]
        tgt = [x for x in cerf if x["people_reached"] is None and x["people_planned"]]
        seen, pool = set(), []
        for x in rows:
            if x["fund_code"] != "cerf" and not (x["allocation_code"] and x["allocation_code"] in seen):
                seen.add(x["allocation_code"])
                pool.append(x)
        ptgt = [x for x in pool if x["people_planned"]]
        return {"n_act": len(acts), "released": s_(rows, "amount_usd"),
                "released_cerf": sum(x["amount_usd"] or 0 for x in rows if x["fund_code"] == "cerf"),
                "refund": s_(rows, "refund_usd"), "prov": sum(x["amount_usd"] or 0 for x in rows if x["provisional"]),
                "reached": s_(cerf, "people_reached"), "n_rep": sum(x["people_reached"] is not None for x in cerf),
                "targeted": s_(tgt, "people_planned"), "n_tgt": len(tgt),
                "ptargeted": s_(ptgt, "people_planned"), "n_ptgt": len(ptgt)}
    for kind, tiles, what in (("framework_aa", t, "framework activations"), ("adhoc_aa", ad, "non-framework allocations")):
        if not tiles:
            continue
        g = flows(kind)
        for k, unit in (("n_act", "n"), ("released", "usd"), ("released_cerf", "usd"), ("refund", "usd"),
                        ("prov", "usd"), ("reached", "n"), ("n_rep", "n"), ("targeted", "n"), ("n_tgt", "n"),
                        ("ptargeted", "n"), ("n_ptgt", "n")):
            cmp(f"{what} {y}: {k}", g[k], tiles.get(k), unit)

    # aa-map.md states the headline figures as the map shows them
    md = (out / "aa-map.md").read_text() if (out / "aa-map.md").exists() else ""
    for figure, text in (("pre-arranged now", f"${t['pre']:,.0f}"), ("people covered", f"{int(t['covered']):,}"),
                         ("released this year", f"${t['released']:,.0f}"),
                         ("co-financing now", f"${t['cofin']:,.0f}" if t["n_cofin"] else None)):
        n[0] += 1
        if text and text not in md:
            bad.append(f"aa-map.md does not state the {figure} the map shows ({text})")
    KEY["open"] = (n[0], bad)
    return n[0], bad


def _report_open() -> None:
    """The open layer's comparisons (open_layer), in the publish run's summary."""
    if "open" not in KEY:
        return
    n, bad = KEY["open"]
    if not bad:
        print(f"  figure check (open layer): the open files agree with the open map ({n} comparisons)")
        return
    for b in bad[:25]:
        print(f"::warning::figure check (open layer): {b}")
    print(f"::warning::figure check (open layer): {len(bad)} of {n} figures of the open files disagree with "
          "the open map — scripts/figure_check.py open_layer() says what each compares")


def check() -> None:
    """Compare the shared figures; print a summary line, or one ::warning:: per mismatch."""
    import landing
    _report_open()
    need = ("map", "financing", "history", "activities", "fw")
    gone = [k for k in need if k not in KEY]
    if gone:
        print(f"::warning::figure check: not run — no data from {', '.join(gone)}")
        return
    M, F, H, A, FW = (KEY[k] for k in need)
    cy = _dt.date.today().year
    bad, n = [], [0]

    def cmp(figure, pages, a, b, kind="usd"):
        n[0] += 1
        tol = 1.0 if kind == "usd" else 0.5
        a0, b0 = (0.0 if x is None else float(x) for x in (a, b))
        if math.isnan(a0) or math.isnan(b0) or abs(a0 - b0) > tol:     # a NaN figure is a mismatch
            bad.append(f"{figure} — {pages}: {_fmt(a, kind)} vs {_fmt(b, kind)}")

    # ---- the map (window.L), by its own tile rule (landing.tile_figures = updateTiles)
    t = landing.tile_figures(M, {"framework"}, cy)
    t_fr = landing.tile_figures(M, {"framework", "retired"}, None)
    t_ad = landing.tile_figures(M, {"adhoc"}, None)
    m_fw = [f for cd in M.values() for f in cd["fws"] if "framework" in f["layers"]]
    m_ret = sum(1 for cd in M.values() for f in cd["fws"] if "retired" in f["layers"])
    m_pre = {f"{iso}|{f['hazard']}": f for iso, cd in M.items() for f in cd["fws"] if "framework" in f["layers"]}

    # ---- the Financing page (D): its layers as the page draws them (g: c current, r retired, a non-framework)
    fw_c = [r for r in F["fw"] if r["g"] == "c"]
    now_c = [r for r in F["now"] if r["g"] == "c"]
    # money pre-arranged outside a framework and not yet released (D223): the map's non-framework
    # layer against the Financing page's (each reads dashboards.read_adhoc_prearranged its own way)
    cmp("pre-arranged outside a framework, not yet released", "Map ↔ Financing", t_ad["pre_ad"],
        sum(r.get("total_usd") or 0 for r in F["now"] if r["g"] == "a"))
    act = F["act"]
    usd = lambda rows: sum(r.get("amount_usd") or 0 for r in rows)   # noqa: E731
    for lc, k in (("active", "n_active"), ("updating", "n_upd"), ("development", "n_dev")):
        cmp(f"frameworks {lc}", "Map ↔ Financing", t[k], sum(r["lifecycle"] == lc for r in fw_c), "n")
        cmp(f"frameworks {lc}", "Map ↔ History", t[k], sum(r["life"] == lc for r in H["rows"]), "n")
    # the Financing page's chart of frameworks by status each year: its current-year bar is today
    fwy_cy = [r["y"].get(str(cy)) for r in F.get("fwy", [])]
    for lc, k in (("active", "n_active"), ("updating", "n_upd"), ("development", "n_dev")):
        cmp(f"frameworks {lc}", "Map ↔ Financing by-year chart", t[k], sum(x == lc for x in fwy_cy), "n")
    # ... and its bar for last year is what the Map's year bar shows (statusAt, per pair)
    fwy = {r["k"]: r for r in F.get("fwy", [])}
    y1 = f"{cy - 1}-12-31"
    off = 0
    for iso, cd in M.items():
        for f in cd["fws"]:
            k = f"{iso}|{f['hazard']}"
            if k in fwy and landing.status_at(f["versions"], f.get("hist"), y1) != fwy[k]["y"].get(str(cy - 1)):
                off += 1
    cmp(f"frameworks by status, {cy - 1}, pairs that differ", "Map ↔ Financing by-year chart", 0, off, "n")
    cmp("retired frameworks", "Map ↔ Financing", m_ret, sum(r["lifecycle"] == "retired" for r in F["fw"]), "n")
    cmp("retired frameworks", "Map ↔ History", m_ret, sum(r["life"] == "retired" for r in H["rows"]), "n")
    cmp("current frameworks", "Map ↔ Activities", t["n_fw"], A["n_live"], "n")
    pre_cerf = sum(r["total_usd"] or 0 for r in now_c if r["ft"] == "cerf")
    pre_pool = sum(r["total_usd"] or 0 for r in now_c if r["ft"] != "cerf")
    cmp("pre-arranged now", "Map ↔ Financing", t["pre"], pre_cerf + pre_pool)
    cmp("pre-arranged now, CERF", "Map ↔ Financing", t["pre_cerf"], pre_cerf)
    # an envelope not split by fund: the map lists it apart, the Financing page with the pooled funds
    cmp("pre-arranged now, Country and Regional Funds", "Map ↔ Financing", t["pre_pooled"] + t["pre_all"], pre_pool)
    cmp("people covered now", "Map ↔ Financing", t["covered"], sum(r["people_covered"] or 0 for r in F["cov"]), "n")
    # co-financing pre-arranged now: the Map's tile (current frameworks) and the Financing page's
    # co-financing now, current frameworks
    cmp("co-financing pre-arranged now", "Map ↔ Financing", t["cofin"],
        sum(r["amount_usd"] or 0 for r in F.get("cofNow", []) if r["g"] == "c"))
    a_cy = [r for r in act if r["g"] == "c" and int(r["year"]) == cy]
    cmp(f"released {cy}, CERF", "Map ↔ Financing", t["released_cerf"], usd(r for r in a_cy if r["fund_code"] == "cerf"))
    cmp(f"released {cy}, Country and Regional Funds", "Map ↔ Financing", t["released"] - t["released_cerf"],
        usd(r for r in a_cy if r["fund_code"] != "cerf"))
    cmp("released to date, framework activations", "Map ↔ Financing", t_fr["released"],
        usd(r for r in act if r["g"] in ("c", "r")))
    cmp("released to date, non-framework allocations", "Map ↔ Financing", t_ad["released"],
        usd(r for r in act if r["g"] == "a"))
    # the map's flows follow the retired layer (D185; all years ticks it on, so the all-years view
    # is the both-layers figure above): current frameworks alone are the Financing page's current
    # layer's own money. The Financing page still counts retired money with either layer (D150)
    t_cur = landing.tile_figures(M, {"framework"}, None)
    cmp("released to date, current frameworks' own", "Map ↔ Financing", t_cur["released"],
        usd(r for r in act if r["g"] == "c"))
    f_pre = {}
    for r in now_c:
        f_pre[r["k"]] = f_pre.get(r["k"], 0) + (r["total_usd"] or 0)
    for k in sorted(set(m_pre) | set(f_pre)):
        cmp(f"pre-arranged now, {k}", "Map ↔ Financing", (m_pre.get(k) or {}).get("pre_now"), f_pre.get(k))

    # ---- History (its timeline's rows; every status ticked)
    ev = [e for r in H["rows"] for e in r["ev"]]
    cmp("framework activations to date", "Map ↔ History", t_fr["n_act"], sum(1 for e in ev if not e["ah"]), "n")
    cmp("released to date, framework activations", "Map ↔ History", t_fr["released"],
        sum(e["a"] or 0 for e in ev if not e["ah"]))
    cmp("non-framework allocations to date", "Map ↔ History", t_ad["n_act"], sum(1 for e in ev if e["ah"]), "n")
    cmp("released to date, non-framework allocations", "Map ↔ History", t_ad["released"],
        sum(e["a"] or 0 for e in ev if e["ah"]))

    # ---- Activities (people reached, CERF allocations of framework activations, to date)
    # the Activities page's people series (page_plan._people_series) reads the map's records year
    # by year: its current year is the map's estimate for the year, its years together the map's total
    t_cy = landing.tile_figures(M, {"framework", "retired"}, cy)
    cmp(f"people reached or targeted, {cy}", "Map ↔ Activities", t_cy["reached"] + t_cy["targeted"] + t_cy["ptargeted"],
        A["reach_cy"], "n")
    cmp("people reached", "Map ↔ Activities", t_fr["reached"], A["reached"], "n")
    cmp("CERF allocations reporting people reached", "Map ↔ Activities", t_fr["n_rep"], A["n_rep"], "n")
    cmp("CERF allocations of framework activations", "Map ↔ Activities", t_fr["n_cerf"], A["n_cerf"], "n")

    # ---- framework pages: the chart's current-year bar, and the version envelope when it is the
    # version pre-arranged now comes from (times the activations a year it allows)
    # (a framework with no envelope has no figure to compare; a page whose envelope is an earlier
    # version's, or a page missing, is counted and named in the summary line)
    n_pg = n_env = 0
    no_page = []
    for k, f in m_pre.items():
        x, parts = FW.get(k), f.get("pre_parts") or {}
        if not f.get("pre_now"):
            continue
        if x is None:
            no_page.append(k)
            continue
        n_pg += 1
        cmp(f"pre-arranged {cy}, {k}", "Map ↔ framework page chart", f["pre_now"] - (parts.get("all") or 0), x["chart_cy"])
        if x["envelope"] and str(x["envelope_version"]) == str(parts.get("version")):
            n_env += 1
            cmp(f"envelope, {k}", "Map ↔ framework page", f["pre_now"],
                x["envelope"] - x.get("envelope_released", 0.0)       # a released pooled envelope is not committed
                + x.get("envelope_cerf", x["envelope"]) * (x["apy"] - 1))   # CERF counts N times
    if no_page:
        bad.append(f"no framework page data for {', '.join(sorted(no_page))} — framework pages")
    pages = (f"framework pages: {n_pg} charts, {n_env} envelopes (the others give an earlier version's, "
             "labelled on the page)")

    if not bad:
        # what the pre-arranged comparisons can and cannot catch (review of PR #58): the Map, the
        # Financing page and the framework pages all read prearranged_now(), so those checks catch a
        # page that transforms it differently, not a wrong envelope; released money, the counts,
        # History's events and people reached come from independent queries
        print(f"  figure check: the figures shown on more than one page agree ({n[0]} comparisons — "
              f"Map, Financing, Activities, History; {pages}). Pre-arranged figures share one source "
              f"(prearranged_now) and are checked for consistent handling; released money, counts and "
              f"people reached are independent")
        return
    for b in bad[:25]:
        print(f"::warning::figure check: {b}")
    print(f"::warning::figure check: {len(bad)} of {n[0]} cross-page figures disagree"
          + (f" (first 25 listed)" if len(bad) > 25 else "")
          + " — scripts/figure_check.py says what each compares")
