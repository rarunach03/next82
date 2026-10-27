"""Likely ranges (10th-90th percentile) for forecasts, and checks that they're calibrated.

Ranges come from LightGBM quantile models. Quantile models are often a bit too
narrow or too wide on new seasons, so a split-conformal correction is measured on
a validation season and applied afterwards: the range is widened (or narrowed) by
the amount that makes COVERAGE of validation outcomes land inside it.
"""
import numpy as np
import pandas as pd

from next82 import config

LOW, HIGH = 0.1, 0.9
COVERAGE = HIGH - LOW  # an 80% range


def tidy(low, point, high, floor=None, ceiling=None):
    """Make a range usable: low <= point <= high, inside [floor, ceiling].

    Separate quantile models can cross (the 10th percentile above the 90th) or leave
    the point forecast outside; sorting and widening fixes both.
    """
    low, point, high = (np.asarray(x, dtype=float) for x in (low, point, high))
    low, high = np.minimum(low, high), np.maximum(low, high)
    low, high = np.minimum(low, point), np.maximum(high, point)
    if floor is not None:
        low, high = np.maximum(low, floor), np.maximum(high, floor)
    if ceiling is not None:
        low, high = np.minimum(low, ceiling), np.minimum(high, ceiling)
    return low, high


def conformal_adjustment(low, high, actual, coverage=COVERAGE) -> float:
    """How much to widen (positive) or narrow (negative) each side so that
    `coverage` of validation outcomes fall inside the range (split conformal)."""
    low, high, actual = (np.asarray(x, dtype=float) for x in (low, high, actual))
    scores = np.maximum(low - actual, actual - high)
    n = len(scores)
    level = min(1.0, np.ceil((n + 1) * coverage) / n)
    return float(np.quantile(scores, level, method="higher"))


def coverage(low, high, actual) -> float:
    """Share of outcomes inside the range."""
    low, high, actual = (np.asarray(x, dtype=float) for x in (low, high, actual))
    return float(np.mean((actual >= low) & (actual <= high)))


def calibration_table(low, high, actual, groups: dict[str, np.ndarray]) -> dict:
    """Coverage and average width by group."""
    low, high, actual = (np.asarray(x, dtype=float) for x in (low, high, actual))
    out = {}
    for name, mask in groups.items():
        mask = np.asarray(mask, bool)
        if mask.any():
            out[name] = {
                "n": int(mask.sum()),
                "coverage": coverage(low[mask], high[mask], actual[mask]),
                "avg_width": float(np.mean(high[mask] - low[mask])),
            }
    return out


def tier(low_games, season_games: float = 82) -> str | None:
    """Availability tier from the low end of the likely range, with cutoffs scaled
    to the season's length: Safe if even a bad outcome is TIER_SAFE_LOW+ games
    (per 82), Risky if it's a setback season (under SETBACK_GAMES), else Moderate."""
    if low_games is None or pd.isna(low_games):
        return None
    scale = season_games / 82
    if low_games >= config.TIER_SAFE_LOW * scale:
        return "Safe"
    return "Risky" if low_games < config.SETBACK_GAMES * scale else "Moderate"


def tier_check(low, actual, season_games, groups: dict[str, np.ndarray]) -> dict:
    """How honest the tiers were: share of Safe players who ended under the Safe
    cutoff, and of Risky players who ended under the Risky cutoff."""
    low, actual, season_games = (np.asarray(x, dtype=float) for x in (low, actual, season_games))
    tiers = np.array([tier(lo, n) for lo, n in zip(low, season_games)])
    scale = season_games / 82
    out = {}
    for name, mask in groups.items():
        mask = np.asarray(mask, bool)
        safe, risky = mask & (tiers == "Safe"), mask & (tiers == "Risky")
        out[name] = {
            "n": int(mask.sum()),
            "safe_share": float(safe.sum() / max(mask.sum(), 1)),
            "risky_share": float(risky.sum() / max(mask.sum(), 1)),
            "safe_under_cutoff": float(np.mean(actual[safe] < config.TIER_SAFE_LOW * scale[safe])) if safe.any() else None,
            "risky_under_cutoff": float(np.mean(actual[risky] < config.SETBACK_GAMES * scale[risky])) if risky.any() else None,
        }
    return out


def print_tier_check(title: str, table: dict):
    print(f"\n{title}: Safe = low end {config.TIER_SAFE_LOW}+, Risky = low end under {config.SETBACK_GAMES}")
    print(f"  {'Group':30s} {'n':>7s} {'Safe':>6s} {'Safe <' + str(config.TIER_SAFE_LOW):>9s} {'Risky':>6s} {'Risky <' + str(config.SETBACK_GAMES):>10s}")
    for g, r in table.items():
        f = lambda v: "   -" if v is None else f"{v:.0%}"
        print(f"  {g:30s} {r['n']:7d} {r['safe_share']:6.0%} {f(r['safe_under_cutoff']):>9s} {r['risky_share']:6.0%} {f(r['risky_under_cutoff']):>10s}")


def print_calibration(title: str, table: dict):
    print(f"\n{title} (target {COVERAGE:.0%} inside the range)")
    print(f"  {'Group':34s} {'n':>7s} {'inside':>8s} {'avg width':>10s}")
    for group, row in table.items():
        print(f"  {group:34s} {row['n']:7d} {row['coverage']:8.0%} {row['avg_width']:10.1f}")


def as_frame(table: dict) -> pd.DataFrame:
    return pd.DataFrame(table).T
