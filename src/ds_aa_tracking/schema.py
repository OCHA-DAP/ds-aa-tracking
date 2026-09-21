"""DDL for the ds-aa-tracking tables in the dev `aa` schema.

Conventions (shared with the existing `aa` writers):
- natural text keys; UNIQUE NULLS NOT DISTINCT composites on fact tables
- this repo is the single writer of every table below; it never writes the
  KB-owned tables (framework_version_map, window, simulated_activation,
  funding_breakdown, actual_activation, activation_allocation) or the
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
}

# ------------------------------------------------------------------ durable
# Entry-path tables: written by the chd-ds-aa-extract proxy (browser entry page)
# and READ by the ingest, which merges them (entered values WIN over KB/sweeps —
# "versions ENTERED, not inferred"). The full-refresh load creates them if
# missing but NEVER drops or truncates them: they are the durable record of
# human entry, not derived data.
DURABLE_TABLES = {
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
}

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
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS cerf_subgrant_project_idx ON aa.cerf_subgrant (project_code)",
    "CREATE INDEX IF NOT EXISTS cerf_subgrant_app_idx ON aa.cerf_subgrant (application_code)",
    """CREATE UNIQUE INDEX IF NOT EXISTS cerf_subgrant_uniq ON aa.cerf_subgrant
       (project_code, partner_name, COALESCE(subgrant_usd, -1), source)""",
]

LEGACY_TABLES = [   # renamed zz_legacy_<name> by the window-first migration; read-only history
    "framework_registry", "activation", "prearranged_funding", "prearranged_sector_budget",
    "entered_version_funding",
]

VIEWS = {
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
        WITH ranked AS (   -- ONE amount per window: latest year, best provenance
            SELECT DISTINCT ON (country_iso3, hazard, version, kind, fund_code, financier, window_name)
                   country_iso3, hazard, version, kind, fund_code, financier, window_name,
                   amount_usd
            FROM aa.window_funding
            WHERE agency IS NULL AND sector IS NULL AND amount_usd IS NOT NULL
            ORDER BY country_iso3, hazard, version, kind, fund_code, financier, window_name,
                     year DESC NULLS LAST,
                     CASE provenance WHEN 'entered' THEN 0 WHEN 'doc-stated' THEN 1
                                     WHEN 'kb' THEN 2 WHEN 'sheet' THEN 3 ELSE 4 END,
                     amount_usd DESC
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
}
