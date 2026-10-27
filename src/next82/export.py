"""Export the forecasts as JSON for the website (web/).

Reads the small committed app files, so it runs without the full dataset:
    web/public/data/index.json         meta, teams, and a summary row per player
    web/public/data/players/<id>.json  one player's factors, history and similar comebacks

Usage:
    python -m next82.export
"""
import json
import math
import shutil
import unicodedata
from datetime import datetime

import numpy as np
import pandas as pd

from next82 import (accuracy, auto_overrides, back_to_back, config, data, evaluate, fantasy, in_season, injuries,
                    overrides, rookies)
from next82.intervals import tier
from next82.explain import GAMES, similar_comebacks, top_factors
from next82.preseason import load_forecasts, load_ranges
from next82.train import HISTORY_PATH, METRICS_PATH, PAST_COMEBACKS_PATH

OUT_DIR = config.ROOT / "web" / "public" / "data"


def next_season(season: str) -> str:
    start = int(season[:4]) + 1
    return f"{start}-{str(start + 1)[-2:]}"


def plain(text: str) -> str:
    """Accent-free lowercase text for search: 'Nikola Jokić' -> 'nikola jokic'."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def clean(value):
    """JSON-safe values: NaN -> None, numpy numbers -> Python numbers."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(obj), ensure_ascii=False, separators=(",", ":"), allow_nan=False))


def player_history(history: pd.DataFrame, seasons: list[str], player_id: int) -> list[dict]:
    """Games per season from the player's first season on; seasons with no record were missed."""
    h = history[history.PLAYER_ID == player_id].set_index("SEASON")
    h = h.reindex(seasons[seasons.index(h.index.min()):])
    season_length = history.groupby("SEASON").season_games.max()
    return [
        {"season": s, "games": int(r.GP) if pd.notna(r.GP) else 0,
         "seasonGames": int(season_length[s]), "missed": pd.isna(r.GP)}
        for s, r in h.iterrows()
    ]


OUT_COLUMNS = ["out_reason", "out_status", "out_injury", "out_report_url", "out_games_after_return"]


def out_info(forecasts: pd.DataFrame, team_ids: pd.Series, today: pd.Timestamp) -> pd.DataFrame:
    """Who's out right now and why, for the stash list:
        out_reason  'injury report' (listed Out on his team's latest report),
                    'long absence, no report' (5+ straight team games missed, not listed),
                    or the override kind ('manual', 'automatic', 'news')
    plus the report's status and reason, and team games left after an expected return."""
    out = pd.DataFrame({"PLAYER_ID": forecasts.PLAYER_ID})
    for c in OUT_COLUMNS:
        out[c] = None
    log = injuries.saved_log()
    listing = auto_overrides.current_listings(log).set_index("PLAYER_ID") if log is not None and len(log) else None
    schedule = data.saved_schedule()
    for i, r in forecasts.iterrows():
        pid = r.PLAYER_ID
        # Listed Out with an injury (not a G League assignment, rest, illness or personal reasons).
        listed = (listing is not None and pid in listing.index and listing.loc[pid, "status"] == "Out"
                  and listing.loc[pid, "injury_type"] not in auto_overrides.NOT_AN_INJURY)
        long_absence = r.has_played == 1 and pd.notna(r.absence_streak) and r.absence_streak >= in_season.OUT_STREAK_GAMES
        if isinstance(r.override_kind, str):
            reason = r.override_kind
        elif listed:
            reason = "injury report"
        elif long_absence:
            reason = "long absence, no report"
        else:
            continue
        games_after = None
        if pd.notna(r.override_earliest) and schedule is not None and pd.notna(r.team_games_left):
            games_after = overrides.games_from(team_ids.get(pid), pd.Timestamp(r.override_earliest), today, schedule,
                                               r.team_games_left)
        row = listing.loc[pid] if listed else None
        out.loc[i, OUT_COLUMNS] = [reason, row.status if row is not None else None,
                                   injuries.clean_reason(row.reason) if row is not None else None,
                                   row.report_url if row is not None else None, games_after]
    return out


def no_tier_reason(r) -> str | None:
    """Why a player has no availability tier (None if they have one or no forecast):
    'comeback' (missed all of last season), 'missed' (rotation minutes but under the
    share of games a rotation role needs, usually from injuries) or 'bench' (fewer
    minutes than a rotation role)."""
    if isinstance(r.tier, str) or pd.isna(r.updated_total):
        return None
    if r.missed_season == 1:
        return "comeback"
    mpg = r.mpg if pd.notna(r.mpg) else r.mpg_lag1
    return "missed" if pd.notna(mpg) and mpg >= config.ROTATION_MIN_MPG else "bench"


def regular_season_end() -> str | None:
    schedule = data.saved_schedule()
    if schedule is None or schedule.empty:
        return None
    return str(pd.to_datetime(schedule.GAME_DATE.astype(str).str[:10]).max().date())


def out_json(r) -> dict | None:
    """Currently out: why, the report's status and reason, and games after an expected return."""
    if not isinstance(r.out_reason, str):
        return None
    return {
        "reason": r.out_reason, "status": r.out_status, "injury": r.out_injury, "reportUrl": r.out_report_url,
        "gamesAfterReturn": None if r.out_games_after_return is None or pd.isna(r.out_games_after_return)
        else round(float(r.out_games_after_return), 1),
    }


def back_to_back_info(forecasts: pd.DataFrame, team_ids: pd.Series, today: pd.Timestamp) -> pd.DataFrame:
    """PLAYER_ID, b2b_left (team second nights from today) and b2b_rate (shrunk rest rate)."""
    schedule = data.saved_schedule()
    out = pd.DataFrame({"PLAYER_ID": forecasts.PLAYER_ID, "b2b_left": np.nan, "b2b_rate": np.nan})
    if schedule is None or not back_to_back.RATES_PATH.exists():
        return out
    league = json.loads(back_to_back.METRICS_PATH.read_text())["league_rate"]
    rates = pd.read_parquet(back_to_back.RATES_PATH).set_index("PLAYER_ID").rate
    left = back_to_back.remaining_back_to_backs(schedule, today)
    out["b2b_left"] = out.PLAYER_ID.map(team_ids).map(left)
    out["b2b_rate"] = out.PLAYER_ID.map(rates).fillna(league)
    return out


def override_json(r) -> dict | None:
    """A manual injury adjustment for the site, or None."""
    if not isinstance(r.override_status, str):
        return None
    day = lambda d: str(pd.Timestamp(d).date()) if d is not None and pd.notna(d) else None
    return {
        "status": r.override_status,
        "note": r.override_note,
        # manual (data/overrides.csv), automatic (injury report + recovery table) or news (team timeline)
        "kind": r.override_kind if isinstance(r.override_kind, str) else "manual",
        "sourceUrl": r.override_source,
        "sourceUrl2": r.override_source_2 if isinstance(r.override_source_2, str) else None,
        "estimated": bool(r.override_estimated),
        "dateAdded": day(r.override_added),
        "reviewBy": day(r.override_review_by),
        "earliestReturn": day(r.override_earliest),
        "latestReturn": day(r.override_latest),
        "indefinite": bool(r.override_indefinite),
        # A team timeline that's a re-evaluation date: shown as "re-evaluation around <date>".
        "reevaluation": bool(r.override_reevaluation == True),  # noqa: E712 (None when not set)
        # Past its review-by date: the site flags it so it can't be missed.
        "needsReview": bool(r.override_kind == "manual" and r.override_review_by is not None and pd.notna(r.override_review_by)
                            and pd.Timestamp(r.override_review_by) < pd.Timestamp.today().normalize()),
    }


def in_season_accuracy() -> dict:
    """Test-season accuracy of the rest-of-season model and its best baseline, if trained."""
    if not in_season.METRICS_PATH.exists():
        return {}
    card = json.loads(in_season.METRICS_PATH.read_text())["test"]["all"]
    baselines = {k: v for k, v in card.items() if k not in ("n", "Rest-of-season model")}
    best = min(baselines, key=baselines.get)
    return {
        "updatedMae": round(card["Rest-of-season model"], 1),
        "updatedBestBaseline": best,
        "updatedBestBaselineMae": round(baselines[best], 1),
    }


def write_accuracy(rosters: pd.DataFrame | None):
    """accuracy.json: the frozen preseason forecast graded against games so far."""
    logs = data.saved_season_logs()
    if rosters is None or logs is None:
        return
    graded = accuracy.season_accuracy(load_forecasts(), rosters, *logs)
    if graded is not None:
        metrics = json.loads(METRICS_PATH.read_text())
        graded["testSeasons"] = {
            "seasons": metrics["test_seasons"],
            "model": round(metrics["results"][metrics["final_model"]]["mae_all"], 1),
            "bestBaseline": round(min(metrics["results"][k]["mae_all"] for k in ("Same as last year", "3-year average")), 1),
        }
        write_json(OUT_DIR / "accuracy.json", graded)


def write_fantasy(forecasts: pd.DataFrame, target: str, rosters: pd.DataFrame | None):
    """fantasy.json: per-game production and forecast games for ranked players.

    Ranked: players with an updated forecast (on a roster, or with games this
    season), and rookies once they've played rookies.MIN_GAMES games. Everyone is
    scored together (one 9-cat pool, one replacement level). The site multiplies
    per-game value by games and ranks in the browser.
    """
    ranked = forecasts[forecasts.updated_total.notna()].set_index("PLAYER_ID")
    per_game = fantasy.player_values(ranked)
    if per_game.empty:
        return
    veterans = ranked.join(per_game[fantasy.STATS], how="inner").assign(rookie=False, draft_range=None)
    veterans["team"] = veterans.TEAM_ABBREVIATION_NOW
    veterans["no_tier_reason"] = [no_tier_reason(r) for r in veterans.itertuples()]
    rookie_rows = rookies.current_rookies(rosters, forecasts.PLAYER_ID) if rosters is not None else pd.DataFrame()
    if not rookie_rows.empty:
        rookie_rows = rookie_rows.assign(rookie=True, tier=None, no_tier_reason="rookie", team=rookie_rows.TEAM_ABBREVIATION,
                                         updated_low=None, updated_high=None, b2b_left=np.nan, b2b_rate=np.nan,
                                         **{c: None for c in OUT_COLUMNS},
                                         **{c: None for c in overrides.OUTPUT})
    cols = ["PLAYER_NAME", "team", "tier", "no_tier_reason", "rookie", "draft_range", "played_so_far", "team_games_left",
            "predicted_rest", "updated_total", "updated_low", "updated_high", "b2b_left", "b2b_rate",
            *OUT_COLUMNS, *overrides.OUTPUT, *fantasy.STATS]
    rows = pd.concat([veterans[cols], rookie_rows[cols]] if not rookie_rows.empty else [veterans[cols]])
    rows = rows.join(fantasy.score(rows[fantasy.STATS])[["espn", "yahoo", *[f"z_{c}" for c in [*fantasy.CATEGORIES, "total"]]]])

    k = json.loads(fantasy.METRICS_PATH.read_text())["shrink_k"]
    rookie_k = json.loads(rookies.METRICS_PATH.read_text())["shrink_k"] if rookies.METRICS_PATH.exists() else None
    replacement = fantasy.replacement_levels(rows.rename(columns={"z_total": "cat9"}))
    players = []
    for pid, r in rows.iterrows():
        players.append({
            "id": int(pid),
            "name": r.PLAYER_NAME,
            "team": r.team if pd.notna(r.team) else None,
            "tier": r.tier if isinstance(r.tier, str) else None,
            "noTierReason": r.no_tier_reason if isinstance(r.no_tier_reason, str) else None,
            "rookie": bool(r.rookie),
            "draftRange": r.draft_range,
            "override": override_json(r),
            "b2bLeft": None if pd.isna(r.b2b_left) else int(r.b2b_left),
            "b2bRate": None if pd.isna(r.b2b_rate) else round(float(r.b2b_rate), 3),
            "out": out_json(r),
            "playedSoFar": None if pd.isna(r.played_so_far) else int(r.played_so_far),
            "gamesLeft": int(r.team_games_left),
            "restGames": round(float(r.predicted_rest), 1),
            # Likely range of rest-of-season games (none for rookies yet).
            "restLow": None if pd.isna(r.updated_low) else round(float(r.updated_low - r.played_so_far), 1),
            "restHigh": None if pd.isna(r.updated_high) else round(float(r.updated_high - r.played_so_far), 1),
            "seasonGames": round(float(r.updated_total), 1),
            "perGame": {"espn": round(float(r.espn), 2), "yahoo": round(float(r.yahoo), 2), "cat9": round(float(r.z_total), 2)},
            "cats": {c: round(float(r[f"z_{c}"]), 2) for c in fantasy.CATEGORIES},
            "stats": {s: round(float(r[s]), 1) for s in ["MIN", "PTS", "REB", "AST", "STL", "BLK", "FG3M", "TOV"]}
            | {"FG%": round(float(r.FGM / r.FGA), 3) if r.FGA else None, "FT%": round(float(r.FTM / r.FTA), 3) if r.FTA else None},
        })
    write_json(OUT_DIR / "fantasy.json", {
        "season": target,
        "shrinkGames": k,
        "rookieShrinkGames": rookie_k,
        "rookieMinGames": rookies.MIN_GAMES,
        "poolSize": fantasy.POOL_SIZE,
        # Per-game score of the 156th-best player per game; values are measured above it.
        "replacement": {fmt: round(v, 3) for fmt, v in replacement.items()},
        "scoring": fantasy.POINTS,
        "players": players,
    })


def current_rotation_role(player_ids: pd.Series) -> pd.Series:
    """A rotation role this season: 15+ minutes per game across at least a quarter
    of the team's games, once the team has played 5+ games."""
    logs = data.saved_season_logs()
    if logs is None or logs[0].empty:
        return pd.Series(False, index=player_ids.index)
    player_games, team_games = logs
    team_count = team_games.groupby("TEAM_ID").size()
    last_team = player_games.sort_values("GAME_DATE").groupby("PLAYER_ID").TEAM_ID.last()
    totals = player_games.groupby("PLAYER_ID").agg(games=("GAME_ID", "size"), minutes=("MIN", "sum"))
    team_games_played = last_team.map(team_count)
    role = (
        (totals.minutes / totals.games >= config.ROTATION_MIN_MPG)
        & (totals.games / team_games_played >= config.ROTATION_MIN_GP_SHARE)
        & (team_games_played >= 5)
    )
    return player_ids.map(role).fillna(False).astype(bool)


def round_or_none(value, digits=1):
    return None if pd.isna(value) else round(float(value), digits)


def main():
    forecasts = load_forecasts()
    history = pd.read_parquet(HISTORY_PATH)
    past = pd.read_parquet(PAST_COMEBACKS_PATH)
    metrics = json.loads(METRICS_PATH.read_text())

    current = forecasts.SEASON.iloc[0]
    target = next_season(current)
    seasons = sorted(history.SEASON.unique())
    rosters = data.saved_rosters(target)
    so_far = data.saved_season_to_date(target)

    if rosters is not None:
        now = rosters[["PLAYER_ID", "TEAM_ABBREVIATION", "TEAM_FULL_NAME"]].rename(
            columns={"TEAM_ABBREVIATION": "TEAM_ABBREVIATION_NOW"}
        )
        forecasts = forecasts.merge(now, on="PLAYER_ID", how="left")
    else:
        forecasts["TEAM_ABBREVIATION_NOW"] = None
        forecasts["TEAM_FULL_NAME"] = None

    # Games played so far this season (the forecasts were made before it started).
    if so_far is not None:
        played, team_games = so_far
        forecasts = forecasts.merge(played[["PLAYER_ID", "GP"]].rename(columns={"GP": "played_so_far"}), on="PLAYER_ID", how="left")
        forecasts["played_so_far"] = forecasts.played_so_far.fillna(0)
        team_so_far = dict(zip(team_games.TEAM_ABBREVIATION, team_games.GAMES))
        forecasts["team_games_so_far"] = forecasts.TEAM_ABBREVIATION_NOW.map(team_so_far)
        if not forecasts.TEAM_ABBREVIATION_NOW.isna().all():
            # Teams that haven't played yet have 0 games, not missing.
            forecasts.loc[forecasts.TEAM_ABBREVIATION_NOW.notna(), "team_games_so_far"] = (
                forecasts.loc[forecasts.TEAM_ABBREVIATION_NOW.notna(), "team_games_so_far"].fillna(0)
            )
        season_started = not team_games.empty
        so_far_through = team_games.LAST_GAME.iloc[0] if season_started else None
    else:
        forecasts["played_so_far"] = None
        forecasts["team_games_so_far"] = None
        season_started, so_far_through = False, None

    # Likely ranges (10th-90th percentile) of the frozen preseason forecast.
    ranges = load_ranges()
    if ranges is not None:
        forecasts = forecasts.merge(ranges, on="PLAYER_ID", how="left")
    else:
        forecasts["low_games"] = forecasts["high_games"] = None

    # Rest-of-season forecast: games so far + predicted games still to come.
    updated = in_season.predict_current()
    updated_as_of = None
    updated_cols = ["updated_total", "predicted_rest", "team_games_left", "absence_streak", "has_played",
                    "updated_low", "updated_high"]
    if updated is not None:
        updated_as_of = updated.as_of.iloc[0]
        cols = ["PLAYER_ID", *[c for c in updated_cols if c in updated]]
        forecasts = forecasts.merge(updated[cols], on="PLAYER_ID", how="left")
    for c in updated_cols:
        if c not in forecasts:
            forecasts[c] = None
    # Not on a roster and no games this season: an updated forecast would just assume
    # they sign somewhere, so the site says "Not on a roster" instead.
    forecasts["not_on_roster"] = forecasts.TEAM_ABBREVIATION_NOW.isna()
    unsigned = forecasts.not_on_roster & (forecasts.played_so_far.fillna(0) == 0)
    forecasts.loc[unsigned, updated_cols] = None

    # Manual injury adjustments (data/overrides.csv), applied before tiers and fantasy
    # values so both use them. The accuracy page and test metrics never see them.
    manual = overrides.load()
    today = updated.as_of.iloc[0] + pd.Timedelta(days=1) if updated is not None else pd.Timestamp.today().normalize()
    for o in overrides.overdue(manual, pd.Timestamp.today().normalize()).itertuples():
        print(f"WARNING: override for {o.player_name} is past its review-by date ({o.review_by.date()}); update data/overrides.csv")
    team_ids = rosters.set_index("PLAYER_ID").TEAM_ID if rosters is not None else pd.Series(dtype=float)
    # Automatic overrides from the injury report and team timelines from news. Manual rows
    # win, except over a news row found after the manual row was added.
    manual_used, automatic, auto_log = auto_overrides.current(manual, today)
    for line in auto_log:
        print(line)
    combined = manual_used.assign(kind="manual")
    if len(automatic):
        combined = pd.concat([combined, automatic], ignore_index=True)
    forecasts = overrides.apply(forecasts, combined, data.saved_schedule(), today, team_ids)

    # Back-to-backs: each team's remaining second nights and each player's rest rate.
    # Shown on the site; not added to the forecast (it didn't improve validation).
    forecasts = forecasts.merge(back_to_back_info(forecasts, team_ids, today), on="PLAYER_ID", how="left")
    forecasts = forecasts.merge(out_info(forecasts, team_ids, today), on="PLAYER_ID", how="left")
    # Availability tier: only for players in a rotation role (for bench players a low
    # range mostly reflects coaching decisions, not health), and only from the updated
    # forecast, whose Safe tier proved honest on test seasons (preseason ranges can't
    # reliably pick out players almost sure to play 45+ games).
    forecasts["rotation_role"] = evaluate.has_rotation_role(forecasts) | current_rotation_role(forecasts.PLAYER_ID)
    forecasts["tier"] = [
        tier(lo) if role else None for lo, role in zip(forecasts.updated_low, forecasts.rotation_role)
    ]

    comeback = forecasts.missed_season == 1
    forecasts["shown"] = forecasts.games_if_healthy.where(comeback, forecasts.pred_games)
    # Search suggestions list the best-known players first: minutes in their last season played.
    recent_mpg = forecasts.mpg.fillna(forecasts.mpg_lag1)
    forecasts["recent_minutes"] = (recent_mpg * forecasts.last_played_gp_share * GAMES).fillna(0)
    forecasts = forecasts.sort_values("shown", ascending=False)

    players = []
    if (OUT_DIR / "players").exists():
        shutil.rmtree(OUT_DIR / "players")
    for _, r in forecasts.iterrows():
        is_comeback = bool(r.missed_season)
        summary = {
            "id": int(r.PLAYER_ID),
            "name": r.PLAYER_NAME,
            "search": plain(r.PLAYER_NAME),
            "team": r.TEAM_ABBREVIATION_NOW if pd.notna(r.TEAM_ABBREVIATION_NOW) else None,
            "lastTeam": r.TEAM_ABBREVIATION,
            "age": int(r.age),
            "games": int(r.GP),
            "seasonGames": int(r.season_games),
            "comeback": is_comeback,
            "forecast": round_or_none(r.pred_games),
            "ifHealthy": round_or_none(r.games_if_healthy) if is_comeback else None,
            "setbackChance": round_or_none(r.p_setback, 3) if is_comeback else None,
            "shown": round_or_none(r.shown),
            "recentMinutes": round(float(r.recent_minutes)),
            "playedSoFar": None if pd.isna(r.played_so_far) else int(r.played_so_far),
            "teamGamesSoFar": None if pd.isna(r.team_games_so_far) else int(r.team_games_so_far),
            "updated": round_or_none(r.updated_total),
            "updatedRest": round_or_none(r.predicted_rest),
            "gamesLeft": None if pd.isna(r.team_games_left) else int(r.team_games_left),
            # Team games since the player's last game, once they've played this season.
            "absenceStreak": int(r.absence_streak) if pd.notna(r.absence_streak) and r.has_played == 1 else None,
            "preLow": round_or_none(r.low_games, 0),
            "preHigh": round_or_none(r.high_games, 0),
            "updatedLow": round_or_none(r.updated_low, 0),
            "updatedHigh": round_or_none(r.updated_high, 0),
            "tier": r.tier,
            "rotationRole": bool(r.rotation_role),
            "noTierReason": no_tier_reason(r),
            "notOnRoster": bool(r.not_on_roster),
            "override": override_json(r),
            "out": out_json(r),
            # Back-to-back second nights the team has left, and how often the player sits them.
            "b2bLeft": None if pd.isna(r.b2b_left) else int(r.b2b_left),
            "b2bRate": None if pd.isna(r.b2b_rate) else round(float(r.b2b_rate), 3),
        }
        players.append(summary)

        factors = top_factors(r)
        detail = summary | {
            "teamName": r.TEAM_FULL_NAME if pd.notna(r.TEAM_FULL_NAME) else None,
            "factorBase": round(float(r.shap_base), 1),
            "factors": [
                {"label": f.factor, "value": f.value, "games": round(float(f.impact_games), 2)}
                for f in factors.itertuples()
            ],
            "history": player_history(history, seasons, r.PLAYER_ID),
            "similar": [
                {"name": s.player, "seasonMissed": s.missed, "age": int(s.age), "before": s.before,
                 "comebackGames": int(s.comeback_games)}
                for s in similar_comebacks(r, past).itertuples()
            ] if is_comeback else [],
        }
        write_json(OUT_DIR / "players" / f"{int(r.PLAYER_ID)}.json", detail)

    write_fantasy(forecasts, target, rosters)
    write_accuracy(rosters)

    teams = []
    if rosters is not None:
        forecast_ids = set(forecasts.PLAYER_ID)
        for (abbr, name), roster in rosters.groupby(["TEAM_ABBREVIATION", "TEAM_FULL_NAME"]):
            teams.append({
                "abbr": abbr,
                "name": name,
                "noForecast": sorted(roster.loc[~roster.PLAYER_ID.isin(forecast_ids), "PLAYER_NAME"]),
            })
        teams.sort(key=lambda t: t["name"])

    results = metrics["results"]
    model_mae = results[metrics["final_model"]]["mae_all"]
    best_baseline = min(("Same as last year", "3-year average"), key=lambda k: results[k]["mae_all"])
    write_json(OUT_DIR / "index.json", {
        "meta": {
            "forecastSeason": target,
            "dataThrough": current,
            "previousSeason": seasons[-2],
            "latestFinishedSeason": config.SEASONS[-1],
            "rostersAsOf": rosters.FETCHED_AT.iloc[0].isoformat() if rosters is not None else None,
            "seasonStarted": season_started,
            "soFarThrough": str(so_far_through)[:10] if so_far_through is not None else None,
            "updatedAsOf": str(updated_as_of)[:10] if updated_as_of is not None else None,
            # Last day of this regular season, so the site can say "out for the season".
            "regularSeasonEnd": regular_season_end(),
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
            "games": GAMES,
            "setbackGames": config.SETBACK_GAMES,
            "tierSafeLow": config.TIER_SAFE_LOW,
            "b2bLeagueRate": (round(json.loads(back_to_back.METRICS_PATH.read_text())["league_rate"], 3)
                              if back_to_back.METRICS_PATH.exists() else None),
            "accuracy": {
                "modelMae": round(model_mae, 1),
                "modelMedianError": round(results[metrics["final_model"]]["median_error_all"], 1),
                "shareWithin16": round(results[metrics["final_model"]]["share_within_16"], 2),
                "bestBaseline": best_baseline,
                "bestBaselineMae": round(results[best_baseline]["mae_all"], 1),
                "comebackHealthyMae": round(metrics["comeback"]["mae_healthy_two_part"], 1),
                "testSeasons": metrics["test_seasons"],
                **in_season_accuracy(),
            },
        },
        "teams": teams,
        "players": players,
    })
    size = sum(p.stat().st_size for p in OUT_DIR.rglob("*.json"))
    where = OUT_DIR.relative_to(config.ROOT) if OUT_DIR.is_relative_to(config.ROOT) else OUT_DIR
    print(f"Exported {len(players)} players and {len(teams)} teams to {where} ({size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
