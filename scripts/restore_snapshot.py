"""Recreate the `aa` schema from a blob snapshot into a LOCAL Postgres, so the site
builds (and the tables can be queried) without a network path to the dev DB.

Point the usual stratus env vars at the local server, e.g.

    DSCI_AZ_DB_DEV_HOST=localhost DSCI_AZ_DB_DEV_UID=postgres DSCI_AZ_DB_DEV_PW=postgres \
    DSCI_AZ_DB_DEV_UID_WRITE=postgres DSCI_AZ_DB_DEV_PW_WRITE=postgres PGSSLMODE=disable \
    uv run python scripts/restore_snapshot.py [--snapshot latest|YYYY-MM-DD] [--from-dir DIR]

(`docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:16` is enough.)
Reading the snapshot from blob needs DSCI_AZ_BLOB_DEV_SAS. The schema is DROPped and
rebuilt; the script refuses to do that on a non-local host unless --allow-remote.
Writes data/snapshot_manifest.json, which build_site.py uses for its "data as of" stamp.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import ocha_stratus as stratus  # noqa: E402

from ds_aa_tracking import snapshot  # noqa: E402

ROOT = Path(__file__).parents[1]
MANIFEST_COPY = ROOT / "data" / "snapshot_manifest.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default="latest", help="latest (default) or YYYY-MM-DD")
    ap.add_argument("--from-dir", help="restore from a local snapshot dir instead of blob")
    ap.add_argument("--allow-remote", action="store_true")
    a = ap.parse_args()
    tmp = None
    if a.from_dir:
        src = Path(a.from_dir)
    else:
        tmp = Path(tempfile.mkdtemp(prefix="aa-restore-"))
        src = snapshot.download(a.snapshot, tmp, stage="dev")
        print(f"downloaded snapshot '{a.snapshot}' -> {src}")
    engine = stratus.get_engine(stage="dev", write=True)
    print(f"restoring into {engine.url.host} ...")
    r = snapshot.restore(engine, src, allow_remote=a.allow_remote)
    m = r["manifest"]
    MANIFEST_COPY.parent.mkdir(exist_ok=True)
    MANIFEST_COPY.write_text(json.dumps(m, indent=1))
    print(f"restored snapshot {m['snapshot_at']}: {m['n_tables']} tables, {m['n_views']} views, "
          f"{m['total_rows']:,} rows")
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    if r["problems"]:
        print("PROBLEMS:\n  " + "\n  ".join(r["problems"]))
        sys.exit(1)


if __name__ == "__main__":
    main()
