"""The Media page (media.html): the shared folder "AA Visuals", shown as it was gathered.

Two things, both read from site_src/media.json (written by scripts/sync_media.py, by hand,
never during the build): the photos, folder by folder under their country, and the social
posts of the catalogue kept with the folder.

Nothing is stored on the site. A photo is Drive's own rendition of the file, asked for by
the file's id (a small one in the grid, a large one in the viewer); the original is one
link away, in Drive. So the page weighs what its list weighs, and it shows a photo only as
long as the folder stays shared by link: a file that goes from the folder leaves a grey
tile until the next sync drops it.

The collection is not curated yet: no selection, no captions, no credits. A photo carries
its file name and its folder, which is all the folder says about it.

The viewer opens INSIDE the page, under the row of the photo it shows: nothing is fixed to
the window, because the page is meant to be embedded in a larger one (as on the Learning
page)."""

import html
import json
from datetime import date
from pathlib import Path

from dashboards import DASH_CSS

MANIFEST = Path(__file__).parents[1] / "site_src" / "media.json"
PREVIEW = 12        # photos of a folder, and posts, shown before "show all"
RENDITION = "https://lh3.googleusercontent.com/d/{id}=w{w}"     # Drive's rendition of a shared file
THUMB_W = 400       # the viewer's width (1600) is in MEDIA_JS
FILE_URL = "https://drive.google.com/file/d/{id}/view"
FOLDER_URL = "https://drive.google.com/drive/folders/{id}"

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
.mh a { margin-left:auto; font-size:12.5px; white-space:nowrap; }
.mgrid { display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:8px; }
.mgrid.clip > .mt:nth-of-type(n+13) { display:none; }
.mt { position:relative; display:block; padding:0; border:0; border-radius:5px; overflow:hidden; background:#e6eaf0;
  aspect-ratio:4/3; cursor:zoom-in; font:inherit; color:#556; }
.mt img { display:block; width:100%; height:100%; object-fit:cover; }
.mt:hover img { filter:brightness(1.07); }
.mt:focus-visible, .mt.on { outline:3px solid var(--accent); outline-offset:1px; }
.mt.video::after { content:'▶'; position:absolute; inset:0; display:grid; place-items:center; color:#fff;
  font-size:26px; text-shadow:0 1px 6px rgba(0,0,0,.6); pointer-events:none; }
/* a file Drive no longer serves: the name, on grey */
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
.mvbar a { color:#9ec5f0; white-space:nowrap; }
.mvbar button { background:#24324d; color:#fff; border:1px solid #3a4b6b; border-radius:4px; cursor:pointer;
  font-size:15px; line-height:1; padding:5px 10px; }
.mvbar button:hover:not(:disabled) { background:#31436a; }
.mvbar button:disabled { opacity:.35; cursor:default; }
.mvbar .pos { font-variant-numeric:tabular-nums; color:#a9b6c9; margin:0 6px; }
.mvstage img { display:block; max-width:100%; max-height:640px; margin:0 auto; border-radius:3px; }
.mvstage iframe { display:block; width:100%; height:520px; border:0; border-radius:3px; background:#000; }
.mpbar { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:10px 0 12px; }
.mpbar button { background:#fff; border:1px solid #cbd5e1; border-radius:14px; padding:4px 12px; font-size:13px;
  cursor:pointer; }
.mpbar button.on { border-color:var(--accent); background:#eaf4ff; color:#0b4f8a; font-weight:600; }
.mpbar button .n { color:var(--muted); margin-left:5px; font-weight:400; }
.mpbar input { padding:5px 10px; border:1px solid #bbb; border-radius:4px; font-size:13px; width:240px; max-width:100%; }
.mpbar .cnt { color:var(--muted); font-size:12.5px; }
.mposts { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:12px; align-items:start; }
.mposts.clip > .mpost:nth-of-type(n+13) { display:none; }
.mpost { background:#fff; border:1px solid #e0e0e0; border-radius:6px; overflow:hidden; display:flex; flex-direction:column; }
.mpost[hidden] { display:none; }
/* a post's picture whole, never cropped: most are cards with the message written on them */
.mpost .pimg { display:block; background:#e6eaf0; min-height:60px; }
.mpost .pimg img { display:block; width:100%; height:auto; max-height:300px; object-fit:contain; }
.mpost .pb { padding:10px 14px 12px; }
.mpost .ph { display:flex; flex-wrap:wrap; gap:4px 8px; align-items:baseline; font-size:12.5px; }
.mpost .plat { background:#1f2a44; color:#fff; border-radius:3px; padding:1px 6px; font-size:11px; font-weight:600; }
.mpost .d { color:var(--muted); margin-left:auto; white-space:nowrap; }
.mpost .pc { color:var(--muted); font-size:12px; margin-top:4px; }
.mpost .pt { font-size:13px; line-height:1.45; margin:8px 0 8px; white-space:pre-line; overflow-wrap:anywhere; }
.mpost .pl { font-size:12.5px; }
"""

MEDIA_JS = """
(function () {
  const big = id => 'https://lh3.googleusercontent.com/d/' + id + '=w1600';
  const view = document.getElementById('mview');               // absent when there is no photo
  const img = view && view.querySelector('img'), frame = view && view.querySelector('iframe');
  let cur = null;

  // tiles past the preview carry their address in data-src: nothing is asked of Drive for
  // a photo that is not shown
  function hydrate(box) {
    box.querySelectorAll('img[data-src]').forEach(i => { i.src = i.dataset.src; i.removeAttribute('data-src'); });
  }
  function expand(box, on) {
    box.classList.toggle('clip', !on);
    if (on) hydrate(box);
    const b = box.parentNode.querySelector('.mmore');
    if (b) b.textContent = on ? 'Show fewer' : b.dataset.all;
  }
  function close() {
    if (cur) cur.classList.remove('on');
    cur = null;
    view.hidden = true;
    img.removeAttribute('src'); frame.removeAttribute('src');
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
    const id = t.dataset.id, video = t.classList.contains('video');
    view.querySelector('.nm').textContent = t.dataset.n;
    view.querySelector('.wh').textContent = [grid.parentNode.dataset.g, t.dataset.s].filter(Boolean).join(' · ');
    view.querySelector('.pos').textContent = (i + 1) + ' / ' + list.length;
    view.querySelector('.pv').disabled = i === 0;
    view.querySelector('.nx').disabled = i === list.length - 1;
    view.querySelector('.og').href = 'https://drive.google.com/file/d/' + id + '/view';
    img.hidden = video; frame.hidden = !video;
    if (video) {
      img.removeAttribute('src');
      frame.src = 'https://drive.google.com/file/d/' + id + '/preview';
    } else {
      frame.removeAttribute('src');
      const small = t.querySelector('img');
      img.alt = t.dataset.n;
      img.src = small.currentSrc || small.src || big(id);   // at once, then the large one
      const large = new Image();
      large.referrerPolicy = 'no-referrer';
      large.onload = () => { if (cur === t) img.src = large.src; };
      large.src = big(id);
    }
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
    if (more) { more.hidden = sifted; more.textContent = pbox.dataset.open === '1' ? 'Show fewer' : more.dataset.all; }
    document.getElementById('mpcnt').textContent = sifted ? n + ' of ' + posts.length + ' posts' : '';
  }

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
})();
"""


def _e(s):
    return html.escape(str(s), quote=True)


def _size(n):
    if not n:
        return ""
    return f"{n / 1e9:.1f} GB" if n >= 1e9 else f"{n / 1e6:.0f} MB" if n >= 1e6 else f"{max(n / 1e3, 1):.0f} KB"


def _n(n, one, many=None):
    return f"{n:,} {one if n == 1 else many or one + 's'}"


def _day(iso):
    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    return f"{d.day} {d:%b %Y}"


def _tile(item, k):
    """One photo (or video) of a folder's grid. Past the preview its picture waits in
    data-src until the folder is opened."""
    src = RENDITION.format(id=item["id"], w=THUMB_W)
    attr = "src" if k < PREVIEW else "data-src"
    cls = "mt video" if item["kind"] == "video" else "mt"
    return (f'<button type="button" class="{cls}" data-id="{_e(item["id"])}" data-n="{_e(item["name"])}" '
            f'data-s="{_e(_size(item.get("bytes")))}" title="{_e(item["name"])}">'
            f'<img loading="lazy" referrerpolicy="no-referrer" {attr}="{_e(src)}" alt="{_e(item["name"])}"></button>')


def _group(g):
    """One folder: its photos as a grid, its documents as links."""
    shown = [i for i in g["items"] if i["kind"] in ("image", "video")]
    docs = [i for i in g["items"] if i["kind"] == "document"]
    label = " › ".join(g["path"][1:])
    weight = _size(sum(i.get("bytes", 0) for i in shown))
    counts = " · ".join(x for x in (
        _n(len(shown), "photo") if shown else "",
        f"{weight} of originals" if weight else "",
        _n(len(docs), "document") if docs and not shown else "") if x)
    out = [f'<section class="mgroup" data-g="{_e(" › ".join(g["path"]))}"><div class="mh">'
           + (f"<b>{_e(label)}</b>" if label else "")
           + f'<span class="n">{counts}</span>'
           f'<a href="{_e(FOLDER_URL.format(id=g["id"]))}" target="_blank" rel="noopener">Open the folder in Drive ↗</a></div>']
    if shown:
        clip = " clip" if len(shown) > PREVIEW else ""
        out.append(f'<div class="mgrid{clip}">' + "".join(_tile(i, k) for k, i in enumerate(shown)) + "</div>")
        if clip:
            all_ = f"Show all {_n(len(shown), 'photo')}"
            out.append(f'<button type="button" class="mmore" data-all="{_e(all_)}">{_e(all_)}</button>')
    if docs:
        out.append('<div class="mdocs">Documents in this folder: ' + " · ".join(
            f'<a href="{_e(FILE_URL.format(id=i["id"]))}" target="_blank" rel="noopener">{_e(i["name"])}</a>'
            + (f' ({_size(i["bytes"])})' if i.get("bytes", 0) >= 5e6 else "") for i in docs) + "</div>")
    return "".join(out) + "</section>"


def _post(p, k):
    attr = "src" if k < PREVIEW else "data-src"
    where = " · ".join(x for x in (p.get("country"), p.get("theme"), p.get("asset")) if x)
    words = " ".join(p.get(f, "") for f in ("platform", "account", "country", "theme", "asset", "text")).lower()
    pic = (f'<a class="pimg" href="{_e(p["url"])}" target="_blank" rel="noopener" tabindex="-1" aria-hidden="true">'
           f'<img loading="lazy" referrerpolicy="no-referrer" {attr}="{_e(p["image"])}" alt=""></a>') if p.get("image") else ""
    return (f'<article class="mpost" data-p="{_e(p["platform"])}" data-q="{_e(words)}">{pic}<div class="pb">'
            f'<div class="ph"><span class="plat">{_e(p["platform"])}</span><b>{_e(p.get("account", ""))}</b>'
            f'<span class="d">{_day(p.get("date"))}</span></div>'
            + (f'<div class="pc">{_e(where)}</div>' if where else "")
            + (f'<p class="pt">{_e(p["text"])}</p>' if p.get("text") else "")
            + f'<a class="pl" href="{_e(p["url"])}" target="_blank" rel="noopener">Open the post on {_e(p["platform"])} ↗</a>'
            "</div></article>")


def _empty():
    return """
<div class='card' style='text-align:center;padding:40px 20px'>
<div style='font-size:34px;line-height:1'>▶</div>
<div class='empty' style='margin-top:10px'>No media collected yet.</div>
<p class='meta' style='margin:8px 0 0'>Meanwhile: <a href='pillar-learning.html'>Learning</a> lists the evaluations,
after-action reviews and stories on record.</p>
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
        return sum(1 for g in gs for i in g["items"] if i["kind"] in ("image", "video"))

    n_photos, n_docs = photos(groups), sum(1 for g in groups for i in g["items"] if i["kind"] == "document")
    listed = _day(m.get("synced"))
    tiles = "".join(f"<div class='tile'><div class='v'>{v:,}</div><div class='l'>{label}</div></div>"
                    for v, label in ((n_photos, "photos"), (len(countries), "countries"),
                                     (len(posts), "social posts"), (n_docs, "captions and documents")) if v)
    jump = "".join(f'<a href="#m-{k}">{_e(c)}<span class="n">{photos(gs):,}</span></a>'
                   for k, (c, gs) in enumerate(countries.items()))
    if posts:
        jump += f'<a href="#posts">Social posts<span class="n">{len(posts):,}</span></a>'

    body = [f"""
<div class='card'><b>A first collection, shown as it was gathered.</b> Photos of anticipatory action
shared by agencies and OCHA teams, and posts about it on social media, from the shared folder
<i>{_e(m["folder"]["title"])}</i>. Nothing has been selected, captioned or credited yet: a photo carries
its file name and the folder it came in, and the full-size original opens in Drive.
{f"Listed on {listed}." if listed else ""}
<div class='tiles'>{tiles}</div>
<div class='mjump'>{jump}</div></div>"""]

    if groups:
        body.append("<h2 id='photos'>Photos, by country</h2>")
        for k, (c, gs) in enumerate(countries.items()):
            body.append(f'<h3 class="mcountry" id="m-{k}">{_e(c)}<span class="n">{_n(photos(gs), "photo")}</span></h3>')
            body += [_group(g) for g in gs]
        body.append("""
<div id="mview" class="mview" hidden>
 <div class="mvbar"><span class="mvcap"><b class="nm"></b><span class="wh"></span></span>
  <span><button type="button" class="pv" aria-label="Previous photo">‹</button><span class="pos"></span><button type="button" class="nx" aria-label="Next photo">›</button></span>
  <a class="og" target="_blank" rel="noopener">Open the original in Drive ↗</a>
  <button type="button" class="cl" aria-label="Close">✕</button></div>
 <div class="mvstage"><img alt="" referrerpolicy="no-referrer"><iframe hidden title="Video" allow="autoplay; fullscreen" allowfullscreen></iframe></div>
</div>""")

    if posts:
        by = {}
        for p in posts:
            by[p["platform"]] = by.get(p["platform"], 0) + 1
        chips = (f'<button type="button" class="on" data-p="">All<span class="n">{len(posts):,}</span></button>'
                 + "".join(f'<button type="button" data-p="{_e(k)}">{_e(k)}<span class="n">{v:,}</span></button>'
                           for k, v in sorted(by.items(), key=lambda kv: -kv[1])))
        years = sorted(p["date"][:4] for p in posts if p.get("date"))
        span = f", from {years[0]} to {years[-1]}" if years else ""
        clip = " clip" if len(posts) > PREVIEW else ""
        all_ = f"Show all {_n(len(posts), 'post')}"
        body.append(f"""
<h2 id='posts'>Social posts</h2>
<p class='meta'>{_n(len(posts), "post")} about anticipatory action by OCHA, CERF and partner accounts{span},
newest first. They come from the catalogue kept with the folder ({_e(m.get("catalogue", ""))}), which is
partial: it is not a record of everything posted. Each post opens on its platform.</p>
<div class='mpbar'>{chips}<input id='mpq' type='search' placeholder='search the posts…' aria-label='Search the posts'>
<span class='cnt' id='mpcnt'></span></div>
<div class='mposts{clip}' id='mposts'>{"".join(_post(p, k) for k, p in enumerate(posts))}</div>
{f'<button type="button" class="mmore" id="mpmore" data-all="{_e(all_)}">{_e(all_)}</button>' if clip else ""}""")

    body.append(f"<style>{DASH_CSS}{MEDIA_CSS}</style><script>{MEDIA_JS}</script>")
    page("media.html", "Media & visuals", "".join(body))
