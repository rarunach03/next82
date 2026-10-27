"""Grading the frozen preseason forecast against the season in progress.

Until the season ends, each player is graded on games played so far against what
their forecast implied for that many team games: a 60-game forecast "expects"
60/82 of every team game. The same pro-rating applies to two simple baselines:
games played last season, and the 3-season average.

Comeback players are graded on their expected games (setback risk included), not
the if-healthy number. Players not on a current roster are left out, since every
forecast assumes the player is in the league.

The trend is recalculated from this season's game logs for every game date, so it
needs no stored history.
"""
import numpy as np
import pandas as pd

from next82 import config, evaluate
from next82.in_season import to_date

METHODS = {
    "model": ("Next82 preseason forecast", "pred_share"),
    "last_season": ("Same as last season", "gp_share"),
    "three_year": ("3-season average", "avg_gp_share_3yr"),
}
BOOTSTRAP_SAMPLES = 2000


def graded_players(forecasts: pd.DataFrame, rosters: pd.DataFrame) -> pd.DataFrame:
    """Forecast rows for players on a current roster, with their team ID."""
    teams = rosters.set_index("PLAYER_ID").TEAM_ID
    out = forecasts[forecasts.PLAYER_ID.isin(teams.index)].copy()
    out["team_id"] = out.PLAYER_ID.map(teams)
    return out


def errors_as_of(players: pd.DataFrame, player_games: pd.DataFrame, team_games: pd.DataFrame,
                 date: pd.Timestamp) -> pd.DataFrame:
    """Per player: games played before `date`, team games before `date`, and the
    absolute miss of each method's pro-rated forecast."""
    pg = player_games[player_games.GAME_DATE < date]
    tg = team_games[team_games.GAME_DATE < date]
    out = players[["PLAYER_ID", "team_id", "missed_season", *[c for _, c in METHODS.values()]]].copy()
    out["played"] = out.PLAYER_ID.map(pg.groupby("PLAYER_ID").size()).fillna(0)
    out["team_games"] = out.team_id.map(tg.groupby("TEAM_ID").size()).fillna(0)
    for key, (_, col) in METHODS.items():
        expected = out[col].fillna(0).clip(0, 1) * out.team_games
        out[f"err_{key}"] = (expected - out.played).abs()
    return out


def summarize(errors: pd.DataFrame, rotation: pd.Series) -> dict:
    """Average miss by method, overall and by group."""
    groups = {
        "all": np.ones(len(errors), bool),
        "rotation players": rotation.reindex(errors.index).fillna(False).to_numpy(),
        "comeback players": (errors.missed_season == 1).to_numpy(),
        "everyone else": (errors.missed_season == 0).to_numpy(),
    }
    return {
        name: {"n": int(m.sum()), **{k: float(errors.loc[m, f"err_{k}"].mean()) for k in METHODS}}
        for name, m in groups.items() if m.any()
    }


def gap_range(errors: pd.DataFrame, baseline: str, seed: int = 0) -> tuple[float, float]:
    """95% range for (baseline miss - model miss), resampling players. If it spans 0,
    the difference so far could easily be luck."""
    gain = (errors[f"err_{baseline}"] - errors.err_model).to_numpy()
    rng = np.random.default_rng(seed)
    means = rng.choice(gain, size=(BOOTSTRAP_SAMPLES, len(gain))).mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def season_accuracy(forecasts: pd.DataFrame, rosters: pd.DataFrame, player_games: pd.DataFrame,
                    team_games: pd.DataFrame) -> dict | None:
    """Accuracy so far, the trend by game date, and how many players were left out."""
    if team_games.empty:
        return None
    player_games = player_games.assign(GAME_DATE=to_date(player_games.GAME_DATE))
    team_games = team_games.assign(GAME_DATE=to_date(team_games.GAME_DATE))
    players = graded_players(forecasts, rosters).set_index("PLAYER_ID", drop=False)
    rotation = evaluate.has_rotation_role(players)

    dates = sorted(team_games.GAME_DATE.unique())
    trend = []
    for day in dates:
        e = errors_as_of(players, player_games, team_games, day + pd.Timedelta(days=1))
        trend.append({
            "date": str(pd.Timestamp(day).date()),
            "avgTeamGames": round(float(e.team_games.mean()), 1),
            **{k: round(float(e[f"err_{k}"].mean()), 2) for k in METHODS},
        })

    latest = errors_as_of(players, player_games, team_games, dates[-1] + pd.Timedelta(days=1))
    groups = summarize(latest, rotation)
    baselines = [k for k in METHODS if k != "model"]
    best = min(baselines, key=lambda k: groups["all"][k])
    low, high = gap_range(latest, best)
    return {
        "asOf": str(pd.Timestamp(dates[-1]).date()),
        "avgTeamGames": round(float(latest.team_games.mean()), 1),
        "methods": {k: label for k, (label, _) in METHODS.items()},
        "groups": {g: {k: (round(v, 2) if isinstance(v, float) else v) for k, v in row.items()} for g, row in groups.items()},
        "bestBaseline": best,
        "gapRange": [round(low, 2), round(high, 2)],
        "excludedNotOnRoster": int(len(forecasts) - len(players)),
        "trend": trend,
        "seasonGames": config.REGULAR_SEASON_GAMES,
    }
