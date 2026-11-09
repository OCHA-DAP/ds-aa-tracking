#!/usr/bin/env bash
# Build the three sites into one folder for GitHub Pages: rebuild → encrypt → stage → check.
# The publish workflow uploads the staged folder ($STAGE, default _site/) as the Pages artifact
# and deploys it (D195): the published site never enters git, every deploy is the whole site
# and atomic (a failed run leaves the live site as it was). Run locally, the script stops
# after the checks; to put a build online, run the workflow: gh workflow run publish.yml.
#   open site    top-level *.html  NO password: the map, Definitions and Accessibility
#                                  (OPEN_PAGES), and a "Coming soon" page in place of every
#                                  other public page (owner, 2026-11-01)
#   dev site     dev/*.html        password SITE_PASSWORD: every public page
#   admin site   admin/*.html      password ADMIN_PASSWORD (no default: it must be set)
# site_build/ is laid out the same way (scripts/build_site.py, write_site). The public pages
# never link to the admin site; the admin site links to the dev site.
# SKIP_BUILD=1 reuses the existing site_build/ + site_encrypted/ output.
# DRY_RUN=1 is accepted as before (stage and check, then stop): the script never deploys.
#
# Hard-won rules encoded here (two incidents, from when the site was committed to gh-pages):
# - the staged folder holds only what is copied in by name: nothing is swept in (the
#   UNENCRYPTED site_build/, scripts/, .venv/… once were)
# - the only directories in the published site are admin/, which holds only encrypted pages and the two
#   pdf.js files of the data-entry page, dev/, which holds only encrypted pages, the map's
#   geometry and the vendored scripts and styles, and dev/media/, which holds only the Media
#   page's photo renditions (<key>-w<width>.jpg, scripts/sync_media.py): any other nested path
#   aborts before anything is uploaded, and so does any other directory
# - every page under dev/ and admin/ is a staticrypt page, and a top-level page is served plain
#   only if the build marked it for the open site (OPEN_META); apart from OPEN_PAGES, a page
#   that is not a "Coming soon" page, or is the size of a real page, aborts before anything is uploaded
# - the OPEN LAYER (scripts/llm_layer.py) is published unencrypted on purpose, at the top level:
#   llms.txt, robots.txt, sitemap.xml and the data behind the pages the open site serves
#   (build_site.OPEN_PAGES: today the map's aa-map.md and aa-*.json / aa-*.csv tables), for
#   fetch-based tools and LLMs. The build writes nothing else (the data of the pages not open
#   yet is not written at all); never a page, never anything from dev/ or admin/.
# The mock-up of the site on unocha.org (scripts/mock_unocha.py: mock-unocha*.html, unlisted) is
# made from the dev pages and published with them, under the site password.
set -euo pipefail
OPEN_GLOBS='*.md aa-*.json aa-*.csv pdf-*.txt llms.txt llms-full.txt robots.txt sitemap.xml'
# the open files present in a directory (a literal name the build did not write is skipped: nullglob
# drops only patterns with a wildcard)
open_files() { ( cd "$1" && shopt -s nullglob && for g in $OPEN_GLOBS; do for f in $g; do [ -f "$f" ] && echo "$f"; done; done; true ); }
cd "$(dirname "$0")/.."
PW="${SITE_PASSWORD:-anticipation2026}"
ADMIN_PW="${ADMIN_PASSWORD:-}"
ADMIN=admin
DEV=dev
# the real pages served without a password: the same list as build_site.OPEN_PAGES (a page
# must be in both to go out plain)
OPEN_PAGES=" index.html definitions.html accessibility.html privacy.html "
# the published site's rules, checked on a staged folder ($1): run on every build's own stage, and
# with CHECK_ONLY=<folder> alone on the site the publish workflow assembles from two builds (D203)
check_stage() (
  cd "$1"
  # every file about to be uploaded, as paths relative to the site root
  FILES=$(find . -type f | sed 's|^\./||' | sort)
  BAD=$(echo "$FILES" | grep "/" | grep -v -E "^$ADMIN/([A-Za-z0-9_.-]+\.html|pdf\.min\.js|pdf\.worker\.min\.js)$" \
        | grep -v -E "^$DEV/([A-Za-z0-9_.-]+\.html|adm-[A-Z]{3}\.json|chart\.umd\.js|sankey\.js|unocha\.css)$" \
        | grep -v -E "^$DEV/media/[0-9a-f]{16}-w[0-9]+\.jpg$" || true)
  if [ -n "$BAD" ]; then
    echo "FATAL: nested path outside $ADMIN/, $DEV/ and $DEV/media/ — aborting" >&2
    echo "$BAD" | head >&2; exit 1
  fi
  DIRS=$(find . -mindepth 1 -type d | sed 's|^\./||' | sort | tr '\n' ' ')
  [ "$DIRS" = "$ADMIN $DEV " ] || [ "$DIRS" = "$ADMIN $DEV $DEV/media " ] \
    || { echo "FATAL: the site contains directories other than $ADMIN/, $DEV/ and $DEV/media/: $DIRS" >&2; exit 1; }
  echo "$FILES" | grep -E '\.html$' | while read -r f; do
    case "$f" in
      */*)    # dev/ and admin/: encrypted, nothing readable
        if ! grep -q "staticrypt-form" "$f" || grep -q "devbanner" "$f"; then
          echo "FATAL: $f is not an encrypted page — aborting" >&2; exit 1
        fi ;;
      *)      # the open site: only what the build marked for it, and apart from OPEN_PAGES only
              # "Coming soon" pages (class='soon' is written by build_site._soon_body alone; the
              # size cap only catches the map's data or a long page, not a short real page)
        if ! grep -q '<meta name="aa-site" content="open">' "$f"; then
          echo "FATAL: $f is served without a password but the build did not mark it for the open site — aborting" >&2; exit 1
        fi
        if [[ "$OPEN_PAGES" != *" $f "* ]] && { ! grep -q "class='soon'" "$f" || [ "$(wc -c < "$f")" -gt 250000 ]; }; then
          echo "FATAL: $f is served without a password but is not a 'Coming soon' page — aborting" >&2; exit 1
        fi ;;
    esac
  done
  [ -f "$ADMIN/index.html" ] || { echo "FATAL: the admin site has no index.html — aborting" >&2; exit 1; }
  # the open files are plain data: never a token, never a page
  for f in $(open_files .); do
    if grep -q "x-site-token\|staticrypt" "$f"; then
      echo "FATAL: open file $f carries a token or a page — aborting" >&2; exit 1
    fi
  done
  [ -f llms.txt ] || { echo "FATAL: the open layer is missing (no llms.txt) — aborting" >&2; exit 1; }
  [ -f "$DEV/index.html" ] || { echo "FATAL: the dev site has no index.html — aborting" >&2; exit 1; }
  echo "staged ✓ (tree clean): $(echo "$FILES" | grep -c -v "/") top-level files ($(open_files . | wc -l | tr -d ' ') of the open layer), $(echo "$FILES" | grep "^$DEV/" | grep -c -v "^$DEV/media/") under $DEV/, $(echo "$FILES" | grep -c "^$DEV/media/") under $DEV/media/ and $(echo "$FILES" | grep -c "^$ADMIN/") under $ADMIN/; $(du -sh . | cut -f1) in $1/"
)
if [ -n "${CHECK_ONLY:-}" ]; then
  [ -d "$CHECK_ONLY" ] || { echo "FATAL: CHECK_ONLY: no folder $CHECK_ONLY" >&2; exit 1; }
  check_stage "$CHECK_ONLY"; exit
fi
[ -n "$ADMIN_PW" ] || { echo "FATAL: ADMIN_PASSWORD is not set (the admin site has no default password)" >&2; exit 1; }
[ "$ADMIN_PW" != "$PW" ] || { echo "FATAL: the admin password must differ from the public one" >&2; exit 1; }

if [ -z "${SKIP_BUILD:-}" ]; then
  uv run python scripts/build_site.py
  # the mock-up never stops the site: if it fails, none of its pages goes out (a half-written
  # set would link to twins that are not there)
  uv run python scripts/mock_unocha.py site_build/$DEV \
    || { rm -f site_build/$DEV/mock-*.html; echo "::warning::mock-up (scripts/mock_unocha.py) failed: not published"; }
  # the mock-up's pages are written after the build's check: checked here (D199)
  uv run python scripts/no_kb.py site_build "$DEV/mock-*.html"
  rm -rf site_encrypted          # nothing from an earlier build may be published by accident
  # the dev site keeps the old site's password and "Remember me" keys (same origin, same salt:
  # .staticrypt.json), so a password remembered on the old site opens it
  npx -y staticrypt site_build/$DEV/*.html -d site_encrypted/$DEV -p "$PW" --short --remember 30 \
    --template-title "Anticipatory action — development version" \
    --template-instructions "The development version of the site, with the pages that are not public yet. For the password, write to ocha-datascience@un.org."
  # the admin password goes through the environment, not the command line
  STATICRYPT_PASSWORD="$ADMIN_PW" npx -y staticrypt site_build/$ADMIN/*.html -d site_encrypted/$ADMIN \
    --short --remember 30 \
    --template-title "AA tracking admin" \
    --template-instructions "Admin site. Enter the admin password." \
    --template-color-primary "#3b2338" --template-color-secondary "#6b4a66"
  # "Remember me" is kept per origin and both sites share one: the admin pages get their own
  # keys, so a remembered public password and a remembered admin password do not overwrite
  # each other
  perl -pi -e 's/staticrypt_passphrase/staticrypt_admin_passphrase/g; s/staticrypt_expiration/staticrypt_admin_expiration/g' \
    site_encrypted/$ADMIN/*.html
fi

# the Media page's photos: the renditions its manifest lists, from the dev blob (needs
# DSCI_AZ_BLOB_DEV_SAS); a cached folder only fetches what it lacks
uv run python scripts/sync_media.py --fetch site_media

# the staged site: built fresh every time, so a page dropped from the build, or moved to the
# admin site, cannot linger at its old address. It is deleted whole first, so only a folder of
# its own is accepted: a name starting with '_' at the repo root (never scripts/, site_build/, .git)
STAGE="${STAGE:-_site}"
[[ "$STAGE" =~ ^_[A-Za-z0-9-]+$ ]] || { echo "FATAL: STAGE must be a folder of its own at the repo root, named _<name>; got '$STAGE'" >&2; exit 1; }
rm -rf "./${STAGE:?}"
mkdir -p "$STAGE/$ADMIN" "$STAGE/$DEV/media"
# the Media page is on the dev site only, so are its photos
if compgen -G 'site_media/*.jpg' >/dev/null; then cp site_media/*.jpg "$STAGE/$DEV/media/"; fi
# the open site: served as built, no password (the guard below checks each page is meant to be)
cp site_build/*.html "$STAGE"/
cp site_encrypted/$DEV/*.html "$STAGE/$DEV"/
cp site_encrypted/$ADMIN/*.html "$STAGE/$ADMIN"/
# the committed copies of the vendored assets (never a local edit not yet committed)
for a in chart.umd.js sankey.js; do                 # the open map loads sankey.js
  git show "HEAD:site_src/$a" > "$STAGE/$a"
done
for a in chart.umd.js sankey.js unocha.css; do      # unocha.css: the mock-up's
  git show "HEAD:site_src/$a" > "$STAGE/$DEV/$a"
done
for a in pdf.min.js pdf.worker.min.js; do          # the data-entry page only: admin site
  git show "HEAD:site_src/$a" > "$STAGE/$ADMIN/$a"
done
# per-country admin-boundary geometry for the map, open and dev (public CODAB data, not encrypted)
cp site_build/adm-*.json "$STAGE"/
cp site_build/adm-*.json "$STAGE/$DEV"/
# the open layer (unencrypted by design; the build already checked it for the proxy token)
for f in $(open_files site_build); do cp "site_build/$f" "$STAGE/$f"; done
touch "$STAGE/.nojekyll"
check_stage "$STAGE"
if [ -z "${GITHUB_ACTIONS:-}" ]; then
  echo "not deployed: the publish workflow deploys (gh workflow run publish.yml)"
fi
