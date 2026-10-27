"""Rest-of-season forecast: games played so far + predicted games still to come.

The preseason forecast stays frozen. This model updates daily during the season,
so a player who gets hurt in November sees their updated forecast drop.

Training data are snapshots of every player every SNAPSHOT_DAYS days through past
seasons. Each snapshot uses only games played before its date; the label is how
many games the player played from that date to the end of the season. The model
predicts the share of the team's remaining games a player will play (so shortened
seasons compare fairly), weighted by games remaining so the training loss matches
the error in games that we report.

The same function, `snapshot_features`, builds features for past snapshots and for
today's forecast, so training and the live site can't drift apart.

Usage:
    python -m next82.in_season     # build snapshots, validate, test, train, save the model
"""
import json

import lightgbm as lgb
import numpy as np
import pandas as pd

from next82 import config, data, intervals, models
from next82.features import FEATURES, load_table

MODEL_PATH = config.MODELS_DIR / "in_season.txt"
# Low and high ends of the likely range (10th and 90th percentiles).
RANGE_MODEL_PATHS = (config.MODELS_DIR / "in_season_low.txt", config.MODELS_DIR / "in_season_high.txt")
METRICS_PATH = config.MODELS_DIR / "in_season_metrics.json"
SNAPSHOTS_PATH = config.PROCESSED_DIR / "in_season_snapshots.parquet"

SNAPSHOT_DAYS = 14
# The first season used for training: earlier seasons have too little history
# before them to make an out-of-time preseason forecast.
FIRST_SEASON = "2000-01"
VALIDATION_SEASON = "2023-24"
TEST_SEASONS = ["2024-25", "2025-26"]
# A player who hasn't played in this many of their team's games is "currently out".
OUT_STREAK_GAMES = 5

SO_FAR_FEATURES = [
    "team_games_so_far",
    "team_games_left",
    "season_progress",
    "played_so_far",
    "missed_so_far",
    "share_so_far",
    "has_played",
    "absence_streak",
    "days_since_last_game",
    "played_last10_share",
]
IN_SEASON_FEATURES = SO_FAR_FEATURES + ["preseason_share"] + FEATURES


def to_date(values: pd.Series) -> pd.Series:
    """Game dates come as '2025-04-13' or '2025-04-13T00:00:00'; keep the day only."""
    return pd.to_datetime(values.astype(str).str[:10])


def snapshot_features(
    player_games: pd.DataFrame,
    team_games: pd.DataFrame,
    team_totals: pd.Series,
    players: pd.DataFrame,
    date: pd.Timestamp,
    known_teams: pd.Series | None = None,
) -> pd.DataFrame:
    """Features for every player in `players` as of the start of `date`.

    player_games: PLAYER_ID, TEAM_ID, GAME_DATE for the season (any dates).
    team_games:   TEAM_ID, GAME_DATE of the season's finished games (any dates).
    team_totals:  games each team plays in the season, indexed by TEAM_ID.
    players:      PLAYER_ID plus preseason features and preseason_share.
    known_teams:  optional current team by PLAYER_ID, for players who haven't
                  played yet (known from rosters for the season in progress; past
                  seasons don't record offseason moves).

    Only games before `date` are used.
    """
    pg = player_games[player_games.GAME_DATE < date]
    tg = team_games[team_games.GAME_DATE < date]
    team_so_far = tg.groupby("TEAM_ID").size().reindex(team_totals.index, fill_value=0)
    team_left = team_totals - team_so_far
    season_start = team_games.GAME_DATE.min()

    played = pg.groupby("PLAYER_ID").size()
    last = pg.sort_values("GAME_DATE").groupby("PLAYER_ID")[["TEAM_ID", "GAME_DATE"]].last()

    out = players[["PLAYER_ID"]].copy()
    out["played_so_far"] = out.PLAYER_ID.map(played).fillna(0)
    if len(last):
        out["team"] = out.PLAYER_ID.map(last.TEAM_ID)
        out["last_game"] = out.PLAYER_ID.map(last.GAME_DATE)
    else:  # nobody has played yet, e.g. on opening day
        out["team"] = None
        out["last_game"] = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns]")
    has_team = out.team.notna()
    # Team for schedule counts: the latest team played for, else the roster team if known.
    schedule_team = out.team if known_teams is None else out.team.fillna(out.PLAYER_ID.map(known_teams))
    knows_schedule = schedule_team.notna() & schedule_team.isin(team_totals.index)

    # Players who haven't played yet have no known team this season (offseason moves
    # aren't in the logs), so they get the league's typical schedule position.
    out["team_games_so_far"] = schedule_team.map(team_so_far).where(knows_schedule, team_so_far.median())
    out["team_games_left"] = schedule_team.map(team_left).where(knows_schedule, team_left.median())

    # Team games since the player's last appearance (all of them if no appearance yet).
    team_dates = tg.sort_values("GAME_DATE").groupby("TEAM_ID").GAME_DATE.apply(np.array)
    streak = []
    last10 = []
    for team, last_game in zip(out.team, out.last_game):
        if pd.isna(team):
            streak.append(np.nan)
            last10.append(np.nan)
            continue
        dates = team_dates.get(team, np.array([], dtype="datetime64[ns]"))
        streak.append(int((dates > np.datetime64(last_game)).sum()))
        last10.append(dates[-10:].min() if len(dates) else pd.NaT)
    out["absence_streak"] = streak
    out["absence_streak"] = out.absence_streak.fillna(out.team_games_so_far)

    # Share of the team's last 10 games the player played.
    recent_from = pd.to_datetime(pd.Series(last10, index=out.index, dtype="object"))
    recent = pg.merge(out[["PLAYER_ID", "team"]].assign(recent_from=recent_from), on="PLAYER_ID")
    recent = recent[(recent.TEAM_ID == recent.team) & (recent.GAME_DATE >= recent.recent_from)]
    recent_games = recent.groupby("PLAYER_ID").size()
    window = out.team_games_so_far.clip(upper=10)
    out["played_last10_share"] = (out.PLAYER_ID.map(recent_games).fillna(0) / window).where(window > 0)

    out["has_played"] = has_team.astype(int)
    out["missed_so_far"] = (out.team_games_so_far - out.played_so_far).clip(lower=0)
    out["share_so_far"] = (out.played_so_far / out.team_games_so_far).clip(upper=1).where(out.team_games_so_far > 0)
    out["season_progress"] = out.team_games_so_far / (out.team_games_so_far + out.team_games_left)
    days_from = out.last_game.fillna(season_start) if pd.notna(season_start) else out.last_game
    out["days_since_last_game"] = (date - days_from).dt.days.where(date > days_from, 0)

    preseason = players.set_index("PLAYER_ID")[["preseason_share", *FEATURES]]
    return out.drop(columns=["team", "last_game"]).join(preseason, on="PLAYER_ID")


def snapshot_dates(team_games: pd.DataFrame) -> list[pd.Timestamp]:
    """Opening day, then every SNAPSHOT_DAYS days while the season still has games left."""
    start, end = team_games.GAME_DATE.min(), team_games.GAME_DATE.max()
    return list(pd.date_range(start, end, freq=f"{SNAPSHOT_DAYS}D"))


def out_of_time_preseason_shares(table: pd.DataFrame) -> pd.Series:
    """Each player's preseason forecast share for every past season, made by a model
    trained only on seasons whose results were known before that season started.

    Rows are the preseason rows (season s-1) for target season s; the model for
    target season s is trained on rows up to season s-2, whose targets are season
    s-1 games. Index matches `table`.
    """
    labeled = table[~table.is_forecast]
    shares = pd.Series(np.nan, index=table.index)
    first_target = config.SEASONS.index(FIRST_SEASON)
    for target in range(first_target, labeled.season_idx.max() + 2):
        rows = labeled[labeled.season_idx == target - 1]
        train = labeled[labeled.season_idx <= target - 2]
        if rows.empty or train.empty:
            continue
        shares.loc[rows.index] = models.predict(models.fit("LightGBM", train), rows)
    return shares


def build_snapshots() -> pd.DataFrame:
    """Snapshots of every player through every past season, with labels."""
    table = load_table()
    table["preseason_share"] = out_of_time_preseason_shares(table)
    player_games = data.load("player_games")[["SEASON", "PLAYER_ID", "TEAM_ID", "GAME_DATE"]]
    team_games = data.load("team_games")[["SEASON", "TEAM_ID", "GAME_DATE"]]
    player_games["GAME_DATE"] = to_date(player_games.GAME_DATE)
    team_games["GAME_DATE"] = to_date(team_games.GAME_DATE)

    parts = []
    for season in config.SEASONS[config.SEASONS.index(FIRST_SEASON):]:
        idx = config.SEASONS.index(season)
        players = table[(table.season_idx == idx - 1) & ~table.is_forecast & table.preseason_share.notna()]
        if players.empty:
            continue
        pg = player_games[(player_games.SEASON == season) & player_games.PLAYER_ID.isin(players.PLAYER_ID)]
        tg = team_games[team_games.SEASON == season]
        totals = tg.groupby("TEAM_ID").size()
        for date in snapshot_dates(tg):
            snap = snapshot_features(pg, tg, totals, players, date)
            after = pg[pg.GAME_DATE >= date].groupby("PLAYER_ID").size()
            snap["games_after"] = snap.PLAYER_ID.map(after).fillna(0)
            snap["SEASON"], snap["date"] = season, date
            parts.append(snap[snap.team_games_left > 0])
    snaps = pd.concat(parts, ignore_index=True)
    snaps["target"] = (snaps.games_after / snaps.team_games_left).clip(upper=1)
    return snaps


def model(**params) -> lgb.LGBMRegressor:
    settings = dict(
        objective="l1", n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=100,
        subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=config.RANDOM_STATE, verbose=-1,
    )
    return lgb.LGBMRegressor(**(settings | params))


def fit(snaps: pd.DataFrame, **params) -> lgb.LGBMRegressor:
    return model(**params).fit(snaps[IN_SEASON_FEATURES], snaps.target, sample_weight=snaps.team_games_left)


def predict_rest(booster_or_model, snaps: pd.DataFrame) -> np.ndarray:
    """Predicted games still to come."""
    share = np.clip(booster_or_model.predict(snaps[IN_SEASON_FEATURES]), 0, 1)
    return share * snaps.team_games_left.to_numpy()


THIRDS = ["first third", "middle third", "last third"]


def season_third(progress) -> np.ndarray:
    """0, 1 or 2: which third of the season a snapshot falls in."""
    return np.minimum((np.asarray(progress, dtype=float) * 3).astype(int), 2)


def fit_range(snaps: pd.DataFrame, **params) -> tuple:
    """Quantile models for the low and high ends of the rest-of-season share."""
    return tuple(
        model(**(params | {"objective": "quantile", "alpha": a})).fit(
            snaps[IN_SEASON_FEATURES], snaps.target, sample_weight=snaps.team_games_left
        )
        for a in (intervals.LOW, intervals.HIGH)
    )


def range_adjustments(range_models, val: pd.DataFrame) -> list[float]:
    """Conformal correction (in share of games left) for each third of the season.

    Early-season outcomes are much more uncertain, so each third gets its own
    correction; that keeps ranges honest (and wide) when few games have been played.
    """
    low, high = (m.predict(val[IN_SEASON_FEATURES]) for m in range_models)
    third = season_third(val.season_progress)
    return [intervals.conformal_adjustment(low[third == t], high[third == t], val.target[third == t]) for t in range(3)]


def predict_range(range_models, adjustments, point_rest: np.ndarray, snaps: pd.DataFrame):
    """Likely range of games still to come: quantile models + per-third correction, tidied."""
    left = snaps.team_games_left.to_numpy()
    adj = np.asarray(adjustments)[season_third(snaps.season_progress)]
    low, high = (np.asarray(m.predict(snaps[IN_SEASON_FEATURES])) for m in range_models)
    return intervals.tidy((low - adj) * left, point_rest, (high + adj) * left, floor=0, ceiling=left)


def range_groups(snaps: pd.DataFrame) -> dict:
    third = season_third(snaps.season_progress)
    return {
        "all": np.ones(len(snaps), bool),
        **{name: third == t for t, name in enumerate(THIRDS)},
        f"currently out ({OUT_STREAK_GAMES}+ games)": ((snaps.has_played == 1) & (snaps.absence_streak >= OUT_STREAK_GAMES)).to_numpy(),
        "hasn't played yet": (snaps.has_played == 0).to_numpy(),
    }


# Baselines for the rest of the season, in games.
def baseline_preseason(snaps):
    """The preseason forecast share, applied to the games left."""
    return snaps.preseason_share.to_numpy() * snaps.team_games_left.to_numpy()


def baseline_pace(snaps):
    """Keep playing at the current rate (preseason share before any team games)."""
    share = snaps.share_so_far.fillna(snaps.preseason_share)
    return share.to_numpy() * snaps.team_games_left.to_numpy()


def baseline_blend(snaps, k: float):
    """Current pace and preseason share, trusting the pace more as games pile up."""
    w = snaps.team_games_so_far / (snaps.team_games_so_far + k)
    share = w * snaps.share_so_far.fillna(0) + (1 - w) * snaps.preseason_share
    return share.to_numpy() * snaps.team_games_left.to_numpy()


def scorecard(snaps: pd.DataFrame, preds: dict[str, np.ndarray]) -> dict:
    """MAE in rest-of-season games by method, overall and by group."""
    err = {name: np.abs(p - snaps.games_after.to_numpy()) for name, p in preds.items()}
    progress = snaps.season_progress
    groups = {
        "all": np.ones(len(snaps), bool),
        "first third of season": (progress < 1 / 3).to_numpy(),
        "middle third": ((progress >= 1 / 3) & (progress < 2 / 3)).to_numpy(),
        "last third": (progress >= 2 / 3).to_numpy(),
        f"currently out ({OUT_STREAK_GAMES}+ games)": ((snaps.has_played == 1) & (snaps.absence_streak >= OUT_STREAK_GAMES)).to_numpy(),
    }
    return {
        g: {"n": int(m.sum()), **{name: float(e[m].mean()) for name, e in err.items()}}
        for g, m in groups.items() if m.any()
    }


def evaluate_methods(train: pd.DataFrame, test: pd.DataFrame, k: float, **params) -> dict:
    m = fit(train, **params)
    return scorecard(test, {
        "Preseason forecast, pro-rated": baseline_preseason(test),
        "Current pace": baseline_pace(test),
        "Blend of pace and preseason": baseline_blend(test, k),
        "Rest-of-season model": predict_rest(m, test),
    })


def tune(snaps: pd.DataFrame) -> tuple[float, dict]:
    """Choose the blend baseline's k and the model settings on the validation season."""
    train = snaps[snaps.SEASON < VALIDATION_SEASON]
    val = snaps[snaps.SEASON == VALIDATION_SEASON]
    best_k = min([5, 10, 20, 40], key=lambda k: np.abs(baseline_blend(val, k) - val.games_after).mean())
    grid = [dict(num_leaves=nl, min_child_samples=mc, n_estimators=ne)
            for nl in (15, 31) for mc in (100, 300) for ne in (300, 600)]
    scores = [(np.abs(predict_rest(fit(train, **g), val) - val.games_after).mean(), i) for i, g in enumerate(grid)]
    best = grid[min(scores)[1]]
    print(f"Validation {VALIDATION_SEASON}: blend k={best_k}, model {best} "
          f"(MAE {min(scores)[0]:.2f} games; grid {min(s for s, _ in scores):.2f}-{max(s for s, _ in scores):.2f})")
    return best_k, best


def print_scorecard(card: dict):
    methods = [k for k in next(iter(card.values())) if k != "n"]
    print(f"{'Group':32s} {'n':>7s} " + " ".join(f"{m[:22]:>23s}" for m in methods))
    for group, row in card.items():
        print(f"{group:32s} {row['n']:7d} " + " ".join(f"{row[m]:23.2f}" for m in methods))


def predict_current(models_dir=config.MODELS_DIR) -> pd.DataFrame | None:
    """Today's rest-of-season forecast for every player with a preseason forecast.

    Uses the saved model, the frozen preseason forecasts and this season's game logs.
    Returns None if the model or the logs aren't available.
    """
    from next82.preseason import load_forecasts

    path = models_dir / MODEL_PATH.name
    logs = data.saved_season_logs()
    if not path.exists() or logs is None:
        return None
    player_games, team_games = logs
    player_games = player_games.assign(GAME_DATE=to_date(player_games.GAME_DATE))
    team_games = team_games.assign(GAME_DATE=to_date(team_games.GAME_DATE))
    forecasts = load_forecasts()
    players = forecasts.assign(preseason_share=forecasts.pred_share)

    teams = data.saved_rosters()
    team_ids = pd.Index(teams.TEAM_ID.unique() if teams is not None else team_games.TEAM_ID.unique())
    totals = pd.Series(config.REGULAR_SEASON_GAMES, index=team_ids)
    # The snapshot is the day after the latest finished game, so it uses every result we have.
    date = team_games.GAME_DATE.max() + pd.Timedelta(days=1) if len(team_games) else pd.Timestamp.today().normalize()
    roster_teams = teams.set_index("PLAYER_ID").TEAM_ID if teams is not None else None
    snap = snapshot_features(player_games, team_games, totals, players, date, known_teams=roster_teams)
    booster = lgb.Booster(model_file=str(path))
    snap["predicted_rest"] = np.clip(booster.predict(snap[IN_SEASON_FEATURES]), 0, 1) * snap.team_games_left
    snap["updated_total"] = snap.played_so_far + snap.predicted_rest
    range_paths = [models_dir / p.name for p in RANGE_MODEL_PATHS]
    if all(p.exists() for p in range_paths) and METRICS_PATH.exists():
        adjustments = json.loads((models_dir / METRICS_PATH.name).read_text())["range_adjustments"]
        range_models = [lgb.Booster(model_file=str(p)) for p in range_paths]
        low, high = predict_range(range_models, adjustments, snap.predicted_rest.to_numpy(), snap)
        snap["updated_low"] = snap.played_so_far + low
        snap["updated_high"] = snap.played_so_far + high
    snap["as_of"] = date - pd.Timedelta(days=1)
    return snap


def main():
    snaps = build_snapshots()
    snaps.to_parquet(SNAPSHOTS_PATH, index=False)
    print(f"Snapshots: {len(snaps):,} rows, {snaps.SEASON.nunique()} seasons, every {SNAPSHOT_DAYS} days\n")

    k, params = tune(snaps)
    train = snaps[snaps.SEASON < TEST_SEASONS[0]]
    test = snaps[snaps.SEASON.isin(TEST_SEASONS)]
    card = evaluate_methods(train, test, k, **params)
    print(f"\nTest seasons {' and '.join(TEST_SEASONS)}: average miss in rest-of-season games")
    print_scorecard(card)

    # Likely ranges: corrections measured on the validation season, coverage checked on test.
    val_train, val = snaps[snaps.SEASON < VALIDATION_SEASON], snaps[snaps.SEASON == VALIDATION_SEASON]
    adjustments = range_adjustments(fit_range(val_train, **params), val)
    range_models = fit_range(train, **params)
    raw_low, raw_high = (m.predict(test[IN_SEASON_FEATURES]) for m in range_models)
    low, high = predict_range(range_models, adjustments, predict_rest(fit(train, **params), test), test)
    calibration = intervals.calibration_table(low, high, test.games_after, range_groups(test))
    print(f"\nRange corrections per third (share of games left): {', '.join(f'{a:+.3f}' for a in adjustments)}; "
          f"low above high before tidying: {int((raw_low > raw_high).sum())} of {len(test)}")
    intervals.print_calibration(f"Rest-of-season ranges, test seasons {' and '.join(TEST_SEASONS)}", calibration)

    final = fit(snaps, **params)
    config.MODELS_DIR.mkdir(exist_ok=True)
    final.booster_.save_model(str(MODEL_PATH))
    for m, path in zip(fit_range(snaps, **params), RANGE_MODEL_PATHS):
        m.booster_.save_model(str(path))
    METRICS_PATH.write_text(json.dumps({
        "snapshot_days": SNAPSHOT_DAYS, "validation_season": VALIDATION_SEASON, "test_seasons": TEST_SEASONS,
        "blend_k": k, "params": params, "test": card,
        "range_adjustments": adjustments, "range_calibration": calibration,
    }, indent=2))
    print(f"\nSaved {MODEL_PATH.relative_to(config.ROOT)} (trained on all {snaps.SEASON.nunique()} seasons)")


if __name__ == "__main__":
    main()
