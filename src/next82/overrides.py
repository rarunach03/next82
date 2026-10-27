"""Manual injury adjustments to the updated forecast (data/overrides.csv).

The model can't read injury news, so a known long absence (e.g. surgery) is entered
by hand: status, an optional return window, a note and a source. For those players
the updated forecast becomes games played so far + the model's predicted share of
the team's games from the return window onward:
    high end    from the earliest return (with the model's high-end share)
    low end     from the latest return (with the model's low-end share); 0 more games
                if the latest return isn't known (the absence could be season-ending)
    point       from the middle of the window; if the latest return isn't known, the
                middle of the range (a return exactly at the earliest date is the best case)
No window at all means "Out indefinitely": the range runs from 0 more games to the
model's high end, and the point (used for fantasy value) is its middle.

`estimated` marks an earliest return that's our own estimate (e.g. from typical
recovery times), not a team timeline; the site says so. `source_url_2` is optional.

Overrides change only what the site shows today: the preseason forecast, the
accuracy page and the model's test metrics never use them.
"""
import pandas as pd

from next82 import config, intervals

PATH = config.ROOT / "data" / "overrides.csv"
COLUMNS = ["player_id", "player_name", "status", "earliest_return", "latest_return", "estimated", "note",
           "source_url", "source_url_2", "date_added", "review_by"]
DATE_COLUMNS = ["earliest_return", "latest_return", "date_added", "review_by"]
OUTPUT = ["override_status", "override_note", "override_source", "override_source_2", "override_added",
          "override_review_by", "override_earliest", "override_latest", "override_indefinite", "override_estimated",
          "override_kind"]


def load(path=None) -> pd.DataFrame:
    """The overrides, with dates parsed (blank = unknown). Reads PATH by default."""
    path = path or PATH
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path, dtype={"player_id": int})
    missing = set(COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"{path.name} is missing columns: {sorted(missing)}")
    for c in DATE_COLUMNS:
        df[c] = pd.to_datetime(df[c], errors="raise")
    df["estimated"] = df.estimated.fillna("").astype(str).str.strip().str.lower().isin(["yes", "true", "1", "y"])
    df["source_url_2"] = pd.Series(
        [u.strip() if isinstance(u, str) and u.strip() else None for u in df.source_url_2], index=df.index, dtype=object
    )
    return df


def overdue(overrides: pd.DataFrame, today: pd.Timestamp) -> pd.DataFrame:
    """Overrides past their review-by date."""
    return overrides[overrides.review_by.notna() & (overrides.review_by < today)]


def games_from(team_id, date: pd.Timestamp, today: pd.Timestamp, schedule: pd.DataFrame, games_left: float) -> float:
    """Team games on or after `date` (never before today), scaled so that from today
    it equals `games_left` (the schedule can still be missing undecided games)."""
    team = schedule[schedule.TEAM_ID == team_id].GAME_DATE
    remaining = (team >= today).sum()
    if remaining == 0:
        return 0.0
    return float((team >= max(date, today)).sum() * games_left / remaining)


def apply(forecasts: pd.DataFrame, overrides: pd.DataFrame, schedule: pd.DataFrame | None, today: pd.Timestamp,
          team_ids: pd.Series) -> pd.DataFrame:
    """Updated forecast with overrides applied (see module docstring).

    forecasts: PLAYER_ID, played_so_far, team_games_left, predicted_rest, updated_total,
               updated_low, updated_high.
    team_ids:  current TEAM_ID by PLAYER_ID.
    """
    out = forecasts.copy()
    for c in OUTPUT:
        out[c] = None
    for o in overrides.itertuples():
        rows = out.index[out.PLAYER_ID == o.player_id]
        if rows.empty:
            print(f"Override for unknown player {o.player_id} ({o.player_name}): skipped")
            continue
        i = rows[0]
        r = out.loc[i]
        if pd.isna(r.predicted_rest) or pd.isna(r.team_games_left) or r.team_games_left <= 0:
            continue
        played, left = r.played_so_far, r.team_games_left
        share = r.predicted_rest / left
        low_share = (r.updated_low - played) / left if pd.notna(r.updated_low) else share
        high_share = (r.updated_high - played) / left if pd.notna(r.updated_high) else share
        earliest, latest = o.earliest_return, o.latest_return
        if pd.isna(earliest) and pd.notna(latest):
            earliest = today
        indefinite = pd.isna(earliest)

        def games(date):
            if schedule is None:
                return left  # no schedule: can't place the return window
            return games_from(team_ids.get(o.player_id), date, today, schedule, left)

        if indefinite:
            low = played
            high = played + high_share * left
            point = (low + high) / 2
        elif pd.notna(latest):
            point = played + share * games(earliest + (latest - earliest) / 2)
            high = played + high_share * games(earliest)
            low = played + low_share * games(latest)
        else:
            high = played + high_share * games(earliest)
            low = played
            point = (low + high) / 2
        low, high = intervals.tidy(low, point, high, floor=played, ceiling=played + left)
        out.loc[i, ["updated_total", "predicted_rest", "updated_low", "updated_high"]] = [
            point, point - played, float(low), float(high)]
        out.loc[i, OUTPUT] = [o.status, o.note, o.source_url, o.source_url_2, o.date_added, o.review_by,
                              earliest if not indefinite else None, latest, indefinite,
                              bool(o.estimated) and not indefinite, getattr(o, "kind", "manual")]
    return out
