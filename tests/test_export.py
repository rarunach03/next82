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
