from datetime import datetime

import pandas as pd
import pytest

from next82 import injuries


@pytest.mark.parametrize("reason, injury_type, body", [
    ("Injury/Illness - Right Achilles Tendon; Repair / Surgery", "Achilles", "achilles tendon"),
    ("Injury/Illness - Right Achilles; Tendinitis", "soreness", "achilles"),      # not a rupture
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
