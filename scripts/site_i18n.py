"""EN / FR / ES for the public site: the team's mechanism (ds-knowledge-base D86, docs/I18N.md).

Copied from ds-knowledge-base scripts/site_i18n.py (the KB says a site may copy it
wholesale; its French table kept the strings of the pages that moved here so this site
could adopt it) and generalised to Spanish along the KB's own checklist ("Adding a
language"): one registry of languages instead of a copy of every helper per language.

How it works (unchanged from D86): every page carries ALL languages at once and a toggle
in the header picks the one shown — no per-language build, no extra pages.
  * T(en)           a plain-text string as <span class="tr" data-en data-fr data-es>; the
                    client swaps textContent, so sorting / filtering see one language.
  * TB(en_html)     a string with markup as dual <span class="lv lv-xx"> blocks; CSS shows
                    the active language.
  * TF / TBF        the same with {name} placeholders filled after the lookup (counts, dates).
  * ATTR / OPT      a title= / placeholder= attribute, an <option>: neither can hold spans,
                    so they carry data-<attr>-<lang> / data-<lang> and the client swaps them.
  * tr8() (JS)      text the pages' scripts build: the page carries the entries it needs
                    (js_dict); pages listen for the 'aalang' event and redraw.
The choice persists in localStorage ('aa-lang', the key the team's other AA pages use:
same origin, so one click flips them all). It is applied in the page's head, before
anything draws, so a page opens in the stored language.

Tables: i18n/fr.json and i18n/es.json (EN key -> translation; whitespace collapsed). The
KB keeps its French table in the module; this site has thousands of strings, and a
reviewer works more easily on the JSON. A string with no translation renders in English
and is reported at the end of the build (report_missing(): count per language, the list
in site_build/i18n-missing.json) — loud, not silent, as in the KB, but not one log line per
string while the site is translated page by page.

Rules (KB I18N.md, unchanged): numbers, currency and percentages keep one format across
languages ($4.0M, 36%) — only unit words translate; data-derived free text (trigger and
threshold prose, notes, window names quoted from documents, organisation names, media
captions) is NOT translated; terminology is doc-sourced (the KB's French glossary; the
Spanish one mined 2026-10-20 from the Dry Corridor and Cuba framework documents, see
i18n/README.md). The translations are drafts for a francophone and a hispanophone
colleague to review.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

LANGS = ("fr", "es")                         # besides English
NAMES = {"en": "English", "fr": "Français", "es": "Español"}
DIR = Path(__file__).parents[1] / "i18n"
OUT = Path(__file__).parents[1] / "site_build"

TABLES: dict[str, dict[str, str]] = {
    l: (json.loads((DIR / f"{l}.json").read_text()) if (DIR / f"{l}.json").exists() else {})
    for l in LANGS}

_WS = re.compile(r"\s+")


def key(s) -> str:
    return _WS.sub(" ", str(s)).strip()


# ---------------------------------------------------------------------------
# controlled vocabularies (this site's codes; display labels are table entries)
# ---------------------------------------------------------------------------

# iso3 -> name, where it differs from the English one (UN French / Spanish short names)
COUNTRY = {
    "fr": {"AFG": "Afghanistan", "BFA": "Burkina Faso", "BGD": "Bangladesh", "COD": "RD Congo",
           "CMR": "Cameroun", "COL": "Colombie", "CUB": "Cuba", "DJI": "Djibouti",
           "ERI": "Érythrée", "ETH": "Éthiopie", "FJI": "Fidji", "GMB": "Gambie",
           "GTM": "Guatemala", "HND": "Honduras", "HTI": "Haïti", "KEN": "Kenya",
           "MDG": "Madagascar", "MLI": "Mali", "MMR": "Myanmar", "MOZ": "Mozambique",
           "MRT": "Mauritanie", "MWI": "Malawi", "NER": "Niger", "NGA": "Nigéria",
           "NIC": "Nicaragua", "NPL": "Népal", "PHL": "Philippines", "PLW": "Palaos",
           "SDN": "Soudan", "SLV": "El Salvador", "SOM": "Somalie", "SSD": "Soudan du Sud",
           "TCD": "Tchad", "TON": "Tonga", "UGA": "Ouganda", "VEN": "Venezuela",
           "VUT": "Vanuatu", "YEM": "Yémen", "ZWE": "Zimbabwe", "AGO": "Angola",
           "BDI": "Burundi", "PAK": "Pakistan", "LKA": "Sri Lanka", "LAO": "Laos",
           "PNG": "Papouasie-Nouvelle-Guinée", "SLB": "Îles Salomon"},
    "es": {"AFG": "Afganistán", "BFA": "Burkina Faso", "BGD": "Bangladés", "COD": "RD del Congo",
           "CMR": "Camerún", "COL": "Colombia", "CUB": "Cuba", "DJI": "Yibuti",
           "ERI": "Eritrea", "ETH": "Etiopía", "FJI": "Fiyi", "GMB": "Gambia",
           "GTM": "Guatemala", "HND": "Honduras", "HTI": "Haití", "KEN": "Kenia",
           "MDG": "Madagascar", "MLI": "Malí", "MMR": "Myanmar", "MOZ": "Mozambique",
           "MRT": "Mauritania", "MWI": "Malaui", "NER": "Níger", "NGA": "Nigeria",
           "NIC": "Nicaragua", "NPL": "Nepal", "PHL": "Filipinas", "PLW": "Palaos",
           "SDN": "Sudán", "SLV": "El Salvador", "SOM": "Somalia", "SSD": "Sudán del Sur",
           "TCD": "Chad", "TON": "Tonga", "UGA": "Uganda", "VEN": "Venezuela",
           "VUT": "Vanuatu", "YEM": "Yemen", "ZWE": "Zimbabue", "AGO": "Angola",
           "BDI": "Burundi", "PAK": "Pakistán", "LKA": "Sri Lanka", "LAO": "Laos",
           "PNG": "Papúa Nueva Guinea", "SLB": "Islas Salomón"},
}

MONTH_ABBR = {"fr": ["", "janv", "févr", "mars", "avr", "mai", "juin", "juil", "août", "sept", "oct", "nov", "déc"],
              "es": ["", "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"]}
MONTH_FULL = {"fr": ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
                     "septembre", "octobre", "novembre", "décembre"],
              "es": ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                     "septiembre", "octubre", "noviembre", "diciembre"]}

# ---------------------------------------------------------------------------
# lookup
# ---------------------------------------------------------------------------

_missing: dict[str, set[str]] = {l: set() for l in LANGS}


def tr(lang: str, en: str) -> str:
    """The string in a language; English, recorded as missing, when there is none."""
    k = key(en)
    out = TABLES[lang].get(k)
    if out is None:
        if k:
            _missing[lang].add(k)
        return en
    # the source's own leading / trailing spaces (' · {0} retired'): keys are trimmed
    lead, trail = re.match(r"\s*", en).group(0), re.search(r"\s*$", en).group(0)
    return lead + out.strip() + trail


def country(iso3: str, en_name: str) -> dict[str, str]:
    return {"en": en_name, **{l: COUNTRY[l].get(iso3, en_name) for l in LANGS}}


def add(en: str, template: str, **values) -> str:
    """Register the translations of a string built from data (a page title, say) from a
    template in the tables: each value is a {'en','fr','es'} dict or a string looked up in
    the tables. Returns en, unchanged."""
    for l in LANGS:
        v = {k: (x[l] if isinstance(x, dict) else tr(l, x)) for k, x in values.items()}
        TABLES[l][key(en)] = tr(l, template).format(**v)
    return en


def register_countries(pairs) -> None:
    """The site names countries by their English name (aa.country_hazard): add each name to
    the tables from COUNTRY, so T(name) and tr8(name) give the French / Spanish exonym. A
    table entry, where one exists, wins."""
    for iso3, en in pairs:
        if isinstance(en, str) and en.strip():
            for l in LANGS:
                if iso3 in COUNTRY[l]:
                    TABLES[l].setdefault(key(en), COUNTRY[l][iso3])


def report_missing() -> None:
    """Called once at the end of the build (build_site.main) — not at exit, so a script that
    merely imports a page module does not overwrite the build's list."""
    n = {l: len(v) for l, v in _missing.items() if v}
    try:            # always rewritten, so a list from an earlier build never lingers
        OUT.mkdir(exist_ok=True)
        (OUT / "i18n-missing.json").write_text(json.dumps(
            {l: sorted(v) for l, v in _missing.items()}, ensure_ascii=False, indent=1))
    except OSError:
        pass
    if not n:
        print("  site_i18n: every string marked for translation has its French and Spanish (pages not yet marked stay English)")
        return
    print("::warning::site_i18n: strings rendered in English for want of a translation — "
          + ", ".join(f"{NAMES[l]} {c}" for l, c in n.items()) + " (list: site_build/i18n-missing.json)")


def _attr(s) -> str:
    return html.escape(str(s), quote=True)


def _all(en: str, given: dict | None, **kw) -> dict[str, str]:
    """{'en': …, 'fr': …, 'es': …}, placeholders filled after the lookup."""
    out = {"en": en, **{l: (given or {}).get(l) or tr(l, en) for l in LANGS}}
    return {l: v.format(**kw) for l, v in out.items()} if kw else out


def T(en: str, fr: str | None = None, es: str | None = None) -> str:
    """Toggle-aware plain-text span (textContent swapped client-side)."""
    v = _all(en, {"fr": fr, "es": es})
    return (f'<span class="tr" data-en="{_attr(v["en"])}"'
            + "".join(f' data-{l}="{_attr(v[l])}"' for l in LANGS)
            + f'>{html.escape(str(v["en"]))}</span>')


def TF(en: str, **kw) -> str:
    """T() with {name} placeholders filled in every language."""
    v = _all(en, None, **kw)
    return (f'<span class="tr" data-en="{_attr(v["en"])}"'
            + "".join(f' data-{l}="{_attr(v[l])}"' for l in LANGS)
            + f'>{html.escape(str(v["en"]))}</span>')


def TB(en_html: str, fr_html: str | None = None, es_html: str | None = None) -> str:
    """Language blocks for a string with markup (links, <b>, …): CSS shows one."""
    v = _all(en_html, {"fr": fr_html, "es": es_html})
    return "".join(f'<span class="lv lv-{l}">{v[l]}</span>' for l in ("en",) + LANGS)


def TBF(en_html: str, **kw) -> str:
    """TB() with {name} placeholders filled in every language."""
    v = _all(en_html, None, **kw)
    return "".join(f'<span class="lv lv-{l}">{v[l]}</span>' for l in ("en",) + LANGS)


def _composed(build) -> dict[str, str]:
    """A string assembled from translated pieces: build(w) is called once per language with w,
    that language's lookup (in English, the string itself)."""
    return {"en": build(lambda x: x), **{l: build(lambda x, l=l: tr(l, x)) for l in LANGS}}


def TC(build, cut: int | None = None) -> str:
    """T() of a composed string (see _composed). cut: past that many characters each
    language is cut, the whole text on hover."""
    v = _composed(build)
    if cut is None or len(v["en"]) <= cut:
        return T(*v.values())
    tip = " ".join(f'data-title-{l}="{_attr(x)}"' for l, x in v.items())
    return (f'<span title="{_attr(v["en"])}" {tip}>'
            + T(*(x[:cut].rstrip() + "…" if len(x) > cut else x for x in v.values())) + "</span>")


def TBC(build) -> str:
    """TB() of a composed string with markup (build returns HTML in each language)."""
    return "".join(f'<span class="lv lv-{l}">{x}</span>' for l, x in _composed(build).items())


def ATTRC(name: str, build) -> str:
    """ATTR() of a composed string."""
    v = _composed(build)
    return f'{name}="{_attr(v["en"])}" ' + " ".join(f'data-{name}-{l}="{_attr(x)}"' for l, x in v.items())


def ATTR(name: str, en: str, **kw) -> str:
    """An attribute (title, placeholder, aria-label) in every language: name="en" plus
    data-name-<lang>, which the client swaps in."""
    v = _all(en, None, **kw)
    return (f'{name}="{_attr(v["en"])}" data-{name}-en="{_attr(v["en"])}"'
            + "".join(f' data-{name}-{l}="{_attr(v[l])}"' for l in LANGS))


def OPT(value: str, en: str, selected: bool = False) -> str:
    """An <option> whose text follows the language (options cannot hold spans)."""
    v = _all(en, None)
    return (f'<option value="{_attr(value)}" class="tr" data-en="{_attr(v["en"])}"'
            + "".join(f' data-{l}="{_attr(v[l])}"' for l in LANGS)
            + (" selected" if selected else "") + f'>{html.escape(v["en"])}</option>')


# the quoted strings of a page, single- and double-quoted scanned apart (each pairing stays on
# its line; a template literal's ${…} would throw a combined scan's pairing off and swallow the
# strings after it — the strings inside template literals go through tr8('…') anyway)
_JS_SQ = re.compile(r"""'((?:[^'\\\n]|\\.)*)'""")
_JS_DQ = re.compile(r'"((?:[^"\\\n]|\\.)*)"')
_JS_TR8 = re.compile(r"""\btr8\(\s*(?:'((?:[^'\\\n]|\\.)*)'|"((?:[^"\\\n]|\\.)*)"|`((?:[^`\\$]|\\.|\$(?!\{))*)`)""")


def _unesc(s: str) -> str:
    # \uXXXX too: the page data is json.dumps'd, which writes '→' or 'é' as an escape
    s = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)
    return s.replace("\\'", "'").replace('\\"', '"').replace("\\`", "`").replace("\\\\", "\\")


def js_dict(page_text: str) -> dict[str, dict[str, str]]:
    """The entries a page's scripts can need: every string literal or data value in the page
    the tables know (labels in the page data — hazards, regions, statuses — included). A
    tr8('…') literal with no translation is reported like any other string."""
    for m in _JS_TR8.finditer(page_text):
        k = _unesc(next(g for g in m.groups() if g is not None))
        for l in LANGS:
            tr(l, k)
    keys = {key(_unesc(m.group(1))) for rx in (_JS_SQ, _JS_DQ) for m in rx.finditer(page_text)}
    # node ids carry their label after a prefix ('d:Other donors', 'p:nr|partner not recorded')
    keys |= {k.rsplit("|", 1)[-1].split(":", 1)[-1] for k in keys if "|" in k or ":" in k}
    return {l: {k: TABLES[l][k] for k in sorted(keys) if k in TABLES[l]} for l in LANGS}


def titles(en: str) -> dict[str, str]:
    return _all(en, None)


# ---------------------------------------------------------------------------
# client-side plumbing (embed in each page)
# ---------------------------------------------------------------------------

LANG_CSS = """
.lv-fr,.lv-es{display:none}
html[data-lang="fr"] .lv-fr,html[data-lang="es"] .lv-es{display:inline}
html[data-lang="fr"] .lv-en,html[data-lang="es"] .lv-en{display:none}
.aa-lang{display:inline-flex;align-items:center;gap:0;border:1px solid rgba(255,255,255,.55);
  border-radius:6px;overflow:hidden;flex:0 0 auto;vertical-align:middle;margin-left:auto}
.aa-lang button{border:none;background:transparent;color:#fff;font-size:12px;font-weight:700;
  padding:4px 9px;cursor:pointer;line-height:1;opacity:.75}
.aa-lang button:hover{opacity:1}
.aa-lang button.on{background:#fff;color:#1f2a44;opacity:1}
"""

TOGGLE_HTML = ('<span class="aa-lang" role="group" aria-label="Language / Langue / Idioma">'
               + "".join(f'<button type="button" data-l="{l}" lang="{l}" title="{NAMES[l]}"'
                         f'{" class=" + chr(34) + "on" + chr(34) if l == "en" else ""} onclick="aaSetLang(\'{l}\')">{l.upper()}</button>'
                         for l in ("en",) + LANGS) + "</span>")

# In the head, before anything draws: the stored language on <html>, and tr8() for the
# pages' scripts (window.I18N: the page's entries, written by the page).
LANG_HEAD_JS = """
(function(){ var l = null; try { l = localStorage.getItem('aa-lang'); } catch(e){}
  if (l === 'fr' || l === 'es') { document.documentElement.setAttribute('data-lang', l);
    document.documentElement.setAttribute('lang', l); } })();
function aaLang(){ return document.documentElement.getAttribute('data-lang') || 'en'; }
function tr8(s){ var l = aaLang(), a = Array.prototype.slice.call(arguments, 1);
  var k = String(s).replace(/\\s+/g, ' ').trim();
  var t = (l !== 'en' && window.I18N && I18N[l] && I18N[l][k]) || s;
  if (t !== s) t = String(s).match(/^\\s*/)[0] + String(t).trim() + String(s).match(/\\s*$/)[0];
  return a.length ? String(t).replace(/\\{(\\d+)\\}/g, function(m, i){ return a[+i] !== undefined ? a[+i] : m; }) : t; }
"""

# The admin site (English only, no toggle): the same tr8() for the shared scripts, no lookup.
LANG_STUB_JS = """
function aaLang(){ return 'en'; }
function tr8(s){ var a = Array.prototype.slice.call(arguments, 1);
  return a.length ? String(s).replace(/\\{(\\d+)\\}/g, function(m, i){ return a[+i] !== undefined ? a[+i] : m; }) : s; }
"""

# aaSetLang (the KB's, for any language): <html data-lang lang>, the .tr spans and options,
# the translated attributes, the toggle, the tab title, then the 'aalang' event for the
# pages' own redraws. At load: the stored language, if any.
LANG_JS = """
function aaSetLang(l){
  document.documentElement.setAttribute('data-lang', l);
  document.documentElement.setAttribute('lang', l);
  try{localStorage.setItem('aa-lang', l);}catch(e){}
  document.querySelectorAll('.tr').forEach(function(el){
    var v = el.getAttribute('data-' + l); if (v !== null) el.textContent = v; });
  ['title', 'placeholder', 'aria-label'].forEach(function(a){
    document.querySelectorAll('[data-' + a + '-en]').forEach(function(el){
      var v = el.getAttribute('data-' + a + '-' + l); if (v !== null) el.setAttribute(a, v); }); });
  document.querySelectorAll('.aa-lang button').forEach(function(b){
    b.classList.toggle('on', b.getAttribute('data-l') === l); });
  if (window.AA_TITLES && window.AA_TITLES[l]) document.title = window.AA_TITLES[l];
  try{document.dispatchEvent(new CustomEvent('aalang', {detail: l}));}catch(e){}
}
(function(){
  var l = aaLang(); if (l === 'en') return;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function(){ aaSetLang(l); });
  else aaSetLang(l);
})();
"""
