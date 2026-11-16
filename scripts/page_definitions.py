"""The Definitions page: how statuses work (the lifecycle diagram that left the Map, owner
2026-10-27, D103) and a glossary of the terms the site uses.

Every definition here is one the site already states somewhere — the Map legend's hover
definitions, the Financing page's method notes, the plain-language boxes, the frameworks
table's footnote — repeated so the pages agree. Nothing is defined here that no page says.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from site_i18n import T, TB, TF  # noqa: E402

PAGE = "definitions.html"
TITLE = "Definitions"

# (term, definition) — the English of each is the string another page shows (or its sentence)
GLOSSARY = [
    ("Frameworks and versions", [
        ("Framework",
         "A framework agrees three things in advance: the trigger model that says when to act, the plan "
         "of activities to be carried out, and the pre-arranged financing that is released the moment "
         "the trigger is met. One framework covers one country and one hazard."),
        ("Version",
         "A framework document, recorded with its status: pre-development, in development or "
         "endorsed; superseded is inferred once a newer endorsed version exists. The most recent "
         "endorsed version decides the framework's status."),
        ("Trigger",
         "The pre-agreed condition, from a forecast or an observation, that activates the framework. "
         "A trigger mechanism can hold several specific triggers with their own windows."),
        ("Trigger window — readiness, action",
         "For sudden-onset hazards, typically a readiness trigger with a long lead time followed by an "
         "action trigger closer to the shock."),
        ("Trigger basis — forecast, observed",
         "Whether the triggers use forecast or observed data, or both (windows of both kinds, or one "
         "window that combines the two)."),
        ("Monitoring season",
         "A static amber ring marks a framework in its monitoring season this month."),
        ("Return period",
         "How often the framework's latest version would activate (any of its trigger windows, in a "
         "year), as the framework document states it, otherwise from its historical simulation."),
        ("Historical simulation (backtest)",
         "The current trigger run over past years, to see when it would have activated. Simulated "
         "activations are kept apart from real ones."),
        ("Technical support",
         "Countries where OCHA supports coordinated anticipatory action but neither leads the effort "
         "nor provides pre-arranged financing."),
        ("No specific hazard",   # in DEV_ONLY_TERMS: left off the open site while landing.GENERAL_ON_OPEN is off (D202)
         "Technical support for anticipatory action in general, not for one hazard. No framework and "
         "no allocation stand behind it; the Map draws its pin with an open ring."),
    ]),
    ("Statuses", [
        ("Active",
         "The most recent version is endorsed, still valid and has not fully triggered (a partial "
         "trigger of independent windows keeps it active)."),
        ("Being updated",
         "How it is derived: an endorsed framework whose most recent version fully triggered or reached "
         "the end of its validity, or whose next version is already in development — the framework "
         "stands, a new version is coming. What it means: a framework that is currently being improved, "
         "including based on learning or the need to reconfirm pre-arranged financing."),
        ("In development",
         "No endorsed version yet: the framework is being built for the first time."),
        ("Retired",
         "Frameworks flagged retired, drawn in grey on the Map so past coverage can be compared with "
         "today's. A framework that a distinct new one replaced, rather than revised, counts as retired."),
        ("Current frameworks",
         "Every framework whose status is active, being updated or in development."),
        ("Activated in the last {n} days",
         "A red ring on the Map marks a framework that activated in the last {n} days."),
    ]),
    ("Activations and allocations", [
        ("Activation (framework activation)",
         "A trigger of a framework version was met and its pre-arranged money was released."),
        ("Non-framework allocation",
         "Countries and hazards with anticipatory-action money outside a framework: money released "
         "without a framework version, or money a fund has pre-arranged and not yet released."),
        ("Two activations a year",
         "Frameworks marked * allow two activations a year: their CERF envelope is counted twice, and "
         "the CERF budget per activation is half of it. Country and Regional Fund envelopes count once."),
    ]),
    ("Money", [
        ("Pre-arranged",
         "The envelope committed to a framework, in place on a date: for every active, being-updated "
         "or in-development framework, the envelope of its most recent version that has one. A stock, "
         "never added over years. With the non-framework allocations layer on, also the money a fund "
         "has pre-arranged outside a framework and not yet released."),
        ("Released",
         "What went out in a year: the allocations drawn by framework activations, plus the "
         "non-framework allocations when that layer is on. A flow, per year. Pre-arranged and released "
         "money are never added together."),
        ("CERF",
         "The UN Central Emergency Response Fund. CERF money stays pre-arranged until a framework is "
         "retired: a framework being updated after an activation keeps its most recent version's "
         "CERF envelope."),
        ("Country and Regional Funds",
         "OCHA's country-based and regional pooled funds. Their money counts as pre-arranged until an "
         "activation draws on it, and from then on it is released money, no longer committed."),
        ("CBPF, RHPF",
         "The two kinds of Country and Regional Funds, apart in the Map's fund switch: CBPF, the "
         "country-based pooled funds; RHPF, the regional humanitarian pooled funds, through their "
         "country windows. OCHA's fund registry says which kind a fund is."),
        ("Co-financing",
         "Money from outside the OCHA-managed funds pre-arranged for the framework, as reported for "
         "the year. It is not a fund: the fund switch does not apply to it."),
        ("Donors",
         "Each donor's share of a fund's income that year, applied to the fund's anticipatory-action "
         "money that year — donors give to the pooled funds as a whole, not to anticipatory action."),
    ]),
    ("People", [
        ("People covered",
         "The latest figure recorded for each current framework — the people its pre-arranged plan "
         "covers, not the people reached once it activated. Retired frameworks cover no one now."),
        ("People reached or targeted",
         "The people CERF reports reached by the allocations an activation drew on. Where no report "
         "has come in yet, the people the allocation planned to reach stand in, and Country and "
         "Regional Fund allocations count the people they target: the headline is an estimate."),
    ]),
]

CSS = r"""
.defs { max-width:980px; }
.defs h2 { margin:22px 0 8px; font-size:17px; }
.defs dl { margin:0; display:grid; grid-template-columns:minmax(150px, 230px) 1fr; gap:6px 18px; }
.defs dt { font-weight:600; color:#0f2540; } .defs dd { margin:0; color:#23364d; line-height:1.5; }
.defs .statushelp { margin:8px 0 18px; } .defs .statushelp summary { font-weight:600; color:#0f2540; }
@media (max-width:640px){ .defs dl { grid-template-columns:1fr; gap:2px 0; } .defs dd { margin-bottom:8px; } }
"""


# terms of what only the development site shows: left out of the open site's copy
DEV_ONLY_TERMS = {"No specific hazard"}


def build_definitions(page, d):
    import landing
    # the recent-activation ring's window, from the Map's own constant
    n_days = re.search(r"const RECENT_DAYS = (\d+);", landing.LANDING_JS).group(1)
    def t(x):
        return TF(x, n=n_days) if "{n}" in x else (TB(x) if "<" in x else T(x))
    meta = TB("The terms used on the Map and the other pages, in the words the pages use where they "
              "define a term; the rest follows the decision log.")

    def body(skip=()):
        sections = "".join(
            f"<h2>{T(head)}</h2><dl>"
            + "".join(f"<dt>{t(term)}</dt><dd>{t(text)}</dd>" for term, text in terms if term not in skip) + "</dl>"
            for head, terms in GLOSSARY)
        return (f"<div class='defs'><p class='meta'>{meta}</p>"
                f"<h2>{T('How statuses work')}</h2>{landing.status_help_html(open_=True)}"
                f"{sections}</div><style>{CSS}</style>")
    open_skip = set() if landing.GENERAL_ON_OPEN else DEV_ONLY_TERMS
    page(PAGE, TITLE, body(), prod_body=body(open_skip) if open_skip else None)
