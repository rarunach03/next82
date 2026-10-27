"""Collect raw player-season data from nba_api and save to data/raw.

Each dataset is saved as one parquet file per season:
    data/raw/<dataset>/<season>.parquet

Files that already exist are skipped, so the script can be rerun after a failure.

Usage:
    python -m next82.data                    # all seasons in config.SEASONS
    python -m next82.data --seasons 2024-25  # specific seasons
    python -m next82.data --force            # re-download existing files
    python -m next82.data --current          # refresh current rosters and games so far only
"""
import argparse
import threading
import time
from datetime import datetime, timedelta

import pandas as pd
from nba_api.stats.endpoints import (
    commonallplayers,
    drafthistory,
    scheduleleaguev2,
    leaguedashplayerbiostats,
    leaguedashplayerstats,
    leaguegamelog,
    playergamelogs,
)
from nba_api.stats.static import teams

from next82 import config

SEASON_TYPE = "Regular Season"
TIMEOUT = 60
MAX_RETRIES = 4


def _player_stats(season: str) -> pd.DataFrame:
    """Season totals per player: age, games played, minutes, box score stats."""
    return leaguedashplayerstats.LeagueDashPlayerStats(
        season=season,
        season_type_all_star=SEASON_TYPE,
        per_mode_detailed="Totals",
        timeout=TIMEOUT,
    ).get_data_frames()[0]


def _player_bio(season: str) -> pd.DataFrame:
    """Height, weight, draft year and country per player."""
    return leaguedashplayerbiostats.LeagueDashPlayerBioStats(
        season=season,
        season_type_all_star=SEASON_TYPE,
        timeout=TIMEOUT,
    ).get_data_frames()[0]


def _player_games(season: str) -> pd.DataFrame:
    """One row per player per game played. Used to find stretches of missed games."""
    return playergamelogs.PlayerGameLogs(
        season_nullable=season,
        season_type_nullable=SEASON_TYPE,
        timeout=TIMEOUT,
    ).get_data_frames()[0]


def _team_games(season: str) -> pd.DataFrame:
    """One row per team per game. Gives each team's full schedule."""
    return leaguegamelog.LeagueGameLog(
        season=season,
        season_type_all_star=SEASON_TYPE,
        player_or_team_abbreviation="T",
        timeout=TIMEOUT,
    ).get_data_frames()[0]


DATASETS = {
    "player_stats": _player_stats,
    "player_bio": _player_bio,
    "player_games": _player_games,
    "team_games": _team_games,
}


def raw_path(dataset: str, season: str):
    return config.RAW_DIR / dataset / f"{season}.parquet"


def fetch(dataset: str, season: str, force: bool = False) -> bool:
    """Download one dataset for one season. Returns True if a request was made."""
    path = raw_path(dataset, season)
    if path.exists() and not force:
        return False

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            df = DATASETS[dataset](season)
            break
        except Exception as e:
            if attempt == MAX_RETRIES:
                raise
            wait = 5 * attempt
            print(f"  {dataset} {season}: {type(e).__name__}, retrying in {wait}s")
            time.sleep(wait)

    df["SEASON"] = season
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    print(f"  {dataset} {season}: {len(df):,} rows")
    return True


def load(dataset: str, seasons: list[str] | None = None) -> pd.DataFrame:
    """Load a raw dataset across seasons into one DataFrame."""
    seasons = seasons or config.SEASONS
    paths = [raw_path(dataset, s) for s in seasons]
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing raw files, run `python -m next82.data`: {missing}")
    return pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)


def roster_path(season: str = config.FORECAST_SEASON):
    return config.RAW_DIR / "current_rosters" / f"{season}.parquet"


def fetch_current_rosters(season: str = config.FORECAST_SEASON) -> pd.DataFrame:
    """Every player currently on an NBA roster and their team, saved to data/raw."""
    df = commonallplayers.CommonAllPlayers(
        is_only_current_season=1, season=season, league_id="00", timeout=TIMEOUT
    ).get_data_frames()[0]
    df = df[df.TEAM_ID != 0]
    full_names = {t["id"]: t["full_name"] for t in teams.get_teams()}
    out = pd.DataFrame({
        "PLAYER_ID": df.PERSON_ID,
        "PLAYER_NAME": df.DISPLAY_FIRST_LAST,
        "TEAM_ID": df.TEAM_ID,
        "TEAM_ABBREVIATION": df.TEAM_ABBREVIATION,
        "TEAM_FULL_NAME": df.TEAM_ID.map(full_names),
        # First NBA season (e.g. 2026 for this season's rookies).
        "FROM_YEAR": pd.to_numeric(df.FROM_YEAR, errors="coerce"),
        "FETCHED_AT": pd.Timestamp.now(),
    })
    path = roster_path(season)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temporary file first so a reader never sees a half-written file.
    tmp = path.with_suffix(".tmp")
    out.to_parquet(tmp, index=False)
    tmp.replace(path)
    return out


def season_to_date_paths(season: str = config.FORECAST_SEASON):
    folder = config.RAW_DIR / "current_season"
    return folder / f"players_{season}.parquet", folder / f"teams_{season}.parquet"


def season_logs_paths(season: str = config.FORECAST_SEASON):
    """Game-by-game logs of the season so far: player games and finished team games."""
    folder = config.RAW_DIR / "current_season"
    return folder / f"player_games_{season}.parquet", folder / f"team_games_{season}.parquet"


def _write(df: pd.DataFrame, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


def schedule_path(season: str = config.FORECAST_SEASON):
    return config.RAW_DIR / "current_season" / f"schedule_{season}.parquet"


def fetch_schedule(season: str = config.FORECAST_SEASON) -> pd.DataFrame:
    """This season's regular-season schedule, one row per team per game (past and future).

    Games whose teams aren't decided yet (e.g. NBA Cup knockout games) have team ID 0
    and are left out, so teams can show fewer than 82 games until they're set.
    """
    g = scheduleleaguev2.ScheduleLeagueV2(season=season, league_id="00", timeout=TIMEOUT).get_data_frames()[0]
    g = g[g.gameId.astype(str).str.startswith("002")]
    date = pd.to_datetime(g.gameDateEst.astype(str).str[:10])
    rows = pd.concat([
        pd.DataFrame({"TEAM_ID": g.homeTeam_teamId, "GAME_ID": g.gameId, "GAME_DATE": date}),
        pd.DataFrame({"TEAM_ID": g.awayTeam_teamId, "GAME_ID": g.gameId, "GAME_DATE": date}),
    ])
    rows = rows[rows.TEAM_ID != 0].sort_values(["TEAM_ID", "GAME_DATE"]).reset_index(drop=True)
    _write(rows, schedule_path(season))
    return rows


def saved_schedule(season: str = config.FORECAST_SEASON) -> pd.DataFrame | None:
    path = schedule_path(season)
    return pd.read_parquet(path) if path.exists() else None


def draft_path(season: str = config.FORECAST_SEASON):
    return config.RAW_DIR / "current_season" / f"draft_{season}.parquet"


def fetch_draft(season: str = config.FORECAST_SEASON) -> pd.DataFrame:
    """This season's rookie draft order (the draft held before it)."""
    df = drafthistory.DraftHistory(season_year_nullable=season[:4], league_id="00", timeout=TIMEOUT).get_data_frames()[0]
    out = pd.DataFrame({"PLAYER_ID": df.PERSON_ID, "PLAYER_NAME": df.PLAYER_NAME, "OVERALL_PICK": df.OVERALL_PICK})
    _write(out, draft_path(season))
    return out


def saved_draft(season: str = config.FORECAST_SEASON) -> pd.DataFrame | None:
    path = draft_path(season)
    return pd.read_parquet(path) if path.exists() else None


def saved_season_logs(season: str = config.FORECAST_SEASON) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """Saved game logs of the season so far, without calling the API. None if never fetched."""
    paths = season_logs_paths(season)
    if not all(p.exists() for p in paths):
        return None
    return tuple(pd.read_parquet(p) for p in paths)


def fetch_season_to_date(season: str = config.FORECAST_SEASON) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Games played so far in the season being forecast: per player, and per team.

    The forecasts were made before the season and stay fixed; these numbers let the
    website show how each player is tracking against their forecast.
    """
    players = leaguedashplayerstats.LeagueDashPlayerStats(
        season=season, season_type_all_star=SEASON_TYPE, per_mode_detailed="Totals", timeout=TIMEOUT
    ).get_data_frames()[0]
    time.sleep(config.REQUEST_DELAY)
    team_games = leaguegamelog.LeagueGameLog(
        season=season, season_type_all_star=SEASON_TYPE, player_or_team_abbreviation="T", timeout=TIMEOUT
    ).get_data_frames()[0]

    # Count only finished games (with a result): the log also lists games in progress
    # today, which player totals don't include yet.
    team_games = team_games[team_games.WL.notna()]
    fetched_at = pd.Timestamp.now()
    players = pd.DataFrame({"PLAYER_ID": players.PLAYER_ID, "GP": players.GP, "FETCHED_AT": fetched_at})
    teams_so_far = (
        team_games.groupby(["TEAM_ID", "TEAM_ABBREVIATION"]).size().rename("GAMES").reset_index()
        .assign(LAST_GAME=team_games.GAME_DATE.max() if len(team_games) else None, FETCHED_AT=fetched_at)
    )
    for df, path in zip((players, teams_so_far), season_to_date_paths(season)):
        _write(df, path)

    # Game-by-game logs for the rest-of-season forecast (absence streaks, recent games).
    time.sleep(config.REQUEST_DELAY)
    player_games = playergamelogs.PlayerGameLogs(
        season_nullable=season, season_type_nullable=SEASON_TYPE, timeout=TIMEOUT
    ).get_data_frames()[0]
    box = ["MIN", "FGM", "FGA", "FG3M", "FTM", "FTA", "REB", "AST", "STL", "BLK", "TOV", "PTS"]
    player_cols = ["PLAYER_ID", "TEAM_ID", "GAME_ID", "GAME_DATE", *box]
    team_cols = ["TEAM_ID", "GAME_ID", "GAME_DATE"]
    player_logs = player_games[player_cols] if len(player_games) else pd.DataFrame(columns=player_cols)
    team_logs = team_games[team_cols] if len(team_games) else pd.DataFrame(columns=team_cols)
    for df, path in zip((player_logs, team_logs), season_logs_paths(season)):
        _write(df, path)
    return players, teams_so_far


def saved_season_to_date(season: str = config.FORECAST_SEASON) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """Saved games-so-far files, without calling the API. None if never fetched."""
    paths = season_to_date_paths(season)
    if not all(p.exists() for p in paths):
        return None
    return tuple(pd.read_parquet(p) for p in paths)


def saved_rosters(season: str = config.FORECAST_SEASON) -> pd.DataFrame | None:
    """The saved rosters, without calling the API. None if never fetched."""
    path = roster_path(season)
    return pd.read_parquet(path) if path.exists() else None


def rosters_are_stale(season: str = config.FORECAST_SEASON) -> bool:
    saved = saved_rosters(season)
    max_age = timedelta(hours=config.ROSTER_MAX_AGE_HOURS)
    return saved is None or datetime.now() - saved.FETCHED_AT.iloc[0] >= max_age


_refresh_lock = threading.Lock()


def refresh_rosters_in_background(season: str = config.FORECAST_SEASON) -> threading.Thread | None:
    """Start refreshing stale rosters in a background thread and return immediately.

    Used by the app so a slow or blocked nba_api never holds up a page load. Does
    nothing if the saved rosters are fresh or a refresh is already running. If the
    refresh fails, the saved copy stays in place.
    """
    if not rosters_are_stale(season) or not _refresh_lock.acquire(blocking=False):
        return None

    def run():
        try:
            fetch_current_rosters(season)
        except Exception:
            pass
        finally:
            _refresh_lock.release()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--seasons", nargs="+", default=config.SEASONS)
    parser.add_argument("--datasets", nargs="+", default=list(DATASETS), choices=list(DATASETS))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--current", "--rosters", action="store_true",
                        help="only refresh current rosters and games played so far")
    args = parser.parse_args()

    if args.current:
        refresh_current()
        return

    for season in args.seasons:
        print(season)
        for dataset in args.datasets:
            if fetch(dataset, season, force=args.force):
                time.sleep(config.REQUEST_DELAY)
    refresh_current()


def refresh_current(season: str = config.FORECAST_SEASON):
    """Refresh current rosters and games played so far in the season being forecast."""
    rosters = fetch_current_rosters(season)
    print(f"Current rosters ({season}): {len(rosters)} players on {rosters.TEAM_ID.nunique()} teams")
    time.sleep(config.REQUEST_DELAY)
    draft = fetch_draft(season)
    print(f"Draft {season[:4]}: {len(draft)} picks")
    time.sleep(config.REQUEST_DELAY)
    schedule = fetch_schedule(season)
    print(f"Schedule: {schedule.GAME_ID.nunique()} games with both teams set")
    time.sleep(config.REQUEST_DELAY)
    from next82 import injuries  # the NBA's official injury report (parsed facts only)

    injuries.refresh(rosters, season)
    time.sleep(config.REQUEST_DELAY)
    players, teams_so_far = fetch_season_to_date(season)
    if teams_so_far.empty:
        print(f"{season} hasn't started yet")
    else:
        print(f"{season} so far: {len(players)} players have played, through {teams_so_far.LAST_GAME.iloc[0]}")


if __name__ == "__main__":
    main()
