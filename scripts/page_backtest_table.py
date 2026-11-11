"""Historical activations, checked by eye (historical-activations.html, admin site; D221).

Owner, 2026-11-11: "a really simple table that is one row per year, with columns grouped and
collapsible by framework, per window within each framework, per trigger within each window. It
defaults to the most recent version, but maybe has the option to select past versions. It shows
whether it triggered, yes or no, and also has the option to go monthly instead of yearly … This
would be the way that we would verify that these are correct. Also, make it clear what the analysis
years are."

One table. A row is a year (or a month); a column is a framework, opened into its windows, a window
opened into its triggers. A cell says whether the trigger would have been met: yes, no, no data (a
year inside the analysis years that could not be assessed, D221) or blank (outside the analysis
years). The line under each column's name gives its analysis years. Real activations of the version
are marked apart from the simulated ones.

Live, like the data admin: the page reads the database through the proxy when it opens (the admin
pages' viewer token), so a correction saved in the data admin shows on a reload. It also carries the
rows of the copy it was built from and shows those, saying so, when the proxy cannot be reached.
"""
import json

import pandas as pd
import sqlalchemy as sa

PAGE, TITLE = "historical-activations.html", "Historical activations"

# table -> the columns the page reads (the proxy's /rows returns every column; these are enough)
READS = {
    "framework_version": ["country_iso3", "hazard", "version", "version_no", "kb_status", "valid_from", "valid_until"],
    "country_hazard": ["country_iso3", "hazard", "country_name", "retired"],
    "window": ["country_iso3", "hazard", "version", "window_code", "window_name", "basis",
               "analysis_start", "analysis_end", "analysis_gap_years"],
    "v_window_trigger": ["country_iso3", "hazard", "version", "window_code", "trigger_code", "name", "basis",
                         "threshold", "implicit", "analysis_start", "analysis_end", "analysis_gap_years"],
    "v_trigger_event": ["country_iso3", "hazard", "version", "window_code", "trigger_code", "event_year",
                        "event_label", "event_date", "event_time", "met", "value", "unit", "recorded_in"],
    "window_activation": ["country_iso3", "hazard", "version", "window_code", "trigger_code", "event_date",
                          "event_label"],
}

CSS = """
.ha-intro { max-width:900px; color:#444; margin:0 0 10px; line-height:1.5; }
.ha-live { font-size:12.5px; color:#555; margin:0 0 10px; min-height:1.2em; }
.ha-live::before { content:''; display:inline-block; width:8px; height:8px; border-radius:50%;
  background:#9e9e9e; margin-right:6px; vertical-align:1px; }
.ha-live.on::before { background:#1c7c3c; } .ha-live.off { color:#8a5c0a; } .ha-live.off::before { background:#c27c0e; }
.ha-bar { display:flex; gap:14px; align-items:center; flex-wrap:wrap; margin:0 0 10px; font-size:13px; }
.ha-bar label { color:#555; } .ha-bar select, .ha-bar input[type=search] { font-size:13px; padding:4px 6px; }
.ha-seg { display:inline-flex; border:1px solid #c9c9c9; border-radius:6px; overflow:hidden; }
.ha-seg button { border:0; background:#fff; padding:5px 12px; font-size:13px; cursor:pointer; color:#333; }
.ha-seg button + button { border-left:1px solid #c9c9c9; }
.ha-seg button[aria-pressed='true'] { background:#1f2a44; color:#fff; }
.ha-key { display:flex; gap:14px; flex-wrap:wrap; font-size:12.5px; color:#444; margin:0 0 10px; align-items:center; }
.ha-key span.c { display:inline-block; min-width:44px; text-align:center; padding:1px 6px; border:1px solid #ddd; margin-right:4px; }
.ha-wrap { overflow:auto; max-height:78vh; border:1px solid #d5d5d5; background:#fff; }
.ha-t { border-collapse:separate; border-spacing:0; font-size:12.5px; }
.ha-t th, .ha-t td { border-right:1px solid #e3e3e3; border-bottom:1px solid #e3e3e3; padding:3px 6px; white-space:nowrap; }
.ha-t thead th { position:sticky; background:#f4f5f7; z-index:2; text-align:center; font-weight:600; vertical-align:top; }
.ha-t thead tr.r1 th { top:0; background:#1f2a44; color:#fff; border-right:2px solid #fff; text-align:left; }
.ha-t thead tr.r2 th { top:var(--h1); } .ha-t thead tr.r3 th { top:calc(var(--h1) + var(--h2)); font-weight:400; }
.ha-t thead tr.r4 th { top:calc(var(--h1) + var(--h2) + var(--h3)); font-weight:400; color:#555; font-size:11.5px; white-space:normal; min-width:92px; }
.ha-t th.y, .ha-t td.y { position:sticky; left:0; z-index:1; background:#f4f5f7; font-weight:600; text-align:left; }
.ha-t thead th.y { z-index:3; }
.ha-t thead tr.r1 th.y { background:#1f2a44; }
.ha-t tbody td { text-align:center; cursor:default; }
.ha-t td.fe, .ha-t th.fe { border-right:2px solid #9aa3b5; }
.ha-t td.yes { background:#1c7c3c; color:#fff; font-weight:600; }
.ha-t td.no { background:#fff; color:#8a8a8a; }
.ha-t td.gap { background:repeating-linear-gradient(45deg, #fbe9c9, #fbe9c9 4px, #fff 4px, #fff 8px); color:#7a5200; font-size:11.5px; }
.ha-t td.out { background:#ececec; color:#ececec; }
.ha-t td.mid { background:#fff; }
.ha-t td.warn { outline:2px solid #c0392b; outline-offset:-2px; }
.ha-t td.ev { cursor:pointer; }
.ha-t td .real { display:inline-block; margin-left:4px; padding:0 4px; border-radius:8px; background:#fff; color:#1f2a44;
  border:1.5px solid #1f2a44; font-size:10.5px; font-weight:700; }
.ha-t tfoot td { position:sticky; bottom:0; background:#f4f5f7; font-size:11.5px; text-align:center; border-top:2px solid #9aa3b5; }
.ha-t tfoot td.y { z-index:3; }
.ha-tg { cursor:pointer; background:none; border:0; color:inherit; font:inherit; padding:0 4px 0 0; }
.ha-t thead select { font-size:11.5px; max-width:210px; margin-left:6px; }
.ha-t thead .sub { font-weight:400; font-size:11.5px; opacity:.85; }
.ha-wn { max-width:230px; overflow:hidden; text-overflow:ellipsis; display:inline-block; vertical-align:bottom; }
.ha-detail { margin:10px 0 0; padding:10px 12px; border:1px solid #d5d5d5; background:#fff; font-size:13px; }
.ha-detail h3 { margin:0 0 6px; font-size:14px; } .ha-detail table { border-collapse:collapse; font-size:12.5px; }
.ha-detail td, .ha-detail th { padding:2px 10px 2px 0; text-align:left; border-bottom:1px solid #eee; }
.ha-empty { padding:14px; color:#666; font-style:italic; }
"""


def _rows(e):
    """The copy the page carries: the same rows the proxy's /rows gives, the columns it reads."""
    out = {}
    with e.connect() as c:
        for table, cols in READS.items():
            have = {r[0] for r in c.execute(sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'aa' AND table_name = :t"), {"t": table})}
            sel = ", ".join(f"{k}::text AS {k}" if k in ("event_date", "valid_from", "valid_until") else
                            f"to_char({k} AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI') AS {k}" if k == "event_time"
                            else k for k in cols if k in have)
            if not sel:
                out[table] = []
                continue
            df = pd.read_sql(sa.text(f"SELECT {sel} FROM aa.{table}"), c)
            out[table] = json.loads(df.to_json(orient="records"))
    return out


def build(e, page, stamp):
    from admin_page import PROXY_URL, site_token
    js = json.dumps({"rows": _rows(e), "stamp": stamp}, ensure_ascii=False).replace("</", "<\\/")
    body = f"""<style>{CSS}</style>
<p class='ha-intro'>What each framework's triggers would have done in past years, as recorded in the
database, to check by eye. A row is a year; a column is a framework. Open a framework to see its
windows, and a window to see its triggers. The line under each name gives the analysis years: only
those years count towards the return period, and the bottom line counts the years met among them.
A real activation recorded against no window shows only on the closed framework column. A
correction is made in the <a href='admin.html#trigger_event'>data admin</a> and shows here on a
reload (there, a list of years is typed with braces: <code>{{2020,2021}}</code>).</p>
<p class='ha-live' id='ha-live' role='status'></p>
<div class='ha-bar'>
 <span class='ha-seg' role='group' aria-label='Rows'>
  <button type='button' data-g='year' aria-pressed='true'>Yearly</button><button type='button' data-g='month' aria-pressed='false'>Monthly</button>
 </span>
 <span class='ha-seg' role='group' aria-label='Columns'>
  <button type='button' data-open='fw'>Frameworks</button><button type='button' data-open='win'>Windows</button><button type='button' data-open='trig'>Triggers</button>
 </span>
 <label>Hazard <select id='ha-hz'><option value=''>all</option></select></label>
 <label>Country <input type='search' id='ha-q' placeholder='name or ISO3' size='14'></label>
 <label><input type='checkbox' id='ha-old'> include frameworks with no current version</label>
 <label><input type='checkbox' id='ha-hide'> hide rows with nothing recorded</label>
</div>
<div class='ha-key'>
 <span><span class='c' style='background:#1c7c3c;color:#fff;font-weight:600'>Yes</span>would have triggered</span>
 <span><span class='c' style='color:#8a8a8a'>No</span>assessed, not triggered</span>
 <span><span class='c' style='background:repeating-linear-gradient(45deg,#fbe9c9,#fbe9c9 4px,#fff 4px,#fff 8px);color:#7a5200'>no data</span>inside the analysis years, could not be assessed</span>
 <span><span class='c' style='background:#ececec'>&nbsp;</span>outside the analysis years</span>
 <span><span class='c' style='border:1.5px solid #1f2a44;border-radius:8px;min-width:0;font-weight:700;font-size:10.5px'>real</span>the version really activated</span>
 <span><span class='c' style='outline:2px solid #c0392b;outline-offset:-2px'>Yes</span>recorded outside the analysis years: check</span>
</div>
<div class='ha-wrap' id='ha-wrap'><div class='ha-empty'>Loading…</div></div>
<div class='ha-detail' id='ha-detail' hidden></div>
<script>
window.PROXY = new URLSearchParams(location.search).get('proxy') || '{PROXY_URL}';
window.SITE_TOKEN = '{site_token()}';
const BUILT = {js};
{SCRIPT}
</script>"""
    page(PAGE, TITLE, body)


SCRIPT = r"""
(function(){
const HAZ = {storm:'Storms', flood:'Floods', drought:'Drought', cholera:'Cholera', plague:'Plague', locusts:'Locusts',
             food_insecurity:'Food insecurity', general:'No specific hazard'};
const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const esc = s => s==null ? '' : String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
const $ = id => document.getElementById(id);
const S = {gran:'year', hz:'', q:'', old:false, hide:false, ver:{}, openFw:{}, openWin:{}};
let FW = [];

// ---------- the rows -> frameworks > versions > windows > triggers > events
function arr(v){ if(v==null) return []; if(Array.isArray(v)) return v.map(Number);
  return String(v).replace(/[{}]/g,'').split(',').filter(x=>x.trim()!=='').map(Number); }
function model(R){
  const names = {}, retired = {};
  for(const r of R.country_hazard||[]){ names[r.country_iso3] = r.country_name || names[r.country_iso3]; retired[r.country_iso3+'|'+r.hazard] = !!r.retired; }
  const vkey = r => [r.country_iso3, r.hazard, r.version].join('|'), wkey = r => vkey(r)+'|'+r.window_code;
  const V = {}, W = {}, T = {};
  for(const r of R.framework_version||[]) V[vkey(r)] = {...r, windows:[], loose:[]};
  for(const r of R.window||[]){ if(r.window_code==null || !V[vkey(r)]) continue;
    const w = W[wkey(r)] = {code:r.window_code, name:r.window_name, basis:r.basis, triggers:[], real:[],
      a0:r.analysis_start==null?null:+r.analysis_start, a1:r.analysis_end==null?null:+r.analysis_end, gaps:arr(r.analysis_gap_years)};
    V[vkey(r)].windows.push(w); }
  for(const r of R.v_window_trigger||[]){ const w = W[wkey(r)]; if(!w) continue;
    const t = {code:r.trigger_code, name:r.name, basis:r.basis, threshold:r.threshold, implicit:!!r.implicit,
               a0:r.analysis_start==null?null:+r.analysis_start, a1:r.analysis_end==null?null:+r.analysis_end,
               gaps:arr(r.analysis_gap_years), ev:[]};
    T[wkey(r)+'|'+r.trigger_code] = t; w.triggers.push(t); }
  for(const r of R.v_trigger_event||[]){ let t = T[wkey(r)+'|'+r.trigger_code];
    if(!t){ // the window's own record, where its triggers are entered but not their events: its own column
      const w = W[wkey(r)]; if(!w) continue;
      t = T[wkey(r)+'|'+r.trigger_code] = {code:r.trigger_code, name:"the window's own record (not entered per trigger)", basis:w.basis,
        threshold:null, implicit:true, a0:w.a0, a1:w.a1, gaps:w.gaps, ev:[]}; w.triggers.push(t); }
    const d = r.event_time || r.event_date || null;
    t.ev.push({y:+r.event_year, label:r.event_label||'', date:d, dy:d?+d.slice(0,4):null, dm:d?+d.slice(5,7):null,
               met:r.met===true||r.met==='true'||r.met==='t', value:r.value, unit:r.unit, from:r.recorded_in}); }
  for(const r of R.window_activation||[]){ if(!/^\d{4}/.test(r.event_date||'')) continue;
    const w = W[wkey(r)], v = V[vkey(r)]; if(!w && !v) continue;
    (w ? w.real : v.loose).push({y:+r.event_date.slice(0,4), m:r.event_date.length>=7?+r.event_date.slice(5,7):null, date:r.event_date,
                 label:r.event_label||'', trig:r.trigger_code||null}); }
  const F = {};
  for(const v of Object.values(V)){ if(!v.windows.length) continue;
    v.windows.sort((a,b)=>a.code.localeCompare(b.code)); v.windows.forEach(w=>w.triggers.sort((a,b)=>a.code.localeCompare(b.code)));
    const k = v.country_iso3+'|'+v.hazard;
    (F[k] = F[k] || {key:k, iso3:v.country_iso3, hazard:v.hazard, name:names[v.country_iso3]||v.country_iso3,
                     retired:!!retired[k], versions:[]}).versions.push(v); }
  const out = Object.values(F);
  for(const f of out){
    f.versions.sort((a,b)=> (b.valid_from||'').localeCompare(a.valid_from||'') || String(b.version).localeCompare(String(a.version)));
    f.def = (f.versions.find(v=>v.kb_status==='endorsed') || f.versions[0]).version;
    // current: its newest endorsed version has not run out, or a version is in development
    const today = new Date().toISOString().slice(0,10), e = f.versions.find(v=>v.kb_status==='endorsed');
    f.current = !f.retired && ((e && (!e.valid_until || e.valid_until >= today)) || f.versions.some(v=>v.kb_status!=='endorsed'));
  }
  out.sort((a,b)=> a.name.localeCompare(b.name) || a.hazard.localeCompare(b.hazard));
  return out;
}

// ---------- one trigger, one row: yes | no | gap | out | mid (a month of an assessed year)
const span = t => t.a0!=null && t.a1!=null;
const inSpan = (t, y) => span(t) && y>=t.a0 && y<=t.a1;
function cellOf(t, row){
  let ev;
  if(row.m === undefined) ev = t.ev.filter(e=>e.y===row.y);
  else if(row.m === null) ev = t.ev.filter(e=>e.y===row.y && e.dm==null);
  else ev = t.ev.filter(e=>e.dy===row.y && e.dm===row.m);
  const met = ev.filter(e=>e.met), ins = inSpan(t, row.y), gap = ins && t.gaps.includes(row.y);
  let s;
  if(met.length) s = 'yes';
  else if(ev.length) s = 'no';
  else if(gap) s = 'gap';
  else if(!ins) s = 'out';
  else s = row.m === undefined ? 'no' : 'mid';
  // a met event in a month is judged against the year the document files it under
  const warn = met.some(e=> t.gaps.includes(e.y) || (span(t) && !inSpan(t, e.y)));
  return {s, ev, met, warn};
}
const RANK = {yes:5, no:4, mid:3, gap:2, out:1};
function merge(cells){
  let s = 'out', ev = [], met = new Set(), warn = false;
  for(const c of cells){ if(RANK[c.s] > RANK[s]) s = c.s; ev = ev.concat(c.ev.map(e=>({...e, trig:c.t.code})));
    c.met.forEach(e=>met.add(e.y+'|'+e.label)); warn = warn || c.warn; }
  return {s, ev, n:met.size, warn};
}
function realIn(w, trigs, row){
  return w.real.filter(r=> r.y===row.y && (row.m===undefined || (row.m===null ? r.m==null : r.m===row.m)) &&
    (trigs.length===w.triggers.length || r.trig==null || trigs.some(t=>t.code===r.trig)));
}

// ---------- columns: a framework closed = 1 column; open = its windows; a window open = its triggers
function shown(){
  const q = S.q.trim().toLowerCase();
  return FW.filter(f=> (S.old || f.current) && (!S.hz || f.hazard===S.hz) &&
    (!q || f.name.toLowerCase().includes(q) || f.iso3.toLowerCase().includes(q)));
}
const verOf = f => f.versions.find(v=>v.version===(S.ver[f.key]||f.def)) || f.versions[0];
function columns(fws){
  const cols = [];
  for(const f of fws){
    const v = verOf(f), mine = [];
    if(!S.openFw[f.key]) mine.push({f, v, wins:v.windows, trigs:v.windows.flatMap(w=>w.triggers.map(t=>({w,t}))), level:'fw'});
    else for(const w of v.windows){
      const k = f.key+'|'+v.version+'|'+w.code;
      if(!S.openWin[k] || w.triggers.length < 2) mine.push({f, v, w, wins:[w], trigs:w.triggers.map(t=>({w,t})), level:'win', wk:k});
      else for(const t of w.triggers) mine.push({f, v, w, wins:[w], trigs:[{w,t}], level:'trig', wk:k});
    }
    if(mine.length) mine[mine.length-1].fe = true;
    cols.push(...mine);
  }
  return cols;
}
// the years a column's triggers assessed: null where no analysis years are recorded
function assessed(trigs){
  const ts = trigs.map(x=>x.t).filter(span);
  if(!ts.length) return null;
  const a0 = Math.min(...ts.map(t=>t.a0)), a1 = Math.max(...ts.map(t=>t.a1));
  const ok = y => ts.some(t=>inSpan(t,y) && !t.gaps.includes(y));
  const gaps = [], years = new Set();
  for(let y=a0; y<=a1; y++){ if(ok(y)) years.add(y); else gaps.push(y); }
  return {a0, a1, years, gaps, same: ts.every(t=>t.a0===a0 && t.a1===a1)};
}
function yearsText(trigs){
  const a = assessed(trigs);
  if(!a) return "analysis years not recorded";
  const n = a.years.size;
  return `${a.a0}–${a.a1}${a.same?'':' (differs by trigger)'} · ${n} year${n===1?'':'s'}` + (a.gaps.length ? `<br>no data: ${a.gaps.join(', ')}` : '');
}
function rowsOf(cols){
  let lo = Infinity, hi = -Infinity;
  const see = y => { if(y!=null && isFinite(y)){ lo = Math.min(lo,y); hi = Math.max(hi,y); } };
  for(const c of cols){ for(const {t} of c.trigs){ see(t.a0); see(t.a1); t.ev.forEach(e=>{ see(e.y); if(S.gran==='month') see(e.dy); }); }
    c.wins.forEach(w=>w.real.forEach(r=>see(r.y))); if(c.level==='fw') c.v.loose.forEach(r=>see(r.y)); }
  const rows = [];
  if(!isFinite(lo)) return rows;
  for(let y=hi; y>=lo; y--){
    if(S.gran==='year') rows.push({y, label:String(y)});
    else { rows.push({y, m:null, label:`${y} · month not recorded`}); for(let m=12; m>=1; m--) rows.push({y, m, label:`${y} ${MON[m-1]}`}); }
  }
  return rows;
}

// ---------- draw
let CELLS = [];
function draw(){
  const fws = shown(), cols = columns(fws), wrap = $('ha-wrap');
  $('ha-detail').hidden = true;
  if(!cols.length){ wrap.innerHTML = "<div class='ha-empty'>No framework matches.</div>"; return; }
  // header 1: frameworks
  let h1 = "<tr class='r1'><th class='y' rowspan='4'>" + (S.gran==='year'?'Year':'Month') + "</th>", h2 = "<tr class='r2'>", h3 = "<tr class='r3'>", h4 = "<tr class='r4'>";
  for(const f of fws){
    const v = verOf(f), mine = cols.filter(c=>c.f===f), open = !!S.openFw[f.key];
    const opts = f.versions.map(x=>`<option value='${esc(x.version)}'${x===v?' selected':''}>${x.version_no!=null?'v'+esc(x.version_no)+' · ':''}${esc(x.version)} · ${esc(x.kb_status||'')}</option>`).join('');
    h1 += `<th class='fe' colspan='${mine.length}'><button class='ha-tg' data-fw='${esc(f.key)}' title='${open?'Close':'Open'} the windows' aria-expanded='${open}'>${open?'▾':'▸'}</button>${esc(f.name)} · ${esc(HAZ[f.hazard]||f.hazard)}` +
      (f.versions.length>1 ? `<select data-ver='${esc(f.key)}' aria-label='Version'>${opts}</select>` : ` <span class='sub'>${v.version_no!=null?'v'+esc(v.version_no)+' · ':''}${esc(v.version)} · ${esc(v.kb_status||'')}</span>`) + `</th>`;
  }
  for(let i=0; i<cols.length; i++){
    const c = cols[i], fe = c.fe ? ' fe' : '';
    if(c.level==='fw'){ h2 += `<th class='${fe}' rowspan='2'>any of ${c.wins.length} window${c.wins.length===1?'':'s'}</th>`; }
    else if(c.level==='win'){ const can = c.w.triggers.length > 1;
      h2 += `<th class='${fe}' rowspan='2' title='${esc(c.w.name)}'>${can?`<button class='ha-tg' data-win='${esc(c.wk)}' title='Open the triggers' aria-expanded='false'>▸</button>`:''}<span class='ha-wn'>${esc(c.w.code)}</span><br><span class='sub ha-wn'>${esc(c.w.name)}</span>${can?`<br><span class='sub'>any of ${c.w.triggers.length} triggers</span>`:''}</th>`; }
    else { const first = i===0 || cols[i-1].w!==c.w || cols[i-1].level!=='trig';
      if(first){ const n = c.w.triggers.length, last = cols[i+n-1];
        h2 += `<th class='${last&&last.fe?'fe':''}' colspan='${n}' title='${esc(c.w.name)}'><button class='ha-tg' data-win='${esc(c.wk)}' title='Close the triggers' aria-expanded='true'>▾</button><span class='ha-wn'>${esc(c.w.code)}</span> <span class='sub ha-wn'>${esc(c.w.name)}</span></th>`; }
      const t = c.trigs[0].t;
      h3 += `<th class='${fe}' title='${esc([t.name, t.threshold].filter(Boolean).join(' — '))}'><span class='ha-wn'>${esc(t.code)}</span></th>`; }
    h4 += `<th class='${fe}'>${yearsText(c.trigs)}</th>`;
  }
  // body
  const rows = rowsOf(cols); CELLS = [];
  let body = '';
  const tot = cols.map(c=>({yes:0, a:assessed(c.trigs)}));
  for(const r of rows){
    let tds = '', any = false;
    cols.forEach((c, i)=>{
      const m = merge(c.trigs.map(({t})=>({...cellOf(t, r), t})));
      const real = c.wins.flatMap(w=>realIn(w, c.trigs.filter(x=>x.w===w).map(x=>x.t), r).map(x=>({...x, win:w.code})));
      // a real activation recorded against no window of the version: on the framework's own column
      if(c.level==='fw') real.push(...c.v.loose.filter(x=>x.y===r.y && (r.m===undefined || (r.m===null ? x.m==null : x.m===r.m))).map(x=>({...x, win:'window not recorded'})));
      if(r.m===undefined && m.s==='yes' && tot[i].a && tot[i].a.years.has(r.y)) tot[i].yes++;
      const has = m.ev.length || real.length; if(has || (m.s==='gap' && r.m===undefined)) any = true;
      const txt = m.s==='yes' ? (m.n>1 ? `Yes ×${m.n}` : 'Yes') : m.s==='no' ? 'No' : m.s==='gap' ? 'no data' : '';
      const id = CELLS.push({c, r, m, real}) - 1;
      tds += `<td class='${m.s}${m.warn?' warn':''}${has?' ev':''}${c.fe?' fe':''}'${has?` data-i='${id}' tabindex='0'`:''}>${txt}${real.length?`<span class='real' title='Real activation'>real</span>`:''}</td>`;
    });
    if(S.hide && !any) continue;
    if(r.m===null && !any) continue;      // the 'month not recorded' line only where it holds something
    body += `<tr><td class='y'>${esc(r.label)}</td>${tds}</tr>`;
  }
  const foot = S.gran==='year' ? `<tfoot><tr><td class='y'>Years met / assessed</td>${cols.map((c,i)=>`<td class='${c.fe?'fe':''}'>${tot[i].a ? tot[i].yes+' / '+tot[i].a.years.size : 'not recorded'}</td>`).join('')}</tr></tfoot>` : '';
  wrap.innerHTML = `<table class='ha-t'><thead>${h1}</tr>${h2}</tr>${h3}</tr>${h4}</tr></thead><tbody>${body}</tbody>${foot}</table>`;
  // sticky header rows sit under one another
  const tb = wrap.querySelector('table'), hs = [...tb.tHead.rows].map(r=>r.getBoundingClientRect().height);
  ['--h1','--h2','--h3'].forEach((k,i)=>tb.style.setProperty(k, hs[i]+'px'));
}
function detail(i){
  const {c, r, m, real} = CELLS[i], d = $('ha-detail'), v = c.v;
  const where = `${c.f.name} · ${HAZ[c.f.hazard]||c.f.hazard} · ${v.version}` + (c.level!=='fw' ? ` · ${c.w.code}` : '') + (c.level==='trig' ? ` · ${c.trigs[0].t.code}` : '');
  const link = t => `admin.html#${t}/?f.country_iso3=${encodeURIComponent(c.f.iso3)}&f.hazard=${encodeURIComponent(c.f.hazard)}&f.version=${encodeURIComponent(v.version).replace(/'/g,'%27')}`;
  const src = {trigger_event:'trigger_event', backtest_event:'backtest_event', simulated_activation:'simulated_activation'};
  let html = `<h3>${esc(where)} — ${esc(r.label)}</h3>`;
  if(m.ev.length) html += `<table><tr><th>Trigger</th><th>Event</th><th>Filed under</th><th>Date</th><th>Met</th><th>Value</th><th>Recorded in</th></tr>` +
    m.ev.sort((a,b)=>(a.date||'').localeCompare(b.date||'') || a.label.localeCompare(b.label)).map(e=>`<tr><td>${esc(e.trig)}</td><td>${esc(e.label)||'(the year)'}</td><td>${e.y}</td><td>${esc(e.date)||'not recorded'}</td><td>${e.met?'yes':'no'}</td><td>${e.value==null?'':esc(e.value)+' '+esc(e.unit||'')}</td><td><a href='${link(src[e.from]||'trigger_event')}'>${esc(e.from)}</a></td></tr>`).join('') + `</table>`;
  if(real.length) html += `<p><b>Real activation${real.length>1?'s':''}:</b> ` + real.map(x=>`${esc(x.date)} ${esc(x.label)} (${esc(x.win)}${x.trig?', '+esc(x.trig):''})`).join('; ') + ` · <a href='${link('window_activation')}'>window_activation</a></p>`;
  if(m.warn) html += `<p style='color:#c0392b'>A met event sits outside this trigger's analysis years (or in a year recorded as no data): the event or the years are wrong.</p>`;
  d.innerHTML = html; d.hidden = false; d.scrollIntoView({block:'nearest'});
}

// ---------- controls
function fillHazards(){ const hz = [...new Set(FW.map(f=>f.hazard))].sort(), el = $('ha-hz');
  el.innerHTML = "<option value=''>all</option>" + hz.map(h=>`<option value='${esc(h)}'>${esc(HAZ[h]||h)}</option>`).join(''); el.value = S.hz; }
document.querySelectorAll('.ha-seg button[data-g]').forEach(b=>b.onclick = ()=>{ S.gran = b.dataset.g;
  document.querySelectorAll('.ha-seg button[data-g]').forEach(x=>x.setAttribute('aria-pressed', x===b));
  S.hide = S.gran==='month'; $('ha-hide').checked = S.hide; draw(); });
document.querySelectorAll('.ha-seg button[data-open]').forEach(b=>b.onclick = ()=>{ const lv = b.dataset.open;
  S.openFw = {}; S.openWin = {};
  if(lv!=='fw') for(const f of FW){ S.openFw[f.key] = true;
    if(lv==='trig') for(const v of f.versions) for(const w of v.windows) S.openWin[f.key+'|'+v.version+'|'+w.code] = true; }
  draw(); });
$('ha-hz').onchange = e=>{ S.hz = e.target.value; draw(); };
$('ha-q').oninput = e=>{ S.q = e.target.value; draw(); };
$('ha-old').onchange = e=>{ S.old = e.target.checked; draw(); };
$('ha-hide').onchange = e=>{ S.hide = e.target.checked; draw(); };
$('ha-wrap').addEventListener('click', e=>{
  const fw = e.target.closest('[data-fw]'), win = e.target.closest('[data-win]'), td = e.target.closest('td[data-i]');
  if(fw){ S.openFw[fw.dataset.fw] = !S.openFw[fw.dataset.fw]; draw(); }
  else if(win){ S.openWin[win.dataset.win] = !S.openWin[win.dataset.win]; draw(); }
  else if(td) detail(+td.dataset.i);
});
$('ha-wrap').addEventListener('keydown', e=>{ const td = e.target.closest('td[data-i]'); if(td && (e.key==='Enter' || e.key===' ')){ e.preventDefault(); detail(+td.dataset.i); } });
$('ha-wrap').addEventListener('change', e=>{ const s = e.target.closest('select[data-ver]'); if(s){ S.ver[s.dataset.ver] = s.value; draw(); } });

// ---------- data: the copy built into the page, then the database itself
function use(R){ FW = model(R); fillHazards(); draw(); }
async function page(table, extra){
  // every row of a table (500 at a time); rows are compared whole, so a row met twice across pages counts once
  const seen = new Map(); let total = Infinity, off = 0;
  while(off < total){
    const r = await fetch(`${PROXY}/rows?table=${table}&limit=500&offset=${off}${extra||''}`, {headers:{'x-site-token':SITE_TOKEN}, cache:'no-store'});
    const j = await r.json(); if(!r.ok) throw new Error(j.error || r.statusText);
    total = j.total; j.rows.forEach(x=>seen.set(JSON.stringify(x), x)); off += 500;
    if(!j.rows.length) break;
  }
  if(seen.size !== total) throw new Error(`${table}: read ${seen.size} of ${total} rows`);
  return [...seen.values()];
}
async function live(){
  const el = $('ha-live');
  try {
    const R = {};
    const [fv, ch, w, wt, wa] = await Promise.all(['framework_version','country_hazard','window','v_window_trigger','window_activation'].map(t=>page(t)));
    Object.assign(R, {framework_version:fv, country_hazard:ch, window:w, v_window_trigger:wt, window_activation:wa});
    // events one country at a time: each read is then a single page
    const isos = [...new Set(wt.map(r=>r.country_iso3))]; R.v_trigger_event = [];
    for(let i=0; i<isos.length; i+=6)
      (await Promise.all(isos.slice(i, i+6).map(c=>page('v_trigger_event', '&f.country_iso3='+encodeURIComponent(c))))).forEach(x=>R.v_trigger_event.push(...x));
    use(R);
    el.className = 'ha-live on';
    el.textContent = `Read from the database at ${new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}. Reload the page to read it again.`;
  } catch(err){
    el.className = 'ha-live off';
    el.textContent = `The database could not be read (${err.message}): showing the copy this page was built from (${BUILT.stamp}).`;
  }
}
use(BUILT.rows);
$('ha-live').textContent = 'Reading the database…';
live();
})();
"""
