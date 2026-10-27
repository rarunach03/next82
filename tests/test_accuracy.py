import numpy as np
import pandas as pd
import pytest

from next82 import accuracy


def _setup():
    days = pd.date_range("2026-10-20", periods=10)
    team_games = pd.DataFrame({"TEAM_ID": [1] * 10, "GAME_DATE": days})
    # Player 10 plays every game; player 20 plays the first 4, then sits.
    player_games = pd.DataFrame({"PLAYER_ID": [10] * 10 + [20] * 4, "TEAM_ID": 1,
                                 "GAME_DATE": list(days) + list(days[:4])})
    forecasts = pd.DataFrame({
        "PLAYER_ID": [10, 20, 30],
        "missed_season": [0, 0, 0],
        "pred_share": [1.0, 0.5, 0.8],
        "gp_share": [0.9, 0.9, 0.9],
        "avg_gp_share_3yr": [0.8, 0.6, 0.7],
        "mpg": [30.0, 10.0, 25.0],
        "mpg_lag1": [30.0, 10.0, 25.0],
        "last_played_gp_share": [0.9, 0.9, 0.9],
    })
    rosters = pd.DataFrame({"PLAYER_ID": [10, 20], "TEAM_ID": [1, 1]})  # 30 isn't on a roster
    return forecasts, rosters, player_games, team_games, days


def test_forecasts_are_pro_rated_to_team_games_so_far():
    forecasts, rosters, pg, tg, days = _setup()
    players = accuracy.graded_players(forecasts, rosters)
    e = accuracy.errors_as_of(players, pg, tg, days[6]).set_index("PLAYER_ID")  # 6 team games so far
    assert e.loc[10, "team_games"] == 6 and e.loc[10, "played"] == 6
    assert e.loc[10, "err_model"] == pytest.approx(0)            # expected 6, played 6
    assert e.loc[20, "err_model"] == pytest.approx(abs(3 - 4))   # expected 3, played 4
    assert e.loc[20, "err_last_season"] == pytest.approx(abs(5.4 - 4))


def test_players_not_on_a_roster_are_not_graded():
    forecasts, rosters, pg, tg, _ = _setup()
    result = accuracy.season_accuracy(forecasts, rosters, pg, tg)
    assert result["groups"]["all"]["n"] == 2
    assert result["excludedNotOnRoster"] == 1
    assert len(result["trend"]) == 10


def test_gap_range_spans_zero_when_methods_tie():
    errors = pd.DataFrame({"err_model": np.ones(50), "err_three_year": np.ones(50)})
    low, high = accuracy.gap_range(errors, "three_year")
    assert low <= 0 <= high
