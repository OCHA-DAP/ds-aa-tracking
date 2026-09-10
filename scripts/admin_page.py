"""admin.html — a Django-admin-style CRUD page over every table in the `aa` schema.

Static page; everything is fetched live from the entry proxy (GET /schema, /rows,
/distinct; POST /save, /delete), so new tables and columns appear automatically and
the page never carries a data snapshot. Two roles:

- viewer: the site token embedded in this (staticrypt-encrypted) page — browse and
  filter every table and view;
- editor: a separate token, never embedded, prompted for once and kept in the
  browser (localStorage `editorToken`, header `x-editor-token`) — add, change,
  delete on the tables this repo owns; every field change is audited to
  aa.entry_audit under the editor's name.

Tables owned by other writers (KB loaders, OneGMS mirrors) and the audit table are
read-only regardless of role — the proxy enforces it, the page just says so.
"""

import os
from pathlib import Path

PROXY_URL = "https://chd-ds-aa-extract.azurewebsites.net"

# grouping for the index page, Django-admin "app" style
GROUPS = [
    ("Frameworks & tracking", "ds-aa-tracking", [
        "framework_registry", "framework_version", "framework_status", "framework_focal_point",
        "framework_calendar", "fund", "prearranged_funding", "prearranged_sector_budget",
        "people_covered", "plan_inclusion", "report_channel_inclusion", "start_network",
        "cirv", "activation", "activation_funding", "emergency_type_override",
        "cerf_allocation_extra", "cerf_application_people", "cerf_application_report",
        "cerf_project_supplement", "cerf_subgrant", "cerf_cva_history"]),
    ("Data entry (entered values win)", "ds-aa-tracking", [
        "entered_version", "entered_window", "entered_window_funding",
        "entered_version_funding", "entry_audit"]),
    ("Knowledge base — trigger performance (read-only)", "ds-knowledge-base", [
        "window", "simulated_activation", "funding_breakdown", "actual_activation",
        "activation_allocation", "version_performance_reported"]),
    ("OneGMS mirrors (read-only)", "ds-cerf-supplement", [
        "cerf_allocation", "cerf_project", "cerf_project_sector", "cerf_project_country",
        "cerf_allocation_storm", "cerf_supplement", "cbpf_fund", "cbpf_allocation",
        "cbpf_project", "cbpf_project_cluster", "cbpf_project_subip"]),
]

# columns that read better as a textarea
LONG_TEXT = ("note", "notes", "comment", "comments", "remark", "remarks", "description",
             "narrative", "statement", "title", "summary", "text", "lesson", "objective")


def build_admin(page):
    token_file = Path(__file__).parents[1] / ".extract_token"
    site_token = os.environ.get("EXTRACT_TOKEN", "").strip() or (
        token_file.read_text().strip() if token_file.exists() else "")
    import json
    body = (ADMIN_HTML
            .replace("__PROXY__", PROXY_URL)
            .replace("__TOKEN__", site_token)
            .replace("__GROUPS__", json.dumps(GROUPS))
            .replace("__LONGTEXT__", json.dumps(LONG_TEXT)))
    page("admin.html", "Administration", body)


ADMIN_HTML = r"""
<div id='adm'>
 <div class='dj-head'>
  <div class='dj-brand'><a href='#'>AA tracking administration</a></div>
  <div class='dj-user' id='who'></div>
 </div>
 <div class='dj-crumbs' id='crumbs'>Home</div>
 <div class='dj-msg' id='msg' hidden></div>
 <div id='view' class='dj-body'><div class='dj-loading'>Loading schema…</div></div>
</div>
<script>
window.PROXY = new URLSearchParams(location.search).get('proxy') || '__PROXY__';
window.SITE_TOKEN = '__TOKEN__';
const GROUPS = __GROUPS__, LONG_TEXT = __LONGTEXT__;
const PAGE = 100;
let SCHEMA = null, ROLE = null, BY_TABLE = {};

// ---------- api
function hdrs(){ const h = {'x-site-token': SITE_TOKEN}; const et = localStorage.getItem('editorToken'); if(et) h['x-editor-token'] = et; return h; }
async function api(path, opts={}, retry=true){
  const r = await fetch(PROXY + path, {...opts, headers: {...(opts.headers||{}), ...hdrs()}});
  if(r.status === 401 && retry){
    const j = await r.json().catch(()=>({}));
    if((j.error||'').includes('editor')){
      const et = prompt('Editor token required (ask Tristan). It is saved in this browser only:');
      if(et){ localStorage.setItem('editorToken', et.trim()); return api(path, opts, false); }
    } else if(localStorage.getItem('editorToken')){
      localStorage.removeItem('editorToken'); return api(path, opts, false);
    }
  }
  return r;
}
async function getJSON(path){ const r = await api(path); const j = await r.json().catch(()=>({error:'bad response'})); if(!r.ok) throw new Error(j.error || r.statusText); return j; }
async function postJSON(path, body){ const r = await api(path, {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify(body)}); const j = await r.json().catch(()=>({error:'bad response'})); if(!r.ok) throw new Error(j.error || r.statusText); return j; }

// ---------- helpers
const esc = s => s==null ? '' : String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const title = s => s.replace(/_/g,' ').replace(/^./, c=>c.toUpperCase());
const isNum = c => ['numeric','bigint','integer','smallint','double precision','real'].includes(c.type);
const isTS = c => c.type.startsWith('timestamp');
const fmt = (c, v) => v==null ? '<span class="dj-null">—</span>' : c.type==='boolean' ? (v ? 'yes' : 'no') : isNum(c) && c.type==='numeric' && Math.abs(+v)>=1000 ? Number(v).toLocaleString() : esc(String(v).length>140 ? String(v).slice(0,140)+'…' : v);
function msg(text, kind='ok'){ const m = document.getElementById('msg'); m.textContent = text; m.className = 'dj-msg ' + kind; m.hidden = false; clearTimeout(m._t); m._t = setTimeout(()=>m.hidden=true, 6000); }
function crumbs(parts){ document.getElementById('crumbs').innerHTML = [`<a href='#'>Home</a>`, ...parts].join(' › '); }
function editorName(){ let n = localStorage.getItem('editorName'); if(!n){ n = prompt('Your name (recorded in the audit trail):'); if(n){ localStorage.setItem('editorName', n.trim()); } } return n; }
function keyOf(t, row){ return Object.fromEntries((t.key||[]).map(k=>[k, row[k]])); }
function keyQS(t, row){ return (t.key||[]).map(k=>encodeURIComponent(k)+'='+encodeURIComponent(row[k]==null?'':row[k])).join('&'); }
function groupOf(name){ for(const [g] of GROUPS){ const grp = GROUPS.find(x=>x[0]===g); if(grp[2].includes(name)) return g; } return null; }

// ---------- header / role
async function refreshRole(){
  try { ROLE = (await getJSON('/whoami')).role; } catch(e){ ROLE = null; }
  const w = document.getElementById('who');
  if(ROLE === 'editor') w.innerHTML = `Editor${localStorage.getItem('editorName')?` · <b>${esc(localStorage.getItem('editorName'))}</b>`:''} · <a onclick='logoutEditor()'>log out</a> · <a href='entry.html'>upload tool</a>`;
  else if(ROLE === 'viewer') w.innerHTML = `Viewer · <a onclick='loginEditor()'>log in as editor</a>`;
  else w.innerHTML = `<span class='dj-warn'>not connected</span>`;
}
function loginEditor(){ const et = prompt('Editor token (ask Tristan). Saved in this browser only:'); if(et){ localStorage.setItem('editorToken', et.trim()); editorName(); boot(); } }
function logoutEditor(){ localStorage.removeItem('editorToken'); boot(); }

// ---------- routing  #table | #table/change?k=v | #table/add
window.addEventListener('hashchange', route);
async function route(){
  if(!SCHEMA) return;
  const h = decodeURIComponent(location.hash.replace(/^#/, ''));
  if(!h) return renderIndex();
  const [tname, rest] = h.split('/', 2);
  const t = BY_TABLE[tname]; if(!t) return renderIndex();
  if(rest && rest.startsWith('add')) return renderForm(t, null);
  if(rest && rest.startsWith('change?')) return renderForm(t, Object.fromEntries(new URLSearchParams(rest.slice(7)).entries()));
  return renderList(t, new URLSearchParams(rest && rest.startsWith('?') ? rest.slice(1) : ''));
}

// ---------- index
function renderIndex(){
  crumbs([]);
  const used = new Set();
  let html = `<div class='dj-cols'><div class='dj-main'>`;
  for(const [g, owner, names] of GROUPS){
    const ts = names.map(n=>BY_TABLE[n]).filter(Boolean); ts.forEach(t=>used.add(t.name));
    if(!ts.length) continue;
    html += module(g, owner, ts);
  }
  const rest = Object.values(SCHEMA).filter(t=>!used.has(t.name) && t.kind==='table');
  if(rest.length) html += module('Other tables', '', rest);
  const views = Object.values(SCHEMA).filter(t=>t.kind==='view');
  if(views.length) html += module('Views (read-only)', 'derived', views);
  html += `</div><div class='dj-side'><div class='dj-module'><h2>Recent actions</h2><div id='recent' class='dj-recent'>…</div></div>
    <div class='dj-module'><h2>About</h2><div class='dj-about'>Every table in the <code>aa</code> schema, straight from the database.
    ${ROLE==='editor' ? 'You can add, change and delete rows on the tables this repo owns; each field change is written to the audit trail under your name.' : 'You are viewing. Log in as editor (top right) to change data.'}
    Tables owned by other writers are read-only here.</div></div></div></div>`;
  document.getElementById('view').innerHTML = html;
  loadRecent();
}
function module(g, owner, ts){
  return `<div class='dj-module'><h2>${esc(g)} ${owner?`<span class='dj-owner'>${esc(owner)}</span>`:''}</h2><table class='dj-modtbl'>` +
    ts.map(t=>`<tr><th><a href='#${t.name}'>${esc(title(t.name))}</a>${t.kind==='view'?" <span class='dj-tag'>view</span>":''}</th>
      <td class='dj-n'>${t.n_rows!=null?Number(t.n_rows).toLocaleString():''}</td>
      <td class='dj-act'>${t.writable && ROLE==='editor' ? `<a class='dj-add' href='#${t.name}/add'>+ Add</a>` : ''}</td>
      <td class='dj-act'><a class='dj-chg' href='#${t.name}'>${t.writable && ROLE==='editor' ? 'Change' : 'View'}</a></td></tr>`).join('') + `</table></div>`;
}
async function loadRecent(){
  const el = document.getElementById('recent'); if(!el) return;
  try {
    const j = await getJSON('/rows?table=entry_audit&order=at&dir=desc&limit=15');
    el.innerHTML = j.rows.length ? j.rows.map(r=>`<div class='dj-rec'><span class='dj-recwho'>${esc(r.entered_by)}</span> · ${esc(r.at)}<br>
      <a href='#${esc(r.table_name)}'>${esc(title(r.table_name))}</a> <span class='dj-null'>${esc(r.row_key)}</span><br>
      <b>${esc(r.field)}</b>: ${r.old_value==null?'—':esc(r.old_value)} → ${r.new_value==null?'—':esc(r.new_value)}</div>`).join('') : '<div class="dj-null">No changes recorded yet.</div>';
  } catch(e){ el.innerHTML = `<div class='dj-warn'>${esc(e.message)}</div>`; }
}

// ---------- change list
const FILTER_SKIP = /note|comment|remark|description|narrative|statement|title|url|name$|label|_at$|amount|usd|people|value|id$|code$/;
async function renderList(t, qs){
  crumbs([`<b>${esc(title(t.name))}</b>`]);
  const v = document.getElementById('view');
  const readonly = !(t.writable && ROLE==='editor');
  const search = qs.get('q') || '', order = qs.get('order') || (t.key ? t.key[0] : t.columns[0].name), dir = qs.get('dir') || 'asc', p = +(qs.get('p')||0);
  const filters = [...qs.entries()].filter(([k])=>k.startsWith('f.'));
  const params = new URLSearchParams({table:t.name, limit:PAGE, offset:p*PAGE, order, dir}); if(search) params.set('q', search); filters.forEach(([k,val])=>params.set(k,val));
  v.innerHTML = `<div class='dj-listhead'><h1>${esc(title(t.name))} <span class='dj-owner'>${esc(t.owner)}${t.kind==='view'?' · view':''}</span></h1>
    ${readonly ? `<div class='dj-ro'>${t.kind==='view' ? 'Database view — read-only.' : !t.writable ? `Read-only here: owned by <b>${esc(t.owner)}</b>${t.name==='entry_audit'?' (append-only audit trail)':''}.` : 'Viewing. Log in as editor to change rows.'}</div>` : `<a class='dj-btn' href='#${t.name}/add'>+ Add ${esc(title(t.name).toLowerCase())}</a>`}
   </div>
   <div class='dj-cols'><div class='dj-main'>
    <form class='dj-search' onsubmit='return doSearch(event,"${t.name}")'><input name='q' value='${esc(search)}' placeholder='Search text columns…'><button>Search</button>
      ${search||filters.length?`<a href='#${t.name}' class='dj-clear'>clear</a>`:''}<span id='count' class='dj-count'></span></form>
    <div id='rows' class='dj-scroll'><div class='dj-loading'>Loading…</div></div><div id='pager' class='dj-pager'></div>
   </div><div class='dj-side' id='filters'></div></div>`;
  try {
    const j = await getJSON('/rows?' + params.toString());
    document.getElementById('count').textContent = `${j.total.toLocaleString()} row${j.total===1?'':'s'}`;
    const cols = t.columns;
    const link = (row) => t.key && t.kind==='table' ? `#${t.name}/change?${keyQS(t,row)}` : null;
    const sortQS = (c) => { const n = new URLSearchParams(qs); n.set('order', c.name); n.set('dir', order===c.name && dir==='asc' ? 'desc' : 'asc'); n.delete('p'); return `#${t.name}/?${n}`; };
    document.getElementById('rows').innerHTML = `<table class='dj-list'><thead><tr>${cols.map(c=>`<th class='${order===c.name?'dj-sorted':''} ${isNum(c)?'dj-num':''}'><a href='${sortQS(c)}'>${esc(c.name)}${order===c.name?(dir==='asc'?' ▲':' ▼'):''}</a></th>`).join('')}</tr></thead><tbody>` +
      j.rows.map(r=>`<tr>${cols.map((c,i)=>`<td class='${isNum(c)?'dj-num':''} ${(t.key||[]).includes(c.name)?'dj-key':''}'>${i===0 && link(r) ? `<a href='${link(r)}'>${fmt(c,r[c.name])||'—'}</a>` : fmt(c,r[c.name])}</td>`).join('')}</tr>`).join('') +
      (j.rows.length ? '' : `<tr><td colspan='${cols.length}' class='dj-null'>No rows.</td></tr>`) + `</tbody></table>`;
    const pages = Math.ceil(j.total/PAGE);
    if(pages > 1){ const pq = (i) => { const n = new URLSearchParams(qs); n.set('p', i); return `#${t.name}/?${n}`; };
      document.getElementById('pager').innerHTML = Array.from({length:pages},(_,i)=> i===p ? `<span class='dj-cur'>${i+1}</span>` : `<a href='${pq(i)}'>${i+1}</a>`).slice(Math.max(0,p-8), p+9).join(' ') + ` <span class='dj-null'>· ${PAGE} per page</span>`; }
    renderFilters(t, qs);
  } catch(e){ document.getElementById('rows').innerHTML = `<div class='dj-warn'>${esc(e.message)}</div>`; }
}
function doSearch(ev, tname){ ev.preventDefault(); const n = new URLSearchParams(); const q = ev.target.q.value.trim(); if(q) n.set('q', q); location.hash = `#${tname}/?${n}`; return false; }
async function renderFilters(t, qs){
  const el = document.getElementById('filters'); if(!el) return;
  const cands = t.columns.filter(c => (c.type==='text' || c.type==='smallint' || c.type==='boolean' || c.type==='integer') && !FILTER_SKIP.test(c.name)).slice(0, 8);
  if(!cands.length){ el.innerHTML=''; return; }
  el.innerHTML = `<div class='dj-module dj-filters'><h2>Filter</h2><div id='fbody'>…</div></div>`;
  const parts = await Promise.all(cands.map(async c => { try { const j = await getJSON(`/distinct?table=${t.name}&col=${c.name}`); return [c, j]; } catch(e){ return [c, null]; } }));
  const body = parts.filter(([c,j]) => j && !j.truncated && j.values.length > 1 && j.values.length <= 40).map(([c,j]) => {
    const cur = qs.get('f.'+c.name);
    const opt = (val, label, n) => { const q2 = new URLSearchParams(qs); q2.delete('p'); if(val===null) q2.delete('f.'+c.name); else q2.set('f.'+c.name, val); return `<li class='${(val===null?!cur:cur===val)?'dj-sel':''}'><a href='#${t.name}/?${q2}'>${esc(label)}</a>${n!=null?` <span class='dj-null'>${n}</span>`:''}</li>`; };
    return `<h3>By ${esc(c.name.replace(/_/g,' '))}</h3><ul>${opt(null,'All')}${j.values.map(v=>opt(v.v==null?'∅':v.v, v.v==null?'(empty)':v.v, v.n)).join('')}</ul>`;
  }).join('');
  document.getElementById('fbody').innerHTML = body || `<div class='dj-null'>No low-cardinality columns.</div>`;
}

// ---------- change form
async function renderForm(t, key){
  const adding = !key;
  crumbs([`<a href='#${t.name}'>${esc(title(t.name))}</a>`, `<b>${adding ? 'Add' : esc(Object.values(key).join(' / '))}</b>`]);
  const v = document.getElementById('view');
  const canEdit = t.writable && ROLE==='editor';
  let row = {};
  if(!adding){
    try { const j = await getJSON(`/rows?table=${t.name}&limit=2&${(t.key||[]).map(k=>`f.${k}=${encodeURIComponent(key[k]===''?'∅':key[k])}`).join('&')}`);
      if(!j.rows.length){ v.innerHTML = `<div class='dj-warn'>Row not found.</div>`; return; } row = j.rows[0]; }
    catch(e){ v.innerHTML = `<div class='dj-warn'>${esc(e.message)}</div>`; return; }
  }
  const field = (c) => {
    const isKey = (t.key||[]).includes(c.name), ro = !canEdit || c.generated || (isKey && !adding);
    const val = row[c.name];
    let input;
    if(ro) input = `<div class='dj-rovalue'>${val==null ? '<span class="dj-null">—</span>' : esc(val)}</div>`;
    else if(c.type==='boolean') input = `<select name='${c.name}'><option value='' ${val==null?'selected':''}>—</option><option value='true' ${val===true?'selected':''}>yes</option><option value='false' ${val===false?'selected':''}>no</option></select>`;
    else if(c.type==='date') input = `<input type='date' name='${c.name}' value='${esc(val||'')}'>`;
    else if(isNum(c)) input = `<input type='number' step='any' name='${c.name}' value='${esc(val==null?'':val)}'>`;
    else if(c.type==='text' && (LONG_TEXT.some(w=>c.name.includes(w)) || String(val||'').length > 120)) input = `<textarea name='${c.name}' rows='3'>${esc(val||'')}</textarea>`;
    else input = `<input type='text' name='${c.name}' value='${esc(val==null?'':val)}'>`;
    return `<div class='dj-row'><label>${esc(c.name)}${isKey?" <span class='dj-tag'>key</span>":''}${!c.nullable&&!c.has_default?" <span class='dj-req'>*</span>":''}</label>${input}<div class='dj-help'>${esc(c.type)}</div></div>`;
  };
  const keyCols = t.columns.filter(c=>(t.key||[]).includes(c.name)), other = t.columns.filter(c=>!(t.key||[]).includes(c.name));
  v.innerHTML = `<h1>${adding?'Add':'Change'} ${esc(title(t.name).toLowerCase())}</h1>
   ${canEdit ? '' : `<div class='dj-ro'>${!t.writable ? `Read-only here: owned by <b>${esc(t.owner)}</b>.` : 'Viewing. Log in as editor to change this row.'}</div>`}
   <form id='f' class='dj-form' onsubmit='return false'>
    <fieldset><h2>Key</h2>${keyCols.map(field).join('')}</fieldset>
    <fieldset><h2>Fields</h2>${other.map(field).join('')}</fieldset>
    ${canEdit ? `<div class='dj-submit'>
      ${adding ? '' : `<button type='button' class='dj-del' onclick='delRow("${t.name}")'>Delete</button>`}
      <button type='button' class='dj-save' onclick='saveRow("${t.name}", ${adding}, "list")'>Save</button>
      <button type='button' onclick='saveRow("${t.name}", ${adding}, "add")'>Save and add another</button>
      <button type='button' onclick='saveRow("${t.name}", ${adding}, "stay")'>Save and continue editing</button></div>` : ''}
   </form>
   ${adding ? '' : `<div class='dj-module' style='margin-top:18px'><h2>History</h2><div id='hist' class='dj-recent'>…</div></div>`}`;
  v._row = row; v._key = key;
  if(!adding) loadHistory(t, row);
}
async function loadHistory(t, row){
  const rk = (t.key||[]).map(k=>row[k]==null?'':String(row[k])).join('/');
  const el = document.getElementById('hist'); if(!el) return;
  try { const j = await getJSON(`/rows?table=entry_audit&order=at&dir=desc&limit=50&f.table_name=${encodeURIComponent(t.name)}&f.row_key=${encodeURIComponent(rk)}`);
    el.innerHTML = j.rows.length ? j.rows.map(r=>`<div class='dj-rec'><span class='dj-recwho'>${esc(r.entered_by)}</span> · ${esc(r.at)} — <b>${esc(r.field)}</b>: ${r.old_value==null?'—':esc(r.old_value)} → ${r.new_value==null?'—':esc(r.new_value)}</div>`).join('') : `<div class='dj-null'>No recorded changes for this row (loaded before the audit trail existed, or never edited).</div>`; }
  catch(e){ el.innerHTML = `<div class='dj-warn'>${esc(e.message)}</div>`; }
}
async function saveRow(tname, adding, after){
  const t = BY_TABLE[tname], v = document.getElementById('view'), f = document.getElementById('f');
  const by = editorName(); if(!by) return msg('A name is required for the audit trail.', 'err');
  const rowVals = {};
  for(const c of t.columns){ const el = f.elements[c.name]; if(!el) continue; rowVals[c.name] = el.value; }
  try {
    const j = await postJSON('/save', {table: tname, key: adding ? null : v._key, row: rowVals, by});
    msg(adding ? `Added ${title(tname).toLowerCase()} ${Object.values(j.key).join(' / ')}.` : `Saved ${j.changes} change${j.changes===1?'':'s'}.`);
    if(after === 'add') location.hash = `#${tname}/add`;
    else if(after === 'stay') { location.hash = `#${tname}/change?${keyQS(t, j.row)}`; route(); }
    else location.hash = `#${tname}`;
    schemaCountsDirty = true;
  } catch(e){ msg(e.message, 'err'); }
}
async function delRow(tname){
  const t = BY_TABLE[tname], v = document.getElementById('view');
  if(!confirm(`Delete this ${title(tname).toLowerCase()} row? This cannot be undone (the deleted values are kept in the audit trail).`)) return;
  const by = editorName(); if(!by) return;
  try { await postJSON('/delete', {table: tname, key: v._key, by}); msg('Row deleted.'); location.hash = `#${tname}`; schemaCountsDirty = true; }
  catch(e){ msg(e.message, 'err'); }
}
let schemaCountsDirty = false;

// ---------- boot
async function boot(){
  await refreshRole();
  try {
    const j = await getJSON('/schema' + (schemaCountsDirty ? '?refresh=1' : ''));
    SCHEMA = Object.fromEntries(j.tables.map(t=>[t.name, t])); BY_TABLE = SCHEMA; schemaCountsDirty = false;
    route();
  } catch(e){ document.getElementById('view').innerHTML = `<div class='dj-warn'>Cannot reach the data service (${esc(e.message)}). Reads need the site token; check that the proxy is running.</div>`; }
}
boot();
</script>
<style>
#adm { --dj-primary:#79aec8; --dj-secondary:#417690; --dj-accent:#f5dd5d; --dj-link:#447e9b; --dj-border:#ddd;
  font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif; font-size:13px; color:#333; background:#fff;
  border:1px solid var(--dj-border); border-radius:6px; overflow:hidden; margin-top:6px; }
#adm a { color:var(--dj-link); text-decoration:none; cursor:pointer; } #adm a:hover { color:#036; text-decoration:underline; }
.dj-head { background:var(--dj-secondary); color:#fff; padding:14px 40px; display:flex; justify-content:space-between; align-items:center; }
#adm .dj-brand a { color:#f5f5f5; font-size:22px; font-weight:300; letter-spacing:.2px; } #adm .dj-brand a:hover { color:#fff; text-decoration:none; }
.dj-user { font-size:12px; color:#ddd; } #adm .dj-user a { color:#fff; text-decoration:underline; } .dj-user b { color:#fff; }
.dj-crumbs { background:var(--dj-primary); color:#c4dce8; padding:10px 40px; font-size:13px; } #adm .dj-crumbs a { color:#fff; } .dj-crumbs b { color:#fff; font-weight:400; }
.dj-msg { margin:0; padding:10px 40px; font-size:13px; background:#dfd; color:#155724; border-bottom:1px solid #cec; }
.dj-msg.err { background:#ffefef; color:#ba2121; border-color:#f3c9c9; }
.dj-body { padding:20px 40px 30px; min-height:400px; background:#fff; }
.dj-cols { display:grid; grid-template-columns: minmax(0,1fr) 280px; gap:24px; align-items:start; }
@media (max-width:1000px) { .dj-cols { grid-template-columns:1fr; } }
.dj-module { background:#fff; border:1px solid #eee; border-radius:4px; margin-bottom:24px; overflow:hidden; }
.dj-module h2 { margin:0; background:var(--dj-primary); color:#fff; font-size:13px; font-weight:400; padding:8px 12px; letter-spacing:.3px; text-transform:uppercase; display:flex; justify-content:space-between; }
.dj-owner { font-size:11px; opacity:.8; font-weight:400; text-transform:none; letter-spacing:0; }
.dj-modtbl { width:100%; border-collapse:collapse; } .dj-modtbl th { text-align:left; font-weight:400; padding:8px 12px; border-bottom:1px solid #eee; width:60%; }
.dj-modtbl td { padding:8px 12px; border-bottom:1px solid #eee; white-space:nowrap; } .dj-modtbl tr:last-child td, .dj-modtbl tr:last-child th { border-bottom:0; }
.dj-modtbl tr:hover th, .dj-modtbl tr:hover td { background:#f8fbfd; }
.dj-n { color:#999; font-size:11.5px; text-align:right; font-variant-numeric:tabular-nums; } .dj-act { text-align:right; font-size:12px; }
#adm .dj-add { color:#417690; } .dj-add::before { content:''; } #adm .dj-chg { color:#417690; }
.dj-tag { display:inline-block; font-size:10px; background:#eef2f5; color:#557; padding:0 5px; border-radius:6px; margin-left:4px; vertical-align:1px; }
.dj-req { color:#ba2121; }
.dj-recent { padding:8px 12px; font-size:12px; } .dj-rec { padding:6px 0; border-bottom:1px solid #f0f0f0; line-height:1.4; } .dj-rec:last-child { border-bottom:0; }
#adm .dj-recwho { color:#417690; font-weight:600; } .dj-about { padding:10px 12px; font-size:12px; color:#555; line-height:1.5; }
.dj-null { color:#999; } .dj-warn { color:#ba2121; padding:10px 0; } .dj-loading { color:#999; padding:20px 0; }
.dj-listhead { display:flex; justify-content:space-between; align-items:center; gap:16px; margin-bottom:8px; }
#adm h1 { font-size:20px; font-weight:300; color:#666; margin:0 0 10px; } #adm h1 .dj-owner { color:#999; }
#adm .dj-btn { background:var(--dj-secondary); color:#fff !important; padding:7px 14px; border-radius:4px; font-size:12.5px; white-space:nowrap; } #adm .dj-btn:hover { background:#205067; text-decoration:none !important; }
.dj-ro { background:#fff8e1; border:1px solid #f0dc9c; color:#6b5310; padding:7px 12px; border-radius:4px; font-size:12px; }
.dj-search { display:flex; gap:8px; align-items:center; margin:6px 0 10px; } .dj-search input { padding:6px 10px; border:1px solid #ccc; border-radius:4px; width:320px; font-size:13px; }
.dj-search button { padding:6px 12px; background:var(--dj-primary); color:#fff; border:0; border-radius:4px; cursor:pointer; } .dj-count { color:#666; font-size:12px; margin-left:auto; } .dj-clear { font-size:12px; }
.dj-scroll { overflow-x:auto; border:1px solid #eee; border-radius:4px; }
table.dj-list { border-collapse:collapse; font-size:12.5px; width:100%; } table.dj-list th { background:#f6f6f6; text-align:left; padding:7px 10px; border-bottom:1px solid #ddd; white-space:nowrap; position:sticky; top:0; font-weight:600; color:#666; }
#adm table.dj-list th a { color:#666; } table.dj-list th.dj-sorted { background:#e8eef3; } #adm table.dj-list th.dj-sorted a { color:#333; }
table.dj-list td { padding:6px 10px; border-bottom:1px solid #eee; vertical-align:top; max-width:360px; overflow-wrap:break-word; } table.dj-list tr:nth-child(even) td { background:#f9f9f9; } table.dj-list tr:hover td { background:#eef4f9; }
table.dj-list td.dj-num, table.dj-list th.dj-num { text-align:right; font-variant-numeric:tabular-nums; } table.dj-list td.dj-key { font-weight:600; }
.dj-pager { margin:10px 0; font-size:12.5px; display:flex; gap:6px; flex-wrap:wrap; } .dj-pager .dj-cur { background:var(--dj-primary); color:#fff; padding:0 7px; border-radius:3px; } #adm .dj-pager a { padding:0 6px; }
.dj-filters h3 { font-size:12px; text-transform:uppercase; letter-spacing:.3px; color:#666; margin:10px 12px 2px; font-weight:600; } .dj-filters ul { list-style:none; margin:0 0 6px; padding:0 12px; }
.dj-filters li { padding:2px 0 2px 8px; border-left:3px solid transparent; font-size:12.5px; } .dj-filters li.dj-sel { border-left-color:var(--dj-primary); font-weight:600; }
.dj-form fieldset { border:1px solid #eee; border-radius:4px; padding:0 0 6px; margin:0 0 16px; } .dj-form fieldset h2 { margin:0 0 6px; background:var(--dj-primary); color:#fff; font-size:12px; font-weight:400; padding:7px 12px; text-transform:uppercase; }
.dj-row { display:grid; grid-template-columns:200px minmax(0,1fr) 120px; gap:12px; align-items:start; padding:8px 12px; border-bottom:1px solid #f2f2f2; } .dj-row:last-child { border-bottom:0; }
.dj-row label { font-weight:600; color:#444; padding-top:6px; word-break:break-word; } .dj-row .dj-help { color:#999; font-size:11px; padding-top:8px; }
.dj-row input, .dj-row select, .dj-row textarea { width:100%; max-width:560px; padding:6px 8px; border:1px solid #ccc; border-radius:4px; font-size:13px; font-family:inherit; box-sizing:border-box; }
.dj-row textarea { resize:vertical; } .dj-rovalue { padding:6px 0; color:#333; white-space:pre-wrap; word-break:break-word; }
.dj-submit { display:flex; gap:8px; align-items:center; background:#f8f8f8; border:1px solid #eee; border-radius:4px; padding:12px; }
.dj-submit button { padding:8px 14px; border:0; border-radius:4px; background:var(--dj-primary); color:#fff; cursor:pointer; font-size:13px; } .dj-submit button:hover { background:#609ab6; }
.dj-submit .dj-save { background:var(--dj-secondary); font-weight:600; } .dj-submit .dj-del { background:#ba2121; margin-right:auto; }
</style>
"""
