"""Framework versions: the unit that actually gets approved.

Framework documents (and their budgets, trigger windows, coverage) are version-specific
— matching the KB model where `frameworks/<slug>/<version>.md` is the endorsed object.
This module builds `aa.framework_version` from:

1. KB page frontmatter (every dated version page in the local ds-knowledge-base clone,
   read-only) — the authoritative version registry, including superseded/retired pages
   that `aa.framework_version_map` (current-versions crosswalk) doesn't carry; and
2. revision dates reported in the tracking sheets ("When revised", "Time of Revision")
   that have NO KB version within ±90 days — kept as `source='sheet-revision'` rows so
   the version-completeness gap is visible on the review site rather than silently lost.

It then attributes version-specific facts (funding, sector budgets, coverage, calendar,
activations, status snapshots) to the version in force at the fact's date. Sheet data
is versionless, so attribution is inference — `version_match` records how, and NULL
means "not attributable yet" (a review queue, not an error).

Caveat shown on the site: figures reported while a framework is under revision may
belong to the *upcoming* version (e.g. AFG drought "$12M" is the revised framework's
number); interval attribution assigns them to the version in force. Manual overrides
belong in a later curation pass.
"""

import os
import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yaml

from .normalize import norm_hazard

KB_DIR = Path(os.environ.get("KB_DIR", "~/OCHA/repos/ds-knowledge-base")).expanduser()

# snapshot date of each source sheet (used to date year-grain facts)
SOURCE_AS_OF = {
    "julia-planning-2026": date(2026, 8, 1),
    "julia-reporting-2024": date(2024, 12, 31),
    "julia-reporting-2025": date(2025, 12, 31),
    "julia-gho-2026": date(2025, 12, 1),
    "julia-activations": date(2026, 8, 1),
    "yakubu-prearranged-jun2026": date(2026, 6, 1),
    "yakubu-cofinancing-jun2026": date(2026, 6, 1),
    "yakubu-people-covered-jun2026": date(2026, 6, 1),
    "yakubu-double-activations": date(2025, 12, 31),
    "yakubu-sector-prearranged-jun2026": date(2026, 6, 1),
    "yakubu-new-extended-2025": date(2025, 12, 31),
    "yakubu-insurance-2026": date(2026, 1, 15),
}


def _parse_version_date(label):
    """'2026-04-04' | '2025-02' | '2020' → date (first day); else None."""
    label = str(label).strip()
    for fmt, pad in (("%Y-%m-%d", ""), ("%Y-%m", "-01"), ("%Y", "-01-01")):
        try:
            return pd.to_datetime(label + pad, format="%Y-%m-%d").date()
        except ValueError:
            continue
    return None


def _frontmatter(path):
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return None
    # frontmatter carries inline `#` comments; yaml handles those natively
    return yaml.safe_load(m.group(1))


def kb_versions():
    """One row per (country, hazard, version) from KB framework page frontmatter."""
    rows = []
    for page in sorted(KB_DIR.glob("frameworks/*/[0-9]*.md")):
        fm = _frontmatter(page)
        if not fm or fm.get("content_type") != "framework":
            continue
        countries = fm.get("country_iso3")
        if isinstance(countries, str):
            countries = [countries.strip()]
        hazard, _ = norm_hazard(fm.get("hazard"))
        version = str(fm.get("version") or page.stem)
        valid_until = fm.get("valid_until")
        for c in countries or []:
            rows.append({
                "country_iso3": c, "hazard": hazard, "version": version,
                "kb_framework": fm.get("framework"),
                "kb_status": fm.get("status"),
                "valid_from": _parse_version_date(version),
                "valid_until": (
                    pd.to_datetime(str(valid_until)).date() if valid_until else None
                ),
                "supersedes": str(fm["supersedes"]) if fm.get("supersedes") else None,
                "prearranged_usd_doc": fm.get("prearranged_funding_usd"),
                "doc_url": fm.get("framework_doc"),
                "source": "kb-frontmatter",
            })
    return pd.DataFrame(rows)


def sheet_revision_versions(status_df, kb_df):
    """Sheet-reported revision dates with no KB version within ±90 days."""
    rows = []
    if status_df is None or "revised_on" not in status_df.columns:
        return pd.DataFrame(rows)
    revs = status_df.loc[
        status_df["revised_on"].notna(),
        ["country_iso3", "hazard", "revised_on", "source"],
    ].drop_duplicates(subset=["country_iso3", "hazard", "revised_on"])
    for _, r in revs.iterrows():
        rev = pd.to_datetime(r["revised_on"]).date()
        near = kb_df[
            (kb_df["country_iso3"] == r["country_iso3"])
            & (kb_df["hazard"] == r["hazard"])
            & kb_df["valid_from"].notna()
        ]
        if any(abs((v - rev).days) <= 90 for v in near["valid_from"]):
            continue
        rows.append({
            "country_iso3": r["country_iso3"], "hazard": r["hazard"],
            "version": rev.isoformat(), "valid_from": rev,
            "source": "sheet-revision",
            "note": f"revision reported in {r['source']}; no KB version within 90d",
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.drop_duplicates(subset=["country_iso3", "hazard", "version"])
    # the same revision often appears in two sheets with slightly different dates
    # (the GHO sheet stamps everything on the 25th) — keep the earliest of any
    # cluster within 60 days per framework
    keep = []
    for _, grp in df.sort_values("valid_from").groupby(["country_iso3", "hazard"]):
        last = None
        for _, r in grp.iterrows():
            if last is None or (r["valid_from"] - last).days > 60:
                keep.append(r)
                last = r["valid_from"]
    return pd.DataFrame(keep).reset_index(drop=True)


REFERENCE_DIR = Path(__file__).parents[2] / "reference"


def historical_versions(fv):
    """Merge reference/historical_framework_versions.csv (curated from the OCHA AA
    web-page sweep and the pa-anticipatory-action monorepo sweep) into the version set.

    A historical row matching an existing version (same country+hazard, valid_from
    within 60 days) ENRICHES it (doc_title/doc_url/analysis_ref, only where empty —
    KB frontmatter stays authoritative); otherwise it's appended as a new version.
    """
    f = REFERENCE_DIR / "historical_framework_versions.csv"
    if not f.exists():
        return fv
    hist = pd.read_csv(f, dtype=str)
    hist["valid_from"] = hist["version"].map(_parse_version_date)
    new_rows = []
    for _, h in hist.iterrows():
        mask = (
            (fv["country_iso3"] == h["country_iso3"])
            & (fv["hazard"] == h["hazard"])
            & fv["valid_from"].notna()
            & (h["valid_from"] is not None)
        )
        near = fv[mask]
        if h["valid_from"] is not None and not near.empty:
            # a bare-year version label ('2021') matches any date in that year;
            # otherwise match within 60 days
            def _delta(row):
                if re.fullmatch(r"\d{4}", str(row["version"])):
                    return 0 if row["valid_from"].year == h["valid_from"].year else 9999
                return abs((row["valid_from"] - h["valid_from"]).days)

            deltas = near.apply(_delta, axis=1)
            if deltas.min() <= 60:
                i = deltas.idxmin()
                # curated CSV values win over imported KB values (the CSV exists to
                # carry corrections from the sweeps, e.g. a mis-pointed framework_doc)
                for col in ("doc_title", "doc_url", "analysis_ref", "note"):
                    if pd.notna(h.get(col)) and str(h.get(col)).strip():
                        fv.at[i, col] = h[col]
                continue
        new_rows.append({
            "country_iso3": h["country_iso3"], "hazard": h["hazard"],
            "version": h["version"], "valid_from": h["valid_from"],
            "doc_title": h.get("doc_title"), "doc_url": h.get("doc_url"),
            "analysis_ref": h.get("analysis_ref"),
            "source": h.get("source", "historical"), "note": h.get("note"),
        })
    if new_rows:
        fv = pd.concat([fv, pd.DataFrame(new_rows)], ignore_index=True)
    return fv


def build_framework_version(tables):
    kb = kb_versions()
    fv = historical_versions(kb)
    sheet = sheet_revision_versions(tables.get("framework_status"), fv)
    fv = pd.concat([fv, sheet], ignore_index=True)
    # drop rows that collide with an earlier-priority version label exactly
    fv = fv.drop_duplicates(subset=["country_iso3", "hazard", "version"], keep="first")
    return fv.sort_values(["country_iso3", "hazard", "valid_from"]).reset_index(drop=True)


def historical_activation_events(existing):
    """reference/historical_activations.csv → extra activation_event rows.

    Julia's and Yakubu's historical activation records are treated as correct: a
    historical row matching an existing event (same country+hazard+year, and same
    month when both known) is SKIPPED, never merged over.
    """
    f = REFERENCE_DIR / "historical_activations.csv"
    if not f.exists():
        return pd.DataFrame()
    hist = pd.read_csv(f)
    rows = []
    for _, h in hist.iterrows():
        m = existing[
            (existing["country_iso3"] == h["country_iso3"])
            & (existing["hazard"] == h["hazard"])
            & (existing["year"] == h["year"])
        ]
        if not m.empty:
            if pd.isna(h.get("month")) or m["month"].isna().any() or (
                m["month"] == h["month"]
            ).any():
                continue
        rows.append(h)
    return pd.DataFrame(rows)


def _intervals(fv):
    """Per (country, hazard): ordered [(version, start, end, hard_end)]. end = next
    version's start; hard_end = the version's own valid_until (may precede end)."""
    out = {}
    for key, grp in fv[fv["valid_from"].notna()].groupby(["country_iso3", "hazard"]):
        grp = grp.sort_values("valid_from")
        spans = []
        rows = list(grp.itertuples())
        for i, r in enumerate(rows):
            end = rows[i + 1].valid_from if i + 1 < len(rows) else None
            spans.append((r.version, r.valid_from, end, r.valid_until))
        out[key] = spans
    return out


def _attribute_date(spans, d):
    """Return (version, match_method) for date d within a framework's spans."""
    for version, start, end, hard_end in spans:
        if d < start:
            continue
        if end is not None and d >= end:
            continue
        if hard_end is not None and pd.notna(hard_end) and d > hard_end:
            return version, "auto-post-validity"
        return version, "auto-interval"
    return None, None


def _fact_date(row, table):
    if table in ("framework_status", "framework_calendar", "people_covered",
                 "framework_focal_point"):
        return pd.to_datetime(row["as_of"]).date()
    if table == "report_channel_inclusion":
        # a framework counted in year N's report = the version in force during N
        return date(int(row["report_year"]), 12, 31)
    if table == "activation":
        ed = str(row["event_date"])
        if len(ed) >= 10:
            return pd.to_datetime(ed[:10]).date()
        if len(ed) == 7:
            return date(int(ed[:4]), int(ed[5:7]), 15)
        return date(int(ed[:4]), 6, 15)
    if table in ("prearranged_funding",):
        snap = SOURCE_AS_OF.get(row["source"])
        y = int(row["year"])
        d = snap or date(y, 12, 31)
        return min(max(d, date(y, 1, 1)), date(y, 12, 31))
    if table == "prearranged_sector_budget":
        return SOURCE_AS_OF.get(row["source"], date(2026, 6, 1))
    return None


VERSIONED_TABLES = [
    "framework_status", "framework_calendar", "people_covered",
    "prearranged_funding", "prearranged_sector_budget", "activation",
    "framework_focal_point", "report_channel_inclusion",
]


def attribute_versions(tables, fv):
    """Fill version/version_match on all version-level tables (in place)."""
    spans_by_fw = _intervals(fv)
    for t in VERSIONED_TABLES:
        df = tables.get(t)
        if df is None or df.empty:
            continue
        versions, methods = [], []
        for _, row in df.iterrows():
            # ad-hoc/EA events are allocations WITHOUT a framework: an explicit
            # category, never version-attributed
            if t == "activation" and row.get("event_type") != "framework_aa":
                versions.append(None)
                methods.append("adhoc-no-framework")
                continue
            # activation events matched to a KB activation inherit its version
            kb_v = row.get("kb_activation_version") if t == "activation" else None
            if kb_v is not None and pd.notna(kb_v) and str(kb_v).strip():
                versions.append(str(kb_v))
                methods.append("kb-activation")
                continue
            spans = spans_by_fw.get((row["country_iso3"], row["hazard"]))
            if not spans:
                versions.append(None), methods.append(None)
                continue
            d = _fact_date(row, t)
            v, m = _attribute_date(spans, d) if d else (None, None)
            versions.append(v), methods.append(m)
        df["version"] = versions
        df["version_match"] = methods
        if t == "activation" and "kb_activation_version" in df.columns:
            df.drop(columns=["kb_activation_version"], inplace=True)
