"""Evaluate all models, then train the final models and write next-season forecasts.

Regular players get one forecast from the main model. Players returning from a
missed season get a two-part forecast instead, because comeback seasons split
into "played a lot" and "barely played" and one number lands in between:
    p_setback         chance of playing fewer than config.SETBACK_GAMES of 82
    games_if_healthy  forecast from a model trained only on seasons without a setback

Outputs:
    models/metrics.json                    test-set error for each model + comeback evaluation
    models/lightgbm.joblib                 final models trained on all labeled seasons
    data/processed/forecasts.parquet       one row per player: forecasts + SHAP values
    data/processed/history.parquet         games played per player per season (app chart)
    data/processed/past_comebacks.parquet  past comeback seasons (app "similar comebacks")

The app reads only metrics.json and the three data/processed files above, so those
are committed to git and the app runs without re-running the pipeline.

Usage:
    python -m next82.train
"""
import json

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

from next82 import config, data, evaluate, explain, intervals, models
from next82.features import FEATURES, TARGET, load_table

FINAL_MODEL = "LightGBM"
MODEL_PATH = config.MODELS_DIR / "lightgbm.joblib"
METRICS_PATH = config.MODELS_DIR / "metrics.json"
FORECASTS_PATH = config.PROCESSED_DIR / "forecasts.parquet"
HISTORY_PATH = config.PROCESSED_DIR / "history.parquet"
PAST_COMEBACKS_PATH = config.PROCESSED_DIR / "past_comebacks.parquet"
RANGES_PATH = config.PROCESSED_DIR / "forecast_ranges.parquet"

# Comeback seasons are rare, so the comeback models are scored season by season:
# each season from here on is predicted by models trained only on earlier seasons.
COMEBACK_EVAL_FROM = "2000-01"


def run_evaluation(df: pd.DataFrame) -> dict:
    train, test = evaluate.split(df)
    results = {name: evaluate.score(test, models.predict(models.fit(name, train), test)) for name in models.MODELS}

    print(f"Train: {train.SEASON.min()} to {train.SEASON.max()} ({len(train):,} rows)")
    print(f"Test:  {test.SEASON.min()} to {test.SEASON.max()} ({len(test):,} rows)\n")
    print(f"{'Model':20s} {'MAE all':>8s} {'MAE rotation':>13s}")
    for name, r in results.items():
        print(f"{name:20s} {r['mae_all']:8.2f} {r['mae_rotation']:13.2f}")

    return {
        "train_seasons": [train.SEASON.min(), train.SEASON.max()],
        "test_seasons": [test.SEASON.min(), test.SEASON.max()],
        "final_model": FINAL_MODEL,
        "results": results,
    }


def evaluate_comebacks(df: pd.DataFrame) -> dict:
    labeled = df[~df.is_forecast]
    parts = []
    for s in range(config.SEASONS.index(COMEBACK_EVAL_FROM), labeled.season_idx.max() + 1):
        train = labeled[labeled.season_idx < s]
        test = labeled[(labeled.season_idx == s) & (labeled.missed_season == 1)]
        if test.empty:
            continue
        parts.append(test.assign(
            p_setback=models.predict_setback(models.fit_setback(train), test),
            healthy=np.clip(models.fit_healthy(train).predict(test[FEATURES]), 0, 1),
            main=models.predict(models.fit(FINAL_MODEL, train), test),
        ))
    c = pd.concat(parts)
    setback = models.is_setback(c)
    ok = ~setback
    out = {
        "from_season": COMEBACK_EVAL_FROM,
        "n": len(c),
        "setback_rate": float(setback.mean()),
        "setback_auc": float(roc_auc_score(setback, c.p_setback)),
        "setback_brier": float(brier_score_loss(setback, c.p_setback)),
        "setback_brier_base_rate": float(brier_score_loss(setback, np.full(len(c), setback.mean()))),
        "n_healthy": int(ok.sum()),
        "mae_healthy_two_part": evaluate.mae_games(c[ok], c.healthy[ok].to_numpy()),
        "mae_healthy_main_model": evaluate.mae_games(c[ok], c.main[ok].to_numpy()),
    }
    print(f"\nComeback seasons {COMEBACK_EVAL_FROM} on (n={out['n']}, setback rate {out['setback_rate']:.0%}):")
    print(f"  Setback chance: AUC {out['setback_auc']:.3f}, Brier {out['setback_brier']:.3f} "
          f"(base rate only: {out['setback_brier_base_rate']:.3f})")
    print(f"  Games if healthy (n={out['n_healthy']}): two-part {out['mae_healthy_two_part']:.2f} "
          f"vs main model {out['mae_healthy_main_model']:.2f}")
    return out


def predict_range(quantiles, adjustment: float, point: np.ndarray, rows: pd.DataFrame):
    """Likely range as a share of the season: quantile models, conformal correction, tidied."""
    low, high = (np.asarray(m.predict(rows[FEATURES])) for m in quantiles)
    return intervals.tidy(low - adjustment, point, high + adjustment, floor=0, ceiling=1)


def preseason_ranges(df: pd.DataFrame) -> tuple[float, dict]:
    """Measure the conformal correction on the validation season, then check coverage
    on the test seasons. Returns the correction and the test calibration table."""
    train, test = evaluate.split(df)
    val_idx = train.season_idx.max()
    fit_part, val = train[train.season_idx < val_idx], train[train.season_idx == val_idx]
    low, high = (m.predict(val[FEATURES]) for m in models.fit_quantiles(fit_part))
    adjustment = intervals.conformal_adjustment(low, high, val[TARGET])

    point = models.predict(models.fit(FINAL_MODEL, train), test)
    low, high = predict_range(models.fit_quantiles(train), adjustment, point, test)
    raw_low, raw_high = (m.predict(test[FEATURES]) for m in models.fit_quantiles(train))
    crossed = int((raw_low > raw_high).sum())
    games = test.season_games_next.to_numpy()
    actual = test[TARGET].to_numpy() * games
    table = intervals.calibration_table(low * games, high * games, actual, {
        "all players": np.ones(len(test), bool),
        "rotation players": evaluate.is_rotation(test).to_numpy(),
        "comeback players": (test.missed_season == 1).to_numpy(),
        "everyone else": (test.missed_season == 0).to_numpy(),
    })
    metrics_tiers = intervals.tier_check(low * games, actual, games, {
        "all players": np.ones(len(test), bool),
        "rotation role": evaluate.has_rotation_role(test).to_numpy(),
        "no rotation role": ~evaluate.has_rotation_role(test).to_numpy(),
    })
    table["tiers"] = metrics_tiers
    print(f"\nPreseason ranges: conformal correction {adjustment * 82:+.1f} games per side "
          f"(measured on {config.SEASONS[val_idx]}); low above high before tidying: {crossed} of {len(test)}")
    intervals.print_calibration(f"Test seasons {test.SEASON.min()} and {test.SEASON.max()}",
                                {k: v for k, v in table.items() if k != "tiers"})
    intervals.print_tier_check("Preseason tiers, test seasons", metrics_tiers)
    return adjustment, table


def _add_shap(rows: pd.DataFrame, model) -> pd.DataFrame:
    values, base = explain.shap_values(model, rows)
    rows = rows.copy()
    for i, f in enumerate(FEATURES):
        rows[f"shap_{f}"] = values[:, i]
    rows["shap_base"] = base
    return rows


def train_final(df: pd.DataFrame):
    labeled, upcoming = df[~df.is_forecast], df[df.is_forecast].copy()
    main, setback, healthy = models.fit(FINAL_MODEL, labeled), models.fit_setback(labeled), models.fit_healthy(labeled)

    upcoming["pred_share"] = models.predict(main, upcoming)
    upcoming["pred_games"] = upcoming.pred_share * explain.GAMES
    upcoming["p_setback"] = models.predict_setback(setback, upcoming)
    upcoming["games_if_healthy"] = np.clip(healthy.predict(upcoming[FEATURES]), 0, 1) * explain.GAMES

    # Factors explain the number each player is shown: the main forecast for
    # regular players, the if-healthy forecast for comeback players.
    comeback = upcoming.missed_season == 1
    upcoming = pd.concat([_add_shap(upcoming[~comeback], main), _add_shap(upcoming[comeback], healthy)])
    return {"main": main, "setback": setback, "healthy": healthy}, upcoming


def season_history() -> pd.DataFrame:
    """Games played by every player in every season, and each season's length.

    Built from the raw stats rather than the model table, which drops some seasons
    (e.g. ones whose next-season result isn't known yet).
    """
    team_games = data.load("team_games")
    season_games = team_games.groupby(["SEASON", "TEAM_ID"]).size().groupby("SEASON").max().rename("season_games")
    history = data.load("player_stats")[["PLAYER_ID", "SEASON", "GP"]].merge(season_games, on="SEASON")
    return history.sort_values(["PLAYER_ID", "SEASON"]).reset_index(drop=True)


def past_comebacks(df: pd.DataFrame) -> pd.DataFrame:
    """First missed seasons with a known comeback result, for the similar-comebacks list."""
    rows = df[(df.missed_season == 1) & (df.missed_season_lag1 == 0) & ~df.is_forecast]
    cols = ["PLAYER_ID", "PLAYER_NAME", "SEASON", "missed_season", "missed_season_lag1", "is_forecast",
            "gp_share_next", *explain.SIMILARITY]
    return rows[list(dict.fromkeys(cols))].reset_index(drop=True)


def main():
    df = load_table()
    metrics = run_evaluation(df)
    metrics["comeback"] = evaluate_comebacks(df)
    adjustment, metrics["ranges"] = preseason_ranges(df)
    final_models, forecasts = train_final(df)

    # Likely ranges for the forecasts, from preseason data only.
    quantiles = models.fit_quantiles(df[~df.is_forecast])
    low, high = predict_range(quantiles, adjustment, forecasts.pred_share.to_numpy(), forecasts)
    ranges = pd.DataFrame({"PLAYER_ID": forecasts.PLAYER_ID.to_numpy(), "low_games": low * explain.GAMES,
                           "high_games": high * explain.GAMES})

    config.MODELS_DIR.mkdir(exist_ok=True)
    joblib.dump(final_models, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    forecasts.to_parquet(FORECASTS_PATH, index=False)
    ranges.to_parquet(RANGES_PATH, index=False)
    season_history().to_parquet(HISTORY_PATH, index=False)
    past_comebacks(df).to_parquet(PAST_COMEBACKS_PATH, index=False)
    print(f"\nSaved {len(forecasts)} forecasts for the season after {forecasts.SEASON.iloc[0]}")


if __name__ == "__main__":
    main()
