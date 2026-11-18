"""Assistant use (assistant-usage.html, admin site): how the AA assistant is used, from the record
of its questions (aa.assistant_question, D248; owner, 2026-11-18: "can we start recording people's
queries? … we want to see how people are using it so we can improve it", then "use our DB. do it
like how we have the site analytics, and add an admin page for this").

Live only: the page loads the rows from the proxy's GET /assistant-usage when it opens, with the
admin pages' viewer token, and again every minute while the tab is in view. Unlike Site usage it
carries no copy of the rows: the questions are in no built page and in no snapshot (they are kept
180 days, a snapshot for good), so without the proxy the page says so and shows nothing.
The sums are done in the browser, so the period can change without a rebuild. One chart (questions
per day, the site's accent: a single series needs no legend), every list a plain table, and the
texts (questions, comments, answers) always escaped.
"""
from page_usage import CSS as USAGE_CSS

PAGE, TITLE = "assistant-usage.html", "Assistant use"

CSS = USAGE_CSS + """
.au-q { white-space:pre-wrap; word-break:break-word; }
.au-list { border-collapse:collapse; width:100%; font-size:13px; }
.au-list th, .au-list td { text-align:left; padding:6px 8px; border-bottom:1px solid #eee; vertical-align:top; }
.au-list th { font-weight:600; color:#444; background:#fafafa; }
.au-list td.when { white-space:nowrap; color:#555; }
.au-tag { display:inline-block; font-size:11.5px; padding:1px 7px; border-radius:9px; background:#eef1f5; color:#333; margin:0 4px 2px 0; }
.au-tag.bad { background:#fde8e8; color:#8a1c1c; } .au-tag.good { background:#e6f4ea; color:#1c5c32; }
.au-ans { margin-top:6px; } .au-ans summary { cursor:pointer; color:#444; font-size:12.5px; }
.au-ans .txt { white-space:pre-wrap; word-break:break-word; background:#fafafa; border:1px solid #eee; border-radius:6px;
  padding:8px 10px; margin-top:4px; max-height:320px; overflow-y:auto; font-size:12.5px; }
.au-find { font-size:13px; padding:5px 9px; border:1px solid #c9c9c9; border-radius:6px; width:min(360px, 100%); margin:0 0 8px; }
.au-more { font-size:12.5px; color:#666; margin-top:6px; }
"""


def build(page):
    from admin_page import PROXY_URL, site_token
    body = f"""<style>{CSS}</style>
<p class='us-intro'>How the AA assistant is used: the questions put to it on its own page and in the
panel of the development site, what it used to answer them, how it went and what readers thought of
the answers (D248; the rows: the <a href='admin.html#assistant_question'>assistant_question table</a>).
Loaded live from the database when this page opens and every minute while it is in view.
No name, login or IP address is recorded: everyone shares one password, so the questions cannot be
tied to a person. The answer is kept only where the question failed or the reader marked it
not helpful. Questions, comments and answers are removed after <span id='au-keep'>180</span> days;
the counts stay.</p>
<p class='us-live' id='us-live' role='status'></p>
<div class='us-filter' role='group' aria-label='Period'>
 <span class='lab' id='us-plab'>Period</span>
 <span class='us-seg' aria-labelledby='us-plab'>
  <button type='button' data-d='7' aria-pressed='false'>7 days</button><button type='button' data-d='30' aria-pressed='true'>30 days</button><button type='button' data-d='90' aria-pressed='false'>90 days</button><button type='button' data-d='all' aria-pressed='false'>All</button>
 </span>
 <span class='us-span' id='us-span'></span>
</div>
<div id='us-body'></div>
<script src='chart.umd.js'></script>
<script>
window.PROXY = new URLSearchParams(location.search).get('proxy') || '{PROXY_URL}';
window.SITE_TOKEN = '{site_token()}';
{SCRIPT}
</script>"""
    page(PAGE, TITLE, body)


SCRIPT = r"""
(function(){
const ACCENT = '#007ce0', INK = '#52514e', GRID = '#ececec';
const RM = matchMedia('(prefers-reduced-motion: reduce)').matches;
let R = [], NAMES = {}, TODAY = new Date().toISOString().slice(0, 10), loaded = false;
let period = 30, liveSpan = 90, sig = '', find = '';
const HAZ = {storm: 'tropical cyclone', flood: 'floods', drought: 'drought', cholera: 'cholera', plague: 'plague',
             locusts: 'locusts', food_insecurity: 'food insecurity'};
const OUT = {answered: 'answered', no_answer: 'no answer given', error: 'failed', limit: 'usage limit reached',
             timeout: 'ran out of time', stopped: 'stopped by the reader'};
const TOOL = {aa_sql: 'a query of the database', aa_tables: 'the list of tables', aa_chart: 'a chart', aa_export: 'a CSV file',
              aa_documents: 'the list of framework documents', aa_doc_search: 'a search of framework documents',
              aa_doc_read: 'a framework document read', WebSearch: 'a web search', WebFetch: 'a web page read'};
const fmt = n => n.toLocaleString('en-US');
const pct = (a, b) => b ? Math.round(100 * a / b) + '%' : '–';
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const dOf = s => new Date(s + 'T00:00:00Z');
const iso = d => d.toISOString().slice(0, 10);
const dayLabel = s => dOf(s).toLocaleDateString('en-GB', {weekday: 'short', day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'});
const tick = s => dOf(s).toLocaleDateString('en-GB', {day: 'numeric', month: 'short', timeZone: 'UTC'});
const when = at => dOf(at.slice(0, 10)).toLocaleDateString('en-GB', {day: 'numeric', month: 'short', timeZone: 'UTC'}) + ' ' + at.slice(11, 16);
const median = xs => { const s = xs.filter(x => x != null).sort((a, b) => a - b); return s.length ? s[Math.floor((s.length - 1) / 2)] : null; };
function count(rows, keys){ const m = new Map(); rows.forEach(r => keys(r).forEach(k => m.set(k, (m.get(k) || 0) + 1))); return m; }
function top(m, k){ return [...m.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0]))).slice(0, k); }
function table(head, rows, empty){
  if(!rows.length) return `<div class='us-empty'>${esc(empty || 'Nothing recorded in this period.')}</div>`;
  return `<div class='xscroll'><table class='us-t'><thead><tr>${head.map(h => `<th${h.num ? " class='num'" : ''}>${esc(h.t)}</th>`).join('')}</tr></thead><tbody>`
    + rows.map(r => `<tr>${r.map((c, i) => `<td class='${head[i].num ? 'num' : ''}${head[i].wrap ? ' w' : ''}'>${esc(c)}</td>`).join('')}</tr>`).join('')
    + `</tbody></table></div>`; }
// one question as a row of a list: when, the question, what is known about it, the answer if kept
function tags(r){
  const t = [];
  if(r.outcome !== 'answered') t.push(`<span class='au-tag bad'>${esc(OUT[r.outcome] || r.outcome)}</span>`);
  if(r.rating === 1) t.push("<span class='au-tag good'>helpful</span>");
  if(r.rating === -1) t.push("<span class='au-tag bad'>not helpful</span>");
  if(r.missing) t.push("<span class='au-tag'>said something was missing</span>");
  r.countries.forEach(c => t.push(`<span class='au-tag'>${esc(NAMES[c] || c)}</span>`));
  r.hazards.forEach(h => t.push(`<span class='au-tag'>${esc(HAZ[h] || h)}</span>`));
  if(r.made_chart) t.push("<span class='au-tag'>chart</span>");
  if(r.made_file) t.push("<span class='au-tag'>CSV file</span>");
  if(r.used_documents) t.push("<span class='au-tag'>document text</span>");
  if(r.seconds != null) t.push(`<span class='au-tag'>${Math.round(r.seconds)} s</span>`);
  t.push(`<span class='au-tag'>${r.surface === 'panel' ? 'panel' + (r.from_page ? ' on ' + esc(r.from_page.replace(/\.html$/, '')) : '') : 'own page'}</span>`);
  return t.join('');
}
function qrow(r){
  const more = [r.comment ? `<div class='au-q'><b>Comment:</b> ${esc(r.comment)}</div>` : '',
                r.error ? `<div class='au-q'><b>Message shown:</b> ${esc(r.error)}</div>` : '',
                r.answer ? `<details class='au-ans'><summary>The answer given</summary><div class='txt'>${esc(r.answer)}</div></details>` : ''].join('');
  return `<tr><td class='when'>${esc(when(r.at))}</td><td><div class='au-q'>${r.question == null ? "<span class='us-empty'>(text removed after the keeping period)</span>" : esc(r.question)}</div>
<div style='margin-top:4px'>${tags(r)}</div>${more}</td></tr>`; }
function qlist(rows, empty, cap){
  if(!rows.length) return `<div class='us-empty'>${esc(empty)}</div>`;
  const shown = rows.slice(0, cap || 100);
  return `<div class='xscroll'><table class='au-list'><thead><tr><th>When (UTC)</th><th>Question</th></tr></thead><tbody>${shown.map(qrow).join('')}</tbody></table></div>`
    + (rows.length > shown.length ? `<div class='au-more'>The ${shown.length} most recent of ${fmt(rows.length)}.</div>` : ''); }
let charts = [];
function draw(days, quiet){
  if(!loaded) return;
  const opened = new Set([...document.querySelectorAll('#us-body details[id]')].filter(d => d.open).map(d => d.id));
  charts.forEach(c => c.destroy()); charts = [];
  const end = TODAY, first = R.length ? R[R.length - 1].at.slice(0, 10) : end;
  const start = days === 'all' ? (first < end ? first : end) : iso(new Date(dOf(end) - (days - 1) * 864e5));
  const P = R.filter(r => r.at.slice(0, 10) >= start && r.at.slice(0, 10) <= end);
  const span = [];
  for(let d = dOf(start); iso(d) <= end; d = new Date(+d + 864e5)) span.push(iso(d));
  document.getElementById('us-span').textContent = `${dayLabel(start)} – ${dayLabel(end)} (UTC)`;
  const n = P.length, convs = new Set(P.map(r => r.conversation || r.id)).size;
  const failed = P.filter(r => r.outcome !== 'answered' && r.outcome !== 'stopped');
  const up = P.filter(r => r.rating === 1).length, down = P.filter(r => r.rating === -1);
  const withOut = P.filter(r => r.made_chart || r.made_file).length;
  const med = median(P.filter(r => r.outcome === 'answered').map(r => r.seconds));
  const tile = (l, v, s) => `<div class='us-tile'><div class='l'>${esc(l)}</div><div class='v'>${esc(v)}</div><div class='s'>${esc(s)}</div></div>`;
  const perDay = count(P, r => [r.at.slice(0, 10)]);
  const byCountry = top(count(P, r => r.countries), 25), byHaz = top(count(P, r => r.hazards), 10);
  const byTable = top(count(P, r => r.tables_used), 25), byTool = top(count(P, r => r.tools), 12);
  const byWhere = top(count(P, r => [r.surface === 'panel' ? 'Panel on ' + (r.from_page ? r.from_page.replace(/\.html$/, '') : 'the development site (page not known)') : "The assistant's own page"]), 30);
  const byOutcome = top(count(P, r => [OUT[r.outcome] || r.outcome]), 10);
  const missing = P.filter(r => r.missing && r.outcome === 'answered');
  const f = find.trim().toLowerCase();
  const all = f ? P.filter(r => (r.question || '').toLowerCase().includes(f)) : P;
  document.getElementById('us-body').innerHTML = `
<div class='us-tiles'>
 ${tile('Questions', fmt(n), fmt(convs) + ' conversation' + (convs === 1 ? '' : 's'))}
 ${tile('Time to answer', med == null ? '–' : Math.round(med) + ' s', 'the middle one, of the answered')}
 ${tile('With a chart or a file', pct(withOut, n), fmt(withOut) + ' question' + (withOut === 1 ? '' : 's'))}
 ${tile('Used document text', pct(P.filter(r => r.used_documents).length, n), 'searched or read a framework document')}
 ${tile('Failed', fmt(failed.length), pct(failed.length, n) + ' of questions')}
 ${tile('Rated', fmt(up) + ' helpful · ' + fmt(down.length) + ' not', pct(up + down.length, n) + ' of questions rated')}
</div>
<div class='card us-card'><h2>Questions per day</h2><p class='sub'>UTC days.</p>
 <div class='us-chart'><canvas id='us-c1' role='img' aria-label='Questions per day; the same figures are in the table below'></canvas></div>
 <details id='au-d1'><summary>As a table</summary>${table([{t: 'Day'}, {t: 'Questions', num: true}], span.slice().reverse().map(d => [dayLabel(d), fmt(perDay.get(d) || 0)]))}</details>
</div>
<div class='card us-card'><h2>Marked not helpful</h2><p class='sub'>With the reader's comment where one was left, and the answer given.</p>
 ${qlist(down, 'No answer was marked not helpful in this period.')}</div>
<div class='card us-card'><h2>Failed</h2><p class='sub'>Questions that ended with an error, no answer, the time limit or the usage limit (a question the reader stopped is not a failure).</p>
 ${qlist(failed, 'No question failed in this period.')}</div>
<div class='card us-card'><h2>Answered, but something was missing</h2><p class='sub'>Answers whose wording says the assistant could not find something. Read from the wording, so a guess: some are wrongly here, and some are missed.</p>
 ${qlist(missing, 'No answer in this period says something was missing.', 50)}</div>
<div class='us-grid'>
 <div class='card us-card'><h2>Countries asked about</h2><p class='sub'>Named in the question or in the assistant's queries; a question can name several.</p>
  ${table([{t: 'Country'}, {t: 'Questions', num: true}, {t: 'Share', num: true}], byCountry.map(([c, k]) => [NAMES[c] || c, fmt(k), pct(k, n)]))}</div>
 <div class='card us-card'><h2>Hazards asked about</h2><p class='sub'>Named in the question or in the assistant's queries.</p>
  ${table([{t: 'Hazard'}, {t: 'Questions', num: true}, {t: 'Share', num: true}], byHaz.map(([h, k]) => [HAZ[h] || h, fmt(k), pct(k, n)]))}</div>
 <div class='card us-card'><h2>What the assistant used</h2><p class='sub'>The questions in which it used each of its tools.</p>
  ${table([{t: 'Tool'}, {t: 'Questions', num: true}, {t: 'Share', num: true}], byTool.map(([t, k]) => [TOOL[t] || t, fmt(k), pct(k, n)]))}</div>
 <div class='card us-card'><h2>Tables and views read</h2><p class='sub'>The tables and views its queries read, the 25 most used.</p>
  ${table([{t: 'Table or view', wrap: true}, {t: 'Questions', num: true}], byTable.map(([t, k]) => [t, fmt(k)]))}</div>
 <div class='card us-card'><h2>Where it was asked</h2><p class='sub'>The assistant's own page, or the panel and the page of the development site it was open on.</p>
  ${table([{t: 'Where'}, {t: 'Questions', num: true}, {t: 'Share', num: true}], byWhere.map(([w, k]) => [w, fmt(k), pct(k, n)]))}</div>
 <div class='card us-card'><h2>How the questions ended</h2><p class='sub'>Every question of the period.</p>
  ${table([{t: 'Ended'}, {t: 'Questions', num: true}, {t: 'Share', num: true}], byOutcome.map(([o, k]) => [o, fmt(k), pct(k, n)]))}</div>
</div>
<div class='card us-card'><h2>All questions</h2><p class='sub'>The most recent first.</p>
 <input type='search' class='au-find' id='au-find' placeholder='Find in the questions' aria-label='Find in the questions' value="${esc(find)}">
 <div id='au-all'>${qlist(all, f ? 'No question of this period has that text.' : 'No question was asked in this period.', 200)}</div></div>`;
  document.querySelectorAll('#us-body details[id]').forEach(d => { if(opened.has(d.id)) d.open = true; });
  const fi = document.getElementById('au-find');
  fi.addEventListener('input', () => { find = fi.value; const q = find.trim().toLowerCase();
    document.getElementById('au-all').innerHTML = qlist(q ? P.filter(r => (r.question || '').toLowerCase().includes(q)) : P,
      q ? 'No question of this period has that text.' : 'No question was asked in this period.', 200); });
  if(typeof Chart === 'undefined') return;
  Chart.defaults.font.family = "-apple-system,'Segoe UI',Roboto,sans-serif";
  Chart.defaults.color = INK;
  Chart.defaults.animation = RM || quiet ? false : {};
  charts.push(new Chart(document.getElementById('us-c1'), {type: 'bar',
    data: {labels: span, datasets: [{data: span.map(d => perDay.get(d) || 0), backgroundColor: ACCENT,
      borderRadius: 4, maxBarThickness: 24, categoryPercentage: 0.9, barPercentage: 0.9}]},
    options: {maintainAspectRatio: false, plugins: {legend: {display: false},
      tooltip: {backgroundColor: '#1f2a44', padding: 8, displayColors: false, titleFont: {weight: '600'},
        callbacks: {title: it => dayLabel(it[0].label), label: it => `${fmt(it.raw)} question${it.raw === 1 ? '' : 's'}`}}},
      scales: {x: {grid: {display: false}, ticks: {autoSkip: true, maxRotation: 0, callback(v){ return tick(this.getLabelForValue(v)); }}},
               y: {beginAtZero: true, grid: {color: GRID}, border: {display: false}, ticks: {precision: 0}}}}}));
}
// ---------- live: GET /assistant-usage on the proxy, the last 90 days (every period but All) or everything
const liveEl = document.getElementById('us-live');
function say(text, cls){ liveEl.textContent = text; liveEl.className = 'us-live ' + (cls || ''); }
const hhmm = s => new Date(s).toISOString().slice(11, 16);
async function live(){
  const since = liveSpan === 'all' ? '' : iso(new Date(Date.now() - (liveSpan - 1) * 864e5));
  try {
    const r = await fetch(PROXY + '/assistant-usage' + (since ? '?since=' + since : ''), {headers: {'x-site-token': SITE_TOKEN}, cache: 'no-store'});
    const j = await r.json().catch(() => ({}));
    if(!r.ok || !j.ok) throw new Error(j.error || 'HTTP ' + r.status);
    const s = liveSpan + '|' + j.rows.length + '|' + j.rows.filter(x => x.rating != null).length + '|' + (j.rows[0] ? j.rows[0].id : '') + '|' + j.at.slice(0, 10);
    NAMES = j.names || {}; TODAY = j.at.slice(0, 10);
    if(j.keep_days) document.getElementById('au-keep').textContent = j.keep_days;
    say(`Live: the record as of ${hhmm(j.at)} UTC, refreshed every minute while this page is in view.`
        + (j.recording ? '' : ' Recording is not switched on: the assistant has no key for it yet.'), j.recording ? 'on' : 'off');
    if(s !== sig || !loaded){ sig = s; R = j.rows; loaded = true; draw(period, true); }
  } catch(e){
    say(loaded ? `The last refresh failed (${e.message}); showing the record loaded before.`
               : `The record could not be loaded (${e.message}). This page holds no copy of it.`, 'off');
  }
}
const seg = document.querySelectorAll('.us-seg button');
seg.forEach(b => b.addEventListener('click', () => {
  seg.forEach(x => x.setAttribute('aria-pressed', x === b ? 'true' : 'false'));
  period = b.dataset.d === 'all' ? 'all' : +b.dataset.d;
  draw(period);
  if(period === 'all' && liveSpan !== 'all'){ liveSpan = 'all'; live(); } }));
say('Loading the record…');
live();
setInterval(() => { if(document.visibilityState === 'visible' && document.activeElement !== document.getElementById('au-find')) live(); }, 60000);
document.addEventListener('visibilitychange', () => { if(document.visibilityState === 'visible') live(); });
})();
"""
