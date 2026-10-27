import json

import pandas as pd
import pytest

from next82 import export, overrides

TODAY = pd.Timestamp("2026-11-01")


def _forecast():
    # 10 played, 72 left; the model expects 80% of the rest (57.6), range 40%-95%.
    return pd.DataFrame({"PLAYER_ID": [7], "played_so_far": [10.0], "team_games_left": [72.0],
                         "predicted_rest": [57.6], "updated_total": [67.6],
                         "updated_low": [10 + 0.40 * 72], "updated_high": [10 + 0.95 * 72]})


def _schedule():
    # Team 1 plays one game a day from Nov 1 for 72 days.
    return pd.DataFrame({"TEAM_ID": 1, "GAME_DATE": pd.date_range(TODAY, periods=72)})


def _override(earliest=None, latest=None, review_by="2026-11-15"):
    return pd.DataFrame([{
        "player_id": 7, "player_name": "Test Player", "status": "Out",
        "earliest_return": pd.to_datetime(earliest), "latest_return": pd.to_datetime(latest),
        "note": "test", "source_url": "https://example.com", "date_added": TODAY,
        "review_by": pd.to_datetime(review_by),
    }])


def _apply(o):
    return overrides.apply(_forecast(), o, _schedule(), TODAY, pd.Series({7: 1})).iloc[0]


def test_return_window_sets_point_and_range():
    r = _apply(_override("2026-11-21", "2026-12-11"))  # games from day 20 and day 40
    assert r.updated_high == pytest.approx(10 + 0.95 * 52)   # earliest return, high-end share
    assert r.updated_low == pytest.approx(10 + 0.40 * 32)    # latest return, low-end share
    assert r.updated_total == pytest.approx(10 + 0.80 * 42)  # middle of the window
    assert r.updated_low <= r.updated_total <= r.updated_high
    assert not r.override_indefinite


def test_no_window_is_out_indefinitely_with_range_from_zero_more_games():
    r = _apply(_override())
    assert r.override_indefinite
    assert r.updated_low == 10                               # 0 more games
    assert r.updated_high == pytest.approx(10 + 0.95 * 72)
    assert r.updated_total == pytest.approx((r.updated_low + r.updated_high) / 2)


def test_only_latest_return_means_back_any_time_until_then():
    r = _apply(_override(latest="2026-12-11"))
    assert r.updated_high == pytest.approx(10 + 0.95 * 72)   # could be back today
    assert r.updated_low == pytest.approx(10 + 0.40 * 32)


def test_only_earliest_return_puts_the_low_end_at_zero_more_games():
    r = _apply(_override(earliest="2026-11-21"))
    assert r.updated_low == 10
    assert r.updated_total == pytest.approx(10 + 0.80 * 52)


def test_overdue_reviews_are_flagged():
    o = pd.concat([_override(review_by="2026-10-30"), _override(review_by="2026-11-15")])
    assert len(overrides.overdue(o, TODAY)) == 1


def test_csv_columns_and_dates(tmp_path):
    path = tmp_path / "overrides.csv"
    path.write_text(",".join(overrides.COLUMNS) + "\n7,Test,Out,,2026-12-01,note,https://x,2026-11-01,2026-11-15\n")
    o = overrides.load(path)
    assert pd.isna(o.earliest_return.iloc[0]) and o.latest_return.iloc[0] == pd.Timestamp("2026-12-01")
    path.write_text("player_id,status\n7,Out\n")
    with pytest.raises(ValueError):
        overrides.load(path)


def test_overrides_never_reach_the_accuracy_page(tmp_path, monkeypatch):
    if not overrides.PATH.exists():
        pytest.skip("no overrides file")
    ids = set(overrides.load().player_id)
    with_dir, without_dir = tmp_path / "with", tmp_path / "without"
    monkeypatch.setattr(export, "OUT_DIR", with_dir)
    export.main()
    monkeypatch.setattr(export, "OUT_DIR", without_dir)
    monkeypatch.setattr(overrides, "PATH", tmp_path / "none.csv")
    export.main()
    if not (with_dir / "accuracy.json").exists():
        pytest.skip("season hasn't started")
    a, b = (json.loads((d / "accuracy.json").read_text()) for d in (with_dir, without_dir))
    assert a == b
    # The overridden players do change in the forecasts, so the test isn't trivial.
    fa, fb = (json.loads((d / "index.json").read_text())["players"] for d in (with_dir, without_dir))
    changed = [x["id"] for x, y in zip(fa, fb) if x["id"] in ids and x["updated"] != y["updated"]]
    assert changed
