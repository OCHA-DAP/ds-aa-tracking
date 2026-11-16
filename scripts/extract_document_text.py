"""Write the text of every registered framework document, page by page, to
aa.framework_document_page (D228).

The nightly job runs this after the entries are applied, so a document registered today is
searchable from tomorrow's snapshot. A document is read once: its sha256 is its identity,
so its text never changes. Only a change of extractor (EXTRACTOR below) re-reads the files
the older one wrote. A failure on one file is reported and the others go on; the script
exits non-zero if any file failed, and the nightly job carries on to the snapshot.

Does nothing on a database that does not have the table yet (run the schema migration).

Usage: uv run python scripts/extract_document_text.py [--dry-run] [--limit N]
"""

import argparse
import io
import os
import sys
from pathlib import Path

import sqlalchemy as sa

os.environ.setdefault("PGSSLMODE", "require")
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import ocha_stratus as stratus  # noqa: E402
import pypdf  # noqa: E402

from ds_aa_tracking import snapshot  # noqa: E402  (CONTAINER: the archive's container)

EXTRACTOR = f"pypdf-{pypdf.__version__}"


def clean(t: str) -> str:
    """Text Postgres can store: no NUL, and no lone surrogate (pypdf decodes some fonts with
    surrogatepass; psycopg2 cannot encode those to UTF-8), each replaced by '?'."""
    return t.replace("\x00", "").encode("utf-8", "replace").decode("utf-8")


def extract_pages(data: bytes) -> list[str]:
    """One string per page, in order. A page that fails or has no text layer gives ''."""
    reader = pypdf.PdfReader(io.BytesIO(data))
    pages = []
    for p in reader.pages:
        try:
            t = p.extract_text() or ""
        except Exception as exc:  # noqa: BLE001 — one bad page must not lose the document
            print(f"    page {len(pages) + 1}: {str(exc).splitlines()[0][:120]}")
            t = ""
        pages.append(clean(t))
    return pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="list what would be read")
    ap.add_argument("--limit", type=int, default=0, help="read at most N documents")
    a = ap.parse_args()

    engine = stratus.get_engine(stage="dev", write=not a.dry_run)
    with engine.connect() as conn:
        if not conn.execute(sa.text(
                "SELECT 1 FROM information_schema.tables WHERE table_schema = 'aa' "
                "AND table_name = 'framework_document_page'")).first():
            print("framework_document_page: table not there yet (run the schema migration); "
                  "nothing done")
            return
        # text of a file no longer in the registry goes with it
        orphans = conn.execute(sa.text("""
            SELECT DISTINCT p.sha256 FROM aa.framework_document_page p
            WHERE NOT EXISTS (SELECT 1 FROM aa.framework_document d WHERE d.sha256 = p.sha256)
            """)).scalars().all()
        todo = conn.execute(sa.text("""
            SELECT d.sha256, d.blob_path, d.title
            FROM aa.framework_document d
            WHERE d.media_type = 'application/pdf'
              AND NOT EXISTS (SELECT 1 FROM aa.framework_document_page p
                              WHERE p.sha256 = d.sha256 AND p.extractor = :ex)
            ORDER BY d.registered_at, d.sha256"""), {"ex": EXTRACTOR}).fetchall()
    if a.limit:
        todo = todo[:a.limit]
    print(f"{len(todo)} document(s) to read with {EXTRACTOR}" + (" (dry run)" if a.dry_run else ""))
    if orphans:
        print(f"{len(orphans)} document(s) no longer registered: "
              + ("their text would be removed (dry run)" if a.dry_run else "removing their text"))
        if not a.dry_run:
            with engine.begin() as conn:
                conn.execute(sa.text("DELETE FROM aa.framework_document_page WHERE sha256 = ANY(:s)"),
                             {"s": list(orphans)})

    read = failed = 0
    for d in todo:
        label = f"{d.sha256[:12]} {(d.title or '')[:70]}"
        if a.dry_run:
            print(f"  (dry) {label}")
            continue
        try:  # download, read AND write: a failure on one document never stops the others
            data = stratus.load_blob_data(d.blob_path, stage="dev",
                                          container_name=snapshot.CONTAINER)
            pages = extract_pages(data)
            if not pages:
                raise ValueError("the PDF has no pages")
            with engine.begin() as conn:  # one document = one transaction: all its pages or none
                conn.execute(sa.text("DELETE FROM aa.framework_document_page WHERE sha256 = :s"),
                             {"s": d.sha256})
                conn.execute(sa.text(
                    "INSERT INTO aa.framework_document_page (sha256, page, text, extractor) "
                    "VALUES (:s, :p, :t, :ex)"),
                    [{"s": d.sha256, "p": i, "t": t, "ex": EXTRACTOR}
                     for i, t in enumerate(pages, start=1)])
        except Exception as exc:  # noqa: BLE001 — report, go on with the others
            failed += 1
            print(f"  ! {label}: {str(exc).splitlines()[0][:160]}")
            continue
        read += 1
        empty = sum(1 for t in pages if not t.strip())
        print(f"  {label}: {len(pages)} pages, {sum(map(len, pages)):,} characters"
              + (f", {empty} without text" if empty else ""))
    if not a.dry_run:
        print(f"done: {read} read, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
