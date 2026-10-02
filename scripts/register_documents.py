"""Register framework documents: archive the file in the dev blob, record its content hash
in aa.framework_document and link it to its version(s) in aa.version_document.

The DB says WHICH FILE is a version's document; publication stays with OCHA (unocha.org /
ReliefWeb) and the link's official_url points there. Files are content-addressed
(projects/ds-aa-tracking/raw/framework_documents/<sha256>.pdf), so re-registering the
same bytes is a no-op and a document shared by several versions is stored once.

Two modes:
  backfill (default) — the PDFs in the knowledge base's committed cache,
      ds-knowledge-base/raw/.pdf-cache/<kb_framework>/<version>.pdf, matched to
      aa.framework_version on (kb_framework, version) — ALL matching rows, so the Dry
      Corridor's one file links to SLV, GTM and HND — as the PUBLISHED rendition. The
      cache is keyed by page, fetched once and kept forever, so a cached file is only
      trusted when the URL it was fetched from (the page's framework_doc at the commit
      that cached it) is the version's doc_url today, or a direct PDF link on the same
      publisher. Skipped and reported otherwise: the version has no document link (the
      ken-drought cache is an IFRC EAP, not an OCHA framework), the page's link changed
      after the fetch, or one file is cached under two versions (bgd-flooding 2020-06-26
      holds the 2021 framework).
  --register FILE --key ISO3/hazard/version [--key …] — one file by hand: versions whose
      official page is WAF-blocked or gone, or an endorsed original that arrived by email
      (--role endorsed). --private keeps it off the public site and the KB.
      --supersedes SHA marks the file this one replaces (same keys) as superseded;
      --update corrects an already-registered file or link instead of refusing.

Dry run by default, reading aa.framework_version and the registry from the nightly blob
snapshot (no DB route needed). Two ways to write:
  --entries — the laptop path (laptops have no DB route since 2026-09-30): uploads the files
      to blob, then an entries file to projects/ds-aa-tracking/entries/ that the nightly
      Databricks job applies once, in order, in one transaction (scripts/apply_entries.py).
      The tables must exist: ship them with a one-off job run with --ensure-schema.
  --write — straight to the dev DB, for anything that has a route to it: creates the two
      tables if missing, uploads to blob, then writes in one transaction.

Usage:
  uv run python scripts/register_documents.py                       # dry run, backfill
  uv run python scripts/register_documents.py --write
  uv run python scripts/register_documents.py --register afg.pdf --key AFG/drought/2026-04-04 \\
      --retrieved-from <url>
  uv run python scripts/register_documents.py --register lac.pdf --key SLV/drought/2024-03-22 \\
      --key GTM/drought/2024-03-22 --key HND/drought/2024-03-22 --retrieved-from <url> --write
"""

import argparse
import datetime as dt
import getpass
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import urllib.parse as up
from pathlib import Path

import pandas as pd
import sqlalchemy as sa
import yaml
from azure.core.exceptions import ResourceNotFoundError

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
os.environ.setdefault("PGSSLMODE", "require")

import ocha_stratus as stratus  # noqa: E402

from ds_aa_tracking import schema, snapshot  # noqa: E402
from ds_aa_tracking.versions import KB_DIR  # noqa: E402

CONTAINER = "projects"
PREFIX = "ds-aa-tracking/raw/framework_documents"
ENTRIES = "ds-aa-tracking/entries"  # applied by the nightly job (scripts/apply_entries.py)
PDF_CACHE = KB_DIR / "raw" / ".pdf-cache"
PUBLISHERS = ("reliefweb.int", "unocha.org")
ROLES = ("endorsed", "published", "translation", "annex")
KEY = ["country_iso3", "hazard", "version", "sha256"]
DOC_COLS = [
    "sha256",
    "blob_path",
    "bytes",
    "title",
    "language",
    "is_public",
    "retrieved_from",
    "retrieved_at",
    "registered_by",
    "source",
    "note",
]
LINK_COLS = [*KEY, "role", "official_url", "note"]
SINGLE_ROLES = ("endorsed", "published")  # one CURRENT file per version (unique index)
CURRENT_IDX = next(i for i in schema.INDEXES if "version_document_current_uniq" in i)


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


def _kb_git(*args):
    return subprocess.run(
        ["git", "-C", str(KB_DIR), *args], capture_output=True, text=True, check=False
    ).stdout


def cache_provenance(pdf):
    """(commit, date, url): the KB commit that first cached the file, and the page's
    framework_doc AT THAT COMMIT — the URL the bytes were actually fetched from. Today's
    doc_url can differ: pages get corrected after the fetch, the cache never does."""
    rel = pdf.relative_to(KB_DIR).as_posix()
    added = _kb_git("log", "--diff-filter=A", "--format=%H %cs", "--", rel).split()
    if not added:
        return None, None, None
    commit, date = added[-2], added[-1]
    page = _kb_git("show", f"{commit}:frameworks/{pdf.parent.name}/{pdf.stem}.md")
    m = re.match(r"^---\n(.*?)\n---", page, re.S)
    try:
        fm = (yaml.safe_load(m.group(1)) if m else None) or {}
    except yaml.YAMLError:
        fm = {}
    return commit[:8], date, fm.get("framework_doc")


def is_direct_pdf(url):
    """A publisher's direct PDF link (…/attachments/….pdf) rather than a landing page."""
    p = up.urlparse(url)
    return p.netloc.endswith(PUBLISHERS) and (
        "/attachments/" in p.path or p.path.lower().endswith(".pdf")
    )


def report_slug(url):
    """(country, slug) of a publication page on either publisher — unocha.org
    /publications/report/<country>/<slug> is mirrored on reliefweb.int/report/<country>/<slug>,
    so the same pair on the other host is the same report."""
    p = up.urlparse(url)
    parts = [x for x in p.path.split("/") if x]
    if p.netloc.endswith(PUBLISHERS) and len(parts) >= 3 and parts[-3] == "report":
        return tuple(parts[-2:])
    return None


def _first(s):
    s = s.dropna()
    return s.iloc[0] if len(s) else None


def _none(v):
    return None if v is None or (not isinstance(v, str | bool) and pd.isna(v)) else v


def plan_backfill(fv, vp):
    """(docs, links, report, held) for the PDFs in the KB cache; report = {kind: [lines]};
    held = {sha: "fw/ver"} registered only on a heuristic (direct link / publisher mirror).
    A version whose page lists framework_doc_annexes comes in several documents (the Dry
    Corridor's 2026 page links Guatemala's national framework, with El Salvador's and
    Honduras's as annexes), so which one the cached file is can't be told: skipped, and
    registered per country by hand."""
    fms = (
        {} if vp is None else {(r.kb_framework, r.version): r.frontmatter for r in vp.itertuples()}
    )
    fms = {k: json.loads(v) if isinstance(v, str) else (v or {}) for k, v in fms.items()}
    cached = {pdf: read_pdf(pdf) for pdf in sorted(PDF_CACHE.glob("*/*.pdf"))}
    paths_by_sha = {}
    for pdf, (_, sha) in cached.items():
        paths_by_sha.setdefault(sha, []).append(f"{pdf.parent.name}/{pdf.stem}")
    docs, links, held = {}, [], {}
    report = {"skipped": [], "check": []}
    for paths in paths_by_sha.values():
        if len(paths) > 1:
            report["skipped"].append(f"one file cached as {' and '.join(paths)}")
    for pdf, (data, sha) in cached.items():
        fw, ver = pdf.parent.name, pdf.stem
        if len(paths_by_sha[sha]) > 1:
            continue
        if fms.get((fw, ver), {}).get("framework_doc_annexes"):
            report["skipped"].append(
                f"{fw}/{ver}: the version comes in several documents (framework_doc_annexes) "
                "— register each by hand"
            )
            continue
        rows = fv[(fv.kb_framework == fw) & (fv.version == ver)]
        if rows.empty:
            versions = ", ".join(sorted(fv.loc[fv.kb_framework == fw, "version"])) or "none"
            report["skipped"].append(f"{fw}/{ver}: matches no version (DB has {versions})")
            continue
        urls = set(rows.doc_url.dropna())
        if not urls:
            report["skipped"].append(
                f"{fw}/{ver}: the version has no document link — not an OCHA-published "
                "framework document?"
            )
            continue
        commit, date, fetched = cache_provenance(pdf)
        if not fetched:
            report["skipped"].append(f"{fw}/{ver}: can't tell which URL the file came from")
            continue
        if fetched not in urls:
            mirror = report_slug(fetched) and report_slug(fetched) in map(report_slug, urls)
            if not (mirror or is_direct_pdf(fetched)):
                report["skipped"].append(
                    f"{fw}/{ver}: fetched from {fetched}, but the version's link is now "
                    f"{', '.join(sorted(urls))}"
                )
                continue
            how = "the same report on the other publisher" if mirror else "the direct link"
            report["check"].append(f"{fw}/{ver}: fetched from {how} {fetched}")
            held[sha] = f"{fw}/{ver}"
        docs.setdefault(
            sha,
            {
                "sha256": sha,
                "data": data,
                "title": _first(rows.doc_title),
                "language": language_of(fms.get((fw, ver))),
                "is_public": True,
                "retrieved_from": fetched,
                "retrieved_at": None,
                "source": "kb-pdf-cache",
                "note": f"ds-knowledge-base raw/.pdf-cache/{fw}/{ver}.pdf, cached {date} "
                f"({commit})",
            },
        )
        links += [
            {
                "country_iso3": r.country_iso3,
                "hazard": r.hazard,
                "version": r.version,
                "sha256": sha,
                "role": "published",
                "official_url": _none(r.doc_url),
                "note": None,
            }
            for r in rows.itertuples()
        ]
    return docs, links, report, held


def plan_register(args, fv):
    data, sha = read_pdf(args.register)
    links, titles = [], []
    for key in args.key:
        iso3, hazard, version = key.split("/", 2)
        r = fv[(fv.country_iso3 == iso3) & (fv.hazard == hazard) & (fv.version == version)]
        if r.empty:
            sys.exit(f"no aa.framework_version row {key}")
        r = r.iloc[0]
        titles.append(_none(r.doc_title))
        official = None
        if not args.private:
            official = args.official_url or (
                _none(r.doc_url) if args.role == "published" else None
            )
        links.append(
            {
                "country_iso3": iso3,
                "hazard": hazard,
                "version": version,
                "sha256": sha,
                "role": args.role,
                "official_url": official,
                "note": args.note,
            }
        )
    doc = {
        "sha256": sha,
        "data": data,
        "title": args.title or next((t for t in titles if t), None),
        "language": args.language,
        "is_public": not args.private,
        "retrieved_from": args.retrieved_from,
        "retrieved_at": args.retrieved_at,
        "source": "entered",
        "note": args.note,
    }
    return {sha: doc}, links


def split_known(docs, links, known_docs, known_links):
    """Split the plan into new rows and rows already registered DIFFERENTLY (a correction:
    never applied silently); rows already registered identically drop out. `taken` =
    new links whose version already has a CURRENT file in an endorsed/published role:
    (link, sha of that file) — replacing it needs --supersedes."""
    kd = None if known_docs is None else known_docs.set_index("sha256")
    kl = None if known_links is None else known_links.set_index(KEY)
    cur = {}
    if known_links is not None:
        live = known_links[known_links.superseded_by.isna()]
        for r in live[live.role.isin(SINGLE_ROLES)].itertuples():
            cur[(r.country_iso3, r.hazard, r.version, r.role)] = r.sha256
    new_docs, new_links, changed_docs, changed_links, diffs, taken = {}, [], {}, [], [], []
    for sha, d in docs.items():
        if kd is None or sha not in kd.index:
            new_docs[sha] = d
            continue
        old = kd.loc[sha]
        dd = [f"is_public {old['is_public']} → {d['is_public']}"] * (
            bool(old["is_public"]) != d["is_public"]
        ) + [
            f"{c} {_none(old[c])} → {d[c]}"
            for c in ("title", "language", "retrieved_from", "note")
            if d[c] is not None and _none(old[c]) != d[c]
        ]
        if dd:
            changed_docs[sha] = d
            diffs.append(f"{sha[:12]}: {'; '.join(dd)}")
    for x in links:
        k = tuple(x[c] for c in KEY)
        if kl is None or k not in kl.index:
            other = cur.get((*k[:3], x["role"]))
            if other and other != x["sha256"]:
                taken.append((x, other))
            else:
                new_links.append(x)
            continue
        old = kl.loc[k]
        d = [
            f"{c} {_none(old[c])} → {x[c]}"
            for c in ("role", "official_url")
            if _none(old[c]) != x[c]
        ]
        if d:
            changed_links.append(x)
            diffs.append(f"{'/'.join(k[:3])} {k[3][:12]}: {'; '.join(d)}")
    return new_docs, new_links, changed_docs, changed_links, diffs, taken


def upload_files(docs):
    for d in docs.values():  # blob first: a DB row never points at a missing file
        stratus.upload_blob_data(
            d["data"],
            blob_path(d["sha256"]),
            stage="dev",
            container_name=CONTAINER,
            content_type="application/pdf",
        )


def doc_row(d, by):
    return {
        **{k: d.get(k) for k in DOC_COLS},
        "blob_path": blob_path(d["sha256"]),
        "bytes": len(d["data"]),
        "registered_by": by,
    }


def _py(v):
    """JSON-safe scalar: numpy -> python, pandas NA -> None."""
    v = _none(v)
    return v.item() if hasattr(v, "item") else v


def write_entries(docs, links, by, changed_docs, changed_links, supersede, known):
    """Upload the files, then ONE entries file the nightly job applies in order in one
    transaction — documents, the links being superseded (before the new current link, for
    the unique index), new links, corrections. apply_entries upserts whole rows, so a
    correction is merged onto the stored row here, the same way write() updates it.
    Returns (blob name, number of rows)."""
    known_docs, known_links = known
    upload_files(docs)
    rows = [{"table": "framework_document", "row": doc_row(d, by)} for d in docs.values()]
    for sha, d in (changed_docs or {}).items():
        old = known_docs.set_index("sha256").loc[sha]
        row = {c: _py(old[c]) for c in DOC_COLS if c != "sha256"} | {"sha256": sha}
        row["is_public"] = d["is_public"]
        row |= {c: d[c] for c in ("title", "language", "retrieved_from", "note") if d[c]}
        rows.append({"table": "framework_document", "row": row})
    if supersede:
        old, new, keys, role = supersede
        live = known_links[known_links.superseded_by.isna()]
        for iso3, hazard, version in keys:
            r = live[
                (live.country_iso3 == iso3)
                & (live.hazard == hazard)
                & (live.version == version)
                & (live.sha256 == old)
                & (live.role == role)
            ]
            if len(r) != 1:  # an upsert would INSERT a phantom row: refuse instead
                sys.exit(
                    f"--supersedes: no current {role} {old[:12]} link on {iso3}/{hazard}/{version}"
                )
            row = {c: _py(r.iloc[0][c]) for c in LINK_COLS} | {"superseded_by": new}
            rows.append({"table": "version_document", "row": row})
    rows += [{"table": "version_document", "row": {c: x[c] for c in LINK_COLS}} for x in links]
    kl = None if known_links is None else known_links.set_index(KEY)
    for x in changed_links:
        old = kl.loc[tuple(x[c] for c in KEY)]
        row = {c: x[c] for c in LINK_COLS} | {"note": x["note"] or _py(old["note"])}
        rows.append({"table": "version_document", "row": row})
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    name = f"{ENTRIES}/{stamp}-register-documents.json"
    payload = {"entered_by": f"{by} via scripts/register_documents.py", "rows": rows}
    stratus.upload_blob_data(
        json.dumps(payload, indent=1, default=_py).encode(),
        name,
        stage="dev",
        container_name=CONTAINER,
        content_type="application/json",
    )
    return name, len(rows)


def write(engine, docs, links, by, changed_docs=None, changed_links=(), supersede=None):
    with engine.begin() as conn:
        for t in ("framework_document", "version_document"):
            conn.execute(sa.text(schema.DURABLE_TABLES[t]))
        conn.execute(sa.text(CURRENT_IDX))
    upload_files(docs)
    rows = [doc_row(d, by) for d in docs.values()]
    values = ", ".join(
        f"CAST(:{c} AS timestamptz)" if c == "retrieved_at" else f":{c}" for c in DOC_COLS
    )
    with engine.begin() as conn:
        if rows:
            conn.execute(
                sa.text(f"""
                INSERT INTO aa.framework_document ({", ".join(DOC_COLS)}) VALUES ({values})
                ON CONFLICT (sha256) DO NOTHING"""),
                rows,
            )
        if supersede:  # before the insert: one current file per role
            old, new, keys, role = supersede
            for iso3, hazard, version in keys:
                n = conn.execute(
                    sa.text("""
                    UPDATE aa.version_document SET superseded_by = :new
                    WHERE country_iso3 = :c AND hazard = :h AND version = :v
                      AND sha256 = :old AND role = :role AND superseded_by IS NULL"""),
                    {"new": new, "old": old, "c": iso3, "h": hazard, "v": version, "role": role},
                ).rowcount
                if n != 1:  # raising rolls the whole transaction back
                    raise SystemExit(
                        f"--supersedes: no current {role} {old[:12]} link on "
                        f"{iso3}/{hazard}/{version}"
                    )
        if links:
            conn.execute(
                sa.text(f"""
                INSERT INTO aa.version_document ({", ".join(LINK_COLS)})
                VALUES ({", ".join(":" + c for c in LINK_COLS)})
                ON CONFLICT (country_iso3, hazard, version, sha256) DO NOTHING"""),
                [{c: x[c] for c in LINK_COLS} for x in links],
            )
        for d in (changed_docs or {}).values():
            conn.execute(
                sa.text("""
                UPDATE aa.framework_document SET is_public = :is_public,
                    title = COALESCE(:title, title), language = COALESCE(:language, language),
                    retrieved_from = COALESCE(:retrieved_from, retrieved_from),
                    note = COALESCE(:note, note)
                WHERE sha256 = :sha256"""),
                {
                    k: d[k]
                    for k in ("sha256", "is_public", "title", "language", "retrieved_from", "note")
                },
            )
        for x in changed_links:
            conn.execute(
                sa.text("""
                UPDATE aa.version_document SET role = :role, official_url = :official_url,
                    note = COALESCE(:note, note)
                WHERE country_iso3 = :country_iso3 AND hazard = :hazard
                  AND version = :version AND sha256 = :sha256"""),
                {c: x[c] for c in LINK_COLS},
            )


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument(
        "--entries", action="store_true", help="upload + entries file for the nightly job"
    )
    mode.add_argument(
        "--write", action="store_true", help="upload + insert into the dev DB directly"
    )
    ap.add_argument("--register", metavar="FILE", help="register one file by hand")
    ap.add_argument("--key", action="append", default=[], help="ISO3/hazard/version (repeatable)")
    ap.add_argument("--role", choices=ROLES, default="published")
    ap.add_argument("--private", action="store_true", help="not public: never on the site or KB")
    ap.add_argument(
        "--official-url", help="publication landing page (default: the version's doc_url)"
    )
    ap.add_argument("--retrieved-from", help="where the file came from (URL, 'email from …')")
    ap.add_argument("--retrieved-at", help="when (date or timestamp), if known")
    ap.add_argument("--language", choices=("en", "fr", "es"))
    ap.add_argument("--title")
    ap.add_argument("--note")
    ap.add_argument("--supersedes", metavar="SHA256", help="the file this one replaces")
    ap.add_argument("--update", action="store_true", help="correct an existing registration")
    ap.add_argument(
        "--accept-checked",
        nargs="*",
        metavar="FW/VER|SHA",
        help="backfill: also write files matched only on a direct link / publisher mirror — "
        "all of them, or only those named (kb_framework/version or sha256 prefix)",
    )
    ap.add_argument("--by", default=getpass.getuser(), help="registered_by")
    args = ap.parse_args()
    if bool(args.register) != bool(args.key):
        ap.error("--register and --key go together")
    if (args.supersedes or args.update) and not args.register:
        ap.error("--supersedes and --update need --register")
    if args.supersedes and not re.fullmatch(r"[0-9a-f]{64}", args.supersedes):
        ap.error("--supersedes takes a full sha256")

    engine = stratus.get_engine(stage="dev", write=True) if args.write else None
    if engine is not None:
        with engine.connect() as conn:
            fv, vp = from_db(conn, "framework_version"), from_db(conn, "version_page")
            known_docs = from_db(conn, "framework_document")
            known_links = from_db(conn, "version_document")
    else:
        fv, vp = from_snapshot("framework_version"), from_snapshot("version_page")
        known_docs = from_snapshot("framework_document")
        known_links = from_snapshot("version_document")

    if args.register:
        docs, links = plan_register(args, fv)
        reg_sha, held = next(iter(docs)), {}
        if args.supersedes == reg_sha:
            sys.exit("--supersedes names the file being registered")
        report = {"skipped": [], "check": []}
    else:
        docs, links, report, held = plan_backfill(fv, vp)
    docs, links, changed_docs, changed_links, diffs, taken = split_known(
        docs, links, known_docs, known_links
    )
    for x, other in taken:
        key = f"{x['country_iso3']}/{x['hazard']}/{x['version']}"
        if args.register and args.supersedes == other:
            links.append(x)  # the replacement --supersedes asked for
        elif args.register:
            sys.exit(
                f"{key} already has a current {x['role']} file {other}: "
                "pass --supersedes with it to replace it, or another --role"
            )
        else:
            report["skipped"].append(f"{key}: already has a current {x['role']} file {other[:12]}")
    if not args.register:  # a file whose every link was skipped is not registered either
        docs = {sha: d for sha, d in docs.items() if any(x["sha256"] == sha for x in links)}
    acc = args.accept_checked
    accepted = {
        sha
        for sha, fwv in held.items()
        if acc == [] or (acc and any(a == fwv or sha.startswith(a) for a in acc))
    }
    docs = {sha: d for sha, d in docs.items() if sha not in held or sha in accepted}
    links = [x for x in links if x["sha256"] not in held or x["sha256"] in accepted]
    if diffs and args.register and not args.update:
        sys.exit(
            "already registered differently (re-run with --update to correct):\n  "
            + "\n  ".join(diffs)
        )
    if not args.update:
        changed_docs, changed_links = {}, []

    mb = sum(len(d["data"]) for d in docs.values()) / 1e6
    print(f"{len(docs)} new documents ({mb:.1f} MB), {len(links)} new version links")
    for x in links:
        print(
            f"  + {x['country_iso3']}/{x['hazard']}/{x['version']}  "
            f"{x['sha256'][:12]}  {x['role']}"
        )
    for line in diffs:
        print(f"  {'~ update' if args.update else '! registered differently, unchanged'}: {line}")
    if args.supersedes:
        current = (
            set()
            if known_links is None
            else set(
                zip(
                    *(known_links[known_links.superseded_by.isna()][c] for c in [*KEY, "role"]),
                    strict=True,
                )
            )
        )
        for k in args.key:
            ok = (*k.split("/", 2), args.supersedes, args.role) in current
            print(
                f"  supersedes {args.supersedes[:12]} on {k}"
                + (
                    ""
                    if ok
                    else f" — NO current {args.role} link with that file: --write would fail"
                )
            )
    for sha, fwv in held.items():
        line = next(x for x in report["check"] if x.startswith(f"{fwv}:"))
        print(
            f"  ? {line} — "
            + ("accepted" if sha in accepted else "HELD BACK")
            + ": check it is the document of the version's landing page"
        )
    for line in report["skipped"]:
        print(f"  ! skipped {line}")
    if not args.register:
        known = (
            set()
            if known_links is None
            else set(
                zip(known_links.country_iso3, known_links.hazard, known_links.version, strict=True)
            )
        )
        covered = known | {(x["country_iso3"], x["hazard"], x["version"]) for x in links}
        for r in (
            fv[fv.doc_url.notna()].sort_values(["country_iso3", "hazard", "version"]).itertuples()
        ):
            if (r.country_iso3, r.hazard, r.version) not in covered:
                print(f"  - no file for {r.country_iso3}/{r.hazard}/{r.version}: {r.doc_url}")

    supersede = None
    if args.supersedes:
        keys = [tuple(k.split("/", 2)) for k in args.key]
        supersede = (args.supersedes, reg_sha, keys, args.role)
    if not (docs or links or changed_docs or changed_links or supersede):
        print("nothing to register")
    elif args.write:
        write(engine, docs, links, args.by, changed_docs, changed_links, supersede)
        print("written")
    elif args.entries:
        known = (known_docs, known_links)
        name, n = write_entries(
            docs, links, args.by, changed_docs, changed_links, supersede, known
        )
        print(
            f"uploaded {len(docs)} file(s) and {CONTAINER}/{name} ({n} rows) — applied by the "
            "next nightly job; now: databricks bundle run aa_tracking_nightly -t prod -p DEFAULT"
        )
    else:
        print("dry run — nothing written (--entries or --write to register)")


if __name__ == "__main__":
    main()
