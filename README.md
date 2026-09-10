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
  sector-level pre-arranged budgets
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
- `src/ds_aa_tracking/schema.py` — DDL (tables + views), all in schema `aa`
- `scripts/ingest.py` — parse → crosswalk to KB → full-refresh load (dev DB)
- `scripts/build_site.py` — render the password-protected GH Pages review site
- `scripts/admin_page.py` — `admin.html`: Django-admin-style CRUD over every `aa` table,
  populated live from the proxy's `/schema`; viewer = site password, editor = separate
  token prompted for in the browser (never embedded). Supersedes the tracking-tables tab.
- `proxy/server.js` — the one server: PDF extraction, framework entry, and generic
  `/schema` `/rows` `/distinct` `/save` `/delete` for the admin page; every field change is
  audited to `aa.entry_audit`; KB-loader and OneGMS-mirror tables are read-only
- `scripts/dashboards.py` — dashboards, per-framework pages, explorer, entry forms
- `scripts/landing.py` — landing map: zoom to a country, subnational scope per framework
  version (KB `geographic_scope` names matched to CODAB boundaries; one
  `adm-<ISO3>.json` per country, CODAB layers cached under `data/codab/`)

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

The proxy (`proxy/`) runs as Azure Web App `chd-ds-aa-extract`; app settings hold the
Anthropic key, the DB write login, `SITE_TOKEN` (viewer) and `EDITOR_TOKEN` (editor).
Redeploy with `az webapp deploy --type zip` from a zip of `proxy/`.
