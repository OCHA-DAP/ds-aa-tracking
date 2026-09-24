"""Databricks entrypoint: KB sync -> snapshot export (-> prune), against the dev DB.

This is the only place that will still reach the dev DB once its public network access
goes (2026-09). It wraps the ordinary scripts unchanged, so the same steps run from a
laptop while access lasts:

    python databricks/nightly.py [--skip-kb-sync] [--ensure-schema] [--no-prune]

Steps
  1. shallow-clone the (public) knowledge base and run scripts/sync_kb.py
     (upsert-only: new KB framework pages -> aa.framework_version / registry)
  2. optional --ensure-schema: scripts/ensure_schema.py (idempotent DDL; off by default so
     a schema change ships deliberately, via a one-off run of this job with the flag)
  3. scripts/export_snapshot.py: consistent snapshot of schema aa -> dev blob
     projects/ds-aa-tracking/snapshot/{latest,YYYY-MM-DD}/ (dated copies kept 30 days)

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
    """spark_python_task's exec context doesn't always define __file__."""
    try:
        return Path(__file__).resolve().parents[1]  # noqa: F821
    except NameError:
        return Path.cwd()


# Under `source: GIT` the checkout lives on the workspace filesystem (wsfs), whose
# import probing is flaky (team pattern: ds-aa-cub-hurricanes/databricks/run_monitor_job.py).
# Copy the scripts + package onto local disk and run from there.
_SRC = _checkout_root()
ROOT = Path("/local_disk0" if Path("/local_disk0").is_dir() else tempfile.gettempdir()) / "aa_tracking_run"
for _sub in ("src", "scripts"):
    shutil.copytree(_SRC / _sub, ROOT / _sub, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def run(*args, **env):
    cmd = [sys.executable, *args]
    print("+", " ".join(str(a) for a in cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True, env={**os.environ, **env})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-kb-sync", action="store_true")
    ap.add_argument("--ensure-schema", action="store_true")
    ap.add_argument("--no-prune", action="store_true")
    a, _unknown = ap.parse_known_args()  # tolerate stray job parameters

    for v in ("DSCI_AZ_DB_DEV_HOST", "DSCI_AZ_DB_DEV_UID_WRITE", "DSCI_AZ_BLOB_DEV_SAS_WRITE"):
        if not os.environ.get(v):
            sys.exit(f"{v} is not set — the cluster policy should inject the dsci secrets")

    if not a.skip_kb_sync:
        kb = Path(tempfile.mkdtemp(prefix="kb-")) / "ds-knowledge-base"
        subprocess.run(["git", "clone", "-q", "--depth", "1", KB_REPO, str(kb)], check=True)
        run("scripts/sync_kb.py", KB_DIR=str(kb))
    if a.ensure_schema:
        run("scripts/ensure_schema.py")
    run("scripts/export_snapshot.py", *(["--no-prune"] if a.no_prune else []))


if __name__ == "__main__":
    main()
