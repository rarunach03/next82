import json

import pytest

from next82 import export
from next82.train import FORECASTS_PATH, HISTORY_PATH, METRICS_PATH, PAST_COMEBACKS_PATH

has_app_files = all(p.exists() for p in [FORECASTS_PATH, HISTORY_PATH, PAST_COMEBACKS_PATH, METRICS_PATH])
pytestmark = pytest.mark.skipif(not has_app_files, reason="app data files not built")


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("data")
    original = export.OUT_DIR
    export.OUT_DIR = out_dir
    try:
        export.main()
    finally:
        export.OUT_DIR = original
    return out_dir


def test_index_shape(out):
    index = json.loads((out / "index.json").read_text())
    assert index["meta"]["forecastSeason"] > index["meta"]["dataThrough"]
    players = index["players"]
    assert len(players) > 300
    assert [p["shown"] for p in players] == sorted((p["shown"] for p in players), reverse=True)
    for p in players:
        assert 0 <= p["shown"] <= 82
        if p["comeback"]:
            assert p["ifHealthy"] is not None and 0 <= p["setbackChance"] <= 1


def test_every_player_has_a_detail_file(out):
    index = json.loads((out / "index.json").read_text())
    for p in index["players"]:
        detail = json.loads((out / "players" / f"{p['id']}.json").read_text())
        assert len(detail["factors"]) == 6
        assert detail["history"]
        assert bool(detail["similar"]) == p["comeback"]


def test_search_text_is_accent_free(out):
    index = json.loads((out / "index.json").read_text())
    jokic = next(p for p in index["players"] if p["name"] == "Nikola Jokić")
    assert jokic["search"] == "nikola jokic"


def test_ranges_are_ordered_and_contain_the_forecast(out):
    index = json.loads((out / "index.json").read_text())
    for p in index["players"]:
        if p["preLow"] is not None:
            assert p["preLow"] <= p["preHigh"]
            assert p["preLow"] - 0.5 <= p["forecast"] <= p["preHigh"] + 0.5
        if p["updatedLow"] is not None:
            assert p["updatedLow"] <= p["updatedHigh"]
            assert p["updatedLow"] - 0.5 <= p["updated"] <= p["updatedHigh"] + 0.5


def test_unsigned_players_without_games_have_no_updated_forecast(out):
    index = json.loads((out / "index.json").read_text())
    unsigned = [p for p in index["players"] if p["notOnRoster"] and not p["playedSoFar"]]
    assert unsigned
    assert all(p["updated"] is None and p["tier"] is None for p in unsigned)


def test_tiers_only_for_rotation_players_with_an_updated_forecast(out):
    index = json.loads((out / "index.json").read_text())
    tiered = [p for p in index["players"] if p["tier"] is not None]
    assert tiered
    assert all(p["rotationRole"] and p["updated"] is not None for p in tiered)


def test_fantasy_file(out):
    path = out / "fantasy.json"
    if not path.exists():
        pytest.skip("fantasy prior not built")
    fantasy = json.loads(path.read_text())
    index = json.loads((out / "index.json").read_text())
    ranked = {p["id"] for p in fantasy["players"]}
    by_id = {p["id"]: p for p in index["players"]}
    # Ranked players all have an updated forecast; games line up with it. Rookies have
    # no preseason forecast, so they're only in fantasy.json.
    for p in fantasy["players"]:
        assert p["rookie"] or by_id[p["id"]]["updated"] is not None
        assert 0 <= p["restGames"] <= p["gamesLeft"]
        if p["restLow"] is not None:  # trade analyzer ranges
            assert p["restLow"] - 0.11 <= p["restGames"] <= p["restHigh"] + 0.11
    # Players with a preseason forecast but no updated one (unsigned, no games) aren't ranked.
    assert not any(by_id[i]["updated"] is None for i in ranked if i in by_id)


def test_accuracy_file(out):
    path = out / "accuracy.json"
    if not path.exists():
        pytest.skip("season hasn't started")
    a = json.loads(path.read_text())
    assert set(a["methods"]) == {"model", "last_season", "three_year"}
    assert a["gapRange"][0] <= a["gapRange"][1]
    dates = [t["date"] for t in a["trend"]]
    assert dates == sorted(dates) and dates[-1] == a["asOf"]


def test_overrides_flag_when_past_review_date(tmp_path, monkeypatch):
    import pandas as pd
    from next82 import export as ex, overrides

    if not overrides.PATH.exists():
        pytest.skip("no overrides file")
    o = overrides.load()
    o["review_by"] = pd.Timestamp("2000-01-01")  # long past
    path = tmp_path / "ov.csv"
    o.assign(**{c: o[c].dt.strftime("%Y-%m-%d") for c in overrides.DATE_COLUMNS}).to_csv(path, index=False)
    monkeypatch.setattr(overrides, "PATH", path)
    monkeypatch.setattr(ex, "OUT_DIR", tmp_path / "out")
    ex.main()
    players = json.loads((tmp_path / "out" / "index.json").read_text())["players"]
    manual = [p for p in players if p["override"] and p["override"]["kind"] == "manual"]
    assert manual and all(p["override"]["needsReview"] for p in manual)
    # Automatic overrides have no review date: they clear on their own.
    assert not any(p["override"]["needsReview"] for p in players if p["override"] and p["override"]["kind"] != "manual")


def test_stash_info(out):
    fantasy = json.loads((out / "fantasy.json").read_text())
    reasons = {"injury report", "long absence, no report", "manual", "automatic", "news"}
    flagged = [p for p in fantasy["players"] if p.get("out")]
    assert all(p["out"]["reason"] in reasons for p in flagged)
    # Override players are always marked out, with their kind as the reason.
    for p in fantasy["players"]:
        if p["override"]:
            assert p["out"] and p["out"]["reason"] == p["override"]["kind"]


def test_positions_are_listed_positions(out):
    """Index and fantasy rows carry the listed position (or None if it wasn't downloaded)."""
    from next82 import data

    allowed = {None, "G", "F", "C", "G-F", "F-G", "F-C", "C-F"}
    index = json.loads((out / "index.json").read_text())
    assert all(p["position"] in allowed for p in index["players"])
    fantasy_path = out / "fantasy.json"
    if fantasy_path.exists():
        assert all(p["position"] in allowed for p in json.loads(fantasy_path.read_text())["players"])
    if not data.saved_positions().empty:
        rostered = [p for p in index["players"] if p["team"]]
        assert sum(p["position"] is not None for p in rostered) >= 0.95 * len(rostered)


def _export_to(tmp_path, monkeypatch, beta: bool):
    from next82 import config

    monkeypatch.setattr(config, "GAME_LEVEL_BETA", beta)
    monkeypatch.setattr(export, "OUT_DIR", tmp_path)
    export.main()
    return json.loads((tmp_path / "index.json").read_text())


def test_game_beta_follows_the_flag(out):
    from next82 import config

    meta = json.loads((out / "index.json").read_text())["meta"]
    assert meta["gameBeta"] == (out / "games.json").exists()
    if not config.GAME_LEVEL_BETA:
        assert not meta["gameBeta"]


def test_game_beta_when_on(tmp_path, monkeypatch):
    from next82 import game_level

    meta = _export_to(tmp_path, monkeypatch, beta=True)["meta"]
    if not game_level.METRICS_PATH.exists() or not meta["seasonStarted"]:
        pytest.skip("no model or no season in progress")
    assert meta["gameBeta"]
    games = json.loads((tmp_path / "games.json").read_text())
    index = json.loads((tmp_path / "index.json").read_text())
    by_id = {p["id"]: p for p in index["players"]}
    assert len(games["players"]) > 300
    for pid, upcoming in games["players"].items():
        assert len(upcoming) >= 1
        assert [g["date"] for g in upcoming] == sorted(g["date"] for g in upcoming)
        assert all(0 <= g["p"] <= 1 and g["date"] >= games["asOf"] for g in upcoming)
        p = by_id.get(int(pid))
        o = p and p["override"]
        # An expected return date: every game before it is near zero.
        if o and o["earliestReturn"]:
            for g in upcoming:
                if g["date"] < o["earliestReturn"][:10]:
                    assert g["p"] <= 0.05 and g["override"] == "return date"
        # Listed Out on the latest report: the next game is near zero.
        if p and p["out"] and p["out"]["reason"] == "injury report" and p["out"]["status"] == "Out":
            assert upcoming[0]["p"] <= 0.05
    # Healthy rotation players (Safe tier, not out) are very likely to play next.
    safe = [games["players"][str(p["id"])][0]["p"] for p in index["players"]
            if p["tier"] == "Safe" and not p["out"] and str(p["id"]) in games["players"]]
    assert len(safe) > 50 and sum(safe) / len(safe) >= 0.85


def test_game_beta_failure_hides_it_and_the_export_finishes(tmp_path, monkeypatch):
    from next82 import game_level

    def broken(*args, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(game_level, "upcoming_rows", broken)
    index = _export_to(tmp_path, monkeypatch, beta=True)
    assert index["meta"]["gameBeta"] is False
    assert not (tmp_path / "games.json").exists()
    assert len(index["players"]) > 300 and (tmp_path / "fantasy.json").exists()


def test_game_beta_live_priors_match_training_priors():
    import pandas as pd

    from next82 import config, game_level
    from next82.features import OUTPUT_PATH, load_table
    from next82.preseason import load_forecasts

    if not OUTPUT_PATH.exists():
        pytest.skip("feature table not built")
    live = game_level.priors_from_forecasts(load_forecasts()).set_index("PLAYER_ID").sort_index()
    trained = game_level.prior_season(load_table(), config.FORECAST_SEASON).set_index("PLAYER_ID").sort_index()
    shared = live.index.intersection(trained.index)
    assert len(shared) > 300
    pd.testing.assert_frame_equal(live.loc[shared], trained.loc[shared], check_dtype=False)


def test_frozen_forecasts_keep_their_own_accuracy(out):
    """The live grading and the preseason note quote the model that made the frozen
    forecasts, even when a newer model makes the updated forecast."""
    from next82.preseason import FROZEN_MODEL

    metrics = json.loads(METRICS_PATH.read_text())
    frozen = metrics["results"][FROZEN_MODEL]
    acc = json.loads((out / "index.json").read_text())["meta"]["accuracy"]
    assert acc["frozenModelMae"] == round(frozen["mae_all"], 1)
    assert acc["modelMae"] == round(metrics["results"][metrics["final_model"]]["mae_all"], 1)
    assert acc["modelChanged"] == (metrics["final_model"] != FROZEN_MODEL)
    graded = out / "accuracy.json"
    if graded.exists():
        assert json.loads(graded.read_text())["testSeasons"]["model"] == round(frozen["mae_all"], 1)
    if acc["ablation"]:
        assert {g["name"] for g in acc["ablation"]["groups"]} >= {"Minutes and workload", "Games played history"}


def test_updated_forecast_uses_the_current_season_models_preseason_input():
    import pandas as pd

    from next82 import in_season
    from next82.preseason import load_forecasts
    from next82.train import FORECASTS_PATH

    snap = in_season.predict_current()
    if snap is None:
        pytest.skip("no season in progress")
    current = pd.read_parquet(FORECASTS_PATH).set_index("PLAYER_ID").pred_share
    frozen = load_forecasts().set_index("PLAYER_ID").pred_share
    shared = snap.PLAYER_ID[snap.PLAYER_ID.isin(current.index)]
    assert len(shared) > 300
    got = snap.set_index("PLAYER_ID").preseason_share.loc[shared]
    assert (got - current.loc[shared]).abs().max() < 1e-9
    # The frozen file is a different (older) model's output, and stays untouched.
    assert (frozen.loc[shared] - current.loc[shared]).abs().max() > 0
