# Next82

**Live site: https://rarunach03.github.io/next82/**

Next82 forecasts how many games every NBA player will play this season (2026-27), explains
what drives each number, and turns it into fantasy basketball rankings.

## What's on the site

- **Preseason forecast.** Games each player will play this season, made before opening night
  (Oct 20, 2026) and frozen. It never changes, so it can be graded honestly. Each forecast
  comes with the factors behind it, in games. Players coming back from a missed season get two
  numbers instead: games if healthy, and the chance of a setback (fewer than 20 games).
- **Updated forecast.** Refreshed every day during the season: games played so far plus a fresh
  prediction for the games left. If a player gets hurt in November, this number drops; the
  preseason one doesn't.
- **Likely ranges.** Both forecasts show a likely range (10th to 90th percentile). On past
  seasons, 80% of real outcomes landed inside these ranges, and ranges are wide early in the
  season and narrow as it goes on.
- **Availability tiers.** Safe, Moderate or Risky, from the low end of the updated forecast's
  range: Safe if even a bad outcome is 45+ games, Risky if it's under 20. Only for players in a
  rotation role, since a bench player's games depend more on the coach than on health.
- **Fantasy rankings.** Per-game production (this season blended with the last three, so a hot
  start doesn't take over) times forecast games, measured above replacement level (the
  156th-best player per game, roughly the best free agent). Rest-of-season value by default,
  full-season as a second view; ESPN points, Yahoo points and 9-category leagues. Rookies are
  ranked once they've played 5 games.
- **Accuracy page.** The frozen preseason forecast graded every day against games played so far,
  next to two simple guesses, with an honest "too early to tell" while the gap could be luck.

## How accurate is it?

| Forecast | Tested on | Average miss | Best simple guess |
|---|---|---|---|
| Preseason forecast (full season) | 2023-24, 2024-25 | 15.6 games | 17.2 (3-season average) |
| Updated forecast (rest of season) | 2024-25, 2025-26 | 7.6 games | 8.1 (pace/preseason blend) |
| Updated forecast, players currently out 5+ games | 2024-25, 2025-26 | 6.6 games | 7.6 (current pace) |
| Comeback players, games if healthy | 2000-01 to 2022-23 | 15.3 games | 23.4 (3-season average) |

Settings and feature choices were made on separate validation seasons, so the test seasons
only measure accuracy. Half of preseason forecasts land within 11 games.

## Setup

```bash
brew install libomp            # macOS only, required by LightGBM
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
cd web && npm install && cd ..
```

Everything the website needs is committed, so after setup this runs straight away:

```bash
cd web && npm run dev          # http://localhost:5173
```

## Rebuild everything from scratch

```bash
python -m next82.data          # download 30 seasons + current rosters, games so far, draft (~6 min)
python -m next82.features      # player-season table
python -m next82.train         # preseason models, accuracy tests, forecasts and ranges (~1 min)
python -m next82.preseason --freeze --freeze-ranges   # freeze them; once per season, before opening night
python -m next82.in_season     # updated-forecast model: snapshots, validation, test (~2 min)
python -m next82.fantasy       # fantasy prior and how much to shrink this season's stats
python -m next82.rookies       # rookie baseline by draft range, shrinkage and games method
python -m next82.export        # write the website's data (web/public/data/)
pytest                         # tests
```

The frozen files (`data/processed/preseason_*.parquet`) can't be overwritten; delete them only
when starting a new season. The latest finished season moves forward on its own each May 1;
until the pipeline is rerun, the site says newer data is available. Set
`NEXT82_LAST_SEASON=2025` to pin a season.

## Daily updates

`scripts/refresh.sh` downloads current rosters, this season's game logs and the draft order,
runs `python -m next82.export` (updated forecasts, ranges, tiers, fantasy values including
rookies, accuracy), and commits and pushes if anything changed. Each push redeploys the site
through GitHub Actions (`.github/workflows/deploy-pages.yml`).

The refresh runs on a home computer, not in the cloud: stats.nba.com doesn't respond to cloud
servers. On the project's Mac a launchd job runs it every morning at 8am from a separate copy of
the repo (macOS doesn't let background jobs into the Desktop folder). Run it by hand any time:

```bash
./scripts/refresh.sh
```

## How it works

- **Data:** regular-season stats, bios and game logs for 1996-97 to 2025-26 from stats.nba.com
  via nba_api, plus this season's games. There's no public injury data, so long absences come
  from matching each player's game log against their team's schedule.
- **Preseason model** (`train.py`): LightGBM on 12,300 past player-seasons. The target is the
  share of the schedule played, so shortened seasons compare fairly. 27 inputs: age, experience,
  minutes, games played in each of the last three seasons, long absences, games missed at the
  start or end of a season, and comeback inputs. SHAP values explain each forecast.
- **Updated forecast** (`in_season.py`): trained on snapshots of every player every 14 days
  through 26 past seasons, each using only games before its date. Inputs add games played and
  missed so far, the current absence streak, recent games and team games left.
- **Ranges** (`intervals.py`): LightGBM quantile models, corrected on a validation season so 80%
  of outcomes land inside; the updated forecast's correction is set separately for each third of
  the season.
- **Fantasy** (`fantasy.py`, `rookies.py`): per-game stats from the last three seasons weighted
  3:2:1, blended with this season's as (season totals + 6 × prior per game) / (games + 6). The 6
  was chosen on a validation season. Rookies are blended with past rookies from their draft range
  (weight 3), and their games come from the updated-forecast model.
- **Accuracy** (`accuracy.py`): each player's games so far against what their forecast implied for
  that many team games, with a resampled 95% range for the gap to the best simple guess.

## Layout

```
src/next82/
  config.py        paths, seasons, cutoffs
  data.py          nba_api downloads (history, rosters, games so far, draft)
  features.py      player-season table
  models.py        baselines, ridge regression, LightGBM, quantile models
  train.py         preseason models, evaluation, forecasts and ranges
  preseason.py     freezing and loading the preseason forecast
  in_season.py     updated (rest-of-season) forecast
  intervals.py     likely ranges, calibration, availability tiers
  fantasy.py       per-game production, scoring, value above replacement
  rookies.py       rookie baseline and rankings
  accuracy.py      grading the preseason forecast during the season
  explain.py       SHAP factors with readable labels
  export.py        the website's data (the only way data reaches the site)
web/               React site (Vite, TypeScript, Tailwind, Recharts); data in public/data/
scripts/           refresh.sh (daily update)
data/, models/     committed: frozen forecasts, current-season data, LightGBM models (text format)
app/               the original Streamlit app (internal)
tests/             pytest; tests needing the full downloaded data skip themselves
```

## Limitations

- No injury reports: rest, benchings, suspensions and unsigned seasons all look like absences.
- Forecasts assume the player is in the league. Players not on a roster who haven't played get
  no updated forecast.
- The preseason edge over simple guessing is real but modest (15.6 vs 17.2 games).
- Comeback forecasts can't see injury type or medical clearance.

## Next up (on hold)

- **Phase 5: injury type.** Research reliable sources for the official NBA injury report and
  historical injury logs, and their terms of use, before building anything. Then use current
  injury status in the updated forecast and test body-region and repeat-injury features, keeping
  them only if validation error improves.
- **Phase 6: fantasy tools.** A "who to stash" list (labeled "long absence" until injury data
  lands), a trade analyzer comparing rest-of-season value, and back-to-back counts for players
  often rested, with each player's rest rate shrunk toward the league average.
