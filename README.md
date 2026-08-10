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

## Running

Source workbooks are read from `AA_TRACKING_DIR` (not committed). DB access via
`ocha-stratus` env vars; `PGSSLMODE=require` is set automatically.

```sh
uv run python scripts/ingest.py
uv run python scripts/build_site.py   # needs graphviz (`brew install graphviz`) for the ERD
```
