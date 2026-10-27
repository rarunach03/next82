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
