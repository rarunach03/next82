"""Do injury-report features improve the updated (rest-of-season) forecast?

Adds features from past NBA injury reports (2019-20 on; published before each
snapshot date) to the in-season snapshots, then retrains the forecast and range
models with and without them. Kept only if validation MAE improves without hurting
range coverage.

Usage:
    python -m next82.injury_features
"""
import json

import numpy as np
import pandas as pd

from next82 import config, in_season, injury_history, intervals

METRICS_PATH = config.MODELS_DIR / "injury_features_metrics.json"


def add_features(snaps: pd.DataFrame) -> pd.DataFrame:
    """Injury features for each snapshot (missing before 2019-20, when no reports exist)."""
    serious = injury_history.serious_types()
    first = injury_history.FIRST_SEASON
    parts = []
    for (season, date), rows in snaps.groupby(["SEASON", "date"]):
        rows = rows.copy()
        if season >= first:
            f = injury_history.snapshot_features(season, pd.Timestamp(date), None, serious)
            rows = rows.join(f, on="PLAYER_ID")
            rows[injury_history.INJURY_FEATURES] = rows[injury_history.INJURY_FEATURES].fillna(0)
        else:
            for c in injury_history.INJURY_FEATURES:
                rows[c] = np.nan
        parts.append(rows)
    return pd.concat(parts).sort_index()


def compare(snaps: pd.DataFrame, train_before: str, seasons: list[str], params: dict, val_for_ranges: pd.DataFrame,
            ranges_train: pd.DataFrame) -> dict:
    """MAE and range coverage on `seasons`, with and without injury features."""
    base = in_season.IN_SEASON_FEATURES
    plus = base + injury_history.INJURY_FEATURES
    train, test = snaps[snaps.SEASON < train_before], snaps[snaps.SEASON.isin(seasons)]
    third = in_season.season_third(test.season_progress)
    out_now = ((test.has_played == 1) & (test.absence_streak >= in_season.OUT_STREAK_GAMES)).to_numpy()
    groups = {"all": np.ones(len(test), bool), **{n: third == t for t, n in enumerate(in_season.THIRDS)},
              "currently out (5+ games)": out_now}
    result = {}
    for name, feats in [("without", base), ("with injury features", plus)]:
        point = in_season.predict_rest(in_season.fit(train, feats, **params), test, feats)
        adjust = in_season.range_adjustments(in_season.fit_range(ranges_train, feats, **params), val_for_ranges, feats)
        low, high = in_season.predict_range(in_season.fit_range(train, feats, **params), adjust, point, test, feats)
        err = np.abs(point - test.games_after.to_numpy())
        result[name] = {g: {"n": int(m.sum()), "mae": float(err[m].mean()),
                            "coverage": intervals.coverage(low[m], high[m], test.games_after.to_numpy()[m])}
                        for g, m in groups.items()}
    return result


def main():
    snaps = add_features(pd.read_parquet(in_season.SNAPSHOTS_PATH))
    params = json.loads(in_season.METRICS_PATH.read_text())["params"]
    val_season, tests = in_season.VALIDATION_SEASON, in_season.TEST_SEASONS
    # Range corrections are measured on the season before the one being scored.
    val = compare(snaps, val_season, [val_season], params,
                  snaps[snaps.SEASON == "2022-23"], snaps[snaps.SEASON < "2022-23"])
    test = compare(snaps, tests[0], tests, params,
                   snaps[snaps.SEASON == val_season], snaps[snaps.SEASON < val_season])
    for title, r in [(f"Validation {val_season}", val), ("Test " + " and ".join(tests), test)]:
        print(f"\n{title}: MAE (games) / range coverage, without -> with injury features")
        for g in r["without"]:
            a, b = r["without"][g], r["with injury features"][g]
            print(f"  {g:26s} n={a['n']:6d}  MAE {a['mae']:.3f} -> {b['mae']:.3f}   coverage {a['coverage']:.0%} -> {b['coverage']:.0%}")
    v0, v1 = val["without"]["all"], val["with injury features"]["all"]
    keep = v1["mae"] < v0["mae"] and abs(v1["coverage"] - intervals.COVERAGE) <= abs(v0["coverage"] - intervals.COVERAGE) + 0.01
    print(f"\nKeep injury features: {keep}")
    METRICS_PATH.write_text(json.dumps({"keep": bool(keep), "validation": val, "test": test}, indent=2))


if __name__ == "__main__":
    main()
