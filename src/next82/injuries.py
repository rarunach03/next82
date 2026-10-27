"""The NBA's official injury report: fetch, parse, classify, match to players.

The league publishes the report as a PDF every 15 minutes during the season at
ak-static.cms.nba.com/referee/injury/Injury-Report_YYYY-MM-DD_HH_MMAM.pdf (older
seasons: ..._05PM.pdf). We download it politely (one report per refresh, a
descriptive User-Agent, a delay between tries), keep only the parsed facts (player,
status, reason, body part, injury type, report time, report URL) and never store
or re-host the PDF. Reasons we can't classify, and names we can't match, are
logged, not guessed.
"""
import io
import re
import time
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pdfplumber
import requests

from next82 import config

BASE_URL = "https://ak-static.cms.nba.com/referee/injury/Injury-Report_"
USER_AGENT = "Next82 student project (unofficial, non-commercial; https://github.com/rarunach03/next82)"
EASTERN = ZoneInfo("America/New_York")
STATUSES = ["Out", "Doubtful", "Questionable", "Probable", "Available"]

# Injury types, checked in order; each is (type, words that indicate it).
INJURY_TYPES = [
    ("ACL", ["acl", "anterior cruciate"]),
    ("Achilles", ["achilles"]),
    ("labrum", ["labrum", "labral"]),
    ("meniscus", ["menisc"]),
    ("fracture", ["fracture", "broken"]),
    ("surgery", ["surgery", "repair", "reconstruction"]),
    ("sprain", ["sprain"]),
    ("strain", ["strain"]),
    ("soreness", ["soreness", "sore", "tightness", "contusion", "bruise", "spasm", "inflammation", "tendinitis",
                  "tendonitis", "tendinopathy", "impingement", "discomfort", "irritation"]),
    ("illness", ["illness", "respiratory", "gastro", "flu", "virus", "covid"]),
    ("rest", ["rest", "injury management", "load management"]),
    ("personal", ["personal"]),
    ("suspension", ["suspension", "suspended"]),
]
# Achilles soreness or tendinitis isn't a rupture: only these words make it the serious type.
ACHILLES_SERIOUS = ["tear", "torn", "rupture", "repair", "surgery"]
NOT_INJURY = ["g league", "two-way", "not with team", "on assignment", "league assignment"]


def report_url(when: datetime) -> str:
    """URL of the report published at `when` (Eastern time), this season's naming."""
    return f"{BASE_URL}{when:%Y-%m-%d_%I_%M%p}.pdf"


def legacy_report_url(day, hour_pm: int = 5) -> str:
    """Older seasons' naming, e.g. Injury-Report_2023-11-01_05PM.pdf."""
    return f"{BASE_URL}{pd.Timestamp(day):%Y-%m-%d}_{hour_pm:02d}PM.pdf"


def get(url: str) -> bytes | None:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    return r.content if r.status_code == 200 and r.content[:4] == b"%PDF" else None


def fetch_latest(now: datetime | None = None, tries: int = 8, delay: float = 1.0) -> tuple[str, datetime, bytes] | None:
    """The most recent report: the latest quarter hour before now, stepping back if it's not up yet."""
    now = (now or datetime.now(EASTERN)).astimezone(EASTERN)
    when = now.replace(minute=now.minute - now.minute % 15, second=0, microsecond=0)
    for _ in range(tries):
        url = report_url(when)
        pdf = get(url)
        if pdf is not None:
            return url, when, pdf
        when -= timedelta(minutes=15)
        time.sleep(delay)
    return None


# ---------------------------------------------------------------- parsing

def _columns(words) -> dict | None:
    """Column start positions from the header row."""
    header = [w for w in words if w["text"] in ("Game", "Matchup", "Team", "Player", "Current", "Reason")]
    if not header:
        return None
    top = min(w["top"] for w in header)
    row = sorted((w for w in header if abs(w["top"] - top) < 3), key=lambda w: w["x0"])
    names = {"Matchup": "matchup", "Team": "team", "Player": "player", "Current": "status", "Reason": "reason"}
    cols = {names[w["text"]]: w["x0"] for w in row if w["text"] in names}
    return {"top": top, **cols} if {"team", "player", "status", "reason"} <= set(cols) else None


def parse_report(pdf: bytes) -> pd.DataFrame:
    """Rows of the report: team, player name ('Last, First'), status, reason.

    The PDF is read word by word with positions: columns come from the header, each
    row is anchored on the player name, and reason text (which wraps onto lines
    above and below the row) goes to the nearest player row.
    """
    rows, team, cols = [], None, None
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        for page in doc.pages:
            words = page.extract_words(x_tolerance=1.5, y_tolerance=2)
            header = _columns(words)
            if header is not None:
                cols = header
                body_top = header["top"] + 5
            elif cols is not None:
                # Later pages repeat the title but not the column headers; columns stay put.
                body_top = min((w["top"] for w in words if w["text"] == "Report:"), default=40) + 15
            else:
                continue
            order = ["team", "player", "status", "reason"]
            starts = sorted((cols[c], c) for c in order) + ([(cols["matchup"], "matchup")] if "matchup" in cols else [])
            starts.sort()

            def column(x):
                name = None
                for start, c in starts:
                    if x >= start - 2:
                        name = c
                return name

            body = [w for w in words if w["top"] > body_top and not w["text"].startswith("Page")]
            lines: dict[tuple[str, int], list] = {}
            for w in body:
                c = column(w["x0"])
                if c in order:
                    key = (c, round(w["top"] / 3))
                    lines.setdefault(key, []).append(w)
            text = {k: (sum(w["top"] for w in ws) / len(ws), " ".join(w["text"] for w in sorted(ws, key=lambda w: w["x0"])))
                    for k, ws in lines.items()}
            players = sorted((y, t) for (c, _), (y, t) in text.items() if c == "player")
            teams = sorted((y, t) for (c, _), (y, t) in text.items() if c == "team")
            statuses = [(y, t) for (c, _), (y, t) in text.items() if c == "status"]
            reasons = sorted((y, t) for (c, _), (y, t) in text.items() if c == "reason")
            if not players:
                continue
            assigned = {i: [] for i in range(len(players))}
            for y, t in reasons:
                if "NOT YET SUBMITTED" in t.upper():
                    continue
                i = min(range(len(players)), key=lambda i: abs(players[i][0] - y))
                if abs(players[i][0] - y) <= 14:
                    assigned[i].append(t)
            for i, (y, name) in enumerate(players):
                for ty, tt in teams:
                    if ty <= y + 3:
                        team = tt
                status = next((t for sy, t in statuses if abs(sy - y) < 4), None)
                rows.append({"team": team, "player_name": name, "status": status, "reason": _join_reason(assigned[i])})
    df = pd.DataFrame(rows, columns=["team", "player_name", "status", "reason"])
    return df[df.status.isin(STATUSES)].reset_index(drop=True)


def _join_reason(lines: list[str]) -> str:
    """Join a reason's wrapped lines. This season's reports put the injury detail on
    its own line ('Right Achilles Tendon' / 'Repair/Surgery') where older ones used ';'."""
    if not lines:
        return ""
    if len(lines) > 1 and ";" not in lines[0] and lines[0].lower().startswith("injury"):
        return f"{lines[0]}; {' '.join(lines[1:])}"
    return " ".join(lines)


def classify(reason: str) -> dict:
    """Category, side, body part and injury type from a reason like
    'Injury/Illness - Right Achilles Tendon; Repair/Surgery'. injury_type is None
    when the reason can't be classified (those are logged, not guessed)."""
    text = re.sub(r"\s+", " ", reason or "").strip()
    low = text.lower()
    if any(k in low for k in NOT_INJURY):
        return {"category": "not injury", "side": None, "body_part": None, "injury_type": "not injury"}
    detail = low.split("-", 1)[1] if "-" in low else low
    part, _, kind = detail.partition(";")
    side = next((s for s in ("left", "right") if part.strip().startswith(s)), None)
    body = part.strip()
    if side:
        body = body[len(side):].strip()
    # Match on the whole text: a phrase can wrap across the ';' we add between lines.
    whole = re.sub(r"\s+", " ", detail.replace(";", " "))
    injury_type = None
    for name, keys in INJURY_TYPES:
        if any(k in whole for k in keys):
            if name == "Achilles" and not any(k in whole for k in ACHILLES_SERIOUS):
                continue
            injury_type = name
            break
    is_injury = low.startswith("injury")
    body = None if body in ("", "n/a") or not is_injury else body
    return {"category": "injury" if is_injury else "other", "side": side if is_injury else None, "body_part": body,
            "injury_type": injury_type}


def _plain(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    name = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", name)
    return re.sub(r"[^a-z]", "", name)


def match_players(report: pd.DataFrame, rosters: pd.DataFrame) -> pd.Series:
    """PLAYER_ID for each report row ('Last, First' + team), or NaN if no unique match."""
    roster = rosters.assign(key=rosters.PLAYER_NAME.map(_plain), team_key=rosters.TEAM_FULL_NAME.map(_plain))
    by_team = {(r.team_key, r.key): r.PLAYER_ID for r in roster.itertuples()}
    by_name = roster.groupby("key").PLAYER_ID.agg(lambda s: s.iloc[0] if len(s) == 1 else None)
    ids = []
    for r in report.itertuples():
        last, _, first = r.player_name.partition(",")
        key = _plain(f"{first} {last}")
        pid = by_team.get((_plain(r.team or ""), key))
        if pid is None:
            pid = by_name.get(key)
        ids.append(pid if pid is not None else float("nan"))
    return pd.Series(ids, index=report.index)


def parsed_report(pdf: bytes, url: str, when: datetime, rosters: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Parsed, classified and matched report, plus log lines for anything left unparsed."""
    report = parse_report(pdf)
    facts = pd.concat([report, pd.DataFrame([classify(r) for r in report.reason], index=report.index)], axis=1)
    facts["PLAYER_ID"] = match_players(report, rosters)
    facts["report_time"] = pd.Timestamp(when).tz_localize(None) if pd.Timestamp(when).tzinfo else pd.Timestamp(when)
    facts["report_url"] = url
    log = [f"Injury report: unmatched player {r.player_name} ({r.team})" for r in facts[facts.PLAYER_ID.isna()].itertuples()]
    log += [f"Injury report: couldn't classify reason for {r.player_name}: {r.reason!r}"
            for r in facts[facts.injury_type.isna()].itertuples()]
    return facts, log


def paths(season: str = config.FORECAST_SEASON):
    folder = config.RAW_DIR / "current_season"
    return folder / f"injuries_{season}.parquet", folder / f"injury_log_{season}.parquet"


def saved_current(season: str = config.FORECAST_SEASON) -> pd.DataFrame | None:
    path = paths(season)[0]
    return pd.read_parquet(path) if path.exists() else None


def saved_log(season: str = config.FORECAST_SEASON) -> pd.DataFrame | None:
    path = paths(season)[1]
    return pd.read_parquet(path) if path.exists() else None


def refresh(rosters: pd.DataFrame, season: str = config.FORECAST_SEASON) -> pd.DataFrame | None:
    """Fetch the latest report, save its parsed facts, and add them to the season's log
    (one row per player per report day). Returns the facts, or None if none was found."""
    latest = fetch_latest()
    if latest is None:
        print("Injury report: no report found in the last two hours")
        return None
    url, when, pdf = latest
    facts, log = parsed_report(pdf, url, when, rosters)
    current_path, log_path = paths(season)
    current_path.parent.mkdir(parents=True, exist_ok=True)
    facts.to_parquet(current_path, index=False)
    day = facts.assign(report_day=facts.report_time.dt.normalize())
    history = saved_log(season)
    history = day if history is None else pd.concat([history[history.report_day != day.report_day.iloc[0]], day])
    history.to_parquet(log_path, index=False)
    print(f"Injury report {when:%Y-%m-%d %I:%M %p} ET: {len(facts)} players listed, "
          f"{(facts.status == 'Out').sum()} out ({url})")
    for line in log:
        print(line)
    return facts
