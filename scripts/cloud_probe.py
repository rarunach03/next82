"""Can this machine reach every data source the daily refresh uses?

Calls each source once with a short timeout and prints OK or FAIL with the reason:
the NBA stats API endpoints (nba_api), the NBA's injury report PDF, and the hosts the
news step needs (Anthropic's API for Claude Code; web search runs on Anthropic's side).
Exits 0 either way: it's a report, not a check. Used by .github/workflows/cloud-probe.yml.

    python scripts/cloud_probe.py
"""
import time
import traceback

import requests
from nba_api.stats.endpoints import (
    commonallplayers,
    drafthistory,
    leaguedashplayerstats,
    leaguegamelog,
    playergamelogs,
    playerindex,
    scheduleleaguev2,
)

from next82 import config, injuries

SEASON = config.FORECAST_SEASON
TIMEOUT = 30
results = []


def probe(name, call):
    start = time.time()
    try:
        detail = call()
        results.append((name, "OK", f"{time.time() - start:.1f}s", detail))
    except Exception as e:  # noqa: BLE001 - report any failure
        results.append((name, "FAIL", f"{time.time() - start:.1f}s", f"{type(e).__name__}: {str(e)[:150]}"))
        traceback.print_exc(limit=1)


def rows(endpoint):
    return f"{len(endpoint.get_data_frames()[0])} rows"


def http(url, **kw):
    def call():
        r = requests.get(url, timeout=TIMEOUT, **kw)
        return f"HTTP {r.status_code}, {len(r.content)} bytes"
    return call


probe("stats: CommonAllPlayers (rosters)", lambda: rows(commonallplayers.CommonAllPlayers(
    is_only_current_season=1, season=SEASON, league_id="00", timeout=TIMEOUT)))
probe("stats: DraftHistory", lambda: rows(drafthistory.DraftHistory(
    season_year_nullable=SEASON[:4], league_id="00", timeout=TIMEOUT)))
probe("stats: PlayerIndex (positions)", lambda: rows(playerindex.PlayerIndex(season=SEASON, league_id="00", timeout=TIMEOUT)))
probe("stats: ScheduleLeagueV2", lambda: rows(scheduleleaguev2.ScheduleLeagueV2(season=SEASON, league_id="00", timeout=TIMEOUT)))
probe("stats: LeagueDashPlayerStats", lambda: rows(leaguedashplayerstats.LeagueDashPlayerStats(
    season=SEASON, season_type_all_star="Regular Season", per_mode_detailed="Totals", timeout=TIMEOUT)))
probe("stats: LeagueGameLog", lambda: rows(leaguegamelog.LeagueGameLog(
    season=SEASON, season_type_all_star="Regular Season", player_or_team_abbreviation="T", timeout=TIMEOUT)))
probe("stats: PlayerGameLogs", lambda: rows(playergamelogs.PlayerGameLogs(
    season_nullable=SEASON, season_type_nullable="Regular Season", timeout=TIMEOUT)))


def injury_report():
    found = injuries.fetch_latest(tries=12, delay=0.2)
    if found is None:
        raise RuntimeError("no report found in the last 3 hours")
    return f"{found[0].rsplit('/', 1)[-1]}, {len(found[2])} bytes"


probe("injury report PDF (ak-static.cms.nba.com)", injury_report)
probe("cdn.nba.com schedule JSON", http("https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"))
probe("api.anthropic.com (Claude Code)", http("https://api.anthropic.com/"))
probe("www.espn.com (news source)", http("https://www.espn.com/nba/injuries", headers={"User-Agent": injuries.USER_AGENT}))

print()
for name, status, took, detail in results:
    print(f"{status:4}  {took:>6}  {name}: {detail}")
