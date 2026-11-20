#!/bin/bash
# The Mac's half of the daily refresh. stats.nba.com doesn't answer cloud servers, so
# this downloads the NBA stats (current rosters, draft order, positions, schedule and this
# season's game logs: next82.data --current --stats-only), runs the injury-timeline news
# search when it's due (scripts/news_timelines.sh), and commits and pushes the raw files.
# That push starts the GitHub Actions workflow (.github/workflows/refresh.yml), which
# reads the injury report, rebuilds the site data and commits it; Vercel then redeploys.
# The cloud also runs on its own schedule, so injuries stay current while the Mac is off.
#
# Run by the launchd job com.next82.refresh every hour and at login (a missed hour runs
# on wake). It does the work once per "NBA day", which starts at 4 am Eastern so the
# night's late games are final, and exits early after that (recorded in
# .git/next82-last-refresh). Pass --force to fetch anyway.
#
# The news search runs every 3 days (sooner for a new serious injury); its schedule is
# kept in data/news_state.json, shared with the cloud. If it fails or times out, the
# stats still go out.
#
# Everything runs inside main(), which bash reads in full before running: `git pull`
# may replace this file while it runs.
set -Eeuo pipefail  # -E: the ERR trap also fires inside main()

COMMIT_MESSAGE="Refresh NBA stats"

# A failed run retries next hour; say so on screen too, not just in the log.
notify_failure() {
  osascript -e 'display notification "Will retry in an hour. Log: ~/Library/Logs/next82-refresh.log" with title "Next82 refresh failed"' 2>/dev/null || true
}

main() {
  cd "$(dirname "$0")/.."
  # The stats files and the news step's files; the injury report files belong to the cloud.
  # Declared, then assigned: macOS's bash 3.2 turns `local files=(...)` into a single string.
  local -a files
  files=(data/raw/current_rosters data/raw/current_season/draft_*.parquet
         data/raw/current_season/player_games_*.parquet data/raw/current_season/players_*.parquet
         data/raw/current_season/positions_*.parquet data/raw/current_season/schedule_*.parquet
         data/raw/current_season/team_games_*.parquet data/raw/current_season/teams_*.parquet
         data/news_timelines.csv data/news_rejected.csv data/overrides.csv data/news_state.json)
  local nba_day marker
  # The NBA day: before 4 am Eastern still counts as the day before.
  nba_day=${REFRESH_TODAY:-$(TZ=America/New_York date -v-4H +%Y-%m-%d)}  # override for testing
  marker=.git/next82-last-refresh
  echo "== $(date) =="
  if [[ "${1:-}" != "--force" && -f "$marker" && "$(cat "$marker")" == "$nba_day" ]]; then
    echo "Already fetched for $nba_day; nothing to do"
    return
  fi
  git pull --rebase --quiet

  ./.venv/bin/python -m next82.data --current --stats-only
  ./scripts/news_timelines.sh || echo "News step failed; continuing the refresh"

  git add -- "${files[@]}"
  if git diff --cached --quiet; then
    echo "No changes"
  else
    git commit --quiet -m "$COMMIT_MESSAGE"
    # The cloud may have pushed meanwhile. It writes the site data and injury files, not
    # these (except the news files, if the news search also runs there), so this rebases cleanly.
    for attempt in 1 2 3; do
      git pull --rebase --quiet && git push --quiet && break
      [[ $attempt == 3 ]] && { echo "Push failed"; exit 1; }
      sleep 30
    done
    echo "Pushed: $COMMIT_MESSAGE"
  fi
  echo "$nba_day" > "$marker"
}

trap notify_failure ERR
main "$@"
exit
