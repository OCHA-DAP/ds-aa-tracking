# ds-aa-tracking

Single authoritative tracking system for OCHA's anticipatory action (AA) portfolio,
superseding the team-member spreadsheets it was seeded from.

This repo owns a set of tables in the dev Postgres `aa` schema, alongside (never
overlapping with) the KB-owned trigger-performance tables (`ds-knowledge-base`) and the
CERF OneGMS mirror (`ds-cerf-supplement`). It adds:

- **framework lifecycle**: registry of every (country, hazard) framework incl. the
  pipeline (early conversations → active → dormant/expired), status snapshots over time,
  focal points, trigger-window calendar
- **funding**: pre-arranged amounts per year and fund source, co-financing,
  sector-level pre-arranged budgets; donor shares (`dash-donors.html`, `scripts/donors.py`):
  each donor's share of a fund's income per fiscal year (`aa.v_contribution`, the
  ds-cerf-supplement contribution mirrors) × the AA that fund released / pre-arranged that
  year, plus hand-entered build earmarks (`aa.build_contribution`)
- **activations**: the full activation-event record 2020→ (framework + ad-hoc, AA + EA,
  CERF + country/regional funds), crosswalked to KB `actual_activation` and the CERF
  mirror, with a reconciliation view for conflicts
- **reporting**: which frameworks count toward which external reports (A-Hub, UK BCs,
  SG/CERF/OCHA annual reports, SF KPI, CPC), GHO/HNRP inclusion, people covered
- **CERF depth**: subgrants to implementing partners (localization), project-level CVA
  and markers, application-level beneficiary demographics, final-report narratives,
  emergency-type retags, CIRV

## Layout

- `src/ds_aa_tracking/normalize.py` — canonical country/hazard/status vocabularies
- `src/ds_aa_tracking/parsers.py` — one parser per source workbook
- `src/ds_aa_tracking/schema.py` — DDL (tables + views), all in schema `aa`; hierarchy
  country_hazard → framework_version → window → {window_activation, simulated_activation,
  window_funding}; ad hoc / early-action allocations off the pair (adhoc_activation)
- publishing: `.github/workflows/publish.yml` rebuilds and publishes nightly, on pushes to
  main, by hand (workflow_dispatch, optionally from a dated snapshot) and on
  `repository_dispatch` events `kb-updated` / `data-updated` (the knowledge base sends one
  when framework pages change). It never touches the dev DB: it restores the blob snapshot
  (below) into a Postgres service container and builds against localhost. Needs the org
  blob secret plus repo secrets `EXTRACT_TOKEN` (the proxy site token) and `SITE_PASSWORD`
  (staticrypt).
- snapshot: the dev DB is losing public network access (2026-09); only Databricks reaches
  it. `databricks.yml` defines one job, **AA Tracking Nightly** (03:30 UTC, Job Compute):
  `databricks/nightly.py` clones the KB and runs `scripts/sync_kb.py`, then
  `scripts/export_snapshot.py` writes every `aa` table (parquet) plus the DDL metadata
  (`schema.json`: exact column types, defaults, sequences, constraints, indexes, view
  definitions) and a `manifest.json` to the dev blob `projects/ds-aa-tracking/snapshot/`
  — `latest/` and a dated copy kept 30 days. `scripts/restore_snapshot.py` rebuilds the
  schema verbatim in a local Postgres (`src/ds_aa_tracking/snapshot.py` holds both halves),
  so nothing in the build is ported to another SQL dialect and the schema page stays
  faithful. Pages carry a "data snapshot <time> UTC" stamp.
- statuses: version = endorsed | development | pre-development (superseded is inferred);
  retired = a flag on country_hazard; per-window triggered flags in window_status
- `src/ds_aa_tracking/migrations.py` — the idempotent window-first migration (run by ensure_schema)
- `scripts/ingest.py` — parse → crosswalk to KB → full-refresh load (dev DB)
- `scripts/build_site.py` — render the password-protected GH Pages review site
- `scripts/admin_page.py` — `admin.html`: Django-admin-style CRUD over every `aa` table,
  populated live from the proxy's `/schema`; viewer = site password, editor = separate
  token prompted for in the browser (never embedded). Supersedes the tracking-tables tab.
- `proxy/server.js` — the one server: PDF extraction, framework entry, and generic
  `/schema` `/rows` `/distinct` `/save` `/delete` for the admin page; every field change is
  audited to `aa.entry_audit`; KB-loader and OneGMS-mirror tables are read-only
- `scripts/dashboards.py` — dashboards, per-framework pages, explorer, entry forms
- `scripts/donors.py` — the donor-shares page (reads `dashboards.funding_series`, so its
  released / pre-arranged totals are the Funding page's)
- `scripts/landing.py` — landing map (base: Natural Earth 1:50m simplified as one topology so
  borders stay shared; zoom: FieldMaps edge-matched COD-AB for every country in view): zoom
  to a country, subnational scope per framework
  version (KB `geographic_scope` names matched to FieldMaps edge-matched COD-AB boundaries; one
  `adm-<ISO3>.json` per country with its neighbours, simplified as one shared-edge topology; layers cached under `data/fieldmaps/`)
  Scope tiers: inside a block-form `geographic_scope`, a comment line on its own names a tier
  for the items below it (`# riverine window — …`), and an item like `Non-endemic provinces
  (all other)` is a rest-of-country tier; tiers render as shades of the hazard colour

## Running

The dev DB is the single source of truth: data is entered and corrected through the
site (`entry.html`, `admin.html`) and the KB sync — there is no spreadsheet ingest any
more (`scripts/ingest.py` is the retired migration-era loader and refuses to run).
DB access via `ocha-stratus` env vars; `PGSSLMODE=require` is set automatically.

```sh
uv run python scripts/ensure_schema.py   # idempotent: create missing tables, additive migrations, views
uv run python scripts/sync_kb.py         # upsert new KB framework pages into the registry
uv run python scripts/build_site.py      # needs graphviz (`brew install graphviz`) for the ERD
bash scripts/publish.sh                  # build → encrypt → gh-pages (SKIP_BUILD=1 reuses the build)
```

Once the laptop can no longer reach the dev DB, work from the snapshot in a local Postgres
(the schema/data writes then go through the site's proxy, or through the Databricks job
with `--ensure-schema` for DDL):

```sh
docker run -d --name aa-pg -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:16
export DSCI_AZ_DB_DEV_HOST=localhost DSCI_AZ_DB_DEV_UID=postgres DSCI_AZ_DB_DEV_PW=postgres \
       DSCI_AZ_DB_DEV_UID_WRITE=postgres DSCI_AZ_DB_DEV_PW_WRITE=postgres PGSSLMODE=disable
uv run python scripts/restore_snapshot.py            # --snapshot YYYY-MM-DD for an older one
uv run python scripts/build_site.py                  # unchanged: it just sees localhost
```

Deploy or run the Databricks job with `databricks bundle deploy -t prod -p DEFAULT` /
`databricks bundle run aa_tracking_nightly -t prod -p DEFAULT` (see `databricks.yml`).

The proxy (`proxy/`) runs as Azure Web App `chd-ds-aa-extract`; app settings hold the
Anthropic key, the DB write login, `SITE_TOKEN` (viewer) and `EDITOR_TOKEN` (editor).
Redeploy with `az webapp deploy --type zip` from a zip of `proxy/`.
