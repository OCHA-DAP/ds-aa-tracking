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
"""
from __future__ import annotations

import argparse
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
