import pandas as pd
import pytest

from next82 import preseason


def test_freeze_refuses_to_overwrite(tmp_path):
    source, dest = tmp_path / "forecasts.parquet", tmp_path / "frozen.parquet"
    pd.DataFrame({"x": [1]}).to_parquet(source)
    preseason.freeze(source, dest)
    pd.DataFrame({"x": [2]}).to_parquet(source)
    with pytest.raises(FileExistsError):
        preseason.freeze(source, dest)
    assert pd.read_parquet(dest).x.tolist() == [1]


@pytest.mark.skipif(not preseason.PRESEASON_PATH.exists(), reason="no frozen forecast")
def test_frozen_forecast_uses_only_preseason_data():
    frozen = pd.read_parquet(preseason.PRESEASON_PATH)
    # Rows describe the last finished season; the forecast is for the one after it.
    assert (frozen.SEASON < preseason.config.FORECAST_SEASON).all()
