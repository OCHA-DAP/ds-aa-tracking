"""The privacy note (privacy.html): what the open site counts and what it does not keep (D197).
Public, linked from the foot of every page beside the accessibility statement (build_site._render),
not a tab. It must say exactly what build_site.COUNT_HEAD sends and proxy/server.js's POST /hit
stores in aa.page_count: change them together.
"""

from site_i18n import T, TB, TF

PAGE, TITLE = "privacy.html", "Privacy"
CONTACT = "ocha-datascience@un.org"
PREPARED = "2026-11-04"   # the date the counting started being described here

CSS = """
.privacy { max-width:820px; }
.privacy h2 { font-size:17px; margin:22px 0 8px; }
.privacy ul { margin:6px 0 10px 20px; padding:0; } .privacy li { margin:4px 0; }
.privacy p { margin:8px 0; line-height:1.5; }
"""


def build(page):
    body = f"""<style>{CSS}</style><div class='card privacy'>
<p>{T("This site counts how it is used, to learn which pages and frameworks readers look at and what to improve. It does so without cookies, and keeps nothing that could tell one reader from another.")}</p>
<h2>{T("What is counted")}</h2>
<ul>
<li>{T("Each page view, each country or framework opened on the map, each change of language, each file downloaded and each link followed to another website.")}</li>
<li>{T("With each: the page, the language it was read in, whether the screen was a phone's or larger and, for a page view, the name of the website the reader came from (the site, not the page).")}</li>
</ul>
<h2>{T("What is not kept")}</h2>
<ul>
<li>{T("No cookie is set, and nothing is stored in your browser for counting.")}</li>
<li>{T("No IP address, identifier, time of day or browser details are recorded. The counting service holds the address a count comes from in memory for about an hour, only to limit how many counts one address can send, and then forgets it.")}</li>
<li>{T("Only daily totals are kept, for example: 12 views of the map in French on phones on 4 November.")}</li>
</ul>
<h2>{T("Where the counts are kept")}</h2>
<p>{T("In the database OCHA's data science team runs for this site, beside the data the site shows. They are not passed to any analytics company or advertiser, and are used only to improve the site.")}</p>
<h2>{T("Contact")}</h2>
<p>{TB("Questions about this note: <a href='mailto:" + CONTACT + "'>" + CONTACT + "</a>.")}</p>
<p class='meta'>{TF("This note was last updated on {d}.", d=PREPARED)}</p>
</div>"""
    page(PAGE, TITLE, body)
