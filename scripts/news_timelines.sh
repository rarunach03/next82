#!/bin/bash
# News search for injury timelines (next82.news): runs every 3 days, or sooner when a
# new player is listed Out with a serious injury; --force runs it anyway. Claude Code
# runs non-interactively in a sandbox folder with web search, web fetch and the news
# file only; its rows are validated in Python before they reach data/news_timelines.csv.
# Called by refresh.sh on the Mac, or by the refresh workflow in GitHub Actions when the
# CLAUDE_CODE_OAUTH_TOKEN secret is set; the caller commits. Set PYTHON to use another Python.
# Uses the standalone Claude Code CLI (~/.local/bin/claude) if installed, else the copy
# bundled with the VS Code extension; set NEXT82_CLAUDE to use another.
# The Python step has its own timeout; this one is a backstop.
set -uo pipefail
cd "$(dirname "$0")/.."
"${PYTHON:-./.venv/bin/python}" -m next82.news "$@" &
pid=$!
# The watchdog's sleep is killed with it, so nothing is left holding the output open
# (a leftover sleep made anything reading this script's output wait 30 minutes).
(
  trap 'kill "$nap" 2>/dev/null; exit 0' TERM
  sleep 1800 >/dev/null 2>&1 &
  nap=$!
  wait "$nap"
  kill "$pid" 2>/dev/null && echo "News search: killed after 30 minutes"
) &
watchdog=$!
wait "$pid"
status=$?
kill "$watchdog" 2>/dev/null
exit $status
