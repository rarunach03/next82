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


def test_serious_injury_gets_an_estimate():
    # Hurt in the last game played (Oct 29), listed the next day: counted from the listing.
    log = _log([{"PLAYER_ID": 1, "team": "A", "status": "Out", "injury_type": "ACL", "body_part": "acl tear",
                 "report_day": "2026-10-30"}])
    r = _build(log, last_game={1: pd.Timestamp("2026-10-29")}).loc[1]
    assert r.earliest_return == pd.Timestamp("2026-10-30") + pd.Timedelta(days=298)
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
    start = pd.Timestamp("2026-10-30")  # later than the last game
    assert r.earliest_return == start + pd.Timedelta(days=55) and r.latest_return == start + pd.Timedelta(days=69)


def test_overdue_recovery_means_back_any_time():
    # Already out at the end of last season, so counted from his March game: overdue now.
    log = _log([{"PLAYER_ID": 1, "team": "A", "status": "Out", "injury_type": "fracture", "body_part": "foot fracture",
                 "report_day": "2026-10-30"}])
    end = pd.DataFrame({"PLAYER_ID": [1], "status": ["Out"], "injury_type": ["fracture"]})
    r = auto_overrides.build(log, RECOVERY, NO_NEWS, [], pd.Series({1: pd.Timestamp("2026-03-01")}), None, TODAY,
                             end)[0].set_index("player_id").loc[1]
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
    assert set(table.injury_type) >= {"ACL", "Achilles", "labrum", "meniscus", "fracture", "dislocation",
                                      "surgery", "patellar tendon"}
    for injury_type, body in [("fracture", "tibia fracture"), ("fracture", "fibula fracture"), ("fracture", "hand"),
                              ("fracture", "wrist fracture"), ("dislocation", "ankle fracture/dislocation"),
                              ("surgery", "low back surgery"), ("patellar tendon", "patellar tendon")]:
        assert auto_overrides.recovery_row(table, injury_type, body) is not None, (injury_type, body)
    # Minor or unstudied versions are left to the model.
    for injury_type, body in [("dislocation", "ring finger dislocation"), ("fracture", "finger fracture"),
                              ("surgery", "right knee surgery")]:
        assert auto_overrides.recovery_row(table, injury_type, body) is None, (injury_type, body)
    assert table.basis.notna().all()
    assert table.source_url.str.startswith("https://").all()
    assert (table.earliest_days < table.average_days).all()


def test_latest_return_is_a_slow_recovery_not_the_average():
    # Half of players return later than the average, so a latest return must be past it.
    table = auto_overrides.load_recovery()
    with_latest = table[table.latest_days.notna()]
    assert (with_latest.latest_days > with_latest.average_days).all()
    # No latest return means it can be season-ending (or of unknown length).
    assert table[table.latest_days.isna()].can_be_season_ending.all()


def test_injury_start_uses_the_later_date_unless_already_out_at_season_end():
    last, first = pd.Timestamp("2026-04-10"), pd.Timestamp("2026-10-26")
    assert auto_overrides.injury_start(last, first, listed_before_season=False) == first   # offseason injury
    assert auto_overrides.injury_start(last, first, listed_before_season=True) == last     # predates the season
    assert auto_overrides.injury_start(pd.NaT, first, False) == first                      # no games at all


def test_offseason_injury_counts_from_first_listing():
    log = _log([{"PLAYER_ID": 1, "team": "A", "status": "Out", "injury_type": "fracture", "body_part": "foot fracture",
                 "report_day": "2026-10-30"}])
    r = _build(log, last_game={1: pd.Timestamp("2026-04-10")}).loc[1]
    assert r.earliest_return == pd.Timestamp("2026-10-30") + pd.Timedelta(days=55)
    end = pd.DataFrame({"PLAYER_ID": [1], "status": ["Out"], "injury_type": ["surgery"]})
    r = auto_overrides.build(log, RECOVERY, NO_NEWS, [], pd.Series({1: pd.Timestamp("2026-04-10")}), None, TODAY, end)[0].iloc[0]
    assert r.earliest_return == TODAY  # counted from April: overdue, back any day


def test_out_on_last_playoff_report_counts_from_last_playoff_game():
    log = _log([{"PLAYER_ID": 1, "team": "A", "status": "Out", "injury_type": "ACL", "body_part": "acl repair",
                 "report_day": "2026-10-26"}])
    # Reports from the last regular-season day and the team's last playoff game day.
    end = pd.DataFrame({"PLAYER_ID": [2, 1], "status": ["Out", "Out"], "injury_type": ["sprain", "ACL"],
                        "report_day": pd.to_datetime(["2026-04-12", "2026-05-10"])})
    last_playoff_game = pd.Timestamp("2026-05-01")
    r = auto_overrides.build(log, RECOVERY, NO_NEWS, [], pd.Series({1: last_playoff_game}), None, TODAY, end)[0].iloc[0]
    assert r.earliest_return == last_playoff_game + pd.Timedelta(days=298)


def test_body_part_alternatives_and_first_matching_row_wins():
    table = pd.DataFrame([
        {"injury_type": "fracture", "body_part_contains": "tibia|lower leg", "earliest_days": 230},
        {"injury_type": "fracture", "body_part_contains": "fibula", "earliest_days": 39},
    ])
    assert auto_overrides.recovery_row(table, "fracture", "lower leg fracture").earliest_days == 230
    assert auto_overrides.recovery_row(table, "fracture", "tibia and fibula fracture").earliest_days == 230
    assert auto_overrides.recovery_row(table, "fracture", "fibula fracture").earliest_days == 39
    assert auto_overrides.recovery_row(table, "fracture", None) is None


def _manual(added):
    return pd.DataFrame([{"player_id": 1, "player_name": "Player 1", "source_url": "https://manual/1",
                          "date_added": pd.Timestamp(added)}])


def test_news_found_after_a_manual_row_wins_and_manual_is_the_fallback():
    news = pd.DataFrame([{"player_id": 1, "earliest_return": pd.Timestamp("2027-01-10"), "latest_return": pd.NaT,
                          "note": "Out 10 weeks (ESPN, Oct 30)", "source_url": "https://news/1",
                          "date_found": pd.Timestamp("2026-10-31"), "source_date": pd.Timestamp("2026-10-30")}])
    rows, lines = auto_overrides.news_over_manual(news, _manual("2026-10-26"), TODAY)
    r = rows.iloc[0]
    assert r.kind == "news" and not r.estimated and r.earliest_return == pd.Timestamp("2027-01-10")
    assert r.source_url == "https://news/1" and r.source_url_2 == "https://manual/1" and len(lines) == 1
    # A manual row added after the news was found still wins.
    assert auto_overrides.news_over_manual(news, _manual("2026-11-01"), TODAY)[0].empty
    assert auto_overrides.news_over_manual(news.iloc[:0], _manual("2026-10-26"), TODAY)[0].empty


def test_most_recently_found_news_row_is_used():
    news = pd.DataFrame([
        {"player_id": 1, "earliest_return": pd.Timestamp("2027-02-01"), "date_found": pd.Timestamp("2026-10-31")},
        {"player_id": 1, "earliest_return": pd.Timestamp("2027-01-01"), "date_found": pd.Timestamp("2026-10-28")},
    ])
    assert auto_overrides.latest_news(news)[1].earliest_return == pd.Timestamp("2027-02-01")


def test_expired_news_timeline_falls_back_to_the_estimate():
    log = _log([{"PLAYER_ID": 1, "team": "A", "status": "Out", "injury_type": "fracture", "body_part": "foot fracture",
                 "report_day": "2026-10-30"}])
    stale = pd.DataFrame([{"player_id": 1, "earliest_return": pd.Timestamp("2026-10-15"),
                           "latest_return": pd.Timestamp("2026-10-25"), "note": "Update in 3 months",
                           "source_url": "https://news/1", "date_found": pd.Timestamp("2026-10-27")}])
    rows, lines = auto_overrides.build(log, RECOVERY, stale, [], pd.Series({1: pd.Timestamp("2026-10-29")}), None, TODAY)
    assert rows.iloc[0].kind == "automatic" and any("expired" in line for line in lines)
    assert auto_overrides.news_over_manual(stale, _manual("2026-10-26"), TODAY)[0].empty


def test_reevaluation_timeline_is_flagged_and_rejected_sources_are_dropped(tmp_path, monkeypatch):
    log = _log([{"PLAYER_ID": 1, "team": "A", "status": "Out", "injury_type": "strain", "body_part": "hamstring strain",
                 "report_day": "2026-10-30"}])
    news = pd.DataFrame([{"player_id": 1, "earliest_return": pd.Timestamp("2026-11-08"), "latest_return": pd.NaT,
                          "note": "Re-evaluated in 2 weeks", "source_url": "https://news/1",
                          "date_found": TODAY, "source_date": TODAY, "timeline_type": "re-evaluation"}])
    r = _build(log, news=news).loc[1]
    assert r.kind == "news" and r.reevaluation and r.earliest_return == pd.Timestamp("2026-11-08")
    path = tmp_path / "news.csv"
    news.to_csv(path, index=False)
    rejected = tmp_path / "rejected.csv"
    pd.DataFrame([{"player_id": 1, "source_url": "https://news/1", "reason": "x", "date_rejected": "2026-10-27"}]).to_csv(rejected, index=False)
    monkeypatch.setattr(auto_overrides, "REJECTED_PATH", rejected)
    assert auto_overrides.load_news(path).empty
