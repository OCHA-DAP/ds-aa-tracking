"""Load the partner organisations extracted from the endorsed framework documents into
aa.framework_partner.

Input: a JSON list of {slug, version, name, acronym, type, role[], agency_parent,
amount_usd, evidence} (one row per organisation per document; the extraction reads the
raw text of each framework document). Rows are keyed to (country_iso3, hazard, version)
through aa.framework_version.kb_framework = slug; a regional framework (several
countries) gets one row per country. Upsert on the primary key; rows curated by hand
(source='entered') are never overwritten.

Usage: uv run python scripts/import_partners.py framework_partners.json [--dry-run]
"""

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
os.environ.setdefault("PGSSLMODE", "require")

import ocha_stratus as stratus  # noqa: E402

TYPES = {"government", "un", "ingo", "nngo", "rcrc", "donor", "academic", "private", "other"}
ROLES = {"implementing", "sub_grantee", "technical", "coordination", "government_counterpart",
         "funding"}


def main():
    path = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
    dry = "--dry-run" in sys.argv
    src = f"doc-extract-{dt.date.today().isoformat()}"
    items = json.loads(Path(path).read_text())
    engine = stratus.get_engine(stage="dev", write=True)
    fv = pd.read_sql("SELECT country_iso3, hazard, version, kb_framework FROM aa.framework_version"
                     " WHERE kb_framework IS NOT NULL", engine)
    ch = pd.read_sql("SELECT country_iso3, hazard, kb_framework FROM aa.country_hazard"
                     " WHERE kb_framework IS NOT NULL", engine)
    by_slug_ver = {}
    for r in fv.itertuples():
        by_slug_ver.setdefault((r.kb_framework, str(r.version)), []).append((r.country_iso3, r.hazard))
    by_slug = {}
    for r in ch.itertuples():
        by_slug.setdefault(r.kb_framework, []).append((r.country_iso3, r.hazard))
    rows, unmatched, seen = [], set(), set()
    for it in items:
        slug, ver = it.get("slug"), str(it.get("version"))
        pairs = by_slug_ver.get((slug, ver)) or by_slug.get(slug)
        if not pairs:
            unmatched.add(slug)
            continue
        name = re.sub(r"\s+", " ", (it.get("name") or "")).strip()
        if not name:
            continue
        typ = (it.get("type") or "other").lower()
        roles = [r for r in (it.get("role") or []) if r in ROLES]
        for c, h in pairs:
            key = (c, h, ver, name.lower())
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "country_iso3": c, "hazard": h, "version": ver, "name": name,
                "acronym": it.get("acronym") or None,
                "org_type": typ if typ in TYPES else "other", "roles": roles,
                "agency_parent": it.get("agency_parent") or None,
                "amount_usd": it.get("amount_usd"), "evidence": (it.get("evidence") or None),
                "source": src,
            })
    print(f"{len(items)} extracted rows -> {len(rows)} partner rows; "
          f"unmatched slugs: {sorted(unmatched) or 'none'}")
    if dry:
        return
    with engine.begin() as conn:
        for r in rows:
            conn.execute(sa.text("""
                INSERT INTO aa.framework_partner (country_iso3, hazard, version, name, acronym,
                    org_type, roles, agency_parent, amount_usd, evidence, source)
                VALUES (:country_iso3, :hazard, :version, :name, :acronym, :org_type, :roles,
                    :agency_parent, :amount_usd, :evidence, :source)
                ON CONFLICT (country_iso3, hazard, version, name, source) DO UPDATE SET
                    acronym = EXCLUDED.acronym, org_type = EXCLUDED.org_type,
                    roles = EXCLUDED.roles, agency_parent = EXCLUDED.agency_parent,
                    amount_usd = EXCLUDED.amount_usd, evidence = EXCLUDED.evidence,
                    updated_at = now()"""), r)
    print(f"imported ✓ (source={src})")


if __name__ == "__main__":
    main()
