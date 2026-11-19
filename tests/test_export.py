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
