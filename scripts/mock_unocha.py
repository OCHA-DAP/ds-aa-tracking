"""The mock-up: the public site as it would sit on https://www.unocha.org/anticipatory-action.

    python scripts/mock_unocha.py [SITE_DIR]      (after build_site.py; publish.sh runs it)

The user's brief (2026-10-27): the whole site, every tab, goes right under the big photo of
OCHA's page; it takes the place of their section tabs (the intro text, "What is anticipatory
action?" and the news stay, below it); our tabs are drawn as their tab row; the content runs full
width, like the photo; it lives on our Pages site, unlisted.

Every page a visitor reaches from the map (the tabs and the framework pages the map opens; not
the unlisted pages) gets a twin, index.html -> mock-unocha.html, x.html -> mock-unocha-x.html:
OCHA's page (site_src/unocha-shell.html, scripts/snapshot_unocha.py) with the page's content in
it. The twins link only to each other and nothing on the site links to them. They are written at
the top level of the site, so publish.sh encrypts them with the public pages.

Our CSS is scoped to .aa-embed, so it cannot restyle OCHA's page. OCHA's rules still reach our
content, as they would on the real page; the ones that break it are reset in EMBED_CSS, and that
list is what the real embed would have to deal with too.
"""
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).parents[1]
SHELL = REPO / "site_src" / "unocha-shell.html"
ROOT = ".aa-embed"
TITLE = "Anticipatory action | OCHA"

# a page as build_site._render writes it
DOC = re.compile(r'<!doctype html><html lang="en"><head>(?P<head>.*?)</head><body>\n'
                 r'(?P<top>.*?)<main[^>]*>(?P<main>.*)</main>(?:<footer class=.foot.>.*?</footer>)?</body></html>\s*', re.S)
# <main id=… tabindex=…> since the skip link (PR #56); the foot (the accessibility link) is ours, not
# shown inside OCHA's page, which has its own footer

# our block in their page: full width like the photo, their tab row, their font
EMBED_CSS = """
#aa.aa-embed { margin:0 calc(50% - 50vw + var(--cd-bleed-scrollbar-width) / 2) 1rem;
  background:#fff; font-family:Roboto, "Helvetica Neue", Arial, sans-serif; font-size:16px;
  line-height:normal; }   /* not their article text size: our px sizes were set against 16px */
.aa-embed .aa-wrap { max-width:calc(1400px + 56px); margin:0 auto; padding:0 28px; }   /* edges = the photo's */
.aa-embed .aa-tabrow { display:flex; align-items:flex-end; flex-wrap:wrap; gap:8px 16px; }
.aa-embed .aa-tabrow [role="tablist"] { flex:1 1 auto; margin:0; }
.aa-embed .uno-section-tabs [role="tablist"] li.aa-sub a { font-weight:400; font-size:.875rem; padding-left:0; }
.aa-embed .aa-lang { border-color:#c9d3df; margin:0 0 8px auto; }
.aa-embed .aa-lang button { color:var(--brand-primary); opacity:1; }
.aa-embed .aa-lang button.on { background:var(--brand-primary); color:#fff; }
.aa-embed .aa-main { max-width:none; margin:0; padding:24px 0 40px; }
.aa-embed .aa-title { font-size:1.5rem; margin:0 0 4px; }
.aa-embed p.meta { margin-top:0; }
@media (max-width:759px){ .aa-embed .aa-wrap { padding:0 16px; } }
.aa-mockbar { background:#222; color:#fff; font:13px/1.4 Roboto, Arial, sans-serif; text-align:center;
  padding:6px 16px; }
.aa-mockbar a { color:#ffd970; }
"""

# their header menus open and close (their own script is not copied); a visit that comes from
# another twin lands on the tabs, not on the photo again
SHELL_JS = """<script>
document.addEventListener('click', function(e){
  var b = e.target.closest('[data-cd-toggler]');
  document.querySelectorAll('[data-cd-toggler][aria-expanded="true"]').forEach(function(o){
    if (o !== b) { o.setAttribute('aria-expanded', 'false');
      document.getElementById(o.getAttribute('aria-controls')).setAttribute('data-cd-hidden', 'true'); } });
  if (!b) return;
  var open = b.getAttribute('aria-expanded') !== 'true';
  b.setAttribute('aria-expanded', String(open));
  document.getElementById(b.getAttribute('aria-controls')).setAttribute('data-cd-hidden', String(!open));
});
(function(){ var r; try { r = new URL(document.referrer); } catch(e) { return; }
  if (r.origin === location.origin && /\\/mock-unocha[\\w.-]*\\.html$/.test(r.pathname) && !location.hash)
    document.getElementById('aa').scrollIntoView(); })();
</script>"""


def mock_name(name):
    return "mock-unocha.html" if name == "index.html" else f"mock-unocha-{name}"


def _quoted(names):
    """As build_site._quoted: any of these file names as a whole quoted string (an href, a
    value in the page data), optionally followed by an anchor or a query."""
    return re.compile(r"""(?<=['"`])(""" + "|".join(sorted(map(re.escape, names), key=len, reverse=True))
                      + r""")(?=[#?'"`])""")


# ---------------------------------------------------------------- CSS scoping
def _rules(css):
    """Top-level (prelude, block) pairs; block is None for a statement (@import …;). Comments,
    strings and nested braces (an @media block) are stepped over, not split on."""
    out, i, n, start, depth, open_at = [], 0, len(css), 0, 0, 0
    while i < n:
        c = css[i]
        if css.startswith("/*", i):
            j = css.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c in "\"'":
            i += 1
            while i < n and css[i] != c:
                i += 2 if css[i] == "\\" else 1
        elif c == "{":
            if depth == 0:
                open_at = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                out.append((css[start:open_at], css[open_at + 1:i]))
                start = i + 1
        elif c == ";" and depth == 0:
            out.append((css[start:i], None))
            start = i + 1
        i += 1
    return out


def _selectors(prelude):
    """A selector list split on its top-level commas (not those inside :is(…) or [a=","])."""
    out, depth, quote, cur = [], 0, None, ""
    for c in prelude:
        if quote:
            quote = None if c == quote else quote
        elif c in "\"'":
            quote = c
        elif c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif c == "," and depth == 0:
            out.append(cur)
            cur = ""
            continue
        cur += c
    return out + [cur]


def _scope_selector(sel):
    """html / body / :root stand for our block; html[data-lang="fr"] .x keeps the html part (the
    language toggle marks <html>) and scopes the rest; main is a div in their page (they have a
    <main>); anything else gets the block in front."""
    sel = sel.strip()
    m = re.match(r"(html|body|:root)(?![\w-])([^\s>+~]*)\s*(.*)", sel, re.S)
    if m:
        first, rest = m.group(1) + m.group(2), m.group(3)
        if not m.group(2) and not rest:
            return ROOT
        return f"{first} {ROOT}" + (f" {rest}" if rest else "")
    return f"{ROOT} " + re.sub(r"(?<![\w.#:\[=-])main(?![\w-])", ".aa-main", sel)


def scope_css(css):
    out = []
    for prelude, block in _rules(css):
        p = re.sub(r"/\*.*?\*/", "", prelude, flags=re.S).strip()
        if block is None:
            if p:
                out.append(p + ";")
        elif p.startswith("@"):
            kw = re.match(r"@([\w-]+)", p).group(1).lower()
            out.append(f"{p}{{{scope_css(block) if kw in ('media', 'supports', 'container', 'layer') else block}}}")
        elif p:
            out.append(",".join(map(_scope_selector, _selectors(p))) + f"{{{block}}}")
    return "\n".join(out)


def _scope_styles(html):
    return re.sub(r"(<style[^>]*>)(.*?)(</style>)", lambda m: m[1] + scope_css(m[2]) + m[3], html, flags=re.S)


# ---------------------------------------------------------------- pages
def reachable(site):
    """index.html and every page reachable from it by links: the tabs and the framework pages
    the map opens. The unlisted pages are linked from no listed page (build_site checks)."""
    names = {p.name for p in site.glob("*.html") if not p.name.startswith("mock-")}
    pat = _quoted(names)
    seen, todo = set(), ["index.html"]
    while todo:
        n = todo.pop()
        if n not in seen and n in names:
            seen.add(n)
            todo += pat.findall((site / n).read_text())
    return seen


def _tab_row(top, name):
    """Our header's tabs, as OCHA's tab row: the page's own tab selected; a framework page sits
    under the Map, which opens it. The language toggle stays, at the right."""
    nav = re.search(r'<nav class="pub">(.*?)</nav>', top, re.S)
    toggle = re.search(r'<span class="aa-lang".*?</span>', top, re.S)
    if not nav or not toggle:
        raise SystemExit(f"FATAL: {name}: no tabs or no language toggle in its header")
    tabs = [(re.search(r'href="([^"]+)"', a)[1], a, label)
            for a, label in re.findall(r"<a\b([^>]*)>(.*?)</a>", nav[1], re.S)]
    here = name if any(href == name for href, _, _ in tabs) else "index.html"
    sub, selected = ' class="sub"', ' aria-selected="true" aria-current="page"'
    items = "".join(
        ("<li class='aa-sub'>" if sub in a else "<li>") + "<a" + a.replace(sub, "")
        + (selected if href == here else "") + f">{label}</a></li>"
        for href, a, label in tabs)
    return (f'<div class="aa-tabrow"><ul class="uno-section-tabs__list" role="tablist">{items}</ul>'
            f"{toggle[0]}</div>"), {href for href, _, _ in tabs}


def mock_page(name, doc, shell, links):
    m = DOC.fullmatch(doc)
    if not m:
        raise SystemExit(f"FATAL: {name} is not shaped as build_site._render writes a page")
    tabs, tab_pages = _tab_row(m["top"], name)
    main = m["main"]
    # the tab names the page already; a framework page keeps its title, under OCHA's own <h1>
    main = re.sub(r"^<h1>(.*?)</h1>", "" if name in tab_pages else r"<h2 class='aa-title'>\1</h2>",
                  main, count=1, flags=re.S)
    head = "".join(re.findall(r"<style>.*?</style>|<script>.*?</script>", m["head"], re.S))
    head = _scope_styles(head).replace("</style>", EMBED_CSS + "</style>", 1)
    head += ("<script>window.AA_TITLES = {" + ", ".join(f'"{l}": "{TITLE}"' for l in ("en", "fr", "es"))
             + "};</script>")
    block = (f'<div class="aa-embed" id="aa"><div class="aa-wrap"><div class="uno-section-tabs">{tabs}'
             f'<div class="aa-main" role="tabpanel">{_scope_styles(main)}</div></div></div></div>')
    block = links.sub(lambda m: mock_name(m[1]), block)
    # what a page's script hangs on <body> (the History page's tooltip) would sit outside the block,
    # where its scoped CSS does not reach: hang it on the block (the real embed needs the same)
    block = block.replace("document.body.appendChild(", "document.getElementById('aa').appendChild(")
    bar = (f'<div class="aa-mockbar" role="note"><b>Mock-up</b> of unocha.org/anticipatory-action with '
           f'the AA site under the photo: not the live OCHA page, and the figures are under development. '
           f'<a href="{name}">This page on the AA site</a></div>')
    out = shell.replace("<!--AA-HEAD-->", head, 1).replace("<!--AA-BLOCK-->", block, 1)
    out = re.sub(r"(<body[^>]*>)", lambda b: b[1] + bar, out, count=1)
    return out.replace("</body>", SHELL_JS + "</body>", 1)


def main(site):
    shell = SHELL.read_text()
    if shell.count("<!--AA-HEAD-->") != 1 or shell.count("<!--AA-BLOCK-->") != 1:
        raise SystemExit(f"FATAL: {SHELL} lacks its markers: re-run scripts/snapshot_unocha.py")
    pages = reachable(site)
    links = _quoted(pages)
    written = set()
    for name in sorted(pages):
        out = mock_name(name)
        (site / out).write_text(mock_page(name, (site / name).read_text(), shell, links))
        written.add(out)
    for f in site.glob("mock-*.html"):     # a page that left the site takes its twin with it
        if f.name not in written:
            f.unlink()
    shutil.copy(REPO / "site_src" / "unocha.css", site / "unocha.css")
    print(f"  mock-up: {len(written)} pages (mock-unocha.html …)")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "site_build")
