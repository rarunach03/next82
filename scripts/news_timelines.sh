#!/bin/bash
# News search for injury timelines (next82.news): runs every 3 days, or sooner when a
# new player is listed Out with a serious injury; --force runs it anyway. Claude Code
# runs non-interactively in a sandbox folder with web search, web fetch and the news
# file only; its rows are validated in Python before they reach data/news_timelines.csv.
# Called by refresh.sh after the injury report step; refresh.sh commits.
# The Python step has its own timeout; this one is a backstop.
set -uo pipefail
cd "$(dirname "$0")/.."
./.venv/bin/python -m next82.news "$@" &
pid=$!
( sleep 1800; kill "$pid" 2>/dev/null && echo "News search: killed after 30 minutes" ) &
watchdog=$!
wait "$pid"
status=$?
kill "$watchdog" 2>/dev/null
exit $status
