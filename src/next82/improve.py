"""Improving the season model: ablation, candidate features and tuning, on validation only.

Every decision here uses rolling validation folds: each of VALIDATION_SEASONS is
predicted by a model trained only on earlier seasons. The test seasons (the last
config.N_TEST_SEASONS labeled seasons) are excluded before anything else happens and
are read only by `final`, once, to report the final comparison.

A candidate feature group is kept only if it lowers the average validation miss by at
least KEEP_MIN_GAIN games AND lowers it in at least KEEP_MIN_FOLDS of the folds (each
model averaged over SEEDS), so a lucky season can't carry it.

Usage:
    python -m next82.improve ablation     # what each existing feature group is worth (+ chart)
    python -m next82.improve chart        # redraw the ablation chart from saved results
    python -m next82.improve candidates   # try new feature groups, one at a time
    python -m next82.improve tune         # light tuning of the chosen model
"""
import argparse
import json

import numpy as np
import pandas as pd

from next82 import config, evaluate, models
from next82.features import COMEBACK_FEATURES, FEATURES, TARGET, load_table

RESULTS_PATH = config.MODELS_DIR / "improve.json"
CHART_PATH = config.MODELS_DIR / "ablation.png"

# Feature seasons used as validation folds (targets 2019-20 to 2023-24), all before the test seasons.
VALIDATION_SEASONS = ["2018-19", "2019-20", "2020-21", "2021-22", "2022-23"]
SEEDS = [42, 7, 2024]
KEEP_MIN_GAIN = 0.05
KEEP_MIN_FOLDS = 4

# The existing features, grouped by what they describe.
GROUPS = {
    "Age and experience": ["age", "years_since_draft", "undrafted", "seasons_in_data"],
    "Body size": ["height_in", "weight_lb"],
    "Games played history": ["gp_share", "gp_share_lag1", "gp_share_lag2", "avg_gp_share_3yr", "missed_season",
                             "missed_season_lag1"],
    "Absences (injury history)": ["longest_gap", "n_major_gaps", "missed_start", "missed_end", "longest_gap_lag1",
                                  "missed_end_lag1", "major_gaps_3yr"],
    "Minutes and workload": ["mpg", "min_share", "mpg_lag1"],
    "Role (usage)": ["usg_pct"],
    "Team changes": ["n_teams"],
    "Comeback inputs": COMEBACK_FEATURES,
}


def labeled_before_test(df: pd.DataFrame) -> pd.DataFrame:
    """Labeled rows with the test seasons removed (the only rows decisions may see)."""
    train, test = evaluate.split(df)
    assert not set(VALIDATION_SEASONS) & set(test.SEASON), "a validation fold is a test season"
    return train


def folds(df: pd.DataFrame):
    """(season, train rows, validation rows): train on every season before the fold."""
    rows = labeled_before_test(df)
    for season in VALIDATION_SEASONS:
        idx = config.SEASONS.index(season)
        yield season, rows[rows.season_idx < idx], rows[rows.season_idx == idx]


def lightgbm(seed: int, **params):
    return models.lightgbm().set_params(random_state=seed, **params)


def fold_maes(df: pd.DataFrame, features: list[str], params: dict | None = None, model: str = "LightGBM") -> pd.Series:
    """Validation average miss (games) per fold; LightGBM is averaged over SEEDS."""
    out = {}
    for season, train, val in folds(df):
        if model == "LightGBM":
            preds = [np.clip(lightgbm(s, **(params or {})).fit(train[features], train[TARGET]).predict(val[features]), 0, 1)
                     for s in SEEDS]
            out[season] = float(np.mean([evaluate.mae_games(val, p) for p in preds]))
        else:
            out[season] = evaluate.mae_games(val, models.predict(models.fit(model, train, features), val, features))
    return pd.Series(out)


def compare(base: pd.Series, new: pd.Series) -> dict:
    """Average change in validation miss (negative is better) and folds improved."""
    diff = new - base
    return {"mean": float(new.mean()), "change": float(diff.mean()), "folds_better": int((diff < 0).sum()),
            "per_fold": {k: round(float(v), 3) for k, v in new.items()}}


def keeps(result: dict) -> bool:
    return -result["change"] >= KEEP_MIN_GAIN and result["folds_better"] >= KEEP_MIN_FOLDS


def load_results() -> dict:
    return json.loads(RESULTS_PATH.read_text()) if RESULTS_PATH.exists() else {}


def save_results(results: dict):
    RESULTS_PATH.write_text(json.dumps(results, indent=2) + "\n")


def ablation(df: pd.DataFrame) -> dict:
    """Retrain without each group; the bigger the miss grows, the more the group matters."""
    assert set(sum(GROUPS.values(), [])) == set(FEATURES), "every feature belongs to exactly one group"
    full = fold_maes(df, FEATURES)
    out = {"validation_seasons": VALIDATION_SEASONS, "seeds": SEEDS, "all_features": compare(full, full), "without": {},
           "other_models": {}}
    # Groups overlap (e.g. games played and comeback inputs), so dropping one can look cheap
    # when another carries the same information; "alone" shows what each knows by itself.
    out["alone"] = {}
    for name, cols in GROUPS.items():
        out["without"][name] = compare(full, fold_maes(df, [f for f in FEATURES if f not in cols]))
        out["alone"][name] = compare(full, fold_maes(df, cols))
        print(f"  without {name:28s} {out['without'][name]['change']:+.3f} games   alone {out['alone'][name]['mean']:.3f}")
    for name in ["Linear regression", "Same as last year", "3-year average"]:
        out["other_models"][name] = compare(full, fold_maes(df, FEATURES, model=name))
    print(f"  LightGBM, all features: {full.mean():.3f}; " + ", ".join(
        f"{k} {v['mean']:.3f}" for k, v in out["other_models"].items()))
    return out


def save_chart(ablation_result: dict, path=CHART_PATH):
    """Two panels: each feature group's validation miss on its own, and how much the miss
    grows when the group is left out of the full model."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    full = ablation_result["all_features"]["mean"]
    order = sorted(ablation_result["alone"], key=lambda k: ablation_result["alone"][k]["mean"], reverse=True)
    alone = [ablation_result["alone"][k]["mean"] for k in order]
    without = [ablation_result["without"][k]["change"] for k in order]
    fig, (a, b) = plt.subplots(1, 2, figsize=(9, 3.8), dpi=120, sharey=True)
    a.barh(order, alone, color="#3987e5", height=0.6)
    a.axvline(full, color="#ff7a1a", lw=1.5, ls="--")
    a.text(full, len(order) - 0.4, f" all features {full:.1f}", color="#ff7a1a", fontsize=8, va="bottom")
    a.set_xlim(min(alone + [full]) - 1, max(alone) + 0.5)
    a.set_xlabel("Average miss using only this group (games)")
    b.barh(order, without, color=["#ff7a1a" if v > 0 else "#9aa3af" for v in without], height=0.6)
    b.axvline(0, color="#6b7380", lw=1)
    b.set_xlabel("Extra miss when the group is left out (games)")
    for ax in (a, b):
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("step", choices=["ablation", "chart"])
    args = parser.parse_args()
    df = load_table()
    results = load_results()
    if args.step == "ablation":
        results["ablation"] = ablation(df)
    if args.step in ("ablation", "chart"):
        save_chart(results["ablation"])
    save_results(results)


if __name__ == "__main__":
    main()
