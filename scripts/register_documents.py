"""Register framework documents: archive the file in the dev blob, record its content hash
in aa.framework_document and link it to its version(s) in aa.version_document.

The DB says WHICH FILE is a version's document; publication stays with OCHA (unocha.org /
ReliefWeb) and official_url points there. Files are content-addressed
(projects/ds-aa-tracking/raw/framework_documents/<sha256>.pdf), so re-registering the
same bytes is a no-op and a document shared by several versions is stored once.

Two modes:
  backfill (default) — every PDF in the knowledge base's committed cache,
      ds-knowledge-base/raw/.pdf-cache/<kb_framework>/<version>.pdf, matched to
      aa.framework_version on (kb_framework, version) — ALL matching rows, so the Dry
      Corridor's one file links to SLV, GTM and HND. A cached file was fetched from the
      version's doc_url, so it registers as the PUBLISHED rendition, public.
  --register FILE --key ISO3/hazard/version [--key …] — one file by hand: versions whose
      official page is WAF-blocked or gone, or an endorsed original that arrived by email
      (--role endorsed). --private keeps it off the public site and the KB.

Dry run by default, reading aa.framework_version from the nightly blob snapshot (no DB
route needed). --write reads and writes the live dev DB — from a laptop that is the SSH
tunnel (`~/bin/db-tunnel up` + the DSCI_AZ_DB_DEV_HOST override) — creates the two tables
if missing, uploads to blob, then inserts in one transaction (ON CONFLICT DO NOTHING).

Usage:
  uv run python scripts/register_documents.py                       # dry run, backfill
  uv run python scripts/register_documents.py --write
  uv run python scripts/register_documents.py --register afg.pdf --key AFG/drought/2026-04-04
  uv run python scripts/register_documents.py --register lac.pdf --key SLV/drought/2024-03-22 \\
      --key GTM/drought/2024-03-22 --key HND/drought/2024-03-22 --retrieved-from <url> --write
"""

import argparse
import getpass
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import sqlalchemy as sa
from azure.core.exceptions import ResourceNotFoundError

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
os.environ.setdefault("PGSSLMODE", "require")

import ocha_stratus as stratus  # noqa: E402

from ds_aa_tracking import schema, snapshot  # noqa: E402
from ds_aa_tracking.versions import KB_DIR  # noqa: E402

CONTAINER = "projects"
PREFIX = "ds-aa-tracking/raw/framework_documents"
PDF_CACHE = KB_DIR / "raw" / ".pdf-cache"
ROLES = ("endorsed", "published", "translation", "annex")
DOC_COLS = [
    "sha256",
    "blob_path",
    "bytes",
    "title",
    "language",
    "is_public",
    "official_url",
    "retrieved_from",
    "retrieved_at",
    "registered_by",
    "source",
    "note",
]


def blob_path(sha):
    return f"{PREFIX}/{sha}.pdf"


def read_pdf(path):
    data = Path(path).read_bytes()
    if not data.startswith(b"%PDF"):
        sys.exit(f"not a PDF: {path}")
    return data, hashlib.sha256(data).hexdigest()


def from_snapshot(table):
    """One aa table from the nightly snapshot (latest/), or None if it isn't in it yet."""
    name = f"{snapshot.PREFIX}/latest/{snapshot.SCHEMA}/{table}.parquet"
    try:
        data = stratus.load_blob_data(name, stage="dev", container_name=snapshot.CONTAINER)
    except ResourceNotFoundError:
        return None
    return pd.read_parquet(io.BytesIO(data))


def from_db(conn, table):
    if conn.execute(sa.text("SELECT to_regclass(:t)"), {"t": f"aa.{table}"}).scalar() is None:
        return None
    return pd.read_sql(sa.text(f"SELECT * FROM aa.{table}"), conn)


def language_of(fm):
    """The page's document language, or None when it lists several (a bilingual version's
    cached file is one of them, and which one was never recorded)."""
    if isinstance(fm, str):
        fm = json.loads(fm)
    langs = (fm or {}).get("languages") or []
    return langs[0] if len(langs) == 1 else None


def first_cached(pdf):
    """When the file was first committed to the KB cache (≈ when it was fetched)."""
    out = subprocess.run(
        [
            "git",
            "-C",
            str(KB_DIR),
            "log",
            "--diff-filter=A",
            "--format=%cI",
            "--",
            str(pdf.relative_to(KB_DIR)),
        ],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    return out[-1] if out else None


def _first(s):
    s = s.dropna()
    return s.iloc[0] if len(s) else None


def plan_backfill(fv, vp):
    """(docs, links, unmatched, ambiguous) for every PDF in the KB cache.

    One file cached under two versions is ambiguous, and neither is registered: the cache
    is keyed by page, fetched once and kept forever, so when a page's doc URL is corrected
    the stale file stays (bgd-flooding 2020-06-26 holds the 2021 framework). Register the
    right one by hand with --register."""
    lang = (
        {}
        if vp is None
        else {(r.kb_framework, r.version): language_of(r.frontmatter) for r in vp.itertuples()}
    )
    cached = {pdf: read_pdf(pdf) for pdf in sorted(PDF_CACHE.glob("*/*.pdf"))}
    paths_by_sha = {}
    for pdf, (_, sha) in cached.items():
        paths_by_sha.setdefault(sha, []).append(f"{pdf.parent.name}/{pdf.stem}")
    ambiguous = [p for p in paths_by_sha.values() if len(p) > 1]
    docs, links, unmatched = {}, [], []
    for pdf, (data, sha) in cached.items():
        fw, ver = pdf.parent.name, pdf.stem
        if len(paths_by_sha[sha]) > 1:
            continue
        rows = fv[(fv.kb_framework == fw) & (fv.version == ver)]
        if rows.empty:
            unmatched.append((fw, ver, sorted(fv.loc[fv.kb_framework == fw, "version"])))
            continue
        urls = list(rows.doc_url.dropna().unique())
        note = f"ds-knowledge-base raw/.pdf-cache/{fw}/{ver}.pdf"
        if len(urls) > 1:
            note += "; also published at " + ", ".join(urls[1:])
        docs.setdefault(
            sha,
            dict(
                sha256=sha,
                data=data,
                title=_first(rows.doc_title),
                language=lang.get((fw, ver)),
                is_public=True,
                official_url=urls[0] if urls else None,
                retrieved_from=urls[0] if urls else None,
                retrieved_at=first_cached(pdf),
                source="kb-pdf-cache",
                note=note,
            ),
        )
        links += [
            dict(
                country_iso3=r.country_iso3,
                hazard=r.hazard,
                version=r.version,
                sha256=sha,
                role="published",
                note=None,
            )
            for r in rows.itertuples()
        ]
    return docs, links, unmatched, ambiguous


def plan_register(args, fv):
    data, sha = read_pdf(args.register)
    links, rows = [], []
    for key in args.key:
        iso3, hazard, version = key.split("/", 2)
        r = fv[(fv.country_iso3 == iso3) & (fv.hazard == hazard) & (fv.version == version)]
        if r.empty:
            sys.exit(f"no aa.framework_version row {key}")
        rows.append(r.iloc[0])
        links.append(
            dict(
                country_iso3=iso3,
                hazard=hazard,
                version=version,
                sha256=sha,
                role=args.role,
                note=args.note,
            )
        )
    rows = pd.DataFrame(rows)
    official = (
        None
        if args.private
        else (args.official_url or (_first(rows.doc_url) if args.role == "published" else None))
    )
    doc = dict(
        sha256=sha,
        data=data,
        title=args.title or _first(rows.doc_title),
        language=args.language,
        is_public=not args.private,
        official_url=official,
        retrieved_from=args.retrieved_from,
        retrieved_at=None,
        source="entered",
        note=args.note,
    )
    return {sha: doc}, links


def write(engine, docs, links, by):
    with engine.begin() as conn:
        for t in ("framework_document", "version_document"):
            conn.execute(sa.text(schema.TABLES[t]))
    for d in docs.values():  # blob first: a DB row never points at a missing file
        stratus.upload_blob_data(
            d["data"],
            blob_path(d["sha256"]),
            stage="dev",
            container_name=CONTAINER,
            content_type="application/pdf",
        )
    rows = [
        {
            **{k: d.get(k) for k in DOC_COLS},
            "blob_path": blob_path(d["sha256"]),
            "bytes": len(d["data"]),
            "registered_by": by,
        }
        for d in docs.values()
    ]
    with engine.begin() as conn:
        if rows:
            conn.execute(
                sa.text(f"""
                INSERT INTO aa.framework_document ({", ".join(DOC_COLS)})
                VALUES ({
                    ", ".join(
                        f"CAST(:{c} AS timestamptz)" if c == "retrieved_at" else f":{c}"
                        for c in DOC_COLS
                    )
                })
                ON CONFLICT (sha256) DO NOTHING"""),
                rows,
            )
        if links:
            conn.execute(
                sa.text("""
                INSERT INTO aa.version_document (country_iso3, hazard, version, sha256, role, note)
                VALUES (:country_iso3, :hazard, :version, :sha256, :role, :note)
                ON CONFLICT DO NOTHING"""),
                links,
            )


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true", help="upload + insert (default: dry run)")
    ap.add_argument("--register", metavar="FILE", help="register one file by hand")
    ap.add_argument("--key", action="append", default=[], help="ISO3/hazard/version (repeatable)")
    ap.add_argument("--role", choices=ROLES, default="published")
    ap.add_argument("--private", action="store_true", help="not public: never on the site or KB")
    ap.add_argument(
        "--official-url", help="publication landing page (default: the version's doc_url)"
    )
    ap.add_argument("--retrieved-from", help="where the file came from (URL, 'email from …')")
    ap.add_argument("--language", choices=("en", "fr", "es"))
    ap.add_argument("--title")
    ap.add_argument("--note")
    ap.add_argument("--by", default=getpass.getuser(), help="registered_by")
    args = ap.parse_args()
    if bool(args.register) != bool(args.key):
        ap.error("--register and --key go together")

    engine = stratus.get_engine(stage="dev", write=True) if args.write else None
    if engine is not None:
        with engine.connect() as conn:
            fv, vp = from_db(conn, "framework_version"), from_db(conn, "version_page")
            known_docs, known_links = (
                from_db(conn, "framework_document"),
                from_db(conn, "version_document"),
            )
    else:
        fv, vp = from_snapshot("framework_version"), from_snapshot("version_page")
        known_docs, known_links = (
            from_snapshot("framework_document"),
            from_snapshot("version_document"),
        )

    if args.register:
        docs, links = plan_register(args, fv)
        unmatched, ambiguous = [], []
    else:
        docs, links, unmatched, ambiguous = plan_backfill(fv, vp)

    have = set() if known_docs is None else set(known_docs.sha256)
    linked = (
        set()
        if known_links is None
        else set(
            zip(
                known_links.country_iso3,
                known_links.hazard,
                known_links.version,
                known_links.sha256,
            )
        )
    )
    docs = {s: d for s, d in docs.items() if s not in have}
    links = [
        x
        for x in links
        if (x["country_iso3"], x["hazard"], x["version"], x["sha256"]) not in linked
    ]

    mb = sum(len(d["data"]) for d in docs.values()) / 1e6
    print(f"{len(docs)} new documents ({mb:.1f} MB), {len(links)} new version links")
    for x in links:
        print(
            f"  + {x['country_iso3']}/{x['hazard']}/{x['version']}  "
            f"{x['sha256'][:12]}  {x['role']}"
        )
    for fw, ver, db_versions in unmatched:
        print(
            f"  ? cached {fw}/{ver}.pdf matches no version "
            f"(DB has {', '.join(db_versions) or 'none'})"
        )
    for paths in ambiguous:
        print(
            f"  ! one file cached as {' and '.join(paths)} — skipped, "
            "register the right one by hand"
        )
    if not args.register:
        covered = linked | {(x["country_iso3"], x["hazard"], x["version"]) for x in links}
        covered = {k[:3] for k in covered}
        for r in (
            fv[fv.doc_url.notna()].sort_values(["country_iso3", "hazard", "version"]).itertuples()
        ):
            if (r.country_iso3, r.hazard, r.version) not in covered:
                print(f"  - no file for {r.country_iso3}/{r.hazard}/{r.version}: {r.doc_url}")

    if args.write:
        write(engine, docs, links, args.by)
        print("written")
    else:
        print("dry run — nothing written (--write to upload and insert)")


if __name__ == "__main__":
    main()
