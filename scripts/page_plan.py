"""The Plan page (pillar-plan.html) — split out of dashboards.py on 2026-09-30
so the page can be reworked on its own. Shared helpers still live in dashboards."""

import json

import pandas as pd

from dashboards import (LIFE_LABEL, _dash_page, _fmt_usd, _records, _st)  # noqa: F401


def build_plan(page, d):
    pr = d["plan_rows"].copy()
    cur = d["current"]
    live = cur[cur["lifecycle"].isin(["active", "updating"])]
    ag = pr[pr["agency"].notna()]
    n_ag = ag["agency"].nunique()
    cov = d["covered"].merge(cur[["country_iso3", "hazard", "country_name", "lifecycle"]],
                             on=["country_iso3", "hazard"], how="left")
    cov = cov[cov["lifecycle"].isin(["active", "updating"])]
    covered = cov["people_covered"].sum()
    fw_ag = (ag.groupby("agency")[["country_iso3", "hazard"]]
             .apply(lambda x: len(x.drop_duplicates())).sort_values(ascending=False))

    def _agencies(c, h):
        return ", ".join(sorted(set(ag.loc[(ag["country_iso3"] == c) & (ag["hazard"] == h), "agency"])))

    def _budget(c, h):
        v = pr.loc[(pr["country_iso3"] == c) & (pr["hazard"] == h) & pr["agency"].notna(), "amount_usd"].sum()
        return _fmt_usd(v) if v else ""

    def _covered(c, h):
        v = cov.loc[(cov["country_iso3"] == c) & (cov["hazard"] == h), "people_covered"].sum()
        return f"{int(v):,}" if v else ""
    fw_rows = "".join(
        f"<tr><td>{r.country_name} — {r.hazard.replace('_', ' ')}</td>"
        f"<td>{_st(LIFE_LABEL.get(r.lifecycle, r.lifecycle))}</td>"
        f"<td>{_agencies(r.country_iso3, r.hazard)}</td>"
        f"<td class='num'>{_budget(r.country_iso3, r.hazard)}</td>"
        f"<td class='num'>{_covered(r.country_iso3, r.hazard)}</td></tr>"
        for r in live.sort_values("country_name").itertuples())
    panels = f"""
<div class='tiles'>
 <div class='tile'><div class='v'>{len(live)}</div><div class='l'>frameworks with a plan (active or being updated)</div></div>
 <div class='tile'><div class='v'>{n_ag}</div><div class='l'>implementing agencies with a pre-arranged budget line</div></div>
 <div class='tile'><div class='v'>{covered/1e6:,.1f}M</div><div class='l'>people covered by the plans (latest figure per framework)</div></div>
</div>
<div class='grid'>
 <div class='panel'><h3>Pre-arranged budget by agency</h3><canvas id='p1' height='300'></canvas>
   <div class='note'>Latest version of every framework that is active or being updated; from the framework documents' agency split. The sector view is on the <a href='dash-funding.html'>Funding</a> page.</div></div>
 <div class='panel'><h3>Frameworks per agency</h3><canvas id='p3' height='300'></canvas></div>
</div>
<h2>Plans by framework</h2>
<section><input class='filter' placeholder='filter…' oninput='filt(this)'>
<div class='scroll'><table class='data'><thead><tr><th>framework</th><th>status</th><th>agencies</th><th>agency budget</th><th>people covered</th></tr></thead><tbody>{fw_rows}</tbody></table></div></section>
<p class='meta'>Delivery detail (CERF projects, sub-grants, localization, cash, people reached) is on the internal <a href='dash-delivery.html'>delivery dashboard</a>.</p>"""
    data = {
        "ag": json.loads(_records(ag, ["agency", "amount_usd"])),
        "fwag": [{"agency": k, "n": int(v)} for k, v in fw_ag.items()],
    }
    js = """
const byA = groupSum(D.ag, r=>r.agency, r=>r.amount_usd), aKeys = Object.keys(byA).sort((a,b)=>byA[b]-byA[a]).slice(0,18);
mkChart('p1','bar',aKeys,[{label:'pre-arranged',data:aKeys.map(k=>byA[k])}],{extra:{indexAxis:'y'}});
const fa = D.fwag.slice(0,20);
mkChart('p3','bar',fa.map(r=>r.agency),[{label:'frameworks',data:fa.map(r=>r.n),backgroundColor:PAL[2]}],{count:true});"""
    _dash_page(page, "pillar-plan.html", "Plan",
               "<b>The plan block of anticipatory action</b> — who acts and for whom: the "
               "agencies with a pre-arranged budget line, the sectors, and the people the "
               "plans cover. Figures follow the latest version of each framework that is "
               "active or being updated.",
               panels, json.dumps(data, default=str), js)
