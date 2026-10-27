"""Back-to-backs: how often a player sits the second night, and how many his team has left.

A back-to-back is a team playing on consecutive days. For each one where a player
played the first night, he "rested" if he missed the second night but played his
team's next game after it (a longer absence is more likely an injury, so it's left
out). A player's rest rate comes from his last three seasons, shrunk toward the
league rate because samples are small:
    rate = (rests + M x league rate) / (back-to-backs + M)
M is chosen on a validation season.

The in-season model already reflects league-average resting, so the rest-of-season
adjustment uses only each player's difference from the league rate:
    games adjustment = -(rate - league rate) x team back-to-backs left x predicted share
and it's only used if it improves the updated forecast on validation.

Usage:
    python -m next82.back_to_back     # rates, choice of M, validation of the adjustment
"""
import json

import numpy as np
import pandas as pd

from next82 import config, data, in_season

RATES_PATH = config.PROCESSED_DIR / f"b2b_rates_{config.FORECAST_SEASON}.parquet"
METRICS_PATH = config.MODELS_DIR / "b2b_metrics.json"
HISTORY_SEASONS = 3
SHRINK_GRID = [0, 5, 10, 20, 40, 80, 160, np.inf]
VALIDATION_SEASON = "2023-24"
TEST_SEASONS = ["2024-25", "2025-26"]


def back_to_backs(team_games: pd.DataFrame) -> pd.DataFrame:
    """Every back-to-back: TEAM_ID, SEASON, first and second night, and the team's next game after it."""
    tg = team_games[["SEASON", "TEAM_ID", "GAME_DATE"]].drop_duplicates().sort_values(["SEASON", "TEAM_ID", "GAME_DATE"])
    tg["next"] = tg.groupby(["SEASON", "TEAM_ID"]).GAME_DATE.shift(-1)
    tg["after"] = tg.groupby(["SEASON", "TEAM_ID"]).GAME_DATE.shift(-2)
    pairs = tg[(tg.next - tg.GAME_DATE).dt.days == 1]
    return pairs.rename(columns={"GAME_DATE": "first", "next": "second"})[["SEASON", "TEAM_ID", "first", "second", "after"]]


def rest_outcomes(player_games: pd.DataFrame, team_games: pd.DataFrame) -> pd.DataFrame:
    """One row per (player, back-to-back) where he played the first night: rested = missed
    the second night; rows where he also missed the next game (likely injury) are dropped."""
    pairs = back_to_backs(team_games)
    played = set(zip(player_games.PLAYER_ID, player_games.TEAM_ID, player_games.GAME_DATE))
    first = player_games.merge(pairs, left_on=["SEASON", "TEAM_ID", "GAME_DATE"], right_on=["SEASON", "TEAM_ID", "first"])
    second = np.array([(p, t, d) in played for p, t, d in zip(first.PLAYER_ID, first.TEAM_ID, first.second)])
    after = np.array([pd.notna(d) and (p, t, d) in played for p, t, d in zip(first.PLAYER_ID, first.TEAM_ID, first.after)])
    out = first.assign(rested=~second, next_played=after)
    out = out[second | after]  # missed both: probably an injury, not rest
    return out[["SEASON", "PLAYER_ID", "TEAM_ID", "first", "second", "rested"]].reset_index(drop=True)


def shrunk_rates(outcomes: pd.DataFrame, m: float, league_rate: float) -> pd.DataFrame:
    """Per player: back-to-backs, rests, and the shrunk rest rate."""
    g = outcomes.groupby("PLAYER_ID").rested.agg(pairs="size", rests="sum")
    g["rate"] = league_rate if np.isinf(m) else (g.rests + m * league_rate) / (g.pairs + m)
    return g


def remaining_back_to_backs(schedule: pd.DataFrame, today: pd.Timestamp) -> pd.Series:
    """Second nights of back-to-backs from `today` on, by TEAM_ID."""
    pairs = back_to_backs(schedule.assign(SEASON="current"))
    return pairs[pairs.second >= today].groupby("TEAM_ID").size()


def adjustment(rate, league_rate: float, b2b_left, share):
    """Games added (negative = fewer) for resting more or less than the league rate."""
    return -(np.asarray(rate, float) - league_rate) * np.asarray(b2b_left, float) * np.asarray(share, float)


# ---------------------------------------------------------------- validation

def _brier(outcomes: pd.DataFrame, rates: pd.Series, league: float) -> float:
    p = outcomes.PLAYER_ID.map(rates).fillna(league)
    return float(((p - outcomes.rested) ** 2).mean())


def choose_m(outcomes: pd.DataFrame) -> tuple[float, dict]:
    """M minimizing the Brier score of predicting VALIDATION_SEASON's rests from the 3 seasons before."""
    i = config.SEASONS.index(VALIDATION_SEASON)
    hist = outcomes[outcomes.SEASON.isin(config.SEASONS[i - HISTORY_SEASONS:i])]
    target = outcomes[outcomes.SEASON == VALIDATION_SEASON]
    league = float(hist.rested.mean())
    scores = {("league only" if np.isinf(m) else f"M={m}"): _brier(target, shrunk_rates(hist, m, league).rate, league)
              for m in SHRINK_GRID}
    best = min(scores, key=scores.get)
    return (np.inf if best == "league only" else float(best.split("=")[1])), scores


def snapshot_b2b_left(snaps: pd.DataFrame, player_games: pd.DataFrame, team_games: pd.DataFrame) -> pd.Series:
    """For in-season snapshots: back-to-back second nights left for the player's latest team."""
    out = pd.Series(0.0, index=snaps.index)
    pairs = back_to_backs(team_games)
    for (season, date), rows in snaps.groupby(["SEASON", "date"]).groups.items():
        pg = player_games[(player_games.SEASON == season) & (player_games.GAME_DATE < date)]
        team = pg.sort_values("GAME_DATE").groupby("PLAYER_ID").TEAM_ID.last()
        left = pairs[(pairs.SEASON == season) & (pairs.second >= date)].groupby("TEAM_ID").size()
        out.loc[rows] = snaps.loc[rows, "PLAYER_ID"].map(team).map(left).fillna(0).to_numpy()
    return out


def evaluate_adjustment(snaps: pd.DataFrame, outcomes: pd.DataFrame, m: float, params: dict,
                        player_games: pd.DataFrame, team_games: pd.DataFrame, seasons: list[str], train_before: str) -> dict:
    """Rest-of-season MAE of the in-season model with and without the back-to-back adjustment."""
    test = snaps[snaps.SEASON.isin(seasons)].copy()
    model = in_season.fit(snaps[snaps.SEASON < train_before], **params)
    base = in_season.predict_rest(model, test)
    adjusted = np.zeros(len(test))
    for season in seasons:
        i = config.SEASONS.index(season)
        hist = outcomes[outcomes.SEASON.isin(config.SEASONS[i - HISTORY_SEASONS:i])]
        league = float(hist.rested.mean())
        rates = shrunk_rates(hist, m, league).rate
        mask = (test.SEASON == season).to_numpy()
        part = test[mask]
        share = base[mask] / part.team_games_left.to_numpy()
        b2b = snapshot_b2b_left(part, player_games, team_games).to_numpy()
        rate = part.PLAYER_ID.map(rates).fillna(league).to_numpy()
        adjusted[mask] = np.clip(base[mask] + adjustment(rate, league, b2b, share), 0, part.team_games_left)
    third = in_season.season_third(test.season_progress)
    groups = {"all": np.ones(len(test), bool), **{n: third == t for t, n in enumerate(in_season.THIRDS)}}
    err = lambda p: np.abs(p - test.games_after.to_numpy())
    return {g: {"n": int(mk.sum()), "model": float(err(base)[mk].mean()), "with back-to-backs": float(err(adjusted)[mk].mean())}
            for g, mk in groups.items()}


def main():
    player_games = data.load("player_games")[["SEASON", "PLAYER_ID", "TEAM_ID", "GAME_DATE"]]
    team_games = data.load("team_games")[["SEASON", "TEAM_ID", "GAME_DATE"]]
    player_games["GAME_DATE"] = in_season.to_date(player_games.GAME_DATE)
    team_games["GAME_DATE"] = in_season.to_date(team_games.GAME_DATE)
    outcomes = rest_outcomes(player_games, team_games)
    print(f"Back-to-back second nights with the player available: {len(outcomes):,}; "
          f"rested {outcomes.rested.mean():.1%} overall")

    m, scores = choose_m(outcomes)
    print(f"\nPredicting {VALIDATION_SEASON} rests (Brier score, lower is better): "
          + ", ".join(f"{k} {v:.4f}" for k, v in scores.items()))
    test_scores = {}
    for s in TEST_SEASONS:
        i = config.SEASONS.index(s)
        hist = outcomes[outcomes.SEASON.isin(config.SEASONS[i - HISTORY_SEASONS:i])]
        league = float(hist.rested.mean())
        target = outcomes[outcomes.SEASON == s]
        test_scores[s] = {name: _brier(target, shrunk_rates(hist, mm, league).rate, league)
                          for name, mm in [("league only", np.inf), (f"M={m:g}", m), ("raw rate (M=0)", 0)]}
    print("Test: " + "; ".join(f"{s}: " + ", ".join(f"{k} {v:.4f}" for k, v in r.items()) for s, r in test_scores.items()))

    snaps = pd.read_parquet(in_season.SNAPSHOTS_PATH)
    params = json.loads(in_season.METRICS_PATH.read_text())["params"]
    val = evaluate_adjustment(snaps, outcomes, m, params, player_games, team_games, [VALIDATION_SEASON], VALIDATION_SEASON)
    test = evaluate_adjustment(snaps, outcomes, m, params, player_games, team_games, TEST_SEASONS, TEST_SEASONS[0])
    use = val["all"]["with back-to-backs"] < val["all"]["model"]
    print("\nRest-of-season games, average miss (model / with back-to-back adjustment):")
    for name, table in [(f"validation {VALIDATION_SEASON}", val), ("test " + " and ".join(TEST_SEASONS), test)]:
        print(f"  {name}: " + "; ".join(f"{g} {r['model']:.3f} / {r['with back-to-backs']:.3f}" for g, r in table.items()))
    print(f"\nUse the adjustment in the updated forecast: {use}")

    current = outcomes[outcomes.SEASON.isin(config.SEASONS[-HISTORY_SEASONS:])]
    league = float(current.rested.mean())
    shrunk_rates(current, m, league).reset_index().to_parquet(RATES_PATH, index=False)
    METRICS_PATH.write_text(json.dumps({
        "shrink_m": None if np.isinf(m) else m, "league_rate": league, "use_in_forecast": bool(use),
        "validation_brier": scores, "test_brier": test_scores, "validation_mae": val, "test_mae": test,
    }, indent=2))
    print(f"Saved {RATES_PATH.relative_to(config.ROOT)} (league rate {league:.1%})")


if __name__ == "__main__":
    main()
