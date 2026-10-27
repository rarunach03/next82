"""Automatic overrides from the NBA's injury report, and team timelines from news.

A player listed Out with a serious injury type in the recovery table
(data/recovery_table.csv) gets an override built like the manual ones:
    earliest return = injury start + the table's fast-end days
    latest return   = start + the table's latest days, or none if it can be season-ending
The injury start is the later of the player's last game played and his first
appearance on this season's report with this injury, so an offseason injury isn't
counted from April. The exception is a player already listed Out with an injury on the
last day of the previous regular season (when every team plays, so everyone injured
is listed; the wording then is often generic, like "knee surgery") or on his team's
last playoff game day: his injury predates the season, so it's counted from his last
game (playoffs included).

A team-announced timeline in data/news_timelines.csv replaces the table's estimate
(it's no longer an estimate). A manual row in data/overrides.csv wins over both,
unless a news row was found after the manual row was added: then the news row wins
and the manual row is the fallback if the news row goes away. Each player's most
recently found news row is the one used. A news timeline whose window has passed
(latest return, or earliest if there's no latest, before today) while the player
is still out has expired: it's ignored, with a log line, until a newer one is found.

The report only lists teams that are about to play, so a player's status comes from
his team's most recent listing in the season's log. An automatic override clears
when that listing no longer includes him, or when he plays again.

Usage:
    python -m next82.auto_overrides     # build the last-game-before-the-season file (needs raw data)
"""
import pandas as pd

from next82 import config, data, injuries
from next82.overrides import COLUMNS

RECOVERY_PATH = config.ROOT / "data" / "recovery_table.csv"
NEWS_PATH = config.ROOT / "data" / "news_timelines.csv"
LAST_GAME_PATH = config.PROCESSED_DIR / f"last_game_before_{config.FORECAST_SEASON}.parquet"
# Parsed facts of the injury reports from the previous season's last regular-season day
# and each playoff team's last playoff game day.
END_OF_LAST_SEASON_PATH = config.PROCESSED_DIR / f"injuries_end_of_season_before_{config.FORECAST_SEASON}.parquet"
# Still out after the latest typical return: assume he's back within this many days.
OVERDUE_WINDOW_DAYS = 14
# Statuses on the end-of-season report that aren't injuries.
NOT_AN_INJURY = ["rest", "not injury", "illness", "personal", "suspension"]
# date_found: when the row was added; source_date: when the source was published.
NEWS_COLUMNS = ["player_id", "earliest_return", "latest_return", "note", "source_url", "date_found", "source_date"]


def load_recovery(path=None) -> pd.DataFrame:
    df = pd.read_csv(path or RECOVERY_PATH)
    df["can_be_season_ending"] = df.can_be_season_ending.astype(str).str.lower().isin(["yes", "true", "1"])
    return df


def load_news(path=None) -> pd.DataFrame:
    path = path or NEWS_PATH
    if not path.exists():
        return pd.DataFrame(columns=NEWS_COLUMNS)
    df = pd.read_csv(path, dtype={"player_id": "Int64"}).reindex(columns=NEWS_COLUMNS)
    for c in ("earliest_return", "latest_return", "date_found", "source_date"):
        df[c] = pd.to_datetime(df[c])
    return df


def recovery_row(recovery: pd.DataFrame, injury_type, body_part) -> pd.Series | None:
    """The table row for an injury, if it's a serious type we have an estimate for.
    body_part_contains may list alternatives separated by "|"; the first matching row wins."""
    rows = recovery[recovery.injury_type == injury_type]
    for _, r in rows.iterrows():
        need = r.body_part_contains
        if pd.isna(need) or (isinstance(body_part, str) and any(n in body_part for n in need.split("|"))):
            return r
    return None


def current_listings(log: pd.DataFrame) -> pd.DataFrame:
    """Each player's row from his team's most recent report day in the log."""
    latest_day = log.groupby("team").report_day.transform("max")
    return log[log.report_day == latest_day]


def last_games(player_games: pd.DataFrame | None, before_season: pd.DataFrame | None) -> pd.Series:
    """Date of each player's last game played: this season if any, else before it."""
    out = pd.Series(dtype="datetime64[ns]")
    if before_season is not None:
        out = before_season.set_index("PLAYER_ID").GAME_DATE
    if player_games is not None and len(player_games):
        this_season = pd.to_datetime(player_games.GAME_DATE.astype(str).str[:10]).groupby(player_games.PLAYER_ID).max()
        out = this_season.combine_first(out)
    return out


def injury_start(last_game, first_listed, listed_before_season: bool):
    """When the recovery clock starts (see module docstring)."""
    if pd.isna(last_game):
        return first_listed
    if listed_before_season or pd.isna(first_listed):
        return last_game
    return max(last_game, first_listed)


def build(log: pd.DataFrame | None, recovery: pd.DataFrame, news: pd.DataFrame, manual_ids, last_game: pd.Series,
          player_games: pd.DataFrame | None, today: pd.Timestamp,
          end_of_last_season: pd.DataFrame | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Override rows (same columns as overrides.csv, plus 'kind') and log lines."""
    already_out = set()
    if end_of_last_season is not None and len(end_of_last_season):
        e = end_of_last_season[(end_of_last_season.status == "Out") & end_of_last_season.PLAYER_ID.notna()
                               & ~end_of_last_season.injury_type.isin(NOT_AN_INJURY)]
        already_out = set(e.PLAYER_ID.astype(int))
    rows, lines = [], []
    if log is None or log.empty:
        return pd.DataFrame(columns=[*COLUMNS, "kind"]), lines
    played_after = {}
    if player_games is not None and len(player_games):
        dates = pd.to_datetime(player_games.GAME_DATE.astype(str).str[:10])
        played_after = dates.groupby(player_games.PLAYER_ID).max().to_dict()
    news_by_id = latest_news(news)
    for r in current_listings(log).itertuples():
        if pd.isna(r.PLAYER_ID) or r.status != "Out":
            continue
        pid = int(r.PLAYER_ID)
        if pid in set(manual_ids):
            continue  # manual rows win
        if pid in played_after and played_after[pid] >= r.report_day:
            continue  # played again since the report: clears
        table = recovery_row(recovery, r.injury_type, r.body_part)
        news_row = news_by_id.get(pid)
        if news_row is not None and expired(news_row, today):
            lines.append(f"News timeline for {r.player_name} has expired (still listed Out); "
                         + ("using the recovery-table estimate" if table is not None else "leaving it to the model"))
            news_row = None
        if table is None and news_row is None:
            continue  # short-term or unknown types: the model handles those
        first_listed = log[(log.PLAYER_ID == r.PLAYER_ID) & (log.injury_type == r.injury_type)].report_day.min()
        start = injury_start(last_game.get(pid, pd.NaT), first_listed, pid in already_out)
        if news_row is not None:
            earliest, latest, estimated = news_row.earliest_return, news_row.latest_return, False
            note = f"{injuries.clean_reason(r.reason)}. Team timeline: {news_row.note}"
            source, source2, kind = r.report_url, news_row.source_url, "news"
        else:
            earliest = start + pd.Timedelta(days=int(table.earliest_days))
            latest = (start + pd.Timedelta(days=int(table.latest_days))
                      if not table.can_be_season_ending and pd.notna(table.latest_days) else pd.NaT)
            estimated = True
            note = (f"{injuries.clean_reason(r.reason)} (NBA injury report, {r.report_day:%b %-d}). {table.basis} "
                    f"Counted from {start:%b %-d, %Y}"
                    + (" (the last game played; already out with it at the end of last season)."
                       if pid in already_out else
                       " (the later of the last game played and the first listing with this injury)."))
            # Still out past the typical recovery: a return could come any time.
            if earliest < today:
                note += " That's past the typical recovery time, so a return could come any day."
                earliest = today
                if pd.notna(latest) and latest < today:
                    latest = today + pd.Timedelta(days=OVERDUE_WINDOW_DAYS)
            source, source2, kind = r.report_url, table.source_url, "automatic"
        rows.append({
            "player_id": pid, "player_name": r.player_name, "status": "Out",
            "earliest_return": earliest, "latest_return": latest, "estimated": estimated, "note": note,
            "source_url": source, "source_url_2": source2, "date_added": r.report_day, "review_by": pd.NaT,
            "kind": kind,
        })
        lines.append(f"Automatic override ({kind}): {r.player_name}, {r.injury_type} "
                     f"({r.body_part or 'no body part'}), back no earlier than {pd.Timestamp(earliest):%Y-%m-%d}"
                     + (f", by {pd.Timestamp(latest):%Y-%m-%d}" if pd.notna(latest) else ", no latest return"))
    return pd.DataFrame(rows, columns=[*COLUMNS, "kind"]), lines


def expired(n, today: pd.Timestamp) -> bool:
    """A news timeline whose window has passed (the player is still out if we're asking)."""
    end = n.latest_return if pd.notna(n.latest_return) else n.earliest_return
    return pd.notna(end) and end < today


def latest_news(news: pd.DataFrame) -> dict:
    """Each player's most recently found news row, by player_id."""
    if not len(news):
        return {}
    news = news.dropna(subset=["player_id"]).sort_values("date_found", kind="stable")
    return {int(r.player_id): r for r in news.itertuples()}


def news_over_manual(news: pd.DataFrame, manual: pd.DataFrame, today: pd.Timestamp) -> tuple[pd.DataFrame, list[str]]:
    """News rows found after a player's manual row was added, as override rows that
    replace it (kind 'news'; the manual row's source stays as the second link)."""
    rows, lines = [], []
    by_id = latest_news(news)
    for m in manual.itertuples():
        n = by_id.get(int(m.player_id))
        if n is None or pd.isna(n.date_found) or (pd.notna(m.date_added) and n.date_found <= m.date_added):
            continue
        if expired(n, today):
            lines.append(f"News timeline for {m.player_name} has expired; using the manual row")
            continue
        rows.append({
            "player_id": int(m.player_id), "player_name": m.player_name, "status": "Out",
            "earliest_return": n.earliest_return, "latest_return": n.latest_return, "estimated": False,
            "note": f"Team timeline: {n.note}", "source_url": n.source_url, "source_url_2": m.source_url,
            "date_added": n.date_found, "review_by": pd.NaT, "kind": "news",
        })
        lines.append(f"News override (replaces manual row from {m.date_added:%Y-%m-%d}): {m.player_name}, back no earlier "
                     f"than {n.earliest_return:%Y-%m-%d}" + (f", by {n.latest_return:%Y-%m-%d}" if pd.notna(n.latest_return)
                                                              else ", no latest return") + f" ({n.source_url})")
    return pd.DataFrame(rows, columns=[*COLUMNS, "kind"]), lines


def current(manual: pd.DataFrame, today: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Today's overrides: the manual rows still in use, plus news and automatic rows
    (from the saved injury log and game logs), and log lines."""
    news = load_news()
    from_news, lines = news_over_manual(news, manual, today)
    manual_used = manual[~manual.player_id.isin(from_news.player_id)]
    logs = data.saved_season_logs()
    before = pd.read_parquet(LAST_GAME_PATH) if LAST_GAME_PATH.exists() else None
    player_games = logs[0] if logs is not None else None
    end = pd.read_parquet(END_OF_LAST_SEASON_PATH) if END_OF_LAST_SEASON_PATH.exists() else None
    automatic, auto_lines = build(injuries.saved_log(), load_recovery(), news, manual.player_id,
                                  last_games(player_games, before), player_games, today, end)
    return manual_used, pd.concat([from_news, automatic], ignore_index=True), lines + auto_lines


def playoff_games(season: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The season's playoff games: player rows (PLAYER_ID, GAME_DATE) and team rows (TEAM_ID, GAME_DATE)."""
    import time

    from nba_api.stats.endpoints import leaguegamelog, playergamelogs

    players = playergamelogs.PlayerGameLogs(season_nullable=season, season_type_nullable="Playoffs",
                                            timeout=data.TIMEOUT).get_data_frames()[0]
    time.sleep(config.REQUEST_DELAY)
    teams = leaguegamelog.LeagueGameLog(season=season, season_type_all_star="Playoffs",
                                        player_or_team_abbreviation="T", timeout=data.TIMEOUT).get_data_frames()[0]
    to_day = lambda s: pd.to_datetime(s.astype(str).str[:10])
    return (pd.DataFrame({"PLAYER_ID": players.PLAYER_ID, "GAME_DATE": to_day(players.GAME_DATE)}),
            pd.DataFrame({"TEAM_ID": teams.TEAM_ID, "GAME_DATE": to_day(teams.GAME_DATE)}))


def main():
    """Built once per season from history: each player's last game before the season in
    progress (playoffs included), and the injury reports from the last regular-season
    day and each playoff team's last playoff game day."""
    from next82 import injury_history

    previous = config.SEASONS[-1]
    games = data.load("player_games")[["PLAYER_ID", "GAME_DATE"]]
    games = games.assign(GAME_DATE=pd.to_datetime(games.GAME_DATE.astype(str).str[:10]))
    playoff_players, playoff_teams = playoff_games(previous)
    last = pd.concat([games, playoff_players]).groupby("PLAYER_ID").GAME_DATE.max()
    last.reset_index().to_parquet(LAST_GAME_PATH, index=False)
    print(f"Saved {LAST_GAME_PATH.relative_to(config.ROOT)} ({len(last):,} players; playoffs included)")

    team_games = data.load("team_games", [previous])
    days = {pd.to_datetime(team_games.GAME_DATE.astype(str).str[:10]).max()}
    days |= set(playoff_teams.groupby("TEAM_ID").GAME_DATE.max())
    reports = [injury_history.cached_day(day, previous) for day in sorted(days)]
    report = pd.concat([r for r in reports if len(r)], ignore_index=True)
    report.to_parquet(END_OF_LAST_SEASON_PATH, index=False)
    print(f"Saved {END_OF_LAST_SEASON_PATH.relative_to(config.ROOT)}: {len(days)} report days "
          f"({sum(len(r) > 0 for r in reports)} found), {(report.status == 'Out').sum()} players out")


if __name__ == "__main__":
    main()
