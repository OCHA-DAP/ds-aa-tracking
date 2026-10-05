"""DDL for the ds-aa-tracking tables in the dev `aa` schema.

Conventions (shared with the existing `aa` writers):
- natural text keys; UNIQUE NULLS NOT DISTINCT composites on fact tables
- this repo is the single writer of every table below — since 2026-10-05 that includes
  the tables the knowledge base's loaders used to write (window, simulated_activation,
  version_performance_reported, funding_breakdown, actual_activation,
  activation_allocation; see BACKTEST_TABLES / KB_ERA_TABLES). It never writes the
  ds-cerf-supplement mirror tables (cerf_allocation, cerf_project*, cerf_supplement,
  cerf_allocation_storm)
- full-refresh loads (truncate + insert in one transaction)
- source rows that conflict across sheets are kept side by side (source in the key);
  reconciliation happens in views, not at load time
"""

TABLES = {
    # ------------------------------------------------ framework-level tracking
    # the (country, hazard) pair — the identity everything hangs off. Not a registry of
    # frameworks: a pair may have no version yet (pipeline) or several over time.
    # Hierarchy: country_hazard -> framework_version -> window -> {window_activation,
    # simulated_activation, window_funding}; ad hoc / early-action allocations attach to
    # the pair directly (adhoc_activation), never to a version.
    "country_hazard": """
        CREATE TABLE IF NOT EXISTS aa.country_hazard (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            country_name text NOT NULL,
            hazard_raw text,
            region text,
            kb_framework text,
            language text,
            us_prio boolean,
            coordination_group text,
            in_kb boolean NOT NULL DEFAULT false,
            retired boolean NOT NULL DEFAULT false,   -- manual: framework retired (hidden
                                                      -- from the map, whatever its versions say)
            retired_note text,
            technical_support boolean NOT NULL DEFAULT false,  -- OCHA supported the
                                                      -- framework technically, no funding
            technical_support_note text,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (country_iso3, hazard)
        )""",
    "framework_version": """
        CREATE TABLE IF NOT EXISTS aa.framework_version (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            version text NOT NULL,         -- date label matching KB page (YYYY[-MM[-DD]])
            kb_framework text,
            kb_status text,                -- endorsed | development | pre-development.
                                           -- 'superseded' is INFERRED (a newer endorsed
                                           -- version exists); retirement is a flag on
                                           -- country_hazard, not a version status
            valid_from date,
            valid_until date,
            valid_until_source text,       -- doc-stated | convention | inherited
            endorsed_by text,              -- erc (major revision, recommitted funds,
                                           -- new validity) | cerf_secretariat (minor
                                           -- revision, same validity + budget)
            supersedes text,
            prearranged_usd_doc numeric,   -- from KB frontmatter (cross-check)
            backtest_sealed_at timestamptz,  -- set = the backtest (window, simulated_
                                           -- activation, version_performance_reported
                                           -- rows) is verified against the endorsed
                                           -- document and frozen: changing it needs an
                                           -- erratum (backtests/errata/, applied by
                                           -- scripts/apply_backtests.py)
            backtest_sealed_by text,
            backtest_sealed_against text,  -- what it was verified against: the document
                                           -- (title / sha256 / table page) or the analysis
            doc_title text,
            doc_url text,                  -- endorsed framework document (PDF)
            analysis_ref text,             -- trigger analysis, e.g. repo@branch:path
            window_rollup text,            -- how window funding rolls up to the total:
                                           -- additive (all windows can fire; total = sum)
                                           -- exclusive (either/or; each window can draw
                                           --   up to the shared pot; total = max)
                                           -- capped (windows sum past the envelope;
                                           --   first to fire draws down)
            source text NOT NULL,          -- kb-frontmatter | sheet-revision | ocha-web | pa-monorepo | entered
            note text,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (country_iso3, hazard, version)
        )""",
    "framework_status": """
        CREATE TABLE IF NOT EXISTS aa.framework_status (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            as_of date NOT NULL,
            source text NOT NULL,
            status text NOT NULL,
            status_raw text,
            revised_on date,
            funding_change text,
            q1_ready boolean,
            expected_status text,
            comments text,
            version text,                  -- attributed framework version (see framework_version)
            version_match text,            -- kb-activation | auto-interval | auto-post-validity
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (country_iso3, hazard, as_of, source)
        )""",
    "framework_focal_point": """
        CREATE TABLE IF NOT EXISTS aa.framework_focal_point (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            role text NOT NULL,
            person text NOT NULL,
            as_of date NOT NULL,
            source text NOT NULL,
            version text,                  -- attributed framework version (see framework_version)
            version_match text,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (country_iso3, hazard, role, person, as_of)
        )""",
    "framework_calendar": """
        CREATE TABLE IF NOT EXISTS aa.framework_calendar (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            month smallint NOT NULL CHECK (month BETWEEN 1 AND 12),
            phase text NOT NULL,
            is_finalization_deadline boolean NOT NULL DEFAULT false,
            version text,                  -- attributed framework version (see framework_version)
            version_match text,            -- kb-activation | auto-interval | auto-post-validity
            as_of date NOT NULL,
            source text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (country_iso3, hazard, month, phase, as_of)
        )""",
    # ALL framework funding hangs off the WINDOW: pre-arranged envelopes, co-financing,
    # and the agency x sector split. window_name is one of the version's windows, or the
    # sentinels 'single' (a one-window framework whose window is not named) and
    # 'unattributed' (the source stated a version-level figure for a multi-window
    # framework — a curation queue, never silently attached to a window).
    # Envelope rows have agency AND sector NULL; split rows carry agency and/or sector.
    # Never sum envelope and split rows together.
    "window_funding": """
        CREATE TABLE IF NOT EXISTS aa.window_funding (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            version text NOT NULL,
            window_name text NOT NULL,     -- window | 'single' | 'unattributed'
            kind text NOT NULL,            -- prearranged | cofinancing | non_aa_mobilised
            fund_code text,                -- references aa.fund; NULL for non-OCHA money
            financier text,                -- who co-finances (agency etc.) — free text
            agency text,                   -- split rows only
            sector text,                   -- split rows only
            amount_usd numeric,
            year smallint,                 -- commitment / calendar year where the source
                                           -- gave one (sheet-era annual commitments)
            provenance text NOT NULL,      -- doc-stated | kb | sheet | entered | window-unattributed
            source text NOT NULL,
            note text,
            updated_at timestamptz NOT NULL DEFAULT now(),
            CHECK ((fund_code IS NULL) = (kind IN ('cofinancing', 'non_aa_mobilised'))),
            UNIQUE NULLS NOT DISTINCT
                (country_iso3, hazard, version, window_name, kind, fund_code, financier,
                 agency, sector, year, source)
        )""",
    "people_covered": """
        CREATE TABLE IF NOT EXISTS aa.people_covered (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            as_of date NOT NULL,
            source text NOT NULL,
            people_covered bigint,
            double_activation text,        -- maybe | no | not_clear
            additional_people_covered bigint,
            remarks text,
            version text,                  -- attributed framework version (see framework_version)
            version_match text,            -- kb-activation | auto-interval | auto-post-validity
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (country_iso3, hazard, as_of, source)
        )""",
    "fund": """
        CREATE TABLE IF NOT EXISTS aa.fund (
            fund_code text PRIMARY KEY,    -- cerf | cbpf-<iso3> | rhpf-<env>[-<iso3>]
            fund_type text NOT NULL,       -- cerf | cbpf | regional_fund
            name text NOT NULL,
            country_iso3 text,
            pf_id integer,                 -- source id in aa.cbpf_fund / OneGMS
            updated_at timestamptz NOT NULL DEFAULT now()
        )""",
    # a FRAMEWORK activation is a window firing: keyed to the window. window_name must be
    # one of the version's windows (aa.window / entered_window) — 'unspecified' stays
    # allowed for sheet-era rows until curated. Ad hoc / early-action allocations live in
    # adhoc_activation, off the (country, hazard) pair.
    # donor earmarks to the OCHA AA project itself ("build" money) — not pooled-fund
    # income, so not in the contribution mirrors; a handful of rows a year, hand-entered
    # (admin page). Donor names follow aa.v_contribution.donor so the donor dashboard
    # can line them up with the pooled-fund shares.
    "build_contribution": """
        CREATE TABLE IF NOT EXISTS aa.build_contribution (
            donor text NOT NULL,
            year smallint NOT NULL,
            amount_usd numeric,
            purpose text NOT NULL DEFAULT 'OCHA AA project',
            source text NOT NULL,
            note text,
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE NULLS NOT DISTINCT (donor, year, purpose, source)
        )""",
    "window_activation": """
        CREATE TABLE IF NOT EXISTS aa.window_activation (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            version text NOT NULL,
            window_name text NOT NULL,
            event_date text NOT NULL,      -- partial ISO, as specific as known
            event_label text NOT NULL DEFAULT '',
            full_activation boolean,       -- false = partial window trigger
            people_targeted bigint,
            url text,                      -- announcement / allocation link
            reported_to_ahub text,
            kb_event_date text,            -- KB actual_activation crosswalk
            comments text,
            source text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (country_iso3, hazard, version, window_name, event_date, event_label)
        )""",
    "adhoc_activation": """
        CREATE TABLE IF NOT EXISTS aa.adhoc_activation (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            event_type text NOT NULL,      -- adhoc_aa | early_action
            event_date text NOT NULL,
            event_label text NOT NULL DEFAULT '',
            people_targeted bigint,
            reported_to_ahub text,
            comments text,
            source text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            CHECK (event_type IN ('adhoc_aa', 'early_action')),
            PRIMARY KEY (country_iso3, hazard, event_type, event_date, event_label)
        )""",
    "activation_funding": """
        CREATE TABLE IF NOT EXISTS aa.activation_funding (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            event_date text NOT NULL,
            window_name text,
            event_label text NOT NULL DEFAULT '',
            event_type text NOT NULL,      -- FK-by-convention to aa.activation
            fund_code text NOT NULL,       -- references aa.fund; *-unspecified
                                           -- placeholders until curated
            allocation_code text,          -- via aa.v_allocation (CERF application_code
                                           -- or cbpf-<fund>-<id>)
            amount_usd numeric,
            people_targeted bigint,        -- as reported per allocation
            reported_to_ahub text,
            match_method text,
            source text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE NULLS NOT DISTINCT
                (country_iso3, hazard, event_date, window_name, event_label,
                 event_type, fund_code, allocation_code)
        )""",
    # ------------------------------------------------ reporting & context
    "report_channel_inclusion": """
        CREATE TABLE IF NOT EXISTS aa.report_channel_inclusion (
            report_year smallint NOT NULL,
            channel text NOT NULL,
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            unit text NOT NULL,            -- framework | country
            counted boolean NOT NULL,
            note text,
            source text NOT NULL,
            version text,                  -- attributed framework version (see framework_version)
            version_match text,

            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (report_year, channel, country_iso3, hazard, unit)
        )""",
    "plan_inclusion": """
        CREATE TABLE IF NOT EXISTS aa.plan_inclusion (
            country_iso3 text NOT NULL,
            year smallint NOT NULL,
            source text NOT NULL,
            plan_type text,                -- HNRP | HRP | FA | HNRP/FA | GHO | other
            in_gho boolean,
            exposure_aa_shocks text,
            aa_feasible boolean,
            aa_prearranged boolean,
            has_framework boolean,
            gho_target_people bigint,
            gho_requirement_usd numeric,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (country_iso3, year, source)
        )""",
    "start_network": """
        CREATE TABLE IF NOT EXISTS aa.start_network (
            country_iso3 text NOT NULL,
            as_of date NOT NULL,
            alerts_count integer,
            alert_years text,
            alerts_activated integer,
            start_ready boolean,
            source text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (country_iso3, as_of)
        )""",
    "cirv": """
        CREATE TABLE IF NOT EXISTS aa.cirv (
            country_iso3 text NOT NULL,
            year smallint NOT NULL,
            country_name text,
            cirv numeric NOT NULL,
            source text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (country_iso3, year)
        )""",
    # ------------------------------------------------ CERF depth (sheet-sourced)
    "cerf_subgrant": """
        CREATE TABLE IF NOT EXISTS aa.cerf_subgrant (
            project_code text NOT NULL,
            application_code text,
            agency text,
            year smallint,
            window_name text,
            country_iso3 text,
            country_name text,
            emergency_type text,
            project_amount_usd numeric,
            partner_name text NOT NULL,
            partner_acronym text,
            partner_type text,             -- NNGO | INGO | RedC | GOV | TBD
            localization text,             -- Local | INGO | TBD (AA-curated rows only)
            pre_existing_agreement text,
            subgrant_usd numeric,
            is_aa boolean NOT NULL DEFAULT false,
            source text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )""",
    "cerf_application_people": """
        CREATE TABLE IF NOT EXISTS aa.cerf_application_people (
            application_code text NOT NULL,
            phase text NOT NULL,           -- planned | reached
            disaggregation text NOT NULL,  -- sex_age | disability | category
            grp text NOT NULL,             -- girls/women/boys/men/.../idps/refugees/...
            value bigint,
            source text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (application_code, phase, disaggregation, grp, source)
        )""",
    "cerf_application_report": """
        CREATE TABLE IF NOT EXISTS aa.cerf_application_report (
            application_code text NOT NULL PRIMARY KEY,
            report_code text,
            report_focal_point text,
            language text,
            report_deadline date,
            revised_deadline date,
            cleared date,
            application_keywords text,
            application_grouping text,
            narr_1a_situation text,
            narr_1b_assistance text,
            narr_2a_situation text,
            narr_2b_assistance text,
            narr_3a_situation text,
            narr_3b_assistance text,
            narr_3c_added_value text,
            source text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )""",
    "cerf_allocation_extra": """
        CREATE TABLE IF NOT EXISTS aa.cerf_allocation_extra (
            application_code text NOT NULL PRIMARY KEY,
            is_aa_reported boolean,        -- OneGMS structured 'Is AA Allocation'
            allocation_keywords text,
            is_sudden_onset boolean,
            is_slow_onset boolean,
            response_required_usd numeric,
            response_received_usd numeric,
            people_affected bigint,
            source text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )""",
    "cerf_project_supplement": """
        CREATE TABLE IF NOT EXISTS aa.cerf_project_supplement (
            project_code text NOT NULL PRIMARY KEY,
            allocation_code text,
            is_aa boolean,
            gender_marker text,
            gbv_marker text,
            disability_marker text,
            cash_marker text,
            people_receiving_cash bigint,
            cva_usd numeric,
            cva_comments text,
            pwd_targeted bigint,
            refugees_targeted bigint,
            returnees_targeted bigint,
            idps_targeted bigint,
            host_communities_targeted bigint,
            source text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )""",
    "cerf_cva_history": """
        CREATE TABLE IF NOT EXISTS aa.cerf_cva_history (
            country_iso3 text,
            country_name text,
            agency text,
            emergency_type text,
            year smallint,
            amount_approved_usd numeric,
            people_receiving_cash bigint,
            cva_usd numeric,
            cva_possible text,
            n_source_rows integer,         -- sheet rows collapsed into this aggregate
            source text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE NULLS NOT DISTINCT
                (country_iso3, agency, emergency_type, year)
        )""",
    "emergency_type_override": """
        CREATE TABLE IF NOT EXISTS aa.emergency_type_override (
            application_code text NOT NULL PRIMARY KEY,
            country_iso3 text,
            country_name text,
            initial_type text NOT NULL,
            actual_type text NOT NULL,
            storm_name text,
            amount_usd numeric,
            source text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )""",
    # ---- KB flip (2026-09-28): the knowledge base is no longer a source. Everything the
    # site used to read from a framework page's frontmatter (scope, monitoring months,
    # trigger facets, data sources, agencies, learning links, the "Trigger windows" table)
    # was imported ONCE (scripts/import_kb_pages.py) and is edited here from now on. The
    # KB will read this DB instead. One row per (framework slug, version).
    "version_page": """
        CREATE TABLE IF NOT EXISTS aa.version_page (
            kb_framework text NOT NULL,    -- framework slug (matches framework_version.kb_framework)
            version text NOT NULL,
            country_iso3 text[] NOT NULL,  -- one, or several for a regional framework
            hazard text,
            frontmatter jsonb NOT NULL,    -- the page's YAML frontmatter, as imported / edited
            frontmatter_text text,         -- raw YAML at import (keeps scope-tier comments)
            triggers jsonb NOT NULL DEFAULT '[]'::jsonb,   -- rows of the page's Trigger windows table
            tiers jsonb NOT NULL DEFAULT '[]'::jsonb,      -- scope tiers parsed from the raw YAML
            body_md text,                  -- the page body (reference only)
            source text NOT NULL,          -- kb-import-YYYY-MM-DD | entered
            note text,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (kb_framework, version)
        )""",
    # learning products (AARs, evaluations, M&E and activation reports, stories, research,
    # guidance): seeded from the AA Compendium of Available Resources (Sept 2026) and the
    # AA website resources list; per framework (country x hazard) or global. `internal`
    # rows never render on the public pages.
    "learning_document": """
        CREATE TABLE IF NOT EXISTS aa.learning_document (
            id serial PRIMARY KEY,
            title text NOT NULL,
            url text,
            publisher text,
            year smallint,
            doc_type text NOT NULL,        -- aar | evaluation | impact_evaluation | monitoring_report
                                           -- | activation_report | case_study | story | research
                                           -- | guidance | trigger_analysis | other
            scope text NOT NULL,           -- global | country
            country_iso3 text[],           -- NULL for global
            hazard text,
            premises text[] NOT NULL DEFAULT '{}',  -- speed | cost_effectiveness | dignity
                                                    -- | development_gains | lives_livelihoods | long_term
            key_stat text,
            summary text,
            internal boolean NOT NULL DEFAULT false,
            section text,                  -- heading in the compendium
            source text NOT NULL,
            note text,
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE NULLS NOT DISTINCT (url, title)
        )""",
    # organisations with a role in a framework version, extracted from the endorsed
    # framework documents (scripts/import_partners.py) and curated here. Funded partners
    # per allocation stay in cerf_subgrant / cbpf_project_subip; this is the framework's
    # own partner list (government counterparts, technical partners, sub-grantees named
    # in the plan), which those mirrors cannot give.
    "framework_partner": """
        CREATE TABLE IF NOT EXISTS aa.framework_partner (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            version text NOT NULL,
            name text NOT NULL,
            acronym text,
            org_type text NOT NULL,        -- government | un | ingo | nngo | rcrc | donor
                                           -- | academic | private | other
            roles text[] NOT NULL DEFAULT '{}',  -- implementing | sub_grantee | technical
                                                 -- | coordination | government_counterpart | funding
            agency_parent text,            -- sub-grantee: the UN agency it works under
            amount_usd numeric,
            evidence text,                 -- short quote from the document
            source text NOT NULL,          -- doc-extract-YYYY-MM-DD | entered
            note text,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (country_iso3, hazard, version, name, source)
        )""",
}

# ------------------------------------------------------------------ durable
# Entry-path tables: written by the chd-ds-aa-extract proxy (browser entry page)
# and READ by the ingest, which merges them (entered values WIN over KB/sweeps —
# "versions ENTERED, not inferred"). The full-refresh load creates them if
# missing but NEVER drops or truncates them: they are the durable record of
# human entry, not derived data.
DURABLE_TABLES = {
    # data-entry files applied by scripts/apply_entries.py (nightly job): one row per file,
    # so a file is applied once and later admin-page edits are never overwritten
    "applied_entries": """
        CREATE TABLE IF NOT EXISTS aa.applied_entries (
            name text PRIMARY KEY,
            sha256 text NOT NULL,
            n_rows integer NOT NULL,
            entered_by text,
            applied_at timestamptz NOT NULL DEFAULT now()
        )""",
    "entered_version": """
        CREATE TABLE IF NOT EXISTS aa.entered_version (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            version text NOT NULL,         -- date label YYYY[-MM[-DD]]
            doc_title text,
            doc_url text,
            endorsed_by text,              -- erc | cerf_secretariat
            valid_until date,
            valid_until_source text,       -- doc-stated | convention | inherited
            window_rollup text,            -- additive | exclusive | capped
            supersedes text,
            note text,
            entered_by text NOT NULL,
            entered_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (country_iso3, hazard, version)
        )""",
    "entered_window": """
        CREATE TABLE IF NOT EXISTS aa.entered_window (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            version text NOT NULL,
            window_name text NOT NULL,
            basis text,                    -- observational | forecast | mixed
            trigger_statement text,        -- plain-text trigger, from the endorsed doc
            monitoring_period text,
            note text,
            entered_by text NOT NULL,
            entered_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (country_iso3, hazard, version, window_name)
        )""",
    "entered_window_funding": """
        CREATE TABLE IF NOT EXISTS aa.entered_window_funding (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            version text NOT NULL,
            window_name text NOT NULL,
            fund_code text NOT NULL,       -- cerf | cbpf-<iso3> | rhpf-* | cofinancing
            financier text,                -- named source when fund_code='cofinancing'
            amount_usd numeric,            -- what this window can draw from this fund
            entered_by text NOT NULL,
            entered_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (country_iso3, hazard, version, window_name, fund_code)
        )""",
    # per-window trigger state, curated by hand (aa.window is truncated by the KB loader,
    # so the flag lives here). A version's "fully triggered" state is inferred from these:
    # any window for all-in / exclusive frameworks, every window for independent ones.
    "window_status": """
        CREATE TABLE IF NOT EXISTS aa.window_status (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            version text NOT NULL,
            window_name text NOT NULL,
            triggered boolean NOT NULL DEFAULT false,
            triggered_on date,
            note text,
            updated_by text,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (country_iso3, hazard, version, window_name)
        )""",
    # the document registry: WHICH FILE is a version's framework document, by content
    # hash. Publication stays with OCHA (unocha.org / ReliefWeb) — version_document's
    # official_url is the canonical public link; the bytes are archived in the dev blob,
    # content-addressed at projects/ds-aa-tracking/raw/framework_documents/<sha256>.pdf,
    # so a file shared by several versions (the Dry Corridor's one document for
    # SLV/GTM/HND) is stored once and linked from each. The archive is the record when an
    # official page goes (nic-drought's ReliefWeb page 404s). Written only by
    # scripts/register_documents.py (read-only in the admin page): a changed file is a
    # new row, never an edit.
    "framework_document": """
        CREATE TABLE IF NOT EXISTS aa.framework_document (
            sha256 text PRIMARY KEY,       -- hex digest of the file bytes = its identity
            blob_path text NOT NULL,       -- container `projects`, dev stage
            bytes bigint NOT NULL,
            media_type text NOT NULL DEFAULT 'application/pdf',
            title text,
            language text,                 -- en | fr | es — one per file; a translation
                                           -- is another file of the SAME version
            is_public boolean NOT NULL,    -- false: never on the public site or in the KB
            retrieved_from text,           -- where THESE BYTES came from (the URL actually
                                           -- fetched, 'email from …'), not today's link
            retrieved_at timestamptz,      -- NULL when unknown (the KB-cache backfill)
            registered_by text NOT NULL,
            source text NOT NULL,          -- kb-pdf-cache | entered
            note text,
            registered_at timestamptz NOT NULL DEFAULT now()
        )""",
    # version <-> document, many-to-many: a version can have several files (the endorsed
    # original, the published rendition, translations, annexes) and a file can serve
    # several versions (a shared regional document, each country on its own page).
    "version_document": """
        CREATE TABLE IF NOT EXISTS aa.version_document (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            version text NOT NULL,         -- aa.framework_version (by convention)
            sha256 text NOT NULL,          -- aa.framework_document
            role text NOT NULL,            -- endorsed (the file as endorsed / circulated)
                                           -- | published (the rendition on the official
                                           --   site — may differ byte-wise from endorsed)
                                           -- | translation | annex
            official_url text,             -- publication LANDING page for this version
                                           -- (not the /attachments/ PDF link); NULL until
                                           -- published, or never if internal
            superseded_by text,            -- sha256 of the file that replaced this one in
                                           -- the same role (OCHA re-uploads a corrected
                                           -- PDF); NULL = current
            note text,
            registered_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (country_iso3, hazard, version, sha256)
        )""",
    "entry_audit": """
        CREATE TABLE IF NOT EXISTS aa.entry_audit (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT now(),
            entered_by text NOT NULL,
            table_name text NOT NULL,
            row_key text NOT NULL,         -- 'ISO/hazard/version[/window[/fund]]'
            field text NOT NULL,
            old_value text,
            new_value text
        )""",
    # ------------------------------------------- backtests (simulated activations)
    # Written by the knowledge base's load_aa_performance.py until 2026-10-05 (from its
    # gsheet / insurance-Excel crosswalk); owned here since. Shapes are the live ones.
    # A version's backtest = its aa.window rows + aa.simulated_activation rows + its
    # aa.version_performance_reported row. While the version is unsealed (development,
    # or endorsed but not yet verified) it is edited freely — entries files with
    # op: replace, the admin page. Once framework_version.backtest_sealed_at is set, the
    # guard_sealed trigger refuses every change except inside an erratum (backtests/errata/,
    # scripts/apply_backtests.py). Simulated activations must fall inside their window's
    # analysis span (deferred constraint trigger simulated_in_span).
    "window": """
        CREATE TABLE IF NOT EXISTS aa.window (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            version text NOT NULL,
            window_name text NOT NULL,
            kb_framework text,             -- attribute (KB folder slug), not part of the key
            all_in boolean NOT NULL DEFAULT false,
            basis text,                    -- forecast | observational | mixed
            allocation_usd bigint,         -- legacy envelope; budgets live in window_funding
            analysis_start integer,        -- the backtest's analysed years: the RP
            analysis_end integer,          --   denominator (wrong span = wrong RP)
            rp_reported numeric,           -- as published (compare v_window_performance)
            prob_reported numeric,
            source text,                   -- where the backtest came from: report (the
                                           -- endorsed document) | repo (the analysis code)
                                           -- | gsheet | excel (KB-era crosswalk) | recon-*
            note text,                     -- reported-vs-derived discrepancies etc.
            PRIMARY KEY (country_iso3, hazard, version, window_name)
        )""",
    "simulated_activation": """
        CREATE TABLE IF NOT EXISTS aa.simulated_activation (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            version text NOT NULL,
            window_name text NOT NULL,
            event_year integer NOT NULL,   -- the year the trigger would have fired, as the
                                           -- document labels it (seasons that straddle two
                                           -- calendar years are labelled either way: MOZ
                                           -- by end year, NER floods by start year) —
                                           -- never a real activation of the version itself
            event_label text,
            kb_framework text,
            event_date date,
            event_time timestamptz,
            time_precision text,           -- year | month | day | hour
            source_note text,
            PRIMARY KEY (country_iso3, hazard, version, window_name, event_year)
        )""",
    "version_performance_reported": """
        CREATE TABLE IF NOT EXISTS aa.version_performance_reported (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            version text NOT NULL,
            kb_framework text,
            kb_status text,
            gsheet_tab text,               -- provenance of the reported numbers
            excel_fv text,
            overall_rp_reported numeric,   -- published overall return period
            overall_prob_reported numeric,
            overall_spend_reported bigint,
            flag text,                     -- KB-era crosswalk flag (PRE_KB, EXCEL_SOURCE, …)
            PRIMARY KEY (country_iso3, hazard, version)
        )""",
    # corrections to sealed backtests: one row per applied errata file. The guard_sealed
    # trigger lets a change through only while aa.erratum_id (SET LOCAL) names a row here
    # whose `versions` covers the row being changed. Written only by apply_backtests.py.
    "backtest_erratum": """
        CREATE TABLE IF NOT EXISTS aa.backtest_erratum (
            id text PRIMARY KEY,           -- the file name stem
            kind text NOT NULL CHECK (kind IN ('transcription', 'analysis-note')),
                                           -- transcription: the DB did not match the
                                           --   endorsed document (fixed in place);
                                           -- analysis-note: the endorsed backtest itself
                                           --   is wrong — recorded, never edited in place
                                           --   (the fix is a new version)
            versions text[] NOT NULL,      -- 'ISO3/hazard/version' keys it may change
            reason text NOT NULL,
            evidence text,                 -- document + page / table, links
            requested_by text NOT NULL,
            source text NOT NULL,          -- backtests/errata/<file> | blob:<path> (private)
            sha256 text NOT NULL,          -- the file as applied (errata are immutable)
            changes jsonb NOT NULL,        -- each change with the row's before-values
            applied_at timestamptz NOT NULL DEFAULT now()
        )""",
    # ------------------------------------------------ KB-era record, frozen
    # Written by the knowledge base until its pages stopped being a source (the KB flip,
    # 2026-09-28); owned here since 2026-10-05 and no longer loaded by anything.
    # funding_breakdown -> superseded by window_funding (+ v_window_funding_split);
    # actual_activation -> window_activation; activation_allocation -> activation_funding.
    # Kept because views and pages still read them (announcement URLs, v_aa_allocation).
    "funding_breakdown": """
        CREATE TABLE IF NOT EXISTS aa.funding_breakdown (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            version text NOT NULL,
            window_name text,              -- null = whole-framework envelope
            fund_source text,              -- CERF | AHF | NHF | … ; null = unspecified
            agency text,
            sector text,
            amount_usd bigint NOT NULL,
            provenance text NOT NULL DEFAULT 'stated',   -- stated | imputed-5-95
            kb_framework text
        )""",
    "actual_activation": """
        CREATE TABLE IF NOT EXISTS aa.actual_activation (
            kb_framework text NOT NULL,
            event_date text NOT NULL,
            window_name text NOT NULL,     -- 'unspecified' when the page did not say
            country_iso3 text,
            hazard text,
            version text,
            full_activation boolean NOT NULL,
            released_usd bigint,
            url text,                      -- the announcement
            note text,
            PRIMARY KEY (kb_framework, event_date, window_name)
        )""",
    # three row kinds: link (kb_framework, event_date, application_code), NO_CERF
    # (kb_framework, event_date, NULL), ADHOC_AA (NULL, NULL, application_code). The live
    # table also carries FOREIGN KEY (application_code) REFERENCES aa.cerf_allocation —
    # not repeated here: that table belongs to the ds-cerf-supplement mirror.
    "activation_allocation": """
        CREATE TABLE IF NOT EXISTS aa.activation_allocation (
            kb_framework text,
            event_date text,
            application_code text,
            flag text,                     -- SHARED_APP | NO_CERF | ADHOC_AA
            note text,
            updated_at timestamptz NOT NULL DEFAULT now(),
            CHECK (kb_framework IS NOT NULL OR application_code IS NOT NULL),
            CHECK ((kb_framework IS NULL) = (event_date IS NULL))
        )""",
}

# the backtest tables the seal guards, and the KB-era tables kept read-only
BACKTEST_TABLES = ["window", "simulated_activation", "version_performance_reported"]
KB_ERA_TABLES = ["funding_breakdown", "actual_activation", "activation_allocation"]

# ------------------------------------------------------------ additive migrations
# DB-first era (2026-09-10): the dev DB is the single source of truth — nothing
# ever DROPs or TRUNCATEs these tables again. Schema evolution happens here as
# append-only ALTER statements (idempotent: use IF NOT EXISTS / IF EXISTS forms),
# applied by ensure_schema() after the CREATE IF NOT EXISTS pass.
ADDITIVE_MIGRATIONS = [
    # 2026-09-21: retirement is a manual flag on the pair (framework level)
    "ALTER TABLE aa.country_hazard ADD COLUMN IF NOT EXISTS retired boolean NOT NULL DEFAULT false",
    "ALTER TABLE aa.country_hazard ADD COLUMN IF NOT EXISTS retired_note text",
    # 2026-09-21: technical support without a funding commitment, at framework level
    "ALTER TABLE aa.country_hazard ADD COLUMN IF NOT EXISTS technical_support boolean NOT NULL DEFAULT false",
    "ALTER TABLE aa.country_hazard ADD COLUMN IF NOT EXISTS technical_support_note text",
    # 2026-10-02: a simulated activation can carry the day (or, for storms, the hour) the
    # trigger would have activated, not only the year; the site reads these when present
    # and falls back to event_year. time_precision: year | month | day | hour.
    "ALTER TABLE IF EXISTS aa.simulated_activation ADD COLUMN IF NOT EXISTS event_date date",
    "ALTER TABLE IF EXISTS aa.simulated_activation ADD COLUMN IF NOT EXISTS event_time timestamptz",
    "ALTER TABLE IF EXISTS aa.simulated_activation ADD COLUMN IF NOT EXISTS time_precision text",
    "ALTER TABLE IF EXISTS aa.simulated_activation ADD COLUMN IF NOT EXISTS source_note text",
    # 2026-10-05: backtests owned here; a verified backtest is sealed (see BACKTEST_GUARDS)
    "ALTER TABLE aa.framework_version ADD COLUMN IF NOT EXISTS backtest_sealed_at timestamptz",
    "ALTER TABLE aa.framework_version ADD COLUMN IF NOT EXISTS backtest_sealed_by text",
    "ALTER TABLE aa.framework_version ADD COLUMN IF NOT EXISTS backtest_sealed_against text",
    "ALTER TABLE aa.window ADD COLUMN IF NOT EXISTS note text",
    """DO $$ BEGIN
         IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'window_span_order'
                        AND conrelid = 'aa.window'::regclass) THEN
           ALTER TABLE aa.window ADD CONSTRAINT window_span_order
             CHECK (analysis_start IS NULL OR analysis_end IS NULL
                    OR analysis_start <= analysis_end);
         END IF;
         IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'window_allocation_nonneg'
                        AND conrelid = 'aa.window'::regclass) THEN
           ALTER TABLE aa.window ADD CONSTRAINT window_allocation_nonneg
             CHECK (allocation_usd IS NULL OR allocation_usd >= 0);
         END IF;
         -- a seal always says who set it and against what
         IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'backtest_seal_complete'
                        AND conrelid = 'aa.framework_version'::regclass) THEN
           ALTER TABLE aa.framework_version ADD CONSTRAINT backtest_seal_complete
             CHECK (backtest_sealed_at IS NULL
                    OR (backtest_sealed_by IS NOT NULL AND backtest_sealed_against IS NOT NULL));
         END IF;
         -- only an endorsed version is sealed (and a sealed one can't be set back to development)
         IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'backtest_seal_endorsed'
                        AND conrelid = 'aa.framework_version'::regclass) THEN
           ALTER TABLE aa.framework_version ADD CONSTRAINT backtest_seal_endorsed
             CHECK (backtest_sealed_at IS NULL OR kb_status = 'endorsed');
         END IF;
       END $$""",
]

# ------------------------------------------------------- backtest guards (2026-10-05)
# Applied by ensure_schema after the additive migrations; every statement is idempotent.
#
# 1. The seal. framework_version.backtest_sealed_at set = the version's backtest is
#    verified against its endorsed document and frozen. guard_sealed (BEFORE INSERT /
#    UPDATE / DELETE on each BACKTEST_TABLES table) refuses a change that touches a sealed
#    version — on either the old or the new row, so a row can't be moved in or out — unless
#    the transaction has SET LOCAL aa.erratum_id to an aa.backtest_erratum row covering that
#    version. Only scripts/apply_backtests.py does that, for a file committed to
#    backtests/errata/ (or, for versions whose document is not public, a file on the
#    private dev blob under projects/ds-aa-tracking/errata/). Setting a seal on an
#    unsealed version is free (the act of sealing); changing or clearing a seal, relabelling
#    or deleting a sealed version needs an erratum too (guard_seal on framework_version);
#    TRUNCATE of these tables is refused while any version is sealed (guard_truncate).
#    Sealing itself is checked here too, whoever does it: the version has windows, every
#    window has a span, no simulated year lies outside it; no version is registered already
#    sealed; aa.backtest_erratum is append-only (guard_erratum).
#    Every writer — the admin page's proxy, entries files, the Databricks job, a laptop on
#    the tunnel — meets the same rule, because it lives in the database.
# 2. The span. A simulated activation must fall inside its window's analysis span (and its
#    window must exist): checked at COMMIT (deferred), so a file can change the span and
#    the years in any order. This is the rule the KB-era data broke — real activations
#    appended to backtests past the analysed years.
# 3. The target. A backtest row belongs to a REGISTERED version: BACKTEST_FKS — window and
#    version_performance_reported reference framework_version, simulated_activation
#    references its window. Deferred (a relabel or an erratum moves rows table by table in
#    one transaction) and NO ACTION (replacing a version's windows without its years fails
#    instead of silently dropping them). So no writer can leave a backtest under a label
#    that is no version — how the KB-era '2025' orphans came about. Added NOT VALID: rows
#    from before are checked once the first errata have cleaned them, by
#    scripts/apply_backtests.py (VALIDATE CONSTRAINT, idempotent).
BACKTEST_FKS = [
    ("window", "window_version_fk",
     "FOREIGN KEY (country_iso3, hazard, version) "
     "REFERENCES aa.framework_version (country_iso3, hazard, version)"),
    ("version_performance_reported", "version_performance_reported_version_fk",
     "FOREIGN KEY (country_iso3, hazard, version) "
     "REFERENCES aa.framework_version (country_iso3, hazard, version)"),
    ("simulated_activation", "simulated_activation_window_fk",
     "FOREIGN KEY (country_iso3, hazard, version, window_name) "
     'REFERENCES aa."window" (country_iso3, hazard, version, window_name)'),
]

BACKTEST_GUARDS = [
    """CREATE OR REPLACE FUNCTION aa.backtest_sealed(c text, h text, v text)
       RETURNS boolean LANGUAGE sql STABLE AS $$
         SELECT EXISTS (SELECT 1 FROM aa.framework_version
                        WHERE country_iso3 = c AND hazard = h AND version = v
                          AND backtest_sealed_at IS NOT NULL)
       $$""",
    """CREATE OR REPLACE FUNCTION aa.require_backtest_erratum(c text, h text, v text, what text)
       RETURNS void LANGUAGE plpgsql AS $$
       DECLARE
         eid text := nullif(current_setting('aa.erratum_id', true), '');
       BEGIN
         IF eid IS NOT NULL AND EXISTS (
              SELECT 1 FROM aa.backtest_erratum e
              WHERE e.id = eid AND (c || '/' || h || '/' || v) = ANY (e.versions)) THEN
           RETURN;
         END IF;
         RAISE EXCEPTION 'the backtest of %/%/% is sealed: % needs an erratum', c, h, v, what
           USING HINT = 'Write a backtests/errata/ file in ds-aa-tracking (see backtests/README.md); '
                        'the nightly job applies it. A changed analysis is a new version.';
       END $$""",
    """CREATE OR REPLACE FUNCTION aa.guard_sealed_backtest()
       RETURNS trigger LANGUAGE plpgsql AS $$
       BEGIN
         -- an update that changes nothing (a re-read confirming the record) is not a change
         IF TG_OP = 'UPDATE' AND NEW IS NOT DISTINCT FROM OLD THEN
           RETURN NEW;
         END IF;
         IF TG_OP IN ('UPDATE', 'DELETE')
            AND aa.backtest_sealed(OLD.country_iso3, OLD.hazard, OLD.version) THEN
           PERFORM aa.require_backtest_erratum(OLD.country_iso3, OLD.hazard, OLD.version,
                                               lower(TG_OP) || ' on aa.' || TG_TABLE_NAME);
         END IF;
         IF TG_OP IN ('INSERT', 'UPDATE')
            AND aa.backtest_sealed(NEW.country_iso3, NEW.hazard, NEW.version) THEN
           PERFORM aa.require_backtest_erratum(NEW.country_iso3, NEW.hazard, NEW.version,
                                               lower(TG_OP) || ' on aa.' || TG_TABLE_NAME);
         END IF;
         IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
         RETURN NEW;
       END $$""",
    *[f"""CREATE OR REPLACE TRIGGER guard_sealed
          BEFORE INSERT OR UPDATE OR DELETE ON aa.{t}
          FOR EACH ROW EXECUTE FUNCTION aa.guard_sealed_backtest()""" for t in BACKTEST_TABLES],
    """CREATE OR REPLACE FUNCTION aa.guard_version_seal()
       RETURNS trigger LANGUAGE plpgsql AS $$
       DECLARE
         bad text;
       BEGIN
         IF TG_OP = 'INSERT' THEN
           IF NEW.backtest_sealed_at IS NOT NULL THEN
             RAISE EXCEPTION 'version %/%/% cannot be registered already sealed: a seal follows a recorded, checked backtest',
               NEW.country_iso3, NEW.hazard, NEW.version;
           END IF;
           RETURN NEW;
         END IF;
         IF OLD.backtest_sealed_at IS NULL THEN
           IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
           IF NEW.backtest_sealed_at IS NOT NULL THEN
             -- the act of sealing: there must be a backtest, and it must be sound, whoever seals
             IF (NEW.country_iso3, NEW.hazard, NEW.version)
                  IS DISTINCT FROM (OLD.country_iso3, OLD.hazard, OLD.version) THEN
               RAISE EXCEPTION 'seal %/%/% and relabel it in separate steps (relabel first)',
                 OLD.country_iso3, OLD.hazard, OLD.version;
             END IF;
             IF NOT EXISTS (SELECT 1 FROM aa."window" w WHERE (w.country_iso3, w.hazard, w.version)
                              = (OLD.country_iso3, OLD.hazard, OLD.version)) THEN
               RAISE EXCEPTION '%/%/% has no backtest windows: nothing to seal',
                 OLD.country_iso3, OLD.hazard, OLD.version;
             END IF;
             SELECT string_agg(w.window_name, ', ') INTO bad FROM aa."window" w
             WHERE (w.country_iso3, w.hazard, w.version) = (OLD.country_iso3, OLD.hazard, OLD.version)
               AND (w.analysis_start IS NULL OR w.analysis_end IS NULL);
             IF bad IS NOT NULL THEN
               RAISE EXCEPTION '%/%/% cannot be sealed: window(s) without an analysis span (%)',
                 OLD.country_iso3, OLD.hazard, OLD.version, bad;
             END IF;
             SELECT string_agg(s.window_name || ' ' || s.event_year, ', ') INTO bad
             FROM aa.simulated_activation s
             JOIN aa."window" w USING (country_iso3, hazard, version, window_name)
             WHERE (s.country_iso3, s.hazard, s.version) = (OLD.country_iso3, OLD.hazard, OLD.version)
               AND s.event_year NOT BETWEEN w.analysis_start AND w.analysis_end;
             IF bad IS NOT NULL THEN
               RAISE EXCEPTION '%/%/% cannot be sealed: simulated year(s) outside the analysis span (%)',
                 OLD.country_iso3, OLD.hazard, OLD.version, bad;
             END IF;
           END IF;
           RETURN NEW;
         END IF;
         IF TG_OP = 'DELETE' THEN
           PERFORM aa.require_backtest_erratum(OLD.country_iso3, OLD.hazard, OLD.version,
                                               'deleting the version');
           RETURN OLD;
         END IF;
         IF (NEW.country_iso3, NEW.hazard, NEW.version)
              IS DISTINCT FROM (OLD.country_iso3, OLD.hazard, OLD.version)
            OR (NEW.backtest_sealed_at, NEW.backtest_sealed_by, NEW.backtest_sealed_against)
              IS DISTINCT FROM
               (OLD.backtest_sealed_at, OLD.backtest_sealed_by, OLD.backtest_sealed_against) THEN
           PERFORM aa.require_backtest_erratum(OLD.country_iso3, OLD.hazard, OLD.version,
                                               'relabelling it or changing its seal');
         END IF;
         RETURN NEW;
       END $$""",
    """CREATE OR REPLACE TRIGGER guard_seal
       BEFORE INSERT OR UPDATE OR DELETE ON aa.framework_version
       FOR EACH ROW EXECUTE FUNCTION aa.guard_version_seal()""",
    # the errata record is append-only: a row is written once, by the transaction applying
    # the erratum (which fills in `changes` at its end), and never changed or removed after
    """CREATE OR REPLACE FUNCTION aa.guard_backtest_erratum()
       RETURNS trigger LANGUAGE plpgsql AS $$
       BEGIN
         IF TG_OP = 'UPDATE'
            AND NEW.id = OLD.id
            AND OLD.changes = '[]'::jsonb
            AND nullif(current_setting('aa.erratum_id', true), '') = OLD.id THEN
           RETURN NEW;            -- apply_backtests.py completing the erratum it is applying
         END IF;
         RAISE EXCEPTION 'aa.backtest_erratum is the record of corrections made: rows are never changed or removed (erratum %)',
           coalesce(OLD.id, '?')
           USING HINT = 'A further correction is a new erratum file.';
       END $$""",
    """CREATE OR REPLACE TRIGGER guard_erratum
       BEFORE UPDATE OR DELETE ON aa.backtest_erratum
       FOR EACH ROW EXECUTE FUNCTION aa.guard_backtest_erratum()""",
    """CREATE OR REPLACE FUNCTION aa.guard_backtest_erratum_truncate()
       RETURNS trigger LANGUAGE plpgsql AS $$
       BEGIN
         RAISE EXCEPTION 'aa.backtest_erratum is the record of corrections made: it cannot be truncated';
       END $$""",
    """CREATE OR REPLACE TRIGGER guard_erratum_truncate
       BEFORE TRUNCATE ON aa.backtest_erratum
       FOR EACH STATEMENT EXECUTE FUNCTION aa.guard_backtest_erratum_truncate()""",
    # TRUNCATE fires no row trigger: refuse it outright while any backtest is sealed
    """CREATE OR REPLACE FUNCTION aa.guard_backtest_truncate()
       RETURNS trigger LANGUAGE plpgsql AS $$
       BEGIN
         IF EXISTS (SELECT 1 FROM aa.framework_version WHERE backtest_sealed_at IS NOT NULL) THEN
           RAISE EXCEPTION 'aa.% holds sealed backtests: it cannot be truncated', TG_TABLE_NAME
             USING HINT = 'Change rows, not the table: unsealed versions by an entries file, '
                          'sealed ones by an erratum (backtests/README.md).';
         END IF;
         RETURN NULL;
       END $$""",
    *[f"""CREATE OR REPLACE TRIGGER guard_truncate
          BEFORE TRUNCATE ON aa.{t}
          FOR EACH STATEMENT EXECUTE FUNCTION aa.guard_backtest_truncate()"""
      for t in [*BACKTEST_TABLES, "framework_version"]],
    """CREATE OR REPLACE FUNCTION aa.check_simulated_in_span()
       RETURNS trigger LANGUAGE plpgsql AS $$
       DECLARE
         w record;
       BEGIN
         IF TG_TABLE_NAME = 'simulated_activation' THEN
           -- the row may be gone by commit time (deleted later in the transaction)
           IF NOT EXISTS (SELECT 1 FROM aa.simulated_activation s
                          WHERE (s.country_iso3, s.hazard, s.version, s.window_name,
                                 s.event_year)
                              = (NEW.country_iso3, NEW.hazard, NEW.version, NEW.window_name,
                                 NEW.event_year)) THEN
             RETURN NULL;
           END IF;
           SELECT analysis_start, analysis_end INTO w FROM aa.window
           WHERE (country_iso3, hazard, version, window_name)
               = (NEW.country_iso3, NEW.hazard, NEW.version, NEW.window_name);
           IF NOT FOUND THEN
             RAISE EXCEPTION 'simulated activation %/%/% "%" %: the window is not in aa.window',
               NEW.country_iso3, NEW.hazard, NEW.version, NEW.window_name, NEW.event_year;
           END IF;
           IF NEW.event_year < coalesce(w.analysis_start, NEW.event_year)
              OR NEW.event_year > coalesce(w.analysis_end, NEW.event_year) THEN
             RAISE EXCEPTION 'simulated activation %/%/% "%" %: outside the analysis span %-%',
               NEW.country_iso3, NEW.hazard, NEW.version, NEW.window_name, NEW.event_year,
               w.analysis_start, w.analysis_end
               USING HINT = 'A year after the analysed span is a real activation: record it '
                            'in window_activation, not in the backtest.';
           END IF;
         ELSE
           SELECT s.event_year INTO w FROM aa.simulated_activation s
           JOIN aa.window x USING (country_iso3, hazard, version, window_name)
           WHERE (x.country_iso3, x.hazard, x.version, x.window_name)
               = (NEW.country_iso3, NEW.hazard, NEW.version, NEW.window_name)
             AND (s.event_year < coalesce(x.analysis_start, s.event_year)
                  OR s.event_year > coalesce(x.analysis_end, s.event_year))
           LIMIT 1;
           IF FOUND THEN
             RAISE EXCEPTION 'window %/%/% "%": span %-% leaves simulated year % outside',
               NEW.country_iso3, NEW.hazard, NEW.version, NEW.window_name,
               NEW.analysis_start, NEW.analysis_end, w.event_year;
           END IF;
         END IF;
         RETURN NULL;
       END $$""",
    # constraint triggers have no CREATE OR REPLACE: dropped and created each run, so the
    # definition here is always the one installed. The window trigger fires on INSERT too:
    # replacing a version's windows deletes and re-inserts them, which is no UPDATE.
    "DROP TRIGGER IF EXISTS simulated_in_span ON aa.simulated_activation",
    """CREATE CONSTRAINT TRIGGER simulated_in_span
       AFTER INSERT OR UPDATE ON aa.simulated_activation
       DEFERRABLE INITIALLY DEFERRED
       FOR EACH ROW EXECUTE FUNCTION aa.check_simulated_in_span()""",
    'DROP TRIGGER IF EXISTS window_span_covers ON aa."window"',
    """CREATE CONSTRAINT TRIGGER window_span_covers
       AFTER INSERT OR UPDATE OF analysis_start, analysis_end ON aa."window"
       DEFERRABLE INITIALLY DEFERRED
       FOR EACH ROW EXECUTE FUNCTION aa.check_simulated_in_span()""",
    *[f"""DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{name}'
                           AND conrelid = 'aa."{table}"'::regclass) THEN
              ALTER TABLE aa."{table}" ADD CONSTRAINT {name} {ddl}
                DEFERRABLE INITIALLY DEFERRED NOT VALID;
            END IF;
          END $$""" for table, name, ddl in BACKTEST_FKS],
]

INDEXES = [
    # KB-era: one row per (activation, allocation) pair, any of the three row kinds
    """CREATE UNIQUE INDEX IF NOT EXISTS activation_allocation_uniq ON aa.activation_allocation
       (COALESCE(kb_framework, ''), COALESCE(event_date, ''), COALESCE(application_code, ''))""",
    "CREATE INDEX IF NOT EXISTS cerf_subgrant_project_idx ON aa.cerf_subgrant (project_code)",
    "CREATE INDEX IF NOT EXISTS cerf_subgrant_app_idx ON aa.cerf_subgrant (application_code)",
    """CREATE UNIQUE INDEX IF NOT EXISTS cerf_subgrant_uniq ON aa.cerf_subgrant
       (project_code, partner_name, COALESCE(subgrant_usd, -1), source)""",
    # one CURRENT endorsed / published file per version (translations and annexes can be
    # several); a replacement sets superseded_by on the old link first
    """CREATE UNIQUE INDEX IF NOT EXISTS version_document_current_uniq ON aa.version_document
       (country_iso3, hazard, version, role)
       WHERE superseded_by IS NULL AND role IN ('endorsed', 'published')""",
]

LEGACY_TABLES = [   # renamed zz_legacy_<name> by the window-first migration; read-only history
    "framework_registry", "activation", "prearranged_funding", "prearranged_sector_budget",
    "entered_version_funding",
]

VIEWS = {
    # ---- backtest performance (moved from the KB's load_aa_performance.py, 2026-10-05).
    # Weibull: RP = (analysed years + 1) / activations; overall = any window firing in a year.
    # Names and columns unchanged — the CERF trigger-allocations app and old ERDs read them.
    "v_window_performance": """
        CREATE OR REPLACE VIEW aa.v_window_performance AS
        SELECT w.country_iso3, w.hazard, w.version, w.window_name, w.kb_framework,
               w.version AS kb_version, w.all_in,
               w.allocation_usd, w.analysis_start, w.analysis_end,
               (w.analysis_end - w.analysis_start + 1)              AS analysis_years,
               count(a.event_year)                                  AS n_activations,
               round((w.analysis_end - w.analysis_start + 1 + 1.0)
                     / nullif(count(a.event_year), 0), 2)           AS return_period,
               round(count(a.event_year)::numeric
                     / nullif(w.analysis_end - w.analysis_start + 1, 0), 3) AS activation_prob,
               w.rp_reported, w.prob_reported
        FROM aa.window w
        LEFT JOIN aa.simulated_activation a
          ON (a.country_iso3, a.hazard, a.version, a.window_name)
           = (w.country_iso3, w.hazard, w.version, w.window_name)
        GROUP BY w.country_iso3, w.hazard, w.version, w.window_name, w.kb_framework, w.all_in,
                 w.allocation_usd, w.analysis_start, w.analysis_end, w.rp_reported,
                 w.prob_reported
    """,
    "v_framework_performance": """
        CREATE OR REPLACE VIEW aa.v_framework_performance AS
        WITH act AS (
            SELECT country_iso3, hazard, version, event_year
            FROM aa.simulated_activation GROUP BY 1, 2, 3, 4
        ),
        dims AS (
            SELECT country_iso3, hazard, version, max(kb_framework) AS kb_framework,
                   min(analysis_start) AS a0, max(analysis_end) AS a1,
                   bool_or(all_in) AS all_in, sum(allocation_usd) AS total_budget
            FROM aa.window GROUP BY 1, 2, 3
        )
        SELECT d.country_iso3, d.hazard, d.version, d.kb_framework, d.version AS kb_version,
               d.a1 - d.a0 + 1                                    AS analysis_years,
               count(a.event_year)                                AS n_activation_years,
               round((d.a1 - d.a0 + 1 + 1.0)
                     / nullif(count(a.event_year), 0), 2)         AS overall_return_period,
               round(count(a.event_year)::numeric
                     / nullif(d.a1 - d.a0 + 1, 0), 3)             AS overall_activation_prob,
               d.all_in, d.total_budget
        FROM dims d
        LEFT JOIN act a
          ON (a.country_iso3, a.hazard, a.version) = (d.country_iso3, d.hazard, d.version)
        GROUP BY d.country_iso3, d.hazard, d.version, d.kb_framework, d.a0, d.a1, d.all_in,
                 d.total_budget
    """,
    # the old crosswalk shape, for readers still keyed (kb_framework, kb_version, country_iso3)
    "framework_version_map": """
        CREATE OR REPLACE VIEW aa.framework_version_map AS
        SELECT kb_framework, version AS kb_version, country_iso3, kb_status, gsheet_tab,
               excel_fv, overall_rp_reported, overall_prob_reported, overall_spend_reported,
               flag
        FROM aa.version_performance_reported
    """,
    # ---- KB-era record (frozen tables), views unchanged
    "v_funding_by_sector": """
        CREATE OR REPLACE VIEW aa.v_funding_by_sector AS
        SELECT country_iso3, hazard, version, kb_framework, version AS kb_version,
               sector, sum(amount_usd) AS amount_usd
        FROM aa.funding_breakdown WHERE sector IS NOT NULL
        GROUP BY 1, 2, 3, 4, 6
    """,
    "v_funding_by_agency": """
        CREATE OR REPLACE VIEW aa.v_funding_by_agency AS
        SELECT country_iso3, hazard, version, kb_framework, version AS kb_version,
               agency, sum(amount_usd) AS amount_usd
        FROM aa.funding_breakdown WHERE agency IS NOT NULL
        GROUP BY 1, 2, 3, 4, 6
    """,
    "v_funding_by_window": """
        CREATE OR REPLACE VIEW aa.v_funding_by_window AS
        SELECT country_iso3, hazard, version, kb_framework, version AS kb_version, window_name,
               bool_or(provenance <> 'stated') AS any_imputed, sum(amount_usd) AS amount_usd
        FROM aa.funding_breakdown WHERE window_name IS NOT NULL
        GROUP BY 1, 2, 3, 4, 6
    """,
    "v_aa_allocation": """
        CREATE OR REPLACE VIEW aa.v_aa_allocation AS
        SELECT ca.application_code, ca.year, ca.country_iso3, ca.emergency_type, ca.title,
               ca.amount_approved, ca.individuals_planned, ca.individuals_reached,
               ca.allocation_status, l.kb_framework, l.event_date,
               l.flag = 'ADHOC_AA' AS aa_adhoc, l.note AS aa_note
        FROM aa.activation_allocation l
        JOIN aa.cerf_allocation ca USING (application_code)
    """,
    "v_activation_funding": """
        CREATE OR REPLACE VIEW aa.v_activation_funding AS
        WITH ev AS (
            SELECT kb_framework, event_date,
                   max(country_iso3) AS country_iso3, max(hazard) AS hazard,
                   max(version) AS version,
                   string_agg(DISTINCT window_name, ' + ' ORDER BY window_name) AS window_name,
                   bool_or(full_activation) AS full_activation,
                   sum(released_usd) AS released_usd
            FROM aa.actual_activation
            GROUP BY kb_framework, event_date
        )
        SELECT ev.kb_framework, ev.event_date, ev.version, ev.version AS kb_version,
               ev.country_iso3, ev.hazard, ev.window_name, ev.full_activation,
               ev.released_usd,
               count(ca.application_code) AS n_allocations,
               string_agg(ca.application_code, ' + ' ORDER BY ca.application_code)
                   AS application_codes,
               bool_or(l.flag = 'SHARED_APP') AS shared_app,
               sum(ca.amount_approved) AS cerf_amount_approved,
               sum(ca.individuals_planned) AS individuals_planned,
               sum(ca.individuals_reached) AS individuals_reached,
               min(ca.allocation_status) AS allocation_status,
               min(ca.erc_endorsement_date) AS erc_endorsement_date
        FROM ev
        LEFT JOIN aa.activation_allocation l USING (kb_framework, event_date)
        LEFT JOIN aa.cerf_allocation ca USING (application_code)
        GROUP BY ev.kb_framework, ev.event_date, ev.version, ev.country_iso3, ev.hazard,
                 ev.window_name, ev.full_activation, ev.released_usd
    """,
    # ---- compatibility names (one release): the old table names as views
    "framework_registry": """
        CREATE OR REPLACE VIEW aa.framework_registry AS SELECT * FROM aa.country_hazard
    """,
    "activation": """
        CREATE OR REPLACE VIEW aa.activation AS
        SELECT country_iso3, hazard, 'framework_aa'::text AS event_type, event_date,
               window_name, event_label, version, NULL::text AS version_match,
               ch.kb_framework, kb_event_date, people_targeted, reported_to_ahub, comments,
               w.source, w.updated_at
        FROM aa.window_activation w
        LEFT JOIN aa.country_hazard ch USING (country_iso3, hazard)
        UNION ALL
        SELECT country_iso3, hazard, event_type, event_date, NULL, event_label, NULL, NULL,
               ch.kb_framework, NULL, people_targeted, reported_to_ahub, comments,
               a.source, a.updated_at
        FROM aa.adhoc_activation a
        LEFT JOIN aa.country_hazard ch USING (country_iso3, hazard)
    """,
    "prearranged_funding": """
        CREATE OR REPLACE VIEW aa.prearranged_funding AS
        SELECT country_iso3, hazard, year, kind, fund_code, financier, amount_usd,
               NULL::boolean AS identified, NULL::text AS funding_change, note AS remarks,
               version, provenance AS version_match, source, updated_at, window_name
        FROM aa.window_funding
        WHERE agency IS NULL AND sector IS NULL
    """,
    # ---- version funding derived from the windows under the version's rollup mode
    "v_version_funding": """
        CREATE OR REPLACE VIEW aa.v_version_funding AS
        WITH votes AS (    -- how many sources report the same amount for the same window/year
            SELECT *, count(*) OVER (PARTITION BY country_iso3, hazard, version, kind, fund_code,
                                                  financier, window_name, year, amount_usd) AS n_agree
            FROM aa.window_funding
            WHERE agency IS NULL AND sector IS NULL AND amount_usd IS NOT NULL
        ),
        ranked AS (   -- ONE amount per window: latest year, best provenance, then the amount
                      -- most sources agree on (2026-09-29: a lone co-financing sheet's 6.0M
                      -- beat three sources and the document at 4.5M for Mozambique storm)
            SELECT DISTINCT ON (country_iso3, hazard, version, kind, fund_code, financier, window_name)
                   country_iso3, hazard, version, kind, fund_code, financier, window_name,
                   amount_usd
            FROM votes
            ORDER BY country_iso3, hazard, version, kind, fund_code, financier, window_name,
                     year DESC NULLS LAST,
                     CASE provenance WHEN 'entered' THEN 0 WHEN 'doc-stated' THEN 1
                                     WHEN 'kb' THEN 2 WHEN 'sheet' THEN 3 ELSE 4 END,
                     n_agree DESC, amount_usd DESC
        ),
        named AS (      -- versions that have envelope rows on NAMED windows
            SELECT DISTINCT country_iso3, hazard, version, kind, fund_code, financier
            FROM ranked WHERE window_name NOT IN ('single', 'unattributed')
        ),
        usable AS (     -- version-level leftovers only count when no named window carries the fund
            SELECT r.* FROM ranked r
            LEFT JOIN named n USING (country_iso3, hazard, version, kind, fund_code, financier)
            WHERE r.window_name NOT IN ('single', 'unattributed') OR n.version IS NULL
        ),
        w AS (
            SELECT country_iso3, hazard, version, kind, fund_code, financier,
                   sum(amount_usd) AS window_sum, max(amount_usd) AS window_max,
                   count(DISTINCT window_name) AS n_windows,
                   bool_or(window_name = 'unattributed') AS has_unattributed
            FROM usable
            GROUP BY 1, 2, 3, 4, 5, 6
        )
        SELECT w.country_iso3, w.hazard, w.version, w.kind, w.fund_code, w.financier,
               fv.window_rollup, w.n_windows, w.has_unattributed,
               CASE WHEN fv.window_rollup = 'exclusive' OR w.has_unattributed THEN w.window_max
                    ELSE w.window_sum END AS total_usd
        FROM w LEFT JOIN aa.framework_version fv USING (country_iso3, hazard, version)
    """,
    # The agency x sector split of a version's pre-arranged money, ONE source per
    # (framework, version, kind): the KB pages, the sheets and browser entries each carry
    # a split, with different sector vocabularies (Agriculture vs Food Security …), so
    # summing them doubled a framework's budget (Burkina Faso drought 2026, found
    # 2026-09-25). Priority: entered > kb (from the endorsed document) > sheets. The
    # envelope check (split total vs v_version_funding) is done by the readers.
    "v_window_funding_split": """
        CREATE OR REPLACE VIEW aa.v_window_funding_split AS
        WITH src AS (
            SELECT country_iso3, hazard, version, kind, source,
                   CASE WHEN provenance = 'entered' THEN 0
                        WHEN source LIKE 'kb-%' OR provenance = 'kb' THEN 1
                        WHEN source LIKE 'yakubu-sector-%' THEN 2
                        ELSE 3 END AS rank_
            FROM aa.window_funding
            WHERE amount_usd IS NOT NULL AND (agency IS NOT NULL OR sector IS NOT NULL)
            GROUP BY 1, 2, 3, 4, 5, 6
        ),
        pick AS (
            SELECT DISTINCT ON (country_iso3, hazard, version, kind)
                   country_iso3, hazard, version, kind, source
            FROM src ORDER BY country_iso3, hazard, version, kind, rank_, source
        )
        SELECT f.* FROM aa.window_funding f
        JOIN pick USING (country_iso3, hazard, version, kind, source)
        WHERE f.amount_usd IS NOT NULL AND (f.agency IS NOT NULL OR f.sector IS NOT NULL)
    """,
    # THE framework status, one row per (country, hazard) — the single rule every page
    # uses (map, headline counts, dashboards):
    #   active       latest version endorsed, in validity, not fully triggered
    #   updating     "being updated": an endorsed framework whose latest version is in
    #                (pre-)development, or whose latest version fully triggered / expired
    #   development  no endorsed version yet (all versions in development, or sheet-only)
    #   retired      manual flag on the pair (hidden from the map)
    #   pipeline     conversation stage only (hidden from the map)
    # "fully triggered" comes from the curated window_status flags: any window for all-in /
    # exclusive rollups, every window otherwise; a version with no windows registered falls
    # back to its activations (any not marked partial).
    "v_framework_lifecycle": """
        CREATE OR REPLACE VIEW aa.v_framework_lifecycle AS
        WITH latest AS (
            SELECT DISTINCT ON (country_iso3, hazard)
                country_iso3, hazard, version, kb_status, valid_from, valid_until, window_rollup
            FROM aa.framework_version
            ORDER BY country_iso3, hazard, valid_from DESC NULLS LAST, version DESC
        ),
        endorsed AS (
            SELECT country_iso3, hazard, bool_or(kb_status = 'endorsed') AS has_endorsed
            FROM aa.framework_version GROUP BY 1, 2
        ),
        wins AS (
            SELECT w.country_iso3, w.hazard, w.version,
                   count(*) AS n_windows,
                   count(*) FILTER (WHERE s.triggered) AS n_triggered,
                   bool_or(coalesce(k.all_in, false)) AS any_all_in
            FROM (SELECT country_iso3, hazard, version, window_name FROM aa.window
                  UNION
                  SELECT country_iso3, hazard, version, window_name FROM aa.entered_window) w
            LEFT JOIN aa.window k ON k.country_iso3 = w.country_iso3 AND k.hazard = w.hazard
                                 AND k.version = w.version AND k.window_name = w.window_name
            LEFT JOIN aa.window_status s ON s.country_iso3 = w.country_iso3
                                 AND s.hazard = w.hazard AND s.version = w.version
                                 AND s.window_name = w.window_name
            GROUP BY 1, 2, 3
        ),
        acts AS (
            SELECT country_iso3, hazard, version,
                   bool_or(full_activation IS DISTINCT FROM false) AS any_full
            FROM aa.window_activation GROUP BY 1, 2, 3
        ),
        sheet AS (
            SELECT DISTINCT ON (country_iso3, hazard) country_iso3, hazard, status
            FROM aa.framework_status ORDER BY country_iso3, hazard, as_of DESC
        ),
        x AS (
            SELECT r.country_iso3, r.hazard, r.retired, r.technical_support,
                   l.version AS latest_version, l.kb_status AS latest_status,
                   l.valid_from AS latest_valid_from, l.valid_until AS latest_valid_until,
                   coalesce(e.has_endorsed, false) AS has_endorsed,
                   coalesce(w.n_windows, 0) AS n_windows,
                   coalesce(w.n_triggered, 0) AS n_triggered,
                   CASE WHEN coalesce(w.n_windows, 0) = 0 THEN coalesce(a.any_full, false)
                        WHEN w.any_all_in OR l.window_rollup = 'exclusive' THEN w.n_triggered > 0
                        ELSE w.n_triggered = w.n_windows END AS fully_triggered,
                   (l.valid_until IS NOT NULL
                    AND l.valid_until < date_trunc('month', CURRENT_DATE)::date) AS expired,
                   s.status AS sheet_status
            FROM aa.country_hazard r
            LEFT JOIN latest l ON l.country_iso3 = r.country_iso3 AND l.hazard = r.hazard
            LEFT JOIN endorsed e ON e.country_iso3 = r.country_iso3 AND e.hazard = r.hazard
            LEFT JOIN wins w ON w.country_iso3 = l.country_iso3 AND w.hazard = l.hazard
                             AND w.version = l.version
            LEFT JOIN acts a ON a.country_iso3 = l.country_iso3 AND a.hazard = l.hazard
                             AND a.version = l.version
            LEFT JOIN sheet s ON s.country_iso3 = r.country_iso3 AND s.hazard = r.hazard
        )
        SELECT x.*,
               CASE WHEN retired THEN 'retired'
                    WHEN latest_version IS NULL THEN
                         CASE WHEN sheet_status IN ('active', 'activated_implementing',
                                                    'monitoring') THEN 'active'
                              WHEN sheet_status IN ('under_revision', 'expired') THEN 'updating'
                              WHEN sheet_status IN ('under_development',
                                                    'project_finalization') THEN 'development'
                              WHEN sheet_status IN ('dormant', 'retired') THEN 'retired'
                              ELSE 'pipeline' END
                    WHEN latest_status IN ('development', 'pre-development') THEN
                         CASE WHEN has_endorsed THEN 'updating' ELSE 'development' END
                    WHEN fully_triggered OR expired THEN 'updating'
                    ELSE 'active' END AS lifecycle
        FROM x
    """,
    # one row per (country, hazard): pair + latest status + current version's funding/coverage
    "v_trk_framework_current": """
        CREATE OR REPLACE VIEW aa.v_trk_framework_current AS
        WITH latest_status AS (
            SELECT DISTINCT ON (country_iso3, hazard)
                country_iso3, hazard, status, status_raw, as_of, source
            FROM aa.framework_status
            ORDER BY country_iso3, hazard, as_of DESC
        ),
        latest_covered AS (
            SELECT DISTINCT ON (country_iso3, hazard)
                country_iso3, hazard, people_covered, as_of
            FROM aa.people_covered
            WHERE people_covered IS NOT NULL
            ORDER BY country_iso3, hazard, as_of DESC
        ),
        current_version AS (
            SELECT DISTINCT ON (country_iso3, hazard)
                country_iso3, hazard, version, kb_status AS version_status, valid_until
            FROM aa.framework_version
            WHERE valid_from IS NOT NULL
              AND (kb_status IS NULL OR kb_status NOT IN ('development'))
            ORDER BY country_iso3, hazard,
                     (kb_status = 'endorsed') DESC, valid_from DESC
        ),
        cerf AS (   -- the current version's CERF envelope, from its windows
            SELECT vf.country_iso3, vf.hazard, vf.version, vf.total_usd,
                   (SELECT max(year) FROM aa.window_funding f
                     WHERE f.country_iso3 = vf.country_iso3 AND f.hazard = vf.hazard
                       AND f.version = vf.version AND f.kind = 'prearranged'
                       AND f.fund_code = 'cerf') AS year
            FROM aa.v_version_funding vf
            WHERE vf.kind = 'prearranged' AND vf.fund_code = 'cerf'
        )
        SELECT r.country_iso3, r.hazard, r.country_name, r.region, r.kb_framework,
               r.in_kb, r.language, r.us_prio, r.retired, r.technical_support,
               lc.lifecycle, lc.fully_triggered, lc.expired, lc.n_windows, lc.n_triggered,
               lc.latest_version, lc.latest_status,
               v.version AS current_version, v.version_status, v.valid_until,
               CASE WHEN r.retired THEN 'retired'
                    WHEN v.version_status = 'endorsed'
                         AND (v.valid_until IS NULL OR v.valid_until >= CURRENT_DATE)
                         AND s.status IN ('under_revision', 'under_development',
                                          'project_finalization',
                                          'early_conversations',
                                          'advanced_conversations')
                    THEN 'active'
                    WHEN s.status IS NULL AND v.version_status = 'endorsed'
                         AND (v.valid_until IS NULL OR v.valid_until >= CURRENT_DATE)
                    THEN 'active'
                    ELSE s.status
               END AS status,
               s.status AS observed_status,
               s.status_raw, s.as_of AS status_as_of, s.source AS status_source,
               p.total_usd AS cerf_prearranged_usd, p.year AS prearranged_year,
               c.people_covered
        FROM aa.country_hazard r
        LEFT JOIN aa.v_framework_lifecycle lc ON lc.country_iso3 = r.country_iso3
                                              AND lc.hazard = r.hazard
        LEFT JOIN current_version v ON v.country_iso3 = r.country_iso3 AND v.hazard = r.hazard
        LEFT JOIN latest_status s ON s.country_iso3 = r.country_iso3 AND s.hazard = r.hazard
        LEFT JOIN latest_covered c ON c.country_iso3 = r.country_iso3 AND c.hazard = r.hazard
        LEFT JOIN cerf p ON p.country_iso3 = r.country_iso3 AND p.hazard = r.hazard
                        AND p.version = v.version
    """,
    # version-level rollup: budget from the windows, coverage, activation count
    "v_trk_version_summary": """
        CREATE OR REPLACE VIEW aa.v_trk_version_summary AS
        SELECT fv.country_iso3, fv.hazard, fv.version, fv.kb_framework, fv.kb_status,
               fv.valid_from, fv.valid_until, fv.source,
               fv.prearranged_usd_doc,
               (SELECT vf.total_usd FROM aa.v_version_funding vf
                 WHERE vf.country_iso3 = fv.country_iso3 AND vf.hazard = fv.hazard
                   AND vf.version = fv.version AND vf.kind = 'prearranged'
                   AND vf.fund_code = 'cerf') AS prearranged_usd_tracked,
               (SELECT max(pc.people_covered) FROM aa.people_covered pc
                 WHERE pc.country_iso3 = fv.country_iso3 AND pc.hazard = fv.hazard
                   AND pc.version = fv.version) AS people_covered,
               (SELECT count(*) FROM aa.window_activation e
                 WHERE e.country_iso3 = fv.country_iso3 AND e.hazard = fv.hazard
                   AND e.version = fv.version) AS n_activations
        FROM aa.framework_version fv
        ORDER BY fv.country_iso3, fv.hazard, fv.valid_from
    """,
    # window activations whose window is not in the window registry — the curation queue
    "v_trk_activation_window_check": """
        CREATE OR REPLACE VIEW aa.v_trk_activation_window_check AS
        SELECT a.country_iso3, a.hazard, a.version, a.window_name, a.event_date,
               (w.window_name IS NOT NULL) AS in_kb_windows,
               (ew.window_name IS NOT NULL) AS in_entered_windows,
               (SELECT string_agg(x.window_name, ' | ') FROM (
                   SELECT window_name FROM aa.window w2
                    WHERE w2.country_iso3 = a.country_iso3 AND w2.hazard = a.hazard
                      AND w2.version = a.version
                   UNION SELECT window_name FROM aa.entered_window e2
                    WHERE e2.country_iso3 = a.country_iso3 AND e2.hazard = a.hazard
                      AND e2.version = a.version) x) AS registry_windows
        FROM aa.window_activation a
        LEFT JOIN aa.window w USING (country_iso3, hazard, version, window_name)
        LEFT JOIN aa.entered_window ew USING (country_iso3, hazard, version, window_name)
    """,
    # activation events vs KB actual_activation: matches + conflicts
    "v_trk_activation_reconciliation": """
        CREATE OR REPLACE VIEW aa.v_trk_activation_reconciliation AS
        WITH funding AS (
            SELECT country_iso3, hazard, event_date, window_name, event_label,
                   event_type,
                   sum(amount_usd) AS total_usd,
                   string_agg(fund_code || ': ' || coalesce(allocation_code, '?'),
                              ' + ' ORDER BY fund_code) AS funds,
                   count(*) AS n_funding_rows
            FROM aa.activation_funding
            GROUP BY 1, 2, 3, 4, 5, 6
        )
        SELECT act.country_iso3, act.hazard, act.event_date, act.window_name,
               act.event_label, act.event_type, act.version,
               act.people_targeted, act.source,
               f.total_usd AS sheet_total_usd, f.funds, f.n_funding_rows,
               act.kb_framework, act.kb_event_date,
               a.released_usd AS kb_released_usd, a.full_activation,
               CASE
                   WHEN act.source LIKE 'historical-ocha-web%%'
                       THEN 'UNVERIFIED_EVIDENCE'
                   WHEN act.event_type = 'early_action' THEN 'EARLY_ACTION'
                   WHEN act.event_type = 'adhoc_aa' THEN 'ADHOC_AA'
                   WHEN act.kb_framework IS NULL THEN 'KB_BACKFILL'
                   WHEN a.released_usd IS NOT NULL AND f.total_usd IS NOT NULL
                        AND abs(a.released_usd - f.total_usd) > 1000
                       THEN 'AMOUNT_CONFLICT'
                   ELSE 'OK'
               END AS reconciliation
        FROM aa.activation act
        LEFT JOIN funding f USING (country_iso3, hazard, event_date, window_name,
                                   event_label, event_type)
        LEFT JOIN aa.actual_activation a
               ON a.kb_framework = act.kb_framework
              AND a.event_date = act.kb_event_date
    """,
    # KB activations with no counterpart in the window activations
    "v_trk_activation_kb_only": """
        CREATE OR REPLACE VIEW aa.v_trk_activation_kb_only AS
        SELECT a.kb_framework, a.event_date, a.country_iso3, a.window_name,
               a.full_activation, a.released_usd, a.note
        FROM aa.actual_activation a
        WHERE NOT EXISTS (
            SELECT 1 FROM aa.activation e
            WHERE e.kb_framework = a.kb_framework
              AND e.kb_event_date = a.event_date
        )
    """,
    "v_trk_aa_localization": """
        CREATE OR REPLACE VIEW aa.v_trk_aa_localization AS
        SELECT year, localization,
               count(*) AS n_subgrants,
               sum(subgrant_usd) AS subgrant_usd
        FROM aa.cerf_subgrant
        WHERE is_aa AND localization IS NOT NULL
        GROUP BY year, localization
        ORDER BY year, localization
    """,
    "v_trk_aa_flag_reconciliation": """
        CREATE OR REPLACE VIEW aa.v_trk_aa_flag_reconciliation AS
        SELECT x.application_code, x.is_aa_reported, c.aa_keyword,
               c.country_iso3, c.year, c.emergency_type, c.amount_approved
        FROM aa.cerf_allocation_extra x
        JOIN aa.cerf_allocation c ON c.application_code = x.application_code
        WHERE x.is_aa_reported IS DISTINCT FROM c.aa_keyword
    """,
    # window envelopes vs the document's stated total under the version's rollup mode
    "v_trk_funding_rollup": """
        CREATE OR REPLACE VIEW aa.v_trk_funding_rollup AS
        SELECT vf.country_iso3, vf.hazard, vf.version, vf.fund_code, vf.window_rollup,
               fv.prearranged_usd_doc AS stated_total,
               vf.total_usd AS rollup_total, vf.n_windows, vf.has_unattributed,
               CASE
                   WHEN fv.prearranged_usd_doc IS NULL THEN 'NO_STATED_TOTAL'
                   WHEN vf.has_unattributed THEN 'WINDOW_UNATTRIBUTED'
                   WHEN fv.window_rollup IS NULL AND vf.n_windows > 1 THEN 'NO_ROLLUP_MODE'
                   WHEN abs(vf.total_usd - fv.prearranged_usd_doc)
                        <= greatest(1000, 0.01 * fv.prearranged_usd_doc) THEN 'OK'
                   ELSE 'MISMATCH'
               END AS rollup_check
        FROM aa.v_version_funding vf
        JOIN aa.framework_version fv USING (country_iso3, hazard, version)
        WHERE vf.kind = 'prearranged' AND vf.fund_code = 'cerf'
    """,
    # the backtest curation queue: error = breaks a rule the database enforces on new rows
    # (rows from before the guards); warn = worth a look; info = the sealing queue
    "v_trk_backtest_check": """
        CREATE OR REPLACE VIEW aa.v_trk_backtest_check AS
        SELECT 'error' AS severity, 'simulated year outside the analysis span' AS "check",
               s.country_iso3, s.hazard, s.version, s.window_name,
               s.event_year || ' outside ' || w.analysis_start || '-' || w.analysis_end AS detail
        FROM aa.simulated_activation s
        JOIN aa.window w USING (country_iso3, hazard, version, window_name)
        WHERE s.event_year NOT BETWEEN w.analysis_start AND w.analysis_end
        UNION ALL
        SELECT 'error', 'backtest under a label that is no version',
               w.country_iso3, w.hazard, w.version, w.window_name, 'not in framework_version'
        FROM aa.window w
        LEFT JOIN aa.framework_version f USING (country_iso3, hazard, version)
        WHERE f.version IS NULL
        UNION ALL
        SELECT 'error', 'simulated year without its window',
               s.country_iso3, s.hazard, s.version, s.window_name, s.event_year::text
        FROM aa.simulated_activation s
        LEFT JOIN aa.window w USING (country_iso3, hazard, version, window_name)
        WHERE w.window_name IS NULL
        UNION ALL
        SELECT 'error', 'reported performance under a label that is no version',
               r.country_iso3, r.hazard, r.version, NULL, 'not in framework_version'
        FROM aa.version_performance_reported r
        LEFT JOIN aa.framework_version f USING (country_iso3, hazard, version)
        WHERE f.version IS NULL
        UNION ALL
        SELECT 'warn', 'window without an analysis span',
               country_iso3, hazard, version, window_name, 'the RP has no denominator'
        FROM aa.window WHERE analysis_start IS NULL OR analysis_end IS NULL
        UNION ALL
        SELECT 'warn', 'simulated year in or after the year the version took effect',
               s.country_iso3, s.hazard, s.version, s.window_name,
               s.event_year || ' vs valid from ' || f.valid_from
               || ' (a real activation, unless the document labels seasons by start year)'
        FROM aa.simulated_activation s
        JOIN aa.framework_version f USING (country_iso3, hazard, version)
        WHERE s.event_year >= extract(year FROM f.valid_from)
        UNION ALL
        SELECT 'warn', 'computed RP differs from the reported one by more than a tenth',
               country_iso3, hazard, version, window_name,
               return_period || ' computed (Weibull) vs ' || rp_reported || ' reported'
        FROM aa.v_window_performance
        WHERE rp_reported IS NOT NULL AND return_period IS NOT NULL
          AND abs(return_period - rp_reported) > 0.1 * rp_reported
        UNION ALL
        SELECT 'info', 'endorsed backtest not yet checked against its document (unsealed)',
               f.country_iso3, f.hazard, f.version, NULL,
               count(*) || ' window(s)'
        FROM aa.framework_version f
        JOIN aa.window w USING (country_iso3, hazard, version)
        WHERE f.kb_status = 'endorsed' AND f.backtest_sealed_at IS NULL
        GROUP BY f.country_iso3, f.hazard, f.version
        UNION ALL
        SELECT 'info', 'endorsed version with no backtest recorded',
               f.country_iso3, f.hazard, f.version, NULL, NULL
        FROM aa.framework_version f
        WHERE f.kb_status = 'endorsed'
          AND NOT EXISTS (SELECT 1 FROM aa.window w
                          WHERE (w.country_iso3, w.hazard, w.version)
                              = (f.country_iso3, f.hazard, f.version))
    """,
}
