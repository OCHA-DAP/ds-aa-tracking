# ds-aa-tracking

Single authoritative tracking system for OCHA's anticipatory action (AA) portfolio,
superseding the team-member spreadsheets it was seeded from — and, since 2026-09-28,
the knowledge base's framework pages (see "The KB flip").

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

## The KB flip (2026-09-28)

This system is **authoritative**. The knowledge base (`ds-knowledge-base`) is no longer a
source: its framework pages were imported once into `aa.version_page` (scope, monitoring
months, trigger facets, data sources, agencies, the "Trigger windows" table, the page body)
and are edited here; the nightly KB sweep (`scripts/sync_kb.py`) is off; the site build
reads only the database snapshot (no KB checkout). The KB's job is now the other way
round: read this DB (registry, versions, statuses, funding) and find the code, monitoring
and published documents for each framework. The KB-loader tables (`window`,
`simulated_activation`, `funding_breakdown`, `actual_activation`) stay as frozen inputs
until their loaders are pointed at this DB.

Two more DB-first tables came with the flip: `aa.learning_document` (the AA Compendium of
Available Resources, Sept 2026, plus the website to-add list; `scripts/import_learning.py`;
`internal` rows never render) and `aa.framework_partner` (organisations named in the
endorsed framework documents, extracted once with `scripts/import_partners.py`, curated in
the admin page). Sector/agency splits are read through `aa.v_window_funding_split` (one
source per version, so a budget table can never double-count). Snapshots dated 31 December
are kept forever (the year-end official state, for the map's time view).

## Layout

- `src/ds_aa_tracking/normalize.py` — canonical country/hazard/status vocabularies
- `src/ds_aa_tracking/parsers.py` — one parser per source workbook
- `src/ds_aa_tracking/schema.py` — DDL (tables + views), all in schema `aa`; hierarchy
  country_hazard → framework_version → window → {window_activation, simulated_activation,
  window_funding}; ad hoc / early-action allocations off the pair (adhoc_activation)
- publishing: `.github/workflows/publish.yml` rebuilds and publishes nightly, on pushes to
  main, by hand (workflow_dispatch, optionally from a dated snapshot) and on
  `repository_dispatch` events `data-updated` (`kb-updated` is still accepted but the KB is
  not a source any more). It never touches the dev DB: it restores the blob snapshot
  (below) into a Postgres service container and builds against localhost. Needs the org
  blob secret plus repo secrets `EXTRACT_TOKEN` (the proxy site token), `SITE_PASSWORD`
  (staticrypt, public site) and `ADMIN_PASSWORD` (staticrypt, admin site; no default
  anywhere, the publish fails without it).
- two sites, one build (2026-10-07): the **public site** is the tabs of its header (map,
  model + historical activations, plan, financing + donor shares, learning, media) and the
  framework pages the map opens — nothing else, and no link to anything else. Every other
  page (data admin and entry, tables, schema, reconciliation and review pages, the extra
  dashboards and explorers, the pages of pipeline frameworks the map does not show) is the
  **admin site**, published under `admin/` with its own password and its own header; it may
  link to the public site, never the reverse. The builders do not say which site a page is
  on: `page()` collects the pages and `write_site()` in `scripts/build_site.py` sorts them
  (`PUBLIC_TABS`), respells the links and stops the build if a public page carries the
  proxy token. `scripts/publish.sh` allows exactly one directory on gh-pages (`admin/`,
  encrypted pages and the two pdf.js files only) and refuses any page that is not
  encrypted. Every page carries the "internal product under development" banner.
- the **open layer** (2026-10-08, `scripts/llm_layer.py`, written by `write_site()`): the one
  thing published unencrypted, so fetch-based tools and LLMs can read the public figures while
  the pages keep their password. At the site root: `llms.txt` (the index: what the site is,
  the caveat, the counting rules, every file), `llms-full.txt` (every Markdown page in one),
  `aa-portfolio.md`, one `fw-<iso3>-<hazard>.md` per framework (every tracked pair; same
  slug as the HTML page where the map opens one), one `doc-<kb_framework>-<version>.md` per
  version page (the structured read of the framework document, without its working sections
  on sources and open questions), one `pdf-<sha256>.txt` per registered public framework
  document (the archived PDF's text, extracted with pypdf from the dev blob and cached under
  `data/framework_documents/`; `OPEN_LAYER_NO_PDF=1` skips it for a quick local build),
  `aa-<table>.json` + `.csv` (frameworks, versions, trigger-windows, windows,
  simulated-activations, activations, prearranged-funding, funding-annual, plan-split,
  partners, learning), `robots.txt`, `sitemap.xml`. Everything the database holds about the
  portfolio goes in, except people and working material: never focal points, the version
  pages' working notes (frontmatter `extra`, raw extracts, QA notes), version provenance
  notes, activation comments, partner evidence, private documents or internal learning
  documents. Regenerated by every publish (nightly, and on each push to main); the build and
  `publish.sh` both refuse an open file that carries the proxy token.
- snapshot: the dev DB is losing public network access (2026-09); only Databricks reaches
  it. `databricks.yml` defines one job, **AA Tracking Nightly** (03:30 UTC, Job Compute):
  `databricks/nightly.py` runs `scripts/export_snapshot.py`, which writes every `aa` table (parquet) plus the DDL metadata
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
- `scripts/build_site.py` — render the two password-protected GH Pages sites (public at
  the root, admin under `admin/`)
- `scripts/admin_page.py` — `admin/admin.html`: Django-admin-style CRUD over every `aa` table,
  populated live from the proxy's `/schema`; viewer = admin-site password, editor = separate
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

## Entering data without database access

Since 2026-09-30 laptops cannot reach the dev DB. Two write paths remain: the admin page
(its proxy runs in Azure), and **entry files**: JSON on the private dev blob
(`projects/ds-aa-tracking/entries/`, never in this public repo) that the nightly Databricks
job applies once each, before the snapshot (`scripts/apply_entries.py`; format in its
docstring; upload with `--upload FILE`, test against a restored local copy with `--dir`).
Every row is audited to `aa.entry_audit`; applied files are recorded in `aa.applied_entries`.

## Running

The dev DB is the single source of truth: data is entered and corrected through the
admin site (`admin/entry.html`, `admin/admin.html`) — there is no spreadsheet ingest and no KB sync any
more (`scripts/ingest.py` is the retired migration-era loader and refuses to run).
DB access via `ocha-stratus` env vars; `PGSSLMODE=require` is set automatically.

```sh
uv run python scripts/ensure_schema.py   # idempotent: create missing tables, additive migrations, views
uv run python scripts/import_kb_pages.py # one-off (done 2026-09-28): KB pages → aa.version_page
uv run python scripts/build_site.py      # needs graphviz (`brew install graphviz`) for the ERD
bash scripts/publish.sh                  # build → encrypt → gh-pages; needs ADMIN_PASSWORD (SKIP_BUILD=1 reuses the build, DRY_RUN=1 stops before the commit)
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
