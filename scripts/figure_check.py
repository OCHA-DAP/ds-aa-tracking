"""The figures that appear on more than one page agree — a build-time check (2026-10-28).

The owner's comment on the Financing page: "why does this $43.7M not match the $38M from CERF on
the first page — we need to make sure the numbers are consistent across the pages". Each page
builder hands this module the data its page embeds (KEY: the map's countries, the Financing page's
D, the History timeline, the Activities tiles, the framework pages' pre-arranged figures);
check() recomputes each shared figure from every page's data, under the same settings, and prints
one ::warning:: line per mismatch (the identifier guard's and the i18n check's way: the build goes
on, the publish run's summary shows it).

Compared like with like (the pages open on different defaults — the map on current frameworks
(D80), Financing with non-framework allocations too (D84)):
  * frameworks by status, retired frameworks: Map ↔ Financing ↔ History (↔ Activities' count)
  * pre-arranged now — total, CERF, Country and Regional Funds — and per framework: Map ↔
    Financing ↔ the framework page (its chart's current-year bar; its version envelope when it is
    the version the figure comes from, times the activations a year it allows)
  * people covered now: Map ↔ Financing
  * released this year by fund (current frameworks): Map ↔ Financing
  * released to date, framework activations and non-framework allocations, and the number of
    each: Map ↔ Financing ↔ History
  * people reached, CERF allocations of framework activations to date: Map ↔ Activities
  * the Financing page's sub-grant shares never exceed an allocation's money
Deliberate differences are not checked here — they are labelled on the pages: a past year on the
map shows the frameworks as they stood then (Financing classifies by today's status); the
Activities page's localisation share leaves partners not yet typed out of the whole, the
Financing page's counts them in; a framework page's version envelope is the budget of one
activation, or that of an earlier version where the current one has no split.
"""
from __future__ import annotations

import datetime as _dt

KEY: dict = {}      # page -> the data it embeds (filled by the builders)


def _fmt(v, kind):
    if v is None:
        return "—"
    return f"${v:,.0f}" if kind == "usd" else f"{v:,.0f}"


def check() -> None:
    """Compare the shared figures; print a summary line, or one ::warning:: per mismatch."""
    import landing
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
        if abs((a or 0) - (b or 0)) > tol:
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
    act = F["act"]
    usd = lambda rows: sum(r.get("amount_usd") or 0 for r in rows)   # noqa: E731
    for lc, k in (("active", "n_active"), ("updating", "n_upd"), ("development", "n_dev")):
        cmp(f"frameworks {lc}", "Map ↔ Financing", t[k], sum(r["lifecycle"] == lc for r in fw_c), "n")
        cmp(f"frameworks {lc}", "Map ↔ History", t[k], sum(r["life"] == lc for r in H["rows"]), "n")
    cmp("retired frameworks", "Map ↔ Financing", m_ret, sum(r["lifecycle"] == "retired" for r in F["fw"]), "n")
    cmp("retired frameworks", "Map ↔ History", m_ret, sum(r["life"] == "retired" for r in H["rows"]), "n")
    cmp("current frameworks", "Map ↔ Activities", t["n_fw"], A["n_live"], "n")
    pre_cerf = sum(r["total_usd"] or 0 for r in now_c if r["ft"] == "cerf")
    pre_pool = sum(r["total_usd"] or 0 for r in now_c if r["ft"] != "cerf")
    cmp("pre-arranged now", "Map ↔ Financing", t["pre"], pre_cerf + pre_pool)
    cmp("pre-arranged now, CERF", "Map ↔ Financing", t["pre_cerf"], pre_cerf)
    # an envelope not split by fund: the map says so, the Financing page counts it as pooled
    cmp("pre-arranged now, Country and Regional Funds", "Map ↔ Financing", t["pre_pooled"], pre_pool)
    cmp("people covered now", "Map ↔ Financing", t["covered"], sum(r["people_covered"] or 0 for r in F["cov"]), "n")
    a_cy = [r for r in act if r["g"] == "c" and int(r["year"]) == cy]
    cmp(f"released {cy}, CERF", "Map ↔ Financing", t["released_cerf"], usd(r for r in a_cy if r["fund_code"] == "cerf"))
    cmp(f"released {cy}, Country and Regional Funds", "Map ↔ Financing", t["released"] - t["released_cerf"],
        usd(r for r in a_cy if r["fund_code"] != "cerf"))
    cmp("released to date, framework activations", "Map ↔ Financing", t_fr["released"],
        usd(r for r in act if r["g"] in ("c", "r")))
    cmp("released to date, non-framework allocations", "Map ↔ Financing", t_ad["released"],
        usd(r for r in act if r["g"] == "a"))
    f_pre = {}
    for r in now_c:
        f_pre[r["k"]] = f_pre.get(r["k"], 0) + (r["total_usd"] or 0)
    for k in sorted(set(m_pre) | set(f_pre)):
        cmp(f"pre-arranged now, {k}", "Map ↔ Financing", (m_pre.get(k) or {}).get("pre_now"), f_pre.get(k))
    for code, x in (F.get("unSplit") or {}).items():
        n[0] += 1
        if sum(x["g"].values()) > 1 + 1e-9:
            bad.append(f"share sub-granted of {code} above 1 — Financing")

    # ---- History (its timeline's rows; every status ticked)
    ev = [e for r in H["rows"] for e in r["ev"]]
    cmp("framework activations to date", "Map ↔ History", t_fr["n_act"], sum(1 for e in ev if not e["ah"]), "n")
    cmp("released to date, framework activations", "Map ↔ History", t_fr["released"],
        sum(e["a"] or 0 for e in ev if not e["ah"]))
    cmp("non-framework allocations to date", "Map ↔ History", t_ad["n_act"], sum(1 for e in ev if e["ah"]), "n")
    cmp("released to date, non-framework allocations", "Map ↔ History", t_ad["released"],
        sum(e["a"] or 0 for e in ev if e["ah"]))

    # ---- Activities (people reached, CERF allocations of framework activations, to date)
    cmp("people reached", "Map ↔ Activities", t_fr["reached"], A["reached"], "n")
    cmp("CERF allocations reporting people reached", "Map ↔ Activities", t_fr["n_rep"], A["n_rep"], "n")
    cmp("CERF allocations of framework activations", "Map ↔ Activities", t_fr["n_cerf"], A["n_cerf"], "n")

    # ---- framework pages: the chart's current-year bar, and the version envelope when it is the
    # version pre-arranged now comes from (times the activations a year it allows)
    for k, f in m_pre.items():
        x, parts = FW.get(k), f.get("pre_parts") or {}
        if x is None or not f.get("pre_now"):
            continue
        cmp(f"pre-arranged {cy}, {k}", "Map ↔ framework page chart", f["pre_now"] - (parts.get("all") or 0), x["chart_cy"])
        if x["envelope"] and str(x["envelope_version"]) == str(parts.get("version")):
            cmp(f"envelope, {k}", "Map ↔ framework page", f["pre_now"], x["envelope"] * x["apy"])

    if not bad:
        print(f"  figure check: the figures shown on more than one page agree ({n[0]} comparisons: "
              "Map, Financing, Activities, History, framework pages)")
        return
    for b in bad[:25]:
        print(f"::warning::figure check: {b}")
    print(f"::warning::figure check: {len(bad)} of {n[0]} cross-page figures disagree"
          + (f" (first 25 listed)" if len(bad) > 25 else "")
          + " — scripts/figure_check.py says what each compares")
