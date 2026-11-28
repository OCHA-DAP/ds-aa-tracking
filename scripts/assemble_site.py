"""Put the published site together from two builds (D203): the open site from the code on the `prod`
branch, the development and admin sites from `main`.

    uv run python scripts/assemble_site.py --dev _dev-build --open _prod/_open-build --out _site

--dev and --open are folders staged by scripts/publish.sh (each already checked by its own
build). The open site is every top-level file of the --open folder: its pages, its "Coming soon"
pages, the open layer, its scripts and the map's geometry. dev/ and admin/ come whole from the
--dev folder. When `prod` and `main` are the same commit (after a promote, and on a pull request's
check) the workflow passes the same folder twice and the site is that one build.

Checks, before the workflow runs publish.sh's own rules on the result (CHECK_ONLY):
- every address in site_src/open_addresses.txt is on the open site: people hold links to them
  (FATAL: a page leaves that list on purpose, with the owner's word). The open site is checked
  against the list of the code that built it (--open-src, the prod checkout; main's list when that
  commit has none), and main's own build against main's list, so a pull request that drops an
  address fails its check, and main opening a page before it is put live stops nothing;
- a "Coming soon" page's link into dev/ lands on a page there (a warning: the open site can be
  behind main, which may have renamed a page).
With --open-sha and --dev-sha (and GH_TOKEN), the run's summary lists the pull requests merged on
main that the open site does not have yet.

The open pages' main address is https://datascience.unocha.org/aa-tracker/ (D258), and this script
moves them there in the copies it assembles (move_open_pages), so it holds for whichever commit built
them without waiting for a promote: on ocha-dap.github.io a page sends the reader on to the same page
at the new address (query and #hash kept); each page names its new address as canonical; the page
counter counts on the new address; and links into dev/ point at the development site on GitHub Pages,
where the password pages stay. The old address keeps serving the same files, so the copy at the new
address can be taken from it, and so its data files keep working for programs.

It also writes open-site-files.json at the top: every top-level file of the open site with its size and
SHA-256, and the open site's commit. The main app of datascience.unocha.org (OCHA-DAP/ds-web-main) reads
it to copy the open site to /aa-tracker/, file by file, checking each one (dev/ and admin/ are never in it).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDRESSES = ROOT / "site_src" / "open_addresses.txt"
SITES = ("dev", "admin")       # the folders taken from the --dev build


def promised(path: Path = ADDRESSES) -> list[str]:
    return [ln.split("#", 1)[0].strip() for ln in path.read_text().splitlines()
            if ln.split("#", 1)[0].strip()]


def lost(site: Path, path: Path) -> list[str]:
    """The addresses of the list at `path` that the staged `site` does not have at its top."""
    return [a for a in promised(path) if not (site / a).is_file()]


MANIFEST = "open-site-files.json"

# D258: the open site's main address, and where the password pages stay
NEW_BASE = "https://datascience.unocha.org/aa-tracker/"
OLD_HOST = "ocha-dap.github.io"
DEV_BASE = f"https://{OLD_HOST}/ds-aa-tracking/dev/"
MOVED_MARK = "/*aa-moved*/"
CHARSET = '<meta charset="utf-8">'
# the page counter as build_site.py writes it (COUNT_HEAD), and as it must count at the new address:
# there the server drops '.html' from addresses (trailingSlash auto), and the proxy's /hit takes
# only names ending in .html
COUNT_MARK = "/*aa-count*/"
COUNT_HOST_OLD = f"location.hostname !== '{OLD_HOST}'"
COUNT_HOST_NEW = "location.hostname !== 'datascience.unocha.org'"
COUNT_PAGE = "var page = location.pathname.split('/').pop() || 'index.html', last;"
COUNT_PAGE_NEW = COUNT_PAGE + " if (!/\\.html$/.test(page)) page += '.html';"


def move_open_pages(out: Path) -> int:
    """D258: point every open page of `out` at its new address (see the module's docstring).

    Runs on the assembled copies only, before the file list is written, and is safe to run twice.
    Stops the publish if a page's head or counter is not as build_site.py writes them, so the
    counts can't stop at zero on a green run."""
    n = 0
    for f in sorted(out.glob("*.html")):
        t = f.read_text()
        if MOVED_MARK not in t:
            if t.count(CHARSET) != 1:
                sys.exit(f"FATAL: {f.name}: no single {CHARSET} to put the move after (D258)")
            new = NEW_BASE + ("" if f.name == "index.html" else f.name[: -len(".html")])
            # the final form of the address: no '.html', and the folder for index.html
            head = (f"<script>{MOVED_MARK}if(location.hostname==='{OLD_HOST}'){{var p=(location.pathname"
                    ".split('/').pop()||'').replace(/\\.html$/,'');if(p==='index')p='';"
                    f"location.replace('{NEW_BASE}'+p+location.search+location.hash);}}"
                    f'</script><link rel="canonical" href="{new}">')
            t = t.replace(CHARSET, CHARSET + head, 1)
        if COUNT_MARK in t:
            t = t.replace(COUNT_HOST_OLD, COUNT_HOST_NEW)
            if COUNT_PAGE_NEW not in t:
                t = t.replace(COUNT_PAGE, COUNT_PAGE_NEW)
            if COUNT_HOST_NEW not in t or COUNT_PAGE_NEW not in t:
                sys.exit(f"FATAL: {f.name}: the page counter is not as build_site.py writes it, so it "
                         "would count nothing at the new address (D258)")
        t = re.sub(r"""(href=['"])dev/""", lambda m: m.group(1) + DEV_BASE, t)
        f.write_text(t)
        n += 1
    return n


# the names ds-web-main copies (scripts/assemble.py there refuses any other, and then the whole list)
PLAIN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}")


def write_manifest(out: Path, open_sha: str = "") -> int:
    """List every top-level file of the assembled site (the open site) in out/MANIFEST.

    Hidden files (.nojekyll) are GitHub Pages settings, not pages: left out. Any other name that
    ds-web-main would refuse stops the publish here, so the copy at datascience.unocha.org never
    stops updating unnoticed."""
    files = []
    for f in sorted(p for p in out.iterdir() if p.is_file() and p.name != MANIFEST):
        if f.name.startswith("."):
            continue
        if not PLAIN_NAME.fullmatch(f.name):
            sys.exit(f"FATAL: the open site has a file name ds-web-main would refuse: {f.name!r}")
        files.append({"path": f.name, "bytes": f.stat().st_size,
                      "sha256": hashlib.sha256(f.read_bytes()).hexdigest()})
    (out / MANIFEST).write_text(json.dumps({"open_sha": open_sha, "files": files}, indent=1) + "\n")
    return len(files)


def assemble(dev: Path, open_: Path, out: Path, open_src: Path | None = None) -> list[str]:
    for d in (dev, open_):
        if not (d / "index.html").is_file() or not (d / "dev" / "index.html").is_file():
            sys.exit(f"FATAL: {d} is not a staged site (no index.html or dev/index.html)")
    if not re.fullmatch(r"_[A-Za-z0-9-]+", out.name) or out.resolve().parent != ROOT:
        sys.exit(f"FATAL: --out must be a folder of its own at the repo root, named _<name>; got {out}")
    if out.resolve() in (dev.resolve(), open_.resolve()):
        sys.exit(f"FATAL: --out {out} is one of the builds it is made from")
    # the open build's own list (a commit from before D203 has none: main's stands in)
    own = open_src / "site_src" / "open_addresses.txt" if open_src else None
    open_list = own if own and own.is_file() else ADDRESSES
    if dev.resolve() != open_.resolve() and (gone := lost(dev, ADDRESSES)):
        sys.exit("FATAL: this build's open site would lose addresses people hold links to "
                 f"(site_src/open_addresses.txt): {', '.join(gone)}")
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    top = [f for f in open_.iterdir() if f.is_file()]
    for f in top:                                   # the open site, as its own build staged it
        shutil.copy2(f, out / f.name)
    for s in SITES:                                 # the development and admin sites, from main
        shutil.copytree(dev / s, out / s)
    if missing := lost(out, open_list):
        sys.exit("FATAL: the open site would lose addresses people hold links to "
                 f"(site_src/open_addresses.txt): {', '.join(missing)}")
    warn = []
    for f in sorted(out.glob("*.html")):
        for t in set(re.findall(r"""href=['"]dev/([A-Za-z0-9_.-]+\.html)""", f.read_text(errors="ignore"))):
            if not (out / "dev" / t).is_file():
                warn.append(f"{f.name} → dev/{t}")
    for w in warn:
        print(f"::warning::open page links to a development page that is not there: {w}")
    print(f"assembled: {len(top)} top-level files from {open_}, {', '.join(s + '/' for s in SITES)} from {dev}; "
          f"{len(promised(open_list))} promised addresses present ({open_list.relative_to(open_list.parents[1])} of "
          f"{'the open build' if open_list is own else 'main'})")
    return warn


def behind(open_sha: str, dev_sha: str) -> list[str]:
    """The pull requests merged on main since the open site's commit (GitHub's compare)."""
    repo = os.environ.get("GITHUB_REPOSITORY", "OCHA-DAP/ds-aa-tracking")
    r = subprocess.run(["gh", "api", f"repos/{repo}/compare/{open_sha}...{dev_sha}"],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[:200])
    lines = []
    for c in json.loads(r.stdout).get("commits", []):
        msg = c["commit"]["message"].split("\n")
        m = re.match(r"Merge pull request #(\d+) from ", msg[0])
        if m and len(c.get("parents", [])) > 1:
            title = next((x for x in msg[1:] if x.strip()), "")
            lines.append(f"#{m.group(1)} {title}")
    return lines


def summary(text: str) -> None:
    print(text)
    if p := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(p, "a") as fh:
            fh.write(text + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dev", type=Path, required=True)
    ap.add_argument("--open", dest="open_", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--open-src", type=Path, default=None,
                    help="the checkout the open build was made from (its address list)")
    ap.add_argument("--open-sha", default="")
    ap.add_argument("--dev-sha", default="")
    a = ap.parse_args()
    out = a.out if a.out.is_absolute() else ROOT / a.out
    assemble(a.dev, a.open_, out, a.open_src)
    print(f"D258: {move_open_pages(out)} open pages point at {NEW_BASE}")
    print(f"{MANIFEST}: {write_manifest(out, a.open_sha)} open files listed")
    if not (a.open_sha and a.dev_sha):
        return
    if a.open_sha == a.dev_sha:
        summary(f"**Open site:** the same code as the development site ({a.dev_sha[:7]}).")
        return
    head = f"**Open site:** built from `prod` ({a.open_sha[:7]}); the development site from {a.dev_sha[:7]}."
    try:
        prs = behind(a.open_sha, a.dev_sha)
    except Exception as e:  # the list is information only: never stop a publish for it
        summary(head + f" (could not list what is not on the open site yet: {e})")
        return
    summary(head + (f" Not on the open site yet ({len(prs)}; `gh workflow run promote.yml` puts them there):\n"
                    + "\n".join(f"- {p}" for p in prs) if prs else " No merged pull request is waiting."))


if __name__ == "__main__":
    main()
