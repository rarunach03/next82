#!/bin/bash
# Daily refresh. Downloads current rosters, this season's game logs and the draft
# order (next82.data --current), then rebuilds everything the site shows from them
# (next82.export): updated forecasts and their ranges, availability tiers, fantasy
# values including rookies, and the accuracy page. The preseason forecast stays frozen.
# Commits and pushes only if something changed; GitHub Actions then redeploys the site.
# Runs on a home computer because stats.nba.com doesn't respond to cloud servers.
#
# Safe to run as often as you like (the launchd job runs it hourly, so it catches up
# whenever the Mac is awake): it does the work once a day and exits early after that,
# either because today's refresh commit is already on GitHub, or because it already
# ran today and found nothing new (recorded in .git/next82-last-refresh).
# Pass --force to refresh anyway.
#
# Everything runs inside main(), which bash reads in full before running: `git pull`
# may replace this file while it runs.
set -euo pipefail

COMMIT_MESSAGE="Refresh rosters and games so far"

main() {
  cd "$(dirname "$0")/.."
  local today marker last_refresh_commit
  today=${REFRESH_TODAY:-$(date +%Y-%m-%d)}  # override for testing
  marker=.git/next82-last-refresh
  echo "== $(date) =="
  git pull --rebase --quiet

  if [[ "${1:-}" != "--force" ]]; then
    last_refresh_commit=$(git log -1 --format=%cd --date=format:%Y-%m-%d --grep="^${COMMIT_MESSAGE}\$" || true)
    if [[ "$last_refresh_commit" == "$today" ]]; then
      echo "Already refreshed today (commit on GitHub); nothing to do"
      return
    fi
    if [[ -f "$marker" && "$(cat "$marker")" == "$today" ]]; then
      echo "Already refreshed today (no changes then); nothing to do"
      return
    fi
  fi

  ./.venv/bin/python -m next82.data --current
  ./.venv/bin/python -m next82.export

  git add data/raw/current_rosters data/raw/current_season web/public/data
  if git diff --cached --quiet; then
    echo "No changes"
  else
    git commit --quiet -m "$COMMIT_MESSAGE"
    git pull --rebase --quiet
    git push --quiet
    echo "Pushed refreshed data"
  fi
  echo "$today" > "$marker"
}

main "$@"
exit
