"""Framework page metadata, DB-first (2026-09-28).

Until the KB flip the site read each framework version's YAML frontmatter (geographic
scope, monitoring months, trigger facets, data sources, agencies, learning links) and
its "Trigger windows" table straight from the ds-knowledge-base clone. That made the
KB a source. It is not one any more: the pages were imported once into
``aa.version_page`` (2026-09-28) and are edited there; the KB reads this DB.
``load_version_pages`` is the one reader the site uses.
"""

import re

import pandas as pd

REST_RE = re.compile(r"all other|non-endemic|rest of|remaining|elsewhere", re.I)


def scope_tiers(front):
    """Tiers inside a block-form geographic_scope: a comment line on its own names a tier
    for the items that follow ('# riverine window — …'); an item such as 'Non-endemic
    provinces (all other)' is a REST tier covering everything not named. -> list of
    {label, items, rest}, or [] when the scope has no tiers."""
    m = re.search(r"^geographic_scope:[ \t]*\n((?:[ \t]+.*\n?)*)", front, re.M)
    if not m:
        return []
    tiers, cur = [], {"label": None, "items": [], "rest": False}
    for line in m.group(1).splitlines():
        st = line.strip()
        if not st:
            continue
        if st.startswith("#"):
            if cur["label"] is not None and not cur["items"]:
                continue                        # a header comment wrapped onto a second line
            label = re.split(r"\s+[—–-]{1,2}\s+|:", st.lstrip("# ").strip(), 1)[0].strip()
            if cur["items"] or cur["rest"]:
                tiers.append(cur)
            cur = {"label": label, "items": [], "rest": False}
            continue
        if not st.startswith("-"):
            continue
        item = st[1:].split("#", 1)[0].strip().strip("\"'")
        if REST_RE.search(item):
            if cur["items"]:
                tiers.append(cur)
                cur = {"label": None, "items": [], "rest": False}
            lab = re.sub(r"\s*\(all other\)\s*", "", item, flags=re.I).strip()
            tiers.append({"label": lab, "items": [], "rest": True})
            continue
        cur["items"].append(item)
    if cur["items"] or cur["rest"]:
        tiers.append(cur)
    if len(tiers) < 2:
        return []
    # an unlabelled tier next to a 'non-X' rest tier is the 'X' tier
    for t in tiers:
        if t["label"] is None:
            rest = next((r for r in tiers if r["rest"] and r["label"]), None)
            t["label"] = (re.sub(r"^non-?\s*", "", rest["label"], flags=re.I) if rest
                          and re.match(r"non-?", rest["label"], re.I) else "named areas")
    return tiers


def load_version_pages(engine):
    """(kb_framework, version) -> {fm, triggers, tiers} from aa.version_page."""
    df = pd.read_sql(
        "SELECT kb_framework, version, frontmatter, triggers, tiers FROM aa.version_page",
        engine)
    return {(r.kb_framework, str(r.version)): {"fm": r.frontmatter or {},
                                              "triggers": r.triggers or [],
                                              "tiers": r.tiers or []}
            for r in df.itertuples()}
