from datetime import datetime

import pandas as pd
import pytest

from next82 import injuries


@pytest.mark.parametrize("reason, injury_type, body", [
    ("Injury/Illness - Right Achilles Tendon; Repair / Surgery", "Achilles", "achilles tendon"),
    ("Injury/Illness - Right Achilles; Tendinitis", "soreness", "achilles"),      # not a rupture
    ("Injury/Illness - Left Patellar Tendon; Repair / Surgery", "patellar tendon", "patellar tendon"),
    ("Injury/Illness - Left Patellar Tendinitis", "soreness", "patellar tendinitis"),  # not a rupture
    ("Injury/Illness - Right Ankle Fracture/Dislocation", "dislocation", "ankle fracture/dislocation"),
    ("Injury/Illness - Left Fibula Fracture", "fracture", "fibula fracture"),
    ("Injury/Illness - Low back surgery", "surgery", "low back surgery"),
    ("Injury/Illness - Left ACL Repair /; Surgery", "ACL", "acl repair /"),
    ("Injury/Illness - Left Meniscus Tear", "meniscus", "meniscus tear"),
    ("Injury/Illness - Left Foot Fracture", "fracture", "foot fracture"),
    ("Injury/Illness - Left Shoulder; Labrum Tear", "labrum", "shoulder"),
    ("Injury/Illness - Right Knee Surgery", "surgery", "knee surgery"),
    ("Injury/Illness - Left Ankle; Sprain", "sprain", "ankle"),
    ("Injury/Illness - Left Hamstring; Strain", "strain", "hamstring"),
    ("Injury/Illness - Left Knee Injury; Management", "rest", "knee injury"),   # wrapped phrase
    ("Injury/Illness - N/a; Illness", "illness", None),
    ("Personal Reasons", "personal", None),
    ("League Suspension", "suspension", None),
    ("G League - Two-Way", "not injury", None),
    ("Injury/Illness - Left Lower Leg Injury", None, "lower leg injury"),     # unclear: logged, not guessed
])
def test_classify(reason, injury_type, body):
    c = injuries.classify(reason)
    assert c["injury_type"] == injury_type
    assert c["body_part"] == body


def test_join_reason_adds_separator_for_new_format():
    assert injuries._join_reason(["Injury/Illness - Right Achilles Tendon", "Repair / Surgery"]) == \
        "Injury/Illness - Right Achilles Tendon; Repair / Surgery"
    assert injuries._join_reason(["Injury/Illness - Left Groin; Strain"]) == "Injury/Illness - Left Groin; Strain"
    assert injuries._join_reason(["G League -", "Two-Way"]) == "G League - Two-Way"


def test_match_players_by_team_then_name():
    rosters = pd.DataFrame({
        "PLAYER_ID": [1, 2, 3],
        "PLAYER_NAME": ["Jalen Williams", "Jalen Williams", "Nikola Jokić"],
        "TEAM_FULL_NAME": ["Oklahoma City Thunder", "Chicago Bulls", "Denver Nuggets"],
    })
    report = pd.DataFrame({"player_name": ["Williams, Jalen", "Jokic, Nikola", "Unknown, Guy"],
                           "team": ["Oklahoma City Thunder", "Denver Nuggets", "Denver Nuggets"]})
    ids = injuries.match_players(report, rosters)
    assert ids.iloc[0] == 1 and ids.iloc[1] == 3 and pd.isna(ids.iloc[2])


def test_report_urls():
    assert injuries.report_url(datetime(2026, 10, 26, 17, 0)).endswith("Injury-Report_2026-10-26_05_00PM.pdf")
    assert injuries.legacy_report_url("2023-11-01").endswith("Injury-Report_2023-11-01_05PM.pdf")


def test_fetch_latest_steps_back_politely(monkeypatch):
    tried = []

    def fake_get(url):
        tried.append(url)
        return b"%PDF fake" if url.endswith("04_30PM.pdf") else None

    monkeypatch.setattr(injuries, "get", fake_get)
    monkeypatch.setattr(injuries.time, "sleep", lambda s: None)
    url, when, pdf = injuries.fetch_latest(datetime(2026, 10, 26, 17, 7, tzinfo=injuries.EASTERN))
    assert url.endswith("04_30PM.pdf") and len(tried) == 3  # 5:00, 4:45, 4:30


def test_reason_joins_and_cleanup():
    assert injuries._join_reason(["Injury/Illness - Right ACL Repair /", "Surgery"]) == "Injury/Illness - Right ACL Repair / Surgery"
    assert injuries.clean_reason("Injury/Illness - Right ACL Repair /; Surgery") == "Injury/Illness - Right ACL Repair / Surgery"
    assert injuries.clean_reason(None) is None


def test_missing_days_are_the_gaps_since_the_log_began():
    log = pd.DataFrame({"report_day": pd.to_datetime(["2026-10-26", "2026-10-27", "2026-10-31"])})
    missing = injuries.missing_days(log, pd.Timestamp("2026-11-02 05:00"))
    assert [f"{d:%m-%d}" for d in missing] == ["10-28", "10-29", "10-30", "11-01"]   # today isn't over yet
    assert injuries.missing_days(None, pd.Timestamp("2026-11-02")) == []
    # Never more than MAX_GAP_DAYS back.
    old = pd.DataFrame({"report_day": pd.to_datetime(["2025-01-01"])})
    assert len(injuries.missing_days(old, pd.Timestamp("2026-11-02"))) == injuries.MAX_GAP_DAYS


def test_fill_gaps_adds_each_missed_days_final_report(tmp_path, monkeypatch):
    log_path = tmp_path / "log.parquet"
    rows = lambda day, hour: pd.DataFrame({
        "team": ["Boston Celtics"], "player_name": ["Tatum, Jayson"], "status": ["Out"], "reason": ["x"],
        "PLAYER_ID": [1628369.0], "report_time": [pd.Timestamp(f"{day} {hour}")],
        "report_url": ["u"], "report_day": [pd.Timestamp(day)]})
    pd.concat([rows("2026-10-26", "17:00"), rows("2026-10-29", "00:45")]).to_parquet(log_path, index=False)
    monkeypatch.setattr(injuries, "paths", lambda season=None: (tmp_path / "now.parquet", log_path))
    asked = []

    def last_report_of(day):
        asked.append(day)
        return (None if day == pd.Timestamp("2026-10-28") else ("url", datetime(day.year, day.month, day.day, 23, 45), b"%PDF"))
    monkeypatch.setattr(injuries, "last_report_of", last_report_of)
    monkeypatch.setattr(injuries, "parsed_report", lambda pdf, url, when, rosters: (rows(f"{when:%Y-%m-%d}", "23:45"), []))

    filled = injuries.fill_gaps(pd.DataFrame(), today="2026-10-30")
    assert [f"{d:%m-%d}" for d in asked] == ["10-27", "10-28"]
    assert [f"{d:%m-%d}" for d in filled] == ["10-27"]          # no report found for the 28th: left out
    saved = pd.read_parquet(log_path)
    assert [f"{d:%m-%d}" for d in saved.report_day] == ["10-26", "10-27", "10-29"]
