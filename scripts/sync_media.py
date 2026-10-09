"""Sync the media manifest (site_src/media.json) from the shared Drive folder "AA Visuals".

The Media page (scripts/page_media.py) shows what the manifest lists, and nothing else.
No file is copied: the folder is shared "anyone with the link", the page shows Drive's own
renditions of each file by its id, and the originals (6 GB of photos on 2026-10-09) stay
where they are. So this script only LISTS. It walks the folder tree through Drive's public
folder view (no sign-in, no API key, no file is fetched) and reads the catalogue workbook
kept at the folder's root: its inventory sheet for sizes and dates, its posts sheet for
the social posts.

    uv run python scripts/sync_media.py             # rewrite site_src/media.json
    uv run python scripts/sync_media.py --dry-run   # say what would change, write nothing

Run by hand, and read the diff before committing it: what is in the manifest is published
(the publish workflow runs on a push that touches site_src/). It is not part of the nightly
build on purpose, so nothing reaches the page that nobody looked at.

What is left out, and said so on every run:
- the catalogue itself and any other spreadsheet at the folder's root (working files, with
  research notes), and hidden sidecar files (.BridgeSort, …);
- catalogue rows that are not a post on a public platform: rows with no exact post link
  (still in the catalogue's recovery queue), and leads that point to a file share or a
  production board (Dropbox, Trello) — private links are not ours to publish;
- of each post, everything but the post itself: the catalogue's notes, verification trail
  and local paths stay in the catalogue.

The manifest is generated: hand edits are overwritten by the next run. Curation (hiding an
item, a caption, a credit) will need its own file or table; none exists yet.
"""

import argparse
import html
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path

ROOT_FOLDER = "1yYua6QS7AU6HuZX9Eadysad_TyZfnRIU"      # "AA Visuals", shared by the AA team
CATALOGUE_PREFIX = "AA Social Media & Visual Asset Catalogue"
POSTS_SHEET, INVENTORY_SHEET = "Verified posts", "Drive asset inventory"
MANIFEST = Path(__file__).parents[1] / "site_src" / "media.json"

UA = {"User-Agent": "Mozilla/5.0 (ds-aa-tracking media sync)"}
ENTRY = re.compile(r'<div class="flip-entry" id="entry-([^"]+)"(.*?)'
                   r'<div class="flip-entry-last-modified">', re.S)
SHEET_MIME = "application/vnd.google-apps.spreadsheet"

# a post counts when its link is on one of these: host suffix -> the platform's name
PLATFORMS = {"x.com": "X", "twitter.com": "X", "linkedin.com": "LinkedIn", "bsky.app": "Bluesky",
             "facebook.com": "Facebook", "instagram.com": "Instagram", "tiktok.com": "TikTok",
             "youtube.com": "YouTube", "youtu.be": "YouTube"}
# the only host a post's picture is taken from: its addresses are stable (LinkedIn's expire)
POST_IMAGE_HOST = "pbs.twimg.com"


def _get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 — retried, then raised as is
            err = e
            time.sleep(2 * (i + 1))
    raise err


def list_folder(folder_id):
    """(title, entries) of one public folder, from Drive's embedded folder view. An entry is
    {id, name, mime, folder}. The view is not paged; the count is checked against the page."""
    body = _get(f"https://drive.google.com/embeddedfolderview?id={folder_id}").decode("utf-8", "replace")
    title = re.search(r"<title>(.*?)</title>", body, re.S)
    rows = []
    for eid, rest in ENTRY.findall(body):
        name = re.search(r'class="flip-entry-title">(.*?)</div>', rest, re.S)
        icon = re.search(r'drive-thirdparty\.googleusercontent\.com/16/type/([^"]+)"', rest)
        href = re.search(r'href="([^"]+)"', rest)
        mime = icon.group(1) if icon else ""
        rows.append({"id": eid, "name": html.unescape(name.group(1)).strip() if name else "",
                     "mime": mime,
                     "folder": "folder" in mime or "/folders/" in (html.unescape(href.group(1)) if href else "")})
    seen = len(re.findall(r'class="flip-entry"', body))
    if seen != len(rows) or "flip-entries" not in body:
        raise SystemExit(f"FATAL: folder {folder_id}: {seen} entries in Drive's page, {len(rows)} read "
                         "— the folder view changed, or the folder is no longer shared by link")
    return (html.unescape(title.group(1)).strip() if title else ""), rows


def walk(root):
    """Every folder under root, depth first: [(path, folder_id, entries)], path = folder names
    below the root ([] for the root itself)."""
    out, title = [], None

    def visit(fid, path):
        nonlocal title
        t, rows = list_folder(fid)
        title = title or t
        out.append((path, fid, rows))
        time.sleep(0.4)                      # one small page per folder: no need to hurry
        for r in sorted((r for r in rows if r["folder"]), key=lambda r: _natural(r["name"])):
            visit(r["id"], path + [r["name"]])

    visit(root, [])
    return title, out


def _natural(s):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", s)]


def _kind(mime):
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime == "application/pdf" or "officedocument" in mime or mime in (
            "application/msword", "application/vnd.google-apps.document",
            "application/vnd.google-apps.presentation") or "spreadsheet" in mime:
        return "document"
    return None                              # sidecars and anything a browser cannot show


def _sheet(wb, name):
    """A sheet as a list of dicts keyed by its header row."""
    if name not in wb.sheetnames:
        raise SystemExit(f"FATAL: the catalogue has no sheet {name!r} (it has: {', '.join(wb.sheetnames)})")
    rows = list(wb[name].iter_rows(values_only=True))
    head = [str(h).strip() if h is not None else "" for h in rows[0]]
    return [dict(zip(head, r)) for r in rows[1:] if any(c not in (None, "") for c in r)]


def _s(v):
    return "" if v is None else str(v).strip()


def _platform(url):
    host = urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")
    return next((p for h, p in PLATFORMS.items() if host == h or host.endswith("." + h)), None)


def _date_from_id(url):
    """The day a post was made, read from its own identifier (UTC): X and LinkedIn ids start
    with the creation time in milliseconds, a Bluesky record key is its creation time."""
    try:
        if m := re.search(r"(?:x|twitter)\.com/[^/]+/status/(\d{15,20})", url):
            ms = (int(m.group(1)) >> 22) + 1288834974657
        elif m := re.search(r"linkedin\.com/.*?(?:activity|ugcPost)[-:](\d{19})", url):
            ms = int(m.group(1)) >> 22
        elif m := re.search(r"bsky\.app/profile/[^/]+/post/([2-7a-z]{13})\b", url):
            n = 0
            for ch in m.group(1):
                n = n * 32 + "234567abcdefghijklmnopqrstuvwxyz".index(ch)
            ms = (n >> 10) // 1000
        else:
            return ""
        d = datetime.fromtimestamp(ms / 1000, UTC).date()
        return d.isoformat() if date(2006, 1, 1) <= d <= date.today() else ""
    except (ValueError, OverflowError, OSError):
        return ""


def _post_image(url):
    """A post's picture, small rendition, when the catalogue has a stable address for it."""
    u = urllib.parse.urlsplit(_s(url))
    if u.scheme != "https" or u.netloc.lower() != POST_IMAGE_HOST:
        return ""
    q = dict(urllib.parse.parse_qsl(u.query))
    q["name"] = "small"
    return urllib.parse.urlunsplit((u.scheme, u.netloc, u.path, urllib.parse.urlencode(q), ""))


def read_posts(rows):
    """The catalogue's posts sheet -> (posts, left_out). Only the post itself is kept."""
    posts, left = [], {"no exact post link": 0, "not on a public platform": 0, "listed twice": 0}
    seen = set()
    for r in rows:
        url = _s(r.get("Exact individual post URL"))
        if not url.lower().startswith("https://"):
            left["no exact post link"] += 1
            continue
        platform = _platform(url)
        if not platform:
            left["not on a public platform"] += 1
            continue
        if url in seen:
            left["listed twice"] += 1
            continue
        seen.add(url)
        given = re.match(r"\d{4}-\d{2}-\d{2}", _s(r.get("Date")))
        post = {"platform": platform, "account": _s(r.get("Account")),
                "date": given.group(0) if given else _date_from_id(url),
                "country": _s(r.get("Country / region")), "theme": _s(r.get("Hazard / theme")),
                "asset": _s(r.get("Asset type")),
                "text": _s(r.get("Original post text / verified excerpt")), "url": url,
                "image": _post_image(r.get("Direct original media URL (when recoverable)"))}
        posts.append({k: v for k, v in post.items() if v})
    posts.sort(key=lambda p: (p.get("date", ""), p["url"]), reverse=True)
    return posts, {k: n for k, n in left.items() if n}


def build():
    import openpyxl

    title, tree = walk(ROOT_FOLDER)
    root_rows = tree[0][2]
    sheets = sorted((r for r in root_rows if r["mime"] == SHEET_MIME and r["name"].startswith(CATALOGUE_PREFIX)),
                    key=lambda r: _natural(r["name"]))
    if not sheets:
        raise SystemExit(f"FATAL: no Google Sheet named {CATALOGUE_PREFIX!r}… at the root of the folder: "
                         "the posts and the file sizes come from it")
    cat = sheets[-1]                         # the highest version, when several are kept
    wb = openpyxl.load_workbook(io.BytesIO(_get(
        f"https://docs.google.com/spreadsheets/d/{cat['id']}/export?format=xlsx")), read_only=True, data_only=True)
    inv = {_s(r.get("Drive file ID")): r for r in _sheet(wb, INVENTORY_SHEET)}
    posts, posts_left = read_posts(_sheet(wb, POSTS_SHEET))

    groups, skipped, empty = [], [], []
    for path, fid, rows in tree:
        items = []
        for r in sorted((r for r in rows if not r["folder"]), key=lambda r: _natural(r["name"])):
            kind = _kind(r["mime"])
            if r["name"].startswith(".") or kind is None or (not path and "spreadsheet" in r["mime"]):
                skipped.append("/".join(path + [r["name"]]))
                continue
            item = {"id": r["id"], "name": r["name"], "kind": kind}
            known = inv.get(r["id"])
            if known:
                size = _s(known.get("Size (bytes)"))
                if re.fullmatch(r"\d+(\.0+)?", size):
                    item["bytes"] = int(float(size))
                modified = re.match(r"\d{4}-\d{2}-\d{2}", _s(known.get("Modified (UTC)")))
                if modified:
                    item["modified"] = modified.group(0)
            items.append(item)
        if items:
            groups.append({"path": path, "id": fid, "items": items})
        elif path and not rows:
            empty.append("/".join(path))
    manifest = {"synced": date.today().isoformat(),
                "folder": {"id": ROOT_FOLDER, "title": title}, "catalogue": cat["name"],
                "groups": groups, "posts": posts}
    return manifest, {"skipped": skipped, "empty": empty, "posts_left": posts_left,
                      "unsized": sum(1 for g in groups for i in g["items"] if "bytes" not in i)}


def dumps(m):
    """The manifest as JSON with one file and one post per line, so a sync reads as a diff."""
    def j(v):
        return json.dumps(v, ensure_ascii=False)
    out = ["{", f' "synced": {j(m["synced"])},', f' "folder": {j(m["folder"])},',
           f' "catalogue": {j(m["catalogue"])},', ' "groups": [']
    for gi, g in enumerate(m["groups"]):
        out.append(f'  {{"path": {j(g["path"])}, "id": {j(g["id"])}, "items": [')
        out += [f"   {j(it)}{',' if k < len(g['items']) - 1 else ''}" for k, it in enumerate(g["items"])]
        out.append("  ]}" + ("," if gi < len(m["groups"]) - 1 else ""))
    out += [" ],", ' "posts": [']
    out += [f"  {j(p)}{',' if k < len(m['posts']) - 1 else ''}" for k, p in enumerate(m["posts"])]
    out += [" ]", "}"]
    return "\n".join(out) + "\n"


def _changes(old, new):
    """What a sync changes, in words: files and posts that came and went."""
    def files(m):
        return {i["id"]: "/".join(g["path"] + [i["name"]]) for g in m.get("groups", []) for i in g["items"]}
    def posts(m):
        return {p["url"]: f'{p["platform"]} {p.get("date", "")} {p.get("account", "")}' for p in m.get("posts", [])}
    lines = []
    for what, a, b in (("file", files(old), files(new)), ("post", posts(old), posts(new))):
        for sign, ids, src in (("+", b.keys() - a.keys(), b), ("-", a.keys() - b.keys(), a)):
            names = sorted(src[i] for i in ids)
            if names:
                lines.append(f"  {sign}{len(names)} {what}(s): " + "; ".join(names[:8])
                             + (f"; … {len(names) - 8} more" if len(names) > 8 else ""))
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="say what would change, write nothing")
    a = ap.parse_args()
    manifest, notes = build()
    n = {k: sum(1 for g in manifest["groups"] for i in g["items"] if i["kind"] == k)
         for k in ("image", "video", "document")}
    size = sum(i.get("bytes", 0) for g in manifest["groups"] for i in g["items"])
    print(f'{manifest["folder"]["title"]}: {n["image"]} photos, {n["video"]} videos, {n["document"]} documents '
          f'in {len(manifest["groups"])} folders ({size / 1e9:.1f} GB of originals, none fetched) · '
          f'{len(manifest["posts"])} posts from {manifest["catalogue"]!r}')
    for k, v in notes["posts_left"].items():
        print(f"  left out: {v} catalogue row(s) — {k}")
    if notes["skipped"]:
        print(f'  left out: {len(notes["skipped"])} file(s) — ' + "; ".join(notes["skipped"]))
    if notes["empty"]:
        print("  empty folder(s): " + "; ".join(notes["empty"]))
    if notes["unsized"]:
        print(f'  {notes["unsized"]} file(s) are not in the catalogue\'s inventory yet: listed without a size')
    old = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    changes = _changes(old, manifest)
    print("\n".join(changes) if changes else "  no file or post added or removed")
    if a.dry_run:
        print("dry run: nothing written")
        return
    MANIFEST.write_text(dumps(manifest))
    print(f"wrote {MANIFEST.relative_to(Path(__file__).parents[1])} — read the diff before committing it")


if __name__ == "__main__":
    sys.exit(main())
