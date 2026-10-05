"""Turn full reads of framework documents into an entries file (scripts/apply_entries.py).

A "doc read" is one JSON per framework version, `<kb>__<version>.json`, with the page body
beside it in `<kb>__<version>.md`, written by reading the version's framework document in
full (the spec lives with the reads, not in git: they are entry data). This script compares
each read with what the database holds (any copy with the same schema: the dev DB through the
tunnel, or a snapshot restored locally) and writes:

- framework_version — valid_from / valid_until / endorsed_by / prearranged_usd_doc /
  doc_title / window_rollup / supersedes. A published final document overrides the DB; a
  draft or secondary source only fills what the DB leaves empty. Every change is reported.
- version_page — the page body, the trigger table and the frontmatter MERGED into the
  existing one (the read's keys win; keys only the DB has, e.g. framework_doc, are kept).
- window — one row per trigger window (basis, allocation, analysed years, reported RP/prob).
- window_funding — the stated rows, provenance 'doc-stated' (agency / sector rows are the
  breakdown; rows without either are the envelope). When a fund's envelope is stated only as
  a total, it goes to window 'unattributed'.
- simulated_activation — the backtest years the document lists, only those BEFORE the
  version took effect (a version's backtest is fixed before it is endorsed).
- people_covered — the people targeted, as at the version's start, source 'framework-doc'.
Partners are compared with aa.framework_partner and reported, not written.

Usage:
    uv run python scripts/docread_to_entries.py DIR [--out ENTRIES.json] [--summary SUMMARY.json]
"""

import argparse
import calendar
import datetime as dt
import json
import re
import sys
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import ocha_stratus as stratus  # noqa: E402

SOURCE = "docread-2026-10"
FUND_ALIASES = {"CERF": "cerf"}


def _date_end(v):
    """'2027' -> 2027-12-31, '2027-01' -> 2027-01-31, '2027-01-15' -> itself; else None."""
    if not v:
        return None
    s = str(v).strip()
    if re.fullmatch(r"\d{4}", s):
        return f"{s}-12-31"
    if re.fullmatch(r"\d{4}-\d{2}", s):
        y, m = map(int, s.split("-"))
        return f"{s}-{calendar.monthrange(y, m)[1]:02d}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    return None


def _date_start(v):
    if not v:
        return None
    s = str(v).strip()
    if re.fullmatch(r"\d{4}", s):
        return f"{s}-01-01"
    if re.fullmatch(r"\d{4}-\d{2}", s):
        return f"{s}-01"
    return s if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else None


def _num(v):
    try:
        x = float(str(v).replace(",", "").replace("$", "").strip())
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def _rp(v):
    """'1-in-5 years', '1 in 4.3', '5-year' -> the number; else None."""
    m = re.search(r"1\s*(?:-|\s)?in\s*(?:-|\s)?([\d.]+)|([\d.]+)\s*-?\s*(?:year|yr|ans?)\b", str(v or ""), re.I)
    return float(m.group(1) or m.group(2)) if m else None


def _prob(v):
    s = str(v or "")
    m = re.search(r"([\d.]+)\s*%", s)
    if m:
        return float(m.group(1)) / 100
    x = _num(s)
    return x if x is not None and 0 < x < 1 else None


def fund_code(label, iso3, funds):
    """The doc's fund label -> aa.fund code: CERF, the country's CBPF (…HF), a regional fund."""
    if not label:
        return None
    k = str(label).strip()
    if k.upper() in FUND_ALIASES:
        return FUND_ALIASES[k.upper()]
    low = k.lower()
    mine = funds[funds["country_iso3"] == iso3]
    if "rhpf" in low or "regional" in low or "fhraoc" in low:
        hit = mine[mine["fund_type"] == "regional_fund"]
        return hit["fund_code"].iloc[0] if len(hit) else "rhpf"
    if low.endswith("hf") or "cbpf" in low or "pooled fund" in low or "humanitarian fund" in low:
        hit = mine[mine["fund_type"] == "cbpf"]
        return hit["fund_code"].iloc[0] if len(hit) else "cbpf-unspecified"
    return None   # an agency's own money, a donor, government: co-financing, named by financier


def _checks(read, fm):
    """Internal consistency of a read: rows add up, windows named, sims inside the analysed span."""
    out = []
    wins = {w.get("window_name") for w in read.get("windows") or []}
    rows = read.get("funding_rows") or []
    for r in rows:
        if r.get("window") and r["window"] not in wins:
            out.append(f"funding row names undeclared window {r['window']!r}")
    for s_ in read.get("simulated_activations") or []:
        if s_.get("window") and s_["window"] not in wins:
            out.append(f"backtest row names undeclared window {s_['window']!r}")
    span = {w.get("window_name"): (w.get("analysis_start"), w.get("analysis_end")) for w in read.get("windows") or []}
    for s_ in read.get("simulated_activations") or []:
        a, b = span.get(s_.get("window"), (None, None))
        y = s_.get("event_year")
        if y and a and b and not (int(a) <= int(y) <= int(b)):
            out.append(f"backtest year {y} outside the analysed {a}-{b} ({s_.get('window')})")
    env = [r for r in rows if not r.get("agency") and not r.get("sector") and (r.get("kind") or "prearranged") == "prearranged"]
    brk = [r for r in rows if (r.get("agency") or r.get("sector")) and (r.get("kind") or "prearranged") == "prearranged"]
    for w in {r.get("window") for r in env}:
        e = sum(_num(r.get("amount_usd")) or 0 for r in env if r.get("window") == w)
        b = sum(_num(r.get("amount_usd")) or 0 for r in brk if r.get("window") == w)
        if b and abs(e - b) > 1:
            out.append(f"window {w!r}: envelope {e:,.0f} vs agency/sector rows {b:,.0f}")
    tot = _num((read.get("framework_version") or {}).get("prearranged_usd_doc"))
    if tot and env and abs(sum(_num(r.get("amount_usd")) or 0 for r in env) - tot) > 1:
        out.append(f"envelope rows sum {sum(_num(r.get('amount_usd')) or 0 for r in env):,.0f} vs stated total {tot:,.0f}")
    ev = {e.get("field", "").split(".")[0] for e in read.get("evidence") or []}
    for f in ("framework_version", "funding_rows", "windows"):
        if read.get(f) and f not in ev and not any(x.startswith(f) for x in ev):
            out.append(f"no evidence rows for {f}")
    return out


def _env_before(db, countries, hz, ver):
    """The version's pre-arranged envelope in the DB before this read (rows without agency /
    sector; an 'all' total only where no per-fund split exists)."""
    wf = db["wf"]
    x = wf[wf["country_iso3"].isin(countries) & (wf["hazard"] == hz) & (wf["version"] == ver)
           & (wf["kind"] == "prearranged") & wf["agency"].isna() & wf["sector"].isna()
           & wf["amount_usd"].notna()]
    if x.empty:
        return None
    if (x["fund_code"] != "all").any():
        x = x[x["fund_code"] != "all"]
    # named windows replace a fund's 'unattributed' total (as v_version_funding); several
    # sources repeating the same figure count once (the largest); windows add up
    named = x[~x["window_name"].isin(["unattributed", "single"])]
    x = pd.concat([named, x[~x["fund_code"].isin(named["fund_code"]) & x["window_name"].isin(["unattributed", "single"])]])
    per = x.groupby(["country_iso3", "fund_code", "window_name"])["amount_usd"].max()
    return float(per.groupby(["country_iso3", "fund_code"]).sum().groupby("fund_code").max().sum())


def load(engine):
    q = lambda s: pd.read_sql(s, engine)  # noqa: E731
    return {
        "fv": q("SELECT * FROM aa.framework_version"),
        "vp": q("SELECT kb_framework, version, frontmatter, triggers, length(body_md) AS body_len "
                "FROM aa.version_page"),
        "win": q('SELECT * FROM aa."window"'),
        "wf": q("SELECT * FROM aa.window_funding"),
        "sim": q("SELECT country_iso3, hazard, version, window_name, event_year FROM aa.simulated_activation"),
        "part": q("SELECT country_iso3, hazard, version, name, acronym FROM aa.framework_partner"),
        "pc": q("SELECT country_iso3, hazard, as_of, source, people_covered FROM aa.people_covered"),
        "fund": q("SELECT fund_code, fund_type, country_iso3 FROM aa.fund"),
    }


def convert(read, body, db):
    """(entries rows, summary dict) for one doc read."""
    rows, changes, dropped = [], [], []
    kb, ver, hz = read["kb_framework"], str(read["version"]), read["hazard"]
    quality = read.get("source_quality") or "published-final"
    final = quality == "published-final"
    fvr = read.get("framework_version") or {}
    fm = dict(read.get("frontmatter") or {})
    countries = read.get("countries") or []
    add = lambda t, r: rows.append({"table": t, "row": r})  # noqa: E731

    vf = _date_start(fvr.get("valid_from"))
    vf_year = int(vf[:4]) if vf else None
    for c in countries:
        cur = db["fv"][(db["fv"]["country_iso3"] == c) & (db["fv"]["hazard"] == hz)
                       & (db["fv"]["version"] == ver)]
        if cur.empty:
            changes.append(f"{c}/{hz}/{ver}: NOT IN aa.framework_version — skipped")
            continue
        cur = cur.iloc[0]
        upd = {}
        basis = fvr.get("valid_until_basis") or ("stated" if fvr.get("valid_until") else "none")
        vu = _date_end(fvr.get("valid_until")) if basis == "stated" else _date_end(fvr.get("valid_until_inferred"))
        want = {
            "valid_from": vf, "valid_until": vu,
            "endorsed_by": fvr.get("endorsed_by"), "prearranged_usd_doc": _num(fvr.get("prearranged_usd_doc")),
            "doc_title": fvr.get("doc_title") or (read.get("identity") or {}).get("doc_title"),
            "window_rollup": fvr.get("window_rollup"), "supersedes": fvr.get("supersedes"),
        }
        for k, v in want.items():
            if v in (None, ""):
                continue
            old = cur.get(k)
            old_s = None if pd.isna(old) else str(old)[:10] if k.startswith("valid") else str(old)
            new_s = str(v)[:10] if k.startswith("valid") else str(v)
            if k == "prearranged_usd_doc" and old_s is not None and _num(old_s) == _num(new_s):
                continue
            if old_s == new_s:
                continue
            inferred = k == "valid_until" and basis != "stated"
            if old_s is None or (final and not inferred):
                upd[k] = v
                changes.append(f"{c}/{hz}/{ver}: {k} {old_s} -> {new_s}")
            else:
                changes.append(f"{c}/{hz}/{ver}: {k} kept {old_s} (read says {new_s}, source {quality})")
        if "valid_until" in upd:
            upd["valid_until_source"] = "framework-doc" if basis == "stated" else basis
        if upd:
            add("framework_version", {"country_iso3": c, "hazard": hz, "version": ver, **upd})

    # ---- page: merged frontmatter, trigger table, body
    vp = db["vp"][(db["vp"]["kb_framework"] == kb) & (db["vp"]["version"] == ver)]
    old_fm = {}
    if len(vp):
        x = vp.iloc[0]["frontmatter"]
        old_fm = x if isinstance(x, dict) else json.loads(x or "{}")
    merged = {**old_fm, **{k: v for k, v in fm.items() if v not in (None, "", [], {})}}
    merged.update({"version": ver, "framework": kb, "source_quality": quality,
                   "doc_read": SOURCE})
    triggers = [{"window": w.get("window_name"), "basis": w.get("basis"), "indicator": w.get("indicator"),
                 "threshold": w.get("threshold"), "lead time": w.get("lead_time"),
                 "return period": w.get("return_period"),
                 "releases (usd)": w.get("allocation_usd")} for w in read.get("windows") or []]
    add("version_page", {"kb_framework": kb, "version": ver, "country_iso3": countries, "hazard": hz,
                         "frontmatter": merged, "frontmatter_text": None, "triggers": triggers, "body_md": body,
                         "source": SOURCE, "note": f"full read of the framework document ({quality})"})

    # ---- windows, funding, backtest, people: per country of the version
    n_win = n_fund = n_sim = 0
    for c in countries:
        if db["fv"][(db["fv"]["country_iso3"] == c) & (db["fv"]["hazard"] == hz)
                    & (db["fv"]["version"] == ver)].empty:
            continue
        all_in = fm.get("all_in")
        mine = lambda r: not r.get("country") or r.get("country") == c  # noqa: E731
        for w in [w for w in read.get("windows") or [] if mine(w)]:
            add("window", {"country_iso3": c, "hazard": hz, "version": ver, "window_name": w["window_name"],
                           "kb_framework": kb, "all_in": bool(all_in) if all_in is not None else False,
                           "basis": w.get("basis"), "allocation_usd": _num(w.get("allocation_usd")),
                           "analysis_start": w.get("analysis_start"), "analysis_end": w.get("analysis_end"),
                           "rp_reported": _rp(w.get("return_period")), "prob_reported": _prob(w.get("probability")),
                           "source": SOURCE})
            n_win += 1
        stated_env = set()
        for r in [r for r in read.get("funding_rows") or [] if mine(r)]:
            amt = _num(r.get("amount_usd"))
            if amt is None:
                continue
            kind = r.get("kind") or "prearranged"
            fc = fund_code(r.get("fund"), c, db["fund"]) if kind == "prearranged" else None
            if kind == "prearranged" and fc is None:
                kind = "cofinancing"
            fin = None if fc else (r.get("financier") or r.get("fund"))
            win = r.get("window") or "unattributed"
            if not r.get("agency") and not r.get("sector"):
                stated_env.add(fc)
            add("window_funding", {"country_iso3": c, "hazard": hz, "version": ver, "window_name": win,
                                   "kind": kind, "fund_code": fc, "financier": fin,
                                   "agency": r.get("agency"), "sector": r.get("sector"),
                                   "amount_usd": amt, "year": None, "provenance": "doc-stated",
                                   "source": SOURCE, "note": f"p.{r.get('page')}" if r.get("page") else None})
            n_fund += 1
        # a fund's envelope stated only as a total (funding_by_source) -> window 'unattributed'
        for label, amt in (fm.get("funding_by_source") or {}).items():
            fc = fund_code(label, c, db["fund"])
            if fc and fc not in stated_env and _num(amt):
                add("window_funding", {"country_iso3": c, "hazard": hz, "version": ver,
                                       "window_name": "unattributed", "kind": "prearranged", "fund_code": fc,
                                       "financier": None, "agency": None, "sector": None,
                                       "amount_usd": _num(amt), "year": None, "provenance": "doc-stated",
                                       "source": SOURCE, "note": "envelope total stated by fund"})
                n_fund += 1
        for s in [s for s in read.get("simulated_activations") or [] if mine(s)]:
            y = s.get("event_year")
            if y is None:
                continue
            if vf_year and int(y) >= vf_year:
                dropped.append(f"{c} {s.get('window')} {y}")
                continue
            d = s.get("event_date")
            add("simulated_activation", {"country_iso3": c, "hazard": hz, "version": ver,
                                         "window_name": s.get("window") or "window not recorded",
                                         "event_year": int(y), "event_label": s.get("event_label"),
                                         "kb_framework": kb, "event_date": d or None,
                                         "time_precision": "day" if d else "year",
                                         "source_note": f"framework document p.{s.get('page')}"})
            n_sim += 1
        tp = _num(fm.get("target_people"))
        if isinstance(fm.get("target_people_by_country"), dict):
            tp = _num(fm["target_people_by_country"].get(c)) or tp
        if tp and vf:
            add("people_covered", {"country_iso3": c, "hazard": hz, "as_of": vf, "source": "framework-doc",
                                   "people_covered": int(tp), "version": ver,
                                   "remarks": f"people targeted in the {ver} framework document"})

    # ---- partners: inserted only where the version has none yet; else compared and reported
    have = db["part"][(db["part"]["hazard"] == hz) & (db["part"]["version"] == ver)
                      & db["part"]["country_iso3"].isin(countries)]
    if have.empty:
        for c in countries:
            for pt in read.get("partners") or []:
                if not pt.get("name"):
                    continue
                add("framework_partner", {"country_iso3": c, "hazard": hz, "version": ver,
                                          "name": pt["name"], "acronym": pt.get("acronym"),
                                          "org_type": pt.get("org_type") or "other",
                                          "roles": [x.strip() for x in str(pt.get("roles") or "").split(";") if x.strip()],
                                          "source": SOURCE})
    have_names = {str(x).lower() for x in list(have["name"]) + list(have["acronym"].dropna())}
    new_partners = [p["name"] for p in read.get("partners") or []
                    if str(p.get("name", "")).lower() not in have_names
                    and str(p.get("acronym") or "").lower() not in have_names]
    checks = _checks(read, fm)
    if fm.get("all_in") is None:
        checks.append("all_in not stated in the read (window all_in written as false)")
    before = _env_before(db, countries, hz, ver)
    doc_env = _num(fvr.get("prearranged_usd_doc"))
    if doc_env is not None and before is not None and abs(before - doc_env) > 1:
        checks.append(f"envelope differs: DB had {before:,.0f}, document states {doc_env:,.0f}")
    summary = {
        "key": f"{kb}/{ver}", "countries": countries, "quality": quality,
        "valid_until_basis": (read.get("framework_version") or {}).get("valid_until_basis"),
        "db_envelope_before": before, "checks": checks,
        "partners_inserted": bool(have.empty and read.get("partners")),
        "identity_ok": (read.get("identity") or {}).get("matches_version"),
        "valid_from": vf,
        "valid_until": _date_end(fvr.get("valid_until")) or _date_end(fvr.get("valid_until_inferred")),
        "envelope": _num(fvr.get("prearranged_usd_doc")), "by_source": fm.get("funding_by_source"),
        "target_people": fm.get("target_people"), "n_windows": n_win, "n_funding_rows": n_fund,
        "n_sim": n_sim, "sim_dropped_after_start": dropped, "changes": changes,
        "partners_not_in_db": new_partners, "issues": read.get("issues") or [],
        "not_in_doc": read.get("not_in_doc") or [],
    }
    return rows, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--out", default=None)
    ap.add_argument("--summary", default=None)
    a = ap.parse_args()
    d = Path(a.dir)
    db = load(stratus.get_engine(stage="dev"))
    all_rows, sums = [], []
    for f in sorted(d.glob("*__*.json")):
        read = json.loads(f.read_text())
        mdf = d / (read.get("body_md_file") or f.with_suffix(".md").name)
        body = mdf.read_text() if mdf.exists() else None
        rows, s = convert(read, body, db)
        all_rows += rows
        sums.append(s)
        print(f"{s['key']}: {len(rows)} rows · windows {s['n_windows']} · funding {s['n_funding_rows']} · "
              f"sim {s['n_sim']} · changes {len(s['changes'])} · issues {len(s['issues'])} · checks {len(s['checks'])}")
    if a.out:
        Path(a.out).write_text(json.dumps(
            {"entered_by": f"full read of older framework documents ({SOURCE})", "rows": all_rows},
            ensure_ascii=False, indent=1, default=str))
        print(f"{len(all_rows)} rows -> {a.out}")
    if a.summary:
        Path(a.summary).write_text(json.dumps(sums, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
