"""Build the modeling table: one row per player-season, target = games played next season.

Games are measured as a share of the team's schedule (gp_share) so that the
shortened 2019-20 and 2020-21 seasons are comparable to 82-game seasons.

Absence features come from matching each player's game log against their
team's schedule, split into stints (consecutive games with one team):
    gap_*      games missed between two appearances with the same team
    missed_start / missed_end
               team games before a player's first appearance / after their last.
               These also capture late signings, releases and buyouts, so they
               are kept separate from mid-stint gaps.

Sat-out seasons: when a player misses a whole season, a row is added for that
season with 0 games played and missed_season = 1 (in-season stats are left blank).
This lets the model learn what happens in comeback years, and lets the app
forecast players who sat out the latest season. Rows are added when the player
played in one of the two seasons before and either returned later (training) or
the season is the latest one and they were a rotation player the season before
(forecast; fringe players who sat out have most likely left the league).

Target rules for a player in season s:
    played in s+1                       -> target = s+1 gp_share
    absent in s+1, returns in any later -> target = 0 (missed the whole season)
    never seen again after s            -> dropped (left the league; can't tell why)
The last season has no target; those rows are what the app forecasts.

Usage:
    python -m next82.features
"""
import pandas as pd

from next82 import config
from next82.data import load

OUTPUT_PATH = config.PROCESSED_DIR / "player_seasons.parquet"

# A run of this many missed games counts as a major absence.
MAJOR_ABSENCE_GAMES = 10

BASE_FEATURES = [
    "age",
    "years_since_draft",
    "undrafted",
    "height_in",
    "weight_lb",
    "gp_share",
    "mpg",
    "min_share",
    "usg_pct",
    "longest_gap",
    "n_major_gaps",
    "missed_start",
    "missed_end",
    "n_teams",
    "missed_season",
    "gp_share_lag1",
    "gp_share_lag2",
    "missed_season_lag1",
    "mpg_lag1",
    "longest_gap_lag1",
    "missed_end_lag1",
    "major_gaps_3yr",
    "avg_gp_share_3yr",
    "seasons_in_data",
]

# Inputs for players coming back from a missed season. For players who played this
# season, the "last played" values are simply this season's. Kept because they
# don't make regular forecasts worse on the 2022-23 validation season
# (14.142 -> 14.112 games, 5-seed average; test seasons not used for this choice).
COMEBACK_FEATURES = [
    "last_played_gp_share",
    "avg_gp_share_3_played",
    "age_x_missed_season",
]
FEATURES = BASE_FEATURES + COMEBACK_FEATURES
TARGET = "gp_share_next"

# Candidate feature groups for improving the season model (next82.improve). They're in
# the table, but only groups that help on validation are added to FEATURES. Each uses
# only the player's season and earlier seasons.
CANDIDATE_GROUPS = {
    "Absence detail": ["n_gaps_5", "gap_games", "gap_games_lag1", "recurring_major_3yr", "missed_last20"],
    "Workload": ["mpg_trend", "heavy_seasons_3yr", "minutes_3yr", "share_40min"],
    "Usage change": ["usg_change", "min_share_change"],
    "Age interactions": ["age_x_missed_3yr", "age_x_mpg"],
    "Durability streaks": ["durable_streak", "durable_5yr"],
    "Production": ["ppg", "pts_per36", "draft_number"],
}
CANDIDATES = [c for cols in CANDIDATE_GROUPS.values() for c in cols]
# 70 of 82 games: a full, healthy season.
DURABLE_SHARE = 70 / 82
HEAVY_MPG = 34


def _season_start(season: str) -> int:
    return int(season[:4])


def team_schedules(team_games: pd.DataFrame) -> pd.DataFrame:
    """Number each team's games 0..n-1 in date order."""
    tg = team_games[["SEASON", "TEAM_ID", "GAME_ID", "GAME_DATE"]].sort_values(
        ["SEASON", "TEAM_ID", "GAME_DATE", "GAME_ID"]
    )
    tg["game_idx"] = tg.groupby(["SEASON", "TEAM_ID"]).cumcount()
    tg["team_n_games"] = tg.groupby(["SEASON", "TEAM_ID"]).GAME_ID.transform("size")
    return tg


def absence_features(player_games: pd.DataFrame, schedules: pd.DataFrame) -> pd.DataFrame:
    """Per player-season absence stats from game logs matched to team schedules."""
    pg = player_games[["SEASON", "PLAYER_ID", "TEAM_ID", "GAME_ID"]].merge(
        schedules, on=["SEASON", "TEAM_ID", "GAME_ID"], how="inner"
    )
    pg = pg.sort_values(["SEASON", "PLAYER_ID", "GAME_DATE", "GAME_ID"])

    # A new stint starts whenever the player's team changes.
    new_stint = pg.groupby(["SEASON", "PLAYER_ID"]).TEAM_ID.transform(lambda t: t != t.shift())
    pg["stint"] = new_stint.groupby([pg.SEASON, pg.PLAYER_ID]).cumsum()

    # Games missed since the previous appearance in the same stint.
    prev_idx = pg.groupby(["SEASON", "PLAYER_ID", "stint"]).game_idx.shift()
    pg["gap"] = (pg.game_idx - prev_idx - 1).fillna(0)

    stints = pg.groupby(["SEASON", "PLAYER_ID", "stint"]).agg(
        first_idx=("game_idx", "min"),
        last_idx=("game_idx", "max"),
        team_n_games=("team_n_games", "first"),
    )
    stints = stints.reset_index()
    first = stints.groupby(["SEASON", "PLAYER_ID"]).first()
    last = stints.groupby(["SEASON", "PLAYER_ID"]).last()

    gaps = pg.groupby(["SEASON", "PLAYER_ID"]).gap
    out = pd.DataFrame({
        "longest_gap": gaps.max(),
        "n_major_gaps": gaps.apply(lambda g: (g >= MAJOR_ABSENCE_GAMES).sum()),
        "missed_start": first.first_idx,
        "missed_end": last.team_n_games - 1 - last.last_idx,
        "n_teams": stints.groupby(["SEASON", "PLAYER_ID"]).size(),
    })
    # A season-ending absence is also a major absence.
    out["n_major_gaps"] += (out.missed_end >= MAJOR_ABSENCE_GAMES).astype(int)
    return out.reset_index()


def season_table() -> pd.DataFrame:
    """One row per player-season with that season's stats and absence features."""
    stats = load("player_stats")
    bio = load("player_bio")
    team_games = load("team_games")
    schedules = team_schedules(team_games)

    # Length of the season = most games any team played (2019-20 varied by team).
    season_games = schedules.groupby("SEASON").team_n_games.max().rename("season_games")
    league_min = stats.groupby("SEASON").MIN.max().rename("max_min")

    df = stats[["SEASON", "PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION", "AGE", "GP", "MIN"]]
    df = df.merge(season_games, on="SEASON").merge(league_min, on="SEASON")

    bio = bio[["SEASON", "PLAYER_ID", "PLAYER_HEIGHT_INCHES", "PLAYER_WEIGHT", "DRAFT_YEAR", "USG_PCT"]]
    df = df.merge(bio, on=["SEASON", "PLAYER_ID"], how="left")
    df = df.merge(absence_features(load("player_games"), schedules), on=["SEASON", "PLAYER_ID"], how="left")

    draft_year = pd.to_numeric(df.DRAFT_YEAR, errors="coerce")
    df = df.assign(
        season_idx=df.SEASON.map({s: i for i, s in enumerate(config.SEASONS)}),
        age=df.AGE,
        years_since_draft=df.SEASON.map(_season_start) - draft_year,
        undrafted=draft_year.isna().astype(int),
        height_in=pd.to_numeric(df.PLAYER_HEIGHT_INCHES, errors="coerce"),
        weight_lb=pd.to_numeric(df.PLAYER_WEIGHT, errors="coerce"),
        gp_share=df.GP / df.season_games,
        mpg=df.MIN / df.GP,
        min_share=df.MIN / df.max_min,
        usg_pct=df.USG_PCT,
    )
    return df


def add_missed_seasons(df: pd.DataFrame) -> pd.DataFrame:
    """Add a row for each season a player sat out entirely (rules in the module docstring)."""
    last_idx = len(config.SEASONS) - 1
    season_games = df.groupby("season_idx").season_games.max()
    df = df.assign(missed_season=0)

    rows = []
    for _, g in df.sort_values("season_idx").groupby("PLAYER_ID"):
        played = set(g.season_idx)
        for s in range(g.season_idx.min() + 1, last_idx + 1):
            if s in played:
                continue
            prev = g[g.season_idx < s].iloc[-1]
            returned = g.season_idx.max() > s and (s - 1 in played or s - 2 in played)
            was_rotation = prev.mpg >= config.ROTATION_MIN_MPG and prev.gp_share >= config.ROTATION_MIN_GP_SHARE
            forecast = s == last_idx and s - 1 in played and was_rotation
            if not (returned or forecast):
                continue
            years = s - prev.season_idx
            rows.append(prev.to_dict() | {
                "SEASON": config.SEASONS[s],
                "season_idx": s,
                "age": prev.age + years,
                "years_since_draft": prev.years_since_draft + years,
                "GP": 0,
                "MIN": 0.0,
                "season_games": season_games[s],
                "gp_share": 0.0,
                "mpg": float("nan"),
                "min_share": 0.0,
                "usg_pct": float("nan"),
                "longest_gap": float("nan"),
                "missed_start": float("nan"),
                "missed_end": float("nan"),
                "n_major_gaps": 1,
                "n_teams": 0,
                "missed_season": 1,
            })
    return pd.concat([df, pd.DataFrame(rows)], ignore_index=True)


def add_history(df: pd.DataFrame) -> pd.DataFrame:
    """Lagged features from earlier seasons, matched by season (not by row)."""
    cols = ["PLAYER_ID", "season_idx", "gp_share", "mpg", "longest_gap", "missed_end"]
    for lag in (1, 2):
        prev = df[cols].copy()
        prev["season_idx"] += lag
        prev = prev.rename(columns={c: f"{c}_lag{lag}" for c in cols[2:]})
        df = df.merge(prev, on=["PLAYER_ID", "season_idx"], how="left")

    # A season between a player's first appearance and now with no record means
    # they missed the whole season: 0 games played, and it counts as a major absence.
    first_seen = df.groupby("PLAYER_ID").season_idx.transform("min")
    for lag in (1, 2):
        sat_out = df[f"gp_share_lag{lag}"].isna() & (df.season_idx - lag >= first_seen)
        df.loc[sat_out, f"gp_share_lag{lag}"] = 0.0
    df["missed_season_lag1"] = (df.season_idx - 1 >= first_seen) & df.gp_share_lag1.eq(0)
    df["missed_season_lag1"] = df.missed_season_lag1.astype(int)

    # 3-season windows include the current season; missed seasons are filled in.
    by_player = df.sort_values("season_idx").groupby("PLAYER_ID")
    window = lambda col, fn, fill: by_player.apply(
        lambda g: g.set_index("season_idx")[col]
        .reindex(range(g.season_idx.min(), g.season_idx.max() + 1), fill_value=fill)
        .rolling(3, min_periods=1).agg(fn)
        .reindex(g.season_idx).set_axis(g.index),
        include_groups=False,
    ).droplevel(0)
    df["major_gaps_3yr"] = window("n_major_gaps", "sum", fill=1)
    df["avg_gp_share_3yr"] = window("gp_share", "mean", fill=0.0)
    # Seasons actually played, so sat-out rows don't count as experience.
    df["seasons_in_data"] = by_player.missed_season.transform(lambda m: (1 - m).cumsum())

    # Comeback inputs: computed over seasons actually played, then carried forward
    # into any sat-out seasons that follow.
    df = df.sort_values(["PLAYER_ID", "season_idx"])
    played = df.missed_season == 0
    df["last_played_gp_share"] = df.gp_share.where(played)
    df["avg_gp_share_3_played"] = (
        df[played].groupby("PLAYER_ID").gp_share.transform(lambda g: g.rolling(3, min_periods=1).mean())
    )
    df[["last_played_gp_share", "avg_gp_share_3_played"]] = (
        df.groupby("PLAYER_ID")[["last_played_gp_share", "avg_gp_share_3_played"]].ffill()
    )
    df["age_x_missed_season"] = df.age * df.missed_season
    return df


def season_log_details(player_games: pd.DataFrame, schedules: pd.DataFrame) -> pd.DataFrame:
    """Per player-season details from game logs: absences of 5+ games, games missed
    mid-stint, games missed of the last team's final 20, share of 40-minute games."""
    pg = player_games[["SEASON", "PLAYER_ID", "TEAM_ID", "GAME_ID", "MIN"]].merge(
        schedules, on=["SEASON", "TEAM_ID", "GAME_ID"], how="inner"
    ).sort_values(["SEASON", "PLAYER_ID", "GAME_DATE", "GAME_ID"])
    new_stint = pg.groupby(["SEASON", "PLAYER_ID"]).TEAM_ID.transform(lambda t: t != t.shift())
    pg["stint"] = new_stint.groupby([pg.SEASON, pg.PLAYER_ID]).cumsum()
    pg["gap"] = (pg.game_idx - pg.groupby(["SEASON", "PLAYER_ID", "stint"]).game_idx.shift() - 1).fillna(0)
    by = pg.groupby(["SEASON", "PLAYER_ID"])
    out = pd.DataFrame({
        "n_gaps_5": by.gap.apply(lambda g: int((g >= 5).sum())),
        "gap_games": by.gap.sum(),
        "share_40min": by.MIN.apply(lambda m: float((pd.to_numeric(m, errors="coerce") >= 40).mean())),
    })
    # The last team's final 20 games (or fewer, if the player joined later): how many he missed.
    last = pg[pg.stint == by.stint.transform("max")]
    lb = last.groupby(["SEASON", "PLAYER_ID"])
    window_start = (lb.team_n_games.first() - 20).clip(lower=0).combine(lb.game_idx.min(), max)
    played = last.assign(start=last.set_index(["SEASON", "PLAYER_ID"]).index.map(window_start))
    played = (played.game_idx >= played.start).groupby([played.SEASON, played.PLAYER_ID]).sum()
    out["missed_last20"] = (lb.team_n_games.first() - window_start) - played
    return out.reset_index()


def _window(df: pd.DataFrame, col: str, n: int, fn: str, fill) -> pd.Series:
    """Rolling `fn` over the player's last n seasons (this one included), seasons with no
    row inside his span filled with `fill`. Uses only this and earlier seasons."""
    by_player = df.sort_values("season_idx").groupby("PLAYER_ID")
    return by_player.apply(
        lambda g: g.set_index("season_idx")[col]
        .reindex(range(g.season_idx.min(), g.season_idx.max() + 1), fill_value=fill)
        .rolling(n, min_periods=1).agg(fn)
        .reindex(g.season_idx).set_axis(g.index),
        include_groups=False,
    ).droplevel(0)


def _streak(df: pd.DataFrame, flag: str) -> pd.Series:
    """Seasons in a row (ending with this one) where `flag` holds; a season with no row breaks it."""
    def run(g):
        s = g.set_index("season_idx")[flag].reindex(range(g.season_idx.min(), g.season_idx.max() + 1), fill_value=False)
        streak, out = 0, []
        for v in s:
            streak = streak + 1 if v else 0
            out.append(streak)
        return pd.Series(out, index=s.index).reindex(g.season_idx).set_axis(g.index)

    return df.sort_values("season_idx").groupby("PLAYER_ID").apply(run, include_groups=False).droplevel(0)


def add_candidates(df: pd.DataFrame, player_games: pd.DataFrame, schedules: pd.DataFrame,
                   stats: pd.DataFrame, bio: pd.DataFrame) -> pd.DataFrame:
    """Candidate features (CANDIDATE_GROUPS), from this and earlier seasons only."""
    df = df.merge(season_log_details(player_games, schedules), on=["SEASON", "PLAYER_ID"], how="left")
    totals = stats[["SEASON", "PLAYER_ID", "PTS"]].drop_duplicates(["SEASON", "PLAYER_ID"])
    df = df.merge(totals, on=["SEASON", "PLAYER_ID"], how="left")
    draft = bio[["PLAYER_ID", "SEASON", "DRAFT_NUMBER"]].assign(
        draft_number=lambda b: pd.to_numeric(b.DRAFT_NUMBER, errors="coerce"))
    df = df.merge(draft[["SEASON", "PLAYER_ID", "draft_number"]].drop_duplicates(["SEASON", "PLAYER_ID"]),
                  on=["SEASON", "PLAYER_ID"], how="left")
    # Sat-out seasons have no stats row: carry the draft pick forward from earlier seasons.
    df = df.sort_values(["PLAYER_ID", "season_idx"])
    df["draft_number"] = df.groupby("PLAYER_ID").draft_number.ffill()

    prev = df[["PLAYER_ID", "season_idx", "gap_games", "usg_pct", "min_share"]].assign(season_idx=lambda d: d.season_idx + 1)
    df = df.merge(prev.rename(columns={"gap_games": "gap_games_lag1", "usg_pct": "usg_lag1", "min_share": "min_share_lag1"}),
                  on=["PLAYER_ID", "season_idx"], how="left")

    df["recurring_major_3yr"] = _window(df.assign(major=(df.n_major_gaps > 0).astype(int)), "major", 3, "sum", fill=1)
    df["mpg_trend"] = df.mpg - df.mpg_lag1
    df["heavy_seasons_3yr"] = _window(df.assign(heavy=(df.mpg >= HEAVY_MPG).astype(int)), "heavy", 3, "sum", fill=0)
    df["minutes_3yr"] = _window(df.assign(m=df.MIN.fillna(0) / 1000), "m", 3, "sum", fill=0.0)
    df["usg_change"] = df.usg_pct - df.usg_lag1
    df["min_share_change"] = df.min_share - df.min_share_lag1
    df["age_x_missed_3yr"] = df.age * (1 - df.avg_gp_share_3yr)
    df["age_x_mpg"] = df.age * df.mpg
    durable = df.assign(durable=df.gp_share >= DURABLE_SHARE)
    df["durable_streak"] = _streak(durable, "durable")
    df["durable_5yr"] = _window(durable.assign(durable=durable.durable.astype(int)), "durable", 5, "sum", fill=0)
    df["ppg"] = df.PTS / df.GP.where(df.GP > 0)
    df["pts_per36"] = df.PTS / df.MIN.where(df.MIN > 0) * 36
    return df.drop(columns=["usg_lag1", "min_share_lag1", "PTS"])


def add_target(df: pd.DataFrame) -> pd.DataFrame:
    """Next season's gp_share, with the rules described in the module docstring."""
    last_idx = len(config.SEASONS) - 1
    # A sat-out row in the latest season is only a forecast input: the player
    # hasn't returned yet, so it can't serve as the previous season's target.
    unconfirmed = (df.season_idx == last_idx) & (df.missed_season == 1)
    nxt = df.loc[~unconfirmed, ["PLAYER_ID", "season_idx", "gp_share", "GP", "season_games"]].copy()
    nxt["season_idx"] -= 1
    nxt = nxt.rename(columns={"gp_share": TARGET, "GP": "gp_next", "season_games": "season_games_next"})
    df = df.merge(nxt, on=["PLAYER_ID", "season_idx"], how="left")

    last_seen = df.groupby("PLAYER_ID").season_idx.transform("max")
    missed_full = df[TARGET].isna() & (last_seen > df.season_idx + 1)
    df.loc[missed_full, [TARGET, "gp_next"]] = 0.0
    # Their next season has no row of its own, so fill in its length from the
    # schedule; error in games is scaled by it.
    season_length = df.groupby("season_idx").season_games.max()
    df.loc[missed_full, "season_games_next"] = (df.loc[missed_full, "season_idx"] + 1).map(season_length)

    df["is_forecast"] = df.season_idx == last_idx
    # Players absent next season and never seen again: can't tell why, so drop.
    keep = df.is_forecast | df[TARGET].notna()
    return df[keep].reset_index(drop=True)


def feature_rows() -> pd.DataFrame:
    """Every player-season with its features (before targets are attached)."""
    df = add_history(add_missed_seasons(season_table()))
    return add_candidates(df, load("player_games"), team_schedules(load("team_games")), load("player_stats"),
                          load("player_bio"))


def build() -> pd.DataFrame:
    df = add_target(feature_rows())
    id_cols = ["SEASON", "season_idx", "PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION", "GP", "season_games"]
    target_cols = [TARGET, "gp_next", "season_games_next", "is_forecast"]
    feature_cols = list(dict.fromkeys(BASE_FEATURES + COMEBACK_FEATURES + CANDIDATES))
    return df[id_cols + feature_cols + target_cols].sort_values(["season_idx", "PLAYER_ID"]).reset_index(drop=True)


def load_table() -> pd.DataFrame:
    if not OUTPUT_PATH.exists():
        raise FileNotFoundError("Run `python -m next82.features` first.")
    return pd.read_parquet(OUTPUT_PATH)


def main():
    df = build()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUTPUT_PATH, index=False)
    n_train = (~df.is_forecast).sum()
    print(f"Saved {len(df):,} rows to {OUTPUT_PATH.relative_to(config.ROOT)}")
    print(f"  with target: {n_train:,}  |  forecast rows ({config.SEASONS[-1]}): {df.is_forecast.sum():,}")
    print(f"  missed full next season (target=0): {(df.gp_next == 0).sum()}")
    print(f"  sat-out season rows: {df.missed_season.sum()} ({(df.missed_season & df.is_forecast).sum()} to forecast)")


if __name__ == "__main__":
    main()
