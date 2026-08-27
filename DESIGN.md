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
                                      -- 'rhpf-wca', …
    fund_type text NOT NULL,          -- cerf | cbpf | regional_fund
    name text NOT NULL,
    country_iso3 text                  -- for country-based pooled funds
);
```

`aa.fund` holds **OCHA pooled funds only** (CERF, CBPFs, regional funds — things that
can have allocation mirrors). **Agency co-financing is NOT a fund**: it is not OCHA
money, amounts are soft, and no mirror will ever exist for it. Co-financing rows in
`prearranged_commitment` carry a free-text `financier` instead of a `fund_code`
(`CHECK ((fund_code IS NULL) = (kind = 'cofinancing'))`). Every other `fund_source`
column becomes a `fund_code` reference; sheets that only say "Country Fund" map to a
placeholder (`cbpf-unspecified`) until curated.

### Unified version registry

**A version IS an endorsed document.** Analytical revalidations or draft reports
without an endorsed doc are not versions (their analysis attaches to the nearest
endorsed version's notes). Endorsement comes from one of two authorities, recorded in
`endorsed_by`:

- `erc` — major revisions: recommits funds, starts a new validity period;
- `cerf_secretariat` — minor revisions: same validity period and budget as the
  predecessor (so `valid_until`/budget are *inherited*, recorded as such).

**Versions are ENTERED, never inferred**, once data entry happens in this system —
the interval-inference used to backfill the sheets is a migration-era crutch and must
not survive into the entry workflow. `valid_until_source` distinguishes `doc-stated`
validity from `convention` (maintainer rules like "+2 years for pilots") and
`inherited` (secretariat revisions) — post-validity review flags weigh doc-stated
dates more heavily than convention ones.

**Regional frameworks do not exist** — they are groupings of national frameworks that
may happen to share a regional document. The Dry Corridor is three national framework
rows (SLV/GTM/HND) whose versions share one `doc_url`; no framework-group entity, no
regional pseudo-country codes.

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
    event_type text NOT NULL,              -- framework_aa | adhoc_aa | early_action
    version text,                          -- null for adhoc/EA
    window_name text,                      -- EVERY framework activation activates a
                                           -- window: NOT NULL when event_type =
                                           -- 'framework_aa' (adhoc/EA have none)
    event_date text NOT NULL,              -- partial ISO, AS SPECIFIC AS KNOWN:
                                           -- 'YYYY' | 'YYYY-MM' | 'YYYY-MM-DD' |
                                           -- 'YYYY-MM-DDTHH:MM' — datetime matters
                                           -- for cyclones; sheet-era rows stay at
                                           -- month grain until curated. Extends the
                                           -- KB's event_date convention; ISO text
                                           -- sorts correctly at any precision.
    event_label text NOT NULL DEFAULT '',  -- last-resort tie-breaker only: same
                                           -- window triggering more than once at the
                                           -- same recorded time (very unlikely —
                                           -- uncharted territory). Convention: storm
                                           -- name first, else admin area, else
                                           -- 'phase-N'; set at curation, never
                                           -- invented by a loader
    kb_framework text, kb_event_date text, -- KB crosswalk (until unified)
    people_targeted bigint,
    reported_to_ahub text,
    comments text,
    CHECK ((event_type = 'framework_aa') = (window_name IS NOT NULL)),
    UNIQUE (country_iso3, hazard, event_date, window_name, event_label)
        NULLS NOT DISTINCT
);

CREATE TABLE aa.activation_funding (       -- one row per activation × fund allocation
    country_iso3 text NOT NULL,
    hazard text NOT NULL,
    event_date text NOT NULL,
    window_name text,
    event_label text NOT NULL DEFAULT '',  -- FK-by-convention to aa.activation
    fund_code text NOT NULL,               -- references aa.fund
    allocation_code text,                  -- CERF application_code / CBPF
                                           -- 'cbpf-<fund>-<id>' via aa.v_allocation
    amount_usd numeric,
    match_method text,
    UNIQUE NULLS NOT DISTINCT
        (country_iso3, hazard, event_date, window_name, event_label,
         fund_code, allocation_code)
);
```

The KB's `activation_allocation` link table gains a `fund_code` column (default
'cerf'); once the CBPF mirror lands, the same confirm-flow (`kb-aa-links`) can link
CBPF allocation codes. Nigeria Sep 2025 stops being an "amount conflict": one
activation, two funding rows summing to the KB's $7M.

### Allocation mirrors, fund-agnostic downstream

- `aa.cerf_allocation` (exists, ds-cerf-supplement) — unchanged.
- `aa.cbpf_allocation` (**built, Aug 2026** — ds-cerf-supplement, from the public CBPF
  OData API): one row per Standard/Reserve allocation envelope (a set of approved
  projects), keyed `(pooled_fund_id, allocation_type_id)` — AllocationTypeId alone
  collides across funds. Plus `aa.cbpf_fund` (46 pooled funds incl. RhPF envelopes).
  ds-cerf-supplement is the home of ALL OneGMS mirrors going forward.
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
                                                          -- make a single window explicit
          basis text NOT NULL,      -- observational | forecast | mixed
          trigger_statement text,   -- the trigger condition in plain text, as stated
                                    -- in the endorsed framework doc for this window
                                    -- (e.g. "7-day GloFAS forecast ≥70% probability of
                                    -- exceeding the 1-in-2-year level at Chatara");
                                    -- sourced from the doc / KB page at ingestion
          …)

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
- Window identity is **per version** — no continuity is enforced across versions
  (windows often change meaningfully between revisions; cross-version comparisons are
  an analysis concern, not a schema constraint).
- `window.allocation_usd` (single stored total) eventually derives from
  `v_version_funding` instead of being stored.

## Further simplifications (same spirit as window-first)

**One activation table, not two.** Today real activations live twice: KB
`actual_activation` (synced from framework-page frontmatter) and our
`activation`(+`activation_funding`), crosswalked by matching. Target: a single
`aa.activation` registry; the KB page sync writes into it (framework events), the
sheets/history seed the rest, and `activation_allocation` dissolves into
`activation_funding` (which already carries fund_code + allocation_code). One event,
one row, N funding rows — no more match_method between two tables that mean the same
thing.

**Calendar becomes window months.** `framework_calendar` mixes trigger-window months
(a property of the *window* — green cells) with process milestones (proposal
development, finalization deadlines — planning/PM info, out of scope for a tracking
schema). Target: `aa.window_month` (window monitoring months, seeded from calendar
greens + KB `monitoring_period` frontmatter); the process-phase cells are simply not
carried forward (recoverable from the raw sheet if ever needed). The calendar table
retires.

**`people_covered` attaches to the window** like funding does (partial activations
cover a window's population, e.g. Chad's $4M partial covering 244k of 400k); rows a
source states only at version level get `window-unattributed` provenance on
multi-window frameworks — same rule as funding, one pattern everywhere.

**Derive expected status; keep only observed status.** Much of `framework_status` is
derivable from the version registry itself (endorsed version in validity = active;
successor in development = under revision; `valid_until` passed with no successor =
expired/dormant). Target: `v_expected_status` computed from `framework_version`, with
`framework_status` retained strictly as *observed* snapshots (what colleagues
reported) and a diff view — status conflicts become "reported vs derived" instead of
"sheet vs sheet".

**Names and regions live in exactly one place.** Fact tables drop denormalized
`country_name`/`region` columns; the registry (and ISO3) is the single source —
display names are a rendering concern.

**One allocation-correction surface.** Our `emergency_type_override` (retags) and the
mirror's `cerf_supplement` (not_tc / not_drought / valid periods) are the same kind of
thing: human corrections to allocation metadata. Target: fold retags into the mirror's
supplement via its existing issue-confirm flow, retiring our table.

**Sheet 'subunits' are windows.** `prearranged_sector_budget.subunit`
(Bangladesh Jamuna/Padma) is renamed `window_name` now and folds into
`v_version_funding`'s window axis at consolidation — no separate concept.

**Application-level sheet tables are transitional.** `cerf_application_people`,
`cerf_application_report` and `cerf_allocation_extra` exist because the sheets carried
them; as mirror feed coverage is verified (per-project demographics summing to
application level, narratives, the structured AA flag) each retires into the mirror.

**`cerf_cva_history` is parked, not designed-in.** Country×agency×year grain with no
allocation codes can never link to anything; it stays as 2020-2023 context and may be
revived if a CVA workstream needs it — target-state CVA is project-level.

**Registry slims to identity + pipeline.** Its irreplaceable job is holding
(country, hazard) identities — including pipeline frameworks with no version yet.
`region`/`language` are derivable conveniences, nothing more.

**EA tagging is CERF's.** Early-action rows are whatever CERF tags as EA; the
EA/rapid-response boundary is not recomputed here.

**Deliberately NOT merged:** `prearranged_funding` (a commitment per version × fund ×
calendar year — the annual renewal/extension record) stays separate from
`v_version_funding` (the structural split of a version's budget). They answer
different questions; the invariant `sum(structural split per fund) = committed amount
per fund` becomes a load-time check, not a merge.

## Migration phases

| # | What | Where | Breaks anything? |
|---|---|---|---|
| 0 | ~~`aa.fund` seed; split `activation_event` → `activation` + `activation_funding`; `fund_code` vocabulary in `prearranged_funding`; reconciliation views updated~~ **done (Aug 2026)** | ds-aa-tracking | Done |
| 1 | CI check: every `framework_version_map` row must exist in `framework_version` (catches drift both ways); agree naming (`version`, `country_iso3`) | ds-knowledge-base PR | No |
| 2 | Extract `trigger_source_crosswalk`; `framework_version_map` becomes a compatibility VIEW over crosswalk + `framework_version`; `load_aa_performance.py` re-pointed | ds-knowledge-base | Consumers keep working via the view |
| 3 | Drop the compatibility view once `gen_trigger_performance.py`, ERD docs and the CERF exposure app stop referencing it | ds-knowledge-base | Coordinated |
| 4 | ~~`aa.cbpf_allocation` mirror + `v_allocation`~~ **done (Aug 2026)**; CBPF project-level mirror also done (cbpf_project/_cluster/_subip); remaining: `activation_allocation.fund_code`, extend kb-aa-links confirm flow to CBPF codes | ds-cerf-supplement + ds-knowledge-base | No |
| 5 | `v_version_funding` consolidated view; optionally migrate KB `funding_breakdown` loader to write `fund_code`; optionally re-key KB fact tables to `(country_iso3, hazard, version)` | ds-knowledge-base | Optional cleanups |
| 6 | Simplifications above: unify activation tables, calendar → `window_month`, window-attached `people_covered`, `v_expected_status`, denormalized-column cleanup, retags into `cerf_supplement` | ds-aa-tracking + ds-knowledge-base + mirror repo | Coordinated, after 0–4 settle |

Ordering notes: 0 and 1 are independent and immediate; 2–3 need a KB PR cycle;
4 waits on the CBPF feed being available; 5 is opportunistic.

## Open questions

2. **Writer of the unified registry**: this plan keeps `framework_version` written by
   ds-aa-tracking (sourced from KB frontmatter + sweeps + sheets). The KB repo then
   *reads* it — acceptable, or should the registry loader move into the KB repo?
3. **Event labels**: for same-month multi-event cases the `event_label` needs a
   convention (e.g. storm name, 'phase-2') — propose curating during the activation
   adjudication pass.

## Parking lot — next-stage notes (2026-08, pre-CERF discussions)

Unscoped items captured from working discussions; none are commitments yet.

**Data administration & pipeline**

- General data-administration pipeline with named responsibilities and update
  frequencies per table/source (who updates what, how often, from where).
- CERF to share their taxonomy definition — align our vocabularies (hazards,
  statuses, windows, funds) to it and record the mapping.
- Verify terminology against CERF and CBPF usage — particularly around
  **sub-granting** (CERF subgrants vs CBPF sub-implementing partners are different
  mechanisms; make sure our column names and site copy use each fund's own terms).
- Pilot the data-update forms (the demo entry form → real backend), with a defined
  spectrum per data type: **automated / semi-automatic / manual** entry.
- Framework ingestion policy: **LLM-drafted with human confirmation** as the only
  ingestion path (no pure-manual page writing), while keeping a separate, explicit
  record of **official endorsement confirmation** (who confirmed the endorsement,
  when — distinct from who confirmed the data entry).

**Content & scope**

- Include the **indicator reporting** agencies must do for their projects
  (project-level indicators from CERF/CBPF reporting — a new fact layer below
  sectors).
- Include the **evidence base** from the (CERF) compendium — link frameworks/
  activations to their evidence entries.
- Define **public vs private** per table/field (what can go on a public site vs
  what stays behind the password — focal points and planning are the obvious
  private candidates; activations and funding are largely public already).

**Site**

- Download buttons (CSV/XLSX) on tables and dashboards.
- A visually appealing **landing page** (the current Overview is a working index,
  not a front door).
