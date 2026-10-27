"""Time-based train/test split and error metrics (MAE in games)."""
import numpy as np
import pandas as pd

from next82 import config
from next82.features import TARGET


def split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train on older seasons, test on the most recent seasons that have a target."""
    labeled = df[~df.is_forecast]
    first_test = labeled.season_idx.max() - config.N_TEST_SEASONS + 1
    return labeled[labeled.season_idx < first_test], labeled[labeled.season_idx >= first_test]


def is_rotation(df: pd.DataFrame) -> pd.Series:
    """Rotation players' availability matters most to teams and fantasy players."""
    return (df.mpg >= config.ROTATION_MIN_MPG) & (df.gp_share >= config.ROTATION_MIN_GP_SHARE)


def has_rotation_role(df: pd.DataFrame) -> pd.Series:
    """A rotation role in the last season played (works for comeback players too):
    15+ minutes per game and at least a quarter of the team's games."""
    mpg = df.mpg.fillna(df.mpg_lag1)
    return (mpg >= config.ROTATION_MIN_MPG) & (df.last_played_gp_share >= config.ROTATION_MIN_GP_SHARE)


def errors_games(df: pd.DataFrame, pred_share: np.ndarray) -> np.ndarray:
    """Absolute error in games for each row, scaled to each target season's length."""
    return (np.abs(pred_share - df[TARGET]) * df.season_games_next).to_numpy()


def mae_games(df: pd.DataFrame, pred_share: np.ndarray) -> float:
    """Mean absolute error in games."""
    return float(np.mean(errors_games(df, pred_share)))


def score(df: pd.DataFrame, pred_share: np.ndarray) -> dict:
    rot = is_rotation(df).to_numpy()
    comeback = (df.missed_season == 1).to_numpy()
    errors = errors_games(df, pred_share)
    return {
        "mae_all": float(errors.mean()),
        "median_error_all": float(np.median(errors)),
        "share_within_16": float((errors <= 16).mean()),
        "mae_rotation": mae_games(df[rot], pred_share[rot]),
        "mae_comeback": mae_games(df[comeback], pred_share[comeback]) if comeback.any() else None,
        "n_all": len(df),
        "n_rotation": int(rot.sum()),
        "n_comeback": int(comeback.sum()),
    }
