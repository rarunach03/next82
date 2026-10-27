"""Rookies in the fantasy rankings.

Rookies have no NBA history, so they have no preseason forecast and no prior. Once a
rookie has played MIN_GAMES games this season, they're ranked with:
  per game   this season's stats shrunk toward a rookie baseline for their draft
             range (from past rookies' first seasons), the same way veterans are
             shrunk toward their own last three seasons:
                 (season totals + K x baseline per game) / (games + K)
  games      a rest-of-season games forecast; the method (the in-season model, a
             pace/draft-range blend, or pace alone) is chosen on a validation season

Usage:
    python -m next82.rookies     # build the baseline, choose K and the games method
"""
import json

import numpy as np
import pandas as pd

from next82 import config, data, fantasy, in_season
from next82.features import FEATURES

BASELINE_PATH = config.PROCESSED_DIR / f"rookie_baseline_{config.FORECAST_SEASON}.parquet"
METRICS_PATH = config.MODELS_DIR / "rookie_metrics.json"

MIN_GAMES = 5
# The in-season model without injury features: with them, rookie validation got worse (5.79 -> 6.17 games).
FEATURES_USED = in_season.BASE_FEATURES
DRAFT_RANGES = [(1, 5, "picks 1-5"), (6, 14, "picks 6-14"), (15, 30, "picks 15-30"), (31, 60, "picks 31-60")]
UNDRAFTED = "undrafted"
VALIDATION_SEASON = "2023-24"
TEST_SEASONS = ["2024-25", "2025-26"]
GAMES_METHODS = ["in-season model", "pace and draft-range blend", "current pace"]


def draft_range(pick) -> str:
    """Draft range label for an overall pick (missing = undrafted)."""
    if pick is None or pd.isna(pick):
        return UNDRAFTED
    for low, high, name in DRAFT_RANGES:
        if low <= pick <= high:
            return name
    return UNDRAFTED


def past_rookies() -> pd.DataFrame:
    """Every past rookie season: first season in the data, drafted that year or undrafted.

    The first season in the data (1996-97) is skipped: players there aren't
    necessarily rookies.
    """
    stats = data.load("player_stats")
    bio = data.load("player_bio")[["SEASON", "PLAYER_ID", "DRAFT_YEAR", "DRAFT_NUMBER"]]
    first = stats.sort_values("SEASON").groupby("PLAYER_ID").SEASON.first()
    rookies = stats[stats.SEASON == stats.PLAYER_ID.map(first)].merge(bio, on=["SEASON", "PLAYER_ID"])
    rookies = rookies[rookies.SEASON > config.SEASONS[0]]
    draft_year = pd.to_numeric(rookies.DRAFT_YEAR, errors="coerce")
    rookies = rookies[(draft_year == rookies.SEASON.str[:4].astype(int)) | draft_year.isna()].copy()
    rookies["draft_range"] = pd.to_numeric(rookies.DRAFT_NUMBER, errors="coerce").map(draft_range)
    season_games = data.load("team_games").groupby(["SEASON", "TEAM_ID"]).size().groupby("SEASON").max()
    rookies["gp_share"] = rookies.GP / rookies.SEASON.map(season_games)
    return rookies


def baseline(rookies: pd.DataFrame) -> pd.DataFrame:
    """Per-game stats (weighted by games) and average share of games played, by draft range."""
    totals = rookies.groupby("draft_range")[[*fantasy.STATS, "GP"]].sum()
    out = totals[fantasy.STATS].div(totals.GP, axis=0)
    out["gp_share"] = rookies.groupby("draft_range").gp_share.mean()
    out["n"] = rookies.groupby("draft_range").size()
    return out


def is_rookie(rosters: pd.DataFrame, forecast_ids, draft: pd.DataFrame | None) -> pd.Series:
    """Rostered players in their first NBA season: no preseason forecast, and either
    drafted this year or first listed this season."""
    first_season = int(config.FORECAST_SEASON[:4])
    drafted = rosters.PLAYER_ID.isin(draft.PLAYER_ID) if draft is not None else False
    new = rosters.FROM_YEAR >= first_season if "FROM_YEAR" in rosters else False
    return ~rosters.PLAYER_ID.isin(forecast_ids) & (drafted | new)


def current_rookies(rosters: pd.DataFrame, forecast_ids, models_dir=config.MODELS_DIR) -> pd.DataFrame:
    """This season's rookies with MIN_GAMES+ games: shrunk per-game stats and a
    rest-of-season games forecast. Empty if the baseline or logs aren't available."""
    logs = data.saved_season_logs()
    if not BASELINE_PATH.exists() or not METRICS_PATH.exists() or logs is None or logs[0].empty:
        return pd.DataFrame()
    import lightgbm as lgb

    settings = json.loads(METRICS_PATH.read_text())
    base = pd.read_parquet(BASELINE_PATH).set_index("draft_range")
    draft = data.saved_draft()
    player_games, team_games = logs
    player_games = player_games.assign(GAME_DATE=in_season.to_date(player_games.GAME_DATE))
    team_games = team_games.assign(GAME_DATE=in_season.to_date(team_games.GAME_DATE))

    rookies = rosters[is_rookie(rosters, forecast_ids, draft)].copy()
    games = player_games.groupby("PLAYER_ID").size()
    rookies["played"] = rookies.PLAYER_ID.map(games).fillna(0)
    rookies = rookies[rookies.played >= MIN_GAMES]
    if rookies.empty:
        return pd.DataFrame()
    picks = draft.set_index("PLAYER_ID").OVERALL_PICK if draft is not None else pd.Series(dtype=float)
    rookies["draft_range"] = rookies.PLAYER_ID.map(picks).map(draft_range)

    # Per game: shrink toward the draft range's baseline.
    totals = player_games[player_games.PLAYER_ID.isin(rookies.PLAYER_ID)].groupby("PLAYER_ID")[fantasy.STATS].sum()
    prior = base.loc[rookies.draft_range, fantasy.STATS].set_axis(rookies.PLAYER_ID)
    per_game = fantasy.shrink(totals, games, prior, settings["shrink_k"])

    # Games: the chosen method on today's snapshot (no preseason history for rookies).
    players = pd.DataFrame({"PLAYER_ID": rookies.PLAYER_ID.to_numpy(),
                            "preseason_share": rookies.draft_range.map(base.gp_share).to_numpy()})
    for f in FEATURES:
        players[f] = np.nan
    totals_by_team = pd.Series(config.REGULAR_SEASON_GAMES, index=pd.Index(rosters.TEAM_ID.unique()))
    date = team_games.GAME_DATE.max() + pd.Timedelta(days=1)
    snap = in_season.snapshot_features(player_games, team_games, totals_by_team, players, date,
                                       known_teams=rosters.set_index("PLAYER_ID").TEAM_ID)
    method = settings["games_method"]
    if method == "in-season model":
        model = lgb.Booster(model_file=str(models_dir / in_season.NO_INJURY_MODEL_PATH.name))
        rest = in_season.predict_rest(model, snap, FEATURES_USED)
    else:
        rest = games_predictions(snap, None, json.loads(in_season.METRICS_PATH.read_text())["blend_k"])[method]
    snap = snap.set_index("PLAYER_ID").assign(predicted_rest=rest)
    out = rookies.set_index("PLAYER_ID")[["PLAYER_NAME", "TEAM_ABBREVIATION", "draft_range"]].join(per_game)
    out["played_so_far"] = snap.played_so_far
    out["team_games_left"] = snap.team_games_left
    out["predicted_rest"] = snap.predicted_rest
    out["updated_total"] = out.played_so_far + out.predicted_rest
    return out


# ---------------------------------------------------------------- validation

def rookie_snapshots(season: str, rookies: pd.DataFrame, base: pd.DataFrame, player_games: pd.DataFrame,
                     team_games: pd.DataFrame) -> pd.DataFrame:
    """In-season snapshots of one season's rookies, with in-season features (no
    preseason history: preseason features missing, preseason share = draft-range
    average) and ESPN points before and after each date."""
    r = rookies[rookies.SEASON == season]
    players = pd.DataFrame({"PLAYER_ID": r.PLAYER_ID.to_numpy(),
                            "preseason_share": r.draft_range.map(base.gp_share).to_numpy()})
    for f in FEATURES:
        players[f] = np.nan
    pg = player_games[(player_games.SEASON == season) & player_games.PLAYER_ID.isin(players.PLAYER_ID)].copy()
    pg["FP"] = fantasy.fantasy_points(pg, "espn")
    tg = team_games[team_games.SEASON == season]
    totals = tg.groupby("TEAM_ID").size()
    parts = []
    for date in in_season.snapshot_dates(tg)[1:]:
        snap = in_season.snapshot_features(pg, tg, totals, players, date)
        before, after = pg[pg.GAME_DATE < date], pg[pg.GAME_DATE >= date]
        snap["fp_before"] = snap.PLAYER_ID.map(before.groupby("PLAYER_ID").FP.sum()).fillna(0)
        snap["games_after"] = snap.PLAYER_ID.map(after.groupby("PLAYER_ID").size()).fillna(0)
        snap["fp_after"] = snap.PLAYER_ID.map(after.groupby("PLAYER_ID").FP.sum()).fillna(0)
        snap["draft_range"] = snap.PLAYER_ID.map(r.set_index("PLAYER_ID").draft_range)
        parts.append(snap[(snap.played_so_far >= MIN_GAMES) & (snap.team_games_left > 0)].assign(SEASON=season, date=date))
    return pd.concat(parts, ignore_index=True)


def per_game_errors(snaps: pd.DataFrame, base: pd.DataFrame) -> dict:
    """MAE in rest-of-season ESPN points per game for each K (rookies with 10+ games left)."""
    s = snaps[snaps.games_after >= 10]
    base_fp = fantasy.fantasy_points(base, "espn")
    prior = s.draft_range.map(base_fp)
    actual = s.fp_after / s.games_after
    out = {}
    for k in fantasy.SHRINK_GRID:
        pred = prior if np.isinf(k) else (s.fp_before + k * prior) / (s.played_so_far + k)
        out["baseline only" if np.isinf(k) else f"K={k}"] = float((pred - actual).abs().mean())
    return out


def games_predictions(snaps: pd.DataFrame, model, blend_k: float) -> dict[str, np.ndarray]:
    """Predicted rest-of-season games by each candidate method (model may be None)."""
    preds = {
        "pace and draft-range blend": in_season.baseline_blend(snaps, blend_k),
        "current pace": in_season.baseline_pace(snaps),
    }
    if model is not None:
        preds = {"in-season model": in_season.predict_rest(model, snaps, FEATURES_USED)} | preds
    return preds


def games_errors(snaps: pd.DataFrame, model, blend_k: float) -> dict:
    preds = games_predictions(snaps, model, blend_k)
    return {name: float(np.abs(p - snaps.games_after).mean()) for name, p in preds.items()}


def main():
    rookies = past_rookies()
    player_games = data.load("player_games")[["SEASON", "PLAYER_ID", "TEAM_ID", "GAME_DATE", *fantasy.STATS[1:]]]
    team_games = data.load("team_games")[["SEASON", "TEAM_ID", "GAME_DATE"]]
    player_games["GAME_DATE"] = in_season.to_date(player_games.GAME_DATE)
    team_games["GAME_DATE"] = in_season.to_date(team_games.GAME_DATE)
    in_season_metrics = json.loads(in_season.METRICS_PATH.read_text())
    params, blend_k = in_season_metrics["params"], in_season_metrics["blend_k"]
    snapshots = pd.read_parquet(in_season.SNAPSHOTS_PATH)

    def evaluate_on(seasons, before):
        """Baseline from rookies before `before`; in-season model trained on seasons before it."""
        base = baseline(rookies[rookies.SEASON < before])
        snaps = pd.concat([rookie_snapshots(s, rookies, base, player_games, team_games) for s in seasons])
        model = in_season.fit(snapshots[snapshots.SEASON < before], FEATURES_USED, **params)
        return snaps, base, model

    val_snaps, val_base, val_model = evaluate_on([VALIDATION_SEASON], VALIDATION_SEASON)
    val_k = per_game_errors(val_snaps, val_base)
    best_k = min(val_k, key=val_k.get)
    val_games = games_errors(val_snaps, val_model, blend_k)
    best_games = min(val_games, key=val_games.get)

    test_snaps, test_base, test_model = evaluate_on(TEST_SEASONS, TEST_SEASONS[0])
    test_k = per_game_errors(test_snaps, test_base)
    test_games = games_errors(test_snaps, test_model, blend_k)

    print(f"Rookie snapshots with {MIN_GAMES}+ games: validation {len(val_snaps)}, test {len(test_snaps)}")
    print(f"\nRest-of-season ESPN points per game, average miss (validation {VALIDATION_SEASON} / test):")
    for k in val_k:
        print(f"  {k:14s} {val_k[k]:5.2f} / {test_k[k]:5.2f}{'   <- chosen' if k == best_k else ''}")
    print("\nRest-of-season games, average miss (validation / test):")
    for m in val_games:
        print(f"  {m:28s} {val_games[m]:5.2f} / {test_games[m]:5.2f}{'   <- chosen' if m == best_games else ''}")

    base = baseline(rookies)
    base.reset_index().to_parquet(BASELINE_PATH, index=False)
    METRICS_PATH.write_text(json.dumps({
        "min_games": MIN_GAMES,
        "shrink_k": float("inf") if best_k == "baseline only" else float(best_k.split("=")[1]),
        "games_method": best_games,
        "validation_season": VALIDATION_SEASON, "test_seasons": TEST_SEASONS,
        "per_game": {"validation": val_k, "test": test_k},
        "games": {"validation": val_games, "test": test_games},
        "baseline_n": base.n.to_dict(),
    }, indent=2))
    print(f"\nSaved {BASELINE_PATH.relative_to(config.ROOT)}: " + ", ".join(f"{i} {int(r.n)}" for i, r in base.iterrows()))


if __name__ == "__main__":
    main()
