"""Upsert-only sync: KB framework-page frontmatter -> aa.framework_version / registry.

DB-first era (2026-09-10): the dev DB is the single source of truth, so this is
deliberately narrow and NON-destructive —
  - INSERTS versions that exist as KB pages but not in aa.framework_version
    (source='kb-frontmatter'), and registry rows for brand-new frameworks;
  - UPDATES only kb-lineage fields (kb_framework, kb_status) on existing rows,
    plus fills doc_title / doc_url / valid_until(+source) / supersedes /
    prearranged_usd_doc ONLY where the DB value is NULL — human-entered and
    admin-page values always win;
  - never deletes anything.
Field-level changes are audited to aa.entry_audit as entered_by='sync-kb'.

The KB-side loaders (load_aa_performance.py / load_aa_cerf.py) keep owning
aa.window / aa.simulated_activation / aa.funding_breakdown / aa.actual_activation.

Usage: uv run python scripts/sync_kb.py [--dry-run]
"""

import os
import sys
from pathlib import Path

import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

os.environ.setdefault("PGSSLMODE", "require")

import ocha_stratus as stratus  # noqa: E402
import pandas as pd  # noqa: E402

from ds_aa_tracking.versions import kb_versions  # noqa: E402

FILL_IF_NULL = ["doc_title", "doc_url", "valid_until", "supersedes",
                "prearranged_usd_doc"]


def main():
    dry = "--dry-run" in sys.argv
    kb = kb_versions()
    if kb.empty:
        sys.exit("no KB pages found — is the ds-knowledge-base clone present?")
    engine = stratus.get_engine(stage="dev", write=True)
    db = pd.read_sql(
        """SELECT country_iso3, hazard, version, kb_framework, kb_status,
                  doc_title, doc_url, valid_until, valid_until_source,
                  supersedes, prearranged_usd_doc
           FROM aa.framework_version""", engine)
    db_keys = {(r.country_iso3, r.hazard, r.version) for r in db.itertuples()}
    db_by_key = {(r.country_iso3, r.hazard, r.version): r for r in db.itertuples()}
    reg = pd.read_sql("SELECT country_iso3, hazard FROM aa.framework_registry", engine)
    reg_keys = set(zip(reg["country_iso3"], reg["hazard"]))

    inserts, updates, audits, new_reg = [], [], [], []
    for _, k in kb.iterrows():
        key = (k["country_iso3"], k["hazard"], k["version"])
        if key not in db_keys:
            inserts.append({
                "country_iso3": k["country_iso3"], "hazard": k["hazard"],
                "version": k["version"], "kb_framework": k["kb_framework"],
                "kb_status": k["kb_status"], "valid_from": k["valid_from"],
                "valid_until": k["valid_until"],
                "valid_until_source": "doc-stated" if k["valid_until"] else None,
                "supersedes": k["supersedes"],
                "prearranged_usd_doc": k["prearranged_usd_doc"],
                "doc_url": k["doc_url"], "source": "kb-frontmatter",
            })
            if (k["country_iso3"], k["hazard"]) not in reg_keys:
                import pycountry
                c = pycountry.countries.get(alpha_3=k["country_iso3"])
                new_reg.append({
                    "country_iso3": k["country_iso3"], "hazard": k["hazard"],
                    "country_name": c.name if c else k["country_iso3"],
                    "kb_framework": k["kb_framework"], "in_kb": True,
                })
                reg_keys.add((k["country_iso3"], k["hazard"]))
            continue
        cur = db_by_key[key]
        sets, row_audits = {}, []
        for f in ("kb_framework", "kb_status"):  # kb lineage: KB always wins
            new = k[f]
            old = getattr(cur, f)
            if new is not None and pd.notna(new) and str(new) != str(old or ""):
                sets[f] = new
                row_audits.append((f, old, new))
        for f in FILL_IF_NULL:  # content: fill gaps only, never overwrite
            old = getattr(cur, f)
            new = k.get(f) if f in k.index else None
            if (old is None or pd.isna(old)) and new is not None and pd.notna(new):
                sets[f] = new
                row_audits.append((f, None, new))
                if f == "valid_until":
                    sets["valid_until_source"] = "doc-stated"
        if sets:
            updates.append((key, sets))
            audits.extend(("framework_version", "/".join(key), f, o, n)
                          for f, o, n in row_audits)

    print(f"KB pages: {len(kb)} · to insert: {len(inserts)} versions, "
          f"{len(new_reg)} registry rows · to update: {len(updates)} rows "
          f"({len(audits)} field changes)")
    if dry:
        for i in inserts:
            print("  + ", i["country_iso3"], i["hazard"], i["version"])
        for key, sets in updates:
            print("  ~ ", *key, "->", ", ".join(sets))
        return

    with engine.begin() as conn:
        for r in new_reg:
            conn.execute(sa.text(
                """INSERT INTO aa.framework_registry
                       (country_iso3, hazard, country_name, kb_framework, in_kb)
                   VALUES (:country_iso3, :hazard, :country_name, :kb_framework, :in_kb)
                   ON CONFLICT (country_iso3, hazard) DO NOTHING"""), r)
        for r in inserts:
            conn.execute(sa.text(
                """INSERT INTO aa.framework_version
                       (country_iso3, hazard, version, kb_framework, kb_status,
                        valid_from, valid_until, valid_until_source, supersedes,
                        prearranged_usd_doc, doc_url, source)
                   VALUES (:country_iso3, :hazard, :version, :kb_framework,
                           :kb_status, :valid_from, :valid_until,
                           :valid_until_source, :supersedes, :prearranged_usd_doc,
                           :doc_url, :source)
                   ON CONFLICT (country_iso3, hazard, version) DO NOTHING"""), r)
        for key, sets in updates:
            assign = ", ".join(f"{f} = :{f}" for f in sets)
            conn.execute(sa.text(
                f"""UPDATE aa.framework_version SET {assign}
                    WHERE country_iso3 = :_c AND hazard = :_h AND version = :_v"""),
                {**sets, "_c": key[0], "_h": key[1], "_v": key[2]})
        for t, rk, f, o, n in audits:
            conn.execute(sa.text(
                """INSERT INTO aa.entry_audit
                       (entered_by, table_name, row_key, field, old_value, new_value)
                   VALUES ('sync-kb', :t, :rk, :f, :o, :n)"""),
                {"t": t, "rk": rk, "f": f,
                 "o": None if o is None or pd.isna(o) else str(o),
                 "n": None if n is None or pd.isna(n) else str(n)})
    print("synced ✓")


if __name__ == "__main__":
    main()
