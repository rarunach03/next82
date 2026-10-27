import numpy as np
import pytest

from next82 import intervals
from next82.export import tier


def test_tidy_never_leaves_low_above_high():
    low, high = intervals.tidy([50, 10, 5], [40, 20, 6], [30, 15, 90], floor=0, ceiling=82)
    assert (low <= high).all()
    # Crossed quantiles are swapped, and the range always contains the point forecast.
    assert low.tolist() == [30, 10, 5]
    assert high.tolist() == [50, 20, 82]


def test_conformal_adjustment_hits_target_coverage():
    rng = np.random.default_rng(0)
    actual = rng.normal(0, 1, 5000)
    # A range that's too narrow (+-0.5) gets widened to cover about 80%.
    adj = intervals.conformal_adjustment(np.full(5000, -0.5), np.full(5000, 0.5), actual)
    assert adj > 0
    assert intervals.coverage(-0.5 - adj, 0.5 + adj, actual) == pytest.approx(0.8, abs=0.01)
    # One that's too wide gets narrowed.
    assert intervals.conformal_adjustment(np.full(5000, -3.0), np.full(5000, 3.0), actual) < 0


def test_tiers_follow_the_low_end_of_the_range():
    assert tier(60) == "Safe"
    assert tier(45) == "Safe"
    assert tier(30) == "Moderate"
    assert tier(19.9) == "Risky"
    assert tier(float("nan")) is None
