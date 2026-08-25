#!/usr/bin/env bash
# Publish the review site: rebuild → encrypt → gh-pages (top-level files ONLY).
#
# Hard-won rules encoded here (two incidents):
# - never `git add -A` on gh-pages (no .gitignore there — sweeps in the
#   UNENCRYPTED site_build/, scripts/, .venv/…)
# - git pathspecs like '*.html' match RECURSIVELY — stage via a loop over
#   top-level files with a literal ./ prefix
# - assert zero staged paths containing '/' before committing, and zero
#   directories in the pushed tree after
set -euo pipefail
cd "$(dirname "$0")/.."
PW="${SITE_PASSWORD:-anticipation2026}"

uv run python scripts/build_site.py
npx -y staticrypt site_build/*.html -d site_encrypted -p "$PW" --short --remember 30 \
  --template-title "AA tracking review" \
  --template-instructions "Internal review site. Ask Tristan for the password."

git checkout -B gh-pages origin/gh-pages
cp site_encrypted/*.html .
git show main:site_src/chart.umd.js > chart.umd.js
touch .nojekyll
for f in *.html chart.umd.js .nojekyll; do git add -f "./$f"; done

if git diff --cached --name-only | grep -q "/"; then
  echo "FATAL: staged a nested path — aborting" >&2
  git status --short | head; exit 1
fi
if git diff --cached --quiet; then
  echo "nothing changed — not publishing"
else
  git commit -m "Publish review site $(date +%F)"
  git push origin gh-pages
fi
git checkout -f main
N_DIRS=$(git ls-tree -d origin/gh-pages --name-only | wc -l | tr -d ' ')
[ "$N_DIRS" = "0" ] || { echo "FATAL: gh-pages tree contains directories!" >&2; exit 1; }
echo "published ✓ (tree clean)"
