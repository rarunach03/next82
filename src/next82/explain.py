"""Per-prediction explanations (top factors behind each forecast).

Uses SHAP values from the LightGBM model. Each feature's SHAP value is how much
it moved the forecast away from the average forecast, converted here to games
out of 82.
"""
import numpy as np
import pandas as pd
import shap

from next82 import config
from next82.features import FEATURES

GAMES = 82

# Labels name seasons explicitly ({cur} = the latest finished season, {prev} and
# {prev2} the two before it), since "this season" is ambiguous once the forecast
# season is underway.
LABELS = {
    "age": "Age",
    "years_since_draft": "Years since draft",
    "undrafted": "Undrafted",
    "height_in": "Height",
    "weight_lb": "Weight",
    "gp_share": "Games played in {cur}",
    "mpg": "Minutes per game in {cur}",
    "min_share": "Total minutes in {cur} vs. league leader",
    "usg_pct": "Usage rate in {cur}",
    "longest_gap": "Longest absence in {cur}",
    "n_major_gaps": "Absences of 10+ games in {cur}",
    "missed_start": "Games missed at start of {cur}",
    "missed_end": "Games missed at end of {cur}",
    "n_teams": "Teams played for in {cur}",
    "missed_season": "Missed all of {cur}",
    "gp_share_lag1": "Games played in {prev}",
    "gp_share_lag2": "Games played in {prev2}",
    "missed_season_lag1": "Missed all of {prev}",
    "mpg_lag1": "Minutes per game in {prev}",
    "longest_gap_lag1": "Longest absence in {prev}",
    "missed_end_lag1": "Games missed at end of {prev}",
    "major_gaps_3yr": "Absences of 10+ games, {prev2} to {cur}",
    "avg_gp_share_3yr": "Average games played, {prev2} to {cur}",
    "seasons_in_data": f"Seasons in the NBA since {config.SEASONS[0]}",
    "last_played_gp_share": "Games played, last season played",
    "avg_gp_share_3_played": "Average games, last 3 seasons played",
    "age_x_missed_season": "Age, if returning from a missed season",
}


def _season_before(season: str, n: int = 1) -> str:
    start = int(season[:4]) - n
    return f"{start}-{str(start + 1)[-2:]}"


def label(feature: str, season: str) -> str:
    """Readable name for a feature, with seasons filled in relative to `season`."""
    return LABELS[feature].format(cur=season, prev=_season_before(season), prev2=_season_before(season, 2))


def format_value(feature: str, value) -> str:
    """Human-readable value for a feature, e.g. '38 of 82 games'."""
    if pd.isna(value):
        return "no data"
    if feature in ("gp_share", "gp_share_lag1", "gp_share_lag2", "avg_gp_share_3yr",
                   "last_played_gp_share", "avg_gp_share_3_played"):
        return f"{value * GAMES:.0f} of {GAMES} games"
    if feature in ("longest_gap", "missed_start", "missed_end", "longest_gap_lag1", "missed_end_lag1"):
        return f"{value:.0f} games"
    if feature in ("undrafted", "missed_season", "missed_season_lag1"):
        return "yes" if value else "no"
    if feature in ("mpg", "mpg_lag1"):
        return f"{value:.1f}"
    if feature in ("usg_pct", "min_share"):
        return f"{value:.0%}"
    if feature == "age_x_missed_season":
        return f"{value:.0f}" if value else "not returning"
    if feature == "height_in":
        return f"{int(value) // 12}'{int(value) % 12}\""
    if feature == "weight_lb":
        return f"{value:.0f} lb"
    return f"{value:.0f}"


def shap_values(model, X: pd.DataFrame) -> tuple[np.ndarray, float]:
    """SHAP values in games (rows x features) and the base value in games.

    For a blend (models.Blend), SHAP values add up like the predictions: the weighted
    tree values plus the linear model's exact ones, coefficient x (input - average input),
    with each missing-value flag counted toward its feature.
    """
    from next82.models import Blend

    if isinstance(model, Blend):
        tree, tree_base = shap_values(model.tree, X)
        lin, lin_base = _linear_shap(model, X[FEATURES])
        w = model.weight
        return w * tree + (1 - w) * lin, w * tree_base + (1 - w) * lin_base
    explainer = shap.TreeExplainer(model)
    values = explainer.shap_values(X[FEATURES]) * GAMES
    return values, float(np.ravel(explainer.expected_value)[0]) * GAMES


def _linear_shap(model, X: pd.DataFrame) -> tuple[np.ndarray, float]:
    """Exact SHAP values (in games) of the blend's linear model (imputer -> scaler -> ridge)."""
    imputer, ridge = model.linear[0], model.linear[-1]
    z = model.linear[:-1].transform(X)
    parts = ridge.coef_ * (z - model.linear_background_)
    values = parts[:, : X.shape[1]].copy()
    if imputer.indicator_ is not None:
        for k, feature in enumerate(imputer.indicator_.features_):
            values[:, feature] += parts[:, X.shape[1] + k]
    base = float(ridge.intercept_ + ridge.coef_ @ model.linear_background_)
    return values * GAMES, base * GAMES


def top_factors(row: pd.Series, n: int = 6) -> pd.DataFrame:
    """Largest factors for one player, from a forecast row holding shap_<feature> columns."""
    impact = pd.Series({f: row[f"shap_{f}"] for f in FEATURES})
    top = impact.reindex(impact.abs().sort_values(ascending=False).index[:n])
    return pd.DataFrame({
        "factor": [label(f, row.SEASON) for f in top.index],
        "value": [
            "did not play" if row.get("missed_season") and pd.isna(row[f]) else format_value(f, row[f])
            for f in top.index
        ],
        "impact_games": top.to_numpy(),
    })


# Similar past comebacks: nearest players on these inputs, each divided by a scale
# so that e.g. 4 years of age counts about as much as 5 minutes per game.
SIMILARITY = {"age": 4, "mpg_lag1": 5, "last_played_gp_share": 0.15, "avg_gp_share_3_played": 0.15}


def similar_comebacks(row: pd.Series, table: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Past players who returned from their first missed season, most similar to `row` first."""
    past = table[(table.missed_season == 1) & (table.missed_season_lag1 == 0) & ~table.is_forecast]
    past = past.dropna(subset=list(SIMILARITY))
    distance = sum(((past[c] - row[c]) / scale) ** 2 for c, scale in SIMILARITY.items()) ** 0.5
    nearest = past.loc[distance.nsmallest(n).index]
    return pd.DataFrame({
        "player": nearest.PLAYER_NAME,
        "missed": nearest.SEASON,
        "age": nearest.age.astype(int),
        "before": (nearest.last_played_gp_share * GAMES).round().astype(int).astype(str) + " games, "
        + nearest.mpg_lag1.round(1).astype(str) + " min",
        "comeback_games": (nearest.gp_share_next * GAMES).round().astype(int),
    }).reset_index(drop=True)
