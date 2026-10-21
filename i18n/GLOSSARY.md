# AA tracking site — Spanish glossary and French gaps (mined from our framework documents)

Mined 2026-10-20 from our framework documents, under the KB's rule (D86, `docs/I18N.md`): terminology is doc-sourced, not invented. The French part covers only the terms the KB's French glossary lacks; the translations in `fr.json` / `es.json` follow both.

## How to read this file

**Sources (Spanish).** Only four Spanish-bodied extracts exist anywhere in the corpus, and they come from **two independent sources**:

| short | file | what it is |
|---|---|---|
| GTM | `ds-knowledge-base/raw/frameworks/lac-dry-corridor/2026-03-13.txt` (same text as `site_build/pdf-ae335974….txt`) | Guatemala drought v3, EN executive summary + ES body |
| HND | `ds-aa-tracking/site_build/pdf-6b6ca85f….txt` | Honduras drought 2026-03-13, same template as GTM |
| SLV | `ds-aa-tracking/site_build/pdf-0df2b5d0….txt` | El Salvador drought 2026-03-13, same template as GTM |
| CUB | `ds-knowledge-base/raw/frameworks/cub-hurricanes/2025-08-26.txt` (same text as `site_build/pdf-206ad3ea….txt`) | Cuba hurricanes v1, EN executive summary + ES body + bilingual ES/EN message drafts (Annex 3) |

- **"DC×3" = one source.** GTM, HND and SLV share one template and differ only in country-specific sentences. Any hit found only in GTM/HND/SLV is one source, even when it shows "3 docs". A term in all four docs is in both sources.
- `lac-dry-corridor/2025-02.txt` is **English** (1 Spanish-looking hit in 30 KB), not Spanish. The other Dry Corridor PDFs in `site_build` (2024-03-22 GTM/HND/SLV, 2025-02 combined) are English too. **No Spanish text exists** for Nicaragua (its PDF was never recovered; its docread is English), Colombia or Venezuela. The docreads under `~/OCHA/data/aa_tracking/docreads` are English summaries. The `*.captions.txt` files are machine-written English and were not used.
- Secondary source: the live Cuba monitoring e-mails, `ds-aa-cub-hurricanes/src/email/` (templates + `send_emails.py`). They are ours and Spanish/English, and are cited as "CUB e-mails". They work the way the HTI e-mails did for the French glossary.

**Sources (French).** 20 extracts under `raw/frameworks/` (tcd-drought ×2, tcd-flooding ×2, ner-drought ×3, ner-flooding ×2, bfa-drought ×4, bfa-flooding, cod-infectious-disease ×3, mdg-storms, mrt-drought, hti-hurricanes). The French `site_build/pdf-*.txt` files are these same versions. Counts are inflated by near-duplicates: ner-drought 2022-01-05 and 2022-08-04 are nearly identical, and the four bfa-drought versions share boilerplate.

**Method.** I collapsed whitespace (so phrases broken across PDF lines still match) and used case-insensitive regex. Accents are matched exactly; both accented and unaccented forms were tried. **count / docs** = total hits / number of documents with at least one hit. Line numbers (l.) refer to the files above. Quotes are taken from the text as extracted.

**Evidence tier** (last column):
- **A** = exact bilingual pair in one document (the CUB Annex 3 messages, ES l.1971–2068 / EN l.2003–2318).
- **B** = the EN executive summary parallels the ES body of the same document.
- **C** = monolingual attestation; the English sense is inferred.
- **NOT ATTESTED** = no document has the term. Anything after "**Suggestion:**" is mine, not from the docs.

---

## 1. Spanish

### 1.1 Core AA vocabulary

| EN | recommended | count / docs | variants seen (counts) | source (file + quote) | tier · notes / **Suggestion** |
|---|---|---|---|---|---|
| anticipatory action | **acción anticipatoria** (pl. *acciones anticipatorias*) | 274 / 4 (DC×3+CUB) | *acción(es) anticipada(s)* 6/3 (DC Annex 1 boilerplate only); *enfoque anticipatorio* 11/4; *acción temprana* 0 | GTM l.79↔l.315: EN "anticipatory action framework for drought in Guatemala" ↔ ES "marco de Acción Anticipatoria (AA) para sequía en Guatemala" | B. The acronym **AA** is kept in Spanish ("marco de AA", "la AA") |
| AA framework | **marco de acción anticipatoria** | 65 / 4 | *marco de AA* 8/4; *marco AA* 4/3; *marco colectivo de acción anticipatoria* 3/1 (CUB e-mails) | GTM l.315 (above) | B. Lowercase in prose (≈33×). Title Case "Marco de Acción Anticipatoria" (≈21×) appears only when naming the framework in e-mails or headings |
| trigger (noun) | **disparador** | 179 / 4 | *desencadenante* 2/2 (GTM l.494 "umbral del desencadenante"; CUB l.450); *desencadenador* 1/1; *activador* 1/1 (CUB l.1969 "[Activador de alistamiento]"); *detonante*, *gatillo* 0 | CUB l.1974: "Disparador de ALISTAMIENTO alcanzado / … READINESS trigger reached" | A. Clear winner. *umbral* = threshold, never trigger |
| trigger mechanism | **mecanismo de activación** | 32 / 4 | none (*mecanismo de disparo / disparador* 0) | GTM l.110↔l.490: EN "Table 1. Trigger Mechanism Statistics" ↔ ES "Tabla 4. Estadísticas del mecanismo de activación" | B. Also renders "activation mechanism" (CUB l.97↔l.468). Chapter title: "Los disparadores y el mecanismo de activación" |
| readiness trigger | **disparador de alistamiento** | 16 / 1 (CUB) + e-mails | heading "Activador de alistamiento" 1 | CUB l.1991↔l.2020: "se ha alcanzado el disparador de alistamiento" ↔ "the readiness trigger … has been reached" | A. Single source: only CUB has a readiness stage (the DC frameworks have none) |
| action trigger | **disparador de acción** (in full: *disparador de acción anticipatoria*) | 8 + 10 / 1 (CUB) | *disparador de la acción* 1 | CUB l.2103: "Disparador de ACCIÓN ANTICIPATORIA alcanzado / … ANTICIPATORY ACTION trigger reached"; CUB e-mails: "Disparador de acción :" | A. CUB calls the action stage *acción anticipatoria*. The short UI form *disparador de acción* is the live e-mails' form |
| readiness (phase) | **alistamiento** | 39 / 1 (CUB) | *ventana de alistamiento* 5/1. Keep separate: *preparación* 41/4 = preparedness (*preparación para desastres / emergencias / la respuesta* 17/4); *preparativos* 1 | CUB l.99↔l.470: (“Readiness” and “Anticipatory Action”) ↔ ("Alistamiento" y "Acción anticipatoria") | B. Mirrors the French split *mobilisation* (readiness) vs *préparation* (preparedness) |
| observational trigger | **disparador observacional** | 11 / 1 (CUB) | *disparador de observación* 5/1; combined *disparador de observación/respuesta temprana* | CUB l.96↔l.467: "for the observational trigger" ↔ "para el disparador observacional"; CUB e-mails: "Disparador observacional :" | A/B. The observational stage's own name is *Respuesta temprana* (Early Response; 27/4) |
| forecast-based trigger | **disparador basado en pronósticos** | 2 / 1 (CUB) | *disparador de pronóstico* 1/1 | CUB l.94↔l.464: "two forecast-based triggers" ↔ "dos disparadores basados en pronósticos" | B. Thin (one doc) but an exact pair |
| trigger window | **ventana** (*ventana de activación*) | 94 / 4; *ventana de activación* 3/3 (DC) | *ventana de monitoreo* 3/3; CUB names each window after its stage: *ventana de alistamiento* 5, *ventana de acción anticipatoria* 6/2, *ventana de respuesta temprana* | GTM l.101↔l.426: “Window A” ↔ “Ventana A”; GTM l.439 "Figura 2 – Ventanas de monitoreo y activación" | B. Keep separate from *ventana de oportunidad* |
| window of opportunity | **ventana de oportunidad** | 12 / 4 | *período de oportunidad* 4/4 | CUB l.2057↔l.2086: "las ventanas de oportunidad establecidas en el marco" ↔ "the windows of opportunity established in the framework" | A |
| to activate / activated / activation | **activar / activado / activación** | *activación* 247/4; *activaciones* 31/4; *activado/a(s)* 27/4; *se activa/activó* 18/4 | *no activación* 12/3 (DC) | GTM l.115↔l.495: "The AA framework was activated" ↔ "El marco AA se activó" | B |
| full / partial activation | **NOT ATTESTED** | 0 | — | CUB expresses the idea as funding scenarios: l.1562 "10% de uso de fondos" vs "100% de uso de fondos" | **Suggestion:** *activación completa / activación parcial*. French attests both (see §2) |
| triggered (a trigger is met) | **alcanzado** — *se alcanzó el disparador / umbral* | *alcanzad-* 26/4; *alcanzar … disparador/umbral* 52/4 | *se cumple cualquiera de los disparadores* 4/4; *desencadenado* 3/1 (CUB annex: "huracanes que se habrían desencadenado"); *disparado* 0 | CUB l.1974 (above); CUB e-mails flag every condition as "ALCANZADO" / "NO ALCANZADO" | A. Use *alcanzado / no alcanzado* for a trigger or threshold and *activado* for the framework (the counterpart of FR *atteint / non atteint*). "Activities are triggered" → *se activan* (GTM l.101↔l.426) |
| threshold | **umbral** (pl. *umbrales*) | 93 / 4 | *umbral de activación* 7/4; *umbrales individuales* 11/3 | GTM l.101↔l.426: "individual thresholds" ↔ "umbrales individuales" | B |
| return period | **período de retorno** | 52 / 4 | always the accented *período* in this phrase (*periodo de retorno* 0). Abbreviation **RP** 15/3 (DC; the English acronym is kept); *PR* 0. "1-in-3-year" → *1 en 3 años* (23/3) | GTM l.96↔l.419: "combined annual return period of 1 in 3 years" ↔ "período de retorno anual combinado de 1 en 3 años" | B |
| overall return period | doc term **período de retorno anual combinado**; for a UI label see note | 13 / 3 (DC) | per season: *período de retorno estacional de activación* 4/2 (GTM l.103↔l.428 "overall seasonal activation return period"); *general / global / total* 0 | GTM l.96↔l.419 (above) | B for *anual combinado*, the doc's name for the overall RP across both windows. **Suggestion** for a short label: *período de retorno general* (cf. GTM l.414 "mecanismo de activación general"). FR uses *globale* |
| effective return period | **NOT ATTESTED** | 0 | — | — | **Suggestion:** *período de retorno efectivo* |
| individual return period | **NOT ATTESTED** as a phrase | 0 (*umbrales individuales* 11/3) | — | GTM l.426 | **Suggestion:** *período de retorno individual* |
| backtest / historical performance | **desempeño histórico** | 8 / 4 | *rendimiento histórico* 3/1 (CUB); *estadísticas históricas de activación* 8/4; *registro histórico* 6/3; *simulación histórica*, *retrospectivo* 0 | GTM l.1439: "Anexo 2- Desarrollo de disparadores y desempeño histórico" | C |
| "would have activated" | **se habría activado** | 5 / 4 | *habría(n) alcanzado / seleccionado* 4/1 (CUB); *se habrían desencadenado* 2/1 | GTM l.1462: "se determina si el mecanismo se habría activado" | C |
| false alarm | **falsa alarma** | 5 / 4 | — | GTM l.839: "En caso de una falsa alarma" | C |
| early response (CUB observational stage) | **respuesta temprana** | 27 / 4 (24 CUB) | — | CUB l.95↔l.465: "early response actions" ↔ "acciones de respuesta temprana" | B. The equivalent of FR *réponse précoce*; not *alerta temprana* |

### 1.2 Money

| EN | recommended | count / docs | variants seen (counts) | source (file + quote) | tier · notes / **Suggestion** |
|---|---|---|---|---|---|
| pre-arranged funding / financing | **financiación preestablecida** | 16 / 4 | *financiamiento preestablecido* 4/4; *fondos preestablecidos* 8/4; *recursos preestablecidos* 1/1; all *preestablecid-* 32/4 vs hyphenated *pre-establecid-* 3/3; *pre-arreglado* 0 | GTM l.86↔l.1107: "The pre-arranged CERF funding is dedicated specifically" ↔ "El financiamiento preestablecido del CERF se dedica específicamente" | B. Chapter title in all four docs: "6. Financiación preestablecida". Write it closed (*preestablecida*) |
| pre-agreed | **acordado previamente / previamente acordado** | 10 / 4 | *pre-aprobado(s)* 3/3 (= pre-approved projects); *pre-acordado* 0 | GTM l.122↔l.843: "The pre-agreed actions" ↔ "Las actividades acordadas previamente" | B. The French three-way distinction survives: money = *preestablecida*, actions = *acordadas previamente*, stock = *preposicionado* |
| pre-positioned | **preposicionado**; noun **preposicionamiento** | 5 / 1 + 9 / 1 (CUB only) | — | CUB l.170↔l.1224: "where they are pre-positioned" ↔ "donde se encuentran preposicionados" | B. Single source |
| envelope | **NOT ATTESTED** in the money sense | 0 (*envolvente* 0; *sobre* only as a preposition) | *monto total* 3/3 (DC message draft) | GTM l.1511: "con un monto total de USD 4,000,000" | **Suggestion:** *monto (preestablecido)*. Avoid the calque *envolvente* |
| allocation | **asignación** | 17 / 4 | *asignación del CERF* 10/4; verb *asignar* 8/4 | CUB l.1941: "Rojo: tenía una asignación del CERF" | C |
| disbursement | **desembolso** | 22 / 4 (*desembols-*) | — | CUB l.2053↔l.2082: "las cartas de aprobación del CERF con los detalles de los desembolsos" ↔ "letters of approval from the CERF with details of the disbursements" | A |
| released (money) | **liberado / liberación (de fondos)** | 7 / 4 | *se liberan* 3/3; *liberación de fondos* 4/4 | GTM l.1104: "si una de ellas se activa, los recursos se liberan en su totalidad" | C. The EN "CERF released the pre-established USD 4 million" (GTM l.117) has no Spanish twin. Keep separate from *desembolsar* (disburse) |
| co-financing | **cofinanciación** | 4 / 3 | *co-financiado* 2/2 (HND/SLV "proyecto co-financiado por ECHO"); *cofinanciamiento* 0 | GTM l.1129: "Cofinanciación (en $US)" (header of Table 7) | C |
| pooled fund | **fondo mancomunado** | 4 / 4 | *fondos comunes* 0 | GTM l.1258: "no se financian … con fondos mancomunados, incluido el CERF" | C, **weak**: the same boilerplate sentence repeated in all four docs. The EN "pooled-fund financing" (GTM l.85) has no Spanish twin |
| country-based pooled fund | **NOT ATTESTED** | 0 | — | — | **Suggestion:** *fondo mancomunado de país (CBPF)*. Check against OCHA's own Spanish usage |
| regional (humanitarian) fund | **NOT ATTESTED** in Spanish | 0 | the French HTI doc names the LAC one (§2) | — | **Suggestion:** *Fondo Humanitario Regional (para América Latina y el Caribe)* |
| implementing partner | **NOT ATTESTED** | 0 (only generic *socio(s)* 63/4, *agencias participantes*) | — | GTM l.807: "las agencias participantes han acordado designar al WFP" | **Suggestion:** *socio implementador* |
| sub-grant | **NOT ATTESTED** | 0 | — | — | **Suggestion:** *subvención (a socios)*. Verify |
| localisation | **localización** | 6 / 3 (DC Annex 1) | *actores locales* 3/3 | GTM l.1410: "Apoyo a la localización: … respeten el compromiso con la localización" | C. One source (DC only) |
| direct implementation | **NOT ATTESTED** | 0 | — | — | **Suggestion:** *implementación directa* |
| cash assistance / cash transfers | **asistencia en efectivo**; **transferencias de efectivo** | 7 / 4; 6 / 3 | *entrega de efectivo* 4/4; *transferencias monetarias*, *cupones*, *vales* 0 | GTM l.129↔l.877: "Provision of Cash Assistance … cash transfers" ↔ "Proveer asistencia en efectivo: incluye … transferencias de efectivo incondicionales" | B |
| cash and voucher assistance (CVA) | **NOT ATTESTED** as a phrase | 0 | — | — | **Suggestion:** *asistencia en efectivo y cupones (CVA)* |
| multi-purpose cash | **efectivo multipropósito** | 1 / 1 (GTM Table 8) | *Multi-propósito* 2/2 (GTM/HND Table 6); *asistencia en efectivo para fines múltiples* 1/1 (CUB l.1799) | GTM l.1201: "Efectivo multipropósito $1,280,000 (32%)" | C. Use it as the sector label |
| rapid response (CERF window) | **respuesta rápida** | 15 / 4 | *fondos de respuesta rápida* 4/4 | GTM l.87↔l.1108: "CERF rapid response funding" ↔ "los fondos de respuesta rápida del CERF" | B |
| approval letter | **carta de aprobación** | 24 / 4 | — | CUB l.2053↔l.2082 (above) | A |

### 1.3 People

| EN | recommended | count / docs | variants seen (counts) | source (file + quote) | tier · notes / **Suggestion** |
|---|---|---|---|---|---|
| people covered (by a plan) | **NOT ATTESTED** | 0 | — | (the "protect up to 60,000 people" sentence exists only in the EN summary) | **Suggestion:** *personas cubiertas* |
| people targeted | **personas objetivo** | 12 / 4 | table header *Número de personas objetivo* 8/4; *público meta* 3/3 (a communications audience, not this sense); *población objetivo*, *personas meta* 0 | GTM l.1187: "Número de personas objetivo" | C |
| people reached | **NOT ATTESTED** | 0 | — | — | **Suggestion:** *personas alcanzadas*. It collides with *disparador alcanzado*; the alternative is *personas asistidas* |
| beneficiaries | **beneficiarios** / **personas beneficiarias** | 22 / 4; 7 / 4 | — | CUB l.2059↔l.2088: "listas de personas beneficiarias" ↔ "lists of beneficiaries" | A. The bilingual text uses the inclusive form *personas beneficiarias* |

### 1.4 Hazards

| EN | recommended | count / docs | variants seen (counts) | source (file + quote) | tier · notes / **Suggestion** |
|---|---|---|---|---|---|
| drought | **sequía** | 153 / 4 | — | GTM l.79↔l.315 (above) | B |
| flood | **inundación / inundaciones** | 10 / 4 | *crecida* 0 | CUB l.199: "proclives a los fuertes vientos y las inundaciones" | C |
| storm family (site label "Trop. cyclones") | **ciclones tropicales** (short: *Ciclones trop.*) | 4 / 2 (CUB 3, HND 1) | *tormentas* 23/1 (CUB's generic word for any system, e.g. "tormentas objetivo"); *huracanes* 104/3; CUB chapter title "Tormentas y huracanes en Cuba"; *sistemas ciclónicos* 1 | CUB l.195: "formación de ciclones tropicales … convertirse en tormentas tropicales o huracanes" | C. *Ciclón tropical* is the umbrella term the doc itself uses, and it matches the FR site label *Cyclone tropical* |
| cholera | **NOT ATTESTED** in the Spanish docs | 0 | — | — | **Suggestion:** *cólera* (standard Spanish) |
| hazard | **amenaza** | 4 / 4 | *peligro* 4/2: a **TIE** (CUB "Peligro, Vulnerabilidad y Riesgo (PVR)", "otros peligros secundarios") | GTM l.378: "alertas frente a múltiples amenazas" | C, tie. *amenaza* is in all four docs and is the UNDRR Spanish term (a suggestion-level reason). *peligro* is Cuba's national usage |
| early warning | **alerta temprana** | 25 / 4 | — | GTM l.124↔l.864: "early warning messaging" ↔ "enviar mensajes de alerta temprana" | B |

### 1.5 Statuses

None of the site's lifecycle statuses appear in the docs as statuses. The French glossary had the same problem.

| EN | recommended | count / docs | variants seen (counts) | source (file + quote) | tier · notes / **Suggestion** |
|---|---|---|---|---|---|
| active | **NOT ATTESTED** as a status | *activo/a* 26/4, but in other senses ("Oficina … (OCR) activa") | — | CUB l.291 | **Suggestion:** *Activo* |
| being updated / under revision | **NOT ATTESTED** | *en revisión*, *en actualización* 0 | *actualización periódica del marco* 4/4 | CUB l.313: "la actualización periódica del marco" | **Suggestion:** *En actualización* (or *En revisión*) |
| in development | **NOT ATTESTED** as a status | *fase de desarrollo* 4/4 | CUB e-mails base.html: "los proyectos están aún en desarrollo" | GTM l.1358: "incluso durante la fase de desarrollo, activación y aprendizaje" | **Suggestion:** *En desarrollo* (supported by the live e-mails' wording) |
| retired | **NOT ATTESTED** | 0 | — | — | **Suggestion:** *Retirado* |
| expired | **NOT ATTESTED** | 0 (*vencido*, *expirado*, *caducado* 0) | the docs speak of *vigencia* 8/4 and *período de validez* 7/4 | GTM l.88↔l.1109: "during the validity period" ↔ "durante el período de validez" (B) | **Suggestion:** *Vencido* (alternative *Expirado*) |
| superseded | **NOT ATTESTED** | 0 | — | — | **Suggestion:** *Reemplazado* |
| endorsed (ERC) | **aprobado** | 18 / 4; title-block "Aprobado por el ERC/CR" 8/4 | *validado* 3/3 (local validation of targeting); *respaldado* 1 (another sense); *endosado* 0 | CUB l.5: "Aprobado por el ERC el 27/08/2025"; CUB e-mails: "ha sido aprobado por el Coordinador de Socorro de Emergencia" | C. The public site shows "endorsed" as Active, so this mostly matters in prose |
| pilot | **piloto** | 2 / 1 (CUB) | *fase piloto* 1; *iniciativas piloto* 1 | CUB l.1848: "La temporada 2025 será una fase piloto" | C. The EN "2024-2025 AA pilot framework" (GTM l.143) has no Spanish twin |
| version (of a framework) | **versión** | 6 / 4 | — | CUB l.3: "Versión 1 – 26/08/2025"; GTM l.3: "Versión 3 – 02/03/2026" | C |
| validity period | **período de validez**; *vigencia* | 7 / 4; 8 / 4 | — | GTM l.88↔l.1109 (above); chapter "Vigencia y futuro del marco" | B |

### 1.6 Institutions and roles

| EN | recommended | count / docs | variants seen (counts) | source (file + quote) | tier · notes / **Suggestion** |
|---|---|---|---|---|---|
| CERF (expansion) | **Fondo Central para la Acción en Casos de Emergencia (CERF)** | 10 / 4 | no competing expansion | GTM l.1083: "Fondo Central para la Acción en Casos de Emergencia (CERF)" | C. Consistent across docs (it is the UN's official Spanish name) |
| OCHA (expansion) | **NOT ATTESTED** (acronym only) | 0 | *OCHA ROLAC* 29/4; "Oficina Regional de la OCHA para América Latina y el Caribe" 1/1 | CUB l.297 | **Suggestion:** *Oficina de Coordinación de Asuntos Humanitarios (OCHA)*. Verify the house form against unocha.org/es. Note the docs write *la OCHA* once and *OCHA* elsewhere |
| Centre for Humanitarian Data | **Centro de Datos Humanitarios (de OCHA)** | 39 / 4 | acronym **CHD** 28/4 (the English acronym is kept) | CUB l.543: "monitoreados por el Centro de Datos Humanitarios (CHD)" | C |
| Emergency Relief Coordinator | **Coordinador del Socorro de Emergencia (ERC)** | 4 / 4 | *Coordinador de Socorro de Emergencia* 4/4. An **exact TIE**: every doc has one of each, and the CUB e-mails use *de Socorro* | GTM l.1097: "por el/la Coordinador/a del Socorro de Emergencia (ERC)"; GTM l.1085: "el Coordinador de Socorro de Emergencia (ERC)" | C, tie. *del Socorro* matches the UN title (a suggestion-level reason). The acronym ERC is kept |
| Resident Coordinator | **Coordinador Residente (CR)**; office **Oficina del Coordinador Residente (OCR)** | 90 / 4; CR 30/4; OCR 40/4 | the inclusive form *Coordinador/a Residente* is frequent | CUB l.2067↔l.2095: "Coordinador Residente de las Naciones Unidas" ↔ "United Nations Resident Coordinator" | A |
| Humanitarian Coordinator / RC/HC | **CR/CH** | 6 / 3 (DC) | *CR/HC* 4/4 (title blocks "Aprobado por el CR/HC"); *Coordinador Humanitario* spelled out 0 | GTM l.522: "el Coordinador Residente (CR/CH) notificará" | C. **Suggestion** for the spelled-out form: *Coordinador Residente y Coordinador Humanitario* |
| humanitarian country team | **Equipo Humanitario de País (EHP)** | 1 / 1 (HND) | CUB has *UNETE*, "Equipo Técnico de Emergencia de las Naciones Unidas", which is a different body | HND l.204: "del Equipo Humanitario de País (EHP)" | C, single hit |
| UN agencies | **agencias de la ONU** / **agencias de Naciones Unidas** | 15 / 4; 13 / 4 | *agencias ONU* 3/3; *organismos de las Naciones Unidas* 5/4; *agencias del Sistema de Naciones Unidas* 4/4 | CUB l.2062↔l.2090: "otras agencias de Naciones Unidas" ↔ "other United Nations agencies" | A for *agencias de Naciones Unidas*; *de la ONU* is slightly more frequent. A close race |
| NGOs (international / national) | **ONG internacionales / ONG nacionales** | *ONGs* 9/4; *ONGs nacionales e internacionales* 8/4 | the docs always pluralise *ONGs*; *organizaciones no gubernamentales* 0 | CUB l.2062↔l.2091: "ONGs nacionales e internacionales" ↔ "national and international NGOs" | A. The docs write *ONGs*; the RAE prefers the invariable *las ONG*. Reviewer to choose |
| Red Cross / Red Crescent national societies | **Cruz Roja** + country name | 9 / 4 | "Cruz Roja Guatemalteca / Hondureña / Salvadoreña / cubana", "Cruz Roja Alemana"; *Media Luna Roja* 0; *Sociedades Nacionales* 0 | GTM l.1577: "Cruz Roja Guatemalteca" | C. **Suggestion** for the generic: *Sociedades Nacionales de la Cruz Roja y de la Media Luna Roja* |
| government (counterparts) | **gobierno**; **contrapartes de gobierno** | 73 / 4; 10 / 3 | *contrapartes gubernamentales* 4/4; *contrapartes sectoriales* 15/4; *autoridades nacionales* 35/4 | GTM l.515: "informará a los y las jefes de agencia y a las contrapartes de gobierno relevantes" | C |
| civil society | **sociedad civil** | 8 / 4 | — | CUB l.2063↔l.2091: "organizaciones de la sociedad civil" ↔ "civil society organizations" | A |
| CERF secretariat | **Secretaría del CERF** | 16 / 4 | *Secretariado del CERF* 6/1 (CUB messages) | CUB l.2043↔l.2069: "equipo del Secretariado del CERF" ↔ "CERF Secretariat Team" | A for *Secretariado*; *Secretaría* is more frequent |

### 1.7 Sectors (as the docs name them)

| EN | recommended | count / docs | variants seen (counts) | source (file + quote) | tier · notes / **Suggestion** |
|---|---|---|---|---|---|
| food security | **Seguridad alimentaria** | 57 / 4 | table label *Seguridad alimentaria-agricultura* 3/2; national bodies use *Seguridad Alimentaria y Nutricional* | GTM l.122↔l.317: "food security, wash, health and nutrition" ↔ "seguridad alimentaria, nutrición, salud y WASH" | B |
| health | **Salud** | 70 / 4 | — | GTM l.122↔l.317 | B |
| nutrition | **Nutrición** | 31 / 3 (DC) | — | GTM l.122↔l.317 | B |
| WASH | **WASH** (expansion *Agua, saneamiento e higiene*) | 40 / 4; 19 / 4 | table label "WASH- Agua, saneamiento e higiene" | CUB l.158↔l.1119: "wash" ↔ "agua, saneamiento e higiene"; GTM l.1145 | B. The English acronym beats the Spanish expansion |
| protection | **Protección** (word only) | 32 / 4 | mostly generic ("centralidad de la protección"); no ES framework has a protection sector | GTM l.1379: "Garantizar la centralidad de la protección" | C, the word only, not as a cluster name |
| child protection | **NOT ATTESTED** | 0 | — | — | **Suggestion:** *Protección de la niñez* (alternative *Protección infantil*) |
| GBV | **NOT ATTESTED** | 0 | — | — | **Suggestion:** *Violencia basada en género (VBG)* |
| shelter and NFI | **Alojamiento** (+ *artículos no alimentarios*) | *Alojamiento* 3/1 | **four words in one doc**: *Vivienda* 5/2 (CUB Table 7 header, and the exact parallel of EN "shelter"); *albergue* 1/1; *refugio* 5/1 (*viviendas refugio*); *artículos no alimentarios* 2/1 | CUB l.158↔l.1119: "education, health and shelter" ↔ "educación y vivienda"; CUB Table 6 sector header "Alojamiento" | B for *vivienda*, C for *alojamiento*. **Flag: reviewer to choose.** **Suggestion:** *Alojamiento y artículos no alimentarios* |
| CCCM | **NOT ATTESTED** | 0 | (CUB has *centros de evacuación* 6/1) | — | **Suggestion:** *Coordinación y gestión de campamentos (CCCM)* |
| education | **Educación** | 8 / 2 (CUB 7, SLV 1) | — | CUB l.158↔l.1119 | B |
| logistics | **Logística** | 12 / 4 | — | CUB l.158↔l.1118 | B |
| early recovery | **Recuperación temprana** | 4 / 4 (one boilerplate sentence) | — | GTM l.1269: "la respuesta rápida y la recuperación temprana" | C, generic sense |
| coordination and support services | **NOT ATTESTED** | 0 | — | — | **Suggestion:** *Coordinación y servicios de apoyo* |
| multi-purpose cash | **Efectivo multipropósito** | see §1.2 | | | |

### 1.8 Other UI words

| EN | recommended | count / docs | variants seen (counts) | source (file + quote) | tier · notes / **Suggestion** |
|---|---|---|---|---|---|
| learning | **aprendizaje** | 49 / 4 | — | GTM l.135↔l.1280: "The learning" ↔ "7. El aprendizaje" | B |
| lessons learned | **lecciones aprendidas** | 23 / 4 | — | GTM l.136↔l.1304: "lessons learned" ↔ "lecciones aprendidas de la activación del 2025" | B |
| after-action review | **análisis (conjunto) posterior a la acción** | 4 / 4 | — | GTM l.141↔l.1336 | B |
| monitoring (of triggers) | **monitoreo** | 67 / 4 | *seguimiento* 30/4, used for M&E ("Seguimiento, evaluación y rendición de cuentas") **and** in the CUB e-mail title; *vigilancia* 17/4 (surveillance) | CUB l.1981↔l.2011: "Cuba : seguimiento de huracanes" ↔ "Cuba: Hurricane monitoring"; GTM l.508: "monitorear el pronóstico estacional" | A/B. **Flag:** two words compete. Use *monitoreo* for trigger monitoring and *seguimiento* for M&E |
| monitoring period | **período de monitoreo** | 3 / 3 (DC) | *momento(s) de monitoreo* 4/2 | GTM Table 5: "Los días 5 de cada mes durante el período de monitoreo" | C |
| lead time | **tiempo de anticipación** | 47 / 3 (DC only) | *plazo de anticipación* 3/1 (CUB, defined at l.474: “Plazo de anticipación” describe el período entre la publicación del pronóstico y…); *plazo de entrega* 1/1 (CUB Table 3 header ↔ EN "Lead time", a calque of "delivery time"); *tiempo de entrega* 4/4 means delivery time (another sense) | GTM l.101↔l.427: "each monitoring moment/lead time" ↔ "cada momento de monitoreo/tiempo de anticipación" | B. **Flag:** competing variants, each from a single source. Avoid *plazo de entrega* |
| forecast | **pronóstico** | 122 / 4 | *previsión* 3/2 | CUB l.96↔l.467: "the forecast triggers" ↔ "los disparadores de pronóstico" | B, decisive |
| seasonal forecast | **pronóstico estacional** | 29 / 3 (DC) | *previsión estacional* 0 | GTM l.430: "El pronóstico estacional de MJJA será monitoreado" | C |
| forecast skill | **habilidad del pronóstico** | 12 / 3 (DC) | *desempeño* 14/4; *precisión / exactitud* 2/1 (CUB metrics) | GTM l.400: "demostraron habilidad de pronóstico significativa" | C. A calque of "skill". The French glossary rejected *compétence* for the same reason, so a reviewer should look at this one |
| Latin America and the Caribbean | **América Latina y el Caribe** | 3 / 1 (CUB) | *Centroamérica* 3/3 | CUB l.297: "Oficina Regional de la OCHA para América Latina y el Caribe (OCHA ROLAC)" | C |
| West and Central Africa | **NOT ATTESTED** | 0 | — | — | **Suggestion:** *África Occidental y Central* |
| Eastern and Southern Africa | **NOT ATTESTED** | 0 | — | — | **Suggestion:** *África Oriental y Meridional* |
| Asia and the Pacific | **NOT ATTESTED** | 0 | — | — | **Suggestion:** *Asia y el Pacífico* |
| Middle East and North Africa | **NOT ATTESTED** | 0 | — | — | **Suggestion:** *Oriente Medio y Norte de África* |

### 1.9 Conventions observed in the Spanish docs

- **Months** are lowercase in prose ("en julio de 2025", "septiembre-noviembre"). Capitals appear only in table and figure cells or at the start of a sentence ("Marzo", "Julio" in the trigger matrix). Abbreviations are three letters with no dot in charts (GTM chronogram: *Ene Feb Mar Abr May Jun Jul Ago Sep Oct Nov Dic*), with a dot in dates ("31 dic. 2024", CUB messages and e-mails). Date format is dd/mm/yyyy ("02/03/2026").
- **Decimal separator: point dominates** (≈44 hits: "1 en 2.92", "3.7 años", "98.2 mm", "(7.5%)"). A decimal comma appears only in CUB prose for millions ("1,7 millones", "3,5 millones", "78,3 millones de dólares") and once in "3,7 años".
- **Thousands separator: comma dominates** (≈135 hits: "170,000", "111,962", "$4,000,000"). A point appears in 8 prose hits (GTM "54.000 hectáreas", "2.627 incendios"; CUB "150.000", "930.000"). The docs therefore mostly follow the EN/Mexican-Central-American format, and nothing in them contradicts the I18N.md rule of one number format across languages.
- **Percentages** take no space: "36%", "el 20%" (38 vs 1 spaced).
- **USD** is written five ways: tables "$4,000,000" and "$440,000 (11%)"; headers "(en $US)", "(en US$)", once "(en dólares EE.UU.)"; prose "4 millones de dólares", "USD 4,000,000", "USD 13 mil millones". No doc uses an "M" abbreviation in Spanish.
- **Quotation marks:** straight double quotes in the Spanish bodies (≈74 overall; curly “ ” only 2–3 per Spanish body, the rest in EN summaries). **No guillemets** (« ») anywhere, unlike French. One CUB typo uses ¨…¨.
- **Capitalisation:** *acción anticipatoria* is lowercase as a concept. *Marco de Acción Anticipatoria* is capitalised when naming the framework in messages, but lowercase is more frequent in prose. Sector labels are in sentence case ("Seguridad alimentaria"). English acronyms are kept: AA, CERF, ERC, CHD, RP, WASH. Spanish ones: CR, OCR, CR/CH, EHP, SNU, ONG(s).
- **Inclusive slash forms** are frequent in formal text ("Coordinador/a Residente", "el/la", "Jefes/as"). For UI labels, pick one form.

---

## 2. French — gaps only

Terms the I18N.md French glossary does not cover yet. Same columns and tiers as above.

**Correction for I18N.md:** the glossary says *activation partielle* is "inferred by analogy (not attested verbatim)". It **is attested**: 7 hits in bfa-drought 2022-03-09, 2024-02 and 2025-02-28 (one boilerplate lineage), e.g. bfa-drought/2024-02 l.50 "une activation partielle du plan d'action est possible". *activation complète* has 5 hits in 5 docs (bfa-drought/2022-03-09 l.1104 "pour une activation complète du cadre").

| EN | recommended | count / docs | variants seen (counts) | source (file + quote) | tier · notes / **Suggestion** |
|---|---|---|---|---|---|
| window of opportunity | **fenêtre d’opportunité** | 74 / 17 | *fenêtre d’action* 2/2 (TCD-D); *fenêtre de déclenchement* 20/3 (NER-D; = trigger window, already in the glossary) | bfa-drought/2022-03-09 l.263: "Ces moments, également appelés fenêtres d'opportunité" | C. The glossary mentions it only inside a note; it deserves its own row |
| partial / full activation | **activation partielle / activation complète** | 7 / 3; 5 / 5 | *activation totale*, *déclenchement partiel* 0 | see correction above | C |
| "would have activated" (backtest) | **aurait déclenché** / **aurait été activé** | 23 / 7; 5 / 4 | *aurait activé* 3/2; *simulation historique* 0 | bfa-drought/2025-02-28 l.703: "les déclencheurs auraient été activés en :"; tcd-drought/2025-03-03 l.2434: "les années où on aurait déclenché" | C |
| historical data / analysis | **données historiques**; **analyse historique** | 40 / 19; 9 / 6 | *performance historique* 1/1 (tcd-flooding 2025); *analyse rétrospective* 2/2 (another sense) | — | C |
| envelope | **enveloppe** | 9 / 6 | *montant total* 1/1 | cod-infectious-disease/2026-06-24 l.48: "L’enveloppe CERF pour chaque activation est limitée à 1 million" | C |
| released (money) | **débloqué(s)** (*des fonds seront débloqués*); noun *déblocage* | *débloqu-* 55/17; "fonds … débloqués" 23/4; *déblocage* 6/4 | *libérer (les fonds)* 3/3 | bfa-drought/2025-02-28 l.41: "Si le déclencheur est activé, des fonds seront débloqués" | C. Keep separate from *décaissement* (= disbursement, already in the glossary) |
| co-financing | **co-financement** | 11 / 5 | *cofinancement* 7/3 (COD 2026, HTI, NER-D 2024). A **close race** | bfa-drought/2026-04-17 l.52: chapter "Co-financement"; cod-infectious-disease/2026-06-24 l.50: "fourniront un cofinancement" | C, flag. Pick one spelling (Spanish is cleanly *cofinanciación*) |
| pooled fund | **fonds commun** | 7 / 7 | *fonds commun global* (= CERF) 4/4; *fonds mutualisé* 0 | hti-hurricanes/2024-08-23 l.446: "le mandat du CERF en tant que fonds commun global" | C |
| country-based pooled fund | **NOT ATTESTED** | 0 (*CBPF*, *fonds humanitaire pays* 0) | — | — | **Suggestion:** *fonds humanitaire pays (CBPF)*. The UN form *fonds de financement commun pour les pays* should be verified |
| regional humanitarian fund | **Fonds humanitaire régional** | 4 / 2 | acronym FHRAOC | bfa-flooding/2025-08 l.334: "Fonds Humanitaire Régional pour l’Afrique de l’Ouest et du Centre (FHRAOC)"; hti-hurricanes/2024-08-23 l.1187: "Fonds Humanitaire Régional géré par OCHA pour … l'Amérique latine et des Caraïbes" | C |
| implementing partner | **partenaire de mise en œuvre** | 23 / 13 | *partenaire d’exécution* 21/11. A **close race**; *partenaires opérationnels* 3/3 | bfa-drought/2024-02 l.910: "partenaires de mise en œuvre"; tcd-drought/2025-03-03 l.1732: "autres partenaires d'exécution" | C, flag |
| sub-grant | **NOT ATTESTED** | 0 (*sous-subvention*, *sous-octroi* 0) | — | — | **Suggestion:** *sous-subvention*. Verify |
| localisation | **localisation** | 22 / 14 | *acteurs locaux / nationaux* 13/10 | bfa-drought/2022-03-09 l.140: "Soutenir la localisation : Tous les partenaires impliqués" | C |
| direct implementation | **mise en œuvre directe** | 1 / 1 | — | hti-hurricanes/2024-08-23 l.1072: "l’OIM est une agence de mise en œuvre directe" | C, single hit |
| cash transfers | **transferts monétaires (TM)** | 162 / 15 | the anglicism *cash* 108/13; *assistance monétaire* 1/1; *coupons* 2/1 | bfa-drought/2022-03-09: "Transferts monétaires inconditionnels via la protection sociale" | C |
| multi-purpose cash | **transferts monétaires à usages multiples** | 6 / 2 | *(à) usages multiples* 10/4; *polyvalents* 1/1 | hti-hurricanes/2024-08-23 table: "Transferts monétaires à usages multiples" | C |
| cash and voucher assistance | **NOT ATTESTED** | 0 | — | — | **Suggestion:** *transferts monétaires et coupons* |
| people covered | **NOT ATTESTED** | 0 (*Couverture nationale*, HTI, is geographic) | — | — | **Suggestion:** *personnes couvertes* |
| people reached | **personnes atteintes** | 3 / 3 (the COD lineage) | *personnes assistées* 0 | cod-infectious-disease/2022-12-07 l.640: "le nombre de personnes atteintes" | C |
| storm family | **cyclones tropicaux** | 26 / 2 | *tempêtes* 41/2; *ouragans* 45/1; *systèmes cycloniques* 22/2 | mdg-storms/2024-12-13 l.76: "le pays subit fréquemment des cyclones tropicaux" | C. Matches the existing site label *Cyclone tropical* |
| being updated / under revision | **mise à jour** (noun); *révisé* | 51 / 14; 13 / 11 | *en révision* 0; *cadre révisé* 3/2 | ner-drought/2024-10-24 l.15: "Mise à jour 2024 : Ce document est une mise à jour du cadre"; cod 2026 l.748: "intégrés dans ce cadre révisé" | C. **Suggestion** for the status label: *En cours de mise à jour* |
| version | **version** | 40 / 17 | — | bfa-drought/2024-02 title: "Version 2024 — Approuvé par le Coordinateur des Secours d'Urgence" | C |
| Resident / Humanitarian Coordinator | **Coordonnateur résident**; **Coordonnateur humanitaire**; combined **CR/CH** | CR 15/6; CH 35/14; *Coordonnateur Résident/Humanitaire* 8/5; *CR/CH* 10/3 | minority spelling *Coordinateur* (résident 2/1, humanitaire 22/12); *RC/HC* 4/4; *CR/HC* 2/2; feminine *Coordonnatrice* in HTI and BFA | bfa-drought/2022-03-09 l.1117: "Approbation par le Coordonnateur Résident/Humanitaire"; cod-infectious-disease/2026-06-24 l.4: "Approbation par le CR/CH" | C. *Coordonnateur* matches the glossary's ERC row |
| humanitarian country team | **équipe humanitaire pays (EHP)** | 23 / 13 | *équipe humanitaire de pays* 3/3; *du pays* 3/3; acronym *EHP* 21/15 vs *HCT* 7/6 | bfa-drought/2024-02 l.168: "L'Equipe Humanitaire Pays (EHP)" | C |
| UN agencies | **agences des Nations Unies** | 55 / 19 | *agences onusiennes* 4/3 | bfa-drought/2026-04-17 l.586: "des agences des Nations Unies, des universités, des ONG nationales et internationales" | C |
| NGOs (international / national) | **ONG internationales / ONG nationales** | *ONG* 75/19; "ONG nationales / internationales / locales" 20/12 | — | bfa-drought/2026-04-17 l.586 (above) | C. *ONG* is invariable |
| Red Cross / Red Crescent national societies | **sociétés de la Croix-Rouge / du Croissant-Rouge** | *Croix-Rouge* 24/15; *Croissant-Rouge* 10/9 | *Sociétés nationales* 0; national names, e.g. "Croix-Rouge Burkinabé (CRBF)" | hti-hurricanes/2024-08-23 l.1135: "les sociétés de la Croix-Rouge/du Croissant-Rouge" | C |
| government (counterparts) | **gouvernement**; **services techniques de l’État**; **autorités nationales** | 141 / 17; 6 / 6; 10 / 6 | *contreparties gouvernementales* 0; *structures étatiques* 5/1 | bfa-drought/2026-04-17 l.77: "comprenant les services techniques de l’Etat et les partenaires humanitaires" | C |
| food security / health / nutrition | **Sécurité alimentaire / Santé / Nutrition** | 291/17; 318/20; 188/12 | *Sécurité alimentaire et nutrition* 33/15 | — | C |
| WASH | **EHA** (*eau, hygiène et assainissement*) — or keep **WASH** | WASH 117/15; EHA 65/12; EAH 45/13 | spelled out *eau, hygiène et assainissement* 12/7 vs *eau, assainissement et hygiène* 13/9; *Eau-Hygiène-Assainissement* 9/6 | bfa-drought/2026-04-17: "UNICEF EHA (WASH)" | C, **flag:** the English acronym is the most frequent, and the French acronym itself is split EHA vs EAH |
| child protection | **protection de l’enfant** | 46 / 8 | — | tcd-drought/2025-03-03 l.1179: "mécanismes communautaires de protection de l’enfant" | C |
| GBV | **violences basées sur le genre (VBG)** | VBG 80/14; spelled out 22/9 | — | bfa-drought/2022-03-09: "réponses multisectorielles aux violences basées sur le genre" | C |
| shelter and NFI | **Abris et biens non alimentaires (ABNA)** | ABNA 25/6 | *Abris / Articles ménagers essentiels (AME)* 7/3 (+ AME 5/2); *abris et NFI* 2/2 | mdg-storms/2024-12-13: "Abris et biens non alimentaires (ABNA)"; bfa-flooding/2025-08: "Abris/Articles ménagers essentiels" | C, flag |
| CCCM | **Coordination et gestion des camps (CCCM)** | 2 / 1 (MDG) | — | mdg-storms/2024-12-13 Table: "Coordination et gestion des camps (CCCM) $ 120,000 (4%)" | C, single doc |
| education / logistics | **Éducation / Logistique** | 92/14; 13/10 | — | — | C |
| early recovery | **NOT ATTESTED** | 0 (bare *relèvement* 10/5) | — | — | **Suggestion:** *relèvement précoce* |
| coordination and support services | **NOT ATTESTED** | 0 | — | — | **Suggestion:** *coordination et services de soutien* |
| learning | **apprentissage** | 305 / 20 | — | — | C (chapter "Apprentissage" in every doc) |
| lessons learned | **leçons apprises** | 38 / 18 | *leçons tirées* 11/7; *retour d’expérience* 2/2 | ner-drought/2024-10-24 l.16: "Il intègre des leçons apprises" | C |
| monitoring period | **période de suivi** | 2 / 1 (MRT) | *mois de suivi* 4/4 (M&E sense) | mrt-drought/2026-04-17 l.636: "durant la période de suivi, février-mai pour le déclencheur prévisionnel" | C, single doc |
| lead time | **délai (de prévision)**; table column **délai maximum** | *délai de prévision* 4/4 | *délai de mise en œuvre (lead time)* 2/2 (NER-D 2022, glossed in English); *délai d’anticipation* 0 | tcd-flooding/2025-07-31 l.30↔l.133: "Délai maximum" ↔ "Maximum lead time"; mdg-storms l.682: "déclenchées selon le délai de prévision" | B for *délai maximum*. The HTI rows *heure limite* and *délai maximum des prévisions* stay as they are |
| West and Central Africa | **Afrique de l’Ouest et du Centre** | 5 / 2 | — | bfa-flooding/2025-08 l.214; MRT: "l’Action Anticipatoire en Afrique de l’Ouest et du Centre" | C |
| Latin America and the Caribbean | **Amérique latine et Caraïbes** | 1 / 1 | as written: "l'Amérique latine et des Caraïbes" | hti-hurricanes/2024-08-23 l.1187 | C |
| Eastern and Southern Africa / Asia and the Pacific / Middle East and North Africa | **NOT ATTESTED** | 0 | — | — | **Suggestion:** *Afrique orientale et australe* / *Asie et Pacifique* / *Moyen-Orient et Afrique du Nord* |
