"""The Activities page (pillar-plan.html; the 'Plan' pillar until 2026-10-27).

Split out of dashboards.py on 2026-09-30 and reworked the same day around partners: the
money views (budget by agency / sector) live on the Financing page. Reworked again on the
review of 2026-11-10 (D224): what makes an effective anticipatory activity, six headline tiles,
one sector-by-hazard table in the IASC's cluster order, and time series for people (by sex and
age) and for partners (how many, and the money by kind of organisation). Shared helpers stay
in dashboards; the few tables `_fetch` does not load are read by `_extra()` below."""

import html
import json
import re
import unicodedata

import pandas as pd
from dashboards import (
    CERF_FW_CODES_SQL,
    LIFE_LABEL,
    PAL,
    _dash_page,
    current_source,
    haz,
    hazard_word,
)
from site_i18n import ATTR, ATTRC, TB, TBC, TBF, TF, T

LIVE = ("active", "updating", "development")
HAZ_ROWS = ["drought", "flood", "storm", "cholera", "other"]

# ---- partners ---------------------------------------------------------------------------
# display groups of aa.framework_partner.org_type; 'rcrc' is split into the national
# society of the country and the international movement (RCRC_INTL matches name/acronym)
TYPE_GROUPS = [("government", "Government"), ("nngo", "National / local NGOs"),
               ("rcrc_nat", "National Red Cross / Red Crescent"), ("un", "UN"),
               ("ingo", "International NGOs"),
               ("rcrc_intl", "International Red Cross / Red Crescent"),
               ("academic", "Academic / research"), ("private", "Private sector"),
               ("donor", "Donors"), ("other", "Other")]
RCRC_INTL = re.compile(r"internation|f[eé]d[eé]ration|ifrc|german|alemana|netherlands|510|"
                       r"climate", re.IGNORECASE)
GLOBAL_TYPES = ("un", "ingo", "rcrc_intl", "donor")    # de-duplicated across countries
# the same UN agency under its French / Spanish acronym (normalised, lower-case)
UN_ALIAS = {"pam": "wfp", "pma": "wfp", "oms": "who", "oim": "iom", "hcr": "unhcr",
            "acnur": "unhcr", "pnud": "undp", "ops": "paho", "opsoms": "paho",
            "pahowho": "paho", "unw": "unwomen"}

# ---- sectors: IASC cluster / sector names (plus CERF's multi-purpose cash and coordination
# and support services). Framework split labels and CERF's IASC sector names -> one bucket;
# the mapping is shown on the page. CERF rows are bucketed on aa.cerf_project_sector.
# iasc_sector_name ('Multi-Sector' there is CERF's multi-purpose cash). Labels that are not an
# IASC sector go to OTHER_SECTOR — CERF itself has no early-warning sector.
OTHER_SECTOR = "Other (not an IASC sector)"
SECTOR_BUCKETS = [
    ("Food Security", ["food security", "food assistance", "food aid", "agriculture",
                       "food security & livelihoods", "food security & agriculture",
                       "agriculture & livelihoods", "agriculture and livelihoods", "food",
                       "food security (food)", "food security (livelihoods/agriculture)",
                       "food security - agriculture", "fsac", "sécurité alimentaire",
                       "sécurité alimentaire et moyens de subsistance"]),
    ("Health", ["health", "santé", "srh", "health (srh)", "sexual and reproductive health"]),
    ("Nutrition", ["nutrition"]),
    ("Water, Sanitation and Hygiene (WASH)", ["wash", "water, sanitation and hygiene",
                                              "water sanitation hygiene",
                                              "eau, assainissement et hygiène (eah)",
                                              # agreed in review 2026-10-16
                                              "early recovery"]),
    ("Protection", ["protection", "child protection", "gbv", "gender-based violence",
                    "gender based violence", "protection (gbv)", "mine action"]),
    ("Shelter and Non-Food Items", ["shelter/nfi", "shelter", "shelter and non-food items",
                                    "emergency shelter and nfi",
                                    "abris et biens non-alimentaires (abna)"]),
    ("Camp Coordination and Camp Management (CCCM)", ["cccm", "camp coordination and camp management",
                                                      "camp coordination / management"]),
    ("Education", ["education"]),
    # coordination and support services: agreed in review 2026-10-16
    ("Logistics", ["logistics", "coordination and support services", "common services",
                   "humanitarian air services"]),
    ("Emergency Telecommunications", ["emergency telecommunications"]),
    ("Multi-purpose cash", ["multi-purpose cash", "multi-sector/mpca", "multi-purpose cash (mpca)"]),
    (OTHER_SECTOR, ["early warning messaging", "multi-sector (community engagement)",
                    "disaster risk reduction"]),
]
SECTOR_COMBINED = {"health & nutrition": ["Health", "Nutrition"],
                   "shelter & cccm": ["Shelter and Non-Food Items", "Camp Coordination and Camp Management (CCCM)"],
                   "food security (window 1) / nutrition (window 2)": ["Food Security", "Nutrition"]}
SECTOR_SKIP = {"to be determined"}
# a bucket name maps to itself: dashboards._merge_labels already buckets the money rows
_SECTOR = ({b.lower(): [b] for b, _ in SECTOR_BUCKETS}
           | {raw: [b] for b, raws in SECTOR_BUCKETS for raw in raws} | SECTOR_COMBINED)


def _buckets(label):
    k = str(label).strip().lower()
    if not k or k in SECTOR_SKIP or k == "nan":
        return []
    return _SECTOR.get(k, [OTHER_SECTOR])


def _cerf_label(iasc, cerf):
    """CERF's IASC sector name, except 'Multi-Sector', which is CERF's multi-purpose cash."""
    i = "" if iasc is None or pd.isna(iasc) else str(iasc).strip()
    return cerf if (not i or i.lower() == "multi-sector") else i


# ---- the heat map's columns: the eight clusters of the IASC's 2026 guidance, in the order of its
# Annex 5 (Global Clusters and Cluster Lead Agencies: the wheel read clockwise from Food
# Security), then one column for what sits outside them (review, 2026-11-10). Each column takes
# the sector buckets above: Emergency Telecommunications with Logistics, camp coordination with
# Shelter (the guidance's consolidated clusters); multi-purpose cash is no cluster, so it is in
# Other with the labels that name no sector.
IASC_OTHER = "Other"
IASC_COLS = [
    ("Food Security", ["Food Security"]),
    ("Health", ["Health"]),
    ("Logistics and Telecommunications", ["Logistics", "Emergency Telecommunications"]),
    ("Nutrition", ["Nutrition"]),
    ("Protection", ["Protection"]),
    ("Shelter, Land and Site Coordination", ["Shelter and Non-Food Items",
                                             "Camp Coordination and Camp Management (CCCM)"]),
    ("Water, Sanitation and Hygiene", ["Water, Sanitation and Hygiene (WASH)"]),
    ("Education", ["Education"]),
    (IASC_OTHER, ["Multi-purpose cash", OTHER_SECTOR]),
]
_COL = {b: col for col, bs in IASC_COLS for b in bs}
assert set(_COL) == {b for b, _ in SECTOR_BUCKETS}, "every sector bucket needs a heat-map column"

# sex and age groups in the order the bars stack them (review, 2026-11-10: "men, boys, girls,
# women (gradients of blue and green respectively)"): blues for men and boys, greens for girls
# and women, the adults darker. NA: people whose sex and age no record gives
SEX_AGE = ["men", "boys", "girls", "women"]
# (the four checked as neighbours in the stack: colour-vision-deficiency dE >= 19, normal vision >= 20)
SEX_AGE_COLOR = {"men": "#1c5cab", "boys": "#5b9be8", "girls": "#45c486", "women": "#0b6b47", "na": "#c8ccd2"}
# the recipient groups of the partner charts, in the review's order; keys as dashboards.ORG_COLOR
PARTNER_GROUPS = [("un", "UN"), ("nngo", "National / local NGOs"), ("ingo", "International NGOs"),
                  ("rc", "Red Cross / Red Crescent"), ("gov", "Government"), ("oth", "Other"),
                  ("nr", "Not recorded yet")]


def _cols(label):
    """The heat-map columns a sector label counts in."""
    return {_COL[b] for b in _buckets(label)}


# ---- the tables `_fetch` does not load ----------------------------------------------------
def _extra():
    """One engine, one read per table, each tolerant of an older snapshot (empty frame).
    The CERF rows are those of the allocations framework activations drew on (CERF_FW_CODES_SQL:
    non-framework and early-action allocations left out), as the map counts them by default — not the
    mirror's title keyword (aa_keyword) nor its sub-grant flag (is_aa). The Country and Regional
    Fund rows are those of the projects of the allocation a framework activation drew on: only
    the projects listed for the release where the allocation paid for other things too (D192)."""
    import ocha_stratus as stratus
    e = stratus.get_engine(stage="dev")
    fw = "(" + CERF_FW_CODES_SQL + ")"
    has_afp = pd.read_sql("SELECT to_regclass('aa.activation_funding_project') AS r", e)["r"].iloc[0] is not None
    listed = ("""
                 AND (p.chf_project_code IN (SELECT x.project_code FROM aa.activation_funding_project x
                                             WHERE x.allocation_code = f.allocation_code)
                      OR NOT EXISTS (SELECT 1 FROM aa.activation_funding_project x
                                     WHERE x.allocation_code = f.allocation_code))""" if has_afp else "")
    pooled = """(SELECT DISTINCT allocation_code FROM aa.activation_funding
                 WHERE fund_code <> 'cerf' AND event_type = 'framework_aa'
                   AND allocation_code ~ '^cbpf-[0-9]+-[0-9]+$') f
                JOIN aa.cbpf_project p
                  ON 'cbpf-' || p.pooled_fund_id || '-' || p.allocation_type_id = f.allocation_code"""
    q = {
        "alloc": ("""SELECT application_code, year, country_iso3,
                            lower(trim(emergency_type)) AS emergency_type, amount_approved,
                            individuals_planned, individuals_reached, report_due_date
                     FROM aa.cerf_allocation WHERE application_code IN """ + fw,
                  ["application_code", "year", "country_iso3", "emergency_type",
                   "amount_approved", "individuals_planned", "individuals_reached",
                   "report_due_date"]),
        # sex and age per allocation summed over its projects: the shares used where the
        # allocation's own breakdown is not in yet (CERF's project records carry it for every year)
        "proj": ("""SELECT p.application_code,
                           sum(p.planned_men) AS planned_men, sum(p.planned_boys) AS planned_boys,
                           sum(p.planned_girls) AS planned_girls, sum(p.planned_women) AS planned_women,
                           sum(p.reached_men) AS reached_men, sum(p.reached_boys) AS reached_boys,
                           sum(p.reached_girls) AS reached_girls, sum(p.reached_women) AS reached_women
                    FROM aa.cerf_project p
                    WHERE p.application_code IN """ + fw + " GROUP BY p.application_code",
                 ["application_code"] + [f"{ph}_{g}" for ph in ("planned", "reached") for g in SEX_AGE]),
        "sector": ("""SELECT p.application_code, s.cerf_sector_name AS sector,
                             s.iasc_sector_name AS iasc, s.sector_amount
                      FROM aa.cerf_project_sector s
                      JOIN aa.cerf_project p USING (project_code)
                      WHERE p.application_code IN """ + fw + " AND s.sector_amount > 0",
                   ["application_code", "sector", "iasc", "sector_amount"]),
        # no allocation code in the file: build_plan keeps the rows of framework allocations
        "cva": ("""SELECT year, country_iso3, lower(trim(emergency_type)) AS emergency_type,
                          amount_approved_usd, cva_usd, people_receiving_cash
                   FROM aa.cerf_cva_history""",
                ["year", "country_iso3", "emergency_type", "amount_approved_usd", "cva_usd",
                 "people_receiving_cash"]),
        "people": ("""SELECT p.application_code, p.phase, p.disaggregation, p.grp, p.value
                      FROM aa.cerf_application_people p
                      WHERE p.application_code IN """ + fw,
                   ["application_code", "phase", "disaggregation", "grp", "value"]),
        # the Country and Regional Funds' projects of framework releases: the people they target
        # by sex and age, and their clusters
        "cbpf_people": ("""SELECT f.allocation_code, sum(p.men) AS men, sum(p.boys) AS boys,
                                  sum(p.girls) AS girls, sum(p.women) AS women
                           FROM """ + pooled + " WHERE true" + listed + " GROUP BY 1",
                        ["allocation_code"] + SEX_AGE),
        "cbpf_cluster": ("""SELECT DISTINCT f.allocation_code, c.cluster
                            FROM """ + pooled + """
                            JOIN aa.cbpf_project_cluster c ON c.chf_project_code = p.chf_project_code
                            WHERE coalesce(c.budget_by_cluster, c.cluster_percentage, 1) > 0""" + listed,
                         ["allocation_code", "cluster"]),
        "incl": ("""SELECT country_iso3, year, source, plan_type, in_gho, exposure_aa_shocks,
                           aa_feasible, aa_prearranged, has_framework, updated_at::date AS updated
                    FROM aa.plan_inclusion""",
                 ["country_iso3", "year", "source", "plan_type", "in_gho",
                  "exposure_aa_shocks", "aa_feasible", "aa_prearranged", "has_framework", "updated"]),
    }
    out = {}
    for key, (sql, cols) in q.items():
        try:
            out[key] = pd.read_sql(sql, e)
        except Exception as exc:  # noqa: BLE001 — an older snapshot lacks the table
            print(f"  plan: {key} unavailable ({exc.__class__.__name__})")
            out[key] = pd.DataFrame(columns=cols)
    return out


# ---- organisation matching ----------------------------------------------------------------
def _n(s):
    """Lower-case ASCII alphanumerics (accents and HTML entities folded)."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = unicodedata.normalize("NFKD", html.unescape(str(s))).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _group(org_type, name, acronym):
    t = org_type if org_type in {k for k, _ in TYPE_GROUPS} | {"rcrc"} else "other"
    if t == "rcrc":
        return "rcrc_intl" if RCRC_INTL.search(f"{name} {acronym or ''}") else "rcrc_nat"
    return t


def _org_ids(p):
    """One id per organisation: partner rows that share a normalised acronym (UN_ALIAS
    applied) or name are merged, within the country for national actors and across
    countries for GLOBAL_TYPES. Approximate: spelling variants without a shared acronym
    stay apart."""
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    first = []
    for i, r in enumerate(p.itertuples()):
        scope = "" if r.grp in GLOBAL_TYPES else r.country_iso3
        a = _n(r.acronym)
        ks = [f"{scope}|{k}" for k in (UN_ALIAS.get(a, a), _n(r.name)) if len(k) >= 2]
        ks = ks or [f"{scope}|row{i}"]
        for k in ks[1:]:
            parent[find(k)] = find(ks[0])
        first.append(ks[0])
    return [find(k) for k in first]


def _partner_rows(d):
    """(rows, none): the partner rows of the current frameworks, each framework's from its latest
    version that has a partner list, with the display group and an organisation id (_org_ids);
    and the current frameworks with no list, as (country name, hazard)."""
    cur = d["current"]
    live = cur[cur["lifecycle"].isin(LIVE)]
    # an earlier framework that a distinct new one replaced (dashboards.old_versions: Somalia
    # drought 2019 / 2020-06-23) is a retired framework: its partner list is not the live one's
    old = d.get("old") or set()
    pt = d["partners"].copy()
    pt["version"] = pt["version"].astype(str)
    pt = pt.loc[[(c, h, v) not in old for c, h, v in zip(pt["country_iso3"], pt["hazard"], pt["version"])]]
    pt = pt.merge(live[["country_iso3", "hazard"]], on=["country_iso3", "hazard"])
    # dated versions rank above undated labels such as 'development' (a plain string max would
    # put 'development' above every date)
    _vk = pt["version"].astype(str).map(lambda v: (v[:1].isdigit(), v))
    lv = (pt.assign(_vk=_vk).sort_values("_vk").groupby(["country_iso3", "hazard"])["version"]
          .last().rename("lv").reset_index())
    pt = pt.merge(lv, on=["country_iso3", "hazard"])
    pt = pt[pt["version"] == pt["lv"]].reset_index(drop=True)
    pt["grp"] = [_group(t, n, a) for t, n, a in zip(pt["org_type"], pt["name"], pt["acronym"])]
    pt["oid"] = _org_ids(pt) if len(pt) else []
    have = set(zip(pt["country_iso3"], pt["hazard"]))
    none = [(r.country_name, r.hazard) for r in live.sort_values(["country_name", "hazard"]).itertuples()
            if (r.country_iso3, r.hazard) not in have]
    return pt, none


def _framework_acts(M, year):
    """The framework activations of `year` on the map's data (landing.assemble), as (iso3,
    framework record, activation): those of the frameworks since retired or replaced too, which
    were frameworks then."""
    return [(iso, f, a) for iso, cd in M.items() for f in cd["fws"] for a in f["activations"]
            if a["type"] == "framework_aa" and str(a["date"])[:4] == str(year)]


def _people_series(M, ex, years):
    """People planned and people reached or targeted by the framework activations of each year, by
    sex and age, and the people with disabilities among them. One row per year:
    {y, p: planned [men, boys, girls, women, not recorded], r: reached or targeted (same order),
     nA / nRep / nTgt: the CERF allocations, those with people reached reported, those awaiting a
     report; nPool: the Country and Regional Fund allocations with people targeted;
     dp, ndp / dr, ndr: people with disabilities planned / reached or targeted, and the CERF
     allocations that give the figure}.

    The totals follow the map's rule (landing.tile_figures), on the map's own records: a CERF
    allocation counts once (an allocation two activations drew on, on the first); its people
    reached where CERF reports them, else the people it plans to reach (targeted); a Country or
    Regional Fund allocation counts the people it targets, in both bars (the funds report no
    people reached here). People planned are the allocation's own plan. The split by sex and age:
    the allocation's own breakdown (CERF's reports), else the shares of its projects' figures
    applied to the allocation's figure (a person in two projects counts twice in the projects'
    sum, so only the shares are used); a pooled fund's allocation: the shares of its projects.
    Disabilities: the allocation's own count (a separate count, overlapping the others); CERF
    only: the people reached where CERF's report gives the figure, else the people targeted."""
    al = ex["alloc"].drop_duplicates("application_code").set_index("application_code")
    pe = ex["people"]
    own, dis = {}, {}       # (code, phase) -> {group: people}; (code, phase) -> people with disabilities
    for (code, ph, dg), g in pe.groupby(["application_code", "phase", "disaggregation"]):
        v = dict(zip(g["grp"], g["value"]))
        if dg == "sex_age":
            own[(code, ph)] = {k: float(v.get(k) or 0) for k in SEX_AGE}
        elif dg == "disability" and pd.notna(v.get("total")):
            dis[(code, ph)] = float(v["total"])
    pj = ex["proj"].set_index("application_code") if len(ex["proj"]) else ex["proj"]
    cb = ex["cbpf_people"].set_index("allocation_code") if len(ex["cbpf_people"]) else ex["cbpf_people"]

    def norm(v):
        t = sum(v.values())
        return {k: x / t for k, x in v.items()} if t > 0 else None

    def shares(code, phase):
        s = norm(own.get((code, phase)) or {})
        if s is None and len(pj) and code in pj.index:
            s = norm({k: float(pj.at[code, f"{phase}_{k}"] or 0) if pd.notna(pj.at[code, f"{phase}_{k}"]) else 0.0
                      for k in SEX_AGE})
        return s

    def pooled_shares(code):
        if not (len(cb) and code in cb.index):
            return None
        return norm({k: float(cb.at[code, k]) if pd.notna(cb.at[code, k]) else 0.0 for k in SEX_AGE})

    out = []
    for y in years:
        r = {"y": y, "p": dict.fromkeys(SEX_AGE + ["na"], 0.0), "r": dict.fromkeys(SEX_AGE + ["na"], 0.0),
             "nA": 0, "nRep": 0, "nTgt": 0, "nPool": 0, "dp": 0.0, "ndp": 0, "dr": 0.0, "ndr": 0, "reached": 0.0}

        def put(bar, people, sh, r=r):
            if not people:
                return
            if sh:
                for k in SEX_AGE:
                    r[bar][k] += people * sh[k]
            else:
                r[bar]["na"] += people
        rows = [x for _, _, a in _framework_acts(M, y) for x in a["funding"]]
        seen = set()
        for x in rows:
            code = x.get("code")
            if x["fund"] == "cerf":
                if x.get("shared"):
                    continue
                r["nA"] += 1
                reached, stand = x.get("reached"), x.get("planned")
                plan = al.at[code, "individuals_planned"] if code in al.index else None
                plan = float(plan) if plan is not None and pd.notna(plan) and plan > 0 else stand
                put("p", plan, shares(code, "planned"))
                if (code, "planned") in dis:
                    r["dp"] += dis[(code, "planned")]
                    r["ndp"] += 1
                if reached is not None:
                    r["nRep"] += 1
                    r["reached"] += reached
                    put("r", reached, shares(code, "reached"))
                elif stand:
                    r["nTgt"] += 1
                    put("r", stand, shares(code, "planned"))
                # people with disabilities: reached where CERF's report gives the figure, else
                # the people the allocation targets (reached or targeted, figure by figure)
                d_ = dis.get((code, "reached")) if reached is not None else None
                d_ = d_ if d_ is not None else dis.get((code, "planned")) if (reached is not None or stand) else None
                if d_ is not None:
                    r["dr"] += d_
                    r["ndr"] += 1
            else:   # a Country or Regional Fund allocation, once: the people it targets
                if code and code in seen:
                    continue
                seen.add(code)
                if x.get("planned"):
                    r["nPool"] += 1
                    sh = pooled_shares(code)
                    put("p", x["planned"], sh)
                    put("r", x["planned"], sh)
        out.append(r)
    return out


def _sector_cells(d, M, ex, cy, live):
    """{(hazard row, column): [framework names]} and {hazard row: (frameworks with a sector, all)}:
    the current frameworks (the map's default layer) by hazard and by the heat map's columns. A
    framework counts in a column when its latest version budgets something there (the framework
    documents' sector split, every fund), or when one of its activations of the current year had
    project money there: the CERF projects' sectors, and the clusters of the Country and Regional
    Fund projects of the release."""
    secs = {}                                  # (iso3, hazard) -> {column}
    pr = d["plan_rows"]
    pr = pr[pr["lifecycle"].isin(LIVE) & pr["sector"].notna()]
    for (c, h), g in pr.groupby(["country_iso3", "hazard"]):
        for s in g["sector"].unique():
            secs.setdefault((c, h), set()).update(_cols(s))
    cerf = {code: g for code, g in ex["sector"].groupby("application_code")}
    pooled = {code: set(g["cluster"]) for code, g in ex["cbpf_cluster"].groupby("allocation_code")}
    pairs = set(zip(live["country_iso3"], live["hazard"]))
    for iso, f, a in _framework_acts(M, cy):
        if (iso, f["hazard"]) not in pairs or a.get("old"):
            continue
        for x in a["funding"]:
            code = x.get("code")
            if x["fund"] == "cerf" and code in cerf:
                for r in cerf[code].drop_duplicates(["iasc", "sector"]).itertuples():
                    secs.setdefault((iso, f["hazard"]), set()).update(_cols(_cerf_label(r.iasc, r.sector)))
            elif x["fund"] != "cerf" and code in pooled:
                for cl in pooled[code]:
                    secs.setdefault((iso, f["hazard"]), set()).update(_cols(cl))
    cells, rows = {}, {}
    for r in live.sort_values("country_name").itertuples():
        hz = haz(r.hazard)
        n, m = rows.get(hz, (0, 0))
        cols = secs.get((r.country_iso3, r.hazard), set())
        rows[hz] = (n + bool(cols), m + 1)
        for col in cols:
            cells.setdefault((hz, col), []).append((r.country_name, r.hazard))
    return cells, rows


# ---- small HTML helpers --------------------------------------------------------------------
def _matrix(cells, rows):
    """Hazard x sector table, the columns in IASC_COLS' order; a cell's shade from PAL[0] by its
    count, and the frameworks it counts in its tooltip (and its accessible name)."""
    r0, g0, b0 = (int(PAL[0][i:i + 2], 16) for i in (1, 3, 5))
    mx = max([len(v) for v in cells.values()] or [1])
    head = "".join(f"<th class='sx' scope='col'><span>{T(c)}</span></th>" for c, _ in IASC_COLS)
    body = ""
    for h in HAZ_ROWS:
        if h not in rows:
            continue
        tds = ""
        for c, _ in IASC_COLS:
            fws = cells.get((h, c), [])
            v = len(fws)
            a = 0.10 + 0.8 * v / mx if v else 0

            def tip(w, h=h, c=c, fws=fws):
                names = ", ".join(w(n) + (" " + w(hazard_word(hz)) if h == "other" else "") for n, hz in fws)
                return f"{w(h)} · {w(c)}: {names}" if fws else f"{w(h)} · {w(c)}: {w('no framework')}"
            # dark on every shade: white never reaches 4.5:1 on this blue (WCAG 1.4.3)
            tds += (f"<td class='mx' style='background:rgba({r0},{g0},{b0},{a:.2f});color:#1a1a1a'"
                    f"{' tabindex=' + chr(39) + '0' + chr(39) if v else ''} {ATTRC('title', tip)}>{v or ''}</td>")
        n, m = rows[h]
        body += (f"<tr><th class='rh' scope='row'>{T(h)}<span class='muted'> {TF('({a} of {b})', a=n, b=m)}</span></th>"
                 f"{tds}</tr>")
    return (f"<div class='scroll' style='max-height:none'><table class='mxt'><thead><tr><th></th>{head}"
            f"</tr></thead><tbody>{body}</tbody></table></div>")


PLAN_CSS = """
table.mxt { border-collapse:collapse; font-size:12px; background:#fff; }
/* the header row is as tall as the longest sector name may wrap to (two lines of ~175px, French and
   Spanish included), so no name is cut at the top of the box */
table.mxt th.sx { vertical-align:bottom; height:182px; padding:4px 2px 0; font-weight:500; }
table.mxt th.sx span { writing-mode:vertical-rl; transform:rotate(180deg); white-space:normal;
  max-height:175px; display:inline-block; color:#444; line-height:1.15; text-align:left; }
table.mxt th.rh { text-align:left; padding:4px 10px 4px 4px; white-space:nowrap; font-weight:600; }
table.mxt th.rh .muted { font-weight:400; color:#666; font-size:11px; }
table.mxt td.mx { width:44px; min-width:44px; height:30px; text-align:center; border:2px solid #fff;
  font-weight:600; cursor:default; }
table.mxt td.mx:focus-visible { outline:2px solid #1a1a1a; outline-offset:-2px; }
.muted { color:#666; }
ul.nm { margin:4px 0 10px; padding-left:18px; font-size:12.5px; }
ul.nm li { margin:2px 0; }
.notyet { background:#fbfaf6; border:1px dashed #d8d2bf; border-radius:6px; padding:10px 16px; margin:18px 0; }
.notyet h3 { margin:2px 0 6px; font-size:14px; } .notyet li { font-size:13px; margin:3px 0; }
table.kpi td.num, table.kpi th.num { text-align:right; }
.tile .tk { font-weight:600; color:#1a1a1a; display:block; margin-bottom:2px; }
.tile .v2 { font-size:20px; font-weight:700; margin-top:8px; }
.tile .yrsw { display:flex; gap:10px; margin-top:6px; font-size:12px; }
.pfbar { display:flex; flex-wrap:wrap; gap:6px 16px; align-items:center; font-size:13px; margin:4px 0 10px;
  padding:6px 10px; background:#f5f7fa; border-radius:6px; }
.pfbar .pft { font-weight:600; }
.cv { position:relative; height:300px; }
"""


def build_plan(page, d):
    import datetime as dt

    import figure_check                       # the cross-page figure check (build_site)
    import landing
    from dashboards import ORG_COLOR
    ex = _extra()
    cur = d["current"]
    live = cur[cur["lifecycle"].isin(LIVE)]
    n_live = len(live)
    cy = dt.date.today().year
    years = list(range(landing.YEAR_FIRST, cy + 1))
    M = d.get("_map")                         # the map's data (landing.assemble; dashboards.build_all)
    if M is None:
        raise SystemExit("FATAL: the Activities page needs the map's data (d['_map'], set by build_all)")

    # ================================================================== tile: people (the map's figures)
    t = landing.tile_figures(M, {"framework"}, cy)
    est = t["reached"] + t["targeted"] + t["ptargeted"]
    approx = bool(t["n_tgt"] or t["n_ptgt"])
    has_reach = bool(t["n_rep"] or t["n_tgt"] or t["n_ptgt"])

    # ================================================================== partners named in the frameworks
    pt, no_list = _partner_rows(d)
    org_grp = pt.groupby("oid")["grp"].agg(lambda x: x.value_counts().index[0]) if len(pt) else pd.Series(dtype=object)
    n_by = org_grp.value_counts()
    n_orgs = len(org_grp)
    n_fw_pt = n_live - len(no_list)
    eco = [(lab, int(sum(n_by.get(k, 0) for k in ks))) for lab, ks in (
        ("Government", ["government"]), ("UN", ["un"]), ("Red Cross / Red Crescent", ["rcrc_nat", "rcrc_intl"]),
        ("International NGOs", ["ingo"]), ("National / local NGOs", ["nngo"]),
        ("Academic / research", ["academic"]), ("Private sector", ["private"]), ("Donors", ["donor"]),
        ("Other", ["other"]))]
    eco_mix = "<ul class='tb'>" + "".join(f"<li>{T(lab)} {n}</li>" for lab, n in eco if n) + "</ul>"

    def _names(xs):
        return ", ".join(f"{T(str(n))} {T(hazard_word(h))}" for n, h in xs)

    # ================================================================== partners funded: the money-flow rows, by year
    # the Financing page's money flows without the intermediary (review, 2026-11-10): pre-arranged
    # money by who holds it (the agencies of the framework budgets, the pooled funds' grantees:
    # the fund -> recipient links), released money by its final recipient (agency -> recipient
    # links: the sub-grantees, the agency itself for what it implements, the pooled funds'
    # grantees). One id per organisation and category, as the flow chart's boxes
    # an organisation: a UN agency ('un|WFP') or a named partner or grantee ('ingo~ActionAid'). A box
    # that stands for a category (an older snapshot's 'ingo|international NGOs', the 'nr|…'
    # placeholders) carries money but is nobody to count: id None
    node = re.compile(r"^[ap]:([a-z]+)([|~])(.*)$")
    ids, agg = {}, {}
    for r in d.get("_flows") or []:
        if not ((r["m"] == "p" and r["lv"] == "f") or (r["m"] == "r" and r["lv"] == "a")):
            continue
        m = node.match(r["t"])
        if not m or not years[0] <= int(r["y"]) <= cy:
            continue
        cat = m.group(1) if m.group(1) in ORG_COLOR else "oth"
        org = m.group(2) == "~" or cat == "un"
        k = (r["m"], int(r["y"]), r["g"], r["fu"], cat,
             ids.setdefault((cat, m.group(3).casefold()), len(ids)) if org else -1)
        agg[k] = agg.get(k, 0.0) + float(r["v"])
    fl = [[*k[:5], k[5] if k[5] >= 0 else None, round(v)] for k, v in sorted(agg.items()) if v >= 0.5]

    def funded(year=None):
        """Organisations with pre-arranged or released framework money (current and retired
        frameworks; non-framework money left out), in `year` or in any year: by category."""
        by = {}
        for m_, y, g, fu, cat, i, v in fl:
            if g != "a" and cat != "nr" and i is not None and (year is None or y == year):
                by.setdefault(cat, set()).add(i)
        return by
    fund_cy, fund_all = funded(cy), funded()

    def fund_block(by):
        n = sum(len(v) for v in by.values())
        mix = "<ul class='tb'>" + "".join(f"<li>{T(lab)} {len(by[k])}</li>" for k, lab in PARTNER_GROUPS
                                         if k != "nr" and by.get(k)) + "</ul>"
        return n, mix
    n_fcy, mix_fcy = fund_block(fund_cy)
    n_fall, mix_fall = fund_block(fund_all)

    # ================================================================== sectors
    cells, hz_rows = _sector_cells(d, M, ex, cy, live)
    n_sec = sum(n for n, _ in hz_rows.values())
    al = ex["alloc"].copy()
    al["hz"] = al["emergency_type"].fillna("").map(lambda x: haz(x) if x else "other")
    hz_of = dict(zip(al["application_code"], al["hz"]))
    # what each column takes in, as recorded (the framework documents' labels, CERF's sectors,
    # the pooled funds' clusters): the mapping shown under the chart
    raw = {}
    pr = d["plan_rows"]
    pr = pr[pr["lifecycle"].isin(LIVE) & pr["sector"].notna()]
    for s in pr["sector"].unique():
        for col in _cols(s):
            raw.setdefault(col, {}).setdefault("frameworks", set()).add(str(s).strip())
    for r in ex["sector"].drop_duplicates(["iasc", "sector"]).itertuples():
        lab = _cerf_label(r.iasc, r.sector)
        shown = (f"{r.iasc} [CERF sector: {r.sector}]"
                 if isinstance(r.iasc, str) and str(r.sector).strip() != r.iasc.strip() else str(lab).strip())
        for col in _cols(lab):
            raw.setdefault(col, {}).setdefault("CERF (IASC sector)", set()).add(shown)
    for cl in ex["cbpf_cluster"]["cluster"].dropna().unique():
        for col in _cols(cl):
            raw.setdefault(col, {}).setdefault("Country and Regional Funds (cluster)", set()).add(str(cl).strip())

    def _src(lab, xs):
        return f"<span class='muted'>{T(lab + ':')}</span> {html.escape('; '.join(sorted(xs)))}"
    mapping = "".join(
        f"<li><b>{T(c)}</b> ← " + " · ".join(_src(lab, raw[c][lab]) for lab in (
            "frameworks", "CERF (IASC sector)", "Country and Regional Funds (cluster)") if lab in raw[c]) + "</li>"
        for c, _ in IASC_COLS if c in raw)
    # sectors filed elsewhere (agreed in review 2026-10-16): Early Recovery under WASH,
    # coordination and support services under Logistics. Named in the note.
    odd = ex["sector"].assign(b=[str(_cerf_label(i, c)).strip().lower()
                                 for i, c in zip(ex["sector"]["iasc"], ex["sector"]["sector"])])
    al_lab = {r.application_code: f"{r.country_iso3} {hz_of.get(r.application_code, 'other')} {int(r.year)}"
              for r in al.itertuples()}

    def _odd(raws):
        g = odd[odd["b"].isin(raws)].groupby("application_code")["sector_amount"].sum()
        return "; ".join(f"{al_lab.get(c, c)} ({html.escape(c)}, ${v/1e3:,.0f}k)" for c, v in g.items())
    er = _odd({"early recovery"})
    cs = _odd({"coordination and support services", "common services", "humanitarian air services"})
    odd_note = ((TBF("<br><b>Early Recovery</b> projects are counted under WASH: {list}.", list=er) if er else "")
                + (TBF("<br><b>Coordination and support services</b> (common services, humanitarian air "
                       "services) are counted under Logistics: {list}.", list=cs) if cs else ""))

    # ================================================================== cash
    # the CVA file has no allocation code: a row counts when a framework allocation of the same
    # country and emergency type falls within a year of it (the file's year is not always the
    # allocation's: its Ethiopia 2020 rows are 20-RR-ETH-46461, a 2021 allocation). An ad hoc
    # allocation that close to a framework one on the same country and hazard would slip in;
    # none does on 2026-10-14.
    cva = ex["cva"].copy()
    fy = {}
    for r in al.itertuples():
        fy.setdefault((r.country_iso3, r.emergency_type), set()).add(int(r.year))
    keep = [any(abs(int(y) - v) <= 1 for v in fy.get((c, t_), ()))
            for y, c, t_ in zip(cva["year"], cva["country_iso3"], cva["emergency_type"])]
    cva_out = (cva[[not k for k in keep]].groupby(["country_iso3", "year", "emergency_type"])
               ["amount_approved_usd"].sum())
    cva = cva[keep]
    out_txt = "; ".join(f"{c} {int(y)} {t_} (${v/1e6:,.1f}M)" for (c, y, t_), v in cva_out.items())
    cash_rows, cash_note, cash_share, cash_hz, cash_trend = [], T("no CVA records in this snapshot"), "–", [], ""
    if len(cva):
        for y, g in cva.groupby("year"):
            base, c_ = float(g["amount_approved_usd"].sum()), float(g["cva_usd"].fillna(0).sum())
            cash_rows.append({"year": int(y), "cash": c_, "base": base, "other": max(base - c_, 0),
                              "share": c_ / base if base else None,
                              "people": int(g["people_receiving_cash"].fillna(0).sum())})
        base_all = float(cva["amount_approved_usd"].sum())
        cva_all = float(cva["cva_usd"].fillna(0).sum())
        # by hazard: how the team talks about cash (above average in the sudden-onset
        # frameworks, storms and floods; little in cholera) — 2026-10-16 review
        for h, g in cva.assign(hz=cva["emergency_type"].fillna("").map(lambda x: haz(x) if x else "other")).groupby("hz"):
            base, c_ = float(g["amount_approved_usd"].sum()), float(g["cva_usd"].fillna(0).sum())
            cash_hz.append({"hz": h, "cash": c_, "other": max(base - c_, 0),
                            "share": c_ / base if base else None})
        cash_hz.sort(key=lambda r: -(r["share"] or 0))
        last3 = [r for r in cash_rows if r["year"] >= max(r_["year"] for r_ in cash_rows) - 2]
        cash_trend = " · ".join(f"{r['year']}: {r['share']:.0%}" for r in last3 if r["share"] is not None)
        cash_share = f"{cva_all / base_all:.0%}" if base_all else "–"
        cerf_all = float(al["amount_approved"].sum())
        # countries whose framework allocations exceed what the CVA file covers (> $0.5M)
        gap = (al.groupby("country_iso3")["amount_approved"].sum()
               .sub(cva.groupby("country_iso3")["amount_approved_usd"].sum(), fill_value=0))
        gap = sorted(gap[gap > 5e5].index)
        cash_note = TBC(lambda w: html.escape(
            w("{share} of the {base} of framework allocations in the CVA file went as cash or vouchers, to "
              "{people} people. The file covers {base} of the {cerf} approved for the {n} CERF allocations "
              "of framework activations{gap}.").format(
                share=f"{cva_all / base_all:.0%}", base=f"${base_all/1e6:,.0f}M",
                people=f"{int(cva['people_receiving_cash'].fillna(0).sum()):,}",
                cerf=f"${cerf_all/1e6:,.0f}M", n=len(al),
                gap=w(" (not all of {list})").format(list=", ".join(gap)) if gap else "")
            + (w(" Left out, no framework allocation of the country and hazard within a year: {list}.")
               .format(list=out_txt) if out_txt else ""), quote=False))
    # the cash tile: the current year's row of CERF's file, else the latest year it has
    cash_y = next((r for r in reversed(cash_rows) if r["year"] == cy), cash_rows[-1] if cash_rows else None)

    # ================================================================== people
    ps = _people_series(M, ex, years)
    now = ps[-1]
    r_cy = sum(now["r"].values())
    known = sum(now["r"][k] for k in SEX_AGE)
    fem_cy = (now["r"]["women"] + now["r"]["girls"]) / known if known else None
    # the latest complete year, beside a current year that few records cover yet
    prev = ps[-2] if len(ps) > 1 else None
    # the first tile is the map as it opens (current frameworks); the series also counts the year's
    # activations of frameworks since retired or replaced: said under the tiles when the two part
    retired_cy = r_cy - est
    figure_check.KEY["activities"] = {
        "n_live": n_live, "reach_cy": r_cy, "reached": sum(r["reached"] for r in ps),
        "n_rep": sum(r["nRep"] for r in ps), "n_cerf": sum(r["nA"] for r in ps)}
    n_na = sum(1 for r in ps if r["p"]["na"] > 0.5 or r["r"]["na"] > 0.5)

    # ================================================================== GHO
    inc = ex["incl"].assign(source=lambda x: x["source"].map(current_source))
    kpi_rows = ""
    kpi_note = []      # (template, values): the note in each language
    s25 = inc[(inc["year"] == 2025) & (inc["source"] == "cerf-workbook-hnrp-2025")]
    s26 = inc[(inc["year"] == 2026) & (inc["source"] == "cerf-workbook-fcdo-bc") & (inc["plan_type"] == "GHO")]
    upd = pd.to_datetime(pd.concat([s25, s26])["updated"], errors="coerce").max() if "updated" in inc else pd.NaT

    def yn(s, col):
        t_, f, na = int((s[col] == True).sum()), int((s[col] == False).sum()), int(s[col].isna().sum())
        return t_, f, na

    def cell(t_, na, n):
        if na == n:
            return f"<td class='num muted'>{T('not assessed')}</td>"
        return f"<td class='num'>{t_}" + (f" <span class='muted'>{TF('({n} blank)', n=na)}</span>" if na else "") + "</td>"
    if len(s25):
        n = len(s25)
        ex_y = int((s25["exposure_aa_shocks"] == "Yes").sum())
        ex_l = int((s25["exposure_aa_shocks"] == "Limited").sum())
        kpi_rows += (f"<tr><td>2025</td><td>{T('review of the 2025 HNRPs')}</td>"
                     f"<td class='num'>{n}</td><td class='num'>{TF('{y} yes · {l} limited', y=ex_y, l=ex_l)}</td>"
                     + cell(yn(s25, "aa_feasible")[0], yn(s25, "aa_feasible")[2], n)
                     + cell(yn(s25, "aa_prearranged")[0], yn(s25, "aa_prearranged")[2], n)
                     + cell(yn(s25, "has_framework")[0], yn(s25, "has_framework")[2], n) + "</tr>")
    if len(s26):
        n = len(s26)
        kpi_rows += (f"<tr><td>2026</td><td>{T('GHO 2026 country list')}</td><td class='num'>{n}</td>"
                     + cell(0, n, n) + cell(0, n, n) + cell(0, n, n)
                     + cell(yn(s26, "has_framework")[0], yn(s26, "has_framework")[2], n) + "</tr>")
        blank = s26.loc[s26["has_framework"].isna(), "country_iso3"].tolist()
        if blank:
            lv = {}
            for r in live.itertuples():
                lv.setdefault(r.country_iso3, []).append((r.hazard, LIFE_LABEL.get(r.lifecycle, r.lifecycle)))

            def blank_txt(w, blank=blank, lv=lv):
                return "; ".join(
                    w("{c} (tracking database: {fw})").format(
                        c=c, fw=", ".join(f"{w(h)} {w(st)}" for h, st in lv[c]) if c in lv
                        else w("no current framework")) for c in blank)
            kpi_note.append(("Blank 'framework' cells for 2026: {list}. ", {"list": blank_txt}))
        jg = inc[(inc["year"] == 2026) & (inc["source"] == "aa-workbook-gho-2026")]
        clash = sorted(set(s26["country_iso3"]) & set(jg.loc[jg["in_gho"] == False, "country_iso3"]))
        if clash:
            kpi_note.append((("A second GHO 2026 list in the database marks {list} as not in the GHO while "
                              "the list above includes it; not reconciled. "), {"list": ", ".join(clash)}))
    if len(s25):
        na_f = s25.loc[s25["aa_feasible"].isna(), "country_iso3"].tolist()
        if na_f:
            kpi_note.append(("2025 'AA feasible' is blank for {list}. ", {"list": ", ".join(na_f)}))

    # ================================================================== page
    map_note = TB(
        "Columns are the eight clusters of the IASC's guidance on cluster simplification (2026), in the "
        "order of its Annex 5, then Other. Food Security takes in agriculture, food assistance and "
        "livelihoods; Logistics and Telecommunications takes in emergency telecommunications and "
        "coordination and support services; Protection takes in child protection, gender-based violence "
        "and mine action; Shelter, Land and Site Coordination takes in shelter, non-food items and camp "
        "coordination and camp management; Water, Sanitation and Hygiene takes in early recovery (agreed "
        "in review 2026-10-16). Other holds multi-purpose cash (CERF's 'Multi-Sector') and labels that "
        "name no cluster (early warning messaging, community engagement, disaster risk reduction). A "
        "combined label ('Health &amp; Nutrition') counts in both columns. 'To be determined' is left out.")
    cash_how = TB(
        "Computed inside CERF's cash-and-voucher file: cash and voucher amount over the approved "
        "amount of the same rows, by the file's year. The file has no allocation code: a row counts when a "
        "CERF allocation of a framework activation for the same country and emergency type falls within a "
        "year of it (the file's years do not always match the allocation year). The rest is 'other "
        "modalities' (in-kind goods and services together — the data do not separate in-kind).")
    ppl_how = TB(
        "Each year counts the framework activations of that year, as the map does. A CERF allocation "
        "counts once: the people CERF reports reached, or, until a report is in, the people it plans to "
        "reach (targeted). A Country or Regional Fund allocation counts the people it targets in both "
        "bars: those funds report no people reached here. People planned are each allocation's own plan. "
        "The split by sex and age is the allocation's own (CERF's reports); where that is not in yet, the "
        "shares of its projects' figures are applied to the allocation's figure. Women and men are adults, "
        "girls and boys children. People with disabilities is a separate count that overlaps the others: "
        "CERF allocations only, the people reached where CERF's report gives the figure and the people "
        "targeted otherwise; the applications of the current year are not all in. The trend line is a second-order polynomial fitted to the complete years.")
    par_how = TB(
        "The <a href='dash-funding.html'>Financing</a> page's money flows without the step in between, year "
        "by year. Pre-arranged money is recorded down to the UN agency of the framework budget or the "
        "grantee of the Country or Regional Fund: who an agency sub-grants to is known once money is "
        "released. Released money is shown by its final recipient: the sub-grantees CERF's agencies "
        "report, the agency itself for what it implements, and the grantees of the Country and Regional "
        "Funds. Pre-arranged money is a stock for each year, never added over years. An organisation "
        "counts once a year, whatever the number of frameworks; recipients not recorded yet are in the "
        "money charts and cannot be counted. Frameworks since retired count in the years they were in "
        "place. The trend lines are second-order polynomials fitted to the complete years.")
    gho_how = TBC(lambda w: w(
        "2025: the review of the 2025 HNRPs; exposure is recorded as 'yes' or 'limited' only. 2026: only "
        "whether a framework exists was recorded; 'not assessed' = no field in the source.") + " " + html.escape(
        "".join(w(tt).format(**{k: (v(w) if callable(v) else v) for k, v in vals.items()}) for tt, vals in kpi_note)))
    gho_upd = (TF("Entered by hand from the AA team's tracking sheets, last on {d}. It does not change when "
                  "the Global Humanitarian Overview's page changes.", d=str(upd.date()))
               if pd.notna(upd) else
               T("Entered by hand from the AA team's tracking sheets. It does not change when the Global "
                 "Humanitarian Overview's page changes."))

    def tk(name):     # a tile's name, in bold above its line
        return f"<span class='tk'>{T(name)}</span>"
    reach_v = (("~" if approx else "") + landing._people(est)) if has_reach else "—"
    cash_tile = (f"<div class='tile'><div class='v'>{cash_y['share']:.0%}</div><div class='l'>{tk('Cash')}"
                 + TF("of the CERF money released by framework activations in {year} went as cash or vouchers "
                      "({cash} of {base} in CERF's cash records)", year=cash_y["year"],
                      cash=f"${cash_y['cash']/1e6:,.1f}M", base=f"${cash_y['base']/1e6:,.1f}M")
                 + "</div></div>" if cash_y and cash_y["share"] is not None else
                 f"<div class='tile'><div class='v'>–</div><div class='l'>{tk('Cash')}{cash_note}</div></div>")
    dis_v = f"{round(now['dr']):,}" if now["ndr"] else "—"
    dis_prev = (TF("{year}: {n} ({a} of {b} CERF allocations)", year=prev["y"], n=f"{round(prev['dr']):,}",
                   a=prev["ndr"], b=prev["nA"]) if prev and prev["ndr"] else "")
    panels = f"""
<div class='tiles'>
 <div class='tile'><div class='v'>{landing._tofixed(t["covered"] / 1e6, 1) + "M" if t["n_fw"] else "—"}</div><div class='l'>{tk("People")}{TF("people covered now by the {n} current frameworks", n=t["n_fw"])}</div>
  <div class='v2'>{reach_v}</div><div class='l'>{TF("people reached or targeted with the {year} releases", year=cy)}{" — " + T("estimate") if approx else ""}</div></div>
 <div class='tile'><div class='v'>{n_orgs}</div><div class='l'>{tk("AA ecosystem partners")}{TF("organisations named in the current frameworks ({n} of {m} have a partner list)", n=n_fw_pt, m=n_live)}{eco_mix}</div></div>
 <div class='tile' id='tFund'><div class='v' data-y='cy'>{n_fcy}</div><div class='v' data-y='all' hidden>{n_fall}</div><div class='l'>{tk("Partners funded through OCHA-managed pooled funds")}{T("grantees and sub-grantees of pre-arranged or released framework money")}
  <div class='yrsw' role='group' {ATTR("aria-label", "Years counted")}><label><input type='radio' name='pfy' value='cy' checked> {cy}</label><label><input type='radio' name='pfy' value='all'> {TF("all years, {a}–{b}", a=years[0], b=cy)}</label></div>
  <div data-y='cy'>{mix_fcy}</div><div data-y='all' hidden>{mix_fall}</div></div></div>
 {cash_tile}
 <div class='tile'><div class='v'>{f"{fem_cy:.0%}" if fem_cy is not None else "—"}</div><div class='l'>{tk("Women and girls")}{TF("of the people reached or targeted with the {year} releases", year=cy)}</div></div>
 <div class='tile'><div class='v'>{dis_v}</div><div class='l'>{tk("People with disabilities")}{TF("reached or targeted with the {year} releases ({a} of {b} CERF allocations give a figure so far)", year=cy, a=now["ndr"], b=now["nA"])}{"<br>" + dis_prev if dis_prev else ""}</div></div>
</div>
<details class='note' style='font-size:12px;margin:2px 0 10px'><summary style='cursor:pointer'>{T("What these figures count")}</summary>{TBF("The first tile shows the <a href='index.html'>Map</a>'s own figures as it opens: the current frameworks (active, being updated or in development) and the framework activations of {year}. Non-framework allocations are left out throughout, except where a switch adds them. Partner lists come from the latest version of each framework that has one. No partner list yet: {none}. The money is on the <a href='dash-funding.html'>Financing</a> page; pre-arranged money and the Country and Regional Funds' money are not recorded by modality, so the cash figure is CERF's released money only.", year=cy, none=_names(no_list) or T("none"))}{" " + TF("The women and girls tile, the disabilities tile and the chart of people also count {n} people reached or targeted in {year} by frameworks since retired, which the first tile leaves out.", n=f"{round(retired_cy):,}", year=cy) if abs(retired_cy) >= 0.5 else ""}</details>

<h2>{T("Anticipatory action by sector and hazard")}</h2>
<p class='meta'>{TBF("The number of current frameworks in each sector, by hazard, in {year}: a framework counts where its latest version budgets something in the sector, or where one of its {year} activations paid for projects in it (CERF and the Country and Regional Funds). {n} of the {m} current frameworks have a sector recorded; the row label gives the count per hazard. Hover over a number for the frameworks it counts.", year=cy, n=n_sec, m=n_live)}</p>
<div class='grid'>
 <div class='panel'>
   {_matrix(cells, hz_rows)}
   <div class='note'>{TB("A blank cell means no sector recorded there, which is not the same as no activity: some frameworks give their budget by agency only.")}{odd_note}</div></div>
</div>
<details><summary style='cursor:pointer;font-size:13px'>{T("Sector mapping (labels as recorded → column)")}</summary>
<ul class='nm'>{mapping}</ul>
<p class='note' style='color:#666;font-size:11.5px'>{map_note}</p></details>

<h2>{T("Cash")}</h2>
<div class='grid'>
 <div class='panel'><h3>{T("Share delivered as cash and vouchers, by hazard (CERF money of framework activations)")}</h3>
   <div style='position:relative;height:260px'><canvas id='pl3' style='max-height:none'></canvas></div>
   {f"<p class='meta'>{TF('In total {share}; the last three years: {trend}.', share=cash_share, trend=cash_trend)}</p>" if cash_trend else ""}
   <div class='note'>{cash_note} {cash_how}</div></div>
</div>

<h2>{T("People")}</h2>
<div class='grid'>
 <div class='panel'><h3>{T("People planned and people reached or targeted, by sex and age")}</h3>
   <div class='cv'><canvas id='pp1' style='max-height:none'></canvas></div>
   <div class='note'>{TBF("For each year, the lighter bar on the left is the people planned and the bar on the right the people reached or targeted, for the framework activations of that year (CERF and the Country and Regional Funds). * {year}: to date.", year=cy)}{" " + T("Grey: people whose sex and age no record gives.") if n_na else ""}</div></div>
 <div class='panel'><h3>{T("People with disabilities, planned and reached or targeted")}</h3>
   <div class='cv'><canvas id='pp2' style='max-height:none'></canvas></div>
   <div class='note'>{TB("CERF allocations of framework activations that give the figure; hover over a bar for how many do. The right bar counts the people reached where CERF's report gives the figure, and the people targeted otherwise.")}</div></div>
</div>
<details class='note' style='font-size:12px;margin:2px 0 10px'><summary style='cursor:pointer'>{T("How the people figures are counted")}</summary>{ppl_how}</details>

<h2>{T("Partners")}</h2>
<div class='pfbar' role='group' {ATTR("aria-label", "What the partner charts count")}>
 <span class='pft'>{T("The four charts count:")}</span>
 <label><input type='checkbox' id='pfC' checked> CERF</label>
 <label><input type='checkbox' id='pfP' checked> CBPF</label>
 <label><input type='checkbox' id='pfR' checked> RHPF</label>
 <label {ATTR("title", "AA money allocated without a framework: released, or pre-arranged and not yet released")}><input type='checkbox' id='pfAdh'> {T("Non-framework allocations")}</label>
</div>
<div class='grid'>
 <div class='panel'><h3>{T("Partners with pre-arranged funding, by year")}</h3>
   <div class='cv'><canvas id='pn1' style='max-height:none'></canvas></div></div>
 <div class='panel'><h3>{T("Partners that received released funding, by year")}</h3>
   <div class='cv'><canvas id='pn2' style='max-height:none'></canvas></div></div>
</div>
<div class='grid' style='margin-top:16px'>
 <div class='panel'><h3>{T("Pre-arranged funding by recipient, by year")}</h3>
   <div class='cv'><canvas id='pf1' style='max-height:none'></canvas></div></div>
 <div class='panel'><h3>{T("Released funding by final recipient, by year")}</h3>
   <div class='cv'><canvas id='pf2' style='max-height:none'></canvas></div></div>
</div>
<p class='note' style='color:#666;font-size:11.5px'>{TBF("Unique organisations and money per year, by kind of organisation. * {year}: to date.", year=cy)}</p>
<details class='note' style='font-size:12px;margin:2px 0 10px'><summary style='cursor:pointer'>{T("How the partner figures are counted")}</summary>{par_how}</details>

<h2>{T("AA in the humanitarian plans")}</h2>
<p class='meta'>{TB("Of the countries in the Global Humanitarian Overview, how many face shocks AA can address, and how many have AA feasible, pre-arranged or a framework. One source per year, as recorded in the AA team's tracking sheets.")} {gho_upd}</p>
<div class='scroll' style='max-height:none'><table class='data kpi'><thead><tr><th>{T("year")}</th><th>{T("source")}</th>
<th class='num'>{T("GHO plans")}</th><th class='num'>{T("exposed to shocks AA can address")}</th><th class='num'>{T("AA feasible")}</th>
<th class='num'>{T("AA pre-arranged")}</th><th class='num'>{T("AA framework")}</th></tr></thead><tbody>{kpi_rows}</tbody></table></div>
<p class='note' style='color:#666;font-size:11.5px'>{gho_how}</p>

<div class='notyet'><h3>{T("Not yet measured")}</h3><ul>
 <li>{TB("<b>National ownership score</b> — a design decision for the team (which elements, which weights); the government roles in the partner lists are one possible input.")}</li>
 <li>{TB("<b>Anticipatory activities</b> (most common activities, readiness vs action per activity) — the frameworks' activities are recorded only as their sectors and a short summary per organisation (in each framework's panel on the map), not in categories that can be counted.")}</li>
 <li>{TB("<b>Geographic coverage</b> (admin areas targeted) — not recorded.")}</li>
 <li>{TB("<b>Sex, age and disability of the people covered</b> — the framework documents' targets are not broken down in the database; the charts above use the allocations' figures.")}</li>
 <li>{TB("<b>In-kind vs cash</b> — only the cash and voucher share of CERF's released money is recorded.")}</li>
</ul></div>
<style>{PLAN_CSS}</style>"""

    data = {
        "cy": cy,
        "years": years,
        "cashHz": cash_hz,
        "people": [{"y": r["y"], "p": [round(r["p"][k]) for k in SEX_AGE + ["na"]],
                    "r": [round(r["r"][k]) for k in SEX_AGE + ["na"]],
                    "nA": r["nA"], "nRep": r["nRep"], "nTgt": r["nTgt"], "nPool": r["nPool"],
                    "dp": round(r["dp"]), "ndp": r["ndp"], "dr": round(r["dr"]), "ndr": r["ndr"]} for r in ps],
        "sa": SEX_AGE_COLOR,
        "fl": fl,
        "org": ORG_COLOR,
    }
    js = """
const CY = D.cy, YS = D.years;
const yLab = y => +y === CY ? y + '*' : String(y);
const pc = v=>v==null?'':' · '+Math.round(v*100)+'%';
const num = v=>Math.round(v).toLocaleString('en-US');
const ppl = v => v >= 1e6 ? (v/1e6).toFixed(1) + 'M' : v >= 1e4 ? Math.round(v/1e3) + 'k' : num(v);
// a lighter tint of a colour (a: 1 the colour itself), for the planned bars
const tint = (hex, a) => { const n = parseInt(hex.slice(1), 16), f = c => Math.round(255 - (255 - c) * a);
  return `rgb(${f(n >> 16)},${f((n >> 8) & 255)},${f(n & 255)})`; };
const sum = xs => xs.reduce((a, b) => a + (b || 0), 0);
// a chart of people: whole numbers on the axis, short totals over the bars
function pplChart(id, labels, ds, extra){
  const ch = mkChart(id, 'bar', labels, ds, {count:true, allLabels:true, ...extra,
    plugins:{...(extra && extra.totals ? {stackTotals:{fmt:ppl, horiz:false}} : {})}});
  ch.options.scales.y.ticks.callback = ppl; return ch; }
// one legend entry per name (a name can stand for two datasets: its planned and its reached bar),
// in the colour of the second (the full colour, not the planned bar's tint); a click shows or hides both
function pairLegend(ch){
  ch.options.plugins.legend.labels.filter = (item, data) => data.datasets.map(d => d.label).lastIndexOf(item.text) === item.datasetIndex;
  ch.options.plugins.legend.onClick = (e, item, legend) => { const c = legend.chart;
    const on = !c.isDatasetVisible(item.datasetIndex);
    c.data.datasets.forEach((d, i) => { if(d.label === item.text) c.setDatasetVisibility(i, on); }); c.update(); }; }
function drawPeople(){
  const P = D.people, SA = ['men', 'boys', 'girls', 'women', 'na'];
  const SAL = [tr8('men'), tr8('boys'), tr8('girls'), tr8('women'), tr8('sex and age not recorded')];
  const bars = [['p', tr8('planned'), 0.5], ['r', tr8('reached or targeted'), 1]];
  const ds = bars.flatMap(([k, bar, a]) => SA.map((g, i) => ({label:SAL[i], bar, stack:k, data:P.map(r => r[k][i]),
    backgroundColor: a < 1 ? tint(D.sa[g], a) : D.sa[g]})).filter(d => d.data.some(v => v)));
  const tr = trendSet(YS, P.map(r => sum(r.r)), CY);
  if(tr){ tr.label = tr8('trend, people reached or targeted'); ds.push(tr); }
  const ch = pplChart('pp1', YS.map(yLab), ds, {stacked:true, totals:true, extra:{interaction:{mode:'nearest', intersect:true}}});
  pairLegend(ch);
  const cb = ch.options.plugins.tooltip.callbacks;
  cb.title = items => items[0].dataset.bar ? `${items[0].label} · ${items[0].dataset.bar}` : items[0].label;
  cb.label = c => { const d = c.dataset; if(!d.stack) return ` ${d.label}: ${num(c.parsed.y)}`;
    const tot = sum(c.chart.data.datasets.filter(x => x.stack === d.stack).map(x => x.data[c.dataIndex]));
    return ` ${d.label}: ${num(c.parsed.y)} (${tot ? Math.round(100 * c.parsed.y / tot) : 0}%)`; };
  cb.footer = items => { const d = items[0].dataset; if(!d.stack) return '';
    const r = P[items[0].dataIndex];
    return [tr8('total: {0}', num(sum(r[d.stack]))),
      d.stack === 'r' ? tr8('{0} CERF allocations reported, {1} awaiting a report, {2} Country and Regional Fund allocations', r.nRep, r.nTgt, r.nPool)
                      : tr8('{0} CERF allocations, {1} Country and Regional Fund allocations', r.nA, r.nPool)]; };
  ch.update();
  const c2 = pplChart('pp2', YS.map(yLab), [
    {label:tr8('planned'), k:'ndp', data:P.map(r => r.dp), backgroundColor:tint(PAL[0], 0.45)},
    {label:tr8('reached or targeted'), k:'ndr', data:P.map(r => r.dr), backgroundColor:PAL[0]}], {});
  c2.options.plugins.tooltip.callbacks.label = c => { const r = P[c.dataIndex];
    return ` ${c.dataset.label}: ${num(c.parsed.y)} · ` + tr8('{0} of {1} CERF allocations give the figure', r[c.dataset.k], r.nA); };
  c2.update();
}
// the partner charts: rows [m (p pre-arranged, r released), year, layer (c current, r retired, a
// non-framework), fund (c CERF, p CBPF, r RHPF), kind of organisation, organisation id, US$]
function drawPartners(){
  const adh = document.getElementById('pfAdh').checked;
  const fu = {c:document.getElementById('pfC').checked, p:document.getElementById('pfP').checked, r:document.getElementById('pfR').checked};
  const G = [['un', tr8('UN')], ['nngo', tr8('National / local NGOs')], ['ingo', tr8('International NGOs')],
             ['rc', tr8('Red Cross / Red Crescent')], ['gov', tr8('Government')], ['oth', tr8('Other')], ['nr', tr8('Not recorded yet')]];
  const draw = (id, m, count) => {
    const rows = D.fl.filter(r => r[0] === m && (adh || r[2] !== 'a') && fu[r[3]] && !(count && (r[4] === 'nr' || r[5] == null)));
    const at = (y, k) => rows.filter(r => r[1] === y && r[4] === k);
    const ds = G.map(([k, lab]) => ({label:lab, backgroundColor:D.org[k],
      data:YS.map(y => count ? new Set(at(y, k).map(r => r[5])).size : sum(at(y, k).map(r => r[6])))})).filter(d => d.data.some(v => v));
    const tr = trendSet(YS, YS.map((y, i) => sum(ds.map(d => d.data[i]))), CY);
    if(tr){ tr.label = tr8('trend'); ds.push(tr); }
    mkChart(id, 'bar', YS.map(yLab), ds, {stacked:true, totals:true, count, allLabels:true}); };
  draw('pn1', 'p', true); draw('pn2', 'r', true); draw('pf1', 'p', false); draw('pf2', 'r', false);
}
function drawPlan(){   // again on a language switch: the labels are translated as drawn
  if(D.cashHz.length) mkChart('pl3','bar',D.cashHz.map(r=>tr8(r.hz)+pc(r.share)),[
    {label:'cash and vouchers',data:D.cashHz.map(r=>r.cash),backgroundColor:PAL[2]},
    {label:'other modalities',data:D.cashHz.map(r=>r.other),backgroundColor:'#c8ccd2'}],
    {stacked:true,totals:true,allLabels:true,extra:{indexAxis:'y'}});
  drawPeople(); drawPartners();
}
drawPlan();
document.addEventListener('aalang', drawPlan);
['pfAdh', 'pfC', 'pfP', 'pfR'].forEach(id => document.getElementById(id).addEventListener('change', drawPartners));
// the funded-partners tile: this year, or every year
document.querySelectorAll("input[name='pfy']").forEach(el => el.addEventListener('change', () => {
  document.querySelectorAll('#tFund [data-y]').forEach(x => { x.hidden = x.dataset.y !== el.value; }); }));"""
    # no card under the page's box (policy_text: what makes an effective anticipatory activity, the
    # AA team's wording): "we don't need the 'who does what for whom and where'" (review, 2026-11-10)
    _dash_page(page, "pillar-plan.html", "Activities",   # the 'Plan' pillar, renamed (owner, 2026-10-27)
               "", panels, json.dumps(data, default=str), js)
