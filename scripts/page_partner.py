"""The partner profile (pillar-partners.html): a sub-tab of Activities, as historical activations
is of Model (owner, 2026-11-17, on a colleague's request: "Can we add something where we can
select a partner and get key stats: Partner, in what framework, how much money pre-arranged, how
much money released, how much cofinancing, sectors?"; D235).

One organisation at a time, from what the other pages already show:
  * frameworks   the current frameworks whose partner list names it (page_plan._partner_rows:
                 each framework's latest version that has a list), with its roles;
  * money        the Financing page's money-flow rows (dashboards._money_flows, d["_flows"]):
                 pre-arranged = the fund -> agency / grantee links into it (a stock per year, never
                 added over years); released = the fund -> agency / grantee links into it, and,
                 apart, what it received through another organisation (a sub-grant) and what it
                 passed on. What an agency implements itself and a grantee's run-on link to
                 itself are the same money, not more;
  * co-financing the Financing page's co-financing now, by co-financer (cofinancing_now). A line
                 that names several organisations for one amount is listed, never added to a total;
  * sectors      the sectors the current frameworks' budgets give it, and the sectors of its
                 projects paid by framework releases (CERF's project sectors, the Country and
                 Regional Funds' project clusters).

One organisation is one money-flow box (one spelling and one kind across CERF and the pooled
funds), joined to its names in the partner lists: a UN agency by its acronym in any of the site's
languages (OMS, PAM, OPS/OMS), another organisation by its name, or by its acronym in a country
where it has money. An organisation only in a partner list, or only a co-financer, has a profile
too. The matching is approximate: a name spelt differently in a framework document and in a fund's
records gives two entries."""

import html
import json
import re
import unicodedata

import pandas as pd
from dashboards import (
    AGENCY_ALIAS,
    CERF_FW_CODES_SQL,
    ORG_COLOR,
    _dash_page,
    _fu,
    _is_un,
    _un_short,
    hazard_word,
)
from page_plan import (
    IASC_COLS,
    LIVE,
    UN_ALIAS,
    _cerf_label,
    _cols,
    _n,
    _partner_rows,
)
from site_i18n import ATTR, TB, TBF, T

PAGE = "pillar-partners.html"
# the kinds of organisation, in the Activities page's order and colours (dashboards.ORG_COLOR)
KINDS = [("un", "UN"), ("nngo", "National / local NGOs"), ("ingo", "International NGOs"),
         ("rc", "Red Cross / Red Crescent"), ("gov", "Government"), ("oth", "Other")]
# a partner list's display group (page_plan._group) -> the kind
GRP_KIND = {"government": "gov", "nngo": "nngo", "rcrc_nat": "rc", "rcrc_intl": "rc", "un": "un", "ingo": "ingo"}
# the roles a partner list records in words of its own (anything else is a note, not shown)
ROLES = {"implementing": "implementing", "coordination": "coordination", "technical": "technical support",
         "funding": "funding", "government_counterpart": "government counterpart", "sub_grantee": "sub-grantee"}
ORG_TYPE = {"UN": "un", "INGO": "ingo", "NNGO": "nngo", "Red Cross": "rcrc"}   # older rows' spellings


def _fold(s):
    """One key per name: entities decoded; case, accents, spaces and punctuation ignored (the
    page's script folds what is typed the same way)."""
    t = unicodedata.normalize("NFD", html.unescape(str(s)))
    return re.sub(r"[^0-9a-z]+", "", "".join(ch for ch in t if not unicodedata.combining(ch)).casefold())


def _un_name(name, acronym):
    """The money-flow name of a UN agency as a partner list writes it ('OMS', 'OPS/OMS', 'Programme
    alimentaire mondial'): the whole name or acronym first, then each part of the acronym, each in
    the site's other languages too (page_plan.UN_ALIAS). None when it names none of them."""
    for x in (acronym, name):
        if isinstance(x, str) and x.strip():
            s = _un_short(x) or _un_short(UN_ALIAS.get(_n(x), ""))
            if s:
                return s
    if isinstance(acronym, str):
        for tok in re.split(r"[^0-9A-Za-z]+", acronym):
            s = _un_short(UN_ALIAS.get(_n(tok), tok)) if tok else None
            if s:
                return s
    return None


def _released_sectors():
    """US$ of project budgets by organisation and sector for the projects framework releases paid:
    CERF's project sectors by agency, and the Country and Regional Funds' project clusters by
    grantee (only the projects listed for the release where the allocation paid for other things
    too, D192). Rows (fund code, organisation, sector label, usd); empty on a snapshot without the
    tables."""
    import ocha_stratus as stratus
    e = stratus.get_engine(stage="dev")
    out = []
    try:
        c = pd.read_sql(
            """SELECT p.agency_short_name AS org, s.cerf_sector_name AS sector, s.iasc_sector_name AS iasc,
                      sum(s.sector_amount) AS usd
               FROM aa.cerf_project_sector s JOIN aa.cerf_project p USING (project_code)
               WHERE p.application_code IN (""" + CERF_FW_CODES_SQL + """) AND s.sector_amount > 0
               GROUP BY 1, 2, 3""", e)
        out += [("cerf", r.org, _cerf_label(r.iasc, r.sector), float(r.usd)) for r in c.itertuples()]
    except Exception as exc:  # noqa: BLE001 — an older snapshot lacks the table
        print(f"  partner profile: CERF project sectors unavailable ({exc.__class__.__name__})")
    try:
        has_afp = pd.read_sql("SELECT to_regclass('aa.activation_funding_project') AS r", e)["r"].iloc[0] is not None
        listed = ("""
                 AND (p.chf_project_code IN (SELECT x.project_code FROM aa.activation_funding_project x
                                             WHERE x.allocation_code = f.allocation_code)
                      OR NOT EXISTS (SELECT 1 FROM aa.activation_funding_project x
                                     WHERE x.allocation_code = f.allocation_code))""" if has_afp else "")
        p = pd.read_sql(
            """SELECT f.fund_code, p.org_name AS org, c.cluster AS sector,
                      sum(coalesce(c.budget_by_cluster, p.budget * c.cluster_percentage / 100.0)) AS usd
               FROM (SELECT allocation_code, min(fund_code) AS fund_code FROM aa.activation_funding
                     WHERE fund_code <> 'cerf' AND event_type = 'framework_aa'
                       AND allocation_code ~ '^cbpf-[0-9]+-[0-9]+$' GROUP BY 1) f
               JOIN aa.cbpf_project p
                 ON 'cbpf-' || p.pooled_fund_id || '-' || p.allocation_type_id = f.allocation_code
               JOIN aa.cbpf_project_cluster c ON c.chf_project_code = p.chf_project_code
               WHERE true""" + listed + " GROUP BY 1, 2, 3", e)
        out += [(r.fund_code, r.org, r.sector, float(r.usd)) for r in p.itertuples() if pd.notna(r.usd) and r.usd > 0]
    except Exception as exc:  # noqa: BLE001
        print(f"  partner profile: pooled-fund project clusters unavailable ({exc.__class__.__name__})")
    return out


def assemble(d):
    """The page's data (see the module's text): orgs, fw (the frameworks and non-framework money
    the rows name), rows [organisation, kind of row, year, framework, layer, fund, US$] and tot
    [view, year, layer, fund, US$] (all the money of the view, recorded recipient or not)."""
    import datetime as dt

    import landing
    cy = dt.date.today().year
    years = list(range(landing.YEAR_FIRST, cy + 1))
    cur = d["current"]
    names = d.get("_flow_names") or {}
    cname = dict(zip(cur["country_iso3"], cur["country_name"]))
    life = dict(zip(zip(cur["country_iso3"], cur["hazard"]), cur["lifecycle"]))

    pt, _none = _partner_rows(d)        # the partner lists of the current frameworks
    listed = set(zip(pt["country_iso3"], pt["hazard"])) if len(pt) else set()
    ent, order = {}, []

    def entity(key, name, kind):
        if key not in ent:
            ent[key] = {"n": name, "k": kind, "l": {}, "c": [], "sb": {}, "sr": {}, "al": set()}
            order.append(key)
        return key

    fws, fw_i = [], {}

    def fw(c, h, g="c"):
        """Index of a framework (country + hazard), of a country's money with no single framework
        (h ''), or of non-framework money of a country and hazard (layer g 'a'). Money of the
        retired layer (g 'r') under a pair that is live today is an earlier framework's, which a
        distinct new one replaced (Somalia drought, dashboards.old_versions): an entry of its own, 'e'."""
        lc = None if g == "a" or not h else life.get((c, h))
        earlier = g == "r" and lc in LIVE
        k = (c or "", h or "", g == "a", earlier)
        if k not in fw_i:
            en = names.get("c:" + c) or cname.get(c) or c
            fw_i[k] = len(fws)
            fws.append({"c": c or "", "n": en if c else "", "h": hazard_word(h) if h else "", "a": g == "a",
                        "lc": "retired" if earlier else lc, "e": earlier,
                        "pl": (c, h) in listed and not earlier and g != "a",
                        "p": f"fw-{c.lower()}-{h}.html" if lc is not None and not earlier else None})
        return fw_i[k]

    # ---- money: the flow rows. One organisation per box: a UN agency ('un|WFP') or a named partner
    # or grantee ('ingo~ActionAid'); the 'nr|…' boxes and an older snapshot's category boxes are no one
    node = re.compile(r"^[ap]:([a-z]+)([|~])(.*)$")

    def money_key(n):
        m = node.match(n)
        if not m or m.group(1) == "nr" or not (m.group(2) == "~" or m.group(1) == "un"):
            return None
        cat = m.group(1) if m.group(1) in ORG_COLOR else "oth"
        return entity(f"{cat}|{m.group(3).casefold()}", m.group(3), cat)

    agg, tot = {}, {}
    for r in d.get("_flows") or []:
        y = int(r["y"])
        if r["lv"] == "d" or not years[0] <= y <= cy:
            continue
        v, f = float(r["v"]), fw(r.get("c"), r.get("h"), r["g"])
        if r["lv"] == "f":
            tk = (r["m"], y, r["g"], r["fu"])
            tot[tk] = tot.get(tk, 0.0) + v
            k = money_key(r["t"])
            if k:
                key = (k, "P" if r["m"] == "p" else "R", y, f, r["g"], r["fu"])
                agg[key] = agg.get(key, 0.0) + v
        elif r["m"] == "r":         # agency / grantee -> final recipient
            ks, kt = money_key(r["s"]), money_key(r["t"])
            if ks == kt:            # what it implements itself: the money it received, not more
                continue
            for k, t in ((kt, "S"), (ks, "O")):
                if k:
                    key = (k, t, y, f, r["g"], r["fu"])
                    agg[key] = agg.get(key, 0.0) + v
    by_name = {}            # folded name -> organisation, the money boxes first
    for k in order:
        by_name.setdefault(_fold(ent[k]["n"]), k)
    in_country = {}         # organisation -> the countries its money rows name
    for (k, _t, _y, f, _g, _f2) in agg:
        in_country.setdefault(k, set()).add(fws[f]["c"])
    # A framework budget names an organisation by its acronym ('NRCS'), a fund's records by its
    # name ('Nigeria Red Cross Society'): two boxes in the money flows, one organisation. Where a
    # partner list of the country gives both the acronym and (nearly) the name, the acronym's box
    # joins the name's
    import difflib
    merged = []
    for r in (pt.itertuples() if len(pt) else ()):
        if not (isinstance(r.acronym, str) and len(_fold(r.acronym)) >= 3):
            continue
        ka, n = by_name.get(_fold(r.acronym)), _fold(r.name)
        if ka is None or ent[ka]["k"] == "un" or r.country_iso3 not in in_country.get(ka, ()):
            continue
        near = [(difflib.SequenceMatcher(None, n, f_).ratio(), kb) for f_, kb in by_name.items()
                if kb != ka and kb in in_country and ent[kb]["k"] != "un" and r.country_iso3 in in_country[kb]
                and len(f_) >= 8]
        near = [x for x in near if x[0] >= 0.9]
        if near:
            kb = max(near)[1]
            for key in [key for key in agg if key[0] == ka]:
                agg[(kb, *key[1:])] = agg.get((kb, *key[1:]), 0.0) + agg.pop(key)
            in_country[kb] |= in_country.pop(ka)
            ent[kb]["al"].add(ent[ka]["n"])
            by_name[_fold(ent[ka]["n"])] = kb
            merged.append((ent[ka]["n"], ent[kb]["n"]))
            order.remove(ka)
            del ent[ka]
    # ... or where the acronym is the initials of one organisation's name in the same country
    # ('HARAF': Hope And Rural Aid Foundation; 'BCHR': Benevolence Coalition for Humanitarian Relief)
    def initials(name):
        ws = re.findall(r"[A-Za-zÀ-ÿ]+", name)
        small = {"and", "of", "for", "the", "in", "et", "de", "du", "des", "la", "le", "pour", "y", "para"}
        return {"".join(w[0] for w in ws).upper(), "".join(w[0] for w in ws if w.lower() not in small).upper()}
    for ka in [k for k in order if k in in_country and re.fullmatch(r"[A-Z]{4,8}", ent[k]["n"]) and ent[k]["k"] != "un"]:
        cand = [kb for kb in order if kb != ka and kb in in_country and ent[kb]["k"] != "un"
                and in_country[kb] & in_country[ka] and " " in ent[kb]["n"] and ent[ka]["n"] in initials(ent[kb]["n"])]
        if len(cand) == 1:
            kb = cand[0]
            for key in [key for key in agg if key[0] == ka]:
                agg[(kb, *key[1:])] = agg.get((kb, *key[1:]), 0.0) + agg.pop(key)
            in_country[kb] |= in_country.pop(ka)
            ent[kb]["al"].add(ent[ka]["n"])
            by_name[_fold(ent[ka]["n"])] = kb
            merged.append((ent[ka]["n"], ent[kb]["n"]))
            order.remove(ka)
            del ent[ka]
    if merged:
        print("  partner profile: a budget's acronym and a fund's name read as one organisation: "
              + "; ".join(f"{a} = {b}" for a, b in merged))

    # ---- the partner lists of the current frameworks
    n_listed = len(listed)
    acr = {}                # folded acronym -> organisation
    in_fw, in_c = {}, {}    # the names and acronyms of a framework's / a country's lists -> organisation
    for _oid, g in (pt.groupby("oid", sort=False) if len(pt) else ()):
        rows = list(g.itertuples())
        key = None
        if any(r.grp == "un" or ORG_TYPE.get(r.org_type) == "un" for r in rows):
            short = next((s for s in (_un_name(r.name, r.acronym) for r in rows) if s), None)
            if short:
                key = entity(f"un|{short.casefold()}", short, "un")
        if key is None:
            # its money box: the same name, or its acronym — for a national organisation only where
            # that box has money in the country (two countries' "Ministry of Health" are two
            # organisations); an international NGO also by the start of its name ('Save the
            # Children (SCI)': 'Save the Children Fund'; 'World Vision Vanuatu': 'World Vision')
            for r in rows:
                n, a = _fold(r.name), _fold(r.acronym) if isinstance(r.acronym, str) else ""
                k = by_name.get(n) or (by_name.get(a) if len(a) >= 3 else None)
                if k is None and r.grp == "ingo" and len(n) >= 8:
                    near = [(sum(v for (k_, t, *_), v in agg.items() if k_ == m_ and t != "O"), m_)
                            for f_, m_ in by_name.items()
                            if ent[m_]["k"] == "ingo" and len(f_) >= 8 and (f_.startswith(n) or n.startswith(f_))]
                    k = max(near)[1] if near else None
                if k is None or ent[k]["k"] == "un" or k not in in_country:
                    continue
                if ent[k]["k"] != "ingo" and r.country_iso3 not in in_country[k]:
                    continue
                key = k
                break
        if key is None:
            # only in the lists: its most usual name, or the shortest where the lists of several
            # countries name it differently (a coordinator named with one country in its title)
            vc = g["name"].astype(str).value_counts()
            nm = vc.index[0] if g["country_iso3"].nunique() == 1 or len(vc) == 1 else min(vc.index, key=len)
            ac = next((r.acronym for r in rows if isinstance(r.acronym, str) and r.acronym.strip()), None)
            label = nm if not ac or _fold(ac) in _fold(nm) else f"{nm} ({ac.strip()})"
            kind = GRP_KIND.get(g["grp"].value_counts().index[0], "oth")
            # the same name in another country's list is the same organisation, unless it is a
            # government body (two countries' "Ministry of Agriculture")
            same = by_name.get(_fold(nm))
            if same is not None and same.startswith("l|") and kind != "gov" and ent[same]["k"] == kind:
                key = same
            else:
                key = entity(f"l|{_oid}", html.unescape(label), kind)
                by_name.setdefault(_fold(nm), key)
        for r in rows:
            f = fw(r.country_iso3, r.hazard)
            got = ent[key]["l"].setdefault(f, [])
            for x in (r.roles if isinstance(r.roles, (list, tuple)) else []):
                if x in ROLES and ROLES[x] not in got:
                    got.append(ROLES[x])
            for x in (r.name, r.acronym):
                if isinstance(x, str) and len(_fold(x)) >= 3:
                    in_fw.setdefault((r.country_iso3, r.hazard), {}).setdefault(_fold(x), key)
                    in_c.setdefault(r.country_iso3, {}).setdefault(_fold(x), key)
            if isinstance(r.acronym, str) and len(_fold(r.acronym)) >= 3:
                acr.setdefault(_fold(r.acronym), key)
            if isinstance(r.acronym, str) and 2 <= len(r.acronym.strip()) <= 12:
                ent[key]["al"].add(html.unescape(r.acronym.strip()))      # what the Find box also answers to

    def find(name, c=None, h=None):
        """The organisation a budget line, a co-financing line or a project names, or None: a UN
        agency; else what the name stands for in that framework's partner list, then in the
        country's lists; else an organisation of that name or acronym anywhere, unless it is a
        national one of another country."""
        n = str(name).strip()
        if _is_un(n):
            short = _un_short(n) or n
            return entity(f"un|{short.casefold()}", short, "un")
        f = _fold(n)
        k = in_fw.get((c, h), {}).get(f) or in_c.get(c, {}).get(f)
        if k is None:
            k = by_name.get(f) or acr.get(f)
            if k is not None and c is not None and ent[k]["k"] in ("gov", "nngo", "rc") and c not in (
                    in_country.get(k, set()) | {fws[x]["c"] for x in ent[k]["l"]}):
                k = None
        return k

    # ---- co-financing now, by co-financer (the Financing page's rows)
    cof = d.get("_cof_now")
    for r in (cof.itertuples() if cof is not None else ()):
        who = str(r.who).strip()
        if not (r.amount_usd > 0) or not who or who.lower().startswith("not recorded"):
            continue
        members = [x.strip() for x in re.split(r",\s*|\s+and\s+", who) if x.strip()] if "," in who else [who]
        for m in members:
            k = find(AGENCY_ALIAS.get(m, m), r.country_iso3, r.hazard)
            if k is None:       # a co-financer the other records do not name
                k = entity(f"c|{_fold(m)}", m, "oth")
                by_name.setdefault(_fold(m), k)
            ent[k]["c"].append([fw(r.country_iso3, r.hazard), round(float(r.amount_usd)),
                                [x for x in members if x != m] if len(members) > 1 else None])

    # ---- sectors. Budgeted: the agency × sector lines of each current framework's latest version
    # that has agency lines (as the money flows read the split)
    sp = d["split_all"]
    sp = sp[sp["agency"].notna()].assign(version=sp.loc[sp["agency"].notna(), "version"].astype(str))
    fvm = d["fv_meta"].assign(vf=pd.to_datetime(d["fv_meta"]["valid_from"].astype(str), errors="coerce"),
                              version=d["fv_meta"]["version"].astype(str))
    old = d.get("old") or set()
    for r in cur[cur["lifecycle"].isin(LIVE)].itertuples():
        c, h = r.country_iso3, r.hazard
        vs = fvm[(fvm["country_iso3"] == c) & (fvm["hazard"] == h)].sort_values("vf", na_position="first")
        for v in reversed([v for v in vs["version"] if (c, h, v) not in old]):
            lines = sp[(sp["country_iso3"] == c) & (sp["hazard"] == h) & (sp["version"] == v)]
            if len(lines):
                for x in lines[lines["sector"].notna()].itertuples():
                    k = find(x.agency, c, h)
                    for col in (_cols(x.sector) if k else ()):
                        s = ent[k]["sb"].setdefault(col, [])
                        if fw(c, h) not in s:
                            s.append(fw(c, h))
                break
    # released: the projects framework releases paid, by sector and kind of fund (a label in two
    # columns: halves). A pooled fund's grantee under the one spelling the money flows give it
    spell = dict(d.get("org_spelling") or [])
    lost = 0.0
    for fc, org, label, usd in _released_sectors():
        if fc == "cerf":
            k = find(AGENCY_ALIAS.get(org, org))
        else:
            org = spell.get(str(org), html.unescape(str(org)))
            k = find(_un_short(org)) if _un_short(org) else by_name.get(_fold(org))
        cols = sorted(_cols(label)) if k else []
        lost += 0.0 if k else usd
        for col in cols:
            by = ent[k]["sr"].setdefault(col, {})
            by[_fu(fc)] = by.get(_fu(fc), 0.0) + usd / len(cols)
    if lost >= 0.5:
        print(f"  partner profile: ${lost:,.0f} of project budgets by sector under a name no organisation has")

    # two organisations of one name (two countries' "Ministry of Agriculture"): each says its country
    seen = {}
    for k in order:
        seen.setdefault(_fold(ent[k]["n"]), []).append(k)
    for ks in seen.values():
        if len(ks) > 1:
            for k in ks:
                cs = sorted({fws[f]["n"] for f in ent[k]["l"]} | {fws[f]["n"] for f, *_ in ent[k]["c"]}
                            | {fws[f]["n"] for (k_, _t, _y, f, _g, _f2) in agg if k_ == k})
                if cs and all(cs):
                    ent[k]["n"] += " — " + ", ".join(cs)
    # a UN agency also answers to its acronym in the site's other languages (OMS, PAM)
    for alias, en in UN_ALIAS.items():
        k = f"un|{(_un_short(en) or '').casefold()}"
        if k in ent:
            ent[k]["al"].add(alias.upper())
    idx = {k: i for i, k in enumerate(order)}
    orgs = [{"n": e["n"], "k": e["k"], "l": sorted([f, rs] for f, rs in e["l"].items()), "c": e["c"],
             "al": sorted(a for a in e["al"] if _fold(a) not in _fold(e["n"])),
             "sb": e["sb"], "sr": {c: {fu: round(v) for fu, v in by.items() if v >= 0.5} for c, by in e["sr"].items()}}
            for e in (ent[k] for k in order)]
    rows = [[idx[k], t, y, f, g, fu, round(v)] for (k, t, y, f, g, fu), v in sorted(agg.items()) if v >= 0.5]
    return {"cy": cy, "years": years, "orgs": orgs, "fw": fws, "rows": rows,
            "tot": [[*k, round(v)] for k, v in sorted(tot.items())],
            "kind": ORG_COLOR, "cols": [c for c, _ in IASC_COLS], "nListed": n_listed,
            "nLive": int(cur["lifecycle"].isin(LIVE).sum())}


CSS = """
.ppick { display:flex; flex-wrap:wrap; gap:8px 12px; align-items:center; margin:6px 0 4px; font-size:14px; }
.ppick input[type=search] { font-size:14px; padding:6px 10px; border:1px solid #b9c2cf; border-radius:6px; width:min(420px, 100%); }
.ppick button, .pchips button { font-size:13px; padding:5px 10px; border:1px solid #b9c2cf; border-radius:6px;
  background:#fff; cursor:pointer; }
.ppick button:hover, .pchips button:hover { background:#f0f4f9; }
.pchips { display:flex; flex-wrap:wrap; gap:6px; margin:4px 0 10px; align-items:center; font-size:13px; }
.pchips button[aria-pressed=true] { background:#1f2a44; color:#fff; border-color:#1f2a44; }
.pmsg { font-size:13px; color:#52514e; margin:2px 0 8px; min-height:18px; }
.pmsg button { font-size:12.5px; margin:2px 4px 2px 0; padding:3px 8px; border:1px solid #b9c2cf; border-radius:6px; background:#fff; cursor:pointer; }
.pfbar { display:flex; flex-wrap:wrap; gap:6px 16px; align-items:center; font-size:13px; margin:4px 0 10px;
  padding:6px 10px; background:#f5f7fa; border-radius:6px; }
.pfbar .pft { font-weight:600; }
.phead { display:flex; flex-wrap:wrap; gap:10px; align-items:baseline; margin:14px 0 2px; }
.phead h2 { margin:0; }
.pkind { font-size:12px; font-weight:600; padding:2px 9px; border-radius:10px; color:#fff; }
.tile .tk { font-weight:600; color:#1a1a1a; display:block; margin-bottom:2px; }
.tile .sub { font-size:12.5px; color:#52514e; margin-top:6px; }
.cv { position:relative; height:260px; }
table.pp td.num, table.pp th.num { text-align:right; white-space:nowrap; }
table.pp td, table.pp th { vertical-align:top; }
table.pp tr.tot td { font-weight:600; border-top:2px solid #c9d1dc; }
table.pp button.lnk { border:0; background:none; padding:0; color:#1c5cab; cursor:pointer; font:inherit; text-align:left; }
table.pp button.lnk:hover { text-decoration:underline; }
.muted { color:#666; }
"""

JS = """
const CY = D.cy, YS = D.years, O = D.orgs, FW = D.fw;
const el = id => document.getElementById(id);
const sum = xs => xs.reduce((a, b) => a + (b || 0), 0);
const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const yLab = y => +y === CY ? y + '*' : String(y);
const fold = s => String(s).normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase().replace(/[^0-9a-z]+/g, '');
const pct = (a, b) => !(b > 0) ? '' : a / b >= 0.0995 ? Math.round(100 * a / b) + '%' : a / b < 0.0005 ? (a > 0 ? '<0.1%' : '0%') : (100 * a / b).toFixed(1) + '%';
const KIND = {un:'UN', nngo:'National / local NGOs', ingo:'International NGOs', rc:'Red Cross / Red Crescent',
              gov:'Government', oth:'Other'};
const LIFE = {active:'active', updating:'being updated', development:'in development', retired:'retired'};
// rows: [organisation, P pre-arranged / R released, received from a fund / S released, received
// through another organisation / O released, passed on, year, framework, layer, fund, US$]
const BY = new Map(); D.rows.forEach(r => { if(!BY.has(r[0])) BY.set(r[0], []); BY.get(r[0]).push(r); });
const opts = () => ({adh: el('ppAdh').checked, fu: {c: el('ppC').checked, p: el('ppP').checked, r: el('ppR').checked}});
const keep = (g, fu, o) => (o.adh || g !== 'a') && o.fu[fu];
const fwName = f => f.a ? (tr8(f.n) + ' ' + tr8(f.h) + ' (' + tr8('non-framework allocation') + ')')
  : f.e ? tr8(f.n) + ' ' + tr8(f.h) + ' (' + tr8('earlier framework') + ')'
  : f.h ? tr8(f.n) + ' ' + tr8(f.h) : f.n ? tr8(f.n) + ' (' + tr8('no single framework') + ')' : tr8('No country recorded');
// the site's money(), without its "$1000k" for a figure a little under a million
const usd = v => v >= 999500 && v < 1e6 ? '$1.0M' : money(v);
const fwCell = f => f.p ? `<a href="${f.p}">${esc(fwName(f))}</a>` : esc(fwName(f));
let cur = null, charts = [];

function figures(i, o){
  const rows = (BY.get(i) || []).filter(r => keep(r[4], r[5], o));
  const of = (t, y) => sum(rows.filter(r => r[1] === t && (y == null || r[2] === y)).map(r => r[6]));
  const tot = (m, y) => sum(D.tot.filter(r => r[0] === m && (y == null || r[1] === y) && keep(r[2], r[3], o)).map(r => r[4]));
  return {rows, preNow: of('P', CY), rel: of('R'), sub: of('S'), on: of('O'), totPre: tot('p', CY), totRel: tot('r'),
          pre: YS.map(y => of('P', y)), relY: YS.map(y => of('R', y)), subY: YS.map(y => of('S', y))};
}

// the organisations ranked, before one is chosen
function drawList(){
  const o = opts();
  const all = O.map((x, i) => ({i, x, f: figures(i, o)})).filter(r => r.f.preNow || r.f.rel || r.f.sub)
    .sort((a, b) => (b.f.preNow + b.f.rel + b.f.sub) - (a.f.preNow + a.f.rel + a.f.sub));
  const top = all.slice(0, 25);
  el('ppOut').innerHTML = `<h2>${tr8('Organisations with the most framework money')}</h2>
<p class="meta">${tr8('The {0} organisations with the most pre-arranged money now and money released since {1}, of the {2} that have either. Choose one for its profile.', top.length, YS[0], all.length)}</p>
<div class="scroll" style="max-height:none"><table class="data pp"><thead><tr><th>${tr8('organisation')}</th><th>${tr8('kind')}</th>
<th class="num">${tr8('pre-arranged now')}</th><th class="num">${tr8('released, {0}–{1}', YS[0], CY)}</th>
<th class="num">${tr8('received through another organisation')}</th></tr></thead><tbody>` +
    top.map(r => `<tr><td><button type="button" class="lnk" data-i="${r.i}">${esc(r.x.n)}</button></td><td>${tr8(KIND[r.x.k])}</td>
<td class="num">${r.f.preNow ? usd(r.f.preNow) : '–'}</td><td class="num">${r.f.rel ? usd(r.f.rel) : '–'}</td>
<td class="num">${r.f.sub ? usd(r.f.sub) : '–'}</td></tr>`).join('') + '</tbody></table></div>';
}

function drawProfile(i){
  const x = O[i], o = opts(), f = figures(i, o);
  const per = new Map();      // framework -> its figures
  const at = k => { if(!per.has(k)) per.set(k, {P:0, R:0, S:0, O:0, roles:null, cof:0, shared:[]}); return per.get(k); };
  f.rows.forEach(r => { if(r[1] !== 'P' || r[2] === CY) at(r[3])[r[1]] += r[6]; });
  x.l.forEach(([k, roles]) => { at(k).roles = roles; });
  x.c.forEach(([k, usd, shared]) => { if(shared) at(k).shared.push([usd, shared]); else at(k).cof += usd; });
  const keys = [...per.keys()].sort((a, b) => (FW[a].a - FW[b].a) || fwName(FW[a]).localeCompare(fwName(FW[b])));
  const cof = sum(x.c.filter(c => !c[2]).map(c => c[1])), nCof = new Set(x.c.filter(c => !c[2]).map(c => c[0])).size;
  const shared = x.c.filter(c => c[2]);
  const nList = x.l.length, withMoney = keys.filter(k => !FW[k].a && FW[k].h && (per.get(k).P || per.get(k).R || per.get(k).S)).length;
  const tile = (v, name, line, sub) => `<div class="tile"><div class="v">${v}</div><div class="l"><span class="tk">${name}</span>${line}${sub ? `<div class="sub">${sub}</div>` : ''}</div></div>`;
  const tiles = [
    tile(nList, tr8('Frameworks'), tr8('of the {0} current frameworks with a partner list name it', D.nListed),
         withMoney === 1 ? tr8('It has pre-arranged or released money under 1 framework.')
                         : tr8('It has pre-arranged or released money under {0} frameworks.', withMoney)),
    tile(f.preNow ? usd(f.preNow) : '–', tr8('Pre-arranged now'),
         f.preNow ? tr8('{0} of the {1} pre-arranged now', pct(f.preNow, f.totPre), usd(f.totPre))
                  : tr8('No budget of a current framework names it for a share of the {0} pre-arranged now.', usd(f.totPre)), ''),
    tile(f.rel ? usd(f.rel) : '–', tr8('Released, {0}–{1}', YS[0], CY),
         f.rel ? tr8('received from the funds: {0} of the {1} released', pct(f.rel, f.totRel), usd(f.totRel))
               : tr8('No release went to it directly, of the {0} released.', usd(f.totRel)),
         [f.on ? tr8('{0} of it passed on to other organisations.', usd(f.on)) : '',
          f.sub ? tr8('{0} more received through another organisation.', usd(f.sub)) : ''].filter(Boolean).join(' ')),
    tile(cof ? usd(cof) : '–', tr8('Co-financing now'),
         cof ? (nCof === 1 ? tr8('its own money beside the funds, in 1 framework') : tr8('its own money beside the funds, in {0} frameworks', nCof))
             : tr8('No current framework records co-financing from it alone.'),
         shared.length ? esc(tr8('Not in this figure: {0}.', shared.map(c => tr8('{0} stated jointly with {1} ({2})', usd(c[1]), c[2].join(', '), fwName(FW[c[0]]))).join('; '))) : '')];
  const body = keys.map(k => { const p = per.get(k), fw = FW[k];
    return `<tr><td>${fwCell(fw)}</td><td>${fw.lc ? tr8(LIFE[fw.lc] || fw.lc) : ''}</td>
<td>${p.roles ? (p.roles.length ? p.roles.map(r => tr8(r)).join(', ') : tr8('named')) : '<span class="muted">' + (fw.pl ? tr8('not named') : fw.a || !fw.h || fw.lc === 'retired' ? '' : tr8('no partner list')) + '</span>'}</td>
<td class="num">${p.P ? usd(p.P) : ''}</td><td class="num">${p.R ? usd(p.R) : ''}</td><td class="num">${p.O ? usd(p.O) : ''}</td>
<td class="num">${p.S ? usd(p.S) : ''}</td><td class="num">${p.cof ? usd(p.cof) : ''}${p.shared.map(s => `<div class="muted">${tr8('{0} with {1}', usd(s[0]), esc(s[1].join(', ')))}</div>`).join('')}</td></tr>`; }).join('');
  // its projects' budgets by sector, for the funds ticked (non-framework allocations have none here)
  const sr = {}; Object.keys(x.sr).forEach(c => { const v = sum(Object.keys(x.sr[c]).filter(fu => o.fu[fu]).map(fu => x.sr[c][fu])); if(v) sr[c] = v; });
  const secs = D.cols.filter(c => (x.sb[c] && x.sb[c].length) || sr[c]);
  const srTot = sum(Object.values(sr));
  el('ppOut').innerHTML = `<div class="phead"><h2>${esc(x.n)}</h2><span class="pkind" style="background:${D.kind[x.k]}">${tr8(KIND[x.k])}</span></div>
<div class="tiles">${tiles.join('')}</div>
<div class="grid">
 <div class="panel"><h3>${tr8('Pre-arranged for it, by year')}</h3><div class="cv"><canvas id="ppc1" style="max-height:none"></canvas></div>
  <div class="note">${tr8('What was in place for it in each year, not added over years. * {0}: now.', CY)}</div></div>
 <div class="panel"><h3>${tr8('Released to it, by year')}</h3><div class="cv"><canvas id="ppc2" style="max-height:none"></canvas></div>
  <div class="note">${tr8('* {0}: to date.', CY)}</div></div>
</div>
<h3>${tr8('Frameworks')}</h3>
${keys.length ? `<div class="scroll" style="max-height:none"><table class="data pp"><thead><tr><th>${tr8('framework')}</th><th>${tr8('status')}</th><th>${tr8('in the partner list as')}</th>
<th class="num">${tr8('pre-arranged now')}</th><th class="num">${tr8('released to it, {0}–{1}', YS[0], CY)}</th><th class="num">${tr8('of which passed on')}</th>
<th class="num">${tr8('received through another organisation')}</th><th class="num">${tr8('co-financing now')}</th></tr></thead><tbody>${body}
<tr class="tot"><td colspan="3">${tr8('Total')}</td><td class="num">${f.preNow ? usd(f.preNow) : ''}</td><td class="num">${f.rel ? usd(f.rel) : ''}</td>
<td class="num">${f.on ? usd(f.on) : ''}</td><td class="num">${f.sub ? usd(f.sub) : ''}</td><td class="num">${cof ? usd(cof) : ''}</td></tr></tbody></table></div>`
  : `<p class="meta">${tr8('No framework names it and no framework money is recorded for it with these boxes ticked.')}</p>`}
<h3>${tr8('Sectors')}</h3>
${secs.length ? `<div class="scroll" style="max-height:none"><table class="data pp"><thead><tr><th>${tr8('sector')}</th><th>${tr8('current frameworks whose budget gives it this sector')}</th>
<th class="num">${tr8('its projects paid by framework releases, all years')}</th></tr></thead><tbody>` +
    secs.map(c => `<tr><td>${tr8(c)}</td><td>${(x.sb[c] || []).map(k => fwCell(FW[k])).join(', ')}</td>
<td class="num">${sr[c] ? usd(sr[c]) + ' <span class="muted">' + pct(sr[c], srTot) + '</span>' : ''}</td></tr>`).join('') + '</tbody></table></div>'
  : `<p class="meta">${tr8('No sector is recorded for it: no framework budget gives it one, and no project of a framework release is recorded under its name.')}</p>`}`;
  charts.forEach(c => c.destroy()); charts = [];
  charts.push(mkChart('ppc1', 'bar', YS.map(yLab), [{label:tr8('pre-arranged'), data:f.pre, backgroundColor:D.kind[x.k]}], {allLabels:true}));
  const ds = [{label:tr8('received from the funds'), data:f.relY, backgroundColor:D.kind[x.k]},
              {label:tr8('received through another organisation'), data:f.subY, backgroundColor:'#9aa3ae'}].filter(d => d.data.some(v => v));
  charts.push(mkChart('ppc2', 'bar', YS.map(yLab), ds.length ? ds : [{label:tr8('received from the funds'), data:f.relY, backgroundColor:D.kind[x.k]}],
                      {stacked:true, totals:true, allLabels:true}));
}

function draw(){
  document.querySelectorAll('#ppChips button').forEach(b => b.setAttribute('aria-pressed', String(+b.dataset.i === cur)));
  el('ppBack').hidden = cur == null;
  if(cur == null) drawList(); else drawProfile(cur);
}
function choose(i, keepText){
  cur = i; el('ppMsg').textContent = '';
  if(!keepText) el('ppS').value = i == null ? '' : O[i].n;
  try { history.replaceState(null, '', i == null ? location.pathname + location.search : '#' + encodeURIComponent(O[i].n)); } catch(e){}
  draw();
}
// what is typed: the organisation of that name, else those whose name holds it (one: chosen;
// several: offered as buttons)
function find(q){
  const k = fold(q); if(!k){ choose(null); return; }
  const exact = O.findIndex(x => fold(x.n) === k);
  if(exact >= 0){ choose(exact); return; }
  const alias = O.map((x, i) => i).filter(i => O[i].al.some(a => fold(a) === k));   // 'PAM': WFP
  if(alias.length === 1){ choose(alias[0]); return; }
  const hits = O.map((x, i) => i).filter(i => fold(O[i].n).includes(k) || O[i].al.some(a => fold(a) === k));
  if(hits.length === 1){ choose(hits[0]); return; }
  const m = el('ppMsg');
  if(!hits.length){ m.textContent = tr8('No organisation with “{0}” in its name.', q.trim()); return; }
  const money_ = i => sum((BY.get(i) || []).map(r => r[6]));
  hits.sort((a, b) => money_(b) - money_(a));
  m.innerHTML = esc(tr8('{0} organisations have “{1}” in their name:', hits.length, q.trim())) + ' ' +
    hits.slice(0, 12).map(i => `<button type="button" data-i="${i}">${esc(O[i].n)}</button>`).join('') +
    (hits.length > 12 ? ' ' + esc(tr8('and {0} more: type more of the name.', hits.length - 12)) : '');
}
function setup(){
  el('ppList').innerHTML = O.map(x => `<option value="${esc(x.n)}">`).join('');
  // the UN agencies with money, by what they hold now and have received: one click each
  const held = i => sum(BY.get(i).filter(r => r[4] !== 'a' && (r[1] === 'R' || r[1] === 'S' || (r[1] === 'P' && r[2] === CY))).map(r => r[6]));
  const un = O.map((x, i) => i).filter(i => O[i].k === 'un' && BY.has(i)).sort((a, b) => held(b) - held(a));
  el('ppChips').innerHTML = `<span class="muted">${tr8('UN agencies:')}</span> ` +
    un.map(i => `<button type="button" data-i="${i}" aria-pressed="false">${esc(O[i].n)}</button>`).join('');
  let h = (location.hash || '').slice(1);
  try { h = decodeURIComponent(h); } catch(e){}
  const i = h ? O.findIndex(x => fold(x.n) === fold(h)) : -1;
  if(i >= 0) choose(i); else draw();
}
el('ppForm').addEventListener('submit', e => { e.preventDefault(); find(el('ppS').value); });
el('ppS').addEventListener('change', () => { const i = O.findIndex(x => x.n === el('ppS').value); if(i >= 0) choose(i); });
el('ppBack').addEventListener('click', () => choose(null));
document.addEventListener('click', e => { const b = e.target.closest('#ppChips button, #ppMsg button, #ppOut button.lnk');
  if(b) choose(+b.dataset.i); });
['ppAdh', 'ppC', 'ppP', 'ppR'].forEach(id => el(id).addEventListener('change', draw));
document.addEventListener('aalang', () => { setup(); });
setup();
"""


def build_partner(page, d):
    data = assemble(d)
    cy, y0 = data["cy"], data["years"][0]
    how = TBF(
        "<b>Frameworks</b>: the partner list of each current framework, from its latest version that has "
        "one ({n} of the {m} current frameworks have a list). <b>Pre-arranged</b>: the share of each "
        "framework's pre-arranged money that its budget gives the organisation, or, for a Country or "
        "Regional Fund, the grantees of its allocation; who a UN agency will sub-grant to is known only "
        "once money is released. It is what is in place at a date, never added over years. "
        "<b>Released</b>: what the funds paid the organisation for framework activations since {y0}: for "
        "CERF, the agency of each project of the allocation the activation drew on; for a Country or Regional "
        "Fund, the grantees of the allocation the activation drew on. What it passed on to other "
        "organisations is part of that figure; what it received through another organisation (a "
        "sub-grant) is shown apart and is part of the other organisation's figure, so the two are not "
        "added. <b>Co-financing</b>: the organisation's own money beside the funds, as the current "
        "frameworks record it; an amount a document states for several organisations together is "
        "listed and not added. <b>Sectors</b>: the sectors a current framework's budget gives the "
        "organisation, and the sectors of its projects that framework releases paid (CERF's project "
        "sectors and the Country and Regional Funds' project clusters). These are the projects' "
        "approved budgets, so they can differ from the released figure, which is what went out "
        "after refunds. Frameworks since retired count in the years they were in "
        "place; non-framework allocations only with their box ticked. The figures are the "
        "<a href='dash-funding.html'>Financing</a> page's money flows, organisation by organisation. "
        "One organisation can appear twice where a framework document and a fund's records spell its "
        "name differently.", n=data["nListed"], m=data["nLive"], y0=y0)
    panels = f"""
<form class='ppick' id='ppForm' role='search'>
 <label for='ppS'>{T("Organisation")}</label>
 <input type='search' id='ppS' list='ppList' autocomplete='off' {ATTR("placeholder", "type a name, for instance WHO")}>
 <datalist id='ppList'></datalist>
 <button type='submit'>{T("Show")}</button>
 <button type='button' id='ppBack' hidden>{T("All organisations")}</button>
</form>
<div class='pchips' id='ppChips'></div>
<div class='pmsg' id='ppMsg' role='status' aria-live='polite'></div>
<div class='pfbar' role='group' {ATTR("aria-label", "What the money figures count")}>
 <span class='pft'>{T("The money figures count:")}</span>
 <label><input type='checkbox' id='ppC' checked> CERF</label>
 <label><input type='checkbox' id='ppP' checked> CBPF</label>
 <label><input type='checkbox' id='ppR' checked> RHPF</label>
 <label {ATTR("title", "AA money allocated without a framework: released, or pre-arranged and not yet released")}><input type='checkbox' id='ppAdh'> {T("Non-framework allocations")}</label>
</div>
<div id='ppOut'></div>
<details class='note' style='font-size:12px;margin:14px 0 10px'><summary style='cursor:pointer'>{T("How the profile is counted")}</summary>{how}</details>
<style>{CSS}</style>"""
    _dash_page(page, PAGE, "Partner profile", "", panels, json.dumps(data, default=str), JS)
    return data
