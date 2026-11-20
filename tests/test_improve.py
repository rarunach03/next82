"""Season model improvement: validation never sees the test seasons; the keep rule."""
import json

import pytest

from next82 import config, evaluate, improve, models, train
from next82.features import OUTPUT_PATH, load_table


def test_validation_folds_come_before_the_test_seasons():
    assert len(improve.VALIDATION_SEASONS) == 5
    last_validation = config.SEASONS.index(improve.VALIDATION_SEASONS[-1])
    first_test = len(config.SEASONS) - 1 - config.N_TEST_SEASONS  # last labeled season is SEASONS[-2]
    assert last_validation < first_test


@pytest.mark.skipif(not OUTPUT_PATH.exists(), reason="feature table not built")
def test_folds_never_include_test_rows():
    df = load_table()
    _, test = evaluate.split(df)
    for season, tr, val in improve.folds(df):
        assert not set(tr.SEASON) & set(test.SEASON) and not set(val.SEASON) & set(test.SEASON)
        assert tr.season_idx.max() < val.season_idx.min()


def test_keep_rule_needs_both_a_real_gain_and_most_folds():
    assert improve.keeps({"change": -0.08, "folds_better": 4})
    assert not improve.keeps({"change": -0.08, "folds_better": 3})
    assert not improve.keeps({"change": -0.02, "folds_better": 5})


def test_the_adopted_model_beat_the_old_one_on_the_test_seasons():
    results = json.loads(improve.RESULTS_PATH.read_text())
    final = results["final"]["season_model"]
    if train.FINAL_MODEL != "LightGBM":
        assert results["final"]["adopt"]
        assert final[train.FINAL_MODEL]["mae_all"] < final["LightGBM"]["mae_all"]
    # Every choice was made before the single test run.
    assert results["candidates"]["kept_features"] and results["tune"]["chosen"]["blend_weight"] == models.BLEND_WEIGHT
