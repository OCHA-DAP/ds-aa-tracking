# Target schema & migration plan — unified versions, multi-fund everything

Requirements this plan satisfies:

1. `framework_version_map` (KB) and `framework_version` (this repo) unify into one
   version registry.
2. A CBPF/regional-fund allocation mirror from OneGMS is coming — the model must
   accommodate it without another redesign.
3. One activation can draw allocations from multiple funds simultaneously
   (e.g. Nigeria floods Sep 2025: CERF $5.0M + NHF $2.0M — one activation, two
   allocations).
4. A framework version can hold pre-arranged funding from multiple sources at once:
   CERF, CBPF/regional funds, and co-financing from other agencies.
5. Funding breakdowns (window/readiness-action, agency, sector splits) vary per fund.

## Target model

### Funds as a dimension

```sql
CREATE TABLE aa.fund (
    fund_code text PRIMARY KEY,       -- 'cerf', 'cbpf-nga' (NHF), 'cbpf-ssd' (SSHF),
                                      -- 'rhpf-wca', 'agency-wfp', 'agency-unicef', …
    fund_type text NOT NULL,          -- cerf | cbpf | regional_fund | agency_cofinancing
    name text NOT NULL,
    country_iso3 text                  -- for country-based pooled funds
);
```

Every `fund_source` column in the schema becomes a `fund_code` reference. Sheets that
only say "Country Fund" map to a placeholder (`cbpf-unspecified`) until curated.

### Unified version registry

`aa.framework_version` (this repo) is THE registry — identity `(country_iso3, hazard,
version)`, already carrying `kb_framework` for KB-page joins, `valid_from/valid_until`,
`doc_url`, `analysis_ref`, provenance. `framework_version_map` shrinks to what it
uniquely holds — the trigger-performance source crosswalk:

```sql
CREATE TABLE aa.trigger_source_crosswalk (   -- KB-owned, replaces framework_version_map
    country_iso3 text NOT NULL,
    hazard text NOT NULL,
    version text NOT NULL,            -- references aa.framework_version (by convention)
    gsheet_tab text, excel_fv text, flag text,
    overall_rp_reported numeric, overall_prob_reported numeric,
    overall_spend_reported bigint,
    PRIMARY KEY (country_iso3, hazard, version)
);
```

KB fact tables (`window`, `simulated_activation`, `funding_breakdown`,
`actual_activation`, `activation_allocation`) keep their `(kb_framework, kb_version,
country_iso3)` keys initially (no big-bang re-key) — `framework_version` carries both
key forms, so every join resolves through it. Re-keying those tables to
`(country_iso3, hazard, version)` is a later, optional cleanup.

### Activations vs allocations (grain fix)

Today's `activation_event` rows are really *allocation-grain* (Julia's sheet has one
row per activation × fund). Split:

```sql
CREATE TABLE aa.activation (               -- one row per real-world activation event
    country_iso3 text NOT NULL,
    hazard text NOT NULL,
    year smallint NOT NULL,
    month smallint,
    event_label text,                      -- disambiguates same-month events
    event_type text NOT NULL,              -- framework_aa | adhoc_aa | early_action
    version text,                          -- null for adhoc/EA
    window_name text,                      -- the window that triggered (null for
                                           -- adhoc/EA; inherited from KB
                                           -- actual_activation.window_name)
    version_match text,
    kb_framework text, kb_event_date text, -- KB crosswalk (until unified)
    people_targeted bigint,
    reported_to_ahub text,
    comments text,
    UNIQUE NULLS NOT DISTINCT (country_iso3, hazard, year, month, event_label)
);

CREATE TABLE aa.activation_funding (       -- one row per activation × fund allocation
    country_iso3 text NOT NULL,
    hazard text NOT NULL,
    year smallint NOT NULL,
    month smallint,
    event_label text,                      -- FK-by-convention to aa.activation
    fund_code text NOT NULL,               -- references aa.fund
    allocation_code text,                  -- CERF application_code / CBPF allocation
                                           -- code once the mirror exists
    amount_usd numeric,
    match_method text,
    UNIQUE NULLS NOT DISTINCT
        (country_iso3, hazard, year, month, event_label, fund_code, allocation_code)
);
```

The KB's `activation_allocation` link table gains a `fund_code` column (default
'cerf'); once the CBPF mirror lands, the same confirm-flow (`kb-aa-links`) can link
CBPF allocation codes. Nigeria Sep 2025 stops being an "amount conflict": one
activation, two funding rows summing to the KB's $7M.

### Allocation mirrors, fund-agnostic downstream

- `aa.cerf_allocation` (exists, ds-cerf-supplement) — unchanged.
- `aa.cbpf_allocation` (future, same OneGMS feed family) — same shape where possible:
  allocation_code PK, country, dates, amounts, type/status, AA flag.
- `aa.v_allocation` — a UNION view (nothing stored) stacking the per-fund mirrors
  and normalizing them to `(fund_code, allocation_code, country_iso3, year,
  amount_usd, is_aa, dates…)`, so links and reconciliation never care which fund a
  code belongs to. Mirrors stay separate tables because they have separate feeds and
  writers.

### Pre-arranged funding, multi-source per version

`prearranged_funding` already keys on `(version-attributed framework, year, kind,
fund_source, source)`; changes:

- `fund_source` → `fund_code` (vocabulary above); `kind` stays
  (`prearranged | cofinancing | non_aa_mobilised`).
- agency co-financing rows become `fund_code = 'agency-<name>'` when the sheet names
  the agency (Yakubu's remarks often do), else `agency-unspecified`.
- fund-source *totals* ('all') remain flagged as totals and are never summed with
  component rows (already the case).

### Windows are universal; funding and activations attach to windows

Every framework version materializes **at least one explicit window row** — a
single-window framework gets one real window (`window_name = 'single'` unless the doc
names it) instead of funding hanging loosely off the version. `n_windows` and
`all_in` become properties you can read off the window set rather than metadata.

```sql
-- unified window registry (extends KB aa.window beyond performance-analyzed versions)
aa.window(country_iso3, hazard, version, window_name,
          all_in boolean, basis text, synthetic boolean,  -- synthetic = created to
          …)                                              -- make a single window explicit

-- the consolidated funding surface attaches to the WINDOW, not the version:
aa.v_version_funding(country_iso3, hazard, version, window_name NOT NULL, fund_code,
                     agency, sector, amount_usd, provenance, source)
-- provenance: doc-stated | imputed-5-95 | sheet | window-unattributed
```

- Single-window versions: all funding lands on the one explicit window — exact, no
  information loss.
- Multi-window versions where a source states only version-level totals: rows carry
  `provenance = 'window-unattributed'` (a review queue) rather than silently
  attaching to the version.
- Budgets that differ per fund per window are one row per (window × fund).
- `aa.activation.window_name` references the same window registry — which window
  actually triggered (the KB's `actual_activation.window_name` seeds this).
- `window.allocation_usd` (single stored total) eventually derives from
  `v_version_funding` instead of being stored.

## Migration phases

| # | What | Where | Breaks anything? |
|---|---|---|---|
| 0 | `aa.fund` seed; split `activation_event` → `activation` + `activation_funding`; `fund_code` vocabulary in `prearranged_funding`; reconciliation views updated | ds-aa-tracking (all owned here) | No — full-refresh tables, site adapts same day |
| 1 | CI check: every `framework_version_map` row must exist in `framework_version` (catches drift both ways); agree naming (`version`, `country_iso3`) | ds-knowledge-base PR | No |
| 2 | Extract `trigger_source_crosswalk`; `framework_version_map` becomes a compatibility VIEW over crosswalk + `framework_version`; `load_aa_performance.py` re-pointed | ds-knowledge-base | Consumers keep working via the view |
| 3 | Drop the compatibility view once `gen_trigger_performance.py`, ERD docs and the CERF exposure app stop referencing it | ds-knowledge-base | Coordinated |
| 4 | `aa.cbpf_allocation` mirror + `v_allocation`; `activation_allocation.fund_code`; extend kb-aa-links confirm flow to CBPF codes | ds-cerf-supplement (or a new onegms mirror repo) + ds-knowledge-base | No |
| 5 | `v_version_funding` consolidated view; optionally migrate KB `funding_breakdown` loader to write `fund_code`; optionally re-key KB fact tables to `(country_iso3, hazard, version)` | ds-knowledge-base | Optional cleanups |

Ordering notes: 0 and 1 are independent and immediate; 2–3 need a KB PR cycle;
4 waits on the CBPF feed being available; 5 is opportunistic.

## Open questions

1. **CBPF feed**: is the OneGMS CBPF allocation extract available with the same access
   as the CERF feed, and should the mirror live in ds-cerf-supplement (renamed scope)
   or a new repo?
2. **Writer of the unified registry**: this plan keeps `framework_version` written by
   ds-aa-tracking (sourced from KB frontmatter + sweeps + sheets). The KB repo then
   *reads* it — acceptable, or should the registry loader move into the KB repo?
3. **Event labels**: for same-month multi-event cases the `event_label` needs a
   convention (e.g. storm name, 'phase-2') — propose curating during the activation
   adjudication pass.
