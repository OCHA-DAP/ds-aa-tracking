"""The Plan page (pillar-plan.html): who does what, for whom and where.

Split out of dashboards.py on 2026-09-30 and reworked the same day around partners: the
money views (budget by agency / sector) live on the Financing page. This page counts
organisations, sectors, people and humanitarian plans. Shared helpers stay in dashboards;
the few tables `_fetch` does not load are read by `_extra()` below."""

import html
import json
import re
import unicodedata

import pandas as pd
from dashboards import EXCLUDED_EVENT_TYPES, LIFE_LABEL, PAL, _dash_page, _st, haz

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
NATIONAL = ("government", "nngo", "rcrc_nat")          # national / local actors
GLOBAL_TYPES = ("un", "ingo", "rcrc_intl", "donor")    # de-duplicated across countries
# the same UN agency under its French / Spanish acronym (normalised, lower-case)
UN_ALIAS = {"pam": "wfp", "pma": "wfp", "oms": "who", "oim": "iom", "hcr": "unhcr",
            "acnur": "unhcr", "pnud": "undp", "ops": "paho", "opsoms": "paho",
            "pahowho": "paho", "unw": "unwomen"}
# roles as the framework documents give them, in priority order (an organisation with
# several roles is counted once, under the first that applies)
ROLES = [("implementing", "implementing"), ("sub_grantee", "sub-grantee"),
         ("government_counterpart", "government counterpart"), ("technical", "technical"),
         ("coordination", "coordination"), ("funding", "funding")]
# who can be named-vs-funded: organisations that deliver (not UN agencies, donors,
# academia, or private firms, which are contracted — e.g. mobile-money providers)
DELIVERY_ROLES = {"implementing", "sub_grantee"}
DELIVERY_TYPES = ("government", "nngo", "rcrc_nat", "rcrc_intl", "ingo", "other")

# ---- sectors: framework split labels and CERF sector names -> one bucket (visible on page)
SECTOR_BUCKETS = [
    ("Food security & agriculture", ["food security", "food assistance", "food aid", "agriculture",
                                     "food security & livelihoods", "food security & agriculture",
                                     "agriculture & livelihoods"]),
    ("Nutrition", ["nutrition"]),
    ("Health", ["health", "srh", "health (srh)", "sexual and reproductive health"]),
    ("WASH", ["wash", "water, sanitation and hygiene"]),
    ("Protection", ["protection", "child protection", "gbv", "gender-based violence",
                    "protection (gbv)"]),
    ("Shelter & NFI", ["shelter/nfi", "shelter", "shelter and non-food items"]),
    ("Multi-purpose cash", ["multi-purpose cash", "multi-sector/mpca"]),
    ("CCCM", ["cccm", "camp coordination and camp management"]),
    ("Education", ["education"]),
    ("Logistics & common services", ["logistics", "common services", "humanitarian air services"]),
    ("Early warning & community engagement", ["early warning messaging",
                                              "multi-sector (community engagement)"]),
    ("Early recovery", ["early recovery"]),
]
SECTOR_COMBINED = {"health & nutrition": ["Health", "Nutrition"],
                   "food security (window 1) / nutrition (window 2)":
                       ["Food security & agriculture", "Nutrition"]}
SECTOR_SKIP = {"to be determined"}
_SECTOR = {raw: [b] for b, raws in SECTOR_BUCKETS for raw in raws} | SECTOR_COMBINED


def _buckets(label):
    k = str(label).strip().lower()
    if not k or k in SECTOR_SKIP or k == "nan":
        return []
    return _SECTOR.get(k, ["Other"])


# ---- the tables `_fetch` does not load ----------------------------------------------------
def _extra():
    """One engine, one read per table, each tolerant of an older snapshot (empty frame)."""
    import ocha_stratus as stratus
    e = stratus.get_engine(stage="dev")
    excl = ", ".join(f"'{t}'" for t in EXCLUDED_EVENT_TYPES)
    q = {
        "alloc": ("""SELECT application_code, year, country_iso3,
                            lower(trim(emergency_type)) AS emergency_type, amount_approved,
                            individuals_planned, individuals_reached
                     FROM aa.cerf_allocation WHERE aa_keyword""",
                  ["application_code", "year", "country_iso3", "emergency_type",
                   "amount_approved", "individuals_planned", "individuals_reached"]),
        "alloc_fw": ("""SELECT DISTINCT allocation_code, country_iso3, hazard
                        FROM aa.activation_funding
                        WHERE fund_code = 'cerf' AND allocation_code IS NOT NULL
                          AND event_type NOT IN (""" + excl + ")",
                     ["allocation_code", "country_iso3", "hazard"]),
        "sector": ("""SELECT p.application_code, s.cerf_sector_name AS sector, s.sector_amount
                      FROM aa.cerf_project_sector s
                      JOIN aa.cerf_project p USING (project_code)
                      JOIN aa.cerf_allocation c ON c.application_code = p.application_code
                      WHERE c.aa_keyword AND s.sector_amount > 0""",
                   ["application_code", "sector", "sector_amount"]),
        # d["subgrant_aa"] without the partner acronym, which the name matching uses
        "subgrant": ("""SELECT project_code, application_code, agency, year, country_iso3,
                               partner_name, partner_acronym, partner_type, localization,
                               subgrant_usd
                        FROM aa.cerf_subgrant WHERE is_aa AND subgrant_usd IS NOT NULL""",
                     ["project_code", "application_code", "agency", "year", "country_iso3",
                      "partner_name", "partner_acronym", "partner_type", "localization",
                      "subgrant_usd"]),
        "cva": ("""SELECT year, country_iso3, amount_approved_usd, cva_usd, people_receiving_cash
                   FROM aa.cerf_cva_history""",
                ["year", "country_iso3", "amount_approved_usd", "cva_usd",
                 "people_receiving_cash"]),
        "people": ("""SELECT p.application_code, p.phase, p.disaggregation, p.grp, p.value
                      FROM aa.cerf_application_people p
                      JOIN aa.cerf_allocation c USING (application_code)
                      WHERE c.aa_keyword""",
                   ["application_code", "phase", "disaggregation", "grp", "value"]),
        "incl": ("""SELECT country_iso3, year, source, plan_type, in_gho, exposure_aa_shocks,
                           aa_feasible, aa_prearranged, has_framework
                    FROM aa.plan_inclusion""",
                 ["country_iso3", "year", "source", "plan_type", "in_gho",
                  "exposure_aa_shocks", "aa_feasible", "aa_prearranged", "has_framework"]),
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


def _same_org(name, acr, s_name, s_acr):
    """Loose match of a named partner to a CERF sub-grantee (same framework)."""
    na, nb, aa, ab = _n(name), _n(s_name), _n(acr), _n(s_acr)
    if len(aa) >= 3 and aa in (ab, nb):
        return True
    if len(ab) >= 3 and ab == na:
        return True
    if na and na == nb:
        return True
    if min(len(na), len(nb)) >= 5 and (na in nb or nb in na):
        return True
    word = html.unescape(str(name)).lower().strip()
    return len(na) >= 3 and bool(re.search(r"\b" + re.escape(word) + r"\b",
                                           html.unescape(str(s_name)).lower()))


def _partners(d, ex):
    """Partner rows of the live frameworks (latest version with partner rows), org ids,
    the CERF AA sub-grants mapped to frameworks, and the named-vs-funded comparison."""
    cur = d["current"]
    live = cur[cur["lifecycle"].isin(LIVE)]
    pt = d["partners"].copy()
    pt["version"] = pt["version"].astype(str)
    pt = pt.merge(live[["country_iso3", "hazard"]], on=["country_iso3", "hazard"])
    # latest partner list per framework: dated versions rank above undated labels such as
    # 'development' (a plain string max would put 'development' above every date)
    _vk = pt["version"].astype(str).map(lambda v: (v[:1].isdigit(), v))
    lv = (pt.assign(_vk=_vk).sort_values("_vk").groupby(["country_iso3", "hazard"])["version"]
          .last().rename("lv").reset_index())
    pt = pt.merge(lv, on=["country_iso3", "hazard"])
    pt = pt[pt["version"] == pt["lv"]].reset_index(drop=True)
    pt["grp"] = [_group(t, n, a) for t, n, a in zip(pt["org_type"], pt["name"], pt["acronym"])]
    pt["roles"] = pt["roles"].apply(lambda r: list(r) if isinstance(r, (list, tuple)) else [])
    pt["oid"] = _org_ids(pt) if len(pt) else []

    # CERF AA sub-grants -> framework: the activation record of the allocation, else the
    # allocation's emergency type (the CERF record) as the hazard
    sg = (ex["subgrant"] if len(ex["subgrant"]) else d["subgrant_aa"]).copy()
    if "partner_acronym" not in sg:
        sg["partner_acronym"] = None
    tbd = (sg["partner_type"].eq("TBD")
           | sg["partner_name"].fillna("").str.contains(r"\bTBD\b|to be determined",
                                                        case=False, regex=True)
           | sg["partner_name"].isna())
    sg["tbd"] = tbd
    af = {(r.allocation_code, r.country_iso3): r.hazard for r in ex["alloc_fw"].itertuples()}
    et = dict(zip(ex["alloc"]["application_code"], ex["alloc"]["emergency_type"]))
    sg["hazard"] = [af.get((a, c), et.get(a)) for a, c in zip(sg["application_code"],
                                                               sg["country_iso3"])]
    sg["skey"] = sg["country_iso3"] + "|" + sg["partner_name"].map(_n)

    rows = []   # one per live framework with partner rows or sub-grants
    for fw in live.itertuples():
        c, h = fw.country_iso3, fw.hazard
        p = pt[(pt["country_iso3"] == c) & (pt["hazard"] == h)]
        s = sg[(sg["country_iso3"] == c) & (sg["hazard"] == h) & ~sg["tbd"]]
        s1 = s.drop_duplicates("skey")
        orgs = p.groupby("oid").agg(grp=("grp", "first"), name=("name", "first"),
                                    acronym=("acronym", "first"),
                                    roles=("roles", lambda x: sorted({r for rs in x for r in rs})))
        deliv = orgs[orgs["grp"].isin(DELIVERY_TYPES)
                     & orgs["roles"].apply(lambda r: bool(DELIVERY_ROLES & set(r)))]
        funded, unfunded = [], []
        if len(s1) and len(p):
            for o in deliv.itertuples():
                hit = any(_same_org(o.name, o.acronym, x.partner_name, x.partner_acronym)
                          for x in s1.itertuples())
                (funded if hit else unfunded).append(o.name)
            not_named = [x.partner_name for x in s1.itertuples()
                         if not any(_same_org(o.name, o.acronym, x.partner_name, x.partner_acronym)
                                    for o in orgs.itertuples())]
        else:
            not_named = []
        n_by = orgs["grp"].value_counts()
        rows.append({
            "country_iso3": c, "hazard": h, "country_name": fw.country_name,
            "lifecycle": fw.lifecycle, "version": p["version"].iloc[0] if len(p) else None,
            "un_impl": int(((orgs["grp"] == "un")
                            & orgs["roles"].apply(lambda r: "implementing" in r)).sum()),
            "government": int(n_by.get("government", 0)), "nngo": int(n_by.get("nngo", 0)),
            "rcrc": int(n_by.get("rcrc_nat", 0) + n_by.get("rcrc_intl", 0)),
            "ingo": int(n_by.get("ingo", 0)),
            "other": int(sum(n_by.get(k, 0) for k in ("academic", "private", "donor", "other"))),
            "n_orgs": len(orgs), "n_sub": len(s1), "has_sub": bool(len(s1)) and bool(len(p)),
            "funded": funded, "unfunded": unfunded, "not_named": not_named})
    return pt, sg, pd.DataFrame(rows)


def _portfolio_orgs(pt):
    """Distinct organisations across the live frameworks: type (most frequent) and
    primary role (first of ROLES any of its rows has)."""
    if not len(pt):
        return pd.DataFrame(columns=["grp", "role"])
    order = [k for k, _ in ROLES]

    def role(rs):
        s = {r for x in rs for r in x}
        return next((k for k in order if k in s), "other")
    return pt.groupby("oid").agg(grp=("grp", lambda x: x.value_counts().index[0]),
                                 role=("roles", role))


# ---- small HTML helpers --------------------------------------------------------------------
def _matrix(counts, cols, row_note, title_unit):
    """Hazard x sector table; cell shade from PAL[0] by count."""
    r0, g0, b0 = (int(PAL[0][i:i + 2], 16) for i in (1, 3, 5))
    mx = max([v for v in counts.values()] or [1])
    head = "".join(f"<th class='sx'><span>{html.escape(c)}</span></th>" for c in cols)
    body = ""
    for h in HAZ_ROWS:
        if h not in row_note:
            continue
        cells = ""
        for c in cols:
            v = counts.get((h, c), 0)
            a = 0.10 + 0.8 * v / mx if v else 0
            fg = "#fff" if a > 0.55 else "#1a1a1a"
            cells += (f"<td class='mx' style='background:rgba({r0},{g0},{b0},{a:.2f});color:{fg}'"
                      f" title='{h} · {html.escape(c)}: {v} {title_unit}'>{v or ''}</td>")
        body += f"<tr><th class='rh'>{h}<span class='muted'> {row_note[h]}</span></th>{cells}</tr>"
    return (f"<div class='scroll' style='max-height:none'><table class='mxt'><thead><tr><th></th>{head}"
            f"</tr></thead><tbody>{body}</tbody></table></div>")


PLAN_CSS = """
table.mxt { border-collapse:collapse; font-size:12px; background:#fff; }
table.mxt th.sx { vertical-align:bottom; height:130px; padding:0 2px; font-weight:500; }
table.mxt th.sx span { writing-mode:vertical-rl; transform:rotate(180deg); white-space:nowrap;
  display:inline-block; color:#444; }
table.mxt th.rh { text-align:left; padding:4px 10px 4px 4px; white-space:nowrap; font-weight:600; }
table.mxt th.rh .muted { font-weight:400; color:#888; font-size:11px; }
table.mxt td.mx { width:34px; min-width:34px; height:28px; text-align:center; border:1px solid #fff;
  font-weight:600; }
.muted { color:#888; }
ul.nm { margin:4px 0 10px; padding-left:18px; font-size:12.5px; }
ul.nm li { margin:2px 0; }
.notyet { background:#fbfaf6; border:1px dashed #d8d2bf; border-radius:6px; padding:10px 16px; margin:18px 0; }
.notyet h3 { margin:2px 0 6px; font-size:14px; } .notyet li { font-size:13px; margin:3px 0; }
table.kpi td.num, table.kpi th.num { text-align:right; }
"""


def build_plan(page, d):
    ex = _extra()
    cur = d["current"]
    live = cur[cur["lifecycle"].isin(LIVE)]
    n_live = len(live)

    # ================================================================== partners
    pt, sg, fw = _partners(d, ex)
    orgs = _portfolio_orgs(pt)
    n_by = orgs["grp"].value_counts()
    n_orgs = len(orgs)
    n_nat = int(sum(n_by.get(k, 0) for k in NATIONAL))
    un_impl = pt[(pt["grp"] == "un") & pt["roles"].apply(lambda r: "implementing" in r)]
    n_un = un_impl["oid"].nunique()
    n_ingo = int(n_by.get("ingo", 0))
    n_fw_pt = int(fw["version"].notna().sum()) if len(fw) else 0
    sgd = sg[~sg["tbd"]]
    n_funded_all = sgd["skey"].nunique()
    cmp_ = fw[fw["has_sub"]] if len(fw) else fw
    n_named = int(cmp_["funded"].str.len().sum() + cmp_["unfunded"].str.len().sum()) if len(cmp_) else 0
    n_named_f = int(cmp_["funded"].str.len().sum()) if len(cmp_) else 0
    n_not_named = int(cmp_["not_named"].str.len().sum()) if len(cmp_) else 0
    sg_years = (f"{int(sg['year'].min())}–{int(sg['year'].max())}" if len(sg) else "")

    # chart 1: organisations by type and primary role
    types = []
    for k, label in TYPE_GROUPS:
        g = orgs[orgs["grp"] == k]
        if len(g):
            types.append({"label": label, "n": g["role"].value_counts().to_dict()})
    # chart 2: CERF AA sub-grant money by recipient, per year (localisation)
    loc_rows = []
    for y, g in sg.groupby("year"):
        loc = g["localization"].fillna("TBD")
        lo = g[loc == "Local"]
        r = {"year": int(y),
             "gov": float(lo.loc[lo["partner_type"] == "GOV", "subgrant_usd"].sum()),
             "nngo": float(lo.loc[lo["partner_type"] == "NNGO", "subgrant_usd"].sum()),
             "rc": float(lo.loc[lo["partner_type"].isin(["RedC", "REDC"]), "subgrant_usd"].sum()),
             "intl": float(g.loc[loc == "INGO", "subgrant_usd"].sum()),
             "tbd": float(g.loc[~loc.isin(["Local", "INGO"]), "subgrant_usd"].sum())}
        r["local_other"] = float(lo["subgrant_usd"].sum()) - r["gov"] - r["nngo"] - r["rc"]
        det = r["gov"] + r["nngo"] + r["rc"] + r["local_other"] + r["intl"]
        r["share"] = (det - r["intl"]) / det if det else None
        loc_rows.append(r)
    loc_all = sum(r["gov"] + r["nngo"] + r["rc"] + r["local_other"] for r in loc_rows)
    det_all = loc_all + sum(r["intl"] for r in loc_rows)
    loc_share = f"{loc_all / det_all:.0%}" if det_all else "–"

    # per-framework table
    cov = dict(zip(zip(d["covered"]["country_iso3"], d["covered"]["hazard"]),
                   d["covered"]["people_covered"]))
    trs = ""
    for r in fw.sort_values(["country_name", "hazard"]).itertuples():
        link = f"fw-{r.country_iso3.lower()}-{r.hazard}.html"
        v = cov.get((r.country_iso3, r.hazard))
        has_v = isinstance(r.version, str)
        ver = (html.escape(r.version) if has_v
               else "<span class='muted'>no partner list yet</span>")
        latest = str(live.loc[(live["country_iso3"] == r.country_iso3)
                              & (live["hazard"] == r.hazard), "latest_version"].iloc[0])
        stale = (f" <span class='muted'>(latest version: {html.escape(latest)})</span>"
                 if has_v and r.version != latest else "")
        n_d = len(r.funded) + len(r.unfunded)
        named = (f"{len(r.funded)} of {n_d}" if r.has_sub and n_d
                 else "<span class='muted'>none named</span>" if r.has_sub
                 else "<span class='muted'>–</span>")
        def z(x, has_v=has_v):
            return x if (x or has_v) else ""
        trs += (f"<tr><td><a href='{link}'>{html.escape(r.country_name)}</a> — "
                f"{r.hazard.replace('_', ' ')}</td>"
                f"<td>{_st(LIFE_LABEL.get(r.lifecycle, r.lifecycle))}</td>"
                f"<td>{ver}{stale}</td>"
                f"<td class='num'>{z(r.un_impl)}</td><td class='num'>{z(r.government)}</td>"
                f"<td class='num'>{z(r.nngo)}</td><td class='num'>{z(r.rcrc)}</td>"
                f"<td class='num'>{z(r.ingo)}</td><td class='num'>{z(r.other)}</td>"
                f"<td class='num'>{r.n_sub or ''}</td><td class='num'>{named}</td>"
                f"<td class='num'>{f'{int(v):,}' if v and pd.notna(v) else ''}</td></tr>")
    # named delivery partners without a CERF AA sub-grant, per framework
    unf = ""
    for r in cmp_.sort_values(["country_name", "hazard"]).itertuples() if len(cmp_) else []:
        if r.unfunded:
            items = ", ".join(html.escape(str(x)) for x in sorted(r.unfunded))
            unf += (f"<li><b>{html.escape(r.country_name)} — {r.hazard}</b> "
                    f"<span class='muted'>({len(r.unfunded)} of "
                    f"{len(r.funded) + len(r.unfunded)})</span>: {items}</li>")

    # ================================================================== sectors
    pr = d["plan_rows"]
    pr = pr[pr["lifecycle"].isin(LIVE) & pr["sector"].notna()]
    plan_cnt, plan_raw = {}, {}
    for (c, h), g in pr.groupby(["country_iso3", "hazard"]):
        bs = set()
        for s in g["sector"].unique():
            for b in _buckets(s):
                bs.add(b)
                plan_raw.setdefault(b, set()).add(str(s).strip())
        for b in bs:
            plan_cnt[(haz(h), b)] = plan_cnt.get((haz(h), b), 0) + 1
    fw_sec = pr.drop_duplicates(["country_iso3", "hazard"])
    n_sec = len(fw_sec)
    live_h = live["hazard"].map(haz).value_counts()
    sec_h = fw_sec["hazard"].map(haz).value_counts()
    plan_note = {h: f"{int(sec_h.get(h, 0))} of {int(live_h.get(h, 0))}"
                 for h in HAZ_ROWS if live_h.get(h, 0)}

    al = ex["alloc"].copy()
    al["hz"] = al["emergency_type"].fillna("").map(lambda x: haz(x) if x else "other")
    hz_of = dict(zip(al["application_code"], al["hz"]))
    cerf_cnt, cerf_raw = {}, {}
    for code, g in ex["sector"].groupby("application_code"):
        bs = set()
        for s in g["sector"].unique():
            for b in _buckets(s):
                bs.add(b)
                cerf_raw.setdefault(b, set()).add(str(s).strip())
        h = hz_of.get(code, "other")
        for b in bs:
            cerf_cnt[(h, b)] = cerf_cnt.get((h, b), 0) + 1
    al_h = al[al["application_code"].isin(ex["sector"]["application_code"])]["hz"].value_counts()
    cerf_note = {h: f"{int(al_h.get(h, 0))}" for h in HAZ_ROWS if al_h.get(h, 0)}
    tot = {}
    for (h, b), v in list(plan_cnt.items()) + list(cerf_cnt.items()):
        tot[b] = tot.get(b, 0) + v
    cols = sorted(tot, key=lambda b: (-tot[b], b))
    mapping = "".join(
        f"<li><b>{html.escape(b)}</b> ← "
        f"{html.escape('; '.join(sorted(plan_raw.get(b, set()) | cerf_raw.get(b, set()))))}</li>"
        for b in cols)

    # ================================================================== cash
    cva = ex["cva"].copy()
    cash_rows, cash_note = [], "no CVA records in this snapshot"
    if len(cva):
        for y, g in cva.groupby("year"):
            base, c_ = float(g["amount_approved_usd"].sum()), float(g["cva_usd"].fillna(0).sum())
            cash_rows.append({"year": int(y), "cash": c_, "other": max(base - c_, 0),
                              "share": c_ / base if base else None,
                              "people": int(g["people_receiving_cash"].fillna(0).sum())})
        base_all = float(cva["amount_approved_usd"].sum())
        cva_all = float(cva["cva_usd"].fillna(0).sum())
        cerf_all = float(al["amount_approved"].sum())
        # countries whose CERF AA approvals exceed what the CVA file covers (> $0.5M)
        gap = (al.groupby("country_iso3")["amount_approved"].sum()
               .sub(cva.groupby("country_iso3")["amount_approved_usd"].sum(), fill_value=0))
        gap = sorted(gap[gap > 5e5].index)
        cash_note = (f"{cva_all / base_all:.0%} of the ${base_all/1e6:,.0f}M in the CVA file went as "
                     f"cash or vouchers, to {int(cva['people_receiving_cash'].fillna(0).sum()):,} "
                     f"people. The file covers ${base_all/1e6:,.0f}M of the ${cerf_all/1e6:,.0f}M "
                     f"approved for the {len(al)} CERF AA allocations"
                     + (f" (not all of {', '.join(gap)})." if gap else "."))

    # ================================================================== people
    rep = al[(al["individuals_reached"].fillna(0) > 0) & (al["individuals_planned"].fillna(0) > 0)]
    rep = rep.sort_values(["year", "country_iso3", "application_code"])
    ppl = [{"label": f"{r.country_iso3} {int(r.year)} · {str(r.application_code).split('-')[-1]}",
            "planned": int(r.individuals_planned), "reached": int(r.individuals_reached)}
           for r in rep.itertuples()]
    n_over = int((rep["individuals_reached"] >= rep["individuals_planned"]).sum())
    pe = ex["people"]
    both = set(pe.loc[(pe["phase"] == "planned") & (pe["disaggregation"] == "sex_age"), "application_code"]) \
        & set(pe.loc[(pe["phase"] == "reached") & (pe["disaggregation"] == "sex_age"), "application_code"])
    pb = pe[pe["application_code"].isin(both)]
    groups = [("women", "sex_age", "women"), ("girls", "sex_age", "girls"),
              ("men", "sex_age", "men"), ("boys", "sex_age", "boys"),
              ("persons with disabilities", "disability", "total")]
    dis = {"labels": [g[0] for g in groups]}
    for ph in ("planned", "reached"):
        x = pb[pb["phase"] == ph]
        dis[ph] = [int(x.loc[(x["disaggregation"] == dg) & (x["grp"] == gr), "value"].sum())
                   for _, dg, gr in groups]
    fem = {ph: (dis[ph][0] + dis[ph][1]) / max(sum(dis[ph][:4]), 1) for ph in ("planned", "reached")}

    # ================================================================== GHO
    inc = ex["incl"]
    kpi_rows = ""
    kpi_note = ""
    s25 = inc[(inc["year"] == 2025) & (inc["source"] == "yakubu-hnrp-2025")]
    s26 = inc[(inc["year"] == 2026) & (inc["source"] == "yakubu-fcdo-bc") & (inc["plan_type"] == "GHO")]

    def yn(s, col):
        t, f, na = int((s[col] == True).sum()), int((s[col] == False).sum()), int(s[col].isna().sum())
        return t, f, na

    def cell(t, na, n):
        if na == n:
            return "<td class='num muted'>not assessed</td>"
        return f"<td class='num'>{t}" + (f" <span class='muted'>({na} blank)</span>" if na else "") + "</td>"
    if len(s25):
        n = len(s25)
        ex_y = int((s25["exposure_aa_shocks"] == "Yes").sum())
        ex_l = int((s25["exposure_aa_shocks"] == "Limited").sum())
        kpi_rows += (f"<tr><td>2025</td><td>review of the 2025 HNRPs</td>"
                     f"<td class='num'>{n}</td><td class='num'>{ex_y} yes · {ex_l} limited</td>"
                     + cell(yn(s25, "aa_feasible")[0], yn(s25, "aa_feasible")[2], n)
                     + cell(yn(s25, "aa_prearranged")[0], yn(s25, "aa_prearranged")[2], n)
                     + cell(yn(s25, "has_framework")[0], yn(s25, "has_framework")[2], n) + "</tr>")
    if len(s26):
        n = len(s26)
        kpi_rows += (f"<tr><td>2026</td><td>GHO 2026 country list (FCDO business case)</td><td class='num'>{n}</td>"
                     + cell(0, n, n) + cell(0, n, n) + cell(0, n, n)
                     + cell(yn(s26, "has_framework")[0], yn(s26, "has_framework")[2], n) + "</tr>")
        blank = s26.loc[s26["has_framework"].isna(), "country_iso3"].tolist()
        if blank:
            lv = {}
            for r in live.itertuples():
                lv.setdefault(r.country_iso3, []).append(
                    f"{r.hazard} {LIFE_LABEL.get(r.lifecycle, r.lifecycle)}")
            lv = {k: ", ".join(v) for k, v in lv.items()}
            kpi_note += ("Blank 'framework' cells for 2026: " + "; ".join(
                f"{c} (tracking database: {lv.get(c, 'no live framework')})" for c in blank) + ". ")
        jg = inc[(inc["year"] == 2026) & (inc["source"] == "julia-gho-2026")]
        clash = sorted(set(s26["country_iso3"]) & set(jg.loc[jg["in_gho"] == False, "country_iso3"]))
        if clash:
            kpi_note += (f"A second GHO 2026 list in the database marks {', '.join(clash)} as not in "
                         "the GHO while the FCDO list includes it; not reconciled. ")
    if len(s25):
        na_f = s25.loc[s25["aa_feasible"].isna(), "country_iso3"].tolist()
        if na_f:
            kpi_note += f"2025 'AA feasible' is blank for {', '.join(na_f)}. "

    # ================================================================== page
    hz_list = ", ".join(sorted(set(fw.loc[fw["version"].isna(), "country_name"] + " "
                                   + fw.loc[fw["version"].isna(), "hazard"]))) if len(fw) else ""
    panels = f"""
<h2>Partners</h2>
<p class='meta'>Organisations named in the framework documents (partner lists of the latest
version that has one, {n_fw_pt} of {n_live} live frameworks) and organisations funded through
CERF AA sub-grants ({sg_years}). No framework money here: the budgets are on the
<a href='dash-funding.html'>Financing</a> page.</p>
<div class='tiles'>
 <div class='tile'><div class='v'>{n_orgs}</div><div class='l'>organisations named in {n_fw_pt} live frameworks</div></div>
 <div class='tile'><div class='v'>{n_nat}</div><div class='l'>national / local actors: {int(n_by.get('government', 0))} government,<br>{int(n_by.get('nngo', 0))} national NGOs, {int(n_by.get('rcrc_nat', 0))} national RC/RC societies</div></div>
 <div class='tile'><div class='v'>{n_un}</div><div class='l'>UN agencies named as implementers</div></div>
 <div class='tile'><div class='v'>{n_ingo}</div><div class='l'>international NGOs</div></div>
 <div class='tile'><div class='v'>{n_funded_all}</div><div class='l'>organisations with a CERF AA sub-grant, {sg_years}</div></div>
 <div class='tile'><div class='v'>{n_named_f} <span style='font-size:14px;font-weight:400'>of {n_named}</span></div><div class='l'>named delivery partners funded by a CERF AA sub-grant<br>({len(cmp_)} frameworks with sub-grant records)</div></div>
 <div class='tile'><div class='v'>{loc_share}</div><div class='l'>of CERF AA sub-grant money to national / local actors<br>(partner determined, {sg_years})</div></div>
</div>
<div class='grid'>
 <div class='panel'><h3>Organisations named in the frameworks, by type and main role</h3>
   <div style='position:relative;height:330px'><canvas id='pl1' style='max-height:none'></canvas></div>
   <div class='note'>Each organisation counted once, under its first role in this order: implementing,
   sub-grantee, government counterpart, technical, coordination, funding. Organisations are merged
   on a shared acronym or name (French / Spanish UN acronyms mapped: PAM/PMA→WFP, OMS→WHO, OIM→IOM,
   HCR/ACNUR→UNHCR, PNUD→UNDP, OPS→PAHO) — within the country for national actors, across countries for UN agencies, INGOs,
   donors and the international Red Cross / Red Crescent (IFRC, partner national societies,
   Climate Centre). Approximate: spellings with no shared acronym stay apart.</div></div>
 <div class='panel'><h3>CERF AA sub-grants by recipient, per year</h3>
   <div style='position:relative;height:330px'><canvas id='pl2' style='max-height:none'></canvas></div>
   <div class='note'>From the CERF sub-grant records of AA allocations (aa.cerf_subgrant), CERF's own
   <i>localization</i> field: 'Local' = government, national NGOs and national Red Cross / Red Crescent
   societies. The share in the label is local money over money whose partner is determined; 'not yet
   determined' (TBD) is shown but left out of the share. Agencies' direct spending is not in these bars.</div></div>
</div>
<h3 style='margin:20px 0 6px'>By framework</h3>
<section><input class='filter' placeholder='filter…' oninput='filt(this)'>
<div class='scroll'><table class='data'><thead><tr><th>framework</th><th>status</th><th>partner list (version)</th>
<th>UN implementers</th><th>government</th><th>national / local NGOs</th><th>Red Cross / Red Crescent</th>
<th>international NGOs</th><th>other</th><th>CERF AA sub-grantees</th><th>named delivery partners with a sub-grant</th>
<th>people covered</th></tr></thead><tbody>{trs}</tbody></table></div></section>
<p class='note' style='color:#666;font-size:11.5px'>Counts of distinct organisations in the partner list.
<b>CERF AA sub-grantees</b>: distinct funded partners of the framework's CERF AA allocations (all activations;
an allocation belongs to the framework its activation record names, else to the hazard CERF gives it).
<b>Named delivery partners</b>: government bodies, NGOs, Red Cross / Red Crescent and other organisations the
document gives an implementing or sub-grantee role (UN agencies, donors, academia and private firms such as
mobile-money providers excluded), matched on name or acronym to those sub-grantees — only where the framework
has sub-grant records. The partner list can be from a newer version than the allocations.
{n_not_named} sub-grantees of these frameworks are not named in the partner list.
Frameworks with no partner list yet: {html.escape(hz_list) or 'none'}. People covered: latest figure per framework.</p>
<details><summary style='cursor:pointer;font-size:13px'>Named delivery partners with no CERF AA sub-grant ({n_named - n_named_f})</summary>
<ul class='nm'>{unf}</ul>
<p class='note' style='color:#666;font-size:11.5px'>No CERF AA sub-grant recorded for the framework's
allocations. They may be funded by the agencies' own resources, pooled funds or bilateral money, which
this database does not trace to partners.</p></details>

<h2>Where the portfolio has experience</h2>
<p class='meta'>Hazard × sector. Left: what the plans foresee — live frameworks whose latest version
budgets something in the sector ({n_sec} of {n_live} live frameworks have a sector split; the rest are
agency-only or have no split recorded, so a blank cell is not 'no experience'). Right: what was
delivered — CERF AA allocations with project money in the sector.</p>
<div class='grid'>
 <div class='panel'><h3>Planned: frameworks with budget in the sector</h3>
   {_matrix(plan_cnt, cols, {h: f'({v})' for h, v in plan_note.items()}, 'frameworks')}
   <div class='note'>Row label: frameworks with a sector split of all live frameworks for the hazard.
   From the framework documents' agency × sector split (aa.v_window_funding_split, latest version).</div></div>
 <div class='panel'><h3>Delivered: CERF AA allocations with money in the sector</h3>
   {_matrix(cerf_cnt, cols, {h: f'({v})' for h, v in cerf_note.items()}, 'allocations')}
   <div class='note'>Row label: CERF AA allocations with sector records for the hazard (CERF emergency
   type). From the CERF project sectors of AA allocations (aa.cerf_project_sector).</div></div>
</div>
<details><summary style='cursor:pointer;font-size:13px'>Sector mapping (labels as recorded → bucket)</summary>
<ul class='nm'>{mapping}</ul>
<p class='note' style='color:#666;font-size:11.5px'>A combined label (e.g. 'Health &amp; Nutrition') counts in
both buckets. 'To be determined' is left out.</p></details>

<h2>Cash</h2>
<div class='grid'>
 <div class='panel'><h3>CERF AA money delivered as cash and vouchers</h3>
   <div style='position:relative;height:300px'><canvas id='pl3' style='max-height:none'></canvas></div>
   <div class='note'>{cash_note} Computed inside the CERF CVA file (aa.cerf_cva_history): cash and voucher
   amount over the approved amount of the same rows, by the file's year. Not joined to the CERF project
   records: the file's years do not always match the allocation year. The rest is 'other modalities'
   (in-kind goods and services together — the data do not separate in-kind).</div></div>
</div>

<h2>People</h2>
<div class='tiles'>
 <div class='tile'><div class='v'>{len(rep)} <span style='font-size:14px;font-weight:400'>of {len(al)}</span></div><div class='l'>CERF AA allocations with people reached reported</div></div>
 <div class='tile'><div class='v'>{n_over}</div><div class='l'>of them reached at least as many people as planned</div></div>
 <div class='tile'><div class='v'>{fem['planned']:.0%} → {fem['reached']:.0%}</div><div class='l'>women and girls, share of people planned → reached<br>({len(both)} allocations with both)</div></div>
</div>
<div class='grid'>
 <div class='panel'><h3>People planned and reached, per CERF AA allocation</h3>
   <div style='position:relative;height:{max(300, 26 * len(ppl) + 60)}px'><canvas id='pl4' style='max-height:none'></canvas></div>
   <div class='note'>From the CERF allocation records (individuals planned / reached). Only allocations whose
   people reached is reported; a zero or blank means not yet reported, not nobody reached.
   Recent figures may be interim.</div></div>
 <div class='panel'><h3>By sex, age and disability</h3>
   <div style='position:relative;height:300px'><canvas id='pl5' style='max-height:none'></canvas></div>
   <div class='note'>Summed over the {len(both)} CERF AA allocations with both a planned and a reached
   breakdown (aa.cerf_application_people; CERF GMS reports 2020–2024). Women / men are adults, girls / boys
   children. Persons with disabilities is a separate count, overlapping the others.</div></div>
</div>

<h2>AA in the humanitarian plans</h2>
<p class='meta'>Of the countries in the Global Humanitarian Overview, how many face shocks AA can address,
and how many have AA feasible, pre-arranged or a framework. One source per year, as recorded in
aa.plan_inclusion.</p>
<div class='scroll' style='max-height:none'><table class='data kpi'><thead><tr><th>year</th><th>source</th>
<th class='num'>GHO plans</th><th class='num'>exposed to shocks AA can address</th><th class='num'>AA feasible</th>
<th class='num'>AA pre-arranged</th><th class='num'>AA framework</th></tr></thead><tbody>{kpi_rows}</tbody></table></div>
<p class='note' style='color:#666;font-size:11.5px'>2025: the review of the 2025 HNRPs; exposure is recorded as
'yes' or 'limited' only. 2026: only whether a framework exists was recorded; 'not assessed' = no field in
the source. {html.escape(kpi_note)}</p>

<div class='notyet'><h3>Not yet measured</h3><ul>
 <li><b>National ownership score</b> — a design decision for the team (which elements, which weights);
   the government roles above are one possible input.</li>
 <li><b>Anticipatory activities</b> (most common activities, readiness vs action per activity) — the
   frameworks' activities are not recorded as structured data, only their sectors.</li>
 <li><b>Geographic coverage</b> (admin areas targeted) — not recorded.</li>
 <li><b>Gender, age and disability</b> beyond the CERF breakdown above — the framework documents' targets
   are not disaggregated in the database.</li>
 <li><b>In-kind vs cash</b> — only the cash and voucher share is recorded.</li>
 <li><b>Action plans</b> — the framework documents are linked from each framework page (table above).</li>
</ul></div>
<style>{PLAN_CSS}</style>"""

    data = {
        "roles": [{"key": k, "label": lab} for k, lab in ROLES],
        "types": types,
        "loc": loc_rows,
        "cash": cash_rows,
        "ppl": ppl,
        "dis": dis,
    }
    js = """
mkChart('pl1','bar',D.types.map(t=>t.label),
  D.roles.map((r,i)=>({label:r.label,data:D.types.map(t=>t.n[r.key]||0),backgroundColor:PAL[i%PAL.length]})),
  {stacked:true,count:true,totals:true,allLabels:true,extra:{indexAxis:'y'}});
const pc = v=>v==null?'':' · '+Math.round(v*100)+'%';
mkChart('pl2','bar',D.loc.map(r=>r.year+pc(r.share)),[
  {label:'government',data:D.loc.map(r=>r.gov),backgroundColor:PAL[0]},
  {label:'national / local NGOs',data:D.loc.map(r=>r.nngo),backgroundColor:PAL[2]},
  {label:'national Red Cross / Red Crescent',data:D.loc.map(r=>r.rc),backgroundColor:PAL[4]},
  {label:'international NGOs',data:D.loc.map(r=>r.intl),backgroundColor:PAL[1]},
  {label:'not yet determined',data:D.loc.map(r=>r.tbd),backgroundColor:'#c8ccd2'}],
  {stacked:true,totals:true,allLabels:true});
if(D.cash.length) mkChart('pl3','bar',D.cash.map(r=>r.year+pc(r.share)),[
  {label:'cash and vouchers',data:D.cash.map(r=>r.cash),backgroundColor:PAL[2]},
  {label:'other modalities',data:D.cash.map(r=>r.other),backgroundColor:'#c8ccd2'}],
  {stacked:true,totals:true,allLabels:true});
mkChart('pl4','bar',D.ppl.map(r=>r.label),[
  {label:'planned',data:D.ppl.map(r=>r.planned),backgroundColor:PAL[0]},
  {label:'reached',data:D.ppl.map(r=>r.reached),backgroundColor:PAL[2]}],
  {count:true,allLabels:true,extra:{indexAxis:'y'}});
mkChart('pl5','bar',D.dis.labels,[
  {label:'planned',data:D.dis.planned,backgroundColor:PAL[0]},
  {label:'reached',data:D.dis.reached,backgroundColor:PAL[2]}],{count:true,allLabels:true});
const num = v=>Number(v).toLocaleString('en-US');
[['pl4','x'],['pl5','y']].forEach(([id,ax])=>{ const ch=document.getElementById(id)._chart;
  if(!ch) return; ch.options.scales[ax].ticks.callback=num;
  ch.options.plugins.tooltip.callbacks.label=c=>` ${c.dataset.label}: ${num(ax==='x'?c.parsed.x:c.parsed.y)}`; ch.update(); });"""
    _dash_page(page, "pillar-plan.html", "Plan",
               "<b>Who does what, for whom and where</b> — the organisations named in the "
               "frameworks and those funded through CERF AA sub-grants, the hazards and sectors "
               "where the portfolio has planned or delivered, the people planned and reached, and "
               "how far AA appears in the humanitarian plans. Figures follow the latest version of "
               "each live framework (active, being updated or in development); the money is on the "
               "<a href='dash-funding.html'>Financing</a> page.",
               panels, json.dumps(data, default=str), js)
