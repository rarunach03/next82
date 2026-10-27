import pandas as pd
import pytest

from next82 import auto_overrides

TODAY = pd.Timestamp("2026-11-01")


def _log(rows):
    df = pd.DataFrame(rows)
    df["report_day"] = pd.to_datetime(df.report_day)
    df["report_url"] = "https://ak-static.cms.nba.com/referee/injury/x.pdf"
    df["reason"] = "Injury/Illness - " + df.body_part.fillna("") + "; " + df.injury_type
    df["player_name"] = df.PLAYER_ID.map(lambda i: f"Player {i}")
    return df


RECOVERY = pd.DataFrame([
    {"injury_type": "ACL", "body_part_contains": None, "earliest_days": 298, "latest_days": None,
     "can_be_season_ending": True, "basis": "ACL basis.", "source_url": "https://study/acl"},
    {"injury_type": "fracture", "body_part_contains": "foot", "earliest_days": 55, "latest_days": 69,
     "can_be_season_ending": False, "basis": "Foot basis.", "source_url": "https://study/foot"},
])
NO_NEWS = pd.DataFrame(columns=auto_overrides.NEWS_COLUMNS)


def _build(log, last_game=None, news=NO_NEWS, manual=(), player_games=None):
    return auto_overrides.build(log, RECOVERY, news, list(manual), pd.Series(last_game or {}, dtype="datetime64[ns]"),
                                player_games, TODAY)[0].set_index("player_id")


def test_serious_injury_gets_an_estimate_from_the_last_game():
    log = _log([{"PLAYER_ID": 1, "team": "A", "status": "Out", "injury_type": "ACL", "body_part": "acl tear",
                 "report_day": "2026-10-30"}])
    r = _build(log, last_game={1: pd.Timestamp("2026-10-20")}).loc[1]
    assert r.earliest_return == pd.Timestamp("2026-10-20") + pd.Timedelta(days=298)
    assert pd.isna(r.latest_return)              # can be season-ending
    assert r.estimated and r.kind == "automatic"
    assert r.source_url.startswith("https://ak-static.cms.nba.com") and r.source_url_2 == "https://study/acl"


def test_body_part_must_match_and_short_term_types_are_ignored():
    log = _log([
        {"PLAYER_ID": 1, "team": "A", "status": "Out", "injury_type": "fracture", "body_part": "hand fracture", "report_day": "2026-10-30"},
        {"PLAYER_ID": 2, "team": "A", "status": "Out", "injury_type": "sprain", "body_part": "ankle", "report_day": "2026-10-30"},
        {"PLAYER_ID": 3, "team": "A", "status": "Questionable", "injury_type": "ACL", "body_part": "acl", "report_day": "2026-10-30"},
    ])
    assert _build(log).empty


def test_window_for_types_that_arent_season_ending():
    log = _log([{"PLAYER_ID": 1, "team": "A", "status": "Out", "injury_type": "fracture", "body_part": "foot fracture",
                 "report_day": "2026-10-30"}])
    r = _build(log, last_game={1: pd.Timestamp("2026-10-25")}).loc[1]
    assert r.earliest_return == pd.Timestamp("2026-12-19") and r.latest_return == pd.Timestamp("2027-01-02")


def test_overdue_recovery_means_back_any_time():
    log = _log([{"PLAYER_ID": 1, "team": "A", "status": "Out", "injury_type": "fracture", "body_part": "foot fracture",
                 "report_day": "2026-10-30"}])
    r = _build(log, last_game={1: pd.Timestamp("2026-03-01")}).loc[1]
    assert r.earliest_return == TODAY
    assert r.latest_return == TODAY + pd.Timedelta(days=auto_overrides.OVERDUE_WINDOW_DAYS)


def test_manual_rows_win():
    log = _log([{"PLAYER_ID": 1, "team": "A", "status": "Out", "injury_type": "ACL", "body_part": "acl", "report_day": "2026-10-30"}])
    assert _build(log, manual=[1]).empty


def test_clears_when_off_the_teams_latest_listing_or_playing_again():
    log = _log([
        {"PLAYER_ID": 1, "team": "A", "status": "Out", "injury_type": "ACL", "body_part": "acl", "report_day": "2026-10-28"},
        {"PLAYER_ID": 9, "team": "A", "status": "Out", "injury_type": "sprain", "body_part": "ankle", "report_day": "2026-10-31"},
        {"PLAYER_ID": 2, "team": "B", "status": "Out", "injury_type": "ACL", "body_part": "acl", "report_day": "2026-10-28"},
    ])
    games = pd.DataFrame({"PLAYER_ID": [2], "GAME_DATE": ["2026-10-29"]})
    out = _build(log, player_games=games)
    assert 1 not in out.index   # team A's latest listing (Oct 31) no longer includes him
    assert 2 not in out.index   # played after the report


def test_team_timeline_from_news_replaces_the_estimate():
    log = _log([{"PLAYER_ID": 1, "team": "A", "status": "Out", "injury_type": "ACL", "body_part": "acl", "report_day": "2026-10-30"}])
    news = pd.DataFrame([{"player_id": 1, "earliest_return": pd.Timestamp("2027-01-10"),
                          "latest_return": pd.Timestamp("2027-01-31"), "note": "Re-evaluated in 10 weeks",
                          "source_url": "https://news/1", "date_found": TODAY}])
    r = _build(log, news=news).loc[1]
    assert r.kind == "news" and not r.estimated
    assert r.earliest_return == pd.Timestamp("2027-01-10") and r.source_url_2 == "https://news/1"


def test_recovery_table_file_is_complete():
    table = auto_overrides.load_recovery()
    assert set(table.injury_type) >= {"ACL", "Achilles", "labrum", "meniscus", "fracture"}
    assert table.source_url.str.startswith("https://").all()
    assert (table.earliest_days < table.average_days).all()


def test_latest_return_is_a_slow_recovery_not_the_average():
    # Half of players return later than the average, so a latest return must be past it.
    table = auto_overrides.load_recovery()
    with_latest = table[table.latest_days.notna()]
    assert (with_latest.latest_days > with_latest.average_days).all()
    # No latest return means it can be season-ending (or of unknown length).
    assert table[table.latest_days.isna()].can_be_season_ending.all()
