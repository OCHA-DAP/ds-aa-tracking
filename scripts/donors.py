"""Donor shares of anticipatory-action money — dash-donors.html.

Method (the one the hand-built "Donor shares of OCHA AA" workbook used, now derived):
a donor's share of a pooled fund in a fiscal year = what they paid into it that year /
everything the fund received that year (aa.v_contribution, from the OneGMS mirrors).
That share is applied to the AA the fund handled the same year, in two buckets:

- released — allocations drawn by activations (framework + ad hoc + EA), from
  aa.activation_funding; the same series the Funding page charts
- pre-arranged — framework envelopes per year + AA-tagged CBPF/RhPF allocations
  (funding_series in dashboards.py; same numbers as the Funding page)

plus a third bucket that is not share-based: "build" money — donor earmarks to the
OCHA AA project itself (aa.build_contribution, hand-entered).

Fiscal-year cut: all contributions in year X attach to all AA money in year X. AA money
on a fund with no contribution rows that year (e.g. sheet-era rows on
'cbpf-unspecified') cannot be attributed and is shown as such, never spread.
Everything is computed client-side from the embedded rows so year / fund / donor
filters recompute the shares.
"""

import datetime as dt
import json

import pandas as pd

from dashboards import _dash_page, _records, funding_series


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

    panels = """
<div class='fbar'>
 <label>Year <select id='fY'></select></label>
 <label>Fund <select id='fFT'><option value=''>all pooled funds</option><option value='cerf'>CERF</option><option value='cbpf'>CBPFs</option><option value='regional_fund'>regional funds</option></select></label>
 <label>Donor type <select id='fDT'><option value=''>all</option></select></label>
 <label>Donor <select id='fD'><option value=''>— pick one for the detail table —</option></select></label>
 <label>Top <select id='fN'><option>15</option><option selected>20</option><option>30</option><option>50</option></select></label>
</div>
<div class='tiles'>
 <div class='tile'><div class='v' id='tC'>–</div><div class='l' id='tCl'>paid into the funds</div></div>
 <div class='tile'><div class='v' id='tR'>–</div><div class='l'>AA released, attributed to donors</div></div>
 <div class='tile'><div class='v' id='tP'>–</div><div class='l'>AA pre-arranged, attributed to donors</div></div>
 <div class='tile'><div class='v' id='tB'>–</div><div class='l'>build earmarks (OCHA AA project)</div></div>
</div>
<div class='note' id='unattr' style='margin:-6px 0 10px'></div>
<div class='grid'>
 <div class='panel'><h3>Donor shares of AA released</h3><canvas id='c1' height='420'></canvas>
   <div class='note'>Each donor's share of the fund's income that year × the AA the fund released that year (activations: framework, ad hoc, EA). Stacked by fund type.</div></div>
 <div class='panel'><h3>Donor shares of AA pre-arranged</h3><canvas id='c2' height='420'></canvas>
   <div class='note'>Same shares × the pre-arranged envelopes / AA-tagged CBPF allocations of that year (the Funding page's annual series).</div></div>
 <div class='panel' style='grid-column:1/-1'><h3>Attributed AA released by year</h3><canvas id='c3' height='260'></canvas>
   <div class='note'>All years; the largest donors over the period, everyone else as "other". Ignores the year filter.</div></div>
</div>
<h2 id='detail'>Donor detail</h2>
<section><p class='meta' id='detailMeta'>Pick a donor in the filter bar: one row per fund they paid into that handled AA that year — the workbook's per-donor tab.</p>
<div class='scroll'><table class='data' id='dtbl'><thead><tr>
<th>fund</th><th>paid by donor</th><th>fund income</th><th>share</th><th>AA released by fund</th><th>donor's share</th><th>AA pre-arranged by fund</th><th>donor's share</th>
</tr></thead><tbody></tbody></table></div></section>
<h2>All donors</h2>
<section><div style='display:flex;gap:10px;align-items:center'>
<input class='filter' placeholder='filter rows…' oninput='filt(this)'>
<button class='dl' onclick='dlTable()'>⬇ CSV</button></div>
<div class='scroll'><table class='data' id='tbl'><thead><tr>
<th>donor</th><th>type</th><th>paid to CERF</th><th>paid to CBPFs/RhPFs</th><th>share of CERF</th><th>released via CERF</th><th>released via CBPFs</th><th>released total</th><th>pre-arranged via CERF</th><th>pre-arranged via CBPFs</th><th>build</th>
</tr></thead><tbody></tbody></table></div></section>"""
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
    }
    js = r"""
const FT = {cerf:'CERF', cbpf:'CBPF', regional_fund:'regional fund'};
const ftOf = fc => fc==='cerf' ? 'cerf' : (fc||'').startsWith('rhpf') ? 'regional_fund' : 'cbpf';
const pct = v => (100*v).toFixed(v>=0.1?1:2)+'%';
const esc = s => String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;');
D.years.forEach(y=>fY.add(new Option(y,y))); fY.add(new Option('all years','all'));
fY.value = String(D.defaultYear);
uniqSorted(D.C, r=>r.donor_type).forEach(t=>fDT.add(new Option(t,t)));
uniqSorted(D.C, r=>r.donor).forEach(n=>fD.add(new Option(n,n)));

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
function draw(){
  const y = fY.value, ft = fFT.value, dtSel = fDT.value, N = +fN.value;
  const {rows, un} = attribute(y, ft);
  const m = byDonor(rows, dtSel);
  D.B.filter(r=>y==='all'||r.year===+y).forEach(r=>{ if(m[r.donor]) m[r.donor].build += r.amount_usd||0;
    else if(!dtSel) m[r.donor] = {donor:r.donor, type:'', paidCerf:0, paidCbpf:0, shareCerf:null, relCerf:0, relCbpf:0, relReg:0, preCerf:0, preCbpf:0, preReg:0, build:r.amount_usd||0}; });
  const L = Object.values(m);
  const sum = f => L.reduce((s,o)=>s+f(o),0);
  tC.textContent = money(sum(o=>o.paidCerf+o.paidCbpf));
  tCl.textContent = 'paid into ' + (ft?FT[ft]+'s':'the pooled funds') + (y==='all'?' 2020→':' in '+y);
  tR.textContent = money(sum(o=>o.relCerf+o.relCbpf+o.relReg));
  tP.textContent = money(sum(o=>o.preCerf+o.preCbpf+o.preReg));
  tB.textContent = money(sum(o=>o.build));
  unattr.innerHTML = (un.rel||un.pre) ? `Not attributable (AA money on a fund with no contribution rows that year — ${un.keys.map(k=>esc(D.FN[k.split('|')[0]]||k.split('|')[0])+' '+k.split('|')[1]).join(', ')}): released ${money(un.rel)}, pre-arranged ${money(un.pre)}. Shown here, never spread across donors.` : 'Every dollar of AA in this selection sits on a fund with known donors.';
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
  document.querySelector('#tbl tbody').innerHTML = L.map(o=>`<tr><td>${esc(o.donor)}</td><td>${esc(o.type)}</td>
    <td>${money(o.paidCerf)}</td><td>${money(o.paidCbpf)}</td><td>${o.shareCerf==null?'':pct(o.shareCerf)}</td>
    <td>${money(o.relCerf)}</td><td>${money(o.relCbpf+o.relReg)}</td><td><b>${money(o.relCerf+o.relCbpf+o.relReg)}</b></td>
    <td>${money(o.preCerf)}</td><td>${money(o.preCbpf+o.preReg)}</td><td>${money(o.build)}</td></tr>`).join('');
  // detail
  const dn = fD.value;
  const det = rows.filter(r=>r.donor===dn && (r.fundRel||r.fundPre)).sort((a,b)=>(b.year-a.year)||(b.paid_usd-a.paid_usd));
  detailMeta.textContent = dn ? `${dn}${y==='all'?', 2020→':', '+y}: one row per fund paid into that handled AA that year — share = paid / fund income that fiscal year.` : 'Pick a donor in the filter bar: one row per fund they paid into that handled AA that year — the workbook\'s per-donor tab.';
  document.querySelector('#dtbl tbody').innerHTML = det.map(r=>`<tr><td>${esc(D.FN[r.fund_code]||r.fund_code)}${y==='all'?' · '+r.year:''}</td>
    <td>${money(r.paid_usd)}</td><td>${money(r.fundIncome)}</td><td>${pct(r.share)}</td>
    <td>${money(r.fundRel)}</td><td><b>${money(r.rel)}</b></td><td>${money(r.fundPre)}</td><td><b>${money(r.pre)}</b></td></tr>`).join('')
    + (det.length ? `<tr><td><b>total</b></td><td>${money(det.reduce((s,r)=>s+r.paid_usd,0))}</td><td></td><td></td><td></td><td><b>${money(det.reduce((s,r)=>s+r.rel,0))}</b></td><td></td><td><b>${money(det.reduce((s,r)=>s+r.pre,0))}</b></td></tr>` : '');
}
function dlTable(){ const cols = ['donor','type','paidCerf','paidCbpf','shareCerf','relCerf','relCbpf','relReg','preCerf','preCbpf','preReg','build'];
  const e = v => v==null ? '' : /[",\n]/.test(String(v)) ? '"'+String(v).replace(/"/g,'""')+'"' : String(v);
  const csv = [cols.join(',')].concat((window._L||[]).map(o=>cols.map(c=>e(typeof o[c]==='number'?Math.round(o[c]):o[c])).join(','))).join('\n');
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv],{type:'text/csv'}));
  a.download = `donor_shares_${fY.value}.csv`; a.click(); URL.revokeObjectURL(a.href); }
[fY,fFT,fDT,fD,fN].forEach(el=>el.addEventListener('change',draw));
draw();"""
    _dash_page(page, "dash-donors.html", "Donor shares of AA",
               "<b>Who funded the anticipatory action.</b> A donor's share of a pooled fund's "
               "income in a fiscal year (their contributions ÷ everything the fund received, "
               "from the OneGMS contribution mirrors), applied to the AA that fund released and "
               "pre-arranged the same year — the Funding page's own series, so the totals agree. "
               "Build money (earmarks to the OCHA AA project) is direct, not share-based. "
               "Cash basis: contributions received in the year, pledges excluded. "
               "<a href='dash-funding.html'>← Funding</a>",
               panels, json.dumps(data, default=str), js)
