"""Framework page metadata, DB-first (2026-09-28).

Until the KB flip the site read each framework version's YAML frontmatter (geographic
scope, monitoring months, trigger facets, data sources, agencies, learning links) and
its "Trigger windows" table straight from the ds-knowledge-base clone. That made the
KB a source. It is not one any more: the pages were imported once into
``aa.version_page`` (scripts/import_kb_pages.py) and are edited there; the KB reads
this DB. ``load_version_pages`` is the one reader the site uses; ``parse_page`` is the
importer's parser (kept here so a re-import stays byte-for-byte the old behaviour).
"""

import re

import pandas as pd
import yaml

REST_RE = re.compile(r"all other|non-endemic|rest of|remaining|elsewhere", re.I)


def parse_page(text):
    """Markdown page -> {fm, fm_text, triggers, tiers, body} or None (no frontmatter)."""
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    trig = []
    t = re.search(r"^## Trigger windows\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if t:
        rows = [ln for ln in t.group(1).splitlines() if ln.strip().startswith("|")]
        if len(rows) >= 3:
            hdr = [h.strip().lower() for h in rows[0].strip().strip("|").split("|")]
            for ln in rows[2:]:
                cells = [c.strip() for c in ln.strip().strip("|").split("|")]
                if len(cells) != len(hdr) or all(not c or c.startswith("e.g.") for c in cells):
                    continue
                trig.append({h: re.sub(r"\*\*(.*?)\*\*", r"\1", c) for h, c in zip(hdr, cells)})
    return {"fm": fm, "fm_text": m.group(1), "triggers": trig,
            "tiers": scope_tiers(m.group(1)), "body": text[m.end():].lstrip("\n")}


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
