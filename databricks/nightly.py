"""Databricks entrypoint: (schema pass) -> snapshot export (-> prune), against the dev DB.

This is the only place that will still reach the dev DB once its public network access
goes (2026-09). It wraps the ordinary scripts unchanged, so the same steps run from a
laptop while access lasts:

    python databricks/nightly.py [--drop-leftovers] [--ensure-schema] [--backfill-events] [--relabel ISO3/HAZARD/OLD NEW] [--no-prune]

Steps
  0. one-off --drop-leftovers: scripts/drop_leftovers.py --write (D168: archives, then drops
     what was left from building the tracker and renames person-named source labels). Run
     it before (or with) --ensure-schema: a schema pass first would rebuild a view that
     ranks sources by their new labels over rows still carrying the old ones
  1. optional --ensure-schema: scripts/ensure_schema.py (idempotent DDL; off by default so
     a schema change ships deliberately, via a one-off run of this job with the flag)
  1a. one-off --backfill-events: scripts/backfill_window_events.py --write (D252): fills the
     window event record from the two backtest tables it replaces, once, after the schema pass
     that creates it; it rolls back (and stops the run) unless regenerating the two tables
     from the record changes nothing and every return period stays the same
  1b. optional --relabel ISO3/HAZARD/OLD NEW: scripts/relabel_version.py — a version label
     is part of the key in several tables and entries files can only upsert, so a relabel
     (placeholder -> endorsement date) runs here, one-off, before the entries that may
     address the new label. A failure stops the run before the entries are applied.
  2. scripts/apply_entries.py: apply new data-entry files from the private dev blob
     (projects/ds-aa-tracking/entries/*.json; each applied once, audited) — the write path
     for entries prepared off-network since laptops lost DB access (2026-09-30). A failure
     here is reported but never blocks the snapshot.
  2b. scripts/stamp_development.py: a development version without development_since gets
     today's date (in-development frameworks count toward pre-arranged money from then on)
  2c. scripts/resolve_provisional.py: a CERF amount entered as provisional (before OneGMS
     recorded the allocation) takes OneGMS's code and amount once the mirror has it
  2c'. scripts/sync_cerf.py: every CERF funding row with an allocation code takes OneGMS's
     approved amount and planned people, as does the people figure of the activation it pays
     for (D232); the amounts of an allocation split over several rows are left as entered and
     warned about when the parts don't add up to OneGMS's figures
  2c''. scripts/mirror_backtest.py: simulated_activation and backtest_event say what the window
     event record (aa.window_event) says, while the pages and the open site's code still read them (D252);
     nothing happens before the backfill
  2d. scripts/extract_document_text.py: the text of each newly registered framework
     document, page by page, into aa.framework_document_page (D228)
  2e. scripts/trim_assistant_log.py: the texts of the AA assistant's questions older than 180
     days are removed (D248); the counts stay
  3. scripts/export_snapshot.py: consistent snapshot of schema aa -> dev blob
     projects/ds-aa-tracking/snapshot/{latest,YYYY-MM-DD}/ (dated copies kept 30 days,
     31-December copies forever), with each view's rows beside the tables (D228)

KB flip (2026-09-28): this system is authoritative; the knowledge base is not a source.
Frameworks and versions are entered here (entry/admin pages).

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
for _sub in ("src", "scripts"):
    shutil.copytree(_SRC / _sub, ROOT / _sub, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
# the mirror list (D154) sits beside the proxy, whose zip ships it; the scripts read it too
(ROOT / "proxy").mkdir(exist_ok=True)
shutil.copy2(_SRC / "proxy" / "mirror_tables.json", ROOT / "proxy" / "mirror_tables.json")


def run(*args, timeout=None, **env):
    cmd = [sys.executable, *args]
    print("+", " ".join(str(a) for a in cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True, env={**os.environ, **env}, timeout=timeout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ensure-schema", action="store_true")
    ap.add_argument("--drop-leftovers", action="store_true", help="one-off, D168")
    ap.add_argument("--backfill-events", action="store_true", help="one-off, D252")
    ap.add_argument("--relabel", nargs=2, metavar=("ISO3/HAZARD/OLD", "NEW"))
    ap.add_argument("--no-prune", action="store_true")
    a, unknown = ap.parse_known_args()  # tolerate stray job parameters, but say so
    if unknown:   # e.g. "--a --b" sent as one: `bundle run --python-params` splits on commas
        print(f"!! ignored job parameter(s) {unknown}: separate flags with commas, "
              '--python-params "--drop-leftovers,--ensure-schema"', flush=True)

    for v in ("DSCI_AZ_DB_DEV_HOST", "DSCI_AZ_DB_DEV_UID_WRITE", "DSCI_AZ_BLOB_DEV_SAS_WRITE"):
        if not os.environ.get(v):
            sys.exit(f"{v} is not set — the cluster policy should inject the dsci secrets")

    if a.drop_leftovers:
        run("scripts/drop_leftovers.py", "--write")
    if a.ensure_schema:
        run("scripts/ensure_schema.py")
    if a.backfill_events:
        run("scripts/backfill_window_events.py", "--write")
    if a.relabel:
        run("scripts/relabel_version.py", *a.relabel, "--write", "--by", "nightly --relabel")
    try:
        run("scripts/apply_entries.py")
    except subprocess.CalledProcessError as ex:  # never block the snapshot on an entry file
        print(f"!! apply_entries failed ({ex}); continuing to the snapshot", flush=True)
    try:   # a development version gets its start date the first night it exists
        run("scripts/stamp_development.py")
    except subprocess.CalledProcessError as ex:
        print(f"!! stamp_development failed ({ex}); continuing to the snapshot", flush=True)
    try:   # provisional CERF amounts give way to OneGMS's once the allocation is recorded there
        run("scripts/resolve_provisional.py")
    except subprocess.CalledProcessError as ex:
        print(f"!! resolve_provisional failed ({ex}); continuing to the snapshot", flush=True)
    try:   # CERF amounts and people targeted follow OneGMS's (D232), after the provisional ones resolve
        run("scripts/sync_cerf.py")
    except subprocess.CalledProcessError as ex:
        print(f"!! sync_cerf failed ({ex}); continuing to the snapshot", flush=True)
    try:   # the two backtest tables the open site still reads follow the event record (D252)
        run("scripts/mirror_backtest.py")
    except subprocess.CalledProcessError as ex:
        print(f"!! mirror_backtest failed ({ex}); continuing to the snapshot", flush=True)
    try:   # a document registered today is searchable from tomorrow's snapshot. Time-limited:
        # it parses arbitrary PDFs, and each document commits on its own, so a stop is safe
        run("scripts/extract_document_text.py", timeout=900)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as ex:
        print(f"!! extract_document_text failed ({ex}); continuing to the snapshot", flush=True)
    try:   # the assistant's questions keep their texts 180 days (D248), whether or not anyone asks
        run("scripts/trim_assistant_log.py")
    except subprocess.CalledProcessError as ex:
        print(f"!! trim_assistant_log failed ({ex}); continuing to the snapshot", flush=True)
    run("scripts/export_snapshot.py", *(["--no-prune"] if a.no_prune else []))


if __name__ == "__main__":
    main()
