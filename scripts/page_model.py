"""The Model page (pillar-model.html) — split out of dashboards.py on 2026-09-30
so the page can be reworked on its own. Shared helpers still live in dashboards."""

import json

import pandas as pd

from dashboards import (LIFE_LABEL, _cal_strip, _dash_page, _records, _st, haz)  # noqa: F401


def build_model(page, d):
    w = d["windows"].copy()
    cur = d["current"]
    live = cur[cur["lifecycle"].isin(["active", "updating", "development"])]
    wl = w[w["is_latest"].fillna(False).astype(bool)
           & w["lifecycle"].isin(["active", "updating", "development"])].copy()
    wl["hz"] = wl["hazard"].map(haz)
    wl["basis"] = wl["basis"].fillna("unspecified")
    n_trig = int(wl["triggered"].fillna(False).astype(bool).sum())
    fc_share = (wl["basis"].str.contains("forecast", case=False).mean() * 100) if len(wl) else 0
    act = d["act_all"].copy()
    act["year"] = act["event_date"].astype(str).str[:4]
    act = act[act["year"].str.match(r"^\d{4}$")].copy()
    act["year"] = act["year"].astype(int)
    act["kind"] = act["event_type"].map(
        lambda t: "framework" if t == "framework_aa" else "ad hoc / early action")
    cal = d["calendar"]
    cal_rows = "".join(
        f"<tr><td>{r.country_name} — {r.hazard.replace('_', ' ')}</td>"
        f"<td>{_st(LIFE_LABEL.get(r.lifecycle, r.lifecycle))}</td>"
        f"<td>{_cal_strip(cal, r.country_iso3, r.hazard)}</td></tr>"
        for r in live.sort_values("country_name").itertuples())

    def _state(r):
        if r.triggered:
            return "triggered" + (f" ({r.triggered_on})" if pd.notna(r.triggered_on) else "")
        return "not triggered"
    win_rows = "".join(
        f"<tr><td>{r.country_name} — {r.hazard.replace('_', ' ')}</td><td>{r.version}</td>"
        f"<td>{r.window_name}</td><td>{r.basis}</td><td>{_state(r)}</td>"
        f"<td class='num'>{f'1-in-{r.return_period:.1f} yr' if pd.notna(r.return_period) else ''}</td>"
        f"<td class='num'>{f'{r.activation_prob*100:.0f}%' if pd.notna(r.activation_prob) else ''}</td>"
        f"<td class='num'>{f'{int(r.n_activations)} in {int(r.analysis_years)} yrs' if pd.notna(r.n_activations) and pd.notna(r.analysis_years) else ''}</td></tr>"
        for r in wl.sort_values(["country_name", "hazard", "window_name"]).itertuples())
    panels = f"""
<div class='tiles'>
 <div class='tile'><div class='v'>{len(live)}</div><div class='l'>frameworks with a model (active, being updated, in development)</div></div>
 <div class='tile'><div class='v'>{len(wl)}</div><div class='l'>trigger windows on the latest versions</div></div>
 <div class='tile'><div class='v'>{n_trig}</div><div class='l'>windows triggered on the latest versions</div></div>
 <div class='tile'><div class='v'>{fc_share:.0f}%</div><div class='l'>of windows are forecast-based</div></div>
</div>
<div class='grid'>
 <div class='panel'><h3>Trigger windows by hazard × basis</h3><canvas id='m1' height='250'></canvas>
   <div class='note'>Latest version of every live framework; basis from the KB trigger registry.</div></div>
 <div class='panel'><h3>Designed return period of the windows</h3><canvas id='m2' height='250'></canvas>
   <div class='note'>From the backtests (1-in-N years); windows without a backtest are not shown.</div></div>
 <div class='panel' style='grid-column:1/-1'><h3>Activations per year — framework triggers vs ad hoc / early action</h3><canvas id='m3' height='250'></canvas></div>
</div>
<h2>Monitoring calendar</h2>
<p class='meta'>Green cells = months the framework is monitored (trigger-window months).</p>
<section><div class='scroll'><table class='data'><thead><tr><th>framework</th><th>status</th><th>monitoring window</th></tr></thead><tbody>{cal_rows}</tbody></table></div></section>
<h2>Trigger windows (latest versions)</h2>
<section><input class='filter' placeholder='filter windows…' oninput='filt(this)'>
<div class='scroll'><table class='data'><thead><tr><th>framework</th><th>version</th><th>window</th><th>basis</th><th>state</th><th>return period</th><th>annual prob.</th><th>backtest</th></tr></thead><tbody>{win_rows}</tbody></table></div></section>"""
    data = {
        "win": json.loads(_records(wl, ["hz", "basis", "return_period", "triggered"])),
        "act": json.loads(_records(
            act.drop_duplicates(["country_iso3", "hazard", "event_date", "event_type"]),
            ["year", "kind"])),
    }
    js = """
const hz = uniqSorted(D.win, r=>r.hz), bases = uniqSorted(D.win, r=>r.basis);
mkChart('m1','bar',hz,bases.map((b,i)=>({label:b, data:hz.map(h=>D.win.filter(r=>r.hz===h&&r.basis===b).length)})),{stacked:true,count:true});
const bins = [['≤ 1-in-3',0,3],['1-in-3 to 5',3,5],['1-in-5 to 10',5,10],['> 1-in-10',10,1e9]];
mkChart('m2','bar',bins.map(b=>b[0]),[{label:'windows',data:bins.map(b=>D.win.filter(r=>r.return_period!=null&&r.return_period>b[1]&&r.return_period<=b[2]).length)}],{count:true});
const yrs = uniqSorted(D.act, r=>r.year), kinds = ['framework','ad hoc / early action'];
mkChart('m3','bar',yrs,kinds.map((k,i)=>({label:k, data:yrs.map(y=>D.act.filter(r=>r.year===y&&r.kind===k).length)})),{stacked:true,count:true});"""
    _dash_page(page, "pillar-model.html", "Model",
               "<b>The model block of anticipatory action</b> — the triggers: what is "
               "monitored, when, on what basis, how often it is designed to fire, and what "
               "actually fired. One row per trigger window of the latest framework versions.",
               panels, json.dumps(data, default=str), js)
