"""Plain-language definition / policy boxes shown at the top of every public page.

DRAFT TEXT FOR REVIEW (2026-09-30): written from the team's own vocabulary (the
aa-methods trigger-design discipline) and the counting rules the site uses; no statistics.
Edit the wording here — every page reads this one place. Keys are page file names.
"""

import html

# the Grand Bargain caucus's outcome document (2024): the definition the Map's box quotes
GB_AA_URL = ("https://interagencystandingcommittee.org/sites/default/files/2024-12/"
             "GB%20AA%20-%20Final%20Caucus%20Outcome%20Document%20-%20New.pdf")

POLICY = {
    # the owner's wording (2026-10-28): the Grand Bargain definition, quoted and linked to its
    # source, then what a framework agrees in advance, each element linked to its page
    "index.html": (
        "What is anticipatory action?",
        "<blockquote class='policy-q'>“Anticipatory action is defined as acting ahead of a predicted "
        "hazardous event to prevent or reduce impacts on lives and livelihoods and humanitarian needs "
        "before they fully unfold. This works best when activities as well as triggers or "
        "decision-making rules are pre-agreed, and decisions are made to guarantee the fast release of "
        "pre-arranged funding.” <cite>— <a href='" + GB_AA_URL + "' target='_blank' rel='noopener'>"
        "Grand Bargain caucus on anticipatory action, 2024</a></cite></blockquote>"
        "<p class='policy-p'>A framework agrees three things in advance: the <b><a href='pillar-model.html'>"
        "trigger model</a></b> that says when to act, the <b><a href='pillar-plan.html'>plan of "
        "activities</a></b> to be carried out, and the <b><a href='dash-funding.html'>pre-arranged "
        "financing</a></b> that is released the moment the trigger is met to enable the activities. "
        "Because these elements are agreed beforehand it is cost-effective, enabling reaching people with "
        "speed to save lives and livelihoods. A <b><a href='pillar-learning.html'>learning</a></b> "
        "component measures against these outcomes to iteratively improve anticipatory action over "
        "time.</p>"
        "<p class='policy-p'>The terms used across the site — statuses, trigger windows, pre-arranged "
        "and released money, people covered and reached — are defined on the "
        "<a href='definitions.html'>Definitions</a> page.</p>"),
    "pillar-model.html": (
        "What is a trigger, and what makes a good one?",
        "A trigger is the pre-agreed condition, from a forecast or an observation, that "
        "activates the framework. A <b>trigger mechanism</b> can hold several specific triggers "
        "with their own <b>windows</b>: for sudden-onset hazards, typically a <b>readiness</b> "
        "trigger with a long lead time followed by an <b>action</b> trigger closer to the shock. "
        "A good trigger is agreed with partners before the season, is set at a level the fund "
        "can afford to meet (its return period), gives enough lead time for the planned "
        "activities, and has been <b>tested against history</b>: would it have activated for "
        "the past shocks it should catch, and stayed quiet in the years it should not?"),
    "pillar-history.html": (
        "Would the triggers have activated in the past?",
        "Each framework's current triggers are tested against decades of historical data: for "
        "every past year (or storm), would they have activated? These <b>simulated activations</b> "
        "show how often a trigger is expected to release money and whether it would have caught "
        "the shocks that mattered. <b>Real activations</b> (when money actually went out) are "
        "marked alongside, so the design can be compared with what happened."),
    "pillar-plan.html": (
        "What makes good anticipatory activities?",
        "Good activities are the ones that can be delivered within the lead time the trigger "
        "gives and that reduce the impacts the forecast warns about: cash before a flood so "
        "families can move assets, livestock feed before the lean season, water treatment "
        "before a cholera peak. They are agreed in advance with the <b>partners</b> who will "
        "deliver them, including government counterparts and national organisations, are "
        "matched to the <b>timing</b> of each trigger window, and are prepared (targeting, "
        "contracts, stocks) so that nothing waits for the activation."),
    "dash-funding.html": (
        "What is pre-arranged financing?",
        "Pre-arranged financing is money committed to a framework before any shock, so it can "
        "be released as soon as the trigger is met. It is a <b>commitment in place</b>, not a flow: "
        "the figures here count each framework's envelope once per year (a past year counts every "
        "framework that was valid at any time in it; this year, those in place today) and never add "
        "it up across years. <b>Released</b> money is what actually went out when a framework "
        "activated; it is drawn from the pre-arranged envelopes, so the two are never added "
        "together. CERF and the Country and Regional Funds both pre-arrange money for "
        "anticipatory action."),
    "pillar-learning.html": (
        "What do we know about anticipatory action?",
        "Every activation is a chance to learn whether acting early worked. Evaluations, "
        "after-action reviews and studies test the core claims of anticipatory action: that it "
        "is faster, more cost-effective and more dignified than responding after the shock, "
        "and that it protects lives, livelihoods and development gains. The map shows headline "
        "findings in the countries they come from; the list below it holds every learning "
        "document, by country and hazard."),
    "media.html": (
        "Anticipatory action in pictures",
        "Stories, videos and photos from activations: what acting ahead looks like for the "
        "people it reaches."),
}


def policy_box(page_name):
    """The box for a page (empty string if none). Marked as draft until the text is agreed."""
    if page_name not in POLICY:
        return ""
    from site_i18n import ATTR, T, TB
    title, body = POLICY[page_name]
    # a <details> box: open on wide screens, folded to its heading on phones (owner, 2026-10-28:
    # "too big" on mobile); without scripts it stays open
    return (f"<details class='policy' open><summary class='policy-h'>{T(title)}"
            f"<span class='policy-draft' {ATTR('title', 'wording under review')}>{T('draft')}</span></summary>"
            f"<div class='policy-b'>{TB(body)}</div></details>"
            "<script>if(matchMedia('(max-width:759px)').matches)"
            "document.currentScript.previousElementSibling.removeAttribute('open');</script>")


POLICY_CSS = """
.policy { background:#f3f7fb; border:1px solid #d5e3f0; border-left:4px solid #1f69b3; border-radius:8px;
          padding:12px 16px; margin:4px 0 14px; max-width:980px; }
.policy-h { font-weight:700; font-size:15px; color:#0f2540; margin-bottom:4px; cursor:pointer; list-style:none; }
.policy-h::-webkit-details-marker { display:none; }
.policy-h::before { content:"\\25B8"; display:inline-block; width:1em; color:#1f69b3; transition:transform .15s; }
.policy[open] > .policy-h::before { transform:rotate(90deg); }
.policy:not([open]) > .policy-h { margin-bottom:0; }
@media (prefers-reduced-motion: reduce) { .policy-h::before { transition:none; } }
.policy-b { font-size:13.5px; line-height:1.55; color:#23364d; }
.policy-b a { color:#1f69b3; }
.policy-q { margin:2px 0 8px; padding:0 0 0 12px; border-left:3px solid #b9cfe6; font-style:italic; color:#23364d; }
.policy-q cite { display:block; font-style:normal; font-size:12.5px; color:#3d5168; margin-top:3px; }
.policy-p { margin:0; }
.policy-draft { font-weight:500; font-size:10.5px; text-transform:uppercase; letter-spacing:.04em; color:#8a5c0a;
                background:#fff4d6; border-radius:4px; padding:1px 6px; margin-left:8px; vertical-align:2px; }
"""
