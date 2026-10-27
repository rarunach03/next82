import numpy as np
import pandas as pd
import pytest

from next82 import fantasy


def _totals(rows):
    df = pd.DataFrame(rows)
    for s in fantasy.STATS:
        if s not in df:
            df[s] = 0.0
    return df


def test_prior_weights_recent_seasons_and_games():
    totals = _totals([
        {"SEASON": "2025-26", "PLAYER_ID": 1, "GP": 10, "PTS": 300.0},  # 30 per game, weight 3
        {"SEASON": "2024-25", "PLAYER_ID": 1, "GP": 10, "PTS": 100.0},  # 10 per game, weight 2
        {"SEASON": "2023-24", "PLAYER_ID": 1, "GP": 0, "PTS": 0.0},     # no games: ignored
    ])
    prior = fantasy.prior_per_game(totals, ["2025-26", "2024-25", "2023-24"])
    # (3*300 + 2*100) / (3*10 + 2*10) = 22 points per game
    assert prior.loc[1, "PTS"] == pytest.approx(22)
    assert prior.loc[1, "prior_games"] == 20


def test_shrink_blends_this_season_toward_the_prior():
    prior = pd.DataFrame({s: [20.0 if s == "PTS" else 0.0] for s in fantasy.STATS}, index=[1])
    current = pd.DataFrame({s: [160.0 if s == "PTS" else 0.0] for s in fantasy.STATS}, index=[1])  # 4 games, 40 ppg
    games = pd.Series({1: 4})
    # K=6: (160 + 6*20) / (4 + 6) = 28
    assert fantasy.shrink(current, games, prior, 6).loc[1, "PTS"] == pytest.approx(28)
    assert fantasy.shrink(current, games, prior, 0).loc[1, "PTS"] == pytest.approx(40)
    assert fantasy.shrink(current, games, prior, np.inf).loc[1, "PTS"] == pytest.approx(20)


def test_points_formats():
    line = pd.DataFrame([{"PTS": 20, "FG3M": 2, "FGM": 8, "FGA": 15, "FTM": 2, "FTA": 3,
                          "REB": 10, "AST": 5, "STL": 1, "BLK": 1, "TOV": 3}])
    # ESPN: 20 + 2 + 16 - 15 + 2 - 3 + 10 + 10 + 4 + 4 - 6 = 44
    assert fantasy.fantasy_points(line, "espn").iloc[0] == pytest.approx(44)
    # Yahoo: 20 + 12 + 7.5 + 3 + 3 - 3 = 42.5
    assert fantasy.fantasy_points(line, "yahoo").iloc[0] == pytest.approx(42.5)


def test_nine_cat_weights_percentages_by_attempts():
    rng = np.random.default_rng(0)
    n = 200
    pg = pd.DataFrame({s: rng.uniform(1, 10, n) for s in fantasy.STATS})
    pg["FGA"] = 10.0
    pg["FGM"] = 4.5
    # Same 60% shooting: on 20 attempts it should be worth more than on 2.
    pg.loc[0, ["FGM", "FGA"]] = [12, 20]
    pg.loc[1, ["FGM", "FGA"]] = [1.2, 2]
    z = fantasy.nine_cat(pg, pool_size=150)
    assert z.loc[0, "FG%"] > z.loc[1, "FG%"] > 0
    assert set(fantasy.CATEGORIES) <= set(z.columns)
