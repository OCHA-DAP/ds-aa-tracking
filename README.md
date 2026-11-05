# ds-aa-tracking

Single authoritative tracking system for OCHA's anticipatory action (AA) portfolio,
superseding the team-member spreadsheets it was seeded from.

This repo owns every table in the dev Postgres `aa` schema except the CERF / CBPF OneGMS
mirrors (`ds-cerf-supplement`), the backtest tables included (see "AA management" below).
It holds:

- **framework lifecycle**: registry of every (country, hazard) framework incl. the
  pipeline (early conversations → active → dormant/expired), status snapshots over time,
  focal points, trigger-window calendar
- **funding**: pre-arranged amounts per year and fund source, co-financing,
  sector-level pre-arranged budgets, hand-entered build earmarks (`aa.build_contribution`)
- **activations**: the full activation-event record 2020→ (framework + ad-hoc, AA + EA,
  CERF + country/regional funds), tied to the CERF mirror's allocations
- **reporting**: which frameworks count toward which external reports (A-Hub, UK BCs,
  SG/CERF/OCHA annual reports, SF KPI, CPC), GHO/HNRP inclusion, people covered
- **CERF depth**: subgrants to implementing partners (imported once from the CERF
  secretariat's workbooks; CERF's feeds publish none), project-level CVA and markers, application-level beneficiary demographics, final-report narratives,
  emergency-type retags, CIRV

Decisions about the site (who made them, when, why, and whether they still stand) are logged in [`docs/DECISIONS.md`](docs/DECISIONS.md).

The data science team's knowledge base, [`ds-knowledge-base`](https://github.com/OCHA-DAP/ds-knowledge-base),
covers a much wider range of topics and goes into more technical detail. It is not a source
for OCHA's AA reporting: for the AA portfolio's figures and statuses, use this database and
its site.

## The record (since 2026-09-28)

This system is **authoritative**. Each framework version's page (scope, monitoring months,
trigger facets, data sources, agencies, the "Trigger windows" table, the page body) was
imported once into `aa.version_page` on 2026-09-28 and is edited here; the site build reads
only the database snapshot.

**AA management (since 2026-10-05).** Every AA table is owned here (DDL and views in
`schema.py`; the loaders that used to write some of them from elsewhere are retired): the
**backtests** — `window`, `simulated_activation`, `version_performance_reported` — are
edited here, and `funding_breakdown`, `actual_activation`, `activation_allocation` are the
frozen record from before 2026-10-05 (superseded by `window_funding`, `window_activation`,
`activation_funding`). This database is the record
of every AA table; backtests are edited freely and corrected as errors are found
(`v_trk_backtest_check` lists the rows that break a rule). Sealing a backtest once it has
been checked against the endorsed document is a follow-up, not yet implemented.

Two more DB-first tables came with the switch on 2026-09-28: `aa.learning_document` (the AA Compendium of
Available Resources, Sept 2026, plus the website to-add list; `scripts/import_learning.py`;
`internal` rows never render) and `aa.framework_partner` (organisations named in the
endorsed framework documents, extracted once with `scripts/import_partners.py`, curated in
the admin page). Sector/agency splits are read through `aa.v_window_funding_split` (one
source per version, so a budget table can never double-count). Snapshots dated 31 December
are kept forever (the year-end official state, for the map's time view).

## Layout

- `src/ds_aa_tracking/schema.py` — DDL (tables + views), all in schema `aa`; hierarchy
  country_hazard → framework_version → window → {window_activation, simulated_activation,
  window_funding}; ad hoc / early-action allocations off the pair (adhoc_activation)
- publishing: `.github/workflows/publish.yml` rebuilds and publishes nightly, on pushes to
  main, by hand (workflow_dispatch, optionally from a dated snapshot) and on
  `repository_dispatch` events `data-updated` (the older name `kb-updated` is still
  accepted). It never touches the dev DB: it restores the blob snapshot
  (below) into a Postgres service container and builds against localhost. Needs the org
  blob secret plus repo secrets `EXTRACT_TOKEN` (the proxy site token), `SITE_PASSWORD`
  (staticrypt, development site) and `ADMIN_PASSWORD` (staticrypt, admin site; no default
  anywhere, the publish fails without it).
- **Publish changes** (D164): an admin-page edit is in the database at once but on the site
  only after the next publish from a fresh copy. The admin page's bar says which copy the
  site shows; its button (editors) has the proxy start `publish.yml` with `fresh_snapshot`,
  which runs the Databricks job first (`scripts/fresh_snapshot.py`) — about 15 minutes to the
  live site. Needs the proxy app setting `GITHUB_TOKEN` (fine-grained, this repo only,
  Actions read and write: it can start, read and cancel this repo's workflow runs; it expires
  within a year, after which the bar shows a GitHub error until it is replaced; unset hides
  the button), and for the workflow the repo variables
  `DATABRICKS_HOST` + `DATABRICKS_CLIENT_ID` and secret `DATABRICKS_CLIENT_SECRET` of the
  service principal `ds-aa-tracking-publish`, which `databricks.yml` lets run the job.
- **open site and development site** (D169, 2026-11-01): the site's address
  (https://ocha-dap.github.io/ds-aa-tracking/) is the **open site**, no password: the map,
  the Definitions page and the accessibility statement (`build_site.OPEN_PAGES`, the map links
  to both), and in place of every other public page a "Coming soon" page (a drawn outline, blurred,
  nothing of the page itself) linking to that page on the **development site**, `dev/`: every
  public page, behind `SITE_PASSWORD` (the old site's password). The open map leaves out the
  figures it may not show (`landing.withheld_on_open_map`: a people-covered figure from a
  framework document none of whose files is registered as public); the development map shows
  them. `site_build/` is laid out as published: the open site at its top, `dev/`, `admin/`.
  `publish.sh` serves a top-level page plain only if the build marked it for the open site
  (`OPEN_META`), and apart from the pages of its own `OPEN_PAGES` list (the same as the
  build's) only a "Coming soon" page, and a small one; everything under
  `dev/` and `admin/` must be encrypted. The admin site links to the development site.
- two sites, one build (2026-10-07): the **public site** is the tabs of its header (map,
  model + historical activations, plan, financing, learning, media) and the
  framework pages the map opens — nothing else, and no link to anything else. Every other
  page (data admin and entry, the schema, the pages of pipeline frameworks the map does not
  show) is the
  **admin site**, published under `admin/` with its own password and its own header; it may
  link to the public site, never the reverse. The builders do not say which site a page is
  on: `page()` collects the pages and `write_site()` in `scripts/build_site.py` sorts them
  (`PUBLIC_TABS`), respells the links and stops the build if a public page carries the
  proxy token. A public page never shows a database name (`aa.<table>`, `v_<view>`) or a raw
  code (a status, hazard, event type, report or fund code: words only, `dashboards.code_words`):
  `write_site()` cleans what slips through (owner, 2026-10-28: auto-remove) — a name is removed, a
  code replaced by its words — and prints a `::warning::` per page cleaned in the publish run, so it
  gets fixed at the source; `AA_SITE_GUARD=strict` stops the build instead (local checks).
  A public page can be **unlisted** (`UNLISTED_TABS`): same password as the
  tabs, but no header link and no link from any page (the build stops if one appears), so
  only people given its address find it. `scripts/publish.sh` allows three directories in
  the published site (`admin/`: encrypted pages and the two pdf.js files; `dev/`: encrypted pages, the
  map's geometry and the vendored scripts; `dev/media/`: the Media page's photos) and refuses
  a page under them that is not encrypted. Every page carries the "internal product under
  development" banner; the development site's adds that it is the development version.
- the **open layer** (`scripts/llm_layer.py`, written by `write_site()`; D66, D181): plain
  Markdown and tables beside the open site's pages, so fetch-based tools and LLMs can read the
  open figures. It carries only the data of the pages served without a password
  (`OPEN_PAGES`; owner, 2026-11-02: "only configure it to put the data live for the one page that
  is actually going live … the map one. we will put the other data live later"): each file has a
  home page (`llm_layer.HOME`) and is written only while that page is open, so opening a page
  puts its data live with it. Today, the map: at the site root `llms.txt` (the index: what the
  site is, the caveat, the counting rules, every file, the dictionary of the map's data,
  `scripts/open_map_fields.py`), `aa-map.md` (the map's headline figures as it opens with the
  map's own notes on them, its frameworks, this year's activations), `aa-map-data.json` (the open
  map's own data as its page embeds it, minus the drawing: whatever the map shows, including the
  country panels and the year selector's past years), `aa-<table>.json` + `.csv` (frameworks,
  versions, activations, prearranged-funding, cofinancing, funds: the frameworks the open map
  shows), `robots.txt` and `sitemap.xml` (these files and the open pages). The figures are the
  open map's own (`landing.OPEN_MAP`: its tiles, its people reached or targeted, its co-financing
  now) and so is its withholding: a people-covered figure from an unpublished framework document
  stays out (`landing.withheld_on_open_map`), and the build stops if a file still carries one.
  Kept in step on every publish, as the data and the site change: `figure_check.open_layer()`
  recomputes every headline figure and each framework's figures from the files as written and
  compares them with the open map's (warnings in the publish run's summary; `llms.txt` states the
  result), the build warns when the map's data gains a field `open_map_fields.py` does not describe
  or the map a tile `aa-map.md` does not state, and when a page is opened whose data no file carries.
  Held until their pages open, code kept but nothing written: the framework pages' Markdown
  (`fw-<iso3>-<hazard>.md`), the structured reads of the framework documents
  (`doc-<framework>-<version>.md`), their full texts (`pdf-<sha256>.txt`, pypdf, cached under
  `data/framework_documents/`), `llms-full.txt`, `aa-portfolio.md` and the Financing,
  Activities, Learning, Model and historical-activation tables. Never published, whatever is
  open: focal points, the version pages' working notes (frontmatter `extra`, raw extracts, QA
  notes), version provenance notes, activation comments, partner evidence, private documents,
  internal learning documents. Regenerated by every publish; the build and `publish.sh` both
  refuse an open file that carries the proxy token, and the build warns (stops under
  `AA_SITE_GUARD=strict`) if a file names another file it did not write. The open map's head
  points at `llms.txt` (`rel="help"`) and `aa-map.md` (`rel="alternate"`), and the open pages say
  it in their visible text, on the line under the title (`build_site.LLMS_LINE`): a tool that
  reads a page as text drops the head's links (a web-fetch reader never found the files,
  2026-11-03). The open map's "Download CSV" links to `aa-frameworks.csv`; a click still
  downloads the table as the map shows it. GitHub Pages serves
  the site under `/ds-aa-tracking/`, so `robots.txt` and `llms.txt` are not at the host root
  where a crawler looks by convention: discovery relies on those links and on links from
  elsewhere (this README: https://ocha-dap.github.io/ds-aa-tracking/llms.txt).
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
- `src/ds_aa_tracking/migrations.py` — the status collapse and window_status seeding (run by ensure_schema)
- `scripts/drop_leftovers.py` — one-off (D168): archives, then drops what was left from
  building the tracker (the zz_legacy tables, version_match, the raw page YAML, old views) and
  renames the source labels that named people
- `scripts/build_site.py` — render the GH Pages sites: the open site at the root (the map,
  Definitions, Accessibility, and "Coming soon" pages), the development site under `dev/` and the admin site under
  `admin/` (both password-protected)
- `scripts/admin_page.py` — `admin/admin.html`: Django-admin-style CRUD over every `aa` table,
  populated live from the proxy's `/schema`; viewer = admin-site password, editor = separate
  token prompted for in the browser (never embedded). Supersedes the tracking-tables tab.
- `proxy/server.js` — the one server: PDF extraction, framework entry, and generic
  `/schema` `/rows` `/distinct` `/save` `/delete` for the admin page; every field change is
  audited to `aa.entry_audit`; the frozen tables from before 2026-10-05 and the mirrors are read-only
- `proxy/mirror_tables.json` — the mirrors (D154): every table and view ds-cerf-supplement
  copies into `aa` every day (CERF OneGMS feeds, CBPF OData API, its storm and drought
  matches), each with what it is copied from. The one list: the proxy refuses writes to them,
  the admin page labels them "Mirror — read-only" and never offers to edit them,
  `scripts/apply_entries.py` fails a file that touches one, and the publish run warns
  (`::warning::`) about any `aa` table neither `schema.py` defines nor this file lists. Any
  `cbpf_` table counts as a mirror before it is listed. Python reads it through
  `src/ds_aa_tracking/mirrors.py`; it ships in the proxy's zip, so a change to it needs a
  proxy redeploy (the admin page's labels follow at the next publish)
- `scripts/dashboards.py` — dashboards, per-framework pages, explorer, entry forms
- `scripts/page_model.py` — the Model page. Its trigger timelines ("How much warning do the
  triggers give?") draw `aa.trigger_timeline`: one panel per hazard on its own clock (hours to
  landfall, days to the flood peak, drought months against the rainy season, with a
  season / calendar switch), rows grouped by framework, current version only. The rows are
  hand-entered from the framework documents through an entries file (`op: replace` per
  version) — never committed here; until the nightly's one-off `--ensure-schema` run creates
  the table, every framework reads "trigger windows not recorded yet"
- `scripts/page_media.py` — the Media page: the folder "AA visuals" (OCHA-HFSA SharePoint,
  "(08) External communication"; a Google Drive folder until that was deleted in Oct 2026) as
  it was gathered (photos by country, the social posts of the folder's catalogue), read from
  `site_src/media.json`. A photo is shown from two renditions published under `dev/media/`
  (public files, as the Drive renditions were); the page links to neither the
  folder nor the originals.
  `scripts/sync_media.py --from DIR` (DIR = the folder downloaded from SharePoint and
  unzipped) archives every file on the dev blob (`projects/ds-aa-tracking/raw/media/`), makes
  the renditions once (`…/processed/media/web/`) and rewrites the manifest; it is run by hand
  and its diff is read before it is committed (not part of the nightly build). `publish.sh`
  fetches the renditions with `--fetch`. Not curated yet: no selection, captions or credits.
  A post the team adds after the catalogue goes in `site_src/media_posts_added.json` (one
  per line, same fields as the manifest's posts, plus `added`); a sync never writes it (D173)
- `scripts/page_climate.py` — two unlisted pages that link only to each other.
  `climate-adaptation.html`: CERF projects coded by hand against climate-adaptation indicators
  (a gate question on climate risk, and activity indicators in seven areas), filterable by
  indicator. `climate-coding-accuracy.html`: how closely automated passes (coders named
  `model-*`, listed in `RUNS`) reproduce the hand coding — kappa, precision and recall per
  run, per indicator, and project by project with the model's evidence quotes. Codes in `aa.cerf_climate_coding`
  (project × indicator × coder), project facts from the CERF mirror. A coder's workbook
  becomes an entry file with `scripts/import_climate_coding.py WORKBOOK --coder NAME --out
  FILE.json` (it checks every header before reading), then `apply_entries.py --upload` —
  only once the nightly's one-off `--ensure-schema` run has created the table.
  The workbooks and the proposals they were coded from never go in git
- `scripts/mock_unocha.py` — the mock-up of the public site embedded in
  https://www.unocha.org/anticipatory-action (unlisted, on the development site under its
  password): `dev/mock-unocha.html`
  and a `mock-unocha-<page>` twin of every page reachable from the map, OCHA's page with ours
  under its photo in place of their section tabs, our CSS scoped to `.aa-embed`. Run by
  `publish.sh` after the build. OCHA's page is a committed snapshot (`site_src/unocha-shell.html`,
  `site_src/unocha.css`), refreshed by hand with `scripts/snapshot_unocha.py`
- `scripts/landing.py` — landing map (base: Natural Earth 1:50m simplified as one topology so
  borders stay shared; zoom: FieldMaps edge-matched COD-AB for every country in view): zoom
  to a country, subnational scope per framework
  version (`geographic_scope` names matched to FieldMaps edge-matched COD-AB boundaries; one
  `adm-<ISO3>.json` per country with its neighbours, simplified as one shared-edge topology; layers cached under `data/fieldmaps/`)
  Scope tiers: inside a block-form `geographic_scope`, a comment line on its own names a tier
  for the items below it (`# riverine window — …`), and an item like `Non-endemic provinces
  (all other)` is a rest-of-country tier; tiers render as shades of the hazard colour

## Entering data without database access

Since 2026-09-30 laptops cannot reach the dev DB. Two write paths remain: the admin page
(its proxy runs in Azure), and **entry files**: JSON on the private dev blob
(`projects/ds-aa-tracking/entries/`, never in this public repo) that the nightly Databricks
job applies once each, before the snapshot (`scripts/apply_entries.py`; format in its
docstring; upload with `--upload FILE`, test against a restored local copy with `--dir`;
`--dry-run` applies each file in its transaction, lets the database check it, and rolls back).
Every row is audited to `aa.entry_audit`; applied files are recorded in `aa.applied_entries`.
Besides upserts, an item can `"delete"` one row by its full key or `"op": "replace"` a
version's rows in a table (a re-run backtest). A file that fails stays pending and never
blocks the others.

**Money released before OneGMS shows it, and money refunded.** A CERF amount that went out
before OneGMS records the allocation is an `aa.activation_funding` row with
`match_method: "provisional"` and no `allocation_code` (the activation's key, `fund_code`
`cerf`, the amount). The nightly job (`scripts/resolve_provisional.py`, after the entries)
replaces it with OneGMS's code and approved amount once the allocation appears (rules in its
docstring), and audits the change; when two allocations could fit, or none has come 120 days
on, it warns and leaves the choice to a person. Money
an activation sent back after it was paused or stopped is an `aa.activation_refund` row
(the activation's key, the fund, the allocation when known, the amount): every page counts
released money net of it.

## Running

The dev DB is the single source of truth: data is entered and corrected through the
admin site (`admin/entry.html`, `admin/admin.html`) — there is no spreadsheet ingest and no sync from elsewhere.
DB access via `ocha-stratus` env vars; `PGSSLMODE=require` is set automatically.

```sh
uv run python scripts/ensure_schema.py   # idempotent: create missing tables, additive migrations, views
uv run python scripts/build_site.py      # needs graphviz (`brew install graphviz`) for the ERD
bash scripts/publish.sh                  # build → encrypt → stage in _site/ → check; needs ADMIN_PASSWORD (SKIP_BUILD=1 reuses the build); never deploys
gh workflow run publish.yml              # put the site online: the workflow builds, uploads _site/ as the Pages artifact and deploys it
```

The site is deployed as a GitHub Pages artifact (Pages in workflow mode, D195): the published
pages are never committed, so the repository holds code only. Only `main` may deploy (the
github-pages environment's branch policy). To go back to an earlier site: a code change is
reverted on `main` (the merge publishes it); earlier data is published with that day's snapshot,
`gh workflow run publish.yml -f snapshot=YYYY-MM-DD` (dated snapshots are kept 30 days). To publish
again, start a new run rather than re-running an old one (its site package is kept one day).

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
Anthropic key, the DB write login, `SITE_TOKEN` (viewer), `EDITOR_TOKEN` (editor),
`GITHUB_TOKEN` (Publish changes) and `COUNT_DB_UID` / `COUNT_DB_PW`: the login of the open
site's page counts (D197: `POST /hit`, the one endpoint without a token, adds 1 to a day's row of
`aa.page_count`; that login can only read and add to that table; unset, the write login is used).
Redeploy with `az webapp deploy -g IMB-CHD-DataScience-EastUS2 -n chd-ds-aa-extract --type zip --src-path <zip>` from a zip of `proxy/` (`server.js`, `package.json`
and `mirror_tables.json`: the proxy will not start without the mirror list).
