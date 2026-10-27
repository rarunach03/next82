"""NBA injury reports, for injury features in the in-season (rest-of-season) model.

For each snapshot date we use only reports published before it (the 5 PM report of
the three days before, and of days 8-10 before for the trend). Reports only list
teams that are about to play, so a player's status is his team's latest listing in
that window. Each report is downloaded once and only its parsed facts are cached
(data/raw/injury_history/<date>.parquet; an empty file marks a day with no report),
so nothing is ever downloaded twice and no PDF is stored.

Usage:
    python -m next82.injury_history     # download and cache what the snapshots need
"""
import time

import numpy as np
import pandas as pd
from nba_api.stats.static import teams as nba_teams

from next82 import config, data, injuries
from next82.auto_overrides import load_recovery

CACHE_DIR = config.RAW_DIR / "injury_history"
FIRST_SEASON = "2019-20"
RECENT_DAYS = (1, 2, 3)        # current status: latest listing in the 3 days before
WEEK_AGO_DAYS = (8, 9, 10)     # trend: latest listing about a week earlier
STATUS_LEVEL = {"Out": 4, "Doubtful": 3, "Questionable": 2, "Probable": 1, "Available": 0}
INJURY_FEATURES = ["listed_out", "listed_level", "serious_injury", "out_week_ago", "status_trend", "days_listed"]
DELAY = 1.0


def _season_players(season: str) -> pd.DataFrame:
    """That season's players with team full names, for matching report names."""
    stats = data.load("player_stats", [season])[["PLAYER_ID", "PLAYER_NAME", "TEAM_ID"]]
    names = {t["id"]: t["full_name"] for t in nba_teams.get_teams()}
    return stats.assign(TEAM_FULL_NAME=stats.TEAM_ID.map(names))


def cached_day(day: pd.Timestamp, season: str, players: pd.DataFrame | None = None) -> pd.DataFrame:
    """Parsed facts of the 5 PM report for `day`: from the cache, else downloaded once."""
    path = CACHE_DIR / f"{day:%Y-%m-%d}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    url = injuries.legacy_report_url(day)
    pdf = injuries.get(url)
    time.sleep(DELAY)
    if pdf is None:
        url = injuries.report_url(pd.Timestamp(day).replace(hour=17).to_pydatetime())
        pdf = injuries.get(url)
        time.sleep(DELAY)
    path.parent.mkdir(parents=True, exist_ok=True)
    if pdf is None:
        pd.DataFrame(columns=["PLAYER_ID", "team", "status", "injury_type", "report_day"]).to_parquet(path, index=False)
        return pd.read_parquet(path)
    players = players if players is not None else _season_players(season)
    facts, _ = injuries.parsed_report(pdf, url, pd.Timestamp(day).replace(hour=17), players)
    facts = facts.assign(report_day=pd.Timestamp(day))[["PLAYER_ID", "team", "status", "injury_type", "report_day"]]
    facts.to_parquet(path, index=False)
    return facts


def latest_listing(reports: list[pd.DataFrame]) -> pd.DataFrame:
    """Each player's row from his team's most recent listing among `reports`."""
    rows = pd.concat([r for r in reports if len(r)], ignore_index=True) if any(len(r) for r in reports) else None
    if rows is None:
        return pd.DataFrame(columns=["PLAYER_ID", "team", "status", "injury_type", "report_day"])
    latest = rows.groupby("team").report_day.transform("max")
    return rows[(rows.report_day == latest) & rows.PLAYER_ID.notna()].drop_duplicates("PLAYER_ID")


def features_from(recent: pd.DataFrame, week_ago: pd.DataFrame, serious_types: set) -> pd.DataFrame:
    """Injury features by PLAYER_ID from the recent and week-ago listings."""
    level = lambda df: df.set_index("PLAYER_ID").status.map(STATUS_LEVEL).fillna(0)
    now, before = level(recent), level(week_ago)
    ids = now.index.union(before.index)
    out = pd.DataFrame(index=ids)
    out["listed_level"] = now.reindex(ids).fillna(0)
    out["listed_out"] = (out.listed_level == STATUS_LEVEL["Out"]).astype(int)
    types = recent.set_index("PLAYER_ID").injury_type.reindex(ids)
    out["serious_injury"] = types.isin(serious_types).astype(int)
    out["out_week_ago"] = (before.reindex(ids).fillna(0) == STATUS_LEVEL["Out"]).astype(int)
    out["status_trend"] = out.listed_level - before.reindex(ids).fillna(0)
    # Rough days listed: a week or more if Out now and a week ago, about a day if only now.
    out["days_listed"] = np.where(out.listed_out & out.out_week_ago, 7, np.where(out.listed_out, 1, 0))
    return out


def snapshot_features(season: str, date: pd.Timestamp, players: pd.DataFrame | None, serious_types: set,
                      reports_for=None) -> pd.DataFrame:
    """Injury features as of the start of `date`, from reports published before it."""
    reports_for = reports_for or (lambda day: cached_day(day, season, players))
    recent = latest_listing([reports_for(date - pd.Timedelta(days=d)) for d in RECENT_DAYS])
    week_ago = latest_listing([reports_for(date - pd.Timedelta(days=d)) for d in WEEK_AGO_DAYS])
    return features_from(recent, week_ago, serious_types)


def serious_types() -> set:
    return set(load_recovery().injury_type)


def add_to_snapshots(snaps: pd.DataFrame) -> pd.DataFrame:
    """Past snapshots with injury features (missing before 2019-20, when no reports exist)."""
    serious = serious_types()
    parts = []
    for (season, date), rows in snaps.drop(columns=INJURY_FEATURES, errors="ignore").groupby(["SEASON", "date"]):
        rows = rows.copy()
        if season >= FIRST_SEASON:
            rows = rows.join(snapshot_features(season, pd.Timestamp(date), None, serious), on="PLAYER_ID")
            rows[INJURY_FEATURES] = rows[INJURY_FEATURES].fillna(0)
        else:
            rows[INJURY_FEATURES] = np.nan
        parts.append(rows)
    return pd.concat(parts).sort_index()


def current_features(log: pd.DataFrame | None, date: pd.Timestamp) -> pd.DataFrame:
    """Injury features as of the start of `date` from this season's saved report log
    (one report per day), so only reports from before `date` count."""
    if log is None or log.empty:
        return pd.DataFrame(columns=INJURY_FEATURES, index=pd.Index([], name="PLAYER_ID"))
    log = log.assign(report_day=pd.to_datetime(log.report_day))
    return snapshot_features(config.FORECAST_SEASON, pd.Timestamp(date), None, serious_types(),
                             reports_for=lambda day: log[log.report_day == day])


def main():
    from next82.in_season import snapshot_dates, to_date

    team_games = data.load("team_games")[["SEASON", "TEAM_ID", "GAME_DATE"]]
    team_games["GAME_DATE"] = to_date(team_games.GAME_DATE)
    seasons = config.SEASONS[config.SEASONS.index(FIRST_SEASON):]
    for season in seasons:
        players = _season_players(season)
        dates = snapshot_dates(team_games[team_games.SEASON == season])
        days = sorted({d - pd.Timedelta(days=k) for d in dates for k in (*RECENT_DAYS, *WEEK_AGO_DAYS)})
        new = [d for d in days if not (CACHE_DIR / f"{d:%Y-%m-%d}.parquet").exists()]
        for d in new:
            cached_day(d, season, players)
        found = sum(len(pd.read_parquet(CACHE_DIR / f"{d:%Y-%m-%d}.parquet")) > 0 for d in days)
        print(f"{season}: {len(days)} report days needed, {len(new)} downloaded now, {found} with a report")


if __name__ == "__main__":
    main()
