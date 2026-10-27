# Next82

**Live site: https://rarunach03.github.io/next82/**

Forecasts how many games an NBA player will play next season and explains what drives each prediction.

## Setup

```bash
brew install libomp            # macOS only, required by LightGBM
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Website

The main front end is a static React site in `web/` (Vite, TypeScript, Tailwind, Recharts).
It reads JSON exported from the forecasts, so it needs no backend and hosts free on Vercel
(`web/vercel.json` handles page routes).

```bash
python -m next82.export      # write web/public/data/ from the committed app files
cd web && npm install && npm run dev
```

`npm run build` writes the deployable site to `web/dist/`.

**Deployment.** GitHub Actions publishes the site to GitHub Pages on every push to `main`
(`.github/workflows/deploy-pages.yml`). Every morning, `refresh-data.yml` updates current
rosters and games so far, re-exports the site data, commits it if anything changed, and
redeploys. stats.nba.com sometimes blocks requests from cloud servers; if the refresh fails,
run `python -m next82.data --current && python -m next82.export` locally and push.

## Streamlit app (internal)

The original Streamlit app still works and is handy for checking the model. The files it
needs are committed, so after setup it runs straight away:

```bash
streamlit run app/streamlit_app.py
```

Link straight to a player or team with `?player=<name>` or `?team=<abbreviation>`,
e.g. `http://localhost:8501/?player=Embiid` or `http://localhost:8501/?team=IND`.

Teams are each player's current team from nba_api, saved in `data/raw/current_rosters/`.
When the saved rosters are over a day old, the Streamlit app refreshes them in the background,
so a slow or blocked nba_api never holds up a page. Rookies have no NBA history, so they're
listed without a forecast.

### During the season

Forecasts are made before the season starts and stay fixed, so they can be checked against
what actually happens. Once the season is underway, the website also shows each player's
games played so far (finished games only). To update rosters and games so far, then the site:

```bash
python -m next82.data --current
python -m next82.export
```

## Rebuild the forecasts

```bash
python -m next82.data        # download raw data from nba_api (~6 min, skips files already present)
python -m next82.features    # build data/processed/player_seasons.parquet
python -m next82.train       # evaluate models, train final models, write the app files (~1 min)
python -m next82.in_season   # rest-of-season model: snapshots, validation, test, models/in_season.txt (~2 min)
python -m next82.fantasy     # fantasy prior (last 3 seasons) and the shrinkage choice
python -m next82.export      # export JSON for the website
```

The latest season moves forward automatically: a season counts as finished from May 1, so
from May 2027 the pipeline downloads 2026-27 and forecasts 2027-28. Until it's rerun, the app
shows a warning that newer data is available. Set `NEXT82_LAST_SEASON=2025` to pin a season.

## How it works

- **Data:** regular-season stats, bios and game logs for 1996-97 to 2025-26 (30 seasons).
- **Target:** next season's games played as a share of the schedule, so the shortened
  lockout and COVID seasons (1998-99, 2011-12, 2019-20, 2020-21) compare fairly. A player who misses the whole next season
  and returns later counts as 0. Players who never return are dropped.
- **Missed seasons:** a season a player sits out entirely gets its own row (0 games), so the
  model learns what happens in comeback years. Rotation players who sat out the latest season
  (e.g. Tyrese Haliburton, Damian Lillard) get a comeback forecast.
- **Comeback forecasts:** comeback seasons split into "played a lot" and "barely played", so a
  single number lands in between. Comeback players instead get two forecasts: the chance of a
  setback (fewer than 20 of 82 games, from a classifier) and games if healthy (from a model trained
  only on seasons without a setback), plus a list of the most similar past comebacks.
- **Features (27):** age, experience, size, games and minutes played, usage, and absences
  estimated by matching game logs to team schedules (longest absence, 10+ game absences,
  games missed at the start/end of the season), the last 1-3 seasons of history, and comeback
  inputs (games in the last season played, average of the last 3 seasons played, age × missed season).
- **Models:** "same as last year" and 3-year-average baselines, ridge regression, LightGBM
  (main forecast), plus a LightGBM setback classifier and if-healthy model for comebacks.
- **Evaluation:** train on 1996-97 to 2022-23, test on 2023-24 and 2024-25. Model settings and
  which features to keep were chosen on 2022-23 as a validation season, so the test seasons are
  only used to report accuracy. Comeback models are tested season by season from 2000-01, each
  season predicted using only earlier seasons.
- **Explanations:** SHAP values from LightGBM, shown in games.

## Results

Test seasons (2023-24 and 2024-25), average error in games:

| Model | All players | Rotation players |
|---|---|---|
| Same as last year | 17.8 | 16.8 |
| 3-year average | 17.2 | 16.3 |
| Linear regression | 15.6 | 14.9 |
| **LightGBM** | **15.6** | **14.7** |

Rotation players: 15+ minutes per game and at least a quarter of their team's games.

Comeback seasons (524 from 2000-01 on, 69% were setbacks):

| | Result |
|---|---|
| Games if healthy, average error | 15.1 games (main model: 30.8) |
| Setback chance, AUC | 0.69 (0.5 = coin flip) |
| Setback chance, Brier score | 0.194 (guessing the overall rate: 0.215) |

The setback chances are roughly calibrated: recalibrating them (isotonic, sigmoid, or a
comeback-only correction) didn't improve them when tested on earlier seasons.

## Layout

```
data/raw/          raw pulls from nba_api (gitignored); current_rosters/ (committed)
data/processed/    player_seasons.parquet (gitignored); forecasts, history and
                   past_comebacks .parquet (committed, used by the app)
models/            lightgbm.joblib (gitignored), metrics.json (committed)
notebooks/         exploration
src/next82/
  config.py        paths, seasons, settings
  data.py          nba_api collection
  features.py      modeling table
  models.py        baselines, linear regression, LightGBM
  evaluate.py      time-based split, MAE in games
  explain.py       SHAP factors with readable labels
  train.py         evaluation + final models + forecasts
  export.py        JSON for the website
web/               React website (src/), exported data (public/data/, committed)
app/               Streamlit app (internal)
.streamlit/        app theme
.github/workflows/ runs the tests on every push
tests/             app tests run on the committed files; data tests skip without the full data
```

## Limitations

- nba_api has no injury data. Absences are inferred from game logs, so rest days,
  suspensions and falling out of the rotation look the same as injuries.
- Forecasts assume the player is in the league next season.
- The main model is only about 2 games more accurate than "same as last year" (15.6 vs 17.8).
  Without injury data, much of a player's availability can't be predicted.
- Comeback forecasts can't see injury type, medical clearance or team plans, and "missed a
  season" includes players who were unsigned or playing overseas.
