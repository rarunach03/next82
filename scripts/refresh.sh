#!/bin/bash
# Daily refresh. Downloads current rosters, this season's game logs and the draft
# order (next82.data --current), then rebuilds everything the site shows from them
# (next82.export): updated forecasts and their ranges, availability tiers, fantasy
# values including rookies, and the accuracy page. The preseason forecast stays frozen.
# Commits and pushes only if something changed; GitHub Actions then redeploys the site.
# Runs on a home computer because stats.nba.com doesn't respond to cloud servers.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== $(date) =="
git pull --rebase --quiet

./.venv/bin/python -m next82.data --current
./.venv/bin/python -m next82.export

git add data/raw/current_rosters data/raw/current_season web/public/data
if git diff --cached --quiet; then
  echo "No changes"
else
  git commit -m "Refresh rosters and games so far"
  git pull --rebase --quiet
  git push --quiet
  echo "Pushed refreshed data"
fi
