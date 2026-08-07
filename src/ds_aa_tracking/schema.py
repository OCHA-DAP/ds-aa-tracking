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
    "framework_registry": """
        CREATE TABLE IF NOT EXISTS aa.framework_registry (
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
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (country_iso3, hazard)
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
            as_of date NOT NULL,
            source text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (country_iso3, hazard, month, phase, as_of)
        )""",
    "prearranged_funding": """
        CREATE TABLE IF NOT EXISTS aa.prearranged_funding (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            year smallint NOT NULL,
            kind text NOT NULL,            -- prearranged | cofinancing | non_aa_mobilised
            fund_source text NOT NULL,     -- cerf | country_regional | all | other
            amount_usd numeric,
            identified boolean,            -- cofinancing identified? (Y/N/TBC sheets)
            funding_change text,           -- new | extended | renewed
            remarks text,
            source text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE NULLS NOT DISTINCT
                (country_iso3, hazard, year, kind, fund_source, source)
        )""",
    "prearranged_sector_budget": """
        CREATE TABLE IF NOT EXISTS aa.prearranged_sector_budget (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            subunit text,                  -- e.g. Jamuna / Padma sub-frameworks
            agency text NOT NULL,
            sector text NOT NULL,
            amount_usd numeric,
            year_label text,               -- 'Prearranged' | '2025' | '2026' (raw)
            status text,
            source text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE NULLS NOT DISTINCT
                (country_iso3, hazard, subunit, agency, sector, year_label)
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
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (country_iso3, hazard, as_of, source)
        )""",
    "activation_event": """
        CREATE TABLE IF NOT EXISTS aa.activation_event (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            year smallint NOT NULL,
            month smallint,
            fund_source text NOT NULL,     -- cerf | country_fund | regional_fund
            mechanism text NOT NULL,       -- framework | adhoc
            aa_or_ea text NOT NULL,        -- AA | EA
            amount_usd numeric,
            people_targeted bigint,
            reported_to_ahub text,         -- yes | no | not yet
            region text,
            comments text,
            kb_framework text,             -- matched to aa.actual_activation
            kb_event_date text,
            application_code text,         -- matched via aa.activation_allocation
            match_method text,
            source text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE NULLS NOT DISTINCT
                (country_iso3, hazard, year, month, fund_source, aa_or_ea)
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

INDEXES = [
    "CREATE INDEX IF NOT EXISTS cerf_subgrant_project_idx ON aa.cerf_subgrant (project_code)",
    "CREATE INDEX IF NOT EXISTS cerf_subgrant_app_idx ON aa.cerf_subgrant (application_code)",
    """CREATE UNIQUE INDEX IF NOT EXISTS cerf_subgrant_uniq ON aa.cerf_subgrant
       (project_code, partner_name, COALESCE(subgrant_usd, -1), source)""",
]

VIEWS = {
    # one row per (country, hazard): registry + latest status + latest funding/coverage
    "v_trk_framework_current": """
        CREATE OR REPLACE VIEW aa.v_trk_framework_current AS
        WITH latest_status AS (
            SELECT DISTINCT ON (country_iso3, hazard)
                country_iso3, hazard, status, status_raw, as_of, source
            FROM aa.framework_status
            ORDER BY country_iso3, hazard, as_of DESC
        ),
        latest_prearranged AS (
            SELECT DISTINCT ON (country_iso3, hazard)
                country_iso3, hazard, amount_usd, year, source
            FROM aa.prearranged_funding
            WHERE kind = 'prearranged' AND fund_source = 'cerf'
            ORDER BY country_iso3, hazard, year DESC,
                     (source = 'yakubu-prearranged-jun2026') DESC
        ),
        latest_covered AS (
            SELECT DISTINCT ON (country_iso3, hazard)
                country_iso3, hazard, people_covered, as_of
            FROM aa.people_covered
            WHERE people_covered IS NOT NULL
            ORDER BY country_iso3, hazard, as_of DESC
        )
        SELECT r.country_iso3, r.hazard, r.country_name, r.region, r.kb_framework,
               r.in_kb, r.language, r.us_prio,
               s.status, s.status_raw, s.as_of AS status_as_of, s.source AS status_source,
               p.amount_usd AS cerf_prearranged_usd, p.year AS prearranged_year,
               c.people_covered
        FROM aa.framework_registry r
        LEFT JOIN latest_status s USING (country_iso3, hazard)
        LEFT JOIN latest_prearranged p USING (country_iso3, hazard)
        LEFT JOIN latest_covered c USING (country_iso3, hazard)
    """,
    # sheet activation events vs KB actual_activation: matches + conflicts
    "v_trk_activation_reconciliation": """
        CREATE OR REPLACE VIEW aa.v_trk_activation_reconciliation AS
        SELECT e.country_iso3, e.hazard, e.year, e.month, e.fund_source,
               e.mechanism, e.aa_or_ea, e.amount_usd AS sheet_amount_usd,
               e.people_targeted, e.kb_framework, e.kb_event_date, e.match_method,
               a.released_usd AS kb_released_usd,
               a.full_activation, a.window_name,
               CASE
                   WHEN e.kb_framework IS NULL AND e.mechanism = 'framework'
                        AND e.fund_source = 'cerf'
                       THEN 'MISSING_IN_KB'
                   WHEN e.kb_framework IS NULL THEN 'OUT_OF_KB_SCOPE'
                   WHEN a.released_usd IS NOT NULL AND e.amount_usd IS NOT NULL
                        AND abs(a.released_usd - e.amount_usd) > 1000
                       THEN 'AMOUNT_CONFLICT'
                   ELSE 'OK'
               END AS reconciliation
        FROM aa.activation_event e
        LEFT JOIN aa.actual_activation a
               ON a.kb_framework = e.kb_framework
              AND a.event_date = e.kb_event_date
    """,
    # KB activations with no counterpart in the sheet list
    "v_trk_activation_kb_only": """
        CREATE OR REPLACE VIEW aa.v_trk_activation_kb_only AS
        SELECT a.kb_framework, a.event_date, a.country_iso3, a.window_name,
               a.full_activation, a.released_usd, a.note
        FROM aa.actual_activation a
        WHERE NOT EXISTS (
            SELECT 1 FROM aa.activation_event e
            WHERE e.kb_framework = a.kb_framework
              AND e.kb_event_date = a.event_date
        )
    """,
    # localization rollup on the curated AA subgrants
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
    # sheet-reported AA flag vs the mirror's title-keyword heuristic
    "v_trk_aa_flag_reconciliation": """
        CREATE OR REPLACE VIEW aa.v_trk_aa_flag_reconciliation AS
        SELECT x.application_code, x.is_aa_reported, c.aa_keyword,
               c.country_iso3, c.year, c.emergency_type, c.amount_approved
        FROM aa.cerf_allocation_extra x
        JOIN aa.cerf_allocation c ON c.application_code = x.application_code
        WHERE x.is_aa_reported IS DISTINCT FROM c.aa_keyword
    """,
}
