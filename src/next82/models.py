"""Baseline ("same as last year"), linear regression, and LightGBM models.

All models predict next season's gp_share and are clipped to [0, 1].
"""
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from next82 import config
from next82.features import FEATURES, TARGET


class SameAsLastYear:
    """Predicts that a player plays the same share of games as this season."""

    def fit(self, X: pd.DataFrame, y: pd.Series):
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return X["gp_share"].to_numpy()


class ThreeYearAverage:
    """Predicts the player's average share of games over the last three seasons."""

    def fit(self, X: pd.DataFrame, y: pd.Series):
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return X["avg_gp_share_3yr"].to_numpy()


def linear():
    # Missing history (first seasons in data) is filled with the median and flagged.
    return make_pipeline(
        SimpleImputer(strategy="median", add_indicator=True),
        StandardScaler(),
        Ridge(alpha=1.0),
    )


def lightgbm():
    # L1 objective optimizes MAE directly. Settings chosen on 2022-23 as a
    # validation season, without looking at the test seasons.
    return LGBMRegressor(
        objective="l1",
        n_estimators=300,
        learning_rate=0.02,
        num_leaves=15,
        min_child_samples=80,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        random_state=config.RANDOM_STATE,
        verbose=-1,
    )


def quantile_model(alpha: float):
    """Same settings as the main model, predicting the `alpha` quantile instead of the median."""
    return lightgbm().set_params(objective="quantile", alpha=alpha)


def fit_quantiles(df: pd.DataFrame, features: list[str] = FEATURES) -> tuple:
    """Models for the low and high ends of the likely range (10th and 90th percentiles)."""
    from next82.intervals import HIGH, LOW

    return tuple(quantile_model(a).fit(df[features], df[TARGET]) for a in (LOW, HIGH))


MODELS = {
    "Same as last year": SameAsLastYear,
    "3-year average": ThreeYearAverage,
    "Linear regression": linear,
    "LightGBM": lightgbm,
}


def setback_classifier():
    return LGBMClassifier(
        n_estimators=300,
        learning_rate=0.02,
        num_leaves=15,
        min_child_samples=80,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        random_state=config.RANDOM_STATE,
        verbose=-1,
    )


def is_setback(df: pd.DataFrame) -> pd.Series:
    return df[TARGET] < config.SETBACK_GAMES / 82


def fit_setback(df: pd.DataFrame):
    """Chance of a setback season (fewer than SETBACK_GAMES of 82)."""
    return setback_classifier().fit(df[FEATURES], is_setback(df))


def fit_healthy(df: pd.DataFrame):
    """Games played next season, trained only on seasons without a setback."""
    healthy = df[~is_setback(df)]
    return lightgbm().fit(healthy[FEATURES], healthy[TARGET])


def predict_setback(model, df: pd.DataFrame) -> np.ndarray:
    return model.predict_proba(df[FEATURES])[:, 1]


def fit(name: str, df: pd.DataFrame, features: list[str] = FEATURES):
    return MODELS[name]().fit(df[features], df[TARGET])


def predict(model, df: pd.DataFrame, features: list[str] = FEATURES) -> np.ndarray:
    return np.clip(model.predict(df[features]), 0, 1)
