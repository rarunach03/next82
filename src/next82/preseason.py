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
from next82.train import FORECASTS_PATH

PRESEASON_PATH = config.PROCESSED_DIR / f"preseason_{config.FORECAST_SEASON}.parquet"


def freeze(source=FORECASTS_PATH, dest=PRESEASON_PATH):
    """Copy the current forecasts to the frozen file. Refuses to overwrite it."""
    if dest.exists():
        raise FileExistsError(f"{dest.name} is frozen and can't be overwritten")
    shutil.copyfile(source, dest)
    return dest


def load_forecasts() -> pd.DataFrame:
    """The preseason forecasts: the frozen copy if there is one, else the latest training output."""
    return pd.read_parquet(PRESEASON_PATH if PRESEASON_PATH.exists() else FORECASTS_PATH)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--freeze", action="store_true", help="freeze the current forecasts")
    if parser.parse_args().freeze:
        print(f"Froze {freeze().relative_to(config.ROOT)}")


if __name__ == "__main__":
    main()
