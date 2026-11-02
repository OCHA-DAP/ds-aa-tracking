#!/usr/bin/env bash
# Publish the three sites: rebuild → encrypt → gh-pages.
#   open site    top-level *.html  NO password: the map, and a "Coming soon" page in place of
#                                  every other public page (owner, 2026-11-01)
#   dev site     dev/*.html        password SITE_PASSWORD: every public page
#   admin site   admin/*.html      password ADMIN_PASSWORD (no default: it must be set)
# site_build/ is laid out the same way (scripts/build_site.py, write_site). The public pages
# never link to the admin site; the admin site links to the dev site.
# SKIP_BUILD=1 reuses the existing site_build/ + site_encrypted/ output.
# DRY_RUN=1 stages and checks everything, then stops before the commit and the push.
#
# Hard-won rules encoded here (two incidents):
# - never `git add -A` on gh-pages (no .gitignore there — sweeps in the
#   UNENCRYPTED site_build/, scripts/, .venv/…)
# - git pathspecs like '*.html' match RECURSIVELY — stage via a loop over
#   named files with a literal ./ prefix
# - the only directories on gh-pages are admin/, which holds only encrypted pages and the two
#   pdf.js files of the data-entry page, dev/, which holds only encrypted pages, the map's
#   geometry and the vendored scripts and styles, and dev/media/, which holds only the Media
#   page's photo renditions (<key>-w<width>.jpg, scripts/sync_media.py): any other nested path
#   aborts before committing, and any other directory in the pushed tree is fatal
# - every page under dev/ and admin/ is a staticrypt page, and a top-level page is served plain
#   only if the build marked it for the open site (OPEN_META); a "Coming soon" page that is
#   not one, or is the size of a real page, aborts before committing
# The mock-up of the site on unocha.org (scripts/mock_unocha.py: mock-unocha*.html, unlisted) is
# made from the dev pages and published with them, under the site password.
set -euo pipefail
cd "$(dirname "$0")/.."
PW="${SITE_PASSWORD:-anticipation2026}"
ADMIN_PW="${ADMIN_PASSWORD:-}"
ADMIN=admin
DEV=dev
[ -n "$ADMIN_PW" ] || { echo "FATAL: ADMIN_PASSWORD is not set (the admin site has no default password)" >&2; exit 1; }
[ "$ADMIN_PW" != "$PW" ] || { echo "FATAL: the admin password must differ from the public one" >&2; exit 1; }

if [ -z "${SKIP_BUILD:-}" ]; then
  uv run python scripts/build_site.py
  # the mock-up never stops the site: if it fails, none of its pages goes out (a half-written
  # set would link to twins that are not there)
  uv run python scripts/mock_unocha.py site_build/$DEV \
    || { rm -f site_build/$DEV/mock-*.html; echo "::warning::mock-up (scripts/mock_unocha.py) failed: not published"; }
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

# gh-pages lives in its own worktree so publishing never switches branches in the
# main tree (uncommitted work there — possibly another session's — stays untouched)
git fetch -q origin gh-pages
WT="$(mktemp -d)/gh-pages"
git worktree prune
git worktree add -q -B gh-pages "$WT" origin/gh-pages
trap 'git worktree remove --force "$WT" 2>/dev/null || true' EXIT

# the published tree is exactly this build: a page dropped from the build, or moved to the
# admin site, must not linger at its old address
rm -f "$WT"/*.html "$WT"/adm-*.json "$WT"/pdf.min.js "$WT"/pdf.worker.min.js "$WT"/chart.umd.js \
      "$WT"/sankey.js "$WT"/unocha.css
rm -rf "${WT:?}/$ADMIN" "${WT:?}/$DEV" "${WT:?}/media"
mkdir "$WT/$ADMIN" "$WT/$DEV" "$WT/$DEV/media"
# the Media page is on the dev site only, so are its photos
if compgen -G 'site_media/*.jpg' >/dev/null; then cp site_media/*.jpg "$WT/$DEV/media/"; fi
# the open site: served as built, no password (the guard below checks each page is meant to be)
cp site_build/*.html "$WT"/
cp site_encrypted/$DEV/*.html "$WT/$DEV"/
cp site_encrypted/$ADMIN/*.html "$WT/$ADMIN"/
# committed copies of the vendored assets (main locally; the checked-out ref in CI)
REF=main; git rev-parse -q --verify main >/dev/null 2>&1 || REF=HEAD
for a in chart.umd.js sankey.js; do                 # the open map loads sankey.js
  git show "$REF:site_src/$a" > "$WT/$a"
done
for a in chart.umd.js sankey.js unocha.css; do      # unocha.css: the mock-up's
  git show "$REF:site_src/$a" > "$WT/$DEV/$a"
done
for a in pdf.min.js pdf.worker.min.js; do          # the data-entry page only: admin site
  git show "$REF:site_src/$a" > "$WT/$ADMIN/$a"
done
# per-country admin-boundary geometry for the map, open and dev (public CODAB data, not encrypted)
cp site_build/adm-*.json "$WT"/
cp site_build/adm-*.json "$WT/$DEV"/
touch "$WT/.nojekyll"
(
  cd "$WT"
  git add -u .                   # tracked files only: what changed and what went away
  for f in *.html adm-*.json chart.umd.js sankey.js .nojekyll; do git add -f "./$f"; done
  for f in $DEV/*.html $DEV/adm-*.json $DEV/chart.umd.js $DEV/sankey.js $DEV/unocha.css; do git add -f "./$f"; done
  for f in $ADMIN/*.html $ADMIN/pdf.min.js $ADMIN/pdf.worker.min.js; do git add -f "./$f"; done
  if [ -n "$(ls -A $DEV/media)" ]; then git add -f ./$DEV/media; fi
  # the tree about to be committed (not just what changed)
  BAD=$(git ls-files | grep "/" | grep -v -E "^$ADMIN/([A-Za-z0-9_.-]+\.html|pdf\.min\.js|pdf\.worker\.min\.js)$" \
        | grep -v -E "^$DEV/([A-Za-z0-9_.-]+\.html|adm-[A-Z]{3}\.json|chart\.umd\.js|sankey\.js|unocha\.css)$" \
        | grep -v -E "^$DEV/media/[0-9a-f]{16}-w[0-9]+\.jpg$" || true)
  if [ -n "$BAD" ]; then
    echo "FATAL: nested path outside $ADMIN/, $DEV/ and $DEV/media/ — aborting" >&2
    echo "$BAD" | head >&2; exit 1
  fi
  git ls-files | grep -E '\.html$' | while read -r f; do
    case "$f" in
      */*)    # dev/ and admin/: encrypted, nothing readable
        if ! grep -q "staticrypt-form" "$f" || grep -q "devbanner" "$f"; then
          echo "FATAL: $f is not an encrypted page — aborting" >&2; exit 1
        fi ;;
      *)      # the open site: only what the build marked for it, and apart from the map only
              # "Coming soon" pages (class='soon' is written by build_site._soon_body alone; the
              # size cap only catches the map's data or a long page, not a short real page)
        if ! grep -q '<meta name="aa-site" content="open">' "$f"; then
          echo "FATAL: $f is served without a password but the build did not mark it for the open site — aborting" >&2; exit 1
        fi
        if [ "$f" != index.html ] && { ! grep -q "class='soon'" "$f" || [ "$(wc -c < "$f")" -gt 250000 ]; }; then
          echo "FATAL: $f is served without a password but is not a 'Coming soon' page — aborting" >&2; exit 1
        fi ;;
    esac
  done
  [ -f "$ADMIN/index.html" ] || { echo "FATAL: the admin site has no index.html — aborting" >&2; exit 1; }
  [ -f "$DEV/index.html" ] || { echo "FATAL: the dev site has no index.html — aborting" >&2; exit 1; }
  if git diff --cached --quiet; then
    echo "nothing changed — not publishing"
  elif [ -n "${DRY_RUN:-}" ]; then
    echo "DRY_RUN: would publish $(git ls-files | grep -c -v "/") top-level files, $(git ls-files "$DEV" | grep -c -v "^$DEV/media/") under $DEV/, $(git ls-files "$DEV/media" | wc -l | tr -d ' ') under $DEV/media/ and $(git ls-files "$ADMIN" | wc -l | tr -d ' ') under $ADMIN/"
    git diff --cached --stat | tail -1
  else
    git commit -q -m "Publish review site $(date +%F)"
    git push -q origin gh-pages
  fi
)
if [ -z "${DRY_RUN:-}" ]; then
  DIRS=$(git ls-tree -d -r origin/gh-pages --name-only | tr '\n' ' ')
  [ "$DIRS" = "$ADMIN $DEV " ] || [ "$DIRS" = "$ADMIN $DEV $DEV/media " ] \
    || { echo "FATAL: gh-pages tree contains directories other than $ADMIN/, $DEV/ and $DEV/media/: $DIRS" >&2; exit 1; }
  echo "published ✓ (tree clean)"
fi
