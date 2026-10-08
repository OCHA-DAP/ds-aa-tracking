#!/usr/bin/env bash
# Publish the two sites: rebuild → encrypt → gh-pages.
#   public site  top-level *.html           password SITE_PASSWORD
#   admin site   admin/*.html               password ADMIN_PASSWORD (no default: it must be set)
# The public site never links to the admin site (scripts/build_site.py, write_site).
# SKIP_BUILD=1 reuses the existing site_build/ + site_encrypted/ output.
# DRY_RUN=1 stages and checks everything, then stops before the commit and the push.
#
# Hard-won rules encoded here (two incidents):
# - never `git add -A` on gh-pages (no .gitignore there — sweeps in the
#   UNENCRYPTED site_build/, scripts/, .venv/…)
# - git pathspecs like '*.html' match RECURSIVELY — stage via a loop over
#   named files with a literal ./ prefix
# - the only directory on gh-pages is admin/, and it holds only encrypted pages and the two
#   pdf.js files of the data-entry page: any other nested path aborts before committing, and
#   any other directory in the pushed tree is fatal
# - every page published is a staticrypt page: one that is not aborts before committing
# - the OPEN LAYER (scripts/llm_layer.py) is published unencrypted on purpose: llms.txt,
#   llms-full.txt, robots.txt, sitemap.xml, *.md (framework pages, document reads), pdf-*.txt
#   (document texts) and aa-*.json / aa-*.csv (the tables) at the top level, for fetch-based
#   tools and LLMs. Never a page, never anything from admin/.
set -euo pipefail
OPEN_GLOBS='*.md aa-*.json aa-*.csv pdf-*.txt llms.txt llms-full.txt robots.txt sitemap.xml'
open_files() { ( cd "$1" && shopt -s nullglob && for g in $OPEN_GLOBS; do for f in $g; do echo "$f"; done; done ); }
cd "$(dirname "$0")/.."
PW="${SITE_PASSWORD:-anticipation2026}"
ADMIN_PW="${ADMIN_PASSWORD:-}"
ADMIN=admin
[ -n "$ADMIN_PW" ] || { echo "FATAL: ADMIN_PASSWORD is not set (the admin site has no default password)" >&2; exit 1; }
[ "$ADMIN_PW" != "$PW" ] || { echo "FATAL: the admin password must differ from the public one" >&2; exit 1; }

if [ -z "${SKIP_BUILD:-}" ]; then
  uv run python scripts/build_site.py
  rm -rf site_encrypted          # nothing from an earlier build may be published by accident
  npx -y staticrypt site_build/*.html -d site_encrypted -p "$PW" --short --remember 30 \
    --template-title "AA tracking review" \
    --template-instructions "Internal review site. Ask Tristan for the password."
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

# gh-pages lives in its own worktree so publishing never switches branches in the
# main tree (uncommitted work there — possibly another session's — stays untouched)
git fetch -q origin gh-pages
WT="$(mktemp -d)/gh-pages"
git worktree prune
git worktree add -q -B gh-pages "$WT" origin/gh-pages
trap 'git worktree remove --force "$WT" 2>/dev/null || true' EXIT

# the published tree is exactly this build: a page dropped from the build, or moved to the
# admin site, must not linger at its old address
rm -f "$WT"/*.html "$WT"/adm-*.json "$WT"/pdf.min.js "$WT"/pdf.worker.min.js
for f in $(open_files "$WT"); do rm -f "$WT/$f"; done
rm -rf "${WT:?}/$ADMIN"
mkdir "$WT/$ADMIN"
cp site_encrypted/*.html "$WT"/
cp site_encrypted/$ADMIN/*.html "$WT/$ADMIN"/
# committed copies of the vendored assets (main locally; the checked-out ref in CI)
REF=main; git rev-parse -q --verify main >/dev/null 2>&1 || REF=HEAD
for a in chart.umd.js sankey.js; do
  git show "$REF:site_src/$a" > "$WT/$a"
done
for a in pdf.min.js pdf.worker.min.js; do          # the data-entry page only: admin site
  git show "$REF:site_src/$a" > "$WT/$ADMIN/$a"
done
# per-country admin-boundary geometry for the landing map (public CODAB data, not encrypted)
cp site_build/adm-*.json "$WT"/
# the open layer (unencrypted by design; the build already checked it for the proxy token)
for f in $(open_files site_build); do cp "site_build/$f" "$WT/$f"; done
touch "$WT/.nojekyll"
(
  cd "$WT"
  git add -u .                   # tracked files only: what changed and what went away
  for f in *.html adm-*.json chart.umd.js sankey.js .nojekyll; do git add -f "./$f"; done
  for f in $(open_files .); do git add -f "./$f"; done
  for f in $ADMIN/*.html $ADMIN/pdf.min.js $ADMIN/pdf.worker.min.js; do git add -f "./$f"; done
  # the tree about to be committed (not just what changed)
  BAD=$(git ls-files | grep "/" | grep -v -E "^$ADMIN/([A-Za-z0-9_.-]+\.html|pdf\.min\.js|pdf\.worker\.min\.js)$" || true)
  if [ -n "$BAD" ]; then
    echo "FATAL: nested path outside $ADMIN/*.html — aborting" >&2
    echo "$BAD" | head >&2; exit 1
  fi
  git ls-files | grep -E '\.html$' | while read -r f; do
    if ! grep -q "staticrypt-form" "$f" || grep -q "devbanner" "$f"; then
      echo "FATAL: $f is not an encrypted page — aborting" >&2; exit 1
    fi
  done
  [ -f "$ADMIN/index.html" ] || { echo "FATAL: the admin site has no index.html — aborting" >&2; exit 1; }
  # the open files are plain data: never a token, never a page
  for f in $(open_files .); do
    if grep -q "x-site-token\|staticrypt" "$f"; then
      echo "FATAL: open file $f carries a token or a page — aborting" >&2; exit 1
    fi
  done
  [ -f llms.txt ] || { echo "FATAL: the open layer is missing (no llms.txt) — aborting" >&2; exit 1; }
  if git diff --cached --quiet; then
    echo "nothing changed — not publishing"
  elif [ -n "${DRY_RUN:-}" ]; then
    echo "DRY_RUN: would publish $(git ls-files | grep -c -v "/") top-level files ($(open_files . | wc -l | tr -d ' ') open) and $(git ls-files "$ADMIN" | wc -l | tr -d ' ') under $ADMIN/"
    git diff --cached --stat | tail -1
  else
    git commit -q -m "Publish review site $(date +%F)"
    git push -q origin gh-pages
  fi
)
if [ -z "${DRY_RUN:-}" ]; then
  DIRS=$(git ls-tree -d -r origin/gh-pages --name-only | tr '\n' ' ')
  [ "$DIRS" = "$ADMIN " ] || { echo "FATAL: gh-pages tree contains directories other than $ADMIN/: $DIRS" >&2; exit 1; }
  echo "published ✓ (tree clean)"
fi
