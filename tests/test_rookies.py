import json

import numpy as np
import pandas as pd
import pytest

from next82 import data, export, rookies
from next82.preseason import load_forecasts


def test_draft_ranges():
    assert rookies.draft_range(1) == "picks 1-5"
    assert rookies.draft_range(14) == "picks 6-14"
    assert rookies.draft_range(30) == "picks 15-30"
    assert rookies.draft_range(60) == "picks 31-60"
    assert rookies.draft_range(None) == rookies.UNDRAFTED
    assert rookies.draft_range(np.nan) == rookies.UNDRAFTED


def test_is_rookie_needs_no_forecast_and_a_first_season():
    rosters = pd.DataFrame({"PLAYER_ID": [1, 2, 3, 4], "FROM_YEAR": [2026, 2015, 2026, 2019]})
    draft = pd.DataFrame({"PLAYER_ID": [1, 4]})
    # 1: drafted and new -> rookie. 2: veteran with a forecast. 3: undrafted, new -> rookie.
    # 4: drafted this year per the draft table but has a forecast -> not a rookie.
    result = rookies.is_rookie(rosters, forecast_ids=[2, 4], draft=draft)
    assert result.tolist() == [True, False, True, False]


has_data = rookies.BASELINE_PATH.exists() and data.saved_season_logs() is not None and data.saved_rosters() is not None
needs_data = pytest.mark.skipif(not has_data, reason="rookie baseline or season logs not available")


@needs_data
def test_current_rookies_have_valid_values(monkeypatch):
    # Early in the season nobody has 5 games yet, so lower the bar to exercise the path.
    monkeypatch.setattr(rookies, "MIN_GAMES", 1)
    r = rookies.current_rookies(data.saved_rosters(), load_forecasts().PLAYER_ID)
    if r.empty:
        pytest.skip("no rookie has played yet")
    assert set(r.draft_range) <= {name for *_, name in rookies.DRAFT_RANGES} | {rookies.UNDRAFTED}
    assert (r.predicted_rest >= 0).all() and (r.predicted_rest <= r.team_games_left).all()
    assert (r.updated_total >= r.played_so_far).all()
    assert r.PTS.notna().all() and np.isfinite(r.PTS).all()


@needs_data
def test_rookies_are_ranked_and_marked(monkeypatch, tmp_path):
    monkeypatch.setattr(rookies, "MIN_GAMES", 1)
    monkeypatch.setattr(export, "OUT_DIR", tmp_path)
    export.main()
    fantasy = json.loads((tmp_path / "fantasy.json").read_text())
    rookie_rows = [p for p in fantasy["players"] if p["rookie"]]
    if not rookie_rows:
        pytest.skip("no rookie has played yet")
    assert all(p["draftRange"] and p["tier"] is None for p in rookie_rows)
    assert all(not p["rookie"] for p in fantasy["players"] if p["draftRange"] is None)
