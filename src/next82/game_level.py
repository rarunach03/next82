"""Game-by-game availability (beta): the chance each player plays each team game.

The season-level forecasts stay the site's main numbers. This model predicts, for one
team game at a time, whether a player on that team plays (logs a game) or not.

Rows. Game logs list only games played, so missed games come from each team's
schedule. A player's stint with a team starts at his first appearance for it (that
game is history only, never a row: it's in the data because he played) and lasts until
he appears for another team, or the season ends. Every team game in between is a row,
labeled played (1) or not (0). So a row for a team on a date exists exactly when the
player's latest earlier game was for that team: nothing after the game decides which
rows exist. Waived players and players out for the season stay on their last team as
misses. Trade dates aren't in the logs, so a traded player's team games between his
last game for the old team and his first for the new one count as misses for the old
team, though he may already have left (counted in the metrics as label noise).

Features use only what's known before each game: the player's own games before that
date, his team's results before it, and the schedule (known in advance). The injury
report is not an input (there's no history of it for training); on the site, a live
"Out" listing or an expected return date overrides the model (`apply_injury_status`).

Past seasons' "schedule" is the games actually played, so in 2019-20 (a training season)
games left reflect the COVID-shortened season; no test or calibration season is affected.

Seasons match the in-season model: train up to 2022-23, calibrate on 2023-24 (isotonic),
test on 2024-25 and 2025-26. The preseason model's 15.6-game average miss is measured
on the same two seasons.

Usage:
    python -m next82.game_level     # build rows, train, calibrate, run the quality gates, save
"""
import json

import lightgbm as lgb
import numpy as np
import pandas as pd

from next82 import config, data, in_season
from next82.features import load_table

ROWS_PATH = config.PROCESSED_DIR / "game_level_rows.parquet"
MODEL_PATH = config.MODELS_DIR / "game_level.txt"
METRICS_PATH = config.MODELS_DIR / "game_level_metrics.json"
CHART_PATH = config.MODELS_DIR / "game_level_calibration.png"

FIRST_SEASON = in_season.FIRST_SEASON
VALIDATION_SEASON = in_season.VALIDATION_SEASON
TEST_SEASONS = in_season.TEST_SEASONS

FEATURES = [
    # Rest and schedule.
    "rest_days",
    "b2b_second",
    "b2b_first",
    "games_last7",
    "days_into_season",
    "team_games_left",
    # Recent availability with the current team.
    "missed_last5",
    "missed_last10",
    "missed_last20",
    "missed_streak",
    "stint_games",
    "played_rate",
    # Role and history.
    "mpg_recent",
    "mpg_season",
    "mpg_last",
    "gp_share_last",
    "age",
]

PARAMS = dict(
    objective="binary", n_estimators=400, learning_rate=0.05, num_leaves=31, min_child_samples=200,
    subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=config.RANDOM_STATE, verbose=-1,
)

# Probability used for games a player is ruled out of by the injury report or a return date.
OUT_PROBABILITY = 0.02

# Quality gates (all must pass for the site to show the beta).
MAX_ECE = 0.05
SEASON_MAE_ALLOWANCE = 1.0
# Better than this is implausible for game-by-game availability: treat as likely leakage.
MAX_PLAUSIBLE_ACCURACY = 0.97
MAX_PLAUSIBLE_AUC = 0.98


def to_date(values: pd.Series) -> pd.Series:
    return in_season.to_date(values)


# ---------------------------------------------------------------- rows and features


def stint_rows(player_games: pd.DataFrame, team_games: pd.DataFrame) -> pd.DataFrame:
    """Every team game of every stint, first appearance included (flagged `first`).

    player_games: PLAYER_ID, TEAM_ID, GAME_DATE (one season, games played).
    team_games:   TEAM_ID, GAME_ID, GAME_DATE (the season's team games).
    Returns PLAYER_ID, TEAM_ID, GAME_ID, GAME_DATE, stint, first, played, sorted by stint and date.
    """
    pg = player_games.sort_values(["PLAYER_ID", "GAME_DATE"]).reset_index(drop=True)
    new_run = (pg.PLAYER_ID != pg.PLAYER_ID.shift()) | (pg.TEAM_ID != pg.TEAM_ID.shift())
    pg["stint"] = new_run.cumsum()
    runs = pg.groupby("stint").agg(PLAYER_ID=("PLAYER_ID", "first"), TEAM_ID=("TEAM_ID", "first"),
                                   start=("GAME_DATE", "min"))
    # A stint ends when the same player's next stint (with another team) starts.
    runs["end"] = runs.groupby("PLAYER_ID").start.shift(-1)
    rows = runs.reset_index().merge(team_games[["TEAM_ID", "GAME_ID", "GAME_DATE"]], on="TEAM_ID")
    rows = rows[(rows.GAME_DATE >= rows.start) & (rows.end.isna() | (rows.GAME_DATE < rows.end))]
    played = pg[["PLAYER_ID", "TEAM_ID", "GAME_DATE"]].assign(played=1)
    rows = rows.merge(played, on=["PLAYER_ID", "TEAM_ID", "GAME_DATE"], how="left")
    rows["played"] = rows.played.fillna(0).astype(int)
    rows["first"] = rows.GAME_DATE == rows.start
    return rows.drop(columns=["start", "end"]).sort_values(["stint", "GAME_DATE"]).reset_index(drop=True)


def _stint_history(rows: pd.DataFrame) -> pd.DataFrame:
    """Features from the stint's earlier team games (rows sorted by stint and date)."""
    k = rows.groupby("stint").cumcount()  # earlier team games in the stint
    missed = 1 - rows.played
    missed_before = missed.groupby(rows.stint).cumsum() - missed
    out = pd.DataFrame(index=rows.index)
    out["stint_games"] = k
    played_before = rows.played.groupby(rows.stint).cumsum() - rows.played
    out["played_rate"] = played_before / k.where(k > 0)
    for n in (5, 10, 20):
        # Missed among the previous n stint games: missed before now minus missed before n games ago.
        ago = missed_before.groupby(rows.stint).shift(n).fillna(0)
        out[f"missed_last{n}"] = missed_before - ago
    # Team games since the last game played in the stint.
    pos = k.where(rows.played == 1)
    last_played_pos = pos.groupby(rows.stint).shift(1)
    last_played_pos = last_played_pos.groupby(rows.stint).ffill()
    out["missed_streak"] = k - last_played_pos - 1
    return out


def _player_history(rows: pd.DataFrame, player_games: pd.DataFrame) -> pd.DataFrame:
    """Features from the player's own games (any team) strictly before each row's date."""
    pg = player_games[["PLAYER_ID", "GAME_DATE", "MIN"]].sort_values(["PLAYER_ID", "GAME_DATE"]).reset_index(drop=True)
    pg["MIN"] = pd.to_numeric(pg.MIN, errors="coerce")
    by = pg.groupby("PLAYER_ID")
    pg["n_games"] = by.cumcount() + 1
    pg["mpg_recent"] = by.MIN.transform(lambda s: s.rolling(5, min_periods=1).mean())
    pg["mpg_season"] = by.MIN.cumsum() / pg.n_games
    pg["last_game"] = pg.GAME_DATE

    q = rows[["PLAYER_ID", "GAME_DATE"]].reset_index().sort_values("GAME_DATE")
    before = pd.merge_asof(q, pg.sort_values("GAME_DATE"), on="GAME_DATE", by="PLAYER_ID", allow_exact_matches=False,
                           suffixes=("", "_pg"))
    week = q.assign(GAME_DATE=q.GAME_DATE - pd.Timedelta(days=7))
    week = pd.merge_asof(week.sort_values("GAME_DATE"), pg[["PLAYER_ID", "GAME_DATE", "n_games"]].sort_values("GAME_DATE"),
                         on="GAME_DATE", by="PLAYER_ID", allow_exact_matches=False)
    before = before.set_index("index")
    week = week.set_index("index")
    out = pd.DataFrame(index=rows.index)
    out["rest_days"] = (rows.GAME_DATE - before.last_game.reindex(rows.index)).dt.days
    out["games_last7"] = before.n_games.reindex(rows.index).fillna(0) - week.n_games.reindex(rows.index).fillna(0)
    out["mpg_recent"] = before.mpg_recent.reindex(rows.index)
    out["mpg_season"] = before.mpg_season.reindex(rows.index)
    return out


def _schedule(rows: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    """Schedule features (known in advance): back-to-backs, days into the season, team games left."""
    sched = schedule[["TEAM_ID", "GAME_DATE"]].drop_duplicates()
    days = set(zip(sched.TEAM_ID, sched.GAME_DATE))
    sched = sched.sort_values(["TEAM_ID", "GAME_DATE"])
    left = sched.assign(left=sched.groupby("TEAM_ID").cumcount(ascending=False))
    out = pd.DataFrame(index=rows.index)
    one = pd.Timedelta(days=1)
    out["b2b_second"] = [int((t, d - one) in days) for t, d in zip(rows.TEAM_ID, rows.GAME_DATE)]
    out["b2b_first"] = [int((t, d + one) in days) for t, d in zip(rows.TEAM_ID, rows.GAME_DATE)]
    out["days_into_season"] = (rows.GAME_DATE - sched.GAME_DATE.min()).dt.days
    out["team_games_left"] = rows.merge(left, on=["TEAM_ID", "GAME_DATE"], how="left")["left"].to_numpy()
    return out


def prior_season(table: pd.DataFrame, season: str) -> pd.DataFrame:
    """Last season's facts for each player, as known before `season` starts: age (a year on),
    minutes per game and share of team games played."""
    prev = config.SEASONS[config.SEASONS.index(season) - 1] if season in config.SEASONS else config.SEASONS[-1]
    rows = table[table.SEASON == prev]
    return pd.DataFrame({
        "PLAYER_ID": rows.PLAYER_ID.to_numpy(),
        "age": (rows.age + 1).to_numpy(),
        "mpg_last": rows.mpg.to_numpy(),
        "gp_share_last": rows.gp_share.to_numpy(),
    }).drop_duplicates("PLAYER_ID")


def season_rows(player_games: pd.DataFrame, team_games: pd.DataFrame, priors: pd.DataFrame) -> pd.DataFrame:
    """Labeled rows with features for one season (first appearances dropped)."""
    rows = stint_rows(player_games, team_games)
    rows = rows.join(_stint_history(rows)).join(_player_history(rows, player_games)).join(_schedule(rows, team_games))
    rows = rows.merge(priors, on="PLAYER_ID", how="left")
    return rows[~rows["first"]].drop(columns=["first"]).reset_index(drop=True)


def trade_gap_games(player_games: pd.DataFrame, team_games: pd.DataFrame) -> int:
    """Old-team games between a traded player's last game there and his first for the next team
    (rows labeled missed, though he may already have left)."""
    pg = player_games.sort_values(["PLAYER_ID", "GAME_DATE"])
    nxt = pg.groupby("PLAYER_ID")[["TEAM_ID", "GAME_DATE"]].shift(-1)
    moves = pg[nxt.TEAM_ID.notna() & (nxt.TEAM_ID != pg.TEAM_ID)].assign(next_date=nxt.GAME_DATE)
    counts = 0
    for team, last, nxt_date in zip(moves.TEAM_ID, moves.GAME_DATE, moves.next_date):
        t = team_games[team_games.TEAM_ID == team]
        counts += int(((t.GAME_DATE > last) & (t.GAME_DATE < nxt_date)).sum())
    return counts


def build_rows() -> tuple[pd.DataFrame, dict]:
    """Labeled rows for every season from FIRST_SEASON on, plus counts for the metrics."""
    table = load_table()
    player_games = data.load("player_games")[["SEASON", "PLAYER_ID", "TEAM_ID", "GAME_ID", "GAME_DATE", "MIN"]]
    team_games = data.load("team_games")[["SEASON", "TEAM_ID", "GAME_ID", "GAME_DATE"]]
    player_games["GAME_DATE"] = to_date(player_games.GAME_DATE)
    team_games["GAME_DATE"] = to_date(team_games.GAME_DATE)
    parts, gaps = [], 0
    for season in config.SEASONS[config.SEASONS.index(FIRST_SEASON):]:
        pg = player_games[player_games.SEASON == season]
        tg = team_games[team_games.SEASON == season]
        rows = season_rows(pg, tg, prior_season(table, season))
        rows["SEASON"] = season
        parts.append(rows)
        gaps += trade_gap_games(pg, tg)
        print(f"  {season}: {len(rows):,} rows, {rows.played.mean():.1%} played")
    rows = pd.concat(parts, ignore_index=True)
    return rows, {"rows": int(len(rows)), "trade_gap_games": int(gaps)}


def features_as_of(player_games: pd.DataFrame, schedule: pd.DataFrame, priors: pd.DataFrame, player: int, team: int,
                   date: pd.Timestamp) -> dict | None:
    """Features for one player and one game of `team` on `date`, straight from the logs.

    Only the player's games before `date` are read; the schedule (known in advance) gives
    the team's game dates. Written separately from the table code above, so tests can
    check one against the other, and used for live predictions. None if the player has
    no stint with `team` yet (no appearance for it, or he played for another team since).
    """
    past = player_games[(player_games.PLAYER_ID == player) & (player_games.GAME_DATE < date)].sort_values("GAME_DATE")
    if past.empty or past.TEAM_ID.iloc[-1] != team:
        return None
    # The stint: the latest unbroken run of games for this team.
    other = past[past.TEAM_ID != team]
    run = past[past.GAME_DATE > other.GAME_DATE.max()] if len(other) else past
    start = run.GAME_DATE.min()
    team_dates = schedule.loc[schedule.TEAM_ID == team, "GAME_DATE"].drop_duplicates().sort_values()
    history = team_dates[(team_dates >= start) & (team_dates < date)]
    played_dates = set(run.GAME_DATE)
    played = np.array([d in played_dates for d in history])
    missed = ~played
    streak = 0
    for p in played[::-1]:
        if p:
            break
        streak += 1
    minutes = pd.to_numeric(past.MIN, errors="coerce")
    one = pd.Timedelta(days=1)
    dates = set(team_dates)
    prior = priors[priors.PLAYER_ID == player]
    pick = (lambda c: float(prior[c].iloc[0]) if len(prior) else np.nan)
    return {
        "rest_days": (date - past.GAME_DATE.iloc[-1]).days,
        "b2b_second": int(date - one in dates),
        "b2b_first": int(date + one in dates),
        "games_last7": int((past.GAME_DATE >= date - pd.Timedelta(days=7)).sum()),
        "days_into_season": (date - schedule.GAME_DATE.min()).days,
        "team_games_left": int((team_dates > date).sum()),
        "missed_last5": int(missed[-5:].sum()),
        "missed_last10": int(missed[-10:].sum()),
        "missed_last20": int(missed[-20:].sum()),
        "missed_streak": streak,
        "stint_games": len(history),
        "played_rate": float(played.mean()) if len(history) else np.nan,
        "mpg_recent": float(minutes.iloc[-5:].mean()),
        "mpg_season": float(minutes.mean()),
        "mpg_last": pick("mpg_last"),
        "gp_share_last": pick("gp_share_last"),
        "age": pick("age"),
    }


# ---------------------------------------------------------------- model, calibration, quality gates


def split(rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Train (before the validation season), validation (calibration), test."""
    order = {s: i for i, s in enumerate(config.SEASONS)}
    idx = rows.SEASON.map(order)
    val_idx = order[VALIDATION_SEASON]
    return rows[idx < val_idx], rows[idx == val_idx], rows[rows.SEASON.isin(TEST_SEASONS)]


def fit(train: pd.DataFrame) -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(**PARAMS).fit(train[FEATURES], train.played)


def raw_probability(model, rows: pd.DataFrame) -> np.ndarray:
    return model.predict_proba(rows[FEATURES])[:, 1]


def fit_calibration(raw: np.ndarray, played: np.ndarray) -> dict:
    """Isotonic calibration (fit on the validation season), stored as interpolation points."""
    from sklearn.isotonic import IsotonicRegression

    iso = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(raw, played)
    return {"x": [float(v) for v in iso.X_thresholds_], "y": [float(v) for v in iso.y_thresholds_]}


def calibrated(raw: np.ndarray, calibration: dict) -> np.ndarray:
    return np.clip(np.interp(raw, calibration["x"], calibration["y"]), 0, 1)


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def calibration_bins(p: np.ndarray, y: np.ndarray, n: int = 10) -> list[dict]:
    """Equal-width bins: average predicted vs. share that played."""
    edges = np.linspace(0, 1, n + 1)
    which = np.clip(np.digitize(p, edges) - 1, 0, n - 1)
    out = []
    for b in range(n):
        m = which == b
        if m.any():
            out.append({"from": float(edges[b]), "to": float(edges[b + 1]), "n": int(m.sum()),
                        "predicted": float(p[m].mean()), "actual": float(y[m].mean())})
    return out


def ece(p: np.ndarray, y: np.ndarray, n: int = 10) -> float:
    """Expected calibration error: the gap between predicted and actual, weighted by bin size."""
    bins = calibration_bins(p, y, n)
    return float(sum(b["n"] * abs(b["predicted"] - b["actual"]) for b in bins) / len(p))


def auc(p: np.ndarray, y: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score

    return float(roc_auc_score(y, p))


def baseline_rate_so_far(rows: pd.DataFrame) -> np.ndarray:
    """(a) The player's play rate so far this season with his team, smoothed: (played + 1) / (games + 2)."""
    played = (rows.played_rate * rows.stint_games).fillna(0)
    return ((played + 1) / (rows.stint_games + 2)).to_numpy()


def baseline_last_season(rows: pd.DataFrame, fallback: float) -> np.ndarray:
    """(b) The player's share of team games played last season (the training play rate if he had none)."""
    return rows.gp_share_last.fillna(fallback).clip(0.01, 0.99).to_numpy()


def season_totals(rows: pd.DataFrame, p: np.ndarray) -> pd.DataFrame:
    """Per player and season: games played in the rows vs. the sum of each game's probability
    (each made the day before). Games outside the rows (first appearances) match on both sides."""
    t = rows[["SEASON", "PLAYER_ID", "played"]].assign(p=p)
    return t.groupby(["SEASON", "PLAYER_ID"]).agg(actual=("played", "sum"), predicted=("p", "sum")).reset_index()


def season_model_mae() -> float:
    """The preseason model's average miss on the test seasons (models/metrics.json)."""
    m = json.loads((config.MODELS_DIR / "metrics.json").read_text())
    return float(m["results"][m["final_model"]]["mae_all"])


def leakage_mismatches(rows: pd.DataFrame, n: int = 400, seed: int = 0) -> int:
    """Recompute features for a sample of rows from the raw logs, using only games before
    each row's date (features_as_of), and count rows where anything differs."""
    table = load_table()
    sample = rows.sample(min(n, len(rows)), random_state=seed)
    bad = 0
    for season, part in sample.groupby("SEASON"):
        pg = data.load("player_games", [season])[["PLAYER_ID", "TEAM_ID", "GAME_ID", "GAME_DATE", "MIN"]]
        tg = data.load("team_games", [season])[["TEAM_ID", "GAME_ID", "GAME_DATE"]]
        pg["GAME_DATE"], tg["GAME_DATE"] = to_date(pg.GAME_DATE), to_date(tg.GAME_DATE)
        priors = prior_season(table, season)
        for r in part.itertuples():
            ref = features_as_of(pg, tg, priors, r.PLAYER_ID, r.TEAM_ID, r.GAME_DATE)
            if ref is None or any(
                not ((pd.isna(getattr(r, f)) and pd.isna(ref[f])) or abs(getattr(r, f) - ref[f]) < 1e-9) for f in FEATURES
            ):
                bad += 1
    return bad


def is_healthy_rotation(rows: pd.DataFrame) -> pd.Series:
    """Rotation players playing every game lately: 20+ minutes, no misses in the last 10 team games."""
    return (rows.mpg_recent >= 20) & (rows.mpg_last >= config.ROTATION_MIN_MPG) & (rows.missed_last10 == 0) & (rows.stint_games >= 10)


def evaluate(rows: pd.DataFrame) -> tuple[lgb.LGBMClassifier, dict, dict]:
    """Train, calibrate, test and run every quality gate. Returns model, calibration, metrics."""
    train, val, test = split(rows)
    model = fit(train)
    calibration = fit_calibration(raw_probability(model, val), val.played.to_numpy())
    p = calibrated(raw_probability(model, test), calibration)
    y = test.played.to_numpy()
    p_val = calibrated(raw_probability(model, val), calibration)

    base_a = baseline_rate_so_far(test)
    base_b = baseline_last_season(test, float(train.played.mean()))
    totals = season_totals(test, p)
    # Same players as the season model's test: those with a preseason forecast (a season before).
    table = load_table()
    forecast_players = set(zip(table.SEASON.map(lambda s: config.SEASONS[config.SEASONS.index(s) + 1]
                                                if config.SEASONS.index(s) + 1 < len(config.SEASONS) else None),
                               table.PLAYER_ID))
    in_pop = [(s, pid) in forecast_players for s, pid in zip(totals.SEASON, totals.PLAYER_ID)]
    totals_pop = totals[in_pop]
    season_mae = float((totals_pop.predicted - totals_pop.actual).abs().mean())
    reference_mae = season_model_mae()
    healthy = is_healthy_rotation(test).to_numpy()
    accuracy = float(((p >= 0.5) == (y == 1)).mean())

    results = {
        "test": {
            "rows": int(len(test)), "played_share": float(y.mean()),
            "log_loss": log_loss(p, y), "log_loss_rate_so_far": log_loss(base_a, y),
            "log_loss_last_season": log_loss(base_b, y),
            "ece": ece(p, y), "ece_uncalibrated": ece(raw_probability(model, test), y),
            "accuracy": accuracy, "auc": auc(p, y),
            "season_total_mae": season_mae, "season_total_players": int(len(totals_pop)),
            "season_model_mae": reference_mae,
            "healthy_rotation_mean": float(p[healthy].mean()), "healthy_rotation_rows": int(healthy.sum()),
            "calibration": calibration_bins(p, y),
        },
        "validation": {"log_loss": log_loss(p_val, val.played.to_numpy()), "ece": ece(p_val, val.played.to_numpy())},
    }
    leaks = leakage_mismatches(pd.concat([train.sample(200, random_state=1), test.sample(200, random_state=2)]))
    seasons = {"train": sorted(train.SEASON.unique()), "calibration": sorted(val.SEASON.unique()), "test": TEST_SEASONS}
    t = results["test"]
    gates = {
        "leakage": {"passed": leaks == 0 and not set(TEST_SEASONS) & set(seasons["train"] + seasons["calibration"]),
                    "value": leaks, "detail": "rows whose features differ when recomputed from earlier games only"},
        "beats_baselines": {"passed": t["log_loss"] < min(t["log_loss_rate_so_far"], t["log_loss_last_season"]),
                            "value": t["log_loss"],
                            "detail": f"vs. {t['log_loss_rate_so_far']:.4f} (rate so far), {t['log_loss_last_season']:.4f} (last season)"},
        "calibration": {"passed": t["ece"] < MAX_ECE, "value": t["ece"], "detail": f"expected calibration error < {MAX_ECE}"},
        "season_consistency": {"passed": season_mae <= reference_mae + SEASON_MAE_ALLOWANCE, "value": season_mae,
                               "detail": f"average miss of summed probabilities vs. {reference_mae:.1f} + {SEASON_MAE_ALLOWANCE}"},
        "sanity": {"passed": bool(((p >= 0) & (p <= 1)).all()) and t["healthy_rotation_mean"] >= 0.85,
                   "value": t["healthy_rotation_mean"], "detail": "probabilities in [0, 1]; healthy rotation players average 0.85+"},
        "plausible": {"passed": accuracy <= MAX_PLAUSIBLE_ACCURACY and t["auc"] <= MAX_PLAUSIBLE_AUC,
                      "value": accuracy, "detail": f"accuracy <= {MAX_PLAUSIBLE_ACCURACY}, AUC <= {MAX_PLAUSIBLE_AUC} (better suggests leakage)"},
    }
    metrics = {
        "seasons": seasons, "features": FEATURES, "params": {k: v for k, v in PARAMS.items() if k != "verbose"},
        "calibration_points": calibration, **results, "gates": gates,
        "all_passed": all(g["passed"] for g in gates.values()),
    }
    return model, calibration, metrics


def save_chart(bins: list[dict], path=CHART_PATH):
    """Reliability chart: predicted chance vs. share that played, on the test seasons."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(4.5, 4.5), dpi=120)
    ax.plot([0, 1], [0, 1], color="#9aa3af", lw=1, ls="--", label="Perfect calibration")
    ax.plot([b["predicted"] for b in bins], [b["actual"] for b in bins], color="#ff7a1a", lw=2, marker="o", ms=5,
            label="Next82 (test seasons)")
    ax.set_xlabel("Predicted chance of playing")
    ax.set_ylabel("Share of games actually played")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(loc="upper left", frameon=False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main():
    print("Building player-game rows")
    rows, counts = build_rows()
    ROWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows.to_parquet(ROWS_PATH, index=False)
    model, calibration, metrics = evaluate(rows)
    metrics["counts"] = counts
    model.booster_.save_model(str(MODEL_PATH))
    METRICS_PATH.write_text(json.dumps(metrics, indent=2, default=float) + "\n")
    save_chart(metrics["test"]["calibration"])
    t = metrics["test"]
    print(f"\nTest seasons {' and '.join(TEST_SEASONS)}: {t['rows']:,} rows, {t['played_share']:.1%} played")
    print(f"  log loss {t['log_loss']:.4f} vs. {t['log_loss_rate_so_far']:.4f} (rate so far), "
          f"{t['log_loss_last_season']:.4f} (last season)")
    print(f"  ECE {t['ece']:.4f} (uncalibrated {t['ece_uncalibrated']:.4f}); accuracy {t['accuracy']:.3f}, AUC {t['auc']:.3f}")
    print(f"  season totals: average miss {t['season_total_mae']:.2f} games ({t['season_total_players']} players) "
          f"vs. season model {t['season_model_mae']:.1f}")
    for name, g in metrics["gates"].items():
        print(f"  {'PASS' if g['passed'] else 'FAIL'} {name}: {g['value']} ({g['detail']})")
    print(f"All gates passed: {metrics['all_passed']}")


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------- live predictions (daily refresh)

# Features that come from the schedule alone; the rest describe the player as of today.
SCHEDULE_FEATURES = ["b2b_second", "b2b_first", "days_into_season", "team_games_left"]


def load_model() -> tuple[lgb.Booster, dict, dict]:
    """The saved model, its calibration and metrics (raises if missing)."""
    metrics = json.loads(METRICS_PATH.read_text())
    return lgb.Booster(model_file=str(MODEL_PATH)), metrics["calibration_points"], metrics


def live_schedule(finished: pd.DataFrame, schedule: pd.DataFrame, data_day: pd.Timestamp,
                  today: pd.Timestamp) -> tuple[pd.DataFrame, pd.Timestamp]:
    """The schedule the live predictions use, and the first day they predict.

    History is the finished games only. A scheduled game before that day which isn't
    final (in progress when the stats were fetched, or postponed) is left out: counted
    as history, every player on the team would look like he missed it. Upcoming games
    start the day after the latest finished game, or today if the stats are older, so a
    game already played never shows as upcoming.
    finished, schedule: TEAM_ID, GAME_ID, GAME_DATE (dates normalized).
    """
    first = max(pd.Timestamp(data_day).normalize(), pd.Timestamp(today).normalize())
    cols = ["TEAM_ID", "GAME_ID", "GAME_DATE"]
    upcoming = schedule.loc[(schedule.GAME_DATE >= first) & ~schedule.GAME_ID.isin(finished.GAME_ID), cols]
    return pd.concat([finished[cols], upcoming]).drop_duplicates(["TEAM_ID", "GAME_ID"]), first


def upcoming_rows(player_games: pd.DataFrame, schedule: pd.DataFrame, priors: pd.DataFrame, teams: pd.Series,
                  today: pd.Timestamp, last_date: pd.Timestamp, min_games: int = 5) -> pd.DataFrame:
    """Feature rows for each rostered player's upcoming team games: the next `min_games`, and
    every game through `last_date`.

    teams: current team by PLAYER_ID (from rosters). Players without a stint with that team
    yet (no game for it this season) are left out. The next game's features come straight
    from the logs (features_as_of); for later games only the schedule features change,
    since whether the player plays in between isn't known yet.
    """
    sched = schedule[["TEAM_ID", "GAME_ID", "GAME_DATE"]].drop_duplicates()
    opponents = sched.merge(sched, on="GAME_ID", suffixes=("", "_opp"))
    opponents = opponents[opponents.TEAM_ID != opponents.TEAM_ID_opp].set_index(["TEAM_ID", "GAME_ID"]).TEAM_ID_opp
    future = sched[sched.GAME_DATE >= today].sort_values("GAME_DATE")
    one = pd.Timedelta(days=1)
    team_days = set(zip(sched.TEAM_ID, sched.GAME_DATE))
    season_start = sched.GAME_DATE.min()
    out = []
    for player, team in teams.items():
        games = future[future.TEAM_ID == team]
        games = games[(np.arange(len(games)) < min_games) | (games.GAME_DATE <= last_date).to_numpy()]
        if games.empty:
            continue
        base = features_as_of(player_games, sched, priors, player, team, games.GAME_DATE.iloc[0])
        if base is None:
            continue
        team_dates = sched.loc[sched.TEAM_ID == team, "GAME_DATE"]
        for i, g in enumerate(games.itertuples()):
            row = dict(base) if i == 0 else base | {
                "b2b_second": int((team, g.GAME_DATE - one) in team_days),
                "b2b_first": int((team, g.GAME_DATE + one) in team_days),
                "days_into_season": (g.GAME_DATE - season_start).days,
                "team_games_left": int((team_dates > g.GAME_DATE).sum()),
            }
            out.append({"PLAYER_ID": player, "TEAM_ID": team, "GAME_ID": g.GAME_ID, "GAME_DATE": g.GAME_DATE,
                        "opponent": opponents.get((team, g.GAME_ID)), "next": i == 0, **row})
    return pd.DataFrame(out)


def predict(rows: pd.DataFrame, booster: lgb.Booster, calibration: dict) -> np.ndarray:
    if rows.empty:
        return np.array([])
    return calibrated(booster.predict(rows[FEATURES]), calibration)


def apply_injury_status(rows: pd.DataFrame, p: np.ndarray, listed_out: set, earliest_return: pd.Series) -> tuple[np.ndarray, list]:
    """The live injury status on top of the model: listed Out on the latest report -> the next
    game is near 0; an expected return date -> every game before it is near 0; after that, the
    model. Returns the probabilities and why each was overridden (None if not)."""
    p = np.asarray(p, dtype=float).copy()
    reasons: list = [None] * len(rows)
    for i, r in enumerate(rows.itertuples()):
        back = earliest_return.get(r.PLAYER_ID)
        if pd.notna(back) and r.GAME_DATE < pd.Timestamp(back):
            p[i], reasons[i] = OUT_PROBABILITY, "return date"
        elif r.next and r.PLAYER_ID in listed_out:
            p[i], reasons[i] = OUT_PROBABILITY, "injury report"
    return p, reasons


def priors_from_forecasts(forecasts: pd.DataFrame) -> pd.DataFrame:
    """Last season's facts for the season being forecast, from the committed forecast rows
    (the same table rows prior_season reads, so live and training features agree)."""
    return pd.DataFrame({
        "PLAYER_ID": forecasts.PLAYER_ID.to_numpy(),
        "age": (forecasts.age + 1).to_numpy(),
        "mpg_last": forecasts.mpg.to_numpy(),
        "gp_share_last": forecasts.gp_share.to_numpy(),
    }).drop_duplicates("PLAYER_ID")


def week_end(today: pd.Timestamp) -> pd.Timestamp:
    """The Sunday ending today's fantasy week (Monday to Sunday)."""
    return today + pd.Timedelta(days=6 - today.weekday())
