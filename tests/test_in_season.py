import numpy as np
import pandas as pd
import pytest

from next82 import in_season
from next82.features import FEATURES


def _season():
    """Team A plays on 10 consecutive days from Nov 1; team B on the same days."""
    days = pd.date_range("2024-11-01", periods=10)
    team_games = pd.DataFrame({"TEAM_ID": ["A"] * 10 + ["B"] * 10, "GAME_DATE": list(days) * 2})
    # Player 1 plays A's first 5 games, then sits. Player 2 plays every B game.
    player_games = pd.DataFrame({
        "PLAYER_ID": [1] * 5 + [2] * 10,
        "TEAM_ID": ["A"] * 5 + ["B"] * 10,
        "GAME_DATE": list(days[:5]) + list(days),
    })
    totals = pd.Series({"A": 82, "B": 82})
    # Player 3 hasn't played this season.
    players = pd.DataFrame({"PLAYER_ID": [1, 2, 3], "preseason_share": [0.8, 0.9, 0.5]})
    for f in FEATURES:
        players[f] = 0.0
    return player_games, team_games, totals, players, days


def test_only_games_before_the_date_count():
    pg, tg, totals, players, days = _season()
    snap = in_season.snapshot_features(pg, tg, totals, players, days[3]).set_index("PLAYER_ID")
    # Games on days 0-2 happened before the snapshot; the game on day 3 hasn't.
    assert snap.loc[1, "played_so_far"] == 3
    assert snap.loc[1, "team_games_so_far"] == 3
    assert snap.loc[1, "team_games_left"] == 79


def test_absence_streak_and_recent_games():
    pg, tg, totals, players, days = _season()
    snap = in_season.snapshot_features(pg, tg, totals, players, days[9] + pd.Timedelta(days=1)).set_index("PLAYER_ID")
    # Player 1 last played on day 4; team A has played 5 games since.
    assert snap.loc[1, "absence_streak"] == 5
    assert snap.loc[1, "days_since_last_game"] == 6
    assert snap.loc[1, "played_last10_share"] == pytest.approx(0.5)
    assert snap.loc[1, "missed_so_far"] == 5
    assert snap.loc[2, "absence_streak"] == 0
    assert snap.loc[2, "share_so_far"] == 1


def test_player_without_games_gets_typical_schedule():
    pg, tg, totals, players, days = _season()
    snap = in_season.snapshot_features(pg, tg, totals, players, days[5]).set_index("PLAYER_ID")
    assert snap.loc[3, "has_played"] == 0
    assert snap.loc[3, "played_so_far"] == 0
    assert snap.loc[3, "team_games_so_far"] == 5  # median of the teams
    assert snap.loc[3, "absence_streak"] == 5  # missed every game so far
    assert snap.loc[3, "preseason_share"] == 0.5


def test_opening_day_snapshot_has_nothing_played():
    pg, tg, totals, players, days = _season()
    snap = in_season.snapshot_features(pg, tg, totals, players, days[0])
    assert (snap.played_so_far == 0).all()
    assert (snap.team_games_left == 82).all()
    assert snap.share_so_far.isna().all()


def test_baselines():
    snaps = pd.DataFrame({
        "team_games_so_far": [0, 20], "team_games_left": [82, 62],
        "share_so_far": [np.nan, 0.5], "preseason_share": [0.8, 0.8],
    })
    assert in_season.baseline_preseason(snaps).tolist() == pytest.approx([65.6, 49.6])
    assert in_season.baseline_pace(snaps).tolist() == pytest.approx([65.6, 31.0])
    # k=20 with 20 games played trusts pace and preseason equally.
    assert in_season.baseline_blend(snaps, 20).tolist() == pytest.approx([65.6, 0.65 * 62])


def test_known_team_sets_schedule_for_player_without_games():
    pg, tg, totals, players, days = _season()
    tg = tg[~((tg.TEAM_ID == "B") & (tg.GAME_DATE >= days[3]))]  # team B has played only 3 games
    snap = in_season.snapshot_features(pg, tg, totals, players, days[5], known_teams=pd.Series({3: "B"}))
    snap = snap.set_index("PLAYER_ID")
    assert snap.loc[3, "team_games_so_far"] == 3
    assert snap.loc[3, "team_games_left"] == 79
    assert snap.loc[3, "has_played"] == 0


@pytest.mark.skipif(not in_season.MODEL_PATH.exists(), reason="rest-of-season model not trained")
def test_current_forecast_is_between_games_played_and_the_maximum():
    snap = in_season.predict_current()
    if snap is None:
        pytest.skip("no current-season logs")
    assert (snap.updated_total >= snap.played_so_far - 1e-9).all()
    assert (snap.updated_total <= snap.played_so_far + snap.team_games_left + 1e-9).all()
    assert (snap.predicted_rest >= 0).all()
