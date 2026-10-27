"""Automatic news search for injury timelines, with Claude Code in non-interactive mode.

Every NEWS_EVERY_DAYS days (sooner if a new player is listed Out with a serious injury
type), Claude Code searches the news for team-announced or major-outlet timelines for
players listed Out on the injury report or with a manual or automatic override. It
runs in a temporary folder that holds only a copy of data/news_timelines.csv, with
web search, web fetch and reading/editing that one file as its only tools (no shell,
no other files, no git). Its rows are then validated here: right columns, a player we
asked about, valid dates after the injury, a source URL that resolves. Valid rows go
into data/news_timelines.csv; rejected ones are logged. refresh.sh commits.

The state (last run date, which players were listed and how) is kept in
.git/next82-news-state.json, so it never reaches GitHub.

Usage:
    python -m next82.news            # run if it's due
    python -m next82.news --force    # run anyway
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests

from next82 import auto_overrides, config, data, injuries, overrides

STATE_PATH = config.ROOT / ".git" / "next82-news-state.json"
NEWS_EVERY_DAYS = 3
RECENT_ROW_DAYS = 7            # skip players with a news row this recent, unless their status changed
TIMEOUT_SECONDS = 25 * 60
MAX_BUDGET_USD = 10
NEWS_FILE = "data/news_timelines.csv"
TOOLS = "WebSearch,WebFetch,Read,Edit"
ALLOWED = ["WebSearch", "WebFetch", f"Read(./{NEWS_FILE})", f"Edit(./{NEWS_FILE})"]


# ---------------------------------------------------------------- schedule

def load_state(path: Path = STATE_PATH) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def signature(status, reason) -> str:
    """What counts as 'status changed' for a player: his report status and reason."""
    return f"{status or ''} | {reason or ''}"


def due(state: dict, today: pd.Timestamp, serious_out: set[int], force: bool = False) -> tuple[bool, str]:
    """Whether to run today, and why."""
    if force:
        return True, "forced"
    if not state.get("last_run"):
        return True, "first run"
    days = (today - pd.Timestamp(state["last_run"])).days
    if days >= NEWS_EVERY_DAYS:
        return True, f"{days} days since the last run"
    new = serious_out - set(state.get("serious_out", []))
    if new:
        return True, f"new player(s) listed Out with a serious injury: {sorted(new)}"
    return False, f"last run {days} day(s) ago; no new serious injuries"


# ---------------------------------------------------------------- inputs

def players_to_check(today: pd.Timestamp) -> pd.DataFrame:
    """Players listed Out on the latest report, plus anyone with a manual or automatic
    override: id, name, team, status, reason, report day, last game, override."""
    log = injuries.saved_log()
    manual = overrides.load()
    manual_used, automatic, _ = auto_overrides.current(manual, today)
    rows = {}
    if log is not None and len(log):
        listed = auto_overrides.current_listings(log)
        # Out with an injury: G League assignments, illness, rest, personal reasons and suspensions are left out.
        out = listed[(listed.status == "Out") & listed.PLAYER_ID.notna() & ~listed.injury_type.isin(auto_overrides.NOT_AN_INJURY)]
        for r in out.itertuples():
            rows[int(r.PLAYER_ID)] = {"player_id": int(r.PLAYER_ID), "player_name": r.player_name, "team": r.team,
                                      "status": r.status, "reason": injuries.clean_reason(r.reason),
                                      "injury_type": r.injury_type, "body_part": r.body_part, "report_day": r.report_day}
    for o in pd.concat([manual.assign(kind="manual"), automatic], ignore_index=True).itertuples():
        pid = int(o.player_id)
        row = rows.setdefault(pid, {"player_id": pid, "player_name": o.player_name, "team": None, "status": None,
                                    "reason": None, "injury_type": None, "body_part": None,
                                    "report_day": pd.NaT})
        row.update(override_kind=o.kind, override_earliest=o.earliest_return, override_latest=o.latest_return,
                   override_note=o.note, override_source=o.source_url)
    out = pd.DataFrame(list(rows.values()))
    if out.empty:
        return out
    logs = data.saved_season_logs()
    before = pd.read_parquet(auto_overrides.LAST_GAME_PATH) if auto_overrides.LAST_GAME_PATH.exists() else None
    out["last_game"] = out.player_id.map(auto_overrides.last_games(logs[0] if logs is not None else None, before))
    return out


def serious_out(players: pd.DataFrame) -> set[int]:
    """Players listed Out with an injury type that has a recovery-table estimate."""
    if players.empty:
        return set()
    recovery = auto_overrides.load_recovery()
    listed = players[players.status == "Out"]
    return {int(p.player_id) for p in listed.itertuples()
            if auto_overrides.recovery_row(recovery, p.injury_type, p.body_part) is not None}


def select(players: pd.DataFrame, news: pd.DataFrame, state: dict, today: pd.Timestamp) -> pd.DataFrame:
    """Drop players with a news row from the last RECENT_ROW_DAYS days, unless their status changed."""
    if players.empty:
        return players
    recent = news[news.date_found >= today - pd.Timedelta(days=RECENT_ROW_DAYS)].player_id.dropna().astype(int)
    before = state.get("players", {})
    keep = [p.player_id not in set(recent) or before.get(str(p.player_id)) != signature(p.status, p.reason)
            for p in players.itertuples()]
    return players[keep]


# ---------------------------------------------------------------- Claude Code

# The standalone CLI from Anthropic's native installer (https://claude.ai/install.sh).
STANDALONE_CLAUDE = Path.home() / ".local" / "bin" / "claude"


def claude_binary() -> str | None:
    """The claude CLI: $NEXT82_CLAUDE, the standalone install, PATH, then the newest copy
    bundled with the VS Code extension as a fallback."""
    if os.environ.get("NEXT82_CLAUDE"):
        return os.environ["NEXT82_CLAUDE"]
    if os.access(STANDALONE_CLAUDE, os.X_OK):
        return str(STANDALONE_CLAUDE)
    found = shutil.which("claude")
    if found:
        return found
    bundled = glob.glob(os.path.expanduser("~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude"))
    version = lambda p: [int(x) for x in p.split("claude-code-")[1].split("-")[0].split(".")]
    return max(bundled, key=version) if bundled else None


def command(binary: str, prompt: str) -> list[str]:
    """Non-interactive run limited to web search, web fetch and reading/editing the news file."""
    return [binary, "-p", prompt,
            "--restricted",                       # no shell or code tools; ignores user/project settings
            "--strict-mcp-config",                # no MCP servers
            "--tools", TOOLS,
            "--allowedTools", *ALLOWED,
            "--permission-mode", "dontAsk",       # anything not allowed above is denied
            "--permission-prompts", "none",
            "--no-session-persistence",
            "--max-budget-usd", str(MAX_BUDGET_USD),
            "--output-format", "json"]


def season_end() -> pd.Timestamp:
    schedule = data.saved_schedule()
    return pd.to_datetime(schedule.GAME_DATE.astype(str).str[:10]).max() if schedule is not None else pd.NaT


def prompt(players: pd.DataFrame, today: pd.Timestamp, last_regular_season_day: pd.Timestamp) -> str:
    day = lambda d: f"{pd.Timestamp(d):%Y-%m-%d}" if d is not None and pd.notna(d) else ""
    lines = []
    for p in players.itertuples():
        override = getattr(p, "override_kind", None)
        lines.append(" | ".join([
            str(p.player_id), p.player_name, p.team or "", p.status or "not listed", p.reason or "",
            day(p.report_day), day(p.last_game),
            f"{override}: earliest {day(p.override_earliest)}, latest {day(p.override_latest) or 'none'}"
            if isinstance(override, str) else "",
        ]))
    after_season = day(last_regular_season_day + pd.Timedelta(days=1)) if pd.notna(last_regular_season_day) else ""
    rejected = auto_overrides.load_rejected()
    rejected_text = ("Never use these sources, which were rejected:\n" + "\n".join(
        f"  {r.source_url} ({r.reason})" for r in rejected.itertuples()) + "\n") if len(rejected) else ""
    return f"""Today is {day(today)}. You keep the injury timelines file for an NBA forecasting site.

Task: for each player below, search the news for a return timeline that the team announced or that a
major outlet (ESPN, The Athletic, NBA.com, team websites, AP, Yahoo Sports, Bleacher Report, a team beat
reporter) reported, such as "out 6-8 weeks", "will be re-evaluated in 4 weeks" or "out for the season".
Only add a row when a dated source clearly states a timeline for this injury. Never guess, estimate or
infer a timeline. If you find nothing clear for a player, add nothing for that player.

Edit the file {NEWS_FILE} (read it first). Add one row per player with a timeline, or replace that
player's existing row if the new source is more recent. Don't touch other rows. Columns:
  player_id        the id from the list below
  earliest_return  YYYY-MM-DD: date of announcement + the shortest stated time (re-evaluation date counts)
  latest_return    YYYY-MM-DD: date of announcement + the longest stated time; blank if none stated
  note             the timeline in plain words, citing the outlet and date, e.g. "Out 6-8 weeks (ESPN, Oct 27)"
  source_url       the exact URL of the article or team statement that states the timeline
  date_found       {day(today)}
  source_date      YYYY-MM-DD the source was published
  timeline_type    "re-evaluation" if the source gives a date or time to re-evaluate, re-examine or check
                   again ("re-evaluated in 4 weeks"); "return" if it says when the player is expected back
                   or how long the player will be out ("out 6-8 weeks", "out for the season")
A date for a status update or check-in, with no expected return or re-evaluation, is not a timeline.
"Out for the season" means earliest_return = {after_season} (the day after the regular season ends), latest_return blank.
Quote fields containing commas. Don't create or edit any other file.
{rejected_text}
Players (id | name | team | report status | report reason | report date | last game | current estimate):
""" + "\n".join(lines) + "\n\nWhen done, reply with one line per row you added or changed (player, timeline, source)."


def run_claude(players: pd.DataFrame, today: pd.Timestamp, original: pd.DataFrame) -> tuple[pd.DataFrame | None, str]:
    """Run Claude Code in a sandbox folder with a copy of the news file; returns the edited file and its reply."""
    binary = claude_binary()
    if binary is None:
        return None, "claude CLI not found"
    with tempfile.TemporaryDirectory(prefix="next82-news-") as tmp:
        target = Path(tmp) / NEWS_FILE
        target.parent.mkdir(parents=True)
        original.to_csv(target, index=False, date_format="%Y-%m-%d")
        # If it stops early (timeout, budget, error), rows it already wrote are still validated.
        try:
            done = subprocess.run(command(binary, prompt(players, today, season_end())), cwd=tmp, capture_output=True,
                                  text=True, timeout=TIMEOUT_SECONDS, stdin=subprocess.DEVNULL)
            try:
                result = json.loads(done.stdout)
                reply = result.get("result") or ""
                if done.returncode != 0 or result.get("is_error"):
                    reply = f"stopped early ({result.get('subtype')}): {reply}"
            except ValueError:
                reply = f"claude exited with {done.returncode}: {(done.stderr or done.stdout)[-500:]}"
        except subprocess.TimeoutExpired:
            reply = f"stopped early: timed out after {TIMEOUT_SECONDS // 60} minutes"
        try:
            edited = pd.read_csv(target, dtype=str, keep_default_na=False)
        except (OSError, ValueError, pd.errors.ParserError) as e:
            return None, f"couldn't read the edited file: {e}"
    return edited, reply


# ---------------------------------------------------------------- validation

def url_resolves(url: str) -> bool:
    """The page exists: any answer but 404/410/5xx (some news sites refuse bots with 401/403/429)."""
    try:
        r = requests.get(url, headers={"User-Agent": injuries.USER_AGENT}, timeout=20, allow_redirects=True, stream=True)
        r.close()
        return r.status_code < 400 or r.status_code in (401, 403, 429)
    except requests.RequestException:
        return False


def _date(value):
    if value is None or (isinstance(value, str) and not value.strip()) or pd.isna(value):
        return pd.NaT
    return pd.to_datetime(value, format="%Y-%m-%d", errors="raise")


def changed_rows(original: pd.DataFrame, edited: pd.DataFrame) -> pd.DataFrame:
    """Rows in the edited file that aren't exactly in the original (as text)."""
    as_text = lambda df: df.astype(str).replace({"nan": "", "NaT": "", "<NA>": ""})
    before = {tuple(r) for r in as_text(original.reindex(columns=auto_overrides.NEWS_COLUMNS))
              .itertuples(index=False)}
    rows = as_text(edited)
    return rows[[tuple(r) not in before for r in rows.reindex(columns=auto_overrides.NEWS_COLUMNS)
                 .itertuples(index=False)]]


def validate(rows: pd.DataFrame, players: pd.DataFrame, today: pd.Timestamp, url_ok=url_resolves
             ) -> tuple[pd.DataFrame, list[str]]:
    """The valid rows (typed like load_news) and a reason for each rejected one."""
    if list(rows.columns) != auto_overrides.NEWS_COLUMNS:
        return pd.DataFrame(columns=auto_overrides.NEWS_COLUMNS), [
            f"wrong columns {list(rows.columns)} (expected {auto_overrides.NEWS_COLUMNS}); all rows rejected"]
    known = players.set_index("player_id")
    rejected = set(auto_overrides.load_rejected().source_url)
    good, problems = [], []
    for r in rows.itertuples(index=False):
        try:
            pid = int(r.player_id)
            if pid not in known.index:
                raise ValueError(f"player_id {r.player_id} isn't one of the players searched")
            earliest, latest = _date(r.earliest_return), _date(r.latest_return)
            found, published = _date(r.date_found), _date(r.source_date)
            if pd.isna(earliest) or pd.isna(found) or pd.isna(published):
                raise ValueError("earliest_return, date_found and source_date are required")
            if found > today or published > today:
                raise ValueError("date_found or source_date is in the future")
            injury = known.loc[pid, "last_game"]
            if pd.notna(injury) and (published < injury or earliest <= injury):
                raise ValueError(f"source or return date isn't after the injury (last game {injury:%Y-%m-%d})")
            if earliest < published:
                raise ValueError("earliest_return is before the source was published")
            if pd.notna(latest) and latest < earliest:
                raise ValueError("latest_return is before earliest_return")
            if not str(r.note).strip():
                raise ValueError("note is empty")
            if r.timeline_type not in auto_overrides.TIMELINE_TYPES:
                raise ValueError(f"timeline_type must be one of {auto_overrides.TIMELINE_TYPES}: {r.timeline_type!r}")
            if str(r.source_url).strip() in rejected:
                raise ValueError(f"source was rejected before: {r.source_url}")
            url = urlparse(str(r.source_url).strip())
            if url.scheme not in ("http", "https") or "." not in url.netloc:
                raise ValueError(f"source_url isn't a URL: {r.source_url!r}")
            if not url_ok(str(r.source_url).strip()):
                raise ValueError(f"source_url doesn't resolve: {r.source_url}")
        except (ValueError, TypeError) as e:
            problems.append(f"rejected row for {r.player_id}: {e}")
            continue
        good.append({"player_id": pid, "earliest_return": earliest, "latest_return": latest,
                     "note": str(r.note).strip(), "source_url": str(r.source_url).strip(),
                     "date_found": found, "source_date": published, "timeline_type": r.timeline_type})
    return pd.DataFrame(good, columns=auto_overrides.NEWS_COLUMNS), problems


def merge(original: pd.DataFrame, valid: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """The news file with valid rows added; a valid row replaces that player's older row."""
    lines = []
    old_ids = set(original.player_id.dropna().astype(int))
    for r in valid.itertuples():
        lines.append(f"News timeline {'changed' if r.player_id in old_ids else 'added'}: player {r.player_id}, "
                     f"earliest {r.earliest_return:%Y-%m-%d}, latest "
                     f"{'none' if pd.isna(r.latest_return) else f'{r.latest_return:%Y-%m-%d}'}: {r.note} ({r.source_url})")
    kept = original[~original.player_id.isin(valid.player_id)]
    merged = pd.concat([kept, valid], ignore_index=True) if len(kept) else valid
    return merged.reindex(columns=auto_overrides.NEWS_COLUMNS), lines


# ---------------------------------------------------------------- main

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="run even if it isn't due")
    args = parser.parse_args(argv)
    today = pd.Timestamp(os.environ.get("REFRESH_TODAY") or pd.Timestamp.today()).normalize()

    state = load_state()
    players = players_to_check(today)
    serious = serious_out(players)
    run, why = due(state, today, serious, args.force)
    if not run:
        print(f"News search: not due ({why})")
        return
    news = auto_overrides.load_news()
    todo = select(players, news, state, today)
    print(f"News search ({why}): {len(todo)} of {len(players)} players to check")
    if len(todo):
        edited, reply = run_claude(todo, today, news)
        print(f"News search reply: {reply.strip()}")
        if edited is None:
            print("News search failed: no edited file")
            raise SystemExit(1)
        valid, problems = validate(changed_rows(news, edited), todo, today)
        for line in problems:
            print(f"News search: {line}")
        merged, lines = merge(news, valid)
        if len(valid):
            merged.to_csv(auto_overrides.NEWS_PATH, index=False, date_format="%Y-%m-%d")
        for line in lines or ["News search: no new timelines"]:
            print(line)
    STATE_PATH.write_text(json.dumps({
        "last_run": f"{today:%Y-%m-%d}", "serious_out": sorted(serious),
        "players": {str(p.player_id): signature(p.status, p.reason) for p in players.itertuples()},
    }, indent=2))


if __name__ == "__main__":
    main()
