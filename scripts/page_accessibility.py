"""The accessibility statement (accessibility.html): what the site does for keyboard, screen
reader and low-vision readers, what it cannot do, how to get the data another way, and whom
to write to. Public, linked from the foot of every page (build_site._render), not a tab.

Owner, 2026-10-29: the contact is the team's address, no personal names.
"""

from site_i18n import T, TB

PAGE, TITLE = "accessibility.html", "Accessibility"
CONTACT = "ocha-datascience@un.org"

CSS = """
.a11y { max-width:820px; }
.a11y h2 { font-size:17px; margin:22px 0 8px; }
.a11y ul { margin:6px 0 10px 20px; padding:0; } .a11y li { margin:4px 0; }
.a11y p { margin:8px 0; line-height:1.5; }
"""


def build(page):
    body = f"""<style>{CSS}</style><div class='card a11y'>
<p>{TB("This site aims to meet the <a href='https://www.w3.org/TR/WCAG21/' target='_blank' rel='noopener'>Web Content Accessibility Guidelines (WCAG) 2.1</a> at level AA, in line with the United Nations' commitment to accessible digital content. It is built to be used with a keyboard, with a screen reader, at high zoom, and in English, French and Spanish.")}</p>
<h2>{T("What the site does")}</h2>
<ul>
<li>{T("Every page can be used with the keyboard alone: Tab moves between controls, Enter or Space activates them, Escape closes a panel or goes back to the world map. A 'skip to content' link is the first stop on each page, and the control with focus is outlined.")}</li>
<li>{T("Text keeps a contrast of at least 4.5:1 against its background; the layout works at 200% zoom and on a phone.")}</li>
<li>{T("The language switch in the header (English, French, Spanish) applies to every page and is remembered.")}</li>
<li>{T("Every figure in a chart is also given in words or in a table on the same page; the Map's table lists everything the map shows, with its totals, and downloads as a CSV file.")}</li>
<li>{T("Nothing flashes. Movement (the map zoom, the panel) is turned off for readers who have asked their system for reduced motion.")}</li>
</ul>
<h2>{T("Known limits")}</h2>
<ul>
<li>{T("The map itself is a picture. The country names and pins drawn over it are the buttons a keyboard and a screen reader reach, and the table under the map lists the same frameworks.")}</li>
<li>{T("Charts are pictures: their figures are in the text and tables around them, not in the chart.")}</li>
<li>{T("Framework documents and reports are published by their authors as PDF files; their accessibility is theirs.")}</li>
<li>{T("Social media posts on the Media page are shown as they were published on their platforms.")}</li>
</ul>
<h2>{T("The data another way")}</h2>
<p>{T("Every table on the site downloads as a CSV file. If a figure or a page is not usable for you, write to us and we will send it in a form that works.")}</p>
<h2>{T("Contact")}</h2>
<p>{TB("Tell us what did not work and on which page: <a href='mailto:" + CONTACT + "'>" + CONTACT + "</a>. We will reply and fix what we can.")}</p>
<p class='meta'>{T("This statement was prepared on 30 October 2026 after an automated check (axe-core) of every page and keyboard testing of the Map. It is reviewed when the site changes.")}</p>
</div>"""
    page(PAGE, TITLE, body)
