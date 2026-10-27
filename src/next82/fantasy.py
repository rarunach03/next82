"""Fantasy value: per-game production x forecast games.

Per-game production blends two sources:
  prior     each player's last three seasons, weighted 3:2:1 toward the latest and by
            games played (built once from preseason data: fantasy_prior_<season>.parquet)
  current   this season's games so far
This season's stats are shrunk toward the prior based on games played:
    per game = (this season's totals + K x prior per game) / (games played + K)
so a 4-game hot start barely moves the numbers. K is chosen on a validation season
by how well early-season stats predict rest-of-season fantasy points per game.

Scoring formats: ESPN and Yahoo default points, and 9-category z-scores against the
top POOL_SIZE players (12 teams x 13 roster spots).

Usage:
    python -m next82.fantasy     # build the prior, choose K, report validation and test
"""
import json

import numpy as np
import pandas as pd

from next82 import config, data
from next82.in_season import SNAPSHOT_DAYS, to_date

PRIOR_PATH = config.PROCESSED_DIR / f"fantasy_prior_{config.FORECAST_SEASON}.parquet"
METRICS_PATH = config.MODELS_DIR / "fantasy_metrics.json"

STATS = ["MIN", "PTS", "FG3M", "FGM", "FGA", "FTM", "FTA", "REB", "AST", "STL", "BLK", "TOV"]
PRIOR_WEIGHTS = (3, 2, 1)  # latest season first
POOL_SIZE = 156
SHRINK_GRID = [0, 3, 6, 10, 15, 20, 30, 50, 100, np.inf]
VALIDATION_SEASON = "2023-24"
TEST_SEASONS = ["2024-25", "2025-26"]
MIN_GAMES_AFTER = 10

POINTS = {
    "espn": {"PTS": 1, "FG3M": 1, "FGM": 2, "FGA": -1, "FTM": 1, "FTA": -1, "REB": 1, "AST": 2, "STL": 4, "BLK": 4, "TOV": -2},
    "yahoo": {"PTS": 1, "REB": 1.2, "AST": 1.5, "STL": 3, "BLK": 3, "TOV": -1},
}
CATEGORIES = ["FG%", "FT%", "FG3M", "PTS", "REB", "AST", "STL", "BLK", "TOV"]


def fantasy_points(stats: pd.DataFrame, fmt: str) -> pd.Series:
    """Fantasy points for rows of (per-game or total) box score stats."""
    return sum(stats[s] * w for s, w in POINTS[fmt].items())


def prior_per_game(season_totals: pd.DataFrame, seasons: list[str]) -> pd.DataFrame:
    """Weighted per-game stats over `seasons` (latest first), weighted by recency and games.

    season_totals: SEASON, PLAYER_ID, GP and STATS columns (season totals).
    Returns per-game STATS plus prior_games (games in those seasons) by PLAYER_ID.
    """
    weights = dict(zip(seasons, PRIOR_WEIGHTS))
    t = season_totals[season_totals.SEASON.isin(seasons) & (season_totals.GP > 0)].copy()
    t["w"] = t.SEASON.map(weights)
    weighted = t[STATS].mul(t.w, axis=0).assign(PLAYER_ID=t.PLAYER_ID, wgp=t.GP * t.w, gp=t.GP)
    g = weighted.groupby("PLAYER_ID").sum()
    out = g[STATS].div(g.wgp, axis=0)
    out["prior_games"] = g.gp
    return out


def shrink(current_totals: pd.DataFrame, games: pd.Series, prior: pd.DataFrame, k: float) -> pd.DataFrame:
    """Per-game stats blending this season's totals with the prior (see module docstring).
    Players without a prior use their current per-game stats as they are."""
    cur = current_totals.reindex(prior.index.union(current_totals.index)).fillna(0)
    g = games.reindex(cur.index).fillna(0)
    p = prior.reindex(cur.index)[STATS]
    if np.isinf(k):
        blended = p.copy()
    else:
        blended = (cur[STATS] + k * p.fillna(0)).div(g + k, axis=0)
    no_prior = p.isna().all(axis=1)
    blended.loc[no_prior] = cur.loc[no_prior, STATS].div(g[no_prior].replace(0, np.nan), axis=0)
    return blended


def nine_cat(per_game: pd.DataFrame, pool_size: int = POOL_SIZE, iterations: int = 3) -> pd.DataFrame:
    """9-category z-scores per game against the top `pool_size` players.

    FG% and FT% use attempt-weighted impact ((player % - pool %) x attempts), so a
    high percentage on few attempts counts for less. The pool is re-chosen a few
    times as the top players by total z.
    """
    pg = per_game.dropna(subset=["PTS"])
    pool = pg.index
    for _ in range(iterations):
        base = pg.loc[pool]
        fg_pct = base.FGM.sum() / base.FGA.sum()
        ft_pct = base.FTM.sum() / base.FTA.sum()
        raw = pd.DataFrame({
            "FG%": pg.FGM - fg_pct * pg.FGA,
            "FT%": pg.FTM - ft_pct * pg.FTA,
            **{c: pg[c] for c in ["FG3M", "PTS", "REB", "AST", "STL", "BLK"]},
            "TOV": -pg.TOV,
        })
        ref = raw.loc[pool]
        z = (raw - ref.mean()) / ref.std()
        z["total"] = z[CATEGORIES].sum(axis=1)
        pool = z.total.nlargest(pool_size).index
    return z


def current_per_game() -> pd.DataFrame | None:
    """Today's per-game stats: this season's games shrunk toward the prior. None if
    the prior hasn't been built."""
    if not PRIOR_PATH.exists() or not METRICS_PATH.exists():
        return None
    prior = pd.read_parquet(PRIOR_PATH).set_index("PLAYER_ID")
    k = json.loads(METRICS_PATH.read_text())["shrink_k"]
    logs = data.saved_season_logs()
    if logs is None or logs[0].empty:
        totals, games = pd.DataFrame(columns=STATS), pd.Series(dtype=float)
    else:
        player_games = logs[0]
        totals = player_games.groupby("PLAYER_ID")[STATS].sum()
        games = player_games.groupby("PLAYER_ID").size()
    per_game = shrink(totals, games, prior, k)
    per_game["games_this_season"] = games.reindex(per_game.index).fillna(0)
    return per_game


def player_values(players: pd.DataFrame) -> pd.DataFrame:
    """Per-game value in each format for `players` (PLAYER_ID index or column).

    Returns per-game stats, ESPN and Yahoo points per game, and 9-category z-scores
    per game (one column per category plus the total), for players with stats.
    """
    per_game = current_per_game()
    if per_game is None:
        return pd.DataFrame()
    ids = players.PLAYER_ID if "PLAYER_ID" in players else players.index
    pg = per_game.reindex(pd.Index(ids)).dropna(subset=["PTS"])
    z = nine_cat(pg)
    return pg.assign(espn=fantasy_points(pg, "espn"), yahoo=fantasy_points(pg, "yahoo")).join(
        z.add_prefix("z_")
    )


# ---------------------------------------------------------------- choosing K

def _snapshot_rows(season: str, player_games: pd.DataFrame, prior: pd.DataFrame) -> pd.DataFrame:
    """Per player at each 14-day snapshot: totals before, and ESPN points per game after."""
    pg = player_games[player_games.SEASON == season]
    pg = pg[pg.PLAYER_ID.isin(prior.index)]
    pg = pg.assign(FP=fantasy_points(pg, "espn"))
    rows = []
    for date in pd.date_range(pg.GAME_DATE.min(), pg.GAME_DATE.max(), freq=f"{SNAPSHOT_DAYS}D")[1:]:
        before, after = pg[pg.GAME_DATE < date], pg[pg.GAME_DATE >= date]
        b = before.groupby("PLAYER_ID").agg(games=("FP", "size"), fp_before=("FP", "sum"))
        a = after.groupby("PLAYER_ID").agg(games_after=("FP", "size"), fp_after=("FP", "sum"))
        snap = b.join(a, how="inner")
        snap = snap[snap.games_after >= MIN_GAMES_AFTER]
        snap["actual_pg"] = snap.fp_after / snap.games_after
        snap["prior_pg"] = fantasy_points(prior.loc[snap.index], "espn")
        rows.append(snap.assign(SEASON=season, date=date))
    return pd.concat(rows)


def shrinkage_errors(snaps: pd.DataFrame) -> dict:
    """MAE in ESPN points per game for each K, overall and by games played so far."""
    buckets = {"all": snaps.games > 0, "1-5 games": snaps.games <= 5,
               "6-15 games": snaps.games.between(6, 15), "16+ games": snaps.games >= 16}
    out = {}
    for k in SHRINK_GRID:
        pred = snaps.prior_pg if np.isinf(k) else (snaps.fp_before + k * snaps.prior_pg) / (snaps.games + k)
        err = (pred - snaps.actual_pg).abs()
        out["prior only" if np.isinf(k) else f"K={k}"] = {b: float(err[m].mean()) for b, m in buckets.items()}
    return out


def main():
    totals = data.load("player_stats")
    seasons = config.SEASONS
    player_games = data.load("player_games")[["SEASON", "PLAYER_ID", "GAME_DATE", *STATS[1:]]]
    player_games["GAME_DATE"] = to_date(player_games.GAME_DATE)

    def prior_for(season):
        i = seasons.index(season)
        return prior_per_game(totals, [seasons[i - 1], seasons[i - 2], seasons[i - 3]])

    val = _snapshot_rows(VALIDATION_SEASON, player_games, prior_for(VALIDATION_SEASON))
    val_errors = shrinkage_errors(val)
    best = min(val_errors, key=lambda k: val_errors[k]["all"])
    test = pd.concat([_snapshot_rows(s, player_games, prior_for(s)) for s in TEST_SEASONS])
    test_errors = shrinkage_errors(test)

    print(f"Rest-of-season ESPN points per game, average miss (validation {VALIDATION_SEASON})")
    for k, row in val_errors.items():
        print(f"  {k:12s} " + "  ".join(f"{b} {v:5.2f}" for b, v in row.items()))
    print(f"\nChosen: {best}. Test seasons {' and '.join(TEST_SEASONS)}:")
    for k in ["K=0", best, "prior only"]:
        print(f"  {k:12s} " + "  ".join(f"{b} {v:5.2f}" for b, v in test_errors[k].items()))

    # The prior for the season in progress, from the three seasons before it.
    prior = prior_per_game(totals, list(reversed(seasons[-3:])))
    prior.reset_index().to_parquet(PRIOR_PATH, index=False)
    k = float("inf") if best == "prior only" else float(best.split("=")[1])
    METRICS_PATH.write_text(json.dumps({
        "shrink_k": k, "validation_season": VALIDATION_SEASON, "test_seasons": TEST_SEASONS,
        "validation": val_errors, "test": test_errors,
    }, indent=2))
    print(f"\nSaved {PRIOR_PATH.relative_to(config.ROOT)} ({len(prior)} players) and K={k:g}")


if __name__ == "__main__":
    main()
