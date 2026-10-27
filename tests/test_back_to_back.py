import numpy as np
import pandas as pd
import pytest

from next82 import back_to_back


def _season():
    # Team 1 plays Nov 1, 2 (back-to-back), 4, 5 (back-to-back), 7.
    days = pd.to_datetime(["2024-11-01", "2024-11-02", "2024-11-04", "2024-11-05", "2024-11-07"])
    team = pd.DataFrame({"SEASON": "2024-25", "TEAM_ID": 1, "GAME_DATE": days})
    # Player 10 rests Nov 2 (back for Nov 4). Player 20 misses Nov 5 AND Nov 7: likely injured, dropped.
    games = [(10, d) for d in days if d != days[1]] + [(20, d) for d in days[:3]]
    pg = pd.DataFrame({"SEASON": "2024-25", "PLAYER_ID": [g[0] for g in games], "TEAM_ID": 1,
                       "GAME_DATE": [g[1] for g in games]})
    return pg, team


def test_back_to_backs_are_consecutive_days():
    _, team = _season()
    pairs = back_to_back.back_to_backs(team)
    assert pairs.first.dt.day.tolist() == [1, 4]
    assert pairs.second.dt.day.tolist() == [2, 5]


def test_rest_outcomes_count_rests_and_drop_likely_injuries():
    pg, team = _season()
    out = back_to_back.rest_outcomes(pg, team).set_index(["PLAYER_ID", "first"])
    assert out.loc[(10, pd.Timestamp("2024-11-01")), "rested"]          # sat the 2nd night, back next game
    assert not out.loc[(10, pd.Timestamp("2024-11-04")), "rested"]      # played both nights
    assert not out.loc[(20, pd.Timestamp("2024-11-01")), "rested"]
    assert (20, pd.Timestamp("2024-11-04")) not in out.index            # missed 2nd night and next game


def test_shrinking_pulls_small_samples_to_the_league_rate():
    outcomes = pd.DataFrame({"PLAYER_ID": [1, 1, 2] + [3] * 100, "rested": [True, True, False] + [True] * 50 + [False] * 50})
    rates = back_to_back.shrunk_rates(outcomes, m=40, league_rate=0.1).rate
    assert rates[1] == pytest.approx((2 + 4) / (2 + 40))   # 2 of 2 is pulled almost to 10%
    assert rates[3] == pytest.approx((50 + 4) / (100 + 40))
    assert (back_to_back.shrunk_rates(outcomes, m=np.inf, league_rate=0.1).rate == 0.1).all()


def test_remaining_back_to_backs_and_adjustment():
    _, team = _season()
    left = back_to_back.remaining_back_to_backs(team.drop(columns="SEASON"), pd.Timestamp("2024-11-03"))
    assert left[1] == 1
    # Resting 10 points more than the league over 10 back-to-backs, healthy 80%: 0.8 fewer games.
    assert back_to_back.adjustment(0.2, 0.1, 10, 0.8) == pytest.approx(-0.8)
