"""What every field of the open map's data means: the dictionary of aa-map-data.json (the open
layer, scripts/llm_layer.py), printed in llms.txt.

aa-map-data.json is the open map's own data, as its page embeds it (landing.OPEN_MAP: the open
copy, without the figures the open map withholds), so whatever the map shows is in it without
anyone touching the open layer. What can fall behind is this dictionary: the build warns when the
map's data carries a field described nowhere here (llm_layer._map_field_alarm), so a field added
to the map gets a line here in the same change. OMIT: fields that only draw the map (left out of
the file).
"""

# fields that only draw the map, or link to a page that is not public yet: not in the file
OMIT = {
    "country": {"bbox", "lbbox", "centroid", "dir", "has_geo"},
    "fw": {"glyph", "layer", "page"},
}

MAP_FIELDS = {
    "country": {
        "name": "the country's name",
        "region": "the OCHA region of the country",
        "area_names": "{area code: area name} of the administrative areas the map draws for the "
                      "country's frameworks (the codes in `scope.pcodes`)",
        "subgrants": "the organisations CERF's anticipatory allocations in the country were sub-granted "
                     "to, by agency: [{agency, partners: [{name, acronym, type (UN, INGO, NNGO, government, "
                     "Red Cross / Red Crescent, other), usd}]}]",
        "pre_x": "pre-arranged money of no single framework (a pooled-fund allocation for a country with "
                 "several hazards), per past year, in the shape of `hist.pre`",
        "fws": "the country's frameworks, and the pairs drawn only for non-framework allocations or "
               "technical support: one object per (country, hazard) pair, fields below",
    },
    "fw": {
        "hazard": "drought, flood, storm, cholera, plague or food_insecurity for a framework; other "
                  "hazards (locusts, for one) for a pair with non-framework allocations only; general for "
                  "technical support not tied to one hazard (see `general`)",
        "hz_label": "the hazard in words",
        "status": "the operational status the team reports (early_conversations, advanced_conversations, "
                  "under_development, active, activated_implementing, retired, ...); not the map's status",
        "status_label": "`status` in words",
        "disp": "the map's status of the pair, the one every figure counts by: active, updating (being "
                "updated) or development for a current framework; retired; pipeline (conversations only, "
                "drawn for technical support); adhoc (non-framework money only: allocations released, or money "
                "pre-arranged and not yet released, `pre_ad`). Equals `lifecycle` "
                "in aa-frameworks where the pair has a framework",
        "disp_label": "`disp` in words; for a `general` pair the page shows technical support instead",
        "layers": "the map layers the pair is drawn on: framework (current frameworks), retired, adhoc "
                  "(non-framework allocations), tech (technical support). The headline figures count "
                  "pairs on `framework` (= `map_layers` in aa-frameworks)",
        "tech": "technical support: OCHA supports coordinated anticipatory action here but neither leads "
                "the effort nor provides pre-arranged financing",
        "general": "true for technical support for anticipatory action in general, not for one hazard "
                   "(hazard `general`, shown as 'No specific hazard'): technical support only, never a "
                   "framework version or an allocation",
        "ring": "`now` when an active framework is monitored this month (the map rings it)",
        "latest": "the most recent version, of any status (= `latest_version`)",
        "current": "the version the map and the country panel open on (the most recent)",
        "in_force": "the version the tracking registry has in force",
        "versions": "every version of the framework, oldest first: fields under version",
        "activations": "every real activation on the pair, newest first: fields under activation",
        "n_act": "framework activations of the pair's current framework",
        "n_act_all": "activation records on the pair, of any kind",
        "n_adhoc": "non-framework allocations on the pair",
        "pre_ad": "money a fund has pre-arranged for the pair outside a framework and not yet released: "
                  "[{date (when it was arranged), label, fund, code (the fund's allocation, when it has one), "
                  "usd, people (targeted), until (when it ended: released, withdrawn or lapsed; blank: still "
                  "pre-arranged), fk and fs (the fund's kind and its box in the map's fund switch)}]. Never an "
                  "activation and never released money; not in `pre_now`. The map adds it to pre-arranged money "
                  "while its non-framework layer is on",
        "adhoc_cerf": "CERF allocations tagged as anticipatory on the pair outside any framework, from "
                      "CERF's records: [{code (CERF's allocation code), year, emergency, title, usd, how "
                      "(how it was matched to the pair), event, url (CERF's page), agencies, sectors, "
                      "reached, planned}]",
        "pre_now": "pre-arranged money now, all funds: what the Pre-arranged tile adds up (= "
                   "`prearranged_usd` in aa-frameworks; two activations a year: the CERF envelope counted "
                   "twice)",
        "pre_parts": "`pre_now` split: {cerf, pooled (Country and Regional Funds), version (the version "
                     "it is the envelope of), apy (activations a year counted)}; `pooled` again as cbpf "
                     "(country-based pooled funds) + rhpf (regional humanitarian pooled funds, their "
                     "country windows included), for the map's fund switch — never add them to `pooled`",
        "apy": "activations a year counted in `pre_now`, where more than one",
        "prearranged": "the registry's CERF figure of the in-force endorsed version: NOT the headline "
                       "figure, which is `pre_now`",
        "prearranged_year": "the year of `prearranged`",
        "cofin_y": "co-financing pre-arranged, per year {year: usd}; the current year is co-financing now "
                   "(= `cofinancing_usd` in aa-frameworks)",
        "covered": "people covered now (blank: no figure, or one taken from a framework document that is "
                   "not published)",
        "hist": "what the year selector shows for past years: fields under hist",
        "learning_docs": "learning products about the pair (after-action reviews, evaluations, activation "
                         "reports, research): [{id, title, url, publisher, year (of publication), type, stat "
                         "(a key statistic)}]",
    },
    "hist": {
        "sh": "the pair's status by date, [[date, status]]: a past year shows the last one before its end",
        "cov": "people covered by date, [[date, people]] (a figure from a framework document that is not "
               "published is left out)",
        "pre": "pre-arranged money per past year, {year: [usd, derived (1: carried from the version in "
               "force rather than reported for the year), activations a year counted, {cerf, cbpf, rhpf, "
               "all (no fund named)}: usd by the map's fund switch]}",
        "retired": "the pair counts as retired",
        "ret_on": "from when, derived (no retirement date is recorded): the day after its last version's "
                  "validity ended, else the first status report saying dormant or retired",
        "ret_note": "how `ret_on` was derived",
        "adhoc": "the years with non-framework allocations on the pair",
    },
    "version": {
        "v": "the version: the date of its endorsement (or of its document), or a year",
        "status": "endorsed, development (not yet endorsed) or retired",
        "valid_from": "start of validity",
        "valid_until": "end of validity (can be past)",
        "valid_until_source": "where the end of validity comes from: stated in the document, by "
                              "convention, or inherited from an earlier version",
        "dev_since": "in development since",
        "endorsed_by": "who endorsed it: the Emergency Relief Coordinator for a major version, the CERF "
                       "secretariat for a minor one",
        "supersedes": "the version it replaces",
        "superseded": "a newer endorsed version exists",
        "fully_triggered": "nothing is left to release under it",
        "doc_url": "the framework document's official page (ReliefWeb or unocha.org)",
        "doc_title": "the document's title",
        "doc_date": "the document's date",
        "prearranged_doc": "the pre-arranged envelope the document states",
        "envelope": "the version's pre-arranged envelope as recorded, all funds",
        "env_cerf": "its CERF part",
        "env_funds": "the envelope by fund: [{fund (a fund code: cerf, a country or regional pooled fund, or "
                     "all = a total not split by fund), usd}]",
        "pool_spent": "its Country or Regional Fund envelope was released by an activation",
        "cofin": "co-financing the document states",
        "cofin_sources": "who provides it, as the document says",
        "regional": "one document serves several countries (each is still its own framework)",
        "agencies": "implementing agencies",
        "target_people": "the people the document targets (blank where the document is not published and "
                         "the figure is the framework's people covered)",
        "all_in": "one trigger releases the whole envelope",
        "rollup": "how the windows' money adds up: additive, exclusive or all_in",
        "n_windows": "number of trigger windows",
        "months": "the months (1-12) the trigger is monitored",
        "months_src": "where `months` comes from: stated (in the document), inferred, calendar sheet",
        "months_note": "how the monitoring months were read from the document",
        "basis": "what the trigger reads: forecast, observational or mixed",
        "calibration": "how the trigger was calibrated",
        "indicators": "the trigger's indicators",
        "data_sources": "the data the trigger reads",
        "triggers": "the trigger table as the document states it: one object per row, under the "
                    "document's own column names (window, indicator, threshold, lead time, return period, "
                    "releases, ...)",
        "windows": "the trigger windows as recorded: [{name, basis, all_in, budget (usd), rp (the backtest's "
                   "return period, years), prob (annual activation probability), sim (simulated "
                   "activations), years (years analysed), triggered, triggered_on}]",
        "backtest": "the historical simulation of the trigger: {start, end (years analysed), in_use_from, "
                    "in_use_to (the years the version was in use: from then on only real activations "
                    "count), windows, rows [{year, label, fired (the windows that would have activated), "
                    "when, and for an event the backtest tested (aa.backtest_event): tested, na (the windows "
                    "it could not be tested on: no record), vals {window: the trigger's value for it}}], "
                    "per_event, n_after, after_note, and when events were tested: n_tested (how many, met or "
                    "not), units {window: what `vals` measures}}",
        "rp": "the overall return period the map's table shows, in years (any window activating in a year)",
        "rp_st": "the return period the document states",
        "rp_bt": "the one from the backtest",
        "rp_src": "which of the two `rp` is: stated or backtest",
        "apy": "activations a year the document allows",
        "funding": "the version's pre-arranged budget split: {src (document: the framework document; sheet: the team's "
                   "sheet), agency [{agency, fund, usd}], sector [{sector, fund, usd}], fund [{fund, usd}], "
                   "pair [{agency, sector, usd}], cofin [{from (the financier), usd}]: the document's "
                   "co-financing lines, kept out of the split}",
        "partners": "organisations the document names: [{name, acronym, group, roles (tags), parent (the UN "
                    "agency a sub-grantee works under), usd (the budget the document attaches, which can "
                    "include its own co-financing)}]",
        "partners_from": "the version whose list `partners` shows, where this one has none of its own",
        "activities": "what each organisation does under the version once the trigger is met, in a line or "
                      "two read from the version's public framework document (not the document's own "
                      "words; no amounts or counts of people): [{agency, text, sector (as the document "
                      "names it)}]",
        "activities_from": "where this version has no lines of its own: the latest version of the same "
                           "framework that has them (its lines are not repeated here)",
        "learning": "lessons the version's record lists",
        "admin_level": "the administrative level of the geographic scope",
        "scope": "the areas drawn: {pcodes, unmatched (scope entries not matched to a map area), national, "
                 "tiers [{label, pcodes, rest (a tier covering the rest of the country), whole (rest that "
                 "covers the whole country, the named areas included)}]}",
        "scope_raw": "the geographic scope as the document words it",
        "scope_tiers_raw": "the document's tiers of areas, as worded",
        "analysis_ref": "where the trigger analysis lives: repository@branch:path in the OCHA-DAP GitHub "
                        "organisation",
        "analysis_url": "its URL",
        "doc_read": "the team has a structured read of the document",
        "source": "where the version record comes from (aa-team, entered, ocha-web)",
    },
    "activation": {
        "date": "the event date, at the precision recorded (YYYY, YYYY-MM or YYYY-MM-DD)",
        "exact_date": "a second record of the activation's date; the map takes the day from it when `date` gives only the month",
        "type": "framework_aa (a framework's trigger) or adhoc_aa (a non-framework allocation)",
        "window": "the trigger window, as recorded (can be a short code of the backtest)",
        "version": "the version it activated under",
        "old": "an activation of an earlier framework that a new one replaced: a retired framework's",
        "people": "the people the activation targeted",
        "url": "a public page on the activation",
        "released": "the amount its public record states (the counted figure is the sum of `funding`)",
        "full": "a full activation (the whole envelope)",
        "funding": "the money released, per fund: fields under funding",
    },
    "funding": {
        "fund": "the fund code (see `fund_code` in the vocabulary)",
        "code": "the fund's allocation code",
        "fk": "[kind, region]: cerf, country (a country-based pooled fund), regional (a regional fund's "
              "envelope, with its region) or unrecorded",
        "fs": "the map's fund switch box the row counts under: cerf, cbpf (a country-based pooled fund) "
              "or rhpf (a regional humanitarian pooled fund; a fund not recorded: the country's one "
              "registered fund)",
        "usd": "released, net of any refund: what the tiles add up",
        "refund": "money sent back after the activation stopped",
        "prov": "entered before OCHA's grant management system recorded the allocation (an estimate)",
        "cerf_url": "CERF's public page for the allocation",
        "reached": "people reached, CERF's report",
        "interim": "summed from project reports, no final report yet",
        "planned": "the people counted while there is no report (CERF: those it plans to reach, else those "
                   "the activation targets; a Country or Regional Fund: those it targets)",
        "shared": "the allocation's people are counted on an earlier activation",
    },
}

# the headline figures (landing.tile_figures), as the map opens: `headline` in aa-map-data.json
TILE_FIELDS = {
    "n_fw": "frameworks on the current-frameworks layer", "n_ctry": "the countries they are in",
    "n_active": "of them active", "n_upd": "being updated", "n_dev": "in development",
    "pre": "pre-arranged now, all funds", "pre_cerf": "its CERF part",
    "pre_ad": "of `pre`, the money pre-arranged outside a framework and not yet released: counted only "
              "while the non-framework layer is on (0 in `headline`; `headline_non_framework` has it)",
    "n_pre_ad": "the records `pre_ad` adds up", "n_pre_ad_ctry": "the countries they are in",
    "pre_pooled": "its Country and Regional Funds part", "pre_all": "its part not split by fund",
    "pre_cbpf": "of the Country and Regional Funds part, the country-based pooled funds'",
    "pre_rhpf": "of the Country and Regional Funds part, the regional humanitarian pooled funds'",
    "apy": "[activations a year, country, hazard, hazard in words] of the frameworks counting more than one",
    "cofin": "co-financing pre-arranged now", "n_cofin": "frameworks with a co-financing figure",
    "covered": "people covered now", "n_cov": "frameworks with a figure",
    "n_act": "framework activations this year", "released": "money they released, net of refunds",
    "released_cerf": "its CERF part", "released_cbpf": "its country-based pooled funds' part",
    "released_rhpf": "its regional humanitarian pooled funds' part", "refund": "money returned after activations stopped",
    "prov": "money estimated, not yet in OCHA's grant management system",
    "n_nousd": "activations with no amount recorded",
    "reached": "people reached, CERF's reports", "n_rep": "CERF allocations with a report",
    "n_interim": "of them interim", "targeted": "people planned or targeted, CERF allocations awaiting reports",
    "n_tgt": "those allocations", "n_cerf": "CERF allocations",
    "ptargeted": "people targeted by Country and Regional Fund allocations", "n_ptgt": "those allocations",
    "n_pool": "Country and Regional Fund allocations",
}
