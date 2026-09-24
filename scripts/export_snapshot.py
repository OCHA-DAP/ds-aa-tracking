"""Snapshot the dev `aa` schema to blob (parquet + DDL metadata) — see
ds_aa_tracking.snapshot for the why and the layout.

Runs nightly on Databricks (databricks/nightly.py) — the only place that will still
reach the dev DB — and works from a laptop while public access lasts.

Usage: uv run python scripts/export_snapshot.py [--out DIR] [--no-upload] [--no-prune]
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
os.environ.setdefault("PGSSLMODE", "require")

import ocha_stratus as stratus  # noqa: E402

from ds_aa_tracking import snapshot  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="write the snapshot here (default: a temp dir)")
    ap.add_argument("--no-upload", action="store_true", help="only write locally")
    ap.add_argument("--no-prune", action="store_true", help="keep every dated copy")
    a = ap.parse_args()
    out = Path(a.out) if a.out else Path(tempfile.mkdtemp(prefix="aa-snapshot-"))
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True, cwd=Path(__file__).parents[1]).stdout.strip()
    except Exception:  # noqa: BLE001
        sha = ""
    host = os.environ.get("DSCI_AZ_DB_DEV_HOST", "")
    m = snapshot.export(stratus.get_engine(stage="dev"), out, source=f"{host} @ {sha}")
    print(f"snapshot {m['snapshot_at']}: {m['n_tables']} tables, {m['n_views']} views, "
          f"{m['total_rows']:,} rows -> {out}")
    if a.no_upload:
        return
    for pfx in snapshot.upload(out, stage="dev"):
        print(f"  uploaded -> {snapshot.CONTAINER}/{pfx}/")
    if not a.no_prune:
        gone = snapshot.prune(stage="dev")
        print(f"  pruned {len(gone)} dated snapshot(s) older than {snapshot.KEEP_DAYS} days"
              + (": " + ", ".join(gone) if gone else ""))


if __name__ == "__main__":
    main()
