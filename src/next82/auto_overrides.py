"""Automatic overrides from the NBA's injury report, and team timelines from news.

A player listed Out with a serious injury type in the recovery table
(data/recovery_table.csv) gets an override built like the manual ones:
    earliest return = injury start + the table's fast-end days
    latest return   = start + the table's latest days, or none if it can be season-ending
The injury start is the later of the player's last game played and his first
appearance on this season's report with this injury, so an offseason injury isn't
counted from April. The exception is a player already listed Out with an injury on the
last day of the previous regular season (when every team plays, so everyone injured
is listed; the wording then is often generic, like "knee surgery"): his injury
predates the season, so it's counted from his last game.

A team-announced timeline in data/news_timelines.csv replaces the table's estimate
(it's no longer an estimate). Manual rows in data/overrides.csv always win.

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
# Parsed facts of the injury report from the previous season's last regular-season day.
END_OF_LAST_SEASON_PATH = config.PROCESSED_DIR / f"injuries_end_of_season_before_{config.FORECAST_SEASON}.parquet"
# Still out after the latest typical return: assume he's back within this many days.
OVERDUE_WINDOW_DAYS = 14
# Statuses on the end-of-season report that aren't injuries.
NOT_AN_INJURY = ["rest", "not injury", "illness", "personal", "suspension"]
NEWS_COLUMNS = ["player_id", "earliest_return", "latest_return", "note", "source_url", "date_found"]


def load_recovery(path=None) -> pd.DataFrame:
    df = pd.read_csv(path or RECOVERY_PATH)
    df["can_be_season_ending"] = df.can_be_season_ending.astype(str).str.lower().isin(["yes", "true", "1"])
    return df


def load_news(path=None) -> pd.DataFrame:
    path = path or NEWS_PATH
    if not path.exists():
        return pd.DataFrame(columns=NEWS_COLUMNS)
    df = pd.read_csv(path, dtype={"player_id": "Int64"})
    for c in ("earliest_return", "latest_return", "date_found"):
        df[c] = pd.to_datetime(df[c])
    return df


def recovery_row(recovery: pd.DataFrame, injury_type, body_part) -> pd.Series | None:
    """The table row for an injury, if it's a serious type we have an estimate for."""
    rows = recovery[recovery.injury_type == injury_type]
    for _, r in rows.iterrows():
        need = r.body_part_contains
        if pd.isna(need) or (isinstance(body_part, str) and need in body_part):
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
    news_by_id = {int(r.player_id): r for r in news.itertuples()} if len(news) else {}
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
                    + (" (his last game; he was already out with it at the end of last season)."
                       if pid in already_out else
                       " (the later of his last game and his first listing with this injury)."))
            # Still out past the typical recovery: he could be back any time.
            if earliest < today:
                note += " He's past the typical recovery time, so a return could come any day."
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


def current(manual: pd.DataFrame, today: pd.Timestamp) -> tuple[pd.DataFrame, list[str]]:
    """Automatic and news overrides for today, from the saved injury log and game logs."""
    logs = data.saved_season_logs()
    before = pd.read_parquet(LAST_GAME_PATH) if LAST_GAME_PATH.exists() else None
    player_games = logs[0] if logs is not None else None
    end = pd.read_parquet(END_OF_LAST_SEASON_PATH) if END_OF_LAST_SEASON_PATH.exists() else None
    return build(injuries.saved_log(), load_recovery(), load_news(), manual.player_id, last_games(player_games, before),
                 player_games, today, end)


def main():
    """Each player's last game before the season in progress, and the injury report from
    the last regular-season day before it (both from history; built once per season)."""
    from next82 import injury_history

    games = data.load("player_games")[["PLAYER_ID", "GAME_DATE"]]
    last = games.assign(GAME_DATE=pd.to_datetime(games.GAME_DATE.astype(str).str[:10])).groupby("PLAYER_ID").GAME_DATE.max()
    last.reset_index().to_parquet(LAST_GAME_PATH, index=False)
    print(f"Saved {LAST_GAME_PATH.relative_to(config.ROOT)} ({len(last):,} players)")

    previous = config.SEASONS[-1]
    team_games = data.load("team_games", [previous])
    final_day = pd.to_datetime(team_games.GAME_DATE.astype(str).str[:10]).max()
    report = injury_history.cached_day(final_day, previous)
    report.to_parquet(END_OF_LAST_SEASON_PATH, index=False)
    print(f"Saved {END_OF_LAST_SEASON_PATH.relative_to(config.ROOT)}: {final_day:%Y-%m-%d} report, "
          f"{(report.status == 'Out').sum()} players out")


if __name__ == "__main__":
    main()
