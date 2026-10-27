"""Project-wide paths and settings."""
import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MODELS_DIR = ROOT / "models"



def last_completed_season(today: date | None = None) -> int:
    """Start year of the latest finished regular season.

    The regular season ends in mid-April, so a season counts as finished from May 1:
    on 2026-10-19 that's 2025 (2025-26); from 2027-05-01 it's 2026 (2026-27).
    """
    today = today or date.today()
    return today.year - 1 if today.month >= 5 else today.year - 2


# Seasons to collect, in nba_api format ("2015-16"). The last one moves forward
# automatically each May; set NEXT82_LAST_SEASON (e.g. 2025) to pin it.
FIRST_SEASON = 1996
LAST_SEASON = int(os.environ.get("NEXT82_LAST_SEASON", last_completed_season()))
SEASONS = [f"{y}-{str(y + 1)[-2:]}" for y in range(FIRST_SEASON, LAST_SEASON + 1)]

# The season being forecast. Current rosters (who plays where now) come from this season.
FORECAST_SEASON = f"{LAST_SEASON + 1}-{str(LAST_SEASON + 2)[-2:]}"
# Refresh current rosters from nba_api at most this often.
ROSTER_MAX_AGE_HOURS = 24

# Most recent seasons held out for testing (time-based split).
N_TEST_SEASONS = 2

# Seconds between nba_api requests to avoid rate limiting.
REQUEST_DELAY = 0.6

RANDOM_STATE = 42

# Rotation players: a meaningful role in a season. Used for reporting error and
# for deciding who gets a comeback forecast after sitting out the latest season.
ROTATION_MIN_MPG = 15
ROTATION_MIN_GP_SHARE = 0.25

# A "setback" season: playing fewer than this many games out of 82. Comeback
# forecasts show the chance of a setback plus the expected games if healthy.
SETBACK_GAMES = 20

# Length of a normal regular season. Used for the season in progress, whose
# schedule may still list some games as undecided (e.g. NBA Cup knockout games).
REGULAR_SEASON_GAMES = 82
