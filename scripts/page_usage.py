"""Site usage (usage.html, admin site): how the open site is used, from its daily page counts
(aa.page_count, D197; owner, 2026-11-04: "is there an analytics dashboard? put one in the admin site").

Live (owner, 2026-11-04: "yeah do the live one, w/o hours"): the page loads the counts from the
proxy's GET /usage when it opens, with the admin pages' viewer token, and again every minute while
the tab is in view. It also carries the snapshot's rows, built like every page (D17), and shows
those, saying so, when the proxy cannot be reached. The sums are done in the browser, so the
period can change without a rebuild: last 7, 30 or 90 days, or everything. One chart per question (views per day; frameworks viewed on the map), one colour
(the site's accent: a single series needs no legend), every chart with its table beside it, and
plain tables for the lists (pages, referring sites, languages, devices, downloads, links out).
"""
import json
from datetime import date

import pandas as pd
import sqlalchemy as sa

PAGE, TITLE = "usage.html", "Site usage"
COLS = ["day", "page", "event", "detail", "lang", "device", "referrer", "n"]
HAZARD_WORDS = {"storm": "tropical cyclone", "flood": "floods", "drought": "drought", "cholera": "cholera",
                "plague": "plague", "locusts": "locusts", "food_insecurity": "food insecurity",
                "general": "no specific hazard"}

CSS = """
.us-intro { max-width:880px; color:#444; margin:0 0 12px; line-height:1.5; }
.us-filter { display:flex; gap:8px; align-items:center; margin:4px 0 16px; flex-wrap:wrap; }
.us-filter .lab { font-size:13px; color:#555; margin-right:2px; }
.us-seg { display:inline-flex; border:1px solid #c9c9c9; border-radius:6px; overflow:hidden; }
.us-seg button { border:0; background:#fff; padding:5px 12px; font-size:13px; cursor:pointer; color:#333; }
.us-seg button + button { border-left:1px solid #c9c9c9; }
.us-seg button[aria-pressed='true'] { background:#1f2a44; color:#fff; }
.us-seg button:focus-visible { outline:2px solid var(--accent); outline-offset:-2px; }
.us-span { font-size:12.5px; color:#666; }
.us-tiles { display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:12px; margin:0 0 16px; }
.us-tile { background:#fff; border:1px solid #e0e0e0; border-radius:6px; padding:12px 14px; }
.us-tile .l { font-size:12.5px; color:#555; }
.us-tile .v { font-size:26px; font-weight:600; margin-top:2px; color:#1d1d1b; }
.us-tile .s { font-size:12px; color:#777; margin-top:2px; }
.us-card { margin:0 0 16px; }
.us-card h2 { font-size:15px; margin:0 0 2px; }
.us-card .sub { font-size:12.5px; color:#666; margin:0 0 10px; }
.us-chart { position:relative; height:260px; }
.us-chart.tall { height:auto; }
.us-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(340px, 1fr)); gap:16px; }
.us-t { border-collapse:collapse; width:100%; font-size:13px; }
.us-t th, .us-t td { text-align:left; padding:4px 8px; border-bottom:1px solid #eee; vertical-align:top; }
.us-t th { font-weight:600; color:#444; background:#fafafa; }
.us-t td.num, .us-t th.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
.us-t td.w { word-break:break-all; }
.us-card details { margin-top:8px; font-size:13px; } .us-card details summary { cursor:pointer; color:#444; }
.us-card details .xscroll { max-height:320px; overflow-y:auto; margin-top:6px; }
.us-empty { color:#666; font-style:italic; padding:6px 0; }
.us-live { font-size:12.5px; color:#555; margin:-4px 0 10px; min-height:1.2em; }
.us-live::before { content:''; display:inline-block; width:8px; height:8px; border-radius:50%;
  background:#9e9e9e; margin-right:6px; vertical-align:1px; }
.us-live.on::before { background:#1c7c3c; } .us-live.off { color:#8a5c0a; }
.us-live.off::before { background:#c27c0e; }
"""


def _rows(e):
    with e.connect() as c:
        if not c.execute(sa.text("SELECT to_regclass('aa.page_count') IS NOT NULL")).scalar():
            return pd.DataFrame(columns=COLS), {}
        df = pd.read_sql(sa.text("SELECT day::text AS day, page, event, detail, lang, device, referrer, n "
                                 "FROM aa.page_count ORDER BY day"), c)
        names = dict(c.execute(sa.text("SELECT country_iso3, max(country_name) FROM aa.country_hazard "
                                       "GROUP BY country_iso3")).all())
    return df, names


def build(e, page, stamp):
    from admin_page import PROXY_URL, site_token
    df, names = _rows(e)
    # page names travel without '.html': the admin build rewrites any quoted public page name in a
    # page (to its ../dev/ address), the data included
    data = [[r.day, r.page.removesuffix(".html"), r.event, r.detail, r.lang, r.device, r.referrer, int(r.n)]
            for r in df.itertuples()]
    used = {d.split("/")[0] for d in df["detail"] if d} if len(df) else set()
    payload = {"rows": data, "names": {k: v for k, v in names.items() if k in used},
               "hazards": HAZARD_WORDS, "today": date.today().isoformat(), "stamp": stamp}
    js = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    body = f"""<style>{CSS}</style>
<p class='us-intro'>How readers use the open site (the pages at the root of the site, never
<code>dev/</code> or <code>admin/</code>), from its daily counts (D197), loaded live from the database
when this page opens and every minute while it is in view (the rows: the
<a href='admin.html#page_count'>page_count table</a>). The counts are indicative, never audited: they
hold no IP address or identifier, so they cannot tell readers apart or say how many people visited.</p>
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
const USAGE = {js};
{SCRIPT}
</script>"""
    page(PAGE, TITLE, body)


SCRIPT = r"""
(function(){
const ACCENT = '#007ce0', INK = '#52514e', GRID = '#ececec';
const RM = matchMedia('(prefers-reduced-motion: reduce)').matches;
const toRows = rows => rows.map(r => ({day: r[0], page: r[1] + '.html', event: r[2], detail: r[3], lang: r[4], device: r[5], ref: r[6], n: r[7]}));
// the snapshot's rows until the live ones arrive (and if they never do)
let R = toRows(USAGE.rows), NAMES = Object.assign({}, USAGE.names), TODAY = USAGE.today;
let period = 30, liveSpan = 90, sig = '', isLive = false;
const LANGS = {en: 'English', fr: 'French', es: 'Spanish'};
const DEV = {phone: 'Phone', desktop: 'Desktop or tablet'};
const fmt = n => n.toLocaleString('en-US');
const pct = (a, b) => b ? Math.round(100 * a / b) + '%' : '–';
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const dOf = s => new Date(s + 'T00:00:00Z');
const dec = u => { try { return decodeURI(u); } catch(e){ return u; } };
const iso = d => d.toISOString().slice(0, 10);
const dayLabel = s => dOf(s).toLocaleDateString('en-GB', {weekday: 'short', day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'});
const tick = s => dOf(s).toLocaleDateString('en-GB', {day: 'numeric', month: 'short', timeZone: 'UTC'});
function place(d){ const [iso3, hz] = d.split('/'); const c = NAMES[iso3] || iso3;
  return hz ? c + ' · ' + (USAGE.hazards[hz] || hz) : c + ' (country)'; }
function sum(rows, key){ const m = new Map(); rows.forEach(r => m.set(key(r), (m.get(key(r)) || 0) + r.n)); return m; }
function top(m, k){ return [...m.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0]))).slice(0, k); }
function table(head, rows, empty){
  if(!rows.length) return `<div class='us-empty'>${esc(empty || 'Nothing counted in this period.')}</div>`;
  return `<div class='xscroll'><table class='us-t'><thead><tr>${head.map(h => `<th${h.num ? " class='num'" : ''}>${esc(h.t)}</th>`).join('')}</tr></thead><tbody>`
    + rows.map(r => `<tr>${r.map((c, i) => `<td class='${head[i].num ? 'num' : ''}${head[i].wrap ? ' w' : ''}'>${esc(c)}</td>`).join('')}</tr>`).join('')
    + `</tbody></table></div>`; }
let charts = [];
function draw(days, quiet){
  // a redraw keeps the reader's place: the tables they opened stay open, nothing animates
  const opened = [...document.querySelectorAll('#us-body details')].map(d => d.open);
  charts.forEach(c => c.destroy()); charts = [];
  const end = TODAY, first = R.length ? R[0].day : end;
  const start = days === 'all' ? (first < end ? first : end) : iso(new Date(dOf(end) - (days - 1) * 864e5));
  const P = R.filter(r => r.day >= start && r.day <= end);
  const span = [];
  for(let d = dOf(start); iso(d) <= end; d = new Date(+d + 864e5)) span.push(iso(d));
  document.getElementById('us-span').textContent = `${dayLabel(start)} – ${dayLabel(end)} (UTC)`;
  const ev = e => P.filter(r => r.event === e), tot = e => ev(e).reduce((a, r) => a + r.n, 0);
  const V = ev('view'), views = tot('view');
  const notEn = V.filter(r => r.lang !== 'en').reduce((a, r) => a + r.n, 0);
  const phone = V.filter(r => r.device === 'phone').reduce((a, r) => a + r.n, 0);
  const tile = (l, v, s) => `<div class='us-tile'><div class='l'>${esc(l)}</div><div class='v'>${esc(v)}</div><div class='s'>${esc(s)}</div></div>`;
  // the map's frameworks: panels opened on the map, and pages opened at one by a shared link
  const fw = new Map();
  ev('panel').forEach(r => { const x = fw.get(r.detail) || {open: 0, link: 0}; x.open += r.n; fw.set(r.detail, x); });
  V.filter(r => r.detail).forEach(r => { const x = fw.get(r.detail) || {open: 0, link: 0}; x.link += r.n; fw.set(r.detail, x); });
  const fwAll = [...fw.entries()].map(([d, x]) => ({d, label: place(d), open: x.open, link: x.link, n: x.open + x.link}))
    .sort((a, b) => b.n - a.n || a.label.localeCompare(b.label));
  const fwTop = fwAll.slice(0, 12);
  const perDay = sum(V, r => r.day);
  const byPage = top(sum(V, r => r.page), 50);
  const byRef = top(sum(V, r => r.ref || '(none: typed, bookmarked or not given)'), 20);
  const byLang = ['en', 'fr', 'es'].map(l => [LANGS[l], V.filter(r => r.lang === l).reduce((a, r) => a + r.n, 0),
                                              ev('lang').filter(r => r.detail === l).reduce((a, r) => a + r.n, 0)]);
  const byDev = ['desktop', 'phone'].map(k => [DEV[k], V.filter(r => r.device === k).reduce((a, r) => a + r.n, 0)]);
  const byDl = top(sum(ev('download'), r => r.detail), 20);
  const byOut = top(sum(ev('out'), r => r.detail), 20);
  document.getElementById('us-body').innerHTML = `
<div class='us-tiles'>
 ${tile('Page views', fmt(views), 'on the open site')}
 ${tile('Map panels opened', fmt(tot('panel')), 'a country or framework')}
 ${tile('Downloads', fmt(tot('download')), 'CSV, llms.txt and other files')}
 ${tile('Links followed out', fmt(tot('out')), 'framework documents and other sites')}
 ${tile('Read in French or Spanish', pct(notEn, views), 'of page views')}
 ${tile('On phones', pct(phone, views), 'of page views')}
</div>
<div class='card us-card'><h2>Page views per day</h2><p class='sub'>Every page of the open site, UTC days.</p>
 <div class='us-chart'><canvas id='us-c1' role='img' aria-label='Page views per day; the same figures are in the table below'></canvas></div>
 <details id='us-d1'><summary>As a table</summary>${table([{t: 'Day'}, {t: 'Page views', num: true}], span.slice().reverse().map(d => [dayLabel(d), fmt(perDay.get(d) || 0)]))}</details>
</div>
<div class='card us-card'><h2>Frameworks viewed on the map</h2><p class='sub'>Panels opened on the map, and the map opened at a framework by a shared link; the ${fwTop.length < fwAll.length ? fwTop.length + ' most viewed of ' + fwAll.length : fwAll.length || 'none'}.</p>
 ${fwAll.length ? `<div class='us-chart tall'><canvas id='us-c2' role='img' aria-label='Frameworks viewed on the map; the same figures are in the table below'></canvas></div>` : `<div class='us-empty'>No panel opened in this period.</div>`}
 <details id='us-d2'><summary>As a table</summary>${table([{t: 'Framework or country'}, {t: 'Opened on the map', num: true}, {t: 'From a shared link', num: true}, {t: 'Total', num: true}],
   fwAll.map(x => [x.label, fmt(x.open), fmt(x.link), fmt(x.n)]))}</details>
</div>
<div class='us-grid'>
 <div class='card us-card'><h2>Pages</h2><p class='sub'>Page views by page (a "Coming soon" page counts under its own name).</p>
  ${table([{t: 'Page'}, {t: 'Views', num: true}, {t: 'Share', num: true}], byPage.map(([p, n]) => [p, fmt(n), pct(n, views)]))}</div>
 <div class='card us-card'><h2>Where readers came from</h2><p class='sub'>The referring site of each page view (the site only, never the page).</p>
  ${table([{t: 'Site'}, {t: 'Views', num: true}], byRef.map(([s, n]) => [s, fmt(n)]))}</div>
 <div class='card us-card'><h2>Languages</h2><p class='sub'>The language each page was read in, and how often readers switched to it.</p>
  ${views ? table([{t: 'Language'}, {t: 'Views', num: true}, {t: 'Share', num: true}, {t: 'Switched to', num: true}], byLang.map(([l, n, s]) => [l, fmt(n), pct(n, views), fmt(s)])) : table([], [])}</div>
 <div class='card us-card'><h2>Devices</h2><p class='sub'>Phone: the site's narrow layout (under 760 px wide).</p>
  ${views ? table([{t: 'Screen'}, {t: 'Views', num: true}, {t: 'Share', num: true}], byDev.map(([l, n]) => [l, fmt(n), pct(n, views)])) : table([], [])}</div>
 <div class='card us-card'><h2>Downloads</h2><p class='sub'>Files of the site readers clicked to download.</p>
  ${table([{t: 'File'}, {t: 'Downloads', num: true}], byDl.map(([f, n]) => [f, fmt(n)]))}</div>
 <div class='card us-card'><h2>Links followed out</h2><p class='sub'>Links to other sites readers clicked, the 20 most used.</p>
  ${table([{t: 'Link (site and path)', wrap: true}, {t: 'Clicks', num: true}], byOut.map(([u, n]) => [dec(u), fmt(n)]))}</div>
</div>`;
  document.querySelectorAll('#us-body details').forEach((d, i) => { if(opened[i]) d.open = true; });
  if(typeof Chart === 'undefined') return;
  Chart.defaults.font.family = "-apple-system,'Segoe UI',Roboto,sans-serif";
  Chart.defaults.color = INK;
  Chart.defaults.animation = RM || quiet ? false : {};
  const tip = {backgroundColor: '#1f2a44', padding: 8, displayColors: false, titleFont: {weight: '600'}};
  charts.push(new Chart(document.getElementById('us-c1'), {type: 'bar',
    data: {labels: span, datasets: [{data: span.map(d => perDay.get(d) || 0), backgroundColor: ACCENT,
      borderRadius: 4, maxBarThickness: 24, categoryPercentage: 0.9, barPercentage: 0.9}]},
    options: {maintainAspectRatio: false, plugins: {legend: {display: false},
      tooltip: {...tip, callbacks: {title: it => dayLabel(it[0].label), label: it => `${fmt(it.raw)} page view${it.raw === 1 ? '' : 's'}`}}},
      scales: {x: {grid: {display: false}, ticks: {autoSkip: true, maxRotation: 0, callback(v){ return tick(this.getLabelForValue(v)); }}},
               y: {beginAtZero: true, grid: {color: GRID}, border: {display: false}, ticks: {precision: 0}}}}}));
  if(fwTop.length){
    const box = document.getElementById('us-c2').parentNode; box.style.height = (fwTop.length * 30 + 40) + 'px';
    // the value at each bar's tip, in ink, never in the bar's colour
    const tipValues = {id: 'tipValues', afterDatasetsDraw(c){ const {ctx} = c, m = c.getDatasetMeta(0);
      ctx.save(); ctx.font = '12px ' + Chart.defaults.font.family; ctx.fillStyle = INK; ctx.textBaseline = 'middle';
      m.data.forEach((b, i) => ctx.fillText(fmt(fwTop[i].n), b.x + 6, b.y)); ctx.restore(); }};
    charts.push(new Chart(document.getElementById('us-c2'), {type: 'bar', plugins: [tipValues],
      data: {labels: fwTop.map(x => x.label), datasets: [{data: fwTop.map(x => x.n), backgroundColor: ACCENT,
        borderRadius: 4, maxBarThickness: 18, categoryPercentage: 0.9, barPercentage: 0.9}]},
      options: {indexAxis: 'y', maintainAspectRatio: false, layout: {padding: {right: 40}},
        plugins: {legend: {display: false}, tooltip: {...tip, callbacks: {label: it => {
          const x = fwTop[it.dataIndex]; return [`${fmt(x.n)} in all`, `${fmt(x.open)} opened on the map`, `${fmt(x.link)} from a shared link`]; }}}},
        scales: {x: {beginAtZero: true, grid: {color: GRID}, border: {display: false}, ticks: {precision: 0}},
                 y: {grid: {display: false}, border: {display: false}}}}}));
  }
}
// ---------- live: GET /usage on the proxy, the last 90 days (every period but All) or everything
const liveEl = document.getElementById('us-live');
function say(text, cls){ liveEl.textContent = text; liveEl.className = 'us-live ' + (cls || ''); }
const hhmm = s => new Date(s).toISOString().slice(11, 16);
async function live(){
  const since = liveSpan === 'all' ? '' : iso(new Date(Date.now() - (liveSpan - 1) * 864e5));
  try {
    const r = await fetch(PROXY + '/usage' + (since ? '?since=' + since : ''), {headers: {'x-site-token': SITE_TOKEN}, cache: 'no-store'});
    const j = await r.json().catch(() => ({}));
    if(!r.ok || !j.ok) throw new Error(j.error || 'HTTP ' + r.status);
    const s = liveSpan + '|' + j.rows.length + '|' + j.rows.reduce((a, x) => a + x[7], 0) + '|' + j.at.slice(0, 10);
    Object.assign(NAMES, j.names); TODAY = j.at.slice(0, 10); isLive = true;
    say(`Live: the counts as of ${hhmm(j.at)} UTC, refreshed every minute while this page is in view.`, 'on');
    if(s !== sig){ sig = s; R = toRows(j.rows); draw(period, true); }
  } catch(e){
    say(isLive ? `The last refresh failed (${e.message}); showing the counts loaded before.`
               : `Showing the ${USAGE.stamp}: the live counts could not be loaded (${e.message}).`, 'off');
  }
}
const seg = document.querySelectorAll('.us-seg button');
seg.forEach(b => b.addEventListener('click', () => {
  seg.forEach(x => x.setAttribute('aria-pressed', x === b ? 'true' : 'false'));
  period = b.dataset.d === 'all' ? 'all' : +b.dataset.d;
  draw(period);
  if(period === 'all' && liveSpan !== 'all'){ liveSpan = 'all'; live(); } }));
say(`Loading the live counts… (showing the ${USAGE.stamp} meanwhile)`);
draw(30);
live();
setInterval(() => { if(document.visibilityState === 'visible') live(); }, 60000);
document.addEventListener('visibilitychange', () => { if(document.visibilityState === 'visible') live(); });
})();
"""
