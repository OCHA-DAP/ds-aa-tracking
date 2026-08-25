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
    "framework_version": """
        CREATE TABLE IF NOT EXISTS aa.framework_version (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            version text NOT NULL,         -- date label matching KB page (YYYY[-MM[-DD]])
            kb_framework text,
            kb_status text,                -- endorsed | superseded | retired | development
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
            source text NOT NULL,          -- kb-frontmatter | sheet-revision | ocha-web | pa-monorepo
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
    "prearranged_funding": """
        CREATE TABLE IF NOT EXISTS aa.prearranged_funding (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            year smallint NOT NULL,
            kind text NOT NULL,            -- prearranged | cofinancing | non_aa_mobilised
            fund_code text,                -- references aa.fund ('all' = source stated
                                           -- only a total; cbpf-unspecified until curated);
                                           -- NULL exactly for non-OCHA money (see CHECK)
            financier text,                -- who co-finances (agency etc.) — free text
            amount_usd numeric,
            identified boolean,            -- cofinancing identified? (Y/N/TBC sheets)
            funding_change text,           -- new | extended | renewed
            remarks text,
            version text,                  -- attributed framework version (see framework_version)
            version_match text,            -- kb-activation | auto-interval | auto-post-validity
            source text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            CHECK ((fund_code IS NULL) = (kind IN ('cofinancing', 'non_aa_mobilised'))),
            UNIQUE NULLS NOT DISTINCT
                (country_iso3, hazard, year, kind, fund_code, financier, source)
        )""",
    "prearranged_sector_budget": """
        CREATE TABLE IF NOT EXISTS aa.prearranged_sector_budget (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            window_name text,              -- e.g. Jamuna / Padma — sheet 'subunits'
                                           -- are windows of the framework
            agency text NOT NULL,
            sector text NOT NULL,
            amount_usd numeric,
            year_label text,               -- 'Prearranged' | '2025' | '2026' (raw)
            status text,
            version text,                  -- attributed framework version (see framework_version)
            version_match text,            -- kb-activation | auto-interval | auto-post-validity
            source text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE NULLS NOT DISTINCT
                (country_iso3, hazard, window_name, agency, sector, year_label)
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
    "activation": """
        CREATE TABLE IF NOT EXISTS aa.activation (
            country_iso3 text NOT NULL,
            hazard text NOT NULL,
            event_type text NOT NULL,      -- framework_aa | adhoc_aa | early_action
            event_date text NOT NULL,      -- partial ISO, as specific as known:
                                           -- YYYY | YYYY-MM | YYYY-MM-DD | YYYY-MM-DDTHH:MM
            window_name text,              -- NOT NULL for framework activations
                                           -- ('unspecified' until curated); NULL for adhoc/EA
            event_label text NOT NULL DEFAULT '',  -- last-resort tie-breaker
                                           -- (storm name | admin area | phase-N)
            version text,
            version_match text,
            kb_framework text,
            kb_event_date text,
            people_targeted bigint,
            reported_to_ahub text,
            comments text,
            source text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            CHECK ((event_type = 'framework_aa') = (window_name IS NOT NULL)),
            -- event_type included beyond the design key: an adhoc-AA and an EA can
            -- legitimately share a month at sheet-era date precision
            UNIQUE NULLS NOT DISTINCT
                (country_iso3, hazard, event_date, window_name, event_label, event_type)
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
            WHERE kind = 'prearranged' AND fund_code = 'cerf'
            ORDER BY country_iso3, hazard, year DESC,
                     (source = 'yakubu-prearranged-jun2026') DESC
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
        )
        SELECT r.country_iso3, r.hazard, r.country_name, r.region, r.kb_framework,
               r.in_kb, r.language, r.us_prio,
               v.version AS current_version, v.version_status, v.valid_until,
               s.status, s.status_raw, s.as_of AS status_as_of, s.source AS status_source,
               p.amount_usd AS cerf_prearranged_usd, p.year AS prearranged_year,
               c.people_covered
        FROM aa.framework_registry r
        LEFT JOIN current_version v USING (country_iso3, hazard)
        LEFT JOIN latest_status s USING (country_iso3, hazard)
        LEFT JOIN latest_prearranged p USING (country_iso3, hazard)
        LEFT JOIN latest_covered c USING (country_iso3, hazard)
    """,
    # version-attribution health: how much of each version-level table is attributed
    "v_trk_version_attribution": """
        CREATE OR REPLACE VIEW aa.v_trk_version_attribution AS
        SELECT t.table_name, t.version_match, count(*) AS n_rows
        FROM (
            SELECT 'framework_status' AS table_name, version_match FROM aa.framework_status
            UNION ALL SELECT 'framework_calendar', version_match FROM aa.framework_calendar
            UNION ALL SELECT 'prearranged_funding', version_match FROM aa.prearranged_funding
            UNION ALL SELECT 'prearranged_sector_budget', version_match FROM aa.prearranged_sector_budget
            UNION ALL SELECT 'people_covered', version_match FROM aa.people_covered
            UNION ALL SELECT 'activation', version_match FROM aa.activation
            UNION ALL SELECT 'framework_focal_point', version_match FROM aa.framework_focal_point
            UNION ALL SELECT 'report_channel_inclusion', version_match FROM aa.report_channel_inclusion
        ) t
        GROUP BY t.table_name, t.version_match
        ORDER BY t.table_name, t.version_match
    """,
    # version-level rollup: what each version's tracked budget/coverage looks like
    "v_trk_version_summary": """
        CREATE OR REPLACE VIEW aa.v_trk_version_summary AS
        SELECT fv.country_iso3, fv.hazard, fv.version, fv.kb_framework, fv.kb_status,
               fv.valid_from, fv.valid_until, fv.source,
               fv.prearranged_usd_doc,
               (SELECT max(pf.amount_usd) FROM aa.prearranged_funding pf
                 WHERE pf.country_iso3 = fv.country_iso3 AND pf.hazard = fv.hazard
                   AND pf.version = fv.version AND pf.kind = 'prearranged'
                   AND pf.fund_code IN ('cerf', 'all')) AS prearranged_usd_tracked,
               (SELECT max(pc.people_covered) FROM aa.people_covered pc
                 WHERE pc.country_iso3 = fv.country_iso3 AND pc.hazard = fv.hazard
                   AND pc.version = fv.version) AS people_covered,
               (SELECT count(*) FROM aa.activation e
                 WHERE e.country_iso3 = fv.country_iso3 AND e.hazard = fv.hazard
                   AND e.version = fv.version) AS n_activations
        FROM aa.framework_version fv
        ORDER BY fv.country_iso3, fv.hazard, fv.valid_from
    """,
    # sheet activation events vs KB actual_activation: matches + conflicts
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
               act.event_label, act.event_type, act.version, act.version_match,
               act.people_targeted, act.source,
               f.total_usd AS sheet_total_usd, f.funds, f.n_funding_rows,
               act.kb_framework, act.kb_event_date,
               a.released_usd AS kb_released_usd, a.full_activation,
               CASE
                   WHEN act.event_type = 'early_action' THEN 'EARLY_ACTION'
                   WHEN act.event_type = 'adhoc_aa' THEN 'ADHOC_AA'
                   WHEN act.kb_framework IS NULL THEN 'MISSING_IN_KB'
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
    # KB activations with no counterpart in the sheet list
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
