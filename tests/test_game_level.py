"""Game-by-game availability (beta): row building, features, injury override, and the
quality gates that must all pass before the site shows the beta."""
import json

import numpy as np
import pandas as pd
import pytest

from next82 import config, data, game_level as gl

D = pd.Timestamp


def schedule(team, dates):
    return pd.DataFrame({"TEAM_ID": team, "GAME_ID": [f"{team}-{d}" for d in dates], "GAME_DATE": [D(d) for d in dates]})


def games(player, team, dates, minutes=30.0):
    return pd.DataFrame({"PLAYER_ID": player, "TEAM_ID": team, "GAME_ID": [f"{team}-{d}" for d in dates],
                         "GAME_DATE": [D(d) for d in dates], "MIN": minutes})


# Team 1 plays every other day in October; team 2 every day from Oct 10.
T1 = schedule(1, [f"2025-10-{d:02d}" for d in range(1, 31, 2)])
T2 = schedule(2, [f"2025-10-{d:02d}" for d in range(10, 31)])
SCHED = pd.concat([T1, T2], ignore_index=True)
PRIORS = pd.DataFrame({"PLAYER_ID": [7], "age": [30.0], "mpg_last": [28.0], "gp_share_last": [0.9]})


# ---------------------------------------------------------------- rows: roster by date


def test_rows_start_after_the_first_appearance_and_run_to_the_season_end():
    pg = games(7, 1, ["2025-10-05", "2025-10-07"])
    rows = gl.season_rows(pg, SCHED, PRIORS)
    # No row for Oct 1/3 (not known to be on the team yet) or Oct 5 (in the data because he played).
    assert rows.GAME_DATE.min() == D("2025-10-07")
    # Missing every game after Oct 7 (waived or hurt) stays in the data as misses.
    assert rows.GAME_DATE.max() == D("2025-10-29")
    assert rows.played.tolist() == [1] + [0] * (len(rows) - 1)


def test_a_traded_player_moves_to_the_new_team_at_his_first_game_there():
    pg = pd.concat([games(7, 1, ["2025-10-01", "2025-10-03"]), games(7, 2, ["2025-10-15", "2025-10-16"])])
    rows = gl.season_rows(pg, SCHED, PRIORS)
    old, new = rows[rows.TEAM_ID == 1], rows[rows.TEAM_ID == 2]
    # Old team: rows until his first game for the new team (the gap counts as missed).
    assert old.GAME_DATE.max() == D("2025-10-13") and old.played.tolist() == [1, 0, 0, 0, 0, 0]
    # New team: from the game after his first there; no row for both teams on any day.
    assert new.GAME_DATE.min() == D("2025-10-16")
    assert not rows.duplicated(["PLAYER_ID", "GAME_DATE"]).any()


def test_a_player_back_with_his_first_team_starts_a_new_stint():
    pg = pd.concat([games(7, 1, ["2025-10-01"]), games(7, 2, ["2025-10-12"]), games(7, 1, ["2025-10-21", "2025-10-23"])])
    rows = gl.season_rows(pg, SCHED, PRIORS)
    back = rows[(rows.TEAM_ID == 1) & (rows.GAME_DATE > D("2025-10-20"))]
    assert back.stint_games.iloc[0] == 1  # history restarts at the return
    assert rows[rows.TEAM_ID == 2].GAME_DATE.max() == D("2025-10-20")


def test_table_features_match_features_recomputed_from_earlier_games():
    pg = pd.concat([
        games(7, 1, ["2025-10-01", "2025-10-03", "2025-10-09", "2025-10-11"], minutes=[30, 31, 12, 25]),
        games(7, 2, ["2025-10-14", "2025-10-15", "2025-10-20", "2025-10-21", "2025-10-28"], minutes=[20, 22, 24, 26, 28]),
        games(8, 1, ["2025-10-03", "2025-10-05", "2025-10-21"], minutes=10),
    ])
    rows = gl.season_rows(pg, SCHED, PRIORS)
    assert len(rows) > 20
    for r in rows.itertuples():
        ref = gl.features_as_of(pg, SCHED, PRIORS, r.PLAYER_ID, r.TEAM_ID, r.GAME_DATE)
        for f in gl.FEATURES:
            a, b = getattr(r, f), ref[f]
            assert (pd.isna(a) and pd.isna(b)) or a == pytest.approx(b), (f, r.GAME_DATE, a, b)


def test_features_ignore_everything_from_the_game_day_on():
    pg = games(7, 1, ["2025-10-01", "2025-10-03"])
    later = pd.concat([pg, games(7, 1, ["2025-10-05", "2025-10-07"], minutes=48)])
    for date in ["2025-10-05", "2025-10-09"]:
        before = later[later.GAME_DATE < D(date)]
        assert gl.features_as_of(later, SCHED, PRIORS, 7, 1, D(date)) == gl.features_as_of(before, SCHED, PRIORS, 7, 1, D(date))


def test_streaks_and_recent_misses():
    pg = games(7, 1, ["2025-10-01", "2025-10-03", "2025-10-05"])
    f = gl.features_as_of(pg, SCHED, PRIORS, 7, 1, D("2025-10-13"))
    # Missed Oct 7, 9, 11; played 3 of 6 stint games.
    assert (f["missed_streak"], f["missed_last5"], f["stint_games"], f["played_rate"]) == (3, 3, 6, 0.5)
    assert f["rest_days"] == 8 and f["games_last7"] == 0
    assert gl.features_as_of(pg, SCHED, PRIORS, 7, 2, D("2025-10-13")) is None  # no stint with team 2


# ---------------------------------------------------------------- live injury status


def test_out_on_the_report_is_near_zero_for_the_next_game_only():
    rows = pd.DataFrame({"PLAYER_ID": [7, 7, 8], "GAME_DATE": [D("2026-11-20"), D("2026-11-22"), D("2026-11-20")],
                         "next": [True, False, True]})
    p, why = gl.apply_injury_status(rows, [0.9, 0.9, 0.9], listed_out={7}, earliest_return=pd.Series(dtype=object))
    assert p.tolist() == [gl.OUT_PROBABILITY, 0.9, 0.9] and why == ["injury report", None, None]


def test_an_expected_return_date_zeroes_games_before_it_then_the_model_takes_over():
    rows = pd.DataFrame({"PLAYER_ID": [7, 7, 7], "GAME_DATE": [D("2026-11-20"), D("2026-11-25"), D("2026-11-28")],
                         "next": [True, False, False]})
    back = pd.Series({7: D("2026-11-25")})
    p, why = gl.apply_injury_status(rows, [0.8, 0.8, 0.8], listed_out={7}, earliest_return=back)
    assert p.tolist() == [gl.OUT_PROBABILITY, 0.8, 0.8] and why == ["return date", None, None]
    assert 0 <= gl.OUT_PROBABILITY <= 0.05


def test_fantasy_week_ends_on_sunday():
    assert gl.week_end(D("2026-11-19")) == D("2026-11-22")  # a Thursday
    assert gl.week_end(D("2026-11-22")) == D("2026-11-22")


def test_calibration_and_metrics_helpers():
    cal = {"x": [0.0, 0.5, 1.0], "y": [0.1, 0.4, 0.95]}
    p = gl.calibrated(np.array([-1, 0, 0.25, 1, 2]), cal)
    assert ((p >= 0) & (p <= 1)).all() and np.all(np.diff(p) >= 0)
    y = np.array([1, 0, 1, 1])
    assert gl.ece(np.array([1.0, 0.0, 1.0, 1.0]), y) == 0
    assert gl.log_loss(np.array([0.9, 0.1, 0.9, 0.9]), y) < gl.log_loss(np.full(4, 0.5), y)


# ---------------------------------------------------------------- quality gates (models/game_level_metrics.json)

metrics = json.loads(gl.METRICS_PATH.read_text()) if gl.METRICS_PATH.exists() else None
needs_metrics = pytest.mark.skipif(metrics is None, reason="game-level model not trained")


@needs_metrics
def test_gate_no_test_season_in_training_or_calibration():
    s = metrics["seasons"]
    assert s["test"] == gl.TEST_SEASONS == ["2024-25", "2025-26"]
    assert not set(s["test"]) & set(s["train"] + s["calibration"])
    assert s["calibration"] == [gl.VALIDATION_SEASON] and max(s["train"]) < gl.VALIDATION_SEASON
    assert metrics["gates"]["leakage"]["value"] == 0


@needs_metrics
def test_gate_beats_both_baselines_in_log_loss():
    t = metrics["test"]
    assert t["log_loss"] < t["log_loss_rate_so_far"]
    assert t["log_loss"] < t["log_loss_last_season"]


@needs_metrics
def test_gate_calibrated_on_test_seasons_with_a_chart():
    assert metrics["test"]["ece"] < 0.05
    assert gl.CHART_PATH.exists()


@needs_metrics
def test_gate_season_totals_no_worse_than_the_season_model():
    t = metrics["test"]
    assert t["season_model_mae"] == pytest.approx(15.6, abs=0.05)
    assert t["season_total_mae"] <= t["season_model_mae"] + 1.0


@needs_metrics
def test_gate_sanity():
    t = metrics["test"]
    assert t["healthy_rotation_mean"] >= 0.85 and t["healthy_rotation_rows"] > 1000
    for b in t["calibration"]:
        assert 0 <= b["predicted"] <= 1 and 0 <= b["actual"] <= 1


@needs_metrics
def test_gate_not_suspiciously_good():
    t = metrics["test"]
    assert t["accuracy"] <= gl.MAX_PLAUSIBLE_ACCURACY and t["auc"] <= gl.MAX_PLAUSIBLE_AUC
    # Playing or not is hard to call a day ahead; a much lower loss than this would mean leakage.
    assert t["log_loss"] > 0.25


@needs_metrics
def test_all_gates_pass_and_the_flag_needs_them():
    assert metrics["all_passed"] == all(g["passed"] for g in metrics["gates"].values())
    if config.GAME_LEVEL_BETA:
        assert metrics["all_passed"], "the beta is switched on but a quality gate fails"


# ---------------------------------------------------------------- on the full data (skips without it)

has_rows = gl.ROWS_PATH.exists() and data.raw_path("player_games", gl.TEST_SEASONS[0]).exists()
needs_rows = pytest.mark.skipif(not has_rows, reason="player-game rows not built")


@needs_rows
def test_leakage_recomputed_features_match_on_a_fresh_sample():
    rows = pd.read_parquet(gl.ROWS_PATH)
    sample = pd.concat([rows[rows.SEASON == s].sample(60, random_state=11) for s in ["2001-02", "2015-16", *gl.TEST_SEASONS]])
    assert gl.leakage_mismatches(sample, n=len(sample), seed=5) == 0


@needs_rows
def test_split_keeps_test_seasons_out():
    rows = pd.read_parquet(gl.ROWS_PATH, columns=["SEASON", "played"])
    train, val, test = gl.split(rows)
    assert set(test.SEASON) == set(gl.TEST_SEASONS)
    assert not set(train.SEASON) & set(gl.TEST_SEASONS) and set(val.SEASON) == {gl.VALIDATION_SEASON}
    assert len(train) + len(val) + len(test) == len(rows)


def test_live_schedule_drops_unfinished_past_games_and_played_ones():
    from next82.game_level import live_schedule
    d = pd.Timestamp
    finished = pd.DataFrame({"TEAM_ID": [1, 2], "GAME_ID": ["g1", "g1"], "GAME_DATE": [d("2026-11-24")] * 2})
    schedule = pd.DataFrame({
        "TEAM_ID": [1, 2, 1, 2, 1, 2, 1, 2],
        "GAME_ID": ["g1", "g1", "g2", "g2", "g3", "g3", "g4", "g4"],
        "GAME_DATE": [d("2026-11-24")] * 2 + [d("2026-11-25")] * 2 + [d("2026-11-26")] * 2 + [d("2026-11-28")] * 2})
    # Nothing final yet on the 25th: its games are still upcoming.
    sched, first = live_schedule(finished, schedule, data_day=d("2026-11-25"), today=d("2026-11-25"))
    assert first == d("2026-11-25") and set(sched.GAME_ID) == {"g1", "g2", "g3", "g4"}
    # Stats fetched mid-evening on the 25th, after another game there finished (so the data
    # day is the 26th) while g2 is in progress: g2 is neither history nor upcoming.
    sched, first = live_schedule(finished, schedule, data_day=d("2026-11-26"), today=d("2026-11-25"))
    assert first == d("2026-11-26") and set(sched.GAME_ID) == {"g1", "g3", "g4"}
    # Stats two days old: games since then were played, so upcoming starts today.
    sched, first = live_schedule(finished, schedule, data_day=d("2026-11-25"), today=d("2026-11-27"))
    assert first == d("2026-11-27") and set(sched.GAME_ID) == {"g1", "g4"}
