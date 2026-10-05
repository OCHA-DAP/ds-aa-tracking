# Full read of older framework versions — extraction spec (2026-10-05)

How to use: the reads are entry data and stay out of git (this repo is public): one
`<kb>__<version>.json` + `.md` per framework version in a private folder (copies of the
2026-10-05 pass: ~/OCHA/data/aa_tracking/docreads/2026-10-05/), turned into an entries file by
`scripts/docread_to_entries.py DIR --out entries.json --summary summary.json` and applied with
`scripts/apply_entries.py`.

The AA tracking database (`aa` schema) is the authoritative record of OCHA's anticipatory-action
frameworks. Older framework versions were only skimmed; the recent ones were read in full. Your
job: read each assigned version's framework document **completely and carefully** — every page,
every table, every annex — and record every value it states, so the older versions are as
complete in the database as the recent ones. Nothing is written to any database by you: you write
one JSON file per version into this folder; the lead turns them into database rows after review.

## Where the documents are
- Full-text extraction of each PDF: `~/OCHA/repos/ds-knowledge-base/raw/frameworks/<kb>/<version>.txt`
  (plus `<version>.captions.txt` for figure captions where present).
- The PDF itself: `~/OCHA/repos/ds-knowledge-base/raw/.pdf-cache/<kb>/<version>.pdf`. **Open the PDF
  pages that hold tables** (budget, trigger, backtest, targeting tables) with the Read tool
  (`pages` parameter, ≤ 20 pages per call): text extraction often scrambles tables. Never guess a
  table cell from scrambled text — look at the page.
- The current KB page for the version (often a stub): `~/OCHA/repos/ds-knowledge-base/frameworks/<kb>/<version>.md`,
  and the folder's other versions (the newest pages show the depth expected).
- Page template / field definitions: `~/OCHA/repos/ds-knowledge-base/frameworks/_TEMPLATE.md`.
  Read it: the `frontmatter` you produce uses exactly its keys and rules.
- Internal drafts and notes (only where no published document exists):
  `~/OCHA/repos/ds-knowledge-base-internal/drive/extracts/CERF Anticipatory Action/…`
- What the DB holds today for the version: `version_inventory.txt` in this folder.

## Rules
1. **Stated values only.** Every number you record carries the page number and a verbatim quote
   (≤ 200 chars) in `evidence`. Never impute, round, convert or sum what the doc does not sum.
   Alternative scenarios (only one draws per event) are not added up. A total the doc states is
   recorded as stated even if its parts don't add up — flag the mismatch in `issues`.
2. **Version identity first.** Confirm the document is the version you were given (title, date,
   signature/endorsement date). If the cached file is a different version (e.g. a later revision
   cached under an older date), say so in `identity` and extract it under the version it really
   is, or stop and report — do not silently attribute values to the wrong version.
3. **Currency.** USD as stated. If the doc states another currency, keep the amount and currency
   in the row (`currency`), and set `amount_usd` only if the doc itself gives the USD figure.
4. **Funds.** `fund` is the doc's own label (CERF, the country fund's acronym e.g. AHF/EHF/SHF/YHF/
   NHF/SSHF, a regional fund, an agency's own money). Co-financing (money beyond the pre-arranged
   CERF / country / regional fund envelope: agency top-ups, government, NGOs, other donors) is
   `kind: cofinancing` with `financier` set.
5. **Windows.** One row per distinct activation window/trigger component (template's counting
   rule). Use the doc's own window names. Each funding row names its window when the doc ties
   money to a window.
6. **Backtest / historical analysis.** If the doc lists the years (or events/storms) in which the
   trigger would have activated in its historical analysis, record each as a
   `simulated_activations` row with its window, and record the analysed period
   (`analysis_start`/`analysis_end`) per window. Only what the doc states — a return period
   alone is not a list of years. Storm names / dates go in `event_label` / `event_date`.
7. **Dates.** `valid_from` = the endorsement / approval / signature date of THIS version as the doc
   or its cover states it (else the doc date, and say so). `valid_until` ONLY when the document
   states an end of validity/coverage; set `framework_version.valid_until_basis` to `stated`. If you
   can only infer an end (e.g. CERF's two-years-from-approval rule, "for the 2023 season"), leave
   `valid_until` null, put your inference in `framework_version.valid_until_inferred` and set
   `valid_until_basis` to `inferred-cerf-2yr` or `inferred-other`, with the reasoning in `issues`.
8. **People.** Total people targeted, and per window / per agency where stated.
8b. **Short fields.** `endorsed_by` is just who (≤ 80 chars, e.g. "HCT and ERC"); the quote goes in
   `evidence`. Keep the document's own window names, and always give `frontmatter.extra.window_name_map`
   mapping them to the window names on the NEWEST page of the folder (null where no counterpart).
8c. **Traps seen in the pilot.** `.captions.txt` can be wrong (rows mixed up, wrong counts) — read
   table and chart pages as images. Framework docs sometimes carry text copied from another
   country's framework (names of other countries' agencies/institutions) — don't record those.
9. **Mandatory fields** (these decide the year-by-year money on the site): `framework_version.valid_from`,
   `valid_until` + `valid_until_basis` (rule 7), `prearranged_usd_doc` (the version's total
   pre-arranged envelope, as stated), `frontmatter.funding_by_source` and `frontmatter.all_in`
   (true = one envelope released on any trigger; false = each window has its own budget). If the doc truly doesn't state one, set null AND
   explain in `not_in_doc` what you found instead.
10. **Envelope vs breakdown.** Give the envelope per window and fund when the doc states it
   (`funding_rows` with agency and sector null), and the agency / sector breakdown as separate rows.
   If the doc only states agency rows, record those; don't add up totals yourself.
11. **Storm backtests.** One `simulated_activations` row per window per YEAR; several storms in the
   same year → one row with all storm names in `event_label` ("ODETTE; RAI") and `event_date` null.
12. **Source quality.** Set top-level `source_quality`: `published-final` (the endorsed published
   framework), `draft` (an unpublished/working draft), or `secondary` (a lessons report, learning page,
   plan summary, technical note — not the framework itself).
13. **Be complete.** Read every section: context, trigger, pre-arranged activities by sector and
   agency, budget tables, targeting, timelines/lead times, monitoring/calendar, partners and
   coordination, annexes. If a field genuinely isn't in the doc, leave it null — and say in
   `not_in_doc` which important fields were looked for and not found.

## Output: one file per version, `<kb>__<version>.json` in this folder
```json
{
  "kb_framework": "tcd-drought", "version": "2022-10-24",
  "countries": ["TCD"], "hazard": "drought",
  "identity": {"doc_title": "...", "doc_date": "YYYY-MM-DD", "matches_version": true, "note": "..."},
  "sources_read": [{"path": "...", "pages": "all" , "what": "text extract"}, {"path": "...pdf", "pages": "12-15", "what": "budget table"}],
  "framework_version": {"valid_from": "YYYY-MM-DD|null", "valid_until": "YYYY|YYYY-MM|YYYY-MM-DD|null",
                        "valid_until_basis": "stated|inferred-cerf-2yr|inferred-other|none", "valid_until_inferred": "YYYY…|null",
                        "endorsed_by": "who endorsed/approved, as stated|null",
                        "prearranged_usd_doc": 0, "window_rollup": "all_in|additive|exclusive|null",
                        "supersedes": "previous version label|null", "doc_title": "..."},
  "frontmatter": { "...every _TEMPLATE.md key that the doc informs: admin_level, geographic_scope, data_sources, trigger_facets, monitoring_period, all_in, valid_until, prearranged_funding_usd, funding_by_source, funding_by_sector, funding_by_agency, funding_rows, cofinancing_usd, cofinancing_sources, implementing_agencies, target_people, languages, framework_doc_date, activations, extra": "..." },
  "windows": [{"window_name": "...", "basis": "forecast|observational|mixed", "indicator": "...", "threshold": "...",
               "lead_time": "...", "issued_months": [..], "return_period": "as stated|null", "probability": "as stated|null",
               "allocation_usd": 0, "people_targeted": 0, "analysis_start": 0, "analysis_end": 0}],
  "funding_rows": [{"window": "|null", "kind": "prearranged|cofinancing", "fund": "CERF|...|null", "financier": "|null",
                    "agency": "|null", "sector": "|null", "amount_usd": 0, "currency": "USD", "page": 0}],
  "simulated_activations": [{"window": "...", "event_year": 0, "event_date": "YYYY-MM-DD|null", "event_label": "|null", "page": 0}],
  "partners": [{"name": "...", "acronym": "|null", "org_type": "UN|INGO|NNGO|government|Red Cross|other", "roles": "..."}],
  "evidence": [{"field": "path.to.value", "value": "...", "page": 0, "quote": "verbatim"}],
  "issues": ["mismatches, ambiguities, things the lead must decide"],
  "not_in_doc": ["fields looked for and not found"],
  "source_quality": "published-final|draft|secondary",
  "body_md_file": "<kb>__<version>.md"
}
```
Write the page body to `<kb>__<version>.md` beside the JSON (NOT inside the JSON): the full
KB-style page body under the template headings (Summary, Method, Trigger logic, Trigger windows
table, Sources & repo completeness, Monitoring, Historical activations, Key decisions & rationale,
Changes from previous version, Open questions) — as thorough as the newest pages in the folder.

Write each version's two files AS SOON AS that version is done (don't batch versions). Keep tool
calls short (read the text extract in chunks of ~400 lines; ≤ 20 PDF pages per Read); long silent
steps have stalled agents before. Write valid JSON (a short Python snippet with json.dump is easiest). When done, run
`python3 -c "import json,sys; json.load(open(sys.argv[1]))" <file>` on each file.

## Report back (short)
Per version: identity ok?, envelope total and by fund, number of windows / funding rows /
simulated activations, and the issues the lead must decide. No need to repeat the JSON.
