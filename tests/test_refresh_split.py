"""The daily refresh is split: the Mac downloads the NBA stats, the cloud reads the injury
report and rebuilds the site. These check each half does only its part, that the news
schedule is shared through a committed file, and that the site data check catches a
broken export."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from next82 import config, data, injuries, news

ROOT = Path(__file__).resolve().parents[1]
STATS = ["fetch_current_rosters", "fetch_draft", "fetch_positions", "fetch_schedule", "fetch_season_to_date"]


@pytest.fixture
def calls(monkeypatch):
    made = []
    rosters = pd.DataFrame({"PLAYER_ID": [1], "TEAM_ID": [2]})
    for name in STATS:
        def fake(season=None, _name=name):
            made.append(_name)
            if _name == "fetch_season_to_date":
                return pd.DataFrame(), pd.DataFrame()
            if _name == "fetch_positions":
                return pd.DataFrame({"POSITION": ["G"]})
            if _name == "fetch_schedule":
                return pd.DataFrame({"GAME_ID": [1]})
            return rosters
        monkeypatch.setattr(data, name, fake)
    monkeypatch.setattr(injuries, "refresh", lambda r, season=None: made.append("injury report"))
    monkeypatch.setattr(data, "saved_rosters", lambda season=None: made.append("saved rosters") or rosters)
    monkeypatch.setattr(config, "REQUEST_DELAY", 0)
    return made


def test_stats_only_never_reads_the_injury_report(calls):
    data.refresh_current(injury_report=False)
    assert calls == STATS[:4] + ["fetch_season_to_date"]


def test_injuries_only_never_calls_the_stats_api(calls):
    data.refresh_current(stats=False)
    assert calls == ["saved rosters", "injury report"]


def test_full_refresh_does_both(calls):
    data.refresh_current()
    assert set(calls) == set(STATS) | {"injury report"}


def test_stats_calls_are_retried(monkeypatch):
    monkeypatch.setattr(data.time, "sleep", lambda s: None)
    tries = []

    def flaky():
        tries.append(1)
        if len(tries) < 3:
            raise TimeoutError
        return "ok"
    assert data._retry(flaky, "test") == "ok" and len(tries) == 3
    with pytest.raises(TimeoutError):
        data._retry(lambda: (_ for _ in ()).throw(TimeoutError()), "test", tries=2)


def test_news_schedule_is_committed_not_kept_in_git_internals():
    assert news.STATE_PATH == ROOT / "data" / "news_state.json"
    assert ".git" not in news.STATE_PATH.parts
    state = news.load_state()
    assert {"last_run", "serious_out", "players"} <= set(state)


def test_site_data_check_passes_a_good_export_and_catches_a_broken_one(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_site_data", ROOT / "scripts" / "check_site_data.py")
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)

    (tmp_path / "players").mkdir()
    players = [{"id": i} for i in range(400)]
    for p in players:
        (tmp_path / "players" / f"{p['id']}.json").write_text("{}")
    for name in ("accuracy.json", "fantasy.json"):
        (tmp_path / name).write_text("{}")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    index = {"meta": {"generatedAt": now, "gameBeta": False}, "teams": [{}] * 30, "players": players}
    (tmp_path / "index.json").write_text(json.dumps(index))
    monkeypatch.setattr(check, "DATA", tmp_path)
    assert check.problems() == []

    (tmp_path / "players" / "3.json").unlink()
    (tmp_path / "fantasy.json").write_text("{broken")
    index["players"] = players[:100]
    index["meta"]["generatedAt"] = "2026-01-01T00:00:00+00:00"
    (tmp_path / "index.json").write_text(json.dumps(index))
    found = " | ".join(check.problems())
    for expected in ("only 100 players", "wasn't just generated", "fantasy.json", "no player file"):
        assert expected in found
