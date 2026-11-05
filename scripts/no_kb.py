"""No reference to the knowledge base on the site (D199).

Owner's rule (2026-11-04): "There should be no reference to the knowledge base at all on this site
anymore." The tracking database has been the record since 2026-09-28; the site never sends a reader
there. build_site.write_site() runs check() on everything it wrote (the open site and the open layer
at the root, dev/, admin/: each page's text, the strings its scripts carry, its data); publish.sh
runs it again on the unocha.org mock-up's pages, which are written after the build:

    uv run python scripts/no_kb.py site_build 'dev/mock-*.html'

Looked for, in the three languages: the words (knowledge base, base de connaissances, base de
conocimiento, ds-knowledge-base) and KB as a word (not a file size: "874 KB"). On the open and
development sites also a lowercase kb ("the kb page", "kb-era") and a data field named after it
(`"kb…":` in a page's data or a JSON file, a kb… column in a CSV). Not checked: the framework
documents' own texts (pdf-*.txt) and the admin site's database names (the columns kb_framework,
kb_status, kb_event_date and the stored provenance code 'kb'), which are the database's.

A hit is a ::warning:: per file in the publish run, so the code or the data gets fixed at the
source; AA_SITE_GUARD=strict (as for the identifier guard) stops the build instead.
"""

import html
import os
import re
import sys
from pathlib import Path

STRICT = os.environ.get("AA_SITE_GUARD", "").strip().lower() == "strict"
ADMIN_DIR = "admin"
SUFFIXES = (".html", ".md", ".txt", ".json", ".csv", ".xml")
SKIP = re.compile(r"^pdf-.*\.txt$|^i18n-missing\.json$")      # the documents' own words; never published

_SIZE = r"(?<!\d )(?<!\d)"     # not a file size ("874 KB", "1.5KB"); "(p.7). KB's" is a reference
WORDS = re.compile(r"(?i:knowledge[\s-]*bases?|bases? de conn?aissances?|bases? de conocimientos?"
                   r"|ds-knowledge-base)|" + _SIZE + r"\bK\.?B\b")
WORDS_PUBLIC = re.compile(WORDS.pattern + "|" + _SIZE + r"(?i:\bkb\b)")
KEYS = re.compile(r'\\?"kb(?:_[a-z_]+)?\\?"\s*:|"src"\s*:\s*"kb"')
CSV_HEAD = re.compile(r"(?:^|,)\"?kb(?:_\w+)?\"?(?:,|$)")


def _hits(rel, s, suffix):
    public = not rel.startswith(ADMIN_DIR + "/")
    text = html.unescape(s) if suffix == ".html" else s
    found = [re.sub(r"\s+", " ", text[max(0, m.start() - 50):m.end() + 50])
             for m in (WORDS_PUBLIC if public else WORDS).finditer(text)]
    if public:
        found += [s[max(0, m.start() - 30):m.end() + 20] for m in KEYS.finditer(s)]
        if suffix == ".csv" and CSV_HEAD.search(s.split("\n", 1)[0]):
            found.append("column: " + s.split("\n", 1)[0][:120])
    return list(dict.fromkeys(found))


def check(root, globs=("**/*",), label="knowledge-base check"):
    """Warn (or stop, AA_SITE_GUARD=strict) on every file under `root` matching `globs` that refers
    to the knowledge base. Returns {file: [snippets]}."""
    root = Path(root)
    files = sorted({f for g in globs for f in root.glob(g) if f.is_file()})
    hits = {}
    for f in files:
        if f.suffix not in SUFFIXES or SKIP.match(f.name):
            continue
        rel = f.relative_to(root).as_posix()
        if h := _hits(rel, f.read_text(errors="replace"), f.suffix):
            hits[rel] = h
    if not hits:
        print(f"  {label}: no reference to the knowledge base ({len(files)} file(s) checked)")
        return hits
    lines = [f"{rel}: {len(h)} reference(s), e.g. " + " | ".join(repr(x) for x in h[:3])
             for rel, h in sorted(hits.items())]
    if STRICT:
        raise SystemExit("FATAL (AA_SITE_GUARD=strict): the site refers to the knowledge base "
                         "(owner's rule, D199):\n  " + "\n  ".join(lines[:60]))
    for ln in lines:
        print(f"::warning::knowledge base: {ln}")
    print(f"::warning::{label}: references on {len(hits)} file(s) — reword them at the source "
          "(the code's text, or the data); AA_SITE_GUARD=strict fails the build instead")
    return hits


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: no_kb.py SITE_DIR [GLOB ...]")
    check(sys.argv[1], tuple(sys.argv[2:]) or ("**/*",), label="knowledge-base check (" + " ".join(sys.argv[2:] or ["all"]) + ")")
