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
# Pass --force to refresh anyway. If data/news_timelines.csv or data/overrides.csv changed
# since the last refresh (edited by hand and pulled, or by the news step), it re-exports
# and pushes even on a day it already refreshed.
#
# Every 3 days (sooner for a new serious injury) the news step (scripts/news_timelines.sh)
# searches for team timelines after the injury report is read. If it fails or times out,
# the rest of the refresh still runs.
#
# Everything runs inside main(), which bash reads in full before running: `git pull`
# may replace this file while it runs.
set -euo pipefail

COMMIT_MESSAGE="Refresh rosters and games so far"
TIMELINES_MESSAGE="Update injury timelines"
TIMELINE_FILES=(data/news_timelines.csv data/overrides.csv)

timelines_hash() { cat "${TIMELINE_FILES[@]}" 2>/dev/null | shasum | cut -d' ' -f1; }

commit_and_push() {
  git add data/raw/current_rosters data/raw/current_season web/public/data "${TIMELINE_FILES[@]}"
  if git diff --cached --quiet; then
    echo "No changes"
  else
    git commit --quiet -m "$1"
    git pull --rebase --quiet
    git push --quiet
    echo "Pushed: $1"
  fi
}

main() {
  cd "$(dirname "$0")/.."
  local today marker last_refresh_commit hash_marker
  today=${REFRESH_TODAY:-$(date +%Y-%m-%d)}  # override for testing
  marker=.git/next82-last-refresh
  hash_marker=.git/next82-timelines-hash
  echo "== $(date) =="
  git pull --rebase --quiet

  if [[ "${1:-}" != "--force" ]]; then
    last_refresh_commit=$(git log -1 --format=%cd --date=format:%Y-%m-%d --grep="^${COMMIT_MESSAGE}\$" || true)
    if [[ "$last_refresh_commit" == "$today" || ( -f "$marker" && "$(cat "$marker")" == "$today" ) ]]; then
      if [[ -f "$hash_marker" && "$(cat "$hash_marker")" != "$(timelines_hash)" ]]; then
        echo "Timelines or overrides changed since the last refresh; re-exporting"
        ./.venv/bin/python -m next82.export
        commit_and_push "$TIMELINES_MESSAGE"
        timelines_hash > "$hash_marker"
      else
        echo "Already refreshed today; nothing to do"
      fi
      return
    fi
  fi

  ./.venv/bin/python -m next82.data --current
  ./scripts/news_timelines.sh || echo "News step failed; continuing the refresh"
  ./.venv/bin/python -m next82.export
  commit_and_push "$COMMIT_MESSAGE"
  timelines_hash > "$hash_marker"
  echo "$today" > "$marker"
}

main "$@"
exit
