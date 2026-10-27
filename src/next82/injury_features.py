"""Do injury-report features improve the updated (rest-of-season) forecast?

Adds features from past NBA injury reports (2019-20 on; published before each
snapshot date) to the in-season snapshots, then retrains the forecast and range
models with and without them. The decision uses rolling validation only: each of
VALIDATION_SEASONS is scored by models trained on the seasons before it (range
corrections measured on the season before that), and results are averaged. The
features are kept only if the average MAE improves, and so does the group they're
meant for (listed Out on the report while the absence streak is under 3 games, i.e.
before the game logs can show it), without hurting range coverage. The test seasons
are scored once, after the decision.

Usage:
    python -m next82.injury_features
"""
import json

import numpy as np
import pandas as pd

from next82 import config, in_season, injury_history, intervals

METRICS_PATH = config.MODELS_DIR / "injury_features_metrics.json"
VALIDATION_SEASONS = ["2021-22", "2022-23", "2023-24"]
NEW_OUT = "listed Out, absent under 3 games"
COVERAGE_SLACK = 0.01   # coverage may drift this much further from the target


def compare(snaps: pd.DataFrame, train_before: str, seasons: list[str], params: dict, val_for_ranges: pd.DataFrame,
            ranges_train: pd.DataFrame) -> dict:
    """MAE and range coverage on `seasons`, with and without injury features."""
    base = in_season.BASE_FEATURES
    plus = base + injury_history.INJURY_FEATURES
    train, test = snaps[snaps.SEASON < train_before], snaps[snaps.SEASON.isin(seasons)]
    third = in_season.season_third(test.season_progress)
    out_now = ((test.has_played == 1) & (test.absence_streak >= in_season.OUT_STREAK_GAMES)).to_numpy()
    new_out = ((test.listed_out == 1) & (test.absence_streak < 3)).to_numpy()
    groups = {"all": np.ones(len(test), bool), **{n: third == t for t, n in enumerate(in_season.THIRDS)},
              "currently out (5+ games)": out_now, NEW_OUT: new_out}
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


def previous(season: str) -> str:
    return config.SEASONS[config.SEASONS.index(season) - 1]


def score(snaps: pd.DataFrame, season_list: list[str], params: dict) -> dict:
    """compare() for seasons scored together, trained before the first of them."""
    first = season_list[0]
    return compare(snaps, first, season_list, params,
                   snaps[snaps.SEASON == previous(first)], snaps[snaps.SEASON < previous(first)])


def average(per_season: dict) -> dict:
    """Simple average over seasons of each model's MAE and coverage by group."""
    seasons = list(per_season.values())
    return {model: {g: {k: float(np.mean([s[model][g][k] for s in seasons])) for k in ("n", "mae", "coverage")}
                    for g in seasons[0][model]}
            for model in seasons[0]}


def decide(avg: dict) -> tuple[bool, dict]:
    """Keep if average MAE improves overall and in NEW_OUT, and coverage gets no worse in either."""
    off = lambda r: abs(r["coverage"] - intervals.COVERAGE)
    checks = {}
    for g in ("all", NEW_OUT):
        a, b = avg["without"][g], avg["with injury features"][g]
        checks[f"{g}: MAE improves"] = b["mae"] < a["mae"]
        checks[f"{g}: coverage no worse"] = off(b) <= off(a) + COVERAGE_SLACK
    return all(checks.values()), checks


def _print(title: str, r: dict):
    print(f"\n{title}: MAE (games) / range coverage, without -> with injury features")
    for g in r["without"]:
        a, b = r["without"][g], r["with injury features"][g]
        print(f"  {g:34s} n={a['n']:7.0f}  MAE {a['mae']:.3f} -> {b['mae']:.3f}   "
              f"coverage {a['coverage']:.0%} -> {b['coverage']:.0%}")


def main():
    snaps = injury_history.add_to_snapshots(pd.read_parquet(in_season.SNAPSHOTS_PATH))
    params = json.loads(in_season.METRICS_PATH.read_text())["params"]
    per_season = {s: score(snaps, [s], params) for s in VALIDATION_SEASONS}
    for s, r in per_season.items():
        _print(f"Validation {s}", r)
    avg = average(per_season)
    _print("Validation average of " + ", ".join(VALIDATION_SEASONS), avg)
    keep, checks = decide(avg)
    for name, ok in checks.items():
        print(f"  {'pass' if ok else 'FAIL'}  {name}")
    print(f"\nKeep injury features: {keep}  (decided before looking at the test seasons)")

    tests = in_season.TEST_SEASONS
    test = score(snaps, tests, params)
    _print("Test " + " and ".join(tests) + " (reported once, after deciding)", test)
    METRICS_PATH.write_text(json.dumps({"keep": bool(keep), "checks": checks, "validation_seasons": per_season,
                                        "validation_average": avg, "test": test}, indent=2))


if __name__ == "__main__":
    main()
