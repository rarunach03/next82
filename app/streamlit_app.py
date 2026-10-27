"""Next82 Streamlit app: search a player, see their forecast and its top factors.

Run:
    streamlit run app/streamlit_app.py
"""
import json
import unicodedata

import altair as alt
import pandas as pd
import streamlit as st

from next82 import config
from next82.explain import GAMES, similar_comebacks, top_factors
from next82.data import refresh_rosters_in_background, saved_rosters
from next82.preseason import load_forecasts
from next82.train import FORECASTS_PATH, HISTORY_PATH, METRICS_PATH, PAST_COMEBACKS_PATH

st.set_page_config(page_title="Next82", page_icon="🏀", layout="centered")

# Chart colors (validated for color-vision deficiency and contrast in both themes).
PALETTE = {
    "light": {"up": "#2a78d6", "down": "#e34948", "past": "#2a78d6", "forecast": "#86b6ef", "text": "#52514e"},
    "dark": {"up": "#3987e5", "down": "#e66767", "past": "#3987e5", "forecast": "#184f95", "text": "#c3c2b7"},
}
theme = getattr(st.context, "theme", None)
colors = PALETTE["dark" if theme is not None and theme.type == "dark" else "light"]


def next_season(season: str) -> str:
    start = int(season[:4]) + 1
    return f"{start}-{str(start + 1)[-2:]}"


def normalize(text: str) -> str:
    """Lowercase and strip accents so 'jokic' matches 'Jokić'."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


APP_FILES = [FORECASTS_PATH, HISTORY_PATH, PAST_COMEBACKS_PATH, METRICS_PATH]


@st.cache_data
def load():
    """The app's data: small files written by `python -m next82.train` and committed to git."""
    if not all(path.exists() for path in APP_FILES):
        return None, None, None, None
    forecasts = load_forecasts()
    # Comeback players are shown their if-healthy forecast plus a setback chance.
    forecasts["shown_games"] = forecasts.games_if_healthy.where(forecasts.missed_season == 1, forecasts.pred_games)
    forecasts = forecasts.sort_values("shown_games", ascending=False)
    forecasts["search"] = forecasts.PLAYER_NAME.map(normalize)
    history = pd.read_parquet(HISTORY_PATH)
    metrics = json.loads(METRICS_PATH.read_text())
    return forecasts, history, metrics, pd.read_parquet(PAST_COMEBACKS_PATH)


@st.cache_resource(ttl=3600)
def start_roster_refresh(season: str):
    """Refresh stale rosters in the background, at most once an hour. Never blocks the page."""
    refresh_rosters_in_background(season)
    return True


@st.cache_data(ttl=300)
def load_rosters(season: str):
    """The saved rosters. A background refresh replaces the file; this picks it up within 5 minutes."""
    return saved_rosters(season)


forecasts, history, metrics, past = load()
if forecasts is None:
    st.error("No forecasts found. Run `python -m next82.data`, `python -m next82.features`, then `python -m next82.train`.")
    st.stop()

# Seasons come from the data files, not today's date, so the app stays consistent
# with the forecasts it has even after a new season finishes.
current = forecasts.SEASON.iloc[0]
target_season = next_season(current)
seasons = sorted(history.SEASON.unique())
previous = seasons[-2]
mae = metrics["results"][metrics["final_model"]]["mae_all"]
comeback_eval = metrics["comeback"]
setback_games = config.SETBACK_GAMES

# Current teams: players move in the offseason, so the team shown is their team now,
# not their last-season team. Players on no roster are unsigned or retired.
start_roster_refresh(target_season)
rosters = load_rosters(target_season)
if rosters is not None:
    now = rosters[["PLAYER_ID", "TEAM_ABBREVIATION", "TEAM_FULL_NAME"]].rename(
        columns={"TEAM_ABBREVIATION": "team_now", "TEAM_FULL_NAME": "team_now_name"}
    )
    forecasts = forecasts.merge(now, on="PLAYER_ID", how="left")
else:
    forecasts = forecasts.assign(team_now=pd.NA, team_now_name=pd.NA)
forecasts["team_label"] = forecasts.team_now.fillna("No team")


def search_label(row) -> str:
    """'Name · TEAM', plus an accent-free spelling so typing 'jokic' finds 'Nikola Jokić'."""
    words = row.PLAYER_NAME.split()
    plain = [unicodedata.normalize("NFKD", w).encode("ascii", "ignore").decode() for w in words]
    changed = [p for p, w in zip(plain, words) if p != w]
    alias = f" ({' '.join(changed)})" if changed else ""
    return f"{row.PLAYER_NAME}{alias} · {row.team_label}"


forecasts["label"] = [search_label(r) for r in forecasts.itertuples()]
same = forecasts.label.duplicated(keep=False)
forecasts.loc[same, "label"] += ", age " + forecasts.loc[same, "age"].astype(int).astype(str)
# Search suggestions list the best-known players first: minutes in their last season played.
recent_mpg = forecasts.mpg.fillna(forecasts.mpg_lag1)
forecasts["recent_minutes"] = (recent_mpg * forecasts.last_played_gp_share * GAMES).fillna(0)

PLAYER_KEY = "player_label"

st.title("Next82")
st.caption(f"How many games will a player play in {target_season}? Forecasts are based on seasons through {current}.")
if config.SEASONS[-1] > current:
    st.warning(
        f"The {config.SEASONS[-1]} season has finished, but these forecasts only use data through {current}. "
        "Rerun the pipeline (see the README) to update them."
    )

ALL_TEAMS = "All teams"
team_names = sorted(rosters.TEAM_FULL_NAME.unique()) if rosters is not None else []
wanted = st.query_params.get("team", "")
by_abbr = dict(zip(rosters.TEAM_ABBREVIATION, rosters.TEAM_FULL_NAME)) if rosters is not None else {}
default_team = by_abbr.get(wanted.upper(), wanted if wanted in team_names else ALL_TEAMS)
team = st.selectbox("Team", [ALL_TEAMS, *team_names], index=([ALL_TEAMS, *team_names]).index(default_team))
if rosters is None:
    st.caption("Current rosters haven't been downloaded yet, so the team filter is unavailable.")
else:
    st.caption(f"Teams as of {rosters.FETCHED_AT.iloc[0]:%b %-d, %Y}.")
pool = forecasts if team == ALL_TEAMS else forecasts[forecasts.team_now_name == team]

options = pool.sort_values("recent_minutes", ascending=False).label.tolist()
if PLAYER_KEY not in st.session_state:
    # First load: open the player from a ?player= link, if any.
    wanted = normalize(st.query_params.get("player", ""))
    st.session_state[PLAYER_KEY] = next((o for o in options if wanted and wanted in normalize(o)), None)
if st.session_state[PLAYER_KEY] not in options:
    st.session_state[PLAYER_KEY] = None  # e.g. the team filter changed
choice = st.selectbox(
    "Search a player",
    options,
    key=PLAYER_KEY,
    placeholder="Start typing a name, e.g. LeBron or Jokic",
    filter_mode="contains",
)
player = pool[pool.label == choice].iloc[0] if choice else None


def back_to_list():
    st.session_state[PLAYER_KEY] = None
    # A fresh table key clears the old row selection, so the same row can be clicked again.
    st.session_state.table_nonce = st.session_state.get("table_nonce", 0) + 1


def played_text(gp: int, season_games: int) -> str:
    """'62 of 82'. Players traded mid-season can play more games than one team's schedule."""
    return f"{gp} of {season_games}" + (" (traded)" if gp > season_games else "")


def forecast_table(rows: pd.DataFrame, show_team: bool = True, show_all_rows: bool = False):
    """Sortable table of forecasts, highest first. Clicking a row opens that player.

    Comeback forecasts (games if healthy) get their own column so they aren't mixed
    up with regular forecasts, which already account for the risk of missing games.
    """
    returning = rows.missed_season == 1
    overview = rows.assign(
        played=[played_text(g, n) for g, n in zip(rows.GP, rows.season_games)],
        forecast=rows.pred_games.round().where(~returning),
        comeback=[
            f"{h:.0f} if healthy · {p:.0%} setback" if r else ""
            for h, p, r in zip(rows.games_if_healthy, rows.p_setback, returning)
        ],
    ).sort_values("shown_games", ascending=False)
    overview.loc[returning.reindex(overview.index), "played"] = "Missed season"
    cols = ["PLAYER_NAME", *(["team_label"] if show_team else []), "age", "played", "forecast", "comeback"]
    key = f"table_{st.session_state.get('table_nonce', 0)}"

    def open_player():
        rows_clicked = st.session_state[key].selection.rows
        if rows_clicked:
            st.session_state[PLAYER_KEY] = overview.label.iloc[rows_clicked[0]]

    st.caption("Click a row to see that player's forecast.")
    st.dataframe(
        overview[cols],
        key=key,
        on_select=open_player,
        selection_mode="single-row",
        hide_index=True,
        width="stretch",
        height=35 * (len(overview) + 1) + 3 if show_all_rows else "auto",
        column_config={
            "PLAYER_NAME": "Player",
            "team_label": "Team",
            "age": st.column_config.NumberColumn("Age", format="%d", width=40),
            "played": st.column_config.TextColumn(f"Played in {current}", width=110),
            "forecast": st.column_config.ProgressColumn(
                f"{target_season} forecast", min_value=0, max_value=GAMES, format="%d games", width=150
            ),
            "comeback": st.column_config.TextColumn(
                "Comeback",
                width=185,
                help=f"Players returning from a missed season: games if healthy, and the chance of "
                f"a setback (fewer than {config.SETBACK_GAMES} games)",
            ),
        },
    )


def factor_chart(row: pd.Series) -> alt.Chart:
    top = top_factors(row)
    top["label"] = top.factor + " · " + top.value
    top["direction"] = top.impact_games.map(lambda v: "Adds games" if v >= 0 else "Costs games")
    top["impact_text"] = top.impact_games.map(lambda v: f"{v:+.1f}")
    order = top.label.tolist()
    reach = max(top.impact_games.abs().max(), 1) * 1.25

    # Each row: factor name on top, bar below, so long names don't squeeze the bars on phones.
    y = alt.Y("label:N", sort=order, title=None, axis=None)
    x_scale = alt.Scale(domain=[-reach, reach], nice=False)
    base = alt.Chart(top).encode(y=y)
    bars = base.mark_bar(cornerRadiusEnd=4, height=14, yOffset=9).encode(
        x=alt.X("impact_games:Q", title="Effect on forecast (games)", scale=x_scale),
        color=alt.Color(
            "direction:N",
            scale=alt.Scale(domain=["Adds games", "Costs games"], range=[colors["up"], colors["down"]]),
            legend=alt.Legend(title=None, orient="top"),
        ),
        tooltip=[
            alt.Tooltip("factor:N", title="Factor"),
            alt.Tooltip("value:N", title="Value"),
            alt.Tooltip("impact_text:N", title="Effect (games)"),
        ],
    )
    names = base.mark_text(align="left", baseline="bottom", dy=-2, fontSize=13, color=colors["text"]).encode(
        x=alt.datum(-reach, scale=x_scale), text="label:N"
    )
    text = dict(x=alt.X("impact_games:Q"), text="impact_text:N")
    up_labels = base.transform_filter("datum.impact_games >= 0").mark_text(
        align="left", dx=6, yOffset=9, color=colors["text"]
    ).encode(**text)
    down_labels = base.transform_filter("datum.impact_games < 0").mark_text(
        align="right", dx=-6, yOffset=9, color=colors["text"]
    ).encode(**text)
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(opacity=0.4).encode(x=alt.X("x:Q", scale=x_scale))
    return (bars + names + up_labels + down_labels + zero).properties(height=alt.Step(52))


def history_chart(row: pd.Series) -> alt.Chart:
    h = history[history.PLAYER_ID == row.PLAYER_ID].set_index("SEASON")
    # Seasons after a player's first appearance with no record were missed entirely.
    h = h.reindex(seasons[seasons.index(h.index.min()):])
    h["SEASON"] = h.index
    h["GP"] = h.GP.fillna(0)
    h["season_games"] = h.season_games.fillna(GAMES)
    h["kind"] = "Played"
    h["note"] = h.GP.astype(int).astype(str) + " of " + h.season_games.astype(int).astype(str)
    h.loc[h.GP == 0, "note"] = "Missed season"

    label = "Forecast if healthy" if row.missed_season else "Forecast"
    fc = pd.DataFrame({
        "SEASON": [f"{target_season}"],
        "GP": [round(row.shown_games)],
        "kind": ["Forecast"],
        "note": [f"{label}: {row.shown_games:.0f} of {GAMES}"],
    })
    data = pd.concat([h[["SEASON", "GP", "kind", "note"]], fc], ignore_index=True)

    x = alt.X("SEASON:N", title=None, sort=None, axis=alt.Axis(labelAngle=0))
    missed = alt.Chart(data[data.note == "Missed season"]).mark_text(
        text="Missed", baseline="bottom", dy=-4, fontSize=11, color=colors["text"]
    ).encode(x=x, y=alt.Y("GP:Q"))
    bars = alt.Chart(data).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=x,
        y=alt.Y("GP:Q", title="Games played", scale=alt.Scale(domain=[0, GAMES])),
        color=alt.Color(
            "kind:N",
            scale=alt.Scale(domain=["Played", "Forecast"], range=[colors["past"], colors["forecast"]]),
            legend=alt.Legend(title=None, orient="top"),
        ),
        tooltip=[alt.Tooltip("SEASON:N", title="Season"), alt.Tooltip("note:N", title="Games")],
    )
    return (bars + missed).properties(height=260)


if player is not None:
    st.button(f"← Back to {team}" if team != ALL_TEAMS else "← All players", on_click=back_to_list)
    team_now_name = player.team_now_name if pd.notna(player.team_now_name) else "No team"
    st.subheader(f"{player.PLAYER_NAME} · {team_now_name}")
    if pd.isna(player.team_now):
        st.caption(f"Not on an NBA roster right now. Last team: {player.TEAM_ABBREVIATION} ({current}).")
    elif player.team_now != player.TEAM_ABBREVIATION:
        st.caption(f"Played for {player.TEAM_ABBREVIATION} in {current}.")

    comeback = bool(player.missed_season)
    c1, c2, c3 = st.columns(3)
    if comeback:
        c1.metric(f"{target_season} if healthy", f"{player.games_if_healthy:.0f} games")
        c2.metric("Chance of a setback", f"{player.p_setback:.0%}", help=f"Playing fewer than {setback_games} of {GAMES} games.")
        c3.metric("Age", f"{player.age:.0f}")
        st.info(
            f"{player.PLAYER_NAME} didn't play in {current}. Players returning from a missed season tend to either "
            f"play a lot or barely play, so instead of one number this shows two: the forecast if they stay healthy, "
            f"and the chance of a setback (fewer than {setback_games} games). "
            f"Based on {comeback_eval['n']} past comeback seasons.",
            icon="ℹ️",
        )
        st.caption(
            f"Out of {GAMES} games. For past comebacks, the if-healthy forecast was off by about "
            f"{comeback_eval['mae_healthy_two_part']:.0f} games on average."
        )
    else:
        change = f"{player.pred_games - player.gp_share * GAMES:+.0f} vs. {current}"
        c1.metric(f"{target_season} forecast", f"{player.pred_games:.0f} games", change)
        c2.metric(f"Played in {current}", played_text(player.GP, player.season_games))
        c3.metric("Age", f"{player.age:.0f}")
        st.caption(f"Out of {GAMES} games. Forecasts are off by about {mae:.0f} games on average, so treat this as a range, not an exact count.")

    st.markdown("#### What's driving the forecast" + (" if healthy" if comeback else ""))
    who = "healthy comeback" if comeback else "player"
    st.caption(
        f"The average {who} is forecast at {player.shap_base:.0f} games. "
        "Each bar shows how much one factor moves this player's forecast up or down."
    )
    st.altair_chart(factor_chart(player), width="stretch")

    if comeback:
        st.markdown("#### Similar past comebacks")
        st.caption("Players with a similar age and role who missed a season (for any reason), and how many games they played when they came back.")
        st.dataframe(
            similar_comebacks(player, past),
            hide_index=True,
            width="stretch",
            column_config={
                "player": "Player",
                "missed": "Season missed",
                "age": st.column_config.NumberColumn("Age", format="%d"),
                "before": "Season before",
                "comeback_games": st.column_config.ProgressColumn(
                    "Comeback season", min_value=0, max_value=GAMES, format="%d games"
                ),
            },
        )

    st.markdown("#### Games played by season")
    st.altair_chart(history_chart(player), width="stretch")

elif team != ALL_TEAMS:
    st.markdown(f"#### {team}: {target_season} forecasts")
    forecast_table(pool, show_team=False, show_all_rows=True)
    no_forecast = rosters[(rosters.TEAM_FULL_NAME == team) & ~rosters.PLAYER_ID.isin(forecasts.PLAYER_ID)]
    if len(no_forecast):
        st.caption(
            f"No forecast yet: {', '.join(sorted(no_forecast.PLAYER_NAME))}. Forecasts need NBA games in "
            f"{previous} or {current}, so rookies aren't included."
        )

else:
    st.markdown(f"#### All {target_season} forecasts")
    forecast_table(forecasts)
