"""Load learning products into aa.learning_document from a JSON list (the parsed AA
Compendium of Available Resources, Sept 2026, plus the website to-add list).

Dedupes on the cleaned url (Outlook safelinks unwrapped, tracking query strings dropped)
and, where the url is a known placeholder, on the normalised title. Upsert on (url, title):
re-running with a corrected file updates rows; rows edited by hand (source='entered')
are never overwritten.

Usage: uv run python scripts/import_learning.py learning_docs.json [--dry-run]
"""

import json
import os
import re
import sys
import urllib.parse as up
from pathlib import Path

import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
os.environ.setdefault("PGSSLMODE", "require")

import ocha_stratus as stratus  # noqa: E402

PLACEHOLDER = ("documentcloud.adobe.com/spodintegration",)
TRACKING = {"_gl", "_ga", "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"}


def clean_url(u):
    if not u:
        return None
    u = u.strip()
    p = up.urlparse(u)
    if "safelinks.protection.outlook.com" in p.netloc:
        inner = up.parse_qs(p.query).get("url", [None])[0]
        if inner:
            return clean_url(inner)
    q = [(k, v) for k, v in up.parse_qsl(p.query, keep_blank_values=True) if k not in TRACKING]
    return up.urlunparse(p._replace(query=up.urlencode(q), fragment=""))


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def main():
    path = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
    dry = "--dry-run" in sys.argv
    docs = json.loads(Path(path).read_text())
    seen, rows, dropped = {}, [], 0
    for d in docs:
        url = clean_url(d.get("url"))
        key = ("t", norm_title(d["title"])) if (not url or any(x in url for x in PLACEHOLDER)) \
            else ("u", url.lower().rstrip("/"))
        if key in seen:      # keep the first (compendium order), but fill gaps from the twin
            prev = seen[key]
            for f in ("publisher", "year", "key_stat", "summary"):
                if prev.get(f) in (None, "") and d.get(f):
                    prev[f] = d[f]
            if not prev.get("premises") and d.get("premises"):
                prev["premises"] = d["premises"]
            dropped += 1
            continue
        iso = d.get("country_iso3")
        iso = [iso] if isinstance(iso, str) else (iso or None)
        row = {
            "title": d["title"].strip(), "url": url, "publisher": d.get("publisher"),
            "year": d.get("year"), "doc_type": d.get("doc_type") or "other",
            "scope": d.get("scope") or ("country" if iso else "global"),
            "country_iso3": iso, "hazard": d.get("hazard"),
            "premises": d.get("premises") or [], "key_stat": d.get("key_stat"),
            "summary": d.get("summary"), "internal": bool(d.get("internal")),
            "section": d.get("section"), "source": d.get("source") or "import",
        }
        seen[key] = row
        rows.append(row)
    print(f"{len(docs)} entries -> {len(rows)} documents ({dropped} duplicates merged); "
          f"{sum(r['internal'] for r in rows)} internal, "
          f"{sum(r['scope'] == 'global' for r in rows)} global")
    if dry:
        return
    engine = stratus.get_engine(stage="dev", write=True)
    with engine.begin() as conn:
        for r in rows:
            conn.execute(sa.text("""
                INSERT INTO aa.learning_document (title, url, publisher, year, doc_type, scope,
                    country_iso3, hazard, premises, key_stat, summary, internal, section, source)
                VALUES (:title, :url, :publisher, :year, :doc_type, :scope, :country_iso3, :hazard,
                    :premises, :key_stat, :summary, :internal, :section, :source)
                ON CONFLICT (url, title) DO UPDATE SET
                    publisher = EXCLUDED.publisher, year = EXCLUDED.year,
                    doc_type = EXCLUDED.doc_type, scope = EXCLUDED.scope,
                    country_iso3 = EXCLUDED.country_iso3, hazard = EXCLUDED.hazard,
                    premises = EXCLUDED.premises, key_stat = EXCLUDED.key_stat,
                    summary = EXCLUDED.summary, internal = EXCLUDED.internal,
                    section = EXCLUDED.section, source = EXCLUDED.source, updated_at = now()
                WHERE aa.learning_document.source <> 'entered'"""), r)
    print("imported ✓")


if __name__ == "__main__":
    main()
