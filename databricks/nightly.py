"""Databricks entrypoint: (schema pass) -> snapshot export (-> prune), against the dev DB.

This is the only place that will still reach the dev DB once its public network access
goes (2026-09). It wraps the ordinary scripts unchanged, so the same steps run from a
laptop while access lasts:

    python databricks/nightly.py [--ensure-schema] [--relabel ISO3/HAZARD/OLD NEW] [--no-prune] [--kb-sync]

Steps
  1. optional --ensure-schema: scripts/ensure_schema.py (idempotent DDL; off by default so
     a schema change ships deliberately, via a one-off run of this job with the flag)
  1b. optional --relabel ISO3/HAZARD/OLD NEW: scripts/relabel_version.py — a version label
     is part of the key in several tables and entries files can only upsert, so a relabel
     (placeholder -> endorsement date) runs here, one-off, before the entries that may
     address the new label. A failure stops the run before the entries are applied.
  2. scripts/apply_entries.py: apply new data-entry files from the private dev blob
     (projects/ds-aa-tracking/entries/*.json; each applied once, audited) — the write path
     for entries prepared off-network since laptops lost DB access (2026-09-30). A failure
     here is reported but never blocks the snapshot.
  2b. scripts/apply_backtests.py: backtest errata and seals committed to backtests/ (plus
     errata for non-public documents from the private blob) — after the entries, so a
     version's pending entries land before a seal freezes it. A sealed backtest changes
     only through an erratum: the database refuses anything else, from any writer. Then
     validates the backtest foreign keys still marked NOT VALID (once the errata have
     cleaned the rows from before). A failure here is reported but never blocks the snapshot.
  3. scripts/export_snapshot.py: consistent snapshot of schema aa -> dev blob
     projects/ds-aa-tracking/snapshot/{latest,YYYY-MM-DD}/ (dated copies kept 30 days,
     31-December copies forever)

KB flip (2026-09-28): this system is authoritative; the knowledge base is no longer a
source, so the nightly sweep of KB framework pages (scripts/sync_kb.py) is OFF. Frameworks
and versions are entered here (entry/admin pages). `--kb-sync` remains only for a
deliberate one-off, never scheduled.

The GitHub Actions publish workflow (04:17 UTC) then restores `latest` into a throwaway
Postgres and builds the site — see .github/workflows/publish.yml.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KB_REPO = "https://github.com/OCHA-DAP/ds-knowledge-base.git"


def _checkout_root() -> Path:
    """The repo checkout: walk up from every hint (spark_python_task's exec context
    doesn't reliably define __file__, and its value isn't always the script path)
    until a directory holding both src/ and scripts/ appears."""
    hints = []
    try:
        hints.append(Path(__file__).resolve())  # noqa: F821
    except NameError:
        pass
    if sys.argv and sys.argv[0]:
        hints.append(Path(sys.argv[0]).resolve())
    hints.append(Path.cwd())
    for h in hints:
        for d in [h, *h.parents]:
            if (d / "src").is_dir() and (d / "scripts").is_dir():
                return d
    raise SystemExit(f"cannot find the repo root from {[str(h) for h in hints]}")


# Under `source: GIT` the checkout lives on the workspace filesystem (wsfs), whose
# import probing is flaky (team pattern: ds-aa-cub-hurricanes/databricks/run_monitor_job.py).
# Copy the scripts + package onto local disk and run from there.
_SRC = _checkout_root()
ROOT = Path("/local_disk0" if Path("/local_disk0").is_dir() else tempfile.gettempdir()) / "aa_tracking_run"
for _sub in ("src", "scripts", "backtests"):
    shutil.copytree(_SRC / _sub, ROOT / _sub, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def run(*args, **env):
    cmd = [sys.executable, *args]
    print("+", " ".join(str(a) for a in cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True, env={**os.environ, **env})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb-sync", action="store_true",
                    help="one-off: sweep KB framework pages into the registry (OFF since the KB flip)")
    ap.add_argument("--ensure-schema", action="store_true")
    ap.add_argument("--relabel", nargs=2, metavar=("ISO3/HAZARD/OLD", "NEW"))
    ap.add_argument("--no-prune", action="store_true")
    a, _unknown = ap.parse_known_args()  # tolerate stray job parameters

    for v in ("DSCI_AZ_DB_DEV_HOST", "DSCI_AZ_DB_DEV_UID_WRITE", "DSCI_AZ_BLOB_DEV_SAS_WRITE"):
        if not os.environ.get(v):
            sys.exit(f"{v} is not set — the cluster policy should inject the dsci secrets")

    if a.kb_sync:
        kb = Path(tempfile.mkdtemp(prefix="kb-")) / "ds-knowledge-base"
        subprocess.run(["git", "clone", "-q", "--depth", "1", KB_REPO, str(kb)], check=True)
        run("scripts/sync_kb.py", "--i-know-the-kb-is-not-a-source", KB_DIR=str(kb))
    if a.ensure_schema:
        run("scripts/ensure_schema.py")
    if a.relabel:
        run("scripts/relabel_version.py", *a.relabel, "--write", "--by", "nightly --relabel")
    try:
        run("scripts/apply_entries.py")
    except subprocess.CalledProcessError as ex:  # never block the snapshot on an entry file
        print(f"!! apply_entries failed ({ex}); continuing to the snapshot", flush=True)
    try:
        run("scripts/apply_backtests.py")
    except subprocess.CalledProcessError as ex:  # nor on a backtest erratum / seal file
        print(f"!! apply_backtests failed ({ex}); continuing to the snapshot", flush=True)
    run("scripts/export_snapshot.py", *(["--no-prune"] if a.no_prune else []))


if __name__ == "__main__":
    main()
