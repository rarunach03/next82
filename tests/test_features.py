import pandas as pd
import pytest

from next82.features import FEATURES, OUTPUT_PATH, TARGET, absence_features, load_table, team_schedules


def _schedule(team, n):
    return pd.DataFrame({
        "SEASON": "2024-25",
        "TEAM_ID": team,
        "GAME_ID": [f"{team}-{i:02d}" for i in range(n)],
        "GAME_DATE": [f"2024-11-{i + 1:02d}" for i in range(n)],
    })


def _played(player, team, idxs):
    return pd.DataFrame({
        "SEASON": "2024-25",
        "PLAYER_ID": player,
        "TEAM_ID": team,
        "GAME_ID": [f"{team}-{i:02d}" for i in idxs],
    })


@pytest.fixture
def schedules():
    return team_schedules(pd.concat([_schedule("A", 30), _schedule("B", 30)]))


def test_gap_and_season_end_absence(schedules):
    # Plays games 0-4, misses 5-16 (12 games), plays 17-19, misses 20-29 to end the season.
    games = _played(1, "A", [*range(5), *range(17, 20)])
    row = absence_features(games, schedules).iloc[0]
    assert row.longest_gap == 12
    assert row.missed_start == 0
    assert row.missed_end == 10
    assert row.n_major_gaps == 2


def test_trade_is_not_an_absence(schedules):
    # Plays A games 0-9, then B games 15-29. The switch between teams is not a gap.
    games = pd.concat([_played(2, "A", range(10)), _played(2, "B", range(15, 30))])
    row = absence_features(games, schedules).iloc[0]
    assert row.longest_gap == 0
    assert row.n_teams == 2
    assert row.missed_end == 0


needs_table = pytest.mark.skipif(not OUTPUT_PATH.exists(), reason="feature table not built")


@needs_table
def test_table_shape():
    df = load_table()
    assert not df.duplicated(["PLAYER_ID", "SEASON"]).any()
    assert df.loc[~df.is_forecast, TARGET].notna().all()
    assert df.loc[df.is_forecast, TARGET].isna().all()
    assert set(FEATURES) <= set(df.columns)


@needs_table
def test_full_missed_season_is_zero():
    # Kevin Durant missed all of 2019-20 (Achilles).
    df = load_table()
    row = df[(df.PLAYER_NAME == "Kevin Durant") & (df.SEASON == "2018-19")].iloc[0]
    assert row.gp_next == 0


@needs_table
def test_sat_out_season_row_for_known_comeback():
    # Durant sat out 2019-20 and returned for 35 of 72 games in 2020-21.
    df = load_table()
    row = df[(df.PLAYER_NAME == "Kevin Durant") & (df.SEASON == "2019-20")].iloc[0]
    assert row.missed_season == 1 and row.GP == 0
    assert row.gp_next == 35


@needs_table
def test_latest_sat_out_is_forecast_only():
    # Haliburton sat out 2025-26: he gets a forecast, but his 2024-25 row has no
    # known target (he hasn't returned yet), so it is dropped.
    df = load_table()
    hali = df[df.PLAYER_NAME == "Tyrese Haliburton"].set_index("SEASON")
    assert hali.loc["2025-26", "missed_season"] == 1
    assert hali.loc["2025-26", "is_forecast"]
    assert "2024-25" not in hali.index


@needs_table
def test_every_target_has_a_season_length():
    # Error in games is scaled by the next season's length; a missing length would
    # silently drop the row from accuracy numbers.
    df = load_table()
    assert df.loc[~df.is_forecast, "season_games_next"].notna().all()


# ---------------------------------------------------------------- candidate features: no leakage


def test_season_log_details_on_a_small_schedule():
    from next82.features import season_log_details

    sched = team_schedules(_schedule(1, 30))
    # Plays games 0-4, misses 5-11 (7), plays 12-24, misses the last 5.
    games = _played(7, 1, list(range(5)) + list(range(12, 25))).assign(MIN=[41.0] * 3 + [30.0] * 15)
    d = season_log_details(games, sched).iloc[0]
    assert (d.n_gaps_5, d.gap_games) == (1, 7)
    # The team's last 20 games are 10-29: he missed 10, 11 and 25-29.
    assert d.missed_last20 == 7
    assert d.share_40min == pytest.approx(3 / 18)


needs_raw = pytest.mark.skipif(not OUTPUT_PATH.exists(), reason="feature table not built")


@needs_raw
@pytest.mark.parametrize("season", ["2008-09", "2022-23"])
def test_candidate_features_use_only_earlier_seasons(season, monkeypatch):
    """Rebuild the features with every raw dataset cut off after `season`: that season's
    candidate values must match the full build exactly."""
    from next82 import config, features

    full = features.feature_rows()
    original = features.load
    upto = [s for s in config.SEASONS if s <= season]
    monkeypatch.setattr(features, "load", lambda dataset, seasons=None: original(dataset, upto))
    cut = features.feature_rows()
    assert cut.SEASON.max() == season
    key = ["SEASON", "PLAYER_ID"]
    a = full[full.SEASON == season].set_index(key).sort_index()
    b = cut[cut.SEASON == season].set_index(key).sort_index()
    shared = a.index.intersection(b.index)
    assert len(shared) > 300
    pd.testing.assert_frame_equal(a.loc[shared, features.CANDIDATES], b.loc[shared, features.CANDIDATES])
