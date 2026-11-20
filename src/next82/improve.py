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
    python -m next82.improve tune         # light tuning, then a LightGBM + linear blend
    python -m next82.improve finalize     # ranges, tiers and SHAP for the chosen model, on validation
    python -m next82.improve in_season    # does the in-season model do better with the blend's forecast?
    python -m next82.improve final        # the one run on the test seasons (refuses to run twice)
    python -m next82.improve tune         # light tuning of the chosen model
"""
import argparse
import json

import numpy as np
import pandas as pd

from next82 import config, evaluate, explain, intervals, models
from next82.features import CANDIDATE_GROUPS, COMEBACK_FEATURES, FEATURES, TARGET, load_table

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


def candidates(df: pd.DataFrame) -> dict:
    """Add candidate groups one at a time; keep each only if it passes the keep rule
    against the features kept so far."""
    kept = list(FEATURES)
    base = fold_maes(df, kept)
    out = {"start": compare(base, base), "rule": {"min_gain": KEEP_MIN_GAIN, "min_folds": KEEP_MIN_FOLDS}, "groups": {}}
    for name, cols in CANDIDATE_GROUPS.items():
        trial = fold_maes(df, kept + cols)
        result = compare(base, trial) | {"kept": False}
        if keeps(result):
            kept, base, result["kept"] = kept + cols, trial, True
        out["groups"][name] = result
        print(f"  + {name:20s} {result['change']:+.3f} games, better in {result['folds_better']}/{len(VALIDATION_SEASONS)} folds "
              f"-> {'KEEP' if result['kept'] else 'drop'}")
    out["kept_features"] = kept
    out["final"] = compare(fold_maes(df, list(FEATURES)), base)
    print(f"  validation miss {out['start']['mean']:.3f} -> {base.mean():.3f}")
    return out


# One setting at a time around the current model (models.lightgbm).
TUNING_GRID = {
    "n_estimators": [150, 600, 1000],
    "learning_rate": [0.01, 0.04],
    "num_leaves": [7, 31],
    "min_child_samples": [40, 160],
    "reg_lambda": [0.0, 5.0],
    "colsample_bytree": [0.5, 1.0],
}
BLEND_WEIGHTS = [0.5, 0.6, 0.7, 0.8, 0.9]


def blend_maes(df: pd.DataFrame, features: list[str], weight: float, params: dict | None = None) -> pd.Series:
    """weight x LightGBM (seed-averaged) + (1 - weight) x linear regression, per fold."""
    out = {}
    for season, train, val in folds(df):
        lgbm = np.mean([np.clip(lightgbm(s, **(params or {})).fit(train[features], train[TARGET]).predict(val[features]), 0, 1)
                        for s in SEEDS], axis=0)
        lin = models.predict(models.fit("Linear regression", train, features), val, features)
        out[season] = evaluate.mae_games(val, weight * lgbm + (1 - weight) * lin)
    return pd.Series(out)


def tune(df: pd.DataFrame, features: list[str]) -> dict:
    """Light tuning on validation: each setting alone, then the settings that passed the
    keep rule together; then a LightGBM + linear blend. Kept only if it passes the rule."""
    base = fold_maes(df, features)
    out = {"current": compare(base, base), "single": {}, "blend": {}}
    winners = {}
    for param, values in TUNING_GRID.items():
        for v in values:
            r = compare(base, fold_maes(df, features, {param: v}))
            out["single"][f"{param}={v}"] = r
            print(f"  {param}={v:<8} {r['change']:+.3f} games, better in {r['folds_better']}/5")
            if keeps(r) and (param not in winners or r["change"] < winners[param][1]):
                winners[param] = (v, r["change"])
    params = {p: v for p, (v, _) in winners.items()}
    best, best_maes = {}, base
    if params:
        combined = fold_maes(df, features, params)
        out["combined"] = compare(base, combined) | {"params": params}
        print(f"  combined {params}: {out['combined']['change']:+.3f}")
        if keeps(out["combined"]):
            best, best_maes = params, combined
    for w in BLEND_WEIGHTS:
        r = compare(best_maes, blend_maes(df, features, w, best))
        out["blend"][str(w)] = r
        print(f"  blend {w:.1f} LightGBM + {1 - w:.1f} linear: {r['change']:+.3f} games, better in {r['folds_better']}/5")
    blend_ok = {w: r for w, r in out["blend"].items() if keeps(r)}
    weight = float(min(blend_ok, key=lambda w: blend_ok[w]["change"])) if blend_ok else 1.0
    final = blend_maes(df, features, weight, best) if weight < 1 else best_maes
    out["chosen"] = {"params": best, "blend_weight": weight, **compare(base, final)}
    print(f"  chosen: params {best or 'unchanged'}, LightGBM weight {weight}: {base.mean():.3f} -> {final.mean():.3f}")
    return out


def fold_ranges(train: pd.DataFrame, val: pd.DataFrame, point: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Likely ranges for a fold, built as in train.preseason_ranges: quantile models, a
    conformal correction measured on the last training season, tidied around `point`."""
    last = train.season_idx.max()
    fit_part, cal = train[train.season_idx < last], train[train.season_idx == last]
    low, high = (m.predict(cal[FEATURES]) for m in models.fit_quantiles(fit_part))
    adjustment = intervals.conformal_adjustment(low, high, cal[TARGET])
    low, high = (np.asarray(m.predict(val[FEATURES])) for m in models.fit_quantiles(train))
    return intervals.tidy(low - adjustment, point, high + adjustment, floor=0, ceiling=1)


def finalize(df: pd.DataFrame) -> dict:
    """Checks before the test seasons, on the validation folds: the blend's average miss,
    80% range coverage, how honest the tiers are, and SHAP (adds up; sensible top factors)."""
    out = {"folds": {}}
    shap_abs = []
    for season, train, val in folds(df):
        new = models.fit("LightGBM + linear blend", train)
        point = models.predict(new, val)
        old = models.predict(models.fit("LightGBM", train), val)
        low, high = fold_ranges(train, val, point)
        games = val.season_games_next.to_numpy()
        actual = val[TARGET].to_numpy() * games
        tiers = intervals.tier_check(low * games, actual, games, {"rotation role": evaluate.has_rotation_role(val).to_numpy()})
        values, base = explain.shap_values(new, val)
        additivity = float(np.abs(values.sum(1) + base - new.predict(val[FEATURES]) * explain.GAMES).max())
        shap_abs.append(pd.DataFrame(np.abs(values), columns=FEATURES).mean())
        out["folds"][season] = {
            "mae_blend": evaluate.mae_games(val, point), "mae_lightgbm": evaluate.mae_games(val, old),
            "coverage": intervals.coverage(low * games, high * games, actual),
            "tiers_rotation": tiers["rotation role"], "shap_max_additivity_error": additivity,
        }
        f = out["folds"][season]
        print(f"  {season}: blend {f['mae_blend']:.2f} vs LightGBM {f['mae_lightgbm']:.2f}; coverage {f['coverage']:.1%}; "
              f"Safe under {config.TIER_SAFE_LOW}: {f['tiers_rotation']['safe_under_cutoff']:.1%}")
    out["coverage_mean"] = float(np.mean([f["coverage"] for f in out["folds"].values()]))
    out["top_factors"] = pd.concat(shap_abs, axis=1).mean(axis=1).sort_values(ascending=False).head(8).round(2).to_dict()
    print(f"  average coverage {out['coverage_mean']:.1%}; top factors (avg |SHAP|, games): {out['top_factors']}")
    return out


IN_SEASON_FOLDS = ["2021-22", "2022-23", "2023-24"]


def in_season_input(df: pd.DataFrame) -> dict:
    """Does the in-season model do better with the blend's preseason forecast as its
    preseason_share input? Rest-of-season miss on folds before its test seasons."""
    from next82 import in_season

    snaps = pd.read_parquet(in_season.SNAPSHOTS_PATH)
    assert not set(IN_SEASON_FOLDS) & set(in_season.TEST_SEASONS)
    params = json.loads(in_season.METRICS_PATH.read_text())["params"]
    table = df.copy()
    shares = in_season.out_of_time_preseason_shares(table, "LightGBM + linear blend")
    # Row for season s-1 holds the forecast for season s.
    nxt = {s: config.SEASONS[i + 1] for i, s in enumerate(config.SEASONS[:-1])}
    blend = pd.Series(shares.to_numpy(), index=pd.MultiIndex.from_arrays([table.SEASON.map(nxt), table.PLAYER_ID]))
    out = {}
    for season in IN_SEASON_FOLDS:
        train, val = snaps[snaps.SEASON < season], snaps[snaps.SEASON == season]
        old = np.abs(in_season.predict_rest(in_season.fit(train, **params), val) - val.games_after).mean()
        swap = lambda d: d.assign(preseason_share=blend.reindex(pd.MultiIndex.from_arrays([d.SEASON, d.PLAYER_ID])).to_numpy())
        btrain, bval = swap(train), swap(val)
        new = np.abs(in_season.predict_rest(in_season.fit(btrain, **params), bval) - bval.games_after).mean()
        out[season] = {"lightgbm_input": float(old), "blend_input": float(new)}
        print(f"  {season}: rest-of-season miss {old:.3f} (LightGBM input) vs {new:.3f} (blend input)")
    change = np.mean([v["blend_input"] - v["lightgbm_input"] for v in out.values()])
    better = sum(v["blend_input"] < v["lightgbm_input"] for v in out.values())
    return {"folds": out, "change": float(change), "folds_better": int(better),
            "use_blend": bool(change < 0 and better >= 2)}


def final(df: pd.DataFrame) -> dict:
    """The one look at the test seasons, after every choice was made on validation."""
    from next82 import in_season

    train, test = evaluate.split(df)
    games = test.season_games_next.to_numpy()
    actual = test[TARGET].to_numpy() * games
    out = {"test_seasons": sorted(test.SEASON.unique()), "season_model": {}}
    for name in ["LightGBM + linear blend", "LightGBM", "Linear regression", "Same as last year", "3-year average"]:
        point = models.predict(models.fit(name, train), test)
        out["season_model"][name] = evaluate.score(test, point)
        if name == "LightGBM + linear blend":
            low, high = fold_ranges(train, test, point)
            out["coverage_new"] = intervals.coverage(low * games, high * games, actual)
    out["coverage_old"] = json.loads((config.MODELS_DIR / "metrics.json").read_text())["ranges"]["all players"]["coverage"]
    r = out["season_model"]
    best_simple = min(("Same as last year", "3-year average"), key=lambda k: r[k]["mae_all"])
    out["best_simple"] = best_simple
    out["adopt"] = r["LightGBM + linear blend"]["mae_all"] < r["LightGBM"]["mae_all"]

    # In-season: the same model with the blend's out-of-time forecast as preseason_share.
    snaps = pd.read_parquet(in_season.SNAPSHOTS_PATH)
    params = json.loads(in_season.METRICS_PATH.read_text())["params"]
    nxt = {s: config.SEASONS[i + 1] for i, s in enumerate(config.SEASONS[:-1])}
    shares = in_season.out_of_time_preseason_shares(df.copy(), "LightGBM + linear blend")
    blend = pd.Series(shares.to_numpy(), index=pd.MultiIndex.from_arrays([df.SEASON.map(nxt), df.PLAYER_ID]))
    swap = lambda d: d.assign(preseason_share=blend.reindex(pd.MultiIndex.from_arrays([d.SEASON, d.PLAYER_ID])).to_numpy())
    s_train, s_test = snaps[snaps.SEASON < in_season.TEST_SEASONS[0]], snaps[snaps.SEASON.isin(in_season.TEST_SEASONS)]
    old = np.abs(in_season.predict_rest(in_season.fit(s_train, **params), s_test) - s_test.games_after).mean()
    bt, bs = swap(s_train), swap(s_test)
    new = np.abs(in_season.predict_rest(in_season.fit(bt, **params), bs) - bs.games_after).mean()
    out["in_season"] = {"test_seasons": in_season.TEST_SEASONS, "old": float(old), "new": float(new),
                        "adopt": bool(out["adopt"] and new < old)}

    print(f"Test seasons {' and '.join(out['test_seasons'])} (feature seasons; forecasting the season after each)")
    print(f"  {'Model':26s} {'avg miss':>9s} {'median':>7s} {'within 16':>10s}")
    for name, v in r.items():
        print(f"  {name:26s} {v['mae_all']:9.2f} {v['median_error_all']:7.1f} {v['share_within_16']:10.0%}")
    print(f"  80% range coverage: new {out['coverage_new']:.1%}, old {out['coverage_old']:.1%}")
    print(f"  in-season rest-of-season miss: {old:.3f} -> {new:.3f}")
    print(f"  adopt the new season model: {out['adopt']}; in-season input: {out['in_season']['adopt']}")
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
    parser.add_argument("step", choices=["ablation", "chart", "candidates", "tune", "finalize", "in_season", "final"])
    args = parser.parse_args()
    df = load_table()
    results = load_results()
    if args.step == "ablation":
        results["ablation"] = ablation(df)
    if args.step == "candidates":
        results["candidates"] = candidates(df)
    if args.step == "final":
        if "final" in results:
            raise SystemExit("The test seasons were already used once; their results are in models/improve.json.")
        results["final"] = final(df)
    if args.step == "in_season":
        results["in_season"] = in_season_input(df)
        print(f"  use the blend's forecast in-season: {results['in_season']['use_blend']}")
    if args.step == "finalize":
        results["finalize"] = finalize(df)
    if args.step == "tune":
        results["tune"] = tune(df, results["candidates"]["kept_features"])
    if args.step in ("ablation", "chart"):
        save_chart(results["ablation"])
    save_results(results)


if __name__ == "__main__":
    main()
