"""Apply a [framework-entry] issue payload to the entered-* reference CSVs.

Called by .github/workflows/framework-entry-bridge.yml with the issue body on
stdin and ENTRY_AUTHOR / ENTRY_DATE in the environment. The body carries one
fenced ```yaml block (produced by the site's ingest-doc page):

    country_iso3: NGA
    hazard: flood
    version: 2026-06-18
    doc_title: ...
    doc_url: ...
    endorsed_by: erc | cerf_secretariat
    valid_until: 2027-06-18
    valid_until_source: doc-stated | convention | inherited
    prearranged_usd_doc: 7000000
    supersedes: 2024-05-01
    note: ...
    windows:
      - window_name: Window 1
        basis: forecast
        trigger_statement: ...
        budget_usd: 350000
        monitoring_period: Apr-Jun

Idempotent: re-filing the same (country_iso3, hazard, version) replaces the
previous entered rows (issue edits re-run the bridge).
"""

import csv
import os
import re
import sys
from pathlib import Path

import yaml

REFERENCE = Path(__file__).parents[1] / "reference"
VERSIONS_CSV = REFERENCE / "entered_framework_versions.csv"
WINDOWS_CSV = REFERENCE / "entered_windows.csv"

VALID_HAZARDS = {"drought", "flood", "storm", "cholera", "plague", "locusts", "other"}


def read_rows(path):
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def write_rows(path, fieldnames, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def main():
    body = sys.stdin.read()
    m = re.search(r"```ya?ml\s*\n(.*?)```", body, re.DOTALL)
    if not m:
        sys.exit("no fenced yaml block found in issue body")
    entry = yaml.safe_load(m.group(1))

    iso3 = str(entry.get("country_iso3", "")).strip().upper()
    hazard = str(entry.get("hazard", "")).strip().lower()
    version = str(entry.get("version", "")).strip()
    if not re.fullmatch(r"[A-Z]{3}", iso3):
        sys.exit(f"bad country_iso3: {iso3!r}")
    if hazard not in VALID_HAZARDS:
        sys.exit(f"bad hazard: {hazard!r} (expected one of {sorted(VALID_HAZARDS)})")
    if not re.fullmatch(r"\d{4}(-\d{2}(-\d{2})?)?", version):
        sys.exit(f"bad version: {version!r} (expected YYYY[-MM[-DD]])")

    author = os.environ.get("ENTRY_AUTHOR", "")
    entered_on = os.environ.get("ENTRY_DATE", "")
    key = {"country_iso3": iso3, "hazard": hazard, "version": version}

    vf, vrows = read_rows(VERSIONS_CSV)
    vrows = [r for r in vrows if not all(r.get(k) == v for k, v in key.items())]
    vrows.append({
        **key,
        **{k: ("" if entry.get(k) is None else str(entry.get(k)))
           for k in ("doc_title", "doc_url", "endorsed_by", "valid_until",
                     "valid_until_source", "prearranged_usd_doc", "supersedes",
                     "note")},
        "entered_by": author, "entered_on": entered_on,
    })
    write_rows(VERSIONS_CSV, vf, vrows)

    wf, wrows = read_rows(WINDOWS_CSV)
    wrows = [r for r in wrows if not all(r.get(k) == v for k, v in key.items())]
    for w in entry.get("windows") or []:
        name = str(w.get("window_name", "")).strip()
        if not name:
            continue
        wrows.append({
            **key, "window_name": name,
            **{k: ("" if w.get(k) is None else str(w.get(k)))
               for k in ("basis", "trigger_statement", "budget_usd",
                         "monitoring_period", "note")},
            "entered_by": author, "entered_on": entered_on,
        })
    write_rows(WINDOWS_CSV, wf, wrows)

    n_win = len(entry.get("windows") or [])
    print(f"applied {iso3}/{hazard} {version}: 1 version row, {n_win} window row(s)")


if __name__ == "__main__":
    main()
