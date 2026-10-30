"""The Media page (media.html): the shared folder "AA Visuals", shown as it was gathered.

Two things, both read from site_src/media.json (written by scripts/sync_media.py, by hand,
never during the build): the photos, folder by folder under their country, and the social
posts of the catalogue kept with the folder.

A photo is shown from two renditions published with the site under media/ (a small one in
the grid, a large one in the viewer), named by the photo's content; scripts/publish.sh
fetches them from the dev blob, where sync_media.py keeps them with the originals. The
page does not link to the folder or to an original (the folder is in a private SharePoint
group). A rendition that does not come leaves a grey tile with the file's name.

The collection is not curated yet: no selection, no captions, no credits. A photo carries
its file name and its folder, which is all the folder says about it.

The viewer opens INSIDE the page, under the row of the photo it shows: nothing is fixed to
the window, because the page is meant to be embedded in a larger one (as on the Learning
page)."""

import html
import json
import re
from datetime import date
from pathlib import Path

from dashboards import DASH_CSS
from site_i18n import ATTR, TB, TBC, TBF, TC, TD, TF, T

MANIFEST = Path(__file__).parents[1] / "site_src" / "media.json"
PREVIEW = 12        # photos of a folder, and posts, shown before "show all"
RENDITION = "media/{key}-w{w}.jpg"      # sync_media.WIDTHS, published by scripts/publish.sh
THUMB_W = 400       # the viewer's width (1600) is in MEDIA_JS

MEDIA_CSS = """
.mjump { display:flex; flex-wrap:wrap; gap:8px; margin:6px 0 4px; }
.mjump a { background:#fff; border:1px solid #cbd5e1; border-radius:14px; padding:4px 12px; font-size:13px;
  color:#1a1a1a; text-decoration:none; }
.mjump a:hover { border-color:var(--accent); color:#0b4f8a; }
.mjump a .n { color:var(--muted); margin-left:5px; font-variant-numeric:tabular-nums; }
h3.mcountry { font-size:16px; margin:26px 0 4px; }
h3.mcountry .n { color:var(--muted); font-weight:400; font-size:13px; margin-left:6px; }
.mgroup { background:#fff; border:1px solid #e0e0e0; border-radius:6px; padding:12px 16px 14px; margin:10px 0; }
.mh { display:flex; flex-wrap:wrap; gap:4px 12px; align-items:baseline; margin-bottom:10px; font-size:14px; }
.mh .n { color:var(--muted); font-size:12.5px; }
.mgrid { display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:8px; }
.mgrid.clip > .mt:nth-of-type(n+13) { display:none; }
.mt { position:relative; display:block; padding:0; border:0; border-radius:5px; overflow:hidden; background:#e6eaf0;
  aspect-ratio:4/3; cursor:zoom-in; font:inherit; color:#556; }
.mt img { display:block; width:100%; height:100%; object-fit:cover; }
.mt:hover img { filter:brightness(1.07); }
.mt:focus-visible, .mt.on { outline:3px solid var(--accent); outline-offset:1px; }
/* a photo whose rendition does not come: the name, on grey */
.mt.gone img { display:none; }
.mt.gone::before { content:attr(data-n); position:absolute; inset:0; display:grid; place-items:center;
  padding:8px; font-size:11px; line-height:1.3; text-align:center; overflow-wrap:anywhere; }
button.mmore { margin-top:10px; padding:5px 12px; border:1px solid #bbb; border-radius:4px; background:#f7f8fa;
  font-size:12.5px; cursor:pointer; }
button.mmore:hover { border-color:var(--accent); background:#eef4fc; }
.mdocs { margin-top:10px; font-size:12.5px; color:var(--muted); }
.mgrid + .mdocs, .mmore + .mdocs { border-top:1px solid #eef0f3; padding-top:9px; }
.mview { grid-column:1 / -1; background:#111a2b; color:#e8edf5; border-radius:6px; padding:10px 12px 12px; }
.mview[hidden], .mview [hidden] { display:none; }
.mvbar { display:flex; flex-wrap:wrap; gap:6px 14px; align-items:center; font-size:12.5px; margin-bottom:8px; }
.mvcap { flex:1; min-width:180px; overflow-wrap:anywhere; }
.mvcap b { color:#fff; margin-right:8px; }
.mvcap .wh { color:#a9b6c9; }
.mvbar button { background:#24324d; color:#fff; border:1px solid #3a4b6b; border-radius:4px; cursor:pointer;
  font-size:15px; line-height:1; padding:5px 10px; }
.mvbar button:hover:not(:disabled) { background:#31436a; }
.mvbar button:disabled { opacity:.35; cursor:default; }
.mvbar .pos { font-variant-numeric:tabular-nums; color:#a9b6c9; margin:0 6px; }
.mvstage img { display:block; max-width:100%; max-height:640px; margin:0 auto; border-radius:3px; }
.mpbar { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:10px 0 12px; }
.mpbar button { background:#fff; border:1px solid #cbd5e1; border-radius:14px; padding:4px 12px; font-size:13px;
  cursor:pointer; }
.mpbar button.on { border-color:var(--accent); background:#eaf4ff; color:#0b4f8a; font-weight:600; }
.mpbar button .n { color:var(--muted); margin-left:5px; font-weight:400; }
.mpbar input { padding:5px 10px; border:1px solid #bbb; border-radius:4px; font-size:13px; width:240px; max-width:100%; }
.mpbar .cnt { color:var(--muted); font-size:12.5px; }
.mposts { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:12px; align-items:start; }
.mposts.clip > .mpost:nth-of-type(n+13) { display:none; }
/* the preview: the newest posts in one row that scrolls sideways, with arrows (owner, 2026-10-28:
   social first, as a carousel); "show all", a platform or a search opens the grid */
.mpwrap { position:relative; }
.mposts.clip { grid-template-columns:none; grid-auto-flow:column; grid-auto-columns:minmax(250px, 290px);
  overflow-x:auto; scroll-snap-type:x mandatory; overscroll-behavior-x:contain; padding:2px 2px 8px; }
.mposts.clip > .mpost { scroll-snap-align:start; }
.mposts.clip .pimg img { max-height:170px; }
.mposts.clip .pt { display:-webkit-box; -webkit-line-clamp:6; -webkit-box-orient:vertical; overflow:hidden; }
.mpnav { position:absolute; top:42%; width:34px; height:34px; border-radius:50%; border:1px solid #cbd5e1;
  background:#fff; box-shadow:0 2px 8px rgba(15,37,64,.18); font-size:18px; line-height:1; cursor:pointer; color:#0f2540; z-index:1; }
.mpnav.l { left:-12px; } .mpnav.r { right:-12px; }
.mpnav:hover:not(:disabled) { border-color:var(--accent); color:#0b4f8a; }
.mpnav:disabled { opacity:0; pointer-events:none; }
.mpnav[hidden] { display:none; }
@media (max-width:759px) { .mpnav { display:none; } }
.mpost { background:#fff; border:1px solid #e0e0e0; border-radius:6px; overflow:hidden; display:flex; flex-direction:column; }
.mpost[hidden] { display:none; }
/* a post's picture whole, never cropped: most are cards with the message written on them */
.mpost .pimg { display:block; background:#e6eaf0; min-height:60px; }
.mpost .pimg img { display:block; width:100%; height:auto; max-height:300px; object-fit:contain; }
.mpost .pb { padding:10px 14px 12px; }
.mpost .ph { display:flex; flex-wrap:wrap; gap:4px 8px; align-items:baseline; font-size:12.5px; }
.mpost .plat { background:#1f2a44; color:#fff; border-radius:3px; padding:1px 6px; font-size:11px; font-weight:600; }
/* the head like a post's: the round badge, the account beside it, platform and date under it */
.mpost .ph { display:grid; grid-template-columns:30px 1fr auto; column-gap:8px; row-gap:2px; align-items:center; }
.mpost .av { grid-row:span 2; width:30px; height:30px; border-radius:50%; background:#1f69b3; color:#fff;
  display:grid; place-items:center; font-size:13px; font-weight:700; }
.mpost .ph b { grid-column:2 / 4; overflow-wrap:anywhere; line-height:1.25; }
.mpost .ph .plat { justify-self:start; }
.mpost .ph .d { margin-left:0; }
.mpost .d { color:var(--muted); margin-left:auto; white-space:nowrap; }
.mpost .pc { color:var(--muted); font-size:12px; margin-top:4px; }
.mpost .pt { font-size:13px; line-height:1.45; margin:8px 0 8px; white-space:pre-line; overflow-wrap:anywhere; }
.mpost .pl { font-size:12.5px; }
/* X's own embed, once it has come (MEDIA_JS): the card it replaces is hidden */
.mpost .xemb:empty { display:none; }
.mpost.embedded { border:0; background:none; overflow:visible; }
.mpost.embedded > .pimg, .mpost.embedded > .pb { display:none; }
.mpost .xemb .twitter-tweet { margin:0 !important; }
"""

MEDIA_JS = """
(function () {
  const big = key => 'media/' + key + '-w1600.jpg';
  const view = document.getElementById('mview');               // absent when there is no photo
  const img = view && view.querySelector('img');
  let cur = null;

  // tiles past the preview carry their address in data-src: nothing is fetched for a photo
  // that is not shown
  function hydrate(box) {
    box.querySelectorAll('img[data-src]').forEach(i => { i.src = i.dataset.src; i.removeAttribute('data-src'); });
  }
  // a "show all" button's words, in the page's language: data-k (photo / post) and data-c (count)
  const allOf = b => tr8(b.dataset.k === 'post' ? 'Show all {0} posts' : b.dataset.c === '1' ? 'Show all {0} photo' : 'Show all {0} photos',
                         Number(b.dataset.c).toLocaleString('en-US'));
  function expand(box, on) {
    box.classList.toggle('clip', !on);
    if (on) hydrate(box);
    const b = box.parentNode.querySelector('.mmore');
    if (b) b.textContent = on ? tr8('Show fewer') : allOf(b);
  }
  function close() {
    if (cur) cur.classList.remove('on');
    cur = null;
    view.hidden = true;
    img.removeAttribute('src');
  }
  function open(t) {
    const grid = t.parentNode, list = [...grid.querySelectorAll('.mt')], i = list.indexOf(t);
    view.hidden = true;                              // out of the grid while its rows are read
    if (t.offsetParent === null) expand(grid, true); // a photo past the preview: open the folder
    if (cur) cur.classList.remove('on');
    cur = t; t.classList.add('on');
    let end = t;                                     // the viewer goes under the photo's row
    for (let n = t.nextElementSibling; n && n.classList.contains('mt') && n.offsetParent !== null
         && n.offsetTop === t.offsetTop; n = n.nextElementSibling) end = n;
    end.after(view);
    const key = t.dataset.key;
    view.querySelector('.nm').textContent = t.dataset.n;
    view.querySelector('.wh').textContent = [grid.parentNode.dataset.g, t.dataset.s].filter(Boolean).join(' · ');
    view.querySelector('.pos').textContent = (i + 1) + ' / ' + list.length;
    view.querySelector('.pv').disabled = i === 0;
    view.querySelector('.nx').disabled = i === list.length - 1;
    const small = t.querySelector('img');
    img.alt = t.dataset.n;
    // at once, then the large one (only the large one when the small one did not come)
    img.src = t.classList.contains('gone') ? big(key) : small.currentSrc || small.src || big(key);
    const large = new Image();
    large.onload = () => { if (cur === t) img.src = large.src; };
    large.src = big(key);
    view.hidden = false;
    const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
    view.scrollIntoView({block: 'nearest', behavior: calm ? 'auto' : 'smooth'});
  }
  function step(d) {
    if (!cur) return;
    const list = [...cur.parentNode.querySelectorAll('.mt')], n = list[list.indexOf(cur) + d];
    if (n) { open(n); n.focus({preventScroll: true}); }
  }

  // ---- the posts: platform and words
  const pbox = document.getElementById('mposts');
  const posts = pbox ? [...pbox.querySelectorAll('.mpost')] : [];
  let plat = '', words = '';
  function sift() {
    let n = 0;
    posts.forEach(p => {
      const ok = (!plat || p.dataset.p === plat) && (!words || p.dataset.q.includes(words));
      p.hidden = !ok; if (ok) n++;
    });
    const sifted = !!(plat || words), more = document.getElementById('mpmore');
    pbox.classList.toggle('clip', !sifted && pbox.dataset.open !== '1');
    if (sifted || pbox.dataset.open === '1') hydrate(pbox);
    if (more) { more.hidden = sifted; more.textContent = pbox.dataset.open === '1' ? tr8('Show fewer') : allOf(more); }
    document.getElementById('mpcnt').textContent = sifted ? tr8('{0} of {1} posts', n, posts.length) : '';
    arrows();
  }
  // the strip's arrows: a step of most of its width; at an end the arrow fades
  const navs = pbox ? [...pbox.parentNode.querySelectorAll('.mpnav')] : [];
  function arrows() {
    const strip = pbox.classList.contains('clip'), end = pbox.scrollWidth - pbox.clientWidth - 2;
    navs.forEach(b => { b.hidden = !strip; b.disabled = b.classList.contains('l') ? pbox.scrollLeft <= 2 : pbox.scrollLeft >= end; });
  }
  if (pbox) {
    pbox.addEventListener('scroll', arrows, {passive: true});
    addEventListener('resize', arrows);
    navs.forEach(b => b.addEventListener('click', () => {
      const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
      pbox.scrollBy({left: (b.classList.contains('l') ? -1 : 1) * pbox.clientWidth * 0.85, behavior: calm ? 'auto' : 'smooth'});
    }));
    arrows();
  }
  // a language switch: the buttons and the count the script wrote
  document.addEventListener('aalang', () => {
    document.querySelectorAll('.mgrid').forEach(g => {
      const b = g.parentNode.querySelector('.mmore');
      if (b) b.textContent = g.classList.contains('clip') ? allOf(b) : tr8('Show fewer');
    });
    if (pbox) sift();
  });

  document.addEventListener('click', e => {
    const t = e.target.closest('.mt');
    if (t) return t === cur ? close() : open(t);
    const m = e.target.closest('.mmore');
    if (m && m.id === 'mpmore') { pbox.dataset.open = pbox.dataset.open === '1' ? '' : '1'; return sift(); }
    if (m) {
      const grid = m.parentNode.querySelector('.mgrid'), on = grid.classList.contains('clip');
      if (!on && cur && cur.parentNode === grid) close();
      return expand(grid, on);
    }
    const f = e.target.closest('.mpbar button');
    if (f) {
      plat = f.dataset.p;
      document.querySelectorAll('.mpbar button').forEach(b => b.classList.toggle('on', b === f));
      return sift();
    }
    if (e.target.closest('.mview .cl')) return close();
    if (e.target.closest('.mview .pv')) return step(-1);
    if (e.target.closest('.mview .nx')) return step(1);
  });
  document.addEventListener('input', e => {
    if (e.target.id === 'mpq') { words = e.target.value.trim().toLowerCase(); sift(); }
  });
  document.addEventListener('keydown', e => {
    if (!cur || e.target.matches('input, textarea, select')) return;
    if (e.key === 'Escape') { const t = cur; close(); t.focus({preventScroll: true}); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); step(1); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1); }
  });
  // a picture that does not come: the photo's name on grey, the post without its picture
  document.addEventListener('error', e => {
    const i = e.target;
    if (!(i instanceof HTMLImageElement)) return;
    const t = i.closest('.mt'), p = i.closest('.pimg');
    if (t) t.classList.add('gone'); else if (p) p.remove();
  }, true);

  // X posts as X shows them (owner, 2026-10-30): a card gives way to X's own embed once it
  // comes into view — X's script loads then, once, with do-not-track on. A post X no longer
  // serves (deleted, protected), or X's script blocked, keeps its card
  const xs = [...document.querySelectorAll('.mpost[data-x]')];
  if (xs.length && 'IntersectionObserver' in window) {
    let lib = null;
    const load = () => lib || (lib = new Promise((ok, no) => {
      const sc = document.createElement('script');
      sc.src = 'https://platform.twitter.com/widgets.js'; sc.async = true; sc.charset = 'utf-8';
      sc.onload = () => (window.twttr && twttr.ready ? twttr.ready(ok) : no());
      sc.onerror = no; document.head.appendChild(sc);
    }));
    const lang = (window.aaLang && aaLang()) || 'en';
    const io = new IntersectionObserver(es => es.forEach(e => {
      if (!e.isIntersecting) return;
      const c = e.target; io.unobserve(c);
      load().then(T => T.widgets.createTweet(c.dataset.x, c.querySelector('.xemb'), {dnt: true, conversation: 'none', lang}))
        .then(el => { if (el) c.classList.add('embedded'); }).catch(() => {});
    }), {rootMargin: '300px'});
    xs.forEach(c => io.observe(c));
  }
})();
"""


def _e(s):
    return html.escape(str(s), quote=True)


def _size(n):
    if not n:
        return ""
    return f"{n / 1e9:.1f} GB" if n >= 1e9 else f"{n / 1e6:.0f} MB" if n >= 1e6 else f"{max(n / 1e3, 1):.0f} KB"


def _day_txt(iso, w=lambda x: x):
    """'5 Oct 2025' (w: one language's month names); '' when there is no date."""
    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    return f"{d.day} {w(f'{d:%b}')} {d.year}"


def _day(iso):
    """_day_txt in every language (a T span); '' when there is no date."""
    return TC(lambda w: _day_txt(iso, w)) if _day_txt(iso) else ""


def _count(n, one, many):
    """'1,234 photos' in every language (one / many: the English templates, '{n} photo')."""
    return TF(one if n == 1 else many, n=f"{n:,}")


def _tile(item, k):
    """One photo of a folder's grid. Past the preview its picture waits in data-src until the
    folder is opened."""
    src = RENDITION.format(key=item["key"], w=THUMB_W)
    attr = "src" if k < PREVIEW else "data-src"
    return (f'<button type="button" class="mt" data-key="{_e(item["key"])}" '
            f'data-n="{_e(item["name"])}" data-s="{_e(_size(item.get("bytes")))}" title="{_e(item["name"])}">'
            f'<img loading="lazy" {attr}="{_e(src)}" alt="{_e(item["name"])}"></button>')


def _group(g):
    """One folder: its photos as a grid, the names of its other files (documents, videos)."""
    shown = [i for i in g["items"] if i["kind"] == "image"]
    docs = [i for i in g["items"] if i["kind"] != "image"]
    label = " › ".join(g["path"][1:])
    weight = _size(sum(i.get("bytes", 0) for i in shown))
    counts = " · ".join(x for x in (
        _count(len(shown), "{n} photo", "{n} photos") if shown else "",
        TF("{w} of originals", w=weight) if weight else "",
        _count(len(docs), "{n} document", "{n} documents") if docs and not shown else "") if x)
    out = [f'<section class="mgroup" data-g="{_e(" › ".join(g["path"]))}"><div class="mh">'
           + (f"<b>{_e(label)}</b>" if label else "")
           + f'<span class="n">{counts}</span></div>']
    if shown:
        clip = " clip" if len(shown) > PREVIEW else ""
        out.append(f'<div class="mgrid{clip}">' + "".join(_tile(i, k) for k, i in enumerate(shown)) + "</div>")
        if clip:
            all_ = _count(len(shown), "Show all {n} photo", "Show all {n} photos")
            out.append(f'<button type="button" class="mmore" data-k="photo" data-c="{len(shown)}">{all_}</button>')
    if docs:
        out.append(f'<div class="mdocs">{T("Documents in this folder:")} ' + " · ".join(
            _e(i["name"]) + (f' ({_size(i["bytes"])})' if i.get("bytes", 0) >= 5e6 else "") for i in docs) + "</div>")
    return "".join(out) + "</section>"


def _post(p, k):
    attr = "src" if k < PREVIEW else "data-src"
    where = " · ".join(x for x in (p.get("country"), p.get("theme"), p.get("asset")) if x)
    words = " ".join(p.get(f, "") for f in ("platform", "account", "country", "theme", "asset", "text")).lower()
    pic = (f'<a class="pimg" href="{_e(p["url"])}" target="_blank" rel="noopener" tabindex="-1" aria-hidden="true">'
           f'<img loading="lazy" referrerpolicy="no-referrer" {attr}="{_e(p["image"])}" alt=""></a>') if p.get("image") else ""
    # an X post: its id, for X's own embed (MEDIA_JS); the card below stays until the embed has come
    xid = re.search(r"/status(?:es)?/(\d+)", p.get("url") or "") if p["platform"] == "X" else None
    xattr, xemb = (f' data-x="{xid.group(1)}"', '<div class="xemb"></div>') if xid else ("", "")
    return (f'<article class="mpost" data-p="{_e(p["platform"])}" data-q="{_e(words)}"{xattr}>{xemb}{pic}<div class="pb">'
            f'<div class="ph"><span class="av" aria-hidden="true">{_e((p.get("account") or p["platform"])[:1].upper())}</span>'
            f'<b>{_e(p.get("account", ""))}</b><span class="plat">{_e(p["platform"])}</span>'
            f'<span class="d">{_day(p.get("date"))}</span></div>'
            + (f'<div class="pc">{_e(where)}</div>' if where else "")
            + (f'<p class="pt">{_e(p["text"])}</p>' if p.get("text") else "")
            + f'<a class="pl" href="{_e(p["url"])}" target="_blank" rel="noopener">{TF("Open the post on {p} ↗", p=p["platform"])}</a>'
            "</div></article>")


def _empty():
    return f"""
<div class='card' style='text-align:center;padding:40px 20px'>
<div style='font-size:34px;line-height:1'>▶</div>
<div class='empty' style='margin-top:10px'>{T("No media collected yet.")}</div>
<p class='meta' style='margin:8px 0 0'>{TB("Meanwhile: <a href='pillar-learning.html'>Learning</a> lists the evaluations, after-action reviews and stories on record.")}</p>
</div>"""


def build_media(page):
    """media.html, from the manifest. Without one (or with an empty one) the page says so."""
    m = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    groups, posts = m.get("groups", []), m.get("posts", [])
    if not groups and not posts:
        page("media.html", "Media & visuals", _empty() + f"<style>{DASH_CSS}</style>")
        return

    countries = {}                                   # country (the folder under the root) -> its folders
    for g in groups:
        countries.setdefault(g["path"][0] if g["path"] else m["folder"]["title"], []).append(g)

    def photos(gs):
        return sum(1 for g in gs for i in g["items"] if i["kind"] == "image")

    n_photos, n_docs = photos(groups), sum(1 for g in groups for i in g["items"] if i["kind"] != "image")
    synced = m.get("synced")
    tiles = "".join(f"<div class='tile'><div class='v'>{v:,}</div><div class='l'>{T(label)}</div></div>"
                    for v, label in ((n_photos, "photos"), (len(countries), "countries"),
                                     (len(posts), "social posts"), (n_docs, "captions and documents")) if v)
    jump = (f'<a href="#posts">{T("Social posts")}<span class="n">{len(posts):,}</span></a>' if posts else "")
    jump += "".join(f'<a href="#m-{k}">{TD(c)}<span class="n">{photos(gs):,}</span></a>'
                    for k, (c, gs) in enumerate(countries.items()))

    body = [f"""
<div class='card'>{TBF("<b>A first collection, shown as it was gathered.</b> Photos of anticipatory action shared by agencies and OCHA teams, and posts about it on social media, from the folder <i>{folder}</i>. Nothing has been selected, captioned or credited yet: a photo carries its file name and the folder it came in.", folder=_e(m["folder"]["title"]))}
{TBC(lambda w: w("Listed on {d}.").format(d=_day_txt(synced, w))) if _day_txt(synced) else ""}
<div class='tiles'>{tiles}</div>
<div class='mjump'>{jump}</div></div>"""]

    if posts:
        by = {}
        for p in posts:
            by[p["platform"]] = by.get(p["platform"], 0) + 1
        chips = (f'<button type="button" class="on" data-p="">{T("All")}<span class="n">{len(posts):,}</span></button>'
                 + "".join(f'<button type="button" data-p="{_e(k)}">{_e(k)}<span class="n">{v:,}</span></button>'
                           for k, v in sorted(by.items(), key=lambda kv: -kv[1])))
        years = sorted(p["date"][:4] for p in posts if p.get("date"))
        clip = " clip" if len(posts) > PREVIEW else ""
        all_ = _count(len(posts), "Show all {n} post", "Show all {n} posts")
        posts_note = TBC(lambda w: w(
            "{n} about anticipatory action by OCHA, CERF and partner accounts{span}, newest first. They come "
            "from the catalogue kept with the folder ({cat}), which is partial: it is not a record of "
            "everything posted. Each post opens on its platform.").format(
                n=w("{n} post" if len(posts) == 1 else "{n} posts").format(n=f"{len(posts):,}"),
                span=w(", from {a} to {b}").format(a=years[0], b=years[-1]) if years else "",
                cat=_e(m.get("catalogue", ""))))
        body.append(f"""
<h2 id='posts'>{T("Social posts")}</h2>
<p class='meta'>{posts_note}</p>
<div class='mpbar'>{chips}<input id='mpq' type='search' {ATTR("placeholder", "search the posts…")} {ATTR("aria-label", "Search the posts")}>
<span class='cnt' id='mpcnt'></span></div>
<div class='mpwrap'><button type="button" class="mpnav l" {ATTR("aria-label", "Earlier in the row")}>‹</button>
<div class='mposts{clip}' id='mposts' tabindex='0' {ATTR("aria-label", "Social posts")}>{"".join(_post(p, k) for k, p in enumerate(posts))}</div>
<button type="button" class="mpnav r" {ATTR("aria-label", "Further along the row")}>›</button></div>
{f'<button type="button" class="mmore" id="mpmore" data-k="post" data-c="{len(posts)}">{all_}</button>' if clip else ""}""")

    if groups:
        body.append(f"<h2 id='photos'>{T('Photos, by country')}</h2>")
        for k, (c, gs) in enumerate(countries.items()):
            body.append(f'<h3 class="mcountry" id="m-{k}">{TD(c)}<span class="n">{_count(photos(gs), "{n} photo", "{n} photos")}</span></h3>')
            body += [_group(g) for g in gs]
        body.append(f"""
<div id="mview" class="mview" hidden>
 <div class="mvbar"><span class="mvcap"><b class="nm"></b><span class="wh"></span></span>
  <span><button type="button" class="pv" {ATTR("aria-label", "Previous photo")}>‹</button><span class="pos"></span><button type="button" class="nx" {ATTR("aria-label", "Next photo")}>›</button></span>
  <button type="button" class="cl" {ATTR("aria-label", "Close")}>✕</button></div>
 <div class="mvstage"><img alt=""></div>
</div>""")

    body.append(f"<style>{DASH_CSS}{MEDIA_CSS}</style><script>{MEDIA_JS}</script>")
    page("media.html", "Media & visuals", "".join(body))
