"""Donor shares of anticipatory-action money — dash-donors.html.

Method (the one the hand-built "Donor shares of OCHA AA" workbook used, now derived):
a donor's share of a pooled fund in a fiscal year = what they paid into it that year /
everything the fund received that year (aa.v_contribution, from the OneGMS mirrors).
That share is applied to the AA the fund handled the same year, in two buckets:

- released — allocations drawn by framework activations, from aa.activation_funding;
  the same series the Financing page charts with its default layers
- pre-arranged — framework envelopes per year + AA-tagged CBPF/RhPF allocations
  (funding_series in dashboards.py; same numbers as the Financing page)

plus a third bucket that is not share-based: "build" money — donor earmarks to the
OCHA AA project itself (aa.build_contribution, hand-entered).

Fiscal-year cut: all contributions in year X attach to all AA money in year X. AA money
on a fund with no contribution rows that year (e.g. sheet-era rows on
'cbpf-unspecified') cannot be attributed and is shown as such, never spread.
Everything is computed client-side from the embedded rows so year / fund / donor
filters recompute the shares.

The page also carries the donor-flows view: the Financing page's 'Where the money flows'
Sankey with the donors level on (the same _money_flows rows, framework money only).
"""

import datetime as dt
import json

import pandas as pd

from dashboards import FLOW_JS, _dash_page, _flow_panel, _money_flows, _records, funding_series


def build_donors(page, d):
    pre, act = funding_series(d)
    P = (pre[(pre["kind"] == "prearranged") & (pre["fund_code"] != "all")]
         .groupby(["fund_code", "year"], as_index=False)["amount_usd"].sum())
    A = (act.groupby(["fund_code", "year"], as_index=False)["amount_usd"].sum())
    C = d["contrib"].copy()
    C["fund_code"] = C["fund_code"].fillna("cbpf:" + C["fund_name"].astype(str))
    C = C[C["paid_usd"].fillna(0) > 0]
    # donor type is a CERF-feed attribute; CBPF-only donors get it by name where CERF knows them
    dtype = (C[C["donor_type"].notna()].groupby("donor")["donor_type"].first())
    C["donor_type"] = C["donor"].map(dtype).fillna(
        C["donor"].map(lambda n: "Private" if "rivate" in str(n) or "UNF" in str(n) else "Other"))
    # one row per donor × fund × year (CERF lists every contribution separately)
    C = C.groupby(["fund_code", "fund_type", "fund_name", "donor", "donor_type", "year"],
                  as_index=False)["paid_usd"].sum()
    B = d["build"].copy()
    fund_names = {**dict(zip(C["fund_code"], C["fund_name"])),
                  "cerf": "CERF", "cbpf-unspecified": "CBPF (fund not recorded)",
                  "rhpf-unspecified": "Regional fund (not recorded)",
                  "cbpf": "CBPF (fund not in registry)", "rhpf": "Regional fund (not in registry)"}
    years = sorted(set(P["year"].dropna().astype(int)) | set(A["year"].dropna().astype(int)))
    years = [y for y in years if y >= 2020]
    default_year = min(max(years), dt.date.today().year - 1) if years else dt.date.today().year - 1
    have_data = len(C) > 0
    # donor flows: the Financing page's Sankey rows, donors first (framework money: the same
    # released series as the attribution above)
    flow_rows, flow_years, flow_default, flow_names = _money_flows(d, pre, act)

    panels = """
<div class='fbar'>
 <label>Year <select id='fY'></select></label>
 <label>Fund <select id='fFT'><option value=''>all pooled funds</option><option value='cerf'>CERF</option><option value='cbpf'>CBPFs</option><option value='regional_fund'>regional funds</option></select></label>
 <label>Donor type <select id='fDT'><option value=''>all</option></select></label>
 <label>Donor <select id='fD'><option value=''>all donors (portfolio view)</option></select></label>
 <label id='fNl'>Top <select id='fN'><option>15</option><option selected>20</option><option>30</option><option>50</option></select></label>
 <button class='dl' id='backAll' style='display:none' onclick='goAll()'>← All donors</button>
</div>
<div id='dHead' style='display:none;margin:14px 0 4px'><h2 style='margin:0;display:inline'><span id='dName'></span></h2>
 <span class='meta' style='margin-left:12px'><a href='#' onclick='goAll();return false'>← All donors</a></span></div>
<div class='tiles'>
 <div class='tile'><div class='v' id='tC'>–</div><div class='l' id='tCl'>paid into the funds</div></div>
 <div class='tile'><div class='v' id='tR'>–</div><div class='l' id='tRl'>AA released, attributed to donors</div></div>
 <div class='tile'><div class='v' id='tP'>–</div><div class='l' id='tPl'>AA pre-arranged, attributed to donors</div></div>
 <div class='tile'><div class='v' id='tB'>–</div><div class='l' id='tBl'>build earmarks (OCHA AA project)</div></div>
</div>
<div class='note' id='unattr' style='margin:-6px 0 10px'></div>
<div class='note' id='gbNote' style='display:none;margin:-6px 0 10px'>Donors report their AA funding annually under the <a href='https://interagencystandingcommittee.org/grand-bargain'>Grand Bargain</a>; these are the figures to use.</div>
<div class='grid'>
 <div class='panel'><h3 id='c1t'>Donor shares of AA released</h3><canvas id='c1' height='420'></canvas>
   <div class='note' id='c1n'>Each donor's share of the fund's income that year × the AA the fund released that year (framework activations). Stacked by fund type.</div></div>
 <div class='panel'><h3 id='c2t'>Donor shares of AA pre-arranged</h3><canvas id='c2' height='420'></canvas>
   <div class='note' id='c2n'>Same shares × the pre-arranged envelopes / AA-tagged country and regional fund allocations of that year (the Financing page's annual series).</div></div>
 <div class='panel' style='grid-column:1/-1'><h3 id='c3t'>Attributed AA released by year</h3><canvas id='c3' height='260'></canvas>
   <div class='note' id='c3n'>All years; the largest donors over the period, everyone else as "other". Ignores the year filter.</div></div>
</div>
<div id='dview' style='display:none'>
<h2 id='byfund'>By fund</h2>
<section><p class='meta' id='fundMeta'></p>
<div style='display:flex;gap:10px;align-items:center'><input class='filter' placeholder='filter rows…' oninput='filt(this)'>
<button class='dl' onclick='dlFund()'>⬇ CSV</button></div>
<div class='scroll'><table class='data' id='ftbl'><thead><tr>
<th>fund</th><th>type</th><th>years</th><th>paid by donor</th><th>AA released by fund</th><th>attributed released</th><th>AA pre-arranged by fund</th><th>attributed pre-arranged</th>
</tr></thead><tbody></tbody></table></div></section>
<h2 id='detail'>Fund × year detail</h2>
<section><p class='meta' id='detailMeta'></p>
<div style='display:flex;gap:10px;align-items:center'><input class='filter' placeholder='filter rows…' oninput='filt(this)'>
<button class='dl' onclick='dlDetail()'>⬇ CSV</button></div>
<div class='scroll'><table class='data' id='dtbl'><thead><tr>
<th>fund</th><th>year</th><th>paid by donor</th><th>fund income</th><th>share</th><th>AA released by fund</th><th>attributed released</th><th>AA pre-arranged by fund</th><th>attributed pre-arranged</th>
</tr></thead><tbody></tbody></table></div></section>
</div>
<div id='pview'>
<h2 id='flows'>Donor flows</h2>
<p class='meta'>Donors → funds → agencies (→ partner types): each donor's share of a fund's income that year, applied to the fund's AA money and followed on to the agencies and, for released money, the partners they sub-grant to. Framework money, as in the shares above; the <a href='dash-funding.html'>Financing page</a> shows the same chart starting at the funds. The fund filter applies; the year, donor-type and donor filters do not (the chart has its own year).</p>
""" + _flow_panel(donors_on=True, donor_toggle=False) + """
<h2>All donors</h2>
<section><p class='meta'>Pick a donor in the filter bar (or click a name) for that donor's view: their share of each fund, attributed AA by fund and by year, and a fund × year table — the workbook's per-donor tab.</p>
<div style='display:flex;gap:10px;align-items:center'>
<input class='filter' placeholder='filter rows…' oninput='filt(this)'>
<button class='dl' onclick='dlTable()'>⬇ CSV</button></div>
<div class='scroll'><table class='data' id='tbl'><thead><tr>
<th>donor</th><th>type</th><th>paid to CERF</th><th>paid to country and regional funds</th><th>share of CERF</th><th>released via CERF</th><th>released via country and regional funds</th><th>released total</th><th>pre-arranged via CERF</th><th>pre-arranged via country and regional funds</th><th>build</th>
</tr></thead><tbody></tbody></table></div></section>
</div>"""
    if not have_data:
        panels = ("<div class='card' style='border-color:#e6a23c'><b>No contribution data in this "
                  "snapshot.</b> The OneGMS contribution mirror (aa.v_contribution) was not part "
                  "of the data snapshot this build used; the next nightly snapshot will include "
                  "it.</div>" + panels)

    data = {
        "C": json.loads(_records(C, ["fund_code", "fund_type", "donor", "donor_type", "year",
                                     "paid_usd"])),
        "P": json.loads(_records(P)),
        "A": json.loads(_records(A)),
        "B": json.loads(_records(B, ["donor", "year", "amount_usd"])),
        "FN": fund_names,
        "years": years,
        "defaultYear": default_year,
        "flow": flow_rows, "flowYears": flow_years, "flowDefault": flow_default,
        "fundNames": flow_names,
    }
    js = r"""
const FT = {cerf:'CERF', cbpf:'CBPF', regional_fund:'regional fund'};
const ftOf = fc => fc==='cerf' ? 'cerf' : (fc||'').startsWith('rhpf') ? 'regional_fund' : 'cbpf';
const pct = v => (100*v).toFixed(v>=0.1?1:2)+'%';
const esc = s => String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;');
// donor view: to the dollar, thousands separators (the portfolio tiles keep money()'s $1.2M)
const dollars = v => v==null ? '' : (v<0?'-':'')+'$'+Math.round(Math.abs(v)).toLocaleString('en-US');
const fundLabel = fc => D.FN[fc]||fc;
const BK = {rel:'#3b3f6b', pre:'#9aa3c7'};   // released / pre-arranged buckets in the donor view
const slug = s => String(s).replace(/[^A-Za-z0-9]+/g,'_').replace(/^_+|_+$/g,'');
D.years.forEach(y=>fY.add(new Option(y,y))); fY.add(new Option('all years','all'));
// pre-arranged money is a STOCK (in place on a date), released money a FLOW (per year): released adds up
// across years, pre-arranged never does — 'all years' shows it as at the latest year instead
const PREY = Math.max(...D.P.map(r=>r.year).filter(yy=>yy <= new Date().getFullYear()));
fY.value = 'all';
uniqSorted(D.C, r=>r.donor_type).forEach(t=>fDT.add(new Option(t,t)));
uniqSorted(D.C.concat(D.B), r=>r.donor).forEach(n=>fD.add(new Option(n,n)));

// shares for one (fund, year): every donor row of that fund-year, with the fund's AA buckets
function attribute(yearSel, ftSel){
  const inYear = r => yearSel==='all' || r.year===+yearSel;
  const inFT = r => !ftSel || ftOf(r.fund_code)===ftSel;
  const den = {}, aa = {};
  D.C.filter(r=>inYear(r)&&inFT(r)).forEach(r=>{ const k=r.fund_code+'|'+r.year; den[k]=(den[k]||0)+r.paid_usd; });
  D.A.filter(r=>inYear(r)&&inFT(r)).forEach(r=>{ const k=r.fund_code+'|'+r.year; (aa[k]??={rel:0,pre:0}).rel += r.amount_usd||0; });
  D.P.filter(r=>inYear(r)&&inFT(r)).forEach(r=>{ const k=r.fund_code+'|'+r.year; (aa[k]??={rel:0,pre:0}).pre += r.amount_usd||0; });
  const rows = D.C.filter(r=>inYear(r)&&inFT(r)).map(r=>{ const k=r.fund_code+'|'+r.year;
    const share = r.paid_usd/den[k], b = aa[k]||{rel:0,pre:0};
    return {...r, ft:ftOf(r.fund_code), fundIncome:den[k], share, fundRel:b.rel, fundPre:b.pre, rel:share*b.rel, pre:share*b.pre}; });
  const un = {rel:0,pre:0,keys:[]};
  Object.entries(aa).forEach(([k,b])=>{ if(!den[k]){ un.rel+=b.rel; un.pre+=b.pre; un.keys.push(k); } });
  return {rows, un};
}
function byDonor(rows, dtSel){
  const m = {};
  rows.filter(r=>!dtSel||r.donor_type===dtSel).forEach(r=>{
    const o = (m[r.donor] ??= {donor:r.donor, type:r.donor_type, paidCerf:0, paidCbpf:0, shareCerf:null,
      relCerf:0, relCbpf:0, relReg:0, preCerf:0, preCbpf:0, preReg:0, build:0});
    if(r.ft==='cerf'){ o.paidCerf+=r.paid_usd; o.shareCerf=(o.shareCerf||0)+r.share; o.relCerf+=r.rel; o.preCerf+=r.pre; }
    else if(r.ft==='cbpf'){ o.paidCbpf+=r.paid_usd; o.relCbpf+=r.rel; o.preCbpf+=r.pre; }
    else { o.paidCbpf+=r.paid_usd; o.relReg+=r.rel; o.preReg+=r.pre; } });
  return m;
}
// re-format a chart mkChart() built with money(): value-axis ticks and tooltips through f
function fmtChart(ch, horiz, f){
  const ax = horiz ? ch.options.scales.x : ch.options.scales.y;
  ax.ticks.callback = v=>f(v);
  ch.options.plugins.tooltip.callbacks.label = c=>{ const v = horiz?c.parsed.x:(c.parsed.y??c.parsed); return ` ${c.dataset.label??''}: ${f(v)}`; };
  ch.update(); }
// CSV: exact values — numbers as written (2 decimals), never rounded to millions
const csvNum = (v, dp=2) => v==null || v==='' ? '' : typeof v==='number' ? v.toFixed(dp) : String(v);
function csvDownload(name, header, rows){
  const e = v => v==null ? '' : /[",\n]/.test(String(v)) ? '"'+String(v).replace(/"/g,'""')+'"' : String(v);
  const csv = [header.join(',')].concat(rows.map(r=>r.map(e).join(','))).join('\n');
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
  a.download = name; a.click(); URL.revokeObjectURL(a.href); }
function setView(dn){
  [dview, backAll, gbNote, dHead].forEach(el=>el.style.display = dn?'':'none');
  [pview, unattr, fNl].forEach(el=>el.style.display = dn?'none':'');
  dName.textContent = dn; }
function draw(){
  const y = fY.value, ft = fFT.value, dtSel = fDT.value, N = +fN.value, dn = fD.value;
  const {rows, un} = attribute(y, ft);
  setView(dn);
  if(dn){ drawDonor(dn, y, ft, rows); return; }
  const m = byDonor(rows, dtSel);
  D.B.filter(r=>y==='all'||r.year===+y).forEach(r=>{ if(m[r.donor]) m[r.donor].build += r.amount_usd||0;
    else if(!dtSel) m[r.donor] = {donor:r.donor, type:'', paidCerf:0, paidCbpf:0, shareCerf:null, relCerf:0, relCbpf:0, relReg:0, preCerf:0, preCbpf:0, preReg:0, build:r.amount_usd||0}; });
  if(y==='all'){ const mP = byDonor(attribute(String(PREY), ft).rows, dtSel);
    Object.values(m).forEach(o=>{ const q = mP[o.donor]; o.preCerf = q?q.preCerf:0; o.preCbpf = q?q.preCbpf:0; o.preReg = q?q.preReg:0; }); }
  const L = Object.values(m);
  const sum = f => L.reduce((s,o)=>s+f(o),0);
  tC.textContent = money(sum(o=>o.paidCerf+o.paidCbpf));
  tCl.textContent = 'paid into ' + (ft?FT[ft]+'s':'the pooled funds') + (y==='all'?' 2020→':' in '+y);
  tR.textContent = money(sum(o=>o.relCerf+o.relCbpf+o.relReg)); tRl.textContent = 'AA released, attributed to donors';
  tP.textContent = money(sum(o=>o.preCerf+o.preCbpf+o.preReg)); tPl.textContent = y==='all' ? `AA pre-arranged, attributed to donors, as at ${PREY} (a stock: never summed across years)` : 'AA pre-arranged, attributed to donors';
  tB.textContent = money(sum(o=>o.build)); tBl.textContent = 'build earmarks (OCHA AA project)';
  c1t.textContent = 'Donor shares of AA released'; c1n.textContent = "Each donor's share of the fund's income that year × the AA the fund released that year (framework activations). Stacked by fund type.";
  c2t.textContent = 'Donor shares of AA pre-arranged' + (y==='all' ? ` — as at ${PREY}` : ''); c2n.textContent = "Same shares × the pre-arranged envelopes / AA-tagged country and regional fund allocations of that year (the Financing page's annual series)." + (y==='all' ? ' Pre-arranged money is in place on a date, so it is shown for the latest year rather than added up over years.' : '');
  c3t.textContent = 'Attributed AA released by year'; c3n.textContent = 'All years; the largest donors over the period, everyone else as "other". Ignores the year filter.';
  // pre-arranged is a stock: under 'all years' the unattributable part is as at PREY, not summed
  const unPre = y==='all' ? attribute(String(PREY), ft).un.pre : un.pre;
  unattr.innerHTML = (un.rel||unPre) ? `Not attributable (AA money on a fund with no contribution rows that year — ${un.keys.map(k=>esc(D.FN[k.split('|')[0]]||k.split('|')[0])+' '+k.split('|')[1]).join(', ')}): released ${money(un.rel)}, pre-arranged ${money(unPre)}${y==='all'?` (as at ${PREY})`:''}. Shown here, never spread across donors.` : 'Every dollar of AA in this selection sits on a fund with known donors.';
  const stack = (id, key) => { const top = L.filter(o=>o[key+'Cerf']+o[key+'Cbpf']+o[key+'Reg']>0)
      .sort((a,b)=>(b[key+'Cerf']+b[key+'Cbpf']+b[key+'Reg'])-(a[key+'Cerf']+a[key+'Cbpf']+a[key+'Reg'])).slice(0,N);
    mkChart(id,'bar',top.map(o=>o.donor),[
      {label:'via CERF', data:top.map(o=>o[key+'Cerf']), backgroundColor:FUND_COLORS.cerf},
      {label:'via CBPFs', data:top.map(o=>o[key+'Cbpf']), backgroundColor:FUND_COLORS.cbpf},
      {label:'via regional funds', data:top.map(o=>o[key+'Reg']), backgroundColor:FUND_COLORS.regional_fund}
    ].filter(d=>d.data.some(v=>v)), {stacked:true, allLabels:true, extra:{indexAxis:'y'}}); };
  stack('c1','rel'); stack('c2','pre');
  // by year, all years
  const yrs = D.years, per = {};
  yrs.forEach(yy=>{ const mm = byDonor(attribute(String(yy), ft).rows, dtSel);
    Object.values(mm).forEach(o=>{ (per[o.donor]??={})[yy] = o.relCerf+o.relCbpf+o.relReg; }); });
  const tot = Object.entries(per).map(([n,v])=>[n, Object.values(v).reduce((s,x)=>s+x,0)]).sort((a,b)=>b[1]-a[1]);
  const top8 = tot.slice(0,8).map(x=>x[0]);
  const ds = top8.map((n,i)=>({label:n, data:yrs.map(yy=>per[n][yy]||0), backgroundColor:PAL[i%PAL.length]}));
  ds.push({label:'other', data:yrs.map(yy=>tot.slice(8).reduce((s,[n])=>s+(per[n][yy]||0),0)), backgroundColor:'#c8c8c4'});
  mkChart('c3','bar',yrs,ds,{stacked:true});
  // main table
  L.sort((a,b)=>(b.relCerf+b.relCbpf+b.relReg+b.preCerf+b.preCbpf+b.preReg+b.build)-(a.relCerf+a.relCbpf+a.relReg+a.preCerf+a.preCbpf+a.preReg+a.build));
  window._L = L;
  document.querySelector('#tbl tbody').innerHTML = L.map(o=>`<tr><td><a href='#donor=${encodeURIComponent(o.donor)}'>${esc(o.donor)}</a></td><td>${esc(o.type)}</td>
    <td>${money(o.paidCerf)}</td><td>${money(o.paidCbpf)}</td><td>${o.shareCerf==null?'':pct(o.shareCerf)}</td>
    <td>${money(o.relCerf)}</td><td>${money(o.relCbpf+o.relReg)}</td><td><b>${money(o.relCerf+o.relCbpf+o.relReg)}</b></td>
    <td>${money(o.preCerf)}</td><td>${money(o.preCbpf+o.preReg)}</td><td>${money(o.build)}</td></tr>`).join('');
}
// ---- one donor's view: their share of each fund, attributed AA by fund and by year, fund × year rows
function drawDonor(dn, y, ft, rows){
  const inYear = r => y==='all' || r.year===+y, inFT = r => !ft || ftOf(r.fund_code)===ft;
  const dr = rows.filter(r=>r.donor===dn);                       // donor × fund × year in the selection
  const det = dr.filter(r=>r.fundRel||r.fundPre).sort((a,b)=>(b.year-a.year)||(b.paid_usd-a.paid_usd));
  const sum = (arr,f) => arr.reduce((s,r)=>s+(f(r)||0),0);
  const PY = y==='all' ? PREY : +y, preRows = det.filter(r=>r.year===PY);   // pre-arranged: one year's stock
  const rel = sum(det,r=>r.rel), pre = sum(preRows,r=>r.pre);
  const build = sum(D.B.filter(r=>r.donor===dn && inYear(r)), r=>r.amount_usd);
  const totRel = sum(D.A.filter(r=>inYear(r)&&inFT(r)), r=>r.amount_usd), totPre = sum(D.P.filter(r=>r.year===PY&&inFT(r)), r=>r.amount_usd);
  const when = y==='all' ? '2020→' : 'in '+y, scope = ft ? FT[ft]+'s' : 'the pooled funds';
  tC.textContent = dollars(rel); tCl.textContent = `AA released, attributed to ${dn} ${when}`;
  tR.textContent = dollars(pre); tRl.textContent = `AA pre-arranged, attributed to ${dn}, as at ${PY}` + (y==='all' ? ' (not summed across years)' : '');
  tP.textContent = dollars(build); tPl.textContent = `build earmarks to the OCHA AA project ${when}`;
  tB.textContent = totRel ? pct(rel/totRel) : '–'; tBl.textContent = `share of all AA released via ${scope} ${when}` + (totPre ? ` · ${pct(pre/totPre)} of pre-arranged as at ${PY}` : '');
  // chart 1: share of each fund's income, latest year in the selection the donor paid in
  const y1 = y==='all' ? Math.max(-Infinity, ...dr.map(r=>r.year)) : +y;
  const s1 = dr.filter(r=>r.year===y1).sort((a,b)=>b.share-a.share);
  c1t.textContent = `${dn}: share of each fund's income${isFinite(y1)?', '+y1:''}`;
  c1n.textContent = "Paid by the donor ÷ everything the fund received that fiscal year (cash basis, pledges excluded)." + (y==='all' ? ' Latest year the donor paid into a fund in this selection; the tables below cover every year.' : '');
  fmtChart(mkChart('c1','bar', s1.map(r=>fundLabel(r.fund_code)),
    [{label:'share of fund income', data:s1.map(r=>100*r.share), backgroundColor:s1.map(r=>FUND_COLORS[r.ft])}],
    {allLabels:true, extra:{indexAxis:'y'}}), true, v=>(+v).toFixed(1)+'%');
  // chart 2 + by-fund table: attributed released / pre-arranged per fund over the selected years
  const byF = {};
  det.forEach(r=>{ const o = byF[r.fund_code] ??= {fund_code:r.fund_code, ft:r.ft, years:new Set(), paid:0, fundRel:0, fundPre:0, rel:0, pre:0};
    o.years.add(r.year); o.paid+=r.paid_usd; o.fundRel+=r.fundRel; o.rel+=r.rel;
    if(r.year===PY){ o.fundPre+=r.fundPre; o.pre+=r.pre; } });
  const F = Object.values(byF).sort((a,b)=>(b.rel+b.pre)-(a.rel+a.pre));
  c2t.textContent = `${dn}: attributed AA by fund${y==='all'?', all years':', '+y}`;
  c2n.textContent = `The donor's share of each fund's income × the AA that fund released (summed over the selected years) and pre-arranged (as at ${PY}: a stock, never summed).`;
  fmtChart(mkChart('c2','bar', F.map(o=>fundLabel(o.fund_code)),
    [{label:'AA released', data:F.map(o=>o.rel), backgroundColor:BK.rel}, {label:'AA pre-arranged', data:F.map(o=>o.pre), backgroundColor:BK.pre}],
    {allLabels:true, extra:{indexAxis:'y'}}), true, dollars);
  // chart 3: by year (every year; the fund filter applies, the year filter does not)
  const perY = {};
  attribute('all', ft).rows.filter(r=>r.donor===dn).forEach(r=>{ const o = perY[r.year] ??= {rel:0,pre:0}; o.rel+=r.rel; o.pre+=r.pre; });
  c3t.textContent = `${dn}: attributed AA by year`;
  c3n.textContent = 'Every year, released and pre-arranged — the annual figures the donor reports under the Grand Bargain. Ignores the year filter; the fund filter applies.';
  fmtChart(mkChart('c3','bar', D.years,
    [{label:'AA released', data:D.years.map(yy=>perY[yy]?.rel||0), backgroundColor:BK.rel},
     {label:'AA pre-arranged', data:D.years.map(yy=>perY[yy]?.pre||0), backgroundColor:BK.pre}], {}), false, dollars);
  // tables
  const yrsOf = o => [...o.years].sort().join(', ');
  fundMeta.textContent = `${dn}, ${y==='all'?'2020→':y}: funds the donor paid into that handled AA in those years, all years combined.`;
  document.querySelector('#ftbl tbody').innerHTML = F.map(o=>`<tr><td>${esc(fundLabel(o.fund_code))}</td><td>${FT[o.ft]}</td><td>${yrsOf(o)}</td>
    <td>${dollars(o.paid)}</td><td>${dollars(o.fundRel)}</td><td><b>${dollars(o.rel)}</b></td><td>${dollars(o.fundPre)}</td><td><b>${dollars(o.pre)}</b></td></tr>`).join('')
    + (F.length ? `<tr><td><b>total</b></td><td></td><td></td><td>${dollars(sum(F,o=>o.paid))}</td><td></td><td><b>${dollars(rel)}</b></td><td></td><td><b>${dollars(pre)}</b></td></tr>` : '<tr><td colspan=8>No AA on a fund this donor paid into in the selection.</td></tr>');
  detailMeta.textContent = `${dn}, ${y==='all'?'2020→':y}: one row per fund × fiscal year — share = paid / fund income that year; attributed = share × the fund's AA that year.`;
  document.querySelector('#dtbl tbody').innerHTML = det.map(r=>`<tr><td>${esc(fundLabel(r.fund_code))}</td><td>${r.year}</td>
    <td>${dollars(r.paid_usd)}</td><td>${dollars(r.fundIncome)}</td><td>${pct(r.share)}</td>
    <td>${dollars(r.fundRel)}</td><td><b>${dollars(r.rel)}</b></td><td>${dollars(r.fundPre)}</td><td><b>${dollars(r.pre)}</b></td></tr>`).join('')
    + (det.length ? `<tr><td><b>total</b></td><td></td><td>${dollars(sum(det,r=>r.paid_usd))}</td><td></td><td></td><td></td><td><b>${dollars(rel)}</b></td><td></td><td>${y==='all' ? `<span class='muted' title='pre-arranged money is a stock: summing it over years would count the same envelope several times'>as at ${PY}: </span>` : ''}<b>${dollars(pre)}</b></td></tr>` : '');
  window._F = F; window._det = det;
}
// ---- exports (exact dollars, 2 decimals; shares as percent, 4 decimals)
function dlTable(){ const cols = ['donor','type','paidCerf','paidCbpf','shareCerf','relCerf','relCbpf','relReg','preCerf','preCbpf','preReg','build'];
  csvDownload(`donor_shares_${fY.value}.csv`, cols.map(c=>c==='shareCerf'?'shareCerf_pct':c),
    (window._L||[]).map(o=>cols.map(c=>c==='shareCerf' ? (o[c]==null?'':csvNum(100*o[c],4)) : csvNum(o[c])))); }
function dlDetail(){ const dn = fD.value;
  csvDownload(`donor_${slug(dn)}_${fY.value}.csv`,
    ['donor','fund_code','fund','fund_type','year','paid_usd','fund_income_usd','share_pct','fund_aa_released_usd','attributed_released_usd','fund_aa_prearranged_usd','attributed_prearranged_usd'],
    (window._det||[]).map(r=>[dn, r.fund_code, fundLabel(r.fund_code), FT[r.ft], r.year, csvNum(r.paid_usd), csvNum(r.fundIncome), csvNum(100*r.share,4),
      csvNum(r.fundRel), csvNum(r.rel), csvNum(r.fundPre), csvNum(r.pre)])); }
function dlFund(){ const dn = fD.value;
  csvDownload(`donor_${slug(dn)}_by_fund_${fY.value}.csv`,
    ['donor','fund_code','fund','fund_type','years','paid_usd','fund_aa_released_usd','attributed_released_usd','fund_aa_prearranged_usd','attributed_prearranged_usd'],
    (window._F||[]).map(o=>[dn, o.fund_code, fundLabel(o.fund_code), FT[o.ft], [...o.years].sort().join(' '), csvNum(o.paid), csvNum(o.fundRel), csvNum(o.rel), csvNum(o.fundPre), csvNum(o.pre)])); }
// ---- routing: the donor lives in location.hash (#donor=Name) so the back button and links work
const donorFromHash = () => { const m = /[#&]donor=([^&]*)/.exec(location.hash); try { return m ? decodeURIComponent(m[1]) : ''; } catch(e){ return ''; } };
function syncFromHash(){ const dn = donorFromHash(); fD.value = dn; if(fD.value!==dn) fD.value = ''; draw(); }
function goAll(){ fD.value = ''; fD.dispatchEvent(new Event('change')); }
fD.addEventListener('change', ()=>{ const h = fD.value ? '#donor='+encodeURIComponent(fD.value) : '';
  if(h !== location.hash) location.hash = h; else draw(); });     // hashchange → syncFromHash → draw
[fY,fFT,fDT,fN].forEach(el=>el.addEventListener('change',draw));
window.addEventListener('hashchange', syncFromHash);
syncFromHash();""" + FLOW_JS + """
// donor flows: donors first; the fund filter keeps its funds (fu: c CERF, p CBPF, r regional fund)
const FU = {c:'cerf', p:'cbpf', r:'regional_fund'};
window._flowDraw = mountFlow({label:'AA money from donors through funds and agencies to partners',
  keep: r=>!fFT.value || FU[r.fu]===fFT.value});
fFT.addEventListener('change', ()=>window._flowDraw());"""
    _dash_page(page, "dash-donors.html", "Donor shares of AA",
               "<b>Who funded the anticipatory action.</b> A donor's share of a pooled fund's "
               "income in a fiscal year (their contributions ÷ everything the fund received, "
               "from the OneGMS contribution mirrors), applied to the AA that fund released and "
               "pre-arranged the same year — the Financing page's own series, so the totals agree. "
               "Build money (earmarks to the OCHA AA project) is direct, not share-based. "
               "Cash basis: contributions received in the year, pledges excluded. "
               "The donor flows, further down, follow that money on to the agencies and "
               "partners. <a href='dash-funding.html'>← Financing</a>",
               panels, json.dumps(data, default=str), js)
