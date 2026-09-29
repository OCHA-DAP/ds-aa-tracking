"""ONE-TIME import of the knowledge-base framework pages into aa.version_page.

KB flip (2026-09-28): the knowledge base stops being a source for the tracking system.
Everything the site read from a framework page's frontmatter now lives in
aa.version_page and is edited there (admin page). This script is the last sweep: it
upserts every frameworks/<slug>/<version>.md page's frontmatter, "Trigger windows"
table, scope tiers and body. Re-running it never overwrites a row that has been edited
since import (source <> 'kb-import-*') unless --force.

Usage: KB_DIR=~/OCHA/repos/ds-knowledge-base uv run python scripts/import_kb_pages.py [--dry-run] [--force]
"""

import datetime as dt
import json
import os
import sys
from pathlib import Path

import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
os.environ.setdefault("PGSSLMODE", "require")

import ocha_stratus as stratus  # noqa: E402

from ds_aa_tracking.kb_pages import parse_page  # noqa: E402
from ds_aa_tracking.normalize import norm_hazard  # noqa: E402
from ds_aa_tracking.versions import KB_DIR  # noqa: E402


def main():
    dry, force = "--dry-run" in sys.argv, "--force" in sys.argv
    src = f"kb-import-{dt.date.today().isoformat()}"
    rows = []
    for pg in sorted(KB_DIR.glob("frameworks/*/[0-9]*.md")):
        p = parse_page(pg.read_text())
        if not p or p["fm"].get("content_type") != "framework":
            continue
        fm = p["fm"]
        iso = fm.get("country_iso3")
        iso = [iso.strip()] if isinstance(iso, str) else [str(x).strip() for x in (iso or [])]
        hazard, _ = norm_hazard(fm.get("hazard"))
        rows.append({
            "kb_framework": fm.get("framework") or pg.parent.name,
            "version": str(fm.get("version") or pg.stem),
            "country_iso3": iso, "hazard": hazard,
            "frontmatter": json.dumps(fm, default=str), "frontmatter_text": p["fm_text"],
            "triggers": json.dumps(p["triggers"]), "tiers": json.dumps(p["tiers"]),
            "body_md": p["body"], "source": src,
        })
    print(f"{len(rows)} framework pages under {KB_DIR}")
    if dry:
        for r in rows:
            print("  ", r["kb_framework"], r["version"], r["country_iso3"], r["hazard"])
        return
    engine = stratus.get_engine(stage="dev", write=True)
    guard = "" if force else "WHERE aa.version_page.source LIKE 'kb-import-%'"
    with engine.begin() as conn:
        for r in rows:
            conn.execute(sa.text(f"""
                INSERT INTO aa.version_page (kb_framework, version, country_iso3, hazard,
                    frontmatter, frontmatter_text, triggers, tiers, body_md, source)
                VALUES (:kb_framework, :version, :country_iso3, :hazard,
                    CAST(:frontmatter AS jsonb), :frontmatter_text, CAST(:triggers AS jsonb),
                    CAST(:tiers AS jsonb), :body_md, :source)
                ON CONFLICT (kb_framework, version) DO UPDATE SET
                    country_iso3 = EXCLUDED.country_iso3, hazard = EXCLUDED.hazard,
                    frontmatter = EXCLUDED.frontmatter, frontmatter_text = EXCLUDED.frontmatter_text,
                    triggers = EXCLUDED.triggers, tiers = EXCLUDED.tiers,
                    body_md = EXCLUDED.body_md, source = EXCLUDED.source, updated_at = now()
                {guard}"""), r)
    print(f"imported ✓ (source={src})")


if __name__ == "__main__":
    main()
