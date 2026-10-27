"""Snapshot the OCHA corporate page the public site is meant to sit in, for the mock-up.

    uv run --no-project --with beautifulsoup4 python scripts/snapshot_unocha.py

Writes two committed files that scripts/mock_unocha.py reads (the build never fetches
unocha.org):
  site_src/unocha-shell.html   the page, with OCHA's own scripts removed (their behaviours,
                               analytics and tag manager must not run from our copy), their
                               section-tabs block removed (the AA site takes its place: user,
                               2026-10-27), and two markers: <!--AA-HEAD--> and <!--AA-BLOCK-->
                               (right under the photo)
  site_src/unocha.css          their stylesheets, concatenated, url()s made absolute
Every root-relative link, image and icon is made absolute, so they load from unocha.org.
Re-run it when the OCHA page changes; nothing else needs to.
"""
import re
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup, Comment

ORIGIN = "https://www.unocha.org"
URL = ORIGIN + "/anticipatory-action"
SRC = Path(__file__).parents[1] / "site_src"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130 Safari/537.36"}


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read().decode("utf-8")


def absolute(v):
    return ORIGIN + v if v.startswith("/") and not v.startswith("//") else v


def main():
    soup = BeautifulSoup(fetch(URL), "html.parser")

    # their stylesheets, in page order, as one local file
    css = []
    for link in soup.select('link[rel~="stylesheet"][href]'):
        href = absolute(link["href"])
        if href.startswith(ORIGIN):
            css.append(f"/* {href.split('?')[0]} */\n"
                       + re.sub(r"""url\((['"]?)(/[^/'")][^'")]*)\1\)""",
                                lambda m: f"url({m.group(1)}{ORIGIN}{m.group(2)}{m.group(1)})",
                                fetch(href)))
    (SRC / "unocha.css").write_text(
        f"/* Stylesheets of {URL}, snapshot {date.today()} (scripts/snapshot_unocha.py).\n"
        "   OCHA's Common Design theme: github.com/UN-OCHA/common_design (GPL-2.0). */\n"
        + "\n".join(css))

    for el in soup(["script", "noscript", "link", "style"]):
        el.decompose()
    for el in soup.find_all(string=lambda s: isinstance(s, Comment)):
        el.extract()
    for el in soup.find_all("meta"):
        if el.get("charset") is None and el.get("name") != "viewport":
            el.decompose()

    # the AA site replaces their tabs and goes right under the photo
    tabs = soup.select_one(".uno-section-tabs")
    hero = soup.select_one("article.cd-article .cd-layout-main-content > .cd-bleed")
    if tabs is None or hero is None:
        raise SystemExit("FATAL: the OCHA page no longer has its section tabs or its photo: "
                         "look at it again before re-running")
    tabs.decompose()
    hero.insert_after(Comment("AA-BLOCK"))

    # their header as their script leaves it (we drop the script): each menu and the search box
    # folded behind its button; scripts/mock_unocha.py opens and closes them
    soup.html["class"] = "js"
    icon = ('<svg width="16" height="16" aria-hidden="true" focusable="false" class="cd-icon '
            'cd-icon--{0} {1}"><use xlink:href="#cd-icon--{0}"></use></svg>')
    for el in soup.select("[data-cd-toggable]"):
        el["data-cd-processed"] = "true"
        kind = el.get("data-cd-component")
        if kind not in ("cd-search", "cd-nav-level-1"):
            continue
        el["data-cd-hidden"] = "true"
        attrs = (f'type="button" id="{el["id"]}-toggler" data-cd-toggler="" aria-expanded="false" '
                 f'aria-haspopup="menu" aria-controls="{el["id"]}"')
        if kind == "cd-search":
            el.insert_before(BeautifulSoup(
                f'<button {attrs} class="cd-search__btn">{icon.format("search", "cd-search__logo")}'
                '<span class="cd-search__btn-label">Search</span></button>', "html.parser"))
        else:
            label = soup.find(id=el["data-cd-replace"])
            label.replace_with(BeautifulSoup(
                f'<button {attrs} class="cd-nav-level-1__btn"><span class="cd-nav-level-1__btn-label">'
                f'{label.get_text(strip=True)}</span>{icon.format("arrow-down", "cd-nav-level-1__icon")}'
                "</button>", "html.parser"))

    # nothing posts from our copy (the subscribe form is a real mailing list)
    for form in soup.find_all("form"):
        if form.get("method", "get").lower() == "post":
            del form["action"]
            form["onsubmit"] = "return false"

    # their video goes through their own oEmbed page, which only they may frame: embed it directly
    for frame in soup.select('iframe[src*="/media/oembed"]'):
        video = re.search(r"(?:youtu\.be/|[?&]v=)([\w-]{11})", urllib.parse.unquote(frame["src"]))
        if video:
            frame["src"] = f"https://www.youtube-nocookie.com/embed/{video[1]}"
            frame["allowfullscreen"] = ""

    for el in soup.find_all(True):
        for a in ("href", "src", "action", "poster"):
            if el.has_attr(a):
                el[a] = absolute(el[a])
        if el.has_attr("srcset"):
            el["srcset"] = ", ".join(absolute(part.strip()) for part in el["srcset"].split(","))

    head = soup.head
    head.append(soup.new_tag("link", rel="icon", href=ORIGIN + "/favicon.ico"))
    head.append(soup.new_tag("link", rel="stylesheet", href=(
        "https://fonts.googleapis.com/css2?family=Roboto:ital,wght@0,300;0,400;0,500;0,700;"
        "0,900;1,400;1,700&display=swap")))
    head.append(soup.new_tag("link", rel="stylesheet", href="unocha.css"))
    head.append(Comment("AA-HEAD"))
    (SRC / "unocha-shell.html").write_text(
        f"<!doctype html>\n<!-- {URL}, snapshot {date.today()} (scripts/snapshot_unocha.py) -->\n"
        + str(soup.html))
    print(f"  site_src/unocha-shell.html, site_src/unocha.css ({len(css)} stylesheets)")


if __name__ == "__main__":
    main()
