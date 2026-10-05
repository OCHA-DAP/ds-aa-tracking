# Backtests: seals and errata

A framework version's **backtest** is its `aa.window` rows (the trigger windows, each with the
analysed years — the return-period denominator), its `aa.simulated_activation` rows (the years
the trigger *would have* fired) and its `aa.version_performance_reported` row (the published
headline figures). The database enforces two rules on every writer (the admin page, entries
files, the Databricks job, a laptop on the tunnel):

1. **A simulated year lies inside its window's analysis span**, and the window exists. A year
   after the analysed span is a real activation: it goes in `window_activation`, never in the
   backtest. (Checked at commit, so a file can move the span and the years in either order.)
2. **A sealed backtest changes only through an erratum.** `framework_version.backtest_sealed_at`
   is set once the backtest has been checked against the endorsed document; from then on the
   `guard_sealed` trigger refuses any insert, update or delete touching that version — unless it
   runs inside an erratum applied by `scripts/apply_backtests.py`. Clearing or changing a seal,
   relabelling or deleting a sealed version is refused the same way. An update that changes
   nothing (a re-read confirming the record) passes.

## Which path

| The version is… | To change its backtest |
|---|---|
| in development, or endorsed but unsealed | an **entries file**: `op: replace` with a `scope` of `country_iso3/hazard/version` makes the given rows the version's rows (years that dropped out go too); `op: delete` removes one row. **Immediately** through the proxy's `POST /entries` (dry run first — what the `record-simulated-activations` skill does, from any repo), or on the private blob for the nightly job (`scripts/apply_entries.py --upload`). Or the admin page. |
| endorsed and checked against its document | add it to a **seal** file here (`seals/`). |
| sealed, and the database doesn't match the document | an **erratum**, kind `transcription` (`errata/`). |
| sealed, and the endorsed backtest itself is wrong | an **erratum**, kind `analysis-note` (no changes; it's recorded and shown). The fix is a **new version**: a changed analysis after endorsement is a revision, not an edit. |
| about to be endorsed under a new label | relabel **before** sealing (`nightly.py --relabel ISO3/HAZARD/OLD NEW`). |

## Files

`errata/<YYYY-MM-DD>-<iso3>-<hazard>-<version>.json` — one correction, applied once, in one
transaction; immutable once applied (a later fix is a new file):

```json
{"kind": "transcription",
 "reason": "what was wrong and why the new values are right",
 "evidence": "the endorsed document (link) + page / table",
 "requested_by": "who",
 "changes": [
   {"op": "delete", "table": "simulated_activation", "key": {"country_iso3": "…", "hazard": "…", "version": "…", "window_name": "…", "event_year": 2025}, "why": "…"},
   {"op": "update", "table": "window", "key": {"country_iso3": "…", "hazard": "…", "version": "…", "window_name": "…"}, "set": {"analysis_end": 2024}, "why": "…"},
   {"op": "insert", "table": "simulated_activation", "row": {"…": "…"}, "why": "…"}]}
```

`key` is exactly the table's primary key. Tables: `window`, `simulated_activation`,
`version_performance_reported`, `framework_version`. Each applied erratum is a row in
`aa.backtest_erratum` with the before-values of every row it changed, and each change is
audited in `aa.entry_audit` as `errata:<id>`.

`seals/<name>.json` — versions verified against their documents:

```json
{"sealed_by": "who", "note": "…",
 "versions": [{"version": "ISO3/hazard/version", "against": "the document (link) + page / table"}]}
```

A version is sealed only if it has windows and no simulated year outside its span; one already
sealed is left alone.

**This repo is public.** An erratum for a version whose framework document is not public goes
on the private dev blob instead (`projects/ds-aa-tracking/errata/<id>.json`, same format; the
nightly job reads both).

## Running

The nightly job applies pending files after the entries files and before the snapshot. By hand
(through the tunnel, or against a restored snapshot):

```sh
uv run python scripts/apply_backtests.py --dry-run   # applies each file in a transaction,
                                                      # runs every check, rolls back
uv run python scripts/apply_backtests.py
```

A dry run checks each file against the database *as it is*: a seal that depends on an erratum
in the same batch (a span fixed first) fails in the dry run and passes in the real one, where
the errata are applied before the seals.

`aa.v_trk_backtest_check` is the curation queue: simulated years outside a span or after the
version took effect, windows without a span, computed-vs-reported RP drift, and the endorsed
backtests not yet sealed.

## History

- **2026-10-05** — the backtest tables moved here from the knowledge base's loader, with the
  guards. The KB-era record had real activations appended to the backtests of six versions
  (COD cholera 2025, HTI storm 2024, MDG storm 2024, NER flood 2025, PHL storm 2025, TCD
  drought 2025 — spans stretched to cover them), the Haiti 2024 backtest replaced by a
  recomputation made after Hurricane Melissa, two spans a year short of their own tables (AFG
  drought 2026, MOZ storm 2026) and two backtests under year labels that are no version (AFG
  and GTM drought '2025'). All checked against the endorsed documents and corrected
  (`errata/2026-10-05-*`); the four that now match their document in full are sealed
  (`seals/2026-10-05-*`).
