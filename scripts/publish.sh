#!/usr/bin/env bash
# Publish the review site: rebuild → encrypt → gh-pages (top-level files ONLY).
# SKIP_BUILD=1 reuses the existing site_build/ + site_encrypted/ output.
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

if [ -z "${SKIP_BUILD:-}" ]; then
  uv run python scripts/build_site.py
  npx -y staticrypt site_build/*.html -d site_encrypted -p "$PW" --short --remember 30 \
    --template-title "AA tracking review" \
    --template-instructions "Internal review site. Ask Tristan for the password."
fi

# gh-pages lives in its own worktree so publishing never switches branches in the
# main tree (uncommitted work there — possibly another session's — stays untouched)
git fetch -q origin gh-pages
WT="$(mktemp -d)/gh-pages"
git worktree prune
git worktree add -q -B gh-pages "$WT" origin/gh-pages
trap 'git worktree remove --force "$WT" 2>/dev/null || true' EXIT

cp site_encrypted/*.html "$WT"/
for a in chart.umd.js pdf.min.js pdf.worker.min.js; do
  git show "main:site_src/$a" > "$WT/$a"
done
# per-country admin geometry for the landing map (public CODAB data, not encrypted)
rm -f "$WT"/adm-*.json
cp site_build/adm-*.json "$WT"/
touch "$WT/.nojekyll"
(
  cd "$WT"
  for f in *.html adm-*.json chart.umd.js pdf.min.js pdf.worker.min.js .nojekyll; do git add -f "./$f"; done
  if git diff --cached --name-only | grep -q "/"; then
    echo "FATAL: staged a nested path — aborting" >&2
    git status --short | head; exit 1
  fi
  if git diff --cached --quiet; then
    echo "nothing changed — not publishing"
  else
    git commit -q -m "Publish review site $(date +%F)"
    git push -q origin gh-pages
  fi
)
N_DIRS=$(git ls-tree -d origin/gh-pages --name-only | wc -l | tr -d ' ')
[ "$N_DIRS" = "0" ] || { echo "FATAL: gh-pages tree contains directories!" >&2; exit 1; }
echo "published ✓ (tree clean)"
