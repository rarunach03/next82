"""Likely ranges (10th-90th percentile) for forecasts, and checks that they're calibrated.

Ranges come from LightGBM quantile models. Quantile models are often a bit too
narrow or too wide on new seasons, so a split-conformal correction is measured on
a validation season and applied afterwards: the range is widened (or narrowed) by
the amount that makes COVERAGE of validation outcomes land inside it.
"""
import numpy as np
import pandas as pd

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


def print_calibration(title: str, table: dict):
    print(f"\n{title} (target {COVERAGE:.0%} inside the range)")
    print(f"  {'Group':34s} {'n':>7s} {'inside':>8s} {'avg width':>10s}")
    for group, row in table.items():
        print(f"  {group:34s} {row['n']:7d} {row['coverage']:8.0%} {row['avg_width']:10.1f}")


def as_frame(table: dict) -> pd.DataFrame:
    return pd.DataFrame(table).T
