"""The AA assistant on the development site: a tab (assistant.html) and a panel on every other page.

Owner, 2026-11-16: "can you put the chatbot on a tab of the dev site? or maybe a sidebar of the actual
site, or like a little chatbot in the corner? … when I promote the site to get other fixes online, i
DO NOT want the chatbot to go live yet. like, keep it greyed out like the other tabs".

The assistant itself is not part of this site: it is the OCHA AA assistant, a separate app (its own
password, its own login; it reads this site's database snapshot, the open layer and the framework
documents). This site frames its embeddable page (ASSISTANT_URL, /aa/embed); the app allows only
this site's address to frame it.

Where it shows (the gate is the build, not the branch: a promote builds the open site from this
same code):
  * dev/assistant.html  the tab: the assistant, full page.
  * dev/*.html          a "Ask a question" button in the corner opening a panel, as a window over
                        the page or docked to its side (the reader's choice, kept in the browser);
                        the frame is made on the first open, never on a page view.
  * the open site       assistant.html is a "Coming soon" page like the other tabs not public yet;
                        no page or file at the root carries the panel or the assistant's address
                        (build_site.write_site stops the build otherwise; publish.sh checks again).
"""

import os
import re
from urllib.parse import urlsplit

from site_i18n import ATTR, T

PAGE, TITLE = "assistant.html", "AA assistant"
# the assistant's embeddable page; a local build points it at a local copy of the app
ASSISTANT_URL = os.environ.get("AA_ASSISTANT_URL", "https://chd-ds-kb-chat.azurewebsites.net/aa/embed")
MARK = "aa-assistant-panel"     # in the panel's code alone: the open site must never carry it
EMBED_PATH = "/aa/embed"        # in the assistant's address alone: likewise
# the panel's block on a page, between these: the unocha.org mock-up (mock_unocha.py) takes it out
BEGIN, END = f"<!--{MARK}-->", f"<!--/{MARK}-->"
PANEL_BLOCK = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)


def origin():
    u = urlsplit(ASSISTANT_URL)
    return f"{u.scheme}://{u.netloc}"


def _frame(cls):
    return (f"<iframe class='{cls}' src='{ASSISTANT_URL}' title='{TITLE}' referrerpolicy='origin' "
            "allow='clipboard-write'></iframe>")


PAGE_CSS = """
.asst-intro { max-width:820px; margin:0 0 10px; font-size:14px; color:#334155; line-height:1.5; }
.asst-full { height:calc(100vh - 150px); min-height:520px; border:1px solid #d6dde8; border-radius:10px;
             overflow:hidden; background:#fff; }
.asst-full iframe { width:100%; height:100%; border:0; display:block; }
"""


def build(page):
    body = (f"<style>{PAGE_CSS}</style>"
            f"<p class='asst-intro'>{T('Ask about the frameworks, the money, the activations and the framework documents on this site. The answers come from the site’s data and documents and say where each figure comes from. Check a figure before you use it. The assistant asks for its own password the first time.')}</p>"
            f"<div class='asst-full'>{_frame('asst')}</div>")
    page(PAGE, TITLE, body)


ICON_CHAT = ("<svg viewBox='0 0 24 24' aria-hidden='true' fill='none' stroke='currentColor' stroke-width='2' "
             "stroke-linecap='round' stroke-linejoin='round'><path d='M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z'/></svg>")
ICON_SIDE = ("<svg viewBox='0 0 24 24' aria-hidden='true' fill='none' stroke='currentColor' stroke-width='2'>"
             "<rect x='3' y='4' width='18' height='16' rx='2'/><path d='M14 4v16'/></svg>")
ICON_WINDOW = ("<svg viewBox='0 0 24 24' aria-hidden='true' fill='none' stroke='currentColor' stroke-width='2'>"
               "<rect x='3' y='4' width='18' height='16' rx='2'/><rect x='11' y='11' width='7' height='6' rx='1'/></svg>")
ICON_FULL = ("<svg viewBox='0 0 24 24' aria-hidden='true' fill='none' stroke='currentColor' stroke-width='2' "
             "stroke-linecap='round'><path d='M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7'/></svg>")
ICON_CLOSE = ("<svg viewBox='0 0 24 24' aria-hidden='true' fill='none' stroke='currentColor' stroke-width='2' "
              "stroke-linecap='round'><path d='M6 6l12 12M18 6L6 18'/></svg>")

PANEL_CSS = """
.aa-asst-launch { position:fixed; right:20px; bottom:20px; z-index:9000; display:flex; align-items:center; gap:8px;
  background:#1f2a44; color:#fff; border:0; border-radius:24px; padding:11px 18px 11px 14px;
  font:600 14px/1 -apple-system,'Segoe UI',Roboto,sans-serif; box-shadow:0 4px 16px rgba(15,23,42,.28); cursor:pointer; }
.aa-asst-launch:hover { background:#2c3b60; }
.aa-asst-launch:focus-visible { outline:3px solid #9ec5f0; outline-offset:2px; }
.aa-asst-launch svg { width:18px; height:18px; flex:none; }
.aa-asst-panel { position:fixed; z-index:9001; background:#fff; display:flex; flex-direction:column;
  box-shadow:0 10px 36px rgba(15,23,42,.22); }
.aa-asst-panel[hidden] { display:none; }
html.aa-asst-window .aa-asst-panel { right:20px; bottom:20px; width:420px; height:min(700px, calc(100vh - 40px));
  border-radius:12px; border:1px solid #d6dde8; overflow:hidden; }
html.aa-asst-side .aa-asst-panel { right:0; top:0; bottom:0; width:440px; border-left:1px solid #d6dde8; }
html.aa-asst-side.aa-asst-open body { margin-right:440px; }
html.aa-asst-open .aa-asst-launch { display:none; }
.aa-asst-bar { display:flex; align-items:center; gap:2px; padding:7px 8px 7px 14px; background:#1f2a44; color:#fff; }
.aa-asst-bar .ttl { flex:1; font:600 14px/1.2 -apple-system,'Segoe UI',Roboto,sans-serif; }
.aa-asst-bar .tag { font-size:10.5px; font-weight:700; letter-spacing:.05em; text-transform:uppercase; background:#f0b429;
  color:#1f2a44; padding:1px 7px; border-radius:9px; margin-left:8px; vertical-align:2px; }
.aa-asst-bar button, .aa-asst-bar a { background:transparent; border:0; color:#cfe0f3; width:32px; height:32px;
  border-radius:6px; display:grid; place-items:center; cursor:pointer; padding:0; margin:0; }
.aa-asst-bar button:hover, .aa-asst-bar a:hover { background:rgba(255,255,255,.14); color:#fff; }
.aa-asst-bar button:focus-visible, .aa-asst-bar a:focus-visible { outline:2px solid #fff; outline-offset:-2px; }
.aa-asst-bar svg { width:17px; height:17px; }
html.aa-asst-side .aa-asst-bar .to-side, html.aa-asst-window .aa-asst-bar .to-window { display:none; }
.aa-asst-frame { flex:1; min-height:0; background:#f7f6f3; }
.aa-asst-frame iframe { width:100%; height:100%; border:0; display:block; }
@media (max-width:759px) {
  html.aa-asst-window .aa-asst-panel, html.aa-asst-side .aa-asst-panel { inset:0; width:auto; height:auto;
    border-radius:0; border:0; }
  html.aa-asst-side.aa-asst-open body { margin-right:0; }
  .aa-asst-bar .to-side, .aa-asst-bar .to-window { display:none; }
  .aa-asst-launch { right:14px; bottom:14px; padding:13px; } .aa-asst-launch .lbl { display:none; }
}
@media print { .aa-asst-launch, .aa-asst-panel { display:none !important; } }
"""

# open/closed is kept for the tab (sessionStorage: the panel stays open from page to page), window
# or side for the browser (localStorage); every read and write may fail (private windows)
PANEL_JS = """(function(){ /*""" + MARK + """*/
var SRC = %s, root = document.documentElement, box = document.getElementById('aa-asst');
if (!box) return;
var panel = box.querySelector('.aa-asst-panel'), launch = box.querySelector('.aa-asst-launch'),
    holder = box.querySelector('.aa-asst-frame');
function get(s, k){ try { return window[s].getItem(k); } catch(e){ return null; } }
function put(s, k, v){ try { window[s].setItem(k, v); } catch(e){} }
function relayout(){ try { window.dispatchEvent(new Event('resize')); } catch(e){} }
function mode(m){ root.classList.toggle('aa-asst-side', m === 'side'); root.classList.toggle('aa-asst-window', m !== 'side');
  put('localStorage', 'aa-asst-mode', m); relayout(); }
function open(){
  if (!holder.firstChild) { var f = document.createElement('iframe'); f.src = SRC; f.title = 'AA assistant';
    f.referrerPolicy = 'origin'; f.setAttribute('allow', 'clipboard-write'); holder.appendChild(f); }
  panel.hidden = false; root.classList.add('aa-asst-open'); launch.setAttribute('aria-expanded', 'true');
  put('sessionStorage', 'aa-asst-open', '1'); relayout(); }
function close(){ panel.hidden = true; root.classList.remove('aa-asst-open'); launch.setAttribute('aria-expanded', 'false');
  put('sessionStorage', 'aa-asst-open', '0'); relayout(); launch.focus(); }
launch.addEventListener('click', open);
box.querySelector('.to-close').addEventListener('click', close);
box.querySelector('.to-side').addEventListener('click', function(){ mode('side'); });
box.querySelector('.to-window').addEventListener('click', function(){ mode('window'); });
panel.addEventListener('keydown', function(e){ if (e.key === 'Escape') close(); });
mode(get('localStorage', 'aa-asst-mode') === 'side' ? 'side' : 'window');
if (get('sessionStorage', 'aa-asst-open') === '1') open();
})();"""


def widget():
    """The corner button and its panel, for every page of the development site but the tab."""
    import json
    return (f"{BEGIN}<style>{PANEL_CSS}</style>"
            f"<div id='aa-asst'>"
            f"<button type='button' class='aa-asst-launch' aria-expanded='false' aria-controls='aa-asst-panel'>"
            f"{ICON_CHAT}<span class='lbl'>{T('Ask a question')}</span></button>"
            f"<section id='aa-asst-panel' class='aa-asst-panel' role='dialog' aria-labelledby='aa-asst-ttl' hidden>"
            f"<div class='aa-asst-bar'><span class='ttl' id='aa-asst-ttl'>{T('AA assistant')}"
            f"<span class='tag'>{T('trial')}</span></span>"
            f"<button type='button' class='to-side' {ATTR('title', 'Dock to the side of the page')} "
            f"{ATTR('aria-label', 'Dock to the side of the page')}>{ICON_SIDE}</button>"
            f"<button type='button' class='to-window' {ATTR('title', 'Show in a window over the page')} "
            f"{ATTR('aria-label', 'Show in a window over the page')}>{ICON_WINDOW}</button>"
            f"<a href='{PAGE}' {ATTR('title', 'Open as a full page')} {ATTR('aria-label', 'Open as a full page')}>{ICON_FULL}</a>"
            f"<button type='button' class='to-close' {ATTR('title', 'Close')} {ATTR('aria-label', 'Close')}>{ICON_CLOSE}</button>"
            f"</div><div class='aa-asst-frame'></div></section></div>"
            f"<script>{PANEL_JS % json.dumps(ASSISTANT_URL)}</script>{END}")


def check_open_site(root):
    """The open site (the files at the root of the build) carries neither the panel nor the
    assistant's address: the assistant is on the development site only (owner, 2026-11-16)."""
    hits = []
    for f in sorted(root.iterdir()):
        if f.is_file() and f.suffix in (".html", ".md", ".txt", ".json", ".csv", ".xml"):
            text = f.read_text(errors="replace")
            if MARK in text or EMBED_PATH in text or origin() in text:
                hits.append(f.name)
    if hits:
        raise SystemExit("FATAL: the open site carries the assistant (development site only): " + ", ".join(hits[:10]))
