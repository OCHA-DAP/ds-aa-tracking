# Reading windows, budgets and historical activations from the tracker

Internal guidance for anyone who used CERF's `window_level` and `activation_history` sheets, such as the
CERF financial-exposure app, or the insurer's workbook of 14 September 2026 that grew out of them.
It explains where the same information now lives in the AA tracker's database, and how to read it.
The rulings behind it are D207 to D216 in [DECISIONS.md](DECISIONS.md).

## What changed, and why

The sheets were the record: one row per window, with a uid (`afg_drought_v2_wt1`), an amount, a
probability, a sum-or-max rule, a cannot-trigger-if rule, monitoring months and a status. Beside it, a
matrix of years by uid held how many times each window would have activated. As copies passed between
teams they drifted:

- versions were numbered from the first one CERF happened to list, so earlier versions had no number;
- several windows were sometimes collapsed into one;
- real activations were added to the simulated ones;
- statuses went out of date;
- southern-hemisphere storm seasons were labelled by their first year.

The tracker's database is now the record. The sheets' two shapes are views of it, rebuilt every night.
Nothing is typed into a sheet any more.

## Where to read it

- **The database:** the dev Postgres, schema `aa`. Read it with a read-only login; the team can give
  you one.
- **The nightly snapshot:** after 03:30 UTC each night, and after any "Publish changes", every table is
  copied to the dev blob under `projects/ds-aa-tracking/snapshot/latest/` (one parquet file per table,
  and the views as SQL in `schema.json`). The views are not parquet files. To query them, rebuild the
  snapshot in a local Postgres with `scripts/restore_snapshot.py` and then run
  `scripts/ensure_schema.py` (the restore does not bring the database's triggers back).

## The model

```
framework (country_iso3, hazard)
└─ version            framework_version: its date label, version_no, cerf_version_id,
   │                  window_rollup, activations_per_year, status
   └─ window          window: window_code, window_name, cannot_trigger_if, monitor_months
      ├─ budget       window_funding: the money on the window, by fund (CERF, pooled funds)
      ├─ trigger      window_trigger: the conditions inside the window, joined by OR,
      │  │            each with its analysis years
      │  └─ event     trigger_event: every event the trigger was tested on (a storm, a season,
      │               an outbreak), met or not
      └─ real activation   window_activation: the window it released, and its trigger where known
```

- **A window is a pot of money with its own activities.** Two windows are merged into one only when both
  their money and their activities are the same (D216). Readiness is always its own window.
- **Several triggers can release the same window.** For example a forecast or an observation, or the
  Primera or Postrera season. The window still activates once.
- **A window with no triggers entered has one implicit trigger, `main`.** The views add it, so every
  window looks the same to a reader.

## The old sheets, the new views

| Old sheet column | Now | Notes |
|---|---|---|
| a `window_level` row | a `v_cerf_window` row | One row per window of every version. `status` says which are current. |
| `uid` | `uid` | Framework id, `v` and the tracker's version number, then the window code (see Ids). |
| `framework_version_id` | `framework_version_id` | The tracker's numbering. CERF's own id is in `cerf_version_id`. |
| `window_code` (`wt1`, `wg1`) | `window_code` (`wt_readiness`, `wg_koshi_action`) | The code says what the window is (D213). |
| `amt` | `amt` | The window's pre-arranged CERF money: the most it can release. Other funds are in `v_window_budget`. |
| `prob` | `framework_probability` | The document's figure where it states one, else computed from the history. `framework_rp_method` says which (`reported` or `empirical`). |
| `exposure_calc` | `exposure_calc` | Taken from the version's rule; blank where none is recorded. Read Budgets below instead. |
| `overall_framework_prob` | `overall_framework_prob` | |
| `status` | `status` | Always from the database, never from a sheet. |
| `old_uid` | `cerf_uids` and `v_cerf_uid_crosswalk` | Every uid any sheet gave the window. |
| `cannot_trigger_if` | `cannot_trigger_if` | The uid of the window whose release blocks this one. |
| `monitor_months` | `monitor_months` | Comma-separated months, `6,7,8,9,10,11,12`. |
| the `activation_history` matrix | `v_cerf_activation_history` | Long format: `uid`, `year`, `n_simulated`, `n_real`, `n`. |

## Ids

- **uid** = framework id + `_v` + version number + `_` + window code, e.g. `cub_storms_v2_wt_action`.
- **The version number counts the framework's versions from the first one on record** (D212). It often
  differs from CERF's:

  | Version | CERF's id | Tracker's id |
  |---|---|---|
  | Chad drought 2025 | `tcd_drought_v1` | `tcd_drought_v3` |
  | Burkina Faso drought 2026 | `bfa_drought_v2` | `bfa_drought_v4` |

  A superseded draft has no number, so its uid uses its date label instead.
- **Old uids:** look them up in `v_cerf_uid_crosswalk`, and always by source. The same string can mean
  two different windows in two sheets. For example, `afg_drought_v1_wt1` is the 2025 version's window A in
  CERF's sheet, but the 2026 version's window A in the insurer's earlier ids.

  | `source` | What it holds |
  |---|---|
  | `cerf-window-level` | CERF's sheet: its `uid` |
  | `cerf-window-level-old` | CERF's sheet: its `old_uid` |
  | `gallagher-2026-09-14` | The insurer's workbook: its `uid` |
  | `gallagher-2026-09-14-old` | The insurer's workbook: its `old_uid` |
  | `gallagher-2026-09-14-earlier` | The insurer's earlier ids |

  `trigger_code` is filled where a sheet's window is now one trigger of a window. `note` says when a
  sheet's single window is several windows here. Ten old uids have no window to map to.

## Budgets

- **`amt` is the window's CERF money:** the most that window can release. Other funds are in
  `v_window_budget`: country-based and regional pooled funds such as `cbpf-nga`, and each row's
  provenance. These are amounts authorised in advance, not cash disbursed.
- **Windows do not simply add up.** A window with `cannot_trigger_if` cannot release once the named window
  has. Windows linked that way count once, at their largest amount; every other window adds. A version
  whose windows are `capped` stays within its document's envelope (Ethiopia drought 2026: $10M + $3M,
  capped at $10M). Some versions release their whole envelope once, whichever window triggers first
  (`window_rollup` = `exclusive`).
- **For a version's most CERF can release in one activation, read `v_version_funding`.** Take `total_usd`
  where `kind = 'prearranged'` and `fund_code = 'cerf'`. It applies all of the rules above (D215). Don't
  sum `amt` yourself.
- **Several activations a year:** `framework_version.activations_per_year` says how many times the
  envelope can be used in a year. The Cuba, Haiti and Philippines storm frameworks allow 2, and DRC
  cholera allows 4. A year's maximum is the per-activation total times that number.
- **Readiness windows** release a small share first, within the same activation. Some have no amount
  (Nepal floods: the share is set in CERF's project budgets).

## Historical activations

- **Simulated and real are kept apart.** `n_simulated` comes from the backtest; `n_real` counts the
  version's real activations; `n` is both, as the old matrix counted. Use `n_simulated` for
  probabilities.
- **`n_simulated` counts distinct events, not triggers.** It is the number of events (storms, seasons,
  outbreaks) that met any of the window's triggers that year. One storm meeting two triggers counts
  once.
- **The raw events** are in `v_trigger_event`, one row per trigger and event. `event_label` is the
  storm's name (empty for a season), `event_date` a date where the source gives one, and `met` is
  true or false: false rows were tested and did not trigger. `recorded_in` says whether the row
  was entered at trigger level (`trigger_event`) or comes from the window's own record.
- **Blank or zero:** each trigger's analysis years are in `v_window_trigger` (`analysis_start`,
  `analysis_end`; the window's years where the trigger has none). A year inside that range with no
  event is 0, meaning assessed with no activation. A year outside it is blank, meaning not assessed.
  `v_cerf_activation_history` only has rows for years with an event, so the zeros have to be added
  (query 2 below).
- **Season labels:** southern-hemisphere storms are labelled by the season's end year (Evan, December
  2012, is 2013). The insurer's workbook labels them by the first year, so its years are one less.
- **The probability** (`framework_probability`, when `empirical`) is the share of analysis years with at
  least one simulated event, not the number of events a year.
- **Where the history is thinner:**
  - Some histories are yearly counts with no names, because no per-event source exists yet: the
    Philippines storms, DRC cholera, and the Dry Corridor's Postrera.
  - Some active windows have no backtest in the database at all, so they have no probability.
  - Haiti's readiness copies its action trigger's storms.

## Status

- **`v_cerf_window.status`:**
  - `Active`: the framework's latest endorsed version;
  - `Outdated`: an earlier endorsed version;
  - `Under development`;
  - `Closed`: the framework is retired.
- **It always comes from the database.** Never copy a status from a sheet: they go out of date.
- **The framework's own status is separate:** active, being updated or in development is
  `v_framework_lifecycle.lifecycle`. A framework can be "being updated" while its windows show `Active`,
  for example after an activation released its money (Ethiopia drought 2026). Which windows have already
  fired is in `window_status.triggered`.

## Example queries

All of these run on the database as it stood on 10 November 2026.

**1. The `window_level` sheet, for current windows**

```sql
SELECT uid, iso3, shock, window_name, type, amt, framework_probability, framework_rp_method,
       exposure_calc, overall_framework_prob, status, cannot_trigger_if, monitor_months
FROM aa.v_cerf_window
WHERE status = 'Active'
ORDER BY uid;
```

**2. The `activation_history` matrix, with blanks for years not assessed**

```sql
WITH w AS (
  SELECT c.uid, min(t.analysis_start) AS a0, max(t.analysis_end) AS a1
  FROM aa.v_cerf_window c
  JOIN aa.v_window_trigger t USING (country_iso3, hazard, version, window_code)
  WHERE c.status = 'Active'
  GROUP BY c.uid)
SELECT w.uid, y.year,
       CASE WHEN h.year IS NOT NULL THEN h.n_simulated
            WHEN y.year BETWEEN w.a0 AND w.a1 THEN 0 END AS n_simulated,   -- NULL = not assessed
       coalesce(h.n_real, 0) AS n_real
FROM w
CROSS JOIN generate_series(1980, 2026) AS y(year)
LEFT JOIN aa.v_cerf_activation_history h ON h.uid = w.uid AND h.year = y.year
ORDER BY w.uid, y.year;
```

**3. What an old uid is now**

```sql
SELECT source, cerf_uid, uid, window_code, trigger_code, note
FROM aa.v_cerf_uid_crosswalk
WHERE cerf_uid = 'hti_storms_v2_wt2';
```

**4. The storms behind a window's history**

```sql
SELECT trigger_code, event_year, event_label, event_date, met
FROM aa.v_trigger_event
WHERE country_iso3 = 'HTI' AND hazard = 'storm' AND version = '2026-10-16'
  AND window_code = 'wt_action'
ORDER BY event_date;
```

**5. A window's money by fund**

```sql
SELECT window_code, fund_code, amount_usd, provenance
FROM aa.v_window_budget
WHERE country_iso3 = 'NGA' AND hazard = 'flood' AND version = '2026-07-27' AND kind = 'prearranged'
ORDER BY window_code, fund_code;
```

**6. Each current version's most CERF can release, per activation and per year**

```sql
SELECT DISTINCT f.country_iso3, f.hazard, f.version,
       f.total_usd AS cerf_per_activation,
       coalesce(v.activations_per_year, 1) AS activations_per_year,
       f.total_usd * coalesce(v.activations_per_year, 1) AS cerf_per_year
FROM aa.v_version_funding f
JOIN aa.framework_version v USING (country_iso3, hazard, version)
JOIN aa.v_cerf_window c USING (country_iso3, hazard, version)
WHERE f.kind = 'prearranged' AND f.fund_code = 'cerf' AND f.financier IS NULL
  AND c.status = 'Active'
ORDER BY 1, 2;
```

## Keeping in step

- **Changes arrive as entries files** that the nightly run applies. A change to the tables or views comes
  as a pull request to `src/ds_aa_tracking/schema.py`. Changes to the database are additions (D203): a
  column or view this note names keeps its meaning.
- **Three views list what is still incomplete:**
  - `v_trk_window_links`: rows below a window that name no window of their version;
  - `v_trk_trigger_check`: windows whose trigger events and simulated years disagree;
  - `v_trk_version_numbers`: versions without a number.
- **Some framework documents are not public** (their `framework_document.is_public` is false). Their
  figures stay inside the team's tools; don't republish them.
