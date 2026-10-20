# French and Spanish versions of the public site

The public site shows in English, French or Spanish; the **EN · FR · ES** switch at the right
of the header picks the language, and the browser keeps the choice for the next visit (and
for the team's other AA pages, which share it). The mechanism is the team's
(ds-knowledge-base decision D86, `docs/I18N.md`), copied into `scripts/site_i18n.py` and
extended to Spanish. The admin site stays English.

**These translations are drafts.** They were written with the KB's French glossary and the
Spanish one in [GLOSSARY.md](GLOSSARY.md) (both mined from our own framework documents),
and need a francophone and a hispanophone colleague to review them.

## What is translated

| Stage | Pages | Status |
|---|---|---|
| 1 | Header, development banner, the plain-language box on top of every tab, the **Financing** page | done (2026-10-20) |
| 2 | Map, Model, Historical activations, Plan, Learning, Media | to do: shown in English under FR / ES until then |
| 3 | The framework pages (one template for all of them) | to do |

Never translated, on purpose (KB rules): organisation and fund names, codes and acronyms;
the framework documents' own text (trigger statements, thresholds, window names quoted from
a document — several are already in French or Spanish); media captions (quoted posts); the
open data files. Numbers keep one format in every language (`$4.0M`, `36%`).

## How to review or correct a translation

`fr.json` and `es.json` map each English string (the key) to its translation. Edit the
value, never the key. Keep:

- the placeholders: `{0}`, `{1}` or `{n}`, `{years}`… stand for a number or a name filled in
  by the page, and may move within the sentence;
- the markup: `<b>…</b>`, `<i>…</i>`, `<a href=…>…</a>` stay around the matching words;
- French typography as in the KB: curly apostrophe (’), a space before `:` `;` `?` `!`.

A string that has no entry shows in English; the build lists them in
`site_build/i18n-missing.json` and says how many in its log.

## Choices the reviewers should confirm

French (KB glossary unless marked *suggestion*):

- **pre-arranged** → *pré-arrangé* (KB standard; the documents also have *préétabli*).
- **released** (money) → *débloqué*, kept apart from *décaissement* (disbursement).
- **Country and Regional Funds** → *fonds communs pays et régionaux* (*suggestion*: no document
  names the country-based pooled funds in French).
- **being updated** → *en cours de révision* (the documents say *cadre révisé*, *mise à jour*).
- **storm** (the site's family of tropical storms, cyclones, hurricanes, typhoons) → *cyclone tropical*.
- **sub-grant** → *sous-subvention* (*suggestion*: not attested); **people covered** → *personnes couvertes* (*suggestion*).

Spanish (GLOSSARY.md; only two independent Spanish documents exist — the Dry Corridor
template and Cuba — so several terms are suggestions):

- **trigger** → *disparador*; **trigger mechanism** → *mecanismo de activación*;
  **readiness** → *alistamiento* (kept apart from *preparación*, preparedness).
- **pre-arranged** → *preestablecido* / *financiación preestablecida*.
- **released** → *liberado*; **allocation / envelope** → *asignación*.
- **hazard** → *amenaza* (the documents are tied between *amenaza* and *peligro*).
- **Country and Regional Funds** → *fondos de país y regionales* (*suggestion*).
- **being updated** → *en actualización* (*suggestion*); **people covered** → *personas cubiertas* (*suggestion*);
  **sub-grant** → *subvención a socios* (*suggestion*).
- **storm** → *ciclón tropical*.

UN agency acronyms (WFP, WHO…) stay in English for now, like the other organisation names;
the reviewers may prefer the UN French / Spanish acronyms (PAM, OMS…).
