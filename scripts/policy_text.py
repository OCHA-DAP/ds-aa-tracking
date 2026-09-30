"""Plain-language definition / policy boxes shown at the top of every public page.

DRAFT TEXT FOR REVIEW (2026-09-30): written from the team's own vocabulary (the
aa-methods trigger-design discipline) and the counting rules the site uses; no statistics.
Edit the wording here — every page reads this one place. Keys are page file names.
"""

import html

POLICY = {
    "index.html": (
        "What is anticipatory action?",
        "Anticipatory action means acting before a forecast shock hits, or before its worst "
        "impacts unfold. A <b>framework</b> agrees three things in advance: the <b>trigger</b> "
        "that says when to act, the <b>activities</b> agencies will carry out, and the "
        "<b>pre-arranged financing</b> that is released the moment the trigger is met. "
        "Because the decision and the money are agreed beforehand, help can reach people days "
        "or weeks earlier than a response that waits for the disaster."),
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
        "be released as soon as the trigger is met. It is a <b>commitment in place on a date</b>: "
        "the figures here count each framework's envelope once, as at that date, and never add "
        "it up across years. <b>Released</b> money is what actually went out when a framework "
        "activated; it is drawn from the pre-arranged envelopes, so the two are never added "
        "together. CERF and the country-based and regional pooled funds (CBPFs and RhPFs) both "
        "pre-arrange money for anticipatory action."),
    "dash-donors.html": (
        "How is AA money attributed to donors?",
        "Donors contribute to the pooled funds as a whole, not to anticipatory action "
        "specifically. This page attributes each fund's AA money to its donors in proportion "
        "to what each donor paid into the fund that year. Donors report their AA funding "
        "annually under the Grand Bargain; these figures are meant to support that reporting."),
    "pillar-learning.html": (
        "What do we know about anticipatory action?",
        "Every activation is a chance to learn whether acting early worked. Evaluations, "
        "after-action reviews and studies test the core claims of anticipatory action: that it "
        "is faster, more cost-effective and more dignified than responding after the shock, "
        "and that it protects lives, livelihoods and development gains. This page collects "
        "that evidence by claim, alongside the learning products for each framework."),
    "media.html": (
        "Anticipatory action in pictures",
        "Stories, videos and photos from activations: what acting ahead looks like for the "
        "people it reaches."),
}


def policy_box(page_name):
    """The box for a page (empty string if none). Marked as draft until the text is agreed."""
    if page_name not in POLICY:
        return ""
    title, body = POLICY[page_name]
    return (f"<div class='policy'><div class='policy-h'>{html.escape(title)}"
            f"<span class='policy-draft' title='wording under review'>draft</span></div>"
            f"<div class='policy-b'>{body}</div></div>")


POLICY_CSS = """
.policy { background:#f3f7fb; border:1px solid #d5e3f0; border-left:4px solid #1f69b3; border-radius:8px;
          padding:12px 16px; margin:4px 0 14px; max-width:980px; }
.policy-h { font-weight:700; font-size:15px; color:#0f2540; margin-bottom:4px; }
.policy-b { font-size:13.5px; line-height:1.55; color:#23364d; }
.policy-draft { font-weight:500; font-size:10.5px; text-transform:uppercase; letter-spacing:.04em; color:#8a5c0a;
                background:#fff4d6; border-radius:4px; padding:1px 6px; margin-left:8px; vertical-align:2px; }
"""
