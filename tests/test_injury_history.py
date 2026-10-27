import pandas as pd

from next82 import injury_history as ih

DATE = pd.Timestamp("2025-01-15")


def _report(day, rows):
    return pd.DataFrame([{"PLAYER_ID": p, "team": t, "status": s, "injury_type": i, "report_day": pd.Timestamp(day)}
                         for p, t, s, i in rows], columns=["PLAYER_ID", "team", "status", "injury_type", "report_day"])


REPORTS = {
    # Team A played on the 14th: player 1 Out (ACL), player 2 Questionable.
    "2025-01-14": _report("2025-01-14", [(1, "A", "Out", "ACL"), (2, "A", "Questionable", "sprain")]),
    # Team B last played on the 12th: player 3 Out (strain).
    "2025-01-12": _report("2025-01-12", [(3, "B", "Out", "strain")]),
    # A week earlier: player 1 already Out, player 2 not listed.
    "2025-01-06": _report("2025-01-06", [(1, "A", "Out", "ACL")]),
}


def reports_for(day):
    return REPORTS.get(f"{day:%Y-%m-%d}", _report(day, []))


def test_only_reports_before_the_date_and_latest_per_team():
    REPORTS["2025-01-15"] = _report("2025-01-15", [(2, "A", "Out", "sprain")])  # same day: must not be used
    try:
        f = ih.snapshot_features("2024-25", DATE, None, {"ACL"}, reports_for)
    finally:
        del REPORTS["2025-01-15"]
    assert f.loc[2, "listed_level"] == ih.STATUS_LEVEL["Questionable"]
    assert f.loc[3, "listed_out"] == 1                    # team B's latest listing, 3 days back


def test_features():
    f = ih.snapshot_features("2024-25", DATE, None, {"ACL"}, reports_for)
    assert f.loc[1, "listed_out"] == 1 and f.loc[1, "serious_injury"] == 1
    assert f.loc[1, "out_week_ago"] == 1 and f.loc[1, "days_listed"] == 7 and f.loc[1, "status_trend"] == 0
    assert f.loc[2, "status_trend"] == ih.STATUS_LEVEL["Questionable"] and f.loc[2, "days_listed"] == 0
    assert f.loc[3, "serious_injury"] == 0 and f.loc[3, "days_listed"] == 1


def test_current_features_from_the_season_log(monkeypatch):
    monkeypatch.setattr(ih, "serious_types", lambda: {"ACL"})
    log = pd.concat([*REPORTS.values(), _report("2025-01-15", [(2, "A", "Out", "sprain")])], ignore_index=True)
    f = ih.current_features(log, DATE)
    assert f.loc[1, "listed_out"] == 1 and f.loc[1, "serious_injury"] == 1
    assert f.loc[2, "listed_level"] == ih.STATUS_LEVEL["Questionable"]   # today's report isn't used yet
    assert ih.current_features(None, DATE).empty


def test_snapshots_get_features_only_from_2019_20(monkeypatch):
    monkeypatch.setattr(ih, "serious_types", lambda: {"ACL"})
    monkeypatch.setattr(ih, "snapshot_features", lambda season, date, players, serious: pd.DataFrame(
        {c: [1] for c in ih.INJURY_FEATURES}, index=pd.Index([1], name="PLAYER_ID")))
    snaps = pd.DataFrame({"SEASON": ["2018-19", "2024-25", "2024-25"], "date": [DATE] * 3, "PLAYER_ID": [1, 1, 2]})
    out = ih.add_to_snapshots(snaps)
    assert out.loc[0, ih.INJURY_FEATURES].isna().all()                    # no reports before 2019-20
    assert out.loc[1, "listed_out"] == 1 and out.loc[2, "listed_out"] == 0  # not listed = 0
    assert ih.add_to_snapshots(out).equals(out)                            # safe to run twice


def test_serious_types_for_the_model_stay_fixed():
    # The model was validated with these; new recovery-table rows mustn't change its features.
    assert ih.serious_types() == {"ACL", "Achilles", "labrum", "meniscus", "fracture"}
