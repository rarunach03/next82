"""The frozen preseason forecast for the season being forecast.

Forecasts are made before the season starts and must never change afterwards: the
website shows them as the "Preseason forecast" and the accuracy page grades them.
`python -m next82.train` keeps writing data/processed/forecasts.parquet, but the
website and app read the frozen copy made here.

Usage (once per season, before opening night):
    python -m next82.preseason --freeze
"""
import argparse
import shutil

import pandas as pd

from next82 import config
from next82.train import FORECASTS_PATH, RANGES_PATH

PRESEASON_PATH = config.PROCESSED_DIR / f"preseason_{config.FORECAST_SEASON}.parquet"
# Likely ranges for the preseason forecast. Added after the point forecasts were
# frozen, but computed from preseason data only, and frozen the same way.
PRESEASON_RANGES_PATH = config.PROCESSED_DIR / f"preseason_ranges_{config.FORECAST_SEASON}.parquet"


def freeze(source=FORECASTS_PATH, dest=PRESEASON_PATH):
    """Copy the current forecasts to the frozen file. Refuses to overwrite it."""
    if dest.exists():
        raise FileExistsError(f"{dest.name} is frozen and can't be overwritten")
    shutil.copyfile(source, dest)
    return dest


def load_forecasts() -> pd.DataFrame:
    """The preseason forecasts: the frozen copy if there is one, else the latest training output."""
    return pd.read_parquet(PRESEASON_PATH if PRESEASON_PATH.exists() else FORECASTS_PATH)


def load_ranges() -> pd.DataFrame | None:
    """Likely ranges for the preseason forecasts (frozen copy first). None if not built."""
    for path in (PRESEASON_RANGES_PATH, RANGES_PATH):
        if path.exists():
            return pd.read_parquet(path)
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--freeze", action="store_true", help="freeze the current forecasts")
    parser.add_argument("--freeze-ranges", action="store_true", help="freeze the forecasts' likely ranges")
    args = parser.parse_args()
    if args.freeze:
        print(f"Froze {freeze().relative_to(config.ROOT)}")
    if args.freeze_ranges:
        print(f"Froze {freeze(RANGES_PATH, PRESEASON_RANGES_PATH).relative_to(config.ROOT)}")


if __name__ == "__main__":
    main()
