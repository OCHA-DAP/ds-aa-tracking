"""Have Databricks take a fresh snapshot of the database now (D164: the admin page's
"Publish changes").

The site is built from a snapshot the nightly Databricks job takes at 03:30 UTC (D17). When the
publish workflow is started with `fresh_snapshot` (the admin page's button, through the proxy's
POST /publish), it runs this first: `start` runs that same job out of hours, the workflow sets
itself up meanwhile, and `wait` returns once the job has finished, so the build restores a copy
taken minutes ago. The job does what it does every night, pending entries files included.

Auth is the Databricks SDK's own: DATABRICKS_HOST + DATABRICKS_CLIENT_ID/SECRET in the workflow
(a service principal with CAN_MANAGE_RUN on the job, databricks.yml); on a laptop, a profile
(DATABRICKS_CONFIG_PROFILE=DEFAULT).

  uv run --no-project --with databricks-sdk python scripts/fresh_snapshot.py start  # prints run_id=…
  uv run --no-project --with databricks-sdk python scripts/fresh_snapshot.py wait RUN_ID
"""

import os
import sys
from datetime import timedelta

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import QueueSettings, RunResultState

JOB = "AA Tracking Nightly (aa snapshot)"  # databricks.yml


def start(w):
    jobs = list(w.jobs.list(name=JOB))
    if len(jobs) != 1:
        sys.exit(f"::error::{len(jobs)} Databricks jobs named {JOB!r} visible (expected 1): "
                 "the service principal needs CAN_MANAGE_RUN on it (databricks.yml)")
    # queued, not skipped, when a run is already going (the job allows one at a time)
    run_id = w.jobs.run_now(jobs[0].job_id, queue=QueueSettings(enabled=True)).run_id
    print(f"Databricks run {run_id} of job {jobs[0].job_id} started", flush=True)
    if out := os.environ.get("GITHUB_OUTPUT"):
        with open(out, "a") as f:
            f.write(f"run_id={run_id}\n")
    else:
        print(f"run_id={run_id}")


def wait(w, run_id):
    # ~8-10 minutes (a cluster start, then the job), longer when queued behind another run
    run = w.jobs.wait_get_run_job_terminated_or_skipped(run_id, timeout=timedelta(minutes=50))
    state = run.state.result_state
    print(f"Databricks run {run_id}: {state.value if state else run.state.life_cycle_state}"
          f" — {run.run_page_url}", flush=True)
    if state != RunResultState.SUCCESS:
        sys.exit(f"::error::the fresh snapshot failed ({run.state.state_message or state}); "
                 "the site was not rebuilt — see the Databricks run")


if __name__ == "__main__":
    cmd = sys.argv[1:2]
    if cmd == ["start"]:
        start(WorkspaceClient())
    elif cmd == ["wait"] and len(sys.argv) == 3:
        wait(WorkspaceClient(), int(sys.argv[2]))
    else:
        sys.exit(__doc__)
